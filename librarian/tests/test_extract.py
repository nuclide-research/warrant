import json
import pytest
from librarian.corpus import Book, Section
from librarian.extract import extract_principles
from tests.fakes import FakeLLM, principles_json
from pathlib import Path

BOOK = Book(isbn="9781633437166", title="CSS in Depth", path=Path("."))
SECTION = Section(heading="12.1.1 Using ems vs px",
                  text="Use ems for spacing immediately around text so it scales.")


def test_extract_principles_parses_llm_json_into_principles():
    llm = FakeLLM([principles_json([
        {"statement": "Use ems for text-adjacent spacing so it scales.",
         "checkability_tier": 2,
         "evidence_chunk": "Use ems for spacing immediately around text."},
    ])])
    out = extract_principles(BOOK, "Typography and spacing", SECTION, llm)
    assert len(out) == 1
    p = out[0]
    assert p.statement.startswith("Use ems")
    assert p.checkability_tier == 2
    assert p.citation.isbn == "9781633437166"
    assert p.citation.chapter == "Typography and spacing"
    assert p.citation.section == "12.1.1 Using ems vs px"
    assert p.id == "9781633437166:typography-and-spacing:12-1-1-using-ems-vs-px:1"


def test_extract_principles_tolerates_fenced_json():
    llm = FakeLLM(["```json\n[]\n```"])
    assert extract_principles(BOOK, "Ch", SECTION, llm) == []


def test_extract_principles_tolerates_bare_fence_and_preamble():
    llm = FakeLLM(["Here is the result:\n```\n[]\n```"])
    assert extract_principles(BOOK, "Ch", SECTION, llm) == []


def test_extract_principles_rejects_non_array():
    llm = FakeLLM([json.dumps({"not": "an array"})])
    with pytest.raises(ValueError):
        extract_principles(BOOK, "Ch", SECTION, llm)


def test_extract_principles_rejects_bad_tier():
    llm = FakeLLM([principles_json([
        {"statement": "x", "checkability_tier": 9, "evidence_chunk": "y"}])])
    with pytest.raises(ValueError):
        extract_principles(BOOK, "Ch", SECTION, llm)
