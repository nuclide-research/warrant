# Warrant — Verify Phase + Citation Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the `loop/` package with the Verify phase and citation report so `WarrantRunner.run()` drives Orient → Retrieve → Plan → Execute → Verify and returns a `(RunState, CitationReport)` tuple.

**Architecture:** The verify phase (`phases/verify.py`) invokes a `VerifierInvoker` per done node with a materialized prompt (node + full principle text + executor self-report + real git diff); `from_grounds` Tier-1 failures route nodes back to Execute while `from_topic` failures surface in the report only. `citationreport.py` projects the final plan + all `VerifierResult`s into a `CitationReport` dataclass. The runner orchestrates an Execute→Verify loop up to `verify_iteration_cap` cycles.

**Tech Stack:** Python 3.10+, dataclasses, subprocess (git diff), pytest. Editable-installed siblings: `agent` (plan artifact), `librarian` (retrieval). All commands run from `/home/cowboy/warrant/loop/`.

---

## File map

| Action | Path |
|--------|------|
| Modify | `loop/models.py` |
| Modify | `loop/runstore.py` |
| Modify | `tests/fakes.py` |
| Create | `loop/verifier_materializer.py` |
| Create | `loop/citationreport.py` |
| Create | `loop/phases/verify.py` |
| Modify | `loop/phases/execute.py` |
| Modify | `loop/runner.py` |
| Create | `tests/test_verifier_materializer.py` |
| Create | `tests/test_citationreport.py` |
| Create | `tests/test_verify.py` |
| Modify | `tests/test_runner.py` |

## CRITICAL: import path rules

All imports from sibling packages use the installed package name, NOT a path with the package name repeated:
- `from agent.plan import PlanNode, Plan` (NOT `agent.agent.plan`)
- `from agent import planops, planstore`
- `from librarian.query import Result`
- `from librarian.models import Principle, Citation`
- `from librarian.store import Index`

Within the `loop` package, use relative imports:
- `from .models import RunState, NodeStatus, ...`
- `from .. import runstore as runstore_mod`
- `from ..verifier_materializer import materialize_verifier`

---

## Task 1: Update models.py and runstore.py

**Files:**
- Modify: `loop/models.py`
- Modify: `loop/runstore.py`
- Test: `tests/test_models.py` (if it exists; add new tests there; otherwise assert via import)

Add `pre_execution_sha` to `NodeStatus`, and add four new types: `VerifierCheckOutcome`, `VerifierResult`, `VerifierInvoker`, `CitationReport`. Update `runstore._node_status_from_dict` to deserialize `pre_execution_sha`.

- [ ] **Step 1: Write the complete new `loop/models.py`**

```python
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
```

- [ ] **Step 2: Update `_node_status_from_dict` in `loop/runstore.py`**

Change this one function (do not touch the rest of the file):

```python
def _node_status_from_dict(d: dict) -> NodeStatus:
    return NodeStatus(
        node_id=d["node_id"],
        status=d["status"],
        attempts=d["attempts"],
        last_result=_executor_result_from_dict(d.get("last_result")),
        pre_execution_sha=d.get("pre_execution_sha", ""),
    )
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v
```

Expected: all tests pass (the default value for `pre_execution_sha` preserves backward compatibility).

- [ ] **Step 4: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/models.py loop/runstore.py
git commit -m "feat(loop): add Verifier models and pre_execution_sha to NodeStatus"
```

---

## Task 2: Update tests/fakes.py

**Files:**
- Modify: `tests/fakes.py`

Add `FakeVerifierInvoker` (same queue pattern as `FakeInvoker`) and the `make_pass_verifier_result` helper.

- [ ] **Step 1: Write failing import test**

```python
# tests/test_fakes_verifier.py  (temporary file — delete after task)
from tests.fakes import FakeVerifierInvoker, make_pass_verifier_result
from loop.models import VerifierResult

def test_fake_verifier_invoker_default():
    inv = FakeVerifierInvoker()
    result = inv.invoke("prompt")
    assert result.verdict == "pass"
    assert result.integrity_verdict == "clean"

def test_fake_verifier_invoker_queue():
    inv = FakeVerifierInvoker()
    inv.queue(make_pass_verifier_result("n1"))
    result = inv.invoke("prompt")
    assert result.node_id == "n1"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_fakes_verifier.py -v
```

Expected: ImportError — `FakeVerifierInvoker` not yet defined.

- [ ] **Step 3: Append to `tests/fakes.py`**

Update the import line at the top of fakes.py:
```python
from loop.models import ExecutorResult, CheckResult, VerifierResult, VerifierCheckOutcome
```

Then append these two items to the end of fakes.py:
```python
class FakeVerifierInvoker:
    """Queue VerifierResults with .queue(result); falls back to a generic pass result."""

    def __init__(self):
        self._results: list[VerifierResult] = []

    def queue(self, result: VerifierResult) -> None:
        self._results.append(result)

    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult:
        if self._results:
            return self._results.pop(0)
        return VerifierResult(
            node_id="unknown",
            verdict="pass",
            confidence=1.0,
            check_outcomes=[],
            integrity_verdict="clean",
            summary="fake pass",
        )


def make_pass_verifier_result(node_id: str) -> VerifierResult:
    return VerifierResult(
        node_id=node_id,
        verdict="pass",
        confidence=1.0,
        check_outcomes=[],
        integrity_verdict="clean",
        summary="all checks passed",
    )
```

- [ ] **Step 4: Run tests**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_fakes_verifier.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Delete the temporary test file**

```bash
rm /home/cowboy/warrant/loop/tests/test_fakes_verifier.py
```

- [ ] **Step 6: Confirm all existing tests still pass**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd /home/cowboy/warrant/loop
git add tests/fakes.py
git commit -m "feat(loop/tests): add FakeVerifierInvoker and make_pass_verifier_result"
```

---

## Task 3: verifier_materializer.py + tests

**Files:**
- Create: `loop/verifier_materializer.py`
- Create: `tests/test_verifier_materializer.py`

Build the Verifier prompt from a plan node, retrieved principles, the Executor's result, and `git diff {pre_execution_sha}`. Mirror the structure of `loop/materializer.py`.

