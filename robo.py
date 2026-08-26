from datetime import datetime
import os
from google import genai
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def executar_robo_apostas():
  # Pega a data atual do sistema de forma dinâmica (26/08/2026)
  data_hoje = datetime.now().strftime("%d/%m/%Y")

  prompt_mestre = f"""
    Você é um sistema automatizado de análise profissional de apostas esportivas.
    Considere a data atual: {data_hoje}. 
    Gere um relatório compacto, profissional e objetivo para o Telegram com análises estatísticas, tendências de mercado, probabilidades, odds e gestão de risco para os jogos do calendário atual de {data_hoje}.
    
    Siga estritamente esta estrutura resumida:
    1. ⚽ ANÁLISE DE APOSTAS DO DIA (Data: {data_hoje} | Fuso Horário: UTC-3).
    2. 🏆 TOP 5 MELHORES APOSTAS (Com Jogo, Mercado, Probabilidade, Odd, Valor e Risco).
    3. 🔒 TOP 3 CONSERVADORAS.
    4. 🚨 JOGOS PARA EVITAR E MOTIVO.
    5. ⚠️ AVISO DE GESTÃO DE BANCA.
    6. 🔒 indicar o link com os jogos através da casa de apostas SuperBET.
    
    Seja direto, focado em qualidade estatística e mantenha o alinhamento com a data de hoje.
    """

  print(f"Gerando análise inteligente para a data: {data_hoje}...")

  # Chamada limpa e direta para evitar estouro de cota (429)
  response = client.models.generate_content(
      model="gemini-3.6-flash", contents=prompt_mestre
  )
  relatorio = response.text

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
        f"Erro ao enviar para o Telegram: {resposta_telegram.status_code} -"
        f" {resposta_telegram.text}"
    )


if __name__ == "__main__":
  executar_robo_apostas()
