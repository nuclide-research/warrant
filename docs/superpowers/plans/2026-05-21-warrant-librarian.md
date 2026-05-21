# Warrant Librarian — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Librarian — the retrieval engine for Warrant — a Python CLI that indexes the `colophon-library` book corpus into a HybridRAG store (extracted principles + semantic embeddings + a principle graph) and answers grounded retrieval queries.

**Architecture:** `librarian index <library>` walks the colophon-library Markdown corpus, splits each chapter into sections, runs one LLM pass per section to extract discrete *principles* (each with a citation, a checkability tier, and its evidence chunk), runs a second LLM pass to extract `refines`/`contradicts`/`shares_topic` edges between principles, embeds the principle statements with a local model, and writes an inspectable index. `librarian query "<text>"` embeds the query, takes the semantic top-N, reranks with a cross-encoder, and returns the top-k principles with citations, tiers, and graph neighbors. The Tier-1 *check compiler* (compiling tier-1 principles into executable checks) is out of scope for this plan — the `checkability_tier` field is populated, but compilation is a later sub-project.

**Tech Stack:** Python 3.11+, `anthropic` (principle/edge extraction), `sentence-transformers` (local embeddings + cross-encoder rerank), `numpy` (vector store), `pytest`. The LLM is reached through a `Protocol` so every extraction test runs against a deterministic fake — no API calls, no key, in the test suite.

---

## File Structure

```
warrant/librarian/
  pyproject.toml            packaging + deps + pytest config
  librarian/
    __init__.py
    __main__.py             python -m librarian entry point
    models.py               Citation, Principle, Edge + dict (de)serialization
    corpus.py               discover books, read chapters, split sections
    extract.py              LLM protocol; extract_principles()
    edges.py                extract_edges()
    llm.py                  AnthropicLLM — the real LLM client
    embedding.py            Embedder — local sentence-transformers wrapper
    store.py                Index dataclass; save_index() / load_index()
    indexer.py              build_index() — orchestrates the index pipeline
    query.py                Reranker; query_index()
    cli.py                  argparse: `index` and `query` subcommands
  tests/
    fixtures/               a tiny fake colophon-library book
    fakes.py                FakeLLM, FakeEmbedder
    test_models.py
    test_corpus.py
    test_extract.py
    test_edges.py
    test_store.py
    test_indexer.py
    test_query.py
    test_cli.py
    test_integration.py
```

One responsibility per file. `corpus.py` is pure parsing (no LLM, no embeddings). `extract.py`/`edges.py` are pure given an `LLM`. `embedding.py`/`query.py` own the vector side. `indexer.py` is the only orchestrator. The CLI is a thin wiring layer.

---

## Task 1: Project scaffold

**Files:**
- Create: `warrant/librarian/pyproject.toml`
- Create: `warrant/librarian/librarian/__init__.py`
- Create: `warrant/librarian/tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import librarian
    assert librarian.__version__ == "0.1.0"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd warrant/librarian && python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian'`

- [ ] **Step 3: Create the package**

`pyproject.toml`:
```toml
[project]
name = "librarian"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40",
    "sentence-transformers>=3.0",
    "numpy>=1.26",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
librarian = "librarian.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`librarian/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install and verify the test passes**

Run: `cd warrant/librarian && pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd warrant/librarian
git add pyproject.toml librarian/__init__.py tests/test_smoke.py
git commit -m "feat(librarian): project scaffold"
```

---

## Task 2: Core models

**Files:**
- Create: `warrant/librarian/librarian/models.py`
- Test: `warrant/librarian/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from librarian.models import Citation, Principle, Edge, principle_to_dict, principle_from_dict


def test_principle_round_trips_through_dict():
    p = Principle(
        id="9781633437166:ch3:intro:1",
        statement="Heading margins should use em units so they scale with font size.",
        citation=Citation(book="CSS in Depth", isbn="9781633437166",
                          chapter="Typography and spacing", section="12.1.1"),
        checkability_tier=1,
        evidence_chunk="If you think the space should resize ... use ems.",
    )
    restored = principle_from_dict(principle_to_dict(p))
    assert restored == p


def test_edge_kind_is_constrained():
    import pytest
    with pytest.raises(ValueError):
        Edge(src="a", dst="b", kind="bogus")
    assert Edge(src="a", dst="b", kind="contradicts").kind == "contradicts"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.models'`

