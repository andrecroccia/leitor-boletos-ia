"""Testes sem IA de verdade: a IA e trocada por uma "IA falsa" com respostas prontas.

Rodar:  py -m unittest discover testes -v
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import gerar_exemplos  # noqa: E402
import processar  # noqa: E402
from leitor import ia  # noqa: E402
from leitor.parsers import identificar_layout  # noqa: E402
from leitor.pdf import ler_paginas, paginas_para_ia  # noqa: E402
from leitor.validacao import Cadastro, cnpj_valido, validar  # noqa: E402

PDF = RAIZ / "boletos_exemplo"

VIDADENT_CERTO = {
    "operadora": "VidaDent Saude Bucal S.A.", "apolice": "VD-2026-0457",
    "valor_total": 1068.30, "cnpj_pagador": "11.222.333/0001-81",
    "subfaturas": [
        {"sub": "", "cnpj": "11.222.333/0005-05", "valor": 344.40},
        {"sub": "", "cnpj": "11.222.333/0006-96", "valor": 187.30},
        {"sub": "", "cnpj": "11.222.333/0007-77", "valor": 536.60},
    ],
}


class IAFalsa:
    """Devolve as respostas da lista, uma por chamada, e guarda o que recebeu."""

    def __init__(self, *respostas):
        self.respostas, self.recebido = list(respostas), []

    def __call__(self, mensagens):
        self.recebido.append(mensagens)
        return json.dumps(self.respostas.pop(0)), "falsa:teste"


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RAIZ / "dados" / "cadastro_unidades.csv").exists() or not list(PDF.glob("*.pdf")):
            gerar_exemplos.main()
        cls.cadastro = Cadastro(RAIZ / "dados" / "cadastro_unidades.csv")

    def tearDown(self):
        ia.PROVEDORES.pop("falsa", None)

    def texto(self, nome):
        paginas = ler_paginas(PDF / nome)
        return paginas, "\n".join(paginas)

    def test_cnpj(self):
        self.assertTrue(cnpj_valido("11.222.333/0001-81"))
        self.assertFalse(cnpj_valido("11.222.333/0001-82"))

    def test_parser_layout_conhecido(self):
        paginas, texto = self.texto("sorriso_900101.pdf")
        nome, parser = identificar_layout(texto)
        dados = parser(paginas)
        linhas, problemas = validar(dados, texto, self.cadastro)
        self.assertEqual(problemas, [])
        self.assertEqual([l["valor"] for l in linhas], [412.50, 287.30, 198.75])

    def test_layout_desconhecido(self):
        _, texto = self.texto("vidadent_VD-2026-0457.pdf")
        self.assertIsNone(identificar_layout(texto))

    def test_dados_pessoais_nao_vao_para_ia(self):
        paginas, _ = self.texto("vidadent_VD-2026-0457.pdf")
        enviado = "\n".join(paginas_para_ia(paginas))
        self.assertNotIn("BENEFICIARIOS", enviado)
        self.assertNotIn("Carla Dias", enviado)
        self.assertIn("1.068,30", enviado)

    def test_ia_acerta(self):
        ia.PROVEDORES["falsa"] = IAFalsa(VIDADENT_CERTO)
        _, texto = self.texto("vidadent_VD-2026-0457.pdf")
        dados, linhas, problemas, _ = processar.ler_com_ia(texto, texto, "falsa", self.cadastro)
        self.assertEqual(problemas, [])
        self.assertEqual([l["unidade"] for l in linhas], ["Aeroporto", "Jardins", "Porto"])

    def test_ia_alucina_e_corrige_na_segunda_tentativa(self):
        errado = json.loads(json.dumps(VIDADENT_CERTO))
        errado["subfaturas"][1]["valor"] = 199.60  # pegou a coluna errada
        falsa = IAFalsa(errado, VIDADENT_CERTO)
        ia.PROVEDORES["falsa"] = falsa
        _, texto = self.texto("vidadent_VD-2026-0457.pdf")
        _, _, problemas, _ = processar.ler_com_ia(texto, texto, "falsa", self.cadastro)
        self.assertEqual(problemas, [])
        self.assertEqual(len(falsa.recebido), 2)
        self.assertIn("soma das subfaturas", falsa.recebido[1][-1]["content"])

    def test_ia_inventa_valor(self):
        inventado = json.loads(json.dumps(VIDADENT_CERTO))
        inventado["valor_total"] = 1100.00
        inventado["subfaturas"][0]["valor"] = 376.10  # soma fecha, mas nao existe no PDF
        _, texto = self.texto("vidadent_VD-2026-0457.pdf")
        _, problemas = validar(inventado, texto, self.cadastro)
        self.assertTrue(any("nao aparece no documento" in p for p in problemas))

    def test_ia_copia_cnpj_do_pagador_e_corrige(self):
        # Erro real do qwen2.5:3b no layout Mais Dente: CNPJ do pagador em todas as subs
        base = {"operadora": "Mais Dente", "apolice": "G-3310", "valor_total": 1040.00,
                "cnpj_pagador": "11.222.333/0001-81"}
        valores = [("01", 480.00), ("02", 310.00), ("03", 250.00)]
        errado = {**base, "subfaturas": [{"sub": s, "cnpj": base["cnpj_pagador"], "valor": v}
                                         for s, v in valores]}
        certo = {**base, "subfaturas": [{"sub": s, "cnpj": "", "valor": v} for s, v in valores]}
        falsa = IAFalsa(errado, certo)
        ia.PROVEDORES["falsa"] = falsa
        _, texto = self.texto("maisdente_G-3310.pdf")
        _, linhas, problemas, _ = processar.ler_com_ia(texto, texto, "falsa", self.cadastro)
        self.assertEqual(problemas, [])
        self.assertEqual([l["unidade"] for l in linhas], ["Shopping Norte", "Shopping Sul", "Lagoa"])
        self.assertIn("CNPJ do PAGADOR", falsa.recebido[1][-1]["content"])

    def test_ia_inventa_cnpj(self):
        inventado = json.loads(json.dumps(VIDADENT_CERTO))
        inventado["subfaturas"][0]["cnpj"] = "00.000.000/0001-91"  # DV valido, mas nao esta no PDF
        _, texto = self.texto("vidadent_VD-2026-0457.pdf")
        _, problemas = validar(inventado, texto, self.cadastro)
        self.assertTrue(any("nao aparece no documento" in p for p in problemas))

    def test_documento_inconsistente_vai_para_revisao(self):
        resposta = {"operadora": "VidaDent", "apolice": "VD-2026-0458", "valor_total": 480.00,
                    "cnpj_pagador": "11.222.333/0001-81", "subfaturas": [
                        {"sub": "", "cnpj": "11.222.333/0002-62", "valor": 149.70},
                        {"sub": "", "cnpj": "11.222.333/0008-58", "valor": 279.50}]}
        ia.PROVEDORES["falsa"] = IAFalsa(resposta, resposta, resposta)
        _, texto = self.texto("vidadent_VD-2026-0458_com_erro.pdf")
        _, _, problemas, _ = processar.ler_com_ia(texto, texto, "falsa", self.cadastro)
        self.assertTrue(any("diferente do total" in p for p in problemas))


if __name__ == "__main__":
    unittest.main()
