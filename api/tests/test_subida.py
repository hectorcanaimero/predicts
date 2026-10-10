"""Tests de `datos/subida.py` y de las rutas `api/datasets.py`.

La parte de streaming/límite de tamaño se prueba directo contra `guardar_csv` (sin pasar por
HTTP ni por Postgres); el aislamiento por empresa y el ciclo de vida del dataset se prueban
contra la API completa (marcados `db`, igual que `test_proyectos.py`).
"""

from __future__ import annotations

import gzip
import io
import resource
import uuid
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from predicts.app import crear_app
from predicts.auth.csrf import COOKIE_CSRF
from predicts.config import settings_para_tests
from predicts.datos.subida import ArchivoGuardado, guardar_csv
from predicts.db.modelos import Dataset, Proyecto
from predicts.db.sesion import get_db
from predicts.errores import ErrorApi

FIXTURES = Path(__file__).parent / "fixtures" / "csv"

CONTENIDO_SIMPLE = b"a,b\n" + b"1,2\n" * 1000


class _ContadorLecturas:
    """Stub de archivo binario que registra con qué `n` se llamó a `read`."""

    def __init__(self, datos: bytes) -> None:
        self._datos = datos
        self._restante = datos
        self.llamadas_n: list[int] = []

    def read(self, n: int = -1) -> bytes:
        self.llamadas_n.append(n)
        if n is None or n < 0:
            trozo, self._restante = self._restante, b""
        else:
            trozo, self._restante = self._restante[:n], self._restante[n:]
        return trozo

    def seek(self, offset: int = 0, whence: int = 0) -> int:
        self._restante = self._datos
        return 0

    def close(self) -> None:
        pass


# --- guardar_csv: tamaño, hash, streaming ---------------------------------------------------


def test_guarda_csv_plano_calcula_tamano_y_sha256(tmp_path) -> None:
    import hashlib

    destino = tmp_path / "e" / "d" / "original.csv"
    resultado = guardar_csv(io.BytesIO(CONTENIDO_SIMPLE), destino, max_mb=500)

    assert isinstance(resultado, ArchivoGuardado)
    assert resultado.ruta == destino
    assert destino.read_bytes() == CONTENIDO_SIMPLE
    assert resultado.tamano_bytes == len(CONTENIDO_SIMPLE)
    assert resultado.sha256 == hashlib.sha256(CONTENIDO_SIMPLE).hexdigest()


def test_corta_con_413_si_supera_max_mb(tmp_path) -> None:
    datos = b"a" * (2 * 1024 * 1024)

    with pytest.raises(ErrorApi) as exc:
        guardar_csv(io.BytesIO(datos), tmp_path / "original.csv", max_mb=1)

    assert exc.value.codigo == "archivo_muy_grande"
    assert exc.value.status == 413


def test_lee_en_bloques_acotados_nunca_todo_de_una(tmp_path) -> None:
    fuente = _ContadorLecturas(CONTENIDO_SIMPLE)

    guardar_csv(fuente, tmp_path / "original.csv", max_mb=500)

    assert fuente.llamadas_n, "guardar_csv no leyó nada"
    assert -1 not in fuente.llamadas_n
    assert None not in fuente.llamadas_n
    assert max(fuente.llamadas_n) <= 1024 * 1024
    assert fuente.llamadas_n.count(1024 * 1024) >= 1


# --- gzip / zip ------------------------------------------------------------------------------


def test_descomprime_gzip(tmp_path) -> None:
    comprimido = gzip.compress(CONTENIDO_SIMPLE)
    destino = tmp_path / "original.csv"

    resultado = guardar_csv(io.BytesIO(comprimido), destino, max_mb=500)

    assert destino.read_bytes() == CONTENIDO_SIMPLE
    assert resultado.tamano_bytes == len(CONTENIDO_SIMPLE)


