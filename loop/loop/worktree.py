from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    pass


@dataclass
class WorktreeInfo:
    path: str
    branch: str
    commit: str


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise WorktreeError(result.stderr.strip())
    return result.stdout


def _parse_porcelain(output: str) -> list[WorktreeInfo]:
    worktrees: list[WorktreeInfo] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(_wt_from_dict(current))
            current = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            current["commit"] = line[len("HEAD "):]
        elif line.startswith("branch refs/heads/"):
            current["branch"] = line[len("branch refs/heads/"):]
        elif line == "bare":
            current["branch"] = "(bare)"
        elif line == "detached":
            current["branch"] = "(detached)"
    if current:
        worktrees.append(_wt_from_dict(current))
    return worktrees


def _wt_from_dict(d: dict[str, str]) -> WorktreeInfo:
    return WorktreeInfo(
        path=d.get("path", ""),
        branch=d.get("branch", "(unknown)"),
        commit=d.get("commit", ""),
    )


class WorktreeManager:
    def create(self, base_repo: Path, branch: str) -> Path:
        slug = branch.replace("/", "-")
        wt_path = base_repo.parent / f"warrant-wt-{slug}"
        _run(["git", "worktree", "add", "-b", branch, str(wt_path)], cwd=base_repo)
        return wt_path

    def remove(self, path: Path) -> None:
        base_repo = self._main_repo(path)
        _run(["git", "worktree", "remove", "--force", str(path)], cwd=base_repo)

    def list_worktrees(self, base_repo: Path) -> list[WorktreeInfo]:
        out = _run(["git", "worktree", "list", "--porcelain"], cwd=base_repo)
        return _parse_porcelain(out)

    def _main_repo(self, worktree_path: Path) -> Path:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=worktree_path, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise WorktreeError(f"not a git repository: {result.stderr.strip()}")
        common = (worktree_path / Path(result.stdout.strip())).resolve()
        # common dir is .git inside main repo
        return common.parent
