#!/usr/bin/env python3
"""Atualiza o retrato eleitoral usado pelo app.

O script foi desenhado para falhar de forma segura: uma fonte quebrada é marcada
como fallback e deixa de ganhar peso. Nenhum número é inventado para substituir
uma fonte indisponível.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
ELECTION_DATE = date(2026, 10, 4)
UA = {"User-Agent": "Eleicoes2026Termometro/0.1 (+github.com/emanoelb5-lgtm/Elei-es)"}

ALIASES = {
    "lula": ["lula", "luiz inácio lula da silva", "luiz inacio lula da silva"],
    "flavio-bolsonaro": ["flávio bolsonaro", "flavio bolsonaro", "flávio", "flavio"],
    "augusto-cury": ["augusto cury", "cury"],
    "renan-santos": ["renan santos", "renan"],
    "ronaldo-caiado": ["ronaldo caiado", "caiado"],
    "romeu-zema": ["romeu zema", "zema"],
    "pablo-marcal": ["pablo marçal", "pablo marcal", "marçal", "marcal"],
}
NAMES = {
    "lula": "Lula",
    "flavio-bolsonaro": "Flávio Bolsonaro",
    "augusto-cury": "Augusto Cury",
    "renan-santos": "Renan Santos",
    "ronaldo-caiado": "Ronaldo Caiado",
    "romeu-zema": "Romeu Zema",
    "pablo-marcal": "Pablo Marçal",
}


def fetch_text(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    return r.text


def parse_percent_near(text: str, aliases: List[str]) -> float | None:
    low = text.lower().replace("\xa0", " ")
    for alias in aliases:
        idx = low.find(alias.lower())
        if idx >= 0:
            chunk = low[idx: idx + 220]
            m = re.search(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", chunk)
            if m:
                return float(m.group(1).replace(",", "."))
    return None


def source_electiolab() -> Dict[str, float]:
    url = "https://electiolab.com/pesquisas-presidenciais-2026"
    text = BeautifulSoup(fetch_text(url), "html.parser").get_text(" ", strip=True)
    result = {}
    for cid, aliases in ALIASES.items():
        value = parse_percent_near(text, aliases)
        if value is not None:
            result[cid] = value
    if not {"lula", "flavio-bolsonaro"}.issubset(result):
        raise ValueError("ElectioLab sem os dois líderes esperados")
    return result


def source_bbc_pollingdata() -> Dict[str, float]:
    url = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/range-chart/portuguese/app/embed"
    text = BeautifulSoup(fetch_text(url), "html.parser").get_text(" ", strip=True)
    result = {}
    for cid, aliases in ALIASES.items():
        value = parse_percent_near(text, aliases)
        if value is not None:
            result[cid] = value
    if not {"lula", "flavio-bolsonaro"}.issubset(result):
        raise ValueError("BBC/PollingData sem os dois líderes esperados")
    return result


def source_uol() -> Dict[str, float]:
    url = "https://noticias.uol.com.br/eleicoes/agregador-de-pesquisas-eleitorais/"
    html = fetch_text(url)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    result = {}
    for cid, aliases in ALIASES.items():
        value = parse_percent_near(text, aliases)
        if value is not None:
            result[cid] = value
    if not {"lula", "flavio-bolsonaro"}.issubset(result):
        raise ValueError("UOL não expôs percentuais no HTML desta execução")
    return result


def source_polymarket() -> Dict[str, float]:
    url = "https://gamma-api.polymarket.com/events/slug/brazil-presidential-election"
    event = requests.get(url, headers=UA, timeout=20).json()
    result: Dict[str, float] = {}
    for market in event.get("markets", []):
        question = (market.get("question") or "").lower()
        title = (market.get("groupItemTitle") or "").lower()
        haystack = f"{question} {title}"
        cid = None
        for key, aliases in ALIASES.items():
            if any(alias.lower() in haystack for alias in aliases):
                cid = key
                break
        if not cid:
            continue
        outcomes = market.get("outcomes", "[]")
        prices = market.get("outcomePrices", "[]")
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        if isinstance(prices, str):
            prices = json.loads(prices)
        yes = None
        for i, out in enumerate(outcomes):
            if str(out).lower() == "yes" and i < len(prices):
                yes = float(prices[i]) * 100
        if yes is not None:
            result[cid] = yes
    if not {"lula", "flavio-bolsonaro"}.issubset(result):
        raise ValueError("Polymarket sem mercados dos dois líderes")
    total = sum(result.values())
    if total > 0:
        result = {k: v * 100 / total for k, v in result.items()}
    return result


def weighted_poll_average(sources: List[Tuple[Dict[str, float], float]]) -> Dict[str, float]:
    ids = set().union(*(s.keys() for s, _ in sources))
    out = {}
    for cid in ids:
        vals = [(s[cid], w) for s, w in sources if cid in s]
        if vals:
            out[cid] = sum(v * w for v, w in vals) / sum(w for _, w in vals)
    return out


def softmax_poll_probability(polls: Dict[str, float], days: int) -> Dict[str, float]:
    temperature = max(2.2, min(7.5, 2.2 + days * 0.18))
    exps = {k: math.exp(v / temperature) for k, v in polls.items()}
    total = sum(exps.values()) or 1
    return {k: v * 100 / total for k, v in exps.items()}


def combine(poll_prob: Dict[str, float], market: Dict[str, float] | None) -> Dict[str, float]:
    if not market:
        return poll_prob
    combined = {}
    ids = set(poll_prob) | set(market)
    for cid in ids:
        p = poll_prob.get(cid, 0.0)
        m = market.get(cid, p)
        combined[cid] = 0.60 * p + 0.40 * m
    total = sum(combined.values()) or 1
    return {k: v * 100 / total for k, v in combined.items()}


def main() -> None:
    now = datetime.now(timezone.utc)
    days = max((ELECTION_DATE - now.date()).days, 0)
    source_defs = [
        ("electiolab", "ElectioLab", "agregador de pesquisas", "https://electiolab.com/pesquisas-presidenciais-2026", source_electiolab, 1.0),
        ("bbc", "BBC / PollingData", "agregador de pesquisas", "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/range-chart/portuguese/app/embed", source_bbc_pollingdata, 1.0),
        ("uol", "UOL Eleições", "agregador de pesquisas", "https://noticias.uol.com.br/eleicoes/agregador-de-pesquisas-eleitorais/", source_uol, 1.0),
    ]
    poll_sources: List[Tuple[Dict[str, float], float]] = []
    statuses = []
    for sid, label, stype, url, fn, weight in source_defs:
        try:
            values = fn()
            poll_sources.append((values, weight))
            statuses.append({"id": sid, "label": label, "type": stype, "status": "ok", "updatedAt": now.isoformat().replace("+00:00", "Z"), "url": url})
        except Exception as exc:
            statuses.append({"id": sid, "label": label, "type": stype, "status": "fallback", "updatedAt": None, "url": url, "error": str(exc)[:160]})

    market = None
    try:
        market = source_polymarket()
        statuses.append({"id": "polymarket", "label": "Polymarket", "type": "mercado de previsão", "status": "ok", "updatedAt": now.isoformat().replace("+00:00", "Z"), "url": "https://polymarket.com/event/brazil-presidential-election"})
    except Exception as exc:
        statuses.append({"id": "polymarket", "label": "Polymarket", "type": "mercado de previsão", "status": "fallback", "updatedAt": None, "url": "https://polymarket.com/event/brazil-presidential-election", "error": str(exc)[:160]})

    if not poll_sources:
        raise SystemExit("Nenhuma fonte de pesquisa disponível; preservando o último arquivo.")

    polls = weighted_poll_average(poll_sources)
    poll_prob = softmax_poll_probability(polls, days)
    final = combine(poll_prob, market)

    hist_path = DATA / "history.json"
    history = json.loads(hist_path.read_text("utf-8")) if hist_path.exists() else []
    previous = history[-1]["probabilities"] if history else {}
    ordered = sorted(final, key=final.get, reverse=True)
    candidates = []
    for cid in ordered:
        win = final[cid]
        prev = float(previous.get(cid, win))
        change = win - prev
        trend = "subindo" if change > 0.05 else "caindo" if change < -0.05 else "estável"
        candidates.append({
            "id": cid,
            "name": NAMES.get(cid, cid.replace("-", " ").title()),
            "pollingSupport": round(polls.get(cid, 0.0), 2),
            "marketProbability": round(market[cid], 2) if market and cid in market else None,
            "winProbability": round(win, 2),
            "change": round(change, 2),
            "trend": trend,
        })

    source_count = sum(1 for s in statuses if s["status"] == "ok")
    confidence = "média" if source_count >= 3 else "baixa"
    snapshot = {
        "schemaVersion": 1,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "electionDate": ELECTION_DATE.isoformat(),
        "daysToElection": days,
        "confidence": confidence,
        "methodology": {"pollModelWeight": 0.60 if market else 1.0, "marketWeight": 0.40 if market else 0.0, "activeSources": source_count},
        "sources": statuses,
        "candidates": candidates,
        "note": "Estimativa experimental produzida por combinação matemática de fontes públicas. Não é pesquisa eleitoral, previsão oficial, recomendação de voto ou aconselhamento de aposta.",
    }
    (DATA / "latest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "utf-8")

    point = {"generatedAt": snapshot["generatedAt"], "probabilities": {c["id"]: c["winProbability"] for c in candidates}}
    history.append(point)
    history = history[-240:]
    hist_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
