from __future__ import annotations

import argparse
from pathlib import Path

from divineos.backup import create_backup, restore_backup, verify_backup
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
    backup = sub.add_parser("backup")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    backup_create = backup_sub.add_parser("create")
    backup_create.add_argument("path", type=Path)
    backup_verify = backup_sub.add_parser("verify")
    backup_verify.add_argument("path", type=Path)
    backup_restore = backup_sub.add_parser("restore")
    backup_restore.add_argument("path", type=Path)
    backup_restore.add_argument("--to-home", required=True, type=Path)
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
    if args.command == "backup" and args.backup_command == "create":
        manifest = create_backup(runtime.provenance.database, args.path)
        print(f"Backup created and verified: {args.path.absolute()}")
        print(f"Manifest: {manifest}")
        return 0
    if args.command == "backup" and args.backup_command == "verify":
        ok, message = verify_backup(args.path)
        print(message)
        return 0 if ok else 1
    if args.command == "backup" and args.backup_command == "restore":
        restored = restore_backup(args.path, args.to_home)
        print(f"Backup restored and verified: {restored}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
