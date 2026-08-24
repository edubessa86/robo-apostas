import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def enviar_relatorio():
  relatorio = """⚽ PAINEL DIÁRIO DE APOSTAS — ANÁLISE DO DIA ⚽

🔥 Status do Sistema: 100% Operacional (Nuvem GitHub)
📅 Frequência: Execução Automática Diária

📊 Resumo de Oportunidades:
• Jogos Analisados: (Aguardando base de dados)
• Mercados de Valor: (Aguardando IA)
• Gestão de Banca: Mantenha sempre a disciplina e o foco na estratégia!

🤖 Este é um relatório gerado automaticamente pelo seu robô inteligente. Em breve, traremos palpites detalhados aqui!"""

  url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
  # Enviando como texto simples para evitar qualquer bloqueio de formatação
  payload = {"chat_id": CHAT_ID, "text": relatorio}

  resposta = requests.post(url, json=payload)

  if resposta.status_code == 200:
    print("Relatório diário enviado com sucesso!")
  else:
    print(f"Erro ao enviar: {resposta.status_code} - {resposta.text}")


if __name__ == "__main__":
  enviar_relatorio()
