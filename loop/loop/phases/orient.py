from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from librarian.store import Index
from ..worktree import WorktreeManager

LLM = Callable[[str], str]

_HONESTY_TEXT = (
    "Never claim more grounding or verification than you actually have. "
    "Mark every ungrounded decision explicitly."
)


@dataclass
class OrientResult:
    anchored_direction: str
    anchored_honesty_constraint: str
    specialist_persona: str
    retrieval_queries: list[str]
    worktree_path: str


def orient(
    direction: str,
    index: Index,
    llm: LLM,
    worktree_mgr: WorktreeManager,
    base_repo: Path,
    run_id: str,
) -> OrientResult:
    anchored_direction = f"#DIRECTION: {direction}"
    anchored_honesty = f"#HONESTY-CONSTRAINT: {_HONESTY_TEXT}"

    citations = sorted({
        (p.citation.isbn, p.citation.book, p.citation.chapter)
        for p in index.principles
    })
    reading_list = "\n".join(
        f"- {book}: {chapter}" for _, book, chapter in citations[:40]
    )
    persona_prompt = (
        f"You are a coding agent. Based on this reading list, write one paragraph "
        f"describing your specialist identity and expertise:\n\n{reading_list}"
    )
    specialist_persona = llm(persona_prompt).strip()

    query_prompt = (
        f"You are a coding agent with this expertise:\n{specialist_persona}\n\n"
        f"Direction: {direction}\n\n"
        f"Draft 3-5 retrieval queries to find the most relevant engineering "
        f"principles for this direction. Return one query per line, no numbering."
    )
    queries_raw = llm(query_prompt).strip()
    retrieval_queries = [q.strip() for q in queries_raw.splitlines() if q.strip()][:5]

    branch = f"warrant/{run_id[:8]}"
    wt_path = worktree_mgr.create(base_repo, branch)

    return OrientResult(
        anchored_direction=anchored_direction,
        anchored_honesty_constraint=anchored_honesty,
        specialist_persona=specialist_persona,
        retrieval_queries=retrieval_queries,
        worktree_path=str(wt_path),
    )
