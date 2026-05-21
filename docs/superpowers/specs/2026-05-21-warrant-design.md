# Warrant — design (v2, research-grounded)

A standalone autonomous coding agent, delivered as a Claude Code skill, whose
expertise is a curated library of books and whose every non-obvious decision is
traceable to a cited source.

Status: v1 was the brainstorm design (2026-05-21). v2 incorporates the Phase 0
research synthesis — a pressure-test against *Agentic Coding with Claude Code*,
*Agentic Architectural Patterns for Building Multi-Agent Systems*, and *Building
AI Agents with LLMs, RAG, and Knowledge Graphs*. Changelog in Section 16.
"Warrant" is a working name; final name is the owner's call.

## 1. Summary

Warrant is a Claude Code skill. Given one direction, it runs as a completely
autonomous coding agent: it retrieves the relevant principles from a library of
real books, plans a solution grounded in those principles, executes the plan
autonomously inside an isolated git worktree, verifies the result against the
same literature **through a structurally separate verifier**, and hands back a
finished branch plus a citation report tracing every non-obvious decision to
its source — book, chapter, section.

The differentiator is not retrieval. RAG-for-code already exists; it retrieves
context and absorbs it silently, producing output with no audit trail.
Warrant's defining constraint is that the retrieval is exposed in the output,
by chapter. That converts a capability into a trust mechanism.

## 2. Scope

Warrant is Artifact A of a three-artifact program: **A — the skill** (this
spec); **B — the standalone CLI**; **C — the starter kit**. This spec covers
Artifact A only. B and C reuse this design and are sequenced after it.

## 3. The idea, precisely

Every coding agent today is frozen weights plus a prompt — invisible, fixed,
unaccountable expertise. Warrant's expertise is a library of books:
`colophon-library`, the Markdown corpus produced by the `colophon` extractor.
You build a Warrant specialist by handing it a reading list. You do not
prompt-engineer it. You educate it. Because the library is inspectable and the
citations expose which parts of it were used, the expertise is accountable.

### Honesty-by-construction

The single principle the whole system obeys: Warrant never claims more
grounding or verification than it actually has, and it marks the boundary
explicitly. v2 makes this *structural* rather than aspirational: the agent that
renders the honesty verdict is not the agent that did the work (Section 8).

## 4. Architecture

Three components, and within the Agent, two subagent roles.

**The Library.** `colophon-library` — a private git repo of books as Markdown,
fed by `colophon`. Inspectable, swappable, versioned.

**The Librarian.** A retrieval helper: at index time it distills the library
into structured principles and a principle graph; at query time it returns the
principles relevant to a query, each with its citation. Section 5.

**The Agent.** The skill itself, running the autonomous loop (Section 6). It
operates through two subagent roles, exploiting Claude Code subagent context
isolation: **Executor** subagents work plan subtrees; a **Verifier** subagent
grades the result. The isolation is the point — the Verifier starts clean and
cannot see the Executor's reasoning.

Flow:

```
one direction
  -> orient     profile, scope, anchor the direction, set up the worktree, draft queries
  -> retrieve   Librarian returns relevant principles + citations (reranked)
  -> plan       build the grounded plan artifact (a versioned decision tree)
  -> execute    Executor subagents work subtrees in the worktree
  -> verify     a separate Verifier subagent grades against the literature
  -> hand back  finished branch + citation report
```

## 5. The Librarian — a HybridRAG principle index

Retrieval granularity is finer than chapter chunks. The retrieval unit is an
extracted *principle*. Following *Building AI Agents with LLMs, RAG, and
Knowledge Graphs* (ch7), the index is hybrid: a semantic index for relevance
plus a lightweight graph for structure. Flat vector RAG alone "neglects
relationships" (ch7) — and Warrant's design depends on one relationship in
particular.

**Index time.** Each chapter is distilled — one LLM pass — into discrete
principles. Each principle is a record:

```
{ id, statement, citation (book / chapter / section), checkability_tier, evidence_chunk }
```

`evidence_chunk` is the raw section text behind the principle. Extracted
principles are stored as inspectable files — the library is auditable down to
the claim.

**Checkability tiers**, assigned at extraction time:

- **Tier 1 — mechanically checkable.** "Body text contrast >= 4.5:1." Compiled
  into an executable check (script, lint rule, test) at index time.
- **Tier 2 — measurable.** "Prefer composition over inheritance." Compiled into
  a computable metric, not a boolean.
- **Tier 3 — judgment.** "The abstraction should feel natural." Not
  mechanizable; flagged judgment-only.