- [ ] **Step 3: Write the implementation**

`librarian/models.py`:
```python
from dataclasses import dataclass, asdict

EDGE_KINDS = ("refines", "contradicts", "shares_topic")


@dataclass(frozen=True)
class Citation:
    book: str
    isbn: str
    chapter: str
    section: str


@dataclass
class Principle:
    id: str
    statement: str
    citation: Citation
    checkability_tier: int  # 1, 2, or 3
    evidence_chunk: str


@dataclass(frozen=True)
class Edge:
    src: str   # principle id
    dst: str   # principle id
    kind: str  # one of EDGE_KINDS

    def __post_init__(self):
        if self.kind not in EDGE_KINDS:
            raise ValueError(f"edge kind must be one of {EDGE_KINDS}, got {self.kind!r}")


def principle_to_dict(p: Principle) -> dict:
    return {**asdict(p), "citation": asdict(p.citation)}


def principle_from_dict(d: dict) -> Principle:
    return Principle(
        id=d["id"],
        statement=d["statement"],
        citation=Citation(**d["citation"]),
        checkability_tier=d["checkability_tier"],
        evidence_chunk=d["evidence_chunk"],
    )
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add librarian/models.py tests/test_models.py
git commit -m "feat(librarian): core models — Citation, Principle, Edge"
```

---

## Task 3: Corpus discovery and section splitting

**Files:**
- Create: `warrant/librarian/librarian/corpus.py`
- Create: `warrant/librarian/tests/fixtures/9999999999999-fixture-book/book.json`
- Create: `warrant/librarian/tests/fixtures/9999999999999-fixture-book/01-the-first-chapter.md`
- Test: `warrant/librarian/tests/test_corpus.py`

- [ ] **Step 1: Create the fixture book**

`tests/fixtures/9999999999999-fixture-book/book.json`:
```json
{"isbn": "9999999999999", "title": "Fixture Book"}
```

`tests/fixtures/9999999999999-fixture-book/01-the-first-chapter.md`:
```markdown
# The First Chapter

Intro text before any section heading.

## Section One

Body of section one. Two sentences here.

## Section Two

Body of section two.
```

- [ ] **Step 2: Write the failing test**

`tests/test_corpus.py`:
```python
from pathlib import Path
from librarian.corpus import discover_books, iter_sections

FIXTURES = Path(__file__).parent / "fixtures"


def test_discover_books_reads_book_json():
    books = discover_books(FIXTURES)
    assert len(books) == 1
    assert books[0].isbn == "9999999999999"
    assert books[0].title == "Fixture Book"


def test_iter_sections_yields_chapter_and_section_context():
    rows = list(iter_sections(FIXTURES))
    # intro text + 2 headed sections = 3 sections
    assert len(rows) == 3
    book, chapter_title, section = rows[1]
    assert book.isbn == "9999999999999"
    assert chapter_title == "The First Chapter"
    assert section.heading == "Section One"
    assert "section one" in section.text.lower()
```

- [ ] **Step 3: Run it, verify it fails**

Run: `python -m pytest tests/test_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.corpus'`

- [ ] **Step 4: Write the implementation**

