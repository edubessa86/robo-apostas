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
  prompt_mestre = """
    ROBÔ DE ANÁLISE DE APOSTAS ESPORTIVAS
    Você é um sistema automatizado de análise profissional de apostas esportivas.
    Sua função é analisar os eventos esportivos disponíveis para hoje e entregar as melhores oportunidades de acordo com PROBABILIDADE, ODDS, VALOR ESPERADO E RISCO, seguindo estritamente uma postura analítica e sem inventar dados.
    
    Gere um relatório compacto e objetivo para o Telegram seguindo esta estrutura resumida:
    1. ⚽ ANÁLISE DE APOSTAS DO DIA (Com data e fuso horário UTC-3 atualizados).
    2. 🏆 TOP 5 MELHORES APOSTAS (Com Jogo, Mercado, Probabilidade, Odd, Valor e Risco).
    3. 🔒 TOP 3 CONSERVADORAS.
    4. 🚨 JOGOS PARA EVITAR E MOTIVO.
    5. ⚠️ AVISO DE GESTÃO DE BANCA.
    
    Seja direto, profissional e focado em qualidade.
    """

  print("Gerando análise inteligente com o Gemini...")
  # Atualizado para o modelo exigido pela API atual do Google
  response = client.models.generate_content(
      model="gemini-3.6-flash", contents=prompt_mestre
  )
  relatorio = response.text

  # Envia o resultado gerado pela IA para o Telegram
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": relatorio, "parse_mode": "Markdown"}

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
