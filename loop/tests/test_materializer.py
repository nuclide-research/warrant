import json
import pytest
from agent.plan import PlanNode, ApplicableCheck
from loop.models import RunState, NodeStatus
from loop import materializer
from tests.fakes import make_fixture_index
from librarian.query import Result


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
    # make_fixture_index generates statement="Principle 1." for s1
    assert "Principle 1." in prompt
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
    node = PlanNode(
        id="n1", level="architectural",
        decision="X", approach="Y",
        grounds=("nonexistent-principle-id",),
        grounds_state="clean",
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


def test_checks_included():
    index = make_fixture_index()
    results = _make_results(index)
    check = ApplicableCheck(check="Verify no circular deps", provenance="from_grounds")
    node = _make_node(grounds=("test-book:ch1:s1",), applicable_checks=(check,))
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "Verify no circular deps" in prompt
    assert "from_grounds" in prompt


def test_ungrounded_node_flagged():
    index = make_fixture_index()
    results = _make_results(index)
    node = PlanNode(
        id="n1", level="architectural",
        decision="X", approach="Y",
        grounds=(), grounds_state="ungrounded", grounds_note="Library silent on this topic.",
    )
    rs = _make_run_state()
    prompt = materializer.materialize(node, results, rs, {})
    assert "ungrounded" in prompt
    assert "Library silent on this topic." in prompt
