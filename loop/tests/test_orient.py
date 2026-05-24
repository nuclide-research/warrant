import subprocess
from pathlib import Path
import pytest
from loop.phases.orient import orient, OrientResult
from loop.worktree import WorktreeManager
from tests.fakes import FakeLLM, make_fixture_index


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_orient_returns_orient_result(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("I am a software engineering specialist.")
    llm.queue("query one\nquery two\nquery three")
    mgr = WorktreeManager()
    result = orient("build a cache", make_fixture_index(), llm, mgr, repo, "abc12345")
    assert isinstance(result, OrientResult)
    # cleanup
    WorktreeManager().remove(Path(result.worktree_path))


def test_orient_anchored_direction_prefix(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("specialist persona")
    llm.queue("q1\nq2\nq3")
    mgr = WorktreeManager()
    result = orient("build a cache", make_fixture_index(), llm, mgr, repo, "abc12345")
    assert result.anchored_direction.startswith("#DIRECTION:")
    assert "build a cache" in result.anchored_direction
    WorktreeManager().remove(Path(result.worktree_path))


def test_orient_honesty_constraint_prefix(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2\nq3")
    mgr = WorktreeManager()
    result = orient("build a thing", make_fixture_index(), llm, mgr, repo, "run99")
    assert result.anchored_honesty_constraint.startswith("#HONESTY-CONSTRAINT:")
    WorktreeManager().remove(Path(result.worktree_path))


def test_orient_queries_capped_at_five(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2\nq3\nq4\nq5\nq6\nq7")
    mgr = WorktreeManager()
    result = orient("direction", make_fixture_index(), llm, mgr, repo, "run01")
    assert len(result.retrieval_queries) <= 5
    WorktreeManager().remove(Path(result.worktree_path))


def test_orient_creates_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    llm = FakeLLM()
    llm.queue("persona")
    llm.queue("q1\nq2")
    mgr = WorktreeManager()
    result = orient("direction", make_fixture_index(), llm, mgr, repo, "wt-test-01")
    assert Path(result.worktree_path).exists()
    WorktreeManager().remove(Path(result.worktree_path))