`librarian/corpus.py`:
```python
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# colophon frontmatter/back-matter files to skip when reading chapters.
_SKIP = re.compile(r"titlepage|copyright|^0?1-cover|table-of-contents|dedication|"
                   r"acknowledg|preface|foreword|^.*-index$|navigation|why-subscribe|"
                   r"contributors|about-the", re.IGNORECASE)


@dataclass(frozen=True)
class Book:
    isbn: str
    title: str
    path: Path


@dataclass(frozen=True)
class Section:
    heading: str
    text: str


def discover_books(library_dir) -> list[Book]:
    library_dir = Path(library_dir)
    books = []
    for d in sorted(library_dir.iterdir()):
        meta = d / "book.json"
        if not (d.is_dir() and meta.exists()):
            continue
        data = json.loads(meta.read_text())
        books.append(Book(isbn=data["isbn"], title=data.get("title", d.name), path=d))
    return books


def _chapter_files(book: Book) -> list[Path]:
    out = []
    for f in sorted(book.path.glob("*.md")):
        if f.name == "_combined.md" or _SKIP.search(f.stem):
            continue
        out.append(f)
    return out


def _chapter_title(md: str, fallback: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def split_sections(md: str) -> list[Section]:
    """Split chapter Markdown on `##`/`###` headings. Text before the first
    heading becomes a section with heading 'Introduction'."""
    sections: list[Section] = []
    heading = "Introduction"
    buf: list[str] = []
    for line in md.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            continue  # the chapter H1, already captured as the title
        m = re.match(r"#{2,3}\s+(.*)", line)
        if m:
            if buf and "".join(buf).strip():
                sections.append(Section(heading=heading, text="\n".join(buf).strip()))
            heading = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections.append(Section(heading=heading, text="\n".join(buf).strip()))
    return sections


def iter_sections(library_dir) -> Iterator[tuple[Book, str, Section]]:
    for book in discover_books(library_dir):
        for f in _chapter_files(book):
            md = f.read_text()
            title = _chapter_title(md, fallback=f.stem)
            for section in split_sections(md):
                yield book, title, section
```

- [ ] **Step 5: Run it, verify it passes**

Run: `python -m pytest tests/test_corpus.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add librarian/corpus.py tests/test_corpus.py tests/fixtures/
git commit -m "feat(librarian): corpus discovery and section splitting"
```

---

## Task 4: Principle extraction (with a fake LLM)

**Files:**
- Create: `warrant/librarian/librarian/extract.py`
- Create: `warrant/librarian/tests/fakes.py`
- Test: `warrant/librarian/tests/test_extract.py`

- [ ] **Step 1: Write the fake LLM**

`tests/fakes.py`:
```python
import json


class FakeLLM:
    """Returns a queued response per complete() call. Records prompts."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def principles_json(items: list[dict]) -> str:
    return json.dumps(items)
```

- [ ] **Step 2: Write the failing test**

`tests/test_extract.py`:
```python
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
```

- [ ] **Step 3: Run it, verify it fails**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.extract'`

- [ ] **Step 4: Write the implementation**

`librarian/extract.py`:
```python
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


def extract_principles(book: Book, chapter: str, section: Section, llm: LLM) -> list[Principle]:
    prompt = _PROMPT.format(book=book.title, chapter=chapter,
                            section=section.heading, text=section.text)
    items = _parse_json_array(llm.complete(prompt))
    out: list[Principle] = []
    for n, item in enumerate(items, start=1):
        tier = int(item["checkability_tier"])
        if tier not in (1, 2, 3):
            raise ValueError(f"bad checkability_tier {tier}")
        pid = f"{book.isbn}:{_slug(chapter)}:{_slug(section.heading)}:{n}"
        out.append(Principle(
            id=pid,
            statement=item["statement"].strip(),
            citation=Citation(book=book.title, isbn=book.isbn,
                              chapter=chapter, section=section.heading),
            checkability_tier=tier,
            evidence_chunk=item["evidence_chunk"].strip(),
        ))
    return out
```

- [ ] **Step 5: Run it, verify it passes**

Run: `python -m pytest tests/test_extract.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add librarian/extract.py tests/fakes.py tests/test_extract.py
git commit -m "feat(librarian): principle extraction with a mockable LLM"
```

---

## Task 5: The Anthropic LLM client

