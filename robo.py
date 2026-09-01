from api_football import buscar_odds_do_jogo, extrair_mercados_seguros


def formatar_jogos_fallback_limpo(jogos, origem, data_hoje, api_football_key=None):
    """Formata cada jogo real para o Telegram no modo de contingência (quando o
    Gemini está indisponível/sem cota).

    IMPORTANTE: esta versão NÃO inventa odd, confiança, escanteios, cartões ou
    placar. Quando o jogo vem da API-Football, busca odds reais via
    buscar_odds_do_jogo + extrair_mercados_seguros (mesma lógica já usada no
    fluxo principal). Quando não há odds reais disponíveis (comum em jogos de
    fontes como ESPN, que não tem dados de odds), o jogo aparece sem mercado
    sugerido, em vez de preenchido com números de mentira.
    """
    blocos = [
        f"🔥 <b>JOGOS DE HOJE — {data_hoje}</b>\n",
        "🇧🇷 Atualizado hoje",
        "⚠️ Modo de contingência: análise por IA indisponível no momento.",
        "⚠️ Só mostramos mercados quando há odd real verificada. Sem odd real, sem sugestão de entrada.",
        "━━━━━━━━━━━━━━━━━━",
        "🏆 <b>JOGOS CONFIRMADOS</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    medalhas = ["🥇", "🥈", "🥉", "⚽️", "⚽️", "⚽️"]
    lista_eventos = jogos[:6]

    for idx, item in enumerate(lista_eventos):
        fixture_id = None

        if "ESPN" in origem:
            nome = item.get("name", "Confronto")
            data_str = item.get("date", "")
            hora = "16:30"
            if "T" in data_str:
                try:
                    hora = data_str.split("T")[1][:5] + " BRT"
                except Exception:
                    pass
            confronto_str = nome
            competicao = "Futebol Internacional"
        else:
            teams = item.get("teams", {})
            home = teams.get("home", {}).get("name", "Mandante")
            away = teams.get("away", {}).get("name", "Visitante")
            fixture = item.get("fixture", {})
            fixture_id = fixture.get("id")
            date_str = fixture.get("date", "")
            hora = "16:30"
            if "T" in date_str:
                try:
                    hora = date_str.split("T")[1][:5] + " BRT"
                except Exception:
                    pass
            competicao = item.get("league", {}).get("name", "Competição")
            confronto_str = f"{home} x {away}"

        medalha = medalhas[idx] if idx < len(medalhas) else "⚽️"

        linhas_bloco = [
            f"{medalha} ⚽️ <b>{confronto_str}</b>",
            f"<i>({competicao})</i>",
            f"🕟 {hora} 🇧🇷",
        ]

        # Só busca odds reais se o jogo veio da API-Football (tem fixture_id) e
        # a chave foi passada. Fontes como ESPN não têm dado de odds aqui.
        entradas = []
        if fixture_id and api_football_key:
            odds_resposta = buscar_odds_do_jogo(api_football_key, fixture_id)
            entradas = extrair_mercados_seguros(odds_resposta)

        if entradas:
            linhas_bloco.append("📊 Odds reais verificadas:")
            for entrada in entradas:
                linhas_bloco.append(
                    "  • " + entrada["mercado"] + " - " + entrada["selecao"]
                    + ": odd " + f"{entrada['odd']:.2f}"
                    + " (prob. implícita ~" + f"{entrada['prob_implicita'] * 100:.0f}%" + ")"
                )
        else:
            linhas_bloco.append("📊 Sem odd real verificada disponível para este jogo no momento.")

        linhas_bloco.append("━━━━━━━━━━━━━━━━━━")
        blocos.append("\n".join(linhas_bloco))

    blocos.extend([
        "⚠️ <b>AVISO</b>",
        "Este é um relatório de contingência: mostra apenas jogos confirmados e,",
        "quando disponível, odds reais de mercado. Não há placar, confiança ou",
        "estatística estimada nesta versão. Aposte com responsabilidade.",
        "",
        "JOGUE COMIGO E GANHE GIROS GRÁTIS NA SUPERBET!",
        "Aposte para ganhar 100 GIROS GRÁTIS! Divirta-se no link abaixo:",
        "https://superbet.onelink.me/Hqv6/03r54ds3",
    ])

    return "\n".join(blocos)
