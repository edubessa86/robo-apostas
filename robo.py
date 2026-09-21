# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from database import DatabaseManager
from quant_engine import QuantEngine
from telegram_formatter import TelegramFormatter

# Configurações de Fuso Horário e Variáveis de Ambiente Seguras
BRT = timezone(timedelta(hours=-3))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# USE_MOCK_DATA=1 -> roda com dados FICTÍCIOS, só imprime o relatório no log
# (não envia ao Telegram e usa banco em memória). Nunca ative isso em produção.
MODO_TESTE = os.getenv("USE_MOCK_DATA", "0") == "1"


def send_telegram_message(text: str) -> bool:
    """Envia o relatório. Retorna True somente se todas as partes foram aceitas."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[ERROR] TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID ausentes. Nada foi enviado.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = TelegramFormatter.split_message(text)
    tudo_ok = True

    for n, parte in enumerate(partes, 1):
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            if not r.ok:
                # Não imprime a exceção do requests: a mensagem inclui a URL com o token.
                print(f"[ERROR] Telegram recusou a parte {n}/{len(partes)}: HTTP {r.status_code} — {r.text[:200]}")
                tudo_ok = False
        except requests.RequestException as e:
            print(f"[ERROR] Falha de rede ao enviar a parte {n}/{len(partes)}: {type(e).__name__}")
            tudo_ok = False
    return tudo_ok


# --------------------------------------------------------------------------- dados
def coletar_fixtures(agora_brt: datetime) -> List[Dict[str, Any]]:
    """PONTO DE INTEGRAÇÃO: aqui entra a coleta REAL de jogos e odds.

    Cada item da lista deve ter este formato:
        {
          "external_id": str,
          "league": str, "home_team": str, "away_team": str,
          "start_time_iso": "2026-09-21T19:00:00-03:00",   # COM fuso (offset ou Z)
          "odds_timestamp_utc": datetime (com tzinfo=UTC),  # última atualização das odds
          "sharp_odds": {"Home": float, "Draw": float, "Away": float},   # Pinnacle
          "commercial_odds": {"Superbet": {"Home":..,"Draw":..,"Away":..}, "Betano": {...}}
        }

    Regras: em caso de falha na API, levante uma exceção. NUNCA devolva dados de exemplo
    nem dados de execuções anteriores. Lista vazia significa apenas "sem jogos hoje".
    """
    raise NotImplementedError(
        "coletor de odds ainda não implementado (coletar_fixtures). "
        "Para testar o fluxo com dados fictícios, use USE_MOCK_DATA=1."
    )


def carregar_mock(agora_brt: datetime) -> List[Dict[str, Any]]:
    """Dados FICTÍCIOS, só para testar o fluxo (USE_MOCK_DATA=1)."""
    inicio = (agora_brt + timedelta(minutes=30)).isoformat()
    agora_utc = datetime.now(timezone.utc)
    return [
        {   # deve dar PASS (EV abaixo do mínimo)
            "external_id": "MOCK_001",
            "league": "Brasileirão Série A",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "start_time_iso": inicio,
            "odds_timestamp_utc": agora_utc,
            "sharp_odds": {"Home": 2.10, "Draw": 3.35, "Away": 3.60},
            "commercial_odds": {
                "Superbet": {"Home": 2.25, "Draw": 3.30, "Away": 3.40},
                "Betano": {"Home": 2.18, "Draw": 3.40, "Away": 3.55},
                "Bet365": {"Home": 2.20, "Draw": 3.30, "Away": 3.65},
            },
        },
        {   # deve dar VALUE no mandante (para validar a formatação)
            "external_id": "MOCK_002",
            "league": "Liga Fictícia",
            "home_team": "Mock A & Cia",
            "away_team": "Mock B",
            "start_time_iso": inicio,
            "odds_timestamp_utc": agora_utc,
            "sharp_odds": {"Home": 2.00, "Draw": 3.50, "Away": 4.00},
            "commercial_odds": {
                "Superbet": {"Home": 2.20, "Draw": 3.40, "Away": 3.80},
                "Betano": {"Home": 2.10, "Draw": 3.45, "Away": 3.90},
            },
        },
    ]


def _parse_inicio(iso: str) -> Optional[datetime]:
    """Interpreta o horário de início. Rejeita datas sem fuso (evita erro de 3h no runner UTC)."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def filtrar_jogos_de_hoje(fixtures: List[Dict[str, Any]], agora_brt: datetime) -> List[Dict[str, Any]]:
    """Mantém só jogos de hoje (BRT) que ainda não começaram."""
    validos = []
    for f in fixtures:
        inicio = _parse_inicio(f.get("start_time_iso", ""))
        if inicio is None:
            print(f"[WARN] {f.get('external_id')}: horário ausente ou sem fuso — ignorado.")
            continue
        inicio_brt = inicio.astimezone(BRT)
        if inicio_brt <= agora_brt or inicio_brt.date() != agora_brt.date():
            continue
        validos.append(f)
    return validos


