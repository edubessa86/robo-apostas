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


def buscar_id_liga_por_nome(api_key: str, nome_busca: str, timeout: int = 15) -> list[dict]:
    """Busca ligas/competições pelo nome usando o endpoint oficial /leagues.

    Use isso para descobrir o ID correto de uma competição (ex: "Copa do
    Brasil", "Serie B", "Libertadores") em vez de adivinhar o número — os
    IDs variam entre provedores de API de futebol e usar um ID errado faz
    o robô simplesmente não encontrar nenhum jogo, sem erro nenhum.

    Retorna uma lista de dicts com id, nome, país e temporadas disponíveis,
    para você conferir e copiar o ID certo para LIGAS_PADRAO.

    Exemplo de uso local (não roda no GitHub Actions, é só para consulta):
        from api_football import buscar_id_liga_por_nome
        resultados = buscar_id_liga_por_nome("SUA_CHAVE", "Copa do Brasil")
        for r in resultados:
            print(r)
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/leagues",
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
            "tipo": liga.get("type"),  # "League" ou "Cup"
            "pais": pais.get("name"),
        })
    return resultados


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
    conversão de fuso, o que também podia
