import unittest
from datetime import date

from scripts.model_lab import VARIANTS, estimate


class ModelLabTests(unittest.TestCase):
    def test_simple_mean_is_equal_weight(self):
        variant = next(v for v in VARIANTS if v["id"] == "simple-mean")
        polls = [
            {"date": date(2026, 9, 1), "institute": "A", "sample": 1000, "values": {"x": 20.0}},
            {"date": date(2026, 9, 2), "institute": "B", "sample": 5000, "values": {"x": 40.0}},
        ]
        result = estimate(polls, date(2026, 9, 2), ["x"], variant, normalize_output=False)
        self.assertAlmostEqual(result["x"], 30.0, places=6)

    def test_current_model_gives_more_weight_to_recent_large_poll(self):
        variant = next(v for v in VARIANTS if v["id"] == "current-v04")
        polls = [
            {"date": date(2026, 8, 24), "institute": "A", "sample": 800, "values": {"x": 20.0}},
            {"date": date(2026, 9, 2), "institute": "B", "sample": 5000, "values": {"x": 40.0}},
        ]
        result = estimate(polls, date(2026, 9, 2), ["x"], variant, normalize_output=False)
        self.assertGreater(result["x"], 30.0)
        self.assertLess(result["x"], 40.0)

    def test_normalization_preserves_total_100(self):
        variant = next(v for v in VARIANTS if v["id"] == "current-v04")
        polls = [
            {
                "date": date(2022, 10, 1),
                "institute": "A",
                "sample": 2000,
                "values": {"a": 45.0, "b": 35.0, "c": 10.0},
            }
        ]
        result = estimate(polls, date(2022, 10, 1), ["a", "b", "c"], variant, normalize_output=True)
        self.assertAlmostEqual(sum(result.values()), 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
