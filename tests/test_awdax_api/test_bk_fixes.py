"""BK3 (lost updates), BK4 (eGazette routing), BK5 (per-user access, proxy secret)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_sessions  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402
from regulatory_strategy import enrich_intent_for_execution, intent_uses_regulatory_feed  # noqa: E402


def _intent(prompt, pipeline="universal"):
    return ScrapeIntent(job_id="j", topic=prompt[:40], raw_prompt=prompt, pipeline=pipeline)


class RegulatoryRoutingTests(unittest.TestCase):
    def test_parliament_debates_stay_universal_even_if_model_says_regulatory(self):
        i = _intent("get all sessions of Rajya Sabha and Lok Sabha debates", "regulatory_feed")
        i.named_sites = ["https://egazette.gov.in"]
        out = enrich_intent_for_execution(i)
        self.assertEqual(out.pipeline, "universal")
        self.assertFalse(intent_uses_regulatory_feed(out))

    def test_explicit_egazette_is_regulatory(self):
        out = enrich_intent_for_execution(_intent("latest egazette notifications from ministry of finance"))
        self.assertEqual(out.pipeline, "regulatory_feed")
        self.assertTrue(intent_uses_regulatory_feed(out))

    def test_ev_prices_universal(self):
        out = enrich_intent_for_execution(_intent("Track EV prices in India"))
        self.assertEqual(out.pipeline, "universal")

    def test_plain_gazette_word_is_regulatory(self):
        out = enrich_intent_for_execution(_intent("gazette notifications this week"))
        self.assertEqual(out.pipeline, "regulatory_feed")

    def test_topic_used_when_raw_prompt_empty(self):
        i = ScrapeIntent(job_id="j", topic="egazette rules")
        self.assertTrue(intent_uses_regulatory_feed(i))


class _TempDb(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        self._patch.start()
        ui_sessions._initialized = None

    def tearDown(self):
        self._patch.stop()
        ui_sessions._initialized = None
        try:
            self._dir.cleanup()
        except OSError:
            pass


class InterruptedRunTests(_TempDb):
    def test_runs_cut_off_by_a_restart_are_marked_failed(self):
        from awdax_api.orchestrator import recover_interrupted_runs
        from awdax_api.session_store import set_awdax_run

        stuck = ui_sessions.create_session(user_id="u", title="stuck")
        set_awdax_run(stuck, status="running", phase="rendering", detail="Reading")
        stuck["run_active"] = True
        ui_sessions.save_session(stuck)
        done = ui_sessions.create_session(user_id="u", title="done")
        set_awdax_run(done, status="succeeded", phase="complete")
        ui_sessions.save_session(done)

        self.assertEqual(recover_interrupted_runs(), 1)
        after = ui_sessions.get_session(stuck["id"])
        self.assertEqual(after["awdax_run"]["status"], "failed")
        self.assertFalse(after["run_active"])
        self.assertIn("interrupted", after["messages"][-1]["content"].lower())
        self.assertEqual(ui_sessions.get_session(done["id"])["awdax_run"]["status"], "succeeded")
        self.assertEqual(recover_interrupted_runs(), 0)


class RunThreadMergeTests(_TempDb):
    def test_rename_during_run_survives_final_persist(self):
        from awdax_api import orchestrator
        from awdax_api.session_store import load_instance_session, persist_session

        sess = ui_sessions.create_session(user_id="u1", title="Old")
        sid = sess["id"]

        def fake_pipeline(s, goal, **kw):
            latest = load_instance_session(sid)
            latest["title"] = "Renamed"
            latest["archived"] = True
            latest["keep_live"] = True
            persist_session(latest)
            return s

        with mock.patch.object(orchestrator, "run_pipeline_for_session", side_effect=fake_pipeline), \
                mock.patch.object(orchestrator.live_bridge, "notify_instance"):
            orchestrator.mark_running(sid)
            orchestrator._run_thread(sid, "goal", None)
        final = load_instance_session(sid)
        self.assertEqual(final["title"], "Renamed")
        self.assertTrue(final["archived"])
        self.assertTrue(final["keep_live"])


class AccessTests(_TempDb):
    def setUp(self):
        super().setUp()
        import app as app_module

        self.client = app_module.app.test_client()

    def _h(self, uid):
        return {"X-User-Id": uid}

    def test_other_user_gets_404_everywhere(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.client.post("/api/instances", json={"title": "x" * 200}, headers=self._h("A"))
            self.assertEqual(r.status_code, 201)
            iid = r.get_json()["id"]
            self.assertEqual(len(r.get_json()["title"]), 80)
            self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=self._h("A")).status_code, 200)
            for method, path in [
                ("get", ""), ("patch", ""), ("delete", ""), ("get", "/messages"),
                ("post", "/messages"), ("get", "/dataset"), ("delete", "/dataset"),
                ("get", "/dashboard"), ("get", "/live"), ("patch", "/live"),
                ("get", "/sources"), ("get", "/dataset/stats"), ("post", "/dataset/rescore"),
                ("get", "/graph/parameters"), ("get", "/graph"),
            ]:
                resp = getattr(self.client, method)(f"/api/instances/{iid}{path}", json={"content": "hi"}, headers=self._h("B"))
                self.assertEqual(resp.status_code, 404, f"{method} {path}")
            # B's attempts changed nothing; A still sees it.
            listed = self.client.get("/api/instances", headers=self._h("A")).get_json()
            self.assertEqual([x["id"] for x in listed], [iid])
            self.assertEqual(self.client.get("/api/instances", headers=self._h("B")).get_json(), [])

    def test_proxy_secret(self):
        with mock.patch.dict(os.environ, {"PROXY_SHARED_SECRET": "s3"}, clear=True):
            wrong = self.client.post("/api/instances", json={}, headers={"X-User-Id": "A", "X-Proxy-Secret": "bad"})
            self.assertEqual(wrong.status_code, 201)
            self.assertNotEqual(ui_sessions.get_session(wrong.get_json()["id"])["user_id"], "A")
            ok = self.client.post("/api/instances", json={}, headers={"X-User-Id": "A", "X-Proxy-Secret": "s3"})
            self.assertEqual(ui_sessions.get_session(ok.get_json()["id"])["user_id"], "A")

    def test_unverifiable_token_is_a_json_401_not_a_shared_user(self):
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "real-secret-real-secret-real-secret-1"}, clear=True):
            r = self.client.get("/api/instances", headers={"Authorization": "Bearer not-a-jwt"})
            self.assertEqual(r.status_code, 401)
            self.assertIn("sign-in", r.get_json()["detail"])


class JwtTests(unittest.TestCase):
    SECRET = "real-secret-real-secret-real-secret-1"

    def _req(self, token=None, cookie=None):
        req = mock.Mock()
        req.headers = {"Authorization": f"Bearer {token}"} if token else {}
        req.cookies = {"awdax_token": cookie} if cookie else {}
        return req

    def test_bad_signature_fails_closed_when_secret_set(self):
        import jwt
        from auth_helper import AuthError, get_user_id

        tok = jwt.encode({"sub": "victim"}, "other-secret-other-secret-other-secret", algorithm="HS256")
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": self.SECRET}, clear=True):
            with self.assertRaises(AuthError):
                get_user_id(self._req(tok))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_user_id(self._req(tok)), "victim")

    def test_valid_hs256_token_and_cookie_fallback(self):
        import jwt
        from auth_helper import get_user_id

        tok = jwt.encode({"sub": "alice"}, self.SECRET, algorithm="HS256")
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": self.SECRET}, clear=True):
            self.assertEqual(get_user_id(self._req(tok)), "alice")
            self.assertEqual(get_user_id(self._req(cookie=tok)), "alice")

    def test_garbage_token_fails_closed_and_no_token_is_anonymous(self):
        from auth_helper import AuthError, get_user_id

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthError):
                get_user_id(self._req("not-a-jwt"))
            self.assertEqual(get_user_id(self._req()), "anonymous")


if __name__ == "__main__":
    unittest.main()
