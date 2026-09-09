from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    """
    Configuraciones globales del sistema Backend.
    Carga variables desde variables de entorno y archivo .env.
    """
    PROJECT_NAME: str = "Ecosistema Herramienta GIS - Backend"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api"

    # Keycloak — valores reales se cargan desde .env (nunca hardcodear secretos acá)
    KEYCLOAK_URL: str = "https://auth.catastrocbba.com"
    KEYCLOAK_REALM: str = "alcaldia-idec"
    KEYCLOAK_CLIENT_ID: str = "app-idec"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_TIMEOUT_SECONDS: int = 20

    # Zentyal (LDAP/Samba4 AD-DC) — integración de directorio institucional
    # valores reales se cargan desde .env (nunca hardcodear secretos acá)
    ZENTYAL_LDAP_HOST: str = ""
    ZENTYAL_LDAP_PORT: int = 636
    ZENTYAL_LDAP_USE_SSL: bool = True
    ZENTYAL_LDAP_VERIFY_CERT: bool = False
    ZENTYAL_LDAP_BIND_DN: str = ""
    ZENTYAL_LDAP_BIND_PASSWORD: str = ""
    # Base y filtro de búsqueda para resolver el DN real del usuario antes de escribir
    # (el `cn` casi nunca coincide con el username de login en AD/Samba4 — no armar el DN a mano)
    ZENTYAL_LDAP_SEARCH_BASE_DN: str = "dc=catastrocbba,dc=com"
    ZENTYAL_LDAP_USER_SEARCH_FILTER: str = "(sAMAccountName={username})"
    ZENTYAL_LDAP_TIMEOUT_SECONDS: int = 10

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:8060"

    # PostgreSQL Database
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "gis_seguridad"
    DATABASE_URL: Optional[str] = None

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

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
