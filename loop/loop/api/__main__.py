from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .. import runstore
from ..citationreport import render_citation_report
from .factory import load_config, build_runner


def _default_config() -> Path:
    return Path(".warrant/config.json")


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
        default=str(_default_config()),
        help="Path to config JSON (default: .warrant/config.json)",
    )
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="Resume the latest run")
    p_resume.add_argument(
        "--config",
        default=str(_default_config()),
        help="Path to config JSON (default: .warrant/config.json)",
    )
    p_resume.set_defaults(func=cmd_resume)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
