# Warrant — Verify Phase + Citation Report Design (Plan 3 of 4)

Status: approved 2026-05-24.

This spec covers plan 3 of the Agent build: the Verify phase and citation report.
It extends the `loop/` package (`warrant/loop/`) with four additions: new models,
a Verifier prompt materializer, the verify phase, and a citation report generator.
Plan 4 adds skill packaging and the real `ClaudeCodeInvoker` /
`ClaudeCodeVerifierInvoker` implementations.

Depends on: the plan artifact (`agent/` package), the Librarian (`librarian/`
package), and the loop package (`loop/`, `ba12a26`).

## 1. Scope

Plan 3 delivers:

1. **New models** — `VerifierCheckOutcome`, `VerifierResult`, `VerifierInvoker`
   protocol, `CitationReport`; `NodeStatus.pre_execution_sha`.
2. **`verifier_materializer.py`** — builds the Verifier subagent prompt from a
   plan node, retrieved principles, the Executor's result, and the actual git
   diff from the worktree.
3. **`phases/verify.py`** — invokes `VerifierInvoker` per done node; routes
   `from_grounds` Tier-1 failures back to Execute; records `from_topic` failures
   and Tier-2/3 results for the report only.
4. **`citationreport.py`** — projects plan + `RunState` + all `VerifierResult`s
   into a `CitationReport`; renders the text summary.
5. **`phases/execute.py` update** — records `pre_execution_sha` on `NodeStatus`
   before each node dispatch.
6. **`runner.py` update** — adds `verifier_invoker` and `verify_iteration_cap`
   parameters; orchestrates the Execute→Verify loop; return type changes to
   `tuple[RunState, CitationReport]`.

Out of scope for plan 3: the `ClaudeCodeVerifierInvoker` implementation, the
second-Verifier escalation (confidence field is reserved but unused), skill
packaging.

## 2. Package structure (changes to loop/)

```
warrant/loop/
  loop/
    models.py             # + VerifierCheckOutcome, VerifierResult, VerifierInvoker,
                          #   CitationReport; NodeStatus.pre_execution_sha
    verifier_materializer.py   # Verifier prompt builder
    citationreport.py     # CitationReport projection + text render
    phases/
      execute.py          # + pre_execution_sha recording
      verify.py           # verify phase
  tests/
    fakes.py              # + FakeVerifierInvoker
    test_verifier_materializer.py
    test_citationreport.py
    test_verify.py
    test_runner.py        # updated: unpack tuple return + plan3 integration test
```

## 3. New models (`models.py`)

### NodeStatus update

Add `pre_execution_sha: str = ""` as a new field with a default:

```python
@dataclass
class NodeStatus:
    node_id: str
    status: str
    attempts: int = 0
    last_result: ExecutorResult | None = None
    pre_execution_sha: str = ""   # HEAD sha recorded before this node was dispatched
```

This field is set by `phases/execute.py` before invoking each node. It is used
by `verifier_materializer.py` to produce the exact diff for that node.

### VerifierCheckOutcome

```python
@dataclass
class VerifierCheckOutcome:
    check_id: str
    provenance: str    # "from_grounds" | "from_topic"
    tier: int          # 1, 2, or 3
    passed: bool | None   # None for Tier-3 (judgment only, not boolean)
    metric_value: str  # Tier-2: the computed value as a string; empty otherwise
    judgment: str      # Tier-3: the rendered assessment; empty otherwise
    detail: str = ""
```

`passed` is `True`/`False` for Tier-1. For Tier-2 it may be `None` (metric
reported, not a pass/fail verdict). For Tier-3 it is always `None`.

### VerifierResult

```python
@dataclass
class VerifierResult:
    node_id: str
    verdict: str                  # "pass" | "fail"
    confidence: float             # 0.0-1.0; reserved for second-verifier escalation
    check_outcomes: list[VerifierCheckOutcome]
    integrity_verdict: str        # "clean" | "integrity_failure" | "audit_catch"
    summary: str                  # one line max
```

