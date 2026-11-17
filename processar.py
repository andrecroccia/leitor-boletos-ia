"""
Le todos os boletos (PDF) de uma pasta e gera o rateio por unidade.

    PDF -> texto -> layout conhecido?  sim -> parser em codigo
                                       nao -> IA (Ollama local ou Gemini)
         -> conferencias em codigo -> planilha (ou "REVISAR")

Uso:
    py processar.py                          # pasta boletos_exemplo, IA do .env
    py processar.py minha_pasta --ia gemini
    py processar.py --ia nenhuma             # sem IA: layout novo vai para revisao
    py processar.py --forcar-ia              # manda TUDO para a IA e compara
                                             # com o parser (mede o acerto da IA)
"""
import argparse
import os
import sys
from pathlib import Path

from leitor import ia
from leitor.parsers import identificar_layout
from leitor.pdf import ler_paginas, paginas_para_ia
from leitor.saida import salvar_json, salvar_planilha
from leitor.util import brl, carregar_env
from leitor.validacao import Cadastro, validar

RAIZ = Path(__file__).resolve().parent


def ler_com_ia(texto: str, texto_conferencia: str, provedor: str, cadastro):
    """Extrai com IA e, se a conferencia reprovar, da UMA chance de corrigir."""
    dados, conversa, modelo, seg = ia.extrair(texto, provedor)
    print(f"     IA ({modelo}) respondeu em {seg:.0f}s")
    linhas, problemas = validar(dados, texto_conferencia, cadastro)
    if problemas:
        print("     conferencia reprovou; pedindo para a IA corrigir:")
        for p in problemas:
            print(f"       - {p}")
        dados, conversa, modelo, seg = ia.extrair(texto, provedor, ia.pedir_correcao(conversa, problemas))
        print(f"     IA respondeu de novo em {seg:.0f}s")
        linhas, problemas = validar(dados, texto_conferencia, cadastro)
    return dados, linhas, problemas, f"IA ({modelo})"


def comparar(a: dict, b: dict) -> list[str]:
    """Diferencas entre o resultado do parser (a) e o da IA (b)."""
    dif = []
    if round(a["valor_total"], 2) != round(float(b.get("valor_total") or 0), 2):
        dif.append(f"total: codigo {brl(a['valor_total'])} x IA {b.get('valor_total')}")
    va = sorted(round(s["valor"], 2) for s in a["subfaturas"])
    vb = sorted(round(float(s.get("valor") or 0), 2) for s in b.get("subfaturas", []))
    if va != vb:
        dif.append(f"subfaturas: codigo {va} x IA {vb}")
    return dif


def main():
    carregar_env(RAIZ)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", nargs="?", default="boletos_exemplo")
    ap.add_argument("--ia", default=os.environ.get("IA_PROVEDOR", "ollama"),
                    choices=["ollama", "gemini", "nenhuma"])
    ap.add_argument("--forcar-ia", action="store_true")
    args = ap.parse_args()

    pasta = (RAIZ / args.pasta) if not Path(args.pasta).is_absolute() else Path(args.pasta)
    pdfs = sorted(pasta.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"Nenhum PDF em {pasta}. Rode antes: py gerar_exemplos.py")
    cadastro = Cadastro(RAIZ / "dados" / "cadastro_unidades.csv")
    saida = RAIZ / "saida"
    cont = {"ok": 0, "sem_rateio": 0, "revisar": 0}

    for pdf in pdfs:
        print(f"\n== {pdf.name}")
        paginas = ler_paginas(pdf)
        texto_todo = "\n".join(paginas)
        texto_ia = "\n\n--- pagina ---\n".join(paginas_para_ia(paginas))
        omitidas = len(paginas) - texto_ia.count("--- pagina ---") - 1
        layout = identificar_layout(texto_todo)

        dados, problemas, linhas, origem = None, [], [], ""
        try:
            if layout and not args.forcar_ia:
                nome, parser = layout
                print(f"     layout conhecido: {nome} -> parser em codigo")
                dados = parser(paginas)
                origem = f"codigo ({nome})"
                linhas, problemas = validar(dados, texto_todo, cadastro)
            elif args.ia == "nenhuma":
                problemas = ["layout desconhecido e a IA esta desligada (--ia nenhuma)"]
            else:
                print(f"     {'layout conhecido, mas --forcar-ia' if layout else 'layout DESCONHECIDO'}"
                      f" -> IA ({args.ia}); {omitidas} pagina(s) com dados pessoais NAO enviada(s)")
                dados, linhas, problemas, origem = ler_com_ia(texto_ia, texto_todo, args.ia, cadastro)
                if layout:
                    dif = comparar(layout[1](paginas), dados)
                    print("     comparacao com o parser: " + ("IGUAL" if not dif else "; ".join(dif)))
        except ia.ErroIA as e:
            problemas = [f"falha na IA: {e}"]
            if "sem conexao" in str(e) and args.ia == "ollama":
                problemas.append("o Ollama esta instalado e aberto? (veja o README)")

        salvar_json(saida / "json", pdf.name, {"origem": origem, "dados": dados,
                                               "problemas": problemas})
        if problemas:
            cont["revisar"] += 1
            print("  [REVISAR] nada foi gerado para este boleto:")
            for p in problemas:
                print(f"       - {p}")
            continue

        print(f"     {dados['operadora']} | apolice {dados['apolice']} | total R$ {brl(dados['valor_total'])}")
        for l in linhas:
            print(f"       sub {l['sub'] or '-':>3}  R$ {brl(l['valor']):>10}  {l['cnpj']}  {l['unidade']}")
        if len(linhas) == 1:
            cont["sem_rateio"] += 1
            print("  [SEM RATEIO] uma unidade so; nao precisa de planilha")
        else:
            cont["ok"] += 1
            arq = salvar_planilha(saida, pdf.name, dados, linhas, origem)
            print(f"  [OK] {arq.relative_to(RAIZ)}")

    print(f"\nResumo: {cont['ok']} planilha(s), {cont['sem_rateio']} sem rateio, "
          f"{cont['revisar']} para revisar.  Detalhes em saida/json/")


if __name__ == "__main__":
    main()
