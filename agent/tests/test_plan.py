import pytest
from agent.plan import LEVELS, GROUNDS_STATES, PROVENANCE, ApplicableCheck


def test_constants_are_tuples_of_strings():
    assert isinstance(LEVELS, tuple)
    assert isinstance(GROUNDS_STATES, tuple)
    assert isinstance(PROVENANCE, tuple)
    assert "architectural" in LEVELS
    assert "structural" in LEVELS
    assert "implementation" in LEVELS
    assert "clean" in GROUNDS_STATES
    assert "conflicted" in GROUNDS_STATES
    assert "ungrounded" in GROUNDS_STATES
    assert "from_grounds" in PROVENANCE
    assert "from_topic" in PROVENANCE


def test_applicable_check_valid():
    c = ApplicableCheck(check="check-42", provenance="from_grounds")
    assert c.check == "check-42"
    assert c.provenance == "from_grounds"


def test_applicable_check_valid_from_topic():
    c = ApplicableCheck(check="check-99", provenance="from_topic")
    assert c.provenance == "from_topic"


def test_applicable_check_rejects_bad_provenance():
    with pytest.raises(ValueError, match="provenance"):
        ApplicableCheck(check="check-1", provenance="invented")


def test_applicable_check_is_frozen():
    c = ApplicableCheck(check="x", provenance="from_grounds")
    with pytest.raises(Exception):
        c.check = "y"  # type: ignore[misc]
