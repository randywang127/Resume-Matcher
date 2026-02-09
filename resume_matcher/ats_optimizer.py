"""ATS Optimizer: checks and scores resume for ATS compliance."""

from __future__ import annotations

from dataclasses import dataclass, field

# Standard ATS-friendly section headings
ATS_STANDARD_SECTIONS = {
    "contact": ["Contact Information"],
    "summary": ["Professional Summary", "Summary"],
    "experience": ["Work Experience", "Professional Experience", "Experience"],
    "education": ["Education"],
    "skills": ["Skills", "Technical Skills"],
    "certifications": ["Certifications"],
    "projects": ["Projects"],
}

# Sections that a strong resume should have
REQUIRED_SECTIONS = ["header", "summary", "experience", "skills", "education"]
RECOMMENDED_SECTIONS = ["certifications", "projects"]

# ATS-unfriendly heading names that should be renamed
HEADING_RENAMES: dict[str, str] = {
    "About Me": "Professional Summary",
    "Objective": "Professional Summary",
    "Career Summary": "Professional Summary",
    "Executive Summary": "Professional Summary",
    "Profile": "Professional Summary",
    "Employment History": "Work Experience",
    "Work History": "Work Experience",
    "Core Competencies": "Skills",
    "Areas of Expertise": "Skills",
    "Proficiencies": "Skills",
    "Competencies": "Skills",
    "Academic Background": "Education",
    "Qualifications": "Education",
}


@dataclass
class ATSIssue:
    """A single ATS compliance issue."""

    severity: str  # "error", "warning", "info"
    category: str  # "structure", "heading", "content", "formatting"
    message: str
    suggestion: str = ""


@dataclass
class ATSReport:
    """Full ATS compliance report."""

    score: int = 100  # 0-100
    issues: list[ATSIssue] = field(default_factory=list)
    section_status: dict[str, str] = field(default_factory=dict)
    heading_suggestions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "section_status": self.section_status,
            "heading_suggestions": self.heading_suggestions,
        }