**Files:**
- Create: `warrant/librarian/librarian/llm.py`
- Test: `warrant/librarian/tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

The real API is not called in the suite; a stub `anthropic`-shaped client verifies the request/response wiring.

`tests/test_llm.py`:
```python
from librarian.llm import AnthropicLLM


class _StubMessages:
    def __init__(self, recorder):
        self._rec = recorder

    def create(self, **kwargs):
        self._rec.update(kwargs)

        class _Block:
            text = "STUB RESPONSE"

        class _Msg:
            content = [_Block()]

        return _Msg()


class _StubClient:
    def __init__(self, recorder):
        self.messages = _StubMessages(recorder)


def test_anthropic_llm_sends_prompt_and_returns_text():
    rec: dict = {}
    llm = AnthropicLLM(model="claude-sonnet-4-6", client=_StubClient(rec))
    out = llm.complete("hello")
    assert out == "STUB RESPONSE"
    assert rec["model"] == "claude-sonnet-4-6"
    assert rec["messages"][0]["content"] == "hello"
    assert rec["max_tokens"] >= 1
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.llm'`

- [ ] **Step 3: Write the implementation**

`librarian/llm.py`:
```python
import os


class AnthropicLLM:
    """LLM implementation backed by the Anthropic API. `client` is injectable
    for tests; in production it defaults to a real anthropic.Anthropic()."""

    def __init__(self, model: str = "claude-sonnet-4-6", client=None,
                 max_tokens: int = 8000):
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._client = client

    def complete(self, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/llm.py tests/test_llm.py
git commit -m "feat(librarian): Anthropic LLM client"
```

---

## Task 6: Edge extraction

**Files:**
- Create: `warrant/librarian/librarian/edges.py`
- Test: `warrant/librarian/tests/test_edges.py`

- [ ] **Step 1: Write the failing test**

`tests/test_edges.py`:
```python
from librarian.models import Citation, Principle
from librarian.edges import extract_edges
from tests.fakes import FakeLLM
import json


def _p(pid, statement):
    return Principle(id=pid, statement=statement,
                     citation=Citation("B", "111", "C", "S"),
                     checkability_tier=3, evidence_chunk="e")


def test_extract_edges_parses_relations_and_drops_unknown_ids():
    principles = [_p("p1", "Prefer composition."), _p("p2", "Always use inheritance.")]
    llm = FakeLLM([json.dumps([
        {"src": "p1", "dst": "p2", "kind": "contradicts"},
        {"src": "p1", "dst": "ghost", "kind": "refines"},  # ghost id -> dropped
    ])])
    edges = extract_edges(principles, llm)
    assert len(edges) == 1
    assert edges[0].src == "p1" and edges[0].dst == "p2"
    assert edges[0].kind == "contradicts"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_edges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.edges'`

- [ ] **Step 3: Write the implementation**

`librarian/edges.py`:
```python
from .extract import LLM, _parse_json_array
from .models import Edge, Principle

_PROMPT = """\
Below is a numbered list of engineering principles, each with an id. Identify
relationships between them. Return ONLY a JSON array; each element:
  {{"src": "<id>", "dst": "<id>", "kind": "refines|contradicts|shares_topic"}}
  refines       = src is a more specific case of dst
  contradicts   = src and dst give conflicting guidance
  shares_topic  = src and dst address the same topic without refining/conflicting
Only relate principles that genuinely relate. No relationships returns [].

PRINCIPLES:
{listing}
"""


def extract_edges(principles: list[Principle], llm: LLM) -> list[Edge]:
    ids = {p.id for p in principles}
    listing = "\n".join(f"- id={p.id}: {p.statement}" for p in principles)
    items = _parse_json_array(llm.complete(_PROMPT.format(listing=listing)))
    edges: list[Edge] = []
    for item in items:
        src, dst, kind = item.get("src"), item.get("dst"), item.get("kind")
        if src in ids and dst in ids and src != dst:
            try:
                edges.append(Edge(src=src, dst=dst, kind=kind))
            except ValueError:
                continue  # unknown kind -> drop
    return edges
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_edges.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/edges.py tests/test_edges.py
git commit -m "feat(librarian): principle-graph edge extraction"
```

