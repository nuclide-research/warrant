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


@dataclass(frozen=True)
class PlanNode:
    id: str
    level: str
    decision: str
    approach: str
    grounds: tuple[str, ...]
    grounds_state: str
    grounds_note: str = ""
    conflict_resolution: str = ""
    applicable_checks: tuple[ApplicableCheck, ...] = ()
    depends_on: tuple[str, ...] = ()
    amended_from: str | None = None
    amended_reason: str | None = None
    children: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(
                f"level must be one of {LEVELS}, got {self.level!r}"
            )
        if self.grounds_state not in GROUNDS_STATES:
            raise ValueError(
                f"grounds_state must be one of {GROUNDS_STATES}, got {self.grounds_state!r}"
            )
        if self.grounds_state == "clean" and not self.grounds:
            raise ValueError(
                "grounds_state 'clean' requires at least one entry in grounds"
            )
        if self.grounds_state == "conflicted":
            if not self.conflict_resolution:
                raise ValueError(
                    "grounds_state 'conflicted' requires a non-empty conflict_resolution"
                )
            if len(self.grounds) < 2:
                raise ValueError(
                    "grounds_state 'conflicted' requires at least 2 entries in grounds"
                )
        if self.grounds_state == "ungrounded":
            if self.grounds:
                raise ValueError(
                    "grounds_state 'ungrounded' requires grounds to be empty"
                )
            if not self.grounds_note:
                raise ValueError(
                    "grounds_state 'ungrounded' requires a non-empty grounds_note"
                )
