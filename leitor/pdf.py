"""Leitura do PDF: texto de cada pagina, com as linhas da tabela reconstruidas."""
import re

import fitz  # PyMuPDF

# Paginas com dados pessoais (nomes, nascimentos) NUNCA vao para a IA.
# O rateio so precisa das paginas de resumo/valores.
_DADOS_PESSOAIS = re.compile(r"BENEFICI[AÁ]RIOS?|NASCIMENTO|CPF", re.IGNORECASE)


def ler_paginas(caminho) -> list[str]:
    """Devolve o texto de cada pagina, uma linha visual por linha de texto.

    O get_text() comum devolve tabelas "uma celula por linha", o que confunde
    modelos de IA pequenos. Aqui as palavras sao agrupadas pela altura (y)
    em que aparecem, reconstruindo as linhas da tabela.
    """
    paginas = []
    with fitz.open(caminho) as doc:
        for pagina in doc:
            palavras = pagina.get_text("words")  # (x0, y0, x1, y1, texto, ...)
            palavras.sort(key=lambda w: (round(w[3]), w[0]))
            linhas, atual, y_atual, x_fim = [], [], None, 0.0
            for x0, _, x1, y1, txt, *_ in palavras:
                if y_atual is None or abs(y1 - y_atual) > 3:
                    if atual:
                        linhas.append("".join(atual))
                    atual, y_atual = [txt], y1
                else:
                    atual.append(("   " if x0 - x_fim > 15 else " ") + txt)
                x_fim = x1
            if atual:
                linhas.append("".join(atual))
            paginas.append("\n".join(linhas))
    return paginas


def tem_dados_pessoais(texto_pagina: str) -> bool:
    return bool(_DADOS_PESSOAIS.search(texto_pagina))


def paginas_para_ia(paginas: list[str]) -> list[str]:
    """Minimizacao de dados (LGPD): so as paginas sem dados pessoais."""
    return [p for p in paginas if not tem_dados_pessoais(p)]
