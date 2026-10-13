#!/usr/bin/env python3
"""Pipeline independente do segundo turno: evidências, modelo e histórico."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
IDS = ("flavio-bolsonaro", "lula")
FINALISTS = frozenset(IDS)
START = date(2026, 10, 5)
ELECTION = date(2026, 10, 25)
BBC_TABLE = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/table/portuguese/app/amp"
MARKET_API = "https://gamma-api.polymarket.com/events/slug/brazil-presidential-election"
MARKET_URL = "https://polymarket.com/event/brazil-presidential-election"
UA = {"User-Agent": "TermometroSegundoTurno/0.11 (+github.com/emanoelb5-lgtm/Elei-es)"}

def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()).strip()

def fingerprint(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()

def _result(values: dict) -> dict:
    if set(values) != FINALISTS:
        raise ValueError("O levantamento precisa conter apenas os dois finalistas")
    parsed = {key: float(values[key]) for key in IDS}
    if any(not math.isfinite(v) or not 0 <= v <= 100 for v in parsed.values()):
        raise ValueError("Percentual inválido")
    if not 0 < sum(parsed.values()) <= 101.1:
        raise ValueError("Percentuais incompatíveis")
    return parsed

def _key(poll: dict) -> str:
    return (poll.get("registration") or "").strip().upper() or "|".join(
        (poll["fieldworkEnd"], normalize(poll["institute"]), str(poll["sample"])))

def validate_poll(row: dict, today: date, *, primary=False) -> dict:
    start, end = date.fromisoformat(row["fieldworkStart"]), date.fromisoformat(row["fieldworkEnd"])
    if not START <= start <= end <= min(today, ELECTION):
        raise ValueError("Coleta fora do período do segundo turno")
    published = row.get("publishedAt")
    if published and not end <= date.fromisoformat(published[:10]) <= today:
        raise ValueError("Data de publicação incompatível")
    basis = row["basis"]
    if basis not in ("total", "valid", "unspecified") or (primary and basis == "unspecified"):
        raise ValueError("Base percentual inválida")
    result = _result(row["result"])
    valid = _result(row["validResult"]) if row.get("validResult") else {}
    if basis == "valid" and abs(sum(result.values()) - 100) > 1.1:
        raise ValueError("Votos válidos não somam aproximadamente 100%")
    if valid and abs(sum(valid.values()) - 100) > 1.1:
        raise ValueError("Votos válidos publicados inválidos")
    if basis == "total" and valid and any(
        abs(result[c] * 100 / sum(result.values()) - valid[c]) > 1.1 for c in IDS
    ):
        raise ValueError("Votos totais e válidos incompatíveis")
    sample = int(row["sample"])
    if not 1 <= sample <= 1_000_000 or not row.get("sourceUrl", "").startswith("https://"):
        raise ValueError("Fonte ou amostra inválida")
    if not row.get("id") or not row.get("institute", "").strip():
        raise ValueError("Pesquisa sem identificação")
    margin = row.get("marginError")
    if margin is not None and (not math.isfinite(float(margin)) or not 0 < float(margin) <= 20):
        raise ValueError("Margem de erro inválida")
    non_candidate = {k: float(v) for k, v in row.get("nonCandidate", {}).items()}
    if any(not math.isfinite(v) or not 0 <= v <= 100 for v in non_candidate.values()):
        raise ValueError("Outras respostas inválidas")
    return {**row, "sample": sample, "result": result, "validResult": valid,
            "nonCandidate": non_candidate,
            "instituteKey": normalize(row.get("instituteKey") or row["institute"].split("/")[0])}

def analytic_values(poll: dict) -> tuple[dict, str] | None:
    if poll["basis"] == "unspecified":
        return None
    if poll.get("validResult"):
        values, origin = poll["validResult"], "válidos publicados"
    elif poll["basis"] == "valid":
        values, origin = poll["result"], "válidos publicados"
    else:
        values, origin = poll["result"], "válidos calculados entre os dois nomes"
    total = sum(values.values())
    return ({c: values[c] * 100 / total for c in IDS}, origin)

def estimate(polls: list[dict], target: date) -> dict:
    latest = {}
    for poll in sorted(polls, key=lambda p: (p["fieldworkEnd"], p.get("publishedAt") or "", p["id"])):
        if poll.get("publishedAt") and poll["publishedAt"][:10] > target.isoformat():
            continue
        age = (target - date.fromisoformat(poll["fieldworkEnd"])).days
        if 0 <= age <= 14 and analytic_values(poll) is not None:
            latest[poll["instituteKey"]] = poll
    if len(latest) < 2 or target > ELECTION:
        return {"status": "insufficient-data", "instituteCount": len(latest), "rows": [],
                "message": "São necessários ao menos dois institutos com base identificada e coleta nos últimos 14 dias."}
    rows = []
    for poll in latest.values():
        values, origin = analytic_values(poll)
        age = (target - date.fromisoformat(poll["fieldworkEnd"])).days
        weight = math.exp(-math.log(2) * age / 7) * min(math.sqrt(poll["sample"] / 2000), 1.4)
        rows.append({"pollId": poll["id"], "institute": poll["institute"], "values": values,
                     "basisOrigin": origin, "weight": weight, "ageDays": age, "sample": poll["sample"]})
    total_weight = sum(r["weight"] for r in rows)
    for row in rows:
        row["weightShare"] = row.pop("weight") / total_weight
    mean = sum(r["values"][IDS[0]] * r["weightShare"] for r in rows)
    variance = sum(r["weightShare"] * (r["values"][IDS[0]] - mean) ** 2 for r in rows)
    # Hipótese explícita: erro estrutural compartilhado não diminui com n.
    # Sem alegar calibração histórica, adiciona horizonte e idade da coleta.
    days = max(0, (ELECTION - target).days)
    latest_age = min(r["ageDays"] for r in rows)
    sigma = math.sqrt(3.0 ** 2 + variance + (days * .10) ** 2 + (latest_age * .15) ** 2)
    probability = 100 * .5 * (1 + math.erf((mean - 50) / (sigma * math.sqrt(2))))
    low, high = max(0, mean - 1.96 * sigma), min(100, mean + 1.96 * sigma)
    return {
        "status": "ok", "modelVersion": "runoff-1", "asOf": target.isoformat(),
        "instituteCount": len(rows), "pollCount": len(rows), "rows": rows,
        "support": {IDS[0]: round(mean, 2), IDS[1]: round(100 - mean, 2)},
        "winProbability": {IDS[0]: round(probability, 1), IDS[1]: round(100 - probability, 1)},
        "intervals": {IDS[0]: [round(low, 1), round(high, 1)], IDS[1]: [round(100 - high, 1), round(100 - low, 1)]},
        "sigma": round(sigma, 3), "calibrated": False, "latestAgeDays": latest_age,
        "quality": "base inicial" if len(rows) < 4 else "base em expansão",
        "message": "Estimativa exploratória de vitória sob as hipóteses do modelo; não calibrada. Não é percentual de votos nem garantia de resultado.",
    }

def build_history(polls: list[dict]) -> list[dict]:
    # Pontos por dia de divulgação, sem conhecimento de publicações futuras.
    dates = sorted({p["publishedAt"][:10] for p in polls if p.get("publishedAt") and analytic_values(p)})
    history = []
    for day in dates:
        eligible = [p for p in polls if p.get("publishedAt") and p["publishedAt"][:10] <= day]
        point = estimate(eligible, date.fromisoformat(day))
        if point["status"] == "ok":
            history.append({"date": day, "support": point["support"],
                            "winProbability": point["winProbability"], "instituteCount": point["instituteCount"]})
    return history

def build_payload(curated: dict, source: dict, generated_at: str, today: date,
                  previous: dict | None = None, market: dict | None = None, sources: list | None = None) -> dict:
    if curated.get("electionDate") != ELECTION.isoformat():
        raise ValueError("Data do segundo turno inesperada")
    candidates = curated.get("candidates", [])
    if {r.get("id") for r in candidates} != FINALISTS or len(candidates) != 2:
        raise ValueError("Finalistas inesperados")
    selected = {}
    for row in (previous or {}).get("polls", []):
        try:
            checked = validate_poll(row, today)
            selected[_key(checked)] = checked
        except (KeyError, TypeError, ValueError):
            continue
    for row in source.get("runoff", []):
        try:
            if "result" not in row:
                row = {**row, "id": row.get("registration") or f"{row['date']}-{row['institute']}-{row['sample']}",
                       "fieldworkEnd": row["date"], "basis": "unspecified", "result": row["candidates"],
                       "sourceUrl": BBC_TABLE, "sourceLabel": "BBC / PollingData", "publishedAt": None}
            checked = validate_poll(row, today)
            selected.setdefault(_key(checked), checked)
        except (KeyError, TypeError, ValueError):
            continue
    for row in curated.get("polls", []):
        checked = validate_poll(row, today, primary=True)
        selected[_key(checked)] = {**checked, "origin": "fonte primária conferida"}
    polls = sorted(selected.values(), key=lambda p: (p["fieldworkEnd"], p.get("publishedAt") or "", p["id"]), reverse=True)
    if len({p["id"] for p in polls}) != len(polls):
        raise ValueError("IDs duplicados de pesquisa")
    revision = fingerprint(polls)
    history, model = build_history(polls), estimate(polls, today)
    if model["status"] == "ok":
        prior = history[-2] if len(history) >= 2 else None
        model["change"] = {c: round(model["support"][c] - prior["support"][c], 2) for c in IDS} if prior else None
        model["changeSince"] = prior["date"] if prior else None
    return {
        "schemaVersion": 2,
        "generatedAt": (previous or {}).get("generatedAt", generated_at) if (previous or {}).get("pollRevision") == revision else generated_at,
        "checkedAt": generated_at, "pollRevision": revision,
        "electionDate": ELECTION.isoformat(), "candidates": candidates, "polls": polls,
        "pollCount": len(polls), "instituteCount": len({p["instituteKey"] for p in polls}),
        "latestPollDate": max((p["fieldworkEnd"] for p in polls), default=None),
        "model": model, "history": history,
        "market": market or {"status": "unavailable", "values": {}, "url": MARKET_URL},
        "sources": sources or [],
        "methodology": "Um levantamento recente por instituto, janela de 14 dias, meia-vida de 7 dias, peso amostral com teto. Votos válidos publicados têm prioridade; totais são convertidos somente entre os dois nomes e identificados como calculados. Base desconhecida não entra. Mercados ficam separados. Modelo normal exploratório com desvio estrutural mínimo de 3 pontos de votos válidos, dispersão dos institutos, distância da eleição e idade da coleta; sem calibração histórica.",
    }

def parse_bbc_runoff(html: str, today: date) -> list[dict]:
    from bs4 import BeautifulSoup
    from scripts.update_analytics import candidate_for_label, parse_metadata, parse_pct, parse_registration
    output = []
    tables = BeautifulSoup(html, "html.parser").find_all("table")
    if not tables:
        raise ValueError("Fonte não contém tabelas interpretáveis")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        columns = {i: candidate_for_label(label) for i, label in enumerate(headers) if candidate_for_label(label)}
        if set(columns.values()) != FINALISTS or len(columns) != 2:
            continue
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) <= max(columns):
                continue
            dates = re.findall(r"(\d{1,2})/(\d{1,2})(?:/2026)?", cells[0])
            if len(dates) < 2:
                continue
            try:
                start = date(2026, int(dates[0][1]), int(dates[0][0]))
                end = date(2026, int(dates[1][1]), int(dates[1][0]))
                if not START <= start <= end <= today:
                    continue
                metadata = parse_metadata(cells[0])
                if metadata["institute"] == "Instituto não identificado":
                    continue
                registration = parse_registration(cells)
                poll = {**metadata, "id": registration or f"bbc-{start}-{end}-{metadata['institute']}",
                        "fieldworkStart": start.isoformat(), "fieldworkEnd": end.isoformat(),
                        "registration": registration, "publishedAt": None, "basis": "unspecified",
                        "result": {c: parse_pct(cells[i]) for i, c in columns.items()},
                        "validResult": {}, "nonCandidate": {}, "sourceUrl": BBC_TABLE,
                        "sourceLabel": "BBC / PollingData", "origin": "tabela pública; base percentual a conferir"}
                output.append(validate_poll(poll, today))
            except (ValueError, TypeError, KeyError):
                continue
    return output

def parse_market(event: dict, now: datetime) -> dict:
    values, timestamps = {}, []
    if event.get("closed") or event.get("active") is False:
        raise ValueError("Evento encerrado ou inativo")
    for market in event.get("markets", []):
        if market.get("closed") or market.get("active") is False:
            continue
        label = normalize(market.get("groupItemTitle") or market.get("question") or "")
        cid = IDS[0] if "flavio" in label else IDS[1] if "lula" in label else None
        if cid is None:
            continue
        outcomes, prices = market.get("outcomes", []), market.get("outcomePrices", [])
        if isinstance(outcomes, str): outcomes = json.loads(outcomes)
        if isinstance(prices, str): prices = json.loads(prices)
        stamp = market.get("updatedAt") or event.get("updatedAt")
        if not stamp:
            raise ValueError("Cotação sem data")
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if updated.tzinfo is None or not 0 <= (now - updated).total_seconds() <= 86400:
            raise ValueError("Cotação antiga")
        timestamps.append(stamp)
        for index, outcome in enumerate(outcomes):
            if str(outcome).lower() == "yes" and index < len(prices):
                values[cid] = float(prices[index]) * 100
    checked = _result(values)
    if not 95 <= sum(checked.values()) <= 101.1:
        raise ValueError("Evento não representa o confronto atual")
    return {"status": "ok", "values": checked, "updatedAt": max(timestamps), "url": MARKET_URL,
            "label": "Polymarket · sinal externo"}

def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Reconstruir com evidências salvas")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    today, stamp = now.astimezone(ZoneInfo("America/Sao_Paulo")).date(), now.isoformat().replace("+00:00", "Z")
    curated = json.loads((DATA / "runoff-curated.json").read_text("utf-8"))
    output = DATA / "runoff-dashboard.json"
    previous_file = output if output.exists() else DATA / "runoff-2026.json"
    previous = json.loads(previous_file.read_text("utf-8")) if previous_file.exists() else {}
    imported, sources = [], []
    market = {"status": "unavailable", "values": {}, "url": MARKET_URL}
    if not args.offline:
        import requests
        for kind, url in (("pollingdata", BBC_TABLE), ("polymarket", MARKET_API)):
            status = {"id": kind, "status": "unavailable", "checkedAt": stamp}
            try:
                response = requests.get(url, headers=UA, timeout=(8, 15))
                response.raise_for_status()
                if kind == "pollingdata":
                    imported = parse_bbc_runoff(response.text, today)
                    status["acceptedPolls"] = len(imported)
                else:
                    market = parse_market(response.json(), now)
                status["status"] = "ok"
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                status["error"] = str(exc)[:180]
            sources.append(status)
    else:
        sources = [{"id": "offline", "status": "saved", "checkedAt": stamp}]
    payload = build_payload(curated, {"runoff": imported}, stamp, today, previous, market, sources)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "utf-8")
    temporary.replace(output)
    # Mantém a leitura compatível com o APK 0.10 enquanto a nova versão é instalada.
    legacy = {k: payload[k] for k in ("generatedAt", "electionDate", "candidates", "polls", "pollCount", "instituteCount")}
    legacy["schemaVersion"] = 1
    legacy["methodology"] = "Pesquisas dos finalistas com coleta integral após 4/10; bases publicadas preservadas."
    (DATA / "runoff-2026.json").write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"Segundo turno: {payload['pollCount']} pesquisas, modelo {payload['model']['status']}, {len(payload['history'])} pontos históricos")

if __name__ == "__main__":
    main()
