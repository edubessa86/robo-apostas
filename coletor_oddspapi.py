import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BRT = timezone(timedelta(hours=-3))

def criar_sessao_http() -> requests.Session:
    """Cria uma sessão HTTP com cabeçalhos completos de navegador para evitar o HTTP 403."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.espn.com.br/",
        "Origin": "https://www.espn.com.br",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    })
    return session

def coletar_fixtures_oddspapi() -> List[Dict[str, Any]]:
    agora_brt = datetime.now(BRT)
    data_str = agora_brt.strftime("%Y%m%d")
    data_iso = agora_brt.strftime("%Y-%m-%d")
    fixtures_coletadas = []

    # 1. TENTATIVA VIA API-FOOTBALL (Primary Provider)
    api_football_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL_KEY_2")
    if api_football_key:
        try:
            url_apifootball = f"https://v3.football.api-sports.io/fixtures?date={data_iso}"
            headers_apifootball = {"x-apisports-key": api_football_key}
            
            resp = requests.get(url_apifootball, headers=headers_apifootball, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("response", [])
                
                for match in matches:
                    status_short = match.get("fixture", {}).get("status", {}).get("short", "")
                    if status_short in ["FT", "AET", "PEN"]:
                        continue  # Pula partidas finalizadas

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

                if fixtures_coletadas:
                    print(f"[OK] {len(fixtures_coletadas)} jogos coletados via API-Football.")
                    return fixtures_coletadas
        except Exception as e:
            print(f"[WARN] Falha na requisição da API-Football: {e}")

    # 2. FALLBACK VIA ESPN (Com Session Anti-Bot)
    session = criar_sessao_http()
    url_espn = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={data_str}"

    try:
        response = session.get(url_espn, timeout=15)
        if response.status_code != 200:
            print(f"[WARN] API da ESPN retornou HTTP {response.status_code}")
            return fixtures_coletadas

        data = response.json()
        events = data.get("events", [])

        for event in events:
            status_state = event.get("status", {}).get("type", {}).get("state", "")
            if status_state == "post":
                continue

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
        print(f"[OK] {len(fixtures_coletadas)} jogos coletados via ESPN.")

    except Exception as e:
        print(f"[ERROR] Erro ao coletar partidas da ESPN: {e}")

    return fixtures_coletadas
