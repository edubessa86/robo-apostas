import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEFAULT_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def enviar_mensagem(chat_id, texto):
  url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
  payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
  requests.post(url, json=payload)


def verificar_mensagens():
  # Puxa as mensagens recentes enviadas para o bot
  url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
  resposta = requests.get(url)
  if resposta.status_code == 200:
    dados = resposta.json()
    resultados = dados.get("result", [])
    if resultados:
      # Pega a última mensagem enviada no chat
      ultima_msg = resultados[-1]
      if "message" in ultima_msg:
        chat_id = ultima_msg["message"]["chat"]["id"]
        texto_msg = ultima_msg["message"].get("text", "").strip()
        return chat_id, texto_msg
  return None, None


def processar_comando(comando, chat_id):
  if comando == "/start":
    resposta = (
        "🤖 *Olá, Eduardo! Sou seu robô de apostas.*\n\nComandos"
        " disponíveis:\n• /hoje - Ver análise geral do dia\n• /top5 - Ver as 5"
        " melhores apostas\n• /conservadoras - Ver apostas de baixo risco"
    )
  elif comando == "/hoje":
    resposta = (
        "⚽ *Análise de Hoje*\n\nNenhum jogo carregado no sistema ainda. Em"
        " breve conectaremos a base de dados!"
    )
  elif comando == "/top5":
    resposta = (
        "🏆 *Top 5 Apostas do Dia*\n\n1. Jogo X — Mercado A (Aguardando"
        " dados...)"
    )
  elif comando == "/conservadoras":
    resposta = "🟢 *Apostas Conservadoras*\n\nLista vazia no momento."
  else:
    resposta = (
        "Desculpe, não reconheci esse comando. Digite /start para ver a ajuda."
    )

  enviar_mensagem(chat_id, resposta)


if __name__ == "__main__":
  # Verifica se há alguma mensagem nova no Telegram
  chat_id_msg, texto_msg = verificar_mensagens()

  if chat_id_msg and texto_msg and texto_msg.startswith("/"):
    print(f"Comando detectado: {texto_msg}")
    processar_comando(texto_msg, chat_id_msg)
  else:
    print("Enviando relatório padrão diário...")
    relatorio = (
        "⚽ *ANÁLISE DE APOSTAS — RELATÓRIO DIÁRIO* ⚽\n\n🔥 *Status:* Rodando"
        " automaticamente na nuvem!\nO robô está ativo e pronto para"
        " responder aos comandos como /start, /hoje e /top5."
    )
    if DEFAULT_CHAT_ID:
      enviar_mensagem(DEFAULT_CHAT_ID, relatorio)
