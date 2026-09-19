from datetime import datetime, timedelta, timezone
import os
import requests

# Variáveis de Ambiente do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Mapeamento das principais ligas de futebol do mundo no endpoint público da ESPN
LIGAS_ELITE = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A Itália",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "uefa.champions": "Champions League",
    "bra.1": "Brasileirão Serie A",
    "usa.1": "MLS"
}

def converter_hora_brasilia(data_utc_str: str) -> tuple[str, str]:
    """Converte datas UTC da ESPN para o Fuso de Brasília (UTC-3)."""
    if not data_utc_str:
        return "16:00 BRT", datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")
    try:
        if 'T' in data_utc_str:
            dt_utc = datetime.fromisoformat(data_utc_str.replace('Z', '+00:00'))
            dt_brt = dt_utc.astimezone(timezone(timedelta(hours=-3)))
            return dt_brt.strftime("%H:%M BRT"), dt_brt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return "16:00 BRT", datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")

def buscar_jogos_filtrados():
    """Busca os jogos do dia filtrando apenas por ligas de elite para evitar times aleatórios."""
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje_br = datetime.now(fuso_br).strftime("%Y-%m-%d")
    
    jogos_filtrados = []
    ids_processados = set()

    print(f"Buscando jogos reais das ligas principais para a data: {data_hoje_br}...")

    # Iteração sobre os endpoints das ligas principais
    for code_liga, nome_liga in LIGAS_ELITE.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code_liga}/scoreboard"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                eventos = resp.json().get("events", [])
                for ev in eventos:
                    game_id = ev.get("id")
                    if game_id in ids_processados:
                        continue
                    
                    data_utc = ev.get("date", "")
                    hora_brt, data_brt = converter_hora_brasilia(data_utc)
                    
                    # FILTRO RÍGIDO: Só aceita se o jogo for no dia exato de hoje em Brasília
                    if data_brt == data_hoje_br:
                        nome = ev.get("name", "Confronto")
                        ids_processados.add(game_id)
                        jogos_filtrados.append({
                            "partida": nome,
                            "liga": nome_liga,
                            "horario": hora_brt
                        })
        except Exception as e:
            print(f"Erro ao buscar liga {nome_liga}: {e}")

    # Fallback: Caso as ligas de elite não tenham jogos no dia, busca no endpoint geral
    if not jogos_filtrados:
        print("Nenhum jogo de liga principal hoje. Buscando no endpoint geral...")
        url_geral = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
        try:
            resp = requests.get(url_geral, timeout=15)
            if resp.status_code == 200:
                for ev in resp.json().get("events", []):
                    game_id = ev.get("id")
                    if game_id in ids_processados:
                        continue
                    
                    data_utc = ev.get("date", "")
                    hora_brt, data_brt = converter_hora_brasilia(data_utc)
                    
                    if data_brt == data_hoje_br:
                        nome = ev.get("name", "Confronto")
                        liga = ev.get("league", {}).get("name", "Futebol Internacional")
                        ids_processados.add(game_id)
                        jogos_filtrados.append({
                            "partida": nome,
                            "liga": liga,
                            "horario": hora_brt
                        })
        except Exception as e:
            print(f"Erro no fallback geral: {e}")

    return jogos_filtrados

def dividir_mensagem(texto: str, limite: int = 3800) -> list:
    """Garante que o texto fique dentro do limite de caracteres do Telegram (4.096)."""
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
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Variáveis do Telegram não configuradas.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)

    for parte in partes:
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code != 200:
                payload_puro = {"chat_id": CHAT_ID, "text": parte}
                requests.post(url, json=payload_puro, timeout=15)
        except Exception as e:
            print(f"Erro ao enviar para Telegram: {e}")

def montar_relatorio(jogos):
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")

    msg = f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "🏆 <b>PARTIDAS CONFIRMADAS DO DIA</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    if not jogos:
        msg += "<i>Nenhuma partida confirmada para o dia de hoje nas principais ligas.</i>\n\n"
    else:
        for j in jogos[:15]:
            msg += f"⚽ <b>{j['partida']}</b>\n"
            msg += f"🏆 <i>{j['liga']}</i>\n"
            msg += f"🕟 Horário: <b>{j['horario']}</b>\n"
            msg += f"🎯 Mercado Sugerido: Dupla Chance ou Over 1.5 Gols\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"

    msg += "\n⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>\n"
    msg += "Mantenha o controle do seu bankroll e confirme as escalações oficiais antes de apostar.\n\n"
    msg += "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!\n"
    msg += "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:\n"
    msg += "https://superbet.onelink.me/Hqv6/03r54ds3"

    return msg

def main():
    jogos = buscar_jogos_filtrados()
    relatorio = montar_relatorio(jogos)
    enviar_telegram(relatorio)

if __name__ == "__main__":
    main()
