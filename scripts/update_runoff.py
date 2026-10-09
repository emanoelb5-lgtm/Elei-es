#!/usr/bin/env python3
"""Publica somente pesquisas do segundo turno presidencial realizadas após 4/10.

Os levantamentos curados têm fonte primária e base percentual explícita. Os
levantamentos novos da tabela BBC entram com a base marcada como não informada
quando não é possível distingui-la sem a documentação original. Não calculamos
uma média entre votos totais e votos válidos nem reutilizamos simulações antigas.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FINALISTS = frozenset({"flavio-bolsonaro", "lula"})
START = date(2026, 10, 5)
BBC_TABLE = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/table/portuguese/app/amp"


def _result(values: dict) -> dict:
    if set(values) != FINALISTS:
        raise ValueError("O levantamento precisa conter apenas os dois finalistas")
    parsed = {key: float(value) for key, value in values.items()}
    if any(value < 0 or value > 100 for value in parsed.values()):
        raise ValueError("Percentual fora do intervalo 0–100")
    if sum(parsed.values()) > 100.5:
        raise ValueError("Percentuais incompatíveis")
    return parsed


def _key(poll: dict) -> str:
    registration = (poll.get("registration") or "").strip().upper()
    if registration:
        return registration
    return "|".join((poll["fieldworkEnd"], poll["institute"].lower(), str(poll["sample"])))


def build_payload(curated: dict, source: dict, generated_at: str, today: date) -> dict:
    if curated.get("electionDate") != "2026-10-25":
        raise ValueError("Data do segundo turno inesperada")
    candidates = curated.get("candidates", [])
    if {row.get("id") for row in candidates} != FINALISTS or len(candidates) != 2:
        raise ValueError("Finalistas inesperados")

    selected: dict[str, dict] = {}
    for row in curated.get("polls", []):
        end = date.fromisoformat(row["fieldworkEnd"])
        if not START <= end <= today:
            raise ValueError("Pesquisa curada fora do período do segundo turno")
        basis = row["basis"]
        if basis not in ("total", "valid"):
            raise ValueError("Base percentual curada não identificada")
        result = _result(row["result"])
        valid = _result(row["validResult"]) if row.get("validResult") else {}
        if basis == "valid" and abs(sum(result.values()) - 100) > 1.1:
            raise ValueError("Votos válidos não somam aproximadamente 100%")
        if basis == "total" and valid and abs(sum(valid.values()) - 100) > 1.1:
            raise ValueError("Votos válidos publicados não somam aproximadamente 100%")
        if not row.get("sourceUrl", "").startswith("https://") or row["sample"] <= 0:
            raise ValueError("Fonte ou amostra curada inválida")
        selected[_key(row)] = {
            **row,
            "result": result,
            "validResult": valid,
            "origin": "fonte primária conferida",
        }

    for row in source.get("runoff", []):
        try:
            end = date.fromisoformat(row["date"])
            if not START <= end <= today or set(row.get("candidates", {})) != FINALISTS:
                continue
            result = _result(row["candidates"])
            imported = {
                "id": row.get("registration") or f"{row['date']}-{row['institute']}-{row['sample']}",
                "institute": row["institute"],
                "fieldworkEnd": row["date"],
                "publishedAt": f"{row['date']}T00:00:00-03:00",
                "sample": int(row["sample"]),
                "method": row.get("method", "Não informado"),
                "registration": row.get("registration"),
                "verifiedTse": bool(row.get("verifiedTse")),
                "basis": "unspecified",
                "result": result,
                "validResult": {},
                "nonCandidate": row.get("nonCandidate", {}),
                "sourceUrl": BBC_TABLE,
                "sourceLabel": "BBC / PollingData",
                "origin": "tabela pública; base percentual a conferir",
            }
            if imported["sample"] > 0:
                selected.setdefault(_key(imported), imported)
        except (KeyError, TypeError, ValueError):
            continue

    polls = sorted(
        selected.values(),
        key=lambda row: (row["fieldworkEnd"], row["publishedAt"], row["institute"]),
        reverse=True,
    )
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "electionDate": curated["electionDate"],
        "candidates": candidates,
        "polls": polls,
        "pollCount": len(polls),
        "instituteCount": len({row["institute"].lower() for row in polls}),
        "methodology": "Somente levantamentos do confronto entre os finalistas após 4/10/2026. Percentuais totais e válidos são identificados separadamente; sem agregação entre bases distintas e sem previsão de resultado.",
    }


def main() -> None:
    curated = json.loads((DATA / "runoff-curated.json").read_text("utf-8"))
    source = json.loads((DATA / "polls.json").read_text("utf-8"))
    now = datetime.now(timezone.utc)
    payload = build_payload(curated, source, now.isoformat().replace("+00:00", "Z"), now.date())
    (DATA / "runoff-2026.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(f"Segundo turno: {payload['pollCount']} pesquisas de {payload['instituteCount']} institutos")


if __name__ == "__main__":
    main()
