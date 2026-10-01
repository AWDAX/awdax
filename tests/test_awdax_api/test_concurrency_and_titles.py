import json
import sqlite3
import threading
import unittest

from ui_sessions import (
    DEFAULT_TITLES,
    create_session,
    delete_session,
    get_session,
    save_session,
    update_session_title,
    _conn,
)
from awdax_api.serializers import to_awdax_instance


class ConcurrencyAndTitlesTests(unittest.TestCase):
    def test_sqlite_wal_mode_and_timeout(self):
        """Verify that SQLite connections use WAL mode and a 30s busy timeout."""
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            journal_mode = cur.fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")

            cur.execute("PRAGMA busy_timeout;")
            busy_timeout = cur.fetchone()[0]
            self.assertGreaterEqual(busy_timeout, 30000)
        finally:
            conn.close()

    def test_concurrent_writes_do_not_deadlock(self):
        """Simulate concurrent threads writing to ui_sessions under WAL mode."""
        sess = create_session(title="Concurrency Test")
        sid = sess["id"]
        errors = []

        def worker(idx: int):
            try:
                for i in range(10):
                    s = get_session(sid)
                    if s:
                        s["prompt_draft"] = f"worker-{idx}-iter-{i}"
                        save_session(s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Encountered concurrency errors: {errors}")
        delete_session(sid)

    def test_update_session_title_atomic(self):
        """Verify that update_session_title atomically updates the title in the DB."""
        sess = create_session(title="Untitled chat")
        sid = sess["id"]
        updated = update_session_title(sid, "Electric Vehicles 2026")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "Electric Vehicles 2026")

        reloaded = get_session(sid)
        self.assertEqual(reloaded["title"], "Electric Vehicles 2026")
        delete_session(sid)

    def test_save_session_preserves_custom_title_against_stale_default(self):
        """Verify that save_session will not overwrite a customized title with a stale default."""
        sess = create_session(title="Untitled chat")
        sid = sess["id"]

        # User renames session
        update_session_title(sid, "Custom Project Name")

        # Background thread had an older snapshot with "Untitled chat"
        stale_snapshot = dict(sess)
        stale_snapshot["title"] = "Untitled chat"
        stale_snapshot["goal"] = "scraping something"
        saved = save_session(stale_snapshot)

        # The custom name must be preserved!
        self.assertEqual(saved["title"], "Custom Project Name")
        reloaded = get_session(sid)
        self.assertEqual(reloaded["title"], "Custom Project Name")
        delete_session(sid)


if __name__ == "__main__":
    unittest.main()