`integrity_verdict` values:
- `"clean"` — no `from_grounds` Tier-1 failures.
- `"integrity_failure"` — one or more `from_grounds` Tier-1 checks failed.
- `"audit_catch"` — no `from_grounds` failures, but one or more `from_topic`
  Tier-1 failures.

A `VerifierResult` with `verdict == "fail"` and `integrity_verdict == "clean"`
is a Tier-2 drift or Tier-3 judgment failure — surfaces in the report but does
not route back to Execute.

### VerifierInvoker protocol

```python
class VerifierInvoker(Protocol):
    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult: ...
```

Mirrors `Invoker`. Plan 4 provides `ClaudeCodeVerifierInvoker`. Tests use
`FakeVerifierInvoker`.

### CitationReport

```python
@dataclass
class CitationReport:
    run_id: str
    plan_id: str
    grounded_clean: int
    grounded_conflicted: int
    grounded_ungrounded: int
    judgment_calls_documented: int    # ungrounded nodes that have a VerifierResult
    judgment_calls_undocumented: int  # ungrounded nodes without a VerifierResult
    tier1_run: int                    # Tier-1 check outcomes in verifier_results
    tier1_failed_integrity: int       # from_grounds Tier-1 with passed=False
    tier1_failed_audit: int           # from_topic Tier-1 with passed=False
    tier2_computed: int               # Tier-2 outcomes (metric computed)
    tier3_assessed: int               # Tier-3 outcomes
    plan_amendments: int              # nodes with amended_from != None in final plan
    suspiciously_clean: bool
    node_verdicts: dict[str, str]     # node_id -> "pass" | "fail" | "unverified"
    generated_at: str                 # ISO-8601
```

## 4. Verifier materializer (`verifier_materializer.py`)

```python
def materialize_verifier(
    node: PlanNode,
    principles: list[Result],
    run_state: RunState,
    executor_result: ExecutorResult,
    worktree_path: str,
    all_nodes: dict[str, PlanNode],
    pre_execution_sha: str = "",
) -> str:
```

### Prompt structure

```
{run_state.anchored_direction}
{run_state.anchored_honesty_constraint}

## Your role
You are a Verifier. You did not write the code below and you have not seen the
Executor's reasoning. Grade the Executor's work strictly against the cited
principles. Do not accept the Executor's self-assessment at face value.

## Plan node
Decision: {node.decision}
Approach: {node.approach}
Grounds state: {node.grounds_state}
[if conflicted]: Conflict resolution: {node.conflict_resolution}
[if ungrounded]: Grounds note: {node.grounds_note}

## Grounding
[for each principle id in node.grounds, looked up in principles dict]
  - Statement: {principle.statement}
  - Evidence: {principle.evidence_chunk}
  - Citation: {principle.citation.book}, ch. {principle.citation.chapter}, §{principle.citation.section}
  - Checkability: Tier {principle.checkability_tier} (1=mechanical, 2=measurable, 3=judgment)

[if any principle id in node.grounds not in principles dict]:
## Missing principles
The following principle ids are cited in the plan but were not retrieved:
  - {id}: grading cannot verify this citation

## Checks to grade
[for each check in node.applicable_checks]:
  - {check.check} (provenance: {check.provenance})

## Executor's self-report
Status claimed: {executor_result.status}
Summary: {executor_result.summary}
Principles honored: {executor_result.principles_honored}
Principles violated: {executor_result.principles_violated}

## Code diff (actual changes in worktree)
[git diff output or "No changes detected."]

## Return format
Return ONLY a JSON object matching this schema — no prose before or after:
{VerifierResult schema as JSON}
```

### Git diff

`subprocess.run(["git", "diff", pre_execution_sha], cwd=worktree_path,
capture_output=True, text=True, check=False)`.

- If `pre_execution_sha` is empty, falls back to
  `subprocess.run(["git", "diff"], ...)` (uncommitted changes only).
