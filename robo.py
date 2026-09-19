# -*- coding: utf-8 -*-
"""
RELATÓRIO DIÁRIO DE PROJEÇÕES DE FUTEBOL — V2
================================================

Principais melhorias sobre a V1:
- Descoberta de partidas do dia separada da busca de histórico.
- Datas calculadas em Brasília e consultadas por dia, reduzindo o risco de
  perder partidas por causa de janelas/feeds da API.
- Retry + timeout + User-Agent nas chamadas HTTP.
- Cache de requests para reduzir chamadas repetidas.
- Forma recente ponderada: jogos mais recentes têm maior peso.
- Separação casa/fora quando houver amostra suficiente.
- Força ofensiva/defensiva combinada com média da competição.
- Poisson com ajuste de empate de baixa pontuação (Dixon-Coles simplificado).
- Probabilidades 1X2, dupla chance, Over/Under, BTTS e placares mais prováveis.
- Escanteios/cartões continuam sendo N/D quando a ESPN não fornece dados.
- "Confiança" NÃO é inventada: é um indicador de qualidade da amostra/modelo,
  separado da probabilidade matemática estimada.
- Filtros de qualidade para evitar projeções com amostra insuficiente.
- Relatório mais transparente e diagnóstico no terminal.

REQUISITOS:
    pip install requests

VARIÁVEIS:
    TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID

Observação:
Este código gera estimativas estatísticas. Não representa garantia de resultado,
não considera automaticamente escalações/lesões/odds/closing line e não deve ser
interpretado como recomendação automática de aposta.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import html
import math
import os
import statistics
import time
from typing import Any

import requests


# ============================================================
# CONFIGURAÇÃO
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BRT = timezone(timedelta(hours=-3))

LIGAS_ELITE = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A Itália",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "uefa.champions": "Champions League",
    "bra.1": "Brasileirão Serie A",
    "usa.1": "MLS",
}

# Parâmetros principais
N_FORMA = 8
N_MINIMO = 5
HISTORICO_DIAS = 120

# Peso temporal: 1.0 = sem redução; 0.85 = cada jogo anterior recebe 85%
# do peso do jogo imediatamente mais recente.
DECAY = 0.88

# Casa/fora só entra no cálculo se houver esta quantidade mínima.
N_MIN_CASA_FORA = 3

# Pequeno fator de suavização para evitar lambdas extremos com amostras pequenas.
SHRINK = 0.20

# Ajuste Dixon-Coles simplificado para resultados 0x0, 1x0, 0x1 e 1x1.
RHO = -0.08

MAX_GOLS = 8
HTTP_TIMEOUT = 15
RETRIES = 3
BACKOFF = 0.8
PAUSA_API = 0.10
TELEGRAM_LIMIT = 3800

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "FootballProjectionBot/2.0 (+https://www.espn.com/)"
})


# ============================================================
# UTILIDADES
# ============================================================

def agora_brt() -> datetime:
    return datetime.now(BRT)


def data_brt(dt: datetime) -> str:
    return dt.astimezone(BRT).strftime("%Y-%m-%d")


def formatar_data_br(dt: datetime) -> str:
    return dt.astimezone(BRT).strftime("%d/%m/%Y")


def converter_hora_brasilia(data_utc_str: str) -> tuple[str, str]:
    if not data_utc_str:
        agora = agora_brt()
        return agora.strftime("%H:%M BRT"), data_brt(agora)

    try:
        dt = datetime.fromisoformat(data_utc_str.replace("Z", "+00:00"))
        dt_brt = dt.astimezone(BRT)
        return dt_brt.strftime("%H:%M BRT"), data_brt(dt_brt)
    except (ValueError, TypeError):
        agora = agora_brt()
        return agora.strftime("%H:%M BRT"), data_brt(agora)


def media_ponderada(valores: list[float], decay: float = DECAY) -> float | None:
    if not valores:
        return None

    # valores devem estar do mais recente para o mais antigo.
    pesos = [decay ** i for i in range(len(valores))]
    return sum(v * p for v, p in zip(valores, pesos)) / sum(pesos)


def clamp(x: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, x))


def safe_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ============================================================
# HTTP / ESPN
# ============================================================

def get_json(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    for tentativa in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, params=params, timeout=HTTP_TIMEOUT)

            if r.status_code == 200:
                return r.json()

            # Erros temporários
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(BACKOFF * tentativa)
                continue

            print(f"[HTTP] {r.status_code} -> {url}")
            return None

        except (requests.RequestException, ValueError) as exc:
            print(f"[HTTP] tentativa {tentativa}/{RETRIES}: {exc}")
            if tentativa < RETRIES:
                time.sleep(BACKOFF * tentativa)

    return None


@lru_cache(maxsize=256)
def scoreboard_dia(league_code: str, yyyymmdd: str) -> tuple[dict, ...]:
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
        f"{league_code}/scoreboard"
    )

    dados = get_json(url, {"dates": yyyymmdd})
    if not dados:
        return tuple()

    return tuple(dados.get("events", []))


def obter_jogos_do_dia(league_code: str, dt: datetime) -> list[dict]:
    """
    Consulta o scoreboard especificamente para o dia em Brasília.
    Isso evita depender de uma chamada histórica para descobrir os jogos atuais.
    """
    return list(scoreboard_dia(league_code, dt.strftime("%Y%m%d")))


def obter_historico_liga(
    league_code: str,
    fim: datetime,
    dias: int = HISTORICO_DIAS
) -> list[dict]:
    """
    Baixa os scoreboards dia a dia. É mais lento que uma chamada por intervalo,
    mas é mais robusto para feeds que não retornam corretamente uma janela longa.
    """
    eventos: dict[str, dict] = {}

    inicio = fim - timedelta(days=dias)

    for i in range(dias + 1):
        dia = inicio + timedelta(days=i)
        for ev in obter_jogos_do_dia(league_code, dia):
            event_id = str(ev.get("id", ""))
            if event_id:
                eventos[event_id] = ev
        time.sleep(PAUSA_API)

    return list(eventos.values())


# ============================================================
# IDENTIFICAÇÃO / STATUS
# ============================================================

def competition(ev: dict) -> dict:
    comps = ev.get("competitions") or []
    return comps[0] if comps else {}


def status_evento(ev: dict) -> str:
    comp = competition(ev)
    status = comp.get("status") or ev.get("status") or {}
    return str(
        (status.get("type") or {}).get("state")
        or status.get("type")
        or status.get("name")
        or ""
    ).lower()


def partida_concluida(ev: dict) -> bool:
    return status_evento(ev) in {"post", "final", "completed"}


def partida_cancelada_adiada(ev: dict) -> bool:
    s = status_evento(ev).upper()
    return any(x in s for x in ("POSTPONED", "CANCELED", "CANCELLED", "SUSPENDED"))


def obter_competidores(ev: dict) -> list[dict]:
    return competition(ev).get("competitors") or []


def obter_times(ev: dict) -> tuple[dict | None, dict | None]:
    comps = obter_competidores(ev)
    if len(comps) < 2:
        return None, None

    casa = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
    fora = next((c for c in comps if c.get("homeAway") == "away"), comps[1])
    return casa, fora


# ============================================================
# ESTATÍSTICAS DE ESCANTEIOS / CARTÕES
# ============================================================

@lru_cache(maxsize=1024)
def obter_escanteios_cartoes(
    league_code: str,
    event_id: str,
    team_id: str
) -> tuple[float | None, float | None]:

    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
        f"{league_code}/summary"
    )

    dados = get_json(url, {"event": event_id})
    if not dados:
        return None, None

    for time_bx in (dados.get("boxscore") or {}).get("teams", []):
        team = time_bx.get("team") or {}
        if str(team.get("id")) != str(team_id):
            continue

        escanteios = None
        cartoes = 0.0
        encontrou_cartao = False

        for stat in time_bx.get("statistics", []):
            chave = str(
                stat.get("name")
                or stat.get("abbreviation")
                or ""
            ).lower()

            valor = safe_float(stat.get("displayValue"))
            if valor is None:
                continue

            if "corner" in chave:
                escanteios = valor
            elif "yellow" in chave or "red" in chave or "card" in chave:
                cartoes += valor
                encontrou_cartao = True

        return escanteios, cartoes if encontrou_cartao else None

    return None, None


# ============================================================
# FORMA RECENTE
# ============================================================

def extrair_gols_do_time(ev: dict, team_id: str) -> tuple[int, int, bool] | None:
    casa, fora = obter_times(ev)
    if not casa or not fora:
        return None

    alvo = None
    adversario = None

    if str(casa.get("team", {}).get("id")) == str(team_id):
        alvo, adversario = casa, fora
    elif str(fora.get("team", {}).get("id")) == str(team_id):
        alvo, adversario = fora, casa
    else:
        return None

    gm = safe_int(alvo.get("score"))
    gs = safe_int(adversario.get("score"))

    if gm is None or gs is None:
        return None

    return gm, gs, alvo.get("homeAway") == "home"


def obter_forma_recente(
    league_code: str,
    team_id: str,
    historico_liga: list[dict],
    cache: dict[str, dict],
    n: int = N_FORMA
) -> dict:

    key = f"{league_code}:{team_id}:{n}"
    if key in cache:
        return cache[key]

    jogos = []

    for ev in historico_liga:
        if not partida_concluida(ev):
            continue

        dados = extrair_gols_do_time(ev, team_id)
        if dados is None:
            continue

        dt = ev.get("date", "")
        jogos.append((dt, ev, dados))

    jogos.sort(key=lambda x: x[0], reverse=True)

    resultado = {
        "jogos_analisados": 0,
        "gols_marcados": [],
        "gols_sofridos": [],
        "casa_gm": [],
        "casa_gs": [],
        "fora_gm": [],
        "fora_gs": [],
        "escanteios": [],
        "cartoes": [],
    }

    for _, ev, (gm, gs, foi_casa) in jogos[:n]:
        resultado["gols_marcados"].append(gm)
        resultado["gols_sofridos"].append(gs)
        resultado["jogos_analisados"] += 1

        if foi_casa:
            resultado["casa_gm"].append(gm)
            resultado["casa_gs"].append(gs)
        else:
            resultado["fora_gm"].append(gm)
            resultado["fora_gs"].append(gs)

        event_id = ev.get("id")
        if event_id:
            esc, crt = obter_escanteios_cartoes(
                league_code, str(event_id), str(team_id)
            )
            if esc is not None:
                resultado["escanteios"].append(esc)
            if crt is not None:
                resultado["cartoes"].append(crt)
            time.sleep(PAUSA_API)

    cache[key] = resultado
    return resultado


def obter_media_competicao(historico: list[dict]) -> dict:
    """
    Calcula médias gerais da competição na janela histórica.
    Serve como prior para reduzir exageros de amostras pequenas.
    """
    gols = []
    gols_casa = []
    gols_fora = []

    for ev in historico:
        if not partida_concluida(ev):
            continue

        casa, fora = obter_times(ev)
        if not casa or not fora:
            continue

        gc = safe_int(casa.get("score"))
        gf = safe_int(fora.get("score"))

        if gc is None or gf is None:
            continue

        gols.append(gc + gf)
        gols_casa.append(gc)
        gols_fora.append(gf)

    return {
        "jogos": len(gols),
        "media_total": media_ponderada(gols, 1.0) if gols else 2.5,
        "media_casa": media_ponderada(gols_casa, 1.0) if gols_casa else 1.35,
        "media_fora": media_ponderada(gols_fora, 1.0) if gols_fora else 1.10,
    }


# ============================================================
# MODELO
# ============================================================

def shrink(valor: float, prior: float, peso: float = SHRINK) -> float:
    return valor * (1 - peso) + prior * peso


def obter_forcas(
    forma: dict,
    competencia: dict,
    mandante: bool
) -> tuple[float, float]:

    ataque = media_ponderada(forma["gols_marcados"])
    defesa = media_ponderada(forma["gols_sofridos"])

    if ataque is None:
        ataque = competencia["media_casa"] if mandante else competencia["media_fora"]
    if defesa is None:
        defesa = competencia["media_fora"] if mandante else competencia["media_casa"]

    # A dimensão casa/fora só substitui a média geral quando existe amostra mínima.
    if mandante and len(forma["casa_gm"]) >= N_MIN_CASA_FORA:
        ataque = 0.60 * media_ponderada(forma["casa_gm"]) + 0.40 * ataque
        defesa = 0.60 * media_ponderada(forma["casa_gs"]) + 0.40 * defesa

    if not mandante and len(forma["fora_gm"]) >= N_MIN_CASA_FORA:
        ataque = 0.60 * media_ponderada(forma["fora_gm"]) + 0.40 * ataque
        defesa = 0.60 * media_ponderada(forma["fora_gs"]) + 0.40 * defesa

    return max(ataque, 0.05), max(defesa, 0.05)


def calcular_lambdas(
    forma_casa: dict,
    forma_fora: dict,
    competencia: dict
) -> tuple[float, float]:

    ataque_casa, defesa_casa = obter_forcas(
        forma_casa, competencia, True
    )
    ataque_fora, defesa_fora = obter_forcas(
        forma_fora, competencia, False
    )

    # Mistura de ataque próprio + defesa adversária.
    base_casa = 0.55 * ataque_casa + 0.45 * defesa_fora
    base_fora = 0.55 * ataque_fora + 0.45 * defesa_casa

    # Pequena vantagem de mando, sem exagero.
    lambda_casa = base_casa * 1.08
    lambda_fora = base_fora * 0.96

    # Limites conservadores para impedir explosões com amostra curta.
    return (
        clamp(lambda_casa, 0.15, 4.50),
        clamp(lambda_fora, 0.15, 4.00),
    )


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        lam = 0.05
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def ajuste_dixon_coles(
    i: int,
    j: int,
    lambda_casa: float,
    lambda_fora: float
) -> float:
    if i == 0 and j == 0:
        return 1 - lambda_casa * lambda_fora * RHO
    if i == 0 and j == 1:
        return 1 + lambda_casa * RHO
    if i == 1 and j == 0:
        return 1 + lambda_fora * RHO
    if i == 1 and j == 1:
        return 1 - RHO
    return 1.0


def matriz_probabilidades(
    lambda_casa: float,
    lambda_fora: float,
    max_gols: int = MAX_GOLS
) -> list[list[float]]:

    matriz = []

    for i in range(max_gols + 1):
        linha = []
        for j in range(max_gols + 1):
            p = (
                poisson_pmf(i, lambda_casa)
                * poisson_pmf(j, lambda_fora)
                * ajuste_dixon_coles(i, j, lambda_casa, lambda_fora)
            )
            linha.append(max(p, 0.0))
        matriz.append(linha)

    soma = sum(map(sum, matriz))

    if soma <= 0:
        return matriz

    return [[p / soma for p in linha] for linha in matriz]


def probabilidades_1x2(matriz: list[list[float]]) -> tuple[float, float, float]:
    casa = empate = fora = 0.0

    for i, linha in enumerate(matriz):
        for j, p in enumerate(linha):
            if i > j:
                casa += p
            elif i == j:
                empate += p
            else:
                fora += p

    return casa, empate, fora


def prob_over(matriz: list[list[float]], linha: float) -> float:
    return sum(
        p
        for i, row in enumerate(matriz)
        for j, p in enumerate(row)
        if i + j > linha
    )


def prob_btts(matriz: list[list[float]]) -> float:
    return sum(
        p
        for i, row in enumerate(matriz)
        for j, p in enumerate(row)
        if i >= 1 and j >= 1
    )


def placares_mais_provaveis(
    matriz: list[list[float]],
    quantidade: int = 3
) -> list[tuple[str, float]]:

    itens = []
    for i, row in enumerate(matriz):
        for j, p in enumerate(row):
            itens.append((f"{i}x{j}", p))

    itens.sort(key=lambda x: x[1], reverse=True)
    return itens[:quantidade]


# ============================================================
# QUALIDADE / PROJEÇÃO
# ============================================================

def qualidade_amostra(jogos_casa: int, jogos_fora: int) -> tuple[str, float]:
    minimo = min(jogos_casa, jogos_fora)

    if minimo >= 8:
        return "ALTA", 1.00
    if minimo >= 6:
        return "BOA", 0.90
    if minimo >= 5:
        return "LIMITADA", 0.75
    return "INSUFICIENTE", 0.0


def projetar_partida(
    forma_casa: dict,
    forma_fora: dict,
    competencia: dict
) -> dict:

    jc = forma_casa["jogos_analisados"]
    jf = forma_fora["jogos_analisados"]

    qualidade, fator = qualidade_amostra(jc, jf)

    if jc < N_MINIMO or jf < N_MINIMO:
        return {
            "dados_suficientes": False,
            "qualidade": qualidade,
            "amostra": f"{jc} jogos (casa) / {jf} jogos (fora)",
            "vencedor": "N/D — amostra insuficiente",
            "dupla_chance": "N/D",
            "gols": "N/D",
            "placar": "N/D",
            "btts": "N/D",
            "escanteios": "N/D",
            "cartoes": "N/D",
            "probabilidades": "N/D",
        }

    lc, lf = calcular_lambdas(forma_casa, forma_fora, competencia)
    matriz = matriz_probabilidades(lc, lf)

    pc, pe, pf = probabilidades_1x2(matriz)

    # Linhas fixas de mercado são exibidas como probabilidades do modelo,
    # em vez de "cravar" uma linha artificial derivada do lambda.
    over_1_5 = prob_over(matriz, 1.5)
    over_2_5 = prob_over(matriz, 2.5)
    over_3_5 = prob_over(matriz, 3.5)
    under_3_5 = 1 - over_3_5
    btts = prob_btts(matriz)

    placares = placares_mais_provaveis(matriz)
    placar_txt = " | ".join(
        f"{p[0]} ({p[1]*100:.1f}%)" for p in placares
    )

    if pc >= pe and pc >= pf:
        resultado = f"Mandante — {pc*100:.1f}%"
        dupla = f"1X — {(pc+pe)*100:.1f}%"
    elif pf >= pc and pf >= pe:
        resultado = f"Visitante — {pf*100:.1f}%"
        dupla = f"X2 — {(pf+pe)*100:.1f}%"
    else:
        resultado = f"Empate — {pe*100:.1f}%"
        dupla = f"1X2 — {pe*100:.1f}% empate"

    # "Confiança" não é probabilidade de acerto. É somente qualidade da amostra.
    confianca_amostra = fator * 100

    esc = "N/D"
    if forma_casa["escanteios"] and forma_fora["escanteios"]:
        esc_total = (
            media_ponderada(forma_casa["escanteios"], 1.0)
            + media_ponderada(forma_fora["escanteios"], 1.0)
        )
        esc = f"Média combinada: {esc_total:.1f}"

    crt = "N/D"
    if forma_casa["cartoes"] and forma_fora["cartoes"]:
        crt_total = (
            media_ponderada(forma_casa["cartoes"], 1.0)
            + media_ponderada(forma_fora["cartoes"], 1.0)
        )
        crt = f"Média combinada: {crt_total:.1f}"

    return {
        "dados_suficientes": True,
        "qualidade": qualidade,
        "amostra": f"{jc} jogos (casa) / {jf} jogos (fora)",
        "lambda_casa": lc,
        "lambda_fora": lf,
        "gols_esperados": lc + lf,
        "vencedor": resultado,
        "dupla_chance": dupla,
        "gols": (
            f"Over 1.5: {over_1_5*100:.1f}% | "
            f"Over 2.5: {over_2_5*100:.1f}% | "
            f"Over 3.5: {over_3_5*100:.1f}% | "
            f"Under 3.5: {under_3_5*100:.1f}%"
        ),
        "btts": f"Sim: {btts*100:.1f}% | Não: {(1-btts)*100:.1f}%",
        "placar": placar_txt,
        "escanteios": esc,
        "cartoes": crt,
        "probabilidades": (
            f"Casa {pc*100:.1f}% | "
            f"Empate {pe*100:.1f}% | "
            f"Fora {pf*100:.1f}%"
        ),
        "qualidade_amostra": f"{confianca_amostra:.0f}/100",
    }


# ============================================================
# PARTIDAS DO DIA
# ============================================================

def buscar_jogos_reais_do_dia() -> list[dict]:
    hoje = agora_brt()
    dia_hoje = data_brt(hoje)

    jogos = []
    ids = set()
    cache_forma = {}

    for code, nome_liga in LIGAS_ELITE.items():
        # 1) Descobre jogos do dia de forma independente.
        eventos_hoje = obter_jogos_do_dia(code, hoje)

        # 2) Histórico separado.
        historico = obter_historico_liga(code, hoje, HISTORICO_DIAS)

        competencia = obter_media_competicao(historico)

        for ev in eventos_hoje:
            event_id = str(ev.get("id", ""))

            if not event_id or event_id in ids:
                continue

            if partida_cancelada_adiada(ev):
                continue

            hora, data_jogo = converter_hora_brasilia(ev.get("date", ""))

            if data_jogo != dia_hoje:
                continue

            casa, fora = obter_times(ev)

            if not casa or not fora:
                continue

            tc = casa.get("team") or {}
            tf = fora.get("team") or {}

            nome_casa = tc.get("displayName") or tc.get("name") or "Mandante"
            nome_fora = tf.get("displayName") or tf.get("name") or "Visitante"
            id_casa = tc.get("id")
            id_fora = tf.get("id")

            if not id_casa or not id_fora:
                continue

            forma_casa = obter_forma_recente(
                code, str(id_casa), historico, cache_forma
            )
            forma_fora = obter_forma_recente(
                code, str(id_fora), historico, cache_forma
            )

            proj = projetar_partida(
                forma_casa, forma_fora, competencia
            )

            ids.add(event_id)

            jogos.append({
                "id": event_id,
                "partida": f"{nome_casa} x {nome_fora}",
                "liga": nome_liga,
                "horario": hora,
                "projecao": proj,
            })

    jogos.sort(key=lambda x: x["horario"])
    return jogos


# ============================================================
# TELEGRAM / RELATÓRIO
# ============================================================

def dividir_mensagem(texto: str, limite: int = TELEGRAM_LIMIT) -> list[str]:
    if len(texto) <= limite:
        return [texto]

    partes = []
    restante = texto

    while restante:
        if len(restante) <= limite:
            partes.append(restante)
            break

        corte = restante.rfind("\n", 0, limite)
        if corte <= 0:
            corte = limite

        partes.append(restante[:corte])
        restante = restante[corte:].lstrip("\n")

    return partes


def montar_relatorio(jogos: list[dict]) -> str:
    data = agora_brt().strftime("%d/%m/%Y")

    msg = (
        f"⚽ <b>RELATÓRIO DE PROJEÇÕES V2 — {data}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>MODELO ESTATÍSTICO + FORMA RECENTE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not jogos:
        msg += (
            "ℹ️ <i>Nenhuma partida foi retornada pelos feeds configurados "
            "para as ligas monitoradas nesta data.</i>\n\n"
            "🔎 <i>Isso significa que não houve evento retornado pela ESPN "
            "após a consulta diária — não que necessariamente não exista "
            "futebol em outras competições.</i>\n"
        )
    else:
        for j in jogos[:20]:
            p = j["projecao"]

            msg += (
                f"⚽ <b>{html.escape(j['partida'])}</b>\n"
                f"🏆 <i>{html.escape(j['liga'])}</i> | 🕟 <b>{j['horario']}</b>\n"
            )

            if not p["dados_suficientes"]:
                msg += (
                    f"⚠️ <b>Dados:</b> {p['qualidade']}\n"
                    f"🔎 <i>Amostra: {p['amostra']}</i>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                )
                continue

            msg += (
                f"👑 <b>1X2:</b> {p['vencedor']}\n"
                f"🎯 <b>Dupla chance:</b> {p['dupla_chance']}\n"
                f"⚽ <b>Gols:</b> {p['gols']}\n"
                f"🤝 <b>BTTS:</b> {p['btts']}\n"
                f"🎯 <b>Placares mais prováveis:</b> {p['placar']}\n"
                f"🚩 <b>Escanteios:</b> {p['escanteios']}\n"
                f"🟨 <b>Cartões:</b> {p['cartoes']}\n"
                f"📊 <b>Prob. 1X2:</b> {p['probabilidades']}\n"
                f"📐 <b>xG do modelo:</b> "
                f"{p['lambda_casa']:.2f} x {p['lambda_fora']:.2f} "
                f"(total {p['gols_esperados']:.2f})\n"
                f"🧪 <b>Qualidade da amostra:</b> {p['qualidade']} "
                f"({p['qualidade_amostra']})\n"
                f"🔎 <i>{p['amostra']}</i>\n"
                "━━━━━━━━━━━━━━━━━━\n"
            )

    msg += (
        "\n⚠️ <b>SOBRE O MODELO</b>\n"
        "As probabilidades são estimativas matemáticas, não garantia de "
        "resultado. O modelo usa forma recente, gols marcados/sofridos, "
        "contexto casa/fora, média da competição e distribuição de Poisson "
        "com ajuste simplificado para placares baixos.\n"
        "Escalações, lesões, suspensões, motivação, calendário, odds e "
        "movimentação de mercado não são incorporados automaticamente.\n"
        "A qualidade da amostra NÃO representa probabilidade de acerto.\n"
        "Aposte com responsabilidade."
    )

    return msg


def enviar_telegram(texto: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[TELEGRAM] Credenciais ausentes; relatório exibido apenas no terminal.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for parte in dividir_mensagem(texto):
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            r = SESSION.post(url, json=payload, timeout=HTTP_TIMEOUT)

            if r.status_code != 200:
                print(f"[TELEGRAM] HTTP {r.status_code}: {r.text[:300]}")

                # Fallback sem HTML.
                SESSION.post(
                    url,
                    json={
                        "chat_id": CHAT_ID,
                        "text": parte,
                        "disable_web_page_preview": True,
                    },
                    timeout=HTTP_TIMEOUT,
                )

        except requests.RequestException as exc:
            print(f"[TELEGRAM] erro de rede: {exc}")


# ============================================================
# DIAGNÓSTICO
# ============================================================

def diagnostico(jogos: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("DIAGNÓSTICO V2")
    print("=" * 70)
    print(f"Data BRT: {agora_brt().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ligas monitoradas: {len(LIGAS_ELITE)}")
    print(f"Partidas encontradas: {len(jogos)}")

    suficientes = sum(
        1 for j in jogos if j["projecao"].get("dados_suficientes")
    )
    print(f"Com amostra suficiente: {suficientes}")
    print(f"Sem amostra suficiente: {len(jogos) - suficientes}")

    if jogos:
        print("\nPartidas:")
        for j in jogos:
            p = j["projecao"]
            print(
                f"- {j['liga']}: {j['partida']} | {j['horario']} | "
                f"dados={p.get('qualidade')}"
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("Iniciando Relatório de Projeções V2...")

    inicio = time.time()

    try:
        jogos = buscar_jogos_reais_do_dia()
    except Exception as exc:
        print(f"ERRO CRÍTICO: {type(exc).__name__}: {exc}")
        raise

    relatorio = montar_relatorio(jogos)

    diagnostico(jogos)

    print("\n" + relatorio)

    enviar_telegram(relatorio)

    print(
        f"\nExecução concluída em {time.time() - inicio:.1f}s."
    )


if __name__ == "__main__":
    main()
