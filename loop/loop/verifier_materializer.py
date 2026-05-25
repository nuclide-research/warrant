from __future__ import annotations
import json
import os
import subprocess

from agent.plan import PlanNode
from librarian.query import Result
from .models import RunState, ExecutorResult

_DIFF_MAX_CHARS = 8000

_VERIFIER_RESULT_SCHEMA = json.dumps(
    {
        "node_id": "<string>",
        "verdict": "pass | fail",
        "confidence": 0.95,
        "check_outcomes": [
            {
                "check_id": "<string>",
                "provenance": "from_grounds | from_topic",
                "tier": 1,
                "passed": True,
                "metric_value": "",
                "judgment": "",
                "detail": "",
            }
        ],
        "integrity_verdict": "clean | integrity_failure | audit_catch",
        "summary": "<one line>",
    },
    indent=2,
)


def _get_diff(worktree_path: str, pre_execution_sha: str) -> str:
    try:
        # Tracked changes: diff against sha (committed) or working tree
        diff_cmd = (
            ["git", "diff", pre_execution_sha]
            if pre_execution_sha
            else ["git", "diff"]
        )
        diff_result = subprocess.run(
            diff_cmd, cwd=worktree_path, capture_output=True, text=True, check=False
        )
        diff = diff_result.stdout if diff_result.returncode == 0 else ""

        # Untracked files — include their contents as pseudo-diffs
        status_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=worktree_path, capture_output=True, check=False,
        )
        untracked_filenames = [
            p for p in status_result.stdout.decode("utf-8", errors="replace").split("\0") if p
        ]
        untracked_parts: list[str] = []
        for fname in untracked_filenames:
            fpath = os.path.join(worktree_path, fname)
            try:
                with open(fpath, "r", errors="replace") as fh:
                    content = fh.read()
                untracked_parts.append(
                    f"--- /dev/null\n+++ b/{fname}\n"
                    + "".join(f"+{line}\n" for line in content.splitlines())
                )
            except Exception:
                untracked_parts.append(f"?? {fname} (unreadable)")
        untracked = (
            "Untracked files (contents):\n" + "\n".join(untracked_parts)
            if untracked_parts
            else ""
        )

        diff = "\n".join(filter(None, [diff, untracked]))
    except Exception:
        diff = ""
    if not diff.strip():
        return "No changes detected."
    if len(diff) > _DIFF_MAX_CHARS:
        diff = diff[:_DIFF_MAX_CHARS] + "\n[diff truncated at 8000 characters]"
    return diff


def materialize_verifier(
    node: PlanNode,
    principles: list[Result],
    run_state: RunState,
    executor_result: ExecutorResult,
    worktree_path: str,
    all_nodes: dict[str, PlanNode],
    pre_execution_sha: str = "",
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
                f"  Evidence: {p.evidence_chunk}\n"
                f"  Checkability: Tier {p.checkability_tier} "
                f"(1=mechanical, 2=measurable, 3=judgment)"
            )
        else:
            missing_ids.append(pid)

    checks_lines = [
        f"- {ac.check} (provenance: {ac.provenance})"
        for ac in node.applicable_checks
    ]

    diff = _get_diff(worktree_path, pre_execution_sha)

    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        (
            "## Your role\n"
            "You are a Verifier. You did not write the code below and you have not seen "
            "the Executor's reasoning. Grade the Executor's work strictly against the "
            "cited principles. Do not accept the Executor's self-assessment at face value."
        ),
        f"## Working directory\n{worktree_path}",
    ]

    node_lines = [
        f"Decision: {node.decision}",
        f"Approach: {node.approach}",
        f"Grounds state: {node.grounds_state}",
    ]
    if node.grounds_state == "conflicted" and node.conflict_resolution:
        node_lines.append(f"Conflict resolution: {node.conflict_resolution}")
    if node.grounds_state == "ungrounded" and node.grounds_note:
        node_lines.append(f"Grounds note: {node.grounds_note}")
    sections.append("## Plan node\n" + "\n".join(node_lines))

    if grounding_lines:
        sections.append("## Grounding\n" + "\n\n".join(grounding_lines))

    if missing_ids:
        lines = "\n".join(
            f"- {i}: grading cannot verify this citation" for i in missing_ids
        )
        sections.append(f"## Missing principles\n{lines}")

    if checks_lines:
        sections.append("## Checks to grade\n" + "\n".join(checks_lines))

    sections.append(
        f"## Executor's self-report\n"
        f"Status claimed: {executor_result.status}\n"
        f"Summary: {executor_result.summary}\n"
        f"Principles honored: {executor_result.principles_honored}\n"
        f"Principles violated: {executor_result.principles_violated}"
    )

    sections.append(f"## Code diff (actual changes in worktree)\n{diff}")

    sections.append(
        f"## Return format\n"
        f"Return ONLY a JSON object matching this schema — no prose before or after:\n"
        f"```json\n{_VERIFIER_RESULT_SCHEMA}\n```"
    )

    return "\n\n".join(sections)