- [ ] **Step 1: Write `tests/test_verifier_materializer.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from loop.verifier_materializer import materialize_verifier
from loop.models import RunState, NodeStatus, ExecutorResult
from agent.plan import PlanNode, ApplicableCheck
from tests.fakes import make_fixture_principle
from librarian.query import Result
import numpy as np


def _make_result(principle) -> Result:
    return Result(principle=principle, citation=principle.citation, score=1.0, neighbors=[])


def _make_run_state() -> RunState:
    return RunState(
        run_id="r1", plan_id="p1", plan_version=1,
        worktree_path="/tmp/fake", phase="execute",
        node_statuses={},
        anchored_direction="#DIRECTION: build a cache layer",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
    )


def _make_executor_result(node_id: str = "n1") -> ExecutorResult:
    return ExecutorResult(
        node_id=node_id, status="done",
        checks_run=[], principles_honored=["p1"],
        principles_violated=[], amendments=[],
        summary="implemented cache layer",
    )


def _make_clean_node(pid: str = "test-book:ch1:s1") -> PlanNode:
    return PlanNode(
        id="n1", level="architectural",
        decision="Implement caching", approach="Use an LRU dict",
        grounds=(pid,), grounds_state="clean",
    )


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path,
                   check=True, capture_output=True)
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path,
                   check=True, capture_output=True)
    return tmp_path


def test_contains_anchored_direction():
    p = make_fixture_principle("test-book:ch1:s1")
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "#DIRECTION: build a cache layer" in prompt


def test_contains_honesty_constraint():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "#HONESTY-CONSTRAINT: be honest" in prompt


def test_contains_verifier_role_section():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "You are a Verifier" in prompt


def test_contains_node_decision_and_approach():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Implement caching" in prompt
    assert "Use an LRU dict" in prompt


def test_grounding_includes_tier():
    p = make_fixture_principle("test-book:ch1:s1", "Prefer composition.")
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node("test-book:ch1:s1"), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Tier" in prompt
    assert "Prefer composition." in prompt


def test_missing_principle_noted():
    p = make_fixture_principle("test-book:ch1:s1")
    node = PlanNode(
        id="n1", level="architectural",
        decision="Do X", approach="Use Y",
        grounds=("test-book:ch1:s1", "missing-id"),
        grounds_state="clean",
    )
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=node, principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Missing principles" in prompt
    assert "missing-id" in prompt


def test_executor_self_report_included():
    p = make_fixture_principle()
    rs = _make_run_state()
    exec_result = ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=["p1"],
        principles_violated=["p2"], amendments=[],
        summary="implemented cache layer",
    )
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=exec_result,
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "implemented cache layer" in prompt
    assert "Executor's self-report" in prompt


def test_diff_section_present_no_sha(git_repo):
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha="",
    )
    assert "Code diff" in prompt


def test_diff_shows_new_file(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    (git_repo / "cache.py").write_text("def lru(): pass\n")
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "cache.py" in prompt


def test_diff_no_changes_message(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "No changes detected" in prompt


def test_return_format_schema_present():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "integrity_verdict" in prompt
    assert "Return format" in prompt


def test_diff_truncated_at_8000(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    (git_repo / "big.py").write_text("x = 1\n" * 2000)  # ~14000 chars
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "truncated" in prompt
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_verifier_materializer.py -v
```

Expected: ImportError — `loop.verifier_materializer` does not exist yet.

- [ ] **Step 3: Create `loop/verifier_materializer.py`**

```python
from __future__ import annotations
import json
import subprocess

from agent.plan import PlanNode
from librarian.query import Result
from .models import RunState, ExecutorResult

_DIFF_MAX_CHARS = 8000

_VERIFIER_RESULT_SCHEMA = json.dumps(
    {
        "node_id": "<string>",
        "verdict": "pass | fail",
        "confidence": 0.95,
        "check_outcomes": [
            {
                "check_id": "<string>",
                "provenance": "from_grounds | from_topic",
                "tier": 1,
                "passed": True,
                "metric_value": "",
                "judgment": "",
                "detail": "",
            }
        ],
        "integrity_verdict": "clean | integrity_failure | audit_catch",
        "summary": "<one line>",
    },
    indent=2,
)


def _get_diff(worktree_path: str, pre_execution_sha: str) -> str:
    try:
        cmd = (
            ["git", "diff", pre_execution_sha]
            if pre_execution_sha
            else ["git", "diff"]
        )
        result = subprocess.run(
            cmd, cwd=worktree_path, capture_output=True, text=True, check=False
        )
        diff = result.stdout if result.returncode == 0 else ""
    except Exception:
        diff = ""
    if not diff.strip():
        return "No changes detected."
    if len(diff) > _DIFF_MAX_CHARS:
        diff = diff[:_DIFF_MAX_CHARS] + "\n[diff truncated at 8000 characters]"
    return diff


def materialize_verifier(
    node: PlanNode,
    principles: list[Result],
    run_state: RunState,
    executor_result: ExecutorResult,
    worktree_path: str,
    all_nodes: dict[str, PlanNode],
    pre_execution_sha: str = "",
) -> str:
    principle_map = {r.principle.id: r for r in principles}

    grounding_lines: list[str] = []
    missing_ids: list[str] = []
    for pid in node.grounds:
        if pid in principle_map:
            r = principle_map[pid]
            p = r.principle
            grounding_lines.append(
                f"- **{p.id}** ({p.citation.book}, {p.citation.chapter}, "
                f"{p.citation.section})\n"
                f"  Statement: {p.statement}\n"
                f"  Evidence: {p.evidence_chunk}\n"
                f"  Checkability: Tier {p.checkability_tier} "
                f"(1=mechanical, 2=measurable, 3=judgment)"
            )
        else:
            missing_ids.append(pid)

    checks_lines = [
        f"- {ac.check} (provenance: {ac.provenance})"
        for ac in node.applicable_checks
    ]

    diff = _get_diff(worktree_path, pre_execution_sha)

    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        (
            "## Your role\n"
            "You are a Verifier. You did not write the code below and you have not seen "
            "the Executor's reasoning. Grade the Executor's work strictly against the "
            "cited principles. Do not accept the Executor's self-assessment at face value."
        ),
    ]

    node_lines = [
        f"Decision: {node.decision}",
        f"Approach: {node.approach}",
        f"Grounds state: {node.grounds_state}",
    ]
    if node.grounds_state == "conflicted" and node.conflict_resolution:
        node_lines.append(f"Conflict resolution: {node.conflict_resolution}")
    if node.grounds_state == "ungrounded" and node.grounds_note:
        node_lines.append(f"Grounds note: {node.grounds_note}")
    sections.append("## Plan node\n" + "\n".join(node_lines))

    if grounding_lines:
        sections.append("## Grounding\n" + "\n\n".join(grounding_lines))

    if missing_ids:
        lines = "\n".join(
            f"- {i}: grading cannot verify this citation" for i in missing_ids
        )
        sections.append(f"## Missing principles\n{lines}")

    if checks_lines:
        sections.append("## Checks to grade\n" + "\n".join(checks_lines))

    sections.append(
        f"## Executor's self-report\n"
        f"Status claimed: {executor_result.status}\n"
        f"Summary: {executor_result.summary}\n"
        f"Principles honored: {executor_result.principles_honored}\n"
        f"Principles violated: {executor_result.principles_violated}"
    )

    sections.append(f"## Code diff (actual changes in worktree)\n{diff}")

    sections.append(
        f"## Return format\n"
        f"Return ONLY a JSON object matching this schema — no prose before or after:\n"
        f"```json\n{_VERIFIER_RESULT_SCHEMA}\n```"
    )

    return "\n\n".join(sections)
```

