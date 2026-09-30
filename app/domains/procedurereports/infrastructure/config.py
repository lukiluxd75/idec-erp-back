from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # REPORTS_DB_* -- prefixed like AVALUOS_DB_* (see core/config/settings.py) so
    # this never silently binds to the main app's own DB_USER/DB_PASSWORD/DB_NAME
    # (this is a second, unrelated SQL Server connection, read from the same .env).
    db_server: str = Field("172.16.67.100,1433", validation_alias="REPORTS_DB_SERVER")
    db_name: str = Field("catastro", validation_alias="REPORTS_DB_NAME")
    db_user: str = Field("jPoloA", validation_alias="REPORTS_DB_USER")
    db_password: str = Field("", validation_alias="REPORTS_DB_PASSWORD")
    db_driver: str = Field("ODBC Driver 17 for SQL Server", validation_alias="REPORTS_DB_DRIVER")
    unit_id: int = Field(102116, validation_alias="UNIDAD_ID")
    unit_name: str = Field("AREA TECNICA CARTOGRAFIA", validation_alias="UNIDAD_NOMBRE")
    central_district_id: int = Field(7, validation_alias="COMUNA_CENTRAL_ID")
    cors_origins: str = "*"
    cors_origin_regex: str = r"https?://([a-zA-Z0-9-]+\.)*catastrocbba\.com(:\d+)?"


settings = Settings()


def cors_origin_list() -> list[str]:
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    return origins or ["*"]
