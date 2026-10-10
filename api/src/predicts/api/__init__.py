"""Paquete de routers de la API.

Cada módulo de este paquete que expone un objeto `router` (`fastapi.APIRouter`) se
incluye automáticamente en `predicts.app.crear_app()`, así cada fase agrega su
archivo sin tocar `app.py`.
"""