class ATSOptimizer:
    """Analyzes a parsed resume for ATS compliance."""

    def check(self, parsed_resume: dict) -> ATSReport:
        """Run ATS compliance checks on a parsed resume dict.

        Args:
            parsed_resume: Output from ResumeParser.to_dict()

        Returns:
            ATSReport with score, issues, and suggestions.
        """
        report = ATSReport()
        sections = parsed_resume.get("sections", {})

        self._check_required_sections(sections, report)
        self._check_section_headings(sections, report)
        self._check_contact_info(sections, report)
        self._check_experience_content(sections, report)
        self._check_skills_content(sections, report)
        self._check_summary_content(sections, report)

        # Clamp score
        report.score = max(0, min(100, report.score))
        return report

    def _check_required_sections(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check that all required sections are present."""
        for section in REQUIRED_SECTIONS:
            if section in sections:
                report.section_status[section] = "present"
            else:
                report.section_status[section] = "missing"
                report.score -= 15
                report.issues.append(
                    ATSIssue(
                        severity="error",
                        category="structure",
                        message=f"Missing required section: {section}",
                        suggestion=f"Add a '{section.title()}' section to your resume.",
                    )
                )

        for section in RECOMMENDED_SECTIONS:
            if section in sections:
                report.section_status[section] = "present"
            else:
                report.section_status[section] = "optional-missing"
                report.issues.append(
                    ATSIssue(
                        severity="info",
                        category="structure",
                        message=f"Optional section not found: {section}",
                        suggestion=f"Consider adding a '{section.title()}' section.",
                    )
                )

    def _check_section_headings(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check that section headings use ATS-standard names."""
        for category, data in sections.items():
            heading = data.get("heading", "")
            if not heading:
                continue

            # Check if heading should be renamed
            for old_name, new_name in HEADING_RENAMES.items():
                if heading.lower() == old_name.lower():
                    report.heading_suggestions[heading] = new_name
                    report.score -= 5
                    report.issues.append(
                        ATSIssue(
                            severity="warning",
                            category="heading",
                            message=f"Non-standard heading: '{heading}'",
                            suggestion=f"Rename to '{new_name}' for better ATS parsing.",
                        )
                    )
                    break

    def _check_contact_info(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check that contact information is present and complete."""
        header = sections.get("header", {})
        content = header.get("content", [])
        full_text = " ".join(content).lower()

        if not content:
            report.score -= 10
            report.issues.append(
                ATSIssue(
                    severity="error",
                    category="content",
                    message="No contact information found at the top of the resume.",
                    suggestion="Add your name, email, phone, and location at the top.",
                )
            )
            return

        # Check for email
        if "@" not in full_text:
            report.score -= 5
            report.issues.append(
                ATSIssue(
                    severity="warning",
                    category="content",
                    message="No email address detected in contact section.",
                    suggestion="Add a professional email address.",
                )
            )

        # Check for phone
        import re

        if not re.search(r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}", full_text):
            report.score -= 3
            report.issues.append(
                ATSIssue(
                    severity="warning",
                    category="content",
                    message="No phone number detected in contact section.",
                    suggestion="Add a phone number.",
                )
            )

    def _check_experience_content(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check quality of experience section."""
        experience = sections.get("experience", {})
        content = experience.get("content", [])

        if not content:
            return

        # Check for quantifiable achievements (numbers/percentages)
        has_metrics = False
        for line in content:
            import re

            if re.search(r"\d+[%+]?", line):
                has_metrics = True
                break

        if not has_metrics:
            report.score -= 5
            report.issues.append(
                ATSIssue(
                    severity="warning",
                    category="content",
                    message="No quantifiable achievements found in experience.",
                    suggestion="Add metrics (e.g., 'Increased sales by 25%', 'Managed team of 10').",
                )
            )

        # Check for action verbs
        action_verbs = {
            "led", "managed", "developed", "built", "designed", "implemented",
            "created", "improved", "reduced", "increased", "delivered",
            "launched", "optimized", "established", "achieved", "drove",
            "spearheaded", "orchestrated", "streamlined", "mentored",
        }
        has_action_verbs = False
        for line in content:
            first_word = line.strip().split()[0].lower() if line.strip() else ""
            if first_word in action_verbs:
                has_action_verbs = True
                break

        if not has_action_verbs:
            report.score -= 3
            report.issues.append(
                ATSIssue(
                    severity="info",
                    category="content",
                    message="Bullet points may not start with strong action verbs.",
                    suggestion="Start bullet points with action verbs like 'Led', 'Developed', 'Implemented'.",
                )
            )

    def _check_skills_content(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check quality of skills section."""
        skills = sections.get("skills", {})
        content = skills.get("content", [])

        if not content:
            return

        # Count approximate number of skills
        full_text = " ".join(content)
        skill_count = len(
            [s.strip() for s in full_text.replace(";", ",").split(",") if s.strip()]
        )

        if skill_count < 5:
            report.score -= 5
            report.issues.append(
                ATSIssue(
                    severity="warning",
                    category="content",
                    message=f"Only {skill_count} skills listed. Most competitive resumes have 8-15.",
                    suggestion="Add more relevant technical and soft skills.",
                )
            )

    def _check_summary_content(
        self, sections: dict, report: ATSReport
    ) -> None:
        """Check quality of summary section."""
        summary = sections.get("summary", {})
        content = summary.get("content", [])

        if not content:
            return

        full_text = " ".join(content)
        word_count = len(full_text.split())

        if word_count < 15:
            report.score -= 3
            report.issues.append(
                ATSIssue(
                    severity="info",
                    category="content",
                    message=f"Summary is very short ({word_count} words).",
                    suggestion="Aim for 30-60 words with key skills and experience highlights.",
                )
            )
        elif word_count > 80:
            report.score -= 3
            report.issues.append(
                ATSIssue(
                    severity="info",
                    category="content",
                    message=f"Summary is quite long ({word_count} words).",
                    suggestion="Keep summary concise, ideally 30-60 words.",
                )
            )
