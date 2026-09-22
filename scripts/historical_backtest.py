#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "historical-backtest.json"

STUDIES = [
    {
        "year": 2022,
        "round": "1º turno",
        "electionDate": date(2022, 10, 2),
        "pollSource": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2022_Brazilian_presidential_election",
        "resultSource": "https://www.tse.jus.br/comunicacao/noticias/2022/Outubro/100-das-secoes-totalizadas-confira-como-ficou-o-quadro-eleitoral-apos-o-1o-turno",
        "aliases": {
            "lula": ["lula"],
            "bolsonaro": ["bolsonaro"],
            "tebet": ["tebet"],
            "gomes": ["gomes", "ciro"],
        },
        "resultValid": {
            "lula": 48.43,
            "bolsonaro": 43.20,
            "tebet": 4.16,
            "gomes": 3.04,
        },
    },
    {
        "year": 2018,
        "round": "1º turno",
        "electionDate": date(2018, 10, 7),
        "pollSource": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2018_Brazilian_presidential_election",
        "resultSource": "https://www.tse.jus.br/comunicacao/noticias/2018/Outubro/concluida-totalizacao-de-votos-do-1o-turno-das-eleicoes-2018",
        "aliases": {
            "bolsonaro": ["bolsonaro"],
            "haddad": ["haddad"],
            "gomes": ["gomes", "ciro"],
            "alckmin": ["alckmin"],
        },
        "resultValid": {
            "bolsonaro": 46.03,
            "haddad": 29.28,
            "gomes": 12.47,
            "alckmin": 4.76,
        },
    },
]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).lower()).strip()

def flatten_columns(df: pd.DataFrame) -> List[str]:
    out = []
    for col in df.columns:
        if isinstance(col, tuple):
            parts = []
            for x in col:
                sx = str(x).strip()
                if sx and not sx.startswith("Unnamed") and sx not in parts:
                    parts.append(sx)
            out.append(" ".join(parts))
        else:
            out.append(str(col))
    return out

def find_col(cols: List[str], terms: List[str]) -> str | None:
    for col in cols:
        low = norm(col)
        if any(term in low for term in terms):
            return col
    return None

def candidate_col(cols: List[str], aliases: List[str]) -> str | None:
    for col in cols:
        low = norm(col)
        if any(alias in low for alias in aliases):
            return col
    return None

def parse_end_date(value, year: int) -> date | None:
    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    year_match = re.findall(r"\b(20\d{2})\b", text)
    parsed_year = int(year_match[-1]) if year_match else year

    # Remove o ano antes de procurar dias. Sem isso, "2018" poderia ser
    # interpretado como um dia 18 pertencente ao último mês da string.
    date_text = re.sub(r"\b20\d{2}\b", "", text)
    hits = re.findall(r"(?<!\d)(\d{1,2})(?!\d)\s*([A-Za-z]{3,9})?", date_text)
    if not hits:
        return None

    explicit_months = [
        mon[:3].lower()
        for _, mon in hits
        if mon and mon[:3].lower() in MONTHS
    ]

    # Percorre de trás para frente e escolhe o último dia plausível. Se o
    # último número não trouxer mês, herda o último mês explícito do período.
    inherited_month = explicit_months[-1] if explicit_months else None
    for day_s, mon_s in reversed(hits):
        month_key = mon_s[:3].lower() if mon_s else inherited_month
        month = MONTHS.get(month_key or "")
        if not month:
            continue
        try:
            return date(parsed_year, month, int(day_s))
        except ValueError:
            continue
    return None

def pct(value) -> float | None:
    m = re.search(r"(\d+(?:[\.,]\d+)?)", str(value))
    if not m:
        return None
    x = float(m.group(1).replace(",", "."))
    return x if 0 <= x <= 100 else None

def sample_n(value) -> int:
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return 2000
    n = int(digits)
    return n if 300 <= n <= 100000 else 2000

def load_polls(study: dict) -> List[dict]:
    response = requests.get(
        study["pollSource"],
        headers={"User-Agent": "TermometroEleicoes/0.4.1 historical-backtest"},
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))

    polls = []
    aliases = study["aliases"]
    election_date = study["electionDate"]
    year = study["year"]

    for df in tables:
        df = df.copy()
        df.columns = flatten_columns(df)
        cols = list(df.columns)

        candidate_cols = {
            cid: candidate_col(cols, candidate_aliases)
            for cid, candidate_aliases in aliases.items()
        }
        if sum(1 for col in candidate_cols.values() if col) < len(aliases):
            continue

        pollster = find_col(cols, ["pollster", "polling firm", "publisher/pollster", "firm"])
        dates = find_col(cols, ["polling period", "date(s)", "date", "dates conducted", "fieldwork", "administered"])
        sample = find_col(cols, ["sample"])
        if not pollster or not dates:
            continue

        for _, row in df.iterrows():
            end = parse_end_date(row.get(dates), year)
            if end is None or end > election_date:
                continue

            values = {}
            valid = True
            for cid, col in candidate_cols.items():
                if not col:
                    valid = False
                    break
                value = pct(row.get(col))
                if value is None:
                    valid = False
                    break
                values[cid] = value
            if not valid:
                continue

            institute = str(row.get(pollster, "")).strip()
            institute = re.sub(r"\[[^\]]+\]", "", institute).strip()
            institute_norm = norm(institute)
            if (
                not institute
                or institute.lower() == "nan"
                or institute_norm in {"results", "2018 election", "2022 election"}
                or len(institute) > 90
                or "was stabbed" in institute_norm
                or "withdrew" in institute_norm
                or "candidacy" in institute_norm
            ):
                continue

            polls.append({
                "date": end,
                "institute": institute,
                "sample": sample_n(row.get(sample)) if sample else 2000,
                "method": "histórico não padronizado",
                "values": values,
            })

    seen = {}
    for poll in polls:
        key = (
            norm(poll["institute"]),
            poll["date"].isoformat(),
            poll["sample"],
            tuple(sorted(poll["values"].items())),
        )
        seen[key] = poll
    return sorted(seen.values(), key=lambda p: (p["date"], norm(p["institute"])))

