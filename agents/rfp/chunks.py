"""Split a markdown doc into chunks, one per section.

Retrieval works on chunks, not whole docs, so the agent reads only the part that
matters and can cite it. Every chunk keeps its doc name and last updated date,
which is what lets the agent prefer the newer of two conflicting docs."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    doc: str       # file name without .md
    section: str   # heading the text sits under
    updated: str   # ISO date from the "Last updated:" line, or "unknown"
    text: str
    title: str = ""   # the doc's "# Title" line. It is often the best topic signal a chunk has.

    @property
    def id(self) -> str:
        return f"{self.doc}::{self.section}"


def _heading(line: str) -> str | None:
    """A heading is '## Title' or a line that is entirely **bold** (the FAQ style)."""
    if line.startswith("## "):
        return line[3:].strip()
    m = re.fullmatch(r"\*\*(.+?)\*\*", line.strip())
    return m.group(1) if m else None


def parse_doc(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    m = re.search(r"Last updated:\s*(\d{4}-\d{2}-\d{2})", raw)
    updated = m.group(1) if m else "unknown"
    t = re.search(r"^# (.+)$", raw, re.MULTILINE)
    doc_title = t.group(1).strip() if t else path.stem   # not "title": the loop below reuses that name

    chunks, section, buf = [], "Overview", []   # text before any heading is "Overview"

    def flush():
        body = "\n".join(buf).strip()
        if body:
            chunks.append(Chunk(path.stem, section, updated, body, doc_title))

    for line in raw.splitlines():
        if line.startswith("# ") or line.startswith("Last updated:"):
            continue  # the title and date are kept as metadata, not as chunk text
        title = _heading(line)
        if title:
            flush()
            section, buf = title, []
        else:
            buf.append(line)
    flush()
    return chunks


def load_chunks(data_dir: str) -> list[Chunk]:
    out: list[Chunk] = []
    for path in sorted(Path(data_dir).glob("*.md")):
        out.extend(parse_doc(path))
    return out
