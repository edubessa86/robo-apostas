import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def enviar_relatorio():
  relatorio = "⚽ Teste de diagnóstico do robô de apostas!"

  url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": relatorio}

  resposta = requests.post(url, json=payload)

  # Mostra a resposta exata do Telegram nos logs do GitHub
  print("Status HTTP:", resposta.status_code)
  print("Resposta do Telegram:", resposta.text)

  dados = resposta.json()
  if dados.get("ok"):
    print("🚀 Mensagem enviada com sucesso de verdade!")
  else:
    print("❌ O Telegram recusou a mensagem por este motivo:")
    print(dados.get("description"))


if __name__ == "__main__":
  enviar_relatorio()
