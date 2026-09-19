# PA Intake & Auto-Draft Agent

Hackathon build of a LangGraph prior-auth intake pipeline (spec: `PA-Intake-hackathon-spec-v2.md`).

**Demo data — not real PHI.** Synthetic notes only.

## Stack (locked)

- Python 3.12+ (local venv uses 3.13 if 3.12 is unavailable)
- LangGraph + OpenRouter (`OPENROUTER_API_KEY` only — no Anthropic SDK)
- Supabase schema in `sql/` (in-memory seed store for early blocks)
- Streamlit UI (later block)

## Blocks

| Block | Status |
| ----- | ------ |
| 1 Setup + fixtures | done |
| 2 Graph skeleton | done |
| 3 Extraction + quote verify | done |
| 4 Critic | **done** |
| 5 Draft + score + alternative | next |
| 6 Gate + persistence | |
| 7 UI | |
| 8 Break-it + demo | |

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

## Golden fixtures

| Fixture | Expect |
| ------- | ------ |
| `fixtures/fixture_a_no_pa.json` | `no_pa_required` |
| `fixtures/fixture_b_auto_completed.json` | `auto_completed`, likelihood ≥ 0.75 |
| `fixtures/fixture_c_needs_review.json` | `needs_review`, 2 missing fields, alternative `etanercept` |
