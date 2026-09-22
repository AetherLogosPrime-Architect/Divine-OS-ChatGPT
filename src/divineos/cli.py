from __future__ import annotations

import argparse

from divineos.runtime import Runtime
from divineos.store import verify_chain


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="divineos")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("briefing")
    sub.add_parser("status")
    remember = sub.add_parser("remember")
    remember.add_argument("text")
    remember.add_argument("--evidence", required=True)
    goal = sub.add_parser("goal")
    goal_sub = goal.add_subparsers(dest="goal_command", required=True)
    goal_add = goal_sub.add_parser("add")
    goal_add.add_argument("text")
    goal_done = goal_sub.add_parser("done")
    goal_done.add_argument("goal_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runtime = Runtime()
    if args.command == "init":
        runtime.initialize()
        print(f"Initialized {runtime.provenance.database}")
        return 0
    runtime.initialize()
    if args.command == "briefing":
        print(runtime.briefing())
        return 0
    if args.command == "status":
        ok, message, count = verify_chain(runtime.provenance.database)
        print(f"{message} ({count} events)")
        return 0 if ok else 1
    if args.command == "remember":
        memory_id = runtime.remember(args.text, args.evidence)
        print(f"Memory recorded: {memory_id}")
        return 0
    if args.command == "goal" and args.goal_command == "add":
        goal_id = runtime.add_goal(args.text)
        print(f"Goal added: {goal_id}")
        return 0
    if args.command == "goal" and args.goal_command == "done":
        runtime.complete_goal(args.goal_id)
        print(f"Goal completed: {args.goal_id}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
