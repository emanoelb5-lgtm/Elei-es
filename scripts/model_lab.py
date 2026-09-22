#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

try:
    from scripts.historical_backtest import STUDIES, load_polls, normalize
except ModuleNotFoundError:
    from historical_backtest import STUDIES, load_polls, normalize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "model-lab.json"

VARIANTS = [
    {
        "id": "current-v04",
        "label": "Modelo atual",
        "decayDays": 10.0,
        "sampleWeight": True,
        "repeatPenalty": True,
    },
    {
        "id": "fast-decay-7",
        "label": "Recência mais rápida · 7 dias",
        "decayDays": 7.0,
        "sampleWeight": True,
        "repeatPenalty": True,
    },
    {
        "id": "slow-decay-14",
        "label": "Recência mais lenta · 14 dias",
        "decayDays": 14.0,
        "sampleWeight": True,
        "repeatPenalty": True,
    },
    {
        "id": "no-sample-weight",
        "label": "Sem peso por amostra",
        "decayDays": 10.0,
        "sampleWeight": False,
        "repeatPenalty": True,
    },
    {
        "id": "no-repeat-penalty",
        "label": "Sem controle de repetição",
        "decayDays": 10.0,
        "sampleWeight": True,
        "repeatPenalty": False,
    },
    {
        "id": "simple-mean",
        "label": "Média simples",
        "decayDays": None,
        "sampleWeight": False,
        "repeatPenalty": False,
    },
]

WINDOW_DAYS = 30


def norm(value: str) -> str:
    return " ".join(str(value).lower().split())


def variant_weight(poll: dict, target: date, institute_count: int, variant: dict) -> float:
    if variant["decayDays"] is None:
        return 1.0

    age = max((target - poll["date"]).days, 0)
    weight = math.exp(-age / float(variant["decayDays"]))

    if variant["sampleWeight"]:
        weight *= min(
            max(math.sqrt(max(int(poll.get("sample", 300)), 300) / 2000.0), 0.65),
            1.60,
        )

    if variant["repeatPenalty"]:
        weight *= 1.0 / math.sqrt(max(institute_count, 1))

    return weight


def estimate(
    polls: List[dict],
    target: date,
    keys: List[str],
    variant: dict,
    normalize_output: bool,
) -> Dict[str, float]:
    eligible = [
        poll
        for poll in polls
        if poll["date"] <= target and 0 <= (target - poll["date"]).days <= WINDOW_DAYS
    ]
    if not eligible:
        return {}

    counts: Dict[str, int] = {}
    for poll in eligible:
        institute = norm(poll.get("institute", ""))
        counts[institute] = counts.get(institute, 0) + 1

    sums = {key: 0.0 for key in keys}
    weights = {key: 0.0 for key in keys}

    for poll in eligible:
        institute = norm(poll.get("institute", ""))
        weight = variant_weight(poll, target, counts.get(institute, 1), variant)
        for key in keys:
            if key not in poll.get("values", {}):
                continue
            sums[key] += float(poll["values"][key]) * weight
            weights[key] += weight

    result = {
        key: sums[key] / weights[key]
        for key in keys
        if weights[key] > 0
    }
    return normalize(result, keys) if normalize_output else result


def mean_absolute_error(prediction: Dict[str, float], observed: Dict[str, float], keys: List[str]) -> float | None:
    comparable = [key for key in keys if key in prediction and key in observed]
    if not comparable:
        return None
    return sum(abs(float(prediction[key]) - float(observed[key])) for key in comparable) / len(comparable)


def historical_evaluation(variant: dict) -> dict:
    studies_out = []
    pooled_errors = []

    for study in STUDIES:
        polls = load_polls(study)
        keys = list(study["aliases"].keys())
        result = normalize(study["resultValid"], keys)
        horizon_errors = []

        for days in [30, 21, 14, 7, 3, 1]:
            cutoff = study["electionDate"] - timedelta(days=days)
            prediction = estimate(polls, cutoff, keys, variant, normalize_output=True)
            error = mean_absolute_error(prediction, result, keys)
            if error is not None:
                horizon_errors.append(error)
                pooled_errors.append(error)

        studies_out.append({
            "year": study["year"],
            "comparisonCount": len(horizon_errors),
            "meanAbsoluteError": (
                round(sum(horizon_errors) / len(horizon_errors), 2)
                if horizon_errors else None
            ),
        })

    return {
        "comparisonCount": len(pooled_errors),
        "pooledMeanAbsoluteError": (
            round(sum(pooled_errors) / len(pooled_errors), 2)
            if pooled_errors else None
        ),
        "studies": studies_out,
    }