**The principle graph.** Also at index time, the LLM pass extracts edges
between principles — three types:

- `refines` — hierarchy (a section principle specializes a chapter principle).
- `contradicts` — two principles disagree. This is the key relationship: the
  plan artifact's `conflicted` grounding state (Section 7) *is* this edge.
  Extracting it once at index time turns conflict detection from runtime
  guesswork into a lookup.
- `shares-topic-with` — used to resolve `from_topic` check provenance
  (Section 7).

The graph is small — a few hundred to a few thousand principle nodes — well
inside the tractable range (ch7). It is not a replacement for the semantic
index; it is the structural layer the flat index discards.

**Query time.** Semantic retrieval over principle *statements*, then a
**rerank** step before returning the top principles (ch6: reranking materially
improves retrieval precision and reduces the chance the genuinely-relevant
principle falls below the cutoff). `librarian index` rebuilds the index and
graph; `librarian query "<text>"` returns reranked principles with citations,
tiers, and graph neighbors.

The hardest single component is the Tier-1 compiler — prose principle to
executable predicate. Build risk in Section 15.

## 6. The Agent loop

Six phases.

1. **Orient.** Parse the direction. Derive a one-paragraph **specialist
   persona** from the library's table-of-contents set (a profiling step — the
   "point it at security books, get a security specialist" property made
   explicit). Emit an **anchored objective block** — `#DIRECTION:` and
   `#HONESTY-CONSTRAINT:` — that is re-injected at the head of every
   subsequent round and every subagent prompt, so the one thing that must not
   drift over a long autonomous run does not. Create the git worktree. Draft
   the retrieval queries.
2. **Retrieve.** Call the Librarian. Hold the returned principles in context —
   retrieval happens before planning so grounding is causal, not post-hoc.
   Bound the count; write the full principle set to a file and keep only the
   cited subset live once planning completes.
3. **Plan.** Build the structured plan artifact (Section 7).
4. **Execute.** Work the plan in the worktree via **Executor subagents**, one
   per subtree (Section 7.1 governs the subagent contract). Full autonomy, no
   mid-run gates — nothing in a worktree is unrecoverable. Each plan
   version-commit is a **checkpoint**.
5. **Verify.** A separate **Verifier subagent** grades the result (Section 8).
   Failures route back to Plan or Execute.
6. **Hand back.** A finished branch plus the citation report (Section 9).

**Context compression.** The main loop does not accumulate full subtree
history. Once an Executor subtree completes, the main loop retains only the
Verifier's structured result; the detail lives on the filesystem as plan
versions and is re-readable, not resident.

**Checkpoint and resume.** Each plan version-commit is a resume point. A
Warrant re-invoked on an existing worktree reads the latest plan version, diffs
it against the working tree, and resumes at the first un-executed node.

**Termination.** The loop ends on exactly one of: verification passes; the
global iteration cap is reached; or stuck-detection fires. Stuck-detection does
not bare-retry — a recurring `from_grounds` failure triggers a *node amendment*
(`amended_from` / `amended_reason`), changing the approach rather than repeating
it. Each subagent runs under a **watchdog timeout** (a hung subagent marks its
node unfinished rather than freezing the run). Each node has a **per-node
attempt cap** so one node cannot consume the global budget in a fail-amend-fail
loop. On any non-pass termination, Warrant still hands back the branch plus an
honest report of what is unfinished.

The books re-enter twice — at Retrieve to guide the plan, at Verify to grade
the result.

## 7. The structured plan artifact

The plan is a *versioned decision tree*, not a flat task list.

```json
{
  "plan_id": "uuid",
  "task": "string",
  "version": 1,
  "nodes": [
    {
      "id": "n1",
      "level": "architectural | structural | implementation",
      "decision": "short statement of the decision",
      "approach": "how it is done",
      "grounds": ["principle-id", "..."],
      "grounds_state": "clean | conflicted | ungrounded",
      "grounds_note": "required when ungrounded — why the library was silent",
      "conflict_resolution": "required when conflicted — which principle won, why",
      "applicable_checks": [
        { "check": "check-id", "provenance": "from_grounds | from_topic" }
      ],
      "depends_on": ["sibling-node-id", "..."],
      "amended_from": null,
      "amended_reason": null,
      "children": ["n2", "..."]
    }
  ]
}
```

