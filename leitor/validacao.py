"""Conferencias em CODIGO. A IA erra as vezes; estas regras nao.

Nada vira planilha sem passar por aqui, venha do parser ou da IA.
"""
import csv
import re
from pathlib import Path

from .util import brl, so_digitos


def cnpj_valido(cnpj: str) -> bool:
    n = [int(c) for c in so_digitos(cnpj)]
    if len(n) != 14 or len(set(n)) == 1:
        return False
    for pos, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                       (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        r = sum(a * b for a, b in zip(n, pesos)) % 11
        if n[pos] != (0 if r < 2 else 11 - r):
            return False
    return True


def _norm_sub(sub) -> str:
    s = str(sub or "").strip()
    return str(int(s)) if s.isdigit() else s.upper()


def _norm_apolice(ap) -> str:
    return str(ap or "").strip().upper()


class Cadastro:
    """Cadastro de unidades (equivale a 'Planilha2'): apolice + sub -> CNPJ/unidade."""

    def __init__(self, caminho: Path):
        self.por_sub, self.por_cnpj = {}, {}
        with open(caminho, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                ap, cnpj = _norm_apolice(r["apolice"]), so_digitos(r["cnpj"])
                if r["sub"].strip():
                    self.por_sub[(ap, _norm_sub(r["sub"]))] = (r["cnpj"], r["unidade"])
                self.por_cnpj[(ap, cnpj)] = (r["cnpj"], r["unidade"])

    def localizar(self, apolice, sub, cnpj):
        ap = _norm_apolice(apolice)
        if so_digitos(cnpj):
            return self.por_cnpj.get((ap, so_digitos(cnpj)))
        return self.por_sub.get((ap, _norm_sub(sub)))


_RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
DICA_CNPJ = ("Preencha cnpj da subfatura SOMENTE se houver um CNPJ escrito na linha "
             "daquela unidade; caso contrario use cnpj vazio (\"\").")


def _aparece(valor: float, texto: str) -> bool:
    """O numero esta escrito no documento? (pega 'alucinacao' da IA)"""
    return brl(valor) in texto or brl(abs(valor)) in texto


def validar(dados: dict, texto: str, cadastro: Cadastro):
    """Devolve (linhas_do_rateio, problemas). Sem problemas = pode gerar planilha."""
    problemas, linhas = [], []
    try:
        total = round(float(dados["valor_total"]), 2)
        subs = dados["subfaturas"]
        apolice = dados["apolice"]
    except (KeyError, TypeError, ValueError) as e:
        return [], [f"resposta incompleta ({e})"]

    if not subs:
        problemas.append("nenhuma subfatura encontrada")
    if total <= 0:
        problemas.append(f"valor total invalido: {total}")
    elif not _aparece(total, texto):
        problemas.append(f"valor total {brl(total)} nao aparece no documento")

    pagador = dados.get("cnpj_pagador", "")
    if pagador and not cnpj_valido(pagador):
        problemas.append(f"CNPJ do pagador invalido: {pagador}")

    # Cada unidade tem CNPJ proprio. O mesmo CNPJ em varias subfaturas quase
    # sempre e o CNPJ do pagador copiado por engano (erro comum de modelo pequeno).
    cnpjs = [so_digitos(s.get("cnpj")) for s in subs if isinstance(s, dict)]
    repetidos = {c for c in cnpjs if c and cnpjs.count(c) > 1}
    # CNPJs que estao de fato escritos no documento (pega CNPJ inventado)
    cnpjs_doc = {so_digitos(c) for c in _RE_CNPJ.findall(texto)}

    soma = 0.0
    for s in subs:
        try:
            valor = round(float(s["valor"]), 2)
        except (KeyError, TypeError, ValueError):
            problemas.append(f"subfatura sem valor: {s}")
            continue
        soma += valor
        sub, cnpj = s.get("sub", ""), s.get("cnpj", "")
        rotulo = f"sub {sub or '?'}" + (f" ({cnpj})" if cnpj else "")
        if not _aparece(valor, texto):
            problemas.append(f"{rotulo}: valor {brl(valor)} nao aparece no documento")
        d = so_digitos(cnpj)
        if d:
            if d not in cnpjs_doc:
                problemas.append(f"{rotulo}: este CNPJ nao aparece no documento (inventado?). {DICA_CNPJ}")
                continue
            if d in repetidos:
                eh_pagador = d == so_digitos(pagador)
                problemas.append(f"{rotulo}: o mesmo CNPJ foi usado em varias subfaturas"
                                 + (" e ele e o CNPJ do PAGADOR" if eh_pagador else "")
                                 + f". {DICA_CNPJ}")
                continue
            if not cnpj_valido(cnpj):
                problemas.append(f"{rotulo}: CNPJ com digito verificador invalido. {DICA_CNPJ}")
                continue
        achado = cadastro.localizar(apolice, sub, cnpj)
        if not achado:
            if d and d == so_digitos(pagador):
                problemas.append(f"{rotulo}: este e o CNPJ do PAGADOR, nao o da unidade. {DICA_CNPJ}")
            else:
                problemas.append(f"{rotulo}: nao esta no cadastro para a apolice {apolice}")
            continue
        linhas.append({"sub": sub, "cnpj": achado[0], "unidade": achado[1], "valor": valor})

    soma = round(soma, 2)
    if subs and abs(soma - total) > 0.005:
        problemas.append(f"soma das subfaturas ({brl(soma)}) diferente do total ({brl(total)})")
    return linhas, problemas
