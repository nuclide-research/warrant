import json
import pytest
from agent.plan import ApplicableCheck, Plan, PlanNode
from agent.planstore import load_latest, load_version, plan_from_dict, plan_to_dict, save_plan


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


def _simple_plan(version: int = 1) -> Plan:
    node = PlanNode(
        id="n1",
        level="architectural",
        decision="Top-level decision",
        approach="Standard approach",
        grounds=("p1",),
        grounds_state="clean",
    )
    return Plan(plan_id="test-plan-001", task="Test task", version=version, nodes=(node,))


def test_save_plan_creates_versioned_file(tmp_path):
    plan = _simple_plan(version=1)
    save_plan(plan, tmp_path)
    expected = tmp_path / "plan.v1.json"
    assert expected.exists()


def test_save_plan_creates_out_dir_if_missing(tmp_path):
    target = tmp_path / "nested" / "plans"
    plan = _simple_plan(version=1)
    save_plan(plan, target)
    assert (target / "plan.v1.json").exists()


def test_save_plan_writes_valid_json(tmp_path):
    save_plan(_simple_plan(version=2), tmp_path)
    raw = (tmp_path / "plan.v2.json").read_text()
    parsed = json.loads(raw)
    assert parsed["version"] == 2
    assert parsed["plan_id"] == "test-plan-001"


def test_load_version_round_trips(tmp_path):
    original = _simple_plan(version=3)
    save_plan(original, tmp_path)
    loaded = load_version(tmp_path, 3)
    assert loaded.plan_id == original.plan_id
    assert loaded.version == 3
    assert loaded.nodes[0].id == "n1"


def test_load_version_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_version(tmp_path, 99)


def test_load_latest_returns_highest_version(tmp_path):
    save_plan(_simple_plan(version=1), tmp_path)
    save_plan(_simple_plan(version=3), tmp_path)
    save_plan(_simple_plan(version=2), tmp_path)
    latest = load_latest(tmp_path)
    assert latest.version == 3


def test_load_latest_raises_on_empty_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest(tmp_path)


def test_save_plan_file_is_human_readable(tmp_path):
    save_plan(_simple_plan(version=1), tmp_path)
    raw = (tmp_path / "plan.v1.json").read_text()
    # Indented JSON — must have newlines
    assert "\n" in raw