**Grounding is three states.** `clean` (one or more principles cleanly drove
the decision); `conflicted` (`grounds` lists principles that disagree —
`conflict_resolution` records which won and why; this is the principle graph's
`contradicts` edge surfaced; it is the first thing a reviewer should read);
`ungrounded` (`grounds` empty, library silent, `grounds_note` records why).

**`applicable_checks` carries provenance.** `from_grounds`: the check comes
from a grounded Tier-1 principle. `from_topic`: the principle graph's
`shares-topic-with` edges matched a check to the approach independent of what
the agent cited. A `from_grounds` failure is an integrity failure (claimed a
principle, violated it); a `from_topic` failure is an audit catch. The report
must not blend them.

**`depends_on` edges.** Sibling subtrees are frequently not independent — node
n3 implements an interface n4 consumes. `depends_on` records this. Warrant
parallelizes only provably-independent siblings, and applies the parallel-work
checklist (independent files, correct starting state, test the merge) before
any parallel Executor dispatch. Without this, subagents sharing the worktree
silently overwrite each other.

**Versioning.** Architectural-level nodes are planned eagerly in v1.
Structural and implementation subtrees expand lazily — each expansion is a new
plan version, and committing that version is the self-gate before executing
the subtree. There is no human-approval gate. Node revisions are amended
(`amended_from`, `amended_reason`); the version history preserves the diff.

### 7.1 Subagent contracts

The Executor subagent's quality depends entirely on the prompt it is handed —
it has no Librarian access and no shared context. When a subtree is delegated,
its prompt is **materialized from the node**: the decision, the approach, the
**full text** of every grounded principle (not IDs — the subagent cannot
resolve them), the check manifest, the `depends_on` context, and the anchored
`#DIRECTION:` / `#HONESTY-CONSTRAINT:` block.

Subagents **return a structured, machine-readable result** — checks run,
pass/fail, principles honored or violated, node amendments — never a prose
summary. A subagent's default behavior is to summarize the artifact away; the
contract forbids it, because Verify and the citation report consume this data.

## 8. Verification — the wall

Verification runs in a **Verifier subagent that is structurally distinct from
the Executor.** An agent that grades its own work rationalizes its mistakes;
honesty-by-construction is only real when a wall separates the agent that makes
the claim from the agent that checks it.

The Verifier receives `{ plan node, full text of the cited principles, the
check manifest, the Executor's diff }` — and, by Claude Code subagent context
isolation, has never seen the Executor's reasoning. It:

