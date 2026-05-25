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


from loop.api.invokers import AnthropicInvoker, TOOL_DEFS
from loop.models import ExecutorResult, VerifierResult


def _make_tool_use_block(name: str, input_dict: dict, tool_id: str = "tid1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_dict
    b.id = tool_id
    return b


_EXECUTOR_RESULT_JSON = json.dumps({
    "node_id": "n1",
    "status": "done",
    "checks_run": [],
    "principles_honored": ["p1"],
    "principles_violated": [],
    "amendments": [],
    "summary": "completed",
})

_PROMPT_WITH_WD = "## Working directory\n/tmp/wt\n\n## Your task\nAdd caching"


class TestAnthropicInvoker:
    def test_end_turn_produces_executor_result(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block(_EXECUTOR_RESULT_JSON)]
        )
        invoker = AnthropicInvoker(mock_client, "claude-sonnet-4-6")
        result = invoker.invoke(_PROMPT_WITH_WD)
        assert isinstance(result, ExecutorResult)
        assert result.node_id == "n1"
        assert result.status == "done"
        assert result.principles_honored == ["p1"]

    def test_tool_loop_dispatches_to_sandbox(self, tmp_path):
        prompt = f"## Working directory\n{tmp_path}\n\n## Your task\nWrite a file"
        mock_client = MagicMock()
        tool_response = _make_response(
            "tool_use",
            [_make_tool_use_block("bash", {"command": "echo hi"}, "tid1")],
        )
        end_response = _make_response(
            "end_turn", [_make_text_block(_EXECUTOR_RESULT_JSON)]
        )
        mock_client.messages.create.side_effect = [tool_response, end_response]

        invoker = AnthropicInvoker(mock_client, "claude-sonnet-4-6")
        result = invoker.invoke(prompt)

        assert mock_client.messages.create.call_count == 2
        assert isinstance(result, ExecutorResult)
        assert result.status == "done"

    def test_max_rounds_returns_failed(self):
        mock_client = MagicMock()
        # Always return tool_use — never end_turn
        mock_client.messages.create.return_value = _make_response(
            "tool_use",
            [_make_tool_use_block("bash", {"command": "echo hi"})],
        )
        invoker = AnthropicInvoker(mock_client, "claude-sonnet-4-6", max_tool_rounds=3)
        result = invoker.invoke(_PROMPT_WITH_WD)

        assert result.status == "failed"
        assert "max tool rounds" in result.summary
        assert mock_client.messages.create.call_count == 3

    def test_bad_json_returns_failed(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block("this is just prose, not JSON")]
        )
        invoker = AnthropicInvoker(mock_client, "claude-sonnet-4-6")
        result = invoker.invoke(_PROMPT_WITH_WD)
        assert result.status == "failed"

    def test_missing_working_directory_uses_fallback(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block(_EXECUTOR_RESULT_JSON)]
        )
        invoker = AnthropicInvoker(mock_client, "claude-sonnet-4-6")
        # No ## Working directory section — should not crash
        result = invoker.invoke("## Your task\nDo something")
        assert isinstance(result, ExecutorResult)


from loop.api.invokers import AnthropicVerifierInvoker, VERIFIER_TOOL_DEFS


_VERIFIER_RESULT_JSON = json.dumps({
    "node_id": "n1",
    "verdict": "pass",
    "confidence": 0.95,
    "check_outcomes": [],
    "integrity_verdict": "clean",
    "summary": "all checks passed",
})


class TestAnthropicVerifierInvoker:
    def test_end_turn_produces_verifier_result(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block(_VERIFIER_RESULT_JSON)]
        )
        invoker = AnthropicVerifierInvoker(mock_client, "claude-sonnet-4-6")
        result = invoker.invoke(_PROMPT_WITH_WD)
        assert isinstance(result, VerifierResult)
        assert result.verdict == "pass"
        assert result.integrity_verdict == "clean"

    def test_bad_json_returns_clean_integrity_verdict(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "end_turn", [_make_text_block("not json at all")]
        )
        invoker = AnthropicVerifierInvoker(mock_client, "claude-sonnet-4-6")
        result = invoker.invoke(_PROMPT_WITH_WD)
        assert result.integrity_verdict == "clean"
        assert result.verdict == "fail"

    def test_verifier_tool_defs_exclude_write_file(self):
        names = {t["name"] for t in VERIFIER_TOOL_DEFS}
        assert "write_file" not in names
        assert "bash" in names
        assert "read_file" in names
        assert "list_directory" in names

    def test_max_rounds_returns_clean_integrity_verdict(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_response(
            "tool_use",
            [_make_tool_use_block("bash", {"command": "echo hi"})],
        )
        invoker = AnthropicVerifierInvoker(
            mock_client, "claude-sonnet-4-6", max_tool_rounds=2
        )
        result = invoker.invoke(_PROMPT_WITH_WD)
        assert result.integrity_verdict == "clean"
