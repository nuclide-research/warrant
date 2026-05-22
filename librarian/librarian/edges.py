import sys

import numpy as np

from .extract import LLM, _parse_json_array
from .models import Edge, Principle

_NEIGHBORS = 5   # nearest neighbors per principle considered as candidate edges
_BATCH = 40      # candidate pairs per LLM classification call

_PROMPT = """\
Below are candidate pairs of engineering principles, gated by topical
similarity. For each pair decide whether a genuine relationship holds.
Return ONLY a JSON array; include an element ONLY for pairs that genuinely
relate:
  {{"src": "<id>", "dst": "<id>", "kind": "refines|contradicts|shares_topic"}}
  refines       = src is a more specific case of dst
  contradicts   = src and dst give conflicting guidance
  shares_topic  = src and dst address the same topic without refining/conflicting
Omit a pair with no real relationship. No relationships -> [].

PAIRS:
{listing}
"""


def _candidate_pairs(embeddings: np.ndarray, n_neighbors: int) -> list[tuple[int, int]]:
    """Principle index pairs (i, j) with i < j where j is among i's nearest
    neighbors by cosine similarity. Embeddings are L2-normalized, so the dot
    product is cosine similarity."""
    count = embeddings.shape[0]
    if count < 2:
        return []
    sims = embeddings @ embeddings.T
    np.fill_diagonal(sims, -np.inf)  # never pair a principle with itself
    k = min(n_neighbors, count - 1)
    pairs: set[tuple[int, int]] = set()
    for i in range(count):
        for j in np.argsort(sims[i])[::-1][:k]:
            j = int(j)
            pairs.add((i, j) if i < j else (j, i))
    return sorted(pairs)


def extract_edges(principles: list[Principle], embeddings: np.ndarray,
                  llm: LLM) -> list[Edge]:
    """Build the principle graph. Candidate pairs are gated by embedding
    similarity (each principle's nearest neighbors), then classified by the
    LLM in bounded batches, so the request never overflows the token limit
    regardless of how many principles the corpus produced. A batch whose
    response is malformed is skipped with a warning; the rest still count."""
    ids = {p.id for p in principles}
    pairs = _candidate_pairs(embeddings, _NEIGHBORS)
    edges: list[Edge] = []
    for start in range(0, len(pairs), _BATCH):
        batch = pairs[start:start + _BATCH]
        listing = "\n".join(
            f"- id={principles[i].id} :: {principles[i].statement}\n"
            f"  id={principles[j].id} :: {principles[j].statement}"
            for i, j in batch)
        try:
            items = _parse_json_array(llm.complete(_PROMPT.format(listing=listing)))
        except (ValueError, KeyError) as e:
            print(f"warning: edge batch {start // _BATCH} skipped, malformed "
                  f"LLM response ({e})", file=sys.stderr)
            continue
        for item in items:
            src, dst, kind = item.get("src"), item.get("dst"), item.get("kind")
            if src in ids and dst in ids and src != dst:
                try:
                    edges.append(Edge(src=src, dst=dst, kind=kind))
                except ValueError:
                    continue  # unknown kind -> drop
    return edges
