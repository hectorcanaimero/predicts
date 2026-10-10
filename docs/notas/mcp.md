# Servidor MCP

`predicts mcp` (`api/src/predicts/comandos/mcp.py`) levanta el servidor MCP de
`api/src/predicts/agente/mcp.py` (SDK `mcp` 2.x). Expone el agente analista (F7.1.T1) y los
resultados de un análisis como herramientas, autenticadas con una **API key de empresa**
(F2.2.T2: `POST /api-keys` desde la web, devuelve la clave `pk_...` una sola vez).

## Herramientas

| Herramienta | Parámetros | Qué devuelve |
|---|---|---|
| `listar_proyectos` | — | Proyectos de la empresa |
| `listar_datasets` | — | Datasets de la empresa (todos los proyectos) |
| `recordatorios` | `analisis_id`, `dias` (7), `limite` (20) | Predicciones de recompra con `fecha_probable` entre hoy y `dias` días, por probabilidad |
| `ciclos_producto` | `analisis_id`, `producto` | Ciclo típico (mediana, dispersión) del producto o grupo que coincide con `producto` (id exacto o nombre) |
| `clientes_en_riesgo` | `analisis_id`, `limite` (20) | Clientes en riesgo de abandono (nivel producto o tienda), por valor histórico |
| `preguntar` | `dataset_id`, `pregunta` | Respuesta del agente analista (F7.1.T1) sobre el dataset |

`recordatorios`, `ciclos_producto` y `clientes_en_riesgo` leen el Parquet del **último análisis
`listo`** indicado por `analisis_id`; un `analisis_id` de otra empresa, inexistente, o sin ese
resultado, rechaza la llamada igual que un `404`.

## Transportes

- **`stdio`** (`predicts mcp` o `predicts mcp --transporte stdio`): el proceso lo lanza el
  cliente MCP (Claude Desktop/Code) y no hay headers HTTP, así que la clave es **una API key
  fija para todo el proceso** — una sola empresa por conexión. Pasarla por `--api-key` o la
  variable de entorno `PREDICTS_API_KEY`. Sin clave, el servidor rechaza toda llamada.
- **`http`** (`predicts mcp --transporte http --host 0.0.0.0 --port 8300`): HTTP streamable
  (`/mcp`); cada request trae su propia clave en `Authorization: Bearer pk_...`, así que el
  mismo proceso sirve a varias empresas a la vez. Pensado para correr detrás de un proxy con
  TLS.

## Conectarlo desde Claude Desktop/Code

### stdio (una empresa, típico en desktop)

En la config de Claude Desktop (`claude_desktop_config.json`) o de Claude Code
(`claude mcp add`):

```json
{
  "mcpServers": {
    "predicts": {
      "command": "uv",
      "args": ["run", "--directory", "/ruta/a/predicts/api", "predicts", "mcp"],
      "env": {
        "PREDICTS_API_KEY": "pk_...",
        "DATABASE_URL": "postgresql+psycopg://..."
      }
    }
  }
}
```

(`DATABASE_URL` y el resto de variables de `predicts.config.Settings` tienen que estar en el
entorno igual que para `predicts api`/`predicts worker`.)

Con el binario instalado (sin `uv run`):

```json
{
  "mcpServers": {
    "predicts": {
      "command": "predicts",
      "args": ["mcp"],
      "env": { "PREDICTS_API_KEY": "pk_..." }
    }
  }
}
```

### HTTP streamable (servidor ya corriendo, multiempresa)

```bash
predicts mcp --transporte http --port 8300
```

En Claude Code: `claude mcp add --transport http predicts https://mcp.ejemplo.com/mcp --header "Authorization: Bearer pk_..."`.
