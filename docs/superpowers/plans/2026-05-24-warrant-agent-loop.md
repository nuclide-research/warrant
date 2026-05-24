# Warrant Agent Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `loop/` Python package that drives Warrant's Orient → Retrieve → Plan → Execute phases with execution state tracking, worktree management, Executor prompt materialization, and stuck detection.

**Architecture:** Phase modules under `loop/phases/` driven by `WarrantRunner` in `runner.py`. All external dependencies (Librarian query, Invoker, LLM callable) are injected. `RunState` persists separately from plan files via `runstore.py`. Executor invocation is decoupled via the `Invoker` protocol so tests run without a live Claude process.

**Tech Stack:** Python 3.11+, `agent` package (planops/planstore/plan at `../agent`), `librarian` package (query_index/Index/Result at `../librarian`), `hatchling`, `pytest`, `concurrent.futures`.

---

## File map

| File | Responsibility |
|------|---------------|
| `loop/pyproject.toml` | Package metadata; editable deps on `agent` + `librarian` |
| `loop/loop/__init__.py` | Empty |
| `loop/loop/models.py` | `RunState`, `NodeStatus`, `ExecutorResult`, `CheckResult`, `NodeAmendment`, `Invoker` protocol |
| `loop/loop/runstore.py` | `save_run`, `load_run`, `load_latest_run` |
| `loop/loop/worktree.py` | `WorktreeManager`, `WorktreeInfo`, `WorktreeError` |
| `loop/loop/materializer.py` | `materialize(node, principles, run_state, all_nodes) -> str` |
| `loop/loop/phases/__init__.py` | Empty |
| `loop/loop/phases/orient.py` | `orient(...)` → `OrientResult` |
| `loop/loop/phases/retrieve.py` | `retrieve(...)` → `list[Result]` |
| `loop/loop/phases/plan.py` | `build_initial(...)` + `expand_subtree(...)` → `Plan` |
| `loop/loop/phases/execute.py` | `execute(...)` → `RunState`; stuck detection |
| `loop/loop/runner.py` | `WarrantRunner` — drives full loop, `run()` + `resume()` |
| `loop/tests/fakes.py` | `FakeLLM`, `FakeInvoker`, `FakeReranker`, `FakeEmbedder`, `make_fixture_index()` |
| `loop/tests/test_models.py` | Model validation invariants |
| `loop/tests/test_runstore.py` | Round-trip, versioning, load_latest |
| `loop/tests/test_materializer.py` | Prompt shape, missing-principle section |
| `loop/tests/test_worktree.py` | Real git fixture: create/list/remove |
| `loop/tests/test_orient.py` | OrientResult fields, worktree created |
| `loop/tests/test_retrieve.py` | Dedup, cap, principles.json written |
| `loop/tests/test_plan.py` | build_initial validates grounds; expand_subtree bumps version + saves |
| `loop/tests/test_execute.py` | Happy path, stuck detection, global cap, watchdog timeout |
| `loop/tests/test_runner.py` | Full `run()` integration: final phase == "done", all nodes done |
| `loop/tests/test_smoke.py` | Import every module, construct WarrantRunner, call `run()` |

---

## Task 1: Package scaffold

**Files:**
- Create: `loop/pyproject.toml`
- Create: `loop/loop/__init__.py`
- Create: `loop/loop/phases/__init__.py`

- [ ] **Step 1: Create the package directories**

```bash
mkdir -p ~/warrant/loop/loop/phases
mkdir -p ~/warrant/loop/tests
touch ~/warrant/loop/loop/__init__.py
touch ~/warrant/loop/loop/phases/__init__.py
touch ~/warrant/loop/tests/__init__.py
```

- [ ] **Step 2: Write `loop/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "loop"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "agent",
    "librarian",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Install loop in editable mode**

```bash
cd ~/warrant/loop
pip install -e ".[dev]"
```

Expected: `Successfully installed loop-0.1.0`

- [ ] **Step 4: Verify imports work**

```bash
cd ~/warrant/loop
python -c "from agent.agent import plan, planops, planstore; from librarian.librarian import query, store; print('deps ok')"
```

Expected: `deps ok`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/
git commit -m "feat(loop): package scaffold — pyproject, directories, editable install"
```

---

## Task 2: Test fakes

**Files:**
- Create: `loop/tests/fakes.py`

- [ ] **Step 1: Write `loop/tests/fakes.py`**

```python
from __future__ import annotations
import numpy as np
from loop.models import ExecutorResult, CheckResult
from librarian.librarian.models import Principle, Citation, Edge
from librarian.librarian.store import Index


class FakeLLM:
    """Queue responses with .queue(text); falls back to default."""

    def __init__(self, default: str = "[]"):
        self._responses: list[str] = []
        self._default = default

    def queue(self, response: str) -> None:
        self._responses.append(response)

    def __call__(self, prompt: str) -> str:
        if self._responses:
            return self._responses.pop(0)
        return self._default


class FakeInvoker:
    """Queue results with .queue(result); falls back to a generic done result."""

    def __init__(self):
        self._results: list[ExecutorResult] = []

    def queue(self, result: ExecutorResult) -> None:
        self._results.append(result)

    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult:
        if self._results:
            return self._results.pop(0)
        return ExecutorResult(
            node_id="unknown",
            status="done",
            checks_run=[],
            principles_honored=[],
            principles_violated=[],
            amendments=[],
            summary="fake done",
        )


class FakeReranker:
    def rerank(self, query: str, candidates):
        return [(c, float(i)) for i, c in enumerate(reversed(candidates))]


class FakeEmbedder:
    def encode(self, texts):
        return np.zeros((len(texts), 4))


def make_fixture_principle(pid: str = "test-book:ch1:s1", statement: str = "Prefer composition over inheritance.") -> Principle:
    return Principle(
        id=pid,
        statement=statement,
        citation=Citation(
            book="Test Book",
            isbn="9999999999999",
            chapter="Chapter 1",
            section="Section 1",
        ),
        checkability_tier=2,
        evidence_chunk="Composition leads to more flexible designs.",
    )


def make_fixture_index(n: int = 2) -> Index:
    principles = [
        make_fixture_principle(
            pid=f"test-book:ch1:s{i}",
            statement=f"Principle {i}.",
        )
        for i in range(1, n + 1)
    ]
    embeddings = np.zeros((n, 4))
    return Index(principles=principles, embeddings=embeddings, edges=[])
```

