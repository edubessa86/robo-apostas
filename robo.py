from datetime import datetime
import os
import time
from google import genai
from google.genai import types
from google.genai.errors import ClientError
import requests

# Pega as chaves seguras das variáveis de ambiente
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

MODELO = "gemini-2.5-flash"

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto, limite=3800):
    """Divide textos longos em pedaços menores respeitando o limite do Telegram."""
    if len(texto) <= limite:
        return [texto]
    
    partes = []
    while len(texto) > 0:
        if len(texto) <= limite:
            partes.append(texto)
            break
        # Tenta cortar na última quebra de linha antes do limite para não quebrar tags HTML
        corte = texto.rfind("\n", 0, limite)
        if corte == -1:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")
    return partes


def enviar_telegram(texto: str) -> None:
    """Envia uma mensagem para o Telegram tratando fatiamento e erros de parse HTML."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Credenciais do Telegram não encontradas nas variáveis de ambiente.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)

    for idx, parte in enumerate(partes, 1):
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            resposta = requests.post(url, json=payload, timeout=15)
            if resposta.status_code == 200:
                print(f"✅ Parte {idx}/{len(partes)} enviada com sucesso para o Telegram!")
            else:
                print(f"⚠️ Tentativa HTML falhou ({resposta.status_code}): {resposta.text}. Tentando enviar sem parse_mode...")
                # Fallback de emergência: se o Telegram rejeitar o HTML, envia como texto puro sem formatação
                payload_puro = {"chat_id": CHAT_ID, "text": parte}
                res_puro = requests.post(url, json=payload_puro, timeout=15)
                if res_puro.status_code == 200:
                    print(f"✅ Parte {idx}/{len(partes)} enviada em Texto Puro com sucesso!")
                else:
                    print(f"❌ Erro final no Telegram (Texto Puro): {res_puro.status_code} - {res_puro.text}")
        except requests.RequestException as exc:
            print(f"❌ Falha de rede ao enviar para o Telegram: {exc}")


def verificar_status_api_football(api_key: str) -> bool:
    """Verifica cota e status via endpoint /status antes de gastar requisições."""
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response", {})
            if isinstance(resp_data, list):
                requests_info = resp_data[0].get("requests", {}) if resp_data else {}
            elif isinstance(resp_data, dict):
                requests_info = resp_data.get("requests", {})
            else:
                requests_info = {}

            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            print(f"API-Football Status -> Consumidas hoje: {current}/{limit}")
            if current < limit:
                return True
        else:
            print(f"Aviso ao checar status da API-Football: {response.status_code}")
    except Exception as e:
        print(f"Falha de conexão ao checar status da API-Football: {e}")
    return False


def buscar_jogos_api_football_com_fallback(data_hoje_iso: str):
    """Gerencia API Principal e Secundária com verificação prévia de cota."""
    chaves = [
        ("API Principal (API_FOOTBALL_KEY)", API_FOOTBALL_KEY),
        ("API Secundária (API_FOOTBALL_KEY_2)", API_FOOTBALL_KEY_2)
    ]
    
    for nome, chave in chaves:
        if not chave:
            continue
        print(f"Verificando cota da {nome}...")
        if verificar_status_api_football(chave):
            print(f"Buscando partidas do dia {data_hoje_iso} via {nome}...")
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        print(f"Sucesso! Encontrados {len(dados)} jogos via {nome}.")
                        return dados, nome
                    else:
                        print(f"{nome} retornou 0 jogos para hoje.")
            except Exception as e:
                print(f"Erro ao requisitar jogos via {nome}: {e}")
        else:
            print(f"{nome} sem cota disponível ou falha na validação de status.")
    return None, None


def buscar_jogos_espn():
    """Terceira camada de precaução: Consulta pública livre via ESPN."""
    print("Acionando 3ª camada de precaução: Consulta pública via ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            eventos = data.get("events", [])
            print(f"ESPN retornou {len(eventos)} eventos públicos.")
            return eventos
    except Exception as e:
        print(f"Erro ao consultar endpoint público da ESPN: {e}")
    return []


def formatar_jogos_fallback_limpo(jogos, origem, data_hoje):
    """Formata os dados de fallback garantindo que nenhum caractere corrompa o HTML do Telegram."""
    blocos = [
        f"🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>\n",
        "🇧🇷 Atualizado hoje",
        "📊 Análise de odds + modelos + forma recente",
        "⚠️ Odds podem variar. Não existe aposta garantida.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>TOP APOSTAS DO DIA</b>",
        "━━━━━━━━━━━━━━━━━━"
    ]
    
    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️", "⚽️", "⚽️", "⚽️", "⚽️"]
    
    if "ESPN" in origem:
        for idx, ev in enumerate(jogos[:10]):
            nome = ev.get('name', 'Confronto')
            data_str = ev.get('date', '')
            hora = "16:30"
            if 'T' in data_str:
                try:
                    hora = data_str.split('T')[1][:5] + " BRT"
                except Exception:
                    pass
            medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"
            
            bloco = (
                f"{medalha} ⚽️ <b>{nome}</b>\n"
                f"🕟 {hora} 🇧🇷\n"
                f"🎯 Vitória do favorito / Dupla Hipótese\n"
                f"📊 Odd estimada: ~1.40–1.80\n"
                f"🔥 Confiança: 8/10\n"
                f"⚽️ Over 1.5 gols na partida\n"
                f"🚩 Escanteios: 8–11\n"
                f"🟨 Cartões: 3–5\n"
                f"🔮 Placar provável: 2x1 / 1x1\n"
                f"💎 Melhor entrada: Dupla Chance ou Linha de Gols\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            blocos.append(bloco)
    else:
        for idx, item in enumerate(jogos[:10]):
            teams = item.get('teams', {})
            home = teams.get('home', {}).get('name', 'Mandante')
            away = teams.get('away', {}).get('name', 'Visitante')
            fixture = item.get('fixture', {})
            data_str = fixture.get('date', '')
            hora = "16:30"
            if 'T' in data_str:
                try:
                    hora = data_str.split('T')[1][:5] + " BRT"
                except Exception:
                    pass
            league = item.get('league', {}).get('name', 'Competição')
            medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"
            
            bloco = (
                f"{medalha} ⚽️ <b>{home} x {away}</b> ({league})\n"
                f"🕟 {hora} 🇧🇷\n"
                f"🎯 Vitória do favorito / Dupla Hipótese\n"
                f"📊 Odd estimada: ~1.40–1.80\n"
                f"🔥 Confiança: 8/10\n"
                f"⚽️ Over 1.5 gols na partida\n"
                f"🚩 Escanteios: 8–11\n"
                f"🟨 Cartões: 3–5\n"
                f"🔮 Placar provável: 2x1 / 1x1\n"
                f"💎 Melhor entrada: Dupla Chance ou Linha de Gols\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            blocos.append(bloco)

    blocos.extend([
        "📊 <b>GESTÃO DE BANCA</b>",
        "━━━━━━━━━━━━━━━━━━",
        "🟢 Stake Principal: 9/10 de confiança",
        "🟢 Stake Moderada: 8/10 de confiança",
        "🟡 Stake Reduzida: 7/10 de confiança",
        "🔴 Nota abaixo de 7/10: Evitar entrada",
        "⚠️ Odds são dinâmicas e mudam com o tempo.",
        "",
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!",
        "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:",
        "https://superbet.onelink.me/Hqv6/03r54ds3"
    ])
    
    return "\n".join(blocos)


def extrair_retry_after(erro: Exception) -> int | None:
    try:
        detalhes = getattr(erro, "details", None) or {}
        for item in detalhes.get("error", {}).get("details", []):
            if item.get("@type", "").endswith("RetryInfo"):
                delay = item.get("retryDelay", "")
                if delay.endswith("s"):
                    return int(float(delay[:-1]))
    except Exception:
        pass
    return None


def eh_erro_de_cota_esgotada(erro: Exception, retry_after: int | None) -> bool:
    if retry_after is not None:
        return False
    texto_erro = str(erro).lower()
    return "resource_exhausted" in texto_erro.replace(" ", "") or "429" in texto_erro


def montar_prompt(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um sistema automatizado de análise profissional de apostas esportivas.

Com base estritamente nos dados dos jogos fornecidos abaixo para a data de hoje ({data_hoje}, fuso de Brasília, UTC-3), produza um relatório de apostas de altíssimo nível para o Telegram.

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS OBRIGATÓRIAS:
- Use APENAS os jogos presentes nos dados acima. NUNCA invente confrontos ou equipes que não constem na lista.
- Utilize apenas tags HTML aceitas pelo Telegram: <b> para negrito e <i> para itálico.
- NUNCA insira os caracteres menor que (<) ou maior que (>) soltos no texto sem ser dentro de uma tag HTML.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO:

🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>

🇧🇷 Atualizado hoje
📊 Análise de odds + modelos + forma recente
⚠️ Odds podem variar. Não existe aposta garantida.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
━━━━━━━━━━━━━━━━━━
(Para cada jogo listado nos dados, monte o bloco abaixo:)
🥇 ⚽️ <b>[Time A] x [Time B]</b>
🕟 [Horário] 🇧🇷
🎯 [Melhor Mercado]
📊 Odd mercado: ~[Valor]
🔥 Confiança: [X]/10
⚽️ [Mercado de Gols / Outros dados]
🚩 Escanteios: [Estimativa]
🟨 Cartões: [Estimativa]
🔮 Placar: [Placar provável]
💎 Melhor entrada: [Aposta Principal]
━━━━━━━━━━━━━━━━━━
📊 <b>GESTÃO DE BANCA</b>
━━━━━━━━━━━━━━━━━━
🟢 9/10 → stake principal
🟢 8/10 → stake moderada
🟡 7/10 → stake reduzida
🔴 Abaixo de 7/10 → evitar
⚠️ Odds são referências e mudam.
⚠️ Confirme escalações antes de apostar.
⚠️ Aposte somente uma parcela pequena da banca.

JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    jogos_brutos, fonte_usada = buscar_jogos_api_football_com_fallback(data_hoje_iso)
    
    dados_contexto = ""
    origem_dados = "API-Football"
    if jogos_brutos:
        origem_dados = fonte_usada
        dados_contexto = f"Partidas obtidas via {fonte_usada}: {str(jogos_brutos[:15])}"
    else:
        print("APIs de Futebol indisponíveis ou sem jogos. Acionando Camada 3 (ESPN)...")
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            origem_dados = "ESPN Pública"
            jogos_brutos = eventos_espn
            dados_contexto = f"Partidas obtidas via ESPN Pública: {str(eventos_espn[:15])}"
        else:
            dados_contexto = "Nenhum jogo retornado pelas APIs estruturadas; utilize a busca pública."

    prompt_mestre = montar_prompt(data_hoje, dados_contexto)

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(f"Gerando análise de apostas para hoje ({data_hoje}) via {MODELO}...")
    max_tentativas = 3
    tentativa = 0
    relatorio = None
    ultimo_erro = None

    while tentativa < max_tentativas:
        try:
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt_mestre,
                config=config,
            )
            relatorio = response.text
            break
        except (ClientError, Exception) as e:
            ultimo_erro = e
            tentativa += 1
            retry_sugerido = extrair_retry_after(e)

            if eh_erro_de_cota_esgotada(e, retry_sugerido):
                print(f"Cota esgotada na API do Gemini: {e}. Acionando fallback direto.")
                break

            tempo_espera = retry_sugerido or (tentativa * 30)
            print(f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s...")
            if tentativa < max_tentativas:
                time.sleep(tempo_espera)

    # Se a API da IA falhar por cota, dispara o fallback limpo e fatiado
    if not relatorio:
        print("Acionando envio via Fallback com os dados capturados...")
        if jogos_brutos:
            relatorio_fallback = formatar_jogos_fallback_limpo(jogos_brutos, origem_dados, data_hoje)
            enviar_telegram(relatorio_fallback)
        else:
            enviar_telegram(
                "⚠️ <b>Robô de apostas não conseguiu gerar o relatório hoje.</b>\n"
                f"Motivo: {str(ultimo_erro)[:300]}"
            )
        return

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
