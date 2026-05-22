from __future__ import annotations
from dataclasses import dataclass

LEVELS: tuple[str, ...] = ("architectural", "structural", "implementation")
GROUNDS_STATES: tuple[str, ...] = ("clean", "conflicted", "ungrounded")
PROVENANCE: tuple[str, ...] = ("from_grounds", "from_topic")


@dataclass(frozen=True)
class ApplicableCheck:
    check: str
    provenance: str

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(
                f"provenance must be one of {PROVENANCE}, got {self.provenance!r}"
            )
