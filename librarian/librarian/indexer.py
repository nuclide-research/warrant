import sys

from .corpus import iter_sections
from .edges import extract_edges
from .extract import extract_principles
from .store import Index


def build_index(library_dir, llm, embedder) -> Index:
    """Walk the library: one extraction pass per section, one edge pass over
    all principles, then embed every principle statement. A section whose LLM
    response is malformed is skipped with a warning, not allowed to abort the
    whole build."""
    principles = []
    for book, chapter, section in iter_sections(library_dir):
        try:
            principles.extend(extract_principles(book, chapter, section, llm))
        except (ValueError, KeyError) as e:
            print(f"warning: skipping {book.isbn} / {chapter} / "
                  f"{section.heading}: malformed LLM response ({e})",
                  file=sys.stderr)

    edges = extract_edges(principles, llm) if principles else []
    embeddings = embedder.encode([p.statement for p in principles])
    return Index(principles=principles, embeddings=embeddings, edges=edges)