- [ ] **Step 4: Run tests**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_verifier_materializer.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/verifier_materializer.py tests/test_verifier_materializer.py
git commit -m "feat(loop): add verifier_materializer with git-diff grounding"
```

---

## Task 4: citationreport.py + tests

**Files:**
- Create: `loop/citationreport.py`
- Create: `tests/test_citationreport.py`

Project plan + RunState + VerifierResults into a `CitationReport` and render it as formatted text.

- [ ] **Step 1: Write `tests/test_citationreport.py`**

```python
from __future__ import annotations
import pytest
from agent.plan import PlanNode
from agent import planops
from loop.models import RunState, VerifierResult, VerifierCheckOutcome, CitationReport
from loop.citationreport import generate_citation_report, render_citation_report


def _plan_with_nodes(*nodes: PlanNode):
    plan = planops.new_plan("test task")
    for n in nodes:
        plan = planops.add_node(plan, n)
    return plan


def _clean_node(nid: str) -> PlanNode:
    return PlanNode(
        id=nid, level="architectural",
        decision=f"Decision {nid}", approach="Approach",
        grounds=("p1",), grounds_state="clean",
    )


def _ungrounded_node(nid: str) -> PlanNode:
    return PlanNode(
        id=nid, level="architectural",
        decision=f"Decision {nid}", approach="Approach",
        grounds=(), grounds_state="ungrounded",
        grounds_note="Library was silent on this topic.",
    )


def _conflicted_node(nid: str) -> PlanNode:
    return PlanNode(
        id=nid, level="architectural",
        decision=f"Decision {nid}", approach="Approach",
        grounds=("p1", "p2"), grounds_state="conflicted",
        conflict_resolution="p1 wins because it is more specific",
    )


def _run_state(plan) -> RunState:
    return RunState(
        run_id="run1", plan_id=plan.plan_id, plan_version=plan.version,
        worktree_path="/tmp/fake", phase="done",
        node_statuses={},
        anchored_direction="#DIRECTION: test",
        anchored_honesty_constraint="be honest",
    )


def _pass_vr(node_id: str) -> VerifierResult:
    return VerifierResult(
        node_id=node_id, verdict="pass", confidence=1.0,
        check_outcomes=[], integrity_verdict="clean", summary="pass",
    )


def _integrity_fail_vr(node_id: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="c1", provenance="from_grounds", tier=1,
        passed=False, metric_value="", judgment="",
    )
    return VerifierResult(
        node_id=node_id, verdict="fail", confidence=0.5,
        check_outcomes=[co], integrity_verdict="integrity_failure",
        summary="integrity check failed",
    )


def _audit_fail_vr(node_id: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="c2", provenance="from_topic", tier=1,
        passed=False, metric_value="", judgment="",
    )
    return VerifierResult(
        node_id=node_id, verdict="fail", confidence=0.8,
        check_outcomes=[co], integrity_verdict="audit_catch",
        summary="audit catch",
    )


def _tier2_vr(node_id: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="m1", provenance="from_grounds", tier=2,
        passed=None, metric_value="0.87", judgment="",
    )
    return VerifierResult(
        node_id=node_id, verdict="pass", confidence=0.9,
        check_outcomes=[co], integrity_verdict="clean",
        summary="metric computed",
    )


def _tier3_vr(node_id: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="j1", provenance="from_grounds", tier=3,
        passed=None, metric_value="", judgment="Abstraction feels natural.",
    )
    return VerifierResult(
        node_id=node_id, verdict="pass", confidence=0.7,
        check_outcomes=[co], integrity_verdict="clean",
        summary="judgment rendered",
    )


def test_grounded_counts():
    plan = _plan_with_nodes(_clean_node("n1"), _conflicted_node("n2"), _ungrounded_node("n3"))
    report = generate_citation_report(plan, _run_state(plan), {})
    assert report.grounded_clean == 1
    assert report.grounded_conflicted == 1
    assert report.grounded_ungrounded == 1


def test_judgment_calls_documented_vs_undocumented():
    plan = _plan_with_nodes(_ungrounded_node("n1"), _ungrounded_node("n2"))
    vrs = {"n1": _pass_vr("n1")}  # n2 has no VerifierResult
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.judgment_calls_documented == 1
    assert report.judgment_calls_undocumented == 1


def test_tier1_failed_integrity():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _integrity_fail_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.tier1_run == 1
    assert report.tier1_failed_integrity == 1
    assert report.tier1_failed_audit == 0


def test_tier1_failed_audit():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _audit_fail_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.tier1_failed_integrity == 0
    assert report.tier1_failed_audit == 1


def test_tier2_computed():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _tier2_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.tier2_computed == 1


def test_tier3_assessed():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _tier3_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.tier3_assessed == 1


def test_plan_amendments_zero():
    plan = _plan_with_nodes(_clean_node("n1"))
    report = generate_citation_report(plan, _run_state(plan), {})
    assert report.plan_amendments == 0


def test_plan_amendments_counted():
    from agent import planops as po
    plan = _plan_with_nodes(_clean_node("n1"))
    plan = po.amend_node(plan, "n1", "stuck")
    plan = po.next_version(plan)
    report = generate_citation_report(plan, _run_state(plan), {})
    assert report.plan_amendments == 1


def test_node_verdicts_pass():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _pass_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    assert report.node_verdicts["n1"] == "pass"


def test_node_verdicts_unverified():
    plan = _plan_with_nodes(_clean_node("n1"))
    report = generate_citation_report(plan, _run_state(plan), {})
    assert report.node_verdicts["n1"] == "unverified"


