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
from pa_agent.data.supabase_client import health_check, is_configured  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, load_fixture  # noqa: E402
from pa_agent.graph import run_case  # noqa: E402
from pa_agent.review import apply_human_edits, rescore_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache, clear_live_overrides  # noqa: E402

STATUS_META = {
    "no_pa_required": {
        "label": "No PA required",
        "color": "green",
        "icon": ":material/check_circle:",
    },
    "auto_completed": {
        "label": "Auto completed",
        "color": "blue",
        "icon": ":material/task_alt:",
    },
    "needs_review": {
        "label": "Needs review",
        "color": "orange",
        "icon": ":material/rate_review:",
    },
}

DEMO_FIXTURES = [
    ("fixture_c_needs_review.json", "1 · Needs review", "Lead with this for the 90s talk track"),
    ("fixture_a_no_pa.json", "2 · No PA", "Fast path — policy says no prior auth"),
    ("fixture_b_auto_completed.json", "3 · Auto completed", "Full criteria met, paste-ready draft"),
]


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
    # Keep extract cache across identical note+criterion runs (big live win).
    # Fixture mocks still clear/rebuild via apply_fixture_mocks when loaded.
    clear_mock_critic()
    clear_live_overrides()
    if st.session_state.last_fixture:
        try:
            apply_fixture_mocks(load_fixture(st.session_state.last_fixture))
        except Exception:
            clear_extract_cache()
            clear_mock_critic()
            clear_live_overrides()

    mode = "LIVE OpenRouter" if is_live_llm() else "MOCK (offline)"
    with st.spinner(f"Running PA agent ({mode})…"):
        result = run_case(
            drug_name=st.session_state.drug_name,
            diagnosis_code=st.session_state.diagnosis_code,
            payer_name=st.session_state.payer_name,
            clinical_note=st.session_state.clinical_note,
        )
    st.session_state.result = result


@st.cache_data(ttl=30, show_spinner=False)
def _cached_supabase_health() -> dict:
    return health_check()


def _status_badge(status: str) -> None:
    meta = STATUS_META.get(
        status,
        {"label": status, "color": "gray", "icon": ":material/help:"},
    )
    st.badge(meta["label"], icon=meta["icon"], color=meta["color"])


def _render_empty_result() -> None:
    with st.container(border=True):
        st.markdown("### Ready when you are")
        st.markdown(
            """
1. Load a demo fixture from the sidebar (**start with Needs review**)
2. Skim the intake fields and clinical note
3. Click **Run PA agent**
            """
        )
        st.caption(
            "Tip: escalate fields, not cases — edit unmet criteria, then re-score."
        )


def _render_field_review(result: dict, *, missing: set[str]) -> dict[str, dict]:
    extractions = result.get("extractions") or []
    status = result.get("status") or "needs_review"
    edits: dict[str, dict] = {}

    if not extractions and status == "no_pa_required":
        st.success("No prior auth required — extraction skipped.", icon=":material/verified:")
        return edits
    if not extractions:
        st.warning("No extractions on this case.")
        return edits

    unmet = [
        e
        for e in extractions
        if (not e.get("met")) or (e.get("criterion_id") in missing)
    ]
    unmet_ids = {e.get("criterion_id") for e in unmet}
    met = [e for e in extractions if e.get("criterion_id") not in unmet_ids]

    if unmet:
        st.markdown(f"**Needs attention** ({len(unmet)})")
        for ext in unmet:
            edits.update(_render_criterion(ext, result, editable=True))
    if met:
        st.markdown(f"**Met** ({len(met)})")
        for ext in met:
            _render_criterion(ext, result, editable=False)

    return edits


