from __future__ import annotations
import json
import re
import subprocess

from loop.models import (
    CheckResult, ExecutorResult, NodeAmendment,
    VerifierCheckOutcome, VerifierResult,
)


def _extract_json(text: str) -> str:
    """Strip markdown fences; fall back to first-{ last-} extraction."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


_LLM_TIMEOUT = 120.0


class ClaudeCodeLLM:
    """Callable LLM that invokes `claude -p <prompt>` and returns stripped stdout."""

    def __call__(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=_LLM_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude timed out after {_LLM_TIMEOUT}s")
        if result.returncode != 0:
            raise RuntimeError(
                f"claude exited {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout.strip()


class ClaudeCodeInvoker:
    """Executor Invoker protocol impl: calls claude -p, parses ExecutorResult JSON."""

    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"claude exited {result.returncode}: {result.stderr.strip()}"
                )
            raw = _extract_json(result.stdout)
            d = json.loads(raw)
            return ExecutorResult(
                node_id=d["node_id"],
                status=d["status"],
                checks_run=[CheckResult(**c) for c in d.get("checks_run", [])],
                principles_honored=d.get("principles_honored", []),
                principles_violated=d.get("principles_violated", []),
                amendments=[NodeAmendment(**a) for a in d.get("amendments", [])],
                summary=d.get("summary", ""),
            )
        except Exception as exc:
            return ExecutorResult(
                node_id="unknown",
                status="failed",
                checks_run=[],
                principles_honored=[],
                principles_violated=[],
                amendments=[],
                summary=str(exc),
            )


class ClaudeCodeVerifierInvoker:
    """VerifierInvoker protocol impl: calls claude -p, parses VerifierResult JSON."""

    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"claude exited {result.returncode}: {result.stderr.strip()}"
                )
            raw = _extract_json(result.stdout)
            d = json.loads(raw)
            return VerifierResult(
                node_id=d["node_id"],
                verdict=d["verdict"],
                confidence=d.get("confidence", 1.0),
                check_outcomes=[
                    VerifierCheckOutcome(**c) for c in d.get("check_outcomes", [])
                ],
                integrity_verdict=d["integrity_verdict"],
                summary=d.get("summary", ""),
            )
        except Exception as exc:
            # integrity_verdict="clean" prevents the verify loop from re-queuing
            # the node on invoker failure — same convention as phases/verify.py
            return VerifierResult(
                node_id="unknown",
                verdict="fail",
                confidence=0.0,
                check_outcomes=[],
                integrity_verdict="clean",
                summary=str(exc),
            )
