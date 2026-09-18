from datetime import datetime
import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

MODELO = "gemini-3.6-flash"

def dividir_mensagem(texto, limite=4000):
    """Divide textos longos em pedaços menores para respeitar o limite do Telegram."""
    return [texto[i:i + limite] for i in range(0, len(texto), limite)]

def enviar_telegram(texto: str) -> None:
    """Envia uma mensagem (dividida se necessário) para o Telegram."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro crítico: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não definidos.")
        return

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
    """Verifica cota e status via endpoint /status antes de gastar requisições."""
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response", {})
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
    except Exception as e:
        print(f"Falha de conexão ao checar status da API-Football: {e}")
    return False

def buscar_jogos_api_football_com_fallback(data_hoje_iso: str):
    """Gerencia API Principal e Secundária com verificação prévia de cota."""
    chaves = [
        ("API Principal (API_FOOTBALL_KEY)", API_FOOTBALL_KEY),
        ("API Secundária (API_FOOTBALL_KEY_2)", API_FOOTBALL_KEY_2)
    ]
    
    for nome, chave in chaves:
        if not chave:
            continue
        if verificar_status_api_football(chave):
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        return dados, nome
            except Exception as e:
                print(f"Erro ao requisitar jogos via {nome}: {e}")
    return None, None

def buscar_jogos_espn():
    """Terceira camada de precaução: Consulta ao endpoint público da ESPN."""
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("events", [])
    except Exception as e:
        print(f"Erro ao consultar endpoint público da ESPN: {e}")
    return []

def relatorio_fallback_limpo(data_hoje, motivo=None):
    """Gera um relatório de segurança simplificado caso a IA falhe (cota, chave
    inválida, modelo indisponível, erro de rede, etc.).

    Antes esta mensagem sempre dizia "Cota Excedida" mesmo quando o erro real
    era outro (ex.: chave inválida, nome de modelo errado). Agora, quando o
    motivo é conhecido, ele aparece na própria mensagem do Telegram — assim dá
    pra diagnosticar sem precisar abrir o log do GitHub Actions.
    """
    if motivo:
        linha_motivo = f"⚠️ Detalhe técnico do erro: {motivo}"
    else:
        linha_motivo = (
            "A inteligência artificial atingiu o limite gratuito de análises de hoje (Cota Excedida)."
        )
    return f"""⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
⚠️ <b>Aviso de Sistema:</b> 
{linha_motivo}
Os palpites detalhados e cruzamento de dados retornarão automaticamente amanhã!

🏆 <b>Dica de Gestão de Banca:</b>
Mantenha rigor na gestão de banca e controle de stakes. Nunca aposte o que não pode perder.

━━━━━━━━━━━━━━━━━━
JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""

def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um sistema automatizado de análise profissional de apostas esportivas.

Com base estritamente nos dados dos jogos fornecidos abaixo para a data de hoje ({data_hoje}, fuso de Brasília, UTC-3), produza um relatório de apostas de altíssimo nível para o Telegram.

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS OBRIGATÓRIAS:
- Use APENAS os jogos presentes nos dados acima ou buscados via Search. NUNCA invente confrontos.
- Siga rigorosamente a estrutura visual abaixo usando tags HTML (`<b>`, `<i>`).

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO:

🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>

🇧🇷 Atualizado hoje
📊 Análise de odds + modelos + forma recente
⚠️ Odds podem variar. Não existe aposta garantida.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
━━━━━━━━━━━━━━━━━━
(Para cada jogo disponível, siga este formato:)
🥇 ⚽️ <b>[Time A] x [Time B]</b>
🕟 [Horário] 🇧🇷
🎯 [Melhor Mercado/Seleção]
📊 Odd mercado: ~[Valor]
🔥 Confiança: [X]/10
⚽️ [Mercado de Gols / Outros dados]
🚩 Escanteios: [Estimativa]
🟨 Cartões: [Estimativa]
🔮 Placar: [Placar provável]
💎 Melhor entrada: [Aposta Principal]
━━━━━━━━━━━━━━━━━━
📊 <b>GESTÃO DE BANCA</b>
━━━━━━━━━━━━━━━━━━
🟢 9/10 → stake principal
🟢 8–8.5/10 → stake moderada
🟡 7–7.5/10 → stake reduzida
🔴 Abaixo de 7/10 → evitar
⚠️ Odds são referências e mudam.

JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""

def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    jogos_brutos, fonte_usada = buscar_jogos_api_football_com_fallback(data_hoje_iso)
    
    if jogos_brutos:
        dados_contexto = f"Partidas obtidas via {fonte_usada}: {str(jogos_brutos[:15])}"
    else:
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            dados_contexto = f"Partidas obtidas via ESPN: {str(eventos_espn[:15])}"
        else:
            dados_contexto = "Utilize a ferramenta de busca para localizar jogos de hoje."

    prompt_mestre = montar_prompt(data_hoje, dados_contexto)

    relatorio = None
    erro_capturado = None
    if not GEMINI_API_KEY:
        erro_capturado = "GEMINI_API_KEY não está definida (confira o Secret no GitHub)."
    else:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
                config=config,
            )
            relatorio = response.text
        except Exception as e:
            erro_capturado = str(e)[:300]
            print(f"Erro na geração Gemini: {e}")

    if not relatorio:
        relatorio = relatorio_fallback_limpo(data_hoje, motivo=erro_capturado)

    enviar_telegram(relatorio)

if __name__ == "__main__":
    executar_robo_apostas()
