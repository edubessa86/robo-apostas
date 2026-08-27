"""Busca jogos de futebol reais do dia via API-Football (api-football.com / API-SPORTS)."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")

LIGAS_PADRAO = {
    71: "Brasileirão Série A",
    39: "Premier League",
    140: "La Liga",
    2: "Champions League",
    135: "Serie A (Itália)",
    61: "Ligue 1",
}


def _headers(api_key):
    return {"x-apisports-key": api_key}


def buscar_id_liga_por_nome(api_key, nome_busca, timeout=15):
    try:
        resp = requests.get(
            BASE_URL + "/leagues",
            headers=_headers(api_key),
            params={"search": nome_busca},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        logger.error("Erro ao buscar ID da liga '%s': %s", nome_busca, exc)
        return []

    resultados = []
    for item in payload.get("response", []):
        liga = item.get("league", {})
        pais = item.get("country", {})
        resultados.append({
            "id": liga.get("id"),
            "nome": liga.get("name"),
            "tipo": liga.get("type"),
            "pais": pais.get("name"),
        })
    return resultados


def buscar_jogos_do_dia(api_key, data=None, hora_minima=10, ligas=None, timeout=15):
    if data is None:
        data = datetime.now(FUSO_BRASILIA).strftime("%Y-%m-%d")
    if ligas is None:
        ligas = LIGAS_PADRAO

    jogos = []

    for liga_id, liga_nome in ligas.items():
        try:
            resp = requests.get(
                BASE_URL + "/fixtures",
                headers=_headers(api_key),
                params={
                    "date": data,
                    "league": liga_id,
                    "season": datetime.now(FUSO_BRASILIA).year,
                    "timezone": "America/Sao_Paulo",
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logger.error("Erro ao buscar fixtures da liga %s (%s): %s", liga_nome, liga_id, exc)
            continue

        for item in payload.get("response", []):
            try:
                fixture = item["fixture"]
                status_curto = fixture["status"]["short"]

                if status_curto != "NS":
                    continue

                horario_iso = fixture["date"]
                horario_local = datetime.fromisoformat(horario_iso)

                if horario_local.hour < hora_minima:
                    continue

                jogos.append({
                    "fixture_id": fixture["id"],
                    "liga": liga_nome,
                    "time_casa": item["teams"]["home"]["name"],
                    "time_fora": item["teams"]["away"]["name"],
                    "horario": horario_local.strftime("%H:%M"),
                })
            except (KeyError, ValueError) as exc:
                logger.warning("Item de fixture ignorado por formato inesperado: %s", exc)
                continue

    logger.info("Encontrados %d jogos pré-jogo a partir das %dh.", len(jogos), hora_minima)
    return jogos


def buscar_odds_do_jogo(api_key, fixture_id, timeout=15):
    try:
        resp = requests.get(
            BASE_URL + "/odds",
            headers=_headers(api_key),
            params={"fixture": fixture_id},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        logger.error("Erro ao buscar odds do fixture %s: %s", fixture_id, exc)
        return []

    return payload.get("response", [])


def formatar_jogos_para_prompt(jogos, odds_por_fixture=None):
    if not jogos:
        return "Nenhum jogo pré-jogo encontrado para hoje a partir do horário configurado."

    odds_por_fixture = odds_por_fixture or {}
    linhas = []

    for jogo in jogos:
        linha = "- " + jogo["time_casa"] + " x " + jogo["time_fora"] + " (" + jogo["liga"] + ", às " + jogo["horario"] + ")"
        odds_jogo = odds_por_fixture.get(jogo["fixture_id"])
        if odds_jogo:
            linha += " — odds disponíveis na API (ver dados brutos anexos)"
        else:
            linha += " — odds não verificadas pela API; NÃO invente valores"
        linhas.append(linha)

    return "\n".join(linhas)
