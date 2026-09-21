# -*- coding: utf-8 -*-
"""
ROBÔ DE PROJEÇÕES E APOSTAS ESPORTIVAS — V5.3
- Proteção contra bloqueio HTTP 403 (Headers de Navegador Completo)
- Integração com Gemini API (gemini-2.5-flash) + Google Search Grounding
- Fallback para API-Football e ESPN Public API
- Link de cadastro personalizado com recompensa ao final das mensagens
"""

from datetime import datetime
import html
import os
import time
import requests
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# --- CONFIGURAÇÕES DE AMBIENTE ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

# Link de indicação/cadastro com recompensa (Pode ser configurado nas Secrets do GitHub)
LINK_CADASTRO_RECOMPENSA = os.environ.get(
    "LINK_CADASTRO_RECOMPENSA", 
    "https://seu-link-de-afiliado-aqui.com/cadastre-se"  # <-- Substitua pelo seu novo link se preferir deixar fixo
)

MODELO = "gemini-2.5-flash"

# Session com Headers anti-bloqueio (Evita HTTP 403 no GitHub Actions)
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

# Inicialização do cliente Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto: str, limite: int = 3900) -> list[str]:
    """Divide mensagens respeitando blocos para não quebrar a sintaxe do Telegram."""
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
    """Envia o relatório formatado em HTML para o Telegram."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[ERRO] Variáveis TELEGRAM_TOKEN ou CHAT_ID não configuradas.")
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
                print(f"[OK] Parte {n}/{len(partes)} enviada para o Telegram!")
            else:
                print(f"[ERRO] Telegram recusou parte {n}: {resposta.status_code} - {resposta.text}")
                tudo_ok = False
        except requests.RequestException as e:
            print(f"[ERRO] Falha de conexão com o Telegram: {e}")
            tudo_ok = False

    return tudo_ok


def verificar_status_api_football(api_key: str) -> bool:
    """Valida cota disponível na API-Football."""
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = SESSION.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response", {})
            requests_info = resp_data[0].get("requests", {}) if isinstance(resp_data, list) and resp_data else resp_data.get("requests", {})
            
            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            print(f"[INFO] API-Football -> Consumidas hoje: {current}/{limit}")
            return current < limit
    except Exception as e:
        print(f"[AVISO] Falha ao verificar cota da API-Football: {e}")
    return False


def buscar_jogos_api_football(data_hoje_iso: str):
    """Busca partidas via API-Football."""
    chaves = [
        ("API Principal", API_FOOTBALL_KEY),
        ("API Secundária", API_FOOTBALL_KEY_2)
    ]
    
    for nome, chave in chaves:
        if not chave:
            continue
        if verificar_status_api_football(chave):
            print(f"[INFO] Buscando partidas ({data_hoje_iso}) via {nome}...")
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
                print(f"[ERRO] Falha na consulta via {nome}: {e}")
    return None, None


def buscar_jogos_espn():
    """Busca jogos via endpoint da ESPN utilizando headers protegidos."""
    print("[INFO] Consultando partidas via feed público da ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            eventos = resp.json().get("events", [])
            print(f"[OK] ESPN retornou {len(eventos)} eventos.")
            return eventos
        else:
            print(f"[AVISO] ESPN respondeu com status {resp.status_code}")
    except Exception as e:
        print(f"[ERRO] Falha ao consultar ESPN: {e}")
    return []


def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    """Gera a instrução do prompt incluindo o novo link de cadastro com recompensa."""
    return f"""
Você é um sistema automatizado de análise profissional de apostas esportivas.
Com base nos dados fornecidos abaixo para a data de hoje ({data_hoje}, fuso de Brasília, UTC-3), produza um relatório de apostas de altíssimo nível para o Telegram.

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS OBRIGATÓRIAS:
1. Use APENAS jogos reais dos dados fornecidos ou confirmados via busca web.
2. Para cada jogo analisado, você DEVE buscar e incluir o link direto da partida na casa de apostas (ex: Sportingbet ou equivalente).
3. Utilize estritamente a estrutura visual HTML abaixo sem alterar as marcas.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO PARA TELEGRAM (HTML):

⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>

(Para cada partida principal encontrada, repita este bloco com dados reais:)
• <b>[Time A] x [Time B]</b> ([Competição] | 🕟 [Horário] BRT)
  • Provável vencedor: [Seleção / Tendência]
  • Odd estimada: [Valor da Odd]
  • Projeção estatística: [Gols / Escanteios / Cartões]
  • 🔗 <a href="[LINK_PARTIDA]">Apostar no Jogo</a>

━━━━━━━━━━━━━━━━━━
📊 <b>DESTAQUES E PROJEÇÕES</b>
• [Análise técnica resumida das principais oportunidades do dia]

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Nenhuma aposta é 100% garantida; odds e estatísticas acima vêm de fontes públicas e podem mudar. Aposte com responsabilidade.

🎁 <b>CADASTRE-SE E RESGATE SUA RECOMPENSA!</b>
Ganhe bônus de boas-vindas e giros grátis se cadastrando no link oficial abaixo:
👉 <a href="{LINK_CADASTRO_RECOMPENSA}">CLIQUE AQUI PARA SE CADASTRAR E GANHAR</a>
"""


def formatar_fallback_emergencial(jogos, origem, data_hoje):
    """Fallback emergencial contendo o novo link de cadastro."""
    linhas = [
        f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>\n",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>TOP APOSTAS DO DIA</b> (Modo de Emergência)\n"
    ]
    
    for idx, ev in enumerate(jogos[:5]):
        if "ESPN" in origem:
            nome = ev.get("name", "Confronto")
        else:
            teams = ev.get("teams", {})
            nome = f"{teams.get('home', {}).get('name', 'Mandante')} x {teams.get('away', {}).get('name', 'Visitante')}"

        linhas.append(
            f"• <b>{nome}</b>\n"
            f"  • Mercados recomendados: Vitória do Favorito / Over 1.5 Gols\n"
        )

    linhas.extend([
        "━━━━━━━━━━━━━━━━━━",
        "⚠️ <b>AVISO LEGAL:</b> Mantenha a gestão de banca e aposte com responsabilidade.\n",
        "🎁 <b>CADASTRE-SE E RESGATE SUA RECOMPENSA!</b>",
        "Ganhe bônus exclusivo se cadastrando pelo link abaixo:",
        f"👉 <a href=\"{LINK_CADASTRO_RECOMPENSA}\">CLIQUE AQUI PARA SE CADASTRAR E GANHAR</a>"
    ])
    
    return "\n".join(linhas)


def executar_robo():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    # 1. Obtenção das partidas
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
            dados_contexto = "Realize busca na web para consultar as partidas de futebol marcadas para o dia de hoje."

    # 2. Execução da IA com busca web
    prompt = montar_prompt(data_hoje, dados_contexto)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"[INFO] Gerando relatório com {MODELO}...")
    relatorio = None
    
    try:
        response = client.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=config,
        )
        relatorio = response.text
    except ClientError as e:
        print(f"[ERRO] Falha na chamada da API Gemini: {e}")
    except Exception as e:
        print(f"[ERRO] Erro inesperado ao gerar relatório: {e}")

    # 3. Envio da mensagem
    if relatorio:
        enviar_telegram(relatorio)
    elif jogos_brutos:
        print("[AVISO] Gerando relatório emergencial de fallback...")
        relatorio_emergencia = formatar_fallback_emergencial(jogos_brutos, fonte_usada, data_hoje)
        enviar_telegram(relatorio_emergencia)
    else:
        enviar_telegram(f"⚠️ <b>Não foi possível gerar o relatório de apostas hoje ({data_hoje}).</b>")


if __name__ == "__main__":
    executar_robo()
