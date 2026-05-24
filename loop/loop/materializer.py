from __future__ import annotations
import json

from agent.plan import PlanNode
from librarian.query import Result
from .models import RunState

_RESULT_SCHEMA = json.dumps(
    {
        "node_id": "<string>",
        "status": "done | failed",
        "checks_run": [
            {
                "check_id": "<string>",
                "provenance": "from_grounds | from_topic",
                "passed": True,
                "detail": "<string>",
            }
        ],
        "principles_honored": ["<principle_id>"],
        "principles_violated": ["<principle_id>"],
        "amendments": [{"node_id": "<string>", "amended_reason": "<string>"}],
        "summary": "<one line>",
    },
    indent=2,
)


def materialize(
    node: PlanNode,
    principles: list[Result],
    run_state: RunState,
    all_nodes: dict[str, PlanNode],
) -> str:
    principle_map = {r.principle.id: r for r in principles}

    grounding_lines: list[str] = []
    missing_ids: list[str] = []
    for pid in node.grounds:
        if pid in principle_map:
            r = principle_map[pid]
            p = r.principle
            grounding_lines.append(
                f"- **{p.id}** ({p.citation.book}, {p.citation.chapter}, "
                f"{p.citation.section})\n"
                f"  Statement: {p.statement}\n"
                f"  Evidence: {p.evidence_chunk}"
            )
        else:
            missing_ids.append(pid)

    checks_lines = [
        f"- {ac.check} (provenance: {ac.provenance})"
        for ac in node.applicable_checks
    ]

    deps_lines: list[str] = []
    for dep_id in node.depends_on:
        dep = all_nodes.get(dep_id)
        if dep:
            deps_lines.append(f"- **{dep_id}**: {dep.decision} — {dep.approach}")

    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        f"## Your task\n{node.decision}",
        f"## Approach\n{node.approach}",
    ]

    if grounding_lines:
        sections.append("## Grounding\n" + "\n\n".join(grounding_lines))

    if missing_ids:
        lines = "\n".join(f"- {i}" for i in missing_ids)
        sections.append(f"# Missing principles (not in retrieved set)\n{lines}")

    if checks_lines:
        sections.append("## Checks you must run\n" + "\n".join(checks_lines))

    if deps_lines:
        sections.append("## Dependencies context\n" + "\n".join(deps_lines))

    sections.append(
        f"## Return format\n"
        f"Return ONLY a JSON object matching this schema — no prose before or after:\n"
        f"```json\n{_RESULT_SCHEMA}\n```"
    )

    return "\n\n".join(sections)