def test_descomprime_zip_con_un_csv(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("compras.csv", CONTENIDO_SIMPLE)
    buffer.seek(0)
    destino = tmp_path / "original.csv"

    resultado = guardar_csv(buffer, destino, max_mb=500)

    assert destino.read_bytes() == CONTENIDO_SIMPLE
    assert resultado.tamano_bytes == len(CONTENIDO_SIMPLE)


def test_zip_con_varios_archivos_rechazado(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("a.csv", CONTENIDO_SIMPLE)
        zf.writestr("b.csv", CONTENIDO_SIMPLE)
    buffer.seek(0)

    with pytest.raises(ErrorApi) as exc:
        guardar_csv(buffer, tmp_path / "original.csv", max_mb=500)

    assert exc.value.codigo == "zip_formato_invalido"
    assert exc.value.status == 400


def test_fixture_gz_y_zip_coinciden_con_el_csv_plano(tmp_path) -> None:
    contenido_plano = (FIXTURES / "utf8.csv").read_bytes()

    con_gz = guardar_csv(
        (FIXTURES / "utf8.csv.gz").open("rb"), tmp_path / "desde_gz.csv", max_mb=500
    )
    con_zip = guardar_csv(
        (FIXTURES / "utf8.zip").open("rb"), tmp_path / "desde_zip.csv", max_mb=500
    )

    assert con_gz.ruta.read_bytes() == contenido_plano
    assert con_zip.ruta.read_bytes() == contenido_plano


# --- memoria con un CSV de 300 MB (lento, fuera de la CI) ------------------------------------


class _GeneradorCSV:
    """File-like que genera un CSV grande fila por fila, sin tenerlo completo en memoria."""

    _FILA = (("x" * 200) + "\n").encode()

    def __init__(self, filas: int) -> None:
        self._filas_totales = filas
        self._filas_restantes = filas
        self._buffer = b""

    def seek(self, offset: int = 0, whence: int = 0) -> int:
        self._filas_restantes = self._filas_totales
        self._buffer = b""
        return 0

    def read(self, n: int = 1024 * 1024) -> bytes:
        while len(self._buffer) < n and self._filas_restantes > 0:
            self._buffer += self._FILA
            self._filas_restantes -= 1
        trozo, self._buffer = self._buffer[:n], self._buffer[n:]
        return trozo

    def close(self) -> None:
        pass


@pytest.mark.lento
def test_subida_de_300mb_no_supera_200mb_de_rss(tmp_path) -> None:
    tamano_objetivo = 300 * 1024 * 1024
    filas = tamano_objetivo // len(_GeneradorCSV._FILA)
    fuente = _GeneradorCSV(filas)

    antes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB en Linux
    guardar_csv(fuente, tmp_path / "original.csv", max_mb=400)
    despues = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    assert (despues - antes) < 200 * 1024


# --- API: subida, listado, detalle, borrado, aislamiento por empresa (requiere Postgres) -----

pytestmark_api = pytest.mark.db

CONTRASENA = "una-contrasena-larga"


@pytest.fixture()
def app(db: Session, monkeypatch, tmp_path):
    monkeypatch.setattr("predicts.auth.sesiones.settings", lambda: settings_para_tests())
    monkeypatch.setattr(
        "predicts.api.datasets.settings",
        lambda: settings_para_tests(DATA_DIR=str(tmp_path), MAX_CSV_MB=1),
    )
    app = crear_app()

    def _get_db() -> Generator[Session]:
        s = Session(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    return app


def _empresa(app, nombre_empresa: str, email: str) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre_empresa": nombre_empresa},
    )
    assert r.status_code == 201
    return cliente


def _csrf(cliente: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": cliente.cookies[COOKIE_CSRF]}


@pytest.fixture()
def ana(app) -> TestClient:
    return _empresa(app, "Tienda Ana", "ana@ejemplo.com")


@pytest.fixture()
def beto(app) -> TestClient:
    return _empresa(app, "Tienda Beto", "beto@ejemplo.com")


def _crear_proyecto(cliente: TestClient) -> dict:
    r = cliente.post(
        "/proyectos", json={"nombre": "Campaña"}, headers=_csrf(cliente)
    )
    assert r.status_code == 201
    return r.json()


def _subir(cliente: TestClient, proyecto_id: str, contenido: bytes, nombre="original.csv"):
    return cliente.post(
        f"/proyectos/{proyecto_id}/datasets",
        files={"archivo": (nombre, contenido, "text/csv")},
        headers=_csrf(cliente),
    )


pytestmark = pytestmark_api


def test_subir_csv_crea_dataset_subido_con_deteccion(ana) -> None:
    proyecto = _crear_proyecto(ana)
    contenido = (FIXTURES / "utf8.csv").read_bytes()

    r = _subir(ana, proyecto["id"], contenido)

    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["estado"] == "subido"
    assert cuerpo["tamano_bytes"] == len(contenido)
    assert cuerpo["deteccion"]["codificacion"] == "utf-8"
    assert cuerpo["deteccion"]["columnas"][0]["nombre"] == "cliente_id"


def test_subir_archivo_muy_grande_responde_413(ana) -> None:
    proyecto = _crear_proyecto(ana)
    contenido = b"a" * (2 * 1024 * 1024)  # MAX_CSV_MB=1 en el fixture `app`

    r = _subir(ana, proyecto["id"], contenido)

    assert r.status_code == 413
    assert r.json()["codigo"] == "archivo_muy_grande"


def test_subir_a_proyecto_de_otra_empresa_404(ana, beto) -> None:
    proyecto_de_ana = _crear_proyecto(ana)

    r = _subir(beto, proyecto_de_ana["id"], b"a,b\n1,2\n")

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


def test_listar_datasets_de_un_proyecto(ana) -> None:
    proyecto = _crear_proyecto(ana)
    _subir(ana, proyecto["id"], b"a,b\n1,2\n")
    _subir(ana, proyecto["id"], b"c,d\n3,4\n")

    r = ana.get(f"/proyectos/{proyecto['id']}/datasets")

    assert r.status_code == 200
    assert len(r.json()) == 2


def test_otra_empresa_no_ve_los_datasets_del_proyecto(ana, beto) -> None:
    proyecto_de_ana = _crear_proyecto(ana)
    _subir(ana, proyecto_de_ana["id"], b"a,b\n1,2\n")

    r = beto.get(f"/proyectos/{proyecto_de_ana['id']}/datasets")

    assert r.status_code == 404


def test_obtener_dataset(ana) -> None:
    proyecto = _crear_proyecto(ana)
    creado = _subir(ana, proyecto["id"], b"a,b\n1,2\n").json()

    r = ana.get(f"/datasets/{creado['id']}")

    assert r.status_code == 200
    assert r.json() == creado


def test_otra_empresa_no_ve_el_dataset_aunque_adivine_el_id(ana, beto) -> None:
    proyecto = _crear_proyecto(ana)
    creado = _subir(ana, proyecto["id"], b"a,b\n1,2\n").json()

    r = beto.get(f"/datasets/{creado['id']}")

    assert r.status_code == 404
    assert r.json()["codigo"] == "no_encontrado"


def test_dataset_inexistente_responde_404(ana) -> None:
    r = ana.get(f"/datasets/{uuid.uuid4()}")

    assert r.status_code == 404


def test_borrar_dataset_borra_archivos_y_fila(ana, db, tmp_path) -> None:
    proyecto = _crear_proyecto(ana)
    creado = _subir(ana, proyecto["id"], b"a,b\n1,2\n").json()
    dataset_id = uuid.UUID(creado["id"])
    empresa_id = db.get(Dataset, dataset_id).empresa_id
    carpeta = tmp_path / str(empresa_id) / str(dataset_id)
    assert carpeta.exists()

    r = ana.delete(f"/datasets/{creado['id']}", headers=_csrf(ana))

    assert r.status_code == 204
    assert not carpeta.exists()
    db.expire_all()
    assert db.get(Dataset, uuid.UUID(creado["id"])) is None


def test_otra_empresa_no_puede_borrar_el_dataset(ana, beto) -> None:
    proyecto = _crear_proyecto(ana)
    creado = _subir(ana, proyecto["id"], b"a,b\n1,2\n").json()

    r = beto.delete(f"/datasets/{creado['id']}", headers=_csrf(beto))

    assert r.status_code == 404


def test_borrar_proyecto_de_ana_no_afecta_datasets_de_beto(ana, beto, db) -> None:
    proyecto_ana = _crear_proyecto(ana)
    proyecto_beto = _crear_proyecto(beto)
    _subir(ana, proyecto_ana["id"], b"a,b\n1,2\n")
    creado_beto = _subir(beto, proyecto_beto["id"], b"a,b\n1,2\n").json()

    r = ana.delete(f"/proyectos/{proyecto_ana['id']}", headers=_csrf(ana))

    assert r.status_code == 204
    assert db.get(Dataset, uuid.UUID(creado_beto["id"])) is not None
    assert db.get(Proyecto, uuid.UUID(proyecto_beto["id"])) is not None
