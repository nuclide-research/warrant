# Warrant — Session State

Last updated: 2026-05-24

**Project.** Warrant is a book-grounded autonomous coding agent: a Claude Code
skill that runs a fully autonomous coding agent grounded in O'Reilly engineering
books, given a single direction. Built as separate artifacts, one at a time:
**A** the skill, then follow-on artifacts (**B** a CLI / the "wild Bill"
no-sandbox variant Nick floated, **C** a shareable kit). Design spec:
`docs/superpowers/specs/2026-05-21-warrant-design.md`.

Artifact A has two parts: the **Librarian** (the retrieval engine, done) and the
**Agent** (the autonomous loop that uses it). The Agent is being built as four
sequential plans; plans 1–3 of 4 are done.

## Done — the Librarian (Artifact A's retrieval engine)

The Librarian indexes reusable engineering principles from the `colophon` book
library into a HybridRAG index: a semantic vector index plus a principle graph,
every principle carrying a citation (book/chapter/section) and a checkability
tier (1 mechanical, 2 measurable, 3 judgment).

- Built via `superpowers:subagent-driven-development` from a 12-task plan
  (`docs/superpowers/plans/2026-05-21-warrant-librarian.md`). Each task got an
  implementer + a spec review + a code-quality review. A final
  whole-implementation review caught a corpus-parser bug every per-task review
  missed (real chapter Markdown opens with an H2, not an H1).
- On `main` (branch `librarian` merged fast-forward, then deleted). 33 tests
  pass. Package at `librarian/`; modules: models, corpus, extract, llm, edges,
  embedding, store, indexer, query, cli.
- CLI: `librarian index <book-library>` builds the index; `librarian query
  <text>` retrieves ranked principles with citations and tiers.
- Live-verified: indexed a real book (*AI for Mass-Scale Code Refactoring and
  Analysis*) end to end — 190 principles, correct citations, working query.
  The smoke test exposed two crash bugs the stub-LLM tests hid: an unwrapped
  edge-extraction call and a principle-id collision. Both fixed (`45269b7`,
  `d0d700f`).
