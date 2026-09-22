#!/usr/bin/env python3
"""Analytics eleitorais auditáveis para o aplicativo Android.

Princípios:
- pesquisas individuais são a unidade estatística; agregadores servem para descoberta;
- levantamentos duplicados são removidos pelo registro TSE (ou por chave de conteúdo);
- cadastro oficial do TSE é usado como camada de verificação quando disponível;
- recência, tamanho amostral e repetição do mesmo instituto entram no peso;
- mercados de previsão são exibidos como sinal separado e NÃO entram na média de pesquisas;
- o sistema estima apoio agregado e incerteza, não probabilidade própria de vitória.
"""
from __future__ import annotations

import io
import json
import math
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

ELECTION_DATE = date(2026, 10, 4)
UA = {"User-Agent": "TermometroEleicoes/0.3 (+github.com/emanoelb5-lgtm/Elei-es)"}
BBC_TABLE = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/table/portuguese/app/amp"
TSE_PACKAGE_API = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=6ee9ef02-b6da-4dd2-8fee-37afe4d2db6d"
TSE_RESOURCE_ID = "769a663e-12c5-489e-a9c8-04633c2d57a3"
POLY_EVENT = "https://gamma-api.polymarket.com/events/slug/brazil-presidential-election"
LIVE_WINDOW_DAYS = 30
HISTORY_DAYS = 90
# Alterações neste arquivo disparam a coleta v3 pelo GitHub Actions.

ALIASES = {
    "lula": ["lula", "luiz inácio lula da silva", "luiz inacio lula da silva"],
    "flavio-bolsonaro": ["flávio bolsonaro", "flavio bolsonaro"],
    "augusto-cury": ["augusto cury"],
    "renan-santos": ["renan santos", "renan missão", "renan missao"],
    "ronaldo-caiado": ["ronaldo caiado", "caiado"],
    "romeu-zema": ["romeu zema", "zema"],
    "pablo-marcal": ["pablo marçal", "pablo marcal"],
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


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("\xa0", " ")).strip()


