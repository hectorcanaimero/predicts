# predicts

**Preveja quando cada cliente vai voltar a comprar cada produto — a partir de um CSV.**
**Predice cuándo cada cliente va a volver a comprar cada producto — a partir de un CSV.**

> 🚧 Em construção, em público. / En construcción, en público.

Você sobe um CSV de vendas, mapeia as colunas (cliente, data, SKU/EAN, produto) e o predicts
calcula o ciclo de recompra de cada cliente e produto, sugere lembretes e ofertas no momento certo,
mede a própria precisão com backtest nos seus dados e exporta tudo em CSV para o seu CRM.

- Estatística/ML decide **quando** (medido com backtest).
- [Jev](https://typesafe.ai) toma as **decisões** com confiança (mapeamento, recompra ou durável, contatar ou não).
- Um LLM escreve as mensagens e explica os resultados.

Stack: Python (FastAPI, DuckDB, PostgreSQL + pgvector) · React (Vite, Tailwind, React Three Fiber) · Docker Compose.
Interface em pt-BR, español e English.

Construído com um time de agentes de IA orquestrado pelo [orch](https://github.com/hectorcanaimero/orch).

## Licença

MIT
