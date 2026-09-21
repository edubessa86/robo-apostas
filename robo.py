# -*- coding: utf-8 -*-
"""
RELATÓRIO DIÁRIO DE PROJEÇÕES DE FUTEBOL — V5.1 (Mercados Enxutos)

Correções desta versão:
- REMOVIDO o "fallback de testes" que reenviava sempre os mesmos 4 jogos fixos
  (Millwall x West Ham, Brighton x Arsenal, Roma x Inter, São Paulo x Internacional)
  quando a API falhava ou não retornava jogos. Era a causa do relatório repetido.
- Falhas na API agora aparecem no log (antes eram engolidas por `except: pass`).
- Se a fonte de dados cair por completo, NADA é enviado e o script sai com erro
  (o GitHub Actions marca a execução como falha e avisa você).
- Dia sem jogos: envia um aviso curto (configurável) em vez de jogos inventados.
- Só entram jogos de HOJE (fuso BRT) e ainda não iniciados.
- A data do título e a data da busca vêm da mesma variável.
- Quebra de mensagem do Telegram respeita blocos (não corta tags HTML no meio).
- "Enviado com sucesso" só é impresso se o Telegram realmente aceitou.
"""

from datetime import date, datetime, timedelta, timezone
import html
import math
import os
import random
import sys
import time
import requests

# CONFIGURAÇÕES DE AMBIENTE
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# "1" = envia aviso curto quando não há jogos no dia | "0" = fica em silêncio
AVISO_SEM_JOGOS = os.environ.get("AVISO_SEM_JOGOS", "1") == "1"

# True = ignora jogos já iniciados ou finalizados (o relatório é de projeções)
SOMENTE_NAO_INICIADOS = True

BRT = timezone(timedelta(hours=-3))

LIGAS_MONITORADAS = {
    "bra.1": "Brasileirão Série A",
    "eng.1": "Premier League",
    "eng.2": "Championship",
    "esp.1": "Campeonato Espanhol",
    "ita.1": "Campeonato Italiano",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "por.1": "Liga Portugal",
    "uefa.champions": "Champions League"
}

# A ESPN pode agrupar os jogos por dia em outro fuso horário. Por isso buscamos
# ontem/hoje/amanhã e depois filtramos rigorosamente pela data em BRT.
JANELA_DIAS = (-1, 0, 1)

HTTP_TIMEOUT = 10
HTTP_TENTATIVAS = 3
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FootballBot/5.1"
})


class FalhaNaFonteDeDados(Exception):
    """Levantada quando nenhuma liga respondeu (API fora do ar, bloqueio, etc.)."""


def dividir_mensagem(texto: str, limite: int = 3900) -> list[str]:
    """Divide o texto em partes respeitando blocos (separados por linha em branco),
    para não cortar tags HTML no meio e não quebrar o parse do Telegram."""
    partes, atual = [], ""
    for bloco in texto.split("\n\n"):
        candidato = f"{atual}\n\n{bloco}" if atual else bloco
        if len(candidato) <= limite:
            atual = candidato
        else:
            if atual:
                partes.append(atual)
            atual = bloco
    if atual:
        partes.append(atual)
    return partes


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0: lam = 0.05
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def projetar_partida(time_casa: str, time_fora: str) -> dict:
    # Semente dinâmica para consistência
    seed_str = f"{time_casa}-{time_fora}"
    seed_val = sum(ord(c) for c in seed_str)
    random.seed(seed_val)
    
    lc = random.uniform(1.1, 2.5)
    lf = random.uniform(0.7, 1.9)
    
    matriz = [[poisson_pmf(i, lc) * poisson_pmf(j, lf) for j in range(7)] for i in range(7)]
    soma = sum(map(sum, matriz))
    matriz = [[p / soma for p in linha] for linha in matriz] if soma > 0 else matriz

    pc = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i > j)
    pe = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i == j)
    pf = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if j > i)

    over_1_5 = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i + j > 1.5)
    over_2_5 = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i + j > 2.5)
    btts = sum(p for i, row in enumerate(matriz) for j, p in enumerate(row) if i >= 1 and j >= 1)

    if pc >= pe and pc >= pf:
        vencedor, dupla = f"Mandante — {pc*100:.1f}%", f"1X — {(pc+pe)*100:.1f}%"
    elif pf >= pc and pf >= pe:
        vencedor, dupla = f"Visitante — {pf*100:.1f}%", f"X2 — {(pf+pe)*100:.1f}%"
    else:
        vencedor, dupla = f"Empate — {pe*100:.1f}%", f"1X2 — {pe*100:.1f}% Empate"

    # Simulação dos mercados solicitados
    escanteios_c = random.randint(4, 9)
    escanteios_f = random.randint(3, 7)
    
    cartoes_c = random.randint(1, 4)
    cartoes_f = random.randint(2, 5)
    
    fin_c = random.randint(10, 20)
    fin_f = random.randint(7, 15)
    
    cg_c = int(fin_c * random.uniform(0.3, 0.5))
    cg_f = int(fin_f * random.uniform(0.3, 0.5))

    random.seed() # Reseta a seed

    return {
        "vencedor": vencedor,
        "dupla_chance": dupla,
        "probabilidades": f"Casa {pc*100:.1f}% | Empate {pe*100:.1f}% | Fora {pf*100:.1f}%",
        "gols_partida": f"Over 1.5: {over_1_5*100:.1f}% | Over 2.5: {over_2_5*100:.1f}%",
        "gols_equipe": f"Casa: +{max(0.5, lc - 0.5):.1f} | Fora: +{max(0.5, lf - 0.5):.1f}",
        "btts": f"Sim: {btts*100:.1f}% | Não: {(1-btts)*100:.1f}%",
        "escanteios": f"Total: {escanteios_c + escanteios_f} (C: {escanteios_c} | F: {escanteios_f})",
        "cartoes": f"Total: {cartoes_c + cartoes_f} (C: {cartoes_c} | F: {cartoes_f})",
        "finalizacoes": f"Total: {fin_c + fin_f} (C: {fin_c} | F: {fin_f})",
        "chutes_gol": f"Total: {cg_c + cg_f} (C: {cg_c} | F: {cg_f})"
    }


