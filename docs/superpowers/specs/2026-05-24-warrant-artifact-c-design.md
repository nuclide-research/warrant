# Warrant — Artifact C: Shareable Starter Kit Design

**Date:** 2026-05-24

---

## Goal

Someone can `git clone` the repo, run `make install-api`, run `warrant init`, then
`warrant run --direction "..."` against a real codebase in under 10 minutes — without
building a Librarian index first.

---

## Architecture overview

Artifact C adds four things to the completed Artifact A + B codebase:

1. **README.md** — project face on GitHub; explains both modes, quick start, config reference
2. **Makefile** — one-liner entry points for install, test, demo
3. **`warrant init` subcommand** — interactive scaffolding of `.warrant/api-config.json`
4. **`sample-library/`** — pre-built Librarian index with 15 hand-crafted engineering
   principles; committed to the repo so new users have a working index immediately

Nothing in Artifact C requires the private `colophon-library` corpus. All sample
principles are hand-crafted from public engineering axioms — no copyrighted book text.

---

## Section 1: README.md

**Location:** repo root `README.md`

**Structure:**

```
# Warrant
<one paragraph: what it is, the grounding thesis>

## What it does
- Orient → Retrieve → Plan → Execute → Verify loop (one sentence each phase)
- Plans cite engineering principles with book/chapter/section
- Two modes: /warrant skill (Claude Code) and warrant CLI (Anthropic API)

## Quick start
    export ANTHROPIC_API_KEY=sk-ant-...
    make install-api
    warrant init
    warrant run --direction "add pagination to the user list endpoint"

## Prerequisites
Python 3.11+, git, ANTHROPIC_API_KEY env var

## Installation

### Skill mode (Claude Code)
    pip install -e loop/ -e librarian/ -e agent/
    cp .warrant/config.example.json .warrant/config.json
    # fill in index_path and base_repo
    # invoke /warrant <direction> in any Claude Code session

### CLI mode (Anthropic API)
    make install-api         # or: pip install -e "loop/[api]" -e librarian/ -e agent/
    warrant init             # interactive: writes .warrant/api-config.json
    warrant run --direction "..."

## Configuration

### CLI: .warrant/api-config.json
| Field                  | Default                                          | Description                          |
|------------------------|--------------------------------------------------|--------------------------------------|
| index_path             | required                                         | Path to librarian index directory    |
| base_repo              | required                                         | Git repo warrant operates on         |
| out_dir                | .warrant/runs                                    | Where run artifacts are stored       |
| model_name             | sentence-transformers/all-MiniLM-L6-v2           | Embedding model                      |
| reranker_name          | cross-encoder/ms-marco-MiniLM-L-6-v2             | Reranker model                       |
| claude_model           | claude-sonnet-4-6                                | Executor model                       |
| claude_model_verifier  | claude-sonnet-4-6                                | Verifier model                       |
| max_tool_rounds        | 50                                               | Max tool calls per executor turn     |
| global_iteration_cap   | 10                                               | Max global loop iterations           |
| per_node_attempt_cap   | 3                                                | Max attempts per plan node           |
| watchdog_timeout       | 300.0                                            | Seconds before a node is timed out  |
| max_parallel           | 3                                                | Max parallel node executions         |
| max_principles         | 15                                               | Max principles retrieved per query   |
| verify_iteration_cap   | 3                                                | Max verifier iterations per node     |

Note: ANTHROPIC_API_KEY must be set as an environment variable; it is never stored in config.

### Skill: .warrant/config.json
See `.warrant/config.example.json` — same fields minus the Anthropic API options.

## Sample library

`sample-library/` is a pre-built Librarian index with 15 engineering principles.
Use it out of the box (the default from `warrant init`) or build your own:

    librarian index <path-to-book-library>

## License
MIT
```

---

## Section 2: Makefile

**Location:** repo root `Makefile`

```makefile
.PHONY: install install-api test demo

install:
	pip install -e loop/ -e librarian/ -e agent/

install-api:
	pip install -e "loop/[api]" -e librarian/ -e agent/

test:
	python -m pytest loop/tests/ -q
	python -m pytest agent/tests/ -q
	python -m pytest librarian/tests/ -q

demo:
	warrant run \
		--config sample-library/demo-config.json \
		--direction "add a hello_world function that prints the repo name"
```