def test_suspiciously_clean_fires():
    nodes = [_clean_node(f"n{i}") for i in range(5)]
    plan = _plan_with_nodes(*nodes)
    vrs = {f"n{i}": _pass_vr(f"n{i}") for i in range(5)}
    report = generate_citation_report(plan, _run_state(plan), vrs,
                                      suspiciously_clean_node_threshold=5)
    assert report.suspiciously_clean is True


def test_suspiciously_clean_does_not_fire_small_plan():
    nodes = [_clean_node(f"n{i}") for i in range(4)]
    plan = _plan_with_nodes(*nodes)
    vrs = {f"n{i}": _pass_vr(f"n{i}") for i in range(4)}
    report = generate_citation_report(plan, _run_state(plan), vrs,
                                      suspiciously_clean_node_threshold=5)
    assert report.suspiciously_clean is False


def test_suspiciously_clean_does_not_fire_with_integrity_failure():
    nodes = [_clean_node(f"n{i}") for i in range(6)]
    plan = _plan_with_nodes(*nodes)
    vrs = {f"n{i}": _pass_vr(f"n{i}") for i in range(5)}
    vrs["n5"] = _integrity_fail_vr("n5")
    report = generate_citation_report(plan, _run_state(plan), vrs,
                                      suspiciously_clean_node_threshold=5)
    assert report.suspiciously_clean is False


def test_render_includes_grounded_line():
    plan = _plan_with_nodes(_clean_node("n1"), _clean_node("n2"))
    report = generate_citation_report(plan, _run_state(plan), {})
    text = render_citation_report(report)
    assert "grounded decisions" in text
    assert "clean 2" in text


def test_render_undoc_flag():
    plan = _plan_with_nodes(_ungrounded_node("n1"))
    report = generate_citation_report(plan, _run_state(plan), {})
    text = render_citation_report(report)
    assert "<- flag" in text


def test_render_no_undoc_flag_when_zero():
    plan = _plan_with_nodes(_clean_node("n1"))
    vrs = {"n1": _pass_vr("n1")}
    report = generate_citation_report(plan, _run_state(plan), vrs)
    text = render_citation_report(report)
    assert "<- flag" not in text


def test_render_suspicious_line():
    nodes = [_clean_node(f"n{i}") for i in range(5)]
    plan = _plan_with_nodes(*nodes)
    vrs = {f"n{i}": _pass_vr(f"n{i}") for i in range(5)}
    report = generate_citation_report(plan, _run_state(plan), vrs,
                                      suspiciously_clean_node_threshold=5)
    text = render_citation_report(report)
    assert "SUSPICIOUSLY CLEAN" in text


def test_render_no_suspicious_line_when_not_set():
    plan = _plan_with_nodes(_clean_node("n1"))
    report = generate_citation_report(plan, _run_state(plan), {})
    text = render_citation_report(report)
    assert "SUSPICIOUSLY CLEAN" not in text
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_citationreport.py -v
```

Expected: ImportError — `loop.citationreport` does not exist yet.

- [ ] **Step 3: Create `loop/citationreport.py`**

```python
from __future__ import annotations
from datetime import datetime, timezone

from agent.plan import Plan
from .models import RunState, VerifierResult, CitationReport


