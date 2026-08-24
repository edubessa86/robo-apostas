import os
import requests

# Pega as chaves de segurança do GitHub
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def enviar_relatorio():
  relatorio = """⚽ **ANÁLISE DE APOSTAS — ROBÔ ATIVO** ⚽

🔥 **Status:** Rodando automaticamente pela nuvem do GitHub!
🟢 O esqueleto do sistema está pronto e operando na nuvem.
"""

  url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": relatorio, "parse_mode": "Markdown"}
  resposta = requests.post(url, json=payload)

  if resposta.status_code == 200:
    print("Relatório automático enviado com sucesso!")
  else:
    print("Erro ao enviar relatório.")


if __name__ == "__main__":
  enviar_relatorio()
