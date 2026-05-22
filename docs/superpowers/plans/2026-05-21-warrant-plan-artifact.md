# Warrant Plan Artifact — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the plan artifact module — the versioned decision-tree data structure that the Warrant agent loop builds, versions, amends, and persists. This is a self-contained Python package: data models with validation, JSON serialization, versioned on-disk persistence, and pure operations/queries. No LLM, no network, no Librarian dependency.

**Architecture:** Three modules under `agent/agent/`: `plan.py` (frozen dataclasses + `__post_init__` validation), `planstore.py` (round-trippable JSON serialization + `plan.v{N}.json` versioned persistence), `planops.py` (pure functions that take a `Plan` and return a new `Plan` or a query result). Tests live in `agent/tests/` and run with `cd /home/cowboy/warrant/agent && python -m pytest`.

**Tech Stack:** Python 3.11+, `pytest`. Zero runtime dependencies beyond the standard library.

---

## File Structure

```
agent/
  pyproject.toml              packaging + pytest config; no runtime deps
  agent/
    __init__.py               __version__ = "0.1.0"
    plan.py                   ApplicableCheck, PlanNode, Plan dataclasses + validation
    planstore.py              plan_to_dict, plan_from_dict, save_plan, load_version, load_latest
    planops.py                new_plan, add_node, amend_node, next_version, find_node, children, independent_siblings
  tests/
    test_smoke.py             package import + version check
    test_plan.py              dataclass construction + every validation branch
    test_planstore.py         round-trip + versioned save/load
    test_planops.py           all operations and queries
    test_integration.py       end-to-end: build plan -> version -> amend -> save -> load_latest -> assert
```

One responsibility per file. `plan.py` owns the schema. `planstore.py` owns I/O. `planops.py` owns mutation and query. No module imports another package's internals — the three modules form a clean stack: `planops` and `planstore` both import from `plan`; `planops` does not import `planstore` and vice versa.

---

## Task 1: Project scaffold

**Files:**
- Create: `agent/pyproject.toml`
- Create: `agent/agent/__init__.py`
- Create: `agent/tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import agent
    assert agent.__version__ == "0.1.0"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Create the package**

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`agent/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install and verify the test passes**

Run: `cd /home/cowboy/warrant/agent && pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/pyproject.toml agent/agent/__init__.py agent/tests/test_smoke.py
git commit -m "feat(agent): project scaffold"
```

---

## Task 2: Constants and ApplicableCheck

**Files:**
- Create: `agent/agent/plan.py` (partial — constants + `ApplicableCheck` only)
- Create: `agent/tests/test_plan.py` (partial — `ApplicableCheck` tests only)

- [ ] **Step 1: Write the failing test**

`tests/test_plan.py`:
```python
import pytest
from agent.plan import LEVELS, GROUNDS_STATES, PROVENANCE, ApplicableCheck


def test_constants_are_tuples_of_strings():
    assert isinstance(LEVELS, tuple)
    assert isinstance(GROUNDS_STATES, tuple)
    assert isinstance(PROVENANCE, tuple)
    assert "architectural" in LEVELS
    assert "structural" in LEVELS
    assert "implementation" in LEVELS
    assert "clean" in GROUNDS_STATES
    assert "conflicted" in GROUNDS_STATES
    assert "ungrounded" in GROUNDS_STATES
    assert "from_grounds" in PROVENANCE
    assert "from_topic" in PROVENANCE


def test_applicable_check_valid():
    c = ApplicableCheck(check="check-42", provenance="from_grounds")
    assert c.check == "check-42"
    assert c.provenance == "from_grounds"


def test_applicable_check_valid_from_topic():
    c = ApplicableCheck(check="check-99", provenance="from_topic")
    assert c.provenance == "from_topic"


def test_applicable_check_rejects_bad_provenance():
    with pytest.raises(ValueError, match="provenance"):
        ApplicableCheck(check="check-1", provenance="invented")


def test_applicable_check_is_frozen():
    c = ApplicableCheck(check="x", provenance="from_grounds")
    with pytest.raises(Exception):
        c.check = "y"  # type: ignore[misc]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.plan'`

- [ ] **Step 3: Write the implementation**

`agent/plan.py`:
```python
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
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/plan.py agent/tests/test_plan.py
git commit -m "feat(agent): constants and ApplicableCheck"
```

---

## Task 3: PlanNode with full validation

