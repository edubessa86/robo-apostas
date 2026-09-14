# 🤖 Robô de Apostas Esportivas v2

Evolução do [robo-apostas](https://github.com/edubessa86/robo-apostas) com **mais ligas**, **filtros configuráveis** e **gestão de banca real**.

## O que tem de novo

| Recurso | v1 | v2 |
| --- | --- | --- |
| Ligas cobertas | 12 | **31** |
| Filtro por faixa de odd | ❌ | ✅ (min/max configuráveis) |
| Filtro por horário | só mínimo | ✅ janela (min e max) |
| Filtro de forma recente | ❌ | ✅ (opcional, últimos 5 jogos) |
| Limite de entradas/dia | 6 fixos | ✅ configurável + teto por jogo |
| Gestão de banca | ❌ | ✅ flat / unidades / Kelly fracionado |
| Stop loss diário | ❌ | ✅ trava automática |
| Exposição máxima | ❌ | ✅ trava automática |
| Histórico + ROI | ❌ | ✅ CSV persistido no próprio repo |
| Ponto de entrada | ⚠️ inexistente | ✅ `robo.py` executável |

## Arquitetura

```javascript
config.py            → todas as configurações (ligas, filtros, banca) via env vars
api_football.py      → integração API-Football: 31 ligas, odds, forma recente
filtros.py           → funil de filtros: odd, mercado, prob., forma, ranking
gestao_banca.py      → stake sizing, proteções diárias, CSV, estatísticas/ROI
robo.py              → ponto de entrada (main), monta e envia o relatório
liquidar_resultados.py → marca green/red no CSV (lucro calculado automaticamente)
apostas.csv          → histórico (criado automaticamente, commitado pelo workflow)
```

## Configuração rápida (GitHub Actions)

**Secrets** (Settings → Secrets and variables → Actions):

- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `API_FOOTBALL_KEY`

**Variables** (opcionais — defaults sensatos em `config.py`):

- `BANCA_INICIAL` (1000), `STAKE_MODE` (`flat`|`kelly`|`unidades`), `STAKE_FIXO_PCT` (0.02)
- `ODD_MIN` (1.30), `ODD_MAX` (2.50), `PROB_MINIMA` (0.55), `MAX_ENTRADAS_POR_DIA` (5)
- `STOP_LOSS_DIARIO_PCT` (0.05), `EXPOSICAO_MAXIMA_DIA_PCT` (0.10)
- `LIGAS_ATIVAS` (vazio = todas; ex: `"71,39,140,2"` só Brasil, Inglaterra, Espanha e Champions)
- `FORMA_MINIMA` (0 = desligado; ex: 3 = time precisa somar 3 vitórias+empates nos últimos 5)

## Uso local

```bash
pip install requests
export API_FOOTBALL_KEY=... TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=...
python robo.py                       # gera relatório + registra no CSV
python liquidar_resultados.py --fixture 12345 --selecao "Home/Draw" --resultado green
```

## ⚠️ Aviso honesto (mantido da v1)

O robô **nunca inventa odd** — só sugere entrada quando há odd real verificada
pela API. No modo `flat` (padrão) a stake é puramente percentual da banca, sem
alegar "valor" que não existe. O modo `kelly` exige probabilidade estimada
própria; usar a prob. implícita da própria odd retorna stake 0 por definição.
Aposte com responsabilidade: 18+, e stake sugerida é teto, não obrigação.
