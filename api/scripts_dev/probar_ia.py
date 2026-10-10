"""Prueba manual de los tres servicios de `predicts.ia` contra las APIs reales (Jev, 9router,
embeddings). No la corre la CI: requiere `PREDICTS_ENV_FILE` apuntando a un `.env` con las claves
reales (ver `/mnt/storage/project/predicts/.env`).

Uso:
    PREDICTS_ENV_FILE=/mnt/storage/project/predicts/.env uv run python scripts_dev/probar_ia.py
"""

from __future__ import annotations

from pydantic import BaseModel

from predicts.config import settings
from predicts.ia import Contador, decidir_choice, decidir_si_no, embeddings, generar


class CategoriaProducto(BaseModel):
    categoria: str
    confianza: float


def main() -> None:
    cfg = settings()
    contador = Contador()

    print("== Jev: decidir_si_no ==")
    decision_si_no = decidir_si_no(
        "¿Este producto es de recompra frecuente (se agota y se vuelve a comprar en días o "
        "semanas, no un bien durable)?",
        {"producto": "Detergente líquido 1L"},
        contador=contador,
    )
    print(decision_si_no)

    print("\n== Jev: decidir_choice ==")
    decision_choice = decidir_choice(
        "¿A qué categoría pertenece este producto?",
        {
            "limpieza": "Productos de limpieza del hogar",
            "alimentos": "Comida o bebida",
            "higiene_personal": "Cuidado personal",
        },
        {"producto": "Detergente líquido 1L"},
        contador=contador,
    )
    print(decision_choice)

    print("\n== 9router: generar (JSON validado) ==")
    categoria = generar(
        "Clasifica este producto en una categoría de supermercado y da tu confianza (0 a 1): "
        "'Detergente líquido 1L'.",
        CategoriaProducto,
        contador=contador,
    )
    print(categoria)

    print("\n== 9router: embeddings ==")
    vectores = embeddings(
        ["detergente líquido 1l", "jabón en polvo 1kg"], configuracion=cfg, contador=contador
    )
    print(f"{len(vectores)} vectores, dimensión {len(vectores[0])}")

    print("\n== Contador ==")
    print(contador.resumen())


if __name__ == "__main__":
    main()
