from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from librarian.store import Index
from agent import planstore

from .models import RunState, NodeStatus, Invoker, VerifierInvoker, VerifierResult, CitationReport
from . import runstore as runstore_mod
from .worktree import WorktreeManager
from .phases.orient import orient
from .phases.retrieve import retrieve
from .phases.plan import build_initial
from .phases.execute import execute
from .phases.verify import verify
from .citationreport import generate_citation_report

LLM = Callable[[str], str]


class WarrantRunner:
    def __init__(
        self,
        index: Index,
        embedder,
        reranker,
        llm: LLM,
        invoker: Invoker,
        verifier_invoker: VerifierInvoker,
        worktree_mgr: WorktreeManager,
        base_repo: Path,
        out_dir: Path,
        global_iteration_cap: int = 10,
        per_node_attempt_cap: int = 3,
        watchdog_timeout: float = 300.0,
        max_parallel: int = 3,
        max_principles: int = 15,
        verify_iteration_cap: int = 3,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._invoker = invoker
        self._verifier_invoker = verifier_invoker
        self._worktree_mgr = worktree_mgr
        self._base_repo = Path(base_repo)
        self._out_dir = Path(out_dir)
        self._cfg = dict(
            global_iteration_cap=global_iteration_cap,
            per_node_attempt_cap=per_node_attempt_cap,
            watchdog_timeout=watchdog_timeout,
            max_parallel=max_parallel,
        )
        self._max_principles = max_principles
        self._verify_iteration_cap = verify_iteration_cap

    def _execute_verify_loop(
        self,
        plan,
        run_state: RunState,
        principles,
    ) -> tuple[RunState, CitationReport]:
        from agent import planstore as _planstore
        all_verifier_results: dict[str, VerifierResult] = {}
        current_plan = plan

        for _ in range(self._verify_iteration_cap):
            run_state = execute(
                current_plan, run_state, principles,
                self._invoker, self._out_dir, **self._cfg,
            )
            run_state, new_vr = verify(
                current_plan, run_state, principles,
                self._verifier_invoker, self._out_dir,
                per_node_attempt_cap=self._cfg["per_node_attempt_cap"],
                watchdog_timeout=self._cfg["watchdog_timeout"],
            )
            all_verifier_results.update({r.node_id: r for r in new_vr})

            current_plan = _planstore.load_version(
                self._out_dir, run_state.plan_version
            )

            has_pending = any(
                ns.status == "pending"
                for ns in run_state.node_statuses.values()
            )
            if not has_pending:
                break

        report = generate_citation_report(
            current_plan, run_state, all_verifier_results
        )
        return run_state, report

    def run(self, direction: str) -> tuple[RunState, CitationReport]:
        run_id = uuid.uuid4().hex

        orient_result = orient(
            direction, self._index, self._llm,
            self._worktree_mgr, self._base_repo, run_id,
        )
        principles = retrieve(
            orient_result.retrieval_queries,
            self._index,
            self._embedder,
            self._reranker,
            orient_result.worktree_path,
            self._max_principles,
        )
        plan = build_initial(direction, principles, self._llm)
        planstore.save_plan(plan, self._out_dir)

        run_state = RunState(
            run_id=run_id,
            plan_id=plan.plan_id,
            plan_version=plan.version,
            worktree_path=orient_result.worktree_path,
            phase="execute",
            node_statuses={
                n.id: NodeStatus(node_id=n.id, status="pending")
                for n in plan.nodes
            },
            anchored_direction=orient_result.anchored_direction,
            anchored_honesty_constraint=orient_result.anchored_honesty_constraint,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        runstore_mod.save_run(run_state, self._out_dir)

        return self._execute_verify_loop(plan, run_state, principles)

    def resume(self, run_state: RunState) -> tuple[RunState, CitationReport]:
        from librarian.models import principle_from_dict
        from librarian.query import Result
        from agent import planstore as _planstore

        plan = _planstore.load_version(self._out_dir, run_state.plan_version)
        principles_file = (
            Path(run_state.worktree_path) / ".warrant" / "principles.json"
        )
        raw = json.loads(principles_file.read_text(encoding="utf-8"))
        principles = [
            Result(principle=principle_from_dict(d), citation=principle_from_dict(d).citation,
                   score=1.0, neighbors=[])
            for d in raw
        ]

        for ns in run_state.node_statuses.values():
            if ns.status == "in_flight":
                ns.status = "pending"

        runstore_mod.save_run(run_state, self._out_dir)

        return self._execute_verify_loop(plan, run_state, principles)
