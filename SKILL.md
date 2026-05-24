---
name: warrant
description: >
  Autonomous book-grounded coding agent. Runs Orient → Retrieve → Plan →
  Execute → Verify given one direction, returns a finished branch and
  citation report. Usage: /warrant <direction>
allowed-tools: Bash
---

Accept the direction from `$ARGUMENTS`.

First, verify that `.warrant/config.json` exists in the current directory. If it is missing, run the following check — it will print setup instructions and exit:

```bash
test -f .warrant/config.json || { echo "No .warrant/config.json found. Copy .warrant/config.example.json, fill in index_path and base_repo, then re-run."; exit 1; }
```

Run the appropriate subcommand based on the direction:

```bash
if [ "$ARGUMENTS" = "resume" ]; then
  python -m loop.skill resume
else
  python -m loop.skill run --direction "$ARGUMENTS"
fi
```

Print the full stdout output to the user (citation report + branch/worktree path).

All logic lives in the Python package. This skill is intentionally thin.
