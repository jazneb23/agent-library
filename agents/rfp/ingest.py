"""Build (or rebuild) the search index for one company.
Run from the project root:  python -m agents.rfp.ingest
For another company:        COMPANY=abc RFP_DATA_DIR=data/abc python -m agents.rfp.ingest"""
from agents.rfp import settings
from agents.rfp.chunks import load_chunks
from agents.rfp.retriever import Retriever


def main() -> None:
    chunks = load_chunks(settings.DATA_DIR)
    n = Retriever().index(chunks)
    print(f"Indexed {n} chunks from {settings.DATA_DIR} for company '{settings.COMPANY}'.")


if __name__ == "__main__":
    main()
