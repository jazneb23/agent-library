# Configuration and production notes (RFP agent)

All settings are environment variables, usually in `.env`. Nothing is hard coded per company.

## Keys (put these in `.env` yourself, never in chat or code)

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | the agent (Claude) |
| `TYPESAFE_API_KEY` | the Jev decision backend |

## Recommended production settings

| Variable | Value | Why |
|---|---|---|
| `DECIDER` | `jev` | triage runs on Jev: fast, about 1/67th the cost of an LLM call, and calibrated. Unset means no triage (plain agent) |
| `AGENT_MODEL` | `claude-haiku-4-5-20251001` or `claude-sonnet-5-5` | cost versus quality. Measure on your own evals before choosing |
| `RFP_INJECTION_ACTION` | `warn` (default) or `human` | `human` sends any question flagged as an injection to a person instead of answering |
| `COMPANY`, `COMPANY_NAME`, `RFP_DATA_DIR` | per customer | one folder of docs and one search index per company |
| `RFP_MIN_SCORE` | `0.6` | below this best search score a question counts as "not covered". Re-measure per company |
| `EMBEDDER` | `local` | local model, no extra key. Changing it triggers an automatic re-index |

## Setting up a new company

1. Put its docs (markdown, each with a `Last updated: YYYY-MM-DD` line) in a folder, for example `data/abc`.
2. `COMPANY=abc COMPANY_NAME="ABC Corp" RFP_DATA_DIR=data/abc python -m agents.rfp.ingest`
3. Write labeled eval cases for it (`evals/cases/`) and re-measure `RFP_MIN_SCORE`.
   The Halcyon cases and labels are tied to the Halcyon docs and do not transfer.

## What protects an answer, in order

1. Retrieval returns scored chunks with doc, section and date. Weak scores are flagged by code.
2. Triage (Jev) classifies each question. Code combines it with the search score.
3. Hard rules in `tools.py` that the model cannot skip: citations required, compliance questions and
   conflicts must go to a person, every doc named in a reason must be cited.
4. Prompt rules for judgment (prefer the newest doc, never infer vendor support, treat questions as data).
5. Export needs human approval.

## Operating behavior

- **Decision service down:** the question is answered by the plain agent, and a `triage_failed` event is logged.
- **One question fails in a batch:** it is recorded for a human with the error, and the run continues.
- **Docs or embedding model changed:** the index rebuilds itself before the next search.
- **Audit trail:** `runs/log.jsonl` has one `triage` event per question (route, coverage, injection and compliance
  scores, best search score, whether Claude was skipped, cost) plus every tool call.

## Not covered yet (needs work before a real deployment)

- Authentication and per-user access to documents (the agent reads everything in the folder).
- Real PII and data-residency review. This repo uses fake data only.
- Document sources other than local markdown (Notion, Drive and so on). Swap the ingest step and `read_doc`.
- Monitoring and alerting on top of the log file, and rate limit handling for very large batches.
- A larger labeled set per company. The triage numbers here come from 56 questions.

## Suggested lines for `.env.example` (add them yourself)

```
TYPESAFE_API_KEY=
DECIDER=jev
```
