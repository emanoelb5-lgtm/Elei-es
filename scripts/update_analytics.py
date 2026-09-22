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
import random
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
REFERENCE_SOURCES = [
    ("uol", "UOL · Agregador", "agregador de conferência · sem peso", "https://noticias.uol.com.br/eleicoes/agregador-de-pesquisas-eleitorais/"),
    ("electiolab", "ElectioLab", "agregador de conferência · sem peso", "https://electiolab.com/pesquisas-presidenciais-2026"),
    ("atlas", "AtlasIntel · pesquisas", "fonte primária de conferência · sem peso", "https://www.atlasintel.org/polls/exclusive-polls"),
]
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
NON_CANDIDATE_ALIASES = {
    "blankNullUndecided": [
        "branco/nulo/não sabe",
        "branco / nulo / não sabe",
        "brancos/nulos/indecisos",
        "brancos / nulos / indecisos",
        "blank/null/undecided",
    ],
    "otherCandidates": ["outros candidatos", "outras candidaturas", "outros", "others"],
    "blank": ["branco", "brancos", "blank"],
    "null": ["nulo", "nulos", "null"],
    "undecided": ["não sabe", "nao sabe", "indeciso", "indecisos", "undecided", "não respondeu", "nao respondeu"],
    "none": ["nenhum", "nenhuma", "nenhum deles", "nenhuma delas", "none"],
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


def non_candidate_for_label(label: str) -> str | None:
    low = norm(label)
    ordered = sorted(
        ((key, alias) for key, aliases in NON_CANDIDATE_ALIASES.items() for alias in aliases),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for key, alias in ordered:
        if norm(alias) in low:
            return key
    return None


def response_composition(polls: List[dict], target: date) -> dict:
    weighted = poll_weights(polls, target)
    if not weighted:
        return {
            "available": False,
            "candidateShare": None,
            "categories": {},
            "residualUnclassified": None,
            "pollCount": 0,
            "note": "Sem pesquisas elegíveis para compor respostas não atribuídas a candidatos.",
        }

    category_sums: Dict[str, float] = {}
    category_weights: Dict[str, float] = {}
    candidate_totals = []
    residual_totals = []

    for poll, weight in weighted:
        candidate_total = sum(float(v) for v in poll.get("values", {}).values())
        non_candidate = {
            key: float(value)
            for key, value in poll.get("nonCandidate", {}).items()
        }
        if 0 <= candidate_total <= 100:
            candidate_totals.append((candidate_total, weight))
            classified = sum(non_candidate.values())
            residual_totals.append((max(0.0, 100.0 - candidate_total - classified), weight))

        for key, value in non_candidate.items():
            category_sums[key] = category_sums.get(key, 0.0) + value * weight
            category_weights[key] = category_weights.get(key, 0.0) + weight

    total_weight = sum(weight for _, weight in candidate_totals)
    candidate_share = (
        sum(value * weight for value, weight in candidate_totals) / total_weight
        if total_weight > 0 else None
    )
    categories = {
        key: round(category_sums[key] / category_weights[key], 2)
        for key in category_sums
        if category_weights.get(key, 0.0) > 0
    }
    residual_weight = sum(weight for _, weight in residual_totals)
    residual = (
        sum(value * weight for value, weight in residual_totals) / residual_weight
        if residual_weight > 0 else None
    )

    return {
        "available": bool(categories) or candidate_share is not None,
        "candidateShare": round(candidate_share, 2) if candidate_share is not None else None,
        "categories": categories,
        "residualUnclassified": round(residual, 2) if residual is not None else None,
        "pollCount": len(weighted),
        "note": (
            "Categorias não candidatas são agregadas apenas quando a fonte as identifica. "
            "Residual não classificado não é tratado como indecisão."
        ),
    }


def sensitivity_analysis(polls: List[dict], target: date) -> dict:
    baseline = aggregate_first_round(polls, target)
    eligible = [
        p for p in polls
        if p["date"] <= target and (target - p["date"]).days <= LIVE_WINDOW_DAYS
    ]
    if not baseline["candidates"] or len(eligible) < 2:
        return {
            "status": "insufficient-data",
            "pollCount": len(eligible),
            "maxLeaveOneOutShift": None,
            "candidates": {},
            "note": "Dados insuficientes para análise de sensibilidade.",
        }

    by_candidate: Dict[str, dict] = {}
    global_max = 0.0
    for cid, values in baseline["candidates"].items():
        base = float(values["support"])
        variants = []
        for index in range(len(eligible)):
            reduced = eligible[:index] + eligible[index + 1:]
            alt = aggregate_first_round(reduced, target)["candidates"].get(cid)
            if alt is not None:
                variants.append(float(alt["support"]))

        recent14 = aggregate_first_round(
            [p for p in polls if p["date"] <= target and (target - p["date"]).days <= 14],
            target,
        )["candidates"].get(cid)

        if variants:
            low = min(variants)
            high = max(variants)
            max_shift = max(abs(v - base) for v in variants)
        else:
            low = high = base
            max_shift = 0.0

        global_max = max(global_max, max_shift)
        by_candidate[cid] = {
            "baseline": round(base, 2),
            "leaveOneOutLow": round(low, 2),
            "leaveOneOutHigh": round(high, 2),
            "maxLeaveOneOutShift": round(max_shift, 2),
            "support14Days": round(float(recent14["support"]), 2) if recent14 else None,
            "difference14Vs30": round(float(recent14["support"]) - base, 2) if recent14 else None,
        }

    level = "alta" if global_max <= 0.5 else "moderada" if global_max <= 1.5 else "baixa"
    return {
        "status": "ok",
        "pollCount": len(eligible),
        "maxLeaveOneOutShift": round(global_max, 2),
        "stability": level,
        "candidates": by_candidate,
        "note": (
            "Teste de robustez: mede a mudança do agregado ao retirar uma pesquisa por vez "
            "e ao comparar janelas de 14 e 30 dias. Não é previsão de resultado."
        ),
    }


def influence_analysis(polls: List[dict], target: date, peer_window_days: int = 10) -> dict:
    """Mede influência mecânica e desvio entre pesquisas contemporâneas.

    Influência = quanto o agregado muda ao remover uma observação ou um instituto.
    Desvio entre pares = distância da pesquisa para levantamentos próximos de outros
    institutos. Nenhum desses diagnósticos altera automaticamente o agregado.
    """
    eligible = [
        p for p in polls
        if p["date"] <= target and (target - p["date"]).days <= LIVE_WINDOW_DAYS
    ]
    baseline = aggregate_first_round(eligible, target)
    if len(eligible) < 3 or not baseline["candidates"]:
        return {
            "status": "insufficient-data",
            "pollCount": len(eligible),
            "instituteCount": len({norm(p.get("institute", "")) for p in eligible}),
            "polls": [],
            "institutes": [],
            "atypicalThreshold": None,
            "note": "Dados insuficientes para diagnóstico de influência.",
        }

    baseline_support = {
        cid: float(values["support"])
        for cid, values in baseline["candidates"].items()
    }

    def summarize_shift(alternative: dict) -> tuple[dict, float, float]:
        deltas = {}
        for cid, base in baseline_support.items():
            alt = alternative.get("candidates", {}).get(cid)
            if alt is None:
                continue
            deltas[cid] = float(alt["support"]) - base
        absolute = [abs(value) for value in deltas.values()]
        return (
            {cid: round(value, 2) for cid, value in deltas.items()},
            round(max(absolute), 2) if absolute else 0.0,
            round(sum(absolute) / len(absolute), 2) if absolute else 0.0,
        )

    poll_rows = []
    raw_peer_deviations = []
    for index, poll in enumerate(eligible):
        reduced = eligible[:index] + eligible[index + 1:]
        alternative = aggregate_first_round(reduced, target)
        deltas, max_shift, mean_shift = summarize_shift(alternative)

        peer_deviations = []
        peer_comparisons = 0
        for cid, observed in poll.get("values", {}).items():
            peers = [
                other for j, other in enumerate(eligible)
                if j != index
                and norm(other.get("institute", "")) != norm(poll.get("institute", ""))
                and abs((other["date"] - poll["date"]).days) <= peer_window_days
                and cid in other.get("values", {})
            ]
            peer_institutes = {norm(p.get("institute", "")) for p in peers}
            if len(peers) < 2 or len(peer_institutes) < 2:
                continue

            weighted_values = []
            for peer in peers:
                distance = abs((peer["date"] - poll["date"]).days)
                recency = math.exp(-distance / 5.0)
                sample_factor = min(
                    max(math.sqrt(max(peer.get("sample", 300), 300) / 2000.0), 0.65),
                    1.60,
                )
                weighted_values.append((float(peer["values"][cid]), recency * sample_factor))

            total_weight = sum(weight for _, weight in weighted_values)
            if total_weight <= 0:
                continue
            peer_mean = sum(value * weight for value, weight in weighted_values) / total_weight
            peer_deviations.append(abs(float(observed) - peer_mean))
            peer_comparisons += 1

        mean_peer_deviation = (
            sum(peer_deviations) / len(peer_deviations)
            if peer_deviations else None
        )
        if mean_peer_deviation is not None:
            raw_peer_deviations.append(mean_peer_deviation)

        poll_rows.append({
            "date": poll["date"].isoformat(),
            "institute": poll.get("institute", "Instituto não identificado"),
            "sample": poll.get("sample", 0),
            "method": poll.get("method", "não identificado"),
            "registration": poll.get("registration"),
            "verifiedTse": bool(poll.get("verifiedTse")),
            "maxAbsoluteShift": max_shift,
            "meanAbsoluteShift": mean_shift,
            "candidateShifts": deltas,
            "peerComparisonCount": peer_comparisons,
            "meanPeerDeviation": round(mean_peer_deviation, 2) if mean_peer_deviation is not None else None,
        })

    threshold = None
    if len(raw_peer_deviations) >= 5:
        ordered = sorted(raw_peer_deviations)
        middle = len(ordered) // 2
        med = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
        deviations = sorted(abs(value - med) for value in raw_peer_deviations)
        middle_dev = len(deviations) // 2
        mad = (
            deviations[middle_dev]
            if len(deviations) % 2
            else (deviations[middle_dev - 1] + deviations[middle_dev]) / 2.0
        )
        threshold = med + max(2.5 * mad, 1.0)

    for row in poll_rows:
        peer_value = row["meanPeerDeviation"]
        row["atypicalSignal"] = bool(
            threshold is not None
            and peer_value is not None
            and row["peerComparisonCount"] >= 2
            and float(peer_value) >= threshold
        )

    institutes = []
    institute_names = sorted({p.get("institute", "Instituto não identificado") for p in eligible}, key=norm)
    for institute in institute_names:
        reduced = [
            poll for poll in eligible
            if norm(poll.get("institute", "")) != norm(institute)
        ]
        alternative = aggregate_first_round(reduced, target)
        deltas, max_shift, mean_shift = summarize_shift(alternative)
        members = [p for p in eligible if norm(p.get("institute", "")) == norm(institute)]
        institutes.append({
            "institute": institute,
            "pollCount": len(members),
            "maxAbsoluteShift": max_shift,
            "meanAbsoluteShift": mean_shift,
            "candidateShifts": deltas,
        })

    return {
        "status": "ok",
        "pollCount": len(eligible),
        "instituteCount": len(institutes),
        "peerWindowDays": peer_window_days,
        "atypicalThreshold": round(threshold, 2) if threshold is not None else None,
        "polls": poll_rows,
        "institutes": institutes,
        "correctionApplied": False,
        "note": (
            "Influência mede mudança mecânica do agregado ao retirar dados. "
            "Sinal atípico usa desvio robusto entre pesquisas contemporâneas e não implica erro, viés ou fraude."
        ),
    }


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


def parse_metadata(text: str) -> dict:
    """Extrai instituto, amostra e método da célula compacta do PollingData."""
    cleaned = re.sub(
        r"^\s*\d{1,2}/\d{1,2}\s*-\s*\d{1,2}/\d{1,2}\s+",
        "",
        text or "",
    ).strip()
    marker = re.search(
        r"\s(\d{1,3}(?:\.\d{3})+|\d{3,6})\s+"
        r"(?=(?:Presencial|Telef[oô]nica|Online|Digital|H[íi]brida|URA|IVR|CATI))",
        cleaned,
        re.IGNORECASE,
    )
    if marker is None:
        marker = re.search(r"\s(\d{1,3}(?:\.\d{3})+|\d{3,6})\s+", cleaned)

    if marker is None:
        return {
            "institute": "Instituto não identificado",
            "sample": 2000,
            "method": "não identificado",
        }

    institute = cleaned[: marker.start()].strip() or "Instituto não identificado"
    sample = parse_sample(marker.group(1))
    tail = cleaned[marker.end():].strip()
    margin = re.search(r"\s\d{1,2}(?:[\.,]\d{1,2})?\s*p\.?p\.?", tail, re.IGNORECASE)
    method = (tail[: margin.start()] if margin else tail).strip()
    method = re.sub(r"\s+\d{1,3}%\s*$", "", method).strip()
    return {
        "institute": institute,
        "sample": sample,
        "method": method or "não identificado",
    }


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
        non_candidate_columns: Dict[int, str] = {}
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
            else:
                response_key = non_candidate_for_label(label)
                if response_key:
                    non_candidate_columns[i] = response_key
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
            non_candidate: Dict[str, float] = {}
            for i, cid in candidate_columns.items():
                if i < len(cells):
                    value = parse_pct(cells[i])
                    if value is not None:
                        values[cid] = value
            for i, response_key in non_candidate_columns.items():
                if i < len(cells):
                    response_value = parse_pct(cells[i])
                    if response_value is not None:
                        non_candidate[response_key] = response_value
            if len(values) < 2:
                continue
            registration = None
            if registration_index is not None and registration_index < len(cells):
                registration = parse_registration([cells[registration_index]])
            if registration is None:
                registration = parse_registration(cells)
            metadata = parse_metadata(cells[0])
            institute = metadata["institute"]
            sample = metadata["sample"]
            method = metadata["method"]
            polls.append({
                "date": end_date,
                "institute": institute,
                "sample": sample,
                "method": method,
                "registration": registration,
                "values": values,
                "nonCandidate": non_candidate,
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
    """Mantém uma observação por pesquisa registrada e escolhe o cenário mais completo."""
    chosen: Dict[tuple, dict] = {}
    for original in polls:
        poll = dict(original)
        reg = (poll.get("registration") or "").upper()
        if reg:
            key = ("tse", reg)
        else:
            key = (
                "content",
                norm(poll.get("institute", "")),
                poll["date"].isoformat(),
                poll.get("sample", 0),
                tuple(sorted((k, round(v, 2)) for k, v in poll["values"].items())),
                tuple(sorted((k, round(v, 2)) for k, v in poll.get("nonCandidate", {}).items())),
            )

        current = chosen.get(key)
        score = (len(poll.get("values", {})), poll.get("sample", 0))
        current_score = (
            (len(current.get("values", {})), current.get("sample", 0))
            if current else (-1, -1)
        )
        if current is None or score > current_score:
            poll["verifiedTse"] = bool(reg and reg in tse_ids)
            chosen[key] = poll

    return sorted(chosen.values(), key=lambda p: (p["date"], norm(p.get("institute", ""))))


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
    methods = {norm(p.get("method", "não identificado")) for p in used}
    registrations = sum(1 for p in used if p.get("registration"))
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
        "methodCount": len(methods),
        "registrationCount": registrations,
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
    composition = response_composition(polls, target)
    decided_total = sum(c["support"] for c in candidates)
    normalized = {
        c["id"]: round(100.0 * c["support"] / decided_total, 2)
        for c in candidates
    } if decided_total > 0 else {}
    return {
        "id": "-vs-".join(sorted(ids)),
        "label": f"{NAMES.get(ids[0], ids[0])} × {NAMES.get(ids[1], ids[1])}",
        "candidates": candidates,
        "pollCount": len(used),
        "instituteCount": len({norm(p["institute"]) for p in used}),
        "responseComposition": composition,
        "pairNormalized": normalized,
        "pairNormalizationNote": "Normalização apenas entre os dois candidatos exibidos; não é projeção de votos válidos.",
    }


def fetch_reference_source(source_id: str, label: str, source_type: str, url: str) -> dict:
    source = {
        "id": source_id,
        "label": label,
        "type": source_type,
        "status": "fallback",
        "updatedAt": None,
        "url": url,
    }
    try:
        response = requests.get(url, headers=UA, timeout=20)
        response.raise_for_status()
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        low = norm(text)
        if not any(norm(alias) in low for alias in ALIASES["lula"]):
            raise RuntimeError("conteúdo eleitoral esperado não localizado")
        if not any(norm(alias) in low for alias in ALIASES["flavio-bolsonaro"]):
            raise RuntimeError("segundo candidato de referência não localizado")
        source["status"] = "ok"
        source["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        date_match = re.search(
            r"(?:atualizad[oa]\s+em|última pesquisa indexada[:\s]+)"
            r"\s*(\d{1,2}\s+de\s+[a-zç]+\s+de\s+2026|\d{1,2}/\d{1,2}/2026)",
            text,
            re.IGNORECASE,
        )
        if date_match:
            source["pageFreshness"] = date_match.group(1)
        return source
    except Exception as exc:
        source["error"] = str(exc)[:180]
        return source


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


def _weighted_peer_mean(peers: List[dict], cid: str, reference_date: date) -> tuple[float, int] | None:
    usable = []
    institutes = set()
    for peer in peers:
        if cid not in peer.get("values", {}):
            continue
        distance = abs((peer["date"] - reference_date).days)
        recency = math.exp(-distance / 5.0)
        sample_factor = min(max(math.sqrt(max(peer.get("sample", 300), 300) / 2000.0), 0.65), 1.60)
        weight = recency * sample_factor
        usable.append((float(peer["values"][cid]), weight))
        institutes.add(norm(peer.get("institute", "")))
    if len(usable) < 2 or len(institutes) < 2:
        return None
    total = sum(weight for _, weight in usable)
    if total <= 0:
        return None
    return sum(value * weight for value, weight in usable) / total, len(institutes)


def build_source_diagnostics(polls: List[dict], peer_window_days: int = 10) -> dict:
    """Compara cada levantamento com pesquisas contemporâneas de OUTROS institutos.

    É um diagnóstico descritivo. Os resíduos não alteram automaticamente o peso
    nem corrigem a média corrente.
    """
    residuals = []
    ordered = sorted(polls, key=lambda p: (p["date"], norm(p.get("institute", ""))))
    for index, poll in enumerate(ordered):
        peers = [
            other
            for j, other in enumerate(ordered)
            if j != index
            and norm(other.get("institute", "")) != norm(poll.get("institute", ""))
            and abs((other["date"] - poll["date"]).days) <= peer_window_days
        ]
        for cid, value in poll.get("values", {}).items():
            peer = _weighted_peer_mean(peers, cid, poll["date"])
            if peer is None:
                continue
            baseline, peer_institutes = peer
            residuals.append({
                "institute": poll.get("institute", "Instituto não identificado"),
                "method": poll.get("method", "não identificado"),
                "candidateId": cid,
                "candidateName": NAMES.get(cid, cid.replace("-", " ").title()),
                "date": poll["date"].isoformat(),
                "registration": poll.get("registration"),
                "residual": float(value) - baseline,
                "absoluteResidual": abs(float(value) - baseline),
                "peerInstitutes": peer_institutes,
            })

    def summarize(field: str) -> List[dict]:
        grouped: Dict[str, List[dict]] = {}
        for row in residuals:
            grouped.setdefault(str(row[field]), []).append(row)

        summaries = []
        for label in sorted(grouped, key=lambda s: norm(s)):
            rows = grouped[label]
            registrations = {r["registration"] for r in rows if r.get("registration")}
            dates = {r["date"] for r in rows}
            mean_abs = sum(r["absoluteResidual"] for r in rows) / len(rows)
            mean_signed = sum(r["residual"] for r in rows) / len(rows)
            variance = sum((r["residual"] - mean_signed) ** 2 for r in rows) / max(len(rows), 1)
            candidate_offsets = {}
            by_candidate: Dict[str, List[dict]] = {}
            for row in rows:
                by_candidate.setdefault(row["candidateId"], []).append(row)
            for cid in sorted(by_candidate, key=lambda key: NAMES.get(key, key).lower()):
                cr = by_candidate[cid]
                if len(cr) < 3:
                    continue
                candidate_offsets[cid] = {
                    "name": NAMES.get(cid, cid.replace("-", " ").title()),
                    "comparisons": len(cr),
                    "meanOffset": round(sum(x["residual"] for x in cr) / len(cr), 2),
                    "meanAbsoluteDeviation": round(sum(x["absoluteResidual"] for x in cr) / len(cr), 2),
                }
            summaries.append({
                "label": label,
                "pollCount": len(registrations) if registrations else len(dates),
                "comparisonCount": len(rows),
                "meanOffset": round(mean_signed, 2),
                "meanAbsoluteDeviation": round(mean_abs, 2),
                "residualSd": round(math.sqrt(max(variance, 0.0)), 2),
                "candidateOffsets": candidate_offsets,
            })
        return summaries

    return {
        "peerWindowDays": peer_window_days,
        "comparisonCount": len(residuals),
        "institutes": summarize("institute"),
        "methods": summarize("method"),
    }


def simple_equal_average(polls: List[dict], target: date) -> dict:
    eligible = [
        p for p in polls
        if p["date"] <= target and (target - p["date"]).days <= LIVE_WINDOW_DAYS
    ]
    ids = sorted(set().union(*(p["values"].keys() for p in eligible))) if eligible else []
    candidates = {}
    for cid in ids:
        values = [float(p["values"][cid]) for p in eligible if cid in p.get("values", {})]
        if values:
            candidates[cid] = sum(values) / len(values)
    return {
        "candidates": candidates,
        "pollCount": len(eligible),
        "instituteCount": len({norm(p.get("institute", "")) for p in eligible}),
    }


def percentile(values: List[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = min(max(q, 0.0), 1.0) * (len(ordered) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def bootstrap_current_support(
    polls: List[dict],
    target: date,
    draws: int = 500,
) -> dict:
    eligible = [
        p for p in polls
        if p["date"] <= target and (target - p["date"]).days <= LIVE_WINDOW_DAYS
    ]
    if len(eligible) < 3:
        return {
            "status": "insufficient-data",
            "draws": 0,
            "candidates": {},
        }

    # Semente determinística por data e conteúdo básico da janela para que duas
    # execuções com os mesmos dados produzam os mesmos percentis.
    fingerprint = sum(
        int(p["date"].strftime("%Y%m%d"))
        + int(p.get("sample", 0))
        + sum(int(round(float(v) * 100)) for v in p.get("values", {}).values())
        for p in eligible
    )
    rng = random.Random(fingerprint)
    series: Dict[str, List[float]] = {}

    for _ in range(draws):
        sample = [eligible[rng.randrange(len(eligible))] for _ in range(len(eligible))]
        aggregate = aggregate_first_round(sample, target)
        for cid, values in aggregate.get("candidates", {}).items():
            series.setdefault(cid, []).append(float(values["support"]))

    candidates = {}
    for cid, values in series.items():
        if len(values) < max(50, draws // 4):
            continue
        candidates[cid] = {
            "p10": round(percentile(values, 0.10) or 0.0, 2),
            "p25": round(percentile(values, 0.25) or 0.0, 2),
            "p50": round(percentile(values, 0.50) or 0.0, 2),
            "p75": round(percentile(values, 0.75) or 0.0, 2),
            "p90": round(percentile(values, 0.90) or 0.0, 2),
            "drawCount": len(values),
        }

    return {
        "status": "ok" if candidates else "insufficient-data",
        "draws": draws,
        "candidates": candidates,
    }


def advanced_uncertainty(
    polls: List[dict],
    target: date,
    aggregate: dict,
    validation: dict,
) -> dict:
    bootstrap = bootstrap_current_support(polls, target)
    empirical_q80 = validation.get("absoluteErrorQuantiles", {}).get("q80")
    empirical_q90 = validation.get("absoluteErrorQuantiles", {}).get("q90")

    candidates = {}
    for cid, values in aggregate.get("candidates", {}).items():
        support = float(values["support"])
        model_low = float(values["low"])
        model_high = float(values["high"])
        model_half = max(support - model_low, model_high - support)

        boot = bootstrap.get("candidates", {}).get(cid)
        if boot:
            bootstrap_low = float(boot["p10"])
            bootstrap_high = float(boot["p90"])
            bootstrap_half = max(support - bootstrap_low, bootstrap_high - support, 0.0)
        else:
            bootstrap_low = bootstrap_high = None
            bootstrap_half = 0.0

        # O erro empírico usa a distribuição de erro absoluto contra a próxima
        # pesquisa publicada. Ele funciona como piso de reprodução, não como
        # probabilidade de resultado eleitoral.
        empirical_half = float(empirical_q80) if empirical_q80 is not None else 0.0
        advanced_half = max(model_half, bootstrap_half, empirical_half, 0.6)

        candidates[cid] = {
            "support": round(support, 2),
            "modelLow": round(model_low, 2),
            "modelHigh": round(model_high, 2),
            "bootstrapP10": round(bootstrap_low, 2) if bootstrap_low is not None else None,
            "bootstrapP50": round(float(boot["p50"]), 2) if boot else None,
            "bootstrapP90": round(bootstrap_high, 2) if bootstrap_high is not None else None,
            "empiricalErrorQ80": round(empirical_half, 2) if empirical_q80 is not None else None,
            "advancedLow": round(max(0.0, support - advanced_half), 2),
            "advancedHigh": round(min(100.0, support + advanced_half), 2),
            "advancedHalfWidth": round(advanced_half, 2),
        }

    return {
        "status": "ok" if candidates else "insufficient-data",
        "bootstrapDraws": bootstrap.get("draws", 0),
        "empiricalErrorQuantileUsed": "q80",
        "empiricalErrorQ80": round(float(empirical_q80), 2) if empirical_q80 is not None else None,
        "empiricalErrorQ90": round(float(empirical_q90), 2) if empirical_q90 is not None else None,
        "candidates": candidates,
        "note": (
            "Faixa avançada combina a incerteza analítica existente, a variabilidade "
            "de reamostragem das pesquisas e um piso baseado no erro absoluto empírico "
            "contra a próxima pesquisa publicada. É uma faixa de incerteza da leitura atual, "
            "não probabilidade de vitória nem previsão do resultado da eleição."
        ),
    }


def rolling_validation(polls: List[dict], minimum_training_polls: int = 4) -> dict:
    """Valida retrospectivamente o agregado contra a próxima pesquisa publicada.

    O alvo é a própria pesquisa seguinte, não o resultado da eleição. O teste
    também compara a ponderação atual com uma média simples das mesmas pesquisas.
    """
    weighted_errors = []
    simple_errors = []
    covered = 0
    cases = 0
    ordered = sorted(polls, key=lambda p: (p["date"], norm(p.get("institute", ""))))

    for heldout in ordered:
        training = [p for p in ordered if p["date"] < heldout["date"]]
        if not training:
            continue
        target = heldout["date"] - timedelta(days=1)
        aggregate = aggregate_first_round(training, target)
        simple = simple_equal_average(training, target)
        if aggregate["pollCount"] < minimum_training_polls or aggregate["instituteCount"] < 2:
            continue

        comparable = 0
        for cid, observed in heldout.get("values", {}).items():
            estimate = aggregate["candidates"].get(cid)
            simple_estimate = simple["candidates"].get(cid)
            if estimate is None or simple_estimate is None:
                continue
            weighted_error = abs(float(observed) - float(estimate["support"]))
            simple_error = abs(float(observed) - float(simple_estimate))
            weighted_errors.append(weighted_error)
            simple_errors.append(simple_error)
            comparable += 1
            if estimate["low"] <= float(observed) <= estimate["high"]:
                covered += 1
        if comparable >= 2:
            cases += 1

    if not weighted_errors:
        return {
            "status": "insufficient-data",
            "caseCount": 0,
            "comparisonCount": 0,
            "meanAbsoluteError": None,
            "medianAbsoluteError": None,
            "simpleMeanAbsoluteError": None,
            "errorDifferenceVsSimple": None,
            "intervalCoverage": None,
            "absoluteErrorQuantiles": {},
        }

    sorted_errors = sorted(weighted_errors)
    middle = len(sorted_errors) // 2
    if len(sorted_errors) % 2:
        median = sorted_errors[middle]
    else:
        median = (sorted_errors[middle - 1] + sorted_errors[middle]) / 2.0

    weighted_mae = sum(weighted_errors) / len(weighted_errors)
    simple_mae = sum(simple_errors) / len(simple_errors)
    absolute_error_quantiles = {
        "q50": round(percentile(weighted_errors, 0.50), 2),
        "q68": round(percentile(weighted_errors, 0.68), 2),
        "q80": round(percentile(weighted_errors, 0.80), 2),
        "q90": round(percentile(weighted_errors, 0.90), 2),
        "q95": round(percentile(weighted_errors, 0.95), 2),
    }

    return {
        "status": "ok",
        "caseCount": cases,
        "comparisonCount": len(weighted_errors),
        "meanAbsoluteError": round(weighted_mae, 2),
        "medianAbsoluteError": round(median, 2),
        "simpleMeanAbsoluteError": round(simple_mae, 2),
        "errorDifferenceVsSimple": round(weighted_mae - simple_mae, 2),
        "intervalCoverage": round(100.0 * covered / len(weighted_errors), 1),
        "absoluteErrorQuantiles": absolute_error_quantiles,
        "target": "próxima pesquisa publicada",
        "note": "Validação interna do agregador; não mede acerto do resultado eleitoral.",
    }


def build_calibration_payload(polls: List[dict], now: datetime) -> dict:
    source_diagnostics = build_source_diagnostics(polls)
    validation = rolling_validation(polls)
    return {
        "schemaVersion": 1,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "correctionApplied": False,
        "correctionPolicy": "diagnóstico somente; nenhum ajuste por instituto ou método altera a média atual",
        "sourceDiagnostics": source_diagnostics,
        "rollingValidation": validation,
        "historicalElectionBacktest": {
            "status": "not-applied",
            "correctionApplied": False,
            "note": "Ajustes históricos só serão considerados após existir uma base histórica reproduzível e validada separadamente.",
        },
    }


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
        "method": poll.get("method", "não identificado"),
        "registration": poll.get("registration"),
        "verifiedTse": bool(poll.get("verifiedTse")),
        "round": round_name,
        "candidates": {k: round(v, 2) for k, v in poll["values"].items()},
        "nonCandidate": {k: round(v, 2) for k, v in poll.get("nonCandidate", {}).items()},
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
    reference_sources = [
        fetch_reference_source(source_id, label, source_type, url)
        for source_id, label, source_type, url in REFERENCE_SOURCES
    ]

    agg = aggregate_first_round(first_round, now.date())
    if not agg["candidates"]:
        raise SystemExit("Nenhuma pesquisa de primeiro turno disponível para a leitura.")

    calibration = build_calibration_payload(first_round, now)
    uncertainty = advanced_uncertainty(
        first_round,
        now.date(),
        agg,
        calibration["rollingValidation"],
    )
    composition = response_composition(first_round, now.date())
    sensitivity = sensitivity_analysis(first_round, now.date())
    influence = influence_analysis(first_round, now.date())
    (DATA / "calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )

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
        uncertainty_row = uncertainty.get("candidates", {}).get(cid, {})
        candidates.append({
            "id": cid,
            "name": NAMES.get(cid, cid.replace("-", " ").title()),
            "pollingSupport": round(support, 2),
            "intervalLow": round(float(uncertainty_row.get("advancedLow", values["low"])), 2),
            "intervalHigh": round(float(uncertainty_row.get("advancedHigh", values["high"])), 2),
            "modelIntervalLow": round(values["low"], 2),
            "modelIntervalHigh": round(values["high"], 2),
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
        "methodCount": agg["methodCount"],
        "registrationCount": agg["registrationCount"],
        "verifiedTseCount": agg["verifiedTseCount"],
        "averageAgeDays": round(agg["averageAgeDays"], 1),
        "effectivePolls": round(agg["effectivePolls"], 1),
        "confidence": quality_label(agg),
    }

    snapshot = {
        "schemaVersion": 6,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "electionDate": ELECTION_DATE.isoformat(),
        "daysToElection": max((ELECTION_DATE - now.date()).days, 0),
        "quality": quality,
        "sources": [polling_source, tse_source, *reference_sources, market_source],
        "candidates": candidates,
        "runoffScenarios": runoff,
        "responseComposition": composition,
        "sensitivity": sensitivity,
        "influence": influence,
        "uncertainty": uncertainty,
        "methodology": {
            "primaryUnit": "pesquisa individual",
            "windowDays": LIVE_WINDOW_DAYS,
            "deduplication": "registro TSE; fallback por instituto/data/amostra/resultados",
            "weighting": "decaimento temporal + tamanho amostral + controle de repetição por instituto",
            "uncertainty": "faixa avançada = intervalo analítico + bootstrap das pesquisas + piso de erro empírico q80",
            "marketUse": "informativo; não entra na média de pesquisas",
            "responseComposition": "categorias não candidatas somente quando identificadas pela fonte; residual não classificado não é indecisão",
            "sensitivity": "leave-one-out por pesquisa + comparação de janelas de 14 e 30 dias; informativo, sem ajuste automático",
            "influence": "remoção de uma pesquisa ou de um instituto + desvio robusto entre pares contemporâneos; diagnóstico apenas",
        },
        "note": "Leitura estatística de pesquisas públicas. Intervalos e testes de sensibilidade expressam incerteza do agregador e não garantem resultado eleitoral.",
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
