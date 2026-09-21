import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

# Configurações de Fuso Horário e Ambiente
BRT = timezone(timedelta(hours=-3))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")[cite: 1]
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")[cite: 1]

def remover_margem_proporcional(odds_1x2: Dict[str, float]) -> Optional[Dict[str, float]]:
    """Remove a margem (vig) das odds da casa sharp para encontrar a probabilidade justa."""
    if not odds_1x2 or any(v <= 1.0 for v in odds_1x2.values()):
        return None
    
    implied_probs = {k: 1.0 / v for k, v in odds_1x2.items()}
    overround = sum(implied_probs.values())
    
    if overround <= 1.0:
        return None  # Anomalia de mercado
        
    return {k: p / overround for k, p in implied_probs.items()}

def analisar_oportunidades_pre_jogo(jogos_do_dia: List[Dict]) -> List[Dict]:
    """Processa apenas partidas pré-jogo a partir das 10h com ancoragem na casa sharp."""
    oportunidades = []
    agora_brt = datetime.now(BRT)

    for jogo in jogos_do_dia:
        horario_jogo = datetime.fromisoformat(jogo["start_time_iso"]).astimezone(BRT)
        
        # Filtro estrito: Apenas partidas que ainda NÃO começaram no dia corrente[cite: 1, 3]
        if horario_jogo < agora_brt or horario_jogo.date() != agora_brt.date():
            continue

        # Odds da Casa Commercial (ex: Superbet) e Sharp (Pinnacle)[cite: 1, 2]
        odds_superbet = jogo.get("odds_superbet", {})  # ex: {"Home": 2.25, "Draw": 3.40, "Away": 3.20}[cite: 1, 2]
        odds_sharp = jogo.get("odds_sharp", {})        # ex: {"Home": 2.10, "Draw": 3.40, "Away": 3.50}

        fair_probs_sharp = remover_margem_proporcional(odds_sharp)
        if not fair_probs_sharp:
            continue

        # Avalia se a Superbet oferece Odd maior que a Odd Fair da Sharp para o Mandante[cite: 1, 2]
        selection = "Home"
        odd_comercial = odds_superbet.get(selection, 0.0)[cite: 1]
        fair_prob = fair_probs_sharp.get(selection, 0.0)
        
        if fair_prob > 0 and odd_comercial > 1.0:
            fair_odd_sharp = 1.0 / fair_prob
            edge_percent = ((odd_comercial / fair_odd_sharp) - 1.0) * 100.0

            # Exige um Edge mínimo de +3.0% em relação ao preço justo da Sharp
            if edge_percent >= 3.0:
                oportunidades.append({
                    "home_team": jogo["home_team"],
                    "away_team": jogo["away_team"],
                    "league": jogo["league"],
                    "horario": horario_jogo.strftime("%H:%M"),
                    "selection": "Vitória Mandante",
                    "odd_comercial": odd_comercial,
                    "fair_odd_sharp": round(fair_odd_sharp, 2),
                    "edge_percent": round(edge_percent, 2),
                    "ev_percent": round((fair_prob * odd_comercial - 1.0) * 100, 2)
                })

    return oportunidades

def formatar_relatorio_10h(oportunidades: List[Dict]) -> str:
    data_hoje = datetime.now(BRT).strftime("%d/%m/%Y")[cite: 1]
    
    linhas = [
        f"⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS PRÉ-JOGO — {data_hoje}</b>",[cite: 1, 2]
        f"<i>Disparo automático das 10:00 BRT (Ancoragem Sharp)</i>\n",[cite: 1]
        "━━━━━━━━━━━━━━━━━━"
    ]

    if not oportunidades:
        linhas.append("⚪ <b>STATUS: PASS</b>\nNenhuma oportunidade atingiu o critério de Edge mínimo em relação à casa Sharp hoje.")[cite: 1, 2]
    else:
        for op in oportunidades:
            linhas.append(
                f"🏆 <b>{op['home_team']} x {op['away_team']}</b> ({op['league']})\n"[cite: 1, 2]
                f"⏰ Horário: {op['horario']} BRT\n"[cite: 1]
                f"🎯 Entrada: <b>{op['selection']}</b>\n"[cite: 1]
                f"🏦 Odd Superbet: <b>{op['odd_comercial']}</b> | Fair Odd Sharp: <b>{op['fair_odd_sharp']}</b>\n"[cite: 1, 2]
                f"💎 Edge de Preço: <b>+{op['edge_percent']}%</b> | EV: <b>+{op['ev_percent']}%</b>\n"[cite: 2]
                "━━━━━━━━━━━━━━━━━━"
            )

    linhas.append(
        "⚠️ <b>GESTÃO DE BANCA:</b> Aposte com responsabilidade usando no máximo 1% a 2% por entrada.\n\n"[cite: 1, 2]
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!\n"[cite: 1]
        "https://superbet.onelink.me/Hqv6/03r54ds3"[cite: 1]
    )
    return "\n".join(linhas)

def enviar_telegram(texto: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:[cite: 1]
        print("Tokens do Telegram não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"[cite: 1]
    payload = {"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}[cite: 1, 2]
    requests.post(url, json=payload, timeout=15)[cite: 1]

if __name__ == "__main__":
    # Exemplo de entrada de dados pré-jogo das 10h[cite: 1]
    jogos_exemplo = [
        {
            "home_team": "Flamengo", "away_team": "Palmeiras", "league": "Brasileirão",[cite: 1]
            "start_time_iso": datetime.now(BRT).replace(hour=16, minute=0).isoformat(),
            "odds_superbet": {"Home": 2.25, "Draw": 3.30, "Away": 3.40},[cite: 1]
            "odds_sharp": {"Home": 2.10, "Draw": 3.30, "Away": 3.60}
        }
    ]

    ops = analisar_oportunidades_pre_jogo(jogos_exemplo)
    relatorio = formatar_relatorio_10h(ops)
    enviar_telegram(relatorio)[cite: 1]
