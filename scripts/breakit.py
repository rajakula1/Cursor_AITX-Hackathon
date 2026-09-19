#!/usr/bin/env python3
"""Break-it smoke: empty / unknown / hallucinated — must not crash."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pa_agent.data.seed_store import clear_cases  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, load_fixture  # noqa: E402
from pa_agent.graph import get_compiled_graph, run_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache  # noqa: E402

PUBLIC = {"no_pa_required", "auto_completed", "needs_review"}


def _reset() -> None:
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def main() -> int:
    cases = [
        ("empty_note", dict(
            drug_name="Ozempic", diagnosis_code="E11.9", payer_name="Aetna",
            clinical_note="",
        )),
        ("unknown_drug", dict(
            drug_name="NotARealDrugXYZ", diagnosis_code="M06.9", payer_name="UHC",
            clinical_note="Demo data — not real PHI.",
        )),
        ("unknown_payer", dict(
            drug_name="Humira", diagnosis_code="M06.9", payer_name="FakePayer",
            clinical_note="Demo data — not real PHI.",
        )),
    ]

    print("Break-it smoke (must not crash; public status only)")
    ok = True
    for label, kwargs in cases:
        _reset()
        try:
            result = run_case(**kwargs)
            status = result.get("status")
            safe = status in PUBLIC and bool(result.get("case_id"))
            ok = ok and safe
            print(f"  [{'OK' if safe else 'FAIL'}] {label}: status={status}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  [CRASH] {label}: {exc}")

    _reset()
    fx = load_fixture("fixture_c_needs_review")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    try:
        result = run_case(
            drug_name=inp["drug_name"],
            diagnosis_code=inp["diagnosis_code"],
            payer_name=inp["payer_name"],
            clinical_note=inp["clinical_note"],
        )
        by_id = {e["criterion_id"]: e for e in result["extractions"]}
        c3_ok = (
            result["status"] == "needs_review"
            and by_id["c3"]["confidence"] == 0.0
            and by_id["c3"]["quote_verified"] is False
        )
        ok = ok and c3_ok
        print(
            f"  [{'OK' if c3_ok else 'FAIL'}] hallucinated_quote (fixture_c): "
            f"c3 conf={by_id['c3']['confidence']} verified={by_id['c3']['quote_verified']}"
        )
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  [CRASH] hallucinated_quote: {exc}")

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
