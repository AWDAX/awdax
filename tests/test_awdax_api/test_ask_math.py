"""Phase 5: questions about a table get exact answers. The expected figures come from tests/fixtures/ask_math.json, which is
computed independently of the engines (make_ask_math.py) and is also checked against the browser engine."""
import json
import os
import statistics
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402

import ask_fastpath  # noqa: E402
import ui_sessions  # noqa: E402
from ask_data import check_query  # noqa: E402
from column_kinds import ask_payload, parse_number, profile_table  # noqa: E402
from query_engine import json_number, run_query  # noqa: E402

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "ask_math.json").read_text(encoding="utf-8"))
COLUMNS, ROWS = FIXTURE["columns"], FIXTURE["rows"]
TYPED = profile_table(COLUMNS, ROWS)
COLS, TABLE_ROWS = ask_payload(TYPED)
INDEX = {c["key"]: c["index"] for c in COLS}
SECRET = "ask-math-test-secret-ask-math-test-secret-1234567890"


def engine_plan(plan):
    """A fixture plan (columns by name) as the checked plan the engine takes (columns by index)."""
    out = {k: v for k, v in plan.items() if k not in ("groupBy", "measure", "filters")}
    for key in ("groupBy", "measure"):
        if key in plan:
            out[key] = INDEX[plan[key]]
    if "filters" in plan:
        out["filters"] = [{**f, **({"column": INDEX[f["column"]]} if "column" in f else {})} for f in plan["filters"]]
    return check_query(out, COLS)


def close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) < 1e-9)


class ReadingTests(unittest.TestCase):
    def test_columns_are_read_as_what_they_are(self):
        kinds = {c.name: c.kind for c in TYPED.columns}
        self.assertEqual(
            kinds,
            {"name": "text", "category": "category", "price": "money", "range_km": "number", "rating": "number",
             "reviews": "number", "discount": "percent", "website": "url", "phone": "text"},
        )
        self.assertEqual(TYPED.columns[INDEX["price"]].currency, "INR")
        self.assertEqual(TYPED.columns[INDEX["range_km"]].suffix, "km")

    def test_indian_money_and_scale_words_are_exact(self):
        for text, value in (("₹12.5 Lakh", "1250000"), ("₹8,50,000", "850000"), ("₹1.2 Crore", "12000000"), ("₹9.99 Lakh", "999000"),
                            ("Rs. 4,75,000", "475000"), ("1,44,879", "144879"), ("(1,200)", "-1200"), ("18.4%", "18.4"), ("₹11 – ₹15 Lakh", "1100000"),
                            ("24.99 - 34.49 Lakh", "2499000"), ("450 km", "450"), ("2.5k", "2500"), ("1.5 M", "1500000")):
            parsed = parse_number(text)
            self.assertIsNotNone(parsed, text)
            self.assertEqual(parsed.value, Decimal(value), text)

    def test_missing_and_unreadable_are_never_zero(self):
        for text in ("N/A", "—", "", "n/a", "TBD", "Contact us", "call for price", "12abc34", "1,23", "up to 500", "10 and above"):
            self.assertIsNone(parse_number(text), text)

    def test_a_range_counts_at_its_low_end_and_is_flagged(self):
        price = TYPED.columns[INDEX["price"]]
        self.assertEqual(price.numbers[3], Decimal(1100000))
        self.assertEqual([i for i, r in enumerate(price.ranged or []) if r], FIXTURE["ranged_price_rows"])
        self.assertEqual({i: price.labels[i] for i in price.excluded}, {8: "Contact us"})

    def test_ask_payload_gives_floats_and_text(self):
        row = TABLE_ROWS[0]
        self.assertEqual((row["price"], row["reviews"], row["rating"], row["category"]), (1250000.0, 1204.0, 4.5, "Cafe"))
        self.assertIsNone(TABLE_ROWS[4]["rating"])  # "N/A"
        self.assertEqual(COLS[INDEX["price"]]["unit"], "INR")