def generate_citation_report(
    plan: Plan,
    run_state: RunState,
    verifier_results: dict[str, VerifierResult],
    suspiciously_clean_node_threshold: int = 5,
) -> CitationReport:
    grounded_clean = 0
    grounded_conflicted = 0
    grounded_ungrounded = 0
    judgment_calls_documented = 0
    judgment_calls_undocumented = 0

    for node in plan.nodes:
        if node.grounds_state == "clean":
            grounded_clean += 1
        elif node.grounds_state == "conflicted":
            grounded_conflicted += 1
        else:
            grounded_ungrounded += 1
            if node.id in verifier_results:
                judgment_calls_documented += 1
            else:
                judgment_calls_undocumented += 1

    tier1_run = 0
    tier1_failed_integrity = 0
    tier1_failed_audit = 0
    tier2_computed = 0
    tier3_assessed = 0

    for vr in verifier_results.values():
        for co in vr.check_outcomes:
            if co.tier == 1:
                tier1_run += 1
                if co.passed is False:
                    if co.provenance == "from_grounds":
                        tier1_failed_integrity += 1
                    else:
                        tier1_failed_audit += 1
            elif co.tier == 2:
                tier2_computed += 1
            elif co.tier == 3:
                tier3_assessed += 1

    plan_amendments = sum(1 for n in plan.nodes if n.amended_from is not None)

    suspiciously_clean = (
        judgment_calls_undocumented == 0
        and tier1_failed_integrity == 0
        and tier1_failed_audit == 0
        and plan_amendments == 0
        and len(plan.nodes) >= suspiciously_clean_node_threshold
    )

    node_verdicts: dict[str, str] = {}
    for node in plan.nodes:
        if node.id in verifier_results:
            node_verdicts[node.id] = verifier_results[node.id].verdict
        else:
            node_verdicts[node.id] = "unverified"

    return CitationReport(
        run_id=run_state.run_id,
        plan_id=plan.plan_id,
        grounded_clean=grounded_clean,
        grounded_conflicted=grounded_conflicted,
        grounded_ungrounded=grounded_ungrounded,
        judgment_calls_documented=judgment_calls_documented,
        judgment_calls_undocumented=judgment_calls_undocumented,
        tier1_run=tier1_run,
        tier1_failed_integrity=tier1_failed_integrity,
        tier1_failed_audit=tier1_failed_audit,
        tier2_computed=tier2_computed,
        tier3_assessed=tier3_assessed,
        plan_amendments=plan_amendments,
        suspiciously_clean=suspiciously_clean,
        node_verdicts=node_verdicts,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_citation_report(report: CitationReport) -> str:
    grounded_total = report.grounded_clean + report.grounded_conflicted
    jc_total = report.judgment_calls_documented + report.judgment_calls_undocumented
    undoc_flag = " <- flag" if report.judgment_calls_undocumented > 0 else ""
    failed_total = report.tier1_failed_integrity + report.tier1_failed_audit
    amendments_note = "  (see version diff)" if report.plan_amendments > 0 else ""

    lines = [
        f"grounded decisions:    {grounded_total:>4}   "
        f"(clean {report.grounded_clean}, conflicted {report.grounded_conflicted})",
        f"judgment calls:        {jc_total:>4}   "
        f"(documented {report.judgment_calls_documented}, "
        f"undocumented {report.judgment_calls_undocumented}{undoc_flag})",
        f"tier-1 checks:         {report.tier1_run:>4} run / {failed_total} failed",
        f"                            "
        f"({report.tier1_failed_integrity} from_grounds <- integrity, "
        f"{report.tier1_failed_audit} from_topic <- audit catch)",
        f"tier-2 metrics:        {report.tier2_computed:>4} computed",
        f"tier-3 principles:     {report.tier3_assessed:>4} assessed, judgment-only",
        f"plan amendments:       {report.plan_amendments:>4}{amendments_note}",
    ]
    if report.suspiciously_clean:
        lines.append("SUSPICIOUSLY CLEAN — review manually")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_citationreport.py -v
```

Expected: all 19 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/citationreport.py tests/test_citationreport.py
git commit -m "feat(loop): add citationreport generation and text render"
```

---

## Task 5: phases/verify.py + tests

**Files:**
- Create: `loop/phases/verify.py`
- Create: `tests/test_verify.py`

Implements the verify phase: invokes VerifierInvoker per done node, routes `integrity_failure` results back to Execute (or to `failed` if at cap), leaves `audit_catch` / `clean` nodes as done.

- [ ] **Step 1: Write `tests/test_verify.py`**

```python
from __future__ import annotations
from pathlib import Path
import json
import pytest
from agent.plan import PlanNode
from agent import planops
from loop.models import (
    RunState, NodeStatus, ExecutorResult, VerifierResult, VerifierCheckOutcome,
)
from loop.phases.verify import verify
from tests.fakes import FakeVerifierInvoker, make_pass_verifier_result


def _clean_node(nid: str) -> PlanNode:
    return PlanNode(
        id=nid, level="architectural",
        decision=f"Decision {nid}", approach="Approach",
        grounds=("p1",), grounds_state="clean",
    )


def _make_plan(*nids: str):
    plan = planops.new_plan("test")
    for nid in nids:
        plan = planops.add_node(plan, _clean_node(nid))
    return plan


def _done_executor_result(nid: str) -> ExecutorResult:
    return ExecutorResult(
        node_id=nid, status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    )


def _make_run_state(plan) -> RunState:
    return RunState(
        run_id="r1", plan_id=plan.plan_id, plan_version=plan.version,
        worktree_path="/tmp/fake", phase="done",
        node_statuses={
            nid: NodeStatus(
                node_id=nid, status="done",
                last_result=_done_executor_result(nid),
            )
            for nid in [n.id for n in plan.nodes]
        },
        anchored_direction="#DIRECTION: test",
        anchored_honesty_constraint="be honest",
    )


def _integrity_fail_vr(nid: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="c1", provenance="from_grounds", tier=1,
        passed=False, metric_value="", judgment="",
    )
    return VerifierResult(
        node_id=nid, verdict="fail", confidence=0.3,
        check_outcomes=[co], integrity_verdict="integrity_failure",
        summary="integrity check failed",
    )


def _audit_catch_vr(nid: str) -> VerifierResult:
    co = VerifierCheckOutcome(
        check_id="c2", provenance="from_topic", tier=1,
        passed=False, metric_value="", judgment="",
    )
    return VerifierResult(
        node_id=nid, verdict="fail", confidence=0.8,
        check_outcomes=[co], integrity_verdict="audit_catch",
        summary="audit catch only",
    )


def test_pass_result_leaves_node_done(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    invoker = FakeVerifierInvoker()
    invoker.queue(make_pass_verifier_result("n1"))
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path)
    assert new_rs.node_statuses["n1"].status == "done"
    assert len(results) == 1
    assert results[0].verdict == "pass"


def test_integrity_failure_routes_to_pending(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    invoker = FakeVerifierInvoker()
    invoker.queue(_integrity_fail_vr("n1"))
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path,
                             per_node_attempt_cap=3)
    assert new_rs.node_statuses["n1"].status == "pending"
    assert new_rs.node_statuses["n1"].attempts == 1


def test_audit_catch_leaves_node_done(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    invoker = FakeVerifierInvoker()
    invoker.queue(_audit_catch_vr("n1"))
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path)
    assert new_rs.node_statuses["n1"].status == "done"


def test_attempt_cap_marks_failed_and_amends(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    run_state.node_statuses["n1"].attempts = 2  # already at cap-1 (cap=3)
    invoker = FakeVerifierInvoker()
    invoker.queue(_integrity_fail_vr("n1"))
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path,
                             per_node_attempt_cap=3)
    assert new_rs.node_statuses["n1"].status == "failed"
    assert new_rs.node_statuses["n1"].attempts == 3
    # plan was amended and saved
    from agent import planstore
    saved_plan = planstore.load_version(tmp_path, new_rs.plan_version)
    amended = [n for n in saved_plan.nodes if n.amended_from is not None]
    assert amended


def test_no_eligible_nodes_skipped(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    run_state.node_statuses["n1"].status = "pending"  # not done, so not eligible
    invoker = FakeVerifierInvoker()
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path)
    assert results == []
    assert new_rs.node_statuses["n1"].status == "pending"


def test_verifier_exception_leaves_node_done(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)

    class BrokenInvoker:
        def invoke(self, prompt, timeout=None):
            raise RuntimeError("network error")

    new_rs, results = verify(plan, run_state, [], BrokenInvoker(), tmp_path)
    assert new_rs.node_statuses["n1"].status == "done"
    assert results[0].summary.startswith("verifier error")


def test_save_run_called(tmp_path):
    plan = _make_plan("n1")
    run_state = _make_run_state(plan)
    invoker = FakeVerifierInvoker()
    invoker.queue(make_pass_verifier_result("n1"))
    verify(plan, run_state, [], invoker, tmp_path)
    from loop import runstore
    saved = runstore.load_latest_run(tmp_path)
    assert saved.run_id == "r1"


def test_multiple_nodes_both_verified(tmp_path):
    plan = _make_plan("n1", "n2")
    run_state = _make_run_state(plan)
    invoker = FakeVerifierInvoker()
    invoker.queue(make_pass_verifier_result("n1"))
    invoker.queue(make_pass_verifier_result("n2"))
    new_rs, results = verify(plan, run_state, [], invoker, tmp_path)
    assert len(results) == 2
    assert new_rs.node_statuses["n1"].status == "done"
    assert new_rs.node_statuses["n2"].status == "done"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_verify.py -v
```

Expected: ImportError — `loop.phases.verify` does not exist yet.

- [ ] **Step 3: Create `loop/phases/verify.py`**

```python
from __future__ import annotations
from pathlib import Path

from agent.plan import Plan, PlanNode
from agent import planops, planstore
from librarian.query import Result
from ..models import RunState, NodeStatus, VerifierResult, VerifierInvoker
from .. import runstore as runstore_mod
from ..verifier_materializer import materialize_verifier


def verify(
    plan: Plan,
    run_state: RunState,
    principles: list[Result],
    verifier_invoker: VerifierInvoker,
    out_dir: Path,
    per_node_attempt_cap: int = 3,
    watchdog_timeout: float = 300.0,
) -> tuple[RunState, list[VerifierResult]]:
    out_dir = Path(out_dir)
    all_nodes: dict[str, PlanNode] = {n.id: n for n in plan.nodes}
    verifier_results: list[VerifierResult] = []

    eligible = [
        node for node in plan.nodes
        if run_state.node_statuses.get(node.id) is not None
        and run_state.node_statuses[node.id].status == "done"
        and run_state.node_statuses[node.id].last_result is not None
    ]

    for node in eligible:
        ns = run_state.node_statuses[node.id]
        prompt = materialize_verifier(
            node=node,
            principles=principles,
            run_state=run_state,
            executor_result=ns.last_result,
            worktree_path=run_state.worktree_path,
            all_nodes=all_nodes,
            pre_execution_sha=ns.pre_execution_sha,
        )
        try:
            vr = verifier_invoker.invoke(prompt, watchdog_timeout)
        except Exception as exc:
            vr = VerifierResult(
                node_id=node.id,
                verdict="fail",
                confidence=0.0,
                check_outcomes=[],
                integrity_verdict="clean",
                summary=f"verifier error: {exc}",
            )

        verifier_results.append(vr)

        if vr.integrity_verdict == "integrity_failure":
            ns.attempts += 1
            if ns.attempts >= per_node_attempt_cap:
                violated = [
                    co.check_id
                    for co in vr.check_outcomes
                    if co.tier == 1
                    and co.provenance == "from_grounds"
                    and co.passed is False
                ]
                reason = (
                    f"verify failed after {ns.attempts} attempt(s)"
                    + (f"; integrity checks failed: {violated}" if violated else "")
                )
                try:
                    plan = planops.amend_node(plan, node.id, reason)
                    plan = planops.next_version(plan)
                    planstore.save_plan(plan, out_dir)
                    run_state.plan_version = plan.version
                    all_nodes = {n.id: n for n in plan.nodes}
                except ValueError:
                    pass
                ns.status = "failed"
            else:
                ns.status = "pending"

    runstore_mod.save_run(run_state, out_dir)
    return run_state, verifier_results
```

- [ ] **Step 4: Run tests**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_verify.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/phases/verify.py tests/test_verify.py
git commit -m "feat(loop): add verify phase with routing and stuck detection"
```

---

## Task 6: Update phases/execute.py

**Files:**
- Modify: `loop/phases/execute.py`

Record `pre_execution_sha` on each `NodeStatus` before each dispatch batch by getting the current HEAD sha from the worktree.

- [ ] **Step 1: Write a failing test in `tests/test_execute.py`** (add to existing file)

Find `tests/test_execute.py` and append:

```python
def test_pre_execution_sha_recorded(tmp_path):
    import subprocess as sp
    repo = tmp_path / "repo"
    repo.mkdir()
    sp.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True)
    (repo / "f.txt").write_text("x")
    sp.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    from agent import planops
    from agent.plan import PlanNode
    from loop.models import RunState, NodeStatus, ExecutorResult
    from loop.phases.execute import execute
    from tests.fakes import FakeInvoker

    node = PlanNode(
        id="n1", level="architectural",
        decision="Do X", approach="Use Y",
        grounds=(), grounds_state="ungrounded", grounds_note="silent",
    )
    plan = planops.new_plan("task")
    plan = planops.add_node(plan, node)

    run_state = RunState(
        run_id="r1", plan_id=plan.plan_id, plan_version=plan.version,
        worktree_path=str(repo), phase="execute",
        node_statuses={"n1": NodeStatus(node_id="n1", status="pending")},
        anchored_direction="#DIRECTION: test",
        anchored_honesty_constraint="be honest",
    )
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    final_rs = execute(plan, run_state, [], invoker, tmp_path)
    sha = final_rs.node_statuses["n1"].pre_execution_sha
    assert sha != ""
    assert len(sha) == 40  # full git sha
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_execute.py::test_pre_execution_sha_recorded -v
```

Expected: FAIL — `pre_execution_sha` is still empty string (default).

- [ ] **Step 3: Update `loop/phases/execute.py`**

Add the `_get_head_sha` helper and update the dispatch loop. Here is the complete new `execute.py`:

```python
from __future__ import annotations
import subprocess as _subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agent.plan import Plan, PlanNode
from agent import planops, planstore
from ..models import RunState, NodeStatus, ExecutorResult, Invoker
from .. import runstore as runstore_mod
from ..materializer import materialize
from librarian.query import Result