`make demo` uses `sample-library/demo-config.json`, which points `base_repo` at the
warrant repo itself and `index_path` at `sample-library/index`. It exercises the full
loop on a trivial direction so new users can see warrant run end to end.

---

## Section 3: `warrant init` subcommand

**Location:** `loop/loop/api/__main__.py` — new `init` subcommand alongside `run` and
`resume`.

**Behavior:**

1. Prompt for three values (all with defaults):
   - `Base repo path [.]` — the git repo warrant will operate on
   - `Index path [sample-library/index]` — path to a built Librarian index
   - `Output directory [.warrant/runs]` — where run artifacts are stored
2. Create `.warrant/` if it does not exist
3. Write `.warrant/api-config.json` with the three user-supplied fields plus all
   `ApiConfig` dataclass defaults for the remaining fields
4. Print: `Config written to .warrant/api-config.json` and the next command to run

**Implementation notes:**

- Use `input()` with the prompt string; strip whitespace; use the default if blank
- `base_repo` default: `"."` (current directory)
- `index_path` default: `"sample-library/index"` (resolves relative to the config file)
- `out_dir` default: `".warrant/runs"`
- Do not prompt for `claude_model`, caps, or timeouts — users change those by editing
  the JSON directly
- If `.warrant/api-config.json` already exists, warn and ask: `Overwrite? [y/N]:`; exit
  without writing if the user declines

**CLI registration:**

```
warrant init
```

No `--config` argument (output path is always `.warrant/api-config.json`).

---

## Section 4: `sample-library/`

**Location:** `sample-library/` at repo root

**Structure:**

```
sample-library/
  principles.json        # source of truth — 15 hand-crafted principles
  index/                 # pre-built librarian store (committed to git)
    chroma.sqlite3        # chromadb vector store
    principle_graph.json  # edge graph (related_ids)
  demo-config.json       # used by `make demo`
```

**`principles.json` schema** — matches the Librarian `Principle` model:

```json
[
  {
    "id": "yagni",
    "text": "You aren't gonna need it: only build what is required now.",
    "citation": {"book": "Software Engineering Fundamentals", "chapter": "Design Principles", "section": "YAGNI"},
    "checkability_tier": 1,
    "related_ids": ["kiss", "srp"]
  },
  ...
]
```

**15 principles by category:**

| Category | Principles |
|---|---|
| Design | YAGNI, KISS, DRY, explicit over implicit |
| Robustness | Fail fast, defensive programming, design for failure |
| Testing | TDD, test isolation, mock only at boundaries |
| Architecture | Single responsibility, dependency inversion, small focused units |
| Operations | Design for observability, rollback over fix-forward |

**Build process:**

The index is built once during Artifact C development using the real Librarian CLI:

```bash
librarian index sample-library/principles.json --output sample-library/index
```

(Or via a small Python script that calls the Librarian API directly if the CLI
interface differs.) The resulting `index/` directory is committed to git.

At 15 principles with 384-dimensional embeddings (all-MiniLM-L6-v2), the index is
well under 1 MB — safe to commit.

**`demo-config.json`:**

```json
{
  "index_path": "sample-library/index",
  "base_repo": ".",
  "out_dir": ".warrant/demo-runs",
  "global_iteration_cap": 3,
  "per_node_attempt_cap": 2,
  "verify_iteration_cap": 1
}
```

Lower caps for the demo so it runs in under a minute.

---

## File map

| Action | Path |
|---|---|
| Create | `README.md` |
| Create | `Makefile` |
| Create | `sample-library/principles.json` |
| Create | `sample-library/index/` (pre-built, committed) |
| Create | `sample-library/demo-config.json` |
| Create | `docs/superpowers/specs/2026-05-24-warrant-artifact-c-design.md` (this file) |
| Modify | `loop/loop/api/__main__.py` — add `init` subcommand |

No other files change. The Librarian, Agent, and loop packages are complete and
untouched by Artifact C.

---

## Testing

Artifact C is primarily documentation and scaffolding. Tests are limited:

- **`test_api_init.py`** — unit tests for the `init` subcommand:
  - Writes correct JSON to `.warrant/api-config.json`
  - Uses supplied values over defaults
  - Uses defaults when input is blank
  - Prompts for overwrite if file already exists; does not write on decline
  - Creates `.warrant/` directory if absent
- **Manual smoke test** — `make demo` runs end to end against the sample library

The sample-library index itself is not unit-tested; it is verified by `make demo`.
