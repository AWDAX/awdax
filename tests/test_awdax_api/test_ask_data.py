"""Ask about this data: the model's plan is held to this table's guardrails, heavy maths runs sandboxed and the
function never reaches the browser. The model is stubbed: these tests are about what happens to its reply."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from ask_data import AskError, answer_question  # noqa: E402

COLUMNS = [
    {"index": 0, "key": "brand", "label": "Brand", "kind": "category"},
    {"index": 1, "key": "price_inr", "label": "Price (INR)", "kind": "money"},
    {"index": 2, "key": "range_km", "label": "Range (km)", "kind": "number"},
]
ROWS = [
    {"brand": "Tata", "price_inr": 1500000.0, "range_km": 315.0},
    {"brand": "MG", "price_inr": 1800000.0, "range_km": 461.0},
    {"brand": "Tata", "price_inr": 1100000.0, "range_km": 250.0},
]


def reply(plan):
    return mock.patch("ask_data.llm_json", return_value=plan)


class PlanGuardrailTests(unittest.TestCase):
    def test_a_valid_query_comes_back_trimmed_to_what_the_engine_reads(self):
        plan = {"kind": "query", "query": {"groupBy": 0, "measure": 1, "agg": "max", "sort": "value-desc", "limit": 3, "extra": "x"}}
        with reply(plan):
            out = answer_question("highest price by brand", COLUMNS, ROWS)
        self.assertEqual(out, {"kind": "query", "query": {"agg": "max", "groupBy": 0, "measure": 1, "filters": [], "sort": "value-desc", "limit": 3}})

    def test_adding_up_a_text_column_is_refused(self):
        with reply({"kind": "query", "query": {"measure": 0, "agg": "sum"}}), self.assertRaises(AskError) as cm:
            answer_question("total brand", COLUMNS, ROWS)
        self.assertIn("isn't a number", str(cm.exception))

    def test_a_column_the_table_does_not_have_is_refused(self):
        for q in ({"groupBy": 7, "agg": "count"}, {"agg": "count", "filters": [{"column": 9, "op": "in", "values": ["x"]}]}, {"groupBy": True, "agg": "count"}):
            with self.subTest(q=q), reply({"kind": "query", "query": q}), self.assertRaises(AskError):
                answer_question("q", COLUMNS, ROWS)

    def test_a_column_named_by_key_or_label_resolves_to_its_index(self):
        plan = {"kind": "query", "query": {"groupBy": "Brand", "measure": "price_inr", "agg": "max", "filters": [{"column": "2", "op": "gte", "values": [300]}]}}
        with reply(plan):
            q = answer_question("highest price by brand", COLUMNS, ROWS)["query"]
        self.assertEqual((q["groupBy"], q["measure"], q["filters"][0]["column"], q["filters"][0]["values"]), (0, 1, 2, ["300"]))

    def test_numeric_comparisons_only_on_number_columns(self):
        plan = {"kind": "query", "query": {"agg": "count", "filters": [{"column": 0, "op": "gte", "values": ["5"]}]}}
        with reply(plan), self.assertRaises(AskError):
            answer_question("brands above 5", COLUMNS, ROWS)

    def test_refusal_passes_through(self):
        with reply({"kind": "refuse", "reason": "This table has no sales figures."}):
            self.assertEqual(answer_question("sales in 2019", COLUMNS, ROWS), {"kind": "refuse", "reason": "This table has no sales figures."})

    def test_model_down_gives_a_plain_message(self):
        with mock.patch("ask_data.llm_json", side_effect=RuntimeError("NVIDIA request failed (secret detail)")), self.assertRaises(AskError) as cm:
            answer_question("anything", COLUMNS, ROWS)
        self.assertNotIn("secret", str(cm.exception))


class ComputeTests(unittest.TestCase):
    FUNCTION = (
        "def answer(rows):\n"
        "    by = {}\n"
        "    for r in rows:\n"
        "        by.setdefault(r['brand'], []).append(r['price_inr'] / r['range_km'])\n"
        "    return [{'Brand': b, 'Rupees per km': round(statistics.mean(v), 2)} for b, v in sorted(by.items())]\n"
    )

    def test_heavy_maths_runs_sandboxed_and_the_function_never_leaves(self):
        plan = {"kind": "compute", "function": self.FUNCTION, "columns": [{"name": "Brand", "type": "text"}, {"name": "Rupees per km", "type": "money"}], "meaning": "Average price per km of range, by brand."}
        with reply(plan):
            out = answer_question("price per km of range by brand", COLUMNS, ROWS)
        self.assertEqual(out["columns"], [{"name": "Brand", "type": "text"}, {"name": "Rupees per km", "type": "money"}])
        self.assertEqual(out["rows"], [["MG", 3904.56], ["Tata", 4580.95]])
        self.assertEqual(out["meaning"], "Average price per km of range, by brand.")
        self.assertNotIn("def answer", json.dumps(out))

    def test_unsafe_generated_code_is_refused_without_running(self):
        plan = {"kind": "compute", "function": "def answer(rows):\n    return ().__class__.__bases__\n", "columns": [], "meaning": ""}
        with reply(plan), mock.patch("ask_sandbox.subprocess.Popen") as spawn, self.assertRaises(AskError) as cm:
            answer_question("anything", COLUMNS, ROWS)
        spawn.assert_not_called()
        self.assertIn("safely", str(cm.exception))

    def test_a_single_number_becomes_a_one_cell_table(self):
        plan = {"kind": "compute", "function": "def answer(rows):\n    return len(rows)\n", "columns": [{"name": "Cars", "type": "number"}], "meaning": "3 cars."}
        with reply(plan):
            out = answer_question("how many cars", COLUMNS, ROWS)
        self.assertEqual((out["columns"], out["rows"]), ([{"name": "Cars", "type": "number"}], [[3]]))


class AskRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_route_answers_and_turns_guardrail_refusals_into_a_refuse_answer(self):
        body = {"question": "highest price by brand", "columns": COLUMNS, "rows": ROWS}
        with reply({"kind": "query", "query": {"groupBy": 0, "measure": 1, "agg": "max"}}):
            ok = self.client.post("/api/ask", json=body)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["kind"], "query")
        with reply({"kind": "query", "query": {"measure": 0, "agg": "sum"}}):
            bad = self.client.post("/api/ask", json=body)
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.get_json()["kind"], "refuse")
        self.assertIn("isn't a number", bad.get_json()["reason"])

    def test_model_down_is_503_so_the_browser_falls_back(self):
        body = {"question": "anything", "columns": COLUMNS, "rows": ROWS}
        with mock.patch("ask_data.llm_json", side_effect=RuntimeError("down")):
            self.assertEqual(self.client.post("/api/ask", json=body).status_code, 503)

    def test_an_oversized_body_is_refused_before_parsing(self):
        with mock.patch("awdax_api.ask_routes.MAX_BODY", 1000), mock.patch("ask_data.llm_json") as llm:
            res = self.client.post("/api/ask", json={"question": "x", "columns": COLUMNS, "rows": ROWS * 50})
        self.assertEqual(res.status_code, 413)
        llm.assert_not_called()

    def test_each_user_has_a_question_budget(self):
        body = {"question": "highest price by brand", "columns": COLUMNS, "rows": ROWS}
        with mock.patch("awdax_api.ask_routes.ASKS_PER_WINDOW", 1), mock.patch.dict("awdax_api.ask_routes._recent", clear=True), reply({"kind": "query", "query": {"agg": "count"}}):
            first = self.client.post("/api/ask", json=body, headers={"X-User-Id": "budget-test"})
            second = self.client.post("/api/ask", json=body, headers={"X-User-Id": "budget-test"})
        self.assertEqual((first.status_code, second.status_code), (200, 429))

    def test_malformed_body_is_400(self):
        self.assertEqual(self.client.post("/api/ask", json={"question": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/ask", json={"question": "x", "columns": [{"key": "a"}], "rows": []}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
