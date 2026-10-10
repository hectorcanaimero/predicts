#!/usr/bin/env python3
"""Servidor falso de 9router para el e2e de F6.3.T3: implementa `POST /v1/chat/completions`
(formato OpenAI, lo que espera `langchain_openai.ChatOpenAI` vía `predicts.ia.llm_texto`) y
`POST /v1/embeddings` (lo que espera `predicts.ia.embeddings`), sin red ni modelo real.

- Embeddings: vector determinista (semilla = hash del texto) de la dimensión que pide
  `productos.embedding` (1536, ver `api/alembic/versions/0001_esquema_inicial.py`). No necesita
  parecerse a un embedding real para el flujo del e2e: solo que dos nombres de producto
  distintos no salgan "iguales" por accidente (ver `productos/equivalentes.py`).
- Chat completions: `predicts.ia.generar()` pide JSON que valide contra un esquema (JSON Schema
  compacto al final del mensaje `system`, ver `ia.py::INSTRUCCION_JSON`). Este servidor llena
  ese esquema de forma genérica (recursión sobre `properties`/`additionalProperties`/`$ref`).
  El único punto no genérico: un campo `dict[str, X]` (`additionalProperties` sin `properties`
  fijas) no tiene sus claves en el esquema -- igual que un modelo real, hay que leerlas del
  prompt. `mensajes/plantillas.py::_prompt` las escribe como `- "clave": ...` en el mensaje
  `user`, así que ese es el único patrón que este servidor conoce. En el flujo normal del e2e
  (solo recompra/ciclos/riesgo/ofertas, sin pedir el tipo `mensajes`) esta ruta no se llama.

Activación: variable de entorno `ROUTER_BASE_URL` apuntando a este servidor con sufijo `/v1`
(ver `docker-compose.e2e.yml`) -- con `/v1` en la base, tanto el cliente OpenAI (que arma
`{base}/chat/completions`) como `predicts.ia._url_embeddings` (que agrega `/v1` solo si falta)
terminan pegándole a este mismo prefijo.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_CLAVE_PROMPT = re.compile(r'(?m)^-\s*"([^"]+)":')
_DIMENSION_EMBEDDING = 1536
_TEXTO_RELLENO = "mensaje de prueba (e2e)"


def _resolver(esquema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in esquema:
        nombre = esquema["$ref"].rsplit("/", 1)[-1]
        return defs.get(nombre, {})
    return esquema


def _ejemplo(esquema: dict[str, Any], defs: dict[str, Any], claves: list[str]) -> object:
    esquema = _resolver(esquema, defs)
    tipo = esquema.get("type")
    if tipo == "object" or "properties" in esquema or "additionalProperties" in esquema:
        propiedades = esquema.get("properties")
        if propiedades:
            requeridos = esquema.get("required", list(propiedades))
            return {
                nombre: _ejemplo(propiedades[nombre], defs, claves)
                for nombre in requeridos
                if nombre in propiedades
            }
        adicionales = esquema.get("additionalProperties")
        if isinstance(adicionales, dict):
            return {clave: _ejemplo(adicionales, defs, claves) for clave in claves}
        return {}
    if tipo == "string":
        return _TEXTO_RELLENO
    if tipo == "integer":
        return 0
    if tipo == "number":
        return 0.0
    if tipo == "boolean":
        return False
    if tipo == "array":
        items = esquema.get("items")
        return [_ejemplo(items, defs, claves)] if items else []
    return None


def _extraer_esquema(texto_sistema: str) -> dict[str, Any] | None:
    inicio = texto_sistema.find("{")
    if inicio == -1:
        return None
    try:
        return json.loads(texto_sistema[inicio:])
    except json.JSONDecodeError:
        return None


def _completar_chat(cuerpo: dict[str, Any]) -> dict[str, Any]:
    mensajes = cuerpo.get("messages", [])
    sistema = "\n".join(m.get("content", "") for m in mensajes if m.get("role") == "system")
    usuario = "\n".join(m.get("content", "") for m in mensajes if m.get("role") == "user")
    esquema = _extraer_esquema(sistema)
    claves = _CLAVE_PROMPT.findall(usuario)
    contenido = json.dumps(
        _ejemplo(esquema, (esquema or {}).get("$defs", {}), claves) if esquema else {},
        ensure_ascii=False,
    )
    return {
        "id": "falso-9router",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": cuerpo.get("model", "falso"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": contenido},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _embedding(texto: str) -> list[float]:
    semilla = int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:8], "big")
    azar = random.Random(semilla)
    return [azar.uniform(-1, 1) for _ in range(_DIMENSION_EMBEDDING)]


def _completar_embeddings(cuerpo: dict[str, Any]) -> dict[str, Any]:
    entradas = cuerpo.get("input", [])
    datos = [
        {"index": i, "embedding": _embedding(texto), "object": "embedding"}
        for i, texto in enumerate(entradas)
    ]
    return {
        "data": datos,
        "model": cuerpo.get("model", "falso"),
        "usage": {
            "prompt_tokens": sum(len(t) for t in entradas),
            "total_tokens": sum(len(t) for t in entradas),
        },
    }


class Manejador(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (nombre fijado por BaseHTTPRequestHandler)
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        if self.path.endswith("/chat/completions"):
            respuesta = _completar_chat(cuerpo)
        elif self.path.endswith("/embeddings"):
            respuesta = _completar_embeddings(cuerpo)
        else:
            self.send_response(404)
            self.end_headers()
            return
        cuerpo_resp = json.dumps(respuesta).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo_resp)))
        self.end_headers()
        self.wfile.write(cuerpo_resp)

    def log_message(self, formato: str, *args: object) -> None:  # silencia el log de acceso
        pass


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", "9100"))
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
    print(f"router-falso escuchando en :{puerto}", flush=True)
    servidor.serve_forever()
