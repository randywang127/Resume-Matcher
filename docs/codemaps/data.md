# Data Models Codemap

> Updated: 2026-02-08

## Data Flow Between Models

```
UploadFile (.docx)
    │
    ▼
ParsedResume ─────► dict (via to_dict())
    │                    │
    │               ┌────┴────┐
    │               ▼         ▼
    │          ATSReport   MatchReport
    │               │         │
    │               └────┬────┘
    │                    ▼
    │              UpdateResult
    │                    │
    │                    ▼
    └──────────► ResumeGenerator ──► bytes (.docx)
```

## Dataclasses (resume_matcher/)

### ResumeSection (parser.py)
```python
heading: str        # Original heading text, e.g. "Work Experience"
category: str       # Normalized key: "experience", "skills", "header"
content: list[str]  # Paragraph texts under this section
```

### ParsedResume (parser.py)
```python
sections: list[ResumeSection]
raw_text: str       # All paragraphs joined with newlines
```
**Serialized form** (`to_dict()`):
```json
{
  "raw_text": "...",
  "sections": {
    "header":     {"heading": "", "content": ["Name", "email | phone"]},
    "summary":    {"heading": "Professional Summary", "content": [...]},
    "experience": {"heading": "Work Experience", "content": [...]},
    "skills":     {"heading": "Skills", "content": [...]},
    "education":  {"heading": "Education", "content": [...]}
  }
}
```

### ATSIssue (ats_optimizer.py)
```python
severity: str       # "error" | "warning" | "info"
category: str       # "structure" | "heading" | "content" | "formatting"
message: str
suggestion: str
```

### ATSReport (ats_optimizer.py)
```python
score: int                          # 0-100
issues: list[ATSIssue]
section_status: dict[str, str]      # e.g. {"skills": "present", "certifications": "missing"}
heading_suggestions: dict[str, str] # e.g. {"About Me": "Professional Summary"}
```

### ParsedJobDescription (job_extractor.py)
```python
title: str
company: str
raw_text: str
sections: dict[str, list[str]]      # e.g. {"requirements": [...], "responsibilities": [...]}
all_requirements: list[str]          # Merged requirements + preferred
```

### MatchReport (match_analyzer.py)
```python
overall_score: float                 # 0-100
matching_keywords: list[str]
missing_keywords: list[str]
keyword_placement: dict[str, str]    # e.g. {"redis": "skills", "django": "experience"}
recommendations: list[str]
```

### UpdateResult (updater.py)
```python
updated_sections: dict               # Same shape as ParsedResume.to_dict()["sections"]
changes_made: list[str]              # Human-readable change log
keywords_added: list[str]
```

## Pydantic Models (main.py)

### JobInput
```python
url: str | None = None
text: str | None = None
```

### AnalyzeRequest
```python
resume: dict    # ParsedResume.to_dict() output
job: dict       # ParsedJobDescription.to_dict() output
```

### UpdateRequest
```python
resume: dict           # ParsedResume.to_dict() output
match_report: dict     # MatchReport.to_dict() output
ats_report: dict | None
```

### GenerateRequest
```python
resume: dict           # Can be ParsedResume or UpdateResult dict
```

## Section Categories

Recognized resume section categories (parser.py):
`header`, `summary`, `experience`, `education`, `skills`, `certifications`, `projects`, `awards`, `languages`, `references`

Recognized JD section categories (job_extractor.py):
`responsibilities`, `requirements`, `preferred`, `benefits`, `about`
