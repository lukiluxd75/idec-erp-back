from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    """
    Global Backend system settings.
    Loads variables from environment variables and the .env file.
    """
    PROJECT_NAME: str = "Ecosistema Herramienta GIS - Backend"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api"

    # Keycloak — real values are loaded from .env (never hardcode secrets here)
    KEYCLOAK_URL: str = "https://auth.catastrocbba.com"
    KEYCLOAK_REALM: str = "alcaldia-idec"
    KEYCLOAK_CLIENT_ID: str = "app-idec"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_TIMEOUT_SECONDS: int = 20

    ZENTYAL_LDAP_HOST: str = ""
    ZENTYAL_LDAP_PORT: int = 636
    ZENTYAL_LDAP_USE_SSL: bool = True
    ZENTYAL_LDAP_VERIFY_CERT: bool = False
    ZENTYAL_LDAP_BIND_DN: str = ""
    ZENTYAL_LDAP_BIND_PASSWORD: str = ""
    ZENTYAL_LDAP_SEARCH_BASE_DN: str = "dc=catastrocbba,dc=com"
    ZENTYAL_LDAP_USER_SEARCH_FILTER: str = "(sAMAccountName={username})"
    ZENTYAL_LDAP_TIMEOUT_SECONDS: int = 10

    # CORS — comma-separated list of allowed browser origins
    FRONTEND_ORIGIN: str = "http://localhost:8060"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]

    # PostgreSQL Database
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "idec_erp"
    DATABASE_URL: Optional[str] = None

    # Connection pool and the guards asked of the server on every connection (see app/core/database/connection.py).
    DB_POOL_SIZE: int = 5
    DB_POOL_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: float = 30.0
    DB_CONNECT_TIMEOUT_SECONDS: int = 10
    # Well above the slowest real request, so it only ever reaches a transaction nobody is going to close.
    DB_IDLE_IN_TRANSACTION_TIMEOUT_MS: int = 600_000
    DB_LOCK_TIMEOUT_MS: int = 10_000

    # Construction-detection GPU engine (stays on 10.0.0.30 — ERP is only a BFF)
    DETECTION_ENGINE_URL: str = "http://10.0.0.30:8100"
    DETECTION_ENGINE_API_KEY: str = ""
    DETECTION_ENGINE_TIMEOUT_SECONDS: float = 120.0

    # Cadastral GIS of the municipality (the IDE): predios, vias.
    CADASTRAL_GIS_URL: str = "https://gs.catastrocbba.com"
    CADASTRAL_GIS_TIMEOUT_SECONDS: float = 30.0

    AVALUOS_DB_HOST: str = "localhost"
    AVALUOS_DB_PORT: str = "5432"
    AVALUOS_DB_USER: str = "postgres"
    AVALUOS_DB_PASSWORD: str = "postgres"
    AVALUOS_DB_NAME: str = "catastro_operativo"
    AVALUOS_DATABASE_URL: Optional[str] = None

    CHATBOT_OLLAMA_URL: str = ""
    CHATBOT_CHAT_MODEL: str = "gemma4:e4b"
    CHATBOT_VISION_MODEL: str = "qwen3-vl:4b"
    CHATBOT_EMBEDDING_MODEL: str = "nomic-embed-text"
    CHATBOT_CHAT_TIMEOUT_SECONDS: float = 120.0
    CHATBOT_VISION_TIMEOUT_SECONDS: float = 180.0
    CHATBOT_EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    CHATBOT_MATCH_THRESHOLD: float = 0.50
    # Tesseract OCR (document ingestion) — empty CHATBOT_TESSERACT_CMD uses whatever 'tesseract' resolves to on PATH
    CHATBOT_TESSERACT_CMD: str = ""
    CHATBOT_TESSERACT_LANG: str = "spa"

    FOLIOS_OCR_API_URL: str = "https://ocr.catastrocbba.com"
    FOLIOS_OCR_TIMEOUT_SECONDS: float = 90.0
    FOLIOS_OCR_POLL_INTERVAL_SECONDS: float = 1.5
    FOLIOS_OCR_RETRIES: int = 2
    FOLIOS_OCR_RETRY_DELAY_SECONDS: float = 3.0
    FOLIOS_CONFIDENCE_THRESHOLD: float = 0.85
    FOLIOS_OLLAMA_URL: str = ""
    FOLIOS_LLM_MODEL: str = "gemma4:e4b"
    FOLIOS_LLM_TIMEOUT_SECONDS: float = 120.0

    TAX_RECEIPT_CONFIDENCE_THRESHOLD: float = 0.85
    TAX_RECEIPT_OLLAMA_URL: str = ""
    # Empty turns the pass off and leaves the lane on its rules alone.
    TAX_RECEIPT_LLM_MODEL: str = "qwen3-vl:4b"
    TAX_RECEIPT_LLM_TIMEOUT_SECONDS: float = 45.0
    # Ceiling on the answer, so a model that keeps writing cannot hold an architect's PC either.
    TAX_RECEIPT_LLM_MAX_TOKENS: int = 1024

    FOLDER_VISION_OLLAMA_URL: str = ""
    # Vacío apaga la pasada y deja la lectura en el OCR, las reglas y el sello.
    FOLDER_VISION_MODEL: str = "qwen3-vl:4b"
    FOLDER_VISION_TIMEOUT_SECONDS: float = 60.0
    # Cuántas fotos de un documento se miran como mucho.
    FOLDER_VISION_MAX_PAGES: int = 3

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @computed_field
    @property
    def AVALUOS_SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.AVALUOS_DATABASE_URL:
            return self.AVALUOS_DATABASE_URL
        return (
            f"postgresql://{self.AVALUOS_DB_USER}:{self.AVALUOS_DB_PASSWORD}"
            f"@{self.AVALUOS_DB_HOST}:{self.AVALUOS_DB_PORT}/{self.AVALUOS_DB_NAME}"
        )

    @computed_field
    @property
    def ISSUER(self) -> str:
        return f"{self.KEYCLOAK_URL.rstrip('/')}/realms/{self.KEYCLOAK_REALM}"

    @computed_field
    @property
    def JWKS_URL(self) -> str:
        return f"{self.ISSUER}/protocol/openid-connect/certs"

    @computed_field
    @property
    def TOKEN_URL(self) -> str:
        return f"{self.ISSUER}/protocol/openid-connect/token"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
