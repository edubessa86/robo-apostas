from datetime import datetime
import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

from api_football import buscar_jogos_do_dia, buscar_odds_do_jogo, formatar_jogos_para_prompt

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

MODELO = "gemini-3.6-flash"

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto, limite=4000):
    """Divide textos longos em pedaços menores para respeitar o limite de caracteres do Telegram."""
    return [texto[i:i + limite] for i in range(0, len(texto), limite)]


def enviar_telegram(texto: str) -> None:
    """Envia uma mensagem (dividida se necessário) para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for parte in dividir_mensagem(texto):
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            resposta = requests.post(url, json=payload, timeout=15)
            if resposta.status_code == 200:
                print("Mensagem enviada com sucesso para o Telegram!")
            else:
                print(f"Erro ao enviar para o Telegram: {resposta.status_code} - {resposta.text}")
        except requests.RequestException as exc:
            print(f"Falha de rede ao enviar para o Telegram: {exc}")


def extrair_retry_after(erro: Exception) -> int | None:
    """Tenta extrair o tempo de espera sugerido pela própria API (quando presente
    no corpo do erro 429), em vez de usar um backoff fixo às cegas.
    """
    try:
        detalhes = getattr(erro, "details", None) or {}
        for item in detalhes.get("error", {}).get("details", []):
            if item.get("@type", "").endswith("RetryInfo"):
                delay = item.get("retryDelay", "")
                if delay.endswith("s"):
                    return int(float(delay[:-1]))
    except Exception:
        pass
    return None


def eh_erro_de_cota_esgotada(erro: Exception, retry_after: int | None) -> bool:
    """Sem RetryInfo sugerido pela API, tratamos como esgotamento sério
    (diário/hard-cap) — retry curto não ajuda nesse caso.
    """
    if retry_after is not None:
        return False
    texto_erro = str(erro).lower()
    return "resource_exhausted" in texto_erro.replace(" ", "") or "429" in texto_erro


def montar_prompt(data_hoje: str, jogos_formatados: str) -> str:
    """Monta o prompt para o Gemini.

    IMPORTANTE: o Gemini NÃO busca mais nada na web aqui — os jogos já vêm
    prontos da API-Football. O papel do modelo agora é só analisar/formatar,
    o que evita consumir a cota (bem mais restrita) de grounding/Google
    Search no tier gratuito.
    """
    return f"""
ROBÔ DE ANÁLISE DE APOSTAS ESPORTIVAS — DISPARO DIÁRIO
Você é um sistema de análise de apostas esportivas e especialista em probabilidade
matemática. Você recebe abaixo a lista REAL de jogos de hoje (já verificada por uma
API de dados esportivos — NÃO busque nem invente outros jogos, use apenas os
fornecidos).

DATA: {data_hoje}
FUSO: Brasília (UTC-3)

JOGOS DE HOJE (pré-jogo, a partir das 10h):
{jogos_formatados}

REGRAS OBRIGATÓRIAS:
- Use SOMENTE os jogos listados acima. NUNCA invente confrontos, times, campeonatos
  ou dados estatísticos que não estejam aqui.
- Quando o jogo estiver marcado como "odds não verificadas pela API", diga isso
  claramente no relatório em vez de inventar uma odd numérica.
- Analise estritamente partidas pré-jogo (todas as listadas já são pré-jogo).

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO PARA O TELEGRAM (HTML)
Utilize tags HTML limpas do Telegram (`<b>`, `<i>`) seguindo estritamente esta estrutura:

⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP JOGOS DO DIA (A partir das 10h)</b>
(Para cada jogo da lista acima, liste de forma objetiva:)
- <b>[Time A] x [Time B]</b> ([Competição], [Horário])
- Análise: [contexto/observação relevante, sem inventar dados]
- Odd: [valor verificado, ou "não verificada" se for o caso]

━━━━━━━━━━━━━━━━━━
📊 <b>DESTAQUES E PROJEÇÕES</b>
- Resumo analítico dos confrontos do dia, com base apenas nos dados fornecidos.

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Nenhuma aposta é 100% garantida.
Aposte com responsabilidade.

Logo abaixo, inclua obrigatoriamente este bloco promocional:
JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")

    if not API_FOOTBALL_KEY:
        print("Erro crítico: API_FOOTBALL_KEY não configurada.")
        enviar_telegram(
            "⚠️ <b>Robô de apostas não rodou hoje.</b>\n"
            "Motivo: variável de ambiente API_FOOTBALL_KEY não configurada."
        )
        return

    print(f"Buscando jogos reais via API-Football para {data_hoje} a partir das 10h...")
    try:
        jogos = buscar_jogos_do_dia(api_key=API_FOOTBALL_KEY, hora_minima=10)
    except Exception as exc:
        print(f"Erro crítico ao buscar jogos na API-Football: {exc}")
        enviar_telegram(
            "⚠️ <b>Robô de apostas não rodou hoje.</b>\n"
            f"Motivo: falha ao buscar jogos na API-Football: {str(exc)[:300]}"
        )
        return

    # Busca odds só para os jogos encontrados (evita gastar cota da API-Football à toa).
    odds_por_fixture = {}
    for jogo in jogos:
        odds = buscar_odds_do_jogo(api_key=API_FOOTBALL_KEY, fixture_id=jogo["fixture_id"])
        if odds:
            odds_por_fixture[jogo["fixture_id"]] = odds

    jogos_formatados = formatar_jogos_para_prompt(jogos, odds_por_fixture)

    if not jogos:
        print("Nenhum jogo encontrado para hoje — encerrando sem chamar o Gemini.")
        enviar_telegram(
            f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>\n\n"
            "Nenhum jogo pré-jogo encontrado nas ligas monitoradas a partir das 10h de hoje."
        )
        return

    prompt_mestre = montar_prompt(data_hoje, jogos_formatados)

    print(f"Enviando {len(jogos)} jogos para análise do modelo {MODELO} (sem grounding)...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None
    ultimo_erro = None

    while tentativa < max_tentativas:
        try:
            # NOTE: sem `tools=[{"google_search": {}}]` — o Gemini não busca mais
            # nada na web, só analisa os dados já fornecidos. Isso usa a cota
            # normal de geração de texto, bem mais generosa que a de grounding.
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            ultimo_erro = e
            tentativa += 1
            retry_sugerido = extrair_retry_after(e)

            if eh_erro_de_cota_esgotada(e, retry_sugerido):
                print(f"Cota esgotada sem sugestão de retry da API: {e}. Abortando tentativas.")
                break

            tempo_espera = retry_sugerido or (tentativa * 45)
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            if tentativa < max_tentativas:
                time.sleep(tempo_espera)

    if not relatorio:
        print("Erro crítico: Não foi possível obter resposta da API do Gemini.")
        enviar_telegram(
            "⚠️ <b>Robô de apostas não conseguiu gerar o relatório hoje.</b>\n"
            f"Motivo: {str(ultimo_erro)[:300]}\n"
            f"(Jogos encontrados pela API-Football: {len(jogos)} — o problema foi na etapa de análise do Gemini.)"
        )
        return

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
