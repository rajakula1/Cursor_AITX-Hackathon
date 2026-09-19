# PA Intake & Auto-Draft Agent — Hackathon Spec v2

**Duration:** 6 hours
**Goal:** A working agent pipeline that takes a drug + diagnosis + payer + clinical note, determines if prior authorization is required, drafts the PA form using extracted clinical justification, self-checks its own extraction, scores approval likelihood, and surfaces only the fields that need human review.

This is a tightened version of the original brief. Keep the graph story. Freeze contracts. Demo three golden cases. Do not add more LLM nodes.

**Data rule:** Synthetic notes only. Fake names. Banner in the UI: “Demo data — not real PHI.” Notes may be sent to OpenRouter and whatever provider serves the Claude slug — never real patient text.

---

## 0. Judging Alignment (100 pts)

Every section below maps to a scoring category. The original table summed to 70; the remaining 30 is treated as **demo + domain accuracy + code clarity** (confirm against the official rubric on site).

| Category | Pts | Where it's addressed |
| :---- | :---- | :---- |
| Completeness | 15 | §4 skeleton-before-LLM; §7 every node degrades to `needs_review`; §9 golden fixtures |
| Technical Depth | 15 | §2 — 10-node graph, parallel extraction, **deterministic quote-span check**, batched critic, deterministic gate |
| Insight Quality | 10 | §2.4 scoring formula + alternative therapy when likelihood is low |
| Usability | 10 | §6 typed PA form, copy-paste export, **field-level review panel** |
| Creativity | 10 | Agent-checks-agent + escalate *fields* not *cases*; critic notes visible in UI |
| Performance | 10 | Parallel Haiku fan-out; **LLM result cache** keyed by `(note_hash, criterion_id)`; optional node-status updates |
| Demo / domain / clarity | 30 | §9 three scripted runs; alias normalization; no crash badge |

---

## 1. Product Framing

| | |
| :---- | :---- |
| **Input** | Drug name, diagnosis (ICD-10), payer name, free-text clinical note |
| **Output** | Submission-ready draft PA (typed schema), approval-likelihood score, alternative-therapy suggestion if likelihood is low, status `auto_completed` \| `needs_review` \| `no_pa_required` |
| **Differentiator** | Escalate *fields*, not *cases*. A second model checks the first. Quotes that are not in the note are rejected in code, not by another prompt. |

**Stack (locked):** Python 3.12, LangGraph, **OpenRouter** (Claude Haiku extract, Claude Sonnet critic+draft — no direct Anthropic SDK), Supabase, Streamlit (or FastAPI + one HTML page). One env var: `OPENROUTER_API_KEY`. No Anthropic console, no auth, no RLS theater, no Next.js unless the team already has a template.

---

## 2. Agent Graph (LangGraph)

### 2.1 State schema

```python
from typing import TypedDict, Optional, Literal, NotRequired

PolicyLookup = Literal["found", "not_found", "error"]
PublicStatus = Literal["no_pa_required", "auto_completed", "needs_review"]

class CriterionResult(TypedDict):
    criterion_id: str
    criterion_text: str
    value: Optional[str]
    quote: Optional[str]
    quote_verified: bool
    confidence: float          # 0.0–1.0, post-critic
    met: bool
    critic_note: str

class PAForm(TypedDict):
    drug_name: str
    diagnosis_code: str
    payer_name: str
    clinical_justification: str
    criteria_checklist: list[dict]  # id, text, met, quote
    quantity: Optional[str]
    duration: Optional[str]
    missing_fields: list[str]
    export_markdown: str

class PAState(TypedDict):
    case_id: str
    drug_name: str
    diagnosis_code: str
    payer_name: str
    clinical_note: str
    drug_class: Optional[str]

    policy_lookup: Optional[PolicyLookup]
    pa_required: Optional[bool]
    policy_criteria: list[dict]       # [{id, text, weight}]

    extractions: list[CriterionResult]
    draft_pa_form: Optional[PAForm]
    missing_fields: list[str]

    approval_likelihood: Optional[float]
    alternative_suggestion: Optional[str]

    status: PublicStatus
    human_review_notes: Optional[str]
    error_log: list[str]
```

### 2.2 Nodes (10)

1. **intake_node** — deterministic. Validate non-empty inputs, generate `case_id`, normalize drug/payer via alias map, upsert `pa_cases`.
2. **coverage_check_node** — `get_payer_policy(...)`. Set `policy_lookup`, `pa_required`, `policy_criteria`, `drug_class`.
   - `not_found` or `error` → skip extraction → finalize as `needs_review` with a clear reason.
   - `found` and `requires_pa=false` → finalize as `no_pa_required`.
