# Warrant Skill Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `WarrantRunner` to real Claude CLI invocations and deliver the `/warrant` Claude Code skill entry point.

**Architecture:** A `loop/loop/skill/` subpackage provides three invoker classes (`ClaudeCodeLLM`, `ClaudeCodeInvoker`, `ClaudeCodeVerifierInvoker`) that call `claude -p <prompt>` via subprocess, a `factory.py` that assembles a configured `WarrantRunner` from a JSON config file, and a `__main__.py` CLI entrypoint. `SKILL.md` at the repo root is the thin Claude Code skill wrapper that calls the Python entrypoint.

**Tech Stack:** Python 3.11+, subprocess, dataclasses, argparse, unittest.mock (tests only), `loop` package (already built), `librarian` package (already built), `agent` package (already built).

---

## Context for implementers

The `loop` package lives at `loop/loop/`. Its test suite is at `loop/tests/`. Run all tests from the `loop/` directory:

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/ -v
```

95 tests currently pass. Do not break any of them.

**Import rules (enforced by package layout):**
- Within `loop/loop/skill/`, use relative imports: `from ..runner import WarrantRunner`, `from ..worktree import WorktreeManager`, `from .invokers import ClaudeCodeLLM`
- Tests at `loop/tests/` use absolute imports: `from loop.skill.invokers import ...`
- `from agent.plan import PlanNode` (NOT `agent.agent.plan`)
- `from librarian.query import Result` (NOT `librarian.librarian.query`)

**Key types** (from `loop/loop/models.py`):
- `ExecutorResult(node_id, status, checks_run, principles_honored, principles_violated, amendments, summary)`
- `CheckResult(check_id, provenance, passed, detail)`
- `NodeAmendment(node_id, amended_reason)`
- `VerifierResult(node_id, verdict, confidence, check_outcomes, integrity_verdict, summary)`
- `VerifierCheckOutcome(check_id, provenance, tier, passed, metric_value, judgment, detail)`

**`WarrantRunner.__init__` signature** (from `loop/loop/runner.py`):
```python
WarrantRunner(index, embedder, reranker, llm, invoker, verifier_invoker,
              worktree_mgr, base_repo, out_dir,
              global_iteration_cap=10, per_node_attempt_cap=3,
              watchdog_timeout=300.0, max_parallel=3,
              max_principles=15, verify_iteration_cap=3)
```

**Librarian constructors:**
- `load_index(path)` from `librarian.store` — accepts str or Path
- `Embedder(model_name)` from `librarian.embedding`
- `Reranker(model_name)` from `librarian.query`

---

## File map

| Action | Path |
|--------|------|
| Create | `loop/loop/skill/__init__.py` |
| Create | `loop/loop/skill/invokers.py` |
| Create | `loop/loop/skill/factory.py` |
| Create | `loop/loop/skill/__main__.py` |
| Create | `loop/tests/test_invokers.py` |
| Create | `loop/tests/test_factory.py` |
| Create | `SKILL.md` |
| Create | `.warrant/config.example.json` |

---

## Task 1: Invokers — `ClaudeCodeLLM`, `ClaudeCodeInvoker`, `ClaudeCodeVerifierInvoker`

**Files:**
- Create: `loop/loop/skill/__init__.py`
- Create: `loop/loop/skill/invokers.py`
- Create: `loop/tests/test_invokers.py`

- [ ] **Step 1: Create the skill subpackage marker**

```bash
mkdir -p /home/cowboy/warrant/loop/loop/skill
touch /home/cowboy/warrant/loop/loop/skill/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `loop/tests/test_invokers.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/test_invokers.py -v
```

Expected: `ModuleNotFoundError: No module named 'loop.skill'` or `ImportError`. If the error is something other than a missing module, investigate before proceeding.

- [ ] **Step 4: Implement `loop/loop/skill/invokers.py`**

```python
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


class ClaudeCodeLLM:
    """Callable LLM that invokes `claude -p <prompt>` and returns stripped stdout."""

    def __call__(self, prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
        )
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
            return VerifierResult(
                node_id="unknown",
                verdict="fail",
                confidence=0.0,
                check_outcomes=[],
                integrity_verdict="clean",
                summary=str(exc),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/test_invokers.py -v
```

