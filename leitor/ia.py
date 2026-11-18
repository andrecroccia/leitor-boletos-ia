"""Extracao com IA para layouts que o codigo NAO conhece.

A IA e so uma funcao remota: entra texto + instrucoes, sai texto (aqui, JSON).
Dois provedores, ambos sem custo:

  ollama  -> modelo rodando no PROPRIO computador (gratis, offline, mais lento)
  gemini  -> API do Google (camada gratuita; precisa de chave no .env)

So usa a biblioteca padrao do Python (urllib), sem SDK.
"""
import json
import os
import time
import urllib.error
import urllib.request

# Formato que a resposta DEVE seguir. No Ollama ele e imposto pelo proprio
# servidor ("structured output"); no Gemini vai junto nas instrucoes.
SCHEMA = {
    "type": "object",
    "properties": {
        "operadora": {"type": "string"},
        "apolice": {"type": "string"},
        "valor_total": {"type": "number"},
        "cnpj_pagador": {"type": "string"},
        "subfaturas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sub": {"type": "string"},
                    "cnpj": {"type": "string"},
                    "valor": {"type": "number"},
                },
                "required": ["sub", "cnpj", "valor"],
            },
        },
    },
    "required": ["operadora", "apolice", "valor_total", "cnpj_pagador", "subfaturas"],
}

INSTRUCOES = f"""Voce extrai dados de faturas/boletos de planos odontologicos empresariais.
Leia o documento e responda SOMENTE com um JSON neste formato (JSON Schema):
{json.dumps(SCHEMA, ensure_ascii=False)}

Regras:
- operadora: nome da empresa que esta cobrando.
- apolice: numero da apolice, contrato ou grupo contratante, exatamente como escrito.
- valor_total: valor total a pagar do documento.
- cnpj_pagador: CNPJ de quem paga (sacado/pagador/responsavel financeiro), copiado do documento.
- subfaturas: uma entrada por unidade/subfatura/subgrupo cobrado.
  - sub: numero da subfatura/subgrupo como aparece; use "" se nao houver numero.
  - cnpj: SOMENTE se houver um CNPJ escrito na mesma linha da unidade. Se nao houver, "".
    O CNPJ do pagador nao e o CNPJ das unidades.
  - valor: valor FINAL devido daquela unidade (ja com coparticipacao, ajustes, descontos e creditos).
- Valores como numero com ponto decimal (ex.: 1068.30). Negativos com sinal de menos.
- Nao invente nada: copie os numeros do documento. Nao some nem calcule se o valor final ja estiver escrito.
"""


class ErroIA(Exception):
    pass


# Erros "temporarios" do servidor: vale esperar e tentar de novo.
# 429 = limite de uso por minuto; 500/502/503/504 = servidor ocupado/instavel.
_TEMPORARIOS = {429, 500, 502, 503, 504}


def _post_json(url: str, corpo: dict, cabecalhos: dict, timeout: int) -> dict:
    """POST com JSON. Em erro temporario, espera cada vez mais e tenta de novo
    ("exponential backoff"): 5s, 15s, 45s..."""
    tentativas = int(os.environ.get("IA_TENTATIVAS_REDE", "4"))
    for n in range(1, tentativas + 1):
        req = urllib.request.Request(
            url, data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json", **cabecalhos}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", "replace")
            try:  # mostra so a mensagem do erro, nao o JSON inteiro
                detalhe = json.loads(detalhe)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            erro = ErroIA(f"HTTP {e.code}: {detalhe[:200]}")
            if e.code not in _TEMPORARIOS:
                raise erro from None
        except urllib.error.URLError as e:
            erro = ErroIA(f"sem conexao com {url.split('?')[0]} ({e.reason})")
            if "localhost" in url:  # Ollama fechado: nao adianta esperar
                raise erro from None
        except TimeoutError:
            erro = ErroIA(f"tempo esgotado ({timeout}s)")
        if n < tentativas:
            espera = 5 * 3 ** (n - 1)
            print(f"     ({erro}; tentando de novo em {espera}s)")
            time.sleep(espera)
    raise erro


# ------------------------------------------------------------------- Ollama
def _ollama(mensagens: list[dict]) -> tuple[str, str]:
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    modelo = os.environ.get("OLLAMA_MODELO", "qwen2.5:3b")
    resp = _post_json(f"{url}/api/chat", {
        "model": modelo,
        "messages": [{"role": "system", "content": INSTRUCOES}, *mensagens],
        "format": SCHEMA,          # o servidor obriga a resposta a seguir o schema
        "stream": False,
        "options": {"temperature": 0},
    }, {}, timeout=int(os.environ.get("IA_TIMEOUT", "900")))
    return resp["message"]["content"], f"ollama:{modelo}"


# ------------------------------------------------------------------- Gemini
def _gemini(mensagens: list[dict]) -> tuple[str, str]:
    chave = os.environ.get("GEMINI_API_KEY", "")
    if not chave:
        raise ErroIA("GEMINI_API_KEY nao definida (veja o .env.exemplo)")
    modelo = os.environ.get("GEMINI_MODELO", "gemini-flash-lite-latest")
    papel = {"user": "user", "assistant": "model"}
    resp = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": INSTRUCOES}]},
            "contents": [{"role": papel[m["role"]], "parts": [{"text": m["content"]}]}
                         for m in mensagens],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        },
        {"x-goog-api-key": chave},  # chave no cabecalho, nunca na URL
        timeout=int(os.environ.get("IA_TIMEOUT", "120")))
    try:
        return resp["candidates"][0]["content"]["parts"][0]["text"], f"gemini:{modelo}"
    except (KeyError, IndexError):
        raise ErroIA(f"resposta inesperada do Gemini: {str(resp)[:300]}") from None


PROVEDORES = {"ollama": _ollama, "gemini": _gemini}


def extrair(texto: str, provedor: str, historico: list[dict] | None = None):
    """Manda o texto para a IA e devolve (dados, mensagens, modelo, segundos).

    `historico` permite uma segunda tentativa: a conversa anterior + o que
    estava errado vai junto, e a IA corrige a propria resposta.
    """
    if provedor not in PROVEDORES:
        raise ErroIA(f"provedor desconhecido: {provedor}")
    mensagens = historico or [{"role": "user", "content": "DOCUMENTO:\n" + texto}]
    t0 = time.perf_counter()
    bruto, modelo = PROVEDORES[provedor](mensagens)
    seg = time.perf_counter() - t0
    try:
        dados = json.loads(bruto.strip().removeprefix("```json").removesuffix("```"))
    except json.JSONDecodeError:
        raise ErroIA(f"a IA nao devolveu JSON valido: {bruto[:200]}") from None
    mensagens = [*mensagens, {"role": "assistant", "content": bruto}]
    return dados, mensagens, modelo, seg


def pedir_correcao(mensagens: list[dict], problemas: list[str]) -> list[dict]:
    """Monta a mensagem de 'tente de novo' com os erros que o codigo achou."""
    texto = ("Sua resposta tem estes problemas, encontrados na conferencia:\n- "
             + "\n- ".join(problemas)
             + "\nReleia o documento e responda de novo o JSON completo, corrigido. "
               "Se o proprio documento estiver inconsistente, copie os valores como estao.")
    return [*mensagens, {"role": "user", "content": texto}]
