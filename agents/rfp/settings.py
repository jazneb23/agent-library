"""Per company settings for the RFP agent. To run it for another company, set
COMPANY and RFP_DATA_DIR, then run the ingest step. No code changes needed."""
import os

COMPANY = os.getenv("COMPANY", "halcyon")                    # short id, used to name the index
COMPANY_NAME = os.getenv("COMPANY_NAME", "Halcyon Data")     # shown to the model in the prompt
DATA_DIR = os.getenv("RFP_DATA_DIR", "data/rfp")            # docs and questionnaire.csv live here
INDEX_DIR = os.getenv("RFP_INDEX_DIR", "runs/index")         # where the vector store is saved
EMBEDDER = os.getenv("EMBEDDER", "local")                    # "local" or "hash" (hash is for tests)
TOP_K = int(os.getenv("RFP_TOP_K", "3"))                     # chunks returned per search
# Below this best score, treat the question as "not covered". Measured on the Halcyon docs with the
# local model: covered questions scored 0.73+, uncovered ones (HIPAA, FedRAMP, on prem) 0.46 or less.
MIN_SCORE = float(os.getenv("RFP_MIN_SCORE", "0.6"))
