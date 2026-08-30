from datetime import datetime
import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODELO = "gemini-2.5-flash"  # gemini-3.6-flash não tem grounding grátis via API (só no AI Studio);
                              # gemini-2.5-flash tem até 500 buscas grátis/dia, suficiente para 1 run diário.

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


def montar_prompt(data_hoje: str) -> str:
    """Monta o prompt para o Gemini.

    Esta versão usa grounding com Google Search (ver `config` em
    `executar_robo_apostas`) porque agora cobrimos qualquer esporte, não só
    futebol — a API-Football sozinha não dá conta disso.

    IMPORTANTE: como não há mais uma lista de jogos pré-verificada vindo de
    uma API, a única defesa contra hallucination aqui são estas regras de
    citação obrigatória. Sem uma fonte real por trás de cada número, o
    modelo tende a inventar "confiança" e placares — por isso isso é
    proibido explicitamente abaixo.
    """
    return f"""
Você é um sistema automatizado de análise esportiva para apostas.

Pesquise na internet (em todos os lugares: sites de estatística esportiva,
casas de apostas, portais de notícias esportivas) e traga todas as apostas
esportivas de qualquer esporte de hoje ({data_hoje}, fuso de Brasília, UTC-3)
a partir das 10h. Para cada evento encontrado, traga:
- Os confrontos do dia
- Prováveis vencedores
- Odds confiáveis para apostar
- Caso seja futebol: prováveis quantidade de escanteios, gols, cartões,
  finalizações e chutes ao gol

REGRAS OBRIGATÓRIAS (siga rigorosamente):
- Toda odd, probabilidade, placar provável ou estatística (escanteios, gols,
  cartões, finalizações, chutes ao gol) que você citar TEM que vir de uma
  fonte real que você encontrou na busca. Cite o nome do site entre
  parênteses ao lado da informação, como "(SportyTrader)" ou "(Forebet)".
- PROIBIDO inventar uma nota de "confiança" própria (ex: 8/10, 9.5/10) que
  não tenha sido dita por nenhuma fonte. Se quiser comunicar confiança, use
  apenas o que a própria fonte afirmou (ex: "Forebet aponta 60% de chance de
  vitória"), nunca um número inventado por você.
- PROIBIDO inventar um placar provável que não tenha sido citado por
  nenhuma fonte encontrada na busca.
- Se não encontrar dados suficientemente confiáveis e citáveis para um
  evento, não o inclua no relatório — não complete com estimativas soltas.
- NUNCA invente confrontos, jogos, times ou competições que não apareceram
  nas buscas.
- Não copie frases inteiras das fontes; resuma com suas próprias palavras.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO PARA O TELEGRAM (HTML)
Utilize tags HTML limpas do Telegram (`<b>`, `<i>`) seguindo estritamente esta estrutura:

⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
(Para cada evento encontrado na busca, liste de forma objetiva:)
- <b>[Time/Competidor A] x [Time/Competidor B]</b> ([Competição], [Horário])
- Prováveis vencedor: [conforme fonte]
- Odd: [valor, com fonte entre parênteses]
- Se futebol: estatísticas prováveis (escanteios, gols, cartões, finalizações,
  chutes ao gol), sempre com fonte

━━━━━━━━━━━━━━━━━━
📊 <b>DESTAQUES E PROJEÇÕES</b>
- Resumo analítico dos eventos do dia, citando as fontes usadas.

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Nenhuma aposta é 100% garantida;
odds e estatísticas acima vêm de fontes públicas e podem mudar. Aposte com responsabilidade.

Logo abaixo, inclua obrigatoriamente este bloco promocional:
JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    prompt_mestre = montar_prompt(data_hoje)

    # Grounding com Google Search: necessário porque agora cobrimos qualquer
    # esporte, "em todos os lugares" — não dá pra restringir a uma API só.
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"Pesquisando apostas de hoje ({data_hoje}) com grounding via {MODELO}...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None
    ultimo_erro = None
    fontes = []

    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
                config=config,
            )
            relatorio = response.text

            # Log das fontes usadas, para você conferir se o modelo pesquisou
            # de verdade ou caiu de novo em modo "chute".
            try:
                candidato = response.candidates[0]
                if candidato.grounding_metadata and candidato.grounding_metadata.grounding_chunks:
                    fontes = [
                        chunk.web.uri
                        for chunk in candidato.grounding_metadata.grounding_chunks
                        if chunk.web
                    ]
                    print(f"Fontes usadas na busca ({len(fontes)}): {fontes}")
                else:
                    print("Aviso: nenhuma fonte de busca retornada pelo Gemini.")
            except (AttributeError, IndexError):
                pass

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
            f"Motivo: {str(ultimo_erro)[:300]}"
        )
        return

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
