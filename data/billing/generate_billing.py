"""Deterministic generator for the fake cloud billing dataset.
Run from the repo root: python data/billing/generate_billing.py
Writes billing.csv, infra.json, deploy_calendar.md and the answer key.
Change SEED or the constants to make new variations. Same seed gives the same data."""
import json
import random
from datetime import date, timedelta

SEED = 42
START = date(2026, 7, 2)
DAYS = 90  # 2026-07-02 to 2026-09-29

random.seed(SEED)

# (account, service, tag, baseline dollars per day)
SERIES = [
    ("prod", "EC2", "team:platform", 210),
    ("prod", "RDS", "team:platform", 130),
    ("prod", "S3", "team:data", 45),
    ("prod", "NAT Gateway", "team:platform", 40),
    ("prod", "CloudFront", "team:web", 55),
    ("prod", "Lambda", "team:web", 18),
    ("staging", "EC2", "team:platform", 60),
    ("staging", "RDS", "team:platform", 25),
    ("ml-research", "EC2", "team:ml", 70),
    ("ml-research", "S3", "team:ml", 22),
]

NAT_SPIKE_START = date(2026, 9, 20)      # runaway data transfer through the NAT gateway
GPU_START = date(2026, 9, 8)             # forgotten GPU instance in ml-research
LAUNCH = (date(2026, 8, 18), date(2026, 8, 20))  # legitimate launch traffic
S3_CREEP_WEEKLY = 0.05                   # prod S3 grows 5 percent per week

rows = []
for d_i in range(DAYS):
    d = START + timedelta(days=d_i)
    for account, service, tag, base in SERIES:
        cost = base * random.uniform(0.95, 1.05)
        if account == "prod" and service == "S3":
            cost *= (1 + S3_CREEP_WEEKLY) ** (d_i / 7)
        if account == "prod" and service == "NAT Gateway" and d >= NAT_SPIKE_START:
            cost = 380 * random.uniform(0.95, 1.05)
        if LAUNCH[0] <= d <= LAUNCH[1] and account == "prod" and service in ("CloudFront", "Lambda"):
            cost *= 4
        rows.append((d.isoformat(), account, service, tag, round(cost, 2)))
    if d >= GPU_START:
        rows.append((d.isoformat(), "ml-research", "EC2-GPU", "team:ml", round(96 * random.uniform(0.99, 1.01), 2)))

with open("data/billing/billing.csv", "w", encoding="utf-8") as f:
    f.write("date,account,service,tag,cost_usd\n")
    for r in rows:
        f.write(",".join(map(str, r)) + "\n")

infra = {"resources": [
    {"resource_id": "nat-0abc123", "type": "NAT Gateway", "account": "prod", "owner": "platform",
     "state": "active", "note": "Handles private subnet egress. A new batch export job was deployed 2026-09-19."},
    {"resource_id": "i-0gpu9f2e", "type": "EC2-GPU (p4d.24xlarge)", "account": "ml-research", "owner": "jlee",
     "state": "running", "last_activity": "2026-09-08", "cpu_avg_7d": "1 percent",
     "note": "Launched for a training run that finished 2026-09-08. Never stopped."},
    {"resource_id": "s3-prod-logs", "type": "S3 bucket", "account": "prod", "owner": "data",
     "state": "active", "lifecycle_policy": None, "note": "Application logs. No expiration or tiering rules."},
    {"resource_id": "cf-prod-web", "type": "CloudFront", "account": "prod", "owner": "web",
     "state": "active", "note": "Serves the marketing site and app assets."},
]}
with open("data/billing/infra.json", "w", encoding="utf-8") as f:
    json.dump(infra, f, indent=2)

with open("data/billing/deploy_calendar.md", "w", encoding="utf-8") as f:
    f.write("""# Deploy and launch calendar
- 2026-07-14: Postgres minor version upgrade (staging then prod)
- 2026-08-18 to 2026-08-20: Halcyon 3.0 public launch. Expect heavy CloudFront and Lambda traffic in prod.
- 2026-09-08: ML team finishes model training run (ml-research)
- 2026-09-19: Platform team deploys nightly batch export job to prod
""")


def monthly(series_filter, since):
    total = sum(r[4] for r in rows if series_filter(r) and r[0] >= since.isoformat())
    days = sum(1 for r in rows if series_filter(r) and r[0] >= since.isoformat())
    return total / days * 30 if days else 0.0


nat_now = monthly(lambda r: r[1] == "prod" and r[2] == "NAT Gateway", NAT_SPIKE_START)
gpu_now = monthly(lambda r: r[2] == "EC2-GPU", GPU_START)
s3_last = sum(r[4] for r in rows if r[1] == "prod" and r[2] == "S3" and r[0] >= "2026-09-23") / 7
s3_first = sum(r[4] for r in rows if r[1] == "prod" and r[2] == "S3" and r[0] <= "2026-07-08") / 7

with open("data/_answer_keys/billing.md", "w", encoding="utf-8") as f:
    f.write(f"""# Cloud cost answer key (agents must never read this file)
Generated with SEED={SEED}. Reference date 2026-09-29. Savings figures are approximate monthly amounts.

| Anomaly | Where | Cause | Correct action | Approx monthly impact |
|---|---|---|---|---|
| NAT gateway spike | prod / NAT Gateway from 2026-09-20 | Batch export job deployed 2026-09-19 routes heavy traffic through NAT | Investigate and route via VPC endpoint. Do not delete the gateway | {nat_now - 40 * 30:,.0f} above baseline |
| Forgotten GPU instance | ml-research / EC2-GPU from 2026-09-08 | Training finished 2026-09-08, instance never stopped | Propose stop (needs approval) | {gpu_now:,.0f} |
| S3 creep | prod / S3 | Logs bucket has no lifecycle policy, grows about 5 percent per week | Propose lifecycle or tiering rule | daily cost grew from {s3_first:.0f} to {s3_last:.0f} |
| False positive: launch spike | prod / CloudFront and Lambda, 2026-08-18 to 2026-08-20 | Planned Halcyon 3.0 launch | Do NOT flag as waste | none |

Rules: savings must be computed by tools, not by the model. Any action that changes infrastructure needs approval.
""")

print(f"Wrote {len(rows)} billing rows. NAT ${nat_now:,.0f}/mo, GPU ${gpu_now:,.0f}/mo.")
