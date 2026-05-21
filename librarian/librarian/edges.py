from .extract import LLM, _parse_json_array
from .models import Edge, Principle

_PROMPT = """\
Below is a numbered list of engineering principles, each with an id. Identify
relationships between them. Return ONLY a JSON array; each element:
  {{"src": "<id>", "dst": "<id>", "kind": "refines|contradicts|shares_topic"}}
  refines       = src is a more specific case of dst
  contradicts   = src and dst give conflicting guidance
  shares_topic  = src and dst address the same topic without refining/conflicting
Only relate principles that genuinely relate. No relationships returns [].

PRINCIPLES:
{listing}
"""


def extract_edges(principles: list[Principle], llm: LLM) -> list[Edge]:
    ids = {p.id for p in principles}
    listing = "\n".join(f"- id={p.id}: {p.statement}" for p in principles)
    items = _parse_json_array(llm.complete(_PROMPT.format(listing=listing)))
    edges: list[Edge] = []
    for item in items:
        src, dst, kind = item.get("src"), item.get("dst"), item.get("kind")
        if src in ids and dst in ids and src != dst:
            try:
                edges.append(Edge(src=src, dst=dst, kind=kind))
            except ValueError:
                continue  # unknown kind -> drop
    return edges
