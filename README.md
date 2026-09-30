# Agent Starter Kit

A reusable kit for building, testing, and guarding AI agents on the Anthropic API. It ships with a shared core, an eval runner, unit tests, CI, and fake datasets with seeded traps for four real workflows.

## What is in it

| Piece | Path | Purpose |
|---|---|---|
| Agent loop | core/agent.py | Ask, run tools, feed results back, repeat, with a step limit and cost tracking |
| Tool registry | core/tools.py | Tools are Python functions plus descriptions Claude reads |
| Approval gate | core/approval.py | Human sign off before any write action |
| Audit log | core/logger.py | JSON lines log of every event and its cost |
| Decision layer | core/decisions.py | Swappable engine (Claude, Jev, cascade) for classify, route, score, and guard judgments |
| Eval runner | evals/ | Scores agents against test cases, with repeat runs and pass rates |
| Sample data | data/ | RFP docs and questionnaire, discovery calls and CRM, AR ledger and email threads, cloud billing |
| Answer keys | data/_answer_keys/ | What correct looks like, readable only by evals and tests |
| Tests | tests/ | Offline unit tests using a fake client, plus guards on the data traps |
| Docs | docs/ | Design notes and best practices |

## Quickstart

```bash
make setup
cp .env.example .env      # then paste your key
make test                 # offline, no key needed
make run-hello
make eval-hello
```

## Agents

| Agent | Workflow | Approval gated action |
|---|---|---|
| hello | Product doc lookup (learning example) | save_note |
| rfp (planned) | Answer security questionnaires with citations and abstention | export_answers |
| discovery (planned) | Score a call, draft a follow up, propose CRM updates | apply_crm_update |
| invoice (planned) | Prioritize collections and draft outreach under a policy | send_email |
| cost (planned) | Explain cloud cost anomalies and propose savings | execute_action |

## Design decisions

- Abstain rather than guess when the docs do not cover a question
- Numbers come from code, reasoning comes from the model
- Fast typed judgments go through a swappable decision layer, so backends can be measured against each other
- Every write action is behind an approval gate
- Text inside data is treated as data, never as instructions
- Evals measure model behavior. Tests prove the code works

## Results

Updated as each agent is completed.

| Agent | Eval cases | Baseline pass rate | Improved pass rate | Avg cost per run |
|---|---|---|---|---|
| rfp | | | | |
| discovery | | | | |
| invoice | | | | |
| cost | | | | |

All data is fictional.
