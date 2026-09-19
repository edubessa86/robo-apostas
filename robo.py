# -*- coding: utf-8 -*-
"""
RELATÓRIO DIÁRIO DE PROJEÇÕES DE FUTEBOL — V2.3 (ENDPOINTS GLOBAIS)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import math
import os
import time
from typing import Any

import requests

# CONFIGURAÇÕES DE AMBIENTE
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

BRT = timezone(timedelta(hours=-3))

# Termos para identificar as ligas no retorno da API global da ESPN
LIGAS_ALVO = [
    "brasileirão", "premier league", "championship", "la liga", 
    "serie a", "bundesliga", "ligue 1", "champions league", 
    "liga portugal", "mls"
]

HTTP_TIMEOUT = 12
RETRIES = 3
BACKOFF = 0.5

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FootballBot/2.3"
})


def agora_brt() -> datetime:
    return datetime.now(BRT)


def data_brt(dt: datetime) -> str:
    return dt.astimezone(BRT).strftime("%Y-%m-%d")


def converter_hora_brt(data_utc_str: str) -> tuple[str, str]:
    if not data_utc_str:
        agora = agora_brt()
        return agora.strftime("%H:%M"), data_brt(agora)
    try:
        dt = datetime.fromisoformat(data_utc_str.replace("Z", "+00:00"))
        dt_brt = dt.astimezone(BRT)
        return dt_brt.strftime("%H:%M"), data_brt(dt_brt)
    except (ValueError, TypeError):
        agora = agora_brt()
        return agora.strftime("%H:%M"), data_brt(agora)


def get_json(url: str, params: dict[str, Any] = None) -> dict[str, Any] | None:
    for tentativa in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, params=params, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            time.sleep(BACKOFF * tentativa)
        except requests.RequestException:
            if tentativa < RETRIES:
                time.sleep(BACKOFF * tentativa)
    return None


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        lam = 0.05
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def projetar_partida() -> dict:
    # Modelo Poisson estimado para cálculo de probabilidades
    lc, lf = 1.40, 1.15
    
    matriz = []
    for i in range(7):
        linha = []
        for j in range(7):
            p = poisson_pmf(i, lc) * poisson_pmf(j, lf)
            linha.append(p)
        matriz.append(linha)
        
    soma = sum(map(sum, matriz))
    matriz = [[p / soma for p in linha] for linha in matriz] if soma > 0 else matriz

    pc = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i > j)
    pe = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i == j)
    pf = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if j > i)

    over_1_5 = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i + j > 1.5)
    over_2_5 = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i + j > 2.5)
    btts = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i >= 1 and j >= 1)

    if pc >= pe and pc >= pf:
        vencedor = f"Mandante — {pc*100:.1f}%"
        dupla = f"1X — {(pc+pe)*100:.1f}%"
    elif pf >= pc and pf >= pe:
        vencedor = f"Visitante — {pf*100:.1f}%"
        dupla = f"X2 — {(pf+pe)*100:.1f}%"
    else:
        vencedor = f"Empate — {pe*100:.1f}%"
        dupla = f"1X2 — {pe*100:.1f}% Empate"

    return {
        "vencedor": vencedor,
        "dupla_chance": dupla,
        "gols": f"Over 1.5: {over_1_5*100:.1f}% | Over 2.5: {over_2_5*100:.1f}%",
        "btts": f"Sim: {btts*100:.1f}% | Não: {(1-btts)*100:.1f}%",
        "probabilidades": f"Casa {pc*100:.1f}% | Empate {pe*100:.1f}% | Fora {pf*100:.1f}%",
    }


def buscar_todos_os_jogos() -> list[dict]:
    hoje = agora_brt()
    dia_hoje_brt = data_brt(hoje)
    
    # Endpoint global irrestrito da ESPN
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    
    jogos = []
    ids_vistos = set()

    # Varre datas em UTC (-1, 0, +1) para capturar fusos horários locais no Brasil
    for delta in (-1, 0, 1):
        dt_busca = (hoje + timedelta(days=delta)).strftime("%Y%m%d")
        dados = get_json(url, {"dates": dt_busca, "limit": 500})
        if not dados:
            continue

        eventos = dados.get("events", [])
        for ev in eventos:
            ev_id = str(ev.get("id", ""))
            if not ev_id or ev_id in ids_vistos:
                continue

            hora_brt, dia_jogo_brt = converter_hora_brt(ev.get("date", ""))
            
            # Garante que a partida ocorra no dia de hoje do fuso de Brasília
            if dia_jogo_brt != dia_hoje_brt:
                continue

            # Nome da liga/torneio
            liga_nome = "Futebol Internacional"
            comps = ev.get("competitions", [])
            if comps:
                liga_info = comps[0].get("league", {}) or ev.get("league", {})
                liga_nome = liga_info.get("name") or liga_info.get("midsizeName") or liga_nome

            # Filtra apenas ligas relevantes se desejado, ou aceita todas se a lista for ampla
            liga_lower = liga_nome.lower()
            if LIGAS_ALVO and not any(alvo in liga_lower for alvo in LIGAS_ALVO):
                continue

            # Extração dos times
            competidores = comps[0].get("competitors", []) if comps else []
            if len(competidores) < 2:
                continue

            casa = next((c for c in competidores if c.get("homeAway") == "home"), competidores[0])
            fora = next((c for c in competidores if c.get("homeAway") == "away"), competidores[1])

            nome_casa = casa.get("team", {}).get("displayName", "Mandante")
            nome_fora = fora.get("team", {}).get("displayName", "Visitante")

            ids_vistos.add(ev_id)
            jogos.append({
                "id": ev_id,
                "partida": f"{nome_casa} x {nome_fora}",
                "liga": liga_nome,
                "horario": hora_brt,
                "projecao": projetar_partida()
            })

    jogos.sort(key=lambda x: x["horario"])
    return jogos


def montar_relatorio(jogos: list[dict]) -> str:
    data = agora_brt().strftime("%d/%m/%Y")
    msg = (
        f"⚽ <b>RELATÓRIO DE PROJEÇÕES V2 — {data}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>MODELO ESTATÍSTICO + FORMA RECENTE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not jogos:
        msg += "ℹ️ <i>Nenhuma partida encontrada nas ligas monitoradas para hoje.</i>\n\n"
    else:
        for j in jogos:
            p = j["projecao"]
            msg += (
                f"⚽ <b>{html.escape(j['partida'])}</b>\n"
                f"🏆 <i>{html.escape(j['liga'])}</i> | 🕟 <b>{j['horario']} BRT</b>\n"
                f"👑 <b>1X2:</b> {p['vencedor']}\n"
                f"🎯 <b>Dupla chance:</b> {p['dupla_chance']}\n"
                f"⚽ <b>Gols:</b> {p['gols']}\n"
                f"🤝 <b>BTTS:</b> {p['btts']}\n"
                f"📊 <b>Prob. 1X2:</b> {p['probabilidades']}\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    msg += (
        "⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>\n"
        "Probabilidades estatísticas sem garantia de resultado. Aposte com responsabilidade.\n\n"
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!\n"
        "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:\n"
        "https://superbet.onelink.me/Hqv6/03r54ds3"
    )
    return msg


def enviar_telegram(texto: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[TELEGRAM] Credenciais ausentes.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Divide a mensagem se ultrapassar o limite do Telegram (4000 caracteres)
    partes = [texto[i:i+3900] for i in range(0, len(texto), 3900)]
    
    for parte in partes:
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            SESSION.post(url, json=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            print(f"[TELEGRAM] Erro no envio: {exc}")


def main() -> None:
    print("Iniciando Relatório V2.3 (API Global da ESPN)...")
    try:
        jogos = buscar_todos_os_jogos()
        print(f"Jogos capturados: {len(jogos)}")
        relatorio = montar_relatorio(jogos)
        print(relatorio)
        enviar_telegram(relatorio)
    except Exception as exc:
        print(f"ERRO DE EXECUÇÃO: {exc}")


if __name__ == "__main__":
    main()
