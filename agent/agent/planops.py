from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from .plan import Plan, PlanNode


def new_plan(task: str) -> Plan:
    return Plan(
        plan_id=uuid.uuid4().hex,
        task=task,
        version=1,
        nodes=(),
    )


def add_node(plan: Plan, node: PlanNode) -> Plan:
    existing_ids = {n.id for n in plan.nodes}
    if node.id in existing_ids:
        raise ValueError(f"Node id {node.id!r} already exists in the plan")
    return dataclasses.replace(plan, nodes=(*plan.nodes, node))


def amend_node(plan: Plan, node_id: str, reason: str, **changes: Any) -> Plan:
    forbidden = {"id", "amended_from", "amended_reason"} & changes.keys()
    if forbidden:
        raise ValueError(
            f"amend_node manages these fields; they may not be passed as changes: {sorted(forbidden)}"
        )
    found = False
    new_nodes = []
    for node in plan.nodes:
        if node.id == node_id:
            found = True
            amended = dataclasses.replace(
                node,
                amended_from=node_id,
                amended_reason=reason,
                **changes,
            )
            new_nodes.append(amended)
        else:
            new_nodes.append(node)
    if not found:
        raise ValueError(f"Node id {node_id!r} not found in the plan")
    return dataclasses.replace(plan, nodes=tuple(new_nodes))


def next_version(plan: Plan) -> Plan:
    return dataclasses.replace(plan, version=plan.version + 1)


def find_node(plan: Plan, node_id: str) -> PlanNode | None:
    for node in plan.nodes:
        if node.id == node_id:
            return node
    return None


def children(plan: Plan, node: PlanNode) -> list[PlanNode]:
    result = []
    for child_id in node.children:
        child = find_node(plan, child_id)
        if child is not None:
            result.append(child)
    return result


def independent_siblings(plan: Plan, node_ids: list[str]) -> bool:
    id_set = set(node_ids)
    for node in plan.nodes:
        if node.id not in id_set:
            continue
        for dep in node.depends_on:
            if dep in id_set:
                return False
    return True
