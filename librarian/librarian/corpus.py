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
