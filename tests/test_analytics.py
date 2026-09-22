# v0.4.1 multi-cycle historical validation.
# v0.4.1: dispara backtest histórico no pipeline completo.
# v0.4 pipeline: inclui calibration.json na publicação.
# Testes determinísticos: sem chamadas de rede.
import unittest
from datetime import date, timedelta

from scripts.update_analytics import (
    parse_metadata,
    dedupe_polls,
    aggregate_first_round,
    build_source_diagnostics,
    rolling_validation,
)


class AnalyticsParserTests(unittest.TestCase):
    def test_compact_metadata_presential(self):
        meta = parse_metadata(
            "08/01-11/01 Quaest 2.004 Presencial (Domiciliar) 2,0p.p. 95%"
        )
        self.assertEqual(meta["institute"], "Quaest")
        self.assertEqual(meta["sample"], 2004)
        self.assertEqual(meta["method"], "Presencial (Domiciliar)")

    def test_compact_metadata_online(self):
        meta = parse_metadata(
            "15/01-20/01 AtlasIntel 5.000 Online 1,0p.p. 95%"
        )
        self.assertEqual(meta["institute"], "AtlasIntel")
        self.assertEqual(meta["sample"], 5000)
        self.assertEqual(meta["method"], "Online")

    def test_large_sample_is_preserved(self):
        meta = parse_metadata(
            "13/03-04/04 Veritá 40.500 Telefonica (IVR) 1,0p.p. 95%"
        )
        self.assertEqual(meta["sample"], 40500)

    def test_dedupe_prefers_more_complete_scenario(self):
        base = {
            "date": date(2026, 9, 20),
            "institute": "Instituto X",
            "sample": 2000,
            "method": "Presencial",
            "registration": "BR-12345/2026",
        }
        polls = [
            {**base, "values": {"lula": 40.0, "flavio-bolsonaro": 35.0}},
            {
                **base,
                "values": {
                    "lula": 40.0,
                    "flavio-bolsonaro": 35.0,
                    "augusto-cury": 6.0,
                    "renan-santos": 3.0,
                },
            },
        ]
        result = dedupe_polls(polls, {"BR-12345/2026"})
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["values"]), 4)
        self.assertTrue(result[0]["verifiedTse"])

    def test_aggregate_reports_real_diversity(self):
        polls = [
            {
                "date": date(2026, 9, 20),
                "institute": "A",
                "sample": 2000,
                "method": "Presencial",
                "registration": "BR-00001/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
            },
            {
                "date": date(2026, 9, 21),
                "institute": "B",
                "sample": 5000,
                "method": "Online",
                "registration": "BR-00002/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0, "flavio-bolsonaro": 36.0},
            },
        ]
        agg = aggregate_first_round(polls, date(2026, 9, 22))
        self.assertEqual(agg["pollCount"], 2)
        self.assertEqual(agg["instituteCount"], 2)
        self.assertEqual(agg["methodCount"], 2)
        self.assertEqual(agg["registrationCount"], 2)
        self.assertIn("lula", agg["candidates"])


    def test_source_diagnostics_use_other_institutes(self):
        polls = [
            {
                "date": date(2026, 9, 10),
                "institute": "A",
                "sample": 2000,
                "method": "Presencial",
                "registration": "BR-10001/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
            },
            {
                "date": date(2026, 9, 11),
                "institute": "B",
                "sample": 2000,
                "method": "Online",
                "registration": "BR-10002/2026",
                "verifiedTse": False,
                "values": {"lula": 42.0, "flavio-bolsonaro": 33.0},
            },
            {
                "date": date(2026, 9, 12),
                "institute": "C",
                "sample": 2000,
                "method": "Telefonica",
                "registration": "BR-10003/2026",
                "verifiedTse": False,
                "values": {"lula": 41.0, "flavio-bolsonaro": 34.0},
            },
        ]
        result = build_source_diagnostics(polls, peer_window_days=10)
        self.assertGreater(result["comparisonCount"], 0)
        labels = {row["label"] for row in result["institutes"]}
        self.assertEqual(labels, {"A", "B", "C"})

    def test_rolling_validation_reports_error_metrics(self):
        polls = []
        base_date = date(2026, 8, 1)
        for idx in range(8):
            polls.append({
                "date": base_date + timedelta(days=idx * 5),
                "institute": ["A", "B", "C", "D"][idx % 4],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-{20000 + idx:05d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": 38.0 + idx * 0.2,
                    "flavio-bolsonaro": 35.0 - idx * 0.1,
                },
            })
        result = rolling_validation(polls, minimum_training_polls=3)
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["caseCount"], 0)
        self.assertIsNotNone(result["meanAbsoluteError"])
        self.assertIsNotNone(result["simpleMeanAbsoluteError"])
        self.assertIsNotNone(result["errorDifferenceVsSimple"])
        self.assertGreaterEqual(result["intervalCoverage"], 0.0)
        self.assertLessEqual(result["intervalCoverage"], 100.0)


if __name__ == "__main__":
    unittest.main()
