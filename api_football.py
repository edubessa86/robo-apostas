"""Busca jogos de futebol reais do dia via API-Football (api-football.com / API-SPORTS).

Por que isso existe: antes, o robô pedia para o Gemini usar a ferramenta
`google_search` (grounding) para descobrir os jogos do dia. Essa cota de
grounding é muito mais restrita no tier gratuito do que a cota normal de
geração de texto, e era a causa principal dos erros 429 constantes.

Agora a busca de jogos é feita aqui, com uma API dedicada e gratuita para
esse fim (free tier: ~100 requisições/dia — mais que suficiente para 1
chamada diária). O Gemini deixa de precisar buscar na web; ele só recebe
esses dados prontos e formata/analisa.

Documentação: https://www.api-football.com/documentation-v3
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")

# IDs de ligas mais comuns (ajuste conforme seu interesse).
# Lista completa de IDs: https://www.api-football.com/documentation-v3#tag/Leagues
LIGAS_PADRAO = {
    71: "Brasileirão Série A",
    39: "Premier League",
    140: "La Liga",
    2: "Champions League",
    135: "Serie A (Itália)",
    61: "Ligue 1",
}


def _headers(api_key: str) -> dict:
    return {"x-apisports-key": api_key}


def buscar_jogos_do_dia(
    api_key: str,
    data: str | None = None,
    hora_minima: int = 10,
    ligas: dict[int, str] | None = None,
    timeout: int = 15,
) -> list[dict]:
    """Retorna jogos de hoje (pré-jogo, ainda não iniciados) a partir da hora mínima.

    IMPORTANTE (bug corrigido): a API-Football, sem o parâmetro `timezone`,
    retorna e filtra as datas em UTC. Um jogo às 21h de Brasília já é
    00h UTC do dia seguinte, e ficava fora do filtro `date=hoje`. Além
    disso, o horário retornado era comparado contra `hora_minima` sem
    conversão de fuso, o que também podia excluir jogos válidos.
    Agora a consulta já pede os dados no fuso de Brasília
    (`timezone=America/Sao_Paulo`), então tanto o agrupamento por dia
    quanto a hora extraída já vêm corretos.

    Args:
        api_key: chave da API-Football (variável de ambiente API_FOOTBALL_KEY).
        data: data no formato "YYYY-MM-DD" (fuso de Brasília). Se None, usa a data atual.
        hora_minima: só retorna jogos com horário de início >= esta hora (Brasília).
        ligas: dict {id_liga: nome} para filtrar. Se None, usa LIGAS_PADRAO.

    Returns:
        Lista de dicts com: liga, time_casa, time_fora, horario, fixture_id.
    """
    if data is None:
        data = datetime.now(FUSO_BRASILIA).strftime("%Y-%m-%d")
    if ligas is None:
        ligas = LIGAS_PADRAO

    jogos: list[dict] = []

    for liga_id, liga_nome in ligas.items():
        try:
            resp = requests.get(
                f"{BASE_URL}/fixtures",
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
                status_curto = fixture["status"]["short"]  # "NS" = Not Started (pré-jogo)

                if status_curto != "NS":
                    continue  # ignora jogos ao vivo ou encerrados

                # Com timezone=America/Sao_Paulo na consulta, a API já retorna
                # este campo com o offset correto (ex: "2026-08-27T21:00:00-03:00").
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


def buscar_odds_do_jogo(api_key: str, fixture_id: int, timeout: int = 15) -> list[dict]:
    """Busca odds disponíveis para um jogo específico.

    ATENÇÃO: o endpoint /odds pode ter cobertura limitada de ligas/casas no
    tier gratuito da API-Football. Se vier vazio, o prompt já orienta o
    Gemini a indicar claramente que a odd não pôde ser verificada, em vez de
    inventar um valor.
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/odds",
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


def formatar_jogos_para_prompt(jogos: list[dict], odds_por_fixture: dict[int, list[dict]] | None = None) -> str:
    """Formata a lista de jogos (e odds, se houver) em texto simples para
    incluir no prompt do Gemini. Isso substitui a busca via `google_search`.
    """
    if not jogos:
        return "Nenhum jogo pré-jogo encontrado para hoje a partir do horário configurado."

    odds_por_fixture = odds_por_fixture or {}
    linhas = []

    for jogo in jogos:
        linha = (
            f"- {jogo['time_casa']} x {jogo['time_fora']} "
            f"({jogo['liga']}, às {jogo['horario']})"
        )
        odds_jogo = odds_por_fixture.get(jogo["fixture_id"])
        if odds_jogo:
            linha += " — odds disponíveis na API (ver dados brutos anexos)"
        else:
            linha += " — odds não verificadas pela API; NÃO invente valores"
        linhas.append(linha)

    return "\n".join(linhas)
