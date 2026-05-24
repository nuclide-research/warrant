# Warrant Artifact B — Standalone CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone `warrant` CLI — a binary that runs the full Warrant loop using the Anthropic Python SDK directly, without requiring Claude Code.

**Architecture:** A new `loop/loop/api/` subpackage parallel to `loop/loop/skill/`. `WorktreeSandbox` executes bash/file tool calls constrained to the git worktree. `AnthropicInvoker` and `AnthropicVerifierInvoker` run multi-turn Anthropic API conversations with tool_use so Executor and Verifier agents can operate the worktree. The existing `WarrantRunner` is used unchanged.

**Tech Stack:** Python 3.11+, `anthropic>=0.25.0` Python SDK, existing `loop`/`agent`/`librarian` packages, pytest.

---

## File map

| Action | Path |
|--------|------|
| Create | `loop/loop/api/__init__.py` |
| Create | `loop/loop/api/sandbox.py` |
| Create | `loop/loop/api/invokers.py` |
| Create | `loop/loop/api/factory.py` |
| Create | `loop/loop/api/__main__.py` |
| Create | `loop/tests/test_api_invokers.py` |
| Create | `loop/tests/test_api_factory.py` |
| Create | `loop/tests/test_api_materializer.py` |
| Create | `.warrant/api-config.example.json` |
| Modify | `loop/loop/materializer.py` |
| Modify | `loop/loop/verifier_materializer.py` |
| Modify | `loop/pyproject.toml` |

---

### Task 1: WorktreeSandbox

**Files:**
- Create: `loop/loop/api/__init__.py`
- Create: `loop/loop/api/sandbox.py`
- Create: `loop/tests/test_api_invokers.py` (sandbox tests only)

The sandbox is the execution primitive for Artifact B. It constrains all file and shell operations to the git worktree directory.

- [ ] **Step 1: Create the test file with failing sandbox tests**

```python
# loop/tests/test_api_invokers.py
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'loop.api'`

- [ ] **Step 3: Create the package stub and implement WorktreeSandbox**

```python
# loop/loop/api/__init__.py
# (empty)
```

```python
# loop/loop/api/sandbox.py
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
```

- [ ] **Step 4: Run the sandbox tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add loop/loop/api/__init__.py loop/loop/api/sandbox.py loop/tests/test_api_invokers.py
git commit -m "feat(api): add WorktreeSandbox — bash/file ops constrained to worktree"
```

---

### Task 2: Tool definitions, `_extract_json`, and `AnthropicLLM`

**Files:**
- Create: `loop/loop/api/invokers.py` (partial — module-level constants + AnthropicLLM)
- Modify: `loop/tests/test_api_invokers.py` (add LLM tests)

This task builds the shared primitives that Task 3 and Task 4 depend on: the tool schema constants, the JSON-extraction helper, and the LLM callable used by Orient and Plan.

- [ ] **Step 1: Add failing LLM tests to the test file**

Append to `loop/tests/test_api_invokers.py`:

```python
import json
from unittest.mock import MagicMock, patch

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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicLLM -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'loop.api.invokers'`

- [ ] **Step 3: Create `invokers.py` with constants and AnthropicLLM**

```python
# loop/loop/api/invokers.py
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
```

- [ ] **Step 4: Add `anthropic` to pyproject.toml dev deps so the import works in tests**

Open `loop/pyproject.toml` and update the `dev` optional-dependency:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "anthropic>=0.25.0"]
```

Then install:

```bash
cd /home/cowboy/warrant && pip install -e loop/[dev] -q
```

- [ ] **Step 5: Run the LLM tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicLLM -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/ -q
```

Expected: all existing tests pass plus the 10 new ones.

- [ ] **Step 7: Commit**

```bash
git add loop/loop/api/invokers.py loop/tests/test_api_invokers.py loop/pyproject.toml
git commit -m "feat(api): add TOOL_DEFS, _extract_json, AnthropicLLM"
```

---

### Task 3: AnthropicInvoker

**Files:**
- Modify: `loop/loop/api/invokers.py` (append AnthropicInvoker class)
- Modify: `loop/tests/test_api_invokers.py` (append executor tests)

The executor invoker drives a multi-turn tool_use conversation. It reads the worktree path from the `## Working directory` section of the materialized prompt, creates a sandbox, and loops until Claude produces `end_turn`.

- [ ] **Step 1: Add failing executor tests**

Append to `loop/tests/test_api_invokers.py`:

