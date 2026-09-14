#!/usr/bin/env python3
"""Reconstrói o histórico anterior ao início do app usando dados públicos reais.

Fontes:
- BBC/PollingData: pesquisas individuais de 1º turno, com data e percentuais.
- Polymarket CLOB: histórico público das probabilidades implícitas dos mercados.

A reconstrução é identificada no JSON como ``historical-reconstruction`` para
não ser confundida com uma leitura ao vivo do Termômetro.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List

import requests
from bs4 import BeautifulSoup

from update_data import (
    ALIASES,
    DATA,
    ELECTION_DATE,
    UA,
    combine,
    softmax_poll_probability,
)

BBC_TABLE = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/table/portuguese/app/amp"
POLY_EVENT = "https://gamma-api.polymarket.com/events/slug/brazil-presidential-election"
POLY_HISTORY = "https://clob.polymarket.com/prices-history"
ORIGIN = "historical-reconstruction"
LOOKBACK_DAYS = 35
ROLLING_POLL_DAYS = 21


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("\xa0", " ")).strip()


def candidate_for_label(label: str) -> str | None:
    low = norm(label)
    # Prefere os nomes completos para não confundir palavras curtas em cabeçalhos.
    ordered = sorted(
        ((cid, alias) for cid, aliases in ALIASES.items() for alias in aliases),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for cid, alias in ordered:
        if norm(alias) in low:
            return cid
    return None


def pct(value: str) -> float | None:
    value = value.strip()
    if not value or value in {"-", "—"}:
        return None
    m = re.search(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", value)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_end_date(value: str) -> date | None:
    # Exemplos: 04/09-09/09, 17/06-19/06.
    matches = re.findall(r"(\d{1,2})/(\d{1,2})", value)
    if not matches:
        return None
    day, month = matches[-1]
    try:
        return date(2026, int(month), int(day))
    except ValueError:
        return None


def parse_sample(value: str) -> int:
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else 2000


def fetch_individual_polls() -> List[dict]:
    response = requests.get(BBC_TABLE, headers=UA, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    selected = None
    for table in soup.find_all("table"):
        text = norm(table.get_text(" ", strip=True))
        if "lula" in text and "flávio bolsonaro" in text and "registro no tse" in text:
            # A primeira tabela correspondente é a de 1º turno.
            selected = table
            break
    if selected is None:
        raise RuntimeError("Tabela de pesquisas de 1º turno da BBC/PollingData não encontrada")

    rows = selected.find_all("tr")
    if not rows:
        raise RuntimeError("Tabela BBC/PollingData sem linhas")

    header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
    candidate_columns: Dict[int, str] = {}
    sample_index = None
    for index, label in enumerate(header_cells):
        low = norm(label)
        if "amostra" in low:
            sample_index = index
        cid = candidate_for_label(label)
        if cid:
            candidate_columns[index] = cid

    if not {"lula", "flavio-bolsonaro"}.issubset(set(candidate_columns.values())):
        raise RuntimeError(f"Cabeçalho inesperado na tabela BBC/PollingData: {header_cells[:12]}")

    polls: List[dict] = []
    for row in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        if len(cells) < 3:
            continue
        end_date = parse_end_date(cells[0])
        if end_date is None:
            continue
        values: Dict[str, float] = {}
        for index, cid in candidate_columns.items():
            if index < len(cells):
                value = pct(cells[index])
                if value is not None:
                    values[cid] = value
        if not {"lula", "flavio-bolsonaro"}.issubset(values):
            continue
        polls.append(
            {
                "date": end_date,
                "sample": parse_sample(cells[sample_index]) if sample_index is not None and sample_index < len(cells) else 2000,
                "values": values,
            }
        )

    if len(polls) < 3:
        raise RuntimeError(f"Poucas pesquisas históricas encontradas: {len(polls)}")
    return polls


def get_event_markets() -> dict:
    response = requests.get(POLY_EVENT, headers=UA, timeout=25)
    response.raise_for_status()
    return response.json()


def yes_token_ids(event: dict) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for market in event.get("markets", []):
        haystack = norm(f"{market.get('question', '')} {market.get('groupItemTitle', '')}")
        cid = candidate_for_label(haystack)
        if not cid:
            continue
        outcomes = market.get("outcomes", [])
        tokens = market.get("clobTokenIds", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except Exception:
                tokens = []
        for index, outcome in enumerate(outcomes):
            if str(outcome).lower() == "yes" and index < len(tokens):
                result[cid] = str(tokens[index])
                break
    return result


def fetch_market_history(start: date, end: date) -> Dict[str, Dict[date, float]]:
    try:
        event = get_event_markets()
        tokens = yes_token_ids(event)
    except Exception:
        return {}

    start_ts = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    output: Dict[str, Dict[date, float]] = {}
    for cid, token in tokens.items():
        try:
            response = requests.get(
                POLY_HISTORY,
                params={"market": token, "startTs": start_ts, "endTs": end_ts, "fidelity": 1440},
                headers=UA,
                timeout=25,
            )
            response.raise_for_status()
            history = response.json().get("history", [])
            by_day: Dict[date, float] = {}
            for item in history:
                stamp = datetime.fromtimestamp(float(item["t"]), tz=timezone.utc).date()
                by_day[stamp] = float(item["p"]) * 100.0
            if by_day:
                output[cid] = by_day
        except Exception:
            continue
    return output


def latest_market_on_or_before(series: Dict[date, float], target: date, max_age_days: int = 3) -> float | None:
    candidates = [d for d in series if d <= target and (target - d).days <= max_age_days]
    if not candidates:
        return None
    return series[max(candidates)]


def market_for_day(history: Dict[str, Dict[date, float]], target: date) -> Dict[str, float] | None:
    raw: Dict[str, float] = {}
    for cid, series in history.items():
        value = latest_market_on_or_before(series, target)
        if value is not None:
            raw[cid] = value
    if not {"lula", "flavio-bolsonaro"}.issubset(raw):
        return None
    total = sum(raw.values())
    if total <= 0:
        return None
    return {cid: value * 100.0 / total for cid, value in raw.items()}


def aggregate_polls(polls: Iterable[dict], target: date) -> tuple[Dict[str, float], int]:
    eligible = [
        poll for poll in polls
        if poll["date"] <= target and (target - poll["date"]).days <= ROLLING_POLL_DAYS
    ]
    if not eligible:
        return {}, 0

    sums: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    for poll in eligible:
        age = (target - poll["date"]).days
        recency = math.exp(-age / 9.0)
        sample_factor = min(max(math.sqrt(max(poll["sample"], 500) / 2000.0), 0.7), 1.6)
        weight = recency * sample_factor
        for cid, value in poll["values"].items():
            sums[cid] = sums.get(cid, 0.0) + value * weight
            weights[cid] = weights.get(cid, 0.0) + weight
    result = {cid: sums[cid] / weights[cid] for cid in sums if weights.get(cid, 0.0) > 0}
    return result, len(eligible)


def historical_points(first_live_day: date) -> List[dict]:
    start = first_live_day - timedelta(days=LOOKBACK_DAYS)
    end = first_live_day - timedelta(days=1)
    polls = fetch_individual_polls()
    market_history = fetch_market_history(start, end)

    points: List[dict] = []
    current = start
    while current <= end:
        polling, poll_count = aggregate_polls(polls, current)
        if {"lula", "flavio-bolsonaro"}.issubset(polling) and poll_count >= 1:
            days = max((ELECTION_DATE - current).days, 0)
            poll_probability = softmax_poll_probability(polling, days)
            market = market_for_day(market_history, current)
            probability = combine(poll_probability, market)
            points.append(
                {
                    "generatedAt": f"{current.isoformat()}T18:00:00Z",
                    "probabilities": {k: round(v, 2) for k, v in probability.items()},
                    "pollingSupport": {k: round(v, 2) for k, v in polling.items()},
                    "marketProbabilities": {k: round(v, 2) for k, v in (market or {}).items()},
                    "origin": ORIGIN,
                    "historical": True,
                    "pollCount": poll_count,
                    "sourceNote": "Reconstrução estatística com pesquisas individuais BBC/PollingData e histórico Polymarket quando disponível.",
                }
            )
        current += timedelta(days=1)
    return points


def enrich_history() -> int:
    path = DATA / "history.json"
    if not path.exists():
        return 0
    history = json.loads(path.read_text("utf-8"))
    live = [entry for entry in history if entry.get("origin") != ORIGIN]
    if not live:
        return 0

    def stamp(entry: dict) -> datetime:
        return datetime.fromisoformat(entry["generatedAt"].replace("Z", "+00:00"))

    live.sort(key=stamp)
    first_live_day = stamp(live[0]).date()
    backfill = historical_points(first_live_day)
    merged = backfill + live
    merged.sort(key=stamp)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return len(backfill)


if __name__ == "__main__":
    count = enrich_history()
    print(f"Histórico retroativo: {count} pontos reconstruídos")
