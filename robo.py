import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from database import DatabaseManager
from quant_engine import QuantEngine
from telegram_formatter import TelegramFormatter

# Configurações de Fuso Horário e Variáveis de Ambiente Seguras
BRT = timezone(timedelta(hours=-3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[WARN] TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID ausentes. Pulando envio.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Falha ao enviar mensagem ao Telegram: {e}")

def run_pipeline_10am() -> None:
    db = DatabaseManager()
    engine = QuantEngine(min_ev=0.03, min_price_edge=0.03, max_data_age_seconds=180)
    
    agora_brt = datetime.now(BRT)
    data_formatada = agora_brt.strftime("%d/%m/%Y")

    # MOCK DE DADOS RECEBIDOS DAS APIS (Pinnacle + Casas Comerciais)
    # Na implementação real, esta lista vem da sua camada de Coleta (Data/Odds Engine)
    mock_fixtures_payload: List[Dict[str, Any]] = [
        {
            "external_id": "FIX_2026_001",
            "league": "Brasileirão Série A",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "start_time_iso": agora_brt.replace(hour=19, minute=0, second=0).isoformat(),
            "odds_timestamp_utc": datetime.now(timezone.utc),
            "sharp_odds": {"Home": 2.10, "Draw": 3.35, "Away": 3.60},  # Pinnacle (Padrão Sharp)
            "commercial_odds": {
                "Superbet": {"Home": 2.25, "Draw": 3.30, "Away": 3.40},
                "Betano": {"Home": 2.18, "Draw": 3.40, "Away": 3.55},
                "Bet365": {"Home": 2.20, "Draw": 3.30, "Away": 3.65}   # Bet365 com Line Shopping na Vitória do Fora
            }
        }
    ]

    processed_matches = []

    for fixture in mock_fixtures_payload:
        # 1. Registrar/Atualizar Partida no SQLite
        match_id = db.log_match(
            external_id=fixture["external_id"],
            league=fixture["league"],
            home=fixture["home_team"],
            away=fixture["away_team"],
            start_time=fixture["start_time_iso"]
        )

        # 2. Executar Engine Quantitativa (Line Shopping + De-vig + Multi-Selection)
        results = engine.evaluate_match_market(
            sharp_odds_1x2=fixture["sharp_odds"],
            commercial_odds_multi_book=fixture["commercial_odds"],
            last_update_utc=fixture["odds_timestamp_utc"]
        )

        # 3. Log dos Sinais de VALOR no Banco para Auditoria Futura de CLV
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

        processed_matches.append({
            "match": {
                "home_team": fixture["home_team"],
                "away_team": fixture["away_team"],
                "league": fixture["league"],
                "horario": datetime.fromisoformat(fixture["start_time_iso"]).astimezone(BRT).strftime("%H:%M")
            },
            "results": results
        })

    # 4. Formatar e Enviar Relatório
    report_html = TelegramFormatter.format_daily_report(data_formatada, processed_matches)
    send_telegram_message(report_html)

if __name__ == "__main__":
    run_pipeline_10am()
