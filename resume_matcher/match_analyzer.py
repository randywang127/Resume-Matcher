"""Match Analyzer: compares resume vs job description and produces gap analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MatchReport:
    """Result of comparing a resume against a job description."""

    overall_score: float = 0.0  # 0-100
    matching_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    # Which resume section each missing keyword should go into
    keyword_placement: dict[str, str] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "matching_keywords": self.matching_keywords,
            "missing_keywords": self.missing_keywords,
            "keyword_placement": self.keyword_placement,
            "recommendations": self.recommendations,
        }


# Common filler words to ignore during keyword extraction
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "must",
    "that", "which", "who", "whom", "this", "these", "those", "it", "its",
    "we", "you", "your", "our", "they", "them", "their", "he", "she",
    "as", "if", "not", "no", "so", "up", "out", "about", "into", "over",
    "after", "before", "between", "under", "above", "such", "each",
    "all", "any", "both", "few", "more", "most", "other", "some",
    "only", "same", "than", "too", "very", "just", "also", "well",
    "etc", "e.g", "i.e", "able", "work", "working", "including",
    "experience", "using", "used", "use", "new", "within", "across",
    "strong", "excellent", "good", "great", "best", "high", "highly",
    "minimum", "preferred", "required", "requirements", "looking",
    "join", "team", "role", "position", "company", "years", "year",
}

# Multi-word technical terms to detect as single units
COMPOUND_TERMS = [
    "machine learning", "deep learning", "natural language processing",
    "computer vision", "data science", "data engineering", "data analysis",
    "project management", "product management", "software engineering",
    "full stack", "front end", "back end", "cloud computing",
    "ci/cd", "ci cd", "version control", "unit testing",
    "rest api", "restful api", "web services", "microservices",
    "agile methodology", "scrum master", "design patterns",
    "object oriented", "test driven", "continuous integration",
    "continuous delivery", "continuous deployment",
    "amazon web services", "google cloud", "microsoft azure",
]


def _normalize(text: str) -> str:
    """Lowercase and clean text for comparison."""
    return re.sub(r"[^\w\s/\+\#\.]", " ", text.lower()).strip()


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords and phrases from text."""
    normalized = _normalize(text)
    keywords: set[str] = set()

    # Extract compound terms first
    for term in COMPOUND_TERMS:
        if term in normalized:
            keywords.add(term)

    # Extract individual words
    words = normalized.split()
    for word in words:
        word = word.strip(".,;:()")
        if len(word) < 2:
            continue
        if word in STOP_WORDS:
            continue
        # Keep words that look like skills/technologies
        keywords.add(word)

    return keywords


def _extract_tech_keywords(text: str) -> set[str]:
    """Extract technology-specific keywords (more targeted)."""
    normalized = _normalize(text)
    tech_keywords: set[str] = set()

    # Common tech patterns: capitalized words, words with dots/hashes/plusses
    # Look for things like Python, AWS, C++, .NET, Node.js, etc.
    raw_words = re.findall(r"[\w\+\#\.]+", text)
    for word in raw_words:
        lower = word.lower().strip(".,;:()")
        if lower in STOP_WORDS or len(lower) < 2:
            continue
        tech_keywords.add(lower)

    # Also get compound terms
    for term in COMPOUND_TERMS:
        if term in normalized:
            tech_keywords.add(term)

    return tech_keywords


class MatchAnalyzer:
    """Compares a parsed resume against a parsed job description."""

    def analyze(
        self, resume_data: dict, job_data: dict
    ) -> MatchReport:
        """Analyze how well a resume matches a job description.

        Args:
            resume_data: Output from ResumeParser.to_dict()
            job_data: Output from JobDescriptionExtractor.to_dict()

        Returns:
            MatchReport with score, matching/missing keywords, recommendations.
        """
        report = MatchReport()

        # Build text from resume
        resume_sections = resume_data.get("sections", {})
        resume_text = self._sections_to_text(resume_sections)
        resume_keywords = _extract_keywords(resume_text)

        # Build text from job description
        jd_requirements = job_data.get("all_requirements", [])
        jd_sections = job_data.get("sections", {})
        jd_text = " ".join(jd_requirements)
        if not jd_text:
            # Fall back to all section content
            for lines in jd_sections.values():
                jd_text += " ".join(lines) + " "
        jd_keywords = _extract_keywords(jd_text)

        # Also extract from responsibilities
        responsibilities_text = " ".join(jd_sections.get("responsibilities", []))
        jd_keywords.update(_extract_keywords(responsibilities_text))

        # Filter to meaningful keywords (skip very common words)
        jd_important = self._filter_important(jd_keywords)
        resume_important = self._filter_important(resume_keywords)

        # Find matches and gaps
        matching = jd_important & resume_important
        missing = jd_important - resume_important

        report.matching_keywords = sorted(matching)
        report.missing_keywords = sorted(missing)

        # Calculate score
        if jd_important:
            report.overall_score = (len(matching) / len(jd_important)) * 100
        else:
            report.overall_score = 0.0

        # Suggest where to place missing keywords
        report.keyword_placement = self._suggest_placement(
            missing, resume_sections
        )

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def _sections_to_text(self, sections: dict) -> str:
        """Flatten all resume sections into a single text string."""
        parts = []
        for data in sections.values():
            content = data.get("content", [])
            parts.extend(content)
        return " ".join(parts)

    def _filter_important(self, keywords: set[str]) -> set[str]:
        """Keep only keywords that are likely meaningful for matching."""
        important = set()
        for kw in keywords:
            # Skip very short non-acronym words
            if len(kw) <= 2 and not kw.isupper():
                continue
            # Skip pure numbers
            if kw.isdigit():
                continue
            important.add(kw)
        return important

    def _suggest_placement(
        self, missing: set[str], resume_sections: dict
    ) -> dict[str, str]:
        """Suggest which resume section each missing keyword should be added to."""
        placement: dict[str, str] = {}
        # Simple heuristic: technical terms go to skills, others to experience
        for keyword in missing:
            if any(keyword in term for term in COMPOUND_TERMS):
                placement[keyword] = "skills"
            elif len(keyword) <= 5 and keyword.replace("+", "").replace("#", "").isalpha():
                # Short words that look like tech abbreviations
                placement[keyword] = "skills"
            else:
                placement[keyword] = "experience"
        return placement

    def _generate_recommendations(self, report: MatchReport) -> list[str]:
        """Generate actionable recommendations based on the analysis."""
        recs: list[str] = []

        if report.overall_score >= 80:
            recs.append(
                "Your resume is a strong match. Focus on fine-tuning bullet points."
            )
        elif report.overall_score >= 50:
            recs.append(
                "Moderate match. Add missing keywords to strengthen your application."
            )
        else:
            recs.append(
                "Low match. Significant keyword gaps exist — consider tailoring "
                "your resume more closely to this role."
            )

        skills_missing = [
            kw for kw, section in report.keyword_placement.items()
            if section == "skills"
        ]
        exp_missing = [
            kw for kw, section in report.keyword_placement.items()
            if section == "experience"
        ]

        if skills_missing:
            recs.append(
                f"Add to Skills section: {', '.join(skills_missing[:10])}"
            )
        if exp_missing:
            recs.append(
                f"Incorporate into Experience bullets: {', '.join(exp_missing[:10])}"
            )

        if len(report.missing_keywords) > 15:
            recs.append(
                "Many keywords are missing. Prioritize the most frequently "
                "mentioned terms in the job description."
            )

        return recs
