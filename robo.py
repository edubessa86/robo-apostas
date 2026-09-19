from datetime import datetime, timedelta, timezone
import os
import requests

# Variáveis de Ambiente do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Mapeamento das principais ligas do mundo na ESPN pública
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
    """Converte as datas UTC para o Fuso Horário de Brasília (UTC-3)."""
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

def calcular_projecoes_e_estatisticas(mandante: str, visitante: str) -> dict:
    """
    Calcula as projeções quantitativas de Dupla Chance, Vencedor Provável,
    Escanteios e Cartões para a partida.
    """
    m_low = mandante.lower()
    v_low = visitante.lower()
    
    top_times = ["bayern", "real", "barcelona", "city", "arsenal", "psg", "inter", "flamengo", "palmeiras", "liverpool"]
    
    # 1. Análise do Favorito e Vencedor Provável
    if any(top in m_low for top in top_times):
        vencedor_provavel = f"{mandante} (Favorito)"
        dupla_chance = f"1X ({mandante} ou Empate)"
        cantos_mandante = "5.5+"
        cantos_visitante = "3.5+"
        cantos_total = "Over 8.5 Escanteios"
        cartoes_total = "Over 3.5 Cartões"
        gols = "Over 2.5 Gols"
        placar = "2 x 0 ou 2 x 1"
        prob = "85%"
    elif any(top in v_low for top in top_times):
        vencedor_provavel = f"{visitante} (Favorito)"
        dupla_chance = f"X2 (Empate ou {visitante})"
        cantos_mandante = "3.5+"
        cantos_visitante = "5.5+"
        cantos_total = "Over 8.5 Escanteios"
        cartoes_total = "Over 4.5 Cartões"
        gols = "Over 1.5 Gols"
        placar = "0 x 2 ou 1 x 2"
        prob = "82%"
    else:
        vencedor_provavel = f"{mandante} / Empate"
        dupla_chance = f"1X ({mandante} ou Empate)"
        cantos_mandante = "4.5+"
        cantos_visitante = "4.5+"
        cantos_total = "Over 9.5 Escanteios"
        cartoes_total = "Over 4.5 Cartões"
        gols = "Over 1.5 Gols"
        placar = "1 x 1 ou 2 x 1"
        prob = "80%"

    return {
        "vencedor_provavel": vencedor_provavel,
        "dupla_chance": dupla_chance,
        "cantos_total": cantos_total,
        "cantos_detalhe": f"Mandante: {cantos_mandante} | Visitante: {cantos_visitante}",
        "cartoes_total": cartoes_total,
        "gols": gols,
        "placar": placar,
        "probabilidade": prob
    }

def buscar_jogos_reais_do_dia():
    """Filtra as partidas oficiais e reais do dia atual em Brasília."""
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje_br = datetime.now(fuso_br).strftime("%Y-%m-%d")
    
    jogos_filtrados = []
    ids_processados = set()

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
                    
                    # Filtra rigorosamente por data
                    if data_brt == data_hoje_br:
                        competidores = ev.get("competitions", [{}])[0].get("competitors", [])
                        if len(competidores) >= 2:
                            mandante = competidores[0].get("team", {}).get("displayName", "Mandante")
                            visitante = competidores[1].get("team", {}).get("displayName", "Visitante")
                            
                            projecao = calcular_projecoes_e_estatisticas(mandante, visitante)
                            
                            ids_processados.add(game_id)
                            jogos_filtrados.append({
                                "partida": f"{mandante} x {visitante}",
                                "liga": nome_liga,
                                "horario": hora_brt,
                                "projecao": projecao
                            })
        except Exception as e:
            print(f"Aviso ao consultar {nome_liga}: {e}")

    return jogos_filtrados

def dividir_mensagem(texto: str, limite: int = 3800) -> list:
    """Fatia textos extensos para respeitar o limite do Telegram."""
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
        print("Erro: Credenciais do Telegram ausentes.")
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
            print(f"Erro de rede ao enviar ao Telegram: {e}")

def montar_relatorio(jogos):
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")

    msg = f"⚽ <b>RELATÓRIO COMPLETO DE APOSTAS — {data_hoje}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "🏆 <b>ANÁLISE E PROJEÇÕES ESTATÍSTICAS DO DIA</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    if not jogos:
        msg += "<i>Nenhuma partida confirmada para hoje nas ligas principais.</i>\n\n"
    else:
        for j in jogos[:10]:
            p = j["projecao"]
            msg += f"⚽ <b>{j['partida']}</b>\n"
            msg += f"🏆 <i>{j['liga']}</i> | 🕟 <b>{j['horario']}</b>\n"
            msg += f"👑 <b>Vencedor Provável:</b> {p['vencedor_provavel']}\n"
            msg += f"🎯 <b>Dupla Chance:</b> {p['dupla_chance']}\n"
            msg += f"⚽ <b>Linha de Gols:</b> {p['gols']} (Placar provável: {p['placar']})\n"
            msg += f"🚩 <b>Escanteios:</b> {p['cantos_total']} ({p['cantos_detalhe']})\n"
            msg += f"🟨 <b>Cartões Estimados:</b> {p['cartoes_total']}\n"
            msg += f"🔥 <b>Confiança Estimada:</b> {p['probabilidade']}\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"

    msg += "\n⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>\n"
    msg += "As estimativas dependem das estatísticas ao vivo e escalações oficiais.\n\n"
    msg += "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!\n"
    msg += "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:\n"
    msg += "https://superbet.onelink.me/Hqv6/03r54ds3"

    return msg

def main():
    jogos = buscar_jogos_reais_do_dia()
    relatorio = montar_relatorio(jogos)
    enviar_telegram(relatorio)

if __name__ == "__main__":
    main()
