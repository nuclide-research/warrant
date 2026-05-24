from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import RunState, NodeStatus, ExecutorResult, CheckResult, NodeAmendment


def _executor_result_from_dict(d: dict | None) -> ExecutorResult | None:
    if d is None:
        return None
    return ExecutorResult(
        node_id=d["node_id"],
        status=d["status"],
        checks_run=[CheckResult(**c) for c in d["checks_run"]],
        principles_honored=d["principles_honored"],
        principles_violated=d["principles_violated"],
        amendments=[NodeAmendment(**a) for a in d["amendments"]],
        summary=d["summary"],
    )


def _node_status_from_dict(d: dict) -> NodeStatus:
    return NodeStatus(
        node_id=d["node_id"],
        status=d["status"],
        attempts=d["attempts"],
        last_result=_executor_result_from_dict(d.get("last_result")),
        pre_execution_sha=d.get("pre_execution_sha", ""),
    )


def run_to_dict(state: RunState) -> dict:
    d = asdict(state)
    return d


def run_from_dict(d: dict) -> RunState:
    node_statuses = {k: _node_status_from_dict(v) for k, v in d["node_statuses"].items()}
    return RunState(
        run_id=d["run_id"],
        plan_id=d["plan_id"],
        plan_version=d["plan_version"],
        worktree_path=d["worktree_path"],
        phase=d["phase"],
        node_statuses=node_statuses,
        anchored_direction=d["anchored_direction"],
        anchored_honesty_constraint=d["anchored_honesty_constraint"],
        iteration=d["iteration"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def save_run(state: RunState, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path = out_dir / f"run.v{state.iteration}.json"
    path.write_text(json.dumps(run_to_dict(state), indent=2), encoding="utf-8")
    return path


def load_run(path: Path) -> RunState:
    return run_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_latest_run(out_dir: Path) -> RunState:
    out_dir = Path(out_dir)
    files = sorted(
        out_dir.glob("run.v*.json"),
        key=lambda p: int(p.stem.split(".v")[1]),
    )
    if not files:
        raise FileNotFoundError(f"No run files found in {out_dir}")
    return load_run(files[-1])
