"""
Rode este script isolado (no mesmo ambiente onde o robô roda) para
descobrir exatamente onde a busca de forma recente está quebrando.
Não depende do resto do projeto — só imprime o que a API realmente devolve.
"""
import json
import requests

LEAGUE = "eng.1"
TEAM_ID = "363"  # Chelsea na ESPN — ajuste se for diferente na sua base

url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUE}/teams/{TEAM_ID}/schedule"
print(f"Chamando: {url}\n")

resp = requests.get(url, timeout=10)
print(f"Status HTTP: {resp.status_code}")

if resp.status_code != 200:
    print("A API não retornou 200 — corpo da resposta:")
    print(resp.text[:1000])
else:
    dados = resp.json()
    print("Chaves de topo do JSON:", list(dados.keys()))
    eventos = dados.get("events", [])
    print(f"Quantidade de eventos retornados: {len(eventos)}")
    if eventos:
        print("\nPrimeiro evento (bruto, resumido):")
        print(json.dumps(eventos[0], indent=2, ensure_ascii=False)[:2000])
