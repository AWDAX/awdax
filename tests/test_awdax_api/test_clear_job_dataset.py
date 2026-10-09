import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import scraper


class ClearJobDatasetTests(unittest.TestCase):
    def test_clears_only_the_selected_jobs_data(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "scraper.sqlite"

            def connection():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn

            with patch.object(scraper, "_get_db", connection), patch.object(scraper, "_UNIVERSAL_DB_INIT", False):
                service = scraper.UniversalScrapeService()
                with closing(connection()) as conn, conn:
                    for job_id in ("one", "two"):
                        conn.execute("INSERT INTO scrape_jobs (id) VALUES (?)", (job_id,))
                        conn.execute("INSERT INTO records (job_id, external_id, data_json) VALUES (?, ?, '{}')", (job_id, job_id))
                        conn.execute(
                            "INSERT INTO merged_tables (job_id, columns_json, rows_json, labels_json) VALUES (?, '[]', '[]', '[]')",
                            (job_id,),
                        )

                service.clear_job_dataset("one")
                service.clear_job_dataset("one")  # Clearing an empty dataset is safe.
                service.clear_job_dataset(None)

                with closing(connection()) as conn:
                    for table, column in (("records", "job_id"), ("merged_tables", "job_id")):
                        remaining = [row[0] for row in conn.execute(f"SELECT {column} FROM {table}")]
                        self.assertEqual(remaining, ["two"])
                    jobs = [row[0] for row in conn.execute("SELECT id FROM scrape_jobs ORDER BY id")]
                    self.assertEqual(jobs, ["one", "two"])

                # Deleting a chat removes its prompt, plans and sources too, and only that job's.
                with closing(connection()) as conn, conn:
                    for job_id in ("one", "two"):
                        conn.execute("INSERT INTO scrape_plans (job_id, plan_json) VALUES (?, '{}')", (job_id,))
                        conn.execute("INSERT INTO sources (job_id, url) VALUES (?, 'https://x.example/')", (job_id,))
                service.delete_job("one")
                service.delete_job(None)
                with closing(connection()) as conn:
                    for table, column in (("scrape_jobs", "id"), ("scrape_plans", "job_id"), ("sources", "job_id"), ("records", "job_id")):
                        remaining = [row[0] for row in conn.execute(f"SELECT {column} FROM {table}")]
                        self.assertEqual(remaining, ["two"], table)


if __name__ == "__main__":
    unittest.main()
