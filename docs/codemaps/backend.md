# Backend Codemap

> Updated: 2026-02-08

## Modules

### main.py — API Layer (271 lines)

**Pydantic Models:**
- `JobInput` — `url: str | None`, `text: str | None`
- `AnalyzeRequest` — `resume: dict`, `job: dict`
- `UpdateRequest` — `resume: dict`, `match_report: dict`, `ats_report: dict | None`
- `GenerateRequest` — `resume: dict`

**Endpoints:**
| Route | Handler | Input | Output |
|-------|---------|-------|--------|
| `GET /health` | `health()` | — | `{"status":"ok"}` |
| `POST /parse-resume` | `parse_resume()` | UploadFile (.docx) | parsed JSON |
| `POST /ats-check` | `ats_check()` | UploadFile (.docx) | ATSReport JSON |
| `POST /parse-job` | `parse_job()` | JobInput JSON | parsed JD JSON |
| `POST /analyze` | `analyze()` | AnalyzeRequest JSON | MatchReport JSON |
| `POST /update-resume` | `update_resume()` | UpdateRequest JSON | UpdateResult JSON |
| `POST /generate` | `generate()` | GenerateRequest JSON | .docx bytes |
| `POST /optimize` | `optimize()` | UploadFile + Form fields | .docx bytes |

---

### parser.py — Resume Parser (208 lines)

**Dataclasses:**
- `ResumeSection` — `heading: str`, `category: str`, `content: list[str]`
- `ParsedResume` — `sections: list[ResumeSection]`, `raw_text: str`

**Class:** `ResumeParser`
- `parse(file: BinaryIO) -> ParsedResume`
- `parse_bytes(data: bytes) -> ParsedResume`

**Strategy:** Walks paragraphs, detects headings via Word styles + bold heuristic + regex patterns. Groups content under detected sections.

---

### ats_optimizer.py — ATS Checker (319 lines)

**Dataclasses:**
- `ATSIssue` — `severity`, `category`, `message`, `suggestion`
- `ATSReport` — `score: int (0-100)`, `issues`, `section_status`, `heading_suggestions`

**Class:** `ATSOptimizer`
- `check(parsed_resume: dict) -> ATSReport`

**Checks:** required sections, heading names, contact info, experience metrics, skills count, summary length.

---

### job_extractor.py — JD Extractor (189 lines)

**Dataclass:**
- `ParsedJobDescription` — `title`, `company`, `raw_text`, `sections`, `all_requirements`

**Class:** `JobDescriptionExtractor`
- `from_text(text: str) -> ParsedJobDescription`
- `from_url(url: str) -> ParsedJobDescription`

**Strategy:** URL mode scrapes page with BeautifulSoup, looks for job container selectors. Text mode splits on section heading patterns.

---

### match_analyzer.py — Gap Analysis (257 lines)

**Dataclass:**
- `MatchReport` — `overall_score`, `matching_keywords`, `missing_keywords`, `keyword_placement`, `recommendations`

**Class:** `MatchAnalyzer`
- `analyze(resume_data: dict, job_data: dict) -> MatchReport`

**Strategy:** Extracts keywords from both resume and JD, computes set intersection/difference, scores by coverage ratio, suggests placement per keyword.

---

### updater.py — Content Updater (232 lines)

**Dataclass:**
- `UpdateResult` — `updated_sections`, `changes_made`, `keywords_added`

**Class:** `ResumeUpdater`
- `update(resume_data, match_report, ats_report?) -> UpdateResult`

**Strategy:** Fixes headings per ATS report, injects missing skills, enhances experience bullets with keywords, appends key terms to summary.

---

### generator.py — DOCX Generator (192 lines)

**Class:** `ResumeGenerator`
- `generate(resume_data: dict) -> bytes`

**Strategy:** Creates Document with professional formatting (Calibri 11pt, narrow margins), renders sections in standard order with horizontal rules.

## Constants

| Module | Constant | Purpose |
|--------|----------|---------|
| parser | `SECTION_PATTERNS` | Regex patterns for resume section headings |
| ats_optimizer | `REQUIRED_SECTIONS` | Sections a resume must have |
| ats_optimizer | `HEADING_RENAMES` | Non-standard → ATS-friendly heading map |
| job_extractor | `JD_SECTION_PATTERNS` | Regex patterns for JD section headings |
| match_analyzer | `STOP_WORDS` | Common words to ignore in keyword extraction |
| match_analyzer | `COMPOUND_TERMS` | Multi-word tech terms (e.g. "machine learning") |
| generator | `SECTION_ORDER` | Standard rendering order for resume sections |
