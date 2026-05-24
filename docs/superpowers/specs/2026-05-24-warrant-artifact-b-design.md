# Warrant Artifact B — Standalone CLI Design

Artifact B delivers the standalone `warrant` CLI: an autonomous coding agent that
runs the full Orient → Retrieve → Plan → Execute → Verify loop using the Anthropic
Python SDK directly, without requiring Claude Code. Artifact A's runner, phases,
materializers, and librarian are reused unchanged. What's new is a transport layer
(`loop/loop/api/`) that replaces Claude Code subprocess calls with multi-turn
Anthropic API calls plus a worktree-constrained sandbox for tool execution.

## 1. Scope

A new `loop/loop/api/` subpackage, plus a `warrant` binary entry_point, plus
small additions to the two materializers (worktree path injection). No changes to
`agent/`, `librarian/`, or any core `loop/loop/` module (runner, phases,
citationreport, runstore, worktree). `WarrantRunner` is used unchanged.

## 2. Package structure

```
loop/loop/api/
    __init__.py
    sandbox.py        — WorktreeSandbox: bash/read/write/list constrained to worktree
    invokers.py       — AnthropicLLM, AnthropicInvoker, AnthropicVerifierInvoker
    factory.py        — ApiConfig dataclass, load_config, build_runner
    __main__.py       — warrant CLI (run + resume subcommands)
```

Modified files:
- `loop/loop/materializer.py` — add `## Working directory` section
- `loop/loop/verifier_materializer.py` — add `## Working directory` section
- `loop/pyproject.toml` — add `api` optional dependency, `warrant` entry_point

## 3. `loop/loop/api/sandbox.py`

**`WorktreeSandbox`** — the execution primitive. All tool calls from Executor and
Verifier route through here.

```python
class WorktreeSandbox:
    def __init__(self, worktree_path: str) -> None:
        self._root = Path(worktree_path).resolve()

    def bash(self, cmd: str, timeout: float = 60.0) -> str: ...
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> str: ...
    def list_directory(self, path: str = ".") -> str: ...
```

**Path boundary enforcement.** Every path argument is resolved against `self._root`.
If the resolved path does not start with `self._root`, `ValueError` is raised. The
`ValueError` propagates to the tool-result handler in the invoker, which returns it
as an error string in the `tool_result` content block — Claude reads it and adapts.

**Bash semantics.** `subprocess.run(cmd, shell=True, cwd=self._root, capture_output=True,
text=True, timeout=timeout)`. Stdout and stderr are merged in the output. Non-zero
exit codes are appended as `[exit code: N]`. Exceptions (timeout, subprocess error)
are caught and returned as error strings — never raised.

**File operations.** `read_file` reads text with UTF-8 encoding. `write_file`
creates parent directories as needed and writes the full content. `list_directory`
returns a newline-separated list of entries relative to `self._root`.

## 4. `loop/loop/api/invokers.py`

### Tool definitions

```python
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
    TOOL_DEFS[3],  # list_directory  (no write_file)
]
```

### System prompt constants

```python
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
```

### `AnthropicLLM`

Used by Orient and Plan phases (no tool loop needed).

```python
class AnthropicLLM:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None: ...
    def __call__(self, prompt: str) -> str: ...
```

`__call__` calls `client.messages.create(model=self._model, max_tokens=2048,
messages=[{"role": "user", "content": prompt}])`. Returns `.content[0].text.strip()`.
Raises `RuntimeError` on `anthropic.APIError` or if the response has no text block.

### `AnthropicInvoker`

Implements `Invoker` protocol (`invoke(prompt, timeout) -> ExecutorResult`).

```python
class AnthropicInvoker:
    def __init__(self, client: anthropic.Anthropic, model: str, max_tool_rounds: int = 50) -> None: ...
    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult: ...
    def _dispatch_tool(self, name: str, inp: dict, sandbox: WorktreeSandbox) -> str: ...
```

**`invoke` logic:**

1. Extract worktree path: `re.search(r'^## Working directory\n(.+)$', prompt, re.MULTILINE)`.
   If the section is absent, use `"."` as a fallback (not a crash).
