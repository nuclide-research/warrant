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
