"""Resume Matcher API — local FastAPI application."""

from __future__ import annotations

import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from resume_matcher.ats_optimizer import ATSOptimizer
from resume_matcher.database import (
    AnalysisRecord,
    JobRecord,
    ResumeRecord,
    get_db,
    init_db,
)
from resume_matcher.generator import ResumeGenerator
from resume_matcher.job_extractor import JobDescriptionExtractor
from resume_matcher.match_analyzer import MatchAnalyzer
from resume_matcher.parser import ResumeParser
from resume_matcher.storage import FileStorage
from resume_matcher.updater import ResumeUpdater

app = FastAPI(
    title="Resume Matcher",
    description="Parse, optimize, and tailor resumes to job descriptions.",
    version="0.2.0",
)

# Initialize database on startup
init_db()

# Service instances
parser = ResumeParser()
ats_optimizer = ATSOptimizer()
job_extractor = JobDescriptionExtractor()
match_analyzer = MatchAnalyzer()
resume_updater = ResumeUpdater()
resume_generator = ResumeGenerator()
file_storage = FileStorage()


# ── Request models ──────────────────────────────────────────────


class JobInput(BaseModel):
    """Input for job description parsing."""

    url: str | None = None
    text: str | None = None


class AnalyzeRequest(BaseModel):
    """Input for gap analysis. Provide IDs or full JSON."""

    resume_id: str | None = None
    job_id: str | None = None
    resume: dict | None = None
    job: dict | None = None


class UpdateRequest(BaseModel):
    """Input for resume update."""

    resume_id: str | None = None
    resume: dict | None = None
    match_report: dict | None = None
    ats_report: dict | None = None
    analysis_id: str | None = None


class GenerateRequest(BaseModel):
    """Input for .docx generation."""

    resume: dict | None = None
    resume_id: str | None = None
    analysis_id: str | None = None


# ── Helper to look up stored records ────────────────────────────


def _get_resume_data(resume_id: str | None, resume_dict: dict | None) -> dict:
    """Resolve resume data from ID or direct JSON."""
    if resume_dict:
        return resume_dict
    if resume_id:
        db = get_db()
        try:
            record = db.query(ResumeRecord).filter_by(id=resume_id).first()
            if not record:
                raise HTTPException(404, f"Resume '{resume_id}' not found.")
            return record.get_parsed()
        finally:
            db.close()
    raise HTTPException(400, "Provide either 'resume_id' or 'resume' data.")


def _get_job_data(job_id: str | None, job_dict: dict | None) -> dict:
    """Resolve job data from ID or direct JSON."""
    if job_dict:
        return job_dict
    if job_id:
        db = get_db()
        try:
            record = db.query(JobRecord).filter_by(id=job_id).first()
            if not record:
                raise HTTPException(404, f"Job '{job_id}' not found.")
            return record.get_parsed()
        finally:
            db.close()
    raise HTTPException(400, "Provide either 'job_id' or 'job' data.")


