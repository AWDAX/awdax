"""Owner-run tool for chats stored under the old shared "anonymous" user. Never runs automatically.

In strict mode no request can be "anonymous", so those chats are unreachable through the API. Use this to look at
them, hand one to the right account, or delete them.

    python scripts/sessions_admin.py list-anonymous
    python scripts/sessions_admin.py assign <session_id> <user_id>
    python scripts/sessions_admin.py purge-anonymous --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_sessions  # noqa: E402


def _rows(where: str, args: tuple = ()) -> list[sqlite3.Row]:
    ui_sessions.init_ui_sessions()
    conn = ui_sessions._conn()
    try:
        return conn.execute(f"SELECT id, title, user_id, updated_at FROM ui_sessions WHERE {where} ORDER BY updated_at DESC", args).fetchall()
    finally:
        conn.close()


def list_anonymous() -> int:
    rows = _rows("user_id IS NULL OR user_id='' OR user_id='anonymous'")
    for r in rows:
        print(f"{r['id']}\t{r['updated_at']}\t{r['title']}")
    print(f"{len(rows)} chat(s) belong to no account", file=sys.stderr)
    return 0


def assign(session_id: str, user_id: str) -> int:
    user_id = user_id.strip()
    if not user_id or user_id == "anonymous":
        print("A real user id is required.", file=sys.stderr)
        return 2
    ui_sessions.init_ui_sessions()
    with ui_sessions._lock:
        conn = ui_sessions._conn()
        try:
            cur = conn.execute(
                "UPDATE ui_sessions SET user_id=? WHERE id=? AND (user_id IS NULL OR user_id='' OR user_id='anonymous')",
                (user_id, session_id),
            )
            conn.commit()
            changed = cur.rowcount
        finally:
            conn.close()
    if not changed:
        print("No such unowned chat (it may already belong to an account).", file=sys.stderr)
        return 1
    print(f"Chat {session_id} now belongs to {user_id}")
    return 0


def purge_anonymous(confirmed: bool) -> int:
    if not confirmed:
        print("This deletes every chat that belongs to no account. Re-run with --yes to do it.", file=sys.stderr)
        return 2
    ui_sessions.init_ui_sessions()
    with ui_sessions._lock:
        conn = ui_sessions._conn()
        try:
            cur = conn.execute("DELETE FROM ui_sessions WHERE user_id IS NULL OR user_id='' OR user_id='anonymous'")
            conn.commit()
            deleted = cur.rowcount
        finally:
            conn.close()
    print(f"Deleted {deleted} chat(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-anonymous")
    a = sub.add_parser("assign")
    a.add_argument("session_id")
    a.add_argument("user_id")
    p = sub.add_parser("purge-anonymous")
    p.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "list-anonymous":
        return list_anonymous()
    if args.cmd == "assign":
        return assign(args.session_id, args.user_id)
    return purge_anonymous(args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