def _render_criterion(ext: dict, result: dict, *, editable: bool) -> dict[str, dict]:
    cid = ext.get("criterion_id") or "?"
    met = bool(ext.get("met"))
    verified = bool(ext.get("quote_verified"))
    conf = float(ext.get("confidence") or 0)
    title = f"{cid} — {ext.get('criterion_text') or ''}"
    edits: dict[str, dict] = {}

    with st.expander(title, expanded=editable):
        chips = st.container(horizontal=True, gap="small")
        with chips:
            st.badge(
                "Met" if met else "Unmet",
                icon=":material/check:" if met else ":material/priority_high:",
                color="green" if met else "orange",
            )
            st.badge(
                "Quote verified" if verified else "Quote failed",
                icon=":material/format_quote:",
                color="green" if verified else "red",
            )
            st.badge(f"Confidence {conf:.2f}", color="blue" if conf >= 0.75 else "gray")

        note = ext.get("critic_note") or "—"
        st.caption("Critic")
        st.code(note, language=None)

        case_id = result.get("case_id")
        if editable:
            new_val = st.text_input(
                "Value",
                value=ext.get("value") or "",
                key=f"val_{case_id}_{cid}",
                help="Corrected extraction value for this criterion.",
            )
            new_quote = st.text_area(
                "Quote (must appear verbatim in the clinical note)",
                value=ext.get("quote") or "",
                key=f"quote_{case_id}_{cid}",
                height=88,
            )
            new_conf = st.slider(
                "Confidence",
                0.0,
                1.0,
                conf,
                0.01,
                key=f"conf_{case_id}_{cid}",
            )
            edits[cid] = {
                "value": new_val.strip() or None,
                "quote": new_quote.strip() or None,
                "confidence": new_conf,
            }
        else:
            st.text_input(
                "Value",
                value=ext.get("value") or "",
                disabled=True,
                key=f"ro_val_{case_id}_{cid}",
            )
            st.text_area(
                "Verified quote",
                value=ext.get("quote") or "",
                disabled=True,
                key=f"ro_quote_{case_id}_{cid}",
                height=88,
            )
    return edits


def _render_results(result: dict) -> None:
    status = result.get("status") or "needs_review"
    missing = set(result.get("missing_fields") or [])
    lik = result.get("approval_likelihood")
    alt = result.get("alternative_suggestion")
    case_id = result.get("case_id") or ""

    with st.container(border=True):
        top = st.container(horizontal=True, gap="medium", vertical_alignment="center")
        with top:
            st.markdown("#### Result")
            _status_badge(status)

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                "Approval likelihood",
                f"{lik:.2f}" if lik is not None else "—",
                border=True,
                help="Blend of met criteria weights and historical payer rate.",
            )
        with m2:
            st.metric(
                "Missing fields",
                str(len(missing)),
                border=True,
                help="Criterion IDs escalated for human review.",
            )
        with m3:
            st.metric(
                "Case ID",
                f"{case_id[:8]}…" if case_id else "—",
                border=True,
            )

        if alt:
            st.info(f"**Formulary alternative:** {alt}", icon=":material/swap_horiz:")
        if result.get("human_review_notes"):
            st.warning(result["human_review_notes"], icon=":material/flag:")

    review_tab, export_tab = st.tabs(["Field review", "Export"])

    with review_tab:
        st.caption(
            "Met / high-confidence fields stay read-only. "
            "Edit unmet fields, then re-score — escalate fields, not cases."
        )
        edits = _render_field_review(result, missing=missing)

        actions = st.container(horizontal=True, gap="small")
        with actions:
            rescore = st.button(
                "Re-score",
                type="primary",
                icon=":material/refresh:",
                help="Re-run likelihood + gate without calling the extractor again.",
            )
            clear = st.button(
                "Clear result",
                type="tertiary",
                icon=":material/close:",
            )
        if rescore:
            patched = apply_human_edits(result, edits) if edits else result
            with st.spinner("Re-scoring…"):
                st.session_state.result = rescore_case(patched)
            st.rerun()
        if clear:
            st.session_state.result = None
            st.rerun()

    with export_tab:
        draft = result.get("draft_pa_form") or {}
        export = draft.get("export_markdown") or ""
        st.caption("Paste into a portal or fax cover sheet.")
        st.text_area(
            "Export markdown",
            value=export,
            height=360,
            key=f"export_{case_id}",
        )
        st.download_button(
            "Download markdown",
            data=export,
            file_name=f"pa_draft_{case_id or 'case'}.md",
            mime="text/markdown",
            icon=":material/download:",
            type="primary",
        )