def normalize(values: Dict[str, float], keys: List[str]) -> Dict[str, float]:
    total = sum(max(values.get(key, 0.0), 0.0) for key in keys)
    if total <= 0:
        return {}
    return {key: 100.0 * max(values.get(key, 0.0), 0.0) / total for key in keys}

def model_mean(polls: List[dict], cutoff: date, keys: List[str], weighted: bool) -> Dict[str, float]:
    eligible = [
        poll for poll in polls
        if poll["date"] <= cutoff and 0 <= (cutoff - poll["date"]).days <= 30
    ]
    if not eligible:
        return {}

    counts: Dict[str, int] = {}
    for poll in eligible:
        key = norm(poll["institute"])
        counts[key] = counts.get(key, 0) + 1

    sums = {key: 0.0 for key in keys}
    weight_sums = {key: 0.0 for key in keys}

    for poll in eligible:
        age = max((cutoff - poll["date"]).days, 0)
        if weighted:
            weight = math.exp(-age / 10.0)
            weight *= min(max(math.sqrt(max(poll["sample"], 300) / 2000.0), 0.65), 1.60)
            weight *= 1.0 / math.sqrt(max(counts[norm(poll["institute"])], 1))
        else:
            weight = 1.0

        for key, value in poll["values"].items():
            if key in sums:
                sums[key] += value * weight
                weight_sums[key] += weight

    raw = {
        key: sums[key] / weight_sums[key]
        for key in keys
        if weight_sums[key] > 0
    }
    return normalize(raw, keys)

def mae(prediction: Dict[str, float], result: Dict[str, float], keys: List[str]) -> float | None:
    if any(key not in prediction for key in keys):
        return None
    return sum(abs(prediction[key] - result[key]) for key in keys) / len(keys)

def run_study(study: dict) -> dict:
    polls = load_polls(study)
    keys = list(study["aliases"].keys())
    result_common = normalize(study["resultValid"], keys)
    election_date = study["electionDate"]

    horizons = [30, 21, 14, 7, 3, 1]
    rows = []
    for days in horizons:
        cutoff = election_date - timedelta(days=days)
        eligible = [
            poll for poll in polls
            if poll["date"] <= cutoff and 0 <= (cutoff - poll["date"]).days <= 30
        ]
        institutes = len({norm(poll["institute"]) for poll in eligible})
        weighted = model_mean(polls, cutoff, keys, True)
        simple = model_mean(polls, cutoff, keys, False)
        weighted_mae = mae(weighted, result_common, keys)
        simple_mae = mae(simple, result_common, keys)

        rows.append({
            "daysBeforeElection": days,
            "cutoff": cutoff.isoformat(),
            "pollCount": len(eligible),
            "instituteCount": institutes,
            "weightedMae": round(weighted_mae, 2) if weighted_mae is not None else None,
            "simpleMae": round(simple_mae, 2) if simple_mae is not None else None,
            "weightedEstimate": {key: round(value, 2) for key, value in weighted.items()},
            "simpleEstimate": {key: round(value, 2) for key, value in simple.items()},
        })

    valid_rows = [row for row in rows if row["weightedMae"] is not None]
    return {
        "status": "ok" if valid_rows else "insufficient-data",
        "year": study["year"],
        "round": study["round"],
        "electionDate": election_date.isoformat(),
        "pollSource": study["pollSource"],
        "resultSource": study["resultSource"],
        "pollCountTotal": len(polls),
        "resultComparisonBasis": "votos dos candidatos comuns normalizados para 100%",
        "officialResultCommonSet": {key: round(value, 2) for key, value in result_common.items()},
        "horizons": rows,
        "averageWeightedMae": round(sum(row["weightedMae"] for row in valid_rows) / len(valid_rows), 2) if valid_rows else None,
        "averageSimpleMae": round(sum(row["simpleMae"] for row in valid_rows) / len(valid_rows), 2) if valid_rows else None,
        "correctionApplied": False,
        "note": "Backtest histórico separado. Não altera pesos, médias ou candidatos de 2026.",
    }

def main():
    results = [run_study(study) for study in STUDIES]
    payload = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "studies": results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for result in results:
        print(
            "Backtest",
            result["year"],
            result["status"],
            "pesquisas=", result["pollCountTotal"],
            "MAE ponderado=", result["averageWeightedMae"],
            "MAE simples=", result["averageSimpleMae"],
        )

if __name__ == "__main__":
    main()