- Executes the Tier-1 checks; pass/fail is deterministic.
- Computes the Tier-2 metrics; reports them as values, not verdicts.
- Renders an explicit, separate judgment-only assessment for each Tier-3
  principle (it does not accept the Executor's "I considered it").
- Renders the `from_grounds` / `from_topic` integrity verdict.
- Computes the `suspiciously clean` flag.

Failure routing: a `from_grounds` Tier-1 failure is an integrity failure and
routes back to Execute; a recurring one triggers a node amendment. A
`from_topic` failure surfaces in the report as an audit catch. Tier-2 drift
surfaces for review.

## 9. The citation report

Produced by the Verifier, as a projection of the final plan artifact and the
verify results. Example shape:

```
grounded decisions:    11   (clean 9, conflicted 2)
judgment calls:         6   (documented 4, undocumented 2  <- flag)
tier-1 checks:         23 applicable / 23 run / 2 failed
                            (1 from_grounds <- integrity, 1 from_topic <- audit catch)
tier-2 metrics:         4 computed
tier-3 principles:      3 assessed, judgment-only
plan amendments:        2  (see version diff)
```

A `suspiciously clean` flag fires when undocumented judgment calls are zero,
Tier-1 pass rate is 100%, and amendments are zero — and the plan exceeds a
node-count threshold (a clean small plan is legitimately clean; a clean large
one is the tell).

## 10. Feedback loops

- **Library-fit.** If the agent rarely cites a book, the reading list does not
  match the tasks.
- **Library self-evaluation.** Aggregated plan amendment diffs show which
  grounded principles keep getting amended away under contact with real code —
  principles the book got wrong, or that do not fit this codebase.
- **Retrieval-quality evaluation.** A golden set of (task -> principles that
  should be retrieved) pairs, scored with recall@k, gates Librarian changes.
  Nothing else checks whether the Librarian retrieved the *right* principles;
  a wrong retrieval produces a confidently mis-grounded plan whose citation
  report still looks clean.

## 11. Autonomy and safety

Warrant runs with full autonomy and no mid-run gates, inside an isolation
boundary: a dedicated git worktree with no deploy credentials. Irreversible or
destructive actions are outside the boundary — not gated, simply unreachable.
The run is uninterrupted from one direction to a finished branch; the human
performs the merge or ship. Checkpointing (Section 6) makes a crashed run
resumable rather than restart-from-zero.

## 12. Phase 0 — research, and the seed library

Phase 0 is a real O'Reilly research pass run with `colophon`, covering agent
architecture, RAG / embeddings / knowledge graphs, information extraction, and
static analysis. This v2 spec is the first product of it: the pressure-test
against three agent-architecture books drove every change in Section 16. Phase
0 also produces the **seed library** — the books read to build Warrant become
Warrant's starting shelf. The construction and the product are the same loop.

## 13. Execution environment

Artifact A runs inside Claude Code. Claude Code provides the real shell and
file tools; the skill fences them into the git worktree and drives the loop.
Executor and Verifier subagents are Claude Code subagents — their context
isolation is what makes the Section 8 wall free. Artifact B, the standalone
CLI, must build its own shell-in-worktree sandbox and its own subagent
isolation; that is B's concern, and A must not be designed around it.

## 14. Build phases

1. **Phase 0** — O'Reilly research pass; methodology, build references, seed
   library. (Underway.)
2. **The Librarian** — principle-extraction index, the principle graph,
   semantic retrieval + rerank, the Tier-1 check compiler.
3. **The plan artifact and the loop** — the structured plan with `depends_on`,
   orient (with profiling + anchoring) / retrieve / plan / execute, worktree,
   checkpointing, Executor-subagent contracts.
4. **Verification** — the Verifier subagent, checks/metrics, the citation
   report, retrieval-quality evals.
5. **Skill packaging** — the Claude Code skill that drives all of the above;
   distribution.

## 15. Open questions and risks

- **The Tier-1 check compiler is the hardest component.** Prose-to-executable-
  predicate works only for the genuinely mechanical subset; the tiering is
  honest about that.
- **A single Verifier is itself a single point of judgment failure.** The wall
  removes self-grading, but one Verifier can still be wrong. For a node where
  the Verifier's confidence is low, a second independent Verifier with a
  tie-break is the documented escalation; v1 does not mandate it but the design
  must leave room for it.
- **Principle-extraction reliability.** An LLM extracting principles and graph
  edges can distort. Mitigated by `evidence_chunk` back-links, inspectable
  principle files, and the retrieval-quality golden set.
- **Library scale.** Retrieval quality and index/graph build time at a large
  library are unproven; revisit after the first working Librarian.
- **Parameters left to implementation.** The iteration cap, per-node attempt
  cap, watchdog timeout, stuck-detection round count, rerank cutoff, and
  `suspiciously clean` node-count threshold are named here and set during the
  build.

## 16. Changelog: v1 -> v2 (Phase 0 research)

Driven by the pressure-test against *Agentic Coding with Claude Code*,
*Agentic Architectural Patterns for Building Multi-Agent Systems*, and
*Building AI Agents with LLMs, RAG, and Knowledge Graphs*.

**Load-bearing (v1 was unsound without these):**

1. **Separate Verifier subagent (the wall).** v1 had one agent plan, execute,
   and grade its own grounding. The literature: an agent grading itself
   rationalizes its mistakes. Verification now runs in a structurally distinct
   subagent. (Sections 4, 6, 8, 9.)
2. **Materialized subagent task-specs.** A delegated subtree's subagent gets
   the full principle *text*, not IDs — it has no Librarian access. (7.1.)
3. **Structured subagent return contract.** Subagents return machine-readable
   results, not prose summaries that drop the artifact. (7.1.)

**Robustness and drift (v1 was fragile without these):**

4. Incremental checkpointing + a resume protocol. (6, 11.)
5. Persistent instruction anchoring of the direction and honesty constraint.
   (6.)
6. A context-compression strategy for the main loop. (6.)
7. Explicit `depends_on` edges in the plan tree; parallelize only independent
   siblings. (7.)
8. Stuck-detection wired to node amendment; per-subagent watchdog timeout;
   per-node attempt cap. (6.)

**Quality and correctness:**

9. HybridRAG — keep the semantic index, add a principle graph (`refines`,
   `contradicts`, `shares-topic-with`); the `conflicted` grounding state is the
   `contradicts` edge. (5, 7.)
10. A rerank step after semantic retrieval. (5.)
11. Librarian retrieval-quality evaluation — a golden set scored with
    recall@k. (10.)
12. A profiling step in Orient — derive a specialist persona from the library.
    (6.)
