import json
from pathlib import Path
from agent.plan import Plan
from loop.phases.plan import build_initial, expand_subtree
from agent import planstore, planops
from tests.fakes import FakeLLM, make_fixture_index
from librarian.query import Result


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
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    planstore.save_plan(plan, tmp_path)
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
    parent = planops.find_node(expanded, "n1")
    assert "n1_1" in parent.children


def test_expand_subtree_nonexistent_node_raises(tmp_path):
    import pytest
    index = make_fixture_index(2)
    results = _make_results(index)
    llm = FakeLLM()
    llm.queue(json.dumps([_node_json("n1", ["test-book:ch1:s1"])]))
    plan = build_initial("build", results, llm)
    planstore.save_plan(plan, tmp_path)
    llm.queue("[]")
    with pytest.raises(ValueError, match="n99"):
        expand_subtree(plan, "n99", results, llm, tmp_path)