2. `sandbox = WorktreeSandbox(worktree_path)`
3. `messages = [{"role": "user", "content": prompt}]`
4. Loop up to `max_tool_rounds`:
   - `response = client.messages.create(model=..., max_tokens=8192, system=_EXECUTOR_SYSTEM, tools=TOOL_DEFS, messages=messages)`
   - If `response.stop_reason == "end_turn"`: extract text from last text block,
     call `_extract_json(text)`, parse as `ExecutorResult`, return it.
   - Else (tool_use): for each `tool_use` block, call `_dispatch_tool(name, inp, sandbox)`.
     Append assistant turn + user tool_result turn. Continue loop.
5. After `max_tool_rounds`: return synthetic `ExecutorResult(status="failed", summary="max tool rounds exceeded", ...)`.
6. On any exception: return synthetic `ExecutorResult(status="failed", summary=str(exc), ...)`.

**`_dispatch_tool`** routes `name` → sandbox method. On `ValueError` (path escape), returns
the error string as tool result content (not re-raised). Unknown tool names return an
error string.

**`_extract_json`** — same helper as `loop/loop/skill/invokers.py`: strip ` ```json ... ``` `
fences, fall back to `{...rfind...}`. Defined once at module level, shared by all three
invokers.

### `AnthropicVerifierInvoker`

Implements `VerifierInvoker` protocol (`invoke(prompt, timeout) -> VerifierResult`).

Same structure as `AnthropicInvoker` with three differences:
- Uses `VERIFIER_TOOL_DEFS` (no write_file)
- Uses `_VERIFIER_SYSTEM`
- On parse failure: returns synthetic `VerifierResult(verdict="fail", integrity_verdict="clean", ...)`
  — prevents the verify loop from re-queuing the node, same convention as `phases/verify.py`.

## 5. `loop/loop/api/factory.py`

### `ApiConfig`

```python
@dataclass
class ApiConfig:
    index_path: str
    out_dir: str
    base_repo: str
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    claude_model: str = "claude-sonnet-4-6"
    claude_model_verifier: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None   # None → use ANTHROPIC_API_KEY env var
    max_tool_rounds: int = 50
    global_iteration_cap: int = 10
    per_node_attempt_cap: int = 3
    watchdog_timeout: float = 300.0
    max_parallel: int = 3
    max_principles: int = 15
    verify_iteration_cap: int = 3
```

### `load_config(config_path: str | Path) -> ApiConfig`

Reads `.warrant/config.json` (or any passed path). Filters to known fields, constructs
`ApiConfig`. Unknown fields are ignored.

### `build_runner(config: ApiConfig) -> WarrantRunner`

```python
def build_runner(config: ApiConfig) -> WarrantRunner:
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package required: pip install 'warrant[api]'"
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

## 6. `loop/loop/api/__main__.py`

Two subcommands: `run` and `resume`. Same shape as `loop/loop/skill/__main__.py`.

```
warrant run --direction "build a cache layer" [--config .warrant/config.json]
warrant resume [--config .warrant/config.json]
```

**`run`:**
1. `load_config(args.config)`, `Path(config.out_dir).mkdir(parents=True, exist_ok=True)`
2. `build_runner(config)`
3. `run_state, report = runner.run(args.direction)`
4. Print `render_citation_report(report)` and `f"worktree: {run_state.worktree_path}"`

**`resume`:**
1. `load_config`, `runstore.load_latest_run(out_dir)`
2. `build_runner`
3. `runner.resume(run_state)`
4. Print report + worktree path

On any exception: print error message and `sys.exit(1)`.

**`main()`** — called by the `warrant` entry_point:

```python
def main() -> None:
    parser = argparse.ArgumentParser(prog="warrant", description="Book-grounded coding agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--direction", required=True)
    run_p.add_argument("--config", default=".warrant/config.json")
    res_p = sub.add_parser("resume")
    res_p.add_argument("--config", default=".warrant/config.json")
    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args)
    else:
        cmd_resume(args)
