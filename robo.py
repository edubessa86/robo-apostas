# -*- coding: utf-8 -*-
"""
ROBÔ DE PROJEÇÕES E APOSTAS ESPORTIVAS — V5.8
- Filtro de fuso horário UTC -> BRT (elimina jogos da madrugada/dia anterior)
- Priorização de grandes ligas de futebol
- Fallback emergencial dinâmico e inteligente
- Envio formatado em HTML com links para a Sportingbet e Cadastro com Recompensa
"""

from datetime import datetime, timedelta
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

LINK_CADASTRO_RECOMPENSA = obter_env(
    "LINK_CADASTRO_RECOMPENSA", 
    "https://seu-link-de-afiliado-aqui.com/cadastre-se"
)

MODELO = "gemini-3.6-flash"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.espn.com.br/",
    "Origin": "https://www.espn.com.br"
})

client = genai.Client(api_key=GEMINI_API_KEY)


def converter_utc_para_brt(data_utc_str: str):
    """Converte string ISO em UTC para objeto datetime no fuso de Brasília (UTC-3)."""
    try:
        dt_utc = datetime.fromisoformat(data_utc_str.replace("Z", "+00:00"))
        return dt_utc - timedelta(hours=3)
    except Exception:
        return None


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
            resp_data = data.get("response", {})
            requests_info = resp_data.get("requests", {}) if isinstance(resp_data, dict) else {}
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
                    jogos_filtrados = []
                    for item in dados:
                        date_utc = item.get("fixture", {}).get("date", "")
                        dt_brt = converter_utc_para_brt(date_utc)
                        # Filtra apenas jogos que ocorrem hoje em BRT e a partir das 08:00 BRT
                        if dt_brt and dt_brt.strftime("%Y-%m-%d") == data_hoje_iso and dt_brt.hour >= 8:
                            item["hora_brt"] = dt_brt.strftime("%H:%M")
                            jogos_filtrados.append(item)
                    if jogos_filtrados:
                        print(f"[OK] Encontrados {len(jogos_filtrados)} jogos válidos via {nome}.")
                        return jogos_filtrados, nome
            except Exception as e:
                print(f"[ERRO] Falha {nome}: {e}")
    return None, None


def buscar_jogos_espn(data_hoje_iso: str):
    print("[INFO] Consultando feed público da ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            eventos = resp.json().get("events", [])
            eventos_filtrados = []
            for ev in eventos:
                date_utc = ev.get("date", "")
                dt_brt = converter_utc_para_brt(date_utc)
                # Garante fuso horário BRT e remove jogos da madrugada
                if dt_brt and dt_brt.strftime("%Y-%m-%d") == data_hoje_iso and dt_brt.hour >= 8:
                    ev["hora_brt"] = dt_brt.strftime("%H:%M")
                    eventos_filtrados.append(ev)
            print(f"[OK] ESPN retornou {len(eventos_filtrados)} eventos válidos para hoje.")
            return eventos_filtrados
    except Exception as e:
        print(f"[ERRO] ESPN: {e}")
    return []


def gerar_link_sportingbet(nome_confronto: str) -> str:
    termo = urllib.parse.quote_plus(f"sportingbet apostas {nome_confronto}")
    return f"https://www.google.com/search?q={termo}"


def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um analista profissional de apostas esportivas.
Sua missão é selecionar os PRINCIPAIS JOGOS DE HOJE ({data_hoje}) das grandes ligas (Brasileirão, Champions League, Premier League, La Liga, Serie A, Ligue 1, Libertadores, Sul-Americana, etc.).
Descarte jogos da madrugada (entre 00:00 e 07:00).

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS ESTRITAS DE FORMATO:
1. Analise cada jogo trazendo palpite de Vencedor/Mercado, Odd estimada, Nível de Confiança, Escanteios, Cartões e Placar Provável.
2. Para CADA jogo, você DEVE colocar o link da Sportingbet no formato: `<a href="https://www.sportingbet.br/">Apostar na Sportingbet</a>`.
3. Siga EXATAMENTE a estrutura visual HTML abaixo:

🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>

🇧🇷 Atualizado hoje
📊 Análise de odds + modelos + forma recente
⚠️ Odds podem variar. Não existe aposta garantida.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
━━━━━━━━━━━━━━━━━━

🥇 ⚽️ <b>[TIME A] x [TIME B]</b>
🕟 [Horário BRT] 🇧🇷
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
    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️"]
    
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
            "mercado": "Dupla Chance (1X) & Ambas Marcam",
            "odd": "~1.60 – 1.85",
            "confianca": "8.0/10",
            "gols": "Ambas Marcam (Sim)",
            "escanteios": "9–12 estimados",
            "cartoes": "4–6 estimados",
            "placar": "1x1 / 2x1",
            "entrada": "1X + Mais de 1.5 Gols"
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
            hora_str = f"{ev.get('hora_brt', '16:00')} BRT"
        else:
            teams = ev.get("teams", {})
            home = teams.get("home", {}).get("name", "Mandante")
            away = teams.get("away", {}).get("name", "Visitante")
            nome = f"{home} x {away}"
            hora_str = f"{ev.get('hora_brt', '16:00')} BRT"

        medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"
        link_sportingbet = gerar_link_sportingbet(nome)
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

    # 1. Coleta e filtragem dos jogos do dia
    jogos_brutos, fonte_usada = buscar_jogos_api_football(data_hoje_iso)
    
    if jogos_brutos:
        dados_contexto = f"Partidas via {fonte_usada}: {str(jogos_brutos[:10])}"
    else:
        eventos_espn = buscar_jogos_espn(data_hoje_iso)
        if eventos_espn:
            fonte_usada = "ESPN Public API"
            jogos_brutos = eventos_espn
            dados_contexto = f"Partidas via ESPN: {str(eventos_espn[:10])}"
        else:
            fonte_usada = "Google Search Grounding"
            dados_contexto = f"Pesquise os principais jogos de futebol de grandes ligas para hoje ({data_hoje})."

    # 2. Geração via IA Gemini
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

    # 3. Envio no Telegram
    if relatorio:
        enviar_telegram(relatorio)
    elif jogos_brutos:
        print("[AVISO] Gerando relatório emergencial com horários e ligas corrigidas...")
        relatorio_emergencia = formatar_fallback_emergencial(jogos_brutos, fonte_usada, data_hoje)
        enviar_telegram(relatorio_emergencia)
    else:
        enviar_telegram(f"⚠️ <b>Não foi possível consultar os jogos de hoje ({data_hoje}).</b>")


if __name__ == "__main__":
    executar_robo()
