from __future__ import annotations
from dataclasses import dataclass
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
    principles_honored: list[str]
    principles_violated: list[str]
    amendments: list[NodeAmendment]
    summary: str


@dataclass
class NodeStatus:
    node_id: str
    status: str                     # "pending" | "in_flight" | "done" | "failed"
    attempts: int = 0
    last_result: ExecutorResult | None = None
    pre_execution_sha: str = ""     # HEAD sha recorded before this node was dispatched


@dataclass
class RunState:
    run_id: str
    plan_id: str
    plan_version: int
    worktree_path: str
    phase: str                      # "orient"|"retrieve"|"plan"|"execute"|"verify"|"done"|"exhausted"
    node_statuses: dict[str, NodeStatus]
    anchored_direction: str
    anchored_honesty_constraint: str
    iteration: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class VerifierCheckOutcome:
    check_id: str
    provenance: str    # "from_grounds" | "from_topic"
    tier: int          # 1, 2, or 3
    passed: bool | None   # None for Tier-3 (judgment only, not boolean)
    metric_value: str  # Tier-2 computed value; empty if not Tier-2
    judgment: str      # Tier-3 rendered assessment; empty if not Tier-3
    detail: str = ""


@dataclass
class VerifierResult:
    node_id: str
    verdict: str                  # "pass" | "fail"
    confidence: float             # 0.0-1.0; reserved for second-verifier escalation (v2)
    check_outcomes: list[VerifierCheckOutcome]
    integrity_verdict: str        # "clean" | "integrity_failure" | "audit_catch"
    summary: str                  # one line max


@dataclass
class CitationReport:
    run_id: str
    plan_id: str
    grounded_clean: int
    grounded_conflicted: int
    grounded_ungrounded: int
    judgment_calls_documented: int    # ungrounded nodes that have a VerifierResult
    judgment_calls_undocumented: int  # ungrounded nodes without a VerifierResult
    tier1_run: int
    tier1_failed_integrity: int       # from_grounds Tier-1 with passed=False
    tier1_failed_audit: int           # from_topic Tier-1 with passed=False
    tier2_computed: int
    tier3_assessed: int
    plan_amendments: int              # nodes with amended_from != None
    suspiciously_clean: bool
    node_verdicts: dict[str, str]     # node_id -> "pass" | "fail" | "unverified"
    generated_at: str                 # ISO-8601


class Invoker(Protocol):
    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult: ...


class VerifierInvoker(Protocol):
    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult: ...
