"""Retrieval layer tests. Offline: fake hash embedder, temporary index folder."""
import pathlib

from agents.rfp.chunks import load_chunks, parse_doc
from agents.rfp.embedder import HashEmbedder
from agents.rfp.retriever import Retriever, keyword_score


def test_chunker_splits_by_heading_and_keeps_dates():
    chunks = parse_doc(pathlib.Path("data/rfp/security_overview_2023.md"))
    assert {c.section for c in chunks} >= {"Encryption", "Data retention"}
    assert all(c.updated == "2023-03-14" for c in chunks)


def test_every_chunk_keeps_its_document_title():
    chunks = load_chunks("data/rfp")
    assert all(isinstance(c.title, str) and c.title for c in chunks)
    sub = [c for c in chunks if c.doc == "subprocessors"]
    assert {c.title for c in sub} == {"Subprocessors"}          # the table chunk knows what doc it is from


def test_chunker_handles_faq_and_headingless_docs():
    faq = parse_doc(pathlib.Path("data/rfp/product_faq.md"))
    assert any("identity provider" in c.section for c in faq)   # bold question became a section
    pricing = parse_doc(pathlib.Path("data/rfp/pricing_packaging.md"))
    assert pricing and pricing[0].section == "Overview"         # no headings at all


def test_keyword_score():
    assert keyword_score("SOC 2 report", "we have a SOC 2 report") == 1.0
    assert keyword_score("hipaa agreement", "AES-256 encryption") == 0.0


def make(tmp_path):
    r = Retriever(embedder=HashEmbedder(), path=str(tmp_path), company="test")
    r.index(load_chunks("data/rfp"))
    return r


def test_search_finds_the_right_chunk(tmp_path):
    hits = make(tmp_path).search("data retention after termination")
    assert hits[0]["section"] == "Data retention"
    assert {h["doc"] for h in hits} >= {"security_overview_2025"}


def test_both_versions_of_a_conflict_are_retrievable_with_dates(tmp_path):
    hits = make(tmp_path).search("data retention after termination", k=5)
    dates = {h["updated"] for h in hits if h["section"] == "Data retention"}
    assert dates == {"2023-03-14", "2025-08-02"}


def test_reindex_does_not_duplicate(tmp_path):
    r = make(tmp_path)
    before = r.collection.count()
    r.index(load_chunks("data/rfp"))
    assert r.collection.count() == before


def test_companies_are_isolated(tmp_path):
    make(tmp_path)
    other = Retriever(embedder=HashEmbedder(), path=str(tmp_path), company="other")
    assert other.search("encryption") == []


# ---- the index never goes stale ----

def test_ensure_index_rebuilds_only_when_docs_or_embedder_change(tmp_path, monkeypatch):
    import shutil

    from agents.rfp import ingest, settings
    docs = tmp_path / "docs"
    shutil.copytree("data/rfp", docs)
    monkeypatch.setattr(settings, "EMBEDDER", "hash")
    r = Retriever(embedder=HashEmbedder(), path=str(tmp_path / "idx"), company="t")
    fp = tmp_path / "t.fingerprint"

    assert ingest.ensure_index(r, str(docs), fp) is True       # first use builds it
    assert ingest.ensure_index(r, str(docs), fp) is False      # unchanged: no rebuild
    (docs / "uptime_sla.md").write_text("# Uptime\nLast updated: 2026-01-01\n\n## Commitments\n99.99 percent\n")
    assert ingest.ensure_index(r, str(docs), fp) is True       # a doc changed
    assert "99.99" in " ".join(h["text"] for h in r.search("uptime commitments"))
    monkeypatch.setattr(settings, "EMBEDDER", "local")
    assert ingest.ensure_index(r, str(docs), fp) is True       # embedding model switched
