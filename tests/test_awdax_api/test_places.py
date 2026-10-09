"""Phase 2: the Google Maps (Places) pipeline. No real network: requests and the scrape service are replaced."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402
import requests  # noqa: E402

import places_pipeline  # noqa: E402
import places_search  # noqa: E402
import scraper  # noqa: E402
import ui_sessions  # noqa: E402
from awdax_api.dataset_export import build_dataset_table  # noqa: E402
from awdax_api.run_report import format_discovery_report  # noqa: E402
from places_search import PlacesError, PlacesQuotaExceeded  # noqa: E402
from places_strategy import intent_uses_places, places_table_schema, reconcile_places_intent  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402

KEY = {"GOOGLE_MAPS_API_KEY": "test-key"}


def _intent(prompt, *, pipeline="universal", geography="", topic=None, places=None):
    return ScrapeIntent(job_id="job1", topic=topic or prompt, raw_prompt=prompt, geography=geography, pipeline=pipeline, places=places or {})


class RoutingTests(unittest.TestCase):
    def _reconcile(self, intent, env=KEY):
        with mock.patch.dict(os.environ, env, clear=True):
            return reconcile_places_intent(intent)

    def test_the_failing_example_goes_to_maps_with_lead_focus(self):
        i = self._reconcile(
            _intent("list all the local business leads in delhi ncr for web development", geography="Delhi NCR", topic="local business leads for web development")
        )
        self.assertEqual(i.pipeline, "places")
        # "Delhi NCR" is a 55,000 km2 region reaching Rohtak and Alwar: it is searched as its real cities instead
        self.assertEqual(i.places["locations"], ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"])
        self.assertTrue(i.places["lead_focus"])
        self.assertFalse(i.places["near_me"])
        self.assertEqual(i.places["search_terms"], ["local business leads for web development"])  # model gave none: topic
        self.assertTrue(intent_uses_places(i))

    def test_a_region_name_becomes_its_cities_but_nothing_else_is_rewritten(self):
        def cities(locations, geography=""):
            i = self._reconcile(_intent("cafes", pipeline="places", geography=geography, places={"search_terms": ["cafes"], "locations": locations}))
            return i.places["locations"]

        five = ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"]
        for name in ("Delhi NCR", "delhi ncr", "  Delhi   NCR ", "NCR", "National Capital Region", "Delhi/NCR", "Delhi-NCR"):
            self.assertEqual(cities([name]), five, name)
        self.assertEqual(cities([], geography="Delhi NCR"), five, "a region found only in the geography")
        self.assertEqual(cities(["Pune"]), ["Pune"])
        self.assertEqual(cities(["Noida", "Delhi NCR"]), ["Noida", "Delhi NCR"], "the user's own list is respected")
        self.assertEqual(cities(["Delhi", "Gurugram", "Noida"]), ["Delhi", "Gurugram", "Noida"], "a planner that already listed cities")
        many = [f"City {n}" for n in range(12)]
        self.assertEqual(len(cities(many)), 8)

    def test_the_models_own_settings_are_cleaned_and_clamped(self):
        i = self._reconcile(
            _intent(
                "cafes in pune",
                pipeline="places",
                places={
                    "search_terms": ["cafes", "Cafes", " ", "bakeries"] + [f"t{n}" for n in range(20)],
                    "locations": ["Pune"],
                    "target_count": 99999,
                    "extra_fields": ["delivery", "reviews_text", "opening_hours"],
                    "lead_focus": "",
                },
            )
        )
        self.assertEqual(i.places["search_terms"][:2], ["cafes", "bakeries"])
        self.assertEqual(len(i.places["search_terms"]), 8)
        self.assertEqual(i.places["target_count"], 300)
        self.assertEqual(i.places["extra_fields"], ["delivery", "opening_hours"])

    def test_no_place_named_means_near_me(self):
        i = self._reconcile(_intent("cafes near me"))
        self.assertEqual(i.pipeline, "places")
        self.assertTrue(i.places["near_me"])
        self.assertEqual(i.places["locations"], [])

    def test_without_a_maps_key_the_web_pipeline_is_kept(self):
        i = self._reconcile(_intent("cafes in pune", pipeline="places", places={"search_terms": ["cafes"]}), env={})
        self.assertEqual(i.pipeline, "universal")
        self.assertFalse(intent_uses_places(i))
        j = self._reconcile(_intent("cafes near me"), env={})
        self.assertEqual(j.pipeline, "universal")

    def test_other_requests_are_left_alone(self):
        for prompt, geo in (
            ("list all EV cars under 20 lakh in India", "India"),
            ("average gold price in India since 2020", "India"),
            ("sessions of the Lok Sabha in Delhi", "Delhi"),
        ):
            i = self._reconcile(_intent(prompt, geography=geo))
            self.assertEqual(i.pipeline, "universal", prompt)

    def test_egazette_wins_even_if_the_model_said_places(self):
        i = self._reconcile(_intent("latest egazette notifications near me", pipeline="places"))
        self.assertEqual(i.pipeline, "regulatory_feed")
        self.assertFalse(intent_uses_places(i))

    def test_schema_has_the_core_columns_and_asked_extras(self):
        i = self._reconcile(_intent("restaurants in pune", pipeline="places", places={"search_terms": ["restaurants"], "locations": ["Pune"], "extra_fields": ["delivery"]}))
        schema = places_table_schema(i)
        self.assertEqual(len(schema["columns"]), len(schema["column_labels"]))
        for col in ("name", "phone", "website", "rating", "address", "source_url", "lead_score", "delivery"):
            self.assertIn(col, schema["columns"])
        self.assertIn("Score", schema["column_labels"])
        lead = self._reconcile(_intent("leads in pune for seo", geography="Pune"))
        self.assertIn("Lead score", places_table_schema(lead)["column_labels"])


class GeometryTests(unittest.TestCase):
    def test_tiles_cover_the_whole_viewport_and_respect_the_cap(self):
        viewport = (28.2, 76.8, 29.0, 77.7)  # about 89 km x 87 km: Delhi NCR sized
        cells = places_pipeline.grid_cells(viewport, 8, 16)
        self.assertLessEqual(len(cells), 16)
        self.assertEqual(min(c[0] for c in cells), viewport[0])
        self.assertEqual(max(c[2] for c in cells), viewport[2])
        self.assertAlmostEqual(min(c[1] for c in cells), viewport[1])
        self.assertAlmostEqual(max(c[3] for c in cells), viewport[3])
        self.assertEqual(len(set(cells)), len(cells))

    def test_a_small_area_is_one_tile_and_tiles_start_at_the_centre(self):
        self.assertEqual(len(places_pipeline.grid_cells((28.60, 77.20, 28.62, 77.22), 8, 16)), 1)
        cells = places_pipeline.grid_cells((0.0, 0.0, 0.4, 0.4), 10, 100)
        centre = (0.2, 0.2)

        def dist(c):
            return ((c[0] + c[2]) / 2 - centre[0]) ** 2 + ((c[1] + c[3]) / 2 - centre[1]) ** 2

        self.assertAlmostEqual(dist(cells[0]), min(dist(c) for c in cells))
        self.assertAlmostEqual(dist(cells[-1]), max(dist(c) for c in cells))

    def test_a_point_is_widened_to_a_searchable_area(self):
        low_lat, low_lng, high_lat, high_lng = places_pipeline.at_least((28.6, 77.2, 28.6, 77.2))
        self.assertLess(low_lat, high_lat)
        self.assertLess(low_lng, high_lng)
        big = (28.0, 76.0, 29.0, 78.0)
        self.assertEqual(places_pipeline.at_least(big), big)

    def test_bbox_is_symmetric_and_grows_with_radius(self):
        a, b = places_pipeline.bbox(28.6, 77.2, 2), places_pipeline.bbox(28.6, 77.2, 5)
        self.assertAlmostEqual((a[0] + a[2]) / 2, 28.6)
        self.assertLess(b[0], a[0])
        self.assertGreater(b[3], a[3])

    def test_task_order_visits_every_pair_once(self):
        for areas, terms in ((3, 4), (5, 8), (16, 8), (5, 2), (1, 3), (4, 1)):
            pairs = places_pipeline.task_order(areas, terms)
            self.assertEqual(sorted(pairs), sorted((a, t) for a in range(areas) for t in range(terms)), (areas, terms))
        self.assertEqual(places_pipeline.task_order(1, 3), [(0, 0), (0, 1), (0, 2)])

    def test_the_first_searches_already_cover_every_city_and_most_categories(self):
        first8 = places_pipeline.task_order(5, 8)[:8]  # 5 cities x 8 categories, but a run may stop after 8 searches
        self.assertEqual({a for a, _ in first8}, {0, 1, 2, 3, 4}, "every city is searched")
        self.assertGreaterEqual(len({t for _, t in first8}), 5, "and several different categories")
        first5 = places_pipeline.task_order(5, 8)[:5]
        self.assertEqual(len({t for _, t in first5}), 5, "no category repeats in the first round")

    def test_search_urls_name_the_place_or_near_me(self):
        self.assertIn("cafes+in+Noida", places_pipeline.maps_search_url("cafes", "Noida"))
        self.assertIn("cafes+near+me", places_pipeline.maps_search_url("cafes", "within 5 km"))


class RowTests(unittest.TestCase):
    PLACE = {
        "id": "p1",
        "displayName": {"text": "Sharma  Clinic"},
        "formattedAddress": "Sector 5, Noida",
        "googleMapsUri": "https://maps.google.com/?cid=1",
        "primaryTypeDisplayName": {"text": "Dental clinic"},
        "businessStatus": "OPERATIONAL",
        "nationalPhoneNumber": "099 1234 5678",
        "rating": 4.5,
        "userRatingCount": 120,
    }

    def test_a_place_becomes_a_row(self):
        row = places_pipeline.place_row(self.PLACE, term="clinics", area="Noida", extra_fields=[], lead_focus="")
        self.assertEqual(
            {k: row[k] for k in ("id", "name", "category", "phone", "website", "has_website", "rating", "reviews", "area", "source_url", "business_status")},
            {
                "id": "p1", "name": "Sharma Clinic", "category": "Dental clinic", "phone": "099 1234 5678", "website": "", "has_website": "no",
                "rating": "4.5", "reviews": "120", "area": "Noida", "source_url": "https://maps.google.com/?cid=1", "business_status": "Operational",
            },
        )

    def test_a_place_google_gave_no_display_name_gets_a_category_from_its_type(self):
        place = {**self.PLACE, "primaryTypeDisplayName": None, "primaryType": "coaching_center"}
        self.assertEqual(places_pipeline.place_row(place, term="t", area="a", extra_fields=[], lead_focus="")["category"], "Coaching center")
        bare = {k: v for k, v in self.PLACE.items() if k != "primaryTypeDisplayName"}
        self.assertEqual(places_pipeline.place_row(bare, term="t", area="a", extra_fields=[], lead_focus="")["category"], "")

    def test_unusable_places_are_dropped(self):
        for bad in ({**self.PLACE, "id": ""}, {**self.PLACE, "displayName": {}}, {**self.PLACE, "businessStatus": "CLOSED_PERMANENTLY"}):
            self.assertIsNone(places_pipeline.place_row(bad, term="t", area="a", extra_fields=[], lead_focus=""))

    def test_extras_are_filled_only_when_asked(self):
        place = {**self.PLACE, "delivery": True, "dineIn": False, "priceLevel": "PRICE_LEVEL_MODERATE", "regularOpeningHours": {"weekdayDescriptions": ["Mon: 9-5", "Tue: 9-5"]}}
        row = places_pipeline.place_row(place, term="t", area="a", extra_fields=["delivery", "dine_in", "price_level", "opening_hours"], lead_focus="")
        self.assertEqual((row["delivery"], row["dine_in"], row["price_level"], row["hours"]), ("yes", "no", "Moderate", "Mon: 9-5 | Tue: 9-5"))
        plain = places_pipeline.place_row(place, term="t", area="a", extra_fields=[], lead_focus="")
        self.assertNotIn("delivery", plain)

    def test_lead_score_prefers_no_website_for_a_web_seller_and_a_website_otherwise(self):
        base = {"phone": "1", "rating": "4.6", "reviews": "80", "business_status": "Operational"}
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "no"}, "web development"), 100)
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "yes"}, "web development"), 70)
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "yes"}, "accounting software for clinics"), 70)  # software: web seller
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "yes"}, "payroll services"), 100)
        self.assertEqual(places_pipeline.lead_score({**base, "has_website": "no"}, "payroll services"), 70)
        self.assertEqual(places_pipeline.lead_score({"has_website": "no"}, ""), 0)
        self.assertEqual(places_pipeline.lead_score({"rating": "oops", "reviews": "x"}, ""), 0)


class _Response:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = text or json.dumps(self._body)
        self.content = self.text.encode()

    def json(self):
        return self._body


class ClientTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, KEY, clear=True)
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(places_search.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_request_shape(self):
        with mock.patch.object(places_search.requests, "post", return_value=_Response(body={"places": [{"id": "a"}], "nextPageToken": "T2"})) as post:
            places, token = places_search.search_text(
                "cafes", field_mask=places_search.field_mask_for(["delivery"]), rect=(1.0, 2.0, 3.0, 4.0), page_token="T1"
            )
        self.assertEqual((places, token), ([{"id": "a"}], "T2"))
        _, kwargs = post.call_args
        self.assertEqual(post.call_args.args[0], "https://places.googleapis.com/v1/places:searchText")
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "test-key")
        mask = kwargs["headers"]["X-Goog-FieldMask"]
        self.assertIn("nextPageToken", mask)
        self.assertIn("places.nationalPhoneNumber", mask)
        self.assertIn("places.delivery", mask)
        self.assertNotIn("places.reviews", mask)
        body = kwargs["json"]
        self.assertEqual(body["textQuery"], "cafes")
        self.assertEqual(body["pageSize"], 20)
        self.assertEqual(body["pageToken"], "T1")
        self.assertEqual(body["locationRestriction"], {"rectangle": {"low": {"latitude": 1.0, "longitude": 2.0}, "high": {"latitude": 3.0, "longitude": 4.0}}})
        self.assertNotIn("locationBias", body)

    def test_circle_bias_radius_is_capped(self):
        with mock.patch.object(places_search.requests, "post", return_value=_Response()) as post:
            places_search.search_text("x", field_mask="m", circle=(1.0, 2.0, 90000))
        self.assertEqual(post.call_args.kwargs["json"]["locationBias"]["circle"]["radius"], 50000.0)

    def test_a_busy_google_is_retried_then_succeeds(self):
        answers = [_Response(503), _Response(429), _Response(body={"places": []})]
        with mock.patch.object(places_search.requests, "post", side_effect=answers) as post:
            self.assertEqual(places_search.search_text("x", field_mask="m"), ([], None))
        self.assertEqual(post.call_count, 3)

    def test_a_refused_key_fails_at_once_with_a_readable_message(self):
        denied = _Response(403, text=json.dumps({"error": {"message": "API key not valid"}}))
        with mock.patch.object(places_search.requests, "post", return_value=denied) as post:
            with self.assertRaisesRegex(PlacesError, "API key not valid"):
                places_search.search_text("x", field_mask="m")
        self.assertEqual(post.call_count, 1)

    def test_exhausted_retries_and_network_errors_raise_places_error(self):
        with mock.patch.object(places_search.requests, "post", side_effect=requests.ConnectionError("down")):
            with self.assertRaisesRegex(PlacesError, "did not answer"):
                places_search.search_text("x", field_mask="m")

    def test_no_key_is_a_clear_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PlacesError, "not set up"):
                places_search.search_text("x", field_mask="m")


class _MeterBase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._dir.cleanup)
        path = Path(self._dir.name) / "p.sqlite"

        def connect():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        patch = mock.patch.object(places_search, "_db", connect)
        patch.start()
        self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, KEY, clear=True)
        env.start()
        self.addCleanup(env.stop)


class MeterTests(_MeterBase):
    def test_a_user_cannot_pass_the_daily_cap_and_others_are_unaffected(self):
        os.environ["PLACES_MAX_CALLS_PER_USER_DAY"] = "5"
        places_search.charge("u1", 3)
        places_search.charge("u1", 2)
        with self.assertRaisesRegex(PlacesQuotaExceeded, "daily"):
            places_search.charge("u1", 1)
        places_search.charge("u2", 5)

    def test_the_monthly_cap_is_shared_by_everyone(self):
        os.environ["PLACES_MONTHLY_CALL_CAP"] = "6"
        places_search.charge("u1", 4)
        places_search.charge("u2", 2)
        with self.assertRaisesRegex(PlacesQuotaExceeded, "month"):
            places_search.charge("u3", 1)
        self.assertEqual(places_search.usage_this_month(), 6)

    def test_a_refused_charge_costs_nothing(self):
        os.environ["PLACES_MAX_CALLS_PER_USER_DAY"] = "2"
        with self.assertRaises(PlacesQuotaExceeded):
            places_search.charge("u1", 3)
        self.assertEqual(places_search.usage_this_month(), 0)

    def test_the_default_cap_is_the_free_tier(self):
        places_search.charge("u1", 1)
        os.environ["PLACES_MAX_CALLS_PER_USER_DAY"] = "5000"
        with self.assertRaises(PlacesQuotaExceeded):
            places_search.charge("u1", 1000)


class RetentionTests(_MeterBase):
    def _seed(self, job_id, age_days):
        conn = places_search._db()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, job_id TEXT, data_json TEXT);
            CREATE TABLE IF NOT EXISTS merged_tables (job_id TEXT PRIMARY KEY, rows_json TEXT);
            """
        )
        conn.execute("INSERT INTO records (job_id, data_json) VALUES (?, '{}')", (job_id,))
        conn.execute("INSERT INTO merged_tables (job_id, rows_json) VALUES (?, '[]')", (job_id,))
        places_search._ensure_tables(conn)
        from datetime import datetime, timedelta, timezone

        when = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        conn.execute("INSERT INTO places_jobs (job_id, created_at) VALUES (?,?)", (job_id, when))
        conn.commit()
        conn.close()

    def _left(self):
        conn = places_search._db()
        out = sorted(r[0] for r in conn.execute("SELECT job_id FROM records"))
        conn.close()
        return out

    def test_nothing_is_deleted_unless_a_retention_is_set(self):
        self._seed("old", 90)
        self.assertEqual(places_search.purge_expired(), 0)
        self.assertEqual(self._left(), ["old"])

    def test_only_maps_data_older_than_the_retention_is_deleted(self):
        self._seed("old", 90)
        self._seed("fresh", 2)
        conn = places_search._db()
        conn.execute("INSERT INTO records (job_id, data_json) VALUES ('web-job', '{}')")  # not a Maps job: never touched
        conn.commit()
        conn.close()
        os.environ["PLACES_RETENTION_DAYS"] = "30"
        self.assertEqual(places_search.purge_expired(), 1)
        self.assertEqual(self._left(), ["fresh", "web-job"])
        self.assertEqual(places_search.purge_expired(), 0)

    def test_a_bad_setting_keeps_everything(self):
        self._seed("old", 90)
        os.environ["PLACES_RETENTION_DAYS"] = "soon"
        self.assertEqual(places_search.purge_expired(), 0)


