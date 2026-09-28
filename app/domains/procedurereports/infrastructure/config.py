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

    db_server: str = "172.16.67.100,1433"
    db_name: str = "catastro"
    db_user: str = "jPoloA"
    db_password: str = ""
    db_driver: str = "ODBC Driver 17 for SQL Server"
    unit_id: int = Field(102116, validation_alias="UNIDAD_ID")
    unit_name: str = Field("AREA TECNICA CARTOGRAFIA", validation_alias="UNIDAD_NOMBRE")
    central_district_id: int = Field(7, validation_alias="COMUNA_CENTRAL_ID")
    cors_origins: str = "*"
    cors_origin_regex: str = r"https?://([a-zA-Z0-9-]+\.)*catastrocbba\.com(:\d+)?"


settings = Settings()


def cors_origin_list() -> list[str]:
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    return origins or ["*"]
