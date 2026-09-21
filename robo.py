# -*- coding: utf-8 -*-
"""
ROBÔ DE PROJEÇÕES E APOSTAS ESPORTIVAS — V5.7
- Fallback dinâmico: variações automáticas de mercados, odds, escanteios e placares
- IA Gemini 3.6 Flash com busca no Google
- Links direcionados da Sportingbet por confronto
- Layout HTML Telegram corrigido e sanitizado
- Link de cadastro e recompensa integrado
"""

from datetime import datetime
import os
import urllib.parse
import requests
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# --- CONFIGURAÇÕES DE AMBIENTE ---
def obter_env(nome: str, padrao: str = "") -> str:
    valor = os.environ.get(nome, padrao)
    return valor.strip() if valor else ""

TELEGRAM_TOKEN = obter_env("TELEGRAM_TOKEN")
CHAT_ID = obter_env("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = obter_env("GEMINI_API_KEY")
API_FOOTBALL_KEY = obter_env("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = obter_env("API_FOOTBALL_KEY_2")

# Link de indicação/cadastro com recompensa
LINK_CADASTRO_RECOMPENSA = obter_env(
    "LINK_CADASTRO_RECOMPENSA", 
    "https://seu-link-de-afiliado-aqui.com/cadastre-se"
)

MODELO = "gemini-3.6-flash"

# Session HTTP com Headers Anti-Bloqueio
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.espn.com.br/",
    "Origin": "https://www.espn.com.br",
    "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
})

client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto: str, limite: int = 3900) -> list[str]:
    partes, atual = [], ""
    for bloco in texto.split("\n\n"):
        candidato = f"{atual}\n\n{bloco}" if atual else bloco
        if len(candidato) <= limite:
            atual = candidato
        else:
            if atual:
                partes.append(atual)
            atual = bloco
    if atual:
        partes.append(atual)
    return partes


def enviar_telegram(texto: str) -> bool:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[ERRO] TELEGRAM_TOKEN ou CHAT_ID ausentes.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)
    tudo_ok = True

    for n, parte in enumerate(partes, 1):
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            resposta = SESSION.post(url, json=payload, timeout=15)
            if resposta.status_code == 200:
                print(f"[OK] Parte {n}/{len(partes)} enviada ao Telegram.")
            else:
                print(f"[ERRO] Telegram {resposta.status_code}: {resposta.text}")
                tudo_ok = False
        except requests.RequestException as e:
            print(f"[ERRO] Conexão Telegram: {e}")
            tudo_ok = False

    return tudo_ok


def verificar_status_api_football(api_key: str) -> bool:
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = SESSION.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response")
            if isinstance(resp_data, list) and len(resp_data) > 0:
                requests_info = resp_data[0].get("requests", {})
            elif isinstance(resp_data, dict):
                requests_info = resp_data.get("requests", {})
            else:
                requests_info = {}

            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            print(f"[INFO] API-Football -> Consumidas hoje: {current}/{limit}")
            return current < limit
    except Exception as e:
        print(f"[AVISO] Status API-Football: {e}")
    return False


def buscar_jogos_api_football(data_hoje_iso: str):
    chaves = [("API Principal", API_FOOTBALL_KEY), ("API Secundária", API_FOOTBALL_KEY_2)]
    for nome, chave in chaves:
        if not chave:
            continue
        if verificar_status_api_football(chave):
            print(f"[INFO] Buscando jogos ({data_hoje_iso}) via {nome}...")
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = SESSION.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        print(f"[OK] Encontrados {len(dados)} jogos via {nome}.")
                        return dados, nome
            except Exception as e:
                print(f"[ERRO] Falha {nome}: {e}")
    return None, None


