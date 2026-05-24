from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from librarian.store import Index
from agent import planstore

from .models import RunState, NodeStatus, Invoker
from . import runstore as runstore_mod
from .worktree import WorktreeManager
from .phases.orient import orient
from .phases.retrieve import retrieve
from .phases.plan import build_initial
from .phases.execute import execute

LLM = Callable[[str], str]


class WarrantRunner:
    def __init__(
        self,
        index: Index,
        embedder,
        reranker,
        llm: LLM,
        invoker: Invoker,
        worktree_mgr: WorktreeManager,
        base_repo: Path,
        out_dir: Path,
        global_iteration_cap: int = 10,
        per_node_attempt_cap: int = 3,
        watchdog_timeout: float = 300.0,
        max_parallel: int = 3,
        max_principles: int = 15,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._invoker = invoker
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

    def run(self, direction: str) -> RunState:
        run_id = uuid.uuid4().hex

        # Orient
        orient_result = orient(
            direction, self._index, self._llm,
            self._worktree_mgr, self._base_repo, run_id,
        )

        # Retrieve
        principles = retrieve(
            orient_result.retrieval_queries,
            self._index,
            self._embedder,
            self._reranker,
            orient_result.worktree_path,
            self._max_principles,
        )

        # Plan
        plan = build_initial(direction, principles, self._llm)
        planstore.save_plan(plan, self._out_dir)

        # Build initial RunState
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

        # Execute
        run_state = execute(
            plan, run_state, principles, self._invoker, self._out_dir,
            **self._cfg,
        )

        return run_state

    def resume(self, run_state: RunState) -> RunState:
        from librarian.models import principle_from_dict
        from librarian.query import Result

        plan = planstore.load_latest(self._out_dir)
        principles_file = (
            Path(run_state.worktree_path) / ".warrant" / "principles.json"
        )
        raw = json.loads(principles_file.read_text(encoding="utf-8"))
        principles = []
        for d in raw:
            p = principle_from_dict(d)
            principles.append(Result(principle=p, citation=p.citation, score=1.0, neighbors=[]))

        # Reset in_flight nodes back to pending
        for ns in run_state.node_statuses.values():
            if ns.status == "in_flight":
                ns.status = "pending"

        return execute(
            plan, run_state, principles, self._invoker, self._out_dir,
            **self._cfg,
        )