```python
from loop.api.invokers import AnthropicInvoker, TOOL_DEFS


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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicInvoker -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` — `AnthropicInvoker` not defined yet.

- [ ] **Step 3: Append AnthropicInvoker to `loop/loop/api/invokers.py`**

Append after the `AnthropicLLM` class:

```python
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
```

- [ ] **Step 4: Run the executor tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicInvoker -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add loop/loop/api/invokers.py loop/tests/test_api_invokers.py
git commit -m "feat(api): add AnthropicInvoker — multi-turn executor tool loop"
```

---

### Task 4: AnthropicVerifierInvoker

**Files:**
- Modify: `loop/loop/api/invokers.py` (append AnthropicVerifierInvoker)
- Modify: `loop/tests/test_api_invokers.py` (append verifier tests)

Same loop structure as AnthropicInvoker but uses read-only tools, a different system prompt, and returns VerifierResult. Parse failure falls back to `integrity_verdict="clean"` to prevent routing loops.

- [ ] **Step 1: Add failing verifier tests**

Append to `loop/tests/test_api_invokers.py`:

```python
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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicVerifierInvoker -v 2>&1 | head -20
```

Expected: `ImportError` — `AnthropicVerifierInvoker` not defined yet.

- [ ] **Step 3: Append AnthropicVerifierInvoker to `loop/loop/api/invokers.py`**

Append after the `AnthropicInvoker` class:

```python
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
```

- [ ] **Step 4: Run the verifier tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py::TestAnthropicVerifierInvoker -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run the full api_invokers test suite**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_invokers.py -v
```

Expected: all 19 tests PASS (8 sandbox + 2 LLM + 5 executor + 4 verifier).

- [ ] **Step 6: Commit**

```bash
git add loop/loop/api/invokers.py loop/tests/test_api_invokers.py
git commit -m "feat(api): add AnthropicVerifierInvoker — read-only verifier tool loop"
```

---

### Task 5: ApiConfig, load_config, build_runner

**Files:**
- Create: `loop/loop/api/factory.py`
- Create: `loop/tests/test_api_factory.py`

The factory assembles a `WarrantRunner` from a config JSON. `ApiConfig` is a superset of `skill/factory.py`'s `Config` — it adds the Claude model names, API key, and `max_tool_rounds`. The `anthropic` import is lazy (inside `build_runner`) to give a clear error if not installed.

- [ ] **Step 1: Write the failing factory tests**

```python
# loop/tests/test_api_factory.py
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loop.api.factory import ApiConfig, load_config, build_runner
from loop.runner import WarrantRunner


def test_load_config_reads_all_fields(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
        "claude_model": "claude-opus-4-7",
        "claude_model_verifier": "claude-haiku-4-5-20251001",
        "anthropic_api_key": "sk-test-123",
        "max_tool_rounds": 20,
        "global_iteration_cap": 5,
        "per_node_attempt_cap": 2,
        "watchdog_timeout": 60.0,
        "max_parallel": 2,
        "max_principles": 8,
        "verify_iteration_cap": 2,
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))

    cfg = load_config(cfg_file)

    assert cfg.index_path == "/data/index"
    assert cfg.claude_model == "claude-opus-4-7"
    assert cfg.claude_model_verifier == "claude-haiku-4-5-20251001"
    assert cfg.anthropic_api_key == "sk-test-123"
    assert cfg.max_tool_rounds == 20
    assert cfg.global_iteration_cap == 5


def test_load_config_applies_defaults(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))

    cfg = load_config(cfg_file)

    assert cfg.claude_model == "claude-sonnet-4-6"
    assert cfg.claude_model_verifier == "claude-sonnet-4-6"
    assert cfg.anthropic_api_key is None
    assert cfg.max_tool_rounds == 50
    assert cfg.global_iteration_cap == 10
    assert cfg.per_node_attempt_cap == 3
    assert cfg.watchdog_timeout == 300.0
    assert cfg.max_parallel == 3
    assert cfg.max_principles == 15
    assert cfg.verify_iteration_cap == 3
    assert cfg.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.reranker_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_load_config_ignores_unknown_fields(tmp_path):
    data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/proj",
        "unknown_field_xyz": "ignored",
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(data))
    cfg = load_config(cfg_file)  # must not raise
    assert cfg.index_path == "/data/index"


def test_build_runner_wires_components(tmp_path):
    cfg = ApiConfig(
        index_path=str(tmp_path / "index"),
        out_dir=str(tmp_path / "runs"),
        base_repo=str(tmp_path / "repo"),
        claude_model="claude-sonnet-4-6",
        global_iteration_cap=7,
        per_node_attempt_cap=2,
        watchdog_timeout=60.0,
        max_parallel=2,
        max_principles=8,
        verify_iteration_cap=2,
        max_tool_rounds=10,
    )
    fake_index = MagicMock()
    # anthropic is lazily imported inside build_runner; patch it on the real module
    with patch("loop.api.factory.load_index", return_value=fake_index), \
         patch("loop.api.factory.Embedder") as mock_emb, \
         patch("loop.api.factory.Reranker") as mock_rnk, \
         patch("anthropic.Anthropic", return_value=MagicMock()):
        runner = build_runner(cfg)

    assert isinstance(runner, WarrantRunner)
    assert runner._cfg["global_iteration_cap"] == 7
    assert runner._cfg["per_node_attempt_cap"] == 2
    assert runner._cfg["watchdog_timeout"] == 60.0
    assert runner._cfg["max_parallel"] == 2
    assert runner._max_principles == 8
    assert runner._verify_iteration_cap == 2
    mock_emb.assert_called_once_with(cfg.model_name)
    mock_rnk.assert_called_once_with(cfg.reranker_name)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_factory.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'loop.api.factory'`

