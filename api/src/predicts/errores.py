"""`ErrorApi`: excepción estándar de la API, formato `{"codigo": str, "parametros": dict}`
(ver docs/arch/001-predicts.md#api)."""

from __future__ import annotations


class ErrorApi(Exception):
    """Error de API con `codigo` traducible por el frontend y `status` HTTP."""

    def __init__(self, codigo: str, status: int, **parametros: object) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.status = status
        self.parametros = parametros
