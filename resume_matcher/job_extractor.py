"""Job Description Extractor: accepts text or URL and extracts structured JD."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

# Patterns to identify JD sections
JD_SECTION_PATTERNS: dict[str, list[str]] = {
    "responsibilities": [
        r"responsibilities",
        r"what\s*you(?:'ll|.will)\s*do",
        r"role\s*(?:description|overview)",
        r"job\s*duties",
        r"key\s*responsibilities",
        r"about\s*the\s*role",
    ],
    "requirements": [
        r"requirements",
        r"qualifications",
        r"what\s*(?:we(?:'re)?\s*looking\s*for|you\s*(?:need|bring))",
        r"minimum\s*qualifications",
        r"basic\s*qualifications",
        r"must\s*have",
        r"required\s*(?:skills|experience|qualifications)",
    ],
    "preferred": [
        r"preferred\s*(?:qualifications|skills|experience)",
        r"nice\s*to\s*have",
        r"bonus\s*(?:points|qualifications)?",
        r"desired\s*(?:skills|experience|qualifications)",
        r"additional\s*qualifications",
    ],
    "benefits": [
        r"benefits",
        r"perks",
        r"what\s*we\s*offer",
        r"compensation",
    ],
    "about": [
        r"about\s*(?:us|the\s*company|the\s*team)",
        r"who\s*we\s*are",
        r"company\s*(?:overview|description)",
    ],
}

COMPILED_JD_PATTERNS: dict[str, re.Pattern] = {}
for _section, _patterns in JD_SECTION_PATTERNS.items():
    _joined = "|".join(_patterns)
    COMPILED_JD_PATTERNS[_section] = re.compile(
        rf"^\s*(?:{_joined})\s*:?\s*$", re.IGNORECASE
    )


@dataclass
class ParsedJobDescription:
    """Structured representation of a job description."""

    title: str = ""
    company: str = ""
    company_background: str = ""
    location: str = ""
    salary_range: str = ""
    raw_text: str = ""
    sections: dict[str, list[str]] = field(default_factory=dict)
    # Flat list of all requirement/qualification lines
    all_requirements: list[str] = field(default_factory=list)
    required_qualifications: list[str] = field(default_factory=list)
    preferred_qualifications: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "company": self.company,
            "company_background": self.company_background,
            "location": self.location,
            "salary_range": self.salary_range,
            "raw_text": self.raw_text,
            "sections": self.sections,
            "all_requirements": self.all_requirements,
            "required_qualifications": self.required_qualifications,
            "preferred_qualifications": self.preferred_qualifications,
            "responsibilities": self.responsibilities,
        }


class JobDescriptionExtractor:
    """Extracts and structures job descriptions from text or URLs."""

    def from_text(self, text: str) -> ParsedJobDescription:
        """Parse a job description from raw text."""
        lines = [line.strip() for line in text.strip().splitlines()]
        return self._parse_lines(lines, text)

    def from_url(self, url: str) -> ParsedJobDescription:
        """Fetch a URL and extract the job description text."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Try to find job description container (common patterns)
        job_container = None
        for selector in [
            '[class*="job-description"]',
            '[class*="job_description"]',
            '[class*="jobDescription"]',
            '[class*="posting"]',
            '[id*="job-description"]',
            '[id*="job_description"]',
            "article",
            "main",
            '[role="main"]',
        ]:
            job_container = soup.select_one(selector)
            if job_container:
                break

        if job_container:
            text = job_container.get_text(separator="\n", strip=True)
        else:
            # Fallback: use body text
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else ""

        # Try to extract title
        title = ""
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        result = self._parse_lines(lines, text)
        if title:
            result.title = title
        return result

    def _parse_lines(
        self, lines: list[str], raw_text: str
    ) -> ParsedJobDescription:
        """Parse lines into structured sections."""
        result = ParsedJobDescription(raw_text=raw_text)
        current_section: str | None = None

        for line in lines:
            if not line:
                continue

            # Check if this line is a section heading
            matched_section = self._match_section(line)
            if matched_section:
                current_section = matched_section
                if current_section not in result.sections:
                    result.sections[current_section] = []
                continue

            if current_section:
                # Clean bullet characters
                cleaned = re.sub(r"^[\u2022\u2023\u25E6\u2043\u2219•\-\*]\s*", "", line)
                if cleaned:
                    result.sections.setdefault(current_section, []).append(cleaned)

        # Build all_requirements from requirements + preferred
        for key in ["requirements", "preferred"]:
            result.all_requirements.extend(result.sections.get(key, []))

        # If no sections were detected, treat all content as requirements
        if not result.sections:
            result.sections["general"] = [l for l in lines if l]
            result.all_requirements = result.sections["general"]

        # Try to guess title from first line if not set
        if not result.title and lines:
            first = lines[0]
            if len(first) < 100 and not self._match_section(first):
                result.title = first

        return result

    def enhance_with_llm(self, result: ParsedJobDescription) -> ParsedJobDescription:
        """Use LLM to extract structured fields from the raw job text.

        Enhances the result with company_background, separated required vs
        preferred qualifications, location, and salary. Falls back gracefully
        if the LLM is unavailable.
        """
        import json
        import logging

        from resume_matcher.llm_client import get_llm_client
        from resume_matcher.prompts import JOB_EXTRACT_SYSTEM, JOB_EXTRACT_USER

        logger = logging.getLogger(__name__)

        try:
            client = get_llm_client()
            prompt = JOB_EXTRACT_USER.format(job_text=result.raw_text[:8000])
            data = client.complete_json(JOB_EXTRACT_SYSTEM, prompt)

            # Merge LLM results into existing result (LLM wins for new fields,
            # existing regex results are kept as fallback for sections)
            if data.get("title") and not result.title:
                result.title = data["title"]
            if data.get("company_name"):
                result.company = data["company_name"]
            if data.get("company_background"):
                result.company_background = data["company_background"]
            if data.get("location"):
                result.location = data["location"]
            if data.get("salary_range"):
                result.salary_range = data["salary_range"]
            if data.get("required_qualifications"):
                result.required_qualifications = data["required_qualifications"]
            if data.get("preferred_qualifications"):
                result.preferred_qualifications = data["preferred_qualifications"]
            if data.get("responsibilities"):
                result.responsibilities = data["responsibilities"]
            if data.get("all_requirements") and not result.all_requirements:
                result.all_requirements = data["all_requirements"]

        except Exception as exc:
            logger.warning("LLM job extraction failed, using regex results: %s", exc)

        return result

    def _match_section(self, text: str) -> str | None:
        """Check if text matches a known JD section heading."""
        stripped = text.strip().rstrip(":")
        for section, pattern in COMPILED_JD_PATTERNS.items():
            if pattern.match(stripped):
                return section
        return None