3. **justification_extraction_node** — OpenRouter `anthropic/claude-haiku-4.5`, **fan-out per criterion** (`asyncio.gather`). Each call returns `{value, confidence, quote}`. Cache by `(sha256(note), criterion_id)`.
4. **quote_verify_node** — **no LLM**. `quote_verified = normalized(quote) in normalized(note)`. If false: `confidence = 0`, `value` kept but `met` cannot become true.
5. **critic_node** — **one** OpenRouter `anthropic/claude-sonnet-4.5` call over all extractions. Structured list: confirm | downgrade | reject + reason. May lower confidence; may not raise a failed quote-verify.
6. **pa_draft_builder_node** — OpenRouter `anthropic/claude-sonnet-4.5`. Fills `PAForm` from critic-adjusted fields. Narrative must only use verified quotes.
7. **approval_likelihood_node** — deterministic (see §2.4).
8. **alternative_suggestion_node** — conditional, `likelihood < 0.55`. `get_formulary_alternative(drug_class, payer)` preferring `requires_pa=false`.
9. **confidence_gate_node** — deterministic. All *required* criteria `met` → `auto_completed`. Else collect `missing_fields` (unmet criterion_ids).
10. **finalize_node** — upsert `pa_cases`, emit `export_markdown`. Escalation copy is produced here (short list of unmet fields) — no separate crash path into the UI.

### 2.3 Edges

```
START → intake → coverage_check
  policy_lookup != found     → finalize (needs_review) → END
  pa_required == false       → finalize (no_pa_required) → END
  pa_required == true        → extract → quote_verify → critic → draft → likelihood
       likelihood < 0.55     → alternative → gate
       else                  → gate
  all required met           → finalize (auto_completed) → END
  else                       → finalize (needs_review) → END

any unhandled exception      → finalize (needs_review, error_log appended) → END
```

Public status is never `error`. Log internally.

### 2.4 What “met” and likelihood mean

A criterion is **met** iff:

- `value` is non-empty, AND
- `quote_verified` is true, AND
- post-critic `confidence >= 0.70`

```
likelihood = 0.70 * (Σ weight_i * confidence_i * 1[met_i] / Σ weight_i)
           + 0.30 * historical_approval_rate
```

If the payer-rate blend is cut, use the first term only. Gate and score **must share** this definition of `met`.

### 2.5 Tools

| Tool | Backing | Notes |
| :---- | :---- | :---- |
| `get_payer_policy(drug, diagnosis, payer)` | Supabase `payer_policies` + alias map | Returns lookup status, `requires_pa`, criteria `[{id,text,weight}]`, `drug_class`, `historical_approval_rate` |
| `get_formulary_alternative(drug_class, payer)` | `formulary_alternatives` | Conditional only |
| `save_case(state)` | `pa_cases` | Upsert on `case_id` |
| `extract_field(criterion, note)` | OpenRouter `anthropic/claude-haiku-4.5`, structured | Parallel, cached |
| `critique_all(extractions, note)` | **One** OpenRouter `anthropic/claude-sonnet-4.5` call | Not per-field |

### 2.6 LLM client (OpenRouter, not Anthropic direct)

All model calls go through OpenRouter’s OpenAI-compatible API. Do **not** use `anthropic` SDK or `ANTHROPIC_API_KEY`.

```python
import os
from langchain_openrouter import ChatOpenRouter

# Fail closed if a provider hop ignores json_schema
_provider = {"require_parameters": True}

extract_llm = ChatOpenRouter(
    model="anthropic/claude-haiku-4.5",
    temperature=0,
    openrouter_provider=_provider,
)

critic_llm = ChatOpenRouter(
    model="anthropic/claude-sonnet-4.5",
    temperature=0,
    openrouter_provider=_provider,
)

draft_llm = critic_llm  # same slug; separate instance is fine
```

Fallback if `langchain-openrouter` is awkward: `ChatOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"], model="anthropic/claude-haiku-4.5")`.

| Concern | Rule |
| :---- | :---- |
| Auth | `OPENROUTER_API_KEY` only. Cursor credits do not pay these calls. |
| Structured output | Use `.with_structured_output(...)` or `response_format.json_schema`. Set `require_parameters: true` so OpenRouter does not route to an endpoint that drops the schema. |
| Schema failure | Treat like an LLM timeout: field = not extracted → `needs_review`. |
| Models | Keep Claude for extract vs critic. Do not swap the extractor to a random cheap model unless the OpenRouter key cannot reach Anthropic slugs. |
| PHI | Synthetic notes only. OpenRouter may route the same slug via Anthropic, Bedrock, Azure, or Vertex. |

---

## 3. Supabase Schema

