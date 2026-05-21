from pathlib import Path

from librarian.corpus import discover_books, iter_sections, _SKIP, _chapter_title, split_sections

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


def test_skip_regex_matches_frontmatter_not_content():
    for stem in ("02-copyright", "01-cover", "30-index", "04-about-the-author",
                 "00-titlepage", "03-table-of-contents", "05-acknowledgments"):
        assert _SKIP.search(stem), stem
    for stem in ("09-thinking-about-the-reader", "12-cover-letters",
                 "01-the-first-chapter", "07-writing-the-foreword"):
        assert not _SKIP.search(stem), stem


_H2_CHAPTER = """\
## Chapter 3. An Introduction to the Tools

*An epigraph.*

### Stop Me If You've Heard This

First section body.

### A Minimal Introduction

Second section body.
"""


def test_chapter_title_handles_h2_chapter_heading():
    assert _chapter_title(_H2_CHAPTER, fallback="06-ch03") == \
        "Chapter 3. An Introduction to the Tools"


def test_split_sections_skips_chapter_title_at_any_level():
    headings = [s.heading for s in split_sections(_H2_CHAPTER)]
    assert "Chapter 3. An Introduction to the Tools" not in headings
    assert headings == ["Introduction", "Stop Me If You've Heard This",
                        "A Minimal Introduction"]
