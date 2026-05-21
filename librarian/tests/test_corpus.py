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
