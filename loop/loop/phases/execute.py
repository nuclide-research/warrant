from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agent.plan import Plan, PlanNode
from agent import planops, planstore
from ..models import RunState, NodeStatus, ExecutorResult, Invoker
from .. import runstore as runstore_mod
from ..materializer import materialize
from librarian.query import Result

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

        ready_ids = [n.id for n in ready]
        assert planops.independent_siblings(plan, ready_ids), (
            f"BUG: dispatch set is not independent: {ready_ids}"
        )

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

        run_state.iteration += 1
        runstore_mod.save_run(run_state, out_dir)

    if _all_done(run_state):
        run_state.phase = "done"
    else:
        run_state.phase = "exhausted"
    runstore_mod.save_run(run_state, out_dir)
    return run_state
