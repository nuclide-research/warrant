# Warrant — design

A standalone autonomous coding agent, delivered as a Claude Code skill, whose
expertise is a curated library of books and whose every non-obvious decision is
traceable to a cited source.

Status: design approved 2026-05-21. This document is the contract for implementation.
"Warrant" is a working name (every decision is *warranted* by a cited source);
final name is the owner's call.

## 1. Summary

Warrant is a Claude Code skill. Given one direction, it runs as a completely
autonomous coding agent: it works out what the task needs, retrieves the
relevant principles from a library of real books, plans a solution grounded in
those principles, executes the plan autonomously inside an isolated git
worktree, verifies the result against the same literature, and hands back a
finished branch plus a citation report tracing every non-obvious decision to
its source — book, chapter, section.

The differentiator is not retrieval. RAG-for-code already exists; it retrieves
context and absorbs it silently, producing output with no audit trail.
Warrant's defining constraint is that the retrieval is *exposed in the output,
by chapter*. That converts a capability into a trust mechanism. The expertise
is a library you curate; the use of that expertise is an auditable record.

## 2. Scope

Warrant is Artifact A of a three-artifact program:

- **A — the skill** (this spec). The autonomous agent as a Claude Code skill.
- **B — the standalone CLI.** The same agent as its own program, with its own
  LLM wrapper and execution sandbox. Reuses this design. Out of scope here.
- **C — the starter kit.** Artifact B generalized into a clone-and-go template.
  Out of scope here.

This spec covers Artifact A only. Each artifact gets its own spec, plan, and
build cycle; B and C are sequenced after A and informed by it.

## 3. The idea, precisely

Every coding agent today is frozen weights plus a prompt. Its expertise is
invisible, fixed, and unaccountable. Warrant's expertise is a library of books:
`colophon-library`, the Markdown corpus produced by the `colophon` extractor.
You build a Warrant specialist by handing it a reading list. Point it at
security books, it is a security specialist; point it at frontend books, a
frontend specialist. You do not prompt-engineer it. You educate it.

Because the library is inspectable and the citations expose which parts of it
were used, the expertise is accountable in a way no black-box agent is. That is
the property to sell: curate the reading list, get the specialist; read the
citation report, audit the specialist.

### Honesty-by-construction

The single principle the whole system obeys: Warrant never claims more
grounding or verification than it actually has, and it marks the boundary
explicitly. A citation report where every decision is cited and every check
passed should read as suspicious, not impressive. The integrity of the system
is that it shows exactly what the books drove and what they did not, exactly
what was mechanically verified and what was not.

## 4. Architecture

Three components.

**The Library.** `colophon-library` — a private git repo of books as Markdown,
one directory per book, fed by the `colophon` extractor. Inspectable,
swappable, versioned. The agent's knowledge base is plain files.

**The Librarian.** A retrieval helper. At index time it distills the library
into structured principles; at query time it returns the principles relevant to
a query, each with its citation. Section 5.

**The Agent.** The skill itself, running the autonomous loop. Section 6.

Flow:

```
one direction
  -> orient     scope the task, set up the worktree, draft retrieval queries
  -> retrieve   Librarian returns relevant principles + citations
  -> plan       build the grounded plan artifact
  -> execute    work the plan autonomously in the worktree (subagent-delegated)
  -> verify     run tier-1 checks, tier-2 metrics; report tier-3 honestly
  -> hand back  finished branch + citation report
```

## 5. The Librarian — a principle-extraction index

Retrieval granularity is finer than chapter chunks. The retrieval unit is an
extracted *principle*.

**Index time.** Each chapter (a `colophon` Markdown file) is distilled — one
LLM pass — into a list of discrete principles. Each principle is a record:

```
{ statement, citation (book / chapter / section), checkability_tier, evidence_chunk }
```

`evidence_chunk` is the raw section text the principle was drawn from: a
citation can always drill from the principle down to the paragraph behind it.
Extracted principles are stored as inspectable files in the library — the
library is auditable down to the individual claim.

**Checkability tiers**, assigned at extraction time:

- **Tier 1 — mechanically checkable.** "Body text contrast >= 4.5:1."
  "Functions under 50 lines." The extractor compiles the principle into an
  executable check (a script, lint rule, or test) then and there.
