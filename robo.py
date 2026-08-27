from datetime import datetime
import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

def dividir_mensagem(texto, limite=4000):
    """Divide textos longos em pedaços menores para respeitar o limite de caracteres do Telegram."""
    return [texto[i:i+limite] for i in range(0, len(texto), limite)]

def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    prompt_mestre = f"""
ROBÔ DE ANÁLISE DE APOSTAS ESPORTIVAS — DISPARO DIÁRIO
Você é um sistema automatizado de análise profissional de apostas esportivas e especialista em probabilidade matemática. Sua função é analisar diariamente os eventos esportivos disponíveis e entregar as melhores oportunidades de acordo com PROBABILIDADE, ODDS, VALOR ESPERADO E RISCO.

1. ESCOPO TEMPORAL E BUSCA
- Data atual: {data_hoje}
- Fuso horário: Brasília (UTC-3)
- Horário de execução diária: A partir das 10h da manhã.
- ATENÇÃO OBRIGATÓRIA: Utilize a ferramenta de busca integrada para pesquisar na web quais são os principais jogos de futebol REAIS que acontecem HOJE ({data_hoje}) a partir das 10h. 
- Analise estritamente partidas que ainda NÃO começaram (pré-jogo). Nunca recomende apostas em partidas ao vivo ou encerradas. NUNCA invente confrontos, times, campeonatos ou dados estatísticos.

2. RIGOR DE DADOS E SUPERBET
- Utilize fontes confiáveis na web para calendário, horários, classificação e escalações prováveis.
- Priorize cotações e mercados da **Superbet** (vitória, empate, dupla chance, gols, handicaps leves, etc.). Se a odd exata não puder ser verificada, indique claramente.

3. ESTRUTURA OBRIGATÓRIA DO RELATÓRIO PARA O TELEGRAM (HTML)
Utilize tags HTML limpas do Telegram (`<b>`, `<i>`) seguindo estritamente esta estrutura:

⚽ <b>RELATÓRIO DIÁRIO DE APOSTAS — {data_hoje}</b>
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP JOGOS DO DIA (A partir das 10h)</b>
(Para os principais jogos reais encontrados para hoje, liste de forma objetiva:)
• <b>[Time A] x [Time B]</b> ([Competição])
- Entrada 1: [Mercado] (Odd: X.XX | Prob: ~80%+)
- Entrada 2: [Mercado] (Odd: X.XX | Prob: ~80%+)

━━━━━━━━━━━━━━━━━━
📊 <b>DESTAQUES E PROJEÇÕES</b>
- Resumo analítico e estatístico dos confrontos do dia.

━━━━━━━━━━━━━━━━━━
⚠️ <b>GESTÃO DE BANCA & AVISO LEGAL</b>
Mantenha rigor na gestão de banca e controle de stakes. Nenhuma aposta é 100% garantida. Aposte com responsabilidade.

Logo abaixo, inclua obrigatoriamente este bloco promocional:
JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""

    print(f"Buscando jogos reais na web (focado no dia {data_hoje} a partir das 10h) com o modelo gemini-3.6-flash...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None

    # Loop robusto com tratamento de erros e ativação correta da ferramenta de busca
    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt_mestre,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            tentativa += 1
            tempo_espera = tentativa * 30  
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            time.sleep(tempo_espera)

    if not relatorio:
        print("Erro crítico: Não foi possível obter resposta da API após as tentativas.")
        return

    # Envia o resultado para o Telegram dividindo caso ultrapasse o limite de caracteres
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(relatorio)

    for parte in partes:
        payload = {
            "chat_id": CHAT_ID,
            "text": parte,
            "parse_mode": "HTML"
        }
        resposta_telegram = requests.post(url, json=payload)
        if resposta_telegram.status_code == 200:
            print("Relatório analítico enviado com sucesso para o Telegram!")
        else:
            print(f"Erro ao enviar para o Telegram: {resposta_telegram.status_code} - {resposta_telegram.text}")

if __name__ == "__main__":
    executar_robo_apostas()
