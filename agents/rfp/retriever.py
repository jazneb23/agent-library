"""Hybrid search: vector similarity (meaning) plus keyword overlap (exact terms).

Why both? Vectors catch "sign in with our identity provider" ~ "SSO". Keywords
catch exact terms like "SOC 2" or "HIPAA" that vectors blur. And vectors ALWAYS
return something, even for a topic we never wrote about, so each hit carries a
score and the agent abstains when the best score is below MIN_SCORE."""
import re

import chromadb

from agents.rfp import settings
from agents.rfp.chunks import Chunk
from agents.rfp.embedder import get_embedder

STOPWORDS = {"the", "a", "an", "of", "to", "do", "you", "your", "we", "our", "is", "are", "and",
             "or", "in", "on", "for", "it", "with", "that", "this", "be", "have", "what", "which",
             "how", "does", "can", "will", "if", "any", "all"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def keyword_score(query: str, text: str) -> float:
    """Share of the query's meaningful words that appear in the chunk (0 to 1)."""
    q = _words(query)
    return len(q & _words(text)) / len(q) if q else 0.0


class Retriever:
    def __init__(self, embedder=None, path: str | None = None, company: str | None = None):
        self.embedder = embedder or get_embedder()
        client = chromadb.PersistentClient(path=path or settings.INDEX_DIR)
        # One collection per company, so company data never mixes.
        self.collection = client.get_or_create_collection(
            name=f"rfp_{company or settings.COMPANY}", metadata={"hnsw:space": "cosine"})

    def index(self, chunks: list[Chunk]) -> int:
        """Rebuild the company's index from scratch (safe to rerun)."""
        existing = self.collection.get()["ids"]
        if existing:
            self.collection.delete(ids=existing)
        if not chunks:
            return 0
        self.collection.add(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=self.embedder.embed([f"{c.section}. {c.text}" for c in chunks]),
            metadatas=[{"doc": c.doc, "section": c.section, "updated": c.updated} for c in chunks])
        return len(chunks)

    def search(self, query: str, k: int | None = None) -> list[dict]:
        k = k or settings.TOP_K
        n = self.collection.count()
        if n == 0:
            return []
        res = self.collection.query(query_embeddings=self.embedder.embed([query]),
                                    n_results=min(max(k * 3, k), n))
        hits = []
        for text, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                                    res["distances"][0], strict=True):
            vec = 1.0 - dist                       # cosine distance to similarity
            kw = keyword_score(query, text)
            hits.append({**meta, "text": text, "vector": round(vec, 3), "keyword": round(kw, 3),
                         "score": round(0.6 * vec + 0.4 * kw, 3)})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:k]
