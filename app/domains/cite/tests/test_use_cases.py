"""
Tests unitarios del dominio CITE.
Usan mocks del repositorio — sin base de datos real.
Ejecutar con: pytest app/domains/cite/tests/ -v
"""
from unittest.mock import MagicMock, patch
from datetime import date, datetime

import pytest

from app.domains.cite.application.use_cases import (
    CrearConfiguracionCiteUseCase,
    GenerarCiteUseCase,
)
from app.domains.cite.domain.entities import (
    Area,
    ConfiguracionCite,
    DocumentoCite,
    Gestion,
)
from app.domains.cite.domain.exceptions import (
    AreaNotFoundException,
    CiteGenerationException,
    ConfiguracionNotFoundException,
    GestionInactivaException,
    GestionNotFoundException,
    PrefijoDuplicadoException,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _gestion(activa: bool = True) -> Gestion:
    return Gestion(
        id_gestion=1,
        anio=2026,
        fecha_inicial=date(2026, 1, 1),
        fecha_final=date(2026, 12, 31),
        activa=activa,
    )


def _area() -> Area:
    return Area(id_area=5, nombre="Dep. Gestión Catastral", tipo="Direccion")


def _config(activo: bool = True, gestion_activa: bool = True) -> ConfiguracionCite:
    return ConfiguracionCite(
        id_configuracion=10,
        id_area=5,
        id_gestion=1,
        prefijo="DGC",
        activo=activo,
        gestion_activa=gestion_activa,
    )


def _documento(correlativo: int = 1) -> DocumentoCite:
    cite = f"DGC-{correlativo:03d}"
    return DocumentoCite(
        id_documento=correlativo,
        id_configuracion=10,
        prefijo="DGC",
        correlativo=correlativo,
        codigo_cite_completo=cite,
        fecha_generacion=datetime(2026, 10, 2, 12, 0, 0),
        referencia="Solicitud inspección predio",
        id_funcionario_remitente=99,
    )


# ── CrearConfiguracionCiteUseCase ─────────────────────────────────────────────

class TestCrearConfiguracionCiteUseCase:

    def _repo(self, **overrides):
        repo = MagicMock()
        repo.get_gestion_by_id.return_value = _gestion()
        repo.get_area_by_id.return_value = _area()
        repo.prefijo_existe_en_gestion.return_value = False
        repo.crear_configuracion.return_value = _config()
        for k, v in overrides.items():
            setattr(repo, k, v)
        return repo

    def test_crea_configuracion_exitosa(self):
        repo = self._repo()
        resultado = CrearConfiguracionCiteUseCase(repo).execute(5, 1, "DGC")
        assert resultado.prefijo == "DGC"
        repo.crear_configuracion.assert_called_once_with(id_area=5, id_gestion=1, prefijo="DGC")

    def test_normaliza_prefijo_a_mayusculas(self):
        repo = self._repo()
        CrearConfiguracionCiteUseCase(repo).execute(5, 1, "dgc")
        repo.crear_configuracion.assert_called_once_with(id_area=5, id_gestion=1, prefijo="DGC")

    def test_falla_si_gestion_no_existe(self):
        repo = self._repo()
        repo.get_gestion_by_id.return_value = None
        with pytest.raises(GestionNotFoundException):
            CrearConfiguracionCiteUseCase(repo).execute(5, 999, "DGC")

    def test_falla_si_gestion_inactiva(self):
        repo = self._repo()
        repo.get_gestion_by_id.return_value = _gestion(activa=False)
        with pytest.raises(GestionInactivaException):
            CrearConfiguracionCiteUseCase(repo).execute(5, 1, "DGC")

    def test_falla_si_area_no_existe(self):
        repo = self._repo()
        repo.get_area_by_id.return_value = None
        with pytest.raises(AreaNotFoundException):
            CrearConfiguracionCiteUseCase(repo).execute(999, 1, "DGC")

    def test_falla_si_prefijo_duplicado(self):
        repo = self._repo()
        repo.prefijo_existe_en_gestion.return_value = True
        with pytest.raises(PrefijoDuplicadoException):
            CrearConfiguracionCiteUseCase(repo).execute(5, 1, "DGC")


# ── GenerarCiteUseCase ────────────────────────────────────────────────────────

class TestGenerarCiteUseCase:

    def _repo(self, **overrides):
        repo = MagicMock()
        repo.get_configuracion_by_id.return_value = _config()
        repo.generar_cite.return_value = _documento(correlativo=1)
        for k, v in overrides.items():
            setattr(repo, k, v)
        return repo

    def test_genera_cite_exitoso(self):
        repo = self._repo()
        doc = GenerarCiteUseCase(repo).execute(10, "Solicitud inspección predio", 99)
        assert doc.codigo_cite_completo == "DGC-001"
        assert doc.correlativo == 1
        repo.generar_cite.assert_called_once_with(
            id_configuracion=10,
            referencia="Solicitud inspección predio",
            id_funcionario_remitente=99,
        )

    def test_correlativos_incrementales(self):
        """El repositorio es el responsable de incrementar, pero el use case
        no debe interferir: verificamos que pasa el id_configuracion correcto."""
        repo = self._repo()
        repo.generar_cite.return_value = _documento(correlativo=15)
        doc = GenerarCiteUseCase(repo).execute(10, "Ref", 99)
        assert doc.correlativo == 15
        assert doc.codigo_cite_completo == "DGC-015"

    def test_falla_si_configuracion_no_existe(self):
        repo = self._repo()
        repo.get_configuracion_by_id.return_value = None
        with pytest.raises(ConfiguracionNotFoundException):
            GenerarCiteUseCase(repo).execute(999, "Ref", 99)

    def test_falla_si_gestion_inactiva(self):
        repo = self._repo()
        repo.get_configuracion_by_id.return_value = _config(gestion_activa=False)
        with pytest.raises(GestionInactivaException):
            GenerarCiteUseCase(repo).execute(10, "Ref", 99)

    def test_falla_si_configuracion_inactiva(self):
        repo = self._repo()
        repo.get_configuracion_by_id.return_value = _config(activo=False)
        with pytest.raises(ConfiguracionNotFoundException):
            GenerarCiteUseCase(repo).execute(10, "Ref", 99)

    def test_propaga_cite_generation_exception(self):
        repo = self._repo()
        repo.generar_cite.side_effect = CiteGenerationException("Conflicto de correlativo")
        with pytest.raises(CiteGenerationException, match="Conflicto"):
            GenerarCiteUseCase(repo).execute(10, "Ref", 99)
