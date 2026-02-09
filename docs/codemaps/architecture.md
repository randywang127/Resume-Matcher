# Architecture Codemap

> Updated: 2026-02-08

## System Overview

Local FastAPI application. Single process, no database, no external services required.

```
Client (curl / Swagger UI)
    │
    ▼
┌─────────────────────────────────────┐
│  main.py (FastAPI, 8 endpoints)     │
│  /health /parse-resume /ats-check   │
│  /parse-job /analyze /update-resume │
│  /generate /optimize                │
└─────────┬───────────────────────────┘
          │ calls
          ▼
┌─────────────────────────────────────┐
│  resume_matcher/                    │
│  ┌──────────┐  ┌────────────────┐  │
│  │ parser   │  │ ats_optimizer  │  │
│  └──────────┘  └────────────────┘  │
│  ┌──────────────┐  ┌────────────┐  │
│  │ job_extractor │  │ match_     │  │
│  │              │  │ analyzer   │  │
│  └──────────────┘  └────────────┘  │
│  ┌──────────┐  ┌────────────────┐  │
│  │ updater  │──│ generator      │  │
│  └──────────┘  └────────────────┘  │
└─────────────────────────────────────┘
```

## Data Flow

```
.docx upload
    │
    ▼
ResumeParser ──► dict{sections}
    │                 │
    ▼                 ▼
ATSOptimizer    JobDescriptionExtractor (text/URL)
    │                 │
    ▼                 ▼
ATSReport        dict{jd_sections, all_requirements}
    │                 │
    └────────┬────────┘
             ▼
        MatchAnalyzer
             │
             ▼
        MatchReport{score, missing_keywords}
             │
             ▼
        ResumeUpdater
             │
             ▼
        UpdateResult{updated_sections}
             │
             ▼
        ResumeGenerator
             │
             ▼
        .docx bytes (download)
```

## Dependency Graph

```
main.py
  ├── parser.py
  ├── ats_optimizer.py
  ├── job_extractor.py
  ├── match_analyzer.py
  ├── updater.py ──► ats_optimizer.py (constants)
  └── generator.py
```

No circular dependencies.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Word I/O | python-docx, lxml |
| Web scraping | requests, beautifulsoup4 |
| Validation | Pydantic |
