#!/usr/bin/env python3
"""Demo rehearsal — Fixture C (messy) → A (fast path) → B (auto-complete).

Matches spec §9 order + §10 90-second talk track.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pa_agent.data.seed_store import clear_cases  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, load_fixture  # noqa: E402
from pa_agent.graph import get_compiled_graph, run_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache  # noqa: E402

# Spec §9 demo order: messy first, then fast path, then auto-complete
DEMO_ORDER = [
    "fixture_c_needs_review",
    "fixture_a_no_pa",
    "fixture_b_auto_completed",
]

TALK_TRACK = [
    (
        "fixture_c_needs_review",
        [
            '1. "We escalate fields, not cases." → show unmet checklist (c3, c4).',
            '2. "The model cannot invent evidence." → c3 quote_verified=false, confidence=0.',
            '3. "A second model critiques the first, then math scores approval."',
            '4. "Likely deny → same-class option that does not need PA." → etanercept.',
            "5. Paste the markdown. Stop talking.",
        ],
    ),
    (
        "fixture_a_no_pa",
        [
            "Fast path: policy says no PA — extraction skipped, status no_pa_required.",
        ],
    ),
    (
        "fixture_b_auto_completed",
        [
            "Happy path: all quotes verified → auto_completed, likelihood ≥ 0.75.",
        ],
    ),
]


def _reset() -> None:
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def _run_one(name: str) -> dict:
    _reset()
    fx = load_fixture(name)
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    return {"fixture": fx, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="PA Intake demo rehearsal")
    parser.add_argument(
        "--talk",
        action="store_true",
        help="Print 90-second talk track prompts",
    )
    args = parser.parse_args()

    print("=" * 64)
    print("PA Intake demo — order: C (messy) → A (fast) → B (auto)")
    print("Demo data — not real PHI.")
    print("=" * 64)

    if args.talk:
        print("\n--- 90-second talk track ---\n")
        for fid, lines in TALK_TRACK:
            print(f"[{fid}]")
            for line in lines:
                print(f"  {line}")
            print()

    ok = True
    for name in DEMO_ORDER:
        bundle = _run_one(name)
        fx = bundle["fixture"]
        result = bundle["result"]
        expected = fx["expected"]["status"]
        match = result["status"] == expected
        ok = ok and match
        flag = "OK" if match else "FAIL"

        print(f"\n[{flag}] {fx['id']}")
        print(f"  status={result['status']}  expected={expected}")
        if result.get("approval_likelihood") is not None:
            print(f"  likelihood={result['approval_likelihood']:.3f}")
        if result.get("alternative_suggestion"):
            print(f"  alternative={result['alternative_suggestion']}")
        if result.get("missing_fields"):
            print(f"  missing_fields={result['missing_fields']}")

        if name == "fixture_c_needs_review":
            by_id = {e["criterion_id"]: e for e in result.get("extractions") or []}
            c3 = by_id.get("c3") or {}
            print(
                f"  c3: quote_verified={c3.get('quote_verified')} "
                f"confidence={c3.get('confidence')} "
                f"(hallucinated quote rejected in code)"
            )
            for ext in result.get("extractions") or []:
                mark = "MET" if ext.get("met") else "UNMET"
                print(
                    f"    [{mark}] {ext['criterion_id']}: "
                    f"conf={float(ext.get('confidence') or 0):.2f} "
                    f"| {ext.get('critic_note') or ''}"
                )

        export = (result.get("draft_pa_form") or {}).get("export_markdown") or ""
        print(f"  export_chars={len(export)}")

        # Spec assertions for the lead demo
        if name == "fixture_c_needs_review":
            ok = ok and len(result.get("missing_fields") or []) == 2
            ok = ok and bool(result.get("alternative_suggestion"))
            lik = result.get("approval_likelihood")
            ok = ok and lik is not None and 0.30 <= lik <= 0.50
        if name == "fixture_b_auto_completed":
            ok = ok and (result.get("approval_likelihood") or 0) >= 0.75
            ok = ok and bool(export)
            ok = ok and all(
                e.get("quote_verified") for e in (result.get("extractions") or [])
            )

    print("\n" + ("ALL DEMO CHECKS PASSED" if ok else "DEMO CHECKS FAILED"))
    print("\nUI: streamlit run app.py  → load fixture_c first for judges.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