```

## 7. Materializer additions

### `loop/loop/materializer.py`

Add one section after the "Approach" section:

```python
sections.append(f"## Working directory\n{run_state.worktree_path}")
```

This provides `AnthropicInvoker` with the path to extract. Harmless for Artifact A —
Claude Code Executors see it as context and already know which worktree to operate in.

### `loop/loop/verifier_materializer.py`

Add one section (after the "Your role" section):

```python
sections.append(f"## Working directory\n{worktree_path}")
```

`worktree_path` is already a parameter to `materialize_verifier`.

## 8. `loop/pyproject.toml` changes

```toml
[project.optional-dependencies]
api = ["anthropic>=0.25.0"]

[project.scripts]
warrant = "loop.api.__main__:main"
```

Install: `pip install -e '.[api]'`

## 9. `.warrant/api-config.example.json`

Documents all fields:

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

Note: `anthropic_api_key` is intentionally absent from the example — use `ANTHROPIC_API_KEY`
env var rather than storing keys in the config file.

## 10. Tests

### `loop/tests/test_api_invokers.py`

**WorktreeSandbox tests:**
- `test_sandbox_bash_runs_in_worktree(tmp_path)` — run `pwd`, assert output equals worktree_path
- `test_sandbox_bash_returns_stderr_and_exit_code(tmp_path)` — run `ls /nonexistent`, assert output contains `[exit code:`
- `test_sandbox_read_file(tmp_path)` — write file, read via sandbox, assert content
- `test_sandbox_write_file(tmp_path)` — write via sandbox, assert file on disk
- `test_sandbox_list_directory(tmp_path)` — create files, list, assert names in output
- `test_sandbox_path_escape_raises(tmp_path)` — `read_file("../../etc/passwd")` raises `ValueError`

**AnthropicLLM tests:**
- `test_llm_returns_text` — mock `client.messages.create` returning text block, assert stripped text
- `test_llm_raises_on_api_error` — mock raises `anthropic.APIError`, assert `RuntimeError`

**AnthropicInvoker tests:**
- `test_executor_end_turn_produces_result` — mock one `end_turn` response with valid JSON, assert `ExecutorResult`
- `test_executor_runs_tool_then_produces_result` — mock `tool_use` then `end_turn`, assert sandbox `bash` called
- `test_executor_max_rounds_returns_failed` — mock always `tool_use`, assert `status="failed"` after `max_tool_rounds`
- `test_executor_bad_json_returns_failed` — mock `end_turn` with prose, assert `status="failed"`
- `test_executor_no_working_directory_section_uses_fallback` — prompt without `## Working directory`, assert no crash

**AnthropicVerifierInvoker tests:**
- `test_verifier_end_turn_produces_result` — mock valid JSON, assert `VerifierResult`
- `test_verifier_bad_json_returns_clean` — mock prose, assert `integrity_verdict="clean"`
- `test_verifier_no_write_file_tool` — assert `write_file` not in verifier's tool call (no `write_file` in VERIFIER_TOOL_DEFS)

### `loop/tests/test_api_factory.py`

- `test_load_config_reads_json(tmp_path)` — write full JSON, assert all fields loaded
- `test_load_config_defaults(tmp_path)` — write minimal JSON (required fields only), assert defaults apply
- `test_build_runner_wires_components(tmp_path, monkeypatch)` — patch `load_index`, `Embedder`, `Reranker`, `anthropic.Anthropic`; assert `build_runner` returns a `WarrantRunner` with correct config params forwarded

## 11. File map

| Action | Path |
|--------|------|
| Create | `loop/loop/api/__init__.py` |
| Create | `loop/loop/api/sandbox.py` |
| Create | `loop/loop/api/invokers.py` |
| Create | `loop/loop/api/factory.py` |
| Create | `loop/loop/api/__main__.py` |
| Create | `loop/tests/test_api_invokers.py` |
| Create | `loop/tests/test_api_factory.py` |
| Create | `.warrant/api-config.example.json` |
| Modify | `loop/loop/materializer.py` |
| Modify | `loop/loop/verifier_materializer.py` |
| Modify | `loop/pyproject.toml` |

## 12. Out of scope

- Changes to `runner.py`, `phases/`, `agent/`, `librarian/`
- Live end-to-end test against real API (all tests mock `anthropic.Anthropic`)
- Model selection flags beyond `claude_model` / `claude_model_verifier` config fields
- Artifact C (shareable kit)
- Parallel Executor subagent coordination changes (B inherits A's max_parallel behavior)
