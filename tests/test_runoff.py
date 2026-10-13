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
        self.curated["polls"] = [p for p in self.curated["polls"] if p["id"] in {"BR-02949/2026", "BR-08134/2026", "BR-00933/2026"}]
        self.today = date(2026, 10, 12)

    def test_only_post_first_round_finalists_and_deduplicates_registration(self):
        source = {"runoff": [
            {"date": "2026-10-03", "institute": "Antiga", "sample": 2000,
             "registration": "BR-OLD/2026", "candidates": {"lula": 48, "flavio-bolsonaro": 45}},
            {"date": "2026-10-08", "fieldworkStart": "2026-10-06", "institute": "Outra", "sample": 1200,
             "registration": "BR-NEW/2026", "candidates": {"lula": 45, "flavio-bolsonaro": 48}},
            {"date": "2026-10-07", "institute": "Datafolha", "sample": 2520,
             "registration": "BR-02949/2026", "candidates": {"lula": 45, "flavio-bolsonaro": 49}},
            {"date": "2026-10-08", "institute": "Incorreta", "sample": 1100,
             "registration": "BR-OTHER/2026", "candidates": {"lula": 40, "romeu-zema": 40}},
        ]}
        result = build_payload(self.curated, source, "2026-10-09T09:00:00Z", self.today)
        self.assertEqual(result["pollCount"], 4)
        self.assertEqual({p["registration"] for p in result["polls"]},
                         {"BR-02949/2026", "BR-08134/2026", "BR-00933/2026", "BR-NEW/2026"})
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

