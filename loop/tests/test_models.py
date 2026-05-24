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
