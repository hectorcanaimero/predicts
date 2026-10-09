# Episodio 0 — LinkedIn (pt-BR) · BORRADOR

Vou construir um produto de IA do zero, em público. E quem vai escrever a maior parte do código não sou eu.

O produto se chama predicts. Você sobe um CSV de vendas e ele prevê quando cada cliente deve voltar a comprar cada produto. Quem compra ração a cada 4 semanas recebe um lembrete na semana certa, não no disparo genérico de sexta-feira.

O time:

Eu decido o produto e aprovo cada etapa.
Um agente no Slack faz o papel de gerente de projeto: transforma minhas ideias em PRD, arquitetura e specs.
O orch, um orquestrador open source que eu escrevi, quebra as specs em tarefas e distribui entre agentes de código rodando em paralelo, cada um no seu branch e no seu PR.
Um supervisor confere tudo a cada 15 minutos e destrava o que travou.
E nada entra sem teste e sem métrica.

A regra que mais importa: o LLM não inventa número. A previsão de "quando" vem de estatística, medida com backtest. O LLM escreve as mensagens e explica os resultados.

Vou contar tudo aqui: decisões, custos reais, o que quebrou. Começando pelo primeiro dia, em que descartei quatro ideias antes de chegar nesta.

Qual parte você quer ver primeiro: a arquitetura ou o time de agentes?

#InteligenciaArtificial #AIEngineering #BuildInPublic #LLM #Python

---

**Notas (para Héctor):**
- Tipo: lanzamiento de serie. Horario: martes a jueves, 8:00–9:30 (Brasília).
- Imagen: diagrama del equipo (Héctor → Hermes → orch → agentes → PRs → supervisor). Lo genero
  cuando confirmes el texto.
- Datos: no hay números todavía; el episodio 1 ya trae los primeros (homelab, decisiones).
- Compromiso público: "vou contar tudo aqui". Confirma que quieres asumirlo.
- Link al repo: solo si ya es público.
- Revisión de confidencialidad: sin empleador, sin marcas, sin "supermercado". ✔
