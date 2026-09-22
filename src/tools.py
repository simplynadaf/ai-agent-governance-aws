"""
Tools for the SYNTHETIC loan crew. All mock — no real bureau, no real network calls.

credit_score        : deterministic mock score (delegates to src.data.mock_credit_score)
pull_bureau_report  : region-restricted; raises a PERMISSION-DENIED error for EU applicants,
                      which makes Traccia's Tier-C heuristic guardrail fire on the tool span
                      (a tool/function span that errored with a denial keyword -> finding).
"""
from __future__ import annotations

from strands import tool
from traccia import observe

from src.data import mock_credit_score


class ToolPermissionDenied(Exception):
    """A denial-style tool error. Its message contains a denial keyword on purpose so the
    Tier-C heuristic guardrail classifies it as a tool_permission finding."""


@tool
@observe(as_type="tool")
def credit_score(applicant_id: str) -> dict:
    """MOCK deterministic credit score for a SYNTHETIC applicant. Not a real bureau."""
    return mock_credit_score(applicant_id)


@tool
@observe(as_type="tool")
def pull_bureau_report(applicant_id: str, region: str = "US") -> dict:
    """
    MOCK external bureau pull. Region-restricted: for EU applicants this raises a
    PERMISSION-DENIED error (data-residency), which Traccia's Tier-C heuristic guardrail
    detects on the errored tool span. US applicants get a mock report.
    """
    if region.upper() == "EU":
        # denial keyword ("permission denied") -> Tier C heuristic guardrail finding
        raise ToolPermissionDenied(
            "permission denied: cross-region bureau pull for EU applicant is not allowed "
            "(data residency). Route through the EU bureau connector."
        )
    return {"applicant_id": applicant_id, "report": "MOCK bureau report (synthetic)", "delinquencies": 0}
