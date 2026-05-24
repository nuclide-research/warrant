# Warrant — Agent Loop Design (Plan 2 of 4)

Status: approved 2026-05-24.

This spec covers plan 2 of the Agent build: the loop package
(`warrant/loop/`). It adds the Orient, Retrieve, Plan, and Execute phases,
execution state tracking, worktree management, the Executor prompt contract,
and stuck detection. Plan 3 adds the Verify phase, Verifier subagent, and
citation report. Plan 4 adds skill packaging.

Depends on: the plan artifact (`agent/` package, `ba12a26`) and the Librarian
(`librarian/` package).

## 1. Scope

Plan 2 delivers a standalone Python package, `loop/`, that drives the first
four phases of the Warrant agent loop:

1. **Orient** — parse direction, derive specialist persona, anchor direction
   and honesty blocks, create worktree, draft retrieval queries.
2. **Retrieve** — call the Librarian, deduplicate, cap, write principle set to
   disk.
3. **Plan** — build the initial plan artifact (architectural nodes eager,
   structural/implementation lazy), expand subtrees on demand.
4. **Execute** — dispatch Executor subagents per independent subtree, track
   execution state, checkpoint after each node, stuck detection.

Out of scope for plan 2: the Verify phase, Verifier subagent, citation report,
failure routing from verification, skill packaging.

## 2. Package structure

```
warrant/loop/
  loop/
    __init__.py
    models.py        # RunState, NodeStatus, ExecutorResult, Invoker protocol
    runner.py        # WarrantRunner — drives Orient → Retrieve → Plan → Execute
    runstore.py      # RunState I/O: save_run, load_run, load_latest_run
    materializer.py  # Executor prompt builder: plan node → materialized string
    worktree.py      # git worktree create/remove/list via subprocess
    phases/
      __init__.py
      orient.py      # Orient phase
      retrieve.py    # Retrieve phase
      plan.py        # Plan phase (initial build + lazy subtree expansion)
      execute.py     # Execute phase (dispatch, RunState updates, stuck detection)
  tests/
    test_models.py
    test_runstore.py
    test_materializer.py
    test_worktree.py
    test_orient.py
    test_retrieve.py
    test_plan.py
    test_execute.py
    test_runner.py   # integration: full Orient → Execute on a fixture
    test_smoke.py
  pyproject.toml
```

The `loop` package imports from `agent` and `librarian` as editable-installed
siblings. It has no dependency on the Claude Code skill layer — that is plan 4.

## 3. Data models (`models.py`)

### RunState

```python
NodeStatusValue = Literal["pending", "in_flight", "done", "failed"]

@dataclass
class NodeStatus:
    node_id: str
    status: NodeStatusValue
    attempts: int = 0
    last_result: ExecutorResult | None = None

@dataclass
class RunState:
    run_id: str                    # uuid4 hex
    plan_id: str                   # matches Plan.plan_id
    plan_version: int              # plan version this run is tracking
    worktree_path: str             # absolute path to git worktree
    phase: str                     # "orient"|"retrieve"|"plan"|"execute"|"done"
    node_statuses: dict[str, NodeStatus]
    anchored_direction: str        # re-injected at every subagent prompt head
    anchored_honesty_constraint: str
    iteration: int = 0             # global iteration counter
    created_at: str = ""           # ISO-8601
    updated_at: str = ""
```

**Invariant:** `node_statuses` keys must be a subset of the current plan's
node ids. `WarrantRunner` enforces this on every node transition — an unknown
node id raises `ValueError` rather than silently creating orphan state.

### ExecutorResult

```python
@dataclass
class CheckResult:
    check_id: str
    provenance: str    # "from_grounds" | "from_topic"
    passed: bool
    detail: str = ""

@dataclass
class NodeAmendment:
    node_id: str
    amended_reason: str

@dataclass
class ExecutorResult:
    node_id: str
    status: str                    # "done" | "failed"
    checks_run: list[CheckResult]
    principles_honored: list[str]  # principle ids
    principles_violated: list[str]
    amendments: list[NodeAmendment]
    summary: str                   # one line max
```

### Invoker protocol

```python
class Invoker(Protocol):
    def invoke(self, prompt: str, timeout: float | None = None) -> ExecutorResult: ...
```

All external Executor invocation goes through `Invoker`. The plan 4 skill
wrapper provides a `ClaudeCodeInvoker` implementation. Tests use a
`FakeInvoker` that returns configurable `ExecutorResult` fixtures.

## 4. RunState I/O (`runstore.py`)

Mirrors `planstore.py` in structure:

- `save_run(state: RunState, out_dir: Path) -> Path` — writes
  `run.v{N}.json` where N is `state.iteration`. Updates `state.updated_at`.
