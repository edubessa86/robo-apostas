Aqui está o código completo do `robo.py` corrigido para resolver a repetição de dados.

A função de fallback agora **lê apenas os dados reais de cada partida** (Nome, Horário convertido para Brasília e Competição) e remove as estatísticas estáticas duplicadas.

```python
from datetime import datetime, timedelta
import os
import time
import requests
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

MODELO = "gemini-2.5-flash"

# Inicializa o cliente oficial moderno do Gemini
client = genai.Client(api_key=GEMINI_API_KEY)


def dividir_mensagem(texto, limite=4000):
    """Divide textos longos em pedaços menores para respeitar o limite do Telegram."""
    return [texto[i : i + limite] for i in range(0, len(texto), limite)]


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
                print(
                    f"Erro ao enviar para o Telegram: {resposta.status_code} - {resposta.text}"
                )
        except requests.RequestException as exc:
            print(f"Falha de rede ao enviar para o Telegram: {exc}")


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
                requests_info = (
                    resp_data[0].get("requests", {}) if resp_data else {}
                )
            elif isinstance(resp_data, dict):
                requests_info = resp_data.get("requests", {})
            else:
                requests_info = {}

            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            print(
                f"API-Football Status -> Consumidas hoje: {current}/{limit}"
            )
            if current < limit:
                return True
        else:
            print(
                f"Erro ao checar status da API-Football: {response.status_code}"
            )
    except Exception as e:
        print(f"Falha de conexão ao checar status da API-Football: {e}")
    return False


def buscar_jogos_api_football_com_fallback(data_hoje_iso: str):
    """Gerencia API Principal e Secundária com verificação prévia de cota."""
    chaves = [
        ("API Principal (API_FOOTBALL_KEY)", API_FOOTBALL_KEY),
        ("API Secundária (API_FOOTBALL_KEY_2)", API_FOOTBALL_KEY_2),
    ]

    for nome, chave in chaves:
        if not chave:
            continue
        print(f"Verificando cota da {nome}...")
        if verificar_status_api_football(chave):
            print(
                f"Buscando partidas do dia {data_hoje_iso} via {nome}..."
            )
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        print(
                            f"Sucesso! Encontrados {len(dados)} jogos via {nome}."
                        )
                        return dados, nome
                    else:
                        print(f"{nome} retornou 0 jogos para hoje.")
            except Exception as e:
                print(f"Erro ao requisitar jogos via {nome}: {e}")
        else:
            print(
                f"{nome} sem cota disponível ou falha na validação de status."
            )
    return None, None


def buscar_jogos_espn():
    """Conferência cruzada via endpoint público da ESPN."""
    print("Acionando 3ª camada: Conferência cruzada via ESPN...")
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            eventos = data.get("events", [])
            print(f"ESPN retornou {len(eventos)} eventos.")
            return eventos
    except Exception as e:
        print(f"Erro ao consultar endpoint da ESPN: {e}")
    return []


def formatar_jogos_fallback_limpo(jogos, origem, data_hoje):
    """Formata os jogos de contingência exibindo apenas dados reais sem repetitivos fictícios."""
    blocos = [
        f"🔥 <b>JOGOS DO DIA — {data_hoje}</b>\n",
        "🇧🇷 Atualizado hoje",
        "⚠️ Modo de Contingência: Análise por IA indisponível no momento.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>PARTIDAS CONFIRMADAS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️"]

    if "ESPN" in origem:
        for idx, ev in enumerate(jogos[:6]):
            nome = ev.get("name", "Confronto")
            data_str = ev.get("date", "")
            hora = "A definir"
            if "T" in data_str:
                try:
                    dt_utc = datetime.fromisoformat(
                        data_str.replace("Z", "+00:00")
                    )
                    dt_brt = dt_utc - timedelta(hours=3)
                    hora = dt_brt.strftime("%H:%M") + " BRT"
                except Exception:
                    pass
            medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"

            bloco = (
                f"{medalha} ⚽️ <b>{nome}</b>\n"
                f"🕟 Horário: <b>{hora}</b>\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            blocos.append(bloco)
    else:
        for idx, item in enumerate(jogos[:6]):
            teams = item.get("teams", {})
            home = teams.get("home", {}).get("name", "Mandante")
            away = teams.get("away", {}).get("name", "Visitante")
            fixture = item.get("fixture", {})
            date_str = fixture.get("date", "")
            hora = "A definir"
            if "T" in date_str:
                try:
                    dt_utc = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00")
                    )
                    dt_brt = dt_utc - timedelta(hours=3)
                    hora = dt_brt.strftime("%H:%M") + " BRT"
                except Exception:
                    pass
            league = item.get("league", {}).get("name", "Competição")
            medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"

            bloco = (
                f"{medalha} ⚽️ <b>{home} x {away}</b>\n"
                f"🏆 <i>{league}</i>\n"
                f"🕟 Horário: <b>{hora}</b>\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            blocos.append(bloco)

    blocos.extend(
        [
            "⚠️ <b>AVISO DE APOSTAS</b>",
            "Confira cotações e linhas de entrada diretamente na sua casa de apostas.",
            "",
            "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!",
            "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:",
            "https://superbet.onelink.me/Hqv6/03r54ds3",
        ]
    )

    texto_final = "\n".join(blocos)
    return texto_final.replace("<7/10", "Abaixo de 7/10")


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

Com base estritamente nos dados dos jogos fornecidos abaixo para a data de hoje ({data_hoje}, fuso de Brasília, UTC-3), produza um relatório de apostas único e personalizado por partida para o Telegram.

DADOS DOS JOGOS DISPONÍVEIS:
{dados_jogos_str}

REGRAS OBRIGATÓRIAS:
- Use APENAS os jogos presentes nos dados acima. NUNCA invente confrontos.
- Crie análises, placares, odds e mercados DIFERENTES e personalizados para cada jogo de acordo com as características das equipes.
- Siga a estrutura visual abaixo usando tags HTML (`<b>`, `<i>`). NUNCA utilize o caractere menor que (<) solto.

ESTRUTURA OBRIGATÓRIA DO RELATÓRIO:

🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>

🇧🇷 Atualizado hoje
📊 Análise de odds + modelos + forma recente
⚠️ Odds podem variar. Não existe aposta garantida.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA</b>
━━━━━━━━━━━━━━━━━━
(Para cada jogo, gere valores e análises específicas:)
🥇 ⚽️ <b>[Time A] x [Time B]</b>
🕟 [Horário] 🇧🇷
🎯 Mercado: [Mercado Específico do Jogo]
📊 Odd mercado: ~[Odd Relevante]
🔥 Confiança: [Nota]/10
⚽️ Gols: [Sugestão de Linha]
🚩 Escanteios: [Projeção]
🟨 Cartões: [Projeção]
🔮 Placar provável: [Placar]
💎 Melhor entrada: [Aposta]
━━━━━━━━━━━━━━━━━━
📊 <b>GESTÃO DE BANCA</b>
━━━━━━━━━━━━━━━━━━
🟢 9/10 → stake principal
🟢 8–8.5/10 → stake moderada
🟡 7–7.5/10 → stake reduzida
🔴 Abaixo de 7/10 → evitar
⚠️ Odds são referências e mudam.

JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!
Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:
https://superbet.onelink.me/Hqv6/03r54ds3
"""


def executar_robo_apostas():
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    data_hoje_iso = datetime.now().strftime("%Y-%m-%d")

    jogos_brutos, fonte_usada = buscar_jogos_api_football_com_fallback(
        data_hoje_iso
    )

    dados_contexto = ""
    origem_dados = "API-Football"
    if jogos_brutos:
        origem_dados = fonte_usada
        dados_contexto = (
            f"Partidas obtidas via {fonte_usada}: {str(jogos_brutos[:15])}"
        )
    else:
        print(
            "APIs de Futebol indisponíveis. Acionando Camada 3 (ESPN)..."
        )
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            origem_dados = "Conferência cruzada ESPN"
            jogos_brutos = eventos_espn
            dados_contexto = f"Partidas obtidas via conferência cruzada ESPN: {str(eventos_espn[:15])}"
        else:
            dados_contexto = "Nenhum jogo retornado pelas APIs; utilize o Grounding do Google Search."

    prompt_mestre = montar_prompt(data_hoje, dados_contexto)

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])

    print(
        f"Gerando análise de apostas para hoje ({data_hoje}) via {MODELO}..."
    )
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
                print(f"Cota esgotada na API do Gemini: {e}. Abortando.")
                break

            tempo_espera = retry_sugerido or (tentativa * 45)
            print(
                f"Aviso de conexão/cota: {e}. Tentativa {tentativa}/{max_tentativas}. Aguardando {tempo_espera}s..."
            )
            if tentativa < max_tentativas:
                time.sleep(tempo_espera)

    if not relatorio:
        print("Erro de cota ou conexão na IA. Executando fallback limpo...")
        if jogos_brutos:
            relatorio_fallback = formatar_jogos_fallback_limpo(
                jogos_brutos, origem_dados, data_hoje
            )
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

```
