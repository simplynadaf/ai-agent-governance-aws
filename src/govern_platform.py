"""
Phase 2 — PLATFORM governance payoff for the Loan Decision Crew (SYNTHETIC).

============================================================================================
  SYNTHETIC / ILLUSTRATIVE. Not a real lender. See loan_crew.py header.
============================================================================================

This is the platform-tier layer that the $0 SDK layer (loan_crew.py) cannot show:
  @govern(fail_open=False) on the CREW entrypoint -> networked runtime policy enforcement
  (Spend Cap, Model Boundary, Loop Cap) evaluated by the Traccia platform, raising
  AgentBlockedError with .reasons / .decision_id / .remaining_budget_usd on deny.

Requires the Traccia platform key (TRACCIA_API_KEY). We init WITH the key here so:
  - traces + governance evidence stream to the Governance Hub (registry, reviews, incidents,
    evidence packs, FRIA live in the dashboard),
  - @govern's before-body agent-status check runs (lagged next-run breaker), and
  - the per-call PEP fires on every instrumented LLM/tool call inside the governed run
    (Spend Cap / Model Boundary / Loop Cap).

IMPORTANT honest caveats (kept true to the SDK — see GOVERNANCE-DEEP-RESEARCH.md §6):
  - @govern defaults fail_open=True; we set fail_open=False for this high-risk crew, but the
    PER-CALL PEP is ALWAYS fail-open (a network blip cannot hard-block that call).
  - Whether a policy actually DENIES depends on the policies you configure in the dashboard
    for agent `loan-prescreen` (Spend Cap / Model Boundary / Loop Cap). With no policy set,
    the crew runs normally and the evidence still streams to the Hub.

Run:  TRACCIA_API_KEY=... python govern_platform.py
      (or put the key in .env — it is git-ignored — and `export $(grep -v '^#' .env | xargs)`)
"""
from __future__ import annotations

import os

from traccia import init, govern, AgentBlockedError, force_flush

_KEY = os.environ.get("TRACCIA_API_KEY", "").strip()
if not _KEY:
    raise SystemExit(
        "TRACCIA_API_KEY not set. Put it in .env (git-ignored) and export it, or pass it in the env.\n"
        "This Phase-2 script needs the platform key; the $0 beats are in loan_crew.py."
    )

# Initialize WITH the platform key so governance decisions + evidence reach the Governance Hub.
# Keep the same governed identity + compliance posture as loan_crew.py so the dashboard shows
# one coherent high-risk agent.
init(
    api_key=_KEY,
    agent_id="loan-prescreen",
    agent_name="Loan Decision Crew (SYNTHETIC)",
    env="dev",
    redact_pii=True,
    compliance={"frameworks": ["eu_ai_act"], "risk_tier": "high"},
)

# Import the crew AFTER init so its own top-level init() does not override ours. loan_crew.guarded_run
# still stamps Annex III, runs the injection guardrail, redaction, disclosure, and the sub-agents.
from src.loan_crew import guarded_run, BlockedByGuardrail  # noqa: E402


# @govern wraps the WHOLE crew run:
#  (A) before-body: agent-status check (fail_open=False -> raise if status cannot be verified),
#  (B) turns on the per-call PEP so Spend Cap / Model Boundary / Loop Cap are evaluated on every
#      instrumented LLM/tool call the crew makes (all sub-agents included).
@govern(fail_open=False, name="loan_crew")
def loan_crew_run(user_text: str) -> str:
    return guarded_run(user_text)


def main():
    print("=" * 78)
    print("Loan Decision Crew (SYNTHETIC) - PLATFORM governance (@govern) payoff")
    print("=" * 78)
    print("agent_id=loan-prescreen | fail_open=False | Spend/Model/Loop cap decided by platform")
    print()

    # A normal pre-screen under @govern. If a dashboard policy denies (e.g. Spend Cap or Loop
    # Cap), this raises AgentBlockedError with the real decision fields. If no policy denies,
    # the crew runs and the whole run's governance evidence streams to the Governance Hub.
    try:
        out = loan_crew_run("Pre-screen applicant A-77 requesting 8000. Applicant id: A-77.")
        print("ALLOWED (no platform policy denied this run):")
        print("  ", out.strip()[:200])
    except AgentBlockedError as e:
        # This is the on-camera platform BLOCK: networked policy stopped the crew.
        print("PLATFORM BLOCK — AgentBlockedError:")
        print("   reasons             :", e.reasons)
        print("   decision_id         :", e.decision_id)
        print("   remaining_budget_usd:", e.remaining_budget_usd)
    except BlockedByGuardrail as e:
        # The local Tier-A injection guardrail can still fire first (defense in depth).
        print("LOCAL GUARDRAIL BLOCK (before any model call):", e)

    force_flush(6.0)
    print("RUN-DONE")
    print()
    print("Evidence for this run is now in the Traccia Governance Hub (registry, reviews,")
    print("incidents, evidence packs, FRIA) for agent 'loan-prescreen'.")


if __name__ == "__main__":
    main()
