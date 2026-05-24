from __future__ import annotations
import dataclasses
import json
from pathlib import Path
from typing import Callable

from agent.plan import Plan, PlanNode
from agent import planops, planstore
from librarian.query import Result

LLM = Callable[[str], str]


def _parse_nodes(response: str) -> list[dict]:
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "nodes" in data:
            return data["nodes"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return []


def _make_node(d: dict, valid_ids: set[str], level: str) -> PlanNode | None:
    try:
        raw_grounds = d.get("grounds", [])
        valid = [g for g in raw_grounds if g in valid_ids]
        invalid = [g for g in raw_grounds if g not in valid_ids]

        if valid:
            grounds_state = "clean"
            grounds = tuple(valid)
            grounds_note = ""
        else:
            grounds_state = "ungrounded"
            grounds = ()
            if invalid:
                grounds_note = f"Cited ids not in retrieved set: {invalid}"
            else:
                grounds_note = d.get("grounds_note", "Library was silent.")

        depends_on = tuple(d.get("depends_on", []))

        return PlanNode(
            id=d["id"],
            level=level,
            decision=d["decision"],
            approach=d["approach"],
            grounds=grounds,
            grounds_state=grounds_state,
            grounds_note=grounds_note,
            depends_on=depends_on,
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_initial(direction: str, principles: list[Result], llm: LLM) -> Plan:
    valid_ids = {r.principle.id for r in principles}
    summary = "\n".join(
        f"- {r.principle.id}: {r.principle.statement}" for r in principles
    )
    prompt = (
        f"Direction: {direction}\n\n"
        f"Available principles (use their ids in the grounds field):\n{summary}\n\n"
        f"Produce a JSON array of architectural-level plan nodes. Each node:\n"
        f'{{"id": "n1", "decision": "...", "approach": "...", "grounds": ["principle-id"]}}\n'
        f"Return ONLY the JSON array."
    )
    raw_nodes = _parse_nodes(llm(prompt))
    plan = planops.new_plan(direction)
    for d in raw_nodes:
        node = _make_node(d, valid_ids, "architectural")
        if node is not None:
            try:
                plan = planops.add_node(plan, node)
            except ValueError:
                continue
    return plan


def expand_subtree(
    plan: Plan,
    node_id: str,
    principles: list[Result],
    llm: LLM,
    out_dir: Path,
) -> Plan:
    parent = planops.find_node(plan, node_id)
    if parent is None:
        raise ValueError(f"node {node_id!r} not found in plan")

    valid_ids = {r.principle.id for r in principles}
    summary = "\n".join(
        f"- {r.principle.id}: {r.principle.statement}" for r in principles
    )
    prompt = (
        f"Parent decision: {parent.decision}\n"
        f"Parent approach: {parent.approach}\n\n"
        f"Available principles:\n{summary}\n\n"
        f"Produce a JSON array of structural/implementation child nodes. Each node:\n"
        f'{{"id": "n1_1", "level": "structural", "decision": "...", '
        f'"approach": "...", "grounds": ["principle-id"], "depends_on": []}}\n'
        f"Return ONLY the JSON array."
    )
    raw_nodes = _parse_nodes(llm(prompt))

    new_plan = planops.next_version(plan)
    child_ids: list[str] = []
    skipped_ids: list[str] = []
    for d in raw_nodes:
        level = d.get("level", "structural")
        if level not in ("structural", "implementation"):
            level = "structural"
        node = _make_node(d, valid_ids, level)
        if node is not None:
            # filter depends_on to only reference existing nodes
            existing_ids = {n.id for n in new_plan.nodes} | set(child_ids)
            if not all(dep in existing_ids for dep in node.depends_on):
                node = dataclasses.replace(
                    node,
                    depends_on=tuple(dep for dep in node.depends_on if dep in existing_ids)
                )
            try:
                new_plan = planops.add_node(new_plan, node)
                child_ids.append(node.id)
            except ValueError:
                skipped_ids.append(node.id)

    if child_ids:
        reason = "subtree expanded"
        if skipped_ids:
            reason = f"subtree expanded (skipped duplicate ids: {skipped_ids})"
        new_plan = planops.amend_node(
            new_plan, node_id,
            reason,
            children=tuple(child_ids),
        )

    planstore.save_plan(new_plan, out_dir)
    return new_plan