- Edge extraction redesigned (`1984874`): the old version sent every principle
  in one prompt and overflowed the token limit on a real book, leaving the
  graph empty. Candidate edges are now gated by embedding similarity (each
  principle's nearest neighbors) and classified in bounded LLM batches, so the
  request size is capped regardless of corpus size. Unit-verified — the
  batching scales; a live re-verify on a real book is still pending.

## Done — the Agent, plan 1 of 4: the plan artifact

The plan artifact is the versioned decision-tree data structure the agent loop
builds, versions, amends, and persists. A self-contained Python package under
`agent/`, with zero runtime dependencies beyond the standard library.

- Built via `superpowers:subagent-driven-development` from the 9-task plan
  `docs/superpowers/plans/2026-05-21-warrant-plan-artifact.md`. Each task got an
  implementer, a spec-compliance review, and a code-quality review; a final
  whole-implementation review closed it out.
- Merged to `main` (branch `agent-plan-artifact`, fast-forward, then deleted).
  69 tests pass. HEAD `ba12a26`.
- Three modules under `agent/agent/`: `plan.py` is the schema (`ApplicableCheck`,
  `PlanNode`, `Plan` frozen dataclasses with `__post_init__` validation);
  `planstore.py` is I/O (dict round-trip plus versioned `plan.v{N}.json`
  persistence); `planops.py` is operations (`new_plan`, `add_node`, `amend_node`,
  `next_version` for mutation; `find_node`, `children`, `independent_siblings`
  for queries). The three modules form a clean stack: `planstore` and `planops`
  both import from `plan`, and neither imports the other.
- One fix landed beyond the plan's literal code. A code review caught that
  `amend_node` forwarded its `**changes` straight into `dataclasses.replace`, so
  a caller could pass `id=` and rewrite a node's identity, producing duplicate
  ids and breaking the unique-id invariant `add_node` enforces. `amend_node` now
  rejects `id`, `amended_from`, and `amended_reason` in `changes` (commit
  `df8313c`).

## Done — the Agent, plan 2 of 4: the loop package

The `loop/` package drives the Orient → Retrieve → Plan → Execute phases.

- Built via `superpowers:subagent-driven-development` from the 13-task plan
  `docs/superpowers/plans/2026-05-24-warrant-agent-loop.md`.
- Merged to `main`. All tests pass. HEAD `2ec060180b94e4785a3942bb1b14a69cae2819be`.
- Modules: `models`, `runstore`, `worktree`, `materializer`,
  `phases/{orient,retrieve,plan,execute}`, `runner`.
- `WarrantRunner.run(direction)` drove Orient → Retrieve → Plan → Execute;
  `.resume(run_state)` re-entered Execute from a checkpoint.
- `Invoker` protocol: plan 4 skill wrapper provides `ClaudeCodeInvoker`;
  tests use `FakeInvoker`.

## Done — the Agent, plan 3 of 4: Verify + citation report

Extends `loop/` with a Verify phase and CitationReport projection. `WarrantRunner.run()`
now drives Orient → Retrieve → Plan → Execute → Verify and returns
`tuple[RunState, CitationReport]`.

- Built via `superpowers:subagent-driven-development` from the 8-task plan
  `docs/superpowers/plans/2026-05-24-warrant-verify-citationreport.md`. Design spec:
  `docs/superpowers/specs/2026-05-24-warrant-verify-citationreport-design.md`.
- Merged to `main` (branch `worktree-agent-verify`, fast-forward, then deleted).
  95 tests pass. HEAD `77db7a1`.
- New modules: `verifier_materializer.py`, `citationreport.py`, `phases/verify.py`.
- Updated: `models.py` (added `VerifierCheckOutcome`, `VerifierResult`, `CitationReport`,
  `VerifierInvoker` Protocol, `pre_execution_sha` on `NodeStatus`); `phases/execute.py`
  (records `pre_execution_sha` via `_get_head_sha` before each dispatch batch);
  `runner.py` (added `_execute_verify_loop`, `verifier_invoker`, `verify_iteration_cap`).
- `VerifierInvoker` protocol: `invoke(prompt, timeout) -> VerifierResult`. Tests use
  `FakeVerifierInvoker`. Live skill wrapper provides the real invoker in plan 4.
- `integrity_failure` verdict routes node back to pending and re-executes; at
  `per_node_attempt_cap` the node is amended + marked failed. `audit_catch` and
  `clean` leave the node done. Verifier exceptions produce a synthetic clean result
  (no routing loop).
- `CitationReport` counts grounded/conflicted/ungrounded nodes, tier-1/2/3 checks,
  amendments, and sets `suspiciously_clean` flag when no stress signals appear on
  plans of >= 5 nodes. `render_citation_report()` produces formatted text output.
- Two bugs caught and fixed by reviews: `_get_diff` untracked-file quoting (use
  `git ls-files -z` not `git status --short`); exhausted-phase spin in
  `_execute_verify_loop` (break when `phase == "exhausted"`).

## Open / next

1. **The Warrant skill wrapper (plan 4).** `SKILL.md` + `ClaudeCodeInvoker` +
   `ClaudeCodeVerifierInvoker`. Wires the runner into a Claude Code skill invoked
   with a single direction string.
2. Artifacts B and C, after A.
3. Optional: live re-verify of Librarian edge extraction on a real book.

## Notes

- `colophon-library` (the book corpus) finished at 195 books — PRIVATE repo
  (full book text is copyrighted).
- The Tier-1 *check compiler* is deliberately out of scope — its own future
  sub-project; `checkability_tier` is populated but not compiled.
- `~/warrant` has no git remote; work lands on `main` locally.
