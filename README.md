# Warrant

Warrant is a book-grounded autonomous coding agent. Given a single direction, it runs an Orient → Retrieve → Plan → Execute → Verify loop, grounding every plan step in engineering principles drawn from a Librarian index. Plans cite their sources; the Verify phase checks them.

## What it does

- **Orient** — decomposes the direction into a plan tree of independent tasks
- **Retrieve** — pulls relevant engineering principles from the index for each task
- **Plan** — annotates each node with applicable checks drawn from retrieved principles
- **Execute** — runs each task in an isolated git worktree, calling real tools
- **Verify** — checks the executor's output against the plan's cited principles

Two modes: `/warrant <direction>` as a Claude Code skill, or `warrant run --direction "..."` as a standalone CLI using the Anthropic API directly.

## Quick start (CLI mode)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
make install-api
warrant init
warrant run --direction "add pagination to the user list endpoint"
```

`warrant init` scaffolds `.warrant/api-config.json` with three prompts (repo path, index path, output dir). The defaults point at `sample-library/`, a pre-built index bundled with the repo, so you can run immediately without building your own.

## Prerequisites

- Python 3.11+
- git
- `ANTHROPIC_API_KEY` environment variable (CLI mode only)

## Installation

### Skill mode (Claude Code)

```bash
pip install -e loop/ -e librarian/ -e agent/
cp .warrant/config.example.json .warrant/config.json
# Edit config.json: set index_path and base_repo
```

Then invoke `/warrant <direction>` in any Claude Code session where `.warrant/config.json` exists. See `SKILL.md` for details.

### CLI mode (Anthropic API)

```bash
make install-api          # or: pip install -e "loop/[api]" -e librarian/ -e agent/
warrant init              # writes .warrant/api-config.json interactively
warrant run --direction "..."
```

To resume the most recent run if it was interrupted:

```bash
warrant resume
```

## Configuration

### CLI: `.warrant/api-config.json`

| Field | Default | Description |
|---|---|---|
| `index_path` | required | Path to the Librarian index directory |
| `base_repo` | required | Git repo Warrant operates on |
| `out_dir` | `.warrant/runs` | Where run artifacts (plans, run state) are stored |
| `model_name` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model for retrieval |
| `reranker_name` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model for retrieval |
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

See `.warrant/config.example.json` for all fields. Same structure as above minus the Anthropic API options.

## Sample library

`sample-library/` contains a pre-built Librarian index with 15 engineering principles covering design, robustness, testing, architecture, and operations. It is ready to use out of the box — `warrant init` defaults to it.

To build your own index from O'Reilly books (requires the `colophon` CLI and a book library):

```bash
librarian index <path-to-book-library> --output <path-to-index>
```

Then set `index_path` in your config to `<path-to-index>`.

## Repository structure

```
agent/          Plan artifact: versioned decision-tree data structure
librarian/      Librarian: indexes engineering principles into a HybridRAG index
loop/           Agent loop: Orient → Retrieve → Plan → Execute → Verify
loop/loop/skill/    Claude Code skill wrapper
loop/loop/api/      Standalone CLI (Anthropic API)
sample-library/ Pre-built index with 15 engineering principles
SKILL.md        Claude Code skill entry point
.warrant/       Config and run artifacts (gitignored except examples)
```

## License

MIT