- If the subprocess fails or the diff is empty, the section reads
  `"No changes detected."`.
- Diff is truncated to 8000 characters with a truncation note to cap prompt
  size on large nodes.

Principle lookup: build a `dict[str, Result]` from the `principles` list for
O(1) access, same pattern as `materializer.py`.

## 5. Verify phase (`phases/verify.py`)

```python
def verify(
    plan: Plan,
    run_state: RunState,
    principles: list[Result],
    verifier_invoker: VerifierInvoker,
    out_dir: Path,
    per_node_attempt_cap: int = 3,
    watchdog_timeout: float = 300.0,
) -> tuple[RunState, list[VerifierResult]]:
```

### Steps

1. Collect nodes eligible for verification: nodes where
   `run_state.node_statuses[node.id].status == "done"` AND
   `run_state.node_statuses[node.id].last_result is not None`.

2. For each eligible node, call
   `verifier_materializer.materialize_verifier(...)` then
   `verifier_invoker.invoke(prompt, watchdog_timeout)`.
   
   On `invoke` exception (timeout or other): produce a synthetic
   `VerifierResult(verdict="fail", confidence=0.0,
   check_outcomes=[], integrity_verdict="clean",
   summary=f"verifier error: {exc}")` and continue. Using
   `integrity_verdict="clean"` ensures the exception does NOT route the node
   back to Execute (preventing infinite retry loops on a broken Verifier).

3. Route each `VerifierResult`:

   **`verdict == "pass"` or `integrity_verdict in ("clean", "audit_catch")`:**
   Node stays `"done"`. No RunState mutation.

   **`verdict == "fail"` and `integrity_verdict == "integrity_failure"`:**
   This is a `from_grounds` Tier-1 failure — integrity violation, routes back
   to Execute:
   - Increment `ns.attempts`.
   - If `ns.attempts >= per_node_attempt_cap`:
     - Build `reason` from failed check ids + `VerifierResult.summary`.
     - Call `planops.amend_node(plan, node.id, reason)`.
     - Call `planops.next_version(plan)`.
     - Call `planstore.save_plan(amended_plan, out_dir)`.
     - Update `run_state.plan_version`.
     - Rebuild `plan` reference.
     - Mark `ns.status = "failed"` (capped, not retried).
   - Else: mark `ns.status = "pending"` (eligible for next Execute pass).

   **`verdict == "fail"` and `integrity_verdict in ("clean", "audit_catch")`:**
   Tier-2 drift or Tier-3 judgment failure, no Execute routing. Node stays
   `"done"`. Surfaces in the report.

4. Call `runstore.save_run(run_state, out_dir)`.

5. Return `(run_state, list_of_verifier_results)`.

Verification runs serially (one node at a time). The Verifier is a judgment
agent; the cost of parallel invocation is not justified in v1.

## 6. Execute phase update (`phases/execute.py`)

Before dispatching each batch of ready nodes, record the current HEAD sha on
each node's `NodeStatus`:

```python
import subprocess as _subprocess

def _get_head_sha(worktree_path: str) -> str:
    try:
        result = _subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path,
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""
```

Called once per dispatch batch (before the `ThreadPoolExecutor` block):

```python
head_sha = _get_head_sha(run_state.worktree_path)
for node in ready:
    run_state.node_statuses[node.id].status = "in_flight"
    run_state.node_statuses[node.id].pre_execution_sha = head_sha
```

## 7. Citation report (`citationreport.py`)

### `generate_citation_report`

```python
def generate_citation_report(
    plan: Plan,
    run_state: RunState,
    verifier_results: dict[str, VerifierResult],
    suspiciously_clean_node_threshold: int = 5,
) -> CitationReport:
```

**Grounded counts:**
Iterate `plan.nodes`:
- `grounded_clean` — `grounds_state == "clean"`
- `grounded_conflicted` — `grounds_state == "conflicted"`
- `grounded_ungrounded` — `grounds_state == "ungrounded"`