Expected: 7 tests pass. Also run the full suite to confirm no regressions:

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/ -v
```

Expected: 102 tests pass (95 existing + 7 new).

- [ ] **Step 6: Commit**

```bash
cd /home/cowboy/warrant
git add loop/loop/skill/__init__.py loop/loop/skill/invokers.py loop/tests/test_invokers.py
git commit -m "feat(loop/skill): add ClaudeCodeLLM, ClaudeCodeInvoker, ClaudeCodeVerifierInvoker invokers"
```

---

## Task 2: Factory — `Config`, `load_config`, `build_runner`

**Files:**
- Create: `loop/loop/skill/factory.py`
- Create: `loop/tests/test_factory.py`

- [ ] **Step 1: Write the failing tests**

Create `loop/tests/test_factory.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from loop.skill.factory import Config, load_config, build_runner
from loop.runner import WarrantRunner


def test_load_config_reads_json(tmp_path):
    cfg_data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/myproject",
        "global_iteration_cap": 5,
        "per_node_attempt_cap": 2,
        "watchdog_timeout": 120.0,
        "max_parallel": 2,
        "max_principles": 10,
        "verify_iteration_cap": 2,
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg_data))

    result = load_config(config_file)

    assert result.index_path == "/data/index"
    assert result.out_dir == ".warrant/runs"
    assert result.base_repo == "/code/myproject"
    assert result.global_iteration_cap == 5
    assert result.per_node_attempt_cap == 2
    assert result.watchdog_timeout == 120.0
    assert result.max_parallel == 2
    assert result.max_principles == 10
    assert result.verify_iteration_cap == 2


def test_load_config_defaults(tmp_path):
    cfg_data = {
        "index_path": "/data/index",
        "out_dir": ".warrant/runs",
        "base_repo": "/code/myproject",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg_data))

    result = load_config(config_file)

    assert result.global_iteration_cap == 10
    assert result.per_node_attempt_cap == 3
    assert result.watchdog_timeout == 300.0
    assert result.max_parallel == 3
    assert result.max_principles == 15
    assert result.verify_iteration_cap == 3
    assert result.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert result.reranker_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_build_runner_wires_components(tmp_path):
    cfg = Config(
        index_path=str(tmp_path / "index"),
        out_dir=str(tmp_path / "runs"),
        base_repo=str(tmp_path / "repo"),
    )
    fake_index = MagicMock()
    with patch("loop.skill.factory.load_index", return_value=fake_index) as mock_idx, \
         patch("loop.skill.factory.Embedder") as mock_emb, \
         patch("loop.skill.factory.Reranker") as mock_rnk:
        runner = build_runner(cfg)

    mock_idx.assert_called_once_with(cfg.index_path)
    mock_emb.assert_called_once_with(cfg.model_name)
    mock_rnk.assert_called_once_with(cfg.reranker_name)
    assert isinstance(runner, WarrantRunner)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/test_factory.py -v
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'loop.skill.factory'`.

- [ ] **Step 3: Implement `loop/loop/skill/factory.py`**

```python
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
from .invokers import ClaudeCodeLLM, ClaudeCodeInvoker, ClaudeCodeVerifierInvoker


@dataclass
class Config:
    index_path: str
    out_dir: str
    base_repo: str
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    global_iteration_cap: int = 10
    per_node_attempt_cap: int = 3
    watchdog_timeout: float = 300.0
    max_parallel: int = 3
    max_principles: int = 15
    verify_iteration_cap: int = 3


def load_config(config_path: Path) -> Config:
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    known = {f.name for f in dataclasses.fields(Config)}
    filtered = {k: v for k, v in data.items() if k in known}
    return Config(**filtered)


def build_runner(config: Config) -> WarrantRunner:
    index = load_index(config.index_path)
    embedder = Embedder(config.model_name)
    reranker = Reranker(config.reranker_name)
    llm = ClaudeCodeLLM()
    invoker = ClaudeCodeInvoker()
    verifier_invoker = ClaudeCodeVerifierInvoker()
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

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/test_factory.py -v
```

Expected: 3 tests pass. Also run the full suite:

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/ -v
```

Expected: 105 tests pass (102 after Task 1 + 3 new).

- [ ] **Step 5: Commit**

```bash
cd /home/cowboy/warrant
git add loop/loop/skill/factory.py loop/tests/test_factory.py
git commit -m "feat(loop/skill): add Config dataclass, load_config, build_runner factory"
```

---

## Task 3: CLI entrypoint — `loop/loop/skill/__main__.py`

**Files:**
- Create: `loop/loop/skill/__main__.py`

No unit tests — this is a thin argparse wrapper around `build_runner`. Verified with smoke tests.

- [ ] **Step 1: Implement `loop/loop/skill/__main__.py`**

