"""Build (or rebuild) the search index for one company.
Run from the project root:  python -m agents.rfp.ingest
For another company:        COMPANY=abc RFP_DATA_DIR=data/abc python -m agents.rfp.ingest

The agent also calls ensure_index() before its first search, so editing a doc or switching the
embedding model never leaves it answering from a stale index."""
from pathlib import Path

from agents.rfp import settings
from agents.rfp.chunks import docs_fingerprint, load_chunks
from agents.rfp.retriever import Retriever
from core.logger import log_event


def fingerprint_path() -> Path:
    return Path(settings.INDEX_DIR) / f"{settings.COMPANY}.fingerprint"


def current_fingerprint(data_dir: str) -> str:
    # The embedding model is part of it: vectors from two models cannot be compared.
    return f"{settings.EMBEDDER}:{docs_fingerprint(data_dir)}"


def build(retriever: Retriever, data_dir: str, fp_path: Path) -> int:
    n = retriever.index(load_chunks(data_dir))
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    fp_path.write_text(current_fingerprint(data_dir), encoding="utf-8")
    return n


def ensure_index(retriever: Retriever | None = None, data_dir: str | None = None,
                 fp_path: Path | None = None) -> bool:
    """Rebuild the index if the docs or the embedding model changed since the last ingest.
    Returns True if it rebuilt. Local and fast, so safe to call on every start."""
    data_dir = data_dir or settings.DATA_DIR
    fp_path = Path(fp_path) if fp_path else fingerprint_path()
    retriever = retriever or Retriever()
    if (fp_path.exists() and fp_path.read_text(encoding="utf-8") == current_fingerprint(data_dir)
            and retriever.collection.count() > 0):
        return False
    n = build(retriever, data_dir, fp_path)
    log_event("system", "index_rebuilt", company=settings.COMPANY, chunks=n, embedder=settings.EMBEDDER)
    return True


def main() -> None:
    n = build(Retriever(), settings.DATA_DIR, fingerprint_path())
    print(f"Indexed {n} chunks from {settings.DATA_DIR} for company '{settings.COMPANY}'.")


if __name__ == "__main__":
    main()