def candidate_for_label(label: str) -> str | None:
    low = norm(label)
    ordered = sorted(
        ((cid, alias) for cid, aliases in ALIASES.items() for alias in aliases),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for cid, alias in ordered:
        if norm(alias) in low:
            return cid
    return None


def parse_pct(text: str) -> float | None:
    m = re.search(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def parse_sample(text: str) -> int:
    digits = re.sub(r"\D", "", text or "")
    value = int(digits) if digits else 2000
    return value if 300 <= value <= 100_000 else 2000


def parse_end_date(text: str) -> date | None:
    matches = re.findall(r"(\d{1,2})/(\d{1,2})(?:/(?:20)?26)?", text or "")
    if not matches:
        return None
    day, month = matches[-1]
    try:
        return date(2026, int(month), int(day))
    except ValueError:
        return None


def parse_registration(cells: Iterable[str]) -> str | None:
    joined = " ".join(cells).upper()
    m = re.search(r"BR[-\s]?\d{5}/2026", joined)
    if not m:
        return None
    return m.group(0).replace(" ", "").replace("BR-", "BR-")


def fetch_tse_registry_ids() -> tuple[set[str], dict]:
    source = {
        "id": "tse",
        "label": "TSE · PesqEle",
        "type": "cadastro oficial de pesquisas",
        "status": "fallback",
        "updatedAt": None,
        "url": "https://dadosabertos.tse.jus.br/dataset/pesquisas-eleitorais-2026",
    }
    try:
        meta = requests.get(TSE_PACKAGE_API, headers=UA, timeout=25)
        meta.raise_for_status()
        package = meta.json()["result"]
        resource = next((r for r in package.get("resources", []) if r.get("id") == TSE_RESOURCE_ID), None)
        if resource is None:
            resource = next((r for r in package.get("resources", []) if "pesquisas eleitorais" in norm(r.get("name", ""))), None)
        if resource is None or not resource.get("url"):
            raise RuntimeError("recurso CSV do TSE não localizado")
        raw = requests.get(resource["url"], headers=UA, timeout=40)
        raw.raise_for_status()
        blob = raw.content
        texts: List[str] = []
        if zipfile.is_zipfile(io.BytesIO(blob)):
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith((".csv", ".txt")):
                        texts.append(zf.read(name).decode("latin-1", errors="ignore"))
        else:
            texts.append(blob.decode("latin-1", errors="ignore"))
        ids = set()
        for text in texts:
            ids.update(m.upper() for m in re.findall(r"BR-\d{5}/2026", text.upper()))
        if not ids:
            raise RuntimeError("nenhum registro BR-xxxxx/2026 encontrado")
        source["status"] = "ok"
        source["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        source["recordsFound"] = len(ids)
        return ids, source
    except Exception as exc:
        source["error"] = str(exc)[:180]
        return set(), source


def fetch_poll_tables() -> tuple[List[dict], List[List[dict]], dict]:
    source = {
        "id": "pollingdata",
        "label": "BBC / PollingData",
        "type": "base de pesquisas individuais",
        "status": "fallback",
        "updatedAt": None,
        "url": BBC_TABLE,
    }
    response = requests.get(BBC_TABLE, headers=UA, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    parsed_tables: List[List[dict]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        candidate_columns: Dict[int, str] = {}
        sample_index = institute_index = registration_index = None
        for i, label in enumerate(headers):
            low = norm(label)
            if "amostra" in low:
                sample_index = i
            if "instituto" in low or "empresa" in low:
                institute_index = i
            if "registro" in low and "tse" in low:
                registration_index = i
            cid = candidate_for_label(label)
            if cid:
                candidate_columns[i] = cid
        if len(set(candidate_columns.values())) < 2:
            continue

        polls: List[dict] = []
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 3:
                continue
            end_date = parse_end_date(cells[0])
            if end_date is None:
                continue
            values: Dict[str, float] = {}
            for i, cid in candidate_columns.items():
                if i < len(cells):
                    value = parse_pct(cells[i])
                    if value is not None:
                        values[cid] = value
            if len(values) < 2:
                continue
            registration = None
            if registration_index is not None and registration_index < len(cells):
                registration = parse_registration([cells[registration_index]])
            if registration is None:
                registration = parse_registration(cells)
            institute = (
                cells[institute_index].strip()
                if institute_index is not None and institute_index < len(cells) and cells[institute_index].strip()
                else "Instituto não identificado"
            )
            sample = parse_sample(cells[sample_index]) if sample_index is not None and sample_index < len(cells) else 2000
            polls.append({
                "date": end_date,
                "institute": institute,
                "sample": sample,
                "registration": registration,
                "values": values,
            })
        if polls:
            parsed_tables.append(polls)

    if not parsed_tables:
        raise RuntimeError("nenhuma tabela de pesquisas foi interpretada")

    # A tabela de 1º turno é a que traz o maior número de candidatos por pesquisa.
    first_round = max(parsed_tables, key=lambda tbl: max(len(p["values"]) for p in tbl))
    first_ids = set().union(*(p["values"].keys() for p in first_round))
    if not {"lula", "flavio-bolsonaro"}.issubset(first_ids):
        raise RuntimeError("tabela de 1º turno não contém os candidatos de referência")

    runoff_tables = [
        tbl for tbl in parsed_tables
        if tbl is not first_round and max(len(p["values"]) for p in tbl) <= 3
    ]
    source["status"] = "ok"
    source["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source["tablesFound"] = len(parsed_tables)
    return first_round, runoff_tables, source


def dedupe_polls(polls: Iterable[dict], tse_ids: set[str]) -> List[dict]:
    seen = set()
    out = []
    for poll in sorted(polls, key=lambda p: p["date"]):
        reg = (poll.get("registration") or "").upper()
        if reg:
            key = ("tse", reg)
        else:
            key = (
                norm(poll.get("institute", "")),
                poll["date"].isoformat(),
                poll.get("sample", 0),
                tuple(sorted((k, round(v, 2)) for k, v in poll["values"].items())),
            )
        if key in seen:
            continue
        seen.add(key)
        poll = dict(poll)
        poll["verifiedTse"] = bool(reg and reg in tse_ids)
        out.append(poll)
    return out


def poll_weights(polls: List[dict], target: date) -> List[tuple[dict, float]]:
    eligible = [p for p in polls if p["date"] <= target and (target - p["date"]).days <= LIVE_WINDOW_DAYS]
    institute_counts = Counter(norm(p["institute"]) for p in eligible)
    weighted = []
    for poll in eligible:
        age = max((target - poll["date"]).days, 0)
        recency = math.exp(-age / 10.0)
        sample_factor = min(max(math.sqrt(max(poll["sample"], 300) / 2000.0), 0.65), 1.60)
        repeat_penalty = 1.0 / math.sqrt(max(institute_counts[norm(poll["institute"])], 1))
        verified_factor = 1.05 if poll.get("verifiedTse") else 1.0
        weighted.append((poll, recency * sample_factor * repeat_penalty * verified_factor))
    return weighted


def aggregate_candidate(weighted: List[tuple[dict, float]], cid: str) -> tuple[float, float, float] | None:
    usable = [(p, w, p["values"][cid]) for p, w in weighted if cid in p["values"] and w > 0]
    if not usable:
        return None
    sw = sum(w for _, w, _ in usable)
    mean = sum(v * w for _, w, v in usable) / sw
    sw2 = sum(w * w for _, w, _ in usable)
    neff = (sw * sw / sw2) if sw2 > 0 else 1.0

    sampling_var = 0.0
    for poll, w, value in usable:
        share = w / sw
        p = min(max(value / 100.0, 0.001), 0.999)
        sampling_var += (share * share) * (p * (1 - p) / max(poll["sample"], 300)) * 10_000.0

    heterogeneity = sum(w * (v - mean) ** 2 for _, w, v in usable) / sw
    se = math.sqrt(max(sampling_var + heterogeneity / max(neff, 1.0), 0.01))
    margin = max(1.96 * se, 0.6)
    return mean, max(0.0, mean - margin), min(100.0, mean + margin)


def aggregate_first_round(polls: List[dict], target: date) -> dict:
    weighted = poll_weights(polls, target)
    ids = sorted(set().union(*(p["values"].keys() for p, _ in weighted))) if weighted else []
    candidates = {}
    for cid in ids:
        agg = aggregate_candidate(weighted, cid)
        if agg:
            candidates[cid] = {"support": agg[0], "low": agg[1], "high": agg[2]}

    used = [p for p, _ in weighted]
    institutes = {norm(p["institute"]) for p in used}
    verified = sum(1 for p in used if p.get("verifiedTse"))
    avg_age = (
        sum((target - p["date"]).days for p in used) / len(used)
        if used else 0.0
    )
    weights = [w for _, w in weighted]
    effective = (sum(weights) ** 2 / sum(w*w for w in weights)) if weights and sum(w*w for w in weights) > 0 else 0.0
    return {
        "candidates": candidates,
        "pollCount": len(used),
        "instituteCount": len(institutes),
        "verifiedTseCount": verified,
        "averageAgeDays": avg_age,
        "effectivePolls": effective,
    }


def aggregate_runoff_table(polls: List[dict], target: date) -> dict | None:
    weighted = poll_weights(polls, target)
    ids = sorted(set().union(*(p["values"].keys() for p, _ in weighted))) if weighted else []
    if len(ids) != 2:
        return None
    candidates = []
    for cid in ids:
        agg = aggregate_candidate(weighted, cid)
        if agg:
            candidates.append({
                "id": cid,
                "name": NAMES.get(cid, cid.replace("-", " ").title()),
                "support": round(agg[0], 2),
                "intervalLow": round(agg[1], 2),
                "intervalHigh": round(agg[2], 2),
            })
    if len(candidates) != 2:
        return None
    used = [p for p, _ in weighted]
    return {
        "id": "-vs-".join(sorted(ids)),
        "label": f"{NAMES.get(ids[0], ids[0])} × {NAMES.get(ids[1], ids[1])}",
        "candidates": candidates,
        "pollCount": len(used),
        "instituteCount": len({norm(p["institute"]) for p in used}),
    }


def fetch_polymarket_signal() -> tuple[dict, dict]:
    source = {
        "id": "polymarket",
        "label": "Polymarket",
        "type": "mercado de previsão · sinal externo",
        "status": "fallback",
        "updatedAt": None,
        "url": "https://polymarket.com/event/brazil-presidential-election",
    }
    try:
        event = requests.get(POLY_EVENT, headers=UA, timeout=20)
        event.raise_for_status()
        result: Dict[str, float] = {}
        for market in event.json().get("markets", []):
            hay = norm(f"{market.get('question','')} {market.get('groupItemTitle','')}")
            cid = candidate_for_label(hay)
            if not cid:
                continue
            outcomes = market.get("outcomes", [])
            prices = market.get("outcomePrices", [])
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if isinstance(prices, str):
                prices = json.loads(prices)
            for i, outcome in enumerate(outcomes):
                if str(outcome).lower() == "yes" and i < len(prices):
                    result[cid] = float(prices[i]) * 100.0
                    break
        if not result:
            raise RuntimeError("mercados de candidatos não encontrados")
        source["status"] = "ok"
        source["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return result, source
    except Exception as exc:
        source["error"] = str(exc)[:180]
        return {}, source


def quality_label(stats: dict) -> str:
    polls = stats["pollCount"]
    institutes = stats["instituteCount"]
    age = stats["averageAgeDays"]
    if polls >= 8 and institutes >= 4 and age <= 10:
        return "boa"
    if polls >= 4 and institutes >= 3 and age <= 16:
        return "moderada"
    return "limitada"


def serialize_poll(poll: dict, round_name: str) -> dict:
    return {
        "date": poll["date"].isoformat(),
        "institute": poll["institute"],
        "sample": poll["sample"],
        "registration": poll.get("registration"),
        "verifiedTse": bool(poll.get("verifiedTse")),
        "round": round_name,
        "candidates": {k: round(v, 2) for k, v in poll["values"].items()},
    }


def build_history(first_round: List[dict], now: datetime, live_point: dict) -> List[dict]:
    path = DATA / "analytics-history.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else []
    live_existing = [p for p in existing if p.get("origin") == "live"]

    reconstructed = []
    start = now.date() - timedelta(days=HISTORY_DAYS)
    current = start
    while current < now.date():
        agg = aggregate_first_round(first_round, current)
        if agg["pollCount"] >= 1 and agg["candidates"]:
            reconstructed.append({
                "generatedAt": f"{current.isoformat()}T18:00:00Z",
                "pollingSupport": {cid: round(v["support"], 2) for cid, v in agg["candidates"].items()},
                "intervals": {
                    cid: {"low": round(v["low"], 2), "high": round(v["high"], 2)}
                    for cid, v in agg["candidates"].items()
                },
                "pollCount": agg["pollCount"],
                "instituteCount": agg["instituteCount"],
                "verifiedTseCount": agg["verifiedTseCount"],
                "origin": "historical-reconstruction",
            })
        current += timedelta(days=1)

    live_existing.append(live_point)
    # Retém no máximo uma leitura ao vivo a cada 6h para evitar peso visual excessivo.
    buckets = {}
    for p in live_existing:
        try:
            stamp = datetime.fromisoformat(p["generatedAt"].replace("Z", "+00:00"))
            buckets[int(stamp.timestamp()) // 21600] = p
        except Exception:
            continue
    live = list(buckets.values())
    merged = reconstructed + live
    merged.sort(key=lambda p: p["generatedAt"])
    return merged[-1000:]


def main() -> None:
    now = datetime.now(timezone.utc)
    tse_ids, tse_source = fetch_tse_registry_ids()
    first_raw, runoff_raw, polling_source = fetch_poll_tables()
    first_round = dedupe_polls(first_raw, tse_ids)
    runoff_tables = [dedupe_polls(tbl, tse_ids) for tbl in runoff_raw]
    market_signal, market_source = fetch_polymarket_signal()

    agg = aggregate_first_round(first_round, now.date())
    if not agg["candidates"]:
        raise SystemExit("Nenhuma pesquisa de primeiro turno disponível para a leitura.")

    history_path = DATA / "analytics-history.json"
    previous_history = json.loads(history_path.read_text("utf-8")) if history_path.exists() else []
    previous_support = {}
    if previous_history:
        previous_support = previous_history[-1].get("pollingSupport", {})

    candidates = []
    for cid, values in sorted(agg["candidates"].items(), key=lambda kv: NAMES.get(kv[0], kv[0]).lower()):
        support = values["support"]
        prev = float(previous_support.get(cid, support))
        change = support - prev
        candidates.append({
            "id": cid,
            "name": NAMES.get(cid, cid.replace("-", " ").title()),
            "pollingSupport": round(support, 2),
            "intervalLow": round(values["low"], 2),
            "intervalHigh": round(values["high"], 2),
            "change": round(change, 2),
            "trend": "subindo" if change > 0.10 else "caindo" if change < -0.10 else "estável",
            "marketSignal": round(market_signal[cid], 2) if cid in market_signal else None,
        })

    runoff = []
    seen_scenarios = set()
    for table in runoff_tables:
        scenario = aggregate_runoff_table(table, now.date())
        if scenario and scenario["id"] not in seen_scenarios and scenario["pollCount"] > 0:
            seen_scenarios.add(scenario["id"])
            runoff.append(scenario)

    quality = {
        "pollCount": agg["pollCount"],
        "instituteCount": agg["instituteCount"],
        "verifiedTseCount": agg["verifiedTseCount"],
        "averageAgeDays": round(agg["averageAgeDays"], 1),
        "effectivePolls": round(agg["effectivePolls"], 1),
        "confidence": quality_label(agg),
    }

    snapshot = {
        "schemaVersion": 3,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "electionDate": ELECTION_DATE.isoformat(),
        "daysToElection": max((ELECTION_DATE - now.date()).days, 0),
        "quality": quality,
        "sources": [polling_source, tse_source, market_source],
        "candidates": candidates,
        "runoffScenarios": runoff,
        "methodology": {
            "primaryUnit": "pesquisa individual",
            "windowDays": LIVE_WINDOW_DAYS,
            "deduplication": "registro TSE; fallback por instituto/data/amostra/resultados",
            "weighting": "decaimento temporal + tamanho amostral + controle de repetição por instituto",
            "uncertainty": "erro amostral aproximado + heterogeneidade entre pesquisas",
            "marketUse": "informativo; não entra na média de pesquisas",
        },
        "note": "Leitura estatística de pesquisas públicas. Os intervalos expressam incerteza do agregador e não garantem resultado eleitoral.",
    }
    (DATA / "analytics.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "utf-8")

    polls_payload = {
        "generatedAt": snapshot["generatedAt"],
        "firstRound": [serialize_poll(p, "1º turno") for p in first_round],
        "runoff": [
            serialize_poll(p, f"2º turno {i+1}")
            for i, table in enumerate(runoff_tables)
            for p in table
        ],
    }
    (DATA / "polls.json").write_text(json.dumps(polls_payload, ensure_ascii=False, indent=2) + "\n", "utf-8")

    live_point = {
        "generatedAt": snapshot["generatedAt"],
        "pollingSupport": {c["id"]: c["pollingSupport"] for c in candidates},
        "intervals": {
            c["id"]: {"low": c["intervalLow"], "high": c["intervalHigh"]}
            for c in candidates
        },
        "pollCount": quality["pollCount"],
        "instituteCount": quality["instituteCount"],
        "verifiedTseCount": quality["verifiedTseCount"],
        "origin": "live",
    }
    history = build_history(first_round, now, live_point)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print(
        "Analytics OK:",
        f"{quality['pollCount']} pesquisas,",
        f"{quality['instituteCount']} institutos,",
        f"{quality['verifiedTseCount']} registros TSE verificados,",
        f"{len(history)} pontos históricos."
    )


if __name__ == "__main__":
    main()
