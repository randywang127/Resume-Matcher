# Resume-Matcher

Local FastAPI application that parses resumes, checks ATS compliance, analyzes job description fit, and generates optimized resumes in Word format.

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

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/parse-resume` | Upload `.docx` resume, get structured JSON |
| `POST` | `/ats-check` | Upload `.docx` resume, get ATS compliance report (0-100 score) |
| `POST` | `/parse-job` | Parse job description from URL or text |
| `POST` | `/analyze` | Compare resume vs job description, get match score and gap analysis |
| `POST` | `/update-resume` | Update resume content with missing keywords |
| `POST` | `/generate` | Generate formatted `.docx` from resume JSON |
| `POST` | `/optimize` | Full pipeline: upload resume + job description, get optimized `.docx` |

## Usage Examples

### Parse a resume

```bash
curl -X POST http://localhost:8000/parse-resume \
  -F "file=@my_resume.docx"
```

### ATS compliance check

```bash
curl -X POST http://localhost:8000/ats-check \
  -F "file=@my_resume.docx"
```

### Parse a job description

```bash
# From text
curl -X POST http://localhost:8000/parse-job \
  -H "Content-Type: application/json" \
  -d '{"text": "Senior Engineer\n\nRequirements:\n- 5+ years Python..."}'

# From URL
curl -X POST http://localhost:8000/parse-job \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/job-posting"}'
```

### Full pipeline (one command)

```bash
curl -X POST http://localhost:8000/optimize \
  -F "file=@my_resume.docx" \
  -F "job_text=Senior Python Developer..." \
  -o optimized_resume.docx
```

## Project Structure

```
Resume-Matcher/
├── main.py                         # FastAPI app and endpoints
├── pyproject.toml                  # Project config and dependencies
├── resume_matcher/
│   ├── parser.py                   # .docx resume parsing
│   ├── ats_optimizer.py            # ATS compliance scoring
│   ├── job_extractor.py            # Job description extraction (text/URL)
│   ├── match_analyzer.py           # Resume vs JD gap analysis
│   ├── updater.py                  # Resume content updater
│   └── generator.py                # .docx generation
└── samples/
    └── sample_resume.docx          # Sample resume for testing
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

## Requirements

- Python 3.10+
