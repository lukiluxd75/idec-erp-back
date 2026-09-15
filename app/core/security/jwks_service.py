import requests
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.security.exceptions import (
    AuthProviderUnavailableException,
    TokenVerificationException,
)


class JWKSService:
    """
    Infrastructure service that fetches, caches in memory,
    and retrieves public keys (JWKS) from the Keycloak server.
    """

    def __init__(self, jwks_url: Optional[str] = None, timeout: Optional[int] = None):
        self._jwks_url = jwks_url or settings.JWKS_URL
        self._timeout = timeout or settings.KEYCLOAK_TIMEOUT_SECONDS
        self._cache: Optional[Dict[str, Any]] = None

    def fetch_jwks(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Download and cache public keys from the Keycloak JWKS endpoint.
        """
        if self._cache is None or force_refresh:
            try:
                response = requests.get(self._jwks_url, timeout=self._timeout)
                response.raise_for_status()
                self._cache = response.json()
            except requests.RequestException as exc:
                raise AuthProviderUnavailableException(
                    f"No se pudo obtener las claves públicas de Keycloak desde {self._jwks_url}: {exc}"
                ) from exc

        return self._cache

    def get_signing_key(self, kid: Optional[str]) -> Dict[str, Any]:
        """
        Find and return the RSA signing key for the given Key ID ('kid').
        If not found on the first pass, refresh the cache once in case of key rotation.
        """
        if not kid:
            raise TokenVerificationException("El encabezado del token no contiene 'kid'")

        jwks = self.fetch_jwks()
        key = self._find_key_in_jwks(jwks, kid)

        # If not found, try refreshing the cache once
        if key is None:
            jwks = self.fetch_jwks(force_refresh=True)
            key = self._find_key_in_jwks(jwks, kid)

        if key is None:
            raise TokenVerificationException(
                f"No se encontró la clave de firma correspondiente para kid='{kid}' en Keycloak"
            )

        return key

    @staticmethod
    def _find_key_in_jwks(jwks: Dict[str, Any], kid: str) -> Optional[Dict[str, Any]]:
        keys = jwks.get("keys", [])
        return next((k for k in keys if k.get("kid") == kid), None)
