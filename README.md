# PA Intake & Auto-Draft Agent

Hackathon build of a LangGraph prior-auth intake pipeline (spec: `PA-Intake-hackathon-spec-v2.md`).

**Demo data — not real PHI.** Synthetic notes only.

## Stack (locked)

- Python 3.12+ (local venv uses 3.13 if 3.12 is unavailable)
- LangGraph + OpenRouter (`OPENROUTER_API_KEY` only — no Anthropic SDK)
- Supabase schema in `sql/` (in-memory seed store for early blocks)
- Streamlit UI (`streamlit run app.py`)

## Architecture

Interactive architecture diagram (Archify showcase):

**[Open `docs/archify/pa-intake-architecture.html`](docs/archify/pa-intake-architecture.html)**

```bash
# from repo root
open docs/archify/pa-intake-architecture.html   # macOS
# or: xdg-open docs/archify/pa-intake-architecture.html
```

The diagram covers:

| Layer | What it shows |
| ----- | ------------- |
| Presentation | Streamlit UI (`app.py`) — fixture load, unmet-field edit, re-score, markdown export |
| Orchestration | LangGraph 10-node PA pipeline (policy → extract → quote verify → critic → draft → score → alternative → gate → persist) |
| LLM | OpenRouter Haiku/Sonnet via `ChatOpenAI` (mock extract for offline tests) |
| Data | In-memory seed store + optional Supabase (`sql/`) |
| Fixtures | Golden A / B / C paths and gate outcomes |

Machine-readable source: [`docs/archify/pa-intake.architecture.json`](docs/archify/pa-intake.architecture.json).

## Blocks

| Block | Status |
| ----- | ------ |
| 1 Setup + fixtures | done |
| 2 Graph skeleton | done |
| 3 Extraction + quote verify | done |
| 4 Critic | done |
| 5 Draft + score + alternative | done |
| 6 Gate + persistence | done |
| 7 UI | done |
| 8 Break-it + demo | **done** |

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# put your OpenRouter key in .env
```

Supabase (optional for Block 1): run `sql/schema.sql` then `sql/seed.sql` in the SQL editor.

## Block 1 checks

```bash
# unit smoke (no API key required)
pytest tests/test_block1_fixtures.py -q

# one OpenRouter ping before wiring nodes
python scripts/ping_openrouter.py
```

## Block 2 checks

```bash
pytest tests/test_block2_graph.py -q
# Fixture A → no_pa_required; unknown policy → needs_review
```

## Block 3 checks

```bash
pytest tests/test_block3_extract_quote.py -q
# Fixture B → all quotes verified / auto_completed
# Fixture C → hallucinated quote confidence 0; missing c3,c4
```

## Block 4 checks

```bash
pytest tests/test_block4_critic.py -q
# critic_note per field; cannot raise failed quote-verify; downgrade can flip gate
```

## Block 5 checks

```bash
pytest tests/test_block5_draft_score.py -q
# Fixture B → draft + likelihood ≥ 0.75; Fixture C → alt etanercept, likelihood ~0.3–0.5
```

## Block 6 checks

```bash
pytest tests/test_block6_gate_persist.py -q
python scripts/run_golden.py
# gate escalates fields; pa_cases upsert; export markdown paste-ready
```

## Block 7 — UI

```bash
streamlit run app.py
```

Sidebar loads golden fixtures (start demo with **fixture_c**). Met fields are read-only; unmet fields are editable; **Re-score** re-runs likelihood + gate without re-extracting.

## Live OpenRouter

```bash
# 1. Put a real key in .env
cp .env.example .env   # if needed
# OPENROUTER_API_KEY=sk-or-v1-...
# USE_MOCK_EXTRACT=0
# INJECT_FIXTURE_C_HALLUCINATION=1   # optional, talk-track #2 only

python scripts/ping_openrouter.py
python scripts/live_smoke.py      # ping + Fixture B live graph
streamlit run app.py              # sidebar shows LIVE vs MOCK
```

Pytest always forces `USE_MOCK_EXTRACT=1` via `tests/conftest.py` so offline tests stay free.

Live hardening: justification is verified-quotes-only; critic soft-fail rejects all fields; exceptions are sanitized before persist; Fixture C inject defaults **off**.

## Block 8 — Break-it + demo

```bash
pytest tests/test_block8_breakit.py -q
python scripts/breakit.py
python scripts/demo.py --talk          # C → A → B + 90s talk track
```

Break-it covers empty note, unknown drug/payer, hallucinated quote — always `needs_review` / safe status, never crash.

### 90-second talk track

1. Escalate **fields**, not cases — Fixture C checklist  
2. Model cannot invent evidence — failed quote → confidence 0 in code  
3. Second model critiques, then **math** scores approval  
4. Likely deny → same-class **no-PA** alternative  
5. Paste the markdown. Stop talking.

## Golden fixtures

| Fixture | Expect |
| ------- | ------ |
| `fixtures/fixture_a_no_pa.json` | `no_pa_required` |
| `fixtures/fixture_b_auto_completed.json` | `auto_completed`, likelihood ≥ 0.75 |
| `fixtures/fixture_c_needs_review.json` | `needs_review`, 2 missing fields, alternative `etanercept` |