```python
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
        prog="python -m loop.skill",
        description="Warrant autonomous coding agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Start a new Warrant run")
    p_run.add_argument("--direction", required=True, help="What to build")
    p_run.add_argument(
        "--config",
        default=str(_default_config()),
        help="Path to config.json (default: .warrant/config.json)",
    )
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="Resume the latest run")
    p_resume.add_argument(
        "--config",
        default=str(_default_config()),
        help="Path to config.json (default: .warrant/config.json)",
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

- [ ] **Step 2: Smoke test — help output**

```bash
cd /home/cowboy/warrant/loop && python -m loop.skill --help
```

Expected output contains: `usage: python -m loop.skill` and subcommands `run` and `resume`.

```bash
cd /home/cowboy/warrant/loop && python -m loop.skill run --help
```

Expected output contains: `--direction` and `--config`.

```bash
cd /home/cowboy/warrant/loop && python -m loop.skill resume --help
```

Expected output contains: `--config`.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/ -v
```

Expected: 105 tests pass (same count as after Task 2 — `__main__.py` adds no new tests).

- [ ] **Step 4: Commit**

```bash
cd /home/cowboy/warrant
git add loop/loop/skill/__main__.py
git commit -m "feat(loop/skill): add CLI entrypoint — run and resume subcommands"
```

---

## Task 4: `SKILL.md` and `.warrant/config.example.json`

**Files:**
- Create: `SKILL.md` (at repo root `~/warrant/SKILL.md`)
- Create: `.warrant/config.example.json`

No code tests — verify YAML frontmatter parses and the JSON is valid.

- [ ] **Step 1: Create `SKILL.md` at the repo root**

Create `/home/cowboy/warrant/SKILL.md`:

```markdown
---
name: warrant
description: >
  Autonomous book-grounded coding agent. Runs Orient -> Retrieve -> Plan ->
  Execute -> Verify given one direction, returns a finished worktree and
  citation report. Usage: /warrant <direction>
allowed-tools: Bash
---

Accept the direction from `$ARGUMENTS`.

First, verify that `.warrant/config.json` exists in the current directory:

```bash
test -f .warrant/config.json || { echo "No .warrant/config.json found. Copy .warrant/config.example.json, fill in index_path and base_repo, then re-run."; exit 1; }
```

If the config is missing, explain the setup and stop — do not proceed.

To start a new run:

```bash
python -m loop.skill run --direction "$ARGUMENTS"
```

Print the full stdout output to the user (citation report + worktree path).

To resume the latest interrupted run, the user invokes `/warrant resume`. In that case, run:

```bash
python -m loop.skill resume
```

All logic lives in the Python package. This skill is intentionally thin.
```

- [ ] **Step 2: Verify SKILL.md frontmatter is valid YAML**

```bash
python3 -c "
import re, sys
text = open('/home/cowboy/warrant/SKILL.md').read()
m = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
if not m:
    print('ERROR: no frontmatter found'); sys.exit(1)
import yaml
data = yaml.safe_load(m.group(1))
assert 'name' in data, 'missing name'
assert 'description' in data, 'missing description'
print('OK:', data)
"
```

If `yaml` is not available: `pip install pyyaml` then re-run.

Expected: `OK: {'name': 'warrant', 'description': '...', 'allowed-tools': 'Bash'}`.

- [ ] **Step 3: Create `.warrant/config.example.json`**

```bash
mkdir -p /home/cowboy/warrant/.warrant
```

Create `/home/cowboy/warrant/.warrant/config.example.json`:

```json
{
  "index_path": "/path/to/built/librarian/index",
  "base_repo": "/path/to/your/project",
  "out_dir": ".warrant/runs",
  "global_iteration_cap": 10,
  "per_node_attempt_cap": 3,
  "watchdog_timeout": 300.0,
  "max_parallel": 3,
  "max_principles": 15,
  "verify_iteration_cap": 3
}
```

- [ ] **Step 4: Verify the JSON is valid**

```bash
python3 -c "import json; data = json.load(open('/home/cowboy/warrant/.warrant/config.example.json')); print('OK:', list(data.keys()))"
```

Expected: `OK: ['index_path', 'base_repo', 'out_dir', 'global_iteration_cap', 'per_node_attempt_cap', 'watchdog_timeout', 'max_parallel', 'max_principles', 'verify_iteration_cap']`

- [ ] **Step 5: Commit**

```bash
cd /home/cowboy/warrant
git add SKILL.md .warrant/config.example.json
git commit -m "feat: add SKILL.md and .warrant/config.example.json"
```

- [ ] **Step 6: Run full test suite one final time**

```bash
cd /home/cowboy/warrant/loop && python -m pytest tests/ -v
```

Expected: 105 tests pass. No failures.

- [ ] **Step 7: Push to origin**

```bash
cd /home/cowboy/warrant && git push origin main
```
