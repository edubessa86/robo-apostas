import os
import requests

# Pega as chaves seguras do GitHub Secrets
TOKEN = os.environ.get("8908004567:AAFebWxT1AkL-jTlW2_EtDl1Z06tPYBr7qg
")
CHAT_ID = os.environ.get("1784568398")


def enviar_relatorio():
  # Estrutura visual robusta para o seu relatório diário
  relatorio = """⚽ **PAINEL DIÁRIO DE APOSTAS — ANÁLISE DO DIA** ⚽

🔥 **Status do Sistema:** 100% Operacional (Nuvem GitHub)
📅 **Frequência:** Execução Automática Diária

📊 **Resumo de Oportunidades:**
• 🟢 *Jogos Analisados:* (Aguardando base de dados)
• 🎯 *Mercados de Valor:* (Aguardando IA)
• ⚠️ *Gestão de Banca:* Mantenha sempre a disciplina e o foco na estratégia!

🤖 *Este é um relatório gerado automaticamente pelo seu robô inteligente. Em breve, traremos palpites detalhados aqui!*
"""

  url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": relatorio, "parse_mode": "Markdown"}

  resposta = requests.post(url, json=payload)

  if resposta.status_code == 200:
    print("Relatório diário robusto enviado com sucesso!")
  else:
    print(f"Erro ao enviar: {resposta.status_code} - {resposta.text}")


if __name__ == "__main__":
  enviar_relatorio()