---

## Task 7: The embedder

**Files:**
- Create: `warrant/librarian/librarian/embedding.py`
- Test: `warrant/librarian/tests/test_embedding.py`

- [ ] **Step 1: Write the failing test**

`tests/test_embedding.py`:
```python
import numpy as np
from librarian.embedding import Embedder


def test_embedder_returns_unit_vectors_one_row_per_text():
    emb = Embedder()
    vecs = emb.encode(["composition over inheritance", "use ems for spacing"])
    assert vecs.shape[0] == 2
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)  # normalized for cosine via dot
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_embedding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.embedding'`

- [ ] **Step 3: Write the implementation**

`librarian/embedding.py`:
```python
import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder:
    """Local sentence-transformers embedder. Returns L2-normalized vectors so
    cosine similarity is a plain dot product."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._model.get_sentence_embedding_dimension()),
                            dtype=np.float32)
        return self._model.encode(texts, normalize_embeddings=True,
                                  convert_to_numpy=True).astype(np.float32)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_embedding.py -v`
Expected: PASS (first run downloads the model)

- [ ] **Step 5: Commit**

```bash
git add librarian/embedding.py tests/test_embedding.py
git commit -m "feat(librarian): local embedder"
```

---

## Task 8: The index store

**Files:**
- Create: `warrant/librarian/librarian/store.py`
- Test: `warrant/librarian/tests/test_store.py`

- [ ] **Step 1: Write the failing test**

`tests/test_store.py`:
```python
import numpy as np
from librarian.models import Citation, Principle, Edge
from librarian.store import Index, save_index, load_index


def _index():
    p = Principle(id="111:c:s:1", statement="Do the thing.",
                  citation=Citation("B", "111", "C", "S"),
                  checkability_tier=1, evidence_chunk="evidence")
    return Index(principles=[p],
                 embeddings=np.ones((1, 4), dtype=np.float32),
                 edges=[Edge("111:c:s:1", "111:c:s:1", "refines")])


def test_save_then_load_round_trips(tmp_path):
    save_index(_index(), tmp_path)
    loaded = load_index(tmp_path)
    assert loaded.principles[0].statement == "Do the thing."
    assert loaded.embeddings.shape == (1, 4)
    assert loaded.edges[0].kind == "refines"
    # principles are written as inspectable per-principle JSON files
    assert (tmp_path / "principles").is_dir()
    assert len(list((tmp_path / "principles").glob("*.json"))) == 1
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.store'`

- [ ] **Step 3: Write the implementation**

`librarian/store.py`:
```python
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from .models import Edge, Principle, principle_from_dict, principle_to_dict


@dataclass
class Index:
    principles: list[Principle]
    embeddings: np.ndarray   # shape (len(principles), dim), row i -> principles[i]
    edges: list[Edge]


def _safe(pid: str) -> str:
    return pid.replace(":", "__").replace("/", "_")


def save_index(index: Index, out_dir) -> None:
    out = Path(out_dir)
    (out / "principles").mkdir(parents=True, exist_ok=True)
    order = []
    for p in index.principles:
        (out / "principles" / f"{_safe(p.id)}.json").write_text(
            json.dumps(principle_to_dict(p), indent=2))
        order.append(p.id)
    np.save(out / "embeddings.npy", index.embeddings)
    (out / "edges.json").write_text(
        json.dumps([asdict(e) for e in index.edges], indent=2))
    (out / "manifest.json").write_text(
        json.dumps({"order": order, "count": len(order)}, indent=2))


def load_index(out_dir) -> Index:
    out = Path(out_dir)
    order = json.loads((out / "manifest.json").read_text())["order"]
    principles = [
        principle_from_dict(json.loads(
            (out / "principles" / f"{_safe(pid)}.json").read_text()))
        for pid in order
    ]
    embeddings = np.load(out / "embeddings.npy")
    edges = [Edge(**e) for e in json.loads((out / "edges.json").read_text())]
    return Index(principles=principles, embeddings=embeddings, edges=edges)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/store.py tests/test_store.py
git commit -m "feat(librarian): index store — inspectable principle files + vectors"
```