- [ ] **Step 3: Create `loop/loop/api/factory.py`**

```python
# loop/loop/api/factory.py
from __future__ import annotations
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from librarian.store import load_index
from librarian.embedding import Embedder
from librarian.query import Reranker

from ..runner import WarrantRunner
from ..worktree import WorktreeManager
from .invokers import AnthropicLLM, AnthropicInvoker, AnthropicVerifierInvoker


@dataclass
class ApiConfig:
    index_path: str
    out_dir: str
    base_repo: str
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    claude_model: str = "claude-sonnet-4-6"
    claude_model_verifier: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    max_tool_rounds: int = 50
    global_iteration_cap: int = 10
    per_node_attempt_cap: int = 3
    watchdog_timeout: float = 300.0
    max_parallel: int = 3
    max_principles: int = 15
    verify_iteration_cap: int = 3


def load_config(config_path: str | Path) -> ApiConfig:
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    known = {f.name for f in dataclasses.fields(ApiConfig)}
    filtered = {k: v for k, v in data.items() if k in known}
    return ApiConfig(**filtered)


def build_runner(config: ApiConfig) -> WarrantRunner:
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package required for the standalone CLI: "
            "pip install 'warrant[api]'"
        )
    index = load_index(config.index_path)
    embedder = Embedder(config.model_name)
    reranker = Reranker(config.reranker_name)
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    llm = AnthropicLLM(client, config.claude_model)
    invoker = AnthropicInvoker(client, config.claude_model, config.max_tool_rounds)
    verifier_invoker = AnthropicVerifierInvoker(
        client, config.claude_model_verifier, config.max_tool_rounds
    )
    worktree_mgr = WorktreeManager()
    return WarrantRunner(
        index=index,
        embedder=embedder,
        reranker=reranker,
        llm=llm,
        invoker=invoker,
        verifier_invoker=verifier_invoker,
        worktree_mgr=worktree_mgr,
        base_repo=Path(config.base_repo),
        out_dir=Path(config.out_dir),
        global_iteration_cap=config.global_iteration_cap,
        per_node_attempt_cap=config.per_node_attempt_cap,
        watchdog_timeout=config.watchdog_timeout,
        max_parallel=config.max_parallel,
        max_principles=config.max_principles,
        verify_iteration_cap=config.verify_iteration_cap,
    )
```

- [ ] **Step 4: Run the factory tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_factory.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add loop/loop/api/factory.py loop/tests/test_api_factory.py
git commit -m "feat(api): add ApiConfig, load_config, build_runner factory"
```

---

### Task 6: CLI entry point and `warrant` binary

**Files:**
- Create: `loop/loop/api/__main__.py`
- Modify: `loop/pyproject.toml`

The `warrant` binary installed on PATH. Same shape as `loop/loop/skill/__main__.py` but imports from `loop.api`.

- [ ] **Step 1: Write the failing CLI test**

Append to `loop/tests/test_api_factory.py`:

```python
import sys
from unittest.mock import MagicMock, patch
from loop.api import __main__ as api_main


