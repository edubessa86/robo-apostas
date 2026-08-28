"""Script auxiliar (uso único/manual): descobre os IDs reais de competições na
API-Football e envia o resultado para o Telegram.

Não faz parte do robô diário — é só uma ferramenta de consulta, pensada para
rodar manualmente via GitHub Actions (workflow_dispatch), já que não depende
de nada além dos secrets que você já tem configurados.

Depois de rodar e anotar os IDs corretos no Telegram, você atualiza o
dicionário LIGAS_PADRAO em api_football.py e pode apagar/ignorar este script.
"""

import os

import requests

from api_football import buscar_id_liga_por_nome

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

# Já confirmados anteriormente (Copa do Brasil=73, Libertadores=13,
# Sudamericana=11, Serie B Brasil=72) — não precisam ser buscados de novo.
# Esta lista cobre o que ainda falta confirmar em LIGAS_PADRAO:
NOMES_PARA_BUSCAR = [
    "Serie A",          # cuidado: existe Itália E Brasil, confira o campo "pais"
    "Premier League",
    "La Liga",
    "Bundesliga",
    "Ligue 1",
    "Champions League",
    "Europa League",
]


def enviar_telegram(texto: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"}, timeout=15)


def main() -> None:
    if not API_FOOTBALL_KEY:
        print("API_FOOTBALL_KEY não configurada.")
        enviar_telegram("⚠️ Não foi possível consultar: API_FOOTBALL_KEY não configurada.")
        return

    linhas = ["🔎 <b>IDs de ligas encontrados na API-Football</b>\n"]

    for nome in NOMES_PARA_BUSCAR:
        print(f"Buscando: {nome}...")
        resultados = buscar_id_liga_por_nome(API_FOOTBALL_KEY, nome)

        if not resultados:
            linha = f"\n<b>{nome}</b>: nenhum resultado encontrado."
            print(linha)
            linhas.append(linha)
            continue

        linhas.append(f"\n<b>{nome}</b>:")
        for r in resultados[:8]:  # limita para não estourar o tamanho da mensagem
            linha = f"  • id={r['id']} | {r['nome']} | {r['tipo']} | {r['pais']}"
            print(linha)
            linhas.append(linha)

    texto_final = "\n".join(linhas)
    print("\n--- Enviando resultado para o Telegram ---")
    enviar_telegram(texto_final)


if __name__ == "__main__":
    main()