---

## Task 9: The index pipeline

**Files:**
- Create: `warrant/librarian/librarian/indexer.py`
- Test: `warrant/librarian/tests/test_indexer.py`

- [ ] **Step 1: Write the failing test**

`tests/test_indexer.py`:
```python
from pathlib import Path
import numpy as np
from librarian.indexer import build_index
from tests.fakes import FakeLLM, principles_json
import json

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    def encode(self, texts):
        return np.ones((len(texts), 4), dtype=np.float32)


def test_build_index_extracts_embeds_and_links():
    # fixture book has 3 sections -> 3 principle-extraction calls, then 1 edge call
    llm = FakeLLM([
        principles_json([{"statement": "Principle A.", "checkability_tier": 1,
                          "evidence_chunk": "a"}]),
        principles_json([{"statement": "Principle B.", "checkability_tier": 2,
                          "evidence_chunk": "b"}]),
        principles_json([]),
        json.dumps([]),  # edge-extraction call
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    assert len(index.principles) == 2
    assert index.embeddings.shape == (2, 4)
    assert index.edges == []
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.indexer'`

- [ ] **Step 3: Write the implementation**

`librarian/indexer.py`:
```python
from .corpus import iter_sections
from .edges import extract_edges
from .extract import extract_principles
from .store import Index


def build_index(library_dir, llm, embedder) -> Index:
    """Walk the library: one extraction pass per section, one edge pass over
    all principles, then embed every principle statement."""
    principles = []
    for book, chapter, section in iter_sections(library_dir):
        principles.extend(extract_principles(book, chapter, section, llm))

    edges = extract_edges(principles, llm) if principles else []
    embeddings = embedder.encode([p.statement for p in principles])
    return Index(principles=principles, embeddings=embeddings, edges=edges)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_indexer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/indexer.py tests/test_indexer.py
git commit -m "feat(librarian): index pipeline orchestration"
```

---

## Task 10: Retrieval with rerank and graph neighbors

**Files:**
- Create: `warrant/librarian/librarian/query.py`
- Test: `warrant/librarian/tests/test_query.py`

- [ ] **Step 1: Write the failing test**

`tests/test_query.py`:
```python
import numpy as np
from librarian.models import Citation, Principle, Edge
from librarian.store import Index
from librarian.query import query_index


def _p(pid, statement):
    return Principle(id=pid, statement=statement,
                     citation=Citation("B", "111", "C", pid),
                     checkability_tier=3, evidence_chunk="e")


class FakeEmbedder:
    # query "layout" embeds parallel to row 0, orthogonal to row 1
    def encode(self, texts):
        return np.array([[1.0, 0.0]], dtype=np.float32)


class FakeReranker:
    def rerank(self, query, candidates):
        # identity rerank: keep semantic order, attach a score
        return [(p, 1.0) for p in candidates]


def test_query_returns_top_k_with_citations_and_graph_neighbors():
    index = Index(
        principles=[_p("p1", "layout principle"), _p("p2", "unrelated principle")],
        embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        edges=[Edge("p1", "p2", "contradicts")],
    )
    results = query_index(index, "layout", FakeEmbedder(), FakeReranker(), k=1)
    assert len(results) == 1
    r = results[0]
    assert r.principle.id == "p1"
    assert r.citation.section == "p1"
    assert r.neighbors == [("p2", "contradicts")]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.query'`

- [ ] **Step 3: Write the implementation**

