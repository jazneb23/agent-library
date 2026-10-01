"""Turn text into vectors (lists of numbers) so "similar meaning" becomes
"close together". Everything goes through get_embedder(), so the engine can be
swapped with one environment variable. To add a provider (Voyage, OpenAI), write
a class with an embed(texts) method and register it in get_embedder."""
import hashlib
import math
import re

from agents.rfp import settings


class LocalEmbedder:
    """Runs on this machine via fastembed. Free, no API key. The model (about
    100MB) downloads once on first use."""
    def __init__(self):
        from fastembed import TextEmbedding
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class HashEmbedder:
    """Deterministic fake for tests: hashes each word into a slot of a 64 number
    vector. Not smart, but texts sharing words land close together, and it needs
    no download, so tests stay offline and instant."""
    DIM = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.DIM
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def get_embedder(name: str | None = None):
    name = name or settings.EMBEDDER
    if name == "local":
        return LocalEmbedder()
    if name == "hash":
        return HashEmbedder()
    raise ValueError(f"Unknown EMBEDDER '{name}'. Use 'local' or 'hash'.")
