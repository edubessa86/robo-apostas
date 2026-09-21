import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from database import DatabaseManager
from quant_engine import QuantEngine
from telegram_formatter import TelegramFormatter
from coletor_oddspapi import coletar_fixtures_oddspapi

BRT = timezone(timedelta(hours=-3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "0") == "1"

def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[ERROR] TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurados.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 'N/A')
        print(f"[ERROR] Falha ao enviar mensagem ao Telegram (HTTP {status_code}).")
        return False

def obter_dados_ficticios(agora_brt: datetime) -> List[Dict[str, Any]]:
    """Gera massa de dados simulada apenas para validação em modo MOCK."""
    return [
        {
            "external_id": "MOCK_2026_001",
            "league": "Brasileirão Série A",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "start_time_iso": agora_brt.replace(hour=16, minute=0, second=0).isoformat(),
            "odds_timestamp_utc": datetime.now(timezone.utc),
            "sharp_odds": {"Home": 2.10, "Draw": 3.35, "Away": 3.60},
            "commercial_odds": {
                "superbet.bet.br": {"Home": 2.25, "Draw": 3.30, "Away": 3.40},
                "betano.bet.br": {"Home": 2.18, "Draw": 3.40, "Away": 3.55}
            }
        }
    ]

def run_pipeline() -> int:
    agora_brt = datetime.now(BRT)
    data_str = agora_brt.strftime("%d/%m/%Y")
    modo = "MOCK / TESTE" if USE_MOCK_DATA else "PRODUÇÃO"
    print(f"[INFO] Executando Pipeline das 10h em {data_str} (Modo: {modo})")

    # 1. Coleta de Fixtures e Odds (Fail-Closed)
    if USE_MOCK_DATA:
        fixtures = obter_dados_ficticios(agora_brt)
        db_path = ":memory:"
    else:
        try:
            fixtures = coletar_fixtures_oddspapi()
        except Exception as e:
            print(f"[CRITICAL] Falha na coleta da API: {e}")
            return 1
            
        if not fixtures:
            print("[INFO] Nenhuma partida ou cotação válida retornada para o dia de hoje.")
            # Se não houver jogos ou odds no dia, finaliza com código 0 sem disparar sinal
            return 0
        db_path = "quant_bot_v7.db"

    # 2. Inicialização dos Módulos Quantitativos
    db = DatabaseManager(db_path=db_path)
    engine = QuantEngine(min_ev=0.03, min_price_edge=0.03, max_data_age_seconds=21600)

    processed_matches = []

    # 3. Processamento de Cada Partida
    for fixture in fixtures:
        match_id = db.log_match(
            external_id=fixture["external_id"],
            league=fixture["league"],
            home=fixture["home_team"],
            away=fixture["away_team"],
            start_time=fixture["start_time_iso"]
        )

        results = engine.evaluate_match_market(
            sharp_odds_1x2=fixture["sharp_odds"],
            commercial_odds_multi_book=fixture["commercial_odds"],
            last_update_utc=fixture["odds_timestamp_utc"]
        )

        # Registra sinais de VALOR no banco SQLite para auditoria de CLV
        for res in results:
            if res.status == "VALUE":
                db.log_signal({
                    "match_id": match_id,
                    "bookmaker": res.best_bookmaker,
                    "market": "1X2",
                    "selection": res.selection,
                    "entry_odd": res.best_odd,
                    "fair_odd_sharp": res.sharp_fair_odd,
                    "fair_prob": res.sharp_fair_prob,
                    "price_edge": res.price_edge_percent,
                    "ev": res.ev_percent,
                    "kelly_stake": res.kelly_stake_percent
                })

        horario_brt = datetime.fromisoformat(fixture["start_time_iso"]).astimezone(BRT).strftime("%H:%M")
        processed_matches.append({
            "match": {
                "home_team": fixture["home_team"],
                "away_team": fixture["away_team"],
                "league": fixture["league"],
                "horario": horario_brt
            },
            "results": results
        })

    # 4. Formatação e Envio do Relatório
    report_html = TelegramFormatter.format_daily_report(data_str, processed_matches)
    
    if USE_MOCK_DATA:
        print("\n--- RELATÓRIO SIMULADO (MOCK) ---")
        print(report_html)
        return 0

    sucesso = send_telegram_message(report_html)
    if sucesso:
        print("[OK] Relatório enviado com sucesso ao Telegram!")
        return 0
    else:
        print("[ERROR] Falha ao entregar relatório no Telegram.")
        return 1

if __name__ == "__main__":
    sys.exit(run_pipeline())=
