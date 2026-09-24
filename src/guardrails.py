"""
Guardrails for the SYNTHETIC loan crew - covering every Traccia guardrail tier + category.

Tier A (explicit, @observe(as_type="guardrail") / guardrail_span):
  - prompt_injection_detector   (block)   -> stops the whole crew before any model call
  - pii_scanner                 (warn)    -> records a PII finding (redaction still masks values)
  - output_validation           (block)   -> rejects unsafe/absolute recommendations
  - fairness_check              (block)   -> rejects any decision that used a protected attribute

Tier C (heuristic) fires automatically when a tool span errors with a denial keyword - we
demonstrate it with a region-restricted bureau pull (see tools.py: pull_bureau_report).

All of these are DETECTION + our own control-flow enforcement (the SDK's guardrail engine is
detection-only; the block is our raise). Kept honest.
"""
from __future__ import annotations

from traccia import observe

# ---- prompt injection --------------------------------------------------------------------
INJECTION_KEYWORDS = [
    "ignore previous", "ignore all", "disregard", "approve everyone",
    "override policy", "bypass", "forget your instructions", "approve all",
]

# ---- output validation: recommendations must be ILLUSTRATIVE, never an absolute decision --
FORBIDDEN_OUTPUT_PHRASES = [
    "you are approved", "loan approved", "guaranteed approval", "definitely approved",
    "you will receive", "unconditionally approve",
]

# ---- fairness: protected attributes that must never drive a decision ----------------------
PROTECTED_ATTRIBUTES = ["age", "gender", "sex", "race", "ethnicity", "religion", "nationality", "marital"]


class GuardrailBlock(Exception):
    """Raised by a block-mode guardrail. Carries the category for the on-screen callout."""
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@observe(
    as_type="guardrail",
    attributes={
        "guardrail.name": "prompt_injection_detector",
        "guardrail.category": "prompt_injection",
        "guardrail.enforcement_mode": "block",
        "guardrail.policy_id": "policy-loan-inj-v1.0",
    },
)
def injection_check(text: str) -> bool:
    """True if the input looks like a prompt-injection / policy-override attempt."""
    lowered = text.lower()
    return any(kw in lowered for kw in INJECTION_KEYWORDS)


@observe(
    as_type="guardrail",
    attributes={
        "guardrail.name": "output_validation",
        "guardrail.category": "output_validation",
        "guardrail.enforcement_mode": "block",
        "guardrail.policy_id": "policy-loan-out-v1.0",
    },
)
def output_validation_triggered(recommendation: str) -> bool:
    """True if the recommendation makes an absolute/unsafe claim (a SYNTHETIC demo must not)."""
    low = recommendation.lower()
    return any(p in low for p in FORBIDDEN_OUTPUT_PHRASES)


@observe(
    as_type="guardrail",
    attributes={
        "guardrail.name": "fairness_check",
        "guardrail.category": "output_validation",
        "guardrail.enforcement_mode": "block",
        "guardrail.policy_id": "policy-loan-fairness-v1.0",
    },
)
def fairness_violation(signals_used: list) -> bool:
    """True if the scoring used any protected attribute. High-risk credit must not (EU AI Act)."""
    used = " ".join(str(s).lower() for s in (signals_used or []))
    return any(p in used for p in PROTECTED_ATTRIBUTES)