class EngineGoldenTests(unittest.TestCase):
    def test_every_case_matches_the_independent_answer(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case["question"]):
                result = run_query(TYPED, engine_plan(case["plan"]))
                want = case["expect"]
                self.assertEqual([r[0] for r in result["rows"]], [r[0] for r in want["rows"]], "groups and their order")
                for got, exp in zip(result["rows"], want["rows"]):
                    self.assertTrue(close(got[1], exp[1]), f"{got} != {exp}")
                    self.assertEqual(got[2], exp[2], "rows in the group")
                self.assertTrue(close(result["overall"], want["overall"]), (result["overall"], want["overall"]))
                self.assertEqual((result["used"], result["matched"]), (want["used"], want["matched"]))

    def test_cells_that_are_not_numbers_are_reported_not_counted_as_zero(self):
        result = run_query(TYPED, engine_plan({"agg": "sum", "measure": "price"}))
        self.assertEqual(result["excluded_count"], 1)
        self.assertEqual(result["excluded"][0]["value"], "Contact us")
        self.assertEqual(result["blank"], 2)  # "N/A" and "—": missing, not unreadable
        self.assertEqual(result["ranged"], 1)
        self.assertEqual(result["used"], 27)

    def test_money_is_exact_to_the_last_rupee(self):
        total = run_query(TYPED, engine_plan({"agg": "sum", "measure": "price"}))["rows"][0][1]
        self.assertEqual(total, 73493999)
        self.assertIsInstance(total, int)

    def test_averages_round_half_to_even_two_places_past_the_source(self):
        self.assertEqual(run_query(TYPED, engine_plan({"agg": "avg", "measure": "rating"}))["overall"], 4.231)

    def test_a_filter_that_matches_nothing_is_an_empty_answer_not_an_error(self):
        result = run_query(TYPED, engine_plan({"agg": "avg", "measure": "rating", "filters": [{"column": "rating", "op": "gte", "values": ["99"]}]}))
        self.assertEqual((result["rows"], result["overall"], result["used"]), ([], None, 0))

    def test_json_number_keeps_whole_numbers_whole(self):
        self.assertEqual((json_number(Decimal("5.0")), json_number(Decimal("2.5")), json_number(None)), (5, 2.5, None))


class FastPathTests(unittest.TestCase):
    def plan(self, question):
        return ask_fastpath.plan(question, COLS)

    def test_plain_questions_are_planned(self):
        cases = {
            "how many rows are there?": {"agg": "count"},
            "How many records do we have": {"agg": "count"},
            "total number of rows": {"agg": "count"},
            "what is the average rating?": {"agg": "avg", "measure": INDEX["rating"]},
            "Average price": {"agg": "avg", "measure": INDEX["price"]},
            "mean reviews": {"agg": "avg", "measure": INDEX["reviews"]},
            "total reviews": {"agg": "sum", "measure": INDEX["reviews"]},
            "sum of reviews by category": {"agg": "sum", "measure": INDEX["reviews"], "groupBy": INDEX["category"], "sort": "value-desc"},
            "highest price": {"agg": "max", "measure": INDEX["price"]},
            "lowest rating": {"agg": "min", "measure": INDEX["rating"]},
            "median reviews": {"agg": "median", "measure": INDEX["reviews"]},
            "average price for each category": {"agg": "avg", "measure": INDEX["price"], "groupBy": INDEX["category"], "sort": "value-desc"},
            "count by category": {"agg": "count", "groupBy": INDEX["category"]},
            "how many per category": {"agg": "count", "groupBy": INDEX["category"]},
            "top 3 by reviews": {"agg": "max", "measure": INDEX["reviews"], "groupBy": INDEX["name"], "sort": "value-desc", "limit": 3},
            "bottom 2 by rating": {"agg": "min", "measure": INDEX["rating"], "groupBy": INDEX["name"], "sort": "value-asc", "limit": 2},
        }
        for question, query in cases.items():
            with self.subTest(question):
                got = self.plan(question)
                self.assertEqual(got, {"kind": "query", "query": query})

    def test_anything_with_a_filter_a_comparison_or_unknown_words_is_left_to_the_ai(self):
        for question in (
            "average rating of cafes", "average rating in Noida", "how many have a website", "how many places are rated above 4",
            "average rating where reviews over 100", "which place has the highest rating", "highest and lowest price", "average price per km",
            "growth in reviews", "average rating 2024", "percentage of places with a website", "average", "price", "how many cars",
            "top 5 cafes by rating", "average rating, then total reviews", "average colour", "", "x" * 300,
        ):
            with self.subTest(question):
                self.assertIsNone(self.plan(question))

    def test_a_name_that_could_be_two_columns_is_not_guessed(self):
        cols = [
            {"index": 0, "key": "name", "label": "Name", "kind": "text", "unit": ""},
            {"index": 1, "key": "rating", "label": "Rating", "kind": "number", "unit": ""},
            {"index": 2, "key": "rating_count", "label": "Rating", "kind": "number", "unit": ""},
        ]
        self.assertIsNone(ask_fastpath.plan("average rating", cols))
        self.assertIsNone(ask_fastpath.plan("average rating", []))

    def test_a_text_column_cannot_be_averaged(self):
        self.assertIsNone(self.plan("average category"))
        self.assertIsNone(self.plan("total website"))

    def test_every_plan_it_makes_passes_the_same_guardrail_as_the_models(self):
        for question in ("average rating by category", "top 3 by reviews", "count by category", "how many rows"):
            check_query(self.plan(question)["query"], COLS)


