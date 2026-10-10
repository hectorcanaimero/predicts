#!/usr/bin/env python3
"""Servidor falso de Jev (TypeSafe) para el e2e de F6.3.T3: implementa `POST /v1/systemone`
(único endpoint que usa `predicts.ia`, ver `typesafe_sdk._core.constants.SYSTEM_ONE_PATH`) con
respuestas deterministas, sin red ni modelo real.

Cada pregunta `choice` se responde con su primer criterio (confianza 0.5, igual que el relleno
de `ClienteJevFalso` en `api/tests/test_mapeo.py`); cada `noul` con `noul=0.5`. La persona que
corre el e2e sobreescribe el mapeo a mano en la pantalla de mapeo, así que la elección exacta de
Jev no importa para que el flujo pase — solo que la respuesta sea válida.

Activación: variable de entorno `TYPESAFE_BASE_URL` apuntando a este servidor (ver
`docker-compose.e2e.yml`); `typesafe_sdk` la lee directo del proceso, sin pasar por
`predicts.config.Settings`.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _responder(preguntas: dict[str, Any]) -> dict[str, Any]:
    respuestas: dict[str, Any] = {}
    for nombre, pregunta in preguntas.items():
        tipo = pregunta.get("type")
        if tipo == "choice":
            criterios = list(pregunta.get("criteria") or {})
            elegido = criterios[0] if criterios else "ignorar"
            probabilidades = (
                {c: 1 / len(criterios) for c in criterios} if criterios else {elegido: 1.0}
            )
            respuestas[nombre] = {
                "type": "choice",
                "choice": elegido,
                "confidence": 0.5,
                "probabilities": probabilidades,
            }
        elif tipo == "score":
            niveles = pregunta.get("criteria") or [""]
            respuestas[nombre] = {
                "type": "score",
                "score": 0.0,
                "confidence": 0.5,
                "legend": {str(i): v for i, v in enumerate(niveles)},
                "probabilities": {str(i): (1.0 if i == 0 else 0.0) for i in range(len(niveles))},
            }
        else:
            respuestas[nombre] = {"type": "noul", "noul": 0.5}
    return respuestas


class Manejador(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (nombre fijado por BaseHTTPRequestHandler)
        if self.path != "/v1/systemone":
            self.send_response(404)
            self.end_headers()
            return
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        respuesta = {
            "model": cuerpo.get("model", "jev-falso"),
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "answers": _responder(cuerpo.get("questions", {})),
        }
        cuerpo_resp = json.dumps(respuesta).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo_resp)))
        self.end_headers()
        self.wfile.write(cuerpo_resp)

    def log_message(self, formato: str, *args: object) -> None:  # silencia el log de acceso
        pass


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", "9200"))
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
    print(f"jev-falso escuchando en :{puerto}", flush=True)
    servidor.serve_forever()
