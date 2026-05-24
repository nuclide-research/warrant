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
