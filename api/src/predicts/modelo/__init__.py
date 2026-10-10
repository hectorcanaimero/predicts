"""Modelo de recompra: intervalos, ciclo contraído por par, predicción y backtesting.

Ver docs/arch/001-predicts.md#modelo-de-recompra-modelo--el-núcleo. `VERSION_MODELO`
se guarda en cada resultado; subirla cuando cambie cualquier fórmula.
"""

from predicts.modelo.ciclos import Ajuste, ParamsModelo, ajustar, intervalos

VERSION_MODELO = "0.1.0"

__all__ = ["VERSION_MODELO", "Ajuste", "ParamsModelo", "ajustar", "intervalos"]
