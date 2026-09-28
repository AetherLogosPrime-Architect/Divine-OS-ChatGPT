"""Reproduce reset table-list coverage on synthetic data, without booting the OS.

Runs only the reviewed _clear_db_tables helper, compiled from its original AST,
against a temporary fixture. This is not a test of the complete CLI reset flow.
Run only against source you have reviewed; AST extraction is not a security sandbox.
"""
import argparse
import ast
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile


def probe(source: Path, scratch: Path):
    path = source / "src/divineos/cli/admin_reset_template.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_clear_db_tables")
    table_lists = {
        n.target.id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
        and n.target.id in {"_LEDGER_TABLES_TO_CLEAR", "_FTS_TABLES"}
    }
    namespace = {"Path": Path, "sqlite3": sqlite3}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    scratch = scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="divineos-reset-probe-", dir=scratch) as directory:
        if not Path(directory).resolve().is_relative_to(scratch):
            raise ValueError("Temporary fixture escaped its scratch directory")
        db = Path(directory) / "synthetic.db"
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("CREATE TABLE system_events (content TEXT)")
            conn.execute("INSERT INTO system_events VALUES ('synthetic event')")
            conn.execute("CREATE TABLE bio (content TEXT)")
            conn.execute("INSERT INTO bio VALUES ('synthetic previous biography')")
        removed = namespace["_clear_db_tables"](db, table_lists["_LEDGER_TABLES_TO_CLEAR"] + table_lists["_FTS_TABLES"])
        with closing(sqlite3.connect(db)) as conn:
            remaining = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                         for name in ("system_events", "bio")}
    return {"scope": "Original helper and table lists, synthetic fixture; full CLI not executed",
            "removed": removed, "remaining": remaining,
            "biography_survives": remaining["bio"] > 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, default=Path(__file__).resolve().parents[1] / ".local/probes")
    args = parser.parse_args()
    print(json.dumps(probe(args.source.resolve(), args.scratch), indent=2))
