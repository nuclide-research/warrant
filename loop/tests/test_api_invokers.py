from __future__ import annotations
import os
from pathlib import Path

import pytest

from loop.api.sandbox import WorktreeSandbox


class TestWorktreeSandbox:
    def test_bash_runs_in_worktree(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        result = sandbox.bash("pwd")
        assert str(tmp_path) in result

    def test_bash_captures_stderr_and_exit_code(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        result = sandbox.bash("ls /nonexistent_path_that_does_not_exist_xyz")
        assert "[exit code:" in result

    def test_bash_merges_stdout_and_stderr(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        result = sandbox.bash("echo out && ls /no_such_path_abc 2>&1 || true")
        assert "out" in result

    def test_read_file(self, tmp_path):
        (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
        sandbox = WorktreeSandbox(str(tmp_path))
        assert sandbox.read_file("hello.txt") == "world"

    def test_write_file(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        sandbox.write_file("sub/new.txt", "content")
        assert (tmp_path / "sub" / "new.txt").read_text(encoding="utf-8") == "content"

    def test_list_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("", encoding="utf-8")
        (tmp_path / "b.py").write_text("", encoding="utf-8")
        sandbox = WorktreeSandbox(str(tmp_path))
        result = sandbox.list_directory()
        assert "a.py" in result
        assert "b.py" in result

    def test_path_escape_raises(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        with pytest.raises(ValueError):
            sandbox.read_file("../../etc/passwd")

    def test_path_escape_in_write_raises(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        with pytest.raises(ValueError):
            sandbox.write_file("../outside.txt", "data")
