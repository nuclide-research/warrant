from librarian.cli import build_parser


def test_parser_has_index_and_query_subcommands():
    parser = build_parser()
    idx = parser.parse_args(["index", "/lib", "--out", "/idx"])
    assert idx.command == "index" and idx.library == "/lib" and idx.out == "/idx"
    q = parser.parse_args(["query", "how to balance a layout", "-k", "3"])
    assert q.command == "query" and q.text == "how to balance a layout" and q.k == 3