**Judgment call counts:**
Among nodes with `grounds_state == "ungrounded"`:
- `judgment_calls_documented` — node has an entry in `verifier_results`
- `judgment_calls_undocumented` — node has no entry in `verifier_results`

**Tier counts** (from `verifier_results` only — reports what was actually assessed):
```python
for vr in verifier_results.values():
    for co in vr.check_outcomes:
        if co.tier == 1:
            tier1_run += 1
            if co.passed is False:
                if co.provenance == "from_grounds":
                    tier1_failed_integrity += 1
                else:
                    tier1_failed_audit += 1
        elif co.tier == 2:
            tier2_computed += 1
        elif co.tier == 3:
            tier3_assessed += 1
```

**Plan amendments:**
`plan_amendments = sum(1 for n in plan.nodes if n.amended_from is not None)`

**Node verdicts:**
```python
node_verdicts = {}
for node in plan.nodes:
    if node.id in verifier_results:
        node_verdicts[node.id] = verifier_results[node.id].verdict
    else:
        node_verdicts[node.id] = "unverified"
```

**Suspiciously clean flag:**
```python
suspiciously_clean = (
    judgment_calls_undocumented == 0
    and tier1_failed_integrity == 0
    and tier1_failed_audit == 0
    and plan_amendments == 0
    and len(plan.nodes) >= suspiciously_clean_node_threshold
)
```

### `render_citation_report`

```python
def render_citation_report(report: CitationReport) -> str:
```

Produces the summary format from the master design:

```
grounded decisions:    {grounded_clean + grounded_conflicted}   (clean {grounded_clean}, conflicted {grounded_conflicted})
judgment calls:        {total_jc}   (documented {documented}, undocumented {undocumented}{undoc_flag})
tier-1 checks:         {tier1_run} run / {tier1_failed_integrity + tier1_failed_audit} failed
                            ({tier1_failed_integrity} from_grounds <- integrity, {tier1_failed_audit} from_topic <- audit catch)
tier-2 metrics:        {tier2_computed} computed
tier-3 principles:     {tier3_assessed} assessed, judgment-only
plan amendments:       {plan_amendments}{amendments_note}
{suspicious_line}
```

- `undoc_flag` is `" <- flag"` when `undocumented > 0`, else empty.
- `amendments_note` is `"  (see version diff)"` when `plan_amendments > 0`, else empty.
- `suspicious_line` is `"SUSPICIOUSLY CLEAN — review manually"` when
  `suspiciously_clean`, else omitted.
- Right-aligned column widths use `str.rjust` for readability.

## 8. WarrantRunner update (`runner.py`)

### New constructor parameters

```python
verifier_invoker: VerifierInvoker,
verify_iteration_cap: int = 3,
```

### New return type

`run(direction: str) -> tuple[RunState, CitationReport]`
`resume(run_state: RunState) -> tuple[RunState, CitationReport]`

### Execute→Verify loop

Replaces the single `execute(...)` call in `run`:

```python
all_verifier_results: dict[str, VerifierResult] = {}
current_plan = plan

for _ in range(self._verify_iteration_cap):
    run_state = execute(current_plan, run_state, principles, self._invoker,
                        self._out_dir, **self._cfg)

    run_state, new_vr = verify(
        current_plan, run_state, principles,
        self._verifier_invoker, self._out_dir,
        per_node_attempt_cap=self._cfg["per_node_attempt_cap"],
        watchdog_timeout=self._cfg["watchdog_timeout"],
    )
    all_verifier_results.update({r.node_id: r for r in new_vr})

    # If verify amended the plan, reload
    current_plan = planstore.load_version(self._out_dir, run_state.plan_version)

    # Check if any nodes were routed back to pending
    has_pending = any(
        ns.status == "pending"
        for ns in run_state.node_statuses.values()
    )
    if not has_pending:
        break

report = generate_citation_report(current_plan, run_state, all_verifier_results)
return run_state, report
```

