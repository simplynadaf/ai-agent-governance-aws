"""
Synthetic applicant data + a deterministic mock credit model for the loan-decision demo.

============================================================================================
  EVERYTHING HERE IS SYNTHETIC. The applicants are invented, the scoring model is a mock
  heuristic (NOT a real bureau, NOT a real model), and no output is a real credit decision.
============================================================================================

The model is DETERMINISTIC (same input -> same score) so the demo is reproducible on camera
and in tests. It deliberately uses ONLY legitimate financial signals (income, existing debt,
requested amount, employment years) and NEVER a protected attribute - the fairness guardrail
in guardrails.py asserts exactly that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Applicant:
    """A SYNTHETIC loan applicant. All values invented for the demo."""
    applicant_id: str
    name: str                      # synthetic; redacted in traces
    email: str                     # synthetic; redacted in traces
    phone: str                     # synthetic; redacted in traces
    annual_income: int
    existing_debt: int
    employment_years: float
    requested_amount: int
    region: str = "US"
    # Present in the record but MUST NOT influence scoring (fairness guardrail checks this):
    age: Optional[int] = None
    protected_note: str = field(default="age is recorded but never used in scoring", repr=False)


# A small, varied synthetic book so the demo shows different outcomes (approve / refer / decline),
# not one hardcoded score. Free-text `raw_text` mimics what a real intake form would submit.
SYNTHETIC_APPLICANTS = {
    "A-42": Applicant(
        applicant_id="A-42", name="Jordan Rivera", email="jordan.rivera@example.com",
        phone="555-0142", annual_income=92000, existing_debt=6000, employment_years=5.0,
        requested_amount=5000, region="US", age=34,
    ),
    "A-77": Applicant(
        applicant_id="A-77", name="Sam Delacroix", email="sam.delacroix@example.com",
        phone="555-0177", annual_income=48000, existing_debt=21000, employment_years=1.0,
        requested_amount=20000, region="US", age=29,
    ),
    "A-13": Applicant(
        applicant_id="A-13", name="Priya Nair", email="priya.nair@example.com",
        phone="555-0113", annual_income=61000, existing_debt=12000, employment_years=2.5,
        requested_amount=15000, region="US", age=41,
    ),
    "A-99": Applicant(
        applicant_id="A-99", name="Chris Vandenberg", email="chris.v@example.com",
        phone="555-0199", annual_income=150000, existing_debt=4000, employment_years=9.0,
        requested_amount=8000, region="EU", age=52,   # EU region -> bureau pull is region-restricted (Tier C demo)
    ),
}


def intake_text(applicant_id: str) -> str:
    """Return the free-text an applicant 'submitted' (includes PII, to demo redaction)."""
    a = SYNTHETIC_APPLICANTS[applicant_id]
    return (
        f"Applicant {a.name} (id {a.applicant_id}) requests a loan of ${a.requested_amount}. "
        f"Annual income ${a.annual_income}, existing debt ${a.existing_debt}, "
        f"{a.employment_years} years employed. Contact: {a.email}, {a.phone}."
    )


def mock_credit_score(applicant_id: str) -> dict:
    """
    DETERMINISTIC mock credit score (300-850) from legitimate signals only. NOT a real bureau.

    Uses income-to-debt, employment stability, and requested-amount-to-income. Deliberately
    ignores `age` and any protected attribute. Same input -> same output.
    """
    a = SYNTHETIC_APPLICANTS[applicant_id]
    score = 550
    # income vs existing debt
    dti = a.existing_debt / max(a.annual_income, 1)
    if dti < 0.10:
        score += 120
    elif dti < 0.25:
        score += 70
    elif dti < 0.40:
        score += 20
    else:
        score -= 40
    # employment stability
    score += int(min(a.employment_years, 8) * 12)
    # requested amount vs income
    ratio = a.requested_amount / max(a.annual_income, 1)
    if ratio > 0.40:
        score -= 60
    elif ratio > 0.20:
        score -= 20
    score = max(300, min(850, score))
    band = "excellent" if score >= 750 else "good" if score >= 680 else "fair" if score >= 600 else "poor"
    return {
        "applicant_id": applicant_id, "score": score, "band": band,
        "signals_used": ["annual_income", "existing_debt", "employment_years", "requested_amount"],
        "signals_excluded": ["age", "name", "region", "gender", "ethnicity"],
        "source": "MOCK_MODEL (synthetic, not a real bureau)",
    }


# Adverse-action / explainability reason codes. Real high-risk credit systems must give the
# applicant the principal reasons for a decision (a legal requirement in many jurisdictions,
# and an EU AI Act transparency/explainability signal). These are derived, not invented.
REASON_CODE_LABELS = {
    "HIGH_DTI": "Debt-to-income ratio is high",
    "THIN_FILE": "Limited employment / credit history",
    "LARGE_REQUEST": "Requested amount is large relative to income",
    "LOW_SCORE": "Overall credit score below threshold",
    "STRONG_PROFILE": "Strong income-to-debt and credit profile",
    "BORDERLINE": "Profile is near the decision threshold",
}


def reason_codes(applicant_id: str, score: int) -> list[str]:
    """Derive principal-reason codes for a decision (explainability / adverse action)."""
    a = SYNTHETIC_APPLICANTS[applicant_id]
    dti = a.existing_debt / max(a.annual_income, 1)
    ratio = a.requested_amount / max(a.annual_income, 1)
    codes: list[str] = []
    if dti >= 0.40:
        codes.append("HIGH_DTI")
    if a.employment_years < 2:
        codes.append("THIN_FILE")
    if ratio > 0.40:
        codes.append("LARGE_REQUEST")
    if score < 600:
        codes.append("LOW_SCORE")
    # borderline band (fair) is itself a principal reason for a refer decision
    if 600 <= score < 700:
        codes.append("BORDERLINE")
    if not codes:
        codes.append("STRONG_PROFILE")
    return codes
