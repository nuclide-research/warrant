import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planops import add_node, amend_node, children, find_node, independent_siblings, new_plan, next_version


def _make_node(node_id: str, *, level: str = "architectural", **kwargs) -> PlanNode:
    defaults = dict(
        level=level,
        decision=f"Decision for {node_id}",
        approach=f"Approach for {node_id}",
        grounds=("p1",),
        grounds_state="clean",
    )
    defaults.update(kwargs)
    return PlanNode(id=node_id, **defaults)


# --- new_plan ---

def test_new_plan_produces_version_1():
    plan = new_plan("Build a REST API")
    assert plan.version == 1


def test_new_plan_has_empty_nodes():
    plan = new_plan("Build a REST API")
    assert plan.nodes == ()


def test_new_plan_has_unique_plan_id():
    p1 = new_plan("task A")
    p2 = new_plan("task A")
    assert p1.plan_id != p2.plan_id


def test_new_plan_plan_id_is_hex_string():
    plan = new_plan("task")
    # uuid4().hex is 32 hex chars
    assert len(plan.plan_id) == 32
    int(plan.plan_id, 16)  # raises ValueError if not hex


def test_new_plan_stores_task():
    plan = new_plan("Implement rate limiting")
    assert plan.task == "Implement rate limiting"


# --- add_node ---

def test_add_node_appends_to_plan():
    plan = new_plan("task")
    node = _make_node("n1")
    updated = add_node(plan, node)
    assert len(updated.nodes) == 1
    assert updated.nodes[0].id == "n1"


def test_add_node_does_not_mutate_original():
    plan = new_plan("task")
    node = _make_node("n1")
    add_node(plan, node)
    assert len(plan.nodes) == 0


def test_add_node_rejects_duplicate_id():
    plan = new_plan("task")
    node = _make_node("n1")
    plan = add_node(plan, node)
    with pytest.raises(ValueError, match="n1"):
        add_node(plan, node)


def test_add_node_preserves_existing_nodes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, _make_node("n2"))
    assert len(plan.nodes) == 2
    assert plan.nodes[0].id == "n1"
    assert plan.nodes[1].id == "n2"


# --- amend_node ---

def test_amend_node_replaces_node():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", approach="Old approach"))
    amended = amend_node(plan, "n1", "Better approach discovered",
                         approach="New approach")
    node = amended.nodes[0]
    assert node.approach == "New approach"


def test_amend_node_sets_amended_from_and_reason():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    amended = amend_node(plan, "n1", "Old approach caused issues",
                         approach="Revised approach")
    node = amended.nodes[0]
    assert node.amended_from == "n1"
    assert node.amended_reason == "Old approach caused issues"


def test_amend_node_does_not_mutate_original():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", approach="Original"))
    amend_node(plan, "n1", "reason", approach="Changed")
    assert plan.nodes[0].approach == "Original"


def test_amend_node_raises_on_missing_id():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    with pytest.raises(ValueError, match="n99"):
        amend_node(plan, "n99", "reason", approach="x")


def test_amend_node_preserves_other_nodes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, _make_node("n2"))
    amended = amend_node(plan, "n1", "reason", approach="New")
    assert amended.nodes[1].id == "n2"
    assert amended.nodes[1].approach == "Approach for n2"


def test_amend_node_can_change_level():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1", level="architectural"))
    amended = amend_node(plan, "n1", "Re-scoped", level="structural")
    assert amended.nodes[0].level == "structural"


# --- next_version ---

def test_next_version_increments_by_one():
    plan = new_plan("task")
    assert plan.version == 1
    v2 = next_version(plan)
    assert v2.version == 2
    v3 = next_version(v2)
    assert v3.version == 3


def test_next_version_preserves_everything_else():
    plan = new_plan("task")
    node = _make_node("n1")
    plan = add_node(plan, node)
    v2 = next_version(plan)
    assert v2.plan_id == plan.plan_id
    assert v2.task == plan.task
    assert len(v2.nodes) == 1
    assert v2.nodes[0].id == "n1"


