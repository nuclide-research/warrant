from dataclasses import dataclass, asdict

EDGE_KINDS = ("refines", "contradicts", "shares_topic")


@dataclass(frozen=True)
class Citation:
    book: str
    isbn: str
    chapter: str
    section: str


@dataclass
class Principle:
    id: str
    statement: str
    citation: Citation
    checkability_tier: int  # 1, 2, or 3
    evidence_chunk: str


@dataclass(frozen=True)
class Edge:
    src: str   # principle id
    dst: str   # principle id
    kind: str  # one of EDGE_KINDS

    def __post_init__(self):
        if self.kind not in EDGE_KINDS:
            raise ValueError(f"edge kind must be one of {EDGE_KINDS}, got {self.kind!r}")


def principle_to_dict(p: Principle) -> dict:
    return {**asdict(p), "citation": asdict(p.citation)}


def principle_from_dict(d: dict) -> Principle:
    return Principle(
        id=d["id"],
        statement=d["statement"],
        citation=Citation(**d["citation"]),
        checkability_tier=d["checkability_tier"],
        evidence_chunk=d["evidence_chunk"],
    )
