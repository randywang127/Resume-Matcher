# Resume-Matcher

Local FastAPI application that parses resumes, checks ATS compliance, analyzes job description fit, and generates optimized resumes in Word format. All results are persisted with IDs for reuse across API calls.

## Quick Start

```bash
# Create virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Start the server
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

## API Endpoints

### Core Pipeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/parse-resume` | Upload `.docx` → structured JSON + `resume_id` |
| `POST` | `/ats-check` | ATS compliance report (file upload or `resume_id`) |
| `POST` | `/parse-job` | Parse JD from URL or text → `job_id` |
| `POST` | `/analyze` | Gap analysis (`resume_id` + `job_id` or full JSON) → `analysis_id` |
| `POST` | `/update-resume` | Update resume with keywords (`analysis_id` or full JSON) |
| `POST` | `/generate` | Generate `.docx` (`analysis_id`, `resume_id`, or full JSON) |
| `POST` | `/optimize` | Full pipeline → optimized `.docx` download |

### Saved Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/resumes` | List all saved resumes |
| `GET` | `/resumes/{id}` | Get a saved resume by ID |
| `GET` | `/jobs` | List all saved job descriptions |
| `GET` | `/jobs/{id}` | Get a saved job by ID |
| `GET` | `/analyses` | List all saved analyses |
| `GET` | `/analyses/{id}` | Get a saved analysis by ID |

## Usage Examples

### Step-by-step workflow (with IDs)

```bash
# 1. Parse resume (returns resume_id)
curl -X POST http://localhost:8000/parse-resume \
  -F "file=@my_resume.docx"
# → { "resume_id": "abc123", "sections": {...} }

# 2. Parse job description (returns job_id)
curl -X POST http://localhost:8000/parse-job \
  -H "Content-Type: application/json" \
  -d '{"text": "Senior Engineer\n\nRequirements:\n- 5+ years Python..."}'
# → { "job_id": "def456", ... }

# 3. Analyze match using IDs (no re-upload needed)
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"resume_id": "abc123", "job_id": "def456"}'
# → { "analysis_id": "ghi789", "match_report": {...} }

# 4. Generate optimized .docx from analysis
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"analysis_id": "ghi789"}' \
  -o updated_resume.docx
```

### Full pipeline (one command)

```bash
# With file upload
curl -X POST http://localhost:8000/optimize \
  -F "file=@my_resume.docx" \
  -F "job_text=Senior Python Developer..." \
  -o optimized_resume.docx

# With saved IDs (no upload needed)
curl -X POST http://localhost:8000/optimize \
  -F "resume_id=abc123" \
  -F "job_id=def456" \
  -o optimized_resume.docx
```

### ATS check (two ways)

```bash
# Upload file
curl -X POST http://localhost:8000/ats-check \
  -F "file=@my_resume.docx"

# Use saved resume_id
curl -X POST http://localhost:8000/ats-check \
  -F "resume_id=abc123"
```

## Project Structure

```
Resume-Matcher/
├── main.py                         # FastAPI app (14 endpoints)
├── pyproject.toml                  # Project config and dependencies
├── resume_matcher/
│   ├── parser.py                   # .docx resume parsing
│   ├── ats_optimizer.py            # ATS compliance scoring
│   ├── job_extractor.py            # Job description extraction (text/URL)
│   ├── match_analyzer.py           # Resume vs JD gap analysis
│   ├── updater.py                  # Resume content updater
│   ├── generator.py                # .docx generation
│   ├── database.py                 # SQLAlchemy models (SQLite → PostgreSQL)
│   └── storage.py                  # File storage (local → S3)
├── data/                           # Auto-created, git-ignored
│   ├── resume_matcher.db           # SQLite database
│   ├── uploads/                    # Original .docx files
│   └── outputs/                    # Generated .docx files
├── docs/codemaps/                  # Architecture documentation
└── samples/
    └── sample_resume.docx          # Sample resume for testing
```

## Storage

All parsed resumes, job descriptions, and analyses are saved automatically:

- **Structured data** (JSON, scores, relationships) → SQLite database at `data/resume_matcher.db`
- **Binary files** (original and generated `.docx`) → `data/uploads/` and `data/outputs/`

### Scaling to production

```python
# database.py — change one environment variable:
DATABASE_URL=postgresql://user:pass@host:5432/resume_matcher

# storage.py — swap FileStorage for S3Storage (same interface)
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `python-docx` | Read/write Word documents |
| `python-multipart` | File upload support |
| `requests` | HTTP fetching for job URLs |
| `beautifulsoup4` | HTML parsing |
| `lxml` | XML processing |
| `sqlalchemy` | Database ORM (SQLite/PostgreSQL) |

## Requirements

- Python 3.10+