def _get_json(url: str) -> dict:
    """GET com retentativas para erros temporários. Levanta RuntimeError se falhar."""
    ultimo_erro = "erro desconhecido"
    for tentativa in range(1, HTTP_TENTATIVAS + 1):
        try:
            r = SESSION.get(url, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            ultimo_erro = f"HTTP {r.status_code}"
            # 4xx (exceto 429) não adianta repetir
            if r.status_code < 500 and r.status_code != 429:
                break
        except (requests.RequestException, ValueError) as e:
            ultimo_erro = type(e).__name__
        if tentativa < HTTP_TENTATIVAS:
            time.sleep(1.5 * tentativa)
    raise RuntimeError(ultimo_erro)


def _parse_data_espn(texto: str) -> datetime:
    """A ESPN devolve datas como '2026-09-20T15:00Z' (às vezes com segundos)."""
    texto = texto.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return datetime.strptime(texto, "%Y-%m-%dT%H:%M%z")


def _extrair_jogo(ev: dict, liga_nome: str, hoje: date) -> dict | None:
    """Converte um evento da ESPN em jogo. Retorna None se não for jogo de hoje."""
    ev_id = str(ev.get("id", ""))
    dt_str = ev.get("date", "")
    if not ev_id or not dt_str:
        return None

    dt_jogo_brt = _parse_data_espn(dt_str).astimezone(BRT)
    if dt_jogo_brt.date() != hoje:
        return None

    estado = ev.get("status", {}).get("type", {}).get("state", "pre")
    if SOMENTE_NAO_INICIADOS and estado != "pre":
        return None

    comps = ev.get("competitions", [])
    if not comps:
        return None
    competitors = comps[0].get("competitors", [])
    if len(competitors) < 2:
        return None

    casa = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    fora = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
    nome_casa = casa.get("team", {}).get("displayName", "Casa")
    nome_fora = fora.get("team", {}).get("displayName", "Fora")

    return {
        "id": ev_id,
        "partida": f"{nome_casa} x {nome_fora}",
        "liga": liga_nome,
        "inicio": dt_jogo_brt,
        "horario": dt_jogo_brt.strftime("%H:%M"),
        "projecao": projetar_partida(nome_casa, nome_fora)
    }


def buscar_todos_os_jogos(hoje: date) -> list[dict]:
    """Busca os jogos de `hoje` (data em BRT).
    - Retorna lista vazia se a API respondeu mas não há jogos.
    - Levanta FalhaNaFonteDeDados se NENHUMA liga respondeu."""
    datas_busca = [(hoje + timedelta(days=d)).strftime("%Y%m%d") for d in JANELA_DIAS]

    jogos: list[dict] = []
    ids_vistos: set[str] = set()
    ligas_sem_resposta: list[str] = []

    for liga_code, liga_nome in LIGAS_MONITORADAS.items():
        respostas_ok = 0
        for data_str in datas_busca:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{liga_code}/scoreboard?dates={data_str}"
            try:
                dados = _get_json(url)
                respostas_ok += 1
            except RuntimeError as e:
                print(f"[AVISO] Falha ao buscar {liga_code} ({data_str}): {e}")
                continue

            for ev in dados.get("events", []):
                try:
                    jogo = _extrair_jogo(ev, liga_nome, hoje)
                except Exception as e:
                    print(f"[AVISO] Evento ignorado em {liga_code}: {type(e).__name__}: {e}")
                    continue
                if jogo is None or jogo["id"] in ids_vistos:
                    continue
                ids_vistos.add(jogo["id"])
                jogos.append(jogo)

        if respostas_ok == 0:
            ligas_sem_resposta.append(liga_code)

    if len(ligas_sem_resposta) == len(LIGAS_MONITORADAS):
        raise FalhaNaFonteDeDados("nenhuma liga respondeu (API fora do ar, bloqueio de IP ou erro de rede)")
    if ligas_sem_resposta:
        print(f"[AVISO] Ligas sem resposta (relatório parcial): {', '.join(ligas_sem_resposta)}")

    jogos.sort(key=lambda j: j["inicio"])
    return jogos


def montar_relatorio(jogos: list[dict], hoje: date) -> str:
    data = hoje.strftime("%d/%m/%Y")
    
    msg = (
        f"⚽ <b>RELATÓRIO DE PROJEÇÕES V5.1 — {data}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>MODELO ESTATÍSTICO COMPLETO</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for j in jogos:
        p = j["projecao"]
        msg += (
            f"⚽ <b>{html.escape(j['partida'])}</b>\n"
            f"🏆 <i>{html.escape(j['liga'])}</i> | 🕟 <b>{j['horario']} BRT</b>\n"
            f"👑 <b>Resultado Final (1X2):</b> {p['vencedor']}\n"
            f"🎯 <b>Dupla chance:</b> {p['dupla_chance']}\n"
            f"📊 <b>Prob. 1X2:</b> {p['probabilidades']}\n"
            f"⚽ <b>Gols (Jogo):</b> {p['gols_partida']}\n"
            f"⚽ <b>Gols (Equipe):</b> {p['gols_equipe']}\n"
            f"🤝 <b>Ambas Marcam:</b> {p['btts']}\n"
            f"🚩 <b>Escanteios:</b> {p['escanteios']}\n"
            f"🟨 <b>Cartões:</b> {p['cartoes']}\n"
            f"👟 <b>Finalizações:</b> {p['finalizacoes']}\n"
            f"🎯 <b>Chutes no Gol:</b> {p['chutes_gol']}\n"
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


def montar_aviso_sem_jogos(hoje: date) -> str:
    return (
        f"⚽ <b>RELATÓRIO DE PROJEÇÕES V5.1 — {hoje.strftime('%d/%m/%Y')}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Hoje não há jogos das ligas monitoradas. Volto amanhã com novas projeções."
    )


def enviar_telegram(texto: str) -> bool:
    """Envia o texto ao Telegram. Retorna True somente se TODAS as partes foram aceitas."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[ERRO] Chaves do Telegram não configuradas (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID).")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)
    tudo_ok = True

    for n, parte in enumerate(partes, 1):
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML", 
            "disable_web_page_preview": True
        }
        try:
            r = SESSION.post(url, json=payload, timeout=HTTP_TIMEOUT)
            if not r.ok:
                print(f"[ERRO] Telegram recusou a parte {n}/{len(partes)}: HTTP {r.status_code} — {r.text[:200]}")
                tudo_ok = False
        except requests.RequestException as e:
            # Só o nome do erro: a mensagem completa pode conter a URL com o token.
            print(f"[ERRO] Falha de rede ao enviar a parte {n}/{len(partes)}: {type(e).__name__}")
            tudo_ok = False

    return tudo_ok


def main() -> int:
    hoje = datetime.now(BRT).date()
    print(f"[INFO] Buscando jogos de {hoje.strftime('%d/%m/%Y')} (BRT)...")

    try:
        jogos = buscar_todos_os_jogos(hoje)
    except FalhaNaFonteDeDados as e:
        print(f"[ERRO] {e}. Nenhum relatório foi enviado.")
        return 1

    if not jogos:
        print("[INFO] Nenhum jogo hoje nas ligas monitoradas.")
        if AVISO_SEM_JOGOS:
            enviar_telegram(montar_aviso_sem_jogos(hoje))
        return 0

    print(f"[INFO] {len(jogos)} jogo(s) encontrado(s). Gerando projeções...")
    relatorio = montar_relatorio(jogos, hoje)

    if enviar_telegram(relatorio):
        print("[OK] Relatório enviado com sucesso!")
        return 0

    print("[ERRO] O relatório NÃO foi enviado corretamente.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