`librarian/query.py`:
```python
from dataclasses import dataclass

import numpy as np

from .models import Citation, Principle
from .store import Index

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
SEMANTIC_POOL = 20  # candidates fed to the reranker


@dataclass
class Result:
    principle: Principle
    citation: Citation
    score: float
    neighbors: list[tuple[str, str]]  # (neighbor principle id, edge kind)


class Reranker:
    """Cross-encoder reranker over (query, principle statement) pairs."""

    def __init__(self, model_name: str = RERANK_MODEL):
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[Principle]) -> list[tuple[Principle, float]]:
        if not candidates:
            return []
        scores = self._model.predict([(query, p.statement) for p in candidates])
        ranked = sorted(zip(candidates, scores), key=lambda t: t[1], reverse=True)
        return [(p, float(s)) for p, s in ranked]


def _neighbors(index: Index, pid: str) -> list[tuple[str, str]]:
    out = []
    for e in index.edges:
        if e.src == pid:
            out.append((e.dst, e.kind))
        elif e.dst == pid:
            out.append((e.src, e.kind))
    return out


def query_index(index: Index, query_text: str, embedder, reranker, k: int = 5) -> list[Result]:
    if not index.principles:
        return []
    qv = embedder.encode([query_text])[0]
    sims = index.embeddings @ qv  # rows are normalized -> dot == cosine
    pool_idx = np.argsort(sims)[::-1][:SEMANTIC_POOL]
    pool = [index.principles[i] for i in pool_idx]
    ranked = reranker.rerank(query_text, pool)[:k]
    return [
        Result(principle=p, citation=p.citation, score=score,
               neighbors=_neighbors(index, p.id))
        for p, score in ranked
    ]
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_query.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/query.py tests/test_query.py
git commit -m "feat(librarian): retrieval — semantic pool, rerank, graph neighbors"
```

---

## Task 11: The CLI

**Files:**
- Create: `warrant/librarian/librarian/cli.py`
- Create: `warrant/librarian/librarian/__main__.py`
- Test: `warrant/librarian/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from librarian.cli import build_parser


def test_parser_has_index_and_query_subcommands():
    parser = build_parser()
    idx = parser.parse_args(["index", "/lib", "--out", "/idx"])
    assert idx.command == "index" and idx.library == "/lib" and idx.out == "/idx"
    q = parser.parse_args(["query", "how to balance a layout", "-k", "3"])
    assert q.command == "query" and q.text == "how to balance a layout" and q.k == 3
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.cli'`

- [ ] **Step 3: Write the implementation**

`librarian/cli.py`:
```python
import argparse
import json
import sys

from .embedding import Embedder
from .indexer import build_index
from .llm import AnthropicLLM
from .query import Reranker, query_index
from .store import load_index, save_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librarian",
                                     description="Warrant's retrieval engine.")
    sub = parser.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("index", help="build the index from a book library")
    pi.add_argument("library", help="path to the colophon-library directory")
    pi.add_argument("--out", default="./librarian-index", help="output index dir")

    pq = sub.add_parser("query", help="retrieve principles for a query")
    pq.add_argument("text", help="the query text")
    pq.add_argument("--index", default="./librarian-index", help="index dir")
    pq.add_argument("-k", type=int, default=5, help="how many principles to return")
    return parser


def _cmd_index(args) -> int:
    index = build_index(args.library, AnthropicLLM(), Embedder())
    save_index(index, args.out)
    print(f"indexed {len(index.principles)} principles, "
          f"{len(index.edges)} edges -> {args.out}", file=sys.stderr)
    return 0


def _cmd_query(args) -> int:
    index = load_index(args.index)
    results = query_index(index, args.text, Embedder(), Reranker(), k=args.k)
    print(json.dumps([
        {"statement": r.principle.statement,
         "tier": r.principle.checkability_tier,
         "citation": {"book": r.citation.book, "chapter": r.citation.chapter,
                      "section": r.citation.section},
         "score": round(r.score, 4),
         "neighbors": r.neighbors}
        for r in results
    ], indent=2))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return {"index": _cmd_index, "query": _cmd_query}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

`librarian/__main__.py`:
```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add librarian/cli.py librarian/__main__.py tests/test_cli.py
git commit -m "feat(librarian): index and query CLI"
```

---

## Task 12: End-to-end integration

**Files:**
- Test: `warrant/librarian/tests/test_integration.py`

- [ ] **Step 1: Write the integration test**

Drives the whole pipeline against the fixture book with fakes — no API, no model download in CI for the pipeline wiring (the real embedder/reranker get their own marked tests, run on demand).

`tests/test_integration.py`:
```python
from pathlib import Path
import json
import numpy as np
from librarian.indexer import build_index
from librarian.store import save_index, load_index
from librarian.query import query_index
from tests.fakes import FakeLLM, principles_json

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    """Deterministic: 'section one' principles get vector [1,0], others [0,1]."""
    def encode(self, texts):
        rows = [[1.0, 0.0] if "one" in t.lower() else [0.0, 1.0] for t in texts]
        return np.array(rows or [[0.0, 0.0]], dtype=np.float32)


