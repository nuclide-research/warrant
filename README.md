<h1 align="center">warrant</h1>

<h4 align="center">Book-grounded coding agent that cites its sources.</h4>

<p align="center">
  <a href="https://github.com/nuclide-research/warrant/blob/main/LICENSE"><img src="https://img.shields.io/github/license/nuclide-research/warrant?style=flat-square" alt="license"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python" alt="python"></a>
  <a href="https://nuclide-research.com"><img src="https://img.shields.io/badge/by-NuClide-blue?style=flat-square" alt="NuClide"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#citation-report">Citation report</a> •
  <a href="#scope">Scope</a>
</p>

---

warrant is a coding agent that grounds every plan step in engineering principles drawn from a Librarian index. One direction goes in. The agent decomposes it into a plan tree, retrieves principles for each task, annotates plan nodes with checks drawn from those principles, executes each task in an isolated git worktree, and verifies the executor's output against the cited sources. The output is a diff plus a citation report: which decisions were grounded, which were judgment calls, which checks fired.

A generic coding agent picks a path and writes code. warrant picks a path, cites the book chapter that supports it, runs the code, and verifies the result against the citation. A failed integrity check routes the node back to pending and re-runs. A clean or audit-catch verdict closes it.

Two entry points: `/warrant <direction>` as a Claude Code skill, or `warrant run --direction "..."` as a standalone CLI on the Anthropic API.

# Features

- Orient, Retrieve, Plan, Execute, Verify loop. Every node carries a citation.
- HybridRAG index over engineering principles (Librarian). Embedding plus reranker plus keyword.
- 15-principle bundled sample index. Run immediately, no custom index required.
- Isolated git worktree per executor node. Failed nodes do not poison the tree.
- Verifier reads the executor's diff against the cited principles, not against itself.
- Citation report on stdout. Grounded vs judgment-call counts, tier 1/2/3 check outcomes, integrity failures, plan amendments.
- `SUSPICIOUSLY CLEAN` flag on plans of five or more nodes that show no stress signals.
- Resume from interrupted runs (`warrant resume`).
- Skill mode calls `claude` via subprocess. No API key required for skill mode.

# Installation

### Skill mode (Claude Code)

```bash
git clone https://github.com/nuclide-research/warrant
cd warrant
pip install -e loop/ -e librarian/ -e agent/
cp .warrant/config.example.json .warrant/config.json
```

Edit `config.json` to set `index_path` and `base_repo`. Then invoke `/warrant <direction>` in any Claude Code session where `.warrant/config.json` exists.

### CLI mode (Anthropic API)

```bash
git clone https://github.com/nuclide-research/warrant
cd warrant
make install-api
warrant init
warrant run --direction "add pagination to the user list endpoint"
```

Python 3.11 or later. The `anthropic` SDK is pulled only in CLI mode via `loop/[api]`.

# Usage

```console
warrant init                                          # scaffold .warrant/api-config.json
warrant run --direction "..."                         # start a new run
warrant resume                                        # resume the latest interrupted run
warrant run --direction "..." --config path/to.json   # explicit config path
```

Skill mode supports the same two commands:

```
/warrant <direction>
/warrant resume
```

# Configuration

### CLI: `.warrant/api-config.json`

| Field | Default | Description |
|---|---|---|
| `index_path` | required | Path to the Librarian index directory |
| `base_repo` | required | Git repo warrant operates on |
| `out_dir` | `.warrant/runs` | Where run artifacts are stored |
| `claude_model` | `claude-sonnet-4-6` | Anthropic model for the executor agent |
| `claude_model_verifier` | `claude-sonnet-4-6` | Anthropic model for the verifier agent |
| `max_tool_rounds` | `50` | Max tool calls per agent turn |
| `global_iteration_cap` | `10` | Max global loop iterations |
| `per_node_attempt_cap` | `3` | Max attempts per plan node before marking failed |
| `watchdog_timeout` | `300.0` | Seconds before a node execution is timed out |
| `max_parallel` | `3` | Max plan nodes executing simultaneously |
| `max_principles` | `15` | Max principles retrieved per query |
| `verify_iteration_cap` | `3` | Max verifier iterations per node |

`ANTHROPIC_API_KEY` is read from the environment. It is never stored in the config file.

### Skill: `.warrant/config.json`

Same structure minus `claude_model`, `claude_model_verifier`, and `max_tool_rounds`. See `.warrant/config.example.json`.

# Sample library

`sample-library/` ships a pre-built Librarian index with 15 engineering principles: YAGNI, KISS, DRY, SRP, TDD, test isolation, fail-fast, defensive programming, mock-at-boundaries, design-for-failure, design-for-observability, rollback-over-fix-forward, dependency inversion, small-focused-units, and explicit-over-implicit. `warrant init` points at it by default.

To build a custom index from O'Reilly books (requires the `colophon` CLI and a book library):

```bash
librarian index <path-to-book-library> --output <path-to-index>
librarian query "error handling" --index <path-to-index>
```

# Citation report

Every run prints a citation report:

```
grounded decisions:       4   (clean 3, conflicted 1)
judgment calls:           1   (documented 1, undocumented 0)
tier-1 checks:            6 run / 1 failed
                               (1 from_grounds <- integrity, 0 from_topic <- audit catch)
tier-2 metrics:           2 computed
tier-3 principles:        3 assessed, judgment-only
plan amendments:          1  (see version diff)
```

The report counts grounded vs ungrounded plan nodes, tier 1/2/3 check outcomes, integrity failures (routed back to pending and re-executed), and plan amendments.

# Repository layout

```
agent/            Plan artifact: versioned decision-tree data structure
librarian/        Retrieval engine: HybridRAG index over engineering principles
loop/             Agent loop: Orient -> Retrieve -> Plan -> Execute -> Verify
loop/loop/api/    Standalone CLI (Anthropic API)
loop/loop/skill/  Claude Code skill invokers and config loader
sample-library/   Pre-built index with 15 engineering principles
SKILL.md          Claude Code skill entry point
.warrant/         Config and run artifacts (gitignored except examples)
```

# Scope

warrant does not replace code review. The citation report shows which decisions were grounded and which were not. Grounded is not correct. The verify phase checks that the executor followed its cited principles, not that the principles were right for the problem. A passing run still needs a human to read the diff.

warrant operates on one direction at a time. It does not maintain project state across directions or merge parallel runs.

# Our other projects

- [aimap](https://github.com/nuclide-research/aimap) - vulnerability scanner for AI and ML infrastructure
- [colophon](https://github.com/nuclide-research/colophon) - O'Reilly books to Markdown CLI, the source feed for Librarian
- [cortex-framework](https://github.com/nuclide-research/cortex-framework) - authorization-context analyzer
- [VisorLog](https://github.com/nuclide-research/visorlog) - finding ledger and ingest pipeline
- [BARE](https://github.com/nuclide-research/BARE) - semantic exploit-module ranking over scanner findings

# License

MIT. Part of the NuClide toolchain. Contact: [nuclide-research.com](https://nuclide-research.com)
