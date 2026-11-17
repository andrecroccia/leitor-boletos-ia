"""Funcoes pequenas usadas em varios lugares."""
import os
import re
from pathlib import Path


def so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def br_para_float(s: str) -> float:
    """'1.068,30' -> 1068.3"""
    return float(s.replace(".", "").replace(",", "."))


def brl(v: float) -> str:
    """1068.3 -> '1.068,30'"""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_env(raiz: Path):
    """Le o arquivo .env (CHAVE=valor) sem precisar de biblioteca extra.
    Variaveis ja definidas no sistema tem prioridade."""
    arq = raiz / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
