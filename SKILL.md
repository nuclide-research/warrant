---
name: warrant
description: >
  Autonomous book-grounded coding agent. Runs Orient → Retrieve → Plan →
  Execute → Verify given one direction, returns a finished branch and
  citation report. Usage: /warrant <direction>
allowed-tools: Bash
---

Accept the direction from `$ARGUMENTS`.

First, verify that `.warrant/config.json` exists in the current directory:

```bash
test -f .warrant/config.json || { echo "No .warrant/config.json found. Copy .warrant/config.example.json, fill in index_path and base_repo, then re-run."; exit 1; }
```

If the config is missing, explain the setup and stop — do not proceed.

To start a new run:

```bash
python -m loop.skill run --direction "$ARGUMENTS"
```

Print the full stdout output to the user (citation report + branch/worktree path).

To resume the latest interrupted run, the user invokes `/warrant resume`. In that case, run:

```bash
python -m loop.skill resume
```

All logic lives in the Python package. This skill is intentionally thin.
