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
