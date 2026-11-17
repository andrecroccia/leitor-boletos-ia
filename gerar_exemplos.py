"""
Gera boletos FICTICIOS em PDF (3 operadoras inventadas, cada uma com um layout)
e o cadastro de unidades usado no rateio.

Tudo aqui e inventado: empresas, CNPJs (validos so no calculo do digito),
nomes de beneficiarios e valores. Serve para treinar e demonstrar o projeto
sem expor nenhum dado real.

Uso:  py gerar_exemplos.py
"""
import csv
from pathlib import Path

import fitz  # PyMuPDF

RAIZ = Path(__file__).resolve().parent
PASTA_PDF = RAIZ / "boletos_exemplo"
PASTA_DADOS = RAIZ / "dados"


# ----------------------------------------------------------------- CNPJs fake
def cnpj(base8: str, filial: int) -> str:
    """Monta um CNPJ com digitos verificadores corretos (base inventada)."""
    n = [int(c) for c in base8 + f"{filial:04d}"]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
                  [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        r = sum(a * b for a, b in zip(n, pesos)) % 11
        n.append(0 if r < 2 else 11 - r)
    s = "".join(map(str, n))
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


BASE = "11222333"  # raiz inventada da "Rede Exemplo de Restaurantes"
UNIDADES = {
    1: "Matriz Centro", 2: "Praia", 3: "Shopping Norte", 4: "Shopping Sul",
    5: "Aeroporto", 6: "Jardins", 7: "Porto", 8: "Lagoa",
}
C = {n: cnpj(BASE, n) for n in UNIDADES}


def brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------- utilitario de PDF
class Pagina:
    """Escreve linhas de texto de cima para baixo numa pagina A4."""

    def __init__(self, doc: fitz.Document):
        self.p = doc.new_page(width=595, height=842)
        self.y = 50

    def linha(self, texto: str, tam: float = 10, x: float = 50, negrito=False, pula=None):
        fonte = "hebo" if negrito else "helv"
        self.p.insert_text((x, self.y), texto, fontsize=tam, fontname=fonte)
        self.y += pula if pula is not None else tam + 6

    def colunas(self, valores, xs, tam=9, negrito=False):
        fonte = "hebo" if negrito else "helv"
        for v, x in zip(valores, xs):
            self.p.insert_text((x, self.y), str(v), fontsize=tam, fontname=fonte)
        self.y += tam + 6

    def regua(self):
        self.p.draw_line((50, self.y - 8), (545, self.y - 8), width=0.5)
        self.y += 4


NOMES = ["Ana Souza", "Bruno Lima", "Carla Dias", "Diego Alves", "Elisa Rocha",
         "Felipe Nunes", "Gabriela Melo", "Heitor Pires", "Isabela Costa", "Joao Prado"]


def pagina_beneficiarios(doc, titulo, qtd, semente):
    """Pagina com nomes e nascimentos (inventados). Dado pessoal -> nao vai para a IA."""
    pg = Pagina(doc)
    pg.linha(titulo, 12, negrito=True)
    pg.linha("RELACAO DE BENEFICIARIOS", 11, negrito=True)
    pg.regua()
    pg.colunas(["Codigo", "Nome", "Nascimento", "Mensalidade"], [50, 140, 340, 460], negrito=True)
    for i in range(qtd):
        nome = NOMES[(i + semente) % len(NOMES)]
        nasc = f"{(i * 7 + semente) % 28 + 1:02d}/{(i * 5 + semente) % 12 + 1:02d}/{1975 + (i * 3 + semente) % 40}"
        pg.colunas([f"{1000 + semente * 10 + i:07d}/00", nome, nasc, brl(49.90)], [50, 140, 340, 460])


# ======================================================================
# Layout A - "Sorriso Pleno Odonto" (layout CONHECIDO: o codigo tem parser)
# Parecido com uma fatura tecnica: 1a pagina = resumo do grupo + boleto,
# depois uma pagina por subfatura com "TOTAL DA SUBFATURA".
# ======================================================================
def layout_a(nome_arq, apolice, master, subs, vencimento="10/12/2026"):
    doc = fitz.open()
    total = round(sum(v for _, _, v in subs), 2)
    pg = Pagina(doc)
    pg.linha("SORRISO PLENO ODONTO - FATURA DE SERVICOS", 13, negrito=True)
    pg.linha(f"Apolice: {apolice}     Competencia: 12/2026     Vencimento: {vencimento}")
    pg.linha("Estipulante: REDE EXEMPLO DE RESTAURANTES LTDA")
    pg.regua()
    if len(subs) > 1:
        pg.linha("RESUMO DO GRUPO (CONSOLIDADO)", 11, negrito=True)
        for sub, _, v in subs:
            pg.colunas([f"Subfatura {sub}", brl(v)], [60, 300])
        pg.regua()
    pg.linha(f"Pague ate o vencimento o valor de R$ {brl(total)}", 11, negrito=True)
    pg.linha(f"Pagador: REDE EXEMPLO DE RESTAURANTES LTDA   CNPJ: {C[master]}")
    pg.linha("Linha digitavel: 00190.00009 01234.567891 23456.789012 1 99990000000000")

    for sub, unid, v in subs:
        mens = round(v * 0.9, 2)
        inc = round(v - mens, 2)
        pg = Pagina(doc)
        pg.linha(f"{sub} - REDE EXEMPLO - {UNIDADES[unid].upper()}", 12, negrito=True)
        pg.linha(f"Apolice: {apolice}   Subfatura: {sub}")
        pg.regua()
        pg.colunas(["Mensalidades", brl(mens)], [60, 300])
        pg.colunas(["Inclusoes", brl(inc)], [60, 300])
        pg.colunas(["Exclusoes", "0,00"], [60, 300])
        pg.colunas(["TOTAL DA SUBFATURA", brl(v)], [60, 300], negrito=True)
    pagina_beneficiarios(doc, f"Apolice {apolice}", 8, int(apolice) % 7)
    doc.save(PASTA_PDF / nome_arq)
    return total


# ======================================================================
# Layout B - "VidaDent Saude" (DESCONHECIDO para o codigo -> vai para a IA)
# Tabela por unidade, com o CNPJ de cada uma e varias colunas de valor.
# ======================================================================
def layout_b(nome_arq, contrato, linhas, total_impresso=None):
    doc = fitz.open()
    pg = Pagina(doc)
    pg.linha("VidaDent Saude Bucal S.A.", 15, negrito=True)
    pg.linha("Demonstrativo mensal de cobranca - Plano Empresarial", 10)
    pg.linha(f"Contrato n. {contrato}    Referencia: dezembro/2026    Emissao: 20/11/2026", 9)
    pg.regua()
    xs = [50, 150, 270, 315, 385, 455, 505]
    pg.colunas(["Unidade", "CNPJ", "Vidas", "Mensal.", "Copart.", "Ajuste", "Total"], xs, 8, negrito=True)
    soma = 0.0
    for unid, vidas, mens, cop, aj in linhas:
        t = round(mens + cop + aj, 2)
        soma += t
        pg.colunas([UNIDADES[unid], C[unid], vidas, brl(mens), brl(cop), brl(aj), brl(t)], xs, 8)
    soma = round(soma, 2)
    total = soma if total_impresso is None else total_impresso
    pg.regua()
    pg.colunas(["TOTAL GERAL A PAGAR", "", "", "", "", "", brl(total)], xs, 9, negrito=True)
    pg.y += 20
    pg.linha("Ficha de compensacao", 10, negrito=True)
    pg.linha(f"Sacado: REDE EXEMPLO DE RESTAURANTES LTDA - {C[1]}", 9)
    pg.linha(f"(=) Valor do documento: {brl(total)}", 9)
    pg.linha("Atencao: valores de coparticipacao referem-se a procedimentos de outubro.", 8)
    pagina_beneficiarios(doc, f"Contrato {contrato}", 10, len(contrato))
    doc.save(PASTA_PDF / nome_arq)
    return total


# ======================================================================
# Layout C - "Mais Dente Planos" (DESCONHECIDO -> IA)
# Texto corrido, valores com descontos e creditos "no meio" do paragrafo.
# Nao traz o CNPJ das unidades: precisa do cadastro (apolice + subgrupo).
# ======================================================================
def layout_c(nome_arq, grupo, subgrupos):
    doc = fitz.open()
    pg = Pagina(doc)
    pg.linha("MAIS DENTE PLANOS ODONTOLOGICOS", 14, negrito=True)
    pg.linha(f"Aviso de cobranca - Grupo contratante {grupo}", 10)
    pg.regua()
    total = 0.0
    for sg, unid, bruto, credito in subgrupos:
        liq = round(bruto - credito, 2)
        total += liq
        pg.linha(f"Subgrupo {sg} ({UNIDADES[unid]}): mensalidades de R$ {brl(bruto)}, "
                 f"credito por exclusao de R$ {brl(credito)},", 9)
        pg.linha(f"    resultando em valor devido de R$ {brl(liq)}.", 9)
    total = round(total, 2)
    pg.y += 8
    pg.linha(f"O grupo {grupo} deve pagar R$ {brl(total)} ate 15/12/2026.", 10, negrito=True)
    pg.linha("Em caso de duvidas ligue 0800 000 0000 (numero ficticio).", 8)
    pg.linha(f"Responsavel financeiro: CNPJ {C[1]}", 8)
    pagina_beneficiarios(doc, f"Grupo {grupo}", 6, 3)
    doc.save(PASTA_PDF / nome_arq)
    return total


def main():
    PASTA_PDF.mkdir(exist_ok=True)
    PASTA_DADOS.mkdir(exist_ok=True)
    for f in PASTA_PDF.glob("*.pdf"):
        f.unlink()

    # A: com rateio (3 subs) e sem rateio (1 sub)
    layout_a("sorriso_900101.pdf", "900101", master=1,
             subs=[("001", 1, 412.50), ("002", 2, 287.30), ("003", 3, 198.75)])
    layout_a("sorriso_900102.pdf", "900102", master=4, subs=[("001", 4, 156.40)])
    # B: tabela com CNPJ por unidade
    layout_b("vidadent_VD-2026-0457.pdf", "VD-2026-0457",
             [(5, 6, 299.40, 45.00, 0.00), (6, 4, 199.60, 0.00, -12.30), (7, 9, 449.10, 87.50, 0.00)])
    # B com ERRO proposital: total impresso nao bate com a soma das linhas
    layout_b("vidadent_VD-2026-0458_com_erro.pdf", "VD-2026-0458",
             [(2, 3, 149.70, 0.00, 0.00), (8, 5, 249.50, 30.00, 0.00)], total_impresso=480.00)
    # C: texto corrido
    layout_c("maisdente_G-3310.pdf", "G-3310",
             [("01", 3, 520.00, 40.00), ("02", 4, 310.00, 0.00), ("03", 8, 275.80, 25.80)])

    # Cadastro (equivale a "Planilha2"): operadora + apolice + sub -> unidade
    with open(PASTA_DADOS / "cadastro_unidades.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["operadora", "apolice", "sub", "cnpj", "unidade"])
        linhas = [
            ("Sorriso Pleno", "900101", "001", 1), ("Sorriso Pleno", "900101", "002", 2),
            ("Sorriso Pleno", "900101", "003", 3), ("Sorriso Pleno", "900102", "001", 4),
            ("VidaDent", "VD-2026-0457", "", 5), ("VidaDent", "VD-2026-0457", "", 6),
            ("VidaDent", "VD-2026-0457", "", 7), ("VidaDent", "VD-2026-0458", "", 2),
            ("VidaDent", "VD-2026-0458", "", 8),
            ("Mais Dente", "G-3310", "01", 3), ("Mais Dente", "G-3310", "02", 4),
            ("Mais Dente", "G-3310", "03", 8),
        ]
        for op, ap, sub, u in linhas:
            w.writerow([op, ap, sub, C[u], UNIDADES[u]])

    print(f"PDFs gerados em {PASTA_PDF}")
    for f in sorted(PASTA_PDF.glob("*.pdf")):
        print("  -", f.name)
    print(f"Cadastro: {PASTA_DADOS / 'cadastro_unidades.csv'}")


if __name__ == "__main__":
    main()
