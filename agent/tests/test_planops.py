import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planops import add_node, amend_node, new_plan, next_version


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