`resume` follows the same pattern: after the in_flight reset it enters the
Execute→Verify loop and returns `(run_state, report)`.

## 9. Test fakes (`tests/fakes.py`)

Add `FakeVerifierInvoker` alongside the existing `FakeInvoker`:

```python
class FakeVerifierInvoker:
    def __init__(self, results: list[VerifierResult] | None = None) -> None:
        self._queue: list[VerifierResult] = list(results or [])

    def invoke(self, prompt: str, timeout: float | None = None) -> VerifierResult:
        if not self._queue:
            raise RuntimeError("FakeVerifierInvoker queue exhausted")
        return self._queue.pop(0)
```

Helper:

```python
def make_pass_verifier_result(node_id: str) -> VerifierResult:
    return VerifierResult(
        node_id=node_id,
        verdict="pass",
        confidence=1.0,
        check_outcomes=[],
        integrity_verdict="clean",
        summary="all checks passed",
    )
```

## 10. Testing strategy

**`test_verifier_materializer.py`** — unit tests, real git fixture (tmp dir,
`git init`, one commit):
- Prompt contains `anchored_direction`, `anchored_honesty_constraint`.
- Prompt contains plan node decision + approach.
- Grounding section includes principle statement and evidence.
- Checks section lists check string + provenance.
- Executor self-report section present.
- Code diff section present; shows actual diff when `pre_execution_sha` is set.
- `pre_execution_sha` empty: falls back to `git diff` (may be empty).
- Missing principle ids produce `## Missing principles` section.
- Diff truncation at 8000 chars.

**`test_citationreport.py`** — unit tests, pure data:
- `generate_citation_report` counts grounded/conflicted/ungrounded correctly.
- `judgment_calls_documented` counts only nodes with VerifierResults.
- Tier counts from verifier_results.
- `suspiciously_clean` fires when all conditions met + node count >= threshold.
- `suspiciously_clean` does NOT fire for small plan (< threshold).
- `render_citation_report` includes integrity label and audit label.
- `undocumented <- flag` appears in render when undocumented > 0.
- `SUSPICIOUSLY CLEAN` line appears in render when flag is set.

**`test_verify.py`** — unit tests, FakeVerifierInvoker:
- `from_grounds` Tier-1 failure: node status set to `"pending"`, attempts incremented.
- `from_topic` failure only: node stays `"done"`.
- All pass: no RunState mutation.
- Attempt cap reached: node amended + marked `"failed"`.
- Verifier invoke exception: node stays `"done"` (synthetic result uses
  `integrity_verdict="clean"` to prevent routing back to Execute).
- `save_run` called after routing.

**`test_runner.py`** — update existing + add integration test:
- Existing tests: unpack `(run_state, report)` tuple.
- New integration test: fixture index + FakeLLM + FakeInvoker (all nodes done)
  + FakeVerifierInvoker (all pass). Assert `run_state.phase == "done"`,
  `isinstance(report, CitationReport)`, `report.tier1_failed_integrity == 0`.
- Re-verify routing test: FakeInvoker returns done, FakeVerifierInvoker returns
  integrity_failure on first call then pass on second. Assert node went through
  two Execute cycles.

## 11. Configuration defaults

| Parameter | Default |
|---|---|
| `verify_iteration_cap` | 3 |
| `suspiciously_clean_node_threshold` | 5 |
| `diff_truncation_chars` | 8000 |

(All overridable at `WarrantRunner` construction or `generate_citation_report`
call.)

## 12. Open questions deferred to plan 4

- `ClaudeCodeVerifierInvoker` implementation (spawns a Claude Code subagent
  in the worktree with the materialized Verifier prompt).
- `VerifierResult.confidence` use: second-verifier escalation logic, tie-break
  mechanism.
- Retrieval-quality evaluation (golden set scored with recall@k) — mentioned
  in master design §10 as a quality gate for Librarian changes; out of scope
  for plan 3.
- Skill packaging (`SKILL.md`, `ClaudeCodeInvoker`).
