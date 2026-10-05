import logging
import ssl

from ldap3 import Connection, Server, Tls, MODIFY_REPLACE
from ldap3.core.exceptions import LDAPException

from app.core.config import settings
from app.core.security.exceptions import (
    DirectoryProviderUnavailableException,
    InvalidCredentialsException,
)
from app.domains.security.domain.ports.directory_provider_port import DirectoryProviderPort

logger = logging.getLogger("uvicorn.error")


class ZentyalLdapAdapter(DirectoryProviderPort):
    """
    Infrastructure adapter implementing DirectoryProviderPort by writing
    directly against the Zentyal directory (Samba4 AD-DC) via LDAPS, using an
    administrative service account (bind DN) configured by environment.
    """

    def __init__(self):
        self._host = settings.ZENTYAL_LDAP_HOST
        self._port = settings.ZENTYAL_LDAP_PORT
        self._use_ssl = settings.ZENTYAL_LDAP_USE_SSL
        self._verify_cert = settings.ZENTYAL_LDAP_VERIFY_CERT
        self._bind_dn = settings.ZENTYAL_LDAP_BIND_DN
        self._bind_password = settings.ZENTYAL_LDAP_BIND_PASSWORD
        self._search_base_dn = settings.ZENTYAL_LDAP_SEARCH_BASE_DN
        self._user_search_filter = settings.ZENTYAL_LDAP_USER_SEARCH_FILTER
        self._timeout = settings.ZENTYAL_LDAP_TIMEOUT_SECONDS

    def _build_server(self) -> Server:
        tls_config = None
        if self._use_ssl:
            tls_config = Tls(
                validate=ssl.CERT_REQUIRED if self._verify_cert else ssl.CERT_NONE,
                version=ssl.PROTOCOL_TLSv1_2,
            )
        return Server(
            self._host,
            port=self._port,
            use_ssl=self._use_ssl,
            tls=tls_config,
            connect_timeout=self._timeout,
        )

    def reset_password(self, username: str, new_password: str) -> None:
        if not self._host or not self._bind_dn:
            raise DirectoryProviderUnavailableException(
                "La integración con el directorio Zentyal no está configurada "
                "(faltan ZENTYAL_LDAP_HOST / ZENTYAL_LDAP_BIND_DN en el entorno)."
            )

        server = self._build_server()

        try:
            conn = Connection(
                server,
                user=self._bind_dn,
                password=self._bind_password,
                auto_bind=True,
            )
        except LDAPException as exc:
            logger.error(f"No se pudo conectar/autenticar contra Zentyal: {exc}")
            raise DirectoryProviderUnavailableException(
                "No se pudo contactar al directorio Zentyal."
            ) from exc

        try:
            search_filter = self._user_search_filter.format(username=username)
            found = conn.search(
                search_base=self._search_base_dn,
                search_filter=search_filter,
                attributes=["distinguishedName"],
            )

            if not found or not conn.entries:
                logger.error(f"Usuario '{username}' no encontrado en Zentyal con filtro {search_filter}")
                raise InvalidCredentialsException(
                    f"No se encontró el usuario '{username}' en el directorio institucional."
                )

            user_dn = conn.entries[0].entry_dn

            # Active Directory/Samba4 requires the password in double quotes and UTF-16-LE encoded
            encoded_password = f'"{new_password}"'.encode("utf-16-le")

            success = conn.modify(
                user_dn,
                {"unicodePwd": [(MODIFY_REPLACE, [encoded_password])]},
            )

            if not success:
                description = conn.result.get("description", "error desconocido")
                logger.error(f"Zentyal rechazó el cambio de contraseña para '{username}' ({user_dn}): {conn.result}")
                raise InvalidCredentialsException(
                    f"No se pudo actualizar la contraseña en el directorio: {description}"
                )
        finally:
            conn.unbind()