class FakeReranker:
    def rerank(self, query, candidates):
        return [(p, 1.0) for p in candidates]


def test_index_save_load_query_round_trip(tmp_path):
    llm = FakeLLM([
        principles_json([{"statement": "Section one principle.",
                          "checkability_tier": 1, "evidence_chunk": "one"}]),
        principles_json([{"statement": "Section two principle.",
                          "checkability_tier": 2, "evidence_chunk": "two"}]),
        principles_json([]),
        json.dumps([]),
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    save_index(index, tmp_path / "idx")
    reloaded = load_index(tmp_path / "idx")

    results = query_index(reloaded, "section one", FakeEmbedder(), FakeReranker(), k=1)
    assert len(results) == 1
    assert "one" in results[0].principle.statement.lower()
    assert results[0].citation.isbn == "9999999999999"
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS — all tests across all modules green.

- [ ] **Step 3: Smoke-test against a real book (manual, requires `ANTHROPIC_API_KEY`)**

Run:
```bash
ANTHROPIC_API_KEY=... python -m librarian index \
  ~/colophon-library/9781633437555-css-in-depth --out /tmp/css-index
python -m librarian query "how should heading margins be sized" --index /tmp/css-index
```
Expected: `index` reports a principle count > 0; `query` returns JSON principles whose citations point into CSS in Depth, with checkability tiers and any graph neighbors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test(librarian): end-to-end index/save/load/query integration"
```

---

## Self-Review

- **Spec coverage** — principle extraction (Task 4), checkability tiers 1/2/3 (Task 4, stored Task 8), the HybridRAG split: semantic index (Tasks 7-10) + principle graph with `refines`/`contradicts`/`shares_topic` (Task 6, traversed Task 10), rerank (Task 10), inspectable principle files (Task 8), `librarian index` / `librarian query` (Task 11). The Tier-1 *check compiler* is intentionally out of scope — `checkability_tier` is populated but compilation is deferred to its own sub-project, as confirmed.
- **Type consistency** — `Principle`, `Citation`, `Edge` defined in Task 2 and used unchanged everywhere. `LLM` protocol defined Task 4, reused Task 6. `Index` defined Task 8, consumed Tasks 9-10. `extract_principles`, `extract_edges`, `build_index`, `query_index` signatures are stable across tasks.
- **No placeholders** — every step carries the actual code or command.

## Out of Scope (follow-on plans)

- **The Tier-1 check compiler** — compiling tier-1 principles into executable checks. Needs its own design spike once the static-analysis research lands.
- **The Agent** — the loop, the plan artifact, the Verifier subagent, skill packaging. Its own spec → plan → build cycle; depends on this Librarian's `query` interface.
- **Retrieval-quality evals** — the golden-set recall@k harness (spec Section 10) attaches once a real index exists.