def test_main_run_calls_runner(tmp_path):
    cfg_data = {
        "index_path": str(tmp_path / "index"),
        "out_dir": str(tmp_path / "runs"),
        "base_repo": str(tmp_path / "repo"),
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg_data))

    fake_runner = MagicMock()
    fake_run_state = MagicMock()
    fake_run_state.worktree_path = "/tmp/wt"
    fake_report = MagicMock()
    fake_runner.run.return_value = (fake_run_state, fake_report)

    with patch("loop.api.__main__.load_config") as mock_cfg, \
         patch("loop.api.__main__.build_runner", return_value=fake_runner), \
         patch("loop.api.__main__.render_citation_report", return_value="report text"), \
         patch("sys.argv", ["warrant", "run", "--direction", "build a cache layer",
                            "--config", str(cfg_file)]):
        mock_cfg.return_value = MagicMock(out_dir=str(tmp_path / "runs"))
        api_main.main()

    fake_runner.run.assert_called_once_with("build a cache layer")
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_factory.py::test_main_run_calls_runner -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'loop.api.__main__'`

- [ ] **Step 3: Create `loop/loop/api/__main__.py`**

```python
# loop/loop/api/__main__.py
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .. import runstore
from ..citationreport import render_citation_report
from .factory import load_config, build_runner


def _default_config() -> Path:
    return Path(".warrant/config.json")


def cmd_run(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    config = load_config(config_path)
    Path(config.out_dir).mkdir(parents=True, exist_ok=True)
    runner = build_runner(config)
    run_state, report = runner.run(args.direction)
    print(render_citation_report(report))
    print(f"worktree: {run_state.worktree_path}")


def cmd_resume(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    config = load_config(config_path)
    run_state = runstore.load_latest_run(Path(config.out_dir))
    runner = build_runner(config)
    run_state, report = runner.resume(run_state)
    print(render_citation_report(report))
    print(f"worktree: {run_state.worktree_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="warrant",
        description="Warrant — book-grounded autonomous coding agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Start a new Warrant run")
    p_run.add_argument("--direction", required=True, help="What to build")
    p_run.add_argument(
        "--config",
        default=str(_default_config()),
        help="Path to config JSON (default: .warrant/config.json)",
    )
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="Resume the latest run")
    p_resume.add_argument(
        "--config",
        default=str(_default_config()),
        help="Path to config JSON (default: .warrant/config.json)",
    )
    p_resume.set_defaults(func=cmd_resume)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update `loop/pyproject.toml`**

Replace the current content with:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "loop"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "agent",
    "librarian",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "anthropic>=0.25.0"]
api = ["anthropic>=0.25.0"]

[project.scripts]
warrant = "loop.api.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 5: Reinstall to pick up the entry_point and dev deps**

```bash
cd /home/cowboy/warrant && pip install -e loop/[dev] -q
```

- [ ] **Step 6: Run the CLI test**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_factory.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 7: Verify the binary is on PATH**

```bash
which warrant && warrant --help
```

Expected: prints `usage: warrant [-h] {run,resume} ...`

- [ ] **Step 8: Commit**

```bash
git add loop/loop/api/__main__.py loop/pyproject.toml loop/tests/test_api_factory.py
git commit -m "feat(api): add warrant CLI entry point — run and resume subcommands"
```

---

### Task 7: Materializer additions

**Files:**
- Modify: `loop/loop/materializer.py`
- Modify: `loop/loop/verifier_materializer.py`
- Create: `loop/tests/test_api_materializer.py`

Add `## Working directory` sections so `AnthropicInvoker` can extract the worktree path from the materialized prompt. Harmless for Artifact A — Claude Code Executors see it as context.

- [ ] **Step 1: Write the failing materializer tests**

```python
# loop/tests/test_api_materializer.py
from __future__ import annotations

from agent.plan import PlanNode, ApplicableCheck
from loop.materializer import materialize
from loop.verifier_materializer import materialize_verifier
from loop.models import RunState, NodeStatus, ExecutorResult


def _make_node(node_id: str = "n1") -> PlanNode:
    return PlanNode(
        id=node_id,
        level="implementation",
        decision="Add a cache layer",
        approach="Use an in-memory dict",
        grounds=[],
        grounds_state="ungrounded",
        grounds_note="library silent on this approach",
        applicable_checks=[],
        depends_on=[],
    )


def _make_run_state(worktree_path: str = "/tmp/wt") -> RunState:
    return RunState(
        run_id="r1",
        plan_id="p1",
        plan_version=1,
        worktree_path=worktree_path,
        phase="execute",
        node_statuses={"n1": NodeStatus(node_id="n1", status="pending")},
        anchored_direction="#DIRECTION: Add caching",
        anchored_honesty_constraint="#HONESTY-CONSTRAINT: Be honest",
    )


def test_materialize_includes_working_directory():
    node = _make_node()
    run_state = _make_run_state("/tmp/my_worktree")
    result = materialize(node, [], run_state, {"n1": node})
    assert "## Working directory" in result
    assert "/tmp/my_worktree" in result


def test_materialize_verifier_includes_working_directory(tmp_path):
    node = _make_node()
    run_state = _make_run_state(str(tmp_path))
    executor_result = ExecutorResult(
        node_id="n1",
        status="done",
        checks_run=[],
        principles_honored=[],
        principles_violated=[],
        amendments=[],
        summary="done",
    )
    result = materialize_verifier(
        node, [], run_state, executor_result, str(tmp_path), {"n1": node}
    )
    assert "## Working directory" in result
    assert str(tmp_path) in result
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_materializer.py -v
```