_INTEGRITY_PROVENANCE = "from_grounds"


def _get_head_sha(worktree_path: str) -> str:
    try:
        result = _subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path,
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _ready_nodes(plan: Plan, run_state: RunState) -> list[PlanNode]:
    done_ids = {
        nid for nid, ns in run_state.node_statuses.items()
        if ns.status == "done"
    }
    ready = []
    for node in plan.nodes:
        ns = run_state.node_statuses.get(node.id)
        if ns is None or ns.status != "pending":
            continue
        if all(dep in done_ids for dep in node.depends_on):
            ready.append(node)
    return ready


def _all_done(run_state: RunState) -> bool:
    return all(
        ns.status in ("done", "failed")
        for ns in run_state.node_statuses.values()
    )


def _has_integrity_failure(result: ExecutorResult) -> bool:
    return any(
        c.provenance == _INTEGRITY_PROVENANCE and not c.passed
        for c in result.checks_run
    )


def _sync_statuses(plan: Plan, run_state: RunState) -> None:
    for node in plan.nodes:
        if node.id not in run_state.node_statuses:
            run_state.node_statuses[node.id] = NodeStatus(
                node_id=node.id, status="pending"
            )


def execute(
    plan: Plan,
    run_state: RunState,
    principles: list[Result],
    invoker: Invoker,
    out_dir: Path,
    global_iteration_cap: int = 10,
    per_node_attempt_cap: int = 3,
    watchdog_timeout: float = 300.0,
    max_parallel: int = 3,
) -> RunState:
    out_dir = Path(out_dir)
    all_nodes: dict[str, PlanNode] = {n.id: n for n in plan.nodes}
    _sync_statuses(plan, run_state)

    while not _all_done(run_state) and run_state.iteration < global_iteration_cap:
        ready = _ready_nodes(plan, run_state)
        if not ready:
            break

        ready_ids = [n.id for n in ready]
        assert planops.independent_siblings(plan, ready_ids), (
            f"BUG: dispatch set is not independent: {ready_ids}"
        )

        head_sha = _get_head_sha(run_state.worktree_path)
        for node in ready:
            run_state.node_statuses[node.id].status = "in_flight"
            run_state.node_statuses[node.id].pre_execution_sha = head_sha

        results: dict[str, ExecutorResult] = {}

        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {
                pool.submit(
                    invoker.invoke,
                    materialize(node, principles, run_state, all_nodes),
                    watchdog_timeout,
                ): node
                for node in ready
            }
            for future in as_completed(futures):
                node = futures[future]
                try:
                    result = future.result()
                    result = ExecutorResult(
                        node_id=node.id,
                        status=result.status,
                        checks_run=result.checks_run,
                        principles_honored=result.principles_honored,
                        principles_violated=result.principles_violated,
                        amendments=result.amendments,
                        summary=result.summary,
                    )
                except Exception as exc:
                    result = ExecutorResult(
                        node_id=node.id,
                        status="failed",
                        checks_run=[], principles_honored=[],
                        principles_violated=[], amendments=[],
                        summary=f"invoker error: {exc}",
                    )
                results[node.id] = result

        for node in ready:
            result = results[node.id]
            ns = run_state.node_statuses[node.id]
            ns.last_result = result

            if result.status == "done":
                ns.status = "done"
            else:
                ns.attempts += 1
                should_amend = (
                    ns.attempts >= per_node_attempt_cap
                    or _has_integrity_failure(result)
                )
                if should_amend:
                    violated = result.principles_violated
                    reason = (
                        f"stuck after {ns.attempts} attempt(s)"
                        + (f"; violated: {violated}" if violated else "")
                    )
                    try:
                        plan = planops.amend_node(plan, node.id, reason)
                        plan = planops.next_version(plan)
                        planstore.save_plan(plan, out_dir)
                        run_state.plan_version = plan.version
                        all_nodes = {n.id: n for n in plan.nodes}
                    except ValueError:
                        pass
                    ns.status = "failed"
                else:
                    ns.status = "pending"

        run_state.iteration += 1
        runstore_mod.save_run(run_state, out_dir)

    if _all_done(run_state):
        run_state.phase = "done"
    else:
        run_state.phase = "exhausted"
    runstore_mod.save_run(run_state, out_dir)
    return run_state
