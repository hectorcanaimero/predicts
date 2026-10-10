# Aislamiento por empresa (tenancy)

Toda tabla de negocio tiene `empresa_id` (`EmpresaMixin`, ver `db/base.py`). La regla para
cualquier endpoint que lea, edite o borre un recurso por `id`:

> Un recurso que existe pero es de otra empresa responde **404 `no_encontrado`**, nunca
> `403`. Un 403 confirmaría que el recurso existe; un 404 no revela nada.

`predicts/tenancy.py` da los dos helpers que implementan esto:

- `de_empresa(query, empresa_id)`: agrega `WHERE <modelo>.empresa_id = :empresa_id` a un
  `select(Modelo)...` armado con `sqlalchemy.select`. Úsalo en todo listado (`GET /recurso`)
  para no traer filas de otras empresas.
- `obtener_o_404(db, Modelo, id, empresa_id)`: busca `Modelo` por `id` con `db.get` y revisa
  que `empresa_id` coincida; si no existe o es de otra empresa, levanta `ErrorApi("no_encontrado", 404)`.
  Úsalo en todo `GET/PATCH/DELETE /recurso/{id}` antes de tocar la fila — incluye el caso de un
  `id` válido pero adivinado (UUID de un recurso real de otra empresa).

## Cómo deben usarlo las fases siguientes

- Cualquier router nuevo que reciba un `id` de ruta (datasets, análisis, plantillas, trabajos,
  decisiones de Jev, api keys) debe resolver el recurso con `obtener_o_404`, no con `db.get`
  directo — `db.get` por sí solo no filtra por empresa.
- Cualquier listado nuevo debe envolver su `select(Modelo)` con `de_empresa` antes de ejecutarlo.
- Los recursos que cuelgan de otro (p. ej. `datasets.proyecto_id`, `analisis.dataset_id`) deben
  además verificar con `obtener_o_404` que el padre (el proyecto, el dataset) es de la empresa
  actual antes de usar su `id` para filtrar al hijo — así un `id` de hijo adivinado tampoco sirve
  aunque el padre no se mencione en la URL.
- Borrar un proyecto (`DELETE /proyectos/{id}`) se apoya en el `ON DELETE CASCADE` de Postgres
  (`modelos.py`) para borrar sus `datasets` y `analisis`: la fila desaparece sola, sin loops en
  Python. Como esa cascada se lleva la fila (y con ella `ruta_original`/`ruta_parquet`), la
  retención de archivos (F8.3.T2, `retencion.py`) debe borrar los archivos de un dataset *antes*
  de que su proyecto se borre, no después — una vez cascadeada la fila ya no hay cómo encontrar
  la ruta.
