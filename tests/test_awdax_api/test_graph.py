import unittest
from unittest.mock import patch

from awdax_api.sources_stats_graph import graph_charts, graph_parameters


class GraphTests(unittest.TestCase):
    def test_formatted_measures_exclude_identifiers(self):
        table = {
            "columns": ["model", "serial_no", "price_inr", "share_pct", "source_url"],
            "rows": [
                ["A", "1", "₹1,20,000", "18.4%", "https://example.com/a"],
                ["B", "2", "₹95,000", "N/A", "https://example.com/b"],
                ["C", "3", "₹1,10,000", "21.6%", "https://example.com/c"],
            ],
        }
        with patch("awdax_api.sources_stats_graph.build_dataset_table", return_value=table):
            listed = graph_parameters({})["parameters"]
            self.assertEqual({p["name"] for p in listed}, {"price_inr", "share_pct"})
            self.assertEqual({p["name"]: p["points"] for p in listed}, {"price_inr": 3, "share_pct": 2})
            charts = graph_charts({}, ["price_inr", "share_pct", "serial_no"])["charts"]
        self.assertEqual(len(charts), 2)
        self.assertEqual(charts[0]["x"], "model")
        self.assertEqual(charts[0]["type"], "line")
        self.assertEqual([p["value"] for p in charts[0]["series"][0]["points"]], [120000, 95000, 110000])
        self.assertEqual([p["value"] for p in charts[1]["series"][0]["points"]], [18.4, 21.6])

    def test_charging_times_share_one_minute_axis(self):
        table = {
            "columns": ["brand", "charging_time"],
            "rows": [
                ["BMW", "31 min"],
                ["Kia", "10 hour"],
                ["Mahindra", "22 hour 20 min"],
                ["Tata", "1 hour 30 min"],
                ["Volvo", "N/A"],
            ],
        }
        with patch("awdax_api.sources_stats_graph.build_dataset_table", return_value=table):
            listed = graph_parameters({})["parameters"]
            chart = graph_charts({}, ["charging_time"])["charts"][0]
        self.assertEqual(listed[0]["unit"], "min")
        self.assertEqual(listed[0]["points"], 4)
        self.assertEqual(chart["type"], "line")
        self.assertEqual(chart["unit"], "min")
        self.assertEqual([point["value"] for point in chart["series"][0]["points"]], [31, 600, 1340, 90])
        self.assertEqual([point["x"] for point in chart["series"][0]["points"]], ["BMW", "Kia", "Mahindra", "Tata"])


if __name__ == "__main__":
    unittest.main()
