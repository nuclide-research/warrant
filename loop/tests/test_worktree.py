import subprocess
from pathlib import Path
import pytest
from loop.worktree import WorktreeManager, WorktreeError


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_create_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/abc12345")
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()
    # cleanup
    mgr.remove(wt_path)


def test_list_worktrees_includes_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    worktrees = mgr.list_worktrees(repo)
    paths = [w.path for w in worktrees]
    assert str(repo) in paths


def test_remove_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/cleanup-test")
    assert wt_path.exists()
    mgr.remove(wt_path)
    assert not wt_path.exists()


def test_create_duplicate_branch_raises(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    mgr = WorktreeManager()
    wt_path = mgr.create(repo, "warrant/dup-test")
    with pytest.raises(WorktreeError):
        mgr.create(repo, "warrant/dup-test")
    mgr.remove(wt_path)
