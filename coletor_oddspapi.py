import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BRT = timezone(timedelta(hours=-3))

def coletar_fixtures_oddspapi() -> List[Dict[str, Any]]:
    """
    Coleta jogos e odds do dia na OddsPapi, filtrando eventos pré-jogo de hoje (BRT)
    e estruturando as cotações para a ancoragem Sharp (Pinnacle) e casas comerciais.
    """
    api_key = os.getenv("ODDSPAPI_KEY")
    if not api_key:
        raise ValueError("A chave ODDSPAPI_KEY não foi configurada nos Secrets do GitHub.")

    tournament_ids_raw = os.getenv("ODDSPAPI_TOURNAMENT_IDS", "")
    if not tournament_ids_raw:
        raise ValueError("A variável ODDSPAPI_TOURNAMENT_IDS está vazia. Informe os IDs dos campeonatos.")

    tournament_ids = [t.strip() for t in tournament_ids_raw.split(",") if t.strip()]
    commercial_books_raw = os.getenv("ODDSPAPI_COMMERCIAL_BOOKS", "superbet.bet.br,betano.bet.br")
    commercial_books = [b.strip() for b in commercial_books_raw.split(",") if b.strip()]

    agora_brt = datetime.now(BRT)
    hoje_str = agora_brt.strftime("%Y-%m-%d")

    fixtures_coletadas = []

    for tournament_id in tournament_ids:
        url = f"https://api.oddspapi.com/v1/odds-by-tournaments?tournament_id={tournament_id}&date={hoje_str}"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"[WARN] Torneio ID {tournament_id} retornou HTTP {response.status_code}.")
                continue

            data = response.json()
            matches = data if isinstance(data, list) else data.get("data", [])

            for match in matches:
                start_time_iso = match.get("start_time") or match.get("date")
                if not start_time_iso:
                    continue

                # Garante conversão segura do horário para o fuso de Brasília
                horario_jogo = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00")).astimezone(BRT)
                
                # Filtro estrito: Apenas jogos do dia corrente que ainda não iniciaram
                if horario_jogo.date() != agora_brt.date() or horario_jogo < agora_brt:
                    continue

                odds_data = match.get("odds", {})

                # Cotações da Casa Sharp (Pinnacle)
                pinnacle_odds = odds_data.get("pinnacle", {})
                sharp_1x2 = {
                    "Home": float(pinnacle_odds.get("home", 0) or 0),
                    "Draw": float(pinnacle_odds.get("draw", 0) or 0),
                    "Away": float(pinnacle_odds.get("away", 0) or 0),
                }

                # Descarta se as odds da casa Sharp estiverem incompletas
                if any(v <= 1.0 for v in sharp_1x2.values()):
                    continue

                # Cotações das Casas Comerciais (Line Shopping)
                commercial_odds = {}
                for book_slug in commercial_books:
                    book_data = odds_data.get(book_slug, {})
                    b_home = float(book_data.get("home", 0) or 0)
                    b_draw = float(book_data.get("draw", 0) or 0)
                    b_away = float(book_data.get("away", 0) or 0)

                    if b_home > 1.0 or b_draw > 1.0 or b_away > 1.0:
                        commercial_odds[book_slug] = {
                            "Home": b_home,
                            "Draw": b_draw,
                            "Away": b_away
                        }

                if not commercial_odds:
                    continue

                fixtures_coletadas.append({
                    "external_id": str(match.get("id", f"{match.get('home_team')}_{match.get('away_team')}")),
                    "league": match.get("tournament_name", match.get("league", "Campeonato")),
                    "home_team": match.get("home_team", "Mandante"),
                    "away_team": match.get("away_team", "Visitante"),
                    "start_time_iso": horario_jogo.isoformat(),
                    "odds_timestamp_utc": datetime.now(timezone.utc),
                    "sharp_odds": sharp_1x2,
                    "commercial_odds": commercial_odds
                })

        except Exception as e:
            print(f"[ERROR] Erro ao processar cotações do torneio {tournament_id}: {e}")

    return fixtures_coletadas
