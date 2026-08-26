from datetime import datetime
import os
from google import genai
from google.genai import types
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def executar_robo_apostas():
  # Pega a data atual do sistema de forma dinâmica
  data_hoje = datetime.now().strftime("%d/%m/%Y")

  prompt_mestre = f"""
    Você é um sistema automatizado de análise profissional de apostas esportivas.
    Pesquise obrigatoriamente na internet os jogos de futebol reais que acontecem HOJE ({data_hoje}).
    Com base estritamente nos jogos reais encontrados na web para hoje, selecione as melhores oportunidades de acordo com PROBABILIDADE, ODDS, VALOR ESPERADO E RISCO.
    
    Gere um relatório compacto e objetivo para o Telegram seguindo esta estrutura resumida:
    1. ⚽ ANÁLISE DE APOSTAS DO DIA (Data: {data_hoje} | Fuso Horário: UTC-3).
    2. 🏆 TOP 5 MELHORES APOSTAS (Com Jogos REAIS de hoje, Mercado, Probabilidade, Odd, Valor e Risco).
    3. 🔒 TOP 3 CONSERVADORAS.
    4. 🚨 JOGOS PARA EVITAR E MOTIVO.
    5. ⚠️ AVISO DE GESTÃO DE BANCA.
    
    Logo abaixo das seções de apostas (antes do aviso final ou no rodapé), inclua obrigatoriamente e exatamente este bloco de convite promocional:

    JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
    Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
    https://superbet.onelink.me/Hqv6/03r54ds3
    
    Atenção: Utilize apenas partidas que realmente façam parte da agenda de jogos de hoje na internet. Nunca invente confrontos ou traga dados desatualizados.
    """

  print(f"Buscando jogos reais na web para a data: {data_hoje}...")

  # Ativa a ferramenta de busca do Google via SDK oficial
  response = client.models.generate_content(
      model="gemini-3.6-flash",
      contents=prompt_mestre,
      config=types.GenerateContentConfig(tools=[{"google_search": {}}]),
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
