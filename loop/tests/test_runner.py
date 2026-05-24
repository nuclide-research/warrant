import json
import subprocess
from pathlib import Path
import pytest
from loop.runner import WarrantRunner
from loop.worktree import WorktreeManager
from loop import runstore
from loop.models import ExecutorResult, CitationReport
from tests.fakes import (
    FakeLLM, FakeInvoker, FakeVerifierInvoker,
    FakeReranker, FakeEmbedder, make_fixture_index,
    make_pass_verifier_result,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path,
                   check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path,
                   check=True, capture_output=True)


def _make_runner(tmp_path, llm, invoker, verifier_invoker=None, index=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    out_dir = tmp_path / "out"
    return WarrantRunner(
        index=index or make_fixture_index(2),
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        llm=llm,
        invoker=invoker,
        verifier_invoker=verifier_invoker or FakeVerifierInvoker(),
        worktree_mgr=WorktreeManager(),
        base_repo=repo,
        out_dir=out_dir,
        global_iteration_cap=5,
        per_node_attempt_cap=2,
        watchdog_timeout=30.0,
        verify_iteration_cap=2,
    ), repo


def test_run_returns_done_run_state(tmp_path):
    llm = FakeLLM()
    llm.queue("I am a specialist.")
    llm.queue("query 1\nquery 2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Use Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    verifier = FakeVerifierInvoker()
    runner, repo = _make_runner(tmp_path, llm, invoker, verifier)
    final_rs, report = runner.run("build a cache layer")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert final_rs.phase == "done"


def test_run_all_nodes_done(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    final_rs, report = runner.run("build something")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    done = all(
        ns.status in ("done", "failed")
        for ns in final_rs.node_statuses.values()
    )
    assert done


def test_run_creates_run_files(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    runner, _ = _make_runner(tmp_path, llm, invoker)
    out_dir = tmp_path / "out"
    final_rs, report = runner.run("build")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert list(out_dir.glob("run.v*.json"))


def test_run_returns_citation_report(tmp_path):
    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1\nq2")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))
    invoker = FakeInvoker()
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done",
    ))
    verifier = FakeVerifierInvoker()
    verifier.queue(make_pass_verifier_result("n1"))
    runner, _ = _make_runner(tmp_path, llm, invoker, verifier)
    final_rs, report = runner.run("build something")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass
    assert isinstance(report, CitationReport)
    assert report.tier1_failed_integrity == 0
    assert report.node_verdicts.get("n1") in ("pass", "unverified")


def test_run_verify_routes_back_and_retries(tmp_path):
    """Node fails verify (integrity), gets re-executed, then passes verify."""
    from loop.models import VerifierResult, VerifierCheckOutcome

    llm = FakeLLM()
    llm.queue("specialist")
    llm.queue("q1")
    llm.queue(json.dumps([{"id": "n1", "decision": "Do X", "approach": "Y",
                           "grounds": []}]))

    invoker = FakeInvoker()
    # First execute: done
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done attempt 1",
    ))
    # Second execute (after verify routes back): done
    invoker.queue(ExecutorResult(
        node_id="n1", status="done",
        checks_run=[], principles_honored=[], principles_violated=[],
        amendments=[], summary="done attempt 2",
    ))

    # First verify: integrity failure -> routes back to pending
    fail_co = VerifierCheckOutcome(
        check_id="c1", provenance="from_grounds", tier=1,
        passed=False, metric_value="", judgment="",
    )
    fail_vr = VerifierResult(
        node_id="n1", verdict="fail", confidence=0.2,
        check_outcomes=[fail_co], integrity_verdict="integrity_failure",
        summary="failed",
    )
    # Second verify: pass
    pass_vr = make_pass_verifier_result("n1")

    verifier = FakeVerifierInvoker()
    verifier.queue(fail_vr)
    verifier.queue(pass_vr)

    runner, _ = _make_runner(
        tmp_path, llm, invoker, verifier,
    )
    final_rs, report = runner.run("build with retries")
    try:
        WorktreeManager().remove(Path(final_rs.worktree_path))
    except Exception:
        pass

    assert report.node_verdicts.get("n1") == "pass"
