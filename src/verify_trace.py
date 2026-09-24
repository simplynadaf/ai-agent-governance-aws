"""
Read traces_gov.jsonl and print a plain-language GOVERNANCE report.

Like a compliance officer's at-a-glance view: which agents ran, which guardrails fired
(and at which tier), the decisions + reason codes, PII-redaction confirmation, and the
EU AI Act evidence stamped on the run. Everything printed is read straight from the trace
file - nothing invented.

Run:  python -m src.verify_trace            # reads traces_gov.jsonl
      python -m src.verify_trace path.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict


def load(path: str) -> list[dict]:
    spans = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for ss in json.loads(line).get("scopeSpans", []):
                spans += ss.get("spans", [])
    return spans


def A(s: dict, k: str):
    return s.get("attributes", {}).get(k)


def main(path: str = "traces_gov.jsonl") -> int:
    try:
        spans = load(path)
    except FileNotFoundError:
        print(f"No trace file at {path}. Run:  python -m src.demo_scenarios")
        return 1

    print("=" * 72)
    print(f"GOVERNANCE REPORT  ·  {path}  ·  {len(spans)} spans")
    print("=" * 72)

    # ---- agents that ran (distinct agent.id) ----
    agents = defaultdict(set)
    for s in spans:
        agents[A(s, "agent.id")].add(s.get("name"))
    print("\nAGENTS THAT RAN")
    for aid in sorted(k for k in agents if k):
        print(f"  · {aid}")

    # ---- guardrails fired (from findings JSON) ----
    fired = defaultdict(set)   # category -> set(source_type)
    for s in spans:
        f = A(s, "guardrail.findings")
        if not f:
            continue
        try:
            for finding in json.loads(f):
                fired[finding.get("category")].add(finding.get("source_type"))
        except Exception:
            pass
    print("\nGUARDRAILS DETECTED  (category - tier)")
    if fired:
        for cat, tiers in sorted(fired.items()):
            print(f"  · {cat:20} {', '.join(sorted(tiers))}")
    else:
        print("  (none)")

    # ---- explicit 3-tier coverage (A explicit / B provider-native / C heuristic) ----
    # Honest reporting: state which tiers were OBSERVED in this trace. Tier B (provider-
    # native: finish_reason / stop_reason / safety_ratings) only fires when the model itself
    # returns a native safety/stop signal, so it may legitimately be "not observed" on a
    # clean run. We do not claim a tier fired unless a real finding carries its source_type.
    all_srcs = set()
    for tiers in fired.values():
        all_srcs |= tiers
    tier_map = [
        ("A", "explicit",        "@observe(as_type=guardrail) / guardrail_span"),
        ("B", "provider_native", "model finish_reason / stop_reason / safety_ratings"),
        ("C", "heuristic",       "tool-error denial keywords"),
    ]
    print("\nGUARDRAIL TIER COVERAGE (observed in this trace)")
    for tier, src, desc in tier_map:
        mark = "YES" if src in all_srcs else "not observed"
        print(f"  · Tier {tier} ({src:15}) {mark:12} - {desc}")
    if "provider_native" not in all_srcs:
        print("    note: Tier B is provider-native; it fires only when the model returns a")
        print("          safety/stop signal. Absence here is expected on a clean run, not a gap.")

    # ---- blocks ----
    blocks = [s for s in spans if A(s, "demo.crew.blocked")]
    print(f"\nHARD BLOCKS: {len(blocks)}  (crew stopped before/at the boundary)")

    # ---- decisions + reason codes ----
    print("\nDECISIONS  (real, from the trace)")
    seen = set()
    for s in spans:
        d = A(s, "governance.decision")
        if d is None:
            continue
        codes = A(s, "governance.reason_codes")
        review = A(s, "governance.needs_human_review")
        key = (d, str(codes))
        if key in seen:
            continue
        seen.add(key)
        rv = "  [→ human review, Art. 14]" if review else ""
        print(f"  · {d.upper():8} reasons={codes}{rv}")

    # ---- compliance evidence coverage ----
    def any_has(k): return any(A(s, k) is not None for s in spans)
    def count_has(k): return sum(1 for s in spans if A(s, k) is not None)
    print("\nEU AI ACT / EVIDENCE COVERAGE")
    print(f"  · risk_tier stamped on         {count_has('eu_ai_act.risk_tier')}/{len(spans)} spans")
    print(f"  · annex_iii_category           {'YES' if any_has('eu_ai_act.annex_iii_category') else 'no'}")
    print(f"  · Art. 50 transparency         {'YES' if any_has('governance.transparency.disclosed') else 'no'}")
    print(f"  · integrity_hash present       {'YES' if any_has('governance.integrity_hash') else 'no'}")
    print(f"  · policy/model version stamped {'YES' if any_has('governance.policy_version') else 'no'}")
    print(f"  · PII redaction applied on     {count_has('governance.redaction_applied')}/{len(spans)} spans")

    # ---- honesty check: no raw PII in the trace ----
    blob = json.dumps([s.get("attributes", {}) for s in spans])
    leaked = sum(x in blob for x in ("john.doe@example.com", "123-45-6789"))
    print(f"\nPII LEAK CHECK: raw test PII found in {leaked} place(s)  (must be 0)")

    print("\n" + "=" * 72)
    print("Note: SYNTHETIC demo. Evidence substrate, not legal compliance.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "traces_gov.jsonl"))