- **Tier 2 — measurable.** "Prefer composition over inheritance." Not a
  boolean, but a computable signal (inheritance depth, composition-vs-extends
  counts). Compiled into a metric.
- **Tier 3 — judgment.** "The abstraction should feel natural." Not
  mechanizable. Flagged judgment-only.

Doing the prose-to-check translation at index time, once per book, is what
keeps verification deterministic instead of vibes-checking at runtime.

**Query time.** Semantic retrieval (local embedding model — no API key,
offline, shareable; the BARE pattern) over the principle *statements*.
`librarian query "<text>"` returns the top principles with citations and tiers.
`librarian index` rebuilds the index when the library changes.

The hardest single component is the Tier-1 compiler — prose principle to
executable predicate. Build risk noted in Section 15.

## 6. The Agent loop

Six phases.

1. **Orient.** Parse the direction; determine what the task touches and what
   "done" means; create the git worktree; draft the retrieval queries.
2. **Retrieve.** Call the Librarian. Hold the returned principles in context —
   retrieval happens *before* planning so that grounding is causal, not
   post-hoc.
3. **Plan.** Build the structured plan artifact (Section 7).
4. **Execute.** Work the plan in the worktree. Full autonomy, no mid-run gates;
   nothing in a worktree is unrecoverable. Plan-subtree execution is delegated
   to subagents to keep the main loop's context clean over a long run.
5. **Verify.** Run the plan's tier-1 checks, compute tier-2 metrics, report
   tier-3 as judgment-only. Failures loop back to Plan or Execute.
6. **Hand back.** A finished branch plus the citation report (Section 9).

**Termination.** The loop ends on exactly one of: verification passes; an
iteration cap is reached; or stuck-detection fires (no progress across a set
number of rounds). In the latter two it still hands back the branch, with an
honest report of what is unfinished.

The books re-enter twice — at Retrieve they guide the plan, at Verify they
grade the result. Same literature, both map and rubric.

## 7. The structured plan artifact

The plan is a *versioned decision tree*, not a flat task list. Hierarchy is
what makes grounding meaningful: a principle applies at a specific level.

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
      "amended_from": null,
      "amended_reason": null,
      "children": ["n2", "..."]
    }
  ]
}
```

**Grounding is three states, not two.**

- `clean` — `grounds` lists one or more principles that cleanly drove the
  decision.
- `conflicted` — `grounds` lists two or more principles that *disagreed*;
  `conflict_resolution` records which won and why. A conflict node is the most
  book-driven decision in the plan and the first thing a reviewer should read.
  It is never recorded as ungrounded.
- `ungrounded` — `grounds` is empty; the library was silent; `grounds_note`
  records why (no principle covered this, boilerplate, and so on). A judgment
  call, made legible.

**`applicable_checks` carries provenance.** `from_grounds`: the check comes
from a grounded tier-1 principle. `from_topic`: the index matched a check to
the approach text independent of what the agent cited. The distinction is
load-bearing at verify time. A `from_grounds` check failure means the agent
claimed a principle and violated it — an integrity failure. A `from_topic`
failure means an applicable principle the agent never cited was violated — an
audit catch. The report must not blend them.

**Versioning.** Architectural-level nodes are planned eagerly in v1 — few,
load-bearing, and you do not want to discover the architecture eight nodes
deep. Structural and implementation subtrees expand lazily: each expansion is a
new plan version. Before executing a subtree the agent must expand it, ground
it, and commit it as a version. That commit is the gate — a *self*-gate. There
is no human-approval gate; a human gate would break walk-away autonomy. When a
node is revised under contact with reality, the node is amended
(`amended_from`, `amended_reason`) and the version history preserves the diff.

## 8. Verification

Verify executes the plan's predetermined check manifest — the
`applicable_checks` already attached to every node — so verification is a run,
not a discovery.

- Tier-1 checks are executed; pass/fail is deterministic.
- Tier-2 metrics are computed and reported as values, not verdicts.
- Tier-3 principles are reported as "not mechanically checked — judgment only."

Failure routing: a `from_grounds` tier-1 failure is an integrity failure and
loops back to Execute (the agent did not do what it grounded). A `from_topic`
failure is surfaced in the report as an audit catch. Tier-2 drift is surfaced
for review.

## 9. The citation report

A pure projection of the final plan artifact and the verify results. Example
shape:

```
grounded decisions:    11   (clean 9, conflicted 2)
judgment calls:         6   (documented 4, undocumented 2  <- flag)
tier-1 checks:         23 applicable / 23 run / 2 failed
                            (1 from_grounds <- integrity, 1 from_topic <- audit catch)