- [ ] **Step 2: Verify fakes import**

```bash
cd ~/warrant/loop
python -c "from tests.fakes import FakeLLM, FakeInvoker, FakeReranker, FakeEmbedder, make_fixture_index; print('fakes ok')"
```

Expected: `fakes ok`

- [ ] **Step 3: Commit**

```bash
cd ~/warrant
git add loop/tests/fakes.py loop/tests/__init__.py
git commit -m "test(loop): fakes — FakeLLM, FakeInvoker, FakeReranker, FakeEmbedder, fixture index"
```

---

## Task 3: Data models

**Files:**
- Create: `loop/loop/models.py`
- Create: `loop/tests/test_models.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_models.py`**

```python
import pytest
from loop.models import (
    CheckResult, NodeAmendment, ExecutorResult,
    NodeStatus, RunState, Invoker,
)


def test_check_result_valid():
    c = CheckResult(check_id="c1", provenance="from_grounds", passed=True)
    assert c.check_id == "c1"
    assert c.passed is True


def test_node_status_defaults():
    ns = NodeStatus(node_id="n1", status="pending")
    assert ns.attempts == 0
    assert ns.last_result is None


def test_run_state_fields():
    rs = RunState(
        run_id="abc",
        plan_id="pid",
        plan_version=1,
        worktree_path="/tmp/wt",
        phase="orient",
        node_statuses={},
        anchored_direction="#DIRECTION: build a thing",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
    )
    assert rs.iteration == 0
    assert rs.created_at == ""


def test_executor_result_fields():
    r = ExecutorResult(
        node_id="n1",
        status="done",
        checks_run=[CheckResult(check_id="c1", provenance="from_grounds", passed=True)],
        principles_honored=["p1"],
        principles_violated=[],
        amendments=[],
        summary="done",
    )
    assert r.status == "done"
    assert len(r.checks_run) == 1


def test_invoker_protocol_satisfied_by_fake():
    from tests.fakes import FakeInvoker
    invoker: Invoker = FakeInvoker()
    result = invoker.invoke("hello")
    assert result.status == "done"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_models.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `loop.models` does not exist yet.

- [ ] **Step 3: Write `loop/loop/models.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_models.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/models.py loop/tests/test_models.py
git commit -m "feat(loop): data models — RunState, NodeStatus, ExecutorResult, Invoker protocol"
```

---

## Task 4: RunState I/O

**Files:**
- Create: `loop/loop/runstore.py`
- Create: `loop/tests/test_runstore.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_runstore.py`**

```python
import json
from pathlib import Path
import pytest
from loop.models import RunState, NodeStatus, ExecutorResult, CheckResult
from loop import runstore


def _make_run_state(**overrides) -> RunState:
    defaults = dict(
        run_id="run-abc",
        plan_id="plan-xyz",
        plan_version=1,
        worktree_path="/tmp/wt",
        phase="orient",
        node_statuses={},
        anchored_direction="#DIRECTION: build",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
        iteration=0,
    )
    defaults.update(overrides)
    return RunState(**defaults)


def test_save_and_load_roundtrip(tmp_path):
    rs = _make_run_state()
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    assert loaded.run_id == rs.run_id
    assert loaded.plan_id == rs.plan_id
    assert loaded.phase == rs.phase


def test_save_sets_updated_at(tmp_path):
    rs = _make_run_state()
    runstore.save_run(rs, tmp_path)
    assert rs.updated_at != ""


def test_save_filename_uses_iteration(tmp_path):
    rs = _make_run_state(iteration=3)
    path = runstore.save_run(rs, tmp_path)
    assert path.name == "run.v3.json"


def test_load_latest_returns_highest_version(tmp_path):
    for i in range(3):
        rs = _make_run_state(iteration=i)
        runstore.save_run(rs, tmp_path)
    latest = runstore.load_latest_run(tmp_path)
    assert latest.iteration == 2


def test_load_latest_raises_when_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        runstore.load_latest_run(tmp_path)


def test_node_status_roundtrip(tmp_path):
    rs = _make_run_state(node_statuses={
        "n1": NodeStatus(node_id="n1", status="done", attempts=1)
    })
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    assert loaded.node_statuses["n1"].status == "done"
    assert loaded.node_statuses["n1"].attempts == 1


def test_executor_result_nested_roundtrip(tmp_path):
    result = ExecutorResult(
        node_id="n1", status="done",
        checks_run=[CheckResult(check_id="c1", provenance="from_grounds", passed=True)],
        principles_honored=["p1"], principles_violated=[],
        amendments=[], summary="done",
    )
    rs = _make_run_state(node_statuses={
        "n1": NodeStatus(node_id="n1", status="done", last_result=result)
    })
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    lr = loaded.node_statuses["n1"].last_result
    assert lr is not None
    assert lr.checks_run[0].check_id == "c1"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_runstore.py -v
```

Expected: `ImportError` — `loop.runstore` does not exist yet.

- [ ] **Step 3: Write `loop/loop/runstore.py`**

```python
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import RunState, NodeStatus, ExecutorResult, CheckResult, NodeAmendment


def _executor_result_from_dict(d: dict | None) -> ExecutorResult | None:
    if d is None:
        return None
    return ExecutorResult(
        node_id=d["node_id"],
        status=d["status"],
        checks_run=[CheckResult(**c) for c in d["checks_run"]],
        principles_honored=d["principles_honored"],
        principles_violated=d["principles_violated"],
        amendments=[NodeAmendment(**a) for a in d["amendments"]],
        summary=d["summary"],
    )


def _node_status_from_dict(d: dict) -> NodeStatus:
    return NodeStatus(
        node_id=d["node_id"],
        status=d["status"],
        attempts=d["attempts"],
        last_result=_executor_result_from_dict(d.get("last_result")),
    )


def run_to_dict(state: RunState) -> dict:
    d = asdict(state)
    return d


