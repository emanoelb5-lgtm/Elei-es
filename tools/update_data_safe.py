#!/usr/bin/env python3
"""Camada de validação para o coletor principal."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_data  # noqa: E402

# Reduz aliases ambíguos e substitui o parser por uma versão que procura
# ocorrências plausíveis dentro de uma janela curta ao redor do nome.
update_data.ALIASES["renan-santos"] = ["renan santos", "renan missao", "renan missão"]

LEADERS = {"lula", "flavio-bolsonaro"}
MINOR_ALIASES = {
    a.lower()
    for cid, aliases in update_data.ALIASES.items()
    if cid not in LEADERS
    for a in aliases
}
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
            # Janela curta evita capturar percentuais de outro candidato ou
            # de um parágrafo editorial posterior.
            chunk = low[found.start(): found.start() + 95]
            for pct in re.finditer(r"(\d{1,2}(?:[\.,]\d{1,2})?)\s*%", chunk):
                value = float(pct.group(1).replace(",", "."))
                if lo <= value <= hi:
                    candidates.append((pct.start(), value))
                    break
    if not candidates:
        return None
    # O percentual mais próximo do nome é o mais provável de pertencer ao
    # cartão/tabela daquele candidato.
    return sorted(candidates, key=lambda x: x[0])[0][1]


update_data.parse_percent_near = safe_percent_near

if __name__ == "__main__":
    update_data.main()