def test_next_version_does_not_mutate_original():
    plan = new_plan("task")
    next_version(plan)
    assert plan.version == 1


def test_amend_node_rejects_id_in_changes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    with pytest.raises(ValueError, match="id"):
        amend_node(plan, "n1", "reason", id="n2")


def test_amend_node_rejects_amended_from_in_changes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    with pytest.raises(ValueError, match="amended_from"):
        amend_node(plan, "n1", "reason", amended_from="forged")


def test_amend_node_rejects_amended_reason_in_changes():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    with pytest.raises(ValueError, match="amended_reason"):
        amend_node(plan, "n1", "reason", amended_reason="forged")


# --- query operations ---

def _plan_with_nodes(*node_ids: str) -> Plan:
    """Build a plan containing one clean node per id."""
    plan = new_plan("query test")
    for nid in node_ids:
        plan = add_node(plan, _make_node(nid))
    return plan


# --- find_node ---

def test_find_node_returns_node_when_present():
    plan = _plan_with_nodes("n1", "n2", "n3")
    node = find_node(plan, "n2")
    assert node is not None
    assert node.id == "n2"


def test_find_node_returns_none_when_missing():
    plan = _plan_with_nodes("n1", "n2")
    assert find_node(plan, "n99") is None


def test_find_node_works_on_empty_plan():
    plan = new_plan("empty")
    assert find_node(plan, "n1") is None


# --- children ---

def test_children_resolves_ids_to_nodes():
    plan = _plan_with_nodes("n1", "n2", "n3")
    # manually build a parent node that references n2 and n3 as children
    parent = PlanNode(
        id="root",
        level="architectural",
        decision="root decision",
        approach="root approach",
        grounds=("p1",),
        grounds_state="clean",
        children=("n2", "n3"),
    )
    plan = add_node(plan, parent)
    result = children(plan, parent)
    assert len(result) == 2
    ids = {n.id for n in result}
    assert ids == {"n2", "n3"}


def test_children_skips_ids_not_in_plan():
    plan = _plan_with_nodes("n1", "n2")
    parent = PlanNode(
        id="root",
        level="architectural",
        decision="root",
        approach="root",
        grounds=("p1",),
        grounds_state="clean",
        children=("n1", "n99"),  # n99 does not exist
    )
    plan = add_node(plan, parent)
    result = children(plan, parent)
    assert len(result) == 1
    assert result[0].id == "n1"


def test_children_empty_when_no_children():
    plan = _plan_with_nodes("n1")
    node = find_node(plan, "n1")
    assert children(plan, node) == []


# --- independent_siblings ---

def test_independent_siblings_true_when_no_cross_depends():
    # n1 and n2 do not depend on each other
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is True


def test_independent_siblings_false_when_one_depends_on_other():
    plan = new_plan("task")
    plan = add_node(plan, _make_node("n1"))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("n1",),  # n2 depends on n1
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is False


def test_independent_siblings_false_when_reverse_depends():
    # n1 depends on n2 — still not independent
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("n2",),
    ))
    plan = add_node(plan, _make_node("n2"))
    assert independent_siblings(plan, ["n1", "n2"]) is False


def test_independent_siblings_true_for_single_node():
    plan = _plan_with_nodes("n1")
    assert independent_siblings(plan, ["n1"]) is True


def test_independent_siblings_true_for_empty_list():
    plan = new_plan("task")
    assert independent_siblings(plan, []) is True


def test_independent_siblings_ignores_depends_on_outside_the_set():
    # n1 and n2 both depend on an external node "root" — not in the set
    plan = new_plan("task")
    plan = add_node(plan, PlanNode(
        id="n1", level="implementation", decision="d1", approach="a1",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    plan = add_node(plan, PlanNode(
        id="n2", level="implementation", decision="d2", approach="a2",
        grounds=("p1",), grounds_state="clean",
        depends_on=("root",),
    ))
    assert independent_siblings(plan, ["n1", "n2"]) is True
