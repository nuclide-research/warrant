from __future__ import annotations

from agent.plan import PlanNode, ApplicableCheck
from loop.materializer import materialize
from loop.verifier_materializer import materialize_verifier
from loop.models import RunState, NodeStatus, ExecutorResult


def _make_node(node_id: str = "n1") -> PlanNode:
    return PlanNode(
        id=node_id,
        level="implementation",
        decision="Add a cache layer",
        approach="Use an in-memory dict",
        grounds=[],
        grounds_state="ungrounded",
        grounds_note="library silent on this approach",
        applicable_checks=[],
        depends_on=[],
    )


def _make_run_state(worktree_path: str = "/tmp/wt") -> RunState:
    return RunState(
        run_id="r1",
        plan_id="p1",
        plan_version=1,
        worktree_path=worktree_path,
        phase="execute",
        node_statuses={"n1": NodeStatus(node_id="n1", status="pending")},
        anchored_direction="#DIRECTION: Add caching",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: Be honest",
    )


def test_materialize_includes_working_directory():
    node = _make_node()
    run_state = _make_run_state("/tmp/my_worktree")
    result = materialize(node, [], run_state, {"n1": node})
    assert "## Working directory" in result
    assert "/tmp/my_worktree" in result


def test_materialize_verifier_includes_working_directory(tmp_path):
    node = _make_node()
    run_state = _make_run_state(str(tmp_path))
    executor_result = ExecutorResult(
        node_id="n1",
        status="done",
        checks_run=[],
        principles_honored=[],
        principles_violated=[],
        amendments=[],
        summary="done",
    )
    result = materialize_verifier(
        node, [], run_state, executor_result, str(tmp_path), {"n1": node}
    )
    assert "## Working directory" in result
    assert str(tmp_path) in result
