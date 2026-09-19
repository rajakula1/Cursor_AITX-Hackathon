"""PA Intake & Auto-Draft — Streamlit UI (Block 7).

Demo data — not real PHI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pa_agent.config import get_settings, is_live_llm  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, load_fixture  # noqa: E402
from pa_agent.graph import run_case  # noqa: E402
from pa_agent.review import apply_human_edits, rescore_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache, clear_live_overrides  # noqa: E402

STATUS_COLORS = {
    "no_pa_required": "#1f6f4a",
    "auto_completed": "#1a4f8b",
    "needs_review": "#9a3412",
}


def _init_state() -> None:
    defaults = {
        "drug_name": "Humira",
        "diagnosis_code": "M06.9",
        "payer_name": "UHC",
        "clinical_note": "",
        "result": None,
        "last_fixture": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _load_fixture(name: str) -> None:
    fx = load_fixture(name)
    apply_fixture_mocks(fx)
    inp = fx["input"]
    st.session_state.drug_name = inp["drug_name"]
    st.session_state.diagnosis_code = inp["diagnosis_code"]
    st.session_state.payer_name = inp["payer_name"]
    st.session_state.clinical_note = inp["clinical_note"]
    st.session_state.last_fixture = fx["id"]
    st.session_state.result = None


def _run_pipeline() -> None:
    clear_extract_cache()
    clear_mock_critic()
    clear_live_overrides()
    # Live: apply_fixture_mocks only injects Fixture C hallucination (if enabled)
    # Mock: full fixture extract maps
    if st.session_state.last_fixture:
        try:
            apply_fixture_mocks(load_fixture(st.session_state.last_fixture))
        except Exception:
            clear_extract_cache()
            clear_mock_critic()
            clear_live_overrides()

    mode = "LIVE OpenRouter" if is_live_llm() else "MOCK (offline)"
    with st.spinner(f"Running PA agent graph ({mode})…"):
        result = run_case(
            drug_name=st.session_state.drug_name,
            diagnosis_code=st.session_state.diagnosis_code,
            payer_name=st.session_state.payer_name,
            clinical_note=st.session_state.clinical_note,
        )
    st.session_state.result = result


def _status_badge(status: str) -> None:
    color = STATUS_COLORS.get(status, "#444")
    st.markdown(
        f"""
        <div style="
            display:inline-block;
            padding:0.35rem 0.85rem;
            border-radius:4px;
            background:{color};
            color:#fff;
            font-weight:600;
            letter-spacing:0.02em;
            font-size:0.95rem;
        ">{status}</div>
        """,
        unsafe_allow_html=True,
    )


def _render_results(result: dict) -> None:
    status = result.get("status") or "needs_review"
    st.subheader("Result")
    cols = st.columns([1.2, 1, 1, 1.4])
    with cols[0]:
        st.caption("Status")
        _status_badge(status)
    with cols[1]:
        lik = result.get("approval_likelihood")
        st.metric("Approval likelihood", f"{lik:.2f}" if lik is not None else "—")
    with cols[2]:
        st.metric("Case", (result.get("case_id") or "")[:8] + "…")
    with cols[3]:
        alt = result.get("alternative_suggestion")
        st.caption("Formulary alternative")
        st.write(alt or "—")

    if result.get("human_review_notes"):
        st.info(result["human_review_notes"])

    extractions = result.get("extractions") or []
    missing = set(result.get("missing_fields") or [])

    st.subheader("Field review")
    st.caption(
        "Met / high-confidence fields are read-only. Unmet fields are editable — "
        "we escalate fields, not cases."
    )

    edits: dict[str, dict] = {}
    if not extractions and status == "no_pa_required":
        st.success("No PA required — extraction skipped.")
    elif not extractions:
        st.warning("No extractions on this case.")

    for ext in extractions:
        cid = ext.get("criterion_id") or "?"
        met = bool(ext.get("met"))
        editable = (not met) or (cid in missing)
        header = f"{'✓' if met else '○'} {cid} — {ext.get('criterion_text') or ''}"
        with st.expander(header, expanded=editable):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**quote_verified:** `{ext.get('quote_verified')}`")
                st.write(f"**confidence:** `{float(ext.get('confidence') or 0):.2f}`")
                st.write(f"**met:** `{met}`")
            with c2:
                note = ext.get("critic_note") or "—"
                st.write("**critic_note**")
                st.code(note, language=None)

            if editable:
                new_val = st.text_input(
                    f"Value ({cid})",
                    value=ext.get("value") or "",
                    key=f"val_{result.get('case_id')}_{cid}",
                )
                new_quote = st.text_area(
                    f"Quote — must appear in the clinical note ({cid})",
                    value=ext.get("quote") or "",
                    key=f"quote_{result.get('case_id')}_{cid}",
                    height=80,
                )
                new_conf = st.slider(
                    f"Confidence ({cid})",
                    0.0,
                    1.0,
                    float(ext.get("confidence") or 0.0),
                    0.01,
                    key=f"conf_{result.get('case_id')}_{cid}",
                )
                edits[cid] = {
                    "value": new_val.strip() or None,
                    "quote": new_quote.strip() or None,
                    "confidence": new_conf,
                }
            else:
                st.text_input(
                    f"Value ({cid})",
                    value=ext.get("value") or "",
                    disabled=True,
                    key=f"ro_val_{result.get('case_id')}_{cid}",
                )
                st.text_area(
                    f"Verified quote ({cid})",
                    value=ext.get("quote") or "",
                    disabled=True,
                    key=f"ro_quote_{result.get('case_id')}_{cid}",
                    height=80,
                )

    draft = result.get("draft_pa_form") or {}
    export = draft.get("export_markdown") or ""

    st.subheader("Export")
    st.caption("Paste into a portal or fax cover sheet.")
    st.text_area(
        "export_markdown",
        value=export,
        height=280,
        key=f"export_{result.get('case_id')}",
    )
    st.download_button(
        "Download export markdown",
        data=export,
        file_name=f"pa_draft_{result.get('case_id', 'case')}.md",
        mime="text/markdown",
    )

    r1, r2 = st.columns(2)
    with r1:
        if st.button("Re-score (no re-extract)", type="secondary", use_container_width=True):
            if edits:
                patched = apply_human_edits(result, edits)
            else:
                patched = result
            with st.spinner("Re-scoring…"):
                st.session_state.result = rescore_case(patched)
            st.rerun()
    with r2:
        if st.button("Clear result", use_container_width=True):
            st.session_state.result = None
            st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="PA Intake Agent",
        layout="wide",
    )
    _init_state()

    st.markdown(
        """
        <div style="
            background:#fff7ed;
            border:1px solid #fdba74;
            color:#9a3412;
            padding:0.65rem 1rem;
            border-radius:6px;
            margin-bottom:0.75rem;
            font-weight:600;
        ">
            Demo data — not real PHI. Synthetic notes only. Do not paste real patient text.
        </div>
        """,
        unsafe_allow_html=True,
    )
    if is_live_llm():
        st.warning(
            "**LIVE mode:** notes are sent to OpenRouter (third party). "
            "Use synthetic demo notes only — never real PHI."
        )

    st.title("PA Intake & Auto-Draft Agent")
    st.caption(
        "Escalate fields, not cases · quote-span check in code · second-model critic · math score"
    )

    with st.sidebar:
        st.header("Demo fixtures")
        st.caption("Rehearse in order: **C → A → B**")
        demo_order = [
            "fixture_c_needs_review.json",
            "fixture_a_no_pa.json",
            "fixture_b_auto_completed.json",
        ]
        for fname in demo_order:
            fx = load_fixture(fname)
            label = f"{fx['id']} → {fx['expected']['status']}"
            if st.button(label, key=f"fx_{fx['id']}", use_container_width=True):
                _load_fixture(fname)
                st.rerun()
        st.divider()
        settings = get_settings()
        if is_live_llm():
            st.success("Mode: **LIVE** OpenRouter")
            st.caption(
                f"Haiku `{settings.extract_model}` · Sonnet `{settings.critic_model}`"
            )
        else:
            st.warning("Mode: **MOCK** (`USE_MOCK_EXTRACT=1`)")
            st.caption("Set `USE_MOCK_EXTRACT=0` + real key in `.env` for live calls.")
        st.caption(
            "Talk-track #2: set `INJECT_FIXTURE_C_HALLUCINATION=1` in `.env` "
            "to force Fixture C's fake c3 quote (default off)."
        )
        if st.button("Run break-it empty note", use_container_width=True):
            st.session_state.drug_name = "Ozempic"
            st.session_state.diagnosis_code = "E11.9"
            st.session_state.payer_name = "Aetna"
            st.session_state.clinical_note = ""
            st.session_state.last_fixture = None
            st.session_state.result = None
            st.rerun()
        if st.button("Run break-it unknown drug", use_container_width=True):
            st.session_state.drug_name = "NotARealDrugXYZ"
            st.session_state.diagnosis_code = "M06.9"
            st.session_state.payer_name = "UHC"
            st.session_state.clinical_note = "Demo data — not real PHI. Follow-up only."
            st.session_state.last_fixture = None
            st.session_state.result = None
            st.rerun()

    left, right = st.columns([1, 1.15])

    with left:
        st.subheader("Intake")
        st.session_state.drug_name = st.text_input(
            "Drug name", st.session_state.drug_name
        )
        st.session_state.diagnosis_code = st.text_input(
            "Diagnosis (ICD-10)", st.session_state.diagnosis_code
        )
        st.session_state.payer_name = st.text_input(
            "Payer", st.session_state.payer_name
        )
        st.session_state.clinical_note = st.text_area(
            "Clinical note",
            st.session_state.clinical_note,
            height=260,
        )
        if st.session_state.last_fixture:
            st.caption(f"Loaded fixture: `{st.session_state.last_fixture}`")

        if st.button("Run PA agent", type="primary", use_container_width=True):
            _run_pipeline()
            st.rerun()

    with right:
        if st.session_state.result:
            _render_results(st.session_state.result)
        else:
            st.subheader("Result")
            st.write(
                "Load a golden fixture from the sidebar (lead with **fixture_c** for the demo), "
                "then click **Run PA agent**."
            )


if __name__ == "__main__":
    main()
