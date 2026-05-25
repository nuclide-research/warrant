from __future__ import annotations
import json
import re

import anthropic

from loop.models import (
    CheckResult,
    ExecutorResult,
    NodeAmendment,
    VerifierCheckOutcome,
    VerifierResult,
)
from .sandbox import WorktreeSandbox


TOOL_DEFS: list[dict] = [
    {
        "name": "bash",
        "description": "Run a shell command in the project worktree.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the worktree (path relative to worktree root).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the worktree.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List directory contents (path relative to worktree root, default '.').",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
]

VERIFIER_TOOL_DEFS: list[dict] = [
    TOOL_DEFS[0],  # bash
    TOOL_DEFS[1],  # read_file
    TOOL_DEFS[3],  # list_directory  (no write_file — verifier is read-only)
]

_EXECUTOR_SYSTEM = (
    "You are an autonomous coding agent implementing a plan node in a git worktree. "
    "Use the provided tools to read files, run tests, and write code. "
    "When the work is complete, output a single JSON object matching the schema "
    "in the prompt and nothing else — no prose before or after the JSON."
)

_VERIFIER_SYSTEM = (
    "You are a Verifier. You did not write the code under review and you have not "
    "seen the Executor's reasoning. Use the tools to inspect files and run checks. "
    "Grade strictly against the cited principles. "
    "When grading is complete, output a single JSON object matching the schema "
    "in the prompt and nothing else."
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


def _dispatch_tool(name: str, inp: dict, sandbox: WorktreeSandbox) -> str:
    """Route a tool_use block to the sandbox. ValueError from path escape returns as error string."""
    try:
        if name == "bash":
            return sandbox.bash(inp["command"])
        elif name == "read_file":
            return sandbox.read_file(inp["path"])
        elif name == "write_file":
            return sandbox.write_file(inp["path"], inp["content"])
        elif name == "list_directory":
            return sandbox.list_directory(inp.get("path", "."))
        return f"unknown tool: {name}"
    except ValueError as exc:
        return f"error: {exc}"


class AnthropicLLM:
    """Callable LLM for Orient and Plan phases — single-turn, no tool use."""

    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    def __call__(self, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            text_block = next(
                (b for b in response.content if getattr(b, "type", None) == "text"),
                None,
            )
            if text_block is None:
                raise RuntimeError("no text block in response")
            return text_block.text.strip()
        except Exception as exc:
            raise RuntimeError(f"anthropic API error: {exc}") from exc


class AnthropicInvoker:
    """Executor Invoker: multi-turn Anthropic API conversation with tool use."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str,
        max_tool_rounds: int = 50,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tool_rounds = max_tool_rounds

    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult:
        m = re.search(r"^## Working directory\n(.+)$", prompt, re.MULTILINE)
        worktree_path = m.group(1).strip() if m else "."
        sandbox = WorktreeSandbox(worktree_path)
        messages: list[dict] = [{"role": "user", "content": prompt}]

        try:
            for _ in range(self._max_tool_rounds):
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=8192,
                    system=_EXECUTOR_SYSTEM,
                    tools=TOOL_DEFS,
                    messages=messages,
                )

                if response.stop_reason == "end_turn":
                    text = next(
                        (
                            b.text
                            for b in response.content
                            if getattr(b, "type", None) == "text"
                        ),
                        "",
                    )
                    raw = _extract_json(text)
                    d = json.loads(raw)
                    return ExecutorResult(
                        node_id=d["node_id"],
                        status=d["status"],
                        checks_run=[CheckResult(**c) for c in d.get("checks_run", [])],
                        principles_honored=d.get("principles_honored", []),
                        principles_violated=d.get("principles_violated", []),
                        amendments=[
                            NodeAmendment(**a) for a in d.get("amendments", [])
                        ],
                        summary=d.get("summary", ""),
                    )

                tool_results: list[dict] = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        result_str = _dispatch_tool(block.name, block.input, sandbox)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            }
                        )
                if not tool_results:
                    break  # stop_reason was max_tokens/stop_sequence — exit loop, return failed
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            return ExecutorResult(
                node_id="unknown",
                status="failed",
                checks_run=[],
                principles_honored=[],
                principles_violated=[],
                amendments=[],
                summary="max tool rounds exceeded",
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


class AnthropicVerifierInvoker:
    """VerifierInvoker: multi-turn Anthropic API conversation with read-only tools."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str,
        max_tool_rounds: int = 50,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tool_rounds = max_tool_rounds

    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult:
        m = re.search(r"^## Working directory\n(.+)$", prompt, re.MULTILINE)
        worktree_path = m.group(1).strip() if m else "."
        sandbox = WorktreeSandbox(worktree_path)
        messages: list[dict] = [{"role": "user", "content": prompt}]

        try:
            for _ in range(self._max_tool_rounds):
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=8192,
                    system=_VERIFIER_SYSTEM,
                    tools=VERIFIER_TOOL_DEFS,
                    messages=messages,
                )

                if response.stop_reason == "end_turn":
                    text = next(
                        (
                            b.text
                            for b in response.content
                            if getattr(b, "type", None) == "text"
                        ),
                        "",
                    )
                    raw = _extract_json(text)
                    d = json.loads(raw)
                    return VerifierResult(
                        node_id=d["node_id"],
                        verdict=d["verdict"],
                        confidence=d.get("confidence", 1.0),
                        check_outcomes=[
                            VerifierCheckOutcome(**c)
                            for c in d.get("check_outcomes", [])
                        ],
                        integrity_verdict=d["integrity_verdict"],
                        summary=d.get("summary", ""),
                    )

                tool_results: list[dict] = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        result_str = _dispatch_tool(block.name, block.input, sandbox)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            }
                        )
                if not tool_results:
                    break  # stop_reason was max_tokens/stop_sequence — exit loop, return failed
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            return VerifierResult(
                node_id="unknown",
                verdict="fail",
                confidence=0.0,
                check_outcomes=[],
                integrity_verdict="clean",
                summary="max tool rounds exceeded",
            )
        except Exception as exc:
            return VerifierResult(
                node_id="unknown",
                verdict="fail",
                confidence=0.0,
                check_outcomes=[],
                integrity_verdict="clean",
                summary=str(exc),
            )
