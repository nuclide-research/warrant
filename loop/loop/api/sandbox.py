from __future__ import annotations
import subprocess
from pathlib import Path


class WorktreeSandbox:
    """Executes bash and file operations constrained to a git worktree directory."""

    def __init__(self, worktree_path: str) -> None:
        self._root = Path(worktree_path).resolve()

    def _resolve(self, path: str) -> Path:
        resolved = (self._root / path).resolve()
        if not str(resolved).startswith(str(self._root)):
            raise ValueError(
                f"path escape rejected: {path!r} resolves outside worktree {self._root}"
            )
        return resolved

    def bash(self, cmd: str, timeout: float = 60.0) -> str:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output = output + result.stderr if output else result.stderr
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output
        except subprocess.TimeoutExpired:
            return f"[exit code: timeout after {timeout}s]"
        except Exception as exc:
            return f"[error: {exc}]"

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"written {len(content)} chars to {path}"

    def list_directory(self, path: str = ".") -> str:
        p = self._resolve(path)
        entries = sorted(p.iterdir(), key=lambda e: e.name)
        return "\n".join(e.relative_to(self._root).as_posix() for e in entries)
