# pipeline schema v16 final.
# schema v16: parametric weighting uncertainty.
# pipeline schema v15 final.
# schema v15: weight stress test.
# pipeline schema v14 final.
# schema v14: exact weight audit.
# pipeline schema v13 final.
# schema v13: candidate scenario coverage.
# pipeline schema v12 final.
# schema v12: house effect shadow validation.
# pipeline schema v11 final.
# schema v11: temporal freshness and coverage.
# pipeline schema v10 final.
# schema v10: methodological diversity bootstrap.
# pipeline schema v9 final.
# schema v9: regime persistence by distinct evidence.
# pipeline schema v8 final.
# schema v8: regime shift shadow model.
# pipeline schema v7 final.
# schema v7: institute-cluster bootstrap.
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
from collections import Counter
from datetime import date, timedelta

from scripts.update_analytics import (
    parse_metadata,
    dedupe_polls,
    aggregate_first_round,
    aggregate_candidate,
    build_source_diagnostics,
    rolling_validation,
    non_candidate_for_label,
    response_composition,
    sensitivity_analysis,
    influence_analysis,
    advanced_uncertainty,
    bootstrap_current_support,
    cluster_bootstrap_current_support,
    aggregate_runoff_table,
    regime_shift_analysis,
    regime_shadow_validation,
    regime_evidence_fingerprint,
    apply_regime_persistence,
    method_group,
    method_diversity_analysis,
    method_bootstrap_current_support,
    temporal_coverage_analysis,
    weighted_quantile_pairs,
    estimate_house_effects,
    apply_house_effect_shadow,
    current_house_effect_shadow,
    house_effect_shadow_validation,
    candidate_scenario_coverage_analysis,
    scenario_coverage_shadow_validation,
    poll_weight_components,
    weight_audit_analysis,
    stress_poll_weights,
    weight_stress_test,
    WEIGHT_STRESS_VARIANTS,
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


    def test_cluster_bootstrap_is_deterministic_and_uses_institutes(self):
        polls = []
        values = {
            "A": [(40.0, 35.0), (41.0, 34.0), (42.0, 33.0)],
            "B": [(37.0, 37.0)],
            "C": [(39.0, 36.0)],
        }
        day = 17
        for institute, rows in values.items():
            for lula, flavio in rows:
                polls.append({
                    "date": date(2026, 9, day),
                    "institute": institute,
                    "sample": 2000,
                    "method": "Presencial",
                    "registration": f"BR-36{day:03d}/2026",
                    "verifiedTse": False,
                    "values": {"lula": lula, "flavio-bolsonaro": flavio},
                    "nonCandidate": {},
                })
                day += 1

        a = cluster_bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        b = cluster_bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "ok")
        self.assertEqual(a["clusterCount"], 3)
        self.assertEqual(a["draws"], 120)
        self.assertIn("lula", a["candidates"])
        self.assertLessEqual(a["candidates"]["lula"]["p10"], a["candidates"]["lula"]["p90"])

    def test_advanced_uncertainty_contains_cluster_component(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": ["A", "A", "B", "C"][idx],
                "sample": 1800 + idx * 100,
                "method": "Online",
                "registration": f"BR-37{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0 + idx, "flavio-bolsonaro": 36.0 - idx * 0.4},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        agg = aggregate_first_round(polls, date(2026, 9, 22))
        validation = {
            "absoluteErrorQuantiles": {"q80": 2.0, "q90": 3.0},
            "absoluteErrorQuantilesBySupportBand": {
                "high": {"count": 30, "q80": 2.5, "q90": 3.5}
            },
        }
        result = advanced_uncertainty(polls, date(2026, 9, 22), agg, validation)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["instituteClusterCount"], 3)
        self.assertGreater(result["instituteBootstrapDraws"], 0)
        row = result["candidates"]["lula"]
        self.assertIsNotNone(row["instituteBootstrapP10"])
        self.assertIsNotNone(row["instituteBootstrapP90"])
        self.assertIn(
            row["dominantComponent"],
            {"analytical", "pollBootstrap", "instituteBootstrap", "empirical"},
        )

    def test_runoff_advanced_uncertainty_does_not_use_first_round_empirical_floor(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": ["A", "B", "C", "D"][idx],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-38{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 48.0 + idx * 0.2, "flavio-bolsonaro": 45.0 - idx * 0.2},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        scenario = aggregate_runoff_table(polls, date(2026, 9, 22))
        self.assertIsNotNone(scenario)
        self.assertFalse(scenario["uncertainty"]["empiricalCalibrationApplied"])
        self.assertEqual(scenario["uncertainty"]["empiricalErrorQuantileUsed"], "none")


    def test_regime_shift_stable_series_does_not_trigger(self):
        polls = []
        start = date(2026, 8, 25)
        for idx in range(16):
            polls.append({
                "date": start + timedelta(days=idx * 2),
                "institute": ["A", "B", "C", "D"][idx % 4],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-39{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": 40.0 + (idx % 3 - 1) * 0.2,
                    "flavio-bolsonaro": 35.0 + (idx % 2) * 0.2,
                },
                "nonCandidate": {},
            })
        result = regime_shift_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["overall"], "stable")
        self.assertFalse(result["adaptiveApplied"])
        self.assertTrue(all(row["level"] == "stable" for row in result["candidates"].values()))

    def test_regime_shift_detects_consistent_recent_level_change(self):
        polls = []
        older_start = date(2026, 8, 24)
        for idx in range(10):
            polls.append({
                "date": older_start + timedelta(days=idx * 2),
                "institute": ["A", "B", "C", "D", "E"][idx % 5],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-40{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0, "flavio-bolsonaro": 36.0},
                "nonCandidate": {},
            })
        for idx, institute in enumerate(["A", "B", "C", "D", "E"]):
            polls.append({
                "date": date(2026, 9, 17 + idx),
                "institute": institute,
                "sample": 2200,
                "method": "Presencial",
                "registration": f"BR-41{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 42.0 + idx * 0.1, "flavio-bolsonaro": 33.0 - idx * 0.1},
                "nonCandidate": {},
            })
        result = regime_shift_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertIn(result["overall"], {"watch", "consistent"})
        self.assertFalse(result["adaptiveApplied"])
        self.assertGreater(result["candidates"]["lula"]["differenceRecentVsPrevious"], 1.5)
        self.assertGreaterEqual(result["candidates"]["lula"]["instituteConsistency"], 0.7)
        self.assertGreater(
            result["candidates"]["lula"]["shadowAdaptiveSupport"],
            result["candidates"]["lula"]["currentSupport"],
        )

    def test_regime_shadow_validation_never_auto_applies(self):
        polls = []
        start = date(2026, 7, 1)
        for idx in range(45):
            phase = idx // 15
            lula = [38.0, 40.0, 42.0][phase]
            flavio = [37.0, 35.5, 34.0][phase]
            polls.append({
                "date": start + timedelta(days=idx * 2),
                "institute": ["A", "B", "C", "D", "E"][idx % 5],
                "sample": 2000,
                "method": "Online",
                "registration": f"BR-42{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": lula + (idx % 3 - 1) * 0.2,
                    "flavio-bolsonaro": flavio + (idx % 2) * 0.2,
                },
                "nonCandidate": {},
            })
        result = regime_shadow_validation(polls)
        self.assertFalse(result["adaptiveApplied"])
        self.assertIn(result["status"], {"ok", "insufficient-data"})
        if result["status"] == "ok":
            self.assertIsNotNone(result["baselineMeanAbsoluteError"])
            self.assertIsNotNone(result["shadowMeanAbsoluteError"])


    def test_regime_persistence_does_not_advance_without_new_evidence(self):
        regime = {
            "status": "ok",
            "overall": "consistent",
            "evidenceFingerprint": "same",
            "candidates": {
                "x": {
                    "level": "consistent",
                    "differenceRecentVsPrevious": 2.0,
                }
            },
        }
        first, history = apply_regime_persistence(regime, [], "2026-09-22T10:00:00Z")
        second, history2 = apply_regime_persistence(regime, history, "2026-09-22T10:15:00Z")
        self.assertEqual(first["candidates"]["x"]["persistenceStreak"], 1)
        self.assertEqual(second["candidates"]["x"]["persistenceStreak"], 1)
        self.assertFalse(second["evidenceChanged"])
        self.assertEqual(len(history2), 1)

    def test_regime_persistence_requires_three_distinct_same_direction_states(self):
        history = []
        for idx, fp in enumerate(["a", "b", "c"]):
            regime = {
                "status": "ok",
                "overall": "consistent",
                "evidenceFingerprint": fp,
                "candidates": {
                    "x": {
                        "level": "consistent",
                        "differenceRecentVsPrevious": 1.5 + idx * 0.1,
                    }
                },
            }
            current, history = apply_regime_persistence(
                regime, history, f"2026-09-22T1{idx}:00:00Z"
            )
        self.assertEqual(current["candidates"]["x"]["persistenceStreak"], 3)
        self.assertTrue(current["candidates"]["x"]["persistentSignal"])
        self.assertEqual(current["persistentCandidateCount"], 1)
        self.assertFalse(current["persistenceApplied"])

    def test_regime_persistence_resets_on_direction_change(self):
        history = []
        for fp, delta in [("a", 2.0), ("b", 2.2), ("c", -2.1)]:
            regime = {
                "status": "ok",
                "overall": "consistent",
                "evidenceFingerprint": fp,
                "candidates": {
                    "x": {
                        "level": "consistent",
                        "differenceRecentVsPrevious": delta,
                    }
                },
            }
            current, history = apply_regime_persistence(
                regime, history, f"2026-09-22T{10+len(history):02d}:00:00Z"
            )
        self.assertEqual(current["candidates"]["x"]["persistenceStreak"], 1)
        self.assertFalse(current["candidates"]["x"]["persistentSignal"])

    def test_regime_fingerprint_ignores_execution_time_and_tracks_poll_evidence(self):
        polls = [{
            "date": date(2026, 9, 20),
            "institute": "A",
            "sample": 2000,
            "method": "Online",
            "registration": "BR-43000/2026",
            "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
            "nonCandidate": {},
        }]
        a = regime_evidence_fingerprint(polls, date(2026, 9, 22))
        b = regime_evidence_fingerprint(polls, date(2026, 9, 22))
        self.assertEqual(a, b)
        polls[0]["values"]["lula"] = 41.0
        c = regime_evidence_fingerprint(polls, date(2026, 9, 22))
        self.assertNotEqual(a, c)


    def test_method_group_normalizes_common_modes(self):
        self.assertEqual(method_group("Presencial domiciliar"), "presencial")
        self.assertEqual(method_group("Telefônica CATI"), "telefonica")
        self.assertEqual(method_group("Online / web"), "online")
        self.assertEqual(method_group("URA / IVR"), "ura-ivr")
        self.assertEqual(method_group("Híbrida"), "hibrida")

    def test_method_diversity_uses_effective_weight_shares(self):
        polls = [
            {
                "date": date(2026, 9, 20),
                "institute": "A",
                "sample": 2000,
                "method": method,
                "registration": f"BR-44{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0 + idx, "flavio-bolsonaro": 35.0 - idx * 0.5},
                "nonCandidate": {},
            }
            for idx, method in enumerate(["Presencial", "Online", "Telefônica", "Presencial"])
        ]
        result = method_diversity_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["methodCount"], 3)
        self.assertGreaterEqual(result["effectiveMethodCount"], 1.0)
        self.assertLessEqual(result["maxWeightShare"], 1.0)
        self.assertAlmostEqual(sum(result["shares"].values()), 1.0, places=3)

    def test_method_bootstrap_is_deterministic(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": chr(ord("A") + idx),
                "sample": 1800 + idx * 100,
                "method": ["Presencial", "Online", "Telefônica", "Presencial"][idx],
                "registration": f"BR-45{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0 + idx, "flavio-bolsonaro": 36.0 - idx * 0.4},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        a = method_bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        b = method_bootstrap_current_support(polls, date(2026, 9, 22), draws=120)
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "ok")
        self.assertEqual(a["clusterCount"], 3)
        self.assertIn("lula", a["candidates"])


    def test_weighted_quantile_pairs(self):
        pairs = [(1.0, 1.0), (5.0, 2.0), (10.0, 1.0)]
        self.assertEqual(weighted_quantile_pairs(pairs, 0.50), 5.0)
        self.assertEqual(weighted_quantile_pairs(pairs, 0.80), 10.0)

    def test_temporal_coverage_detects_fresh_diversified_window(self):
        polls = []
        for idx in range(8):
            polls.append({
                "date": date(2026, 9, 15 + idx),
                "institute": ["A","B","C","D"][idx % 4],
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-46{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
                "nonCandidate": {},
            })
        result = temporal_coverage_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["latestAgeDays"], 0)
        self.assertGreaterEqual(result["distinctPollDates"], 6)
        self.assertIn(result["freshness"], {"fresca", "moderada"})
        self.assertIn(result["temporalConcentration"], {"diversificada", "moderada"})

    def test_temporal_coverage_flags_stale_concentrated_window(self):
        polls = [
            {
                "date": date(2026, 8, 25),
                "institute": "A",
                "sample": 2000,
                "method": "Online",
                "registration": f"BR-47{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0 + idx * 0.1, "flavio-bolsonaro": 35.0},
                "nonCandidate": {},
            }
            for idx in range(5)
        ]
        result = temporal_coverage_analysis(polls, date(2026, 9, 22))
        self.assertEqual(result["freshness"], "defasada")
        self.assertEqual(result["temporalConcentration"], "concentrada")


    def test_house_effect_shrinkage_reduces_small_sample_offset(self):
        polls = []
        base_date = date(2026, 9, 1)
        for idx in range(18):
            institute = ["A", "B", "C"][idx % 3]
            lula = {"A": 43.0, "B": 39.0, "C": 40.0}[institute]
            flavio = {"A": 33.0, "B": 37.0, "C": 36.0}[institute]
            polls.append({
                "date": base_date + timedelta(days=idx),
                "institute": institute,
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-48{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": lula, "flavio-bolsonaro": flavio},
                "nonCandidate": {},
            })
        effects = estimate_house_effects(
            polls,
            date(2026, 9, 20),
            prior_strength=6.0,
            min_candidate_comparisons=4,
        )
        self.assertEqual(effects["status"], "ok")
        a = effects["effects"].get("a")
        self.assertIsNotNone(a)
        row = a["candidateEffects"]["lula"]
        self.assertLess(abs(row["shrunkenOffset"]), abs(row["rawOffset"]))
        self.assertLessEqual(abs(row["shrunkenOffset"]), 3.0)

    def test_apply_house_effect_shadow_moves_values_opposite_offset(self):
        polls = [{
            "date": date(2026, 9, 20),
            "institute": "A",
            "sample": 2000,
            "method": "Online",
            "registration": "BR-49000/2026",
            "verifiedTse": False,
            "values": {"lula": 42.0, "flavio-bolsonaro": 34.0},
            "nonCandidate": {},
        }]
        effects = {
            "effects": {
                "a": {
                    "candidateEffects": {
                        "lula": {"shrunkenOffset": 2.0},
                        "flavio-bolsonaro": {"shrunkenOffset": -1.5},
                    }
                }
            }
        }
        adjusted = apply_house_effect_shadow(polls, date(2026, 9, 22), effects)
        self.assertAlmostEqual(adjusted[0]["values"]["lula"], 40.0)
        self.assertAlmostEqual(adjusted[0]["values"]["flavio-bolsonaro"], 35.5)

    def test_current_house_effect_shadow_never_applies_correction(self):
        polls = []
        for idx in range(18):
            institute = ["A", "B", "C"][idx % 3]
            offsets = {"A": 1.5, "B": -1.0, "C": 0.0}
            polls.append({
                "date": date(2026, 9, 1) + timedelta(days=idx),
                "institute": institute,
                "sample": 2000,
                "method": "Presencial",
                "registration": f"BR-50{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": 40.0 + offsets[institute],
                    "flavio-bolsonaro": 35.0 - offsets[institute],
                },
                "nonCandidate": {},
            })
        result = current_house_effect_shadow(polls, date(2026, 9, 22))
        self.assertFalse(result["correctionApplied"])
        self.assertIn(result["status"], {"ok", "insufficient-data"})
        if result["status"] == "ok":
            self.assertIn("lula", result["candidates"])

    def test_house_effect_validation_is_leakage_free_and_non_automatic(self):
        polls = []
        start = date(2026, 7, 1)
        for idx in range(50):
            institute = ["A", "B", "C", "D", "E"][idx % 5]
            institute_shift = {"A": 1.5, "B": -1.0, "C": 0.8, "D": -0.5, "E": 0.0}[institute]
            polls.append({
                "date": start + timedelta(days=idx * 2),
                "institute": institute,
                "sample": 1800 + (idx % 4) * 100,
                "method": "Online",
                "registration": f"BR-51{idx:03d}/2026",
                "verifiedTse": False,
                "values": {
                    "lula": 40.0 + institute_shift + (idx % 3 - 1) * 0.2,
                    "flavio-bolsonaro": 35.0 - institute_shift + (idx % 2) * 0.2,
                },
                "nonCandidate": {},
            })
        result = house_effect_shadow_validation(polls)
        self.assertFalse(result["correctionApplied"])
        self.assertIn(result["status"], {"ok", "insufficient-data"})
        if result["status"] == "ok":
            self.assertGreater(result["comparisonCount"], 0)
            self.assertIsNotNone(result["baselineMeanAbsoluteError"])
            self.assertIsNotNone(result["shadowMeanAbsoluteError"])


    def test_scenario_coverage_does_not_treat_absence_as_zero(self):
        polls = [
            {
                "date": date(2026, 9, 20),
                "institute": "A",
                "sample": 2000,
                "method": "Presencial",
                "registration": "BR-52000/2026",
                "verifiedTse": False,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0, "augusto-cury": 5.0},
                "nonCandidate": {},
            },
            {
                "date": date(2026, 9, 21),
                "institute": "B",
                "sample": 2000,
                "method": "Online",
                "registration": "BR-52001/2026",
                "verifiedTse": False,
                "values": {"lula": 41.0, "flavio-bolsonaro": 34.0},
                "nonCandidate": {},
            },
            {
                "date": date(2026, 9, 22),
                "institute": "C",
                "sample": 2000,
                "method": "Telefônica",
                "registration": "BR-52002/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0, "flavio-bolsonaro": 36.0},
                "nonCandidate": {},
            },
        ]
        result = candidate_scenario_coverage_analysis(polls, date(2026, 9, 22), core_threshold=0.70)
        self.assertEqual(result["status"], "ok")
        self.assertIn("lula", result["coreCandidates"])
        self.assertIn("flavio-bolsonaro", result["coreCandidates"])
        self.assertNotIn("augusto-cury", result["coreCandidates"])
        self.assertGreater(result["candidates"]["augusto-cury"]["baselineSupport"], 0.0)
        self.assertIsNone(result["candidates"]["augusto-cury"]["harmonizedSupport"])
        self.assertFalse(result["harmonizationApplied"])

    def test_scenario_coverage_harmonized_shadow_uses_common_set(self):
        polls = []
        for idx in range(8):
            values = {
                "lula": 40.0 + (idx % 2),
                "flavio-bolsonaro": 35.0 - (idx % 2),
                "renan-santos": 5.0,
            }
            if idx < 6:
                values["augusto-cury"] = 6.0
            polls.append({
                "date": date(2026, 9, 15 + idx),
                "institute": ["A","B","C","D"][idx % 4],
                "sample": 1800,
                "method": "Presencial",
                "registration": f"BR-53{idx:03d}/2026",
                "verifiedTse": False,
                "values": values,
                "nonCandidate": {},
            })
        result = candidate_scenario_coverage_analysis(polls, date(2026, 9, 22), core_threshold=0.70)
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["scenarioCount"], 2)
        self.assertGreater(result["harmonizedPollCount"], 0)
        self.assertLessEqual(result["harmonizedWeightShare"], 1.0)
        self.assertIsNotNone(result["maxHarmonizedShift"])
        self.assertFalse(result["harmonizationApplied"])

    def test_scenario_coverage_validation_never_auto_applies(self):
        polls = []
        start = date(2026, 7, 1)
        for idx in range(45):
            values = {
                "lula": 40.0 + (idx % 3 - 1) * 0.2,
                "flavio-bolsonaro": 35.0 + (idx % 2) * 0.2,
                "renan-santos": 5.0,
            }
            if idx % 4 != 0:
                values["augusto-cury"] = 6.0
            polls.append({
                "date": start + timedelta(days=idx * 2),
                "institute": ["A","B","C","D","E"][idx % 5],
                "sample": 1900,
                "method": "Online",
                "registration": f"BR-54{idx:03d}/2026",
                "verifiedTse": False,
                "values": values,
                "nonCandidate": {},
            })
        result = scenario_coverage_shadow_validation(polls)
        self.assertFalse(result["harmonizationApplied"])
        self.assertIn(result["status"], {"ok", "insufficient-data"})
        if result["status"] == "ok":
            self.assertGreater(result["comparisonCount"], 0)
            self.assertIsNotNone(result["baselineMeanAbsoluteError"])
            self.assertIsNotNone(result["shadowMeanAbsoluteError"])


    def test_weight_audit_matches_production_weight_formula(self):
        polls = [
            {
                "date": date(2026, 9, 20),
                "institute": "A",
                "sample": 2000,
                "method": "Presencial",
                "registration": "BR-55000/2026",
                "verifiedTse": True,
                "values": {"lula": 40.0, "flavio-bolsonaro": 35.0},
                "nonCandidate": {},
            },
            {
                "date": date(2026, 9, 21),
                "institute": "A",
                "sample": 1000,
                "method": "Online",
                "registration": "BR-55001/2026",
                "verifiedTse": False,
                "values": {"lula": 41.0},
                "nonCandidate": {},
            },
            {
                "date": date(2026, 9, 22),
                "institute": "B",
                "sample": 3000,
                "method": "Telefônica",
                "registration": "BR-55002/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0, "flavio-bolsonaro": 36.0},
                "nonCandidate": {},
            },
        ]
        audit = weight_audit_analysis(polls, date(2026, 9, 22))
        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["pollCount"], 3)
        self.assertAlmostEqual(
            sum(row["windowWeightShare"] for row in audit["rows"]),
            1.0,
            places=5,
        )
        flavio_total = sum(
            row["candidateWeightShares"].get("flavio-bolsonaro", 0.0)
            for row in audit["rows"]
        )
        self.assertAlmostEqual(flavio_total, 1.0, places=5)
        missing = next(row for row in audit["rows"] if row["registration"] == "BR-55001/2026")
        self.assertNotIn("flavio-bolsonaro", missing["candidateWeightShares"])
        self.assertFalse(audit["automaticAdjustment"])

    def test_weight_components_multiply_to_raw_weight(self):
        poll = {
            "date": date(2026, 9, 20),
            "institute": "A",
            "sample": 2500,
            "method": "Presencial",
            "registration": "BR-56000/2026",
            "verifiedTse": True,
            "values": {"lula": 40.0},
        }
        counts = Counter({"a": 4})
        parts = poll_weight_components(poll, date(2026, 9, 22), counts)
        product = (
            parts["recencyFactor"]
            * parts["sampleFactor"]
            * parts["repeatPenalty"]
            * parts["verificationFactor"]
        )
        self.assertAlmostEqual(parts["rawWeight"], product, places=12)


    def test_weight_stress_production_matches_current_aggregate(self):
        polls = [
            {
                "date": date(2026, 9, 16 + idx),
                "institute": ["A", "A", "B", "C", "D"][idx],
                "sample": [1200, 1800, 2200, 3000, 1600][idx],
                "method": "Presencial",
                "registration": f"BR-57{idx:03d}/2026",
                "verifiedTse": idx % 2 == 0,
                "values": {
                    "lula": 39.0 + idx,
                    "flavio-bolsonaro": 36.0 - idx * 0.4,
                },
                "nonCandidate": {},
            }
            for idx in range(5)
        ]
        current = aggregate_first_round(polls, date(2026, 9, 22))
        production = next(v for v in WEIGHT_STRESS_VARIANTS if v["id"] == "production")
        weighted = stress_poll_weights(
            polls,
            date(2026, 9, 22),
            production["decayDays"],
            production["sampleExponent"],
            production["repeatExponent"],
        )
        for cid in current["candidates"]:
            alt = aggregate_candidate(weighted, cid)
            self.assertIsNotNone(alt)
            self.assertAlmostEqual(
                current["candidates"][cid]["support"],
                alt[0],
                places=10,
            )

    def test_weight_stress_reports_range_without_automatic_adjustment(self):
        polls = []
        for idx in range(12):
            polls.append({
                "date": date(2026, 9, 5) + timedelta(days=idx),
                "institute": ["A", "A", "A", "B", "C", "D"][idx % 6],
                "sample": [800, 1200, 1800, 2500][idx % 4],
                "method": "Online",
                "registration": f"BR-58{idx:03d}/2026",
                "verifiedTse": idx % 3 == 0,
                "values": {
                    "lula": 37.0 + idx * 0.5,
                    "flavio-bolsonaro": 38.0 - idx * 0.35,
                },
                "nonCandidate": {},
            })
        result = weight_stress_test(polls, date(2026, 9, 22))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["variantCount"], 7)
        self.assertEqual(result["productionVariantId"], "production")
        self.assertFalse(result["automaticAdjustment"])
        self.assertGreaterEqual(result["overallMaxShift"], 0.0)
        self.assertIn(result["sensitivity"], {"baixa", "moderada", "alta"})
        for row in result["candidates"].values():
            self.assertLessEqual(row["minSupport"], row["baselineSupport"] + row["maxAbsoluteShift"] + 1e-9)
            self.assertGreaterEqual(row["maxSupport"], row["baselineSupport"] - row["maxAbsoluteShift"] - 1e-9)

    def test_weight_stress_variants_change_only_declared_parameters(self):
        ids = [v["id"] for v in WEIGHT_STRESS_VARIANTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 7)
        production = next(v for v in WEIGHT_STRESS_VARIANTS if v["id"] == "production")
        self.assertEqual(production["decayDays"], 10.0)
        self.assertEqual(production["sampleExponent"], 0.50)
        self.assertEqual(production["repeatExponent"], 0.50)


    def test_advanced_uncertainty_contains_parameter_stress_envelope(self):
        polls = []
        for idx in range(10):
            polls.append({
                "date": date(2026, 9, 8) + timedelta(days=idx),
                "institute": ["A", "A", "A", "B", "C"][idx % 5],
                "sample": [800, 1200, 2000, 3500, 5000][idx % 5],
                "method": ["Presencial", "Online", "Telefônica"][idx % 3],
                "registration": f"BR-59{idx:03d}/2026",
                "verifiedTse": idx % 2 == 0,
                "values": {
                    "lula": 37.0 + idx * 0.55,
                    "flavio-bolsonaro": 38.0 - idx * 0.40,
                },
                "nonCandidate": {},
            })
        target = date(2026, 9, 22)
        agg = aggregate_first_round(polls, target)
        stress = weight_stress_test(polls, target)
        result = advanced_uncertainty(
            polls,
            target,
            agg,
            {"absoluteErrorQuantiles": {"q80": 0.5, "q90": 1.0}},
            weight_stress=stress,
        )
        self.assertEqual(result["parameterStressVariantCount"], 7)
        self.assertFalse(result["parameterStressAutomaticAdjustment"])
        for cid, row in result["candidates"].items():
            stress_row = stress["candidates"][cid]
            self.assertAlmostEqual(row["parameterStressLow"], stress_row["minSupport"], places=2)
            self.assertAlmostEqual(row["parameterStressHigh"], stress_row["maxSupport"], places=2)
            self.assertLessEqual(row["advancedLow"], row["parameterStressLow"] + 1e-9)
            self.assertGreaterEqual(row["advancedHigh"], row["parameterStressHigh"] - 1e-9)
            self.assertIn(
                row["dominantComponent"],
                {"analytical", "pollBootstrap", "instituteBootstrap", "methodBootstrap", "parameterStress", "empirical"},
            )

    def test_parameter_stress_does_not_shift_central_support(self):
        polls = [
            {
                "date": date(2026, 9, 18 + idx),
                "institute": ["A", "B", "C", "D"][idx],
                "sample": [900, 1600, 3000, 5000][idx],
                "method": "Online",
                "registration": f"BR-60{idx:03d}/2026",
                "verifiedTse": False,
                "values": {"lula": 39.0 + idx, "flavio-bolsonaro": 36.0 - idx * 0.6},
                "nonCandidate": {},
            }
            for idx in range(4)
        ]
        target = date(2026, 9, 22)
        agg = aggregate_first_round(polls, target)
        result = advanced_uncertainty(polls, target, agg, {"absoluteErrorQuantiles": {}})
        for cid, row in result["candidates"].items():
            self.assertAlmostEqual(row["support"], agg["candidates"][cid]["support"], places=2)


if __name__ == "__main__":
    unittest.main()