```

- [ ] **Step 4: Run the new test**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_execute.py::test_pre_execution_sha_recorded -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/phases/execute.py tests/test_execute.py
git commit -m "feat(loop/execute): record pre_execution_sha on NodeStatus before dispatch"
```

---

## Task 7: Update runner.py

**Files:**
- Modify: `loop/runner.py`

Add `verifier_invoker` + `verify_iteration_cap` parameters, import verify + generate_citation_report, run the Execute→Verify loop, change return type to `tuple[RunState, CitationReport]`.

- [ ] **Step 1: Write `loop/runner.py` — complete new version**

```python
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from librarian.store import Index
from agent import planstore

from .models import RunState, NodeStatus, Invoker, VerifierInvoker, VerifierResult, CitationReport
from . import runstore as runstore_mod
from .worktree import WorktreeManager
from .phases.orient import orient
from .phases.retrieve import retrieve
from .phases.plan import build_initial
from .phases.execute import execute
from .phases.verify import verify
from .citationreport import generate_citation_report

LLM = Callable[[str], str]


class WarrantRunner:
    def __init__(
        self,
        index: Index,
        embedder,
        reranker,
        llm: LLM,
        invoker: Invoker,
        verifier_invoker: VerifierInvoker,
        worktree_mgr: WorktreeManager,
        base_repo: Path,
        out_dir: Path,
        global_iteration_cap: int = 10,
        per_node_attempt_cap: int = 3,
        watchdog_timeout: float = 300.0,
        max_parallel: int = 3,
        max_principles: int = 15,
        verify_iteration_cap: int = 3,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._invoker = invoker
        self._verifier_invoker = verifier_invoker
        self._worktree_mgr = worktree_mgr
        self._base_repo = Path(base_repo)
        self._out_dir = Path(out_dir)
        self._cfg = dict(
            global_iteration_cap=global_iteration_cap,
            per_node_attempt_cap=per_node_attempt_cap,
            watchdog_timeout=watchdog_timeout,
            max_parallel=max_parallel,
        )
        self._max_principles = max_principles
        self._verify_iteration_cap = verify_iteration_cap

    def _execute_verify_loop(
        self,
        plan,
        run_state: RunState,
        principles,
    ) -> tuple[RunState, CitationReport]:
        from agent import planstore as _planstore
        all_verifier_results: dict[str, VerifierResult] = {}
        current_plan = plan

        for _ in range(self._verify_iteration_cap):
            run_state = execute(
                current_plan, run_state, principles,
                self._invoker, self._out_dir, **self._cfg,
            )
            run_state, new_vr = verify(
                current_plan, run_state, principles,
                self._verifier_invoker, self._out_dir,
                per_node_attempt_cap=self._cfg["per_node_attempt_cap"],
                watchdog_timeout=self._cfg["watchdog_timeout"],
            )
            all_verifier_results.update({r.node_id: r for r in new_vr})

            current_plan = _planstore.load_version(
                self._out_dir, run_state.plan_version
            )

            has_pending = any(
                ns.status == "pending"
                for ns in run_state.node_statuses.values()
            )
            if not has_pending:
                break

        report = generate_citation_report(
            current_plan, run_state, all_verifier_results
        )
        return run_state, report

    def run(self, direction: str) -> tuple[RunState, CitationReport]:
        run_id = uuid.uuid4().hex

        orient_result = orient(
            direction, self._index, self._llm,
            self._worktree_mgr, self._base_repo, run_id,
        )
        principles = retrieve(
            orient_result.retrieval_queries,
            self._index,
            self._embedder,
            self._reranker,
            orient_result.worktree_path,
            self._max_principles,
        )
        plan = build_initial(direction, principles, self._llm)
        planstore.save_plan(plan, self._out_dir)

        run_state = RunState(
            run_id=run_id,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            worktree_path=orient_result.worktree_path,
            phase="execute",
            node_statuses={
                n.id: NodeStatus(node_id=n.id, status="pending")
                for n in plan.nodes
            },
            anchored_direction=orient_result.anchored_direction,
            anchored_honesty_constraint=orient_result.anchored_honesty_constraint,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        runstore_mod.save_run(run_state, self._out_dir)

        return self._execute_verify_loop(plan, run_state, principles)

    def resume(self, run_state: RunState) -> tuple[RunState, CitationReport]:
        from librarian.models import principle_from_dict
        from librarian.query import Result
        from agent import planstore as _planstore

        plan = _planstore.load_version(self._out_dir, run_state.plan_version)
        principles_file = (
            Path(run_state.worktree_path) / ".warrant" / "principles.json"
        )
        raw = json.loads(principles_file.read_text(encoding="utf-8"))
        principles = [
            Result(principle=principle_from_dict(d), citation=principle_from_dict(d).citation,
                   score=1.0, neighbors=[])
            for d in raw
        ]

        for ns in run_state.node_statuses.values():
            if ns.status == "in_flight":
                ns.status = "pending"

        runstore_mod.save_run(run_state, self._out_dir)

        return self._execute_verify_loop(plan, run_state, principles)
```

