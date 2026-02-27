"""ATS Transformer: uses LLM to convert a parsed resume into ATS-standard format.

This produces the "core base" resume that all subsequent operations build on.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from resume_matcher.llm_client import get_llm_client
from resume_matcher.prompts import ATS_TRANSFORM_SYSTEM, ATS_TRANSFORM_USER

logger = logging.getLogger(__name__)


@dataclass
class ATSTransformResult:
    """Result of ATS transformation."""

    ats_resume: dict = field(default_factory=dict)
    changes_made: list[str] = field(default_factory=list)
    original_score: int = 0  # ATS score before transformation
    transformed_score: int = 0  # ATS score after transformation

    def to_dict(self) -> dict:
        return {
            "ats_resume": self.ats_resume,
            "changes_made": self.changes_made,
            "original_score": self.original_score,
            "transformed_score": self.transformed_score,
        }


class ATSTransformer:
    """Transforms a parsed resume into ATS-standard format using LLM."""

    def transform(self, parsed_resume: dict) -> ATSTransformResult:
        """Transform a parsed resume into ATS-standard format.

        Args:
            parsed_resume: Output from ResumeParser.to_dict()

        Returns:
            ATSTransformResult with the transformed resume and change log.
        """
        from resume_matcher.ats_optimizer import ATSOptimizer

        result = ATSTransformResult()
        optimizer = ATSOptimizer()

        # Score the original resume
        original_report = optimizer.check(parsed_resume)
        result.original_score = original_report.score

        # Call LLM to transform
        resume_json = json.dumps(parsed_resume, indent=2)
        prompt = ATS_TRANSFORM_USER.format(resume_json=resume_json)

        try:
            client = get_llm_client()
            transformed = client.complete_json(ATS_TRANSFORM_SYSTEM, prompt)
        except Exception as exc:
            logger.error("LLM ATS transformation failed: %s", exc)
            raise ValueError(f"ATS transformation failed: {exc}") from exc

        # Validate the LLM output has the expected structure
        if "sections" not in transformed:
            raise ValueError(
                "LLM returned invalid resume structure (missing 'sections' key)."
            )

        # Safety check: verify all companies, titles, dates are preserved
        self._validate_preservation(parsed_resume, transformed)

        # Score the transformed resume
        transformed_report = optimizer.check(transformed)
        result.transformed_score = transformed_report.score

        # Diff to find changes
        result.changes_made = self._diff_changes(parsed_resume, transformed)

        result.ats_resume = transformed
        return result

    def _validate_preservation(
        self, original: dict, transformed: dict
    ) -> None:
        """Verify that factual data (companies, titles, dates) are preserved.

        Raises ValueError if critical data is missing from the transformed version.
        """
        original_sections = original.get("sections", {})
        transformed_sections = transformed.get("sections", {})

        # Check experience entries are preserved
        orig_exp = original_sections.get("experience", {})
        trans_exp = transformed_sections.get("experience", {})

        orig_entries = orig_exp.get("entries", [])
        trans_entries = trans_exp.get("entries", [])

        if orig_entries and trans_entries:
            orig_companies = {e.get("company", "").lower() for e in orig_entries}
            trans_companies = {e.get("company", "").lower() for e in trans_entries}

            missing = orig_companies - trans_companies
            if missing:
                logger.warning(
                    "LLM dropped companies from resume: %s. Falling back.",
                    missing,
                )
                raise ValueError(
                    f"LLM removed companies from resume: {missing}"
                )

    def _diff_changes(self, original: dict, transformed: dict) -> list[str]:
        """Compare original and transformed to produce a change log."""
        changes: list[str] = []
        orig_sections = original.get("sections", {})
        trans_sections = transformed.get("sections", {})

        # Check for renamed headings
        for category in orig_sections:
            if category in trans_sections:
                old_heading = orig_sections[category].get("heading", "")
                new_heading = trans_sections[category].get("heading", "")
                if old_heading and new_heading and old_heading != new_heading:
                    changes.append(
                        f"Renamed '{old_heading}' → '{new_heading}'"
                    )

        # Check for content changes in each section
        for category in trans_sections:
            if category in orig_sections:
                old_content = orig_sections[category].get("content", [])
                new_content = trans_sections[category].get("content", [])
                if old_content != new_content:
                    changes.append(f"Updated {category} section content")

        # Check for new sections
        new_sections = set(trans_sections) - set(orig_sections)
        for s in new_sections:
            changes.append(f"Added {s} section")

        if not changes:
            changes.append("No significant changes needed")

        return changes
