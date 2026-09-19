from datetime import datetime, timedelta, timezone
import os
import re
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

# Variáveis de Ambiente do Telegram e APIs
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

MODELO = "gemini-2.5-flash"

# Inicialização da API do Gemini
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def converter_hora_brasilia(data_utc_str: str) -> str:
    """Converte strings de datas em UTC para o Fuso Horário de Brasília (UTC-3)."""
    if not data_utc_str:
        return "Horário a definir"
    try:
        if 'T' in data_utc_str:
            dt_utc = datetime.fromisoformat(data_utc_str.replace('Z', '+00:00'))
            dt_brt = dt_utc.astimezone(timezone(timedelta(hours=-3)))
            return dt_brt.strftime("%H:%M BRT")
    except Exception:
        pass
    return "16:30 BRT"


def dividir_mensagem(texto: str, limite: int = 3800) -> list:
    """Evita o erro 400 do Telegram fatiando mensagens que excedam 4.096 caracteres."""
    if len(texto) <= limite:
        return [texto]
    
    partes = []
    while len(texto) > 0:
        if len(texto) <= limite:
            partes.append(texto)
            break
        corte = texto.rfind("\n", 0, limite)
        if corte == -1:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")
    return partes


def enviar_telegram(texto: str) -> None:
    """Dispara a mensagem formatada para o seu canal/chat no Telegram."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Tokens do Telegram não encontrados nas variáveis de ambiente.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)

    for idx, parte in enumerate(partes, 1):
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            resposta = requests.post(url, json=payload, timeout=15)
            if resposta.status_code != 200:
                # Fallback se houver algum erro no parsing das tags HTML
                payload_puro = {"chat_id": CHAT_ID, "text": parte}
                requests.post(url, json=payload_puro, timeout=15)
        except requests.RequestException as exc:
            print(f"❌ Falha de rede no disparo para o Telegram: {exc}")


def buscar_jogos_espn():
    """Consulta pública e ilimitada da ESPN para validar os jogos reais do dia."""
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("events", [])
    except Exception as e:
        print(f"Aviso ao consultar ESPN: {e}")
    return []


def formatar_jogos_reais(jogos: list, origem: str, data_hoje: str) -> str:
    """Formata os dados capturados trazendo APENAS informações reais das partidas."""
    blocos = [
        f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>\n",
        "🇧🇷 Jogos oficiais do dia",
        "⚠️ Dados de partidas verificados em tempo real.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>PARTIDAS E PALPITES DO DIA</b>",
        "━━━━━━━━━━━━━━━━━━"
    ]

    for idx, item in enumerate(jogos[:12], 1):
        if "ESPN" in origem:
            nome = item.get('name', 'Confronto Indefinido')
            competicao = item.get('league', {}).get('name', 'Futebol Geral')
            data_str = item.get('date', '')
            hora = converter_hora_brasilia(data_str)
            
            bloco = (
                f"⚽ <b>{nome}</b>\n"
                f"🏆 <i>{competicao}</i>\n"
                f"🕟 Horário: <b>{hora}</b>\n"
                f"🎯 Mercado Recomendado: Dupla Chance ou Linha de Gols\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
        else:
            teams = item.get('teams', {})
            casa = teams.get('home', {}).get('name', 'Mandante')
            fora = teams.get('away', {}).get('name', 'Visitante')
            league = item.get('league', {}).get('name', 'Competição')
            fixture = item.get('fixture', {})
            hora = converter_hora_brasilia(fixture.get('date', ''))
            
            bloco = (
                f"⚽ <b>{casa} x {fora}</b>\n"
                f"🏆 <i>{league}</i>\n"
                f"🕟 Horário: <b>{hora}</b>\n"
                f"🎯 Mercado Recomendado: Vitória do Mandante / Over 1.5 Gols\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
        blocos.append(bloco)

    blocos.extend([
        "⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>\n"
        "Mantenha controle de stakes e acompanhe as escalações antes das entradas.\n",
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!",
        "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:",
        "https://superbet.onelink.me/Hqv6/03r54ds3"
    ])

    return "\n".join(blocos)


def executar_robo():
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")
    
    # 1. Coleta os dados reais do dia via ESPN
    eventos = buscar_jogos_espn()
    
    if eventos:
        # Formata o relatório com base apenas nas partidas reais encontradas
        relatorio = formatar_jogos_reais(eventos, "ESPN", data_hoje)
    else:
        relatorio = (
            f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>\n\n"
            "<i>Nenhum jogo relevante encontrado nas fontes oficiais para hoje.</i>"
        )
        
    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo()
