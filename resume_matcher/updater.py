"""Resume Updater: modifies resume content to better match a job description."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field

from resume_matcher.ats_optimizer import ATS_STANDARD_SECTIONS, HEADING_RENAMES


@dataclass
class UpdateResult:
    """Result of updating a resume to match a job description."""

    updated_sections: dict = field(default_factory=dict)
    changes_made: list[str] = field(default_factory=list)
    keywords_added: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "updated_sections": self.updated_sections,
            "changes_made": self.changes_made,
            "keywords_added": self.keywords_added,
        }


class ResumeUpdater:
    """Updates resume content based on match analysis and ATS checks."""

    def update(
        self,
        resume_data: dict,
        match_report: dict,
        ats_report: dict | None = None,
    ) -> UpdateResult:
        """Update resume content to better match the job description.

        Args:
            resume_data: Parsed resume from ResumeParser.to_dict()
            match_report: From MatchAnalyzer.analyze().to_dict()
            ats_report: Optional ATS report from ATSOptimizer.check().to_dict()

        Returns:
            UpdateResult with modified sections and change log.
        """
        result = UpdateResult()
        sections = deepcopy(resume_data.get("sections", {}))

        # Step 1: Fix ATS heading issues
        if ats_report:
            self._fix_headings(sections, ats_report, result)

        # Step 2: Add missing keywords to skills section
        self._update_skills(sections, match_report, result)

        # Step 3: Enhance experience bullets with missing keywords
        self._update_experience(sections, match_report, result)

        # Step 4: Update summary with key terms
        self._update_summary(sections, match_report, result)

        result.updated_sections = sections
        return result

    def _fix_headings(
        self, sections: dict, ats_report: dict, result: UpdateResult
    ) -> None:
        """Rename section headings to ATS-standard names."""
        suggestions = ats_report.get("heading_suggestions", {})
        for category, data in sections.items():
            heading = data.get("heading", "")
            if heading in suggestions:
                new_heading = suggestions[heading]
                data["heading"] = new_heading
                result.changes_made.append(
                    f"Renamed heading '{heading}' → '{new_heading}'"
                )

    def _update_skills(
        self, sections: dict, match_report: dict, result: UpdateResult
    ) -> None:
        """Add missing keywords to the skills section."""
        missing = match_report.get("missing_keywords", [])
        placement = match_report.get("keyword_placement", {})

        # Get keywords that should go into skills
        skills_to_add = [kw for kw in missing if placement.get(kw) == "skills"]
        if not skills_to_add:
            return

        skills_section = sections.get("skills")
        if not skills_section:
            # Create skills section if it doesn't exist
            sections["skills"] = {
                "heading": "Skills",
                "content": [],
            }
            skills_section = sections["skills"]
            result.changes_made.append("Added missing 'Skills' section")

        # Get existing skills text
        existing_content = skills_section.get("content", [])
        existing_text = " ".join(existing_content).lower()

        # Filter out keywords already present (case-insensitive)
        new_skills = [
            kw for kw in skills_to_add
            if kw.lower() not in existing_text
        ]

        if new_skills:
            # Append new skills to the existing skills line
            if existing_content:
                # Add to the last line of skills
                last_line = existing_content[-1]
                # Capitalize skill names properly
                formatted = [self._format_skill(s) for s in new_skills]
                updated_line = last_line.rstrip(", ") + ", " + ", ".join(formatted)
                existing_content[-1] = updated_line
            else:
                formatted = [self._format_skill(s) for s in new_skills]
                existing_content.append(", ".join(formatted))

            skills_section["content"] = existing_content
            result.keywords_added.extend(new_skills)
            result.changes_made.append(
                f"Added {len(new_skills)} skills: {', '.join(new_skills[:10])}"
            )

    def _update_experience(
        self, sections: dict, match_report: dict, result: UpdateResult
    ) -> None:
        """Enhance experience bullet points with relevant missing keywords."""
        missing = match_report.get("missing_keywords", [])
        placement = match_report.get("keyword_placement", {})

        exp_keywords = [kw for kw in missing if placement.get(kw) == "experience"]
        if not exp_keywords:
            return

        experience = sections.get("experience")
        if not experience:
            return

        content = experience.get("content", [])
        if not content:
            return

        # Try to weave keywords into existing bullet points
        keywords_used: list[str] = []
        updated_content: list[str] = []

        for line in content:
            updated_line = line
            # Check if this is a bullet point (not a job title line)
            is_bullet = not re.match(
                r"^[A-Z][\w\s]+\s*[—\-–]\s*\w", line
            )
            if is_bullet and exp_keywords:
                # Try to naturally append a relevant keyword
                for kw in list(exp_keywords):
                    if kw.lower() not in line.lower() and kw not in keywords_used:
                        # Add keyword context to bullet point
                        updated_line = self._enhance_bullet(line, kw)
                        if updated_line != line:
                            keywords_used.append(kw)
                            exp_keywords.remove(kw)
                            break

            updated_content.append(updated_line)

        experience["content"] = updated_content
        if keywords_used:
            result.keywords_added.extend(keywords_used)
            result.changes_made.append(
                f"Enhanced {len(keywords_used)} experience bullets with keywords: "
                f"{', '.join(keywords_used[:10])}"
            )

    def _update_summary(
        self, sections: dict, match_report: dict, result: UpdateResult
    ) -> None:
        """Add key missing terms to the professional summary."""
        missing = match_report.get("missing_keywords", [])
        if not missing:
            return

        summary = sections.get("summary")
        if not summary:
            return

        content = summary.get("content", [])
        if not content:
            return

        # Pick top 3 missing keywords to weave into summary
        summary_text = " ".join(content).lower()
        keywords_for_summary = []
        for kw in missing[:5]:
            if kw.lower() not in summary_text:
                keywords_for_summary.append(kw)
            if len(keywords_for_summary) >= 3:
                break

        if keywords_for_summary:
            formatted = [self._format_skill(kw) for kw in keywords_for_summary]
            # Append a clause to the summary
            addition = f" Skilled in {', '.join(formatted)}."
            content[-1] = content[-1].rstrip(".") + "." + addition
            summary["content"] = content
            result.keywords_added.extend(keywords_for_summary)
            result.changes_made.append(
                f"Added key terms to summary: {', '.join(keywords_for_summary)}"
            )

    def _enhance_bullet(self, bullet: str, keyword: str) -> str:
        """Try to naturally enhance a bullet point with a keyword."""
        formatted_kw = self._format_skill(keyword)
        # Append "utilizing {keyword}" or "leveraging {keyword}"
        clean = bullet.rstrip(".")
        return f"{clean}, utilizing {formatted_kw}."

    def _format_skill(self, skill: str) -> str:
        """Format a skill keyword for display (capitalize properly)."""
        # Keep known acronyms uppercase
        if len(skill) <= 4 and skill.isalpha():
            return skill.upper() if len(skill) <= 3 else skill.title()
        # Keep terms with special chars as-is (e.g. c++, node.js)
        if not skill.isalpha():
            return skill
        return skill.title()
