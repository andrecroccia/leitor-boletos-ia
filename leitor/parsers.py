"""Parsers em CODIGO para os layouts que ja conhecemos.

Codigo e gratis, rapido e sempre da a mesma resposta. Por isso, quando o
layout e conhecido, ele tem prioridade sobre a IA.

Para ensinar um layout novo ao programa: escreva uma funcao que recebe a
lista de paginas e devolve o dicionario no formato abaixo, e registre-a em
PARSERS com uma "assinatura" (regex que identifica o layout).

Formato (o mesmo que a IA devolve):
    {
      "operadora": str, "apolice": str, "valor_total": float,
      "cnpj_pagador": str,
      "subfaturas": [{"sub": str, "cnpj": str, "valor": float}, ...]
    }
"""
import re

from .pdf import tem_dados_pessoais
from .util import br_para_float


def parser_sorriso_pleno(paginas: list[str]) -> dict:
    p1 = paginas[0]
    apolice = re.search(r"Apolice:\s*(\d+)", p1).group(1)
    total = br_para_float(re.search(r"valor de R\$\s*([\d.,]+)", p1).group(1))
    pagador = re.search(r"CNPJ:\s*([\d./-]+)", p1).group(1)

    subs = []
    for pag in paginas[1:]:
        if tem_dados_pessoais(pag):
            continue
        cab = re.search(r"^(\d{3}) - ", pag, re.MULTILINE)
        tot = re.search(r"TOTAL DA SUBFATURA\s+([\d.,]+)", pag)
        if cab and tot:
            subs.append({"sub": cab.group(1), "cnpj": "", "valor": br_para_float(tot.group(1))})

    return {"operadora": "Sorriso Pleno", "apolice": apolice, "valor_total": total,
            "cnpj_pagador": pagador, "subfaturas": subs}


# (nome, assinatura, funcao)
PARSERS = [
    ("Sorriso Pleno", re.compile(r"SORRISO PLENO ODONTO - FATURA"), parser_sorriso_pleno),
]


def identificar_layout(texto: str):
    """Devolve (nome, funcao) do parser que reconhece o texto, ou None."""
    for nome, assinatura, funcao in PARSERS:
        if assinatura.search(texto):
            return nome, funcao
    return None