class RunoffReliabilityTest(unittest.TestCase):
    def setUp(self):
        from scripts import update_runoff
        self.pipeline = update_runoff
        self.curated = json.loads((ROOT / "data/runoff-curated.json").read_text("utf-8"))
        self.curated["polls"] = [p for p in self.curated["polls"] if p["id"] in {"BR-02949/2026", "BR-08134/2026", "BR-00933/2026"}]
        self.today = date(2026, 10, 12)
        self.stamp = "2026-10-13T00:00:00Z"

    def build(self, **kwargs):
        return build_payload(self.curated, {"runoff": []}, self.stamp, self.today, **kwargs)

    def test_sync_without_new_evidence_preserves_revision_and_data_timestamp(self):
        first = self.build()
        second = build_payload(self.curated, {"runoff": []}, "2026-10-13T00:15:00Z", self.today, previous=first)
        self.assertEqual(first["pollRevision"], second["pollRevision"])
        self.assertEqual(first["generatedAt"], second["generatedAt"])
        self.assertNotEqual(first["checkedAt"], second["checkedAt"])

    def test_partial_source_failure_keeps_confirmed_polls_and_history(self):
        first = self.build()
        empty_curated = {**self.curated, "polls": []}
        second = build_payload(empty_curated, {}, self.stamp, self.today, previous=first)
        self.assertEqual(first["pollRevision"], second["pollRevision"])
        self.assertEqual(first["history"], second["history"])

    def test_model_uses_published_valid_votes_not_average_of_raw_bases(self):
        payload = self.build()
        model = payload["model"]
        self.assertEqual(model["status"], "ok")
        self.assertAlmostEqual(sum(model["support"].values()), 100)
        self.assertAlmostEqual(sum(model["winProbability"].values()), 100)
        self.assertTrue(52 <= model["support"]["flavio-bolsonaro"] <= 53)
        self.assertFalse(model["calibrated"])
        self.assertGreaterEqual(model["sigma"], 3)
        for cid in model["support"]:
            self.assertLessEqual(model["intervals"][cid][0], model["support"][cid])
            self.assertGreaterEqual(model["intervals"][cid][1], model["support"][cid])

    def test_history_does_not_leak_future_publications(self):
        history = self.build()["history"]
        self.assertEqual([p["date"] for p in history], ["2026-10-08", "2026-10-10"])
        self.assertEqual([p["instituteCount"] for p in history], [2, 3])
        self.assertTrue(52 <= history[0]["support"]["flavio-bolsonaro"] <= 53)

    def test_latest_per_institute_and_unknown_basis_excluded(self):
        first = self.build()
        duplicate = copy.deepcopy(first["polls"][0])
        duplicate["id"] = "earlier-same-institute"
        duplicate["fieldworkStart"] = "2026-10-05"
        duplicate["fieldworkEnd"] = "2026-10-06"
        duplicate["result"] = {"flavio-bolsonaro": 60, "lula": 40}
        duplicate["validResult"] = {}
        duplicate["basis"] = "valid"
        unknown = {**duplicate, "id": "unknown", "instituteKey": "unknown", "basis": "unspecified"}
        model = self.pipeline.estimate(first["polls"] + [duplicate, unknown], self.today)
        self.assertEqual(model["instituteCount"], 3)
        self.assertNotIn("earlier-same-institute", {r["pollId"] for r in model["rows"]})
        self.assertNotIn("unknown", {r["pollId"] for r in model["rows"]})

    def test_old_or_single_institute_model_is_unavailable(self):
        payload = self.build()
        self.assertEqual(self.pipeline.estimate(payload["polls"][:1], self.today)["status"], "insufficient-data")
        self.assertEqual(self.pipeline.estimate(payload["polls"], date(2026, 10, 24))["status"], "insufficient-data")
        self.assertEqual(self.pipeline.estimate(payload["polls"], date(2026, 10, 26))["status"], "insufficient-data")

    def test_entire_fieldwork_must_be_after_first_round(self):
        bad = copy.deepcopy(self.curated)
        bad["polls"][0]["fieldworkStart"] = "2026-10-03"
        with self.assertRaises(ValueError):
            build_payload(bad, {}, self.stamp, self.today)

    def test_future_publication_and_nan_rejected(self):
        for field, value in [("publishedAt", "2026-10-14"), ("result", {"lula": float("nan"), "flavio-bolsonaro": 49})]:
            bad = copy.deepcopy(self.curated)
            bad["polls"][0][field] = value
            with self.assertRaises(ValueError):
                build_payload(bad, {}, self.stamp, self.today)

    def test_conditional_total_conversion_documented(self):
        payload = self.build()
        poll = {**payload["polls"][0], "basis": "total", "validResult": {},
                "result": {"flavio-bolsonaro": 48, "lula": 42}}
        values, origin = self.pipeline.analytic_values(poll)
        self.assertAlmostEqual(values["flavio-bolsonaro"], 48 / 90 * 100)
        self.assertIn("calculados", origin)

    def test_market_is_separate_and_stale_quotes_are_rejected(self):
        from datetime import datetime, timezone
        first = self.build()
        changed = self.build(market={"status": "ok", "values": {"lula": 60, "flavio-bolsonaro": 40}})
        self.assertEqual(first["model"], changed["model"])
        stale = {"active": True, "markets": [
            {"groupItemTitle": "Flávio Bolsonaro", "outcomes": ["Yes", "No"], "outcomePrices": ["0.7", "0.3"], "updatedAt": "2026-10-01T12:00:00Z"},
            {"groupItemTitle": "Lula", "outcomes": ["Yes", "No"], "outcomePrices": ["0.3", "0.7"], "updatedAt": "2026-10-01T12:00:00Z"}]}
        with self.assertRaises(ValueError):
            self.pipeline.parse_market(stale, datetime(2026, 10, 12, tzinfo=timezone.utc))

    def test_bbc_imports_only_post_vote_finalists_with_full_period(self):
        html = """<table><tr><th>Instituto</th><th>Flávio Bolsonaro</th><th>Lula</th></tr>
        <tr><td>06/10 - 08/10 Outra 2.000 Presencial 2 p.p. BR-10001/2026</td><td>49%</td><td>45%</td></tr>
        <tr><td>03/10 - 08/10 Outra 2.000 Presencial 2 p.p. BR-10002/2026</td><td>49%</td><td>45%</td></tr>
        </table>"""
        rows = self.pipeline.parse_bbc_runoff(html, self.today)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["basis"], "unspecified")
        self.assertIsNone(rows[0]["publishedAt"])
        self.assertEqual(rows[0]["fieldworkStart"], "2026-10-06")


if __name__ == "__main__":
    unittest.main()
