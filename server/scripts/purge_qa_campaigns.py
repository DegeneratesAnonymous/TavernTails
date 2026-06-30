"""Purge QA campaign artifacts from local development databases.

This is intentionally narrow: it removes campaigns whose names start with
``QA `` plus their session folders/campaign memory rows. It also removes
throwaway users created by automated acceptance runs, such as
``qa-fresh-final-...@example.com``.

Usage:
    python -m server.scripts.purge_qa_campaigns
    python -m server.scripts.purge_qa_campaigns --commit
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASES = (
    ROOT / "data" / "taverntails.db",
    ROOT / "taverntails.db",
)
SESSIONS_DIR = ROOT / "server" / "sessions"
CAMPAIGNS_DIR = ROOT / "server" / "campaigns"


CAMPAIGN_DEPENDENTS = (
    ("campaignchangelog", "campaign_id"),
    ("campaignhook", "campaign_id"),
    ("campaignrelationship", "campaign_id"),
    ("campaignentity", "campaign_id"),
    ("chatmessage", "campaign_id"),
    ("roll", "campaign_id"),
)


USER_DEPENDENTS = (
    ("friendrequest", "from_user_id"),
    ("friendrequest", "to_user_id"),
    ("supportticket", "user_id"),
    ("userblock", "blocker_id"),
    ("userblock", "blocked_id"),
    ("userreport", "reporter_id"),
    ("userreport", "reported_id"),
    ("directmessage", "sender_id"),
    ("directmessage", "recipient_id"),
)


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return {str(row[0]).lower() for row in rows}


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if table not in _tables(conn):
        return False
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return any(str(row[1]).lower() == column.lower() for row in rows)


def _session_ids_from_metadata(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        meta = json.loads(raw)
    except Exception:
        return []
    sessions = meta.get("sessions") if isinstance(meta, dict) else []
    if not isinstance(sessions, list):
        return []
    return [str(sid) for sid in sessions if sid]


def _remove_path(path: Path, *, commit: bool, quiet: bool) -> None:
    if not path.exists():
        return
    if not quiet:
        print(f"  {'DELETE' if commit else 'DRY-RUN'} {path}")
    if commit:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def purge_database(db_path: Path, *, commit: bool, quiet: bool) -> dict[str, int]:
    if not db_path.exists():
        return {"campaigns": 0, "users": 0, "sessions": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = _tables(conn)
        if "campaign" not in tables:
            return {"campaigns": 0, "users": 0, "sessions": 0}

        campaigns = conn.execute(
            "select id, name, metadata_json from campaign where lower(name) like 'qa %'"
        ).fetchall()
        campaign_ids = [str(row["id"]) for row in campaigns]
        session_ids: list[str] = []
        for row in campaigns:
            session_ids.extend(_session_ids_from_metadata(row["metadata_json"]))

        users: list[sqlite3.Row] = []
        if "user" in tables:
            users = conn.execute(
                "select id, email from user where lower(email) like 'qa-fresh-final-%'"
            ).fetchall()
        user_ids = [int(row["id"]) for row in users]

        if not quiet:
            print(f"{db_path}: {len(campaign_ids)} QA campaigns, {len(user_ids)} QA users")
            for row in campaigns:
                print(f"  campaign {row['id']} {row['name']}")
            for row in users:
                print(f"  user {row['id']} {row['email']}")

        if commit:
            with conn:
                for table, column in CAMPAIGN_DEPENDENTS:
                    if table in tables and _column_exists(conn, table, column) and campaign_ids:
                        conn.executemany(
                            f"delete from {table} where {column} = ?",
                            [(cid,) for cid in campaign_ids],
                        )
                if campaign_ids:
                    conn.executemany("delete from campaign where id = ?", [(cid,) for cid in campaign_ids])

                for table, column in USER_DEPENDENTS:
                    if table in tables and _column_exists(conn, table, column) and user_ids:
                        conn.executemany(
                            f"delete from {table} where {column} = ?",
                            [(uid,) for uid in user_ids],
                        )
                if "character" in tables and _column_exists(conn, "character", "owner_id") and user_ids:
                    conn.executemany("delete from character where owner_id = ?", [(uid,) for uid in user_ids])
                if "chatmessage" in tables and _column_exists(conn, "chatmessage", "sender_id") and user_ids:
                    conn.executemany("delete from chatmessage where sender_id = ?", [(uid,) for uid in user_ids])
                if user_ids:
                    conn.executemany("delete from user where id = ?", [(uid,) for uid in user_ids])

        for campaign_id in campaign_ids:
            _remove_path(CAMPAIGNS_DIR / campaign_id, commit=commit, quiet=quiet)
        for session_id in set(session_ids):
            _remove_path(SESSIONS_DIR / session_id, commit=commit, quiet=quiet)

        return {"campaigns": len(campaign_ids), "users": len(user_ids), "sessions": len(set(session_ids))}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Actually delete matching QA artifacts.")
    parser.add_argument("--quiet", action="store_true", help="Only print the summary.")
    parser.add_argument(
        "--db",
        action="append",
        default=[],
        help="Database path to clean. Defaults to data/taverntails.db and taverntails.db.",
    )
    args = parser.parse_args()

    db_paths = [Path(p).resolve() for p in args.db] if args.db else list(DEFAULT_DATABASES)
    totals = {"campaigns": 0, "users": 0, "sessions": 0}
    for db_path in db_paths:
        result = purge_database(db_path, commit=args.commit, quiet=args.quiet)
        for key, value in result.items():
            totals[key] += value

    action = "Deleted" if args.commit else "Would delete"
    print(
        f"{action} {totals['campaigns']} QA campaigns, "
        f"{totals['sessions']} session folders, {totals['users']} QA users."
    )
    if not args.commit:
        print("Dry run only. Re-run with --commit to apply.")


if __name__ == "__main__":
    main()
