# pipeline schema v6 final.
# schema v6: advanced uncertainty.
# schema v5: influence diagnostics.
# schema v4: composition + sensitivity validation.
# pipeline corrente separado do backtest histórico.
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
    non_candidate_for_label,
    response_composition,
    sensitivity_analysis,
    influence_analysis,
    advanced_uncertainty,
    bootstrap_current_support,
    percentile,
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
        self.assertGreaterEqual(result["empiricalQ80Coverage"], 0.0)
        self.assertLessEqual(result["empiricalQ80Coverage"], 100.0)
        self.assertGreaterEqual(result["empiricalQ90Coverage"], result["empiricalQ80Coverage"])


    def test_non_candidate_header_classification(self):
        self.assertEqual(non_candidate_for_label("Branco"), "blank")
        self.assertEqual(non_candidate_for_label("Nulos"), "null")
        self.assertEqual(non_candidate_for_label("Não sabe / não respondeu"), "undecided")
        self.assertEqual(non_candidate_for_label("Nenhum deles"), "none")
        self.assertIsNone(non_candidate_for_label("Lula"))

    def test_response_composition_keeps_residual_unclassified(self):
        polls = [
            {
                "date": date(2026, 9, 20),
                "institute": "A",
                "sample": 2000,
                "method": "Presencial",
                "registration": "BR-30001/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
                "nonCandidate": {"blank": 5.0, "undecided": 10.0},
            },
            {
                "date": date(2026, 9, 21),
                "institute": "B",
                "sample": 2000,
                "method": "Online",
                "registration": "BR-30002/2026",
                "verifiedTse": False,
                "values": {"lula": 42.0, "flavio-bolsonaro": 34.0},
                "nonCandidate": {"blank": 4.0, "undecided": 8.0},
            },
        ]
        result = response_composition(polls, date(2026, 9, 22))
        self.assertTrue(result["available"])
        self.assertIn("blank", result["categories"])
        self.assertIn("undecided", result["categories"])
        self.assertGreater(result["residualUnclassified"], 0.0)
        self.assertLess(result["candidateShare"], 100.0)

    def test_sensitivity_reports_leave_one_out_range(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": chr(ord("A") + idx),
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-31{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": 38.0 + idx,
                    "flavio-bolsonaro": 36.0 - idx * 0.5,
                },
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        result = sensitivity_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["maxLeaveOneOutShift"], 0.0)
        self.assertIn("lula", result["candidates"])
        row = result["candidates"]["lula"]
        self.assertLessEqual(row["leaveOneOutLow"], row["baseline"] + 5.0)
        self.assertGreaterEqual(row["leaveOneOutHigh"], row["baseline"] - 5.0)


    def test_influence_analysis_reports_poll_and_institute_removal(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": ["A", "B", "C", "D"][idx],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-32{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": [39.0, 40.0, 41.0, 48.0][idx],
                    "flavio-bolsonaro": [36.0, 35.0, 34.0, 29.0][idx],
                },
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        result = influence_analysis(polls, date(2026, 9, 22), peer_window_days=10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["pollCount"], 4)
        self.assertEqual(result["instituteCount"], 4)
        self.assertEqual(len(result["polls"]), 4)
        self.assertEqual(len(result["institutes"]), 4)
        self.assertFalse(result["correctionApplied"])
        self.assertGreaterEqual(max(row["maxAbsoluteShift"] for row in result["polls"]), 0.0)

    def test_influence_analysis_does_not_label_small_sample_as_atypical(self):
        polls = [
            {
                "date": date(2026, 9, 20 + idx),
                "institute": chr(ord("A") + idx),
                "sample": 1500,
                "method": "Online",
                "registration": f"BR-33{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0 + idx, "flavio-bolsonaro": 35.0 - idx},
                "nonCandidate": {},
            }
            for idx in range(3)
        ]
        result = influence_analysis(polls, date(2026, 9, 22))
        self.assertIsNone(result["atypicalThreshold"])
        self.assertTrue(all(not row["atypicalSignal"] for row in result["polls"]))


    def test_percentile_interpolates(self):
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5, places=6)

    def test_bootstrap_current_support_is_deterministic(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": chr(ord("A") + idx),
                "sample": 1800 + idx * 100,
                "method": "Online",
                "registration": f"BR-34{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0 + idx, "flavio-bolsonaro": 36.0 - idx * 0.4},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        a = bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        b = bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "ok")
        self.assertIn("lula", a["candidates"])
        self.assertLessEqual(a["candidates"]["lula"]["p10"], a["candidates"]["lula"]["p90"])

    def test_advanced_uncertainty_never_narrower_than_model_interval(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": chr(ord("A") + idx),
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-35{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0 + idx, "flavio-bolsonaro": 35.0 - idx * 0.5},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        agg = aggregate_first_round(polls, date(2026, 9, 22))
        validation = {"absoluteErrorQuantiles": {"q80": 2.5, "q90": 3.5}}
        result = advanced_uncertainty(polls, date(2026, 9, 22), agg, validation)
        self.assertEqual(result["status"], "ok")
        for cid, row in result["candidates"].items():
            support = agg["candidates"][cid]["support"]
            model_half = max(
                support - agg["candidates"][cid]["low"],
                agg["candidates"][cid]["high"] - support,
            )
            self.assertGreaterEqual(row["advancedHalfWidth"] + 1e-9, model_half)
            self.assertGreaterEqual(row["advancedHalfWidth"], 2.5)


if __name__ == "__main__":
    unittest.main()