Expected: both tests FAIL — `## Working directory` not in output yet.

- [ ] **Step 3: Modify `loop/loop/materializer.py`**

In `materialize()`, add the working directory section after the initial `sections` list is defined (after the `## Approach` entry). The current code at lines 63–68:

```python
    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        f"## Your task\n{node.decision}",
        f"## Approach\n{node.approach}",
    ]
```

Change to:

```python
    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        f"## Your task\n{node.decision}",
        f"## Approach\n{node.approach}",
        f"## Working directory\n{run_state.worktree_path}",
    ]
```

- [ ] **Step 4: Modify `loop/loop/verifier_materializer.py`**

In `materialize_verifier()`, add after the "Your role" section. The current `sections` definition (lines 119–128):

```python
    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        (
            "## Your role\n"
            "You are a Verifier. You did not write the code below and you have not seen "
            "the Executor's reasoning. Grade the Executor's work strictly against the "
            "cited principles. Do not accept the Executor's self-assessment at face value."
        ),
    ]
```

Change to:

```python
    sections: list[str] = [
        run_state.anchored_direction,
        run_state.anchored_honesty_constraint,
        (
            "## Your role\n"
            "You are a Verifier. You did not write the code below and you have not seen "
            "the Executor's reasoning. Grade the Executor's work strictly against the "
            "cited principles. Do not accept the Executor's self-assessment at face value."
        ),
        f"## Working directory\n{worktree_path}",
    ]
```

- [ ] **Step 5: Run the materializer tests**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/test_api_materializer.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/ -q
```

Expected: all tests pass (109 existing + new tests).

- [ ] **Step 7: Commit**

```bash
git add loop/loop/materializer.py loop/loop/verifier_materializer.py loop/tests/test_api_materializer.py
git commit -m "feat(api): add working directory section to executor and verifier materializers"
```

---

### Task 8: Example config and final integration check

**Files:**
- Create: `.warrant/api-config.example.json`

Documents the Artifact B config format. The `anthropic_api_key` field is intentionally absent — use `ANTHROPIC_API_KEY` env var instead.

- [ ] **Step 1: Create the example config**

```json
{
  "index_path": "/path/to/built/librarian/index",
  "base_repo": "/path/to/your/project",
  "out_dir": ".warrant/runs",
  "claude_model": "claude-sonnet-4-6",
  "claude_model_verifier": "claude-sonnet-4-6",
  "max_tool_rounds": 50,
  "global_iteration_cap": 10,
  "per_node_attempt_cap": 3,
  "watchdog_timeout": 300.0,
  "max_parallel": 3,
  "max_principles": 15,
  "verify_iteration_cap": 3
}
```

Note: set `ANTHROPIC_API_KEY` in the environment; do not put API keys in the config file.

- [ ] **Step 2: Create the file**

```bash
mkdir -p /home/cowboy/warrant/.warrant
```

Write the above JSON to `.warrant/api-config.example.json`.

- [ ] **Step 3: Run the complete test suite**

```bash
cd /home/cowboy/warrant && python -m pytest loop/tests/ agent/tests/ librarian/tests/ -q
```

Expected: all tests pass (109 existing + new api tests).

- [ ] **Step 4: Verify the `warrant` binary works**

```bash
warrant --help
warrant run --help
warrant resume --help
```

Expected: usage text for each subcommand, no errors.

- [ ] **Step 5: Update SESSION.md**

Add an "Artifact B complete" section analogous to the existing plan sections. Record: branch name, commit SHA, test count, what was built.

- [ ] **Step 6: Commit**

```bash
git add .warrant/api-config.example.json SESSION.md
git commit -m "docs: add api-config.example.json and update SESSION.md — Artifact B complete"
```

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-warrant-artifact-b.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
