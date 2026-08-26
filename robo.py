from datetime import datetime
import os
import time
from google import genai
from google.genai.errors import ClientError
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")

    prompt_mestre = f"""
Você é um sistema automatizado de análise profissional de apostas esportivas e especialista em probabilidade matemática.
Com base nos principais jogos de futebol reais que acontecem HOJE ({data_hoje}).

Para cada um dos 10 jogos principais do dia, selecione rigorosamente 3 mercados/odds diferentes que possuam uma probabilidade estatística de acerto próxima ou superior a 80% (focado em linhas conservadoras, duplas hipóteses, gols seguros ou handicaps leves).

Gere um relatório compacto, direto e focado exclusivamente para disparo no Telegram, seguindo estritamente esta estrutura:

1. ⚽ TOP 10 JOGOS DO DIA (Data: {data_hoje} | Fuso: UTC-3)
(Para cada um dos 10 jogos, liste de forma objetiva:)
• Jogo [X]: [Time A] x [Time B] ([Competição])
  - Entrada 1: [Mercado] (Odd: X.XX | Prob: ~80%)
  - Entrada 2: [Mercado] (Odd: X.XX | Prob: ~80%)
  - Entrada 3: [Mercado] (Odd: X.XX | Prob: ~80%)

2. ⚠️ GESTÃO DE BANCA
(Instrução rápida de 1 linha sobre controle de risco e stakes).

Logo abaixo das análises, inclua obrigatoriamente este bloco promocional:

JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3

Atenção: Utilize apenas partidas reais da agenda de hoje. Nunca invente confrontos, times ou dados estatísticos.
"""

    print(f"Gerando análise analítica para a data: {data_hoje}...")

    max_tentativas = 3
    tentativa = 0
    relatorio = None

    # Loop robusto com tratamento de erros de cota e conexão
    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt_mestre,
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            tentativa += 1
            tempo_espera = tentativa * 30  # Espera progressiva maior (30s, 60s)
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            time.sleep(tempo_espera)

    if not relatorio:
        print("Erro crítico: Não foi possível obter resposta da API após as tentativas.")
        return

    # Envia o resultado para o Telegram
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": relatorio,
    }

    resposta_telegram = requests.post(url, json=payload)

    if resposta_telegram.status_code == 200:
        print("Relatório analítico da IA enviado com sucesso para o Telegram!")
    else:
        print(
            f"Erro ao enviar para o Telegram: {resposta_telegram.status_code} - {resposta_telegram.text}"
        )


if __name__ == "__main__":
    executar_robo_apostas()