- `load_run(path: Path) -> RunState` — reads and deserializes a single file.
- `load_latest_run(out_dir: Path) -> RunState` — globs `run.v*.json`, picks
  the highest N, loads it.

Serialization: `dataclasses.asdict` with a custom encoder for the nested
`ExecutorResult` in `NodeStatus.last_result`. `encoding="utf-8"` on all
file I/O.

Run files and plan files coexist in the same `out_dir`; `run.v*.json` and
`plan.v*.json` are distinct by prefix.

## 5. Worktree management (`worktree.py`)

```python
@dataclass
class WorktreeInfo:
    path: str
    branch: str
    commit: str

class WorktreeManager:
    def create(self, base_repo: Path, branch: str) -> Path: ...
    def remove(self, path: Path) -> None: ...
    def list_worktrees(self, base_repo: Path) -> list[WorktreeInfo]: ...
```

Implemented via `subprocess` calls to `git worktree add/remove/list
--porcelain`. `create` derives the worktree path as
`{base_repo}/../warrant-wt-{branch_slug}` and raises `WorktreeError` if the
branch already exists. `remove` calls `git worktree remove --force`.
`list_worktrees` parses `--porcelain` output into `WorktreeInfo` records.

Tests use a real git repo fixture (tmp directory, `git init`, one commit) —
no mocking of subprocess.

## 6. Orient phase (`phases/orient.py`)

Input: `direction: str`, `index: Index`, `llm`, `worktree_mgr: WorktreeManager`,
`base_repo: Path`, `run_id: str`.

```python
@dataclass
class OrientResult:
    anchored_direction: str
    anchored_honesty_constraint: str
    specialist_persona: str        # one paragraph
    retrieval_queries: list[str]   # 3-5 queries
    worktree_path: str
```

Steps:

1. Format `anchored_direction` as `#DIRECTION: {direction}` and
   `anchored_honesty_constraint` as the fixed honesty prose block.
2. Derive `specialist_persona`: collect unique `(isbn, book, chapter)` tuples
   from `index.principles`; ask the LLM to produce a one-paragraph specialist
   identity from that reading list. No extra I/O — the citation set is already
   in the index.
3. Ask the LLM to draft 3-5 retrieval queries from the direction and persona.
4. Call `worktree_mgr.create(base_repo, branch=f"warrant/{run_id[:8]}")`.
5. Return `OrientResult`.

The LLM parameter is the same injectable pattern as the Librarian's `llm`
parameter — a callable `(prompt: str) -> str`. Tests pass a fake.

## 7. Retrieve phase (`phases/retrieve.py`)

Input: `queries: list[str]`, `index: Index`, `embedder`, `reranker`,
`max_principles: int = 15`, `worktree_path: str`.

Steps:

1. Call `query_index(index, query, embedder, reranker, k=SEMANTIC_POOL)` for
   each query. Merge results, deduplicate by `principle.id`, keeping the
   highest score per id.
2. Rerank the merged pool with `reranker.rerank(combined_query, merged)`.
3. Cap at `max_principles`.
4. Write the full set to `{worktree_path}/.warrant/principles.json` — the
   file is the durable record.
5. Return `list[Result]`.

`combined_query` for the final rerank is the retrieval queries joined with a
space — a lightweight cross-query coherence pass.

## 8. Plan phase (`phases/plan.py`)

Two operations:

**`build_initial(direction, principles, llm) -> Plan`**

LLM call produces architectural-level nodes. For each node, the LLM cites
principle ids from the retrieved set. Validation: every cited id is checked
against the retrieved principles; an unknown id downgrades the node's
`grounds_state` to `ungrounded` (with `grounds_note` explaining the miss)
rather than raising. Returns a `Plan` via `planops.new_plan` + repeated
`planops.add_node`.

**`expand_subtree(plan, node_id, principles, llm, out_dir) -> Plan`**

Lazy expansion of one architectural node into structural/implementation
children. Steps:

1. LLM call: given the parent node + its grounded principles, produce child
   nodes.
2. Call `planops.next_version(plan)` to get `plan_v2`.
3. Call `planops.add_node` for each child.
4. Call `planstore.save_plan(plan_v2, out_dir)` — the save is the self-gate
   before execution of this subtree.
5. Return `plan_v2`.

Expansion is called by `WarrantRunner` before dispatching each architectural
node's children.

## 9. Execute phase (`phases/execute.py`)

**Loop:**

