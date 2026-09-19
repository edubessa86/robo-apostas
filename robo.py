"""
Relatório diário de projeções para futebol — versão baseada em dados reais.

DIFERENÇA EM RELAÇÃO À VERSÃO ANTERIOR:
A versão anterior decidia "Vencedor Provável", linha de gols, escanteios e
cartões apenas checando se o NOME do time estava numa lista fixa
(["bayern", "real", "flamengo", ...]) e devolvia textos e uma "confiança"
fixa (85%/82%/80%) sempre iguais, sem olhar nenhum dado da partida.

Esta versão busca a forma recente real de cada time (últimos N jogos) na
API pública da ESPN, usando o endpoint de scoreboard por intervalo de
datas (dates=YYYYMMDD-YYYYMMDD) — o mesmo caminho que já funciona
corretamente para achar as partidas do dia. Isso substitui a tentativa
anterior de usar o endpoint /teams/{id}/schedule, que na prática devolve
só uma janela curta de jogos (passados e futuros misturados) e não um
histórico confiável. A partir do histórico real — gols marcados/sofridos
e, quando disponível, escanteios e cartões — usamos um modelo de Poisson
(método estatístico
padrão em análise de futebol) para estimar probabilidades. Não existe
"robô de apostas" público com taxa de acerto de ~80% comprovada e
auditada — mercados de apostas são precificados de forma eficiente, e
apostadores profissionais trabalham com margens de poucos pontos
percentuais, não 80%. Por isso este script NUNCA inventa um número de
confiança: quando os dados reais não são suficientes, ele diz isso
explicitamente em vez de preencher com um valor fixo.

LIMITAÇÃO IMPORTANTE: a API pública da ESPN nem sempre expõe estatísticas
de escanteios e cartões por partida, dependendo da liga. Quando isso
acontece, o relatório informa "dados indisponíveis" em vez de arriscar um
número sem base.
"""

from datetime import datetime, timedelta, timezone
import math
import os
import time

import requests

# Variáveis de Ambiente do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Mapeamento das principais ligas do mundo na ESPN pública
LIGAS_ELITE = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A Itália",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "uefa.champions": "Champions League",
    "bra.1": "Brasileirão Serie A",
    "usa.1": "MLS",
}

JOGOS_PARA_ANALISAR_FORMA = 5  # quantos jogos recentes usar por time
JANELA_HISTORICO_DIAS = 45     # quantos dias para trás buscar no scoreboard
PAUSA_ENTRE_REQUISICOES = 0.15  # segundos, para não sobrecarregar a API pública


# ---------------------------------------------------------------------------
# Utilidades de data/hora
# ---------------------------------------------------------------------------

def converter_hora_brasilia(data_utc_str: str) -> tuple[str, str]:
    """Converte as datas UTC para o Fuso Horário de Brasília (UTC-3)."""
    if not data_utc_str:
        return "16:00 BRT", datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")
    try:
        if "T" in data_utc_str:
            dt_utc = datetime.fromisoformat(data_utc_str.replace("Z", "+00:00"))
            dt_brt = dt_utc.astimezone(timezone(timedelta(hours=-3)))
            return dt_brt.strftime("%H:%M BRT"), dt_brt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return "16:00 BRT", datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Modelo estatístico (Poisson) — substitui os percentuais fixos inventados
# ---------------------------------------------------------------------------

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        lam = 0.05  # evita lambda zero/negativo em times sem gols na amostra
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def prob_resultado(lambda_casa: float, lambda_fora: float, max_gols: int = 6):
    """Probabilidade de vitória do mandante / empate / vitória do visitante,
    assumindo gols de cada time como variáveis de Poisson independentes
    (modelo simplificado, o mesmo princípio usado em análises acadêmicas de
    futebol — não é garantia de resultado, é uma estimativa)."""
    prob_casa = prob_empate = prob_fora = 0.0
    for i in range(max_gols + 1):
        for j in range(max_gols + 1):
            p = poisson_pmf(i, lambda_casa) * poisson_pmf(j, lambda_fora)
            if i > j:
                prob_casa += p
            elif i == j:
                prob_empate += p
            else:
                prob_fora += p
    return prob_casa, prob_empate, prob_fora


