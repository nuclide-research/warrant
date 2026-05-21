import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from .models import Edge, Principle, principle_from_dict, principle_to_dict


@dataclass
class Index:
    principles: list[Principle]
    embeddings: np.ndarray   # shape (len(principles), dim), row i -> principles[i]
    edges: list[Edge]


def _safe(pid: str) -> str:
    """Map a principle id to a safe filename. Known limitation: extract.py
    truncates slug components to 50 chars, so two sections in one chapter
    whose headings share a 50-char prefix can produce the same id and thus
    the same filename, silently overwriting. Acceptable for the current
    corpus; revisit before large-scale indexing."""
    return pid.replace(":", "__").replace("/", "_")


def save_index(index: Index, out_dir) -> None:
    if len(index.principles) != index.embeddings.shape[0]:
        raise ValueError(
            f"principles/embeddings length mismatch: "
            f"{len(index.principles)} vs {index.embeddings.shape[0]}")
    out = Path(out_dir)
    (out / "principles").mkdir(parents=True, exist_ok=True)
    for stale in (out / "principles").glob("*.json"):
        stale.unlink()
    order = []
    for p in index.principles:
        (out / "principles" / f"{_safe(p.id)}.json").write_text(
            json.dumps(principle_to_dict(p), indent=2))
        order.append(p.id)
    np.save(out / "embeddings.npy", index.embeddings)
    (out / "edges.json").write_text(
        json.dumps([asdict(e) for e in index.edges], indent=2))
    (out / "manifest.json").write_text(
        json.dumps({"order": order, "count": len(order)}, indent=2))


def load_index(out_dir) -> Index:
    out = Path(out_dir)
    order = json.loads((out / "manifest.json").read_text())["order"]
    principles = [
        principle_from_dict(json.loads(
            (out / "principles" / f"{_safe(pid)}.json").read_text()))
        for pid in order
    ]
    embeddings = np.load(out / "embeddings.npy")
    edges = [Edge(**e) for e in json.loads((out / "edges.json").read_text())]
    return Index(principles=principles, embeddings=embeddings, edges=edges)
