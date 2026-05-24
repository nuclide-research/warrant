# Warrant — Session State

Last updated: 2026-05-22

**Project.** Warrant is a book-grounded autonomous coding agent: a Claude Code
skill that runs a fully autonomous coding agent grounded in O'Reilly engineering
books, given a single direction. Built as separate artifacts, one at a time:
**A** the skill, then follow-on artifacts (**B** a CLI / the "wild Bill"
no-sandbox variant Nick floated, **C** a shareable kit). Design spec:
`docs/superpowers/specs/2026-05-21-warrant-design.md`.

Artifact A has two parts: the **Librarian** (the retrieval engine, done) and the
**Agent** (the autonomous loop that uses it). The Agent is being built as four
sequential plans; plan 1 of 4 is done.

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
- `WarrantRunner.run(direction)` drives the full loop; `.resume(run_state)`
  re-enters Execute from a checkpoint.
- `Invoker` protocol: plan 4 skill wrapper provides `ClaudeCodeInvoker`;
  tests use `FakeInvoker`.

## Open / next

1. **The Agent, plan 3 of 4: Verify + citation report.**
   The Verifier subagent, Tier-1/2/3 check execution, failure routing
   (from_grounds → Execute, from_topic → report), the citation report
   projection. Same path: brainstorm → spec → plan → subagent build.
2. **The Warrant skill wrapper (plan 4).** `SKILL.md` + `ClaudeCodeInvoker`.
3. Artifacts B and C, after A.
4. Optional: live re-verify of Librarian edge extraction on a real book.

## Notes

- `colophon-library` (the book corpus) finished at 195 books — PRIVATE repo
  (full book text is copyrighted).
- The Tier-1 *check compiler* is deliberately out of scope — its own future
  sub-project; `checkability_tier` is populated but not compiled.
- `~/warrant` has no git remote; work lands on `main` locally.
