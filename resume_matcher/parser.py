"""Resume parser: reads a .docx file and extracts structured sections."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO

from docx import Document


# Common section heading patterns (case-insensitive)
SECTION_PATTERNS: dict[str, list[str]] = {
    "contact": [
        r"contact\s*info(?:rmation)?",
        r"personal\s*info(?:rmation)?",
    ],
    "summary": [
        r"summary",
        r"professional\s*summary",
        r"profile",
        r"objective",
        r"about\s*me",
        r"career\s*summary",
        r"executive\s*summary",
    ],
    "experience": [
        r"experience",
        r"work\s*experience",
        r"professional\s*experience",
        r"employment\s*history",
        r"work\s*history",
    ],
    "education": [
        r"education",
        r"academic\s*background",
        r"qualifications",
    ],
    "skills": [
        r"skills",
        r"technical\s*skills",
        r"core\s*competencies",
        r"competencies",
        r"areas?\s*of\s*expertise",
        r"proficiencies",
    ],
    "certifications": [
        r"certifications?",
        r"licenses?\s*(?:&|and)?\s*certifications?",
        r"professional\s*certifications?",
    ],
    "projects": [
        r"projects",
        r"personal\s*projects",
        r"key\s*projects",
    ],
    "awards": [
        r"awards?",
        r"honors?",
        r"achievements?",
    ],
    "languages": [
        r"languages?",
    ],
    "references": [
        r"references?",
    ],
}


def _compile_patterns() -> dict[str, re.Pattern]:
    """Pre-compile section heading regex patterns."""
    compiled: dict[str, re.Pattern] = {}
    for section, patterns in SECTION_PATTERNS.items():
        joined = "|".join(patterns)
        compiled[section] = re.compile(
            rf"^\s*(?:{joined})\s*:?\s*$", re.IGNORECASE
        )
    return compiled


COMPILED_PATTERNS = _compile_patterns()


@dataclass
class ResumeSection:
    """A single section of a resume."""

    heading: str
    category: str  # normalized category key (e.g. "experience", "skills")
    content: list[str] = field(default_factory=list)


@dataclass
class ParsedResume:
    """Structured representation of a parsed resume."""

    sections: list[ResumeSection] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        result: dict = {"raw_text": self.raw_text, "sections": {}}
        for section in self.sections:
            result["sections"][section.category] = {
                "heading": section.heading,
                "content": section.content,
            }
        return result


def _classify_heading(text: str) -> str | None:
    """Match a paragraph text to a known section category."""
    stripped = text.strip()
    if not stripped:
        return None
    for category, pattern in COMPILED_PATTERNS.items():
        if pattern.match(stripped):
            return category
    return None


def _is_heading_style(paragraph) -> bool:
    """Check if paragraph uses a Word heading style."""
    style_name = (paragraph.style.name or "").lower()
    return "heading" in style_name


def _is_likely_heading(paragraph) -> bool:
    """Heuristic: short, bold text that looks like a section heading."""
    text = paragraph.text.strip()
    if not text or len(text) > 80:
        return False

    # Check if entire paragraph is bold
    if paragraph.runs:
        all_bold = all(run.bold for run in paragraph.runs if run.text.strip())
        if all_bold and len(text) < 50:
            return True

    # Check if it matches a known section pattern
    if _classify_heading(text) is not None:
        return True

    return False


class ResumeParser:
    """Parses a .docx resume into structured sections."""

    def parse(self, file: BinaryIO) -> ParsedResume:
        """Parse a resume from a file-like object.

        Args:
            file: A binary file-like object containing .docx data.

        Returns:
            ParsedResume with extracted sections.
        """
        doc = Document(file)
        return self._extract_sections(doc)

    def parse_bytes(self, data: bytes) -> ParsedResume:
        """Parse a resume from raw bytes."""
        return self.parse(BytesIO(data))

    def _extract_sections(self, doc: Document) -> ParsedResume:
        """Walk through paragraphs and group them into sections."""
        sections: list[ResumeSection] = []
        current_section: ResumeSection | None = None
        raw_lines: list[str] = []

        for para in doc.paragraphs:
            text = para.text.strip()
            raw_lines.append(text)

            if not text:
                continue

            # Detect section headings
            is_heading = _is_heading_style(para) or _is_likely_heading(para)
            category = _classify_heading(text) if is_heading else None

            if category is not None:
                # Start a new section
                current_section = ResumeSection(
                    heading=text,
                    category=category,
                )
                sections.append(current_section)
            elif current_section is not None:
                # Append content to the current section
                current_section.content.append(text)
            else:
                # Content before any recognized heading → treat as "header" (contact/name)
                if not sections or sections[0].category != "header":
                    current_section = ResumeSection(
                        heading="",
                        category="header",
                    )
                    sections.insert(0, current_section)
                sections[0].content.append(text)

        return ParsedResume(
            sections=sections,
            raw_text="\n".join(raw_lines),
        )