tier-2 metrics:         4 computed
tier-3 principles:      3 reported, not mechanically checked
plan amendments:        2  (see version diff)
```

A `suspiciously clean` flag fires when undocumented judgment calls are zero,
tier-1 pass rate is 100%, and there are zero amendments — *and* the plan
exceeds a node-count threshold. A clean small plan is legitimately clean; a
clean large one is the tell.

## 10. Feedback loops

Two, both emergent from the artifacts above.

- **Library-fit.** If the agent rarely cites a book you added, your reading
  list does not match your tasks. The citation report is a signal on curation.
- **Library self-evaluation.** Aggregated across runs, the plan amendment diffs
  show which grounded principles keep getting amended away under contact with
  real code. A principle that repeatedly fails to survive is one the book got
  wrong, or that does not fit this codebase. The library becomes
  self-evaluating, not merely inspectable.

## 11. Autonomy and safety

Warrant runs with full autonomy and no mid-run gates, inside an isolation
boundary. It works in a dedicated git worktree with no deploy credentials.
Irreversible or destructive actions (deploy, force-push of a shared branch,
data deletion, spend) are outside the boundary — not gated, simply unreachable.
The autonomous run is uninterrupted from one direction to a finished branch;
the human performs the merge or ship. "Completely autonomous" is satisfied
because the run never stops and never asks; it is safe to distribute because
the blast radius is a throwaway branch.

## 12. Phase 0 — research, and the seed library

Phase 0 is a real O'Reilly research pass, run with `colophon`, before
implementation. It targets four areas, each mapping to a component:

- **Agent architecture** — the loop, autonomy patterns, tool use.
- **RAG, embeddings, retrieval** — the Librarian.
- **Information extraction from text** — the principle-extraction pass (the
  hardest component).
- **Static analysis, ASTs, writing linters** — the Tier-1 check compiler (the
  other hardest component).

Phase 0 produces three things at once: the design-informing methodology, the
engineering references for the build, and the seed library — the books read to
build Warrant become Warrant's starting shelf. The finished agent ships already
knowing agentic coding, RAG, and static analysis, because that is what it is
built from. Its first citations are the books that built it.

The construction and the product are the same loop: read the literature, apply
it, cite it. Warrant is built the way Warrant works.

## 13. Execution environment

Artifact A runs *inside* Claude Code. Claude Code provides the real shell and
file tools; the skill's job is to fence them into the git worktree and drive
the loop. Plan-subtree execution is delegated to Claude Code subagents, all
sharing the one worktree. There is no handoff to a separate process. Artifact
B, the standalone CLI, must build its own shell-in-worktree sandbox; that is
B's concern, and A must not be designed around it.

## 14. Build phases

High-level; the detailed implementation plan is produced separately by the
writing-plans step.

1. **Phase 0** — O'Reilly research pass (Section 12). Produces the methodology,
   build references, and seed library.
2. **The Librarian** — principle-extraction index, semantic retrieval, the
   Tier-1 check compiler.
3. **The plan artifact and the loop** — the structured plan, orient / retrieve
   / plan / execute, worktree, subagent delegation.
4. **Verification** — running checks and metrics, the citation report.
5. **Skill packaging** — the Claude Code skill that drives all of the above;
   distribution.

## 15. Open questions and risks

- **Principle-extraction reliability.** An LLM extracting principles from prose
  can distort. Mitigations: every principle links to its `evidence_chunk` for
  verification against the source; extracted principles are stored as
  inspectable files and can be corrected; extraction is a bounded,
  once-per-book task.
- **The Tier-1 check compiler is the hardest component.** Prose-to-executable-
  predicate works only for the genuinely mechanical subset; the tiering is
  honest about that. Phase 0's static-analysis research targets this directly.
- **Library scale.** Retrieval quality and index build time at a large library
  are unproven; revisit after the first working Librarian.
- **Parameters left to implementation.** The iteration cap, the stuck-detection
  round count, and the `suspiciously clean` node-count threshold are named here
  and set during the build.
