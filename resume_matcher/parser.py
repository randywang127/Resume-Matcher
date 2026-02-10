"""Resume parser: reads .docx and .pdf files and extracts structured sections."""

from __future__ import annotations

import bisect
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO

import pdfplumber
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
    entries: list[dict] | None = None  # structured sub-entries (experience only)


@dataclass
class ParsedResume:
    """Structured representation of a parsed resume."""

    sections: list[ResumeSection] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        result: dict = {"raw_text": self.raw_text, "sections": {}}
        for section in self.sections:
            section_dict: dict = {
                "heading": section.heading,
                "content": section.content,
            }
            if section.entries is not None:
                section_dict["entries"] = section.entries
            result["sections"][section.category] = section_dict
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


# ── DOCX-specific heading helpers ──────────────────────────────


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


# ── PDF heading helpers ────────────────────────────────────────


def _is_bold_font(fontname: str) -> bool:
    """Check if a PDF font name indicates bold weight."""
    name = fontname.lower()
    return any(kw in name for kw in ("bold", "-bd", "heavy", "black"))


def _is_heading_by_font(line_text: str, line_chars: list[dict], body_font_size: float) -> bool:
    """Determine if a PDF text line is a heading based on font metadata.

    Uses two signals:
    1. Font size significantly larger than body text
    2. All characters are bold
    """
    stripped = line_text.strip()
    if not stripped or len(stripped) > 80:
        return False

    non_space_chars = [c for c in line_chars if c.get("text", "").strip()]
    if not non_space_chars:
        return False

    # Signal 1: font size is larger than body text
    sizes = [c.get("size", 0) for c in non_space_chars]
    median_size = sorted(sizes)[len(sizes) // 2] if sizes else 0
    if median_size >= body_font_size + 1.5:
        return True

    # Signal 2: all characters are bold and line is short
    if len(stripped) < 50:
        all_bold = all(_is_bold_font(c.get("fontname", "")) for c in non_space_chars)
        if all_bold:
            return True

    return False


def _is_likely_heading_text(text: str) -> bool:
    """Check if plain text looks like a heading (no font info needed).

    Used as a fallback for PDFs where font metadata is missing/unreliable.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return False

    # Matches a known section pattern
    if _classify_heading(stripped) is not None:
        return True

    return False


def _compute_body_font_size(all_chars: list[dict]) -> float:
    """Compute the most common (mode) font size across all pages — this is the body size."""
    if not all_chars:
        return 12.0  # safe default
    sizes = [round(c.get("size", 12.0), 1) for c in all_chars if c.get("text", "").strip()]
    if not sizes:
        return 12.0
    counter = Counter(sizes)
    return counter.most_common(1)[0][0]


# ── Experience entry parser ────────────────────────────────────

# Date patterns: "Jan 2020 - Present", "2019 – 2023", "Mar 2018 - Dec 2020", etc.
_DATE_PATTERN = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|(?:19|20)\d{2}"
    r"|Present|Current",
    re.IGNORECASE,
)

# Location patterns: "City, ST" or "City, State" or "Remote"
_LOCATION_PATTERN = re.compile(
    r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}\b"  # City, ST
    r"|Remote",
    re.IGNORECASE,
)


def _looks_like_company_or_title(line: str) -> bool:
    """Check if a line looks like a company/title header (has pipe separator with date or location)."""
    if " | " not in line:
        return False
    return bool(_DATE_PATTERN.search(line)) or bool(_LOCATION_PATTERN.search(line))


def _parse_experience_entries(content: list[str]) -> list[dict]:
    """Parse flat experience content into structured per-role entries.

    Each entry has:
        company: str
        title: str
        location: str
        dates: str
        bullets: list[str]

    Heuristic: Lines containing " | " with a date or location pattern are
    treated as company or title headers. Everything else is a bullet point.
    """
    entries: list[dict] = []
    current_entry: dict | None = None

    for line in content:
        if _looks_like_company_or_title(line):
            parts = [p.strip().strip("|").strip() for p in line.split(" | ") if p.strip().strip("|").strip()]

            # Find date and location parts
            date_str = ""
            location_str = ""
            name_parts = []
            for part in parts:
                if _DATE_PATTERN.search(part) and not date_str:
                    date_str = part
                elif _LOCATION_PATTERN.search(part) and not location_str:
                    location_str = part
                else:
                    name_parts.append(part)

            name = " | ".join(name_parts) if name_parts else parts[0]

            if current_entry is None or current_entry.get("title"):
                # Start a new entry (this is a company line)
                current_entry = {
                    "company": name,
                    "title": "",
                    "location": location_str,
                    "dates": date_str,
                    "bullets": [],
                }
                entries.append(current_entry)
            else:
                # This is a title line for the current company
                current_entry["title"] = name
                if date_str and not current_entry["dates"]:
                    current_entry["dates"] = date_str
                elif date_str:
                    current_entry["dates"] = date_str
                if location_str and not current_entry["location"]:
                    current_entry["location"] = location_str
        else:
            # Bullet point
            if current_entry is not None:
                current_entry["bullets"].append(line)
            elif entries:
                entries[-1]["bullets"].append(line)
            else:
                # Content before any header — create a catch-all entry
                current_entry = {
                    "company": "",
                    "title": "",
                    "location": "",
                    "dates": "",
                    "bullets": [line],
                }
                entries.append(current_entry)

    return entries


# ── Shared section-grouping logic ──────────────────────────────


def _group_into_sections(lines: list[str], heading_flags: list[bool]) -> ParsedResume:
    """Group lines into sections using pre-computed heading flags.

    This is the format-agnostic core shared by both docx and PDF parsers.
    """
    sections: list[ResumeSection] = []
    current_section: ResumeSection | None = None
    raw_lines: list[str] = []

    for text, is_heading in zip(lines, heading_flags):
        raw_lines.append(text)

        if not text.strip():
            continue

        category = _classify_heading(text) if is_heading else None

        if category is not None:
            current_section = ResumeSection(heading=text.strip(), category=category)
            sections.append(current_section)
        elif current_section is not None:
            current_section.content.append(text.strip())
        else:
            # Content before any recognized heading → "header" (name/contact)
            if not sections or sections[0].category != "header":
                current_section = ResumeSection(heading="", category="header")
                sections.insert(0, current_section)
            sections[0].content.append(text.strip())

    # Post-process: parse structured entries for experience sections
    for section in sections:
        if section.category == "experience" and section.content:
            section.entries = _parse_experience_entries(section.content)

    return ParsedResume(
        sections=sections,
        raw_text="\n".join(raw_lines),
    )


# ── Main parser class ─────────────────────────────────────────


class ResumeParser:
    """Parses .docx and .pdf resumes into structured sections."""

    # ── Public API ─────────────────────────────────────────────

    def parse_file(self, data: bytes, filename: str) -> ParsedResume:
        """Route to the correct parser based on file extension.

        Args:
            data: raw file bytes
            filename: original filename (used to determine format)

        Returns:
            ParsedResume with extracted sections.

        Raises:
            ValueError: if file format is unsupported.
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".docx":
            return self.parse_bytes(data)
        elif ext == ".pdf":
            return self.parse_pdf_bytes(data)
        else:
            raise ValueError(f"Unsupported file format '{ext}'. Use .docx or .pdf.")

    def parse(self, file: BinaryIO) -> ParsedResume:
        """Parse a .docx resume from a file-like object."""
        doc = Document(file)
        return self._extract_sections_docx(doc)

    def parse_bytes(self, data: bytes) -> ParsedResume:
        """Parse a .docx resume from raw bytes."""
        return self.parse(BytesIO(data))

    def parse_pdf(self, file: BinaryIO) -> ParsedResume:
        """Parse a PDF resume from a file-like object."""
        with pdfplumber.open(file) as pdf:
            # Limit to first 20 pages (resumes are typically 1-4)
            pages = pdf.pages[:20]

            if not pages:
                raise ValueError("The PDF file appears to be empty or corrupted.")

            # Collect all characters across pages
            all_chars: list[dict] = []
            page_char_lines: list[dict[float, list[dict]]] = []

            for page in pages:
                chars = page.chars or []
                all_chars.extend(chars)
                page_char_lines.append(_group_chars_into_lines(chars))

            # Early check: reject scanned/image-only PDFs
            if not any(c.get("text", "").strip() for c in all_chars):
                raise ValueError(
                    "This PDF appears to contain scanned images rather than text. "
                    "Please upload a text-based PDF or convert to .docx."
                )

            body_size = _compute_body_font_size(all_chars)

            # Build lines and heading flags from character data directly
            lines: list[str] = []
            heading_flags: list[bool] = []

            for line_chars_map in page_char_lines:
                for y_key in sorted(line_chars_map.keys()):
                    chars_in_line = line_chars_map[y_key]
                    # Sort by x-position for correct reading order.
                    # Critical for small-caps headings where the first
                    # letter of each word is at a different y-offset/size
                    # but grouped into the same line by tolerance.
                    chars_in_line.sort(key=lambda c: c.get("x0", 0))
                    line_text = "".join(
                        c.get("text", "") for c in chars_in_line
                    )
                    # Collapse excessive whitespace (from left/right aligned
                    # text on the same line, e.g. "Company      City, ST")
                    line_text = re.sub(r" {3,}", " | ", line_text)
                    lines.append(line_text)

                    is_heading = _is_heading_by_font(
                        line_text, chars_in_line, body_size
                    )
                    if not is_heading:
                        is_heading = _is_likely_heading_text(line_text)

                    heading_flags.append(is_heading)

            return _group_into_sections(lines, heading_flags)

    def parse_pdf_bytes(self, data: bytes) -> ParsedResume:
        """Parse a PDF resume from raw bytes."""
        return self.parse_pdf(BytesIO(data))

    # ── DOCX internal ─────────────────────────────────────────

    def _extract_sections_docx(self, doc: Document) -> ParsedResume:
        """Walk through docx paragraphs and group them into sections."""
        lines: list[str] = []
        heading_flags: list[bool] = []

        for para in doc.paragraphs:
            text = para.text.strip()
            lines.append(text)

            is_heading = _is_heading_style(para) or _is_likely_heading(para)
            heading_flags.append(is_heading)

        return _group_into_sections(lines, heading_flags)


def _group_chars_into_lines(chars: list[dict], tolerance: float = 3.0) -> dict[float, list[dict]]:
    """Group PDF characters into lines by their y-coordinate (top position).

    Characters within `tolerance` pixels of each other vertically are
    considered part of the same line. Uses bisect for O(N log M) performance.
    """
    if not chars:
        return {}

    lines: dict[float, list[dict]] = {}
    sorted_keys: list[float] = []

    for char in sorted(chars, key=lambda c: (c.get("top", 0), c.get("x0", 0))):
        top = char.get("top", 0)
        idx = bisect.bisect_left(sorted_keys, top - tolerance)
        matched_key = None
        if idx < len(sorted_keys) and abs(sorted_keys[idx] - top) <= tolerance:
            matched_key = sorted_keys[idx]
        elif idx > 0 and abs(sorted_keys[idx - 1] - top) <= tolerance:
            matched_key = sorted_keys[idx - 1]

        if matched_key is not None:
            lines[matched_key].append(char)
        else:
            lines[top] = [char]
            bisect.insort(sorted_keys, top)

    return lines
