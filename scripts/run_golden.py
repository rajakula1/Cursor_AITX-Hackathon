#!/usr/bin/env python3
"""Run the three golden fixtures and print status / export preview."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pa_agent.data.seed_store import clear_cases  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, list_fixtures, load_fixture  # noqa: E402
from pa_agent.graph import get_compiled_graph, run_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache  # noqa: E402
from pa_agent.tools.save_case import get_saved_case  # noqa: E402


def main() -> int:
    get_compiled_graph.cache_clear()
    ok = True
    for path in list_fixtures():
        clear_cases()
        clear_extract_cache()
        clear_mock_critic()
        fx = load_fixture(path.name)
        apply_fixture_mocks(fx)
        inp = fx["input"]
        expected = fx["expected"]["status"]
        result = run_case(
            drug_name=inp["drug_name"],
            diagnosis_code=inp["diagnosis_code"],
            payer_name=inp["payer_name"],
            clinical_note=inp["clinical_note"],
        )
        saved = get_saved_case(result["case_id"])
        match = result["status"] == expected
        ok = ok and match
        flag = "OK" if match else "FAIL"
        print(f"[{flag}] {fx['id']}: status={result['status']} expected={expected}")
        print(f"       case_id={result['case_id']} persisted={saved is not None}")
        if result.get("approval_likelihood") is not None:
            print(f"       likelihood={result['approval_likelihood']:.3f}")
        if result.get("alternative_suggestion"):
            print(f"       alternative={result['alternative_suggestion']}")
        if result.get("missing_fields"):
            print(f"       missing={result['missing_fields']}")
        export = (result.get("draft_pa_form") or {}).get("export_markdown") or ""
        preview = export.strip().splitlines()[:8]
        for line in preview:
            print(f"       | {line}")
        print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
