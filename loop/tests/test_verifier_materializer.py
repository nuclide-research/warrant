from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from loop.verifier_materializer import materialize_verifier
from loop.models import RunState, NodeStatus, ExecutorResult
from agent.plan import PlanNode, ApplicableCheck
from tests.fakes import make_fixture_principle
from librarian.query import Result
import numpy as np


def _make_result(principle) -> Result:
    return Result(principle=principle, citation=principle.citation, score=1.0, neighbors=[])


def _make_run_state() -> RunState:
    return RunState(
        run_id="r1", plan_id="p1", plan_version=1,
        worktree_path="/tmp/fake", phase="execute",
        node_statuses={},
        anchored_direction="#DIRECTION: build a cache layer",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: be honest",
    )


def _make_executor_result(node_id: str = "n1") -> ExecutorResult:
    return ExecutorResult(
        node_id=node_id, status="done",
        checks_run=[], principles_honored=["p1"],
        principles_violated=[], amendments=[],
        summary="implemented cache layer",
    )


def _make_clean_node(pid: str = "test-book:ch1:s1") -> PlanNode:
    return PlanNode(
        id="n1", level="architectural",
        decision="Implement caching", approach="Use an LRU dict",
        grounds=(pid,), grounds_state="clean",
    )


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path,
                   check=True, capture_output=True)
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path,
                   check=True, capture_output=True)
    return tmp_path


def test_contains_anchored_direction():
    p = make_fixture_principle("test-book:ch1:s1")
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "#DIRECTION: build a cache layer" in prompt


def test_contains_honesty_constraint():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "#HONESTY-CONSTRAINT: be honest" in prompt


def test_contains_verifier_role_section():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "You are a Verifier" in prompt


def test_contains_node_decision_and_approach():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Implement caching" in prompt
    assert "Use an LRU dict" in prompt


def test_grounding_includes_tier():
    p = make_fixture_principle("test-book:ch1:s1", "Prefer composition.")
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node("test-book:ch1:s1"), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Tier" in prompt
    assert "Prefer composition." in prompt


def test_missing_principle_noted():
    p = make_fixture_principle("test-book:ch1:s1")
    node = PlanNode(
        id="n1", level="architectural",
        decision="Do X", approach="Use Y",
        grounds=("test-book:ch1:s1", "missing-id"),
        grounds_state="clean",
    )
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=node, principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "Missing principles" in prompt
    assert "missing-id" in prompt


def test_executor_self_report_included():
    p = make_fixture_principle()
    rs = _make_run_state()
    exec_result = ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=["p1"],
        principles_violated=["p2"], amendments=[],
        summary="implemented cache layer",
    )
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=exec_result,
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "implemented cache layer" in prompt
    assert "Executor's self-report" in prompt


def test_diff_section_present_no_sha(git_repo):
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha="",
    )
    assert "Code diff" in prompt


def test_diff_shows_new_file(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    (git_repo / "cache.py").write_text("def lru(): pass\n")
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "cache.py" in prompt


def test_diff_no_changes_message(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "No changes detected" in prompt


def test_return_format_schema_present():
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path="/tmp/fake", all_nodes={},
    )
    assert "integrity_verdict" in prompt
    assert "Return format" in prompt


def test_diff_truncated_at_8000(git_repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    (git_repo / "big.py").write_text("x = 1\n" * 2000)  # ~14000 chars
    p = make_fixture_principle()
    rs = _make_run_state()
    prompt = materialize_verifier(
        node=_make_clean_node(), principles=[_make_result(p)],
        run_state=rs, executor_result=_make_executor_result(),
        worktree_path=str(git_repo), all_nodes={},
        pre_execution_sha=sha,
    )
    assert "truncated" in prompt
