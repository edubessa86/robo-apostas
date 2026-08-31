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
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

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


def verificar_status_api_football(api_key: str) -> bool:
    """Camada de precaução: Verifica cota e status via endpoint /status antes de gastar requisições."""
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response", {})
            
            # Tratamento seguro caso a resposta venha como lista ou dicionário
            if isinstance(resp_data, list):
                requests_info = resp_data[0].get("requests", {}) if resp_data else {}
            elif isinstance(resp_data, dict):
                requests_info = resp_data.get("requests", {})
            else:
                requests_info = {}

            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            print(f"API-Football Status -> Consumidas hoje: {current}/{limit}")
            if current < limit:
                return True
        else:
            print(f"Erro ao checar status da API-Football: {response.status_code}")
    except Exception as e:
        print(f"Falha de conexão ao checar status da API-Football: {e}")
    return False


def buscar_jogos_api_football_com_fallback(data_hoje_iso: str):
    """Gerencia API Principal (Key 1) e Secundária (Key 2) com verificação prévia de cota."""
    chaves = [
        ("API Principal (API_FOOTBALL_KEY)", API_FOOTBALL_KEY),
        ("API Secundária (API_FOOTBALL_KEY_2)", API_FOOTBALL_KEY_2)
    ]
    
    for nome, chave in chaves:
        if not chave:
            continue
        print(f"Verificando cota da {nome}...")
        if verificar_status_api_football(chave):
            print(f"Buscando partidas do dia {data_hoje_iso} via {nome}...")
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        print(f"Sucesso! Encontrados {len(dados)} jogos via {nome}.")
                        return dados, nome
                    else:
                        print(f"{nome} retornou 0 jogos para hoje.")
            except Exception as e:
                print(f"Erro ao requisitar jogos via {nome}: {e}")
        else:
            print(f"{nome} sem cota disponível ou falha na validação de status.")
    return None, None


def buscar_jogos_espn():
    """Terceira camada de precaução: Conferência cruzada via endpoint público de placares da ESPN."""
    print("Acionando 3ª camada de precaução: Conferência cruzada via endpoint público da ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            eventos = data.get("events", [])
            print(f"ESPN retornou {len(eventos)} eventos para cruzamento.")
            return eventos
    except Exception as e:
        print(f"Erro ao consultar endpoint público da ESPN: {e}")
    return []


def extrair_retry_after(erro: Exception) -> int | None:
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
    if retry_after is not None:
        return False
    texto_erro = str(erro).lower()
    return "resource_exhausted" in texto_erro.replace(" ", "") or "429" in texto_erro


def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um sistema automatizado de análise esportiva para apostas.

Com base nos dados obtidos das fontes de verificação ({data_hoje}, fuso de Brasília, UTC-3) a partir das 10h, traga as melhores apostas esportivas:
- Contexto de dados estruturados: {dados_jogos_str}

REGRAS OBRIGATÓRIAS (siga rigorosamente):
- Toda odd, probabilidade, placar provável ou estatística citada TEM que vir de uma fonte real encontrada. Cite o nome da fonte entre parênteses ao lado da informação.
- PROIBIDO inventar notas de "confiança" ou placares prováveis que não constem nas fontes.
- Se não encontrar dados suficientes para um evento, não o inclua.
- NUNCA invente confrontos, jogos ou competições que não apareceram nas fontes.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO PARA O TELEGRAM (HTML)
Utilize tags HTML limpas do Telegram (`<b>`, `<i>`) seguindo estritamente esta estrutura:

⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
(Para cada evento encontrado, liste de forma objetiva:)
- <b>[Time A] x [Time B]</b> ([Competição], [Horário])
- Provável vencedor: [conforme fonte]
- Odd: [valor, com fonte entre parênteses]
- Estatísticas prováveis (escanteios, gols, cartões, finalizações, chutes ao gol), sempre com fonte

━━━━━━━━━━━━━━━━━━
📊 <b>DESTAQUES E PROJEÇÕES</b>
- Resumo analítico dos eventos do dia, citando as fontes usadas.

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Nenhuma aposta é 100% garantida; odds e estatísticas acima vêm de fontes públicas e podem mudar. Aposte com responsabilidade.

Logo abaixo, inclua obrigatoriamente este bloco promocional:
JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    # 1ª e 2ª Camada: API-Football (Chave 1 e Chave 2 com verificação prévia de status)
    jogos_brutos, fonte_usada = buscar_jogos_api_football_com_fallback(data_hoje_iso)
    
    dados_contexto = ""
    if jogos_brutos:
        dados_contexto = f"Partidas obtidas via {fonte_usada}: {str(jogos_brutos[:15])}"
    else:
        print("APIs de Futebol (Principal e Secundária) indisponíveis ou sem jogos. Acionando Camada 3 (ESPN)...")
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            dados_contexto = f"Partidas obtidas via conferência cruzada ESPN: {str(eventos_espn[:15])}"
        else:
            dados_contexto = "Nenhum jogo retornado pelas APIs estruturadas; utilize rigorosamente o Grounding do Google Search."

    prompt_mestre = montar_prompt(data_hoje, dados_contexto)

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"Gerando análise de apostas para hoje ({data_hoje}) via {MODELO}...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None
    ultimo_erro = None

    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
                config=config,
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            ultimo_erro = e
            tentativa += 1
            retry_sugerido = extrair_retry_after(e)

            if eh_erro_de_cota_esgotada(e, retry_sugerido):
                print(f"Cota esgotada na API do Gemini: {e}. Abortando.")
                break

            tempo_espera = retry_sugerido or (tentativa * 45)
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            if tentativa < max_tentativas:
                time.sleep(tempo_espera)

    if not relatorio:
        print("Erro crítico: Não foi possível obter resposta da API do Gemini devido à cota.")
        # Fallback inteligente: se o Gemini estourar a cota mas temos dados das APIs de futebol/ESPN, enviamos o resumo direto
        if dados_contexto and "Nenhum jogo retornado" not in dados_contexto:
            relatorio_fallback = f"""⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>STATUS DO SISTEMA</b>
O assistente de IA atingiu temporariamente o limite de cota da API (429), mas os dados foram capturados com sucesso pelas camadas de redundância.

📊 <b>DADOS BRUTOS CAPTURADOS:</b>
<code>{str(dados_contexto)[:1500]}</code>

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Aposte com responsabilidade.

JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3"""
            enviar_telegram(relatorio_fallback)
        else:
            enviar_telegram(
                "⚠️ <b>Robô de apostas não conseguiu gerar o relatório hoje.</b>\n"
                f"Motivo: {str(ultimo_erro)[:300]}"
            )
        return

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
