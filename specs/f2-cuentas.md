---
type: spec
project_id: predicts
phase: 2
version: 0.1
depends_on:
  - docs/arch/001-predicts.md
consumed_by:
  - orch-atomizer
generated_by: orch-spec
generated_at: 2026-10-09
title: Cuentas, empresas y proyectos
---

# F2 — Cuentas, empresas y proyectos

Login propio con email y contraseña, sesiones seguras, aislamiento por empresa y proyectos.
Contratos en la arquitectura: *Componentes → Autenticación y empresas*, *Interfaces → API HTTP* y
la tabla de errores `{"codigo", "parametros"}`.

Contexto común: el de `specs/f0-base.md`. Las tablas ya existen (F0.2.T2); **no cambiar el
esquema**. Cada router va en su propio archivo de `api/src/predicts/api/` (lo descubre `app.py`).
Los códigos de error son claves estables en `snake_case` (por ejemplo `credenciales_invalidas`);
los textos los traduce el frontend.

## F2.1 — Package: autenticación

### F2.1.T1 — Registro, login, sesiones, CSRF y límite de intentos

- `auth/seguridad.py`: hash y verificación con **Argon2id** (`argon2-cffi`, parámetros por
  defecto de la librería, rehash si cambian); validación de contraseña (mínimo 10 caracteres,
  no igual al email).
- `auth/sesiones.py`: token aleatorio de 32 bytes; en la base solo su SHA-256; expiración
  deslizante de 30 días; cookie `predicts_sesion` `HttpOnly`, `SameSite=Lax`, `Secure` fuera de
  dev; cerrar sesión borra la fila.
- **CSRF:** cookie `predicts_csrf` (no HttpOnly) + header `X-CSRF-Token` obligatorio en
  POST/PUT/PATCH/DELETE autenticados; comparación en tiempo constante.
- **Límite de intentos:** tabla `intentos_login`; 5 fallos por email o 20 por IP en 15 minutos →
  `429 demasiados_intentos` con `reintentar_en_s`.
- `auth/dependencias.py`: `usuario_actual` y `empresa_actual` (dependencias FastAPI).
- `api/auth.py`: `POST /auth/registro` (crea **empresa + usuario dueño** en una transacción;
  email único, normalizado a minúsculas), `POST /auth/login`, `POST /auth/logout`,
  `GET /auth/yo` (usuario, empresa, idioma preferido). Mismo error `credenciales_invalidas` para
  email inexistente y contraseña equivocada, y tiempo de respuesta similar en ambos casos.
- `PATCH /auth/yo` para cambiar el idioma preferido (`pt-BR|es|en`).

Done when: tests (marcador `db`) cubren registro, email duplicado, login correcto y fallido,
sesión expirada, logout, CSRF faltante o inválido, límite de intentos por email y por IP, cambio
de idioma, y que el token nunca se guarda en claro.

- **Modelo**: claude/claude-opus-5-5
- **Estimación**: 4h
- **Razón**: Seguridad; los errores aquí son vulnerabilidades.
- **Dependencies**: F0.2.T2, F0.2.T4
- **Files**:
  - `api/src/predicts/auth/__init__.py`
  - `api/src/predicts/auth/seguridad.py`
  - `api/src/predicts/auth/sesiones.py`
  - `api/src/predicts/auth/csrf.py`
  - `api/src/predicts/auth/dependencias.py`
  - `api/src/predicts/api/auth.py`
  - `api/tests/test_auth.py`

### F2.1.T2 — Recuperación de contraseña y envío de email

- `correo/__init__.py`: envío por SMTP con la configuración `SMTP_*`; si no está configurado, escribe el
  email completo en el log (modo dev). Plantillas de texto e HTML en
  `api/src/predicts/correo/plantillas/<idioma>/` para `pt-BR`, `es` y `en`, elegidas por el
  idioma del usuario.
- `auth/recuperacion.py`: token de un solo uso (32 bytes, guardado como SHA-256), válido 1 hora;
  pedir uno nuevo invalida los anteriores; al restablecer se cierran todas las sesiones del
  usuario.
- `api/recuperacion.py`: `POST /auth/recuperar` (siempre `204`, exista o no el email, para no
  filtrar cuentas; con el mismo límite de intentos que el login) y `POST /auth/restablecer`
  (token + contraseña nueva).

Done when: tests cubren email existente e inexistente (misma respuesta), token vencido, reusado
e inválido, cierre de sesiones al restablecer, y el contenido del email en los tres idiomas (con
un transporte falso).

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2.5h
- **Razón**: Flujo estándar con detalles de seguridad ya definidos.
- **Dependencies**: F2.1.T1
- **Files**:
  - `api/src/predicts/correo/`
  - `api/src/predicts/auth/recuperacion.py`
  - `api/src/predicts/api/recuperacion.py`
  - `api/tests/test_recuperacion.py`

## F2.2 — Package: empresas y proyectos

### F2.2.T1 — Aislamiento por empresa y CRUD de proyectos

- `tenancy.py`: helper `de_empresa(query, empresa_id)` y una verificación usada por todas las
  rutas que reciben un id (`obtener_o_404(db, Modelo, id, empresa_id)`): un recurso de otra
  empresa responde `404 no_encontrado`, nunca `403` (no revelar que existe).
- `api/proyectos.py`: `GET/POST /proyectos`, `GET/PATCH/DELETE /proyectos/{id}`; campos:
  `nombre`, `idioma_mensajes` (`pt-BR|es|en`), `tono` (`cercano|neutro|formal`), `descripcion`.
  Borrar un proyecto borra en cascada sus datasets y análisis (y marca sus archivos para la
  retención).
- `docs/notas/tenancy.md`: la regla y cómo la deben usar las fases siguientes.

Done when: tests con dos empresas verifican que ninguna ve, edita ni borra proyectos de la otra
(incluido por id adivinado) y cubren validación de campos.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 2h
- **Razón**: CRUD con una regla de aislamiento clara.
- **Dependencies**: F2.1.T1
- **Files**:
  - `api/src/predicts/tenancy.py`
  - `api/src/predicts/api/proyectos.py`
  - `api/tests/test_proyectos.py`
  - `docs/notas/tenancy.md`

### F2.2.T2 — API keys por empresa

Para el servidor MCP y usos programáticos (F7):

- `auth/api_keys.py`: crear (`pk_` + 32 bytes en base62; se muestra una sola vez), listar
  (prefijo, nombre, creada, último uso), revocar; en la base solo el SHA-256.
- Dependencia `empresa_por_api_key` (header `Authorization: Bearer pk_…`) que actualiza
  `ultimo_uso`.
- `api/api_keys.py`: `GET/POST /api-keys`, `DELETE /api-keys/{id}` (requieren sesión).

Done when: tests cubren creación (el valor completo solo en la respuesta de creación), uso,
revocación, aislamiento entre empresas y que la key nunca queda en claro en la base.

- **Modelo**: claude/claude-sonnet-5
- **Estimación**: 1.5h
- **Razón**: Patrón conocido y acotado.
- **Dependencies**: F2.2.T1
- **Files**:
  - `api/src/predicts/auth/api_keys.py`
  - `api/src/predicts/api/api_keys.py`
  - `api/tests/test_api_keys.py`