def load_current_polls() -> List[dict]:
    payload = json.loads((DATA / "polls.json").read_text("utf-8"))
    result = []
    for item in payload.get("firstRound", []):
        try:
            end_date = date.fromisoformat(item["date"])
        except Exception:
            continue
        result.append({
            "date": end_date,
            "institute": item.get("institute", "Instituto não identificado"),
            "sample": int(item.get("sample", 2000)),
            "values": {
                str(key): float(value)
                for key, value in item.get("candidates", {}).items()
            },
        })
    return sorted(result, key=lambda poll: (poll["date"], norm(poll["institute"])))


def current_rolling_evaluation(polls: List[dict], variant: dict) -> dict:
    errors = []
    cases = 0

    for heldout in polls:
        training = [poll for poll in polls if poll["date"] < heldout["date"]]
        target = heldout["date"] - timedelta(days=1)
        eligible = [
            poll
            for poll in training
            if poll["date"] <= target and 0 <= (target - poll["date"]).days <= WINDOW_DAYS
        ]
        institute_count = len({norm(poll["institute"]) for poll in eligible})
        if len(eligible) < 4 or institute_count < 2:
            continue

        keys = list(heldout["values"].keys())
        prediction = estimate(training, target, keys, variant, normalize_output=False)
        comparable = [key for key in keys if key in prediction]
        if len(comparable) < 2:
            continue

        for key in comparable:
            errors.append(abs(float(prediction[key]) - float(heldout["values"][key])))
        cases += 1

    return {
        "caseCount": cases,
        "comparisonCount": len(errors),
        "meanAbsoluteError": round(sum(errors) / len(errors), 2) if errors else None,
        "target": "próxima pesquisa publicada",
    }


def main() -> None:
    current_polls = load_current_polls()
    rows = []

    for variant in VARIANTS:
        historical = historical_evaluation(variant)
        current = current_rolling_evaluation(current_polls, variant)
        rows.append({
            "id": variant["id"],
            "label": variant["label"],
            "parameters": {
                "windowDays": WINDOW_DAYS,
                "decayDays": variant["decayDays"],
                "sampleWeight": variant["sampleWeight"],
                "repeatPenalty": variant["repeatPenalty"],
            },
            "historical": historical,
            "currentRolling": current,
        })

    production = next(row for row in rows if row["id"] == "current-v04")
    p_hist = production["historical"]["pooledMeanAbsoluteError"]
    p_current = production["currentRolling"]["meanAbsoluteError"]

    for row in rows:
        hist = row["historical"]["pooledMeanAbsoluteError"]
        current = row["currentRolling"]["meanAbsoluteError"]
        row["deltaVsProduction"] = {
            "historicalMae": (
                round(hist - p_hist, 2)
                if hist is not None and p_hist is not None else None
            ),
            "currentRollingMae": (
                round(current - p_current, 2)
                if current is not None and p_current is not None else None
            ),
        }

        historical_consistent = all(
            study["meanAbsoluteError"] is not None
            for study in row["historical"]["studies"]
        )
        improves_both = (
            hist is not None
            and current is not None
            and p_hist is not None
            and p_current is not None
            and hist <= p_hist - 0.10
            and current <= p_current - 0.10
        )
        no_cycle_regression = True
        production_studies = {
            study["year"]: study["meanAbsoluteError"]
            for study in production["historical"]["studies"]
        }
        for study in row["historical"]["studies"]:
            baseline = production_studies.get(study["year"])
            value = study["meanAbsoluteError"]
            if baseline is not None and value is not None and value > baseline + 0.10:
                no_cycle_regression = False

        row["promotionCandidate"] = bool(
            row["id"] != "current-v04"
            and historical_consistent
            and improves_both
            and no_cycle_regression
        )

    candidates = [row["id"] for row in rows if row["promotionCandidate"]]
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "productionModelId": "current-v04",
        "automaticPromotion": False,
        "promotionPolicy": (
            "Uma variante só é sinalizada para revisão se reduzir o MAE em pelo menos "
            "0,10 p.p. no conjunto histórico e na validação corrente, sem piorar nenhum "
            "ciclo histórico em mais de 0,10 p.p. Nenhuma promoção é automática."
        ),
        "promotionCandidates": candidates,
        "variants": rows,
        "note": (
            "Laboratório técnico de fórmulas. Os resultados avaliam o agregador; "
            "não classificam candidatos e não alteram a leitura de 2026 automaticamente."
        ),
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(
        "Model lab:",
        [(row["id"], row["historical"]["pooledMeanAbsoluteError"], row["currentRolling"]["meanAbsoluteError"]) for row in rows],
        "promotionCandidates=", candidates,
    )


if __name__ == "__main__":
    main()