# ── Endpoints ───────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """Upload a .docx resume and get back structured JSON.

    The parsed result is saved and a `resume_id` is returned.
    Use this ID in subsequent calls to /ats-check, /analyze, etc.
    """
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Only .docx files are supported. Please upload a Word document.",
        )

    try:
        contents = await file.read()
        result = parser.parse_bytes(contents)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to parse the document: {exc}"
        )

    parsed_dict = result.to_dict()

    # Save to database and file storage
    db = get_db()
    try:
        record = ResumeRecord(
            filename=file.filename or "resume.docx",
            parsed_json=json.dumps(parsed_dict),
            raw_text=parsed_dict.get("raw_text", ""),
        )
        db.add(record)
        db.flush()  # get the generated ID

        # Store original .docx file
        file_path = file_storage.save("uploads", record.id, contents)
        record.file_path = file_path
        db.commit()

        resume_id = record.id
    finally:
        db.close()

    return {"resume_id": resume_id, **parsed_dict}


@app.post("/ats-check")
async def ats_check(
    file: UploadFile | None = File(None),
    resume_id: str | None = Form(None),
):
    """ATS compliance check. Upload a .docx or provide a resume_id.

    Returns a score (0-100), list of issues, and heading suggestions.
    """
    if file and file.filename:
        if not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Only .docx files are supported.")
        try:
            contents = await file.read()
            parsed = parser.parse_bytes(contents)
            parsed_dict = parsed.to_dict()
        except Exception as exc:
            raise HTTPException(422, f"Failed to parse the document: {exc}")
    elif resume_id:
        parsed_dict = _get_resume_data(resume_id, None)
    else:
        raise HTTPException(400, "Provide a .docx file or a resume_id.")

    report = ats_optimizer.check(parsed_dict)
    return report.to_dict()


@app.post("/parse-job")
async def parse_job(body: JobInput):
    """Parse a job description from a URL or raw text.

    The result is saved and a `job_id` is returned for later use.
    """
    if not body.url and not body.text:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'url' or 'text' in the request body.",
        )

    try:
        if body.url:
            result = job_extractor.from_url(body.url)
        else:
            result = job_extractor.from_text(body.text)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to extract job description: {exc}"
        )

    parsed_dict = result.to_dict()

    # Save to database
    db = get_db()
    try:
        record = JobRecord(
            title=parsed_dict.get("title", ""),
            source_url=body.url or "",
            parsed_json=json.dumps(parsed_dict),
        )
        db.add(record)
        db.commit()
        job_id = record.id
    finally:
        db.close()

    return {"job_id": job_id, **parsed_dict}


@app.post("/analyze")
async def analyze(body: AnalyzeRequest):
    """Analyze how well a resume matches a job description.

    Accepts resume_id + job_id, or full JSON for both.
    Returns match score, keywords, and recommendations.
    The analysis is saved and an `analysis_id` is returned.
    """
    resume_data = _get_resume_data(body.resume_id, body.resume)
    job_data = _get_job_data(body.job_id, body.job)

    try:
        match_report = match_analyzer.analyze(resume_data, job_data)
    except Exception as exc:
        raise HTTPException(422, f"Analysis failed: {exc}")

    ats_report = ats_optimizer.check(resume_data)

    match_dict = match_report.to_dict()
    ats_dict = ats_report.to_dict()

    # Save analysis to database
    db = get_db()
    try:
        record = AnalysisRecord(
            resume_id=body.resume_id or "",
            job_id=body.job_id or "",
            match_report=json.dumps(match_dict),
            ats_report=json.dumps(ats_dict),
        )
        db.add(record)
        db.commit()
        analysis_id = record.id
    finally:
        db.close()

    return {
        "analysis_id": analysis_id,
        "match_report": match_dict,
        "ats_report": ats_dict,
    }


@app.post("/update-resume")
async def update_resume(body: UpdateRequest):
    """Update resume content to better match the job description.

    Provide analysis_id to use saved data, or pass resume + match_report directly.
    """
    if body.analysis_id:
        # Load from saved analysis
        db = get_db()
        try:
            analysis = db.query(AnalysisRecord).filter_by(id=body.analysis_id).first()
            if not analysis:
                raise HTTPException(404, f"Analysis '{body.analysis_id}' not found.")
            resume_data = _get_resume_data(analysis.resume_id or None, body.resume)
            match_data = json.loads(analysis.match_report)
            ats_data = json.loads(analysis.ats_report) if analysis.ats_report else None
        finally:
            db.close()
    else:
        resume_data = _get_resume_data(body.resume_id, body.resume)
        if not body.match_report:
            raise HTTPException(400, "Provide 'match_report' or 'analysis_id'.")
        match_data = body.match_report
        ats_data = body.ats_report

    try:
        result = resume_updater.update(resume_data, match_data, ats_data)
    except Exception as exc:
        raise HTTPException(422, f"Update failed: {exc}")

    return result.to_dict()


@app.post("/generate")
async def generate(body: GenerateRequest):
    """Generate a .docx file from resume data.

    Provide resume JSON, resume_id, or analysis_id.
    Returns a downloadable Word document.
    """
    if body.analysis_id:
        db = get_db()
        try:
            analysis = db.query(AnalysisRecord).filter_by(id=body.analysis_id).first()
            if not analysis:
                raise HTTPException(404, f"Analysis '{body.analysis_id}' not found.")
            if analysis.updated_resume_json and analysis.updated_resume_json != "{}":
                resume_data = json.loads(analysis.updated_resume_json)
            else:
                resume_data = _get_resume_data(analysis.resume_id or None, None)
        finally:
            db.close()
    else:
        resume_data = _get_resume_data(body.resume_id, body.resume)

    try:
        docx_bytes = resume_generator.generate(resume_data)
    except Exception as exc:
        raise HTTPException(422, f"Generation failed: {exc}")

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=updated_resume.docx"},
    )


@app.post("/optimize")
async def optimize(
    file: UploadFile | None = File(None),
    resume_id: str | None = Form(None),
    job_id: str | None = Form(None),
    job_url: str | None = Form(None),
    job_text: str | None = Form(None),
):
    """Full pipeline: get back an optimized .docx.

    Resume input (pick one):
      - Upload a .docx file
      - Provide `resume_id` from a previous /parse-resume call

    Job input (pick one):
      - Provide `job_url` to scrape a job posting
      - Provide `job_text` with raw job description
      - Provide `job_id` from a previous /parse-job call

    All intermediate results are saved with IDs returned in response headers.
    """
    # ── Resolve resume ──────────────────────────────────────────
    contents: bytes | None = None
    existing_resume_id: str | None = None

    if file and file.filename:
        if not file.filename.lower().endswith(".docx"):
            raise HTTPException(400, "Only .docx files are supported.")
        try:
            contents = await file.read()
            parsed_resume = parser.parse_bytes(contents)
            resume_dict = parsed_resume.to_dict()
        except Exception as exc:
            raise HTTPException(422, f"Failed to parse resume: {exc}")
    elif resume_id:
        existing_resume_id = resume_id
        resume_dict = _get_resume_data(resume_id, None)
    else:
        raise HTTPException(400, "Provide a .docx file or a resume_id.")

    # ── Resolve job description ─────────────────────────────────
    existing_job_id: str | None = None

    if job_id:
        existing_job_id = job_id
        job_dict = _get_job_data(job_id, None)
    elif job_url or job_text:
        try:
            if job_url:
                job_result = job_extractor.from_url(job_url)
            else:
                job_result = job_extractor.from_text(job_text)
            job_dict = job_result.to_dict()
        except Exception as exc:
            raise HTTPException(422, f"Failed to parse job description: {exc}")
    else:
        raise HTTPException(400, "Provide job_id, job_url, or job_text.")

    # ── Run pipeline ────────────────────────────────────────────
    ats_report = ats_optimizer.check(resume_dict).to_dict()
    match_report = match_analyzer.analyze(resume_dict, job_dict).to_dict()
    update_result = resume_updater.update(resume_dict, match_report, ats_report)

    try:
        docx_bytes = resume_generator.generate(update_result.to_dict())
    except Exception as exc:
        raise HTTPException(422, f"Failed to generate document: {exc}")

    # ── Save to database ────────────────────────────────────────
    db = get_db()
    try:
        # Resume: reuse existing or create new
        if existing_resume_id:
            rid = existing_resume_id
        else:
            resume_rec = ResumeRecord(
                filename=(file.filename if file else "resume.docx"),
                parsed_json=json.dumps(resume_dict),
                raw_text=resume_dict.get("raw_text", ""),
            )
            db.add(resume_rec)
            db.flush()
            if contents:
                file_storage.save("uploads", resume_rec.id, contents)
                resume_rec.file_path = f"uploads/{resume_rec.id}.docx"
            rid = resume_rec.id

        # Job: reuse existing or create new
        if existing_job_id:
            jid = existing_job_id
        else:
            job_rec = JobRecord(
                title=job_dict.get("title", ""),
                source_url=job_url or "",
                parsed_json=json.dumps(job_dict),
            )
            db.add(job_rec)
            db.flush()
            jid = job_rec.id

        # Analysis: always new
        analysis_rec = AnalysisRecord(
            resume_id=rid,
            job_id=jid,
            match_report=json.dumps(match_report),
            ats_report=json.dumps(ats_report),
            updated_resume_json=json.dumps(update_result.to_dict()),
        )
        db.add(analysis_rec)
        db.flush()

        output_path = file_storage.save("outputs", analysis_rec.id, docx_bytes)
        analysis_rec.output_file_path = output_path

        db.commit()
        aid = analysis_rec.id
    finally:
        db.close()

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": "attachment; filename=optimized_resume.docx",
            "X-Resume-Id": rid,
            "X-Job-Id": jid,
            "X-Analysis-Id": aid,
        },
    )


# ── Listing endpoints ───────────────────────────────────────────


@app.get("/resumes")
async def list_resumes():
    """List all saved resumes."""
    db = get_db()
    try:
        records = db.query(ResumeRecord).order_by(ResumeRecord.created_at.desc()).all()
        return [r.to_summary() for r in records]
    finally:
        db.close()


@app.get("/resumes/{resume_id}")
async def get_resume(resume_id: str):
    """Get a saved resume by ID."""
    db = get_db()
    try:
        record = db.query(ResumeRecord).filter_by(id=resume_id).first()
        if not record:
            raise HTTPException(404, f"Resume '{resume_id}' not found.")
        return {"resume_id": record.id, **record.get_parsed()}
    finally:
        db.close()


@app.get("/jobs")
async def list_jobs():
    """List all saved job descriptions."""
    db = get_db()
    try:
        records = db.query(JobRecord).order_by(JobRecord.created_at.desc()).all()
        return [r.to_summary() for r in records]
    finally:
        db.close()


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a saved job description by ID."""
    db = get_db()
    try:
        record = db.query(JobRecord).filter_by(id=job_id).first()
        if not record:
            raise HTTPException(404, f"Job '{job_id}' not found.")
        return {"job_id": record.id, **record.get_parsed()}
    finally:
        db.close()


@app.get("/analyses")
async def list_analyses():
    """List all saved analyses."""
    db = get_db()
    try:
        records = db.query(AnalysisRecord).order_by(AnalysisRecord.created_at.desc()).all()
        return [r.to_summary() for r in records]
    finally:
        db.close()


@app.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get a saved analysis with full match report."""
    db = get_db()
    try:
        record = db.query(AnalysisRecord).filter_by(id=analysis_id).first()
        if not record:
            raise HTTPException(404, f"Analysis '{analysis_id}' not found.")
        return {
            "analysis_id": record.id,
            "resume_id": record.resume_id,
            "job_id": record.job_id,
            "match_report": json.loads(record.match_report) if record.match_report else {},
            "ats_report": json.loads(record.ats_report) if record.ats_report else {},
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
    finally:
        db.close()
