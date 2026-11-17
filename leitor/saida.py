"""Gravacao do resultado: planilha de rateio + JSON de auditoria."""
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

MOEDA = '"R$" #,##0.00'


def salvar_json(pasta: Path, arquivo_pdf: str, registro: dict):
    """Guarda o que foi extraido (e por quem) para conferir depois."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / (Path(arquivo_pdf).stem + ".json")
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def salvar_planilha(pasta: Path, arquivo_pdf: str, dados: dict, linhas: list[dict], origem: str):
    pasta.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Rateio"
    negrito = Font(bold=True)

    info = [("Arquivo", arquivo_pdf), ("Operadora", dados["operadora"]),
            ("Apolice", dados["apolice"]), ("Valor total", dados["valor_total"]),
            ("Lido por", origem)]
    for i, (k, v) in enumerate(info, start=1):
        ws.cell(i, 1, k).font = negrito
        c = ws.cell(i, 2, v)
        if k == "Valor total":
            c.number_format = MOEDA

    cab = 7
    for j, t in enumerate(["Sub", "CNPJ", "Unidade", "Valor", "%"], start=1):
        c = ws.cell(cab, j, t)
        c.font = negrito
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    for i, l in enumerate(linhas, start=cab + 1):
        ws.cell(i, 1, l["sub"])
        ws.cell(i, 2, l["cnpj"])
        ws.cell(i, 3, l["unidade"])
        ws.cell(i, 4, l["valor"]).number_format = MOEDA
        ws.cell(i, 5, f"=D{i}/$B$4").number_format = "0.00%"
    fim = cab + len(linhas)
    ws.cell(fim + 1, 3, "Soma").font = negrito
    c = ws.cell(fim + 1, 4, f"=SUM(D{cab + 1}:D{fim})")
    c.number_format, c.font = MOEDA, negrito
    ws.cell(fim + 2, 3, "Confere?").font = negrito
    ws.cell(fim + 2, 4, f'=IF(ABS(D{fim + 1}-B4)<0.01,"OK","VERIFICAR")').font = negrito

    for col, larg in zip("ABCDE", (12, 22, 20, 14, 9)):
        ws.column_dimensions[col].width = larg
    ws.column_dimensions["B"].width = 34

    destino = pasta / f"Rateio_{Path(arquivo_pdf).stem}.xlsx"
    wb.save(destino)
    return destino
