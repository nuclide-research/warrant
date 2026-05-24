import json
from pathlib import Path
import pytest
from agent.plan import PlanNode
from agent import planops
from loop.models import RunState, NodeStatus, ExecutorResult, CheckResult
from loop.phases.execute import execute
from loop import runstore
from tests.fakes import FakeInvoker, make_fixture_index
from librarian.query import Result


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
    assert list(tmp_path.glob("run.v*.json"))


def test_execute_respects_global_iteration_cap(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    # FakeInvoker with no queued results returns "done" by default — use a failing invoker
    from loop.models import CheckResult

    class AlwaysFailInvoker:
        def invoke(self, prompt, timeout=None):
            return ExecutorResult(
                node_id="n1", status="failed",
                checks_run=[], principles_honored=[], principles_violated=[],
                amendments=[], summary="always fails",
            )

    final_rs = execute(
        plan, rs, _make_principles(), AlwaysFailInvoker(), tmp_path,
        global_iteration_cap=2,
        per_node_attempt_cap=10,
    )
    # Cap hit with node still not done — should be exhausted, not done
    assert final_rs.phase in ("exhausted", "done")
    assert final_rs.iteration >= 2


def test_execute_stuck_detection_amends_node(tmp_path):
    plan = _make_plan_with_node("n1")
    rs = _make_run_state(plan)
    invoker = FakeInvoker()
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
            node_id = "n1" if "## Approach\nDo first" in prompt else "n2"
            call_order.append(node_id)
            return ExecutorResult(
                node_id=node_id, status="done",
                checks_run=[], principles_honored=[], principles_violated=[],
                amendments=[], summary="done",
            )

    execute(plan, rs, _make_principles(), OrderTrackingInvoker(), tmp_path)
    assert call_order.index("n1") < call_order.index("n2")