class _Base(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        patch.start()
        self.addCleanup(patch.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        env = mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": SECRET, "AWDAX_AUTH_MODE": "strict", "PROXY_SHARED_SECRET": ""})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._dir.cleanup)
        import app as app_module
        from awdax_api import ask_routes

        ask_routes._recent.clear()
        self.addCleanup(ask_routes._recent.clear)
        self.client = app_module.app.test_client()
        table = {"columns": COLUMNS, "column_labels": [c.label for c in TYPED.columns], "rows": ROWS, "row_count": len(ROWS), "records": []}
        patch = mock.patch("awdax_api.ask_routes.build_dataset_table", return_value=table)
        self.table = patch.start()
        self.addCleanup(patch.stop)
        self.chat = self.client.post("/api/instances", json={}, headers=self.auth("alice")).get_json()["id"]

    @staticmethod
    def auth(sub):
        return {"Authorization": "Bearer " + jwt.encode({"sub": sub}, SECRET, algorithm="HS256")}

    def ask(self, question, sub="alice", chat=None):
        return self.client.post(f"/api/instances/{chat or self.chat}/ask", json={"question": question}, headers=self.auth(sub))

    def case(self, question):
        return next(c for c in FIXTURE["cases"] if c["question"] == question)

    def model(self, reply):
        return mock.patch("ask_data.llm_json", return_value=reply)

    def no_model(self):
        return mock.patch("ask_data.llm_json", side_effect=AssertionError("the model must not be asked"))


class EndpointFastTests(_Base):
    def test_plain_questions_get_the_exact_answer_without_the_model(self):
        for question, case in (
            ("how many rows are there?", "how many rows"), ("what is the average rating?", "average rating"), ("total reviews", "total reviews"),
            ("highest price", "highest price"), ("lowest price", "lowest price"), ("median rating", "median rating"),
            ("average discount", "average discount"), ("average price by category", "average price by category"),
            ("count by category", "count by category"), ("top 3 by reviews", "top 3 by reviews"), ("bottom 2 by rating", "bottom 2 by rating"),
        ):
            with self.subTest(question), self.no_model():
                r = self.ask(question)
                self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
                data, want = r.get_json(), self.case(case)["expect"]
                self.assertEqual((data["kind"], data["source"]), ("answer", "fast"))
                self.assertEqual([x[0] for x in data["rows"]], [x[0] for x in want["rows"]])
                for got, exp in zip(data["rows"], want["rows"]):
                    self.assertTrue(close(got[1], exp[1]), (question, got, exp))
                self.assertTrue(close(data["overall"], want["overall"]))
                self.assertTrue(data["meaning"].endswith("."))

    def test_the_answer_says_what_was_calculated_and_what_was_left_out(self):
        with self.no_model():
            data = self.ask("total price").get_json()
        self.assertEqual(data["excluded_count"], 1)
        self.assertEqual(data["excluded"][0]["value"], "Contact us")
        self.assertIn("1 cell(s) that are not numbers were left out", data["meaning"])
        self.assertIn("the total of Price", data["meaning"].lower().replace("the total of price", "the total of Price"))
        self.assertEqual((data["used"], data["matched"]), (27, 30))
        self.assertEqual(data["unit"], "INR")

    def test_plain_questions_do_not_use_up_the_question_budget(self):
        with mock.patch("awdax_api.ask_routes.ASKS_PER_WINDOW", 1), self.no_model():
            for _ in range(5):
                self.assertEqual(self.ask("average rating").status_code, 200)


class EndpointModelTests(_Base):
    def test_a_model_plan_is_run_exactly(self):
        plan = {"kind": "query", "query": {"agg": "avg", "measure": INDEX["rating"], "filters": [
            {"column": INDEX["category"], "op": "in", "values": ["Cafe", "Gym"]}, {"column": INDEX["website"], "op": "present", "values": []}]}}
        with self.model(plan):
            data = self.ask("average rating of cafes and gyms that have a website").get_json()
        rows = [i for i in range(30) if ROWS[i][1] in ("Cafe", "Gym") and ROWS[i][7] and ROWS[i][4] != "N/A"]
        expected = Decimal(sum(Decimal(ROWS[i][4]) for i in rows)) / len(rows)
        self.assertEqual((data["kind"], data["source"]), ("answer", "plan"))
        self.assertAlmostEqual(data["rows"][0][1], float(round(expected, 3)), places=9)
        self.assertEqual(data["used"], len(rows))

    def test_a_plan_that_breaks_the_guardrails_is_a_refusal_that_says_why(self):
        bad = {"kind": "query", "query": {"agg": "sum", "measure": INDEX["category"]}}
        with self.model(bad):
            data = self.ask("sum the categories").get_json()
        self.assertEqual(data["kind"], "refuse")
        self.assertIn("isn't a number", data["reason"])

    def test_the_model_refusing_is_passed_on(self):
        with self.model({"kind": "refuse", "reason": "The table has no weather."}):
            self.assertEqual(self.ask("will it rain?").get_json(), {"kind": "refuse", "reason": "The table has no weather."})

    def test_a_model_that_is_down_is_a_503_but_plain_questions_still_work(self):
        with mock.patch("ask_data.llm_json", side_effect=RuntimeError("down")):
            r = self.ask("what is the market share of cafes?")
            self.assertEqual(r.status_code, 503)
            self.assertIn("couldn't be reached", r.get_json()["detail"])
            self.assertEqual(self.ask("average rating").status_code, 200)

    def test_model_questions_are_budgeted_per_account(self):
        reply = {"kind": "query", "query": {"agg": "count"}}
        with mock.patch("awdax_api.ask_routes.ASKS_PER_WINDOW", 2), self.model(reply):
            codes = [self.ask("something only the model reads").status_code for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])
            other = self.client.post("/api/instances", json={}, headers=self.auth("bob")).get_json()["id"]
            self.assertEqual(self.ask("something only the model reads", sub="bob", chat=other).status_code, 200)

    def test_bad_requests(self):
        for body in ({}, {"question": ""}, {"question": "  "}, {"question": "x" * 501}):
            r = self.client.post(f"/api/instances/{self.chat}/ask", json=body, headers=self.auth("alice"))
            self.assertEqual(r.status_code, 400, body)

    def test_an_empty_chat_is_a_refusal_not_an_error(self):
        self.table.return_value = None
        data = self.ask("average rating").get_json()
        self.assertEqual(data["kind"], "refuse")
        self.assertIn("no data yet", data["reason"])

    def test_another_account_cannot_ask_about_this_chat_and_strangers_are_refused(self):
        self.assertEqual(self.ask("average rating", sub="bob").status_code, 404)
        self.assertEqual(self.client.post(f"/api/instances/{self.chat}/ask", json={"question": "average rating"}).status_code, 401)


class CalculationTests(_Base):
    """Heavier maths runs as a short function in the sandbox over every row; the answer must be the exact figure."""

    def run_function(self, source, columns, meaning="m"):
        reply = {"kind": "compute", "function": source, "columns": columns, "meaning": meaning}
        with self.model(reply):
            r = self.ask("a calculation only the model reads")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual((data["kind"], data["source"]), ("answer", "calculation"), data)
        return data

    def floats(self, key):
        return [r[key] for r in TABLE_ROWS]

    def test_share_of_a_total(self):
        src = "def answer(rows):\n    total = sum(r['reviews'] for r in rows)\n    mine = sum(r['reviews'] for r in rows if r['category'] == 'Cafe')\n    return 100 * mine / total\n"
        data = self.run_function(src, [{"name": "Cafe share of reviews (%)", "type": "percent"}])
        mine = sum(r["reviews"] for r in TABLE_ROWS if r["category"] == "Cafe")
        self.assertAlmostEqual(data["rows"][0][0], 100 * mine / sum(self.floats("reviews")), places=9)

    def test_spread_percentile_correlation_and_trend(self):
        reviews = self.floats("reviews")
        pairs = [(r["rating"], r["reviews"]) for r in TABLE_ROWS if r["rating"] is not None]
        xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
        rated = [r for r in self.floats("rating") if r is not None]
        for src, columns, want in (
            ("def answer(rows):\n    return statistics.stdev([r['rating'] for r in rows if r['rating'] is not None])\n", [{"name": "Rating spread", "type": "number"}], statistics.stdev(rated)),
            ("def answer(rows):\n    return statistics.quantiles([r['reviews'] for r in rows], n=100)[89]\n", [{"name": "90th percentile", "type": "number"}], statistics.quantiles(reviews, n=100)[89]),
            ("def answer(rows):\n    p = [(r['rating'], r['reviews']) for r in rows if r['rating'] is not None]\n    return statistics.correlation([a for a, b in p], [b for a, b in p])\n", [{"name": "Correlation", "type": "number"}], statistics.correlation(xs, ys)),
            ("def answer(rows):\n    p = [(r['rating'], r['reviews']) for r in rows if r['rating'] is not None]\n    return statistics.linear_regression([a for a, b in p], [b for a, b in p]).slope\n", [{"name": "Slope", "type": "number"}], statistics.linear_regression(xs, ys).slope),
        ):
            with self.subTest(columns[0]["name"]):
                self.assertAlmostEqual(self.run_function(src, columns)["rows"][0][0], want, places=9)

    def test_weighted_average_ratio_and_rows_above_average(self):
        rated = [r for r in TABLE_ROWS if r["rating"] is not None]
        weighted = sum(r["rating"] * r["reviews"] for r in rated) / sum(r["reviews"] for r in rated)
        src = "def answer(rows):\n    p = [r for r in rows if r['rating'] is not None]\n    return sum(r['rating'] * r['reviews'] for r in p) / sum(r['reviews'] for r in p)\n"
        self.assertAlmostEqual(self.run_function(src, [{"name": "Rating weighted by reviews", "type": "number"}])["rows"][0][0], weighted, places=9)

        both = [r for r in TABLE_ROWS if r["price"] is not None and r["range_km"]]
        src = "def answer(rows):\n    p = [r for r in rows if r['price'] is not None and r['range_km']]\n    return sum(r['price'] for r in p) / sum(r['range_km'] for r in p)\n"
        self.assertAlmostEqual(self.run_function(src, [{"name": "Rupees per km of range", "type": "money"}])["rows"][0][0], sum(r["price"] for r in both) / sum(r["range_km"] for r in both), places=6)

        mean = statistics.fmean(r["rating"] for r in rated)
        src = "def answer(rows):\n    p = [r['rating'] for r in rows if r['rating'] is not None]\n    m = statistics.fmean(p)\n    return len([x for x in p if x > m])\n"
        self.assertEqual(self.run_function(src, [{"name": "Rows above average", "type": "number"}])["rows"][0][0], len([r for r in rated if r["rating"] > mean]))

    def test_a_table_result_keeps_its_columns_and_rows(self):
        src = "def answer(rows):\n    out = {}\n    for r in rows:\n        out[r['category']] = out.get(r['category'], 0) + r['reviews']\n    return [{'Category': k, 'Reviews': v} for k, v in sorted(out.items())]\n"
        data = self.run_function(src, [{"name": "Category", "type": "text"}, {"name": "Reviews", "type": "number"}], "Reviews per category")
        totals = {}
        for r in TABLE_ROWS:
            totals[r["category"]] = totals.get(r["category"], 0) + r["reviews"]
        self.assertEqual(data["rows"], [[k, v] for k, v in sorted(totals.items())])
        self.assertEqual(data["meaning"], "Reviews per category")

    def test_unsafe_or_broken_code_is_a_refusal_not_a_crash(self):
        for src in ("def answer(rows):\n    import os\n    return 1\n", "def answer(rows):\n    return open('x').read()\n", "def answer(rows):\n    return 1 / 0\n"):
            with self.model({"kind": "compute", "function": src, "columns": [], "meaning": "m"}):
                data = self.ask("a calculation only the model reads").get_json()
            self.assertEqual(data["kind"], "refuse", src)


if __name__ == "__main__":
    unittest.main()