```sql
create table payer_aliases (
  alias text primary key,
  canonical_payer text not null
);

create table drug_aliases (
  alias text primary key,
  canonical_drug text not null,
  drug_class text not null
);

create table payer_policies (
  id uuid primary key default gen_random_uuid(),
  payer_name text not null,
  drug_name text not null,
  drug_class text not null,
  diagnosis_code text not null,
  requires_pa boolean not null,
  criteria jsonb not null default '[]'::jsonb,
  -- criteria items: {"id":"c1","text":"...","weight":1.0}
  historical_approval_rate numeric default 0.7,
  created_at timestamptz default now(),
  unique (payer_name, drug_name, diagnosis_code)
);

create table formulary_alternatives (
  id uuid primary key default gen_random_uuid(),
  payer_name text not null,
  drug_class text not null,
  original_drug text not null,
  alternative_drug text not null,
  requires_pa boolean not null default false
);

create table pa_cases (
  case_id uuid primary key default gen_random_uuid(),
  drug_name text,
  diagnosis_code text,
  payer_name text,
  drug_class text,
  clinical_note text,
  policy_lookup text,
  pa_required boolean,
  policy_criteria jsonb,
  extractions jsonb,
  draft_pa_form jsonb,
  missing_fields jsonb,
  approval_likelihood numeric,
  alternative_suggestion text,
  status text check (status in ('no_pa_required','auto_completed','needs_review')),
  human_review_notes text,
  error_log jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

Seed **6–10** policy rows across 2–3 payers × 2–3 drugs, mixing `requires_pa` true/false. Seed **≥2** formulary alternatives. Seed aliases for every canonical name plus at least one common variant (`UHC` → `UnitedHealthcare`, `Humira` → `adalimumab` if you seed the generic).

Cap each PA policy at **4–5 criteria** so fan-out stays demo-friendly.

---

## 4. Time-boxed breakdown (6 hours)

| Time | Block | Tasks |
| :---- | :---- | :---- |
| **0:00 – 0:40** | Setup + fixtures | Repo, `OPENROUTER_API_KEY`, schema, seeds, **three golden notes with expected status** (§9). Mock `extract_field` until routing works. Confirm one OpenRouter ping before wiring nodes. |
| **0:40 – 1:30** | Graph skeleton | `PAState`, all nodes stubbed. `intake → coverage → finalize` on the no-PA fixture. Unknown policy → `needs_review`. |
| **1:30 – 2:20** | Extraction + quote verify | OpenRouter Haiku fan-out + substring check + LLM cache. |
| **2:20 – 2:45** | Critic | One batched OpenRouter Sonnet call. Show `critic_note` per field. |
| **2:45 – 3:25** | Draft + score + alternative | Typed `PAForm`, formula, formulary lookup. |
| **3:25 – 4:00** | Gate + persistence | Shared `met` definition; upsert; export markdown. |
| **4:00 – 5:10** | UI | Form in; result out: status badge, likelihood, checklist, **editable unmet fields**, copy button. Node status text if time. |
| **5:10 – 5:30** | Break-it | Empty note, unknown drug, hallucinated quote (fixture 3). Must not crash. |
| **5:30 – 6:00** | Demo script | Rehearse §9 in order: messy case first, then fast path, then auto-complete. |

---

## 5. Cut lines (if time runs short)

Cut in this order. Each step still leaves a demoable, judge-defensible pipeline:

1. Drop streaming node-status text — spinner is fine
2. Drop policy LRU — it is not the latency story
3. Drop payer-rate blending in likelihood — keep `met` ratio
4. Keep a **stub** alternative string even if you skip the table call
5. **Never cut:** critic, quote-span check, conditional routing, likelihood number, field-level missing list

---

## 6. Output / usability

Finalize produces:

1. DB upsert
2. `export_markdown` the user can paste into a portal or fax cover: drug, diagnosis, narrative, criteria checklist with **verified** quotes
3. UI review panel: high-confidence fields read-only; unmet fields editable. Optional “re-score” re-enters likelihood + gate without re-extracting verified fields

---

## 7. Resilience

- Every node try/except → `needs_review` + `error_log`; graph never throws to the UI
- Intake: empty note / unresolvable aliases → `needs_review` with reason
- Coverage: no policy row → `needs_review`, **never** `no_pa_required`
- Each OpenRouter call: timeout + one retry; then field is “not extracted” and routes to review. Same path if structured-output routing fails.
- Quote verify is not optional

---

## 8. Performance

- Parallel OpenRouter Haiku fan-out (one round-trip of wall clock for N criteria)
- Cache extraction by `(note_hash, criterion_id)` so the three demo cases re-run instantly
- Optional: stream LangGraph node names to the UI so waiting reads as depth

---

## 9. Golden fixtures (build against these from minute 40)

### Fixture A — no PA required

- Drug/payer/diagnosis on a `requires_pa=false` row
- Note can be short
- **Expect:** `no_pa_required`, no extraction calls (or skipped), likelihood unused

### Fixture B — auto-completed

- PA required, 4 criteria
- Note contains a verbatim sentence for each criterion
- **Expect:** all `quote_verified=true`, status `auto_completed`, likelihood ≥ 0.75, export markdown non-empty

### Fixture C — needs review + alternative (lead demo)

- PA required, 4 criteria
- Note supports 2 criteria with verbatim quotes
- One extraction is instructed (or a mocked extractor) to return a quote **not** in the note → span check zeros it
- One criterion truly missing
- **Expect:** `needs_review`, `missing_fields` length 2, alternative drug present, likelihood ~0.3–0.5

Put these in `fixtures/*.json` with `expected.status` and assert in a tiny `pytest` or a “Run golden cases” button.

---

## 10. 90-second talk track

1. “We escalate fields, not cases.” Show Fixture C checklist.
2. “The model cannot invent evidence.” Show the failed quote turned to confidence 0 in code.
3. “A second model critiques the first, then math scores approval — not another LLM yes/no.”
4. “If this drug is likely to deny, here is a same-class option that does not need PA.”
5. Paste the markdown. Stop talking.
