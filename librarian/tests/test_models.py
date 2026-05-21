import pytest

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
    with pytest.raises(ValueError):
        Edge(src="a", dst="b", kind="bogus")
    assert Edge(src="a", dst="b", kind="contradicts").kind == "contradicts"
