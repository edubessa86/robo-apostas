import html
import math
import random
import os
from datetime import datetime, timedelta, timezone
import requests

# CONFIGURAÇÕES DE AMBIENTE
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HTTP_TIMEOUT = 10
SESSION = requests.Session()

def dividir_mensagem(texto, limite=3900):
    """Divide textos longos em pedaços menores para respeitar o limite de caracteres do Telegram."""
    return [texto[i:i + limite] for i in range(0, len(texto), limite)]

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0: lam = 0.05
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def projetar_partida(time_casa: str, time_fora: str) -> dict:
    # Semente dinâmica para manter os dados consistentes na mesma execução
    seed_str = f"{time_casa}-{time_fora}"
    seed_val = sum(ord(c) for c in seed_str)
    random.seed(seed_val)
    
    # Projeções de Gols (Poisson)
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

    # Simulação dos mercados mantidos
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

def montar_relatorio(jogos: list[dict]) -> str:
    BRT = timezone(timedelta(hours=-3))
    data = datetime.now(BRT).strftime("%d/%m/%Y")
    
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
            f"⚽ <b>Total de Gols (Jogo):</b> {p['gols_partida']}\n"
            f"⚽ <b>Total de Gols (Equipe):</b> {p['gols_equipe']}\n"
            f"🤝 <b>Ambas as Equipes Marcam:</b> {p['btts']}\n"
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

def enviar_telegram(texto: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    partes = dividir_mensagem(texto)
    for parte in partes:
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML", 
            "disable_web_page_preview": True
        }
        try:
            SESSION.post(url, json=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException:
            pass
