# Warrant Skill Wrapper — design (Plan 4 of 4)

Plan 4 wires `WarrantRunner` to real Claude invocations and delivers the
Claude Code skill entry point. Three concerns: real implementations of the
`Invoker` and `VerifierInvoker` protocols; a factory that assembles
`WarrantRunner` from a config file; and `SKILL.md` at the repo root.

## 1. Scope

A new `loop/loop/skill/` subpackage plus `SKILL.md` at `~/warrant/SKILL.md`.
No new Python packages; no changes to `agent/`, `librarian/`, or the existing
`loop/loop/` modules.

## 2. `loop/loop/skill/invokers.py`

Three callable objects that all use the same primitive: `subprocess.run(["claude",
"-p", prompt], capture_output=True, text=True, timeout=timeout)`. The `-p`
flag puts Claude CLI into non-interactive print mode.

**`ClaudeCodeLLM`**

A callable `(prompt: str) -> str`. Calls `claude -p <prompt>`, returns
`stdout.strip()`. Used by the runner for Orient (specialist persona, retrieval
queries) and Plan (initial plan JSON). On non-zero returncode or timeout, raises
`RuntimeError`.

**`ClaudeCodeInvoker`**

Implements the `Invoker` protocol: `invoke(prompt, timeout) -> ExecutorResult`.
Calls `claude -p <prompt>`. Extracts the JSON block from stdout — the executor
prompt already instructs Claude to return only JSON; the invoker strips any
surrounding markdown fences with a regex, then `json.loads()`. On parse
failure or subprocess error, returns a synthetic `ExecutorResult` with
`status="failed"` and the error in `summary`, so the runner's attempt-cap
machinery handles it normally.

**`ClaudeCodeVerifierInvoker`**

Implements `VerifierInvoker`: `invoke(prompt, timeout) -> VerifierResult`. Same
pattern as `ClaudeCodeInvoker`. Extracts the JSON block, parses `VerifierResult`.
On failure, returns a synthetic `VerifierResult` with `verdict="fail"`,
`integrity_verdict="clean"` (so the runner does not route the node back to
pending — same convention as `phases/verify.py` exception handling).

**JSON extraction helper**

A module-level `_extract_json(text: str) -> str` that:
1. Tries to strip ` ```json ... ``` ` or ` ``` ... ``` ` fences
2. Falls back to the first `{` to the last `}` via rfind
3. Returns the candidate string for `json.loads`

This is shared by both invokers.

## 3. `loop/loop/skill/factory.py`

**`Config` dataclass**

```python
@dataclass
class Config:
    index_path: str       # path to built librarian index directory
    out_dir: str          # where run state and plan versions are saved
    base_repo: str        # git repo to create worktrees from
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    global_iteration_cap: int = 10
    per_node_attempt_cap: int = 3
    watchdog_timeout: float = 300.0
    max_parallel: int = 3
    max_principles: int = 15
    verify_iteration_cap: int = 3
```

**`load_config(config_path: Path) -> Config`**

Reads `.warrant/config.json` (or any path passed in). JSON fields map
directly to `Config` fields. Unknown fields are ignored.

**`build_runner(config: Config) -> WarrantRunner`**

1. `load_index(config.index_path)` from `librarian.store`
2. `Embedder(config.model_name)` from `librarian.embedding`
3. `Reranker(config.reranker_name)` from `librarian.query`
4. `ClaudeCodeLLM()`, `ClaudeCodeInvoker()`, `ClaudeCodeVerifierInvoker()`
5. `WorktreeManager()`
6. Returns `WarrantRunner(index, embedder, reranker, llm, invoker,
   verifier_invoker, worktree_mgr, base_repo=config.base_repo,
   out_dir=config.out_dir, ...config params...)`

## 4. `loop/loop/skill/__main__.py`

Two subcommands: `run` and `resume`.

```
python -m loop.skill run --direction "build a cache layer" [--config .warrant/config.json]
python -m loop.skill resume [--config .warrant/config.json]
```

**`run`**

1. Load config (`--config`, default `.warrant/config.json`), create `out_dir` if absent
2. `build_runner(config)`
3. `run_state, report = runner.run(direction)`
4. Print `render_citation_report(report)`
5. Print the worktree branch name (from `run_state.worktree_path`)

**`resume`**

1. Load config, load `runstore.load_latest_run(out_dir)`
2. `build_runner(config)`
3. `run_state, report = runner.resume(run_state)`
4. Print report + branch

On any exception, print the error and exit 1.

## 5. `SKILL.md`

At `~/warrant/SKILL.md`:

```yaml
---
name: warrant
description: >
  Autonomous book-grounded coding agent. Runs Orient → Retrieve → Plan →
  Execute → Verify given one direction, returns a finished branch and
  citation report. Usage: /warrant <direction>
allowed-tools: Bash
---
```

**Instructions body:**

- Accept `direction` from `$ARGUMENTS`
- Verify `.warrant/config.json` exists in the current directory; if not,
  explain setup and stop
- Run `python -m loop.skill run --direction "$ARGUMENTS"` via Bash
- Print the stdout output (citation report + branch name) to the user
- If the user invokes `/warrant resume`, run `python -m loop.skill resume` instead

The skill is intentionally thin: all logic lives in Python. Claude Code
provides the shell and the subagent invocations (via the subprocess calls
inside the invokers).

## 6. `.warrant/config.example.json`

Documents required fields:

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

## 7. Tests

**`loop/tests/test_invokers.py`**

Uses `unittest.mock.patch("subprocess.run")` to mock Claude CLI responses:

- `test_llm_returns_stripped_stdout` — mock returns stdout `"  hello  "`, assert result is `"hello"`
- `test_llm_raises_on_nonzero` — mock returncode 1, assert `RuntimeError`
- `test_executor_invoker_parses_json` — mock stdout contains `ExecutorResult` JSON (no fences), assert result is `ExecutorResult` with correct fields
- `test_executor_invoker_handles_fenced_json` — mock stdout wraps JSON in ` ```json ... ``` `, assert parses correctly
- `test_executor_invoker_returns_failed_on_bad_json` — mock stdout is plain prose, assert returned `ExecutorResult.status == "failed"`
- `test_verifier_invoker_parses_json` — same pattern for `VerifierResult`
- `test_verifier_invoker_returns_clean_on_bad_json` — parse failure returns `integrity_verdict="clean"`

**`loop/tests/test_factory.py`**

- `test_load_config_reads_json(tmp_path)` — write a JSON file, assert `load_config` returns correct `Config`
- `test_load_config_defaults(tmp_path)` — write minimal JSON (only required fields), assert defaults apply
- `test_build_runner_wires_components(tmp_path, monkeypatch)` — patch `load_index` to return a fake index, patch `Embedder`/`Reranker` constructors, assert `build_runner` returns a `WarrantRunner` with the right types

## 8. File map

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

## 9. Out of scope

- A README or installation guide (Artifact C)
- Changes to `agent/`, `librarian/`, or existing `loop/` modules
- Any live test against a real Claude CLI subprocess (all tests mock subprocess)
- Model selection flags on the CLI (uses the default `claude -p` model)
