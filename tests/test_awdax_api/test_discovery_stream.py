import unittest
import queue
from unittest.mock import patch

from app import app
from awdax_api.orchestrator import _on_job, _on_source
from awdax_api.run_registry import instance_for_job, unregister_job
from awdax_api.session_store import append_message, append_run_event, load_instance_session, persist_session
from awdax_api.sources_stats_graph import build_sources_response
from discovery import SourceCandidate
from inspector import ScrapePlan, discover_inspected_from_queries
from query_generation import GeneratedQuery
from reasoning import ScrapeIntent
from ui_sessions import create_session, delete_session


class DiscoveryStreamTests(unittest.TestCase):
    def test_inspection_emits_source_before_and_after_validation(self):
        candidate = SourceCandidate(url="https://example.org/cars", title="Cars", domain="example.org")
        plan = ScrapePlan(
            source_name="Cars",
            entry_url=candidate.url,
            source_url=candidate.url,
            dry_run_rows=5,
            confidence=0.8,
        )
        updates = []
        with (
            patch("listing_sources.anchor_listings_for_intent", return_value=[]),
            patch("source_search.search_hits_for_query", return_value=[{"url": candidate.url}]),
            patch("discovery.candidate_from_serp_hit", return_value=candidate),
            patch("table_merge.intent_avoid_oem_sites", return_value=False),
            patch("inspector.inspect_source", return_value=plan),
        ):
            sources, plans = discover_inspected_from_queries(
                ScrapeIntent.from_dict({"topic": "cars"}),
                [GeneratedQuery(query="cars")],
                on_source=updates.append,
            )
        self.assertEqual([item["status"] for item in updates], ["inspecting", "validated"])
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(plans), 1)

    def test_source_is_persisted_and_sent_before_discovery_finishes(self):
        sess = create_session(title="Discovery stream test")
        source = {
            "url": "https://example.org/cars",
            "title": "Cars",
            "domain": "example.org",
            "origin": "search",
            "status": "inspecting",
        }
        try:
            with patch("awdax_api.orchestrator.live_bridge.notify_instance") as notify:
                _on_source(sess["id"], source)
                source["status"] = "validated"
                _on_source(sess["id"], source)
            current = load_instance_session(sess["id"])
            listed = build_sources_response(current)["sources"]
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["status"], "validated")
            self.assertEqual(notify.call_count, 2)
            self.assertEqual(notify.call_args.args[1]["type"], "source")
        finally:
            delete_session(sess["id"])

    def test_event_ids_keep_increasing_after_history_is_trimmed(self):
        sess = {"awdax_run": {"id": "run"}, "run_events": []}
        for index in range(55):
            append_run_event(sess, phase="discovery", detail=f"site {index}")
        self.assertEqual(len(sess["run_events"]), 50)
        self.assertEqual(sess["run_events"][-1]["id"], 55)

    def test_run_state_survives_session_reload(self):
        sess = create_session(title="Run persistence test")
        try:
            sess["goal"] = "Find cars"
            sess["awdax_run"] = {"id": "run-1", "phase": "discovery", "status": "running"}
            append_message(sess, role="user", content="Find cars")
            append_run_event(sess, phase="discovery", detail="Searching")
            persist_session(sess)
            loaded = load_instance_session(sess["id"])
            self.assertEqual(loaded["goal"], "Find cars")
            self.assertEqual(loaded["messages"][0]["content"], "Find cars")
            self.assertEqual(loaded["run_events"][0]["detail"], "Searching")
            self.assertEqual(loaded["awdax_run"]["phase"], "discovery")
        finally:
            delete_session(sess["id"])

    def test_event_stream_delivers_source_frames(self):
        sess = create_session(title="SSE source test")
        pending = queue.Queue()
        pending.put({"type": "source", "source": {"url": "https://example.org/cars", "status": "inspecting"}})
        try:
            with (
                patch("awdax_api.routes.live_bridge.subscribe", return_value=pending),
                patch("awdax_api.routes.live_bridge.unsubscribe"),
            ):
                response = app.test_client().get(f"/api/instances/{sess['id']}/live/stream", buffered=False)
                chunks = iter(response.response)
                self.assertIn(b"event: status", next(chunks))
                self.assertIn(b"event: source", next(chunks))
                response.close()
        finally:
            delete_session(sess["id"])

    def test_starting_chat_enables_live_discovery(self):
        sess = create_session(title="Live chat test")
        try:
            with patch("awdax_api.routes.start_run") as start:
                response = app.test_client().post(
                    f"/api/instances/{sess['id']}/messages",
                    json={"content": "Find electric cars"},
                )
            self.assertEqual(response.status_code, 201)
            start.assert_called_once_with(sess["id"], "Find electric cars", max_pages=None)
            loaded = load_instance_session(sess["id"])
            self.assertTrue(loaded["keep_live"])
            self.assertEqual(loaded["messages"][0]["content"], "Find electric cars")
        finally:
            delete_session(sess["id"])

    def test_new_job_is_registered_for_backend_live_events(self):
        sess = create_session(title="Job mapping test")
        try:
            _on_job(sess["id"], "job-stream-test")
            self.assertEqual(instance_for_job("job-stream-test"), sess["id"])
            self.assertEqual(load_instance_session(sess["id"])["job_id"], "job-stream-test")
        finally:
            unregister_job(sess["id"], "job-stream-test")
            delete_session(sess["id"])


if __name__ == "__main__":
    unittest.main()
