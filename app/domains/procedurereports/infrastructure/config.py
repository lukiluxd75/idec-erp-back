from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", _BACKEND_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # REPORTS_DB_* -- prefixed like AVALUOS_DB_* (see core/config/settings.py) so
    # this never silently binds to the main app's own DB_USER/DB_PASSWORD/DB_NAME
    # (this is a second, unrelated SQL Server connection, read from the same .env).
    #
    # Los defaults quedan vacíos a propósito: antes traían el servidor y el
    # usuario reales de producción escritos en el código, lo que publicaba esa
    # infraestructura en el repositorio y contradecía la regla de
    # core/config/settings.py ("never hardcode secrets here"). No se pierde nada:
    # connection_string() (ver db.py) ya exige los cuatro valores y falla con un
    # mensaje claro si falta alguno, así que estos defaults nunca fueron usables
    # por sí solos. Los valores van en el .env del backend.
    db_server: str = Field("", validation_alias="REPORTS_DB_SERVER")
    db_name: str = Field("catastro", validation_alias="REPORTS_DB_NAME")
    db_user: str = Field("", validation_alias="REPORTS_DB_USER")
    db_password: str = Field("", validation_alias="REPORTS_DB_PASSWORD")
    # Empty = auto-detect (FreeTDS on Linux, ODBC 17/18 on Windows when installed).
    db_driver: str = Field("", validation_alias="REPORTS_DB_DRIVER")
    db_tds_version: str = Field("7.4", validation_alias="REPORTS_DB_TDS_VERSION")
    db_encrypt: bool = Field(False, validation_alias="REPORTS_DB_ENCRYPT")
    unit_id: int = Field(102116, validation_alias="UNIDAD_ID")
    unit_name: str = Field("AREA TECNICA CARTOGRAFIA", validation_alias="UNIDAD_NOMBRE")
    central_district_id: int = Field(7, validation_alias="COMUNA_CENTRAL_ID")
    cors_origins: str = "*"
    cors_origin_regex: str = r"https?://([a-zA-Z0-9-]+\.)*catastrocbba\.com(:\d+)?"


settings = Settings()


def cors_origin_list() -> list[str]:
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    return origins or ["*"]
