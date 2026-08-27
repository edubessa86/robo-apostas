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

# AJUSTE: se seguir tomando 429 mesmo fora do horário de pico, considere trocar
# para um modelo com cota de grounding diferente (ex: "gemini-2.5-flash") só
# para testar se o problema é específico do 3.6-flash na sua conta.
MODELO = "gemini-3.6-flash"

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto, limite=4000):
    """Divide textos longos em pedaços menores para respeitar o limite de caracteres do Telegram."""
    return [texto[i:i + limite] for i in range(0, len(texto), limite)]


def enviar_telegram(texto: str) -> None:
    """Envia uma mensagem (dividida se necessário) para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for parte in dividir_mensagem(texto):
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            resposta = requests.post(url, json=payload, timeout=15)
            if resposta.status_code == 200:
                print("Mensagem enviada com sucesso para o Telegram!")
            else:
                print(f"Erro ao enviar para o Telegram: {resposta.status_code} - {resposta.text}")
        except requests.RequestException as exc:
            print(f"Falha de rede ao enviar para o Telegram: {exc}")


def extrair_retry_after(erro: Exception) -> int | None:
    """Tenta extrair o tempo de espera sugerido pela própria API (quando presente
    no corpo do erro 429), em vez de usar um backoff fixo às cegas.
    """
    try:
        detalhes = getattr(erro, "details", None) or {}
        for item in detalhes.get("error", {}).get("details", []):
            if item.get("@type", "").endswith("RetryInfo"):
                delay = item.get("retryDelay", "")  # ex: "30s"
                if delay.endswith("s"):
                    return int(float(delay[:-1]))
    except Exception:
        pass
    return None


def eh_erro_de_cota_diaria(erro: Exception) -> bool:
    """Heurística simples: mensagens de cota diária/grounding costumam mencionar
    'PerDay' ou 'per day' no corpo do erro, diferente de cota por minuto
    ('PerMinute'). Cota diária esgotada não se resolve com retry curto.
    """
    texto_erro = str(erro).lower()
    return "perday" in texto_erro.replace(" ", "") or "daily" in texto_erro


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

    print(f"Buscando jogos reais na web (focado no dia {data_hoje} a partir das 10h) com o modelo {MODELO}...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None
    ultimo_erro = None

    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            ultimo_erro = e
            tentativa += 1

            # Cota diária esgotada: retry não resolve, sai do loop imediatamente
            # em vez de queimar as 3 tentativas e vários minutos de espera à toa.
            if eh_erro_de_cota_diaria(e):
                print(
                    f"Cota DIÁRIA de grounding/API provavelmente esgotada: {e}. "
                    "Retry não vai ajudar hoje — abortando tentativas."
                )
                break

            # Usa o retry-after sugerido pela própria API quando disponível;
            # senão, cai no backoff progressivo (mais generoso que antes).
            tempo_espera = extrair_retry_after(e) or (tentativa * 45)
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            if tentativa < max_tentativas:
                time.sleep(tempo_espera)

    if not relatorio:
        print("Erro crítico: Não foi possível obter resposta da API após as tentativas.")
        # Antes o script simplesmente parava aqui sem avisar ninguém.
        # Agora manda um aviso curto pro Telegram para você saber que o robô
        # não rodou hoje, em vez de descobrir só olhando o log do GitHub Actions.
        enviar_telegram(
            "⚠️ <b>Robô de apostas não conseguiu gerar o relatório hoje.</b>\n"
            f"Motivo: {str(ultimo_erro)[:300]}\n"
            "Provável causa: cota gratuita da API do Gemini esgotada "
            "(especialmente a cota de busca/grounding, que é bem menor que a "
            "cota normal de tokens no tier free)."
        )
        return

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
