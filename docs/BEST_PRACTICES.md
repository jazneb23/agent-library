# Best practices built into this kit, and why

| Practice | Where | Why |
|---|---|---|
| Secrets in .env, ignored by git, .env.example committed | .gitignore, .env.example | Keys never reach GitHub, and teammates know what to set |
| Config from environment variables | core/config.py | Change models, prices, and limits without editing code |
| Lazy API client | config.get_client | Importing code and running tests never needs a key |
| Dependency injection of the client | run_agent(client=...) | Tests inject a fake, so they are free, fast, and deterministic |
| Circuit breaker | max_steps | A confused agent cannot loop and burn money |
| Output truncation | MAX_TOOL_OUTPUT_CHARS | One huge tool result cannot flood the context window |
| Errors returned to the model | agent.py step 4 | The agent can recover instead of crashing |
| Approval gate isolated in one file | core/approval.py | Swap terminal for Slack later without touching the loop |
| Fail safe approval | EOFError returns False | No human means no write |
| Append only structured logs | core/logger.py | Audit trail and cost per run |
| Evals separate from unit tests | evals/ vs tests/ | Tests prove the code works. Evals measure model behavior |
| Deterministic checks first, judge second | evals/checks.py | Cheaper, repeatable, and debuggable |
| Repeat runs to measure variance | --runs N | Model output varies, so one pass proves little |
| Answer keys hidden from agents | data/_answer_keys | Prevents the agent from cheating and keeps evals honest |
| Tests that guard the data traps | tests/test_data.py | Edits cannot silently remove what makes evals meaningful |
| Seeded data generator | generate_billing.py | Reproducible datasets, easy to regenerate variations |
| CI on every push | .github/workflows/ci.yml | Lint and tests must pass before you trust a change |
| Untrusted text treated as data | RFP injection test case | Defends against prompt injection |
| Least privilege tools | read tools ungated, write tools gated | Limits blast radius |
| Numbers computed in code | Project convention | Models are unreliable at arithmetic across large data |