**Files:**
- Extend: `agent/agent/plan.py` (add `PlanNode`)
- Extend: `agent/tests/test_plan.py` (add `PlanNode` tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan.py`:
```python
from agent.plan import PlanNode


def _base_clean_node(**overrides) -> PlanNode:
    """Minimal valid PlanNode with grounds_state='clean'."""
    kwargs = dict(
        id="n1",
        level="architectural",
        decision="Use hexagonal architecture",
        approach="Ports and adapters; no framework in the domain layer",
        grounds=("principle-42",),
        grounds_state="clean",
    )
    kwargs.update(overrides)
    return PlanNode(**kwargs)


def test_plan_node_minimal_valid():
    node = _base_clean_node()
    assert node.id == "n1"
    assert node.level == "architectural"
    assert node.grounds == ("principle-42",)
    assert node.grounds_state == "clean"
    assert node.grounds_note == ""
    assert node.conflict_resolution == ""
    assert node.applicable_checks == ()
    assert node.depends_on == ()
    assert node.amended_from is None
    assert node.amended_reason is None
    assert node.children == ()


def test_plan_node_rejects_bad_level():
    with pytest.raises(ValueError, match="level"):
        _base_clean_node(level="tactical")


def test_plan_node_rejects_bad_grounds_state():
    with pytest.raises(ValueError, match="grounds_state"):
        _base_clean_node(grounds_state="pending")


def test_plan_node_clean_requires_grounds():
    with pytest.raises(ValueError, match="grounds"):
        _base_clean_node(grounds=())


def test_plan_node_conflicted_requires_conflict_resolution():
    with pytest.raises(ValueError, match="conflict_resolution"):
        PlanNode(
            id="n2",
            level="structural",
            decision="Choose DB",
            approach="PostgreSQL",
            grounds=("p1", "p2"),
            grounds_state="conflicted",
            # conflict_resolution intentionally omitted — defaults to ""
        )


def test_plan_node_conflicted_requires_at_least_two_grounds():
    with pytest.raises(ValueError, match="grounds"):
        PlanNode(
            id="n2",
            level="structural",
            decision="Choose DB",
            approach="PostgreSQL",
            grounds=("p1",),
            grounds_state="conflicted",
            conflict_resolution="p1 wins because it is more recent",
        )


def test_plan_node_conflicted_valid():
    node = PlanNode(
        id="n2",
        level="structural",
        decision="Choose DB",
        approach="PostgreSQL",
        grounds=("p1", "p2"),
        grounds_state="conflicted",
        conflict_resolution="p1 wins because it is more specific",
    )
    assert node.grounds_state == "conflicted"
    assert node.conflict_resolution == "p1 wins because it is more specific"


def test_plan_node_ungrounded_rejects_non_empty_grounds():
    with pytest.raises(ValueError, match="grounds"):
        PlanNode(
            id="n3",
            level="implementation",
            decision="Use stdlib only",
            approach="No third-party libraries",
            grounds=("some-principle",),
            grounds_state="ungrounded",
            grounds_note="Library is silent on stdlib-vs-third-party",
        )


def test_plan_node_ungrounded_requires_grounds_note():
    with pytest.raises(ValueError, match="grounds_note"):
        PlanNode(
            id="n3",
            level="implementation",
            decision="Use stdlib only",
            approach="No third-party libraries",
            grounds=(),
            grounds_state="ungrounded",
            # grounds_note intentionally omitted — defaults to ""
        )


def test_plan_node_ungrounded_valid():
    node = PlanNode(
        id="n3",
        level="implementation",
        decision="Use stdlib only",
        approach="No third-party libraries",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note="Library is silent on stdlib-vs-third-party for this context",
    )
    assert node.grounds == ()
    assert node.grounds_note != ""


def test_plan_node_is_frozen():
    node = _base_clean_node()
    with pytest.raises(Exception):
        node.id = "mutated"  # type: ignore[misc]


def test_plan_node_with_optional_fields():
    check = ApplicableCheck(check="c1", provenance="from_grounds")
    node = PlanNode(
        id="n4",
        level="implementation",
        decision="Validate input at boundary",
        approach="Pydantic models on all API entry points",
        grounds=("p5",),
        grounds_state="clean",
        applicable_checks=(check,),
        depends_on=("n1",),
        amended_from="n4-old",
        amended_reason="Original approach caused circular imports",
        children=("n5", "n6"),
    )
    assert node.applicable_checks == (check,)
    assert node.depends_on == ("n1",)
    assert node.amended_from == "n4-old"
    assert node.children == ("n5", "n6")
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: FAIL — `ImportError: cannot import name 'PlanNode' from 'agent.plan'`

- [ ] **Step 3: Write the implementation**

Extend `agent/plan.py` — append after `ApplicableCheck`:
```python
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
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: PASS (all tests including the 5 from Task 2)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/plan.py agent/tests/test_plan.py
git commit -m "feat(agent): PlanNode dataclass with full grounds-state validation"
```

---

## Task 4: Plan dataclass

**Files:**
- Extend: `agent/agent/plan.py` (add `Plan`)
- Extend: `agent/tests/test_plan.py` (add `Plan` tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan.py`:
```python
from agent.plan import Plan


def _make_node(node_id: str) -> PlanNode:
    return PlanNode(
        id=node_id,
        level="architectural",
        decision=f"Decision for {node_id}",
        approach=f"Approach for {node_id}",
        grounds=("p1",),
        grounds_state="clean",
    )


def test_plan_minimal_valid():
    plan = Plan(plan_id="abc123", task="Build a thing", version=1, nodes=())
    assert plan.plan_id == "abc123"
    assert plan.task == "Build a thing"
    assert plan.version == 1
    assert plan.nodes == ()


def test_plan_with_nodes():
    n1 = _make_node("n1")
    n2 = _make_node("n2")
    plan = Plan(plan_id="abc123", task="Build a thing", version=2, nodes=(n1, n2))
    assert len(plan.nodes) == 2
    assert plan.nodes[0].id == "n1"
    assert plan.nodes[1].id == "n2"


def test_plan_is_frozen():
    plan = Plan(plan_id="abc123", task="Build a thing", version=1, nodes=())
    with pytest.raises(Exception):
        plan.version = 2  # type: ignore[misc]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: FAIL — `ImportError: cannot import name 'Plan' from 'agent.plan'`

- [ ] **Step 3: Write the implementation**

Extend `agent/plan.py` — append after `PlanNode`:
```python
@dataclass(frozen=True)
class Plan:
    plan_id: str
    task: str
    version: int
    nodes: tuple[PlanNode, ...]
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_plan.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/plan.py agent/tests/test_plan.py
git commit -m "feat(agent): Plan dataclass"
```

---

## Task 5: JSON serialization — plan_to_dict / plan_from_dict

**Files:**
- Create: `agent/agent/planstore.py` (partial — serialization only)
- Create: `agent/tests/test_planstore.py` (partial — serialization tests only)

- [ ] **Step 1: Write the failing tests**

`tests/test_planstore.py`:
```python
import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planstore import plan_from_dict, plan_to_dict


def _make_plan() -> Plan:
    check = ApplicableCheck(check="c1", provenance="from_grounds")
    node = PlanNode(
        id="n1",
        level="architectural",
        decision="Use hexagonal architecture",
        approach="Ports and adapters",
        grounds=("p1", "p2"),
        grounds_state="clean",
        applicable_checks=(check,),
        depends_on=(),
        children=("n2",),
    )
    return Plan(
        plan_id="deadbeef",
        task="Build the thing",
        version=1,
        nodes=(node,),
    )


def test_plan_to_dict_produces_json_serialisable_dict():
    import json
    d = plan_to_dict(_make_plan())
    raw = json.dumps(d)  # must not raise
    assert isinstance(raw, str)
    assert "deadbeef" in raw


def test_plan_to_dict_tuples_become_lists():
    d = plan_to_dict(_make_plan())
    assert isinstance(d["nodes"], list)
    node_d = d["nodes"][0]
    assert isinstance(node_d["grounds"], list)
    assert isinstance(node_d["applicable_checks"], list)
    assert isinstance(node_d["depends_on"], list)
    assert isinstance(node_d["children"], list)


def test_plan_to_dict_applicable_check_is_nested_dict():
    d = plan_to_dict(_make_plan())
    check_d = d["nodes"][0]["applicable_checks"][0]
    assert isinstance(check_d, dict)
    assert check_d["check"] == "c1"
    assert check_d["provenance"] == "from_grounds"


def test_plan_round_trips_through_dict():
    original = _make_plan()
    restored = plan_from_dict(plan_to_dict(original))
    assert restored.plan_id == original.plan_id
    assert restored.task == original.task
    assert restored.version == original.version
    assert len(restored.nodes) == 1
    node = restored.nodes[0]
    assert node.id == "n1"
    assert node.level == "architectural"
    assert node.grounds == ("p1", "p2")
    assert node.grounds_state == "clean"
    assert node.children == ("n2",)
    assert len(node.applicable_checks) == 1
    assert node.applicable_checks[0].check == "c1"
    assert node.applicable_checks[0].provenance == "from_grounds"


def test_plan_round_trips_with_all_optional_fields():
    check = ApplicableCheck(check="c2", provenance="from_topic")
    node = PlanNode(
        id="n3",
        level="implementation",
        decision="Use stdlib json",
        approach="No third-party serializers",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note="Library is silent on serializer choice",
        applicable_checks=(check,),
        depends_on=("n1",),
        amended_from="n3-old",
        amended_reason="Old approach used orjson which added a dep",
        children=(),
    )
    plan = Plan(plan_id="ff00ff", task="Serialize things", version=3, nodes=(node,))
    restored = plan_from_dict(plan_to_dict(plan))
    n = restored.nodes[0]
    assert n.grounds_state == "ungrounded"
    assert n.grounds_note == "Library is silent on serializer choice"
    assert n.amended_from == "n3-old"
    assert n.amended_reason == "Old approach used orjson which added a dep"
    assert n.depends_on == ("n1",)
    assert n.applicable_checks[0].provenance == "from_topic"


def test_plan_round_trips_conflicted_node():
    node = PlanNode(
        id="n5",
        level="structural",
        decision="Choose caching strategy",
        approach="In-process LRU",
        grounds=("p10", "p11"),
        grounds_state="conflicted",
        conflict_resolution="p10 wins — it applies to read-heavy workloads specifically",
    )
    plan = Plan(plan_id="aabbcc", task="Cache things", version=1, nodes=(node,))
    restored = plan_from_dict(plan_to_dict(plan))
    n = restored.nodes[0]
    assert n.grounds_state == "conflicted"
    assert n.conflict_resolution.startswith("p10 wins")
    assert n.grounds == ("p10", "p11")
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planstore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.planstore'`

- [ ] **Step 3: Write the implementation**

`agent/planstore.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from .plan import ApplicableCheck, Plan, PlanNode


def plan_to_dict(plan: Plan) -> dict:
    return {
        "plan_id": plan.plan_id,
        "task": plan.task,
        "version": plan.version,
        "nodes": [_node_to_dict(n) for n in plan.nodes],
    }


def _node_to_dict(node: PlanNode) -> dict:
    return {
        "id": node.id,
        "level": node.level,
        "decision": node.decision,
        "approach": node.approach,
        "grounds": list(node.grounds),
        "grounds_state": node.grounds_state,
        "grounds_note": node.grounds_note,
        "conflict_resolution": node.conflict_resolution,
        "applicable_checks": [
            {"check": c.check, "provenance": c.provenance}
            for c in node.applicable_checks
        ],
        "depends_on": list(node.depends_on),
        "amended_from": node.amended_from,
        "amended_reason": node.amended_reason,
        "children": list(node.children),
    }


def plan_from_dict(d: dict) -> Plan:
    return Plan(
        plan_id=d["plan_id"],
        task=d["task"],
        version=d["version"],
        nodes=tuple(_node_from_dict(n) for n in d["nodes"]),
    )


def _node_from_dict(d: dict) -> PlanNode:
    return PlanNode(
        id=d["id"],
        level=d["level"],
        decision=d["decision"],
        approach=d["approach"],
        grounds=tuple(d["grounds"]),
        grounds_state=d["grounds_state"],
        grounds_note=d.get("grounds_note", ""),
        conflict_resolution=d.get("conflict_resolution", ""),
        applicable_checks=tuple(
            ApplicableCheck(check=c["check"], provenance=c["provenance"])
            for c in d.get("applicable_checks", [])
        ),
        depends_on=tuple(d.get("depends_on", [])),
        amended_from=d.get("amended_from"),
        amended_reason=d.get("amended_reason"),
        children=tuple(d.get("children", [])),
    )
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planstore.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/planstore.py agent/tests/test_planstore.py
git commit -m "feat(agent): plan_to_dict / plan_from_dict round-trip serialization"
```

---

## Task 6: Versioned on-disk persistence — save_plan / load_version / load_latest

**Files:**
- Extend: `agent/agent/planstore.py` (add save/load functions)
- Extend: `agent/tests/test_planstore.py` (add persistence tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planstore.py`:
```python
from agent.planstore import load_latest, load_version, save_plan


def _simple_plan(version: int = 1) -> Plan:
    node = PlanNode(
        id="n1",
        level="architectural",
        decision="Top-level decision",
        approach="Standard approach",
        grounds=("p1",),
        grounds_state="clean",
    )
    return Plan(plan_id="test-plan-001", task="Test task", version=version, nodes=(node,))


def test_save_plan_creates_versioned_file(tmp_path):
    plan = _simple_plan(version=1)
    save_plan(plan, tmp_path)
    expected = tmp_path / "plan.v1.json"
    assert expected.exists()


def test_save_plan_creates_out_dir_if_missing(tmp_path):
    target = tmp_path / "nested" / "plans"
    plan = _simple_plan(version=1)
    save_plan(plan, target)
    assert (target / "plan.v1.json").exists()


def test_save_plan_writes_valid_json(tmp_path):
    save_plan(_simple_plan(version=2), tmp_path)
    raw = (tmp_path / "plan.v2.json").read_text()
    parsed = json.loads(raw)
    assert parsed["version"] == 2
    assert parsed["plan_id"] == "test-plan-001"


def test_load_version_round_trips(tmp_path):
    original = _simple_plan(version=3)
    save_plan(original, tmp_path)
    loaded = load_version(tmp_path, 3)
    assert loaded.plan_id == original.plan_id
    assert loaded.version == 3
    assert loaded.nodes[0].id == "n1"


def test_load_version_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_version(tmp_path, 99)


def test_load_latest_returns_highest_version(tmp_path):
    save_plan(_simple_plan(version=1), tmp_path)
    save_plan(_simple_plan(version=3), tmp_path)
    save_plan(_simple_plan(version=2), tmp_path)
    latest = load_latest(tmp_path)
    assert latest.version == 3


def test_load_latest_raises_on_empty_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest(tmp_path)


def test_save_plan_file_is_human_readable(tmp_path):
    save_plan(_simple_plan(version=1), tmp_path)
    raw = (tmp_path / "plan.v1.json").read_text()
    # Indented JSON — must have newlines
    assert "\n" in raw
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planstore.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_plan' from 'agent.planstore'`

- [ ] **Step 3: Write the implementation**

Extend `agent/planstore.py` — append after `_node_from_dict`:
```python
def save_plan(plan: Plan, out_dir) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    filename = out / f"plan.v{plan.version}.json"
    filename.write_text(json.dumps(plan_to_dict(plan), indent=2))


def load_version(out_dir, version: int) -> Plan:
    out = Path(out_dir)
    filename = out / f"plan.v{version}.json"
    if not filename.exists():
        raise FileNotFoundError(f"No plan version {version} at {out_dir}")
    return plan_from_dict(json.loads(filename.read_text()))


def load_latest(out_dir) -> Plan:
    out = Path(out_dir)
    candidates = list(out.glob("plan.v*.json"))
    if not candidates:
        raise FileNotFoundError(f"No plan files found in {out_dir}")

    def _version_num(p: Path) -> int:
        # extract the integer between "plan.v" and ".json"
        stem = p.stem  # e.g. "plan.v3"
        return int(stem.split(".v")[1])

    latest = max(candidates, key=_version_num)
    return plan_from_dict(json.loads(latest.read_text()))
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planstore.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/planstore.py agent/tests/test_planstore.py
git commit -m "feat(agent): versioned on-disk persistence — save_plan, load_version, load_latest"
```

---

## Task 7: Mutation operations — new_plan / add_node / amend_node / next_version

**Files:**
- Create: `agent/agent/planops.py` (partial — mutation operations)
- Create: `agent/tests/test_planops.py` (partial — mutation tests)

- [ ] **Step 1: Write the failing tests**

`tests/test_planops.py`:
```python
import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planops import add_node, amend_node, new_plan, next_version


def _make_node(node_id: str, *, level: str = "architectural", **kwargs) -> PlanNode:
    defaults = dict(
        level=level,
        decision=f"Decision for {node_id}",
        approach=f"Approach for {node_id}",
        grounds=("p1",),
        grounds_state="clean",
    )
    defaults.update(kwargs)
    return PlanNode(id=node_id, **defaults)


# --- new_plan ---

def test_new_plan_produces_version_1():
    plan = new_plan("Build a REST API")
    assert plan.version == 1


def test_new_plan_has_empty_nodes():
    plan = new_plan("Build a REST API")
    assert plan.nodes == ()


def test_new_plan_has_unique_plan_id():
    p1 = new_plan("task A")
    p2 = new_plan("task A")
    assert p1.plan_id != p2.plan_id


def test_new_plan_plan_id_is_hex_string():
    plan = new_plan("task")
    # uuid4().hex is 32 hex chars
    assert len(plan.plan_id) == 32
    int(plan.plan_id, 16)  # raises ValueError if not hex


def test_new_plan_stores_task():
    plan = new_plan("Implement rate limiting")
    assert plan.task == "Implement rate limiting"


# --- add_node ---

def test_add_node_appends_to_plan():
    plan = new_plan("task")
    node = _make_node("n1")
    updated = add_node(plan, node)
    assert len(updated.nodes) == 1
    assert updated.nodes[0].id == "n1"


def test_add_node_does_not_mutate_original():
    plan = new_plan("task")
    node = _make_node("n1")
    add_node(plan, node)
    assert len(plan.nodes) == 0


def test_add_node_rejects_duplicate_id():
    plan = new_plan("task")
    node = _make_node("n1")
    plan = add_node(plan, node)
    with pytest.raises(ValueError, match="n1"):
        add_node(plan, node)


def test_add_node_preserves_existing_nodes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, _make_node("n2"))
    assert len(plan.nodes) == 2
    assert plan.nodes[0].id == "n1"
    assert plan.nodes[1].id == "n2"


# --- amend_node ---

def test_amend_node_replaces_node():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", approach="Old approach"))
    amended = amend_node(plan, "n1", "Better approach discovered",
                         approach="New approach")
    node = amended.nodes[0]
    assert node.approach == "New approach"


def test_amend_node_sets_amended_from_and_reason():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    amended = amend_node(plan, "n1", "Old approach caused issues",
                         approach="Revised approach")
    node = amended.nodes[0]
    assert node.amended_from == "n1"
    assert node.amended_reason == "Old approach caused issues"


def test_amend_node_does_not_mutate_original():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", approach="Original"))
    amend_node(plan, "n1", "reason", approach="Changed")
    assert plan.nodes[0].approach == "Original"


def test_amend_node_raises_on_missing_id():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    with pytest.raises(ValueError, match="n99"):
        amend_node(plan, "n99", "reason", approach="x")


def test_amend_node_preserves_other_nodes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, _make_node("n2"))
    amended = amend_node(plan, "n1", "reason", approach="New")
    assert amended.nodes[1].id == "n2"
    assert amended.nodes[1].approach == "Approach for n2"


def test_amend_node_can_change_level():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", level="architectural"))
    amended = amend_node(plan, "n1", "Re-scoped", level="structural")
    assert amended.nodes[0].level == "structural"


# --- next_version ---

def test_next_version_increments_by_one():
    plan = new_plan("task")
    assert plan.version == 1
    v2 = next_version(plan)
    assert v2.version == 2
    v3 = next_version(v2)
    assert v3.version == 3


def test_next_version_preserves_everything_else():
    plan = new_plan("task")
    node = _make_node("n1")
    plan = add_node(plan, node)
    v2 = next_version(plan)
    assert v2.plan_id == plan.plan_id
    assert v2.task == plan.task
    assert len(v2.nodes) == 1
    assert v2.nodes[0].id == "n1"


def test_next_version_does_not_mutate_original():
    plan = new_plan("task")
    next_version(plan)
    assert plan.version == 1
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.planops'`

- [ ] **Step 3: Write the implementation**

`agent/planops.py`:
```python
from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from .plan import Plan, PlanNode


def new_plan(task: str) -> Plan:
    return Plan(
        plan_id=uuid.uuid4().hex,
        task=task,
        version=1,
        nodes=(),
    )


def add_node(plan: Plan, node: PlanNode) -> Plan:
    existing_ids = {n.id for n in plan.nodes}
    if node.id in existing_ids:
        raise ValueError(f"Node id {node.id!r} already exists in the plan")
    return dataclasses.replace(plan, nodes=(*plan.nodes, node))


def amend_node(plan: Plan, node_id: str, reason: str, **changes: Any) -> Plan:
    found = False
    new_nodes = []
    for node in plan.nodes:
        if node.id == node_id:
            found = True
            amended = dataclasses.replace(
                node,
                amended_from=node_id,
                amended_reason=reason,
                **changes,
            )
            new_nodes.append(amended)
        else:
            new_nodes.append(node)
    if not found:
        raise ValueError(f"Node id {node_id!r} not found in the plan")
    return dataclasses.replace(plan, nodes=tuple(new_nodes))


def next_version(plan: Plan) -> Plan:
    return dataclasses.replace(plan, version=plan.version + 1)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planops.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/planops.py agent/tests/test_planops.py
git commit -m "feat(agent): mutation operations — new_plan, add_node, amend_node, next_version"
```

---

## Task 8: Query operations — find_node / children / independent_siblings

**Files:**
- Extend: `agent/agent/planops.py` (add query functions)
- Extend: `agent/tests/test_planops.py` (add query tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planops.py`:
```python
from agent.planops import children, find_node, independent_siblings


def _plan_with_nodes(*node_ids: str) -> Plan:
    """Build a plan containing one clean node per id."""
    plan = new_plan("query test")
    for nid in node_ids:
        plan = add_node(plan, _make_node(nid))
    return plan


# --- find_node ---

def test_find_node_returns_node_when_present():
    plan = _plan_with_nodes("n1", "n2", "n3")
    node = find_node(plan, "n2")
    assert node is not None
    assert node.id == "n2"


def test_find_node_returns_none_when_missing():
    plan = _plan_with_nodes("n1", "n2")
    assert find_node(plan, "n99") is None


def test_find_node_works_on_empty_plan():
    plan = new_plan("empty")
    assert find_node(plan, "n1") is None


# --- children ---

def test_children_resolves_ids_to_nodes():
    plan = _plan_with_nodes("n1", "n2", "n3")
    # manually build a parent node that references n2 and n3 as children
    parent = PlanNode(
        id="root",
        level="architectural",
        decision="root decision",
        approach="root approach",
        grounds=("p1",),
        grounds_state="clean",
        children=("n2", "n3"),
    )
    plan = add_node(plan, parent)
    result = children(plan, parent)
    assert len(result) == 2
    ids = {n.id for n in result}
    assert ids == {"n2", "n3"}


def test_children_skips_ids_not_in_plan():
    plan = _plan_with_nodes("n1", "n2")
    parent = PlanNode(
        id="root",
        level="architectural",
        decision="root",
        approach="root",
        grounds=("p1",),
        grounds_state="clean",
        children=("n1", "n99"),  # n99 does not exist
    )
    plan = add_node(plan, parent)
    result = children(plan, parent)
    assert len(result) == 1
    assert result[0].id == "n1"


def test_children_empty_when_no_children():
    plan = _plan_with_nodes("n1")
    node = find_node(plan, "n1")
    assert children(plan, node) == []


# --- independent_siblings ---

def test_independent_siblings_true_when_no_cross_depends():
    # n1 and n2 do not depend on each other
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is True


def test_independent_siblings_false_when_one_depends_on_other():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("n1",),  # n2 depends on n1
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is False


def test_independent_siblings_false_when_reverse_depends():
    # n1 depends on n2 — still not independent
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("n2",),
    ))
    plan = add_node(plan, _make_node("n2"))
    assert independent_siblings(plan, ["n1", "n2"]) is False


def test_independent_siblings_true_for_single_node():
    plan = _plan_with_nodes("n1")
    assert independent_siblings(plan, ["n1"]) is True


def test_independent_siblings_true_for_empty_list():
    plan = new_plan("task")
    assert independent_siblings(plan, []) is True


def test_independent_siblings_ignores_depends_on_outside_the_set():
    # n1 and n2 both depend on an external node "root" — not in the set
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is True
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planops.py -v`
Expected: FAIL — `ImportError: cannot import name 'find_node' from 'agent.planops'`

- [ ] **Step 3: Write the implementation**

Extend `agent/planops.py` — append after `next_version`:
```python
def find_node(plan: Plan, node_id: str) -> PlanNode | None:
    for node in plan.nodes:
        if node.id == node_id:
            return node
    return None


def children(plan: Plan, node: PlanNode) -> list[PlanNode]:
    result = []
    for child_id in node.children:
        child = find_node(plan, child_id)
        if child is not None:
            result.append(child)
    return result


def independent_siblings(plan: Plan, node_ids: list[str]) -> bool:
    id_set = set(node_ids)
    for node in plan.nodes:
        if node.id not in id_set:
            continue
        for dep in node.depends_on:
            if dep in id_set:
                return False
    return True
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_planops.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add agent/agent/planops.py agent/tests/test_planops.py
git commit -m "feat(agent): query operations — find_node, children, independent_siblings"
```

---

## Task 9: End-to-end integration test

**Files:**
- Create: `agent/tests/test_integration.py`

This task writes no new implementation code — it exercises the full stack (models -> operations -> serialization -> persistence) in a single scenario that mirrors real Warrant agent-loop usage: build a small plan, expand it, amend a node, version it, save it, load the latest, and assert the final state.

- [ ] **Step 1: Write the integration test**

`tests/test_integration.py`:
```python
"""
End-to-end: build a plan through the full lifecycle the agent loop drives.

Scenario:
  1. Agent starts a new plan for a task.
  2. It adds an architectural node (clean, grounded).
  3. It adds a structural node (conflicted — two principles disagree).
  4. It adds an implementation node (ungrounded — library silent).
  5. It adds a second implementation node that depends on the first.
  6. It amends the ungrounded node after discovering a principle.
  7. It bumps the version and saves.
  8. It loads the latest version from disk.
  9. Asserts the whole state is intact, including amendment metadata.
  10. Asserts that the two implementation nodes are NOT independent siblings.
  11. Asserts that architectural + structural nodes are NOT independent
      (the structural node depends on the architectural one).
"""
import json

from agent.plan import ApplicableCheck, PlanNode
from agent.planops import (
    add_node,
    amend_node,
    children,
    find_node,
    independent_siblings,
    new_plan,
    next_version,
)
from agent.planstore import load_latest, save_plan


def test_full_agent_loop_lifecycle(tmp_path):
    # 1. Start a new plan
    plan = new_plan("Implement a rate-limiting middleware")
    assert plan.version == 1
    assert plan.nodes == ()

    # 2. Architectural node — clean grounding
    arch_check = ApplicableCheck(check="rate-limit-header-present", provenance="from_grounds")
    arch_node = PlanNode(
        id="arch-1",
        level="architectural",
        decision="Rate limiting enforced at the API gateway layer",
        approach="Token-bucket algorithm, one bucket per client API key",
        grounds=("p-rate-limit-gateway", "p-token-bucket-fairness"),
        grounds_state="clean",
        applicable_checks=(arch_check,),
        children=("struct-1", "impl-1"),
    )
    plan = add_node(plan, arch_node)
    assert len(plan.nodes) == 1

    # 3. Structural node — conflicted grounding
    struct_node = PlanNode(
        id="struct-1",
        level="structural",
        decision="Store bucket state in Redis",
        approach="Redis INCR + EXPIRE; no in-process state",
        grounds=("p-distributed-state", "p-single-process-simplicity"),
        grounds_state="conflicted",
        conflict_resolution=(
            "p-distributed-state wins: horizontal scaling is a stated requirement "
            "and single-process state breaks under multiple gateway instances"
        ),
        depends_on=("arch-1",),
    )
    plan = add_node(plan, struct_node)

    # 4. Implementation node — ungrounded; library was silent
    impl_node_1 = PlanNode(
        id="impl-1",
        level="implementation",
        decision="Choose Redis client library",
        approach="Use redis-py; it is the de-facto Python client",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note=(
            "None of the indexed books address Python Redis client selection; "
            "redis-py is chosen by convention"
        ),
        depends_on=("struct-1",),
    )
    plan = add_node(plan, impl_node_1)

    # 5. Second implementation node — depends on impl-1
    impl_node_2 = PlanNode(
        id="impl-2",
        level="implementation",
        decision="Expose current bucket state via /metrics",
        approach="Prometheus counter per bucket, scraped every 15s",
        grounds=("p-observability-first",),
        grounds_state="clean",
        depends_on=("impl-1",),
    )
    plan = add_node(plan, impl_node_2)
    assert len(plan.nodes) == 4

    # 6. Amend impl-1: agent found a relevant principle mid-run
    plan = amend_node(
        plan,
        "impl-1",
        "Librarian found p-client-library-stability after initial planning",
        grounds=("p-client-library-stability",),
        grounds_state="clean",
        grounds_note="",
        approach="Use redis-py: grounded in p-client-library-stability (maintenance + adoption)",
    )
    amended = find_node(plan, "impl-1")
    assert amended is not None
    assert amended.grounds_state == "clean"
    assert amended.grounds == ("p-client-library-stability",)
    assert amended.amended_from == "impl-1"
    assert amended.amended_reason == "Librarian found p-client-library-stability after initial planning"
    assert amended.grounds_note == ""

    # 7. Bump version and save
    plan = next_version(plan)
    assert plan.version == 2
    save_plan(plan, tmp_path)
    assert (tmp_path / "plan.v2.json").exists()

    # Verify the JSON is well-formed and readable
    raw = json.loads((tmp_path / "plan.v2.json").read_text())
    assert raw["version"] == 2
    assert len(raw["nodes"]) == 4

    # 8. Load latest from disk
    loaded = load_latest(tmp_path)
    assert loaded.version == 2
    assert loaded.plan_id == plan.plan_id
    assert loaded.task == "Implement a rate-limiting middleware"
    assert len(loaded.nodes) == 4

    # 9. Full state integrity check on loaded plan
    loaded_arch = find_node(loaded, "arch-1")
    assert loaded_arch is not None
    assert loaded_arch.grounds_state == "clean"
    assert loaded_arch.applicable_checks[0].check == "rate-limit-header-present"
    assert loaded_arch.applicable_checks[0].provenance == "from_grounds"

    loaded_struct = find_node(loaded, "struct-1")
    assert loaded_struct is not None
    assert loaded_struct.grounds_state == "conflicted"
    assert loaded_struct.conflict_resolution.startswith("p-distributed-state wins")

    loaded_impl1 = find_node(loaded, "impl-1")
    assert loaded_impl1 is not None
    assert loaded_impl1.grounds_state == "clean"
    assert loaded_impl1.amended_from == "impl-1"
    assert loaded_impl1.amended_reason != ""

    loaded_impl2 = find_node(loaded, "impl-2")
    assert loaded_impl2 is not None
    assert loaded_impl2.depends_on == ("impl-1",)

    # 10. impl-1 and impl-2 are NOT independent siblings (impl-2 depends on impl-1)
    assert independent_siblings(loaded, ["impl-1", "impl-2"]) is False

    # 11. arch-1 and struct-1 are NOT independent: struct-1 depends on arch-1.
    assert independent_siblings(loaded, ["arch-1", "struct-1"]) is False

    # struct-1 and impl-2 — impl-2.depends_on = impl-1 (not in the set), so independent
    assert independent_siblings(loaded, ["struct-1", "impl-2"]) is True

    # 12. children() resolves arch-1's children references
    arch_children = children(loaded, loaded_arch)
    arch_child_ids = {n.id for n in arch_children}
    # arch-1.children = ("struct-1", "impl-1"); both exist in the plan
    assert arch_child_ids == {"struct-1", "impl-1"}
```

- [ ] **Step 2: Run it, verify it passes**

Run: `cd /home/cowboy/warrant/agent && python -m pytest tests/test_integration.py -v`
Expected: PASS. Tasks 1-8 implemented every module this test exercises, so it passes on the first run. A failure here is a real integration bug — diagnose it, do not skip it.

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

Run: `cd /home/cowboy/warrant/agent && python -m pytest -v`
Expected: PASS (all tests across all test files)

If the integration test itself fails on a logic assertion, diagnose the failure — do not skip it. The test scenario is constructed so every assertion should pass given correct implementations.

- [ ] **Step 4: Commit**

```bash
git add agent/tests/test_integration.py
git commit -m "test(agent): end-to-end integration — full plan lifecycle"
```

---

## Self-Review

**Spec coverage (Section 7 of the design):**

| Spec element | Covered | Notes |
|---|---|---|
| `LEVELS` tuple | Task 2 | `("architectural", "structural", "implementation")` |
| `GROUNDS_STATES` tuple | Task 2 | `("clean", "conflicted", "ungrounded")` |
| `PROVENANCE` tuple | Task 2 | `("from_grounds", "from_topic")` |
| `ApplicableCheck` frozen dataclass + provenance validation | Task 2 | |
| `PlanNode` frozen dataclass — all 13 fields | Task 3 | |
| `PlanNode` validation — `clean` requires grounds | Task 3 | |
| `PlanNode` validation — `conflicted` requires ≥2 grounds + conflict_resolution | Task 3 | |
| `PlanNode` validation — `ungrounded` requires empty grounds + grounds_note | Task 3 | |
| `Plan` frozen dataclass | Task 4 | |
| `plan_to_dict` / `plan_from_dict` round-trip | Task 5 | tuples→lists and back; nested ApplicableCheck |
| `save_plan` — writes `plan.v{N}.json` | Task 6 | creates dir, indented JSON |
| `load_version` — loads by version number | Task 6 | raises FileNotFoundError on miss |
| `load_latest` — loads highest-numbered version | Task 6 | raises FileNotFoundError on empty |
| `new_plan` — version 1, uuid4 hex plan_id, empty nodes | Task 7 | |
| `add_node` — append + duplicate-id guard | Task 7 | |
| `amend_node` — dataclasses.replace + amended_from/reason | Task 7 | |
| `next_version` — version + 1 | Task 7 | |
| `find_node` — returns PlanNode or None | Task 8 | |
| `children` — resolves ids, skips missing | Task 8 | |
| `independent_siblings` — cross-depends check | Task 8 | |
| End-to-end lifecycle (build → amend → version → save → load) | Task 9 | |

**Out of scope for this plan (confirmed):** agent loop, execution state, "executed/un-executed" node tracking, Librarian integration, retrieval, Executor/Verifier subagent contracts, the citation report, worktree management. All of those land in plans 2-4.

**Real code in every step:** confirmed. No step contains a placeholder, ellipsis, or `# ... implement here` comment. Every test and every implementation is complete and runnable.
