"""Busca jogos de futebol reais do dia via API-Football (api-football.com / API-SPORTS)."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")

# Todos os ids abaixo foram confirmados via /leagues?search= na própria
# API-Football (checando o campo "pais" de cada resultado).
LIGAS_PADRAO = {
    71: "Brasileirão Série A",       # Brazil
    72: "Serie B (Brasil)",          # Brazil - remova se não quiser cobrir a Série B
    73: "Copa do Brasil",            # Brazil
    13: "CONMEBOL Libertadores",     # World
    11: "CONMEBOL Sudamericana",     # World
    39: "Premier League",            # England
    140: "La Liga",                  # Spain
    135: "Serie A (Itália)",         # Italy
    78: "Bundesliga",                # Germany
    61: "Ligue 1",                   # France
    2: "Champions League",           # World (UEFA)
    3: "Europa League",              # World (UEFA)
}

# Mercados considerados conservadores o suficiente para o robô sugerir.
MERCADOS_CONSERVADORES = {"Double Chance", "Goals Over/Under"}
PROBABILIDADE_MINIMA = 0.70  # implícita a partir da odd real (1/odd)


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


def extrair_mercados_seguros(odds_response, mercados_aceitos=None, prob_minima=PROBABILIDADE_MINIMA):
    """Extrai até 3 mercados conservadores da resposta bruta de /odds, com
    probabilidade implícita (1/odd) igual ou acima do mínimo definido.

    Todos os valores retornados (odd, seleção, mercado) vêm diretamente da
    API — nada aqui é estimado ou inventado.
    """
    if mercados_aceitos is None:
        mercados_aceitos = MERCADOS_CONSERVADORES
    if not odds_response:
        return []

    bookmakers = odds_response[0].get("bookmakers", [])
    if not bookmakers:
        return []

    # Usa a primeira casa de apostas disponível. Se quiser padronizar por uma
    # casa específica (ex: Bet365), filtre bookmakers por "name" aqui.
    bets = bookmakers[0].get("bets", [])
    entradas = []
    for bet in bets:
        if bet.get("name") not in mercados_aceitos:
            continue
        for valor in bet.get("values", []):
            try:
                odd = float(valor["odd"])
            except (KeyError, ValueError, TypeError):
                continue
            if odd <= 0:
                continue
            prob_implicita = 1 / odd
            if prob_implicita >= prob_minima:
                entradas.append({
                    "mercado": bet["name"],
                    "selecao": valor["value"],
                    "odd": odd,
                    "prob_implicita": prob_implicita,
                })

    entradas.sort(key=lambda e: e["prob_implicita"], reverse=True)
    return entradas[:3]


def formatar_jogos_para_prompt(jogos, odds_por_fixture=None):
    """Monta o texto de jogos+odds que vai para o prompt do Gemini.

    IMPORTANTE (correção de bug): antes, quando havia odds disponíveis, o
    texto só dizia "ver dados brutos anexos" sem anexar nada de fato — o
    modelo nunca recebia os números reais. Agora os valores de odd e
    probabilidade implícita são escritos diretamente na linha do jogo.
    """
    if not jogos:
        return "Nenhum jogo pré-jogo encontrado para hoje a partir do horário configurado."

    odds_por_fixture = odds_por_fixture or {}
    linhas = []

    for jogo in jogos:
        linha = "- " + jogo["time_casa"] + " x " + jogo["time_fora"] + " (" + jogo["liga"] + ", às " + jogo["horario"] + ")"
        odds_jogo = odds_por_fixture.get(jogo["fixture_id"])
        entradas = extrair_mercados_seguros(odds_jogo) if odds_jogo else []

        if entradas:
            linha += "\n  Odds reais verificadas (NÃO altere estes números, apenas comente):"
            for entrada in entradas:
                linha += (
                    "\n    * " + entrada["mercado"] + " - " + entrada["selecao"]
                    + ": odd " + f"{entrada['odd']:.2f}"
                    + " (prob. implícita ~" + f"{entrada['prob_implicita'] * 100:.0f}%" + ")"
                )
        elif odds_jogo:
            linha += "\n  Odds verificadas pela API, mas nenhum mercado atingiu o mínimo de confiança; NÃO invente valores"
        else:
            linha += "\n  Odds não verificadas pela API; NÃO invente valores"

        linhas.append(linha)

    return "\n".join(linhas)
