from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_path_prefix_sibling_rejected(self, tmp_path):
        sandbox = WorktreeSandbox(str(tmp_path))
        # A sibling path whose string starts with the root string (e.g. /tmp/abcevil vs /tmp/abc)
        # must be rejected even though startswith would accept it.
        sibling = tmp_path.parent / (tmp_path.name + "evil")
        sibling.mkdir(exist_ok=True)
        (sibling / "file.txt").write_text("data")
        with pytest.raises(ValueError):
            sandbox.read_file(f"../{tmp_path.name}evil/file.txt")


from loop.api.invokers import AnthropicLLM


def _make_text_block(text: str):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _make_response(stop_reason: str, content: list):
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = content
    return r


class TestAnthropicLLM:
    def test_llm_returns_stripped_text(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block("  hello world  ")]
        )
        llm = AnthropicLLM(mock_client, "claude-sonnet-4-6")
        result = llm("some prompt")
        assert result == "hello world"

    def test_llm_raises_on_api_error(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("api connection failed")
        llm = AnthropicLLM(mock_client, "claude-sonnet-4-6")
        with pytest.raises(RuntimeError):
            llm("some prompt")
