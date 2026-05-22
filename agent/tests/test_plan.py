import pytest
from agent.plan import LEVELS, GROUNDS_STATES, PROVENANCE, ApplicableCheck, PlanNode


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


def _base_clean_node(**overrides) -> PlanNode:
    """Minimal valid PlanNode with grounds_state='clean'."""
    kwargs = dict(
        id="n1",
        level="architectural",
        decision="Use hexagonal architecture",
        approach="Ports and adapters; no framework in the domain layer",
        grounds=("principle-42",),
        grounds_state="clean",
    )
    kwargs.update(overrides)
    return PlanNode(**kwargs)


def test_plan_node_minimal_valid():
    node = _base_clean_node()
    assert node.id == "n1"
    assert node.level == "architectural"
    assert node.grounds == ("principle-42",)
    assert node.grounds_state == "clean"
    assert node.grounds_note == ""
    assert node.conflict_resolution == ""
    assert node.applicable_checks == ()
    assert node.depends_on == ()
    assert node.amended_from is None
    assert node.amended_reason is None
    assert node.children == ()


def test_plan_node_rejects_bad_level():
    with pytest.raises(ValueError, match="level"):
        _base_clean_node(level="tactical")


def test_plan_node_rejects_bad_grounds_state():
    with pytest.raises(ValueError, match="grounds_state"):
        _base_clean_node(grounds_state="pending")


def test_plan_node_clean_requires_grounds():
    with pytest.raises(ValueError, match="grounds"):
        _base_clean_node(grounds=())


def test_plan_node_conflicted_requires_conflict_resolution():
    with pytest.raises(ValueError, match="conflict_resolution"):
        PlanNode(
            id="n2",
            level="structural",
            decision="Choose DB",
            approach="PostgreSQL",
            grounds=("p1", "p2"),
            grounds_state="conflicted",
        )


def test_plan_node_conflicted_requires_at_least_two_grounds():
    with pytest.raises(ValueError, match="grounds"):
        PlanNode(
            id="n2",
            level="structural",
            decision="Choose DB",
            approach="PostgreSQL",
            grounds=("p1",),
            grounds_state="conflicted",
            conflict_resolution="p1 wins because it is more recent",
        )


def test_plan_node_conflicted_valid():
    node = PlanNode(
        id="n2",
        level="structural",
        decision="Choose DB",
        approach="PostgreSQL",
        grounds=("p1", "p2"),
        grounds_state="conflicted",
        conflict_resolution="p1 wins because it is more specific",
    )
    assert node.grounds_state == "conflicted"
    assert node.conflict_resolution == "p1 wins because it is more specific"


def test_plan_node_ungrounded_rejects_non_empty_grounds():
    with pytest.raises(ValueError, match="grounds"):
        PlanNode(
            id="n3",
            level="implementation",
            decision="Use stdlib only",
            approach="No third-party libraries",
            grounds=("some-principle",),
            grounds_state="ungrounded",
            grounds_note="Library is silent on stdlib-vs-third-party",
        )


def test_plan_node_ungrounded_requires_grounds_note():
    with pytest.raises(ValueError, match="grounds_note"):
        PlanNode(
            id="n3",
            level="implementation",
            decision="Use stdlib only",
            approach="No third-party libraries",
            grounds=(),
            grounds_state="ungrounded",
        )


def test_plan_node_ungrounded_valid():
    node = PlanNode(
        id="n3",
        level="implementation",
        decision="Use stdlib only",
        approach="No third-party libraries",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note="Library is silent on stdlib-vs-third-party for this context",
    )
    assert node.grounds == ()
    assert node.grounds_note != ""


def test_plan_node_is_frozen():
    node = _base_clean_node()
    with pytest.raises(Exception):
        node.id = "mutated"  # type: ignore[misc]


def test_plan_node_with_optional_fields():
    check = ApplicableCheck(check="c1", provenance="from_grounds")
    node = PlanNode(
        id="n4",
        level="implementation",
        decision="Validate input at boundary",
        approach="Pydantic models on all API entry points",
        grounds=("p5",),
        grounds_state="clean",
        applicable_checks=(check,),
        depends_on=("n1",),
        amended_from="n4-old",
        amended_reason="Original approach caused circular imports",
        children=("n5", "n6"),
    )
    assert node.applicable_checks == (check,)
    assert node.depends_on == ("n1",)
    assert node.amended_from == "n4-old"
    assert node.children == ("n5", "n6")
