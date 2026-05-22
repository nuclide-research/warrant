import json
import re
from typing import Protocol

from .corpus import Book, Section
from .models import Citation, Principle


class LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


_PROMPT = """\
You are extracting discrete, reusable engineering principles from one section
of a technical book. Return ONLY a JSON array. Each element:
  {{"statement": "<one imperative principle, self-contained>",
    "checkability_tier": <1|2|3>,
    "evidence_chunk": "<the sentence(s) the principle is drawn from>"}}

checkability_tier:
  1 = mechanically checkable (a script/lint/test could verify it)
  2 = measurable (a metric, not a pass/fail)
  3 = judgment (not mechanizable)

Extract only genuine principles. A section with none returns [].

BOOK: {book}
CHAPTER: {chapter}
SECTION: {section}

TEXT:
{text}
"""


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:50].strip("-") or "x"


def _parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    return data


def extract_principles(book: Book, chapter: str, section: Section, llm: LLM,
                       section_index: int = 0) -> list[Principle]:
    """Extract principles from one section. section_index is the section's
    position in the book; it disambiguates the principle id when two sections
    in a chapter share a heading (or slug-collide after truncation)."""
    prompt = _PROMPT.format(book=book.title, chapter=chapter,
                            section=section.heading, text=section.text)
    items = _parse_json_array(llm.complete(prompt))
    out: list[Principle] = []
    for n, item in enumerate(items, start=1):
        tier = int(item["checkability_tier"])
        if tier not in (1, 2, 3):
            raise ValueError(f"bad checkability_tier {tier}")
        pid = f"{book.isbn}:{_slug(chapter)}:{_slug(section.heading)}:{section_index}:{n}"
        out.append(Principle(
            id=pid,
            statement=item["statement"].strip(),
            citation=Citation(book=book.title, isbn=book.isbn,
                              chapter=chapter, section=section.heading),
            checkability_tier=tier,
            evidence_chunk=item["evidence_chunk"].strip(),
        ))
    return out