class GeocodeTests(_MeterBase):
    OK = {"status": "OK", "results": [{"geometry": {"location": {"lat": 28.6, "lng": 77.2}, "viewport": {"southwest": {"lat": 28.4, "lng": 76.9}, "northeast": {"lat": 28.9, "lng": 77.5}}}}]}

    def test_a_name_is_geocoded_once_then_served_from_the_cache(self):
        with mock.patch.object(places_search.requests, "get", return_value=_Response(body=self.OK)) as get:
            first = places_search.geocode("Delhi NCR")
            again = places_search.geocode("  delhi   ncr ")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(first, again)
        self.assertEqual(first["viewport"], (28.4, 76.9, 28.9, 77.5))
        self.assertEqual(first["center"], (28.6, 77.2))

    def test_an_old_cache_entry_is_refetched(self):
        with mock.patch.object(places_search.requests, "get", return_value=_Response(body=self.OK)) as get:
            places_search.geocode("Delhi")
            conn = places_search._db()
            conn.execute("UPDATE geo_cache SET created_at='2020-01-01T00:00:00+00:00'")
            conn.commit()
            conn.close()
            places_search.geocode("Delhi")
        self.assertEqual(get.call_count, 2)

    def test_an_unknown_name_is_remembered_but_a_disabled_api_is_not(self):
        with mock.patch.object(places_search.requests, "get", return_value=_Response(body={"status": "ZERO_RESULTS", "results": []})) as get:
            self.assertIsNone(places_search.geocode("Nowhereville"))
            self.assertIsNone(places_search.geocode("Nowhereville"))
        self.assertEqual(get.call_count, 1)
        with mock.patch.object(places_search.requests, "get", return_value=_Response(body={"status": "REQUEST_DENIED"})) as get:
            self.assertIsNone(places_search.geocode("Delhi"))
            self.assertIsNone(places_search.geocode("Delhi"))
        self.assertEqual(get.call_count, 2)

    def test_network_failure_is_none(self):
        with mock.patch.object(places_search.requests, "get", side_effect=requests.ConnectionError("down")):
            self.assertIsNone(places_search.geocode("Delhi"))


