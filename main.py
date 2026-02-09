"""Resume Matcher API — local FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from resume_matcher.ats_optimizer import ATSOptimizer
from resume_matcher.generator import ResumeGenerator
from resume_matcher.job_extractor import JobDescriptionExtractor
from resume_matcher.match_analyzer import MatchAnalyzer
from resume_matcher.parser import ResumeParser
from resume_matcher.updater import ResumeUpdater

app = FastAPI(
    title="Resume Matcher",
    description="Parse, optimize, and tailor resumes to job descriptions.",
    version="0.1.0",
)

# Service instances
parser = ResumeParser()
ats_optimizer = ATSOptimizer()
job_extractor = JobDescriptionExtractor()
match_analyzer = MatchAnalyzer()
resume_updater = ResumeUpdater()
resume_generator = ResumeGenerator()


# ── Request models ──────────────────────────────────────────────


class JobInput(BaseModel):
    """Input for job description parsing."""

    url: str | None = None
    text: str | None = None


class AnalyzeRequest(BaseModel):
    """Input for gap analysis."""

    resume: dict
    job: dict


class UpdateRequest(BaseModel):
    """Input for resume update."""

    resume: dict
    match_report: dict
    ats_report: dict | None = None


class GenerateRequest(BaseModel):
    """Input for .docx generation."""

    resume: dict


# ── Endpoints ───────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """Upload a .docx resume and get back structured JSON.

    Returns parsed sections: header, summary, experience, skills,
    education, certifications, etc.
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

    return result.to_dict()


@app.post("/ats-check")
async def ats_check(file: UploadFile = File(...)):
    """Upload a .docx resume and get an ATS compliance report.

    Returns a score (0-100), list of issues, and heading suggestions.
    """
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Only .docx files are supported.",
        )

    try:
        contents = await file.read()
        parsed = parser.parse_bytes(contents)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to parse the document: {exc}"
        )

    report = ats_optimizer.check(parsed.to_dict())
    return report.to_dict()


@app.post("/parse-job")
async def parse_job(body: JobInput):
    """Parse a job description from a URL or raw text.

    Provide either `url` or `text` in the request body.
    Returns structured sections: responsibilities, requirements,
    preferred qualifications, etc.
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

    return result.to_dict()


@app.post("/analyze")
async def analyze(body: AnalyzeRequest):
    """Analyze how well a resume matches a job description.

    Accepts parsed resume and parsed job description JSON.
    Returns match score, matching/missing keywords, and recommendations.
    """
    try:
        report = match_analyzer.analyze(body.resume, body.job)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Analysis failed: {exc}"
        )

    return report.to_dict()


@app.post("/update-resume")
async def update_resume(body: UpdateRequest):
    """Update resume content to better match the job description.

    Accepts parsed resume, match report, and optional ATS report.
    Returns updated sections with a change log.
    """
    try:
        result = resume_updater.update(
            body.resume, body.match_report, body.ats_report
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Update failed: {exc}"
        )

    return result.to_dict()


@app.post("/generate")
async def generate(body: GenerateRequest):
    """Generate a .docx file from resume data.

    Accepts resume sections JSON and returns a downloadable Word document.
    """
    try:
        docx_bytes = resume_generator.generate(body.resume)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Generation failed: {exc}"
        )

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=updated_resume.docx"},
    )


@app.post("/optimize")
async def optimize(
    file: UploadFile = File(...),
    job_url: str | None = Form(None),
    job_text: str | None = Form(None),
):
    """Full pipeline: upload resume + provide JD → get back optimized .docx.

    Upload a .docx resume and provide either `job_url` or `job_text`
    as form fields. Returns a downloadable updated Word document along
    with the analysis report.

    Use the Swagger UI (/docs) for easy testing.
    """
    # Validate inputs
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400, detail="Only .docx files are supported."
        )
    if not job_url and not job_text:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'job_url' or 'job_text' as a form field.",
        )

    # Step 1: Parse resume
    try:
        contents = await file.read()
        parsed_resume = parser.parse_bytes(contents)
        resume_dict = parsed_resume.to_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to parse resume: {exc}"
        )

    # Step 2: ATS check
    ats_report = ats_optimizer.check(resume_dict).to_dict()

    # Step 3: Parse job description
    try:
        if job_url:
            job_data = job_extractor.from_url(job_url).to_dict()
        else:
            job_data = job_extractor.from_text(job_text).to_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to parse job description: {exc}"
        )

    # Step 4: Analyze match
    match_report = match_analyzer.analyze(resume_dict, job_data).to_dict()

    # Step 5: Update resume
    update_result = resume_updater.update(
        resume_dict, match_report, ats_report
    )

    # Step 6: Generate .docx
    try:
        docx_bytes = resume_generator.generate(update_result.to_dict())
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to generate document: {exc}"
        )

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=optimized_resume.docx"},
    )