```
while undone nodes exist and iteration < global_iteration_cap:
    # Use planops.independent_siblings — already implemented in plan 1
    dispatchable = [n for n in planops.independent_siblings(plan)
                    if run_state.node_statuses[n.id].status == "pending"]
    dispatch dispatchable nodes (parallel up to max_parallel)
    update RunState
    save_run
    iteration += 1
```

**Per-node execution:**

1. Mark node `in_flight` in `RunState`; `save_run`.
2. Call `materializer.materialize(node, principles, run_state)` → prompt.
3. Call `invoker.invoke(prompt, timeout=watchdog_timeout)` → `ExecutorResult`.
   A timeout raises `InvokerTimeout`; caught here, node marked `failed`.
4. On `done`: mark node `done`; store `last_result`.
5. On `failed`: increment `attempts`.
   - If `attempts >= per_node_attempt_cap` or a `from_grounds` Tier-1
     `CheckResult` has `passed=False`: trigger stuck detection.
   - Stuck detection: call `planops.amend_node` with a reason derived from
     `last_result.principles_violated`; call `planops.next_version`; save the
     amended plan version; update `run_state.plan_version` to match.

**Parallelism:** `concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel)`.
Each worker calls `invoker.invoke` for one node. Results are collected after
the batch; `RunState` is updated serially after all workers return.

**Configuration** (defaults, all overridable at `WarrantRunner` construction):

| Parameter | Default |
|---|---|
| `global_iteration_cap` | 10 |
| `per_node_attempt_cap` | 3 |
| `watchdog_timeout` | 300.0 s |
| `max_parallel` | 3 |
| `max_principles` | 15 |

## 10. Executor prompt (`materializer.py`)

`materialize(node: PlanNode, principles: list[Result], run_state: RunState) -> str`

Prompt structure:

```
{run_state.anchored_direction}
{run_state.anchored_honesty_constraint}

## Your task
{node.decision}

## Approach
{node.approach}

## Grounding
For each principle id in node.grounds:
  - Statement: {principle.statement}
  - Evidence: {principle.evidence_chunk}
  - Citation: {principle.citation.book}, {principle.citation.chapter}, {principle.citation.section}

## Checks you must run
For each applicable_check in node.applicable_checks:
  - {check.check} (provenance: {check.provenance})

## Dependencies context
For each dep_id in node.depends_on:
  - {dep_node.decision}: {dep_node.approach}

## Return format
Return ONLY a JSON object matching this schema — no prose before or after:
{ExecutorResult schema as JSON}
```

Principle lookup: `materializer` takes the full `list[Result]` from the
Retrieve phase and builds a `dict[principle_id, Result]` for O(1) lookup.
An id in `node.grounds` not found in the lookup is noted in a
`# Missing principles` section of the prompt (honest about the gap) rather
than silently dropped.

## 11. WarrantRunner (`runner.py`)

```python
class WarrantRunner:
    def __init__(
        self,
        index: Index,
        embedder,
        reranker,
        llm,
        invoker: Invoker,
        worktree_mgr: WorktreeManager,
        base_repo: Path,
        out_dir: Path,
        **config,   # global_iteration_cap, per_node_attempt_cap, etc.
    ): ...

    def run(self, direction: str) -> RunState: ...
    def resume(self, run_state: RunState) -> RunState: ...
```

`run` drives the full Orient → Retrieve → Plan → Execute sequence, saving
`RunState` after each phase transition. `resume` reads the latest plan version
and run state, diffs node statuses, and re-enters Execute at the first
non-done node. Both return the final `RunState`; the caller (plan 4 skill
wrapper) hands back the worktree branch and the run state to the Verify phase
(plan 3).

## 12. Testing strategy

- **Unit tests** per module: `test_models.py` (validation invariants),
  `test_runstore.py` (round-trip, versioning), `test_materializer.py`
  (prompt shape, missing-principle handling), `test_worktree.py` (real git
  fixture), phase tests with fake LLM + fake Invoker.
- **Integration test** (`test_runner.py`): full `run()` on a fixture index
  (the existing librarian test fixture book), fake LLM producing valid nodes,
  fake Invoker returning done results. Asserts final `RunState.phase == "done"`
  and all nodes `done`.
- **Smoke test** (`test_smoke.py`): imports every module, constructs
  `WarrantRunner` with fakes, calls `run()` on a one-node plan. Fails fast on
  import errors or construction failures.

Fake LLM and fake Invoker live in `tests/fakes.py` (mirrors
`librarian/tests/fakes.py`).

## 13. Open questions deferred to plan 3

- Failure routing from the Verifier back into Execute (a plan 3 concern).
- The citation report format and its projection from `RunState` + plan
  versions.
- Second Verifier escalation for low-confidence nodes (mentioned in the
  master design as a future extension; plan 3 decides whether v1 includes it).
