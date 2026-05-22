"""
End-to-end: build a plan through the full lifecycle the agent loop drives.

Scenario:
  1. Agent starts a new plan for a task.
  2. It adds an architectural node (clean, grounded).
  3. It adds a structural node (conflicted — two principles disagree).
  4. It adds an implementation node (ungrounded — library silent).
  5. It adds a second implementation node that depends on the first.
  6. It amends the ungrounded node after discovering a principle.
  7. It bumps the version and saves.
  8. It loads the latest version from disk.
  9. Asserts the whole state is intact, including amendment metadata.
  10. Asserts that the two implementation nodes are NOT independent siblings.
  11. Asserts that architectural + structural nodes are NOT independent
      (the structural node depends on the architectural one).
"""
import json

from agent.plan import ApplicableCheck, PlanNode
from agent.planops import (
    add_node,
    amend_node,
    children,
    find_node,
    independent_siblings,
    new_plan,
    next_version,
)
from agent.planstore import load_latest, save_plan


def test_full_agent_loop_lifecycle(tmp_path):
    # 1. Start a new plan
    plan = new_plan("Implement a rate-limiting middleware")
    assert plan.version == 1
    assert plan.nodes == ()

    # 2. Architectural node — clean grounding
    arch_check = ApplicableCheck(check="rate-limit-header-present", provenance="from_grounds")
    arch_node = PlanNode(
        id="arch-1",
        level="architectural",
        decision="Rate limiting enforced at the API gateway layer",
        approach="Token-bucket algorithm, one bucket per client API key",
        grounds=("p-rate-limit-gateway", "p-token-bucket-fairness"),
        grounds_state="clean",
        applicable_checks=(arch_check,),
        children=("struct-1", "impl-1"),
    )
    plan = add_node(plan, arch_node)
    assert len(plan.nodes) == 1

    # 3. Structural node — conflicted grounding
    struct_node = PlanNode(
        id="struct-1",
        level="structural",
        decision="Store bucket state in Redis",
        approach="Redis INCR + EXPIRE; no in-process state",
        grounds=("p-distributed-state", "p-single-process-simplicity"),
        grounds_state="conflicted",
        conflict_resolution=(
            "p-distributed-state wins: horizontal scaling is a stated requirement "
            "and single-process state breaks under multiple gateway instances"
        ),
        depends_on=("arch-1",),
    )
    plan = add_node(plan, struct_node)

    # 4. Implementation node — ungrounded; library was silent
    impl_node_1 = PlanNode(
        id="impl-1",
        level="implementation",
        decision="Choose Redis client library",
        approach="Use redis-py; it is the de-facto Python client",
        grounds=(),
        grounds_state="ungrounded",
        grounds_note=(
            "None of the indexed books address Python Redis client selection; "
            "redis-py is chosen by convention"
        ),
        depends_on=("struct-1",),
    )
    plan = add_node(plan, impl_node_1)

    # 5. Second implementation node — depends on impl-1
    impl_node_2 = PlanNode(
        id="impl-2",
        level="implementation",
        decision="Expose current bucket state via /metrics",
        approach="Prometheus counter per bucket, scraped every 15s",
        grounds=("p-observability-first",),
        grounds_state="clean",
        depends_on=("impl-1",),
    )
    plan = add_node(plan, impl_node_2)
    assert len(plan.nodes) == 4

    # 6. Amend impl-1: agent found a relevant principle mid-run
    plan = amend_node(
        plan,
        "impl-1",
        "Librarian found p-client-library-stability after initial planning",
        grounds=("p-client-library-stability",),
        grounds_state="clean",
        grounds_note="",
        approach="Use redis-py: grounded in p-client-library-stability (maintenance + adoption)",
    )
    amended = find_node(plan, "impl-1")
    assert amended is not None
    assert amended.grounds_state == "clean"
    assert amended.grounds == ("p-client-library-stability",)
    assert amended.amended_from == "impl-1"
    assert amended.amended_reason == "Librarian found p-client-library-stability after initial planning"
    assert amended.grounds_note == ""

    # 7. Bump version and save
    plan = next_version(plan)
    assert plan.version == 2
    save_plan(plan, tmp_path)
    assert (tmp_path / "plan.v2.json").exists()

    # Verify the JSON is well-formed and readable
    raw = json.loads((tmp_path / "plan.v2.json").read_text())
    assert raw["version"] == 2
    assert len(raw["nodes"]) == 4

    # 8. Load latest from disk
    loaded = load_latest(tmp_path)
    assert loaded.version == 2
    assert loaded.plan_id == plan.plan_id
    assert loaded.task == "Implement a rate-limiting middleware"
    assert len(loaded.nodes) == 4

    # 9. Full state integrity check on loaded plan
    loaded_arch = find_node(loaded, "arch-1")
    assert loaded_arch is not None
    assert loaded_arch.grounds_state == "clean"
    assert loaded_arch.applicable_checks[0].check == "rate-limit-header-present"
    assert loaded_arch.applicable_checks[0].provenance == "from_grounds"

    loaded_struct = find_node(loaded, "struct-1")
    assert loaded_struct is not None
    assert loaded_struct.grounds_state == "conflicted"
    assert loaded_struct.conflict_resolution.startswith("p-distributed-state wins")

    loaded_impl1 = find_node(loaded, "impl-1")
    assert loaded_impl1 is not None
    assert loaded_impl1.grounds_state == "clean"
    assert loaded_impl1.amended_from == "impl-1"
    assert loaded_impl1.amended_reason != ""

    loaded_impl2 = find_node(loaded, "impl-2")
    assert loaded_impl2 is not None
    assert loaded_impl2.depends_on == ("impl-1",)

    # 10. impl-1 and impl-2 are NOT independent siblings (impl-2 depends on impl-1)
    assert independent_siblings(loaded, ["impl-1", "impl-2"]) is False

    # 11. arch-1 and struct-1 are NOT independent: struct-1 depends on arch-1.
    assert independent_siblings(loaded, ["arch-1", "struct-1"]) is False

    # struct-1 and impl-2 — impl-2.depends_on = impl-1 (not in the set), so independent
    assert independent_siblings(loaded, ["struct-1", "impl-2"]) is True

    # 12. children() resolves arch-1's children references
    arch_children = children(loaded, loaded_arch)
    arch_child_ids = {n.id for n in arch_children}
    # arch-1.children = ("struct-1", "impl-1"); both exist in the plan
    assert arch_child_ids == {"struct-1", "impl-1"}
