# Testes determinísticos: sem chamadas de rede.
import unittest
from datetime import date

from scripts.update_analytics import (
    parse_metadata,
    dedupe_polls,
    aggregate_first_round,
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


if __name__ == "__main__":
    unittest.main()
