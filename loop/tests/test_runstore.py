import json
from pathlib import Path
import pytest
from loop.models import RunState, NodeStatus, ExecutorResult, CheckResult
from loop import runstore


def _make_run_state(**overrides) -> RunState:
    defaults = dict(
        run_id="run-abc",
        plan_id="plan-xyz",
        plan_version=1,
        worktree_path="/tmp/wt",
        phase="orient",
        node_statuses={},
        anchored_direction="#DIRECTION: build",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
        iteration=0,
    )
    defaults.update(overrides)
    return RunState(**defaults)


def test_save_and_load_roundtrip(tmp_path):
    rs = _make_run_state()
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    assert loaded.run_id == rs.run_id
    assert loaded.plan_id == rs.plan_id
    assert loaded.phase == rs.phase


def test_save_sets_updated_at(tmp_path):
    rs = _make_run_state()
    runstore.save_run(rs, tmp_path)
    assert rs.updated_at != ""


def test_save_filename_uses_iteration(tmp_path):
    rs = _make_run_state(iteration=3)
    path = runstore.save_run(rs, tmp_path)
    assert path.name == "run.v3.json"


def test_load_latest_returns_highest_version(tmp_path):
    for i in range(3):
        rs = _make_run_state(iteration=i)
        runstore.save_run(rs, tmp_path)
    latest = runstore.load_latest_run(tmp_path)
    assert latest.iteration == 2


def test_load_latest_raises_when_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        runstore.load_latest_run(tmp_path)


def test_node_status_roundtrip(tmp_path):
    rs = _make_run_state(node_statuses={
        "n1": NodeStatus(node_id="n1", status="done", attempts=1)
    })
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    assert loaded.node_statuses["n1"].status == "done"
    assert loaded.node_statuses["n1"].attempts == 1


def test_executor_result_nested_roundtrip(tmp_path):
    result = ExecutorResult(
        node_id="n1", status="done",
        checks_run=[CheckResult(check_id="c1", provenance="from_grounds", passed=True)],
        principles_honored=["p1"], principles_violated=[],
        amendments=[], summary="done",
    )
    rs = _make_run_state(node_statuses={
        "n1": NodeStatus(node_id="n1", status="done", last_result=result)
    })
    runstore.save_run(rs, tmp_path)
    loaded = runstore.load_run(tmp_path / "run.v0.json")
    lr = loaded.node_statuses["n1"].last_result
    assert lr is not None
    assert lr.checks_run[0].check_id == "c1"