- [ ] **Step 2: Verify the full test suite still runs**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v 2>&1 | head -40
```

Expected: tests that don't involve runner should pass; runner tests may fail due to signature change — that's expected.

- [ ] **Step 3: Commit**

```bash
cd /home/cowboy/warrant/loop
git add loop/runner.py
git commit -m "feat(loop): add Execute→Verify loop to WarrantRunner, return (RunState, CitationReport)"
```

---

## Task 8: Update tests/test_runner.py

**Files:**
- Modify: `tests/test_runner.py`

Update the 3 existing tests to unpack the tuple return, update `_make_runner` to accept a `verifier_invoker`, and add a Plan 3 integration test.

- [ ] **Step 1: Write the complete new `tests/test_runner.py`**

```python
import json
import subprocess
from pathlib import Path
import pytest
from loop.runner import WarrantRunner
from loop.worktree import WorktreeManager
from loop import runstore
from loop.models import ExecutorResult, CitationReport
from tests.fakes import (
    FakeLLM, FakeInvoker, FakeVerifierInvoker,
    FakeReranker, FakeEmbedder, make_fixture_index,
    make_pass_verifier_result,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path,
                   check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path,
                   check=True, capture_output=True)


def _make_runner(tmp_path, llm, invoker, verifier_invoker=None, index=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    out_dir = tmp_path / "out"
    return WarrantRunner(
        index=index or make_fixture_index(2),
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        llm=llm,
        invoker=invoker,
        verifier_invoker=verifier_invoker or FakeVerifierInvoker(),
        worktree_mgr=WorktreeManager(),
        base_repo=repo,
        out_dir=out_dir,
        global_iteration_cap=5,
        per_node_attempt_cap=2,
        watchdog_timeout=30.0,
        verify_iteration_cap=2,
    ), repo


def test_run_returns_done_run_state(tmp_path):
    llm = FakeLLM()
    llm.queue("I am a specialist.")
    llm.queue("query 1\nquery 2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Use Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    verifier = FakeVerifierInvoker()
    runner, repo = _make_runner(tmp_path, llm, invoker, verifier)
    final_rs, report = runner.run("build a cache layer")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert final_rs.phase == "done"


def test_run_all_nodes_done(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    final_rs, report = runner.run("build something")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    done = all(
        ns.status in ("done", "failed")
        for ns in final_rs.node_statuses.values()
    )
    assert done


def test_run_creates_run_files(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    out_dir = tmp_path / "out"
    final_rs, report = runner.run("build")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert list(out_dir.glob("run.v*.json"))


def test_run_returns_citation_report(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    verifier = FakeVerifierInvoker()
    verifier.queue(make_pass_verifier_result("n1"))
    runner, _ = _make_runner(tmp_path, llm, invoker, verifier)
    final_rs, report = runner.run("build something")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert isinstance(report, CitationReport)
    assert report.tier1_failed_integrity == 0
    assert report.node_verdicts.get("n1") in ("pass", "unverified")


def test_run_verify_routes_back_and_retries(tmp_path):
    """Node fails verify (integrity), gets re-executed, then passes verify."""
    from loop.models import VerifierResult, VerifierCheckOutcome

    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))

    invoker = FakeInvoker()
    # First execute: done
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done attempt 1",
    ))
    # Second execute (after verify routes back): done
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done attempt 2",
    ))

    # First verify: integrity failure → routes back to pending
    fail_co = VerifierCheckOutcome(
        check_id="c1", provenance="from_grounds", tier=1,
        passed=False, metric_value="", judgment="",
    )
    fail_vr = VerifierResult(
        node_id="n1", verdict="fail", confidence=0.2,
        check_outcomes=[fail_co], integrity_verdict="integrity_failure",
        summary="failed",
    )
    # Second verify: pass
    pass_vr = make_pass_verifier_result("n1")

    verifier = FakeVerifierInvoker()
    verifier.queue(fail_vr)
    verifier.queue(pass_vr)

    runner, _ = _make_runner(
        tmp_path, llm, invoker, verifier,
    )
    final_rs, report = runner.run("build with retries")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass

    assert report.node_verdicts.get("n1") == "pass"
```

- [ ] **Step 2: Run the new tests**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/test_runner.py -v
```

Expected: all 5 tests PASS (including the 3 updated existing tests and the 2 new ones).

- [ ] **Step 3: Run full test suite**

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/cowboy/warrant/loop
git add tests/test_runner.py
git commit -m "test(loop): update runner tests for Verify integration, add routing test"
```

---

## Final: Commit plan document

After all 8 tasks pass, the plan doc itself should be committed if it was not already:

```bash
cd /home/cowboy/warrant
git add docs/superpowers/plans/2026-05-24-warrant-verify-citationreport.md
git commit -m "docs: add Plan 3 implementation plan — Verify + CitationReport"
```

Then run the full suite one last time:

```bash
cd /home/cowboy/warrant/loop
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass.

Update `SESSION.md` to record Plan 3 completion and update HEAD.