class _FakeService:
    """Stands in for scraper.universal_service: keeps what the run stores and announces."""

    def __init__(self):
        self.records, self.tables, self.events = [], [], []

    def store_record(self, job_id, source_url, row, plan=None):
        self.records.append((job_id, source_url, row))
        return {"id": len(self.records)}

    def save_merged_table(self, job_id, table):
        self.tables.append((job_id, table))

    def emit_event(self, kind, data=None):
        self.events.append((kind, data))

    def get_merged_table(self, job_id):
        return self.tables[-1][1] if self.tables else None


def _place(pid, name=None, **extra):
    return {"id": pid, "displayName": {"text": name or pid}, "googleMapsUri": f"https://maps.google.com/?cid={pid}", "businessStatus": "OPERATIONAL", **extra}


class RunTests(unittest.TestCase):
    def setUp(self):
        self.service = _FakeService()
        for patch in (
            mock.patch.object(scraper, "universal_service", self.service),
            mock.patch.dict(os.environ, {**KEY, "PLACES_WORKERS": "2"}, clear=True),
            mock.patch.object(places_search, "charge"),
            mock.patch.object(places_search, "register_job"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.calls = []
        self.progress, self.sources = [], []

    def _cfg(self, **over):
        cfg = {"search_terms": ["restaurants", "clinics"], "locations": ["Delhi NCR"], "near_me": False, "target_count": 200, "extra_fields": [], "lead_focus": "web development"}
        cfg.update(over)
        return cfg

    def _run(self, cfg, *, hint=None, search=None, user="u1", **kw):
        intent = _intent("leads", pipeline="places", places=cfg)
        sess = {"id": "chat1", "table_schema": places_table_schema(intent)}
        with mock.patch.object(places_search, "search_text", side_effect=search or self._search):
            return places_pipeline.run_places_job(
                sess, intent, user_id=user, location_hint=hint,
                on_progress=lambda phase, msg: self.progress.append((phase, msg)),
                on_source=self.sources.append, **kw,
            )

    def _search(self, query, *, field_mask, rect=None, circle=None, page_token=None, **_):
        """20 fresh places per call, three pages per query."""
        n = len(self.calls)
        self.calls.append({"query": query, "rect": rect, "token": page_token})
        page = int(page_token or 1)
        places = [_place(f"{n}-{i}", websiteUri="https://x.test" if i % 2 else "", nationalPhoneNumber="1", rating=4.2, userRatingCount=60) for i in range(20)]
        return places, (str(page + 1) if page < 3 else None)

    def _geocode(self, viewport=(28.2, 76.8, 29.0, 77.7)):
        return mock.patch.object(places_search, "geocode", return_value={"center": (28.6, 77.2), "viewport": viewport})

    def test_a_named_region_is_tiled_and_stops_at_the_target(self):
        with self._geocode():
            stats = self._run(self._cfg(target_count=100))
        self.assertEqual(stats["stopped"], "target")
        self.assertGreaterEqual(stats["places"], 100)
        self.assertLess(stats["places"], 100 + 5 * 20)
        rects = [c["rect"] for c in self.calls if c["token"] is None]
        self.assertGreater(len({r for r in rects}), 1, "first pages are spread over several tiles")
        self.assertTrue(all(c["rect"] is not None for c in self.calls))
        self.assertEqual({c["query"] for c in self.calls}, {"restaurants", "clinics"})  # the rectangle carries the place
        # the table was saved sorted, with every column of the schema, and announced
        job, table = self.service.tables[-1]
        self.assertEqual(job, "job1")
        scores = [int(r["lead_score"]) for r in table["rows"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(set(table["rows"][0]), set(table["columns"]))
        self.assertTrue(any(kind == "table" for kind, _ in self.service.events))
        self.assertEqual(len(self.service.records), stats["places"])

    def test_a_web_seller_sees_businesses_without_a_website_first(self):
        with self._geocode():
            self._run(self._cfg(target_count=40))
        rows = self.service.tables[-1][1]["rows"]
        self.assertEqual(rows[0]["has_website"], "no")
        self.assertEqual(rows[-1]["has_website"], "yes")

    def test_no_category_can_fill_the_target_before_the_others_are_searched(self):
        with self._geocode():
            stats = self._run(self._cfg(search_terms=["a", "b", "c", "d"], locations=["X"], target_count=80))
        by_term = {}
        for r in self.service.tables[-1][1]["rows"]:
            by_term[r["matched_query"]] = by_term.get(r["matched_query"], 0) + 1
        self.assertEqual(set(by_term), {"a", "b", "c", "d"}, "every category was searched before the target was reached")
        self.assertLessEqual(max(by_term.values()), 40, by_term)  # 1.5x its even share (30) rounded up to whole pages of 20
        self.assertEqual(stats["stopped"], "target")

    def test_the_cap_lifts_when_the_other_categories_have_nothing_to_give(self):
        def search(query, *, page_token=None, **kw):
            self.calls.append(query)
            nxt = {None: "2", "2": "3"}.get(page_token)  # "a" has three pages of 20; the others have nothing
            return ([_place(f"{query}-{len(self.calls)}-{i}") for i in range(20)] if query == "a" else []), (nxt if query == "a" else None)

        with self._geocode((28.60, 77.20, 28.62, 77.22)):
            stats = self._run(self._cfg(search_terms=["a", "b", "c"], locations=["X"], target_count=60), search=search)
        self.assertGreaterEqual(stats["places"], 60)
        self.assertEqual(stats["stopped"], "target")

    def test_several_cities_are_all_searched_early(self):
        def geocode(name):
            base = {"Delhi": 28.6, "Gurugram": 28.45, "Noida": 28.57, "Ghaziabad": 28.67, "Faridabad": 28.41}[name]
            return {"center": (base, 77.2), "viewport": (base - 0.05, 77.15, base + 0.05, 77.25)}

        os.environ["PLACES_MAX_CALLS_PER_RUN"] = "8"
        with mock.patch.object(places_search, "geocode", side_effect=geocode):
            self._run(self._cfg(locations=["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"], search_terms=[f"t{i}" for i in range(8)], target_count=300))
        areas = {r["area"] for r in self.service.tables[-1][1]["rows"]}
        terms = {r["matched_query"] for r in self.service.tables[-1][1]["rows"]}
        self.assertEqual(areas, {"Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"}, "8 searches reached all 5 cities")
        self.assertGreaterEqual(len(terms), 5)

    def test_budget_stops_the_run_and_says_so(self):
        os.environ["PLACES_MAX_CALLS_PER_RUN"] = "3"
        with self._geocode():
            stats = self._run(self._cfg())
        self.assertEqual((stats["calls"], len(self.calls), stats["stopped"]), (3, 3, "budget"))

    def test_calls_are_charged_before_they_are_made(self):
        order = []
        places_search.charge.side_effect = lambda user, n: order.append(("charge", user, n))
        os.environ["PLACES_MAX_CALLS_PER_RUN"] = "4"
        with self._geocode():
            self._run(self._cfg(), search=lambda *a, **k: (order.append(("call",)) or self._search(*a, **k)))
        self.assertEqual(order[0][:2], ("charge", "u1"))
        self.assertEqual(sum(n for _, _, n in (o for o in order if o[0] == "charge")), 4)
        self.assertEqual([o[0] for o in order].count("call"), 4)

    def test_a_used_up_quota_keeps_what_was_found(self):
        seen = {"n": 0}

        def charge(user, n):
            seen["n"] += 1
            if seen["n"] > 1:
                raise PlacesQuotaExceeded("monthly budget used up")

        places_search.charge.side_effect = charge
        with self._geocode():
            stats = self._run(self._cfg())
        self.assertEqual(stats["stopped"], "quota")
        self.assertGreater(stats["places"], 0)
        self.assertIn("monthly", stats["error"])

    def test_quota_before_anything_is_found_is_an_error(self):
        places_search.charge.side_effect = PlacesQuotaExceeded("daily limit")
        with self._geocode(), self.assertRaisesRegex(PlacesQuotaExceeded, "daily"):
            self._run(self._cfg())

    def test_the_same_place_from_two_searches_is_one_row(self):
        def search(query, **kw):
            return [_place("same", name=f"found by {query}")], None

        with self._geocode((28.60, 77.20, 28.62, 77.22)):
            stats = self._run(self._cfg(), search=search)
        self.assertEqual(stats["places"], 1)
        self.assertEqual(self.service.tables[-1][1]["rows"][0]["matched_query"], "restaurants")

    def test_several_places_are_all_searched_and_alternate(self):
        named = {}

        def geocode(name):
            named[name] = True
            base = 10 if name == "Pune" else 20
            return {"center": (base, base), "viewport": (base, base, base + 0.3, base + 0.3)}

        with mock.patch.object(places_search, "geocode", side_effect=geocode):
            stats = self._run(self._cfg(locations=["Pune", "Mumbai"], search_terms=["cafes"], target_count=500))
        self.assertEqual(set(named), {"Pune", "Mumbai"})
        self.assertEqual({r["area"] for r in self.service.tables[-1][1]["rows"]}, {"Pune", "Mumbai"})
        self.assertEqual(stats["locations"], ["Pune", "Mumbai"])
        self.assertEqual({s["title"] for s in self.sources}, {"Google Maps: cafes — Pune", "Google Maps: cafes — Mumbai"})

    def test_a_place_google_cannot_find_is_searched_by_name_in_the_query(self):
        with mock.patch.object(places_search, "geocode", return_value=None):
            self._run(self._cfg(locations=["Narnia"], search_terms=["cafes"], target_count=5))
        self.assertEqual(self.calls[0]["query"], "cafes in Narnia")
        self.assertIsNone(self.calls[0]["rect"])

    def test_near_me_widens_ring_by_ring_only_while_short_of_the_target(self):
        def search(query, *, rect=None, **kw):
            self.calls.append({"query": query, "rect": rect})
            return [_place(f"{rect}-{i}") for i in range(5)], None  # few places, no next page

        stats = self._run(self._cfg(locations=[], near_me=True, search_terms=["cafes"], target_count=15), hint={"lat": 28.6, "lng": 77.2}, search=search)
        rects = [c["rect"] for c in self.calls]
        self.assertEqual(len(rects), 3)  # 5 + 5 + 5 = target reached in the third ring
        widths = [r[3] - r[1] for r in rects]
        self.assertEqual(widths, sorted(widths))
        self.assertEqual(len(set(widths)), 3)
        self.assertEqual(stats["stopped"], "target")
        self.assertTrue(any("widening" in m for _, m in self.progress))

    def test_near_me_stops_widening_at_the_last_ring(self):
        def search(query, *, rect=None, **kw):
            self.calls.append(rect)
            return [], None

        with self.assertRaisesRegex(PlacesError, "no places"):
            self._run(self._cfg(locations=[], near_me=True, search_terms=["cafes"], target_count=50), hint={"lat": 28.6, "lng": 77.2}, search=search)
        self.assertEqual(len(self.calls), len(places_pipeline.RING_KM))

    def test_near_me_without_any_position_asks_for_a_place(self):
        with self.assertRaisesRegex(PlacesError, "Name a city"):
            self._run(self._cfg(locations=[], near_me=True), hint=None)

    def test_a_default_centre_can_stand_in_for_the_position(self):
        os.environ["PLACES_DEFAULT_CENTER"] = "18.52, 73.85"
        stats = self._run(self._cfg(locations=[], near_me=True, search_terms=["cafes"], target_count=20))
        self.assertGreaterEqual(stats["places"], 20)
        lat = (self.calls[0]["rect"][0] + self.calls[0]["rect"][2]) / 2
        self.assertAlmostEqual(lat, 18.52, places=2)

    def test_when_every_search_fails_the_error_is_raised(self):
        def search(*a, **k):
            raise PlacesError("Google Maps refused the API key.")

        with self._geocode(), self.assertRaisesRegex(PlacesError, "refused the API key"):
            self._run(self._cfg(), search=search)

    def test_one_bad_search_does_not_lose_the_others(self):
        def search(query, **kw):
            if query == "clinics":
                raise ValueError("garbled")
            return [_place(f"r-{len(self.calls)}") for _ in range(1)] + [_place(f"x{len(self.calls)}")], None

        with self._geocode((28.60, 77.20, 28.62, 77.22)):
            stats = self._run(self._cfg(), search=search)
        self.assertGreater(stats["places"], 0)
        self.assertIn("could not be read", stats["error"])

    def test_a_deleted_chat_stops_the_run_before_it_spends_more(self):
        class Gone(Exception):
            pass

        def alive():
            raise Gone()

        with self._geocode(), self.assertRaises(Gone):
            self._run(self._cfg(), check_alive=alive)
        self.assertEqual(self.calls, [])

    def test_progress_and_sources_are_reported(self):
        with self._geocode():
            self._run(self._cfg(target_count=30))
        self.assertTrue(any(phase == "extracting" and "places so far" in msg for phase, msg in self.progress))
        self.assertTrue(self.sources)
        for s in self.sources:
            self.assertEqual((s["status"], s["origin"]), ("validated", "places"))
            self.assertTrue(s["url"].startswith("https://www.google.com/maps/search/"))


class DatasetAndReportTests(unittest.TestCase):
    def test_a_places_chat_reads_its_saved_table_and_never_re_merges(self):
        service = _FakeService()
        service.save_merged_table("job1", {"columns": ["name", "phone"], "column_labels": ["Name", "Phone"], "rows": [{"name": "A", "phone": "1"}, {"name": "A", "phone": "2"}]})
        sess = {"id": "c", "job_id": "job1", "intent": {"pipeline": "places", "topic": "x", "job_id": "job1"}}
        with mock.patch("awdax_api.dataset_export.universal_service", service):
            table = build_dataset_table(sess)
        self.assertEqual(table["row_count"], 2, "two businesses with one name stay two rows")
        self.assertIn("source_url", table["columns"])
        service.tables.clear()
        with mock.patch("awdax_api.dataset_export.universal_service", service):
            self.assertIsNone(build_dataset_table(sess))

    def test_the_report_describes_the_maps_run(self):
        stats = {"places": 87, "areas": 16, "searched": 9, "calls": 12, "stopped": "budget", "terms": ["restaurants", "clinics"], "locations": ["Delhi NCR"], "error": ""}
        text = format_discovery_report({"places_stats": stats, "table_schema": {"columns": ["name", "phone"]}}, goal="leads")
        for fragment in ("87 places in Delhi NCR", "12 Google requests", "restaurants, clinics", "PLACES_MAX_CALLS_PER_RUN", "name, phone"):
            self.assertIn(fragment, text)
        self.assertNotIn("VALIDATED SOURCES", text)


class WiringTests(unittest.TestCase):
    def test_the_pipeline_runs_maps_without_discovery_or_plans(self):
        from awdax_api import pipeline_runner

        intent = _intent("cafes in pune", pipeline="places", places={"search_terms": ["cafes"], "locations": ["Pune"], "target_count": 10, "extra_fields": [], "lead_focus": ""})
        sess = {"id": "chat1", "user_id": "u7"}
        stats = {"places": 3}
        with (
            mock.patch.object(pipeline_runner, "parse_prompt", return_value=intent),
            mock.patch.object(pipeline_runner, "generate_search_queries", side_effect=AssertionError("web discovery must not run")),
            mock.patch.object(pipeline_runner, "discover_inspected_sources", side_effect=AssertionError("web discovery must not run")),
            mock.patch.object(pipeline_runner.universal_service, "clear_job_dataset"),
            mock.patch.dict(os.environ, KEY, clear=True),
            mock.patch("places_pipeline.run_places_job", return_value=stats) as run,
        ):
            out = pipeline_runner.run_pipeline_for_session(sess, "cafes in pune", location_hint={"lat": 1, "lng": 2})
        self.assertEqual(out["places_stats"], stats)
        self.assertEqual((out["plans"], out["sources"]), ([], []))
        self.assertIn("name", out["table_schema"]["columns"])
        self.assertEqual(out["search_queries"][0]["query"], "cafes — Pune")
        self.assertEqual(run.call_args.kwargs["user_id"], "u7")
        self.assertEqual(run.call_args.kwargs["location_hint"], {"lat": 1, "lng": 2})

    def test_the_live_switch_does_not_rerun_a_finished_maps_search(self):
        from awdax_api import orchestrator

        sess = {"id": "c", "goal": "cafes", "intent": {"pipeline": "places"}, "awdax_run": {"status": "succeeded"}, "messages": [{"role": "user"}]}
        with mock.patch.object(orchestrator, "start_run") as start, mock.patch.object(orchestrator, "is_running", return_value=False):
            orchestrator.resume_instance("c", sess)
            start.assert_not_called()
            sess["awdax_run"] = {"status": "failed"}
            orchestrator.resume_instance("c", sess)
            start.assert_called_once()


class LocationRouteTests(unittest.TestCase):
    SECRET = "route-test-secret-route-test-secret-1234567890"
    PROXY = "proxy-secret"

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        patch.start()
        self.addCleanup(patch.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        env = mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": self.SECRET, "PROXY_SHARED_SECRET": self.PROXY}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._dir.cleanup)
        import app as app_module

        self.client = app_module.app.test_client()

    def _chat(self, headers):
        return self.client.post("/api/instances", json={}, headers=headers).get_json()["id"]

    def _send(self, headers, body, extra=None):
        iid = self._chat(headers)
        with mock.patch("awdax_api.routes.submit_run") as start:
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "cafes near me", **body}, headers={**headers, **(extra or {})})
        return iid, r, start

    @property
    def _jwt(self):
        return {"Authorization": "Bearer " + jwt.encode({"sub": "u1", "app_metadata": {"provider": "google"}}, self.SECRET, algorithm="HS256")}

    @property
    def _proxy(self):
        return {"X-User-Id": "u1", "X-Proxy-Secret": self.PROXY}

    def test_a_browser_position_is_passed_to_the_run(self):
        _, r, start = self._send(self._jwt, {"location": {"lat": 28.6, "lng": 77.2}})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(start.call_args.kwargs["location_hint"], {"lat": 28.6, "lng": 77.2, "source": "browser"})

    def test_no_position_passes_no_hint(self):
        _, r, start = self._send(self._jwt, {})
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("location_hint", start.call_args.kwargs)

    def test_a_bad_position_is_a_400_with_no_side_effects(self):
        for bad in ("here", {"lat": "x", "lng": 1}, {"lat": 91, "lng": 0}, {"lat": 0, "lng": 181}, {"lat": True, "lng": 0}, {"lat": float("nan"), "lng": 0}, {"lat": 1}):
            iid, r, start = self._send(self._jwt, {"location": bad})
            self.assertEqual(r.status_code, 400, repr(bad))
            start.assert_not_called()
            self.assertEqual(self.client.get(f"/api/instances/{iid}/messages", headers=self._jwt).get_json(), [])

    def test_a_position_sent_as_a_header_is_never_trusted(self):
        geo = {"X-Awdax-Geo-Lat": "19.07", "X-Awdax-Geo-Lng": "72.87"}
        for headers in (self._jwt, self._proxy):
            _, r, start = self._send(headers, {}, geo)  # anyone could have typed these
            self.assertEqual(r.status_code, 201)
            self.assertNotIn("location_hint", start.call_args.kwargs)

    def test_the_browsers_position_is_used_whatever_headers_say(self):
        geo = {"X-Awdax-Geo-Lat": "19.07", "X-Awdax-Geo-Lng": "72.87"}
        _, _, start = self._send(self._jwt, {"location": {"lat": 28.6, "lng": 77.2}}, geo)
        self.assertEqual(start.call_args.kwargs["location_hint"], {"lat": 28.6, "lng": 77.2, "source": "browser"})


if __name__ == "__main__":
    unittest.main()
