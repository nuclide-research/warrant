from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .. import runstore
from ..citationreport import render_citation_report
from .factory import load_config, build_runner

_DEFAULT_CONFIG = Path(".warrant/api-config.json")
_INIT_OUTPUT = Path(".warrant/api-config.json")


def cmd_run(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    config = load_config(config_path)
    Path(config.out_dir).mkdir(parents=True, exist_ok=True)
    runner = build_runner(config)
    run_state, report = runner.run(args.direction)
    print(render_citation_report(report))
    print(f"worktree: {run_state.worktree_path}")


def cmd_resume(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    config = load_config(config_path)
    run_state = runstore.load_latest_run(Path(config.out_dir))
    runner = build_runner(config)
    run_state, report = runner.resume(run_state)
    print(render_citation_report(report))
    print(f"worktree: {run_state.worktree_path}")


def cmd_init(args: argparse.Namespace) -> None:
    out_path = _INIT_OUTPUT
    if out_path.exists():
        answer = input(f"{out_path} already exists. Overwrite? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return
    base_repo = input("Base repo path [.]: ").strip() or "."
    index_path = input("Index path [sample-library/index]: ").strip() or "sample-library/index"
    out_dir = input("Output directory [.warrant/runs]: ").strip() or ".warrant/runs"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"index_path": index_path, "base_repo": base_repo, "out_dir": out_dir}, indent=2),
        encoding="utf-8",
    )
    print(f"Config written to {out_path}")
    print('Next: warrant run --direction "..."')


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="warrant",
        description="Warrant — book-grounded autonomous coding agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Start a new Warrant run")
    p_run.add_argument("--direction", required=True, help="What to build")
    p_run.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="Path to config JSON (default: .warrant/api-config.json)",
    )
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="Resume the latest run")
    p_resume.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="Path to config JSON (default: .warrant/api-config.json)",
    )
    p_resume.set_defaults(func=cmd_resume)

    p_init = sub.add_parser("init", help="Scaffold .warrant/api-config.json interactively")
    p_init.set_defaults(func=cmd_init)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
