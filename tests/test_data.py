"""Guards the sample data. If someone edits a dataset and removes a seeded trap,
these fail, so your evals never silently lose their teeth."""
import csv
import glob
import json
import pathlib

D = pathlib.Path("data")


def read(p):
    return (D / p).read_text(encoding="utf-8")


def test_rfp_conflicts_and_gaps_exist():
    assert "30 days" in read("rfp/security_overview_2023.md")
    assert "90 days" in read("rfp/security_overview_2025.md")
    assert "any plan" in read("rfp/product_faq.md")
    assert "Enterprise plan only" in read("rfp/sso_identity.md")
    alltext = " ".join(p.read_text().lower() for p in (D / "rfp").glob("*.md"))
    for missing in ("hipaa", "fedramp", "on premise", "on-premise"):
        assert missing not in alltext


def test_rfp_questionnaire_covers_every_category():
    with open(D / "rfp/questionnaire.csv", encoding="utf-8") as f:
        cats = {r["category"] for r in csv.DictReader(f)}
    assert {"direct", "conflict", "multi_doc", "not_covered", "false_premise", "injection", "trap_compliance"} <= cats


def test_ar_ledger_references_real_customers():
    with open(D / "ar/customers.csv") as f:
        ids = {r["customer_id"] for r in csv.DictReader(f)}
    with open(D / "ar/ar_ledger.csv") as f:
        assert {r["customer_id"] for r in csv.DictReader(f)} <= ids


def test_billing_contains_the_seeded_anomalies():
    with open(D / "billing/billing.csv") as f:
        rows = list(csv.DictReader(f))
    nat = [float(r["cost_usd"]) for r in rows if r["service"] == "NAT Gateway" and r["date"] >= "2026-09-20"]
    assert min(nat) > 300
    assert any(r["service"] == "EC2-GPU" for r in rows)


def test_calls_and_crm_line_up():
    assert len(glob.glob(str(D / "calls/call_*.md"))) == 3
    assert len(json.loads(read("calls/crm.json"))["accounts"]) == 3


def test_every_dataset_has_an_answer_key():
    for k in ("rfp", "calls", "ar", "billing"):
        assert (D / f"_answer_keys/{k}.md").exists()
