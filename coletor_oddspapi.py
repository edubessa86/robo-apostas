import os
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BRT = timezone(timedelta(hours=-3))

def coletar_fixtures_oddspapi() -> List[Dict[str, Any]]:
    agora_brt = datetime.now(BRT)
    data_iso = agora_brt.strftime("%Y-%m-%d")
    fixtures_coletadas = []

    # Token individual da Football-Data.org
    token = os.getenv("FOOTBALL_DATA_KEY") or "f69f2ff03e884589ab432cd58501ec56"
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={data_iso}&dateTo={data_iso}"
    headers = {
        "X-Auth-Token": token
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        # Tratamento do Rate Limiting / Throttling (HTTP 429)
        if response.status_code == 429:
            wait_time = int(response.headers.get("X-RequestCounter-Reset", 60))
            print(f"[WARN] Limite de requisições atingido. Aguardando {wait_time}s para tentar novamente...")
            time.sleep(wait_time)
            response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            print(f"[OK] Total de jogos encontrados no dia: {len(matches)}")

            for match in matches:
                status = match.get("status")
                # Descarta jogos finalizados, adiados ou cancelados
                if status in ["FINISHED", "CANCELLED", "POSTPONED"]:
                    continue

                external_id = str(match.get("id"))
                league_name = match.get("competition", {}).get("name", "Futebol Profissional")
                home_team = match.get("homeTeam", {}).get("name", "Mandante")
                away_team = match.get("awayTeam", {}).get("name", "Visitante")
                start_time_iso = match.get("utcDate")

                fixtures_coletadas.append({
                    "external_id": external_id,
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

            print(f"[OK] {len(fixtures_coletadas)} jogos prontos para análise.")
        else:
            print(f"[ERROR] API retornou HTTP {response.status_code}: {response.text}")

    except Exception as e:
        print(f"[ERROR] Erro ao consultar Football-Data.org: {e}")

    return fixtures_coletadas
