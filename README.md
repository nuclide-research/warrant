# warrant

Book-grounded autonomous coding agent that runs an Orient → Retrieve → Plan → Execute → Verify loop against a Librarian index of engineering principles.

Given one direction, warrant decomposes it into a plan tree, retrieves relevant engineering principles from the index for each task, annotates every plan node with applicable checks drawn from those principles, executes each task in an isolated git worktree, and runs a verify phase that checks the executor's output against the cited principles. Every plan step is grounded in a source; the citation report at the end shows which decisions were grounded, which were judgment calls, and which checks failed. A failed integrity check routes the node back to pending and re-executes; a clean or audit-catch verdict closes it.

Two entry points: `/warrant <direction>` as a Claude Code skill, or `warrant run --direction "..."` as a standalone CLI using the Anthropic API directly.

## Install

### Skill mode (Claude Code)

```
git clone https://github.com/nuclide-research/warrant
cd warrant
pip install -e loop/ -e librarian/ -e agent/
cp .warrant/config.example.json .warrant/config.json
# Edit config.json: set index_path and base_repo
```

Then invoke `/warrant <direction>` in any Claude Code session where `.warrant/config.json` exists.

### CLI mode (Anthropic API)

```
git clone https://github.com/nuclide-research/warrant
cd warrant
make install-api
# or: pip install -e "loop/[api]" -e librarian/ -e agent/

warrant init              # writes .warrant/api-config.json (3 prompts)
warrant run --direction "add pagination to the user list endpoint"
```

Python 3.11+. The `anthropic` SDK is a CLI-mode-only dependency (`loop/[api]`). Skill mode requires no network-level API key; it calls `claude` via subprocess.

`warrant init` defaults to `sample-library/index`, a pre-built index bundled with the repo. Run immediately without building a custom index.

## Usage

```
warrant init                                          # scaffold .warrant/api-config.json
warrant run --direction "..."                         # start a new run
warrant resume                                        # resume the latest interrupted run
warrant run --direction "..." --config path/to.json   # explicit config path
```

The skill entry point supports the same two commands:

```
/warrant <direction>
/warrant resume
```

## Configuration

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

`ANTHROPIC_API_KEY` is read from the environment; it is never stored in the config file.

### Skill: `.warrant/config.json`

Same structure, minus `claude_model`, `claude_model_verifier`, and `max_tool_rounds`. See `.warrant/config.example.json`.

## Sample library

`sample-library/` contains a pre-built Librarian index with 15 engineering principles: YAGNI, KISS, DRY, SRP, TDD, test isolation, fail-fast, defensive programming, mock-at-boundaries, design-for-failure, design-for-observability, rollback-over-fix-forward, dependency inversion, small-focused-units, and explicit-over-implicit. Ready to use immediately. `warrant init` defaults to it.

To build a custom index from O'Reilly books (requires the `colophon` CLI and a book library):

```
librarian index <path-to-book-library> --output <path-to-index>
librarian query "error handling" --index <path-to-index>
```

## Citation report

Every run produces a citation report on stdout:

```
grounded decisions:       4   (clean 3, conflicted 1)
judgment calls:           1   (documented 1, undocumented 0)
tier-1 checks:            6 run / 1 failed
                               (1 from_grounds <- integrity, 0 from_topic <- audit catch)
tier-2 metrics:           2 computed
tier-3 principles:        3 assessed, judgment-only
plan amendments:          1  (see version diff)
```

The report counts grounded vs ungrounded plan nodes, tier-1/2/3 check outcomes, integrity failures (routed back to pending and re-executed), and plan amendments. A `SUSPICIOUSLY CLEAN` flag fires when a plan of five or more nodes shows no stress signals at all.

## Repository structure

```
agent/          Plan artifact: versioned decision-tree data structure and operations
librarian/      Retrieval engine: indexes engineering principles into a HybridRAG index
loop/           Agent loop: Orient -> Retrieve -> Plan -> Execute -> Verify
loop/loop/api/  Standalone CLI (Anthropic API)
loop/loop/skill/  Claude Code skill invokers and config loader
sample-library/ Pre-built index with 15 engineering principles
SKILL.md        Claude Code skill entry point
.warrant/       Config and run artifacts (gitignored except examples)
```

## What warrant is not

warrant does not replace code review. The citation report shows which decisions were grounded and which were not; grounded does not mean correct. The verify phase checks that the executor followed its cited principles, not that the principles were right for the problem. A passing run still needs a human to read the diff.

warrant operates on one direction at a time. It does not maintain long-running project state across directions or merge parallel runs.

## License

MIT. Part of the NuClide toolchain. Contact: [nuclide-research.com](https://nuclide-research.com)
