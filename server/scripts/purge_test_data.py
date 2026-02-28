"""Purge all development test data, keeping only the Admin and Bilbo accounts.

Removes every user, campaign, character, chat message, roll, friend request,
support ticket, user block, user report, and direct message that does NOT
belong to the two canonical seed accounts (admin and bilbo).

Session folders on disk that belong to removed campaigns are also deleted.

Usage:
    python -m server.scripts.purge_test_data          # dry-run (prints what would be removed)
    python -m server.scripts.purge_test_data --commit  # actually deletes

The seed-account emails are read from the same environment variables that
``db.ensure_seed_users()`` uses, so they stay in sync with your ``.env``:

    TAVERNTAILS_ADMIN_EMAIL   (default: admin@example.com)
    TAVERNTAILS_TEST_EMAIL    (default: bilbo@example.com)
"""

import json
import os
import shutil
import sys

from sqlmodel import Session, select

from server import db

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")
DRY_RUN = "--commit" not in sys.argv


def _keep_emails() -> set[str]:
    admin = (os.environ.get("TAVERNTAILS_ADMIN_EMAIL") or "admin@example.com").strip().lower()
    bilbo = (os.environ.get("TAVERNTAILS_TEST_EMAIL") or "bilbo@example.com").strip().lower()
    return {admin, bilbo}


def purge() -> None:
    db.create_db_and_tables()

    keep_emails = _keep_emails()
    print(f"Keeping accounts: {', '.join(sorted(keep_emails))}")
    if DRY_RUN:
        print("DRY RUN — pass --commit to apply changes.\n")

    with Session(db.engine) as session:
        # ── Identify users to keep and remove ────────────────────────────────
        all_users = session.exec(select(db.User)).all()
        keep_ids: set[int] = set()
        remove_ids: set[int] = set()

        for u in all_users:
            email = (u.email or "").strip().lower()
            if email in keep_emails:
                keep_ids.add(u.id)
                print(f"  KEEP   user #{u.id}  {u.email or '(no email)'}  ({u.username or 'no username'})")
            else:
                remove_ids.add(u.id)
                print(f"  REMOVE user #{u.id}  {u.email or '(no email)'}  ({u.username or 'no username'})")

        if not remove_ids:
            print("\nNothing to remove.")
            return

        # ── Identify campaigns to keep and remove ────────────────────────────
        all_campaigns = session.exec(select(db.Campaign)).all()
        remove_campaign_ids: set[str] = set()

        for c in all_campaigns:
            remove_campaign_ids.add(c.id)
            print(f"  REMOVE campaign {c.id}  '{c.name}'  owner_id={c.owner_id}")

        # ── Delete dependent data for removed users ───────────────────────────

        def _delete_for_users(model, *cols):
            for col in cols:
                stmt = select(model).where(getattr(model, col).in_(remove_ids))
                rows = session.exec(stmt).all()
                for row in rows:
                    print(f"  DELETE {model.__name__} id={row.id}")
                    if not DRY_RUN:
                        session.delete(row)

        def _delete_campaigns_rows(model, col):
            stmt = select(model).where(getattr(model, col).in_(remove_campaign_ids))
            rows = session.exec(stmt).all()
            for row in rows:
                print(f"  DELETE {model.__name__} id={row.id}")
                if not DRY_RUN:
                    session.delete(row)

        # Characters
        _delete_for_users(db.Character, "owner_id")

        # Rolls belonging to removed campaigns
        if remove_campaign_ids:
            _delete_campaigns_rows(db.Roll, "campaign_id")

        # Chat messages — both by sender and by campaign
        for u_id in remove_ids:
            rows = session.exec(select(db.ChatMessage).where(db.ChatMessage.sender_id == u_id)).all()
            for row in rows:
                print(f"  DELETE ChatMessage id={row.id}")
                if not DRY_RUN:
                    session.delete(row)
        if remove_campaign_ids:
            _delete_campaigns_rows(db.ChatMessage, "campaign_id")

        # Friend requests
        for model_col in [("from_user_id",), ("to_user_id",)]:
            _delete_for_users(db.FriendRequest, *model_col)

        # Support tickets
        _delete_for_users(db.SupportTicket, "user_id")

        # User blocks
        _delete_for_users(db.UserBlock, "blocker_id", "blocked_id")

        # User reports
        _delete_for_users(db.UserReport, "reporter_id", "reported_id")

        # Direct messages
        _delete_for_users(db.DirectMessage, "sender_id", "recipient_id")

        # Campaigns
        for c_id in remove_campaign_ids:
            stmt = select(db.Campaign).where(db.Campaign.id == c_id)
            c = session.exec(stmt).first()
            if c:
                print(f"  DELETE Campaign id={c.id}")
                if not DRY_RUN:
                    session.delete(c)

        # Users
        for u_id in remove_ids:
            stmt = select(db.User).where(db.User.id == u_id)
            u = session.exec(stmt).first()
            if u:
                print(f"  DELETE User id={u.id}")
                if not DRY_RUN:
                    session.delete(u)

        if not DRY_RUN:
            session.commit()
            print("\nDatabase changes committed.")

    # ── Remove session folders on disk ───────────────────────────────────────
    if os.path.isdir(SESSIONS_DIR):
        for entry in os.listdir(SESSIONS_DIR):
            session_path = os.path.join(SESSIONS_DIR, entry)
            if not os.path.isdir(session_path):
                continue
            meta_path = os.path.join(session_path, "meta.json")
            if not os.path.exists(meta_path):
                continue
            # Read owner from meta.json
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except Exception:
                meta = {}
            owner_email = (meta.get("owner") or "").strip().lower()
            if owner_email not in keep_emails:
                print(f"  {'DRY-RUN: would delete' if DRY_RUN else 'DELETE'} session dir {session_path}")
                if not DRY_RUN:
                    shutil.rmtree(session_path)

    if DRY_RUN:
        print("\nDry run complete. No changes made. Re-run with --commit to apply.")
    else:
        print("\nPurge complete.")


if __name__ == "__main__":
    purge()
