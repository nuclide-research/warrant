import sys

from .corpus import iter_sections
from .edges import extract_edges
from .extract import extract_principles
from .store import Index


def build_index(library_dir, llm, embedder) -> Index:
    """Walk the library: one extraction pass per section, one edge pass over
    all principles, then embed every principle statement. A section whose LLM
    response is malformed is skipped with a warning; if the edge pass itself
    fails, the index is still built without a principle graph. Neither is
    allowed to abort the whole build."""
    principles = []
    for section_index, (book, chapter, section) in enumerate(iter_sections(library_dir)):
        try:
            principles.extend(
                extract_principles(book, chapter, section, llm, section_index))
        except (ValueError, KeyError) as e:
            print(f"warning: skipping {book.title} ({book.isbn}) / {chapter} / "
                  f"{section.heading}: malformed LLM response ({e})",
                  file=sys.stderr)

    edges: list = []
    if principles:
        try:
            edges = extract_edges(principles, llm)
        except (ValueError, KeyError) as e:
            print(f"warning: edge extraction failed, building index with no "
                  f"principle graph ({e})", file=sys.stderr)
    embeddings = embedder.encode([p.statement for p in principles])
    return Index(principles=principles, embeddings=embeddings, edges=edges)
