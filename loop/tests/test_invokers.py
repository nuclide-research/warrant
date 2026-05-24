import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from loop.skill.invokers import ClaudeCodeLLM, ClaudeCodeInvoker, ClaudeCodeVerifierInvoker
from loop.models import ExecutorResult, VerifierResult


def _make_proc(stdout="", returncode=0, stderr=""):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = stderr
    return m


class TestClaudeCodeLLM:
    def test_llm_returns_stripped_stdout(self):
        with patch("subprocess.run", return_value=_make_proc("  hello  ")):
            result = ClaudeCodeLLM()("any prompt")
        assert result == "hello"

    def test_llm_raises_on_nonzero(self):
        with patch("subprocess.run", return_value=_make_proc(returncode=1, stderr="oops")):
            with pytest.raises(RuntimeError):
                ClaudeCodeLLM()("any prompt")

    def test_llm_raises_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120.0)):
            with pytest.raises(RuntimeError):
                ClaudeCodeLLM()("any prompt")


class TestClaudeCodeInvoker:
    def test_executor_invoker_parses_json(self):
        payload = json.dumps({
            "node_id": "n1",
            "status": "done",
            "checks_run": [],
            "principles_honored": ["p1"],
            "principles_violated": [],
            "amendments": [],
            "summary": "completed successfully",
        })
        with patch("subprocess.run", return_value=_make_proc(payload)):
            result = ClaudeCodeInvoker().invoke("prompt")
        assert isinstance(result, ExecutorResult)
        assert result.node_id == "n1"
        assert result.status == "done"
        assert result.principles_honored == ["p1"]

    def test_executor_invoker_handles_fenced_json(self):
        payload = json.dumps({
            "node_id": "n2",
            "status": "done",
            "checks_run": [],
            "principles_honored": [],
            "principles_violated": [],
            "amendments": [],
            "summary": "fenced ok",
        })
        fenced = f"```json\n{payload}\n```"
        with patch("subprocess.run", return_value=_make_proc(fenced)):
            result = ClaudeCodeInvoker().invoke("prompt")
        assert result.node_id == "n2"
        assert result.status == "done"

    def test_executor_invoker_returns_failed_on_bad_json(self):
        with patch("subprocess.run", return_value=_make_proc("just some prose, not json")):
            result = ClaudeCodeInvoker().invoke("prompt")
        assert result.status == "failed"


class TestClaudeCodeVerifierInvoker:
    def test_verifier_invoker_parses_json(self):
        payload = json.dumps({
            "node_id": "n1",
            "verdict": "pass",
            "confidence": 0.95,
            "check_outcomes": [],
            "integrity_verdict": "clean",
            "summary": "all checks passed",
        })
        with patch("subprocess.run", return_value=_make_proc(payload)):
            result = ClaudeCodeVerifierInvoker().invoke("prompt")
        assert isinstance(result, VerifierResult)
        assert result.node_id == "n1"
        assert result.verdict == "pass"
        assert result.integrity_verdict == "clean"

    def test_verifier_invoker_returns_clean_on_bad_json(self):
        with patch("subprocess.run", return_value=_make_proc("not json at all")):
            result = ClaudeCodeVerifierInvoker().invoke("prompt")
        assert result.integrity_verdict == "clean"
