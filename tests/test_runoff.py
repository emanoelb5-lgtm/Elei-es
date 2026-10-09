import copy
import json
import unittest
from datetime import date
from pathlib import Path

from scripts.update_runoff import build_payload


ROOT = Path(__file__).resolve().parents[1]


class RunoffPayloadTest(unittest.TestCase):
    def setUp(self):
        self.curated = json.loads((ROOT / "data/runoff-curated.json").read_text("utf-8"))
        self.today = date(2026, 10, 9)

    def test_only_post_first_round_finalists_and_deduplicates_registration(self):
        source = {"runoff": [
            {"date": "2026-10-03", "institute": "Antiga", "sample": 2000,
             "registration": "BR-OLD/2026", "candidates": {"lula": 48, "flavio-bolsonaro": 45}},
            {"date": "2026-10-08", "institute": "Outra", "sample": 1200,
             "registration": "BR-NEW/2026", "candidates": {"lula": 45, "flavio-bolsonaro": 48}},
            {"date": "2026-10-07", "institute": "Datafolha", "sample": 2520,
             "registration": "BR-02949/2026", "candidates": {"lula": 45, "flavio-bolsonaro": 49}},
            {"date": "2026-10-08", "institute": "Incorreta", "sample": 1100,
             "registration": "BR-OTHER/2026", "candidates": {"lula": 40, "romeu-zema": 40}},
        ]}
        result = build_payload(self.curated, source, "2026-10-09T09:00:00Z", self.today)
        self.assertEqual(result["pollCount"], 3)
        self.assertEqual({p["registration"] for p in result["polls"]},
                         {"BR-02949/2026", "BR-08134/2026", "BR-NEW/2026"})
        self.assertTrue(all(p["fieldworkEnd"] >= "2026-10-05" for p in result["polls"]))
        self.assertEqual(next(p for p in result["polls"] if p["registration"] == "BR-NEW/2026")["basis"], "unspecified")
        self.assertNotIn("aggregate", result)

    def test_curated_percent_bases_remain_distinct(self):
        result = build_payload(self.curated, {"runoff": []}, "2026-10-09T09:00:00Z", self.today)
        by_id = {p["id"]: p for p in result["polls"]}
        self.assertEqual(by_id["BR-02949/2026"]["result"]["flavio-bolsonaro"], 49)
        self.assertEqual(by_id["BR-02949/2026"]["validResult"]["flavio-bolsonaro"], 52)
        self.assertEqual(by_id["BR-08134/2026"]["basis"], "valid")
        self.assertEqual(result["electionDate"], "2026-10-25")

    def test_rejects_curated_poll_from_before_the_vote(self):
        bad = copy.deepcopy(self.curated)
        bad["polls"][0]["fieldworkEnd"] = "2026-10-03"
        with self.assertRaises(ValueError):
            build_payload(bad, {"runoff": []}, "2026-10-09T09:00:00Z", self.today)


if __name__ == "__main__":
    unittest.main()
