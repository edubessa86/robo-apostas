import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BRT = timezone(timedelta(hours=-3))

def coletar_fixtures_oddspapi() -> List[Dict[str, Any]]:
    agora_brt = datetime.now(BRT)
    data_iso = agora_brt.strftime("%Y-%m-%d")
    fixtures_coletadas = []

    api_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL_KEY_2")
    
    if not api_key:
        print("[ERROR] Nenhuma chave API_FOOTBALL_KEY encontrada nas variáveis de ambiente.")
        return fixtures_coletadas

    # Adicionado o fuso horário de Brasília para consultar a data correta
    url = f"https://v3.football.api-sports.io/fixtures?date={data_iso}&timezone=America/Sao_Paulo"
    headers = {
        "x-apisports-key": api_key,
        "x-rapidapi-key": api_key
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            # Diagnóstico de avisos ou erros internos do plano na API-Football
            errors = data.get("errors")
            if errors and len(errors) > 0:
                print(f"[WARN] API-Football retornou alerta no JSON: {errors}")

            matches = data.get("response", [])
            print(f"[DEBUG] Total de partidas brutas retornadas no JSON: {len(matches)}")

            for match in matches:
                status_short = match.get("fixture", {}).get("status", {}).get("short", "")
                
                # Descarta partidas finalizadas ou canceladas
                if status_short in ["FT", "AET", "PEN", "CANC", "ABD"]:
                    continue

                league_name = match.get("league", {}).get("name", "Futebol Profissional")
                home_team = match.get("teams", {}).get("home", {}).get("name", "Mandante")
                away_team = match.get("teams", {}).get("away", {}).get("name", "Visitante")
                start_time_iso = match.get("fixture", {}).get("date")

                fixtures_coletadas.append({
                    "external_id": str(match.get("fixture", {}).get("id")),
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
            print(f"[OK] {len(fixtures_coletadas)} jogos restantes filtrados com sucesso.")
        else:
            print(f"[ERROR] API-Football retornou HTTP {response.status_code}")

    except Exception as e:
        print(f"[ERROR] Erro ao consultar API-Football: {e}")

    return fixtures_coletadas