# ------------------------------------------------------------------------ pipeline
def run_pipeline_10am() -> int:
    agora_brt = datetime.now(BRT)
    data_formatada = agora_brt.strftime("%d/%m/%Y")
    print(f"[INFO] Pipeline de {data_formatada} (modo {'TESTE/MOCK' if MODO_TESTE else 'PRODUÇÃO'})")

    try:
        if MODO_TESTE:
            fixtures = carregar_mock(agora_brt)
        else:
            fixtures = filtrar_jogos_de_hoje(coletar_fixtures(agora_brt), agora_brt)
    except NotImplementedError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Falha na coleta de dados: {type(e).__name__}. Nenhum relatório enviado.")
        return 1

    engine = QuantEngine(min_ev=0.03, min_price_edge=0.03, max_data_age_seconds=180)
    processed_matches = []

    with DatabaseManager(":memory:" if MODO_TESTE else None) as db:
        for fixture in fixtures:
            try:
                # 1. Registrar/atualizar a partida no SQLite
                match_id = db.log_match(
                    external_id=fixture["external_id"],
                    league=fixture["league"],
                    home=fixture["home_team"],
                    away=fixture["away_team"],
                    start_time=fixture["start_time_iso"],
                )

                # 2. Engine quantitativa (line shopping + de-vig + multi-seleção)
                results = engine.evaluate_match_market(
                    sharp_odds_1x2=fixture["sharp_odds"],
                    commercial_odds_multi_book=fixture["commercial_odds"],
                    last_update_utc=fixture["odds_timestamp_utc"],
                )

                # 3. Log dos sinais para auditoria futura de CLV
                for res in results:
                    print(f"[INFO] {fixture['home_team']} x {fixture['away_team']} | "
                          f"{res.selection}: {res.status} EV={res.ev_percent}% {res.note}".rstrip())
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
                            "kelly_stake": res.kelly_stake_percent,
                        })

                processed_matches.append({
                    "match": {
                        "home_team": fixture["home_team"],
                        "away_team": fixture["away_team"],
                        "league": fixture["league"],
                        "horario": datetime.fromisoformat(
                            fixture["start_time_iso"].replace("Z", "+00:00")
                        ).astimezone(BRT).strftime("%H:%M"),
                    },
                    "results": results,
                })
            except Exception as e:
                print(f"[ERROR] Fixture {fixture.get('external_id')} ignorada: {type(e).__name__}: {e}")

    # 4. Formatar e enviar
    report_html = TelegramFormatter.format_daily_report(data_formatada, processed_matches)

    if MODO_TESTE:
        print("\n----- RELATÓRIO (modo teste, NÃO enviado) -----\n" + report_html)
        return 0

    if send_telegram_message(report_html):
        print("[OK] Relatório enviado.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(run_pipeline_10am())
