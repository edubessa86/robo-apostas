# app.py
from fastapi import FastAPI, BackgroundTasks
from datetime import datetime
import os
import requests
from google import genai

from arbitrage_engine import calcular_surebet_1x2
from value_engine import calcular_value_bet
from movement_engine import analisar_movimento_odd

app = FastAPI(title="Robô de Apostas V7 Engine")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")[cite: 1]
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")[cite: 1]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")[cite: 1]
MODELO = "gemini-2.5-flash"[cite: 1, 4]

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None[cite: 4]

def enviar_telegram(texto: str) -> None:[cite: 4]
    if not TELEGRAM_TOKEN or not CHAT_ID:[cite: 4]
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"[cite: 1, 4]
    payload = {"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}[cite: 4]
    try:
        requests.post(url, json=payload, timeout=15)[cite: 4]
    except Exception as e:
        print(f"Erro no envio Telegram: {e}")[cite: 4]

def consultar_gemini_interpretacao(dados_jogo: dict, oportunidades: list) -> str:
    """O Gemini interpreta a matemática existente e elabora uma explicação de apoio."""[cite: 1]
    if not client:
        return "Análise tática indisponível no momento."

    prompt = f"""
    Você é um analista quantitativo de futebol.
    Analise a partida {dados_jogo['home_name']} x {dados_jogo['away_name']} aos {dados_jogo['elapsed']}' minutos.
    Placar: {dados_jogo['home_goals']} x {dados_jogo['away_goals']}.
    Estatísticas reais:
    - Finalizações no alvo: Mandante {dados_jogo['home_sot']} | Visitante {dados_jogo['away_sot']}
    - Posse de bola: Mandante {dados_jogo['home_possession']}% | Visitante {dados_jogo['away_possession']}%

    Oportunidades Matemáticas Detectadas:
    {oportunidades}

    Forneça uma breve explicação técnica (máximo 3 frases) em HTML (`<b>`, `<i>`) justificando o valor tático/estatístico dessas oportunidades.
    NÃO invente odds ou probabilidades. Utilize estritamente os dados informados.
    """
    try:
        response = client.models.generate_content(model=MODELO, contents=prompt)[cite: 4]
        return response.text
    except Exception as e:
        return f"<i>Análise qualitativa indisponível ({e}).</i>"

def formatar_alerta_v7(dados_jogo: dict, oportunidades: list, analise_gemini: str) -> str:
    linhas = [
        f"🚨 <b>OPORTUNIDADE QUANTITATIVA DETECTADA</b>",
        f"⚽ <b>{dados_jogo['home_name']} {dados_jogo['home_goals']} x {dados_jogo['away_goals']} {dados_jogo['away_name']}</b> ({dados_jogo['elapsed']}')",
        f"━━━━━━━━━━━━━━━━━━"
    ]

    for op in oportunidades:
        if op["type"] == "SUREBET":
            linhas.append(
                f"🟢 <b>SUREBET DETECTADA (ROI: +{op['roi_percent']}%)</b>\n"
                f"🏦 Distribuição R$100:\n"
                f"  • Mandante @ {op['stakes']['Home']['odd']} -> R$ {op['stakes']['Home']['stake']}\n"
                f"  • Empate @ {op['stakes']['Draw']['odd']} -> R$ {op['stakes']['Draw']['stake']}\n"
                f"  • Visitante @ {op['stakes']['Away']['odd']} -> R$ {op['stakes']['Away']['stake']}\n"
                f"💰 Lucro garantido: R$ {op['lucro_estimado']}"
            )
        elif op["type"] == "VALUE_BET":
            linhas.append(
                f"💎 <b>VALUE BET (+EV: +{op['ev_percent']}%)</b>\n"
                f"📊 Prob. Modelo: <b>{op['prob_modelo_percent']}%</b> | Implícita: <b>{op['prob_implicita_percent']}%</b>\n"
                f"📈 Odd Atual: <b>{op['odd_atual']}</b> | Odd Justa: <b>{op['odd_justa']}</b>"
            )
        elif op["type"] == "ODD_DROPPING":
            linhas.append(
                f"📉 <b>MOVIMENTO DE ODD</b>\n"
                f"⚠️ {op['alerta']} ({op['odd_inicial']} ➡️ {op['odd_atual']})"
            )
        linhas.append("━━━━━━━━━━━━━━━━━━")

    linhas.append(f"🧠 <b>Análise do Modelo:</b>\n{analise_gemini}")
    return "\n".join(linhas)

def executar_pipeline_v7():
    """Pipeline principal acionada pelo servidor."""
    # Exemplo de payload processado vindo da data_engine e odds_engine
    jogo_mock = {
        "home_name": "Flamengo", "away_name": "Palmeiras",
        "home_goals": 0, "away_goals": 0, "elapsed": 35,
        "home_sot": 5, "away_sot": 1,
        "home_possession": 62, "away_possession": 38
    }

    # 1. Checagem de Surebet entre 3 casas
    odd_home_casaA = 2.20
    odd_draw_casaB = 3.60
    odd_away_casaC = 4.10
    
    surebet = calcular_surebet_1x2(odd_home_casaA, odd_draw_casaB, odd_away_casaC)

    # 2. Checagem de Value Bet (Poisson calculou 54% para vitória do mandante)[cite: 1]
    prob_modelo_home = 0.54
    value_bet = calcular_value_bet(prob_modelo_home, odd_home_casaA)

    # 3. Checagem de Movimento de Odds (A odd do Flamengo caiu de 2.40 para 2.20)
    movimento = analisar_movimento_odd(2.40, 2.20)

    oportunidades = [op for op in [surebet, value_bet, movimento] if op is not None]

    if oportunidades:
        analise_gemini = consultar_gemini_interpretacao(jogo_mock, oportunidades)
        mensagem = formatar_alerta_v7(jogo_mock, oportunidades, analise_gemini)
        enviar_telegram(mensagem)[cite: 4]

@app.get("/rodar-robo")
@app.post("/rodar-robo")
def rodar_robo_endpoint(background_tasks: BackgroundTasks):[cite: 4]
    background_tasks.add_task(executar_pipeline_v7)[cite: 4]
    return {
        "status": "sucesso",
        "mensagem": "Pipeline quantitativa V7 iniciada em segundo plano.",
        "timestamp": datetime.now().isoformat()
    }[cite: 4]