def media(lista, padrao=None):
    return sum(lista) / len(lista) if lista else padrao


# ---------------------------------------------------------------------------
# Busca de forma recente real dos times na API pública da ESPN
# ---------------------------------------------------------------------------

def obter_escanteios_cartoes(league_code: str, event_id: str, team_id: str):
    """Tenta extrair escanteios e cartões (amarelo+vermelho) do boxscore da
    partida. Retorna (None, None) quando a API pública não disponibiliza
    esse dado para a liga/partida — o valor NÃO é inventado."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/summary"
    try:
        resp = requests.get(url, params={"event": event_id}, timeout=10)
        if resp.status_code != 200:
            return None, None
        dados = resp.json()
    except Exception:
        return None, None

    times_boxscore = dados.get("boxscore", {}).get("teams", [])
    for time_bx in times_boxscore:
        if str(time_bx.get("team", {}).get("id")) != str(team_id):
            continue
        escanteios = None
        cartoes = 0.0
        cartao_encontrado = False
        for stat in time_bx.get("statistics", []):
            chave = (stat.get("name") or stat.get("abbreviation") or "").lower()
            valor = stat.get("displayValue")
            if valor is None:
                continue
            try:
                valor_num = float(str(valor).replace(",", "."))
            except ValueError:
                continue
            if "corner" in chave:
                escanteios = valor_num
            elif "yellow" in chave or "red" in chave or "card" in chave:
                cartoes += valor_num
                cartao_encontrado = True
        return escanteios, (cartoes if cartao_encontrado else None)
    return None, None


def _partida_concluida(ev: dict) -> bool:
    """Verifica se a partida já terminou. A API da ESPN normalmente expõe
    isso em competitions[0].status.type.state == 'post' (e às vezes também
    no nível do evento) — checamos os dois lugares por segurança."""
    comp = ev.get("competitions", [{}])[0]
    for status in (comp.get("status", {}), ev.get("status", {})):
        estado = status.get("type", {}).get("state")
        if estado:
            return estado == "post"
    return False


def obter_historico_liga(league_code: str, dias: int = JANELA_HISTORICO_DIAS) -> list:
    """Busca, em UMA única chamada, todos os jogos de uma liga nos últimos
    `dias` dias (incluindo hoje) usando o endpoint de scoreboard por
    intervalo de datas — o mesmo que já comprovadamente funciona para achar
    as partidas do dia. Isso evita depender do endpoint /schedule, que na
    prática devolve só uma janela curta de jogos (passados e futuros
    misturados), não o histórico real do time."""
    fuso_br = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_br)
    fim = hoje.strftime("%Y%m%d")
    inicio = (hoje - timedelta(days=dias)).strftime("%Y%m%d")

    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/scoreboard"
    try:
        resp = requests.get(url, params={"dates": f"{inicio}-{fim}"}, timeout=15)
        if resp.status_code != 200:
            print(f"Aviso: scoreboard histórico de {league_code} retornou HTTP {resp.status_code}")
            return []
        return resp.json().get("events", [])
    except Exception as e:
        print(f"Aviso: falha ao buscar histórico de {league_code}: {e}")
        return []


def obter_forma_recente(league_code: str, team_id: str, historico_liga: list, cache: dict,
                         n: int = JOGOS_PARA_ANALISAR_FORMA) -> dict:
    """Filtra, a partir do histórico já baixado da liga, os últimos N jogos
    CONCLUÍDOS de um time e calcula médias reais de gols marcados/sofridos
    e, quando a API fornecer, escanteios e cartões."""
    if team_id in cache:
        return cache[team_id]

    resultado = {
        "jogos_analisados": 0,
        "gols_marcados": [],
        "gols_sofridos": [],
        "escanteios": [],
        "cartoes": [],
    }

    jogos_do_time = []
    for ev in historico_liga:
        if not _partida_concluida(ev):
            continue
        comp = ev.get("competitions", [{}])[0]
        competidores = comp.get("competitors", [])
        if not any(str(c.get("team", {}).get("id")) == str(team_id) for c in competidores):
            continue
        jogos_do_time.append(ev)

    jogos_do_time.sort(key=lambda ev: ev.get("date", ""), reverse=True)

    for ev in jogos_do_time[:n]:
        comp = ev.get("competitions", [{}])[0]
        competidores = comp.get("competitors", [])
        time_alvo = next((c for c in competidores if str(c.get("team", {}).get("id")) == str(team_id)), None)
        adversario = next((c for c in competidores if str(c.get("team", {}).get("id")) != str(team_id)), None)
        if not time_alvo or not adversario:
            continue
        try:
            gm = int(float(time_alvo.get("score", 0)))
            gs = int(float(adversario.get("score", 0)))
        except (TypeError, ValueError):
            continue

        resultado["gols_marcados"].append(gm)
        resultado["gols_sofridos"].append(gs)
        resultado["jogos_analisados"] += 1

        event_id = ev.get("id")
        if event_id:
            time.sleep(PAUSA_ENTRE_REQUISICOES)
            esc, crt = obter_escanteios_cartoes(league_code, event_id, team_id)
            if esc is not None:
                resultado["escanteios"].append(esc)
            if crt is not None:
                resultado["cartoes"].append(crt)

    cache[team_id] = resultado

    if resultado["jogos_analisados"] == 0:
        print(
            f"Aviso: nenhum jogo concluído encontrado para o time {team_id} "
            f"na liga {league_code} nos últimos {JANELA_HISTORICO_DIAS} dias. "
            "Verifique se a API mudou de formato (rode diagnostico_forma.py)."
        )

    return resultado


# ---------------------------------------------------------------------------
# Projeção da partida a partir de dados reais
# ---------------------------------------------------------------------------

def projetar_partida(forma_mandante: dict, forma_visitante: dict) -> dict:
    jogos_m = forma_mandante["jogos_analisados"]
    jogos_v = forma_visitante["jogos_analisados"]

    if jogos_m == 0 or jogos_v == 0:
        return {
            "vencedor_provavel": "Dados insuficientes (sem jogos recentes na API)",
            "dupla_chance": "N/D",
            "gols": "N/D",
            "placar_esperado": "N/D",
            "escanteios": "N/D",
            "cartoes": "N/D",
            "probabilidade_modelo": "N/D",
            "amostra": f"{jogos_m} jogos (mandante) / {jogos_v} jogos (visitante)",
            "dados_suficientes": False,
        }

    media_gm_marcados = media(forma_mandante["gols_marcados"], 1.0)
    media_gm_sofridos = media(forma_mandante["gols_sofridos"], 1.0)
    media_gv_marcados = media(forma_visitante["gols_marcados"], 1.0)
    media_gv_sofridos = media(forma_visitante["gols_sofridos"], 1.0)

    # Gols esperados = média de ataque do time combinada com média de defesa do adversário
    lambda_casa = (media_gm_marcados + media_gv_sofridos) / 2
    lambda_fora = (media_gv_marcados + media_gm_sofridos) / 2

    prob_casa, prob_empate, prob_fora = prob_resultado(lambda_casa, lambda_fora)

    if prob_casa >= prob_fora:
        vencedor = f"Mandante — modelo estima {prob_casa * 100:.0f}%"
        dupla_chance = f"1X (Mandante ou Empate) — modelo estima {(prob_casa + prob_empate) * 100:.0f}%"
    else:
        vencedor = f"Visitante — modelo estima {prob_fora * 100:.0f}%"
        dupla_chance = f"X2 (Empate ou Visitante) — modelo estima {(prob_fora + prob_empate) * 100:.0f}%"

    gols_esperados_total = lambda_casa + lambda_fora
    linha_gols = f"Over {max(gols_esperados_total - 0.5, 0.5):.1f} Gols (esperado pelo modelo: {gols_esperados_total:.1f})"
    placar_esperado = f"{round(lambda_casa)} x {round(lambda_fora)} (aprox., baseado na média recente)"

    if forma_mandante["escanteios"] and forma_visitante["escanteios"]:
        esc_total = media(forma_mandante["escanteios"]) + media(forma_visitante["escanteios"])
        escanteios = f"Over {max(esc_total - 0.5, 0.5):.1f} Escanteios (média recente combinada: {esc_total:.1f})"
    else:
        escanteios = "Dados de escanteios indisponíveis na API pública para esta liga"

    if forma_mandante["cartoes"] and forma_visitante["cartoes"]:
        cart_total = media(forma_mandante["cartoes"]) + media(forma_visitante["cartoes"])
        cartoes = f"Over {max(cart_total - 0.5, 0.5):.1f} Cartões (média recente combinada: {cart_total:.1f})"
    else:
        cartoes = "Dados de cartões indisponíveis na API pública para esta liga"

    return {
        "vencedor_provavel": vencedor,
        "dupla_chance": dupla_chance,
        "gols": linha_gols,
        "placar_esperado": placar_esperado,
        "escanteios": escanteios,
        "cartoes": cartoes,
        "probabilidade_modelo": f"Casa {prob_casa*100:.0f}% | Empate {prob_empate*100:.0f}% | Fora {prob_fora*100:.0f}%",
        "amostra": f"{jogos_m} jogos (mandante) / {jogos_v} jogos (visitante)",
        "dados_suficientes": True,
    }


# ---------------------------------------------------------------------------
# Busca das partidas do dia
# ---------------------------------------------------------------------------

def buscar_jogos_reais_do_dia():
    """Filtra as partidas oficiais e reais do dia atual em Brasília e monta
    a projeção de cada uma a partir da forma recente real dos dois times."""
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje_br = datetime.now(fuso_br).strftime("%Y-%m-%d")

    jogos_filtrados = []
    ids_processados = set()
    cache_forma = {}  # evita buscar a forma do mesmo time mais de uma vez

    for code_liga, nome_liga in LIGAS_ELITE.items():
        # Uma única chamada traz o intervalo (histórico + hoje) da liga inteira.
        eventos = obter_historico_liga(code_liga)
        if not eventos:
            print(f"Aviso: nenhum evento retornado para {nome_liga} ({code_liga}) no intervalo buscado.")
            continue

        for ev in eventos:
            game_id = ev.get("id")
            if game_id in ids_processados:
                continue

            comp = ev.get("competitions", [{}])[0]
            status_nome = comp.get("status", {}).get("type", {}).get("name", "")
            if "POSTPONED" in status_nome or "CANCELED" in status_nome or "SUSPENDED" in status_nome:
                continue

            data_utc = ev.get("date", "")
            hora_brt, data_brt = converter_hora_brasilia(data_utc)
            if data_brt != data_hoje_br:
                continue

            competidores = comp.get("competitors", [])
            if len(competidores) < 2:
                continue

            mandante_comp = next((c for c in competidores if c.get("homeAway") == "home"), competidores[0])
            visitante_comp = next((c for c in competidores if c.get("homeAway") == "away"), competidores[1])

            mandante_nome = mandante_comp.get("team", {}).get("displayName", "Mandante")
            visitante_nome = visitante_comp.get("team", {}).get("displayName", "Visitante")
            mandante_id = mandante_comp.get("team", {}).get("id")
            visitante_id = visitante_comp.get("team", {}).get("id")

            if not mandante_id or not visitante_id:
                continue

            forma_mandante = obter_forma_recente(code_liga, mandante_id, eventos, cache_forma)
            forma_visitante = obter_forma_recente(code_liga, visitante_id, eventos, cache_forma)
            projecao = projetar_partida(forma_mandante, forma_visitante)

            ids_processados.add(game_id)
            jogos_filtrados.append({
                "partida": f"{mandante_nome} x {visitante_nome}",
                "liga": nome_liga,
                "horario": hora_brt,
                "projecao": projecao,
            })

    return jogos_filtrados


# ---------------------------------------------------------------------------
# Montagem e envio do relatório
# ---------------------------------------------------------------------------

def dividir_mensagem(texto: str, limite: int = 3800) -> list:
    """Fatia textos extensos para respeitar o limite do Telegram."""
    if len(texto) <= limite:
        return [texto]
    partes = []
    while len(texto) > 0:
        if len(texto) <= limite:
            partes.append(texto)
            break
        corte = texto.rfind("\n", 0, limite)
        if corte == -1:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")
    return partes


def enviar_telegram(texto: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Credenciais do Telegram ausentes.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    partes = dividir_mensagem(texto)

    for parte in partes:
        payload = {"chat_id": CHAT_ID, "text": parte, "parse_mode": "HTML"}
        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code != 200:
                payload_puro = {"chat_id": CHAT_ID, "text": parte}
                requests.post(url, json=payload_puro, timeout=15)
        except Exception as e:
            print(f"Erro de rede ao enviar ao Telegram: {e}")


def montar_relatorio(jogos):
    fuso_br = timezone(timedelta(hours=-3))
    data_hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")

    msg = f"⚽ <b>RELATÓRIO DE PROJEÇÕES — {data_hoje}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "🏆 <b>ESTIMATIVAS BASEADAS NA FORMA RECENTE REAL DOS TIMES</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    if not jogos:
        msg += "<i>Nenhuma partida confirmada para hoje nas ligas principais.</i>\n\n"
    else:
        for j in jogos[:10]:
            p = j["projecao"]
            msg += f"⚽ <b>{j['partida']}</b>\n"
            msg += f"🏆 <i>{j['liga']}</i> | 🕟 <b>{j['horario']}</b>\n"
            msg += f"👑 <b>Vencedor Provável:</b> {p['vencedor_provavel']}\n"
            msg += f"🎯 <b>Dupla Chance:</b> {p['dupla_chance']}\n"
            msg += f"⚽ <b>Linha de Gols:</b> {p['gols']} (placar aprox.: {p['placar_esperado']})\n"
            msg += f"🚩 <b>Escanteios:</b> {p['escanteios']}\n"
            msg += f"🟨 <b>Cartões Estimados:</b> {p['cartoes']}\n"
            msg += f"📊 <b>Probabilidades do modelo:</b> {p['probabilidade_modelo']}\n"
            msg += f"🔎 <i>Amostra: {p['amostra']}</i>\n"
            msg += "━━━━━━━━━━━━━━━━━━\n"

    msg += "\n⚠️ <b>SOBRE ESTE RELATÓRIO</b>\n"
    msg += (
        "As estimativas usam um modelo estatístico simplificado (Poisson) "
        "a partir dos últimos jogos de cada time. Não são garantia de "
        "resultado e não substituem análise de escalações, lesões e "
        "contexto da partida. Aposte com responsabilidade.\n"
    )

    return msg


def main():
    jogos = buscar_jogos_reais_do_dia()

    sem_dados = sum(1 for j in jogos if not j["projecao"]["dados_suficientes"])
    print(f"Resumo da execução: {len(jogos)} partidas encontradas, {sem_dados} sem forma recente suficiente.")

    relatorio = montar_relatorio(jogos)
    print(relatorio)  # útil para depuração local e para os logs da execução agendada
    enviar_telegram(relatorio)


if __name__ == "__main__":
    main()