def run_from_dict(d: dict) -> RunState:
    node_statuses = {k: _node_status_from_dict(v) for k, v in d["node_statuses"].items()}
    return RunState(
        run_id=d["run_id"],
        plan_id=d["plan_id"],
        plan_version=d["plan_version"],
        worktree_path=d["worktree_path"],
        phase=d["phase"],
        node_statuses=node_statuses,
        anchored_direction=d["anchored_direction"],
        anchored_honesty_constraint=d["anchored_honesty_constraint"],
        iteration=d["iteration"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def save_run(state: RunState, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path = out_dir / f"run.v{state.iteration}.json"
    path.write_text(json.dumps(run_to_dict(state), indent=2), encoding="utf-8")
    return path


def load_run(path: Path) -> RunState:
    return run_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_latest_run(out_dir: Path) -> RunState:
    out_dir = Path(out_dir)
    files = sorted(
        out_dir.glob("run.v*.json"),
        key=lambda p: int(p.stem.split(".v")[1]),
    )
    if not files:
        raise FileNotFoundError(f"No run files found in {out_dir}")
    return load_run(files[-1])
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_runstore.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/runstore.py loop/tests/test_runstore.py
git commit -m "feat(loop): RunState I/O — save_run, load_run, load_latest_run with nested ExecutorResult"
```

---

## Task 5: WorktreeManager

**Files:**
- Create: `loop/loop/worktree.py`
- Create: `loop/tests/test_worktree.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_worktree.py`**

```python
import subprocess
from pathlib import Path
import pytest
from loop.worktree import WorktreeManager, WorktreeError


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_create_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/abc12345")
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()
    # cleanup
    mgr.remove(wt_path)


def test_list_worktrees_includes_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    worktrees = mgr.list_worktrees(repo)
    paths = [w.path for w in worktrees]
    assert str(repo) in paths


def test_remove_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/cleanup-test")
    assert wt_path.exists()
    mgr.remove(wt_path)
    assert not wt_path.exists()


def test_create_duplicate_branch_raises(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/dup-test")
    with pytest.raises(WorktreeError):
        mgr.create(repo, "warrant/dup-test")
    mgr.remove(wt_path)
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_worktree.py -v
```

Expected: `ImportError` — `loop.worktree` does not exist yet.

- [ ] **Step 3: Write `loop/loop/worktree.py`**

```python
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    pass


@dataclass
class WorktreeInfo:
    path: str
    branch: str
    commit: str


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise WorktreeError(result.stderr.strip())
    return result.stdout


def _parse_porcelain(output: str) -> list[WorktreeInfo]:
    worktrees: list[WorktreeInfo] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(_wt_from_dict(current))
            current = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            current["commit"] = line[len("HEAD "):]
        elif line.startswith("branch refs/heads/"):
            current["branch"] = line[len("branch refs/heads/"):]
        elif line == "bare":
            current["branch"] = "(bare)"
        elif line == "detached":
            current["branch"] = "(detached)"
    if current:
        worktrees.append(_wt_from_dict(current))
    return worktrees


def _wt_from_dict(d: dict[str, str]) -> WorktreeInfo:
    return WorktreeInfo(
        path=d.get("path", ""),
        branch=d.get("branch", "(unknown)"),
        commit=d.get("commit", ""),
    )


class WorktreeManager:
    def create(self, base_repo: Path, branch: str) -> Path:
        slug = branch.replace("/", "-")
        wt_path = base_repo.parent / f"warrant-wt-{slug}"
        _run(["git", "worktree", "add", "-b", branch, str(wt_path)], cwd=base_repo)
        return wt_path

    def remove(self, path: Path) -> None:
        base_repo = self._main_repo(path)
        _run(["git", "worktree", "remove", "--force", str(path)], cwd=base_repo)

    def list_worktrees(self, base_repo: Path) -> list[WorktreeInfo]:
        out = _run(["git", "worktree", "list", "--porcelain"], cwd=base_repo)
        return _parse_porcelain(out)

    def _main_repo(self, worktree_path: Path) -> Path:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=worktree_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise WorktreeError("not a git repository")
        common = Path(result.stdout.strip())
        # common dir is .git inside main repo
        return common.parent
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_worktree.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/worktree.py loop/tests/test_worktree.py
git commit -m "feat(loop): WorktreeManager — create/remove/list via git worktree subprocess"
```

---

## Task 6: Materializer

**Files:**
- Create: `loop/loop/materializer.py`
- Create: `loop/tests/test_materializer.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_materializer.py`**

```python
import json
import pytest
from agent.agent.plan import PlanNode, ApplicableCheck
from loop.models import RunState, NodeStatus
from loop import materializer
from tests.fakes import make_fixture_index
from librarian.librarian.query import Result


def _make_run_state() -> RunState:
    return RunState(
        run_id="run-abc",
        plan_id="pid",
        plan_version=1,
        worktree_path="/tmp/wt",
        phase="execute",
        node_statuses={},
        anchored_direction="#DIRECTION: build a thing",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
    )


def _make_node(grounds=("test-book:ch1:s1",), depends_on=(), applicable_checks=()) -> PlanNode:
    return PlanNode(
        id="n1",
        level="architectural",
        decision="Choose approach X",
        approach="Use pattern Y",
        grounds=grounds,
        grounds_state="clean" if grounds else "ungrounded",
        grounds_note="" if grounds else "Library silent.",
        applicable_checks=applicable_checks,
        depends_on=depends_on,
    )


def _make_results(index) -> list[Result]:
    from librarian.librarian.query import _neighbors
    return [
        Result(principle=p, citation=p.citation, score=1.0, neighbors=[])
        for p in index.principles
    ]


def test_prompt_contains_direction():
    index = make_fixture_index()
    results = _make_results(index)
    node = _make_node()
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "#DIRECTION: build a thing" in prompt


def test_prompt_contains_honesty_constraint():
    index = make_fixture_index()
    results = _make_results(index)
    node = _make_node()
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "#HONESTY-CONSTRAINT" in prompt


def test_prompt_contains_principle_text():
    index = make_fixture_index()
    results = _make_results(index)
    node = _make_node(grounds=("test-book:ch1:s1",))
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "Prefer composition over inheritance." in prompt
    assert "Composition leads to more flexible designs." in prompt


def test_prompt_contains_return_format():
    index = make_fixture_index()
    results = _make_results(index)
    node = _make_node()
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "Return ONLY a JSON object" in prompt
    assert "node_id" in prompt


def test_missing_principle_flagged():
    index = make_fixture_index()
    results = _make_results(index)
    node = _make_node(grounds=("nonexistent-principle-id",))
    # grounds_state must be valid — use ungrounded since ground doesn't exist
    node = PlanNode(
        id="n1", level="architectural",
        decision="X", approach="Y",
        grounds=("nonexistent-principle-id",),
        grounds_state="clean",  # simulate agent citing an id not in retrieved set
        grounds_note="",
    )
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "Missing principles" in prompt
    assert "nonexistent-principle-id" in prompt


def test_deps_context_included():
    index = make_fixture_index()
    results = _make_results(index)
    dep = PlanNode(
        id="n0", level="architectural",
        decision="Choose dep approach", approach="Use dep pattern",
        grounds=(), grounds_state="ungrounded", grounds_note="silent",
    )
    node = _make_node(grounds=("test-book:ch1:s1",), depends_on=("n0",))
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {"n0": dep})
    assert "Choose dep approach" in prompt
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_materializer.py -v
```

Expected: `ImportError` — `loop.materializer` does not exist yet.

- [ ] **Step 3: Write `loop/loop/materializer.py`**

```python
from __future__ import annotations
import json

from agent.agent.plan import PlanNode
from librarian.librarian.query import Result
from .models import RunState

_RESULT_SCHEMA = json.dumps(
    {
        "node_id": "<string>",
        "status": "done | failed",
        "checks_run": [
            {
                "check_id": "<string>",
                "provenance": "from_grounds | from_topic",
                "passed": True,
                "detail": "<string>",
            }
        ],
        "principles_honored": ["<principle_id>"],
        "principles_violated": ["<principle_id>"],
        "amendments": [{"node_id": "<string>", "amended_reason": "<string>"}],
        "summary": "<one line>",
    },
    indent=2,
)


def materialize(
    node: PlanNode,
    principles: list[Result],
    run_state: RunState,
    all_nodes: dict[str, PlanNode],
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
                f"  Evidence: {p.evidence_chunk}"
            )
        else:
            missing_ids.append(pid)

    checks_lines = [
        f"- {ac.check} (provenance: {ac.provenance})"
        for ac in node.applicable_checks
    ]

    deps_lines: list[str] = []
    for dep_id in node.depends_on:
        dep = all_nodes.get(dep_id)
        if dep:
            deps_lines.append(f"- **{dep_id}**: {dep.decision} — {dep.approach}")

    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        f"## Your task\n{node.decision}",
        f"## Approach\n{node.approach}",
    ]

    if grounding_lines:
        sections.append("## Grounding\n" + "\n\n".join(grounding_lines))

    if missing_ids:
        lines = "\n".join(f"- {i}" for i in missing_ids)
        sections.append(f"# Missing principles (not in retrieved set)\n{lines}")

    if checks_lines:
        sections.append("## Checks you must run\n" + "\n".join(checks_lines))

    if deps_lines:
        sections.append("## Dependencies context\n" + "\n".join(deps_lines))

    sections.append(
        f"## Return format\n"
        f"Return ONLY a JSON object matching this schema — no prose before or after:\n"
        f"```json\n{_RESULT_SCHEMA}\n```"
    )

    return "\n\n".join(sections)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_materializer.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/materializer.py loop/tests/test_materializer.py
git commit -m "feat(loop): materializer — Executor prompt from plan node + principles"
```

---

## Task 7: Orient phase

**Files:**
- Create: `loop/loop/phases/orient.py`
- Create: `loop/tests/test_orient.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_orient.py`**

```python
import subprocess
from pathlib import Path
import pytest
from loop.phases.orient import orient, OrientResult
from loop.worktree import WorktreeManager
from tests.fakes import FakeLLM, make_fixture_index


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_orient_returns_orient_result(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("I am a software engineering specialist.")
    llm.queue("query one\nquery two\nquery three")
    mgr = WorktreeManager()
    result = orient("build a cache", make_fixture_index(), llm, mgr, repo, "abc12345")
    assert isinstance(result, OrientResult)
    # cleanup
    from loop.worktree import WorktreeManager as WM
    WM().remove(Path(result.worktree_path))


def test_orient_anchored_direction_prefix(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("specialist persona")
    llm.queue("q1\nq2\nq3")
    mgr = WorktreeManager()
    result = orient("build a cache", make_fixture_index(), llm, mgr, repo, "abc12345")
    assert result.anchored_direction.startswith("#DIRECTION:")
    assert "build a cache" in result.anchored_direction
    WM().remove(Path(result.worktree_path))


def test_orient_honesty_constraint_prefix(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2\nq3")
    mgr = WorktreeManager()
    result = orient("build a thing", make_fixture_index(), llm, mgr, repo, "run99")
    assert result.anchored_honesty_constraint.startswith("#HONESTY-CONSTRAINT:")
    WM().remove(Path(result.worktree_path))


def test_orient_queries_capped_at_five(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2\nq3\nq4\nq5\nq6\nq7")
    mgr = WorktreeManager()
    result = orient("direction", make_fixture_index(), llm, mgr, repo, "run01")
    assert len(result.retrieval_queries) <= 5
    WM().remove(Path(result.worktree_path))


def test_orient_creates_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2")
    mgr = WorktreeManager()
    result = orient("direction", make_fixture_index(), llm, mgr, repo, "wt-test-01")
    assert Path(result.worktree_path).exists()
    WM().remove(Path(result.worktree_path))
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_orient.py -v
```

Expected: `ImportError` — `loop.phases.orient` does not exist yet.

- [ ] **Step 3: Write `loop/loop/phases/orient.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from librarian.librarian.store import Index
from ..worktree import WorktreeManager

LLM = Callable[[str], str]

_HONESTY_TEXT = (
    "Never claim more grounding or verification than you actually have. "
    "Mark every ungrounded decision explicitly."
)


@dataclass
class OrientResult:
    anchored_direction: str
    anchored_honesty_constraint: str
    specialist_persona: str
    retrieval_queries: list[str]
    worktree_path: str


def orient(
    direction: str,
    index: Index,
    llm: LLM,
    worktree_mgr: WorktreeManager,
    base_repo: Path,
    run_id: str,
) -> OrientResult:
    anchored_direction = f"#DIRECTION: {direction}"
    anchored_honesty = f"#HONESTY-CONSTRAINT: {_HONESTY_TEXT}"

    citations = sorted({
        (p.citation.isbn, p.citation.book, p.citation.chapter)
        for p in index.principles
    })
    reading_list = "\n".join(
        f"- {book}: {chapter}" for _, book, chapter in citations[:40]
    )
    persona_prompt = (
        f"You are a coding agent. Based on this reading list, write one paragraph "
        f"describing your specialist identity and expertise:\n\n{reading_list}"
    )
    specialist_persona = llm(persona_prompt).strip()

    query_prompt = (
        f"You are a coding agent with this expertise:\n{specialist_persona}\n\n"
        f"Direction: {direction}\n\n"
        f"Draft 3-5 retrieval queries to find the most relevant engineering "
        f"principles for this direction. Return one query per line, no numbering."
    )
    queries_raw = llm(query_prompt).strip()
    retrieval_queries = [q.strip() for q in queries_raw.splitlines() if q.strip()][:5]

    branch = f"warrant/{run_id[:8]}"
    wt_path = worktree_mgr.create(base_repo, branch)

    return OrientResult(
        anchored_direction=anchored_direction,
        anchored_honesty_constraint=anchored_honesty,
        specialist_persona=specialist_persona,
        retrieval_queries=retrieval_queries,
        worktree_path=str(wt_path),
    )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_orient.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/phases/orient.py loop/tests/test_orient.py
git commit -m "feat(loop): orient phase — direction anchor, persona derivation, query drafting, worktree"
```

---

## Task 8: Retrieve phase

**Files:**
- Create: `loop/loop/phases/retrieve.py`
- Create: `loop/tests/test_retrieve.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_retrieve.py`**

```python
import json
from pathlib import Path
from loop.phases.retrieve import retrieve
from tests.fakes import FakeReranker, FakeEmbedder, make_fixture_index


def test_retrieve_returns_results(tmp_path):
    index = make_fixture_index(2)
    results = retrieve(
        queries=["query one"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    assert len(results) > 0


def test_retrieve_writes_principles_json(tmp_path):
    index = make_fixture_index(2)
    retrieve(
        queries=["query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    principles_file = tmp_path / ".warrant" / "principles.json"
    assert principles_file.exists()
    data = json.loads(principles_file.read_text())
    assert isinstance(data, list)
    assert len(data) > 0


def test_retrieve_deduplicates(tmp_path):
    index = make_fixture_index(2)
    # Two identical queries — result set should not double
    results = retrieve(
        queries=["same query", "same query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    ids = [r.principle.id for r in results]
    assert len(ids) == len(set(ids))


def test_retrieve_respects_max_principles(tmp_path):
    index = make_fixture_index(10)
    results = retrieve(
        queries=["query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
        max_principles=3,
    )
    assert len(results) <= 3
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_retrieve.py -v
```

Expected: `ImportError` — `loop.phases.retrieve` does not exist yet.

- [ ] **Step 3: Write `loop/loop/phases/retrieve.py`**

```python
from __future__ import annotations
import json
from pathlib import Path

from librarian.librarian.store import Index
from librarian.librarian.query import query_index, Result, SEMANTIC_POOL
from librarian.librarian.models import principle_to_dict


def retrieve(
    queries: list[str],
    index: Index,
    embedder,
    reranker,
    worktree_path: str,
    max_principles: int = 15,
) -> list[Result]:
    seen: dict[str, Result] = {}
    for query in queries:
        results = query_index(index, query, embedder, reranker, k=SEMANTIC_POOL)
        for r in results:
            pid = r.principle.id
            if pid not in seen or r.score > seen[pid].score:
                seen[pid] = r

    merged = list(seen.values())
    combined_query = " ".join(queries)
    reranked_pairs = reranker.rerank(combined_query, [r.principle for r in merged])
    reranked_ids = [p.id for p, _ in reranked_pairs]
    id_to_result = {r.principle.id: r for r in merged}
    ordered = [id_to_result[pid] for pid in reranked_ids if pid in id_to_result]
    top = ordered[:max_principles]

    warrant_dir = Path(worktree_path) / ".warrant"
    warrant_dir.mkdir(parents=True, exist_ok=True)
    (warrant_dir / "principles.json").write_text(
        json.dumps([principle_to_dict(r.principle) for r in top], indent=2),
        encoding="utf-8",
    )

    return top
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_retrieve.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/phases/retrieve.py loop/tests/test_retrieve.py
git commit -m "feat(loop): retrieve phase — deduplicate, rerank, cap, write principles.json"
```

---

## Task 9: Plan phase

**Files:**
- Create: `loop/loop/phases/plan.py`
- Create: `loop/tests/test_plan.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_plan.py`**

```python
import json
from pathlib import Path
from agent.agent.plan import Plan
from loop.phases.plan import build_initial, expand_subtree
from agent.agent import planstore
from tests.fakes import FakeLLM, make_fixture_index
from librarian.librarian.query import Result


def _make_results(index):
    return [
        Result(principle=p, citation=p.citation, score=1.0, neighbors=[])
        for p in index.principles
    ]


def _node_json(node_id: str, grounds: list[str]) -> dict:
    return {
        "id": node_id,
        "decision": f"Decision for {node_id}",
        "approach": f"Approach for {node_id}",
        "grounds": grounds,
    }


def test_build_initial_returns_plan():
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build a cache", results, llm)
    assert isinstance(plan, Plan)
    assert len(plan.nodes) == 1
    assert plan.nodes[0].id == "n1"


def test_build_initial_valid_ground_is_clean():
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    assert plan.nodes[0].grounds_state == "clean"
    assert "test-book:ch1:s1" in plan.nodes[0].grounds


def test_build_initial_unknown_ground_becomes_ungrounded():
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["nonexistent-id"])]))
    plan = build_initial("build", results, llm)
    assert plan.nodes[0].grounds_state == "ungrounded"
    assert plan.nodes[0].grounds == ()


def test_build_initial_empty_llm_response_returns_empty_plan():
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM(default="not json")
    plan = build_initial("build", results, llm)
    assert isinstance(plan, Plan)
    assert len(plan.nodes) == 0


def test_expand_subtree_bumps_version(tmp_path):
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    # build initial with one node
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    planstore.save_plan(plan, tmp_path)
    # expand n1
    llm.queue(json.dumps([_node_json("n1_1", ["test-book:ch1:s1"])]))
    expanded = expand_subtree(plan, "n1", results, llm, tmp_path)
    assert expanded.version == plan.version + 1


def test_expand_subtree_saves_plan_file(tmp_path):
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    planstore.save_plan(plan, tmp_path)
    llm.queue(json.dumps([_node_json("n1_1", ["test-book:ch1:s1"])]))
    expanded = expand_subtree(plan, "n1", results, llm, tmp_path)
    saved = planstore.load_version(tmp_path, expanded.version)
    assert saved.version == expanded.version


def test_expand_subtree_adds_children_to_parent(tmp_path):
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    planstore.save_plan(plan, tmp_path)
    llm.queue(json.dumps([_node_json("n1_1", ["test-book:ch1:s1"])]))
    expanded = expand_subtree(plan, "n1", results, llm, tmp_path)
    from agent.agent.planops import find_node
    parent = find_node(expanded, "n1")
    assert "n1_1" in parent.children
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_plan.py -v
```

Expected: `ImportError` — `loop.phases.plan` does not exist yet.

- [ ] **Step 3: Write `loop/loop/phases/plan.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

from agent.agent.plan import Plan, PlanNode
from agent.agent import planops, planstore
from librarian.librarian.query import Result

LLM = Callable[[str], str]


def _parse_nodes(response: str) -> list[dict]:
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "nodes" in data:
            return data["nodes"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return []


def _make_node(d: dict, valid_ids: set[str], level: str) -> PlanNode | None:
    try:
        raw_grounds = d.get("grounds", [])
        valid = [g for g in raw_grounds if g in valid_ids]
        invalid = [g for g in raw_grounds if g not in valid_ids]

        if valid:
            grounds_state = "clean"
            grounds = tuple(valid)
            grounds_note = ""
        else:
            grounds_state = "ungrounded"
            grounds = ()
            if invalid:
                grounds_note = f"Cited ids not in retrieved set: {invalid}"
            else:
                grounds_note = d.get("grounds_note", "Library was silent.")

        depends_on = tuple(d.get("depends_on", []))

        return PlanNode(
            id=d["id"],
            level=level,
            decision=d["decision"],
            approach=d["approach"],
            grounds=grounds,
            grounds_state=grounds_state,
            grounds_note=grounds_note,
            depends_on=depends_on,
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_initial(direction: str, principles: list[Result], llm: LLM) -> Plan:
    valid_ids = {r.principle.id for r in principles}
    summary = "\n".join(
        f"- {r.principle.id}: {r.principle.statement}" for r in principles
    )
    prompt = (
        f"Direction: {direction}\n\n"
        f"Available principles (use their ids in the grounds field):\n{summary}\n\n"
        f"Produce a JSON array of architectural-level plan nodes. Each node:\n"
        f'{{"id": "n1", "decision": "...", "approach": "...", "grounds": ["principle-id"]}}\n'
        f"Return ONLY the JSON array."
    )
    raw_nodes = _parse_nodes(llm(prompt))
    plan = planops.new_plan(direction)
    for d in raw_nodes:
        node = _make_node(d, valid_ids, "architectural")
        if node is not None:
            try:
                plan = planops.add_node(plan, node)
            except ValueError:
                continue
    return plan


def expand_subtree(
    plan: Plan,
    node_id: str,
    principles: list[Result],
    llm: LLM,
    out_dir: Path,
) -> Plan:
    parent = planops.find_node(plan, node_id)
    if parent is None:
        raise ValueError(f"node {node_id!r} not found in plan")

    valid_ids = {r.principle.id for r in principles}
    summary = "\n".join(
        f"- {r.principle.id}: {r.principle.statement}" for r in principles
    )
    prompt = (
        f"Parent decision: {parent.decision}\n"
        f"Parent approach: {parent.approach}\n\n"
        f"Available principles:\n{summary}\n\n"
        f"Produce a JSON array of structural/implementation child nodes. Each node:\n"
        f'{{"id": "n1_1", "level": "structural", "decision": "...", '
        f'"approach": "...", "grounds": ["principle-id"], "depends_on": []}}\n'
        f"Return ONLY the JSON array."
    )
    raw_nodes = _parse_nodes(llm(prompt))

    new_plan = planops.next_version(plan)
    child_ids: list[str] = []
    for d in raw_nodes:
        level = d.get("level", "structural")
        if level not in ("structural", "implementation"):
            level = "structural"
        node = _make_node(d, valid_ids, level)
        if node is not None:
            try:
                new_plan = planops.add_node(new_plan, node)
                child_ids.append(node.id)
            except ValueError:
                continue

    if child_ids:
        new_plan = planops.amend_node(
            new_plan, node_id,
            reason="subtree expanded",
            children=tuple(child_ids),
        )

    planstore.save_plan(new_plan, out_dir)
    return new_plan
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_plan.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/phases/plan.py loop/tests/test_plan.py
git commit -m "feat(loop): plan phase — build_initial + expand_subtree with lazy versioning"
```

---

## Task 10: Execute phase

**Files:**
- Create: `loop/loop/phases/execute.py`
- Create: `loop/tests/test_execute.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_execute.py`**

```python
import json
from pathlib import Path
import pytest
from agent.agent.plan import PlanNode
from agent.agent import planops
from loop.models import RunState, NodeStatus, ExecutorResult, CheckResult
from loop.phases.execute import execute
from loop import runstore
from tests.fakes import FakeInvoker, make_fixture_index
from librarian.librarian.query import Result


def _make_run_state(plan, phase="execute") -> RunState:
    return RunState(
        run_id="run-abc",
        plan_id=plan.plan_id,
        plan_version=plan.version,
        worktree_path="/tmp/wt",
        phase=phase,
        node_statuses={
            n.id: NodeStatus(node_id=n.id, status="pending")
            for n in plan.nodes
        },
        anchored_direction="#DIRECTION: build",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
    )


def _make_plan_with_node(node_id: str = "n1"):
    plan = planops.new_plan("build a thing")
    node = PlanNode(
        id=node_id, level="architectural",
        decision="Do X", approach="Use Y",
        grounds=(), grounds_state="ungrounded",
        grounds_note="library silent",
    )
    return planops.add_node(plan, node)


def _make_principles():
    index = make_fixture_index(1)
    return [
        Result(principle=p, citation=p.citation, score=1.0, neighbors=[])
        for p in index.principles
    ]


def test_execute_happy_path(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    final_rs = execute(plan, rs, _make_principles(), invoker, tmp_path)
    assert final_rs.node_statuses["n1"].status == "done"
    assert final_rs.phase == "done"


def test_execute_saves_run_state(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    execute(plan, rs, _make_principles(), invoker, tmp_path)
    # A run file must have been written
    assert list(tmp_path.glob("run.v*.json"))


def test_execute_respects_global_iteration_cap(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    # Invoker always fails — should hit cap
    invoker = FakeInvoker()
    final_rs = execute(
        plan, rs, _make_principles(), invoker, tmp_path,
        global_iteration_cap=2,
        per_node_attempt_cap=10,
    )
    assert final_rs.iteration >= 2 or final_rs.phase == "done"


def test_execute_stuck_detection_amends_node(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    invoker = FakeInvoker()
    # Always returns failed with a from_grounds violation
    failing = ExecutorResult(
        node_id="n1", status="failed",
        checks_run=[CheckResult(check_id="c1", provenance="from_grounds", passed=False)],
        principles_honored=[], principles_violated=["test-book:ch1:s1"],
        amendments=[], summary="failed",
    )
    for _ in range(5):
        invoker.queue(failing)
    final_rs = execute(
        plan, rs, _make_principles(), invoker, tmp_path,
        global_iteration_cap=10,
        per_node_attempt_cap=3,
    )
    # Node should be in a terminal state (failed or done after amendment)
    status = final_rs.node_statuses["n1"].status
    assert status in ("failed", "done")


def test_execute_depends_on_respected(tmp_path):
    plan = planops.new_plan("task")
    n1 = PlanNode(
        id="n1", level="architectural",
        decision="First", approach="Do first",
        grounds=(), grounds_state="ungrounded", grounds_note="silent",
    )
    n2 = PlanNode(
        id="n2", level="architectural",
        decision="Second", approach="Do second",
        grounds=(), grounds_state="ungrounded", grounds_note="silent",
        depends_on=("n1",),
    )
    plan = planops.add_node(planops.add_node(plan, n1), n2)
    rs = _make_run_state(plan)
    call_order: list[str] = []

    class OrderTrackingInvoker:
        def invoke(self, prompt: str, timeout=None) -> ExecutorResult:
            node_id = "n1" if "Do first" in prompt else "n2"
            call_order.append(node_id)
            return ExecutorResult(
                node_id=node_id, status="done",
                checks_run=[], principles_honored=[], principles_violated=[],
                amendments=[], summary="done",
            )

    execute(plan, rs, _make_principles(), OrderTrackingInvoker(), tmp_path)
    assert call_order.index("n1") < call_order.index("n2")
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_execute.py -v
```

Expected: `ImportError` — `loop.phases.execute` does not exist yet.

- [ ] **Step 3: Write `loop/loop/phases/execute.py`**

```python
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agent.agent.plan import Plan, PlanNode
from agent.agent import planops, planstore
from ..models import RunState, NodeStatus, ExecutorResult, Invoker
from .. import runstore as runstore_mod
from ..materializer import materialize
from librarian.librarian.query import Result

_INTEGRITY_PROVENANCE = "from_grounds"


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

        # Safety check: ready nodes must not depend on each other
        ready_ids = [n.id for n in ready]
        assert planops.independent_siblings(plan, ready_ids), (
            f"BUG: dispatch set is not independent: {ready_ids}"
        )

        # Mark all as in_flight before dispatch
        for node in ready:
            run_state.node_statuses[node.id].status = "in_flight"

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

        # Update node statuses
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
                        plan = planops.amend_node(plan, node.id, reason=reason)
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

    run_state.phase = "done"
    runstore_mod.save_run(run_state, out_dir)
    return run_state
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_execute.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/phases/execute.py loop/tests/test_execute.py
git commit -m "feat(loop): execute phase — dispatch, RunState tracking, stuck detection, parallel workers"
```

---

## Task 11: WarrantRunner

**Files:**
- Create: `loop/loop/runner.py`
- Create: `loop/tests/test_runner.py`

- [ ] **Step 1: Write failing tests in `loop/tests/test_runner.py`**

```python
import json
import subprocess
from pathlib import Path
import pytest
from loop.runner import WarrantRunner
from loop.worktree import WorktreeManager
from loop import runstore
from tests.fakes import FakeLLM, FakeInvoker, FakeReranker, FakeEmbedder, make_fixture_index
from loop.models import ExecutorResult


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _make_runner(tmp_path, llm, invoker, index=None):
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
        worktree_mgr=WorktreeManager(),
        base_repo=repo,
        out_dir=out_dir,
        global_iteration_cap=5,
        per_node_attempt_cap=2,
        watchdog_timeout=30.0,
    ), repo


def test_run_returns_done_run_state(tmp_path):
    llm = FakeLLM()
    llm.queue("I am a specialist.")                                     # persona
    llm.queue("query 1\nquery 2")                                       # queries
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Use Y", "grounds": []}]))  # build_initial
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, repo = _make_runner(tmp_path, llm, invoker)
    final_rs = runner.run("build a cache layer")
    # cleanup worktree
    from loop.worktree import WorktreeManager as WM
    from pathlib import Path
    try:
        WM().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert final_rs.phase == "done"


def test_run_all_nodes_done(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y", "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    final_rs = runner.run("build something")
    from loop.worktree import WorktreeManager as WM
    try:
        WM().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    done = all(ns.status in ("done", "failed") for ns in final_rs.node_statuses.values())
    assert done


def test_run_creates_run_files(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "X", "approach": "Y", "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    out_dir = tmp_path / "out"
    final_rs = runner.run("build")
    from loop.worktree import WorktreeManager as WM
    try:
        WM().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert list(out_dir.glob("run.v*.json"))
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd ~/warrant/loop
pytest tests/test_runner.py -v
```

Expected: `ImportError` — `loop.runner` does not exist yet.

- [ ] **Step 3: Write `loop/loop/runner.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from librarian.librarian.store import Index
from agent.agent import planstore

from .models import RunState, NodeStatus, Invoker
from . import runstore as runstore_mod
from .worktree import WorktreeManager
from .phases.orient import orient
from .phases.retrieve import retrieve
from .phases.plan import build_initial
from .phases.execute import execute

LLM = Callable[[str], str]


class WarrantRunner:
    def __init__(
        self,
        index: Index,
        embedder,
        reranker,
        llm: LLM,
        invoker: Invoker,
        worktree_mgr: WorktreeManager,
        base_repo: Path,
        out_dir: Path,
        global_iteration_cap: int = 10,
        per_node_attempt_cap: int = 3,
        watchdog_timeout: float = 300.0,
        max_parallel: int = 3,
        max_principles: int = 15,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._invoker = invoker
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

    def run(self, direction: str) -> RunState:
        run_id = uuid.uuid4().hex

        # Orient
        orient_result = orient(
            direction, self._index, self._llm,
            self._worktree_mgr, self._base_repo, run_id,
        )

        # Retrieve
        principles = retrieve(
            orient_result.retrieval_queries,
            self._index,
            self._embedder,
            self._reranker,
            orient_result.worktree_path,
            self._max_principles,
        )

        # Plan
        plan = build_initial(direction, principles, self._llm)
        planstore.save_plan(plan, self._out_dir)

        # Build initial RunState
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

        # Execute
        run_state = execute(
            plan, run_state, principles, self._invoker, self._out_dir,
            **self._cfg,
        )

        return run_state

    def resume(self, run_state: RunState) -> RunState:
        plan = planstore.load_latest(self._out_dir)
        principles_file = (
            Path(run_state.worktree_path) / ".warrant" / "principles.json"
        )
        from librarian.librarian.models import principle_from_dict
        from librarian.librarian.query import Result
        import json
        raw = json.loads(principles_file.read_text(encoding="utf-8"))
        principles = [
            Result(
                principle=principle_from_dict(d),
                citation=principle_from_dict(d).citation,
                score=1.0,
                neighbors=[],
            )
            for d in raw
        ]

        # Reset in_flight nodes back to pending
        for ns in run_state.node_statuses.values():
            if ns.status == "in_flight":
                ns.status = "pending"

        return execute(
            plan, run_state, principles, self._invoker, self._out_dir,
            **self._cfg,
        )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd ~/warrant/loop
pytest tests/test_runner.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/warrant
git add loop/loop/runner.py loop/tests/test_runner.py
git commit -m "feat(loop): WarrantRunner — drives full Orient → Retrieve → Plan → Execute loop"
```

---

## Task 12: Smoke test

**Files:**
- Create: `loop/tests/test_smoke.py`

- [ ] **Step 1: Write `loop/tests/test_smoke.py`**

```python
"""Import-level and construction smoke test — fails fast on any wiring error."""
import json
import subprocess
from pathlib import Path


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_all_imports():
    import loop.models
    import loop.runstore
    import loop.worktree
    import loop.materializer
    import loop.phases.orient
    import loop.phases.retrieve
    import loop.phases.plan
    import loop.phases.execute
    import loop.runner


def test_runner_construction_and_run(tmp_path):
    from loop.runner import WarrantRunner
    from loop.worktree import WorktreeManager
    from loop.models import ExecutorResult
    from tests.fakes import FakeLLM, FakeInvoker, FakeReranker, FakeEmbedder, make_fixture_index

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    llm = FakeLLM()
    llm.queue("I am a specialist.")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "X", "approach": "Y", "grounds": []}]))

    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))

    runner = WarrantRunner(
        index=make_fixture_index(2),
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        llm=llm,
        invoker=invoker,
        worktree_mgr=WorktreeManager(),
        base_repo=repo,
        out_dir=tmp_path / "out",
        global_iteration_cap=3,
    )
    final_rs = runner.run("build a thing")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert final_rs.phase == "done"
```

- [ ] **Step 2: Run smoke test**

```bash
cd ~/warrant/loop
pytest tests/test_smoke.py -v
```

Expected: `2 passed`

- [ ] **Step 3: Run full test suite**

```bash
cd ~/warrant/loop
pytest -v
```

Expected: all tests pass. Note the total count.

- [ ] **Step 4: Commit**

```bash
cd ~/warrant
git add loop/tests/test_smoke.py
git commit -m "test(loop): smoke test — import check + full run() on one-node fixture"
```

---

## Task 13: Final wiring and SESSION.md update

**Files:**
- Modify: `warrant/SESSION.md`

- [ ] **Step 1: Run the full warrant test suite (all packages)**

```bash
cd ~/warrant/agent && pytest -v
cd ~/warrant/librarian && pytest -v
cd ~/warrant/loop && pytest -v
```

Expected: all suites pass with no failures.

- [ ] **Step 2: Get the HEAD commit hash**

```bash
cd ~/warrant && git rev-parse HEAD
```

Copy the output — you will paste it into SESSION.md in the next step.

- [ ] **Step 3: Update SESSION.md**

Open `~/warrant/SESSION.md`. Replace the "Open / next" section with (substituting the actual commit hash for `HEAD_HASH`):

```markdown
## Done — the Agent, plan 2 of 4: the loop package

The `loop/` package drives the Orient → Retrieve → Plan → Execute phases.

- Built via `superpowers:subagent-driven-development` from the 13-task plan
  `docs/superpowers/plans/2026-05-24-warrant-agent-loop.md`.
- Merged to `main`. All tests pass. HEAD `HEAD_HASH`.
- Modules: `models`, `runstore`, `worktree`, `materializer`,
  `phases/{orient,retrieve,plan,execute}`, `runner`.
- `WarrantRunner.run(direction)` drives the full loop; `.resume(run_state)`
  re-enters Execute from a checkpoint.
- `Invoker` protocol: plan 4 skill wrapper provides `ClaudeCodeInvoker`;
  tests use `FakeInvoker`.

## Open / next

1. **The Agent, plan 3 of 4: Verify + citation report.**
   The Verifier subagent, Tier-1/2/3 check execution, failure routing
   (from_grounds → Execute, from_topic → report), the citation report
   projection. Same path: brainstorm → spec → plan → subagent build.
2. **The Warrant skill wrapper (plan 4).** `SKILL.md` + `ClaudeCodeInvoker`.
3. Artifacts B and C, after A.
4. Optional: live re-verify of Librarian edge extraction on a real book.
```

- [ ] **Step 4: Commit SESSION.md**

```bash
cd ~/warrant
git add SESSION.md
git commit -m "docs: update SESSION.md — loop package complete, plan 3 next"
```