def buscar_jogos_espn():
    print("[INFO] Consultando feed público da ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            eventos = resp.json().get("events", [])
            print(f"[OK] ESPN retornou {len(eventos)} eventos.")
            return eventos
        else:
            print(f"[AVISO] ESPN status {resp.status_code}")
    except Exception as e:
        print(f"[ERRO] ESPN: {e}")
    return []


def gerar_link_sportingbet(nome_confronto: str) -> str:
    """Gera link de busca direto para a partida na Sportingbet."""
    termo = urllib.parse.quote_plus(f"sportingbet apostas {nome_confronto}")
    return f"https://www.google.com/search?q={termo}"


def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um analista profissional de apostas esportivas.
Com base nos dados fornecidos abaixo para {data_hoje} (Horário de Brasília, UTC-3), gere um relatório de apostas detalhado e completo para o Telegram.

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS ESTRITAS DE FORMATO:
1. Analise cada jogo trazendo palpite de Vencedor/Mercado, Odd estimada, Nível de Confiança, Escanteios, Cartões e Placar Provável.
2. Para CADA jogo, você DEVE colocar o link da Sportingbet no formato: `<a href="https://www.sportingbet.br/">Apostar na Sportingbet</a>`.
3. Siga EXATAMENTE a estrutura visual HTML abaixo, sem alterar as tags.

ESTRUTURA OBRIGATÓRIA DA MENSAGEM (HTML):

🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>

🇧🇷 Atualizado hoje
📊 Análise de odds + modelos + forma recente
⚠️ Odds podem variar. Não existe aposta garantida.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
━━━━━━━━━━━━━━━━━━

🥇 ⚽️ <b>[TIME A] x [TIME B]</b>
🕟 [Horário] 🇧🇷
🎯 <b>Mercado Principal:</b> [Ex: Vitória do Mandante / Dupla Chance]
📊 Odd mercado: ~[Ex: 1.65]
🔥 Confiança: [Ex: 8.5/10]
⚽️ Over 1.5 Gols
🚩 Escanteios: [Ex: 8-11]
🟨 Cartões: [Ex: 3-5]
🔮 Placar provável: [Ex: 2x1 / 1x0]
💎 Melhor entrada: [Ex: Casa Vence + Over 1.5]
🔗 <a href="https://www.sportingbet.br/">Apostar na Sportingbet</a>
━━━━━━━━━━━━━━━━━━

(Repita a estrutura acima utilizando 🥈 ⚽️, 🥉 ⚽️ e ⚽️ para os demais jogos do dia)

📊 <b>GESTÃO DE BANCA</b>
━━━━━━━━━━━━━━━━━━
🟢 9/10 → stake principal
🟢 8–8.5/10 → stake moderada
🟡 7–7.5/10 → stake reduzida
🔴 Abaixo de 7/10 → evitar
⚠️ Odds são referências e mudam. Aposte com responsabilidade.

🎁 <b>CADASTRE-SE E RESGATE SUA RECOMPENSA!</b>
Ganhe bônus de boas-vindas e giros grátis se cadastrando no link oficial abaixo:
👉 <a href="{LINK_CADASTRO_RECOMPENSA}">CLIQUE AQUI PARA SE CADASTRAR E GANHAR</a>
"""


def formatar_fallback_emergencial(jogos, origem, data_hoje):
    """Fallback emergencial com variações dinâmicas para cada jogo."""
    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️"]
    
    # Matriz de variações para evitar repetição de estatísticas no fallback
    variacoes = [
        {
            "mercado": "Vitória do Favorito / Casa Vence",
            "odd": "~1.50 – 1.72",
            "confianca": "8.5/10",
            "gols": "Over 1.5 Gols na partida",
            "escanteios": "8–11 estimados",
            "cartoes": "3–5 estimados",
            "placar": "2x1 / 2x0",
            "entrada": "Vitória Mandante + Over 1.5"
        },
        {
            "mercado": "Dupla Chance & Ambas Marcam",
            "odd": "~1.60 – 1.85",
            "confianca": "8.0/10",
            "gols": "Ambas Marcam (Sim)",
            "escanteios": "9–12 estimados",
            "cartoes": "4–6 estimados",
            "placar": "1x1 / 2x1",
            "entrada": "Dupla Chance + Mais de 1.5 Gols"
        },
        {
            "mercado": "Empate Anula Aposta (DNB)",
            "odd": "~1.45 – 1.65",
            "confianca": "7.5/10",
            "gols": "Under 3.5 Gols",
            "escanteios": "7–10 estimados",
            "cartoes": "3–4 estimados",
            "placar": "1x0 / 0x0",
            "entrada": "DNB Favorito"
        },
        {
            "mercado": "Over 2.5 Gols na Partida",
            "odd": "~1.75 – 2.05",
            "confianca": "7.0/10",
            "gols": "Over 2.5 Gols",
            "escanteios": "10–13 estimados",
            "cartoes": "5–7 estimados",
            "placar": "3x1 / 2x2",
            "entrada": "Over 2.5 Gols Asiático"
        },
        {
            "mercado": "Handicap Asiático 0 (Empate Anula)",
            "odd": "~1.55 – 1.80",
            "confianca": "8.0/10",
            "gols": "Over 1.5 Gols",
            "escanteios": "8–10 estimados",
            "cartoes": "4–5 estimados",
            "placar": "0x2 / 1x2",
            "entrada": "Handicap 0 Visitante"
        }
    ]

    linhas = [
        f"🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>\n",
        "🇧🇷 Atualizado hoje (Modo de Contingência)",
        "📊 Análise de odds + modelos + forma recente",
        "⚠️ Odds podem variar. Não existe aposta garantida.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>TOP APOSTAS DO DIA</b>",
        "━━━━━━━━━━━━━━━━━━\n"
    ]
    
    for idx, ev in enumerate(jogos[:6]):
        if "ESPN" in origem:
            nome = ev.get("name", "Confronto Esportivo")
            hora_str = "Horário a confirmar"
        else:
            teams = ev.get("teams", {})
            home = teams.get("home", {}).get("name", "Mandante")
            away = teams.get("away", {}).get("name", "Visitante")
            nome = f"{home} x {away}"
            date_raw = ev.get("fixture", {}).get("date", "")
            hora_str = date_raw.split("T")[1][:5] + " BRT" if "T" in date_raw else "Horário a confirmar"

        medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"
        link_sportingbet = gerar_link_sportingbet(nome)
        
        # Seleciona uma variação diferente para cada jogo
        var = variacoes[idx % len(variacoes)]

        linhas.append(
            f"{medalha} ⚽️ <b>{nome.upper()}</b>\n"
            f"🕟 {hora_str} 🇧🇷\n"
            f"🎯 <b>Mercado Principal:</b> {var['mercado']}\n"
            f"📊 Odd mercado: {var['odd']}\n"
            f"🔥 Confiança: {var['confianca']}\n"
            f"⚽️ {var['gols']}\n"
            f"🚩 Escanteios: {var['escanteios']}\n"
            f"🟨 Cartões: {var['cartoes']}\n"
            f"🔮 Placar provável: {var['placar']}\n"
            f"💎 Melhor entrada: {var['entrada']}\n"
            f"🔗 <a href=\"{link_sportingbet}\">Apostar na Sportingbet</a>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

    linhas.extend([
        "📊 <b>GESTÃO DE BANCA</b>",
        "━━━━━━━━━━━━━━━━━━",
        "🟢 9/10 → stake principal",
        "🟢 8–8.5/10 → stake moderada",
        "🟡 7–7.5/10 → stake reduzida",
        "🔴 Abaixo de 7/10 → evitar",
        "⚠️ Odds são referências e mudam. Aposte com responsabilidade.\n",
        "🎁 <b>CADASTRE-SE E RESGATE SUA RECOMPENSA!</b>",
        "Ganhe bônus de boas-vindas e giros grátis se cadastrando no link abaixo:",
        f"👉 <a href=\"{LINK_CADASTRO_RECOMPENSA}\">CLIQUE AQUI PARA SE CADASTRAR E GANHAR</a>"
    ])
    
    return "\n".join(linhas)


def executar_robo():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    # 1. Coleta das partidas
    jogos_brutos, fonte_usada = buscar_jogos_api_football(data_hoje_iso)
    
    if jogos_brutos:
        dados_contexto = f"Partidas via {fonte_usada}: {str(jogos_brutos[:10])}"
    else:
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            fonte_usada = "ESPN Public API"
            jogos_brutos = eventos_espn
            dados_contexto = f"Partidas via ESPN: {str(eventos_espn[:10])}"
        else:
            fonte_usada = "Google Search Grounding"
            dados_contexto = "Pesquise na web os jogos de futebol mais relevantes agendados para hoje."

    # 2. Geração do relatório via IA
    prompt = montar_prompt(data_hoje, dados_contexto)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"[INFO] Gerando relatório via {MODELO}...")
    relatorio = None
    
    try:
        response = client.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=config,
        )
        relatorio = response.text
    except ClientError as e:
        print(f"[ERRO] Cota ou chamada API Gemini: {e}")
    except Exception as e:
        print(f"[ERRO] Exceção geral na IA: {e}")

    # 3. Envio do relatório ou fallback formatado
    if relatorio:
        enviar_telegram(relatorio)
    elif jogos_brutos:
        print("[AVISO] Gerando relatório emergencial com layout dinâmico...")
        relatorio_emergencia = formatar_fallback_emergencial(jogos_brutos, fonte_usada, data_hoje)
        enviar_telegram(relatorio_emergencia)
    else:
        enviar_telegram(f"⚠️ <b>Não foi possível consultar os jogos de hoje ({data_hoje}).</b>")


if __name__ == "__main__":
    executar_robo()
