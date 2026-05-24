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
