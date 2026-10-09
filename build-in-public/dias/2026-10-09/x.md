# Dia 1 · X (pt-BR) · BORRADOR

## Opção A — post único

Dia 1 do predicts: um app que prevê quando cada cliente vai voltar a comprar cada produto, a partir de um CSV.

Antes de escrever código, descartei 4 ideias. Hoje só decisões: CSV como entrada, DuckDB pra analisar, Postgres pra app, e o LLM proibido de inventar data.

Construindo em público com um time de agentes de IA.

[imagem: diagrama do time — eu → agente no Slack → orch → agentes de código → PRs]

## Opção B — fio (5 posts)

1/ Dia 1 do predicts. Vou construir do zero, em público, um app que prevê quando cada cliente volta a comprar cada produto. Quem compra ração a cada 4 semanas recebe o lembrete na semana certa.

2/ A entrada é um CSV. Qualquer empresa exporta as vendas pra CSV, então ninguém precisa de integração pra testar. Você mapeia as colunas (cliente, data, SKU ou EAN, produto) e pronto.

3/ Regra principal: o LLM não inventa número. O "quando" vem de estatística e é medido com backtest nos dados do próprio cliente. O LLM escreve as mensagens e explica os resultados.

4/ As decisões pequenas (essa coluna é a data? esse produto se recompra ou é durável?) vão pro Jev, que responde com probabilidade. Abaixo do limite de confiança, quem decide é uma pessoa.

5/ Quem escreve o código é um time de agentes orquestrado pelo orch, um projeto open source meu. Amanhã: a arquitetura. Repo: github.com/hectorcanaimero/predicts

---

**Notas (para Héctor):**
- Elige A (rápido) o B (hilo, más alcance). Horario sugerido: 12:00 o 19:00 (Brasília).
- La imagen la genero cuando confirmes; también sirve para Instagram.
- Confidencialidad revisada: sin empleador, sin marcas, sin "supermercado". ✔
