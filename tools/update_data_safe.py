#!/usr/bin/env python3
"""Camada de validação e parsing seguro para os coletores eleitorais.

Também serve como ponto estável de execução do histórico v2 usado pelas curvas
reais de 5, 15 e 30 dias do aplicativo.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_data  # noqa: E402

# Evita aliases excessivamente curtos, que podem coincidir com texto editorial.
update_data.ALIASES["renan-santos"] = ["renan santos", "renan missao", "renan missão"]

LEADERS = {"lula", "flavio-bolsonaro"}
LEADER_ALIASES = {
    a.lower()
    for cid, aliases in update_data.ALIASES.items()
    if cid in LEADERS
    for a in aliases
}


def safe_percent_near(text, aliases):
    low = text.lower().replace("\xa0", " ")
    alias_set = {a.lower() for a in aliases}
    is_leader = bool(alias_set & LEADER_ALIASES)
    lo, hi = (20.0, 60.0) if is_leader else (0.0, 15.0)

    candidates = []
    for alias in aliases:
        pattern = re.escape(alias.lower())
        for found in re.finditer(pattern, low):
            chunk = low[found.start(): found.start() + 95]
            for pct in re.finditer(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", chunk):
                value = float(pct.group(1).replace(",", "."))
                if lo <= value <= hi:
                    candidates.append((pct.start(), value))
                    break
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x[0])[0][1]


update_data.parse_percent_near = safe_percent_near


def parse_candidates(segment):
    result = {}
    for cid, aliases in update_data.ALIASES.items():
        value = safe_percent_near(segment, aliases)
        if value is not None:
            result[cid] = value
    if not {"lula", "flavio-bolsonaro"}.issubset(result):
        raise ValueError("Trecho de 1º turno não contém os dois líderes")
    return result


def source_electiolab_first_round():
    url = "https://electiolab.com/pesquisas-presidenciais-2026"
    text = update_data.BeautifulSoup(update_data.fetch_text(url), "html.parser").get_text(" ", strip=True)
    low = text.lower()
    start = low.find("cenário atual")
    if start < 0:
        start = low.find("cenario atual")
    end = low.find("cenários de 2º turno", max(start, 0))
    if end < 0:
        end = low.find("cenarios de 2º turno", max(start, 0))
    if start < 0 or end <= start:
        raise ValueError("Não foi possível isolar o 1º turno no ElectioLab")
    return parse_candidates(text[start:end])


def source_bbc_first_round():
    url = "https://news.files.bbci.co.uk/include/vjamericas/1561-poll-tracker-brazil-2026/range-chart/portuguese/app/embed"
    text = update_data.BeautifulSoup(update_data.fetch_text(url), "html.parser").get_text(" ", strip=True)
    # A página contém 1º e 2º turno no mesmo HTML. O primeiro bloco termina na
    # primeira ocorrência de "Fonte:"/"Última atualização" antes do segundo bloco.
    low = text.lower()
    start = low.find("intenção de voto para presidente")
    if start < 0:
        start = low.find("intencao de voto para presidente")
    markers = [
        low.find("fonte:", max(start, 0)),
        low.find("última atualização", max(start, 0)),
        low.find("ultima atualização", max(start, 0)),
    ]
    markers = [m for m in markers if m > start]
    end = min(markers) if markers else -1
    if start < 0 or end <= start:
        raise ValueError("Não foi possível isolar o 1º turno na BBC/PollingData")
    return parse_candidates(text[start:end])


update_data.source_electiolab = source_electiolab_first_round
update_data.source_bbc_pollingdata = source_bbc_first_round

if __name__ == "__main__":
    update_data.main()
