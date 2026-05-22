from __future__ import annotations

import json
from pathlib import Path

from .plan import ApplicableCheck, Plan, PlanNode


def plan_to_dict(plan: Plan) -> dict:
    return {
        "plan_id": plan.plan_id,
        "task": plan.task,
        "version": plan.version,
        "nodes": [_node_to_dict(n) for n in plan.nodes],
    }


def _node_to_dict(node: PlanNode) -> dict:
    return {
        "id": node.id,
        "level": node.level,
        "decision": node.decision,
        "approach": node.approach,
        "grounds": list(node.grounds),
        "grounds_state": node.grounds_state,
        "grounds_note": node.grounds_note,
        "conflict_resolution": node.conflict_resolution,
        "applicable_checks": [
            {"check": c.check, "provenance": c.provenance}
            for c in node.applicable_checks
        ],
        "depends_on": list(node.depends_on),
        "amended_from": node.amended_from,
        "amended_reason": node.amended_reason,
        "children": list(node.children),
    }


def plan_from_dict(d: dict) -> Plan:
    return Plan(
        plan_id=d["plan_id"],
        task=d["task"],
        version=d["version"],
        nodes=tuple(_node_from_dict(n) for n in d["nodes"]),
    )


def _node_from_dict(d: dict) -> PlanNode:
    return PlanNode(
        id=d["id"],
        level=d["level"],
        decision=d["decision"],
        approach=d["approach"],
        grounds=tuple(d["grounds"]),
        grounds_state=d["grounds_state"],
        grounds_note=d.get("grounds_note", ""),
        conflict_resolution=d.get("conflict_resolution", ""),
        applicable_checks=tuple(
            ApplicableCheck(check=c["check"], provenance=c["provenance"])
            for c in d.get("applicable_checks", [])
        ),
        depends_on=tuple(d.get("depends_on", [])),
        amended_from=d.get("amended_from"),
        amended_reason=d.get("amended_reason"),
        children=tuple(d.get("children", [])),
    )


def save_plan(plan: Plan, out_dir) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    filename = out / f"plan.v{plan.version}.json"
    filename.write_text(json.dumps(plan_to_dict(plan), indent=2))


def load_version(out_dir, version: int) -> Plan:
    out = Path(out_dir)
    filename = out / f"plan.v{version}.json"
    if not filename.exists():
        raise FileNotFoundError(f"No plan version {version} at {out_dir}")
    return plan_from_dict(json.loads(filename.read_text()))


def load_latest(out_dir) -> Plan:
    out = Path(out_dir)
    candidates = list(out.glob("plan.v*.json"))
    if not candidates:
        raise FileNotFoundError(f"No plan files found in {out_dir}")

    def _version_num(p: Path) -> int:
        # extract the integer between "plan.v" and ".json"
        stem = p.stem  # e.g. "plan.v3"
        return int(stem.split(".v")[1])

    latest = max(candidates, key=_version_num)
    return plan_from_dict(json.loads(latest.read_text()))