def _render_sidebar() -> None:
    st.header("Demo")
    st.caption("Rehearse in order: **Needs review → No PA → Auto completed**")

    for fname, label, help_text in DEMO_FIXTURES:
        fx = load_fixture(fname)
        if st.button(
            label,
            key=f"fx_{fx['id']}",
            width="stretch",
            help=help_text,
            icon=":material/playlist_play:",
        ):
            _load_fixture(fname)
            st.rerun()

    if st.session_state.last_fixture:
        st.caption(f"Loaded: `{st.session_state.last_fixture}`")

    st.divider()
    st.subheader("System")
    settings = get_settings()
    if is_live_llm():
        st.badge("LIVE OpenRouter", icon=":material/cloud:", color="green")
        st.caption(f"`{settings.extract_model}` · `{settings.critic_model}`")
    else:
        st.badge("MOCK offline", icon=":material/science:", color="orange")
        st.caption("Set `USE_MOCK_EXTRACT=0` in `.env` for live calls.")

    st.write("")
    if not is_configured():
        st.badge("Supabase off", icon=":material/database:", color="gray")
        st.caption("Using in-memory seeds.")
    else:
        sb = _cached_supabase_health()
        if sb.get("ok"):
            tables = sb.get("tables") or {}
            st.badge("Supabase connected", icon=":material/database:", color="green")
            st.caption(
                f"Policies {tables.get('payer_policies')} · "
                f"Cases {tables.get('pa_cases')}"
            )
        else:
            st.badge("Supabase issue", icon=":material/database:", color="red")
            st.caption(sb.get("message") or "Check schema / seed.")

    with st.expander("Break-it scenarios"):
        st.caption("Safety demos — should escalate, never crash.")
        if st.button("Empty clinical note", width="stretch", icon=":material/note:"):
            st.session_state.drug_name = "Ozempic"
            st.session_state.diagnosis_code = "E11.9"
            st.session_state.payer_name = "Aetna"
            st.session_state.clinical_note = ""
            st.session_state.last_fixture = None
            st.session_state.result = None
            st.rerun()
        if st.button("Unknown drug", width="stretch", icon=":material/medication:"):
            st.session_state.drug_name = "NotARealDrugXYZ"
            st.session_state.diagnosis_code = "M06.9"
            st.session_state.payer_name = "UHC"
            st.session_state.clinical_note = (
                "Demo data — not real PHI. Follow-up only."
            )
            st.session_state.last_fixture = None
            st.session_state.result = None
            st.rerun()

    with st.expander("Talk-track notes"):
        st.markdown(
            """
- Escalate **fields**, not cases  
- Failed quote → confidence 0 in code  
- Critic then **math** scores approval  
- Low likelihood → same-class no-PA alternative  
- Paste the markdown  

For talk-track #2, set `INJECT_FIXTURE_C_HALLUCINATION=1` in `.env`.
            """
        )


def main() -> None:
    st.set_page_config(
        page_title="PA Intake Agent",
        page_icon=":material/health_and_safety:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()

    st.warning(
        "**Demo data — not real PHI.** Synthetic notes only. "
        "Do not paste real patient text.",
        icon=":material/privacy_tip:",
    )
    if is_live_llm():
        st.info(
            "**LIVE mode:** notes are sent to OpenRouter. Use synthetic demo notes only.",
            icon=":material/cloud_upload:",
        )

    st.title("PA Intake & Auto-Draft")
    st.caption(
        "Escalate fields, not cases · quote-span check in code · "
        "second-model critic · math score"
    )

    with st.sidebar:
        _render_sidebar()

    left, right = st.columns([1, 1.2], gap="large")

    with left:
        with st.form("intake_form", border=True):
            st.subheader("Intake")
            st.text_input("Drug name", key="drug_name")
            st.text_input("Diagnosis (ICD-10)", key="diagnosis_code")
            st.text_input("Payer", key="payer_name")
            st.text_area("Clinical note", key="clinical_note", height=280)
            submitted = st.form_submit_button(
                "Run PA agent",
                type="primary",
                icon=":material/play_arrow:",
                width="stretch",
            )
        if submitted:
            if not (st.session_state.clinical_note or "").strip():
                st.error(
                    "Clinical note is empty — the agent will escalate safely, "
                    "but load a fixture for the demo path.",
                    icon=":material/warning:",
                )
            _run_pipeline()
            st.rerun()

    with right:
        if st.session_state.result:
            _render_results(st.session_state.result)
        else:
            _render_empty_result()


if __name__ == "__main__":
    main()
