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

    # Zentyal (LDAP/Samba4 AD-DC) — institutional directory integration
    # real values are loaded from .env (never hardcode secrets here)
    ZENTYAL_LDAP_HOST: str = ""
    ZENTYAL_LDAP_PORT: int = 636
    ZENTYAL_LDAP_USE_SSL: bool = True
    ZENTYAL_LDAP_VERIFY_CERT: bool = False
    ZENTYAL_LDAP_BIND_DN: str = ""
    ZENTYAL_LDAP_BIND_PASSWORD: str = ""
    # Base DN and search filter to resolve the real user DN before writing
    # (`cn` almost never matches the login username in AD/Samba4 — do not build the DN by hand)
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

    # Construction-detection GPU engine (stays on 10.0.0.30 — ERP is only a BFF)
    DETECTION_ENGINE_URL: str = "http://10.0.0.30:8100"
    DETECTION_ENGINE_API_KEY: str = ""
    DETECTION_ENGINE_TIMEOUT_SECONDS: float = 120.0

    # Appraisal-review domain — read-mostly connection to catastro_operativo, the
    # external Avalúos system's own DB (never idec_erp; separate server/login)
    AVALUOS_DB_HOST: str = "localhost"
    AVALUOS_DB_PORT: str = "5432"
    AVALUOS_DB_USER: str = "postgres"
    AVALUOS_DB_PASSWORD: str = "postgres"
    AVALUOS_DB_NAME: str = "catastro_operativo"
    AVALUOS_DATABASE_URL: Optional[str] = None

    # Chatbot domain — external Ollama host (not this server; empty means "not
    # configured yet", which the chat engine turns into a 503 instead of trying
    # to connect anywhere)
    CHATBOT_OLLAMA_URL: str = ""
    CHATBOT_CHAT_MODEL: str = "gemma4:e4b"
    CHATBOT_VISION_MODEL: str = "qwen3-vl:4b"
    CHATBOT_EMBEDDING_MODEL: str = "nomic-embed-text"
    CHATBOT_CHAT_TIMEOUT_SECONDS: float = 120.0
    CHATBOT_VISION_TIMEOUT_SECONDS: float = 180.0
    CHATBOT_EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    CHATBOT_MATCH_THRESHOLD: float = 0.50
    # Tesseract OCR (document ingestion) — empty CHATBOT_TESSERACT_CMD uses
    # whatever 'tesseract' resolves to on PATH
    CHATBOT_TESSERACT_CMD: str = ""
    CHATBOT_TESSERACT_LANG: str = "spa"

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
