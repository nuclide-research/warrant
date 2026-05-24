from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class CheckResult:
    check_id: str
    provenance: str   # "from_grounds" | "from_topic"
    passed: bool
    detail: str = ""


@dataclass
class NodeAmendment:
    node_id: str
    amended_reason: str


@dataclass
class ExecutorResult:
    node_id: str
    status: str                     # "done" | "failed"
    checks_run: list[CheckResult]
    principles_honored: list[str]   # principle ids
    principles_violated: list[str]
    amendments: list[NodeAmendment]
    summary: str                    # one line max


@dataclass
class NodeStatus:
    node_id: str
    status: str                     # "pending" | "in_flight" | "done" | "failed"
    attempts: int = 0
    last_result: ExecutorResult | None = None


@dataclass
class RunState:
    run_id: str
    plan_id: str
    plan_version: int
    worktree_path: str
    phase: str                      # "orient"|"retrieve"|"plan"|"execute"|"done"
    node_statuses: dict[str, NodeStatus]
    anchored_direction: str
    anchored_honesty_constraint: str
    iteration: int = 0
    created_at: str = ""
    updated_at: str = ""


class Invoker(Protocol):
    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult: ...
