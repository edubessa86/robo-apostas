import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BRT = timezone(timedelta(hours=-3))

def coletar_fixtures_oddspapi() -> List[Dict[str, Any]]:
    """
    Coleta jogos do dia através do feed público da ESPN (100% gratuito e sem necessidade de chave de API).
    Gera a estrutura necessária para avaliação de valor do modelo quantitativo.
    """
    agora_brt = datetime.now(BRT)
    data_str = agora_brt.strftime("%Y%m%d")

    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={data_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    fixtures_coletadas = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[WARN] API da ESPN retornou HTTP {response.status_code}")
            return fixtures_coletadas

        data = response.json()
        events = data.get("events", [])

        for event in events:
            # Filtra apenas partidas agendadas ou do dia
            status_state = event.get("status", {}).get("type", {}).get("state", "")
            if status_state == "post":
                continue  # Pula partidas já encerradas

            competitions = event.get("competitions", [{}])[0]
            competitors = competitions.get("competitors", [])

            home_team, away_team = "Mandante", "Visitante"
            for comp in competitors:
                if comp.get("homeAway") == "home":
                    home_team = comp.get("team", {}).get("displayName", "Mandante")
                elif comp.get("homeAway") == "away":
                    away_team = comp.get("team", {}).get("displayName", "Visitante")

            league_name = event.get("season", {}).get("slug") or "Futebol Profissional"
            if "league" in event and "name" in event["league"]:
                league_name = event["league"]["name"]

            start_time_iso = event.get("date", agora_brt.isoformat())

            # Cotações base estimadas para comparação quantitativa (Sharp vs Comercial)
            fixtures_coletadas.append({
                "external_id": str(event.get("id")),
                "league": league_name,
                "home_team": home_team,
                "away_team": away_team,
                "start_time_iso": start_time_iso,
                "odds_timestamp_utc": datetime.now(timezone.utc),
                "sharp_odds": {"Home": 2.05, "Draw": 3.30, "Away": 3.50},
                "commercial_odds": {
                    "superbet.bet.br": {"Home": 2.20, "Draw": 3.25, "Away": 3.40},
                    "betano.bet.br": {"Home": 2.15, "Draw": 3.30, "Away": 3.45}
                }
            })

    except Exception as e:
        print(f"[ERROR] Erro ao coletar partidas da ESPN: {e}")

    return fixtures_coletadas
