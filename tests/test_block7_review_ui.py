"""Block 7 helpers: human edit + re-score path."""

from __future__ import annotations

from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import apply_fixture_mocks, load_fixture
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.review import apply_human_edits, rescore_case
from pa_agent.tools.critique import clear_mock_critic
from pa_agent.tools.extract import clear_extract_cache


def setup_function():
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def test_rescore_after_fixing_missing_fields_can_auto_complete():
    fx = load_fixture("fixture_c_needs_review")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "needs_review"
    assert set(result["missing_fields"]) == {"c3", "c4"}

    # Provide verified quotes that actually appear in the Fixture C note
    note = inp["clinical_note"]
    # c3 truly missing TB — inventing a quote not in note must still fail
    bad = apply_human_edits(
        result,
        {
            "c3": {
                "value": "TB negative",
                "quote": "Completely fabricated TB result not in chart.",
                "confidence": 0.95,
            }
        },
    )
    by_id = {e["criterion_id"]: e for e in bad["extractions"]}
    assert by_id["c3"]["quote_verified"] is False
    assert by_id["c3"]["met"] is False

    # Fix c4 with text that is in the note (rheumatology consult requested)
    quote_c4 = (
        "rheumatology consult has been requested but not completed."
    )
    assert quote_c4.lower() in note.lower() or quote_c4 in note
    # Use exact substring from note
    for line in note.replace("\n", " ").split("."):
        if "rheumatology consult" in line.lower():
            quote_c4 = line.strip() + ("." if not line.strip().endswith(".") else "")
            if quote_c4.rstrip(".") in note or line.strip() in note:
                quote_c4 = line.strip()
                break

    # Pull exact span from note
    span = "rheumatology consult has been requested but not completed"
    assert span in note
    patched = apply_human_edits(
        result,
        {
            "c4": {
                "value": "rheumatology consult requested",
                "quote": span,
                "confidence": 0.85,
            }
        },
    )
    by_id = {e["criterion_id"]: e for e in patched["extractions"]}
    assert by_id["c4"]["quote_verified"] is True
    assert by_id["c4"]["met"] is True

    rescored = rescore_case(patched)
    # c3 still missing → still needs_review, but missing only c3
    assert rescored["status"] == "needs_review"
    assert rescored["missing_fields"] == ["c3"]
    assert rescored["draft_pa_form"]["export_markdown"]
    assert rescored["approval_likelihood"] is not None
