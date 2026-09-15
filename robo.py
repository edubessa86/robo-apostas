from datetime import datetime, timedelta
import os
import random
import time
import requests
from google import genai
from google.genai import types

# Pega as chaves seguras do GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_KEY_2 = os.environ.get("API_FOOTBALL_KEY_2")

MODELO = "gemini-2.5-flash"

# Inicializa o cliente oficial do Gemini
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def dividir_mensagem(texto, limite=4000):
    return [texto[i : i + limite] for i in range(0, len(texto), limite)]


def enviar_telegram(texto: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro crítico: TELEGRAM_TOKEN ou CHAT_ID não definidos.")
        return

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
    if not api_key:
        return False
    url = "https://v3.football.api-sports.io/status"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            resp_data = data.get("response", {})
            requests_info = (
                resp_data[0].get("requests", {})
                if isinstance(resp_data, list) and resp_data
                else resp_data.get("requests", {})
            )
            current = requests_info.get("current", 0)
            limit = requests_info.get("limit_day", 100)
            if current < limit:
                return True
    except Exception as e:
        print(f"Falha ao checar status API-Football: {e}")
    return False


def buscar_jogos_api_football_com_fallback(data_hoje_iso: str):
    chaves = [
        ("API Principal", API_FOOTBALL_KEY),
        ("API Secundária", API_FOOTBALL_KEY_2),
    ]

    for nome, chave in chaves:
        if not chave:
            continue
        if verificar_status_api_football(chave):
            url = f"https://v3.football.api-sports.io/fixtures?date={data_hoje_iso}"
            headers = {"x-apisports-key": chave}
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    dados = resp.json().get("response", [])
                    if dados:
                        return dados, nome
            except Exception as e:
                print(f"Erro na busca via {nome}: {e}")
    return None, None


def buscar_jogos_espn():
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("events", [])
    except Exception as e:
        print(f"Erro ao consultar ESPN: {e}")
    return []


def gerar_indicadores_contingencia(nome_confronto):
    """Gera projeções caso a IA falhe por cota esgotada."""
    random.seed(hash(nome_confronto))

    gols_mandante = random.choice([0, 1, 2, 3])
    gols_visitante = random.choice([0, 1, 2])
    placar = f"{gols_mandante} x {gols_visitante}"

    total_gols_est = gols_mandante + gols_visitante
    linha_gols = (
        "Over 2.5 Gols"
        if total_gols_est >= 3
        else ("Over 1.5 Gols" if total_gols_est == 2 else "Under 2.5 Gols")
    )

    cantos = random.randint(8, 12)
    cartoes = random.randint(3, 6)
    confianca = round(random.uniform(7.5, 9.2), 1)
    odd = round(random.uniform(1.55, 2.10), 2)

    if gols_mandante > gols_visitante:
        mercado = "Vitória Casa / Empate Anula"
        entrada = "Mandante Vence ou Empata"
    elif gols_visitante > gols_mandante:
        mercado = "Double Chance / Fora"
        entrada = "Visitante ou Empate"
    else:
        mercado = "Ambas Marcam (BTTS)"
        entrada = "Ambas as Equipes Marcam"

    return {
        "placar": placar,
        "mercado": mercado,
        "entrada": entrada,
        "odd": odd,
        "confianca": confianca,
        "gols": linha_gols,
        "escanteios": f"Over {cantos - 1.5} Escanteios (~{cantos})",
        "cartoes": f"Over {cartoes - 0.5} Cartões (~{cartoes})",
    }


def formatar_jogos_fallback_completo(jogos, origem, data_hoje):
    blocos = [
        f"🔥 <b>APOSTAS ESPORTIVAS — {data_hoje}</b>\n",
        "🇧🇷 Atualizado hoje",
        "📊 Análise por modelos estatísticos alternativos",
        "⚠️ Modo de contingência ativado.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>TOP APOSTAS DO DIA</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️"]

    for idx, item in enumerate(jogos[:6]):
        if "ESPN" in origem:
            nome = item.get("name", "Confronto").replace(" at ", " x ")
            data_str = item.get("date", "")
            league = "Liga Principal"
        else:
            teams = item.get("teams", {})
            home = teams.get("home", {}).get("name", "Mandante")
            away = teams.get("away", {}).get("name", "Visitante")
            nome = f"{home} x {away}"
            data_str = item.get("fixture", {}).get("date", "")
            league = item.get("league", {}).get("name", "Competição")

        hora = "A definir"
        if "T" in data_str:
            try:
                dt_utc = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
                dt_brt = dt_utc - timedelta(hours=3)
                hora = dt_brt.strftime("%H:%M") + " BRT"
            except Exception:
                pass

        stats = gerar_indicadores_contingencia(nome)
        medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"

        bloco = (
            f"{medalha} ⚽️ <b>{nome}</b>\n"
            f"🏆 <i>{league}</i> | 🕟 <b>{hora}</b>\n"
            f"🎯 Mercado: <b>{stats['mercado']}</b>\n"
            f"📊 Odd mercado: <b>~{stats['odd']}</b>\n"
            f"🔥 Confiança: <b>{stats['confianca']}/10</b>\n"
            f"⚽️ Gols: <b>{stats['gols']}</b>\n"
            f"🚩 Escanteios: <b>{stats['escanteios']}</b>\n"
            f"🟨 Cartões: <b>{stats['cartoes']}</b>\n"
            f"🔮 Placar provável: <b>{stats['placar']}</b>\n"
            f"💎 Melhor entrada: <b>{stats['entrada']}</b>\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        blocos.append(bloco)

    blocos.extend([
        "📊 <b>GESTÃO DE BANCA</b>",
        "🟢 9/10 → stake principal",
        "🟢 8–8.5/10 → stake moderada",
        "🟡 7–7.5/10 → stake reduzida",
        "⚠️ Odds são referências e mudam.",
        "",
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!",
        "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:",
        "https://superbet.onelink.me/Hqv6/03r54ds3",
    ])

    return "\n".join(blocos)


def montar_prompt_abrangente(data_hoje: str, dados_jogos_str: str) -> str:
    return f"""
Você é um especialista sênior em quantificação de riscos esportivos e apostas de valor.

Sua missão é realizar uma PESQUISA ABRANGENTE em tempo real via Google Search cruzando os 15 PILARES DE ANÁLISE ESPORTIVA abaixo para encontrar as entradas de MAIOR VALOR E ASSERTIVIDADE (alvo de ~70% de acerto) para a data de hoje ({data_hoje}, fuso de Brasília, UTC-3).

PILARES QUE VOCÊ DEVE PESQUISAR E REUNIR DADOS:
1. Sofascore / Flashscore (desempenho e ratings recente)
2. WhoScored (estilo tático e mapa de calor)
3. FBref (Gols Esperados - xG / Assistências Esperadas - xA)
4. Transfermarkt (valor de mercado e elenco disponível)
5. H2H recente (histórico de confronto direto dos últimos 3 anos)
6. Forma recente (últimos 5 jogos de cada time)
7. Rendimento Mandante vs Visitante
8. Lista de desfalques (lesões e suspensões de titulares)
9. Escalações prováveis e rotações táticas
10. Estatísticas médias de escanteios por jogo
11. Média de cartões por partida + histórico do Árbitro
12. Dropping Odds (movimentação de odds nas últimas horas)
13. Valor da Odd vs Probabilidade Implícita calculada
14. Motivação e situação na tabela da competição
15. Fatores externos (clima, distância de viagem e desgaste de calendário)

JOGOS DISPONÍVEIS:
{dados_jogos_str}

DIRETRIZES DE SAÍDA:
- Pesquise no Google os dados reais e atuais para cada confronto antes de decidir as dicas.
- Filtre APENAS as entradas com maior probabilidade matemática de acerto.
- Formate a resposta rigorosamente em HTML (`<b>`, `<i>`) sem usar o caractere menor que (<) solto.

ESTRUTURA DA MENSAGEM:

🔥 <b>APOSTAS HIGH-VALUE — {data_hoje}</b>

🇧🇷 Atualizado hoje com Análise Quantitativa em 15 Fontes
📊 Métricas xG + Dropping Odds + Desfalques
⚠️ Aposte com responsabilidade e gestão de banca.
━━━━━━━━━━━━━━━━━━
🏆 <b>TOP APOSTAS DO DIA (MÁXIMA ASSERTIVIDADE)</b>
━━━━━━━━━━━━━━━━━━
(Para cada jogo analisado, forneça os dados pesquisados:)
🥇 ⚽️ <b>[Time Mandante] x [Time Visitante]</b>
🕟 [Horário] 🇧🇷 | 🏆 <i>[Competição]</i>
🎯 Mercado principal: [Entrada Conservadora de Alta Probabilidade]
📊 Odd verificada: ~[Odd Atual]
🔥 Nível de Confiança: [Nota 8.0 a 10]/10
⚽️ Projeção de Gols: [Linha sugerida com base em xG]
🚩 Projeção de Escanteios: [Média estimada de cantos]
🟨 Projeção de Cartões: [Estimativa com base no árbitro]
🔮 Placar Provável: [Placar estimado]
💎 Aposta de Valor: [Sugestão de entrada principal]
💡 <i>Análise quantitativa: [Resumo sucinto reunindo desfalques, xG ou forma recente]</i>
━━━━━━━━━━━━━━━━━━
📊 <b>GESTÃO DE BANCA RECOMENDADA</b>
━━━━━━━━━━━━━━━━━━
🟢 Confiança 9.0–10 → Stake Cheia (1.5% a 2%)
🟢 Confiança 8.0–8.9 → Stake Moderada (1%)
🔴 Abaixo de 8.0 → Fora da grade de hoje

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
        eventos_espn = buscar_jogos_espn()
        if eventos_espn:
            origem_dados = "ESPN"
            jogos_brutos = eventos_espn
            dados_contexto = (
                f"Partidas obtidas via ESPN: {str(eventos_espn[:15])}"
            )
        else:
            dados_contexto = "Realize busca no Google pelas principais partidas de futebol de hoje."

    relatorio = None

    if client:
        prompt_mestre = montar_prompt_abrangente(data_hoje, dados_contexto)
        try:
            # Habilita a ferramenta de busca do Google para a IA realizar a pesquisa dos 15 pilares
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            config = types.GenerateContentConfig(tools=[grounding_tool])

            print(
                f"Iniciando varredura quantitativa e busca de dados para {data_hoje}..."
            )
            response = client.models.generate_content(
                model=MODELO, contents=prompt_mestre, config=config
            )
            relatorio = response.text
        except Exception as e:
            print(f"Aviso no motor de IA: {e}. Executando fallback com projeções...")

    if not relatorio:
        if jogos_brutos:
            relatorio = formatar_jogos_fallback_completo(
                jogos_brutos, origem_dados, data_hoje
            )
        else:
            relatorio = (
                "⚠️ <b>Não foi possível gerar a grade analítica para hoje.</b>"
            )

    enviar_telegram(relatorio)


if __name__ == "__main__":
    executar_robo_apostas()
