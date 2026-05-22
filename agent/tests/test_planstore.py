import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planstore import plan_from_dict, plan_to_dict


def _make_plan() -> Plan:
    check = ApplicableCheck(check="c1", provenance="from_grounds")
    node = PlanNode(
        id="n1",
        level="architectural",
        decision="Use hexagonal architecture",
        approach="Ports and adapters",
        grounds=("p1", "p2"),
        grounds_state="clean",
        applicable_checks=(check,),
        depends_on=(),
        children=("n2",),
    )
    return Plan(
        plan_id="deadbeef",
        task="Build the thing",
        version=1,
        nodes=(node,),
    )


def test_plan_to_dict_produces_json_serialisable_dict():
    import json
    d = plan_to_dict(_make_plan())
    raw = json.dumps(d)  # must not raise
    assert isinstance(raw, str)
    assert "deadbeef" in raw


def test_plan_to_dict_tuples_become_lists():
    d = plan_to_dict(_make_plan())
    assert isinstance(d["nodes"], list)
    node_d = d["nodes"][0]
    assert isinstance(node_d["grounds"], list)
    assert isinstance(node_d["applicable_checks"], list)
    assert isinstance(node_d["depends_on"], list)
    assert isinstance(node_d["children"], list)


def test_plan_to_dict_applicable_check_is_nested_dict():
    d = plan_to_dict(_make_plan())
    check_d = d["nodes"][0]["applicable_checks"][0]
    assert isinstance(check_d, dict)
    assert check_d["check"] == "c1"
    assert check_d["provenance"] == "from_grounds"


def test_plan_round_trips_through_dict():
    original = _make_plan()
    restored = plan_from_dict(plan_to_dict(original))
    assert restored.plan_id == original.plan_id
    assert restored.task == original.task
    assert restored.version == original.version
    assert len(restored.nodes) == 1
    node = restored.nodes[0]
    assert node.id == "n1"
    assert node.level == "architectural"
    assert node.grounds == ("p1", "p2")
    assert node.grounds_state == "clean"
    assert node.children == ("n2",)
    assert len(node.applicable_checks) == 1
    assert node.applicable_checks[0].check == "c1"
    assert node.applicable_checks[0].provenance == "from_grounds"


def test_plan_round_trips_with_all_optional_fields():
    check = ApplicableCheck(check="c2", provenance="from_topic")
    node = PlanNode(
        id="n3",
        level="implementation",
        decision="Use stdlib json",
        approach="No third-party serializers",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note="Library is silent on serializer choice",
        applicable_checks=(check,),
        depends_on=("n1",),
        amended_from="n3-old",
        amended_reason="Old approach used orjson which added a dep",
        children=(),
    )
    plan = Plan(plan_id="ff00ff", task="Serialize things", version=3, nodes=(node,))
    restored = plan_from_dict(plan_to_dict(plan))
    n = restored.nodes[0]
    assert n.grounds_state == "ungrounded"
    assert n.grounds_note == "Library is silent on serializer choice"
    assert n.amended_from == "n3-old"
    assert n.amended_reason == "Old approach used orjson which added a dep"
    assert n.depends_on == ("n1",)
    assert n.applicable_checks[0].provenance == "from_topic"


def test_plan_round_trips_conflicted_node():
    node = PlanNode(
        id="n5",
        level="structural",
        decision="Choose caching strategy",
        approach="In-process LRU",
        grounds=("p10", "p11"),
        grounds_state="conflicted",
        conflict_resolution="p10 wins — it applies to read-heavy workloads specifically",
    )
    plan = Plan(plan_id="aabbcc", task="Cache things", version=1, nodes=(node,))
    restored = plan_from_dict(plan_to_dict(plan))
    n = restored.nodes[0]
    assert n.grounds_state == "conflicted"
    assert n.conflict_resolution.startswith("p10 wins")
    assert n.grounds == ("p10", "p11")
