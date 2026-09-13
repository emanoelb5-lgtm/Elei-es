#!/usr/bin/env python3
"""Camada de validação para o coletor principal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_data  # noqa: E402

# Evita correspondências ambíguas: o apelido curto "Renan" apareceu em texto
# editorial antes do valor correto e gerou um falso 23,8% na primeira execução.
update_data.ALIASES["renan-santos"] = ["renan santos"]

if __name__ == "__main__":
    update_data.main()
