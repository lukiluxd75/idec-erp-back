import requests
from typing import Optional, Dict, Any
from jose import jwt

from app.core.config import settings
from app.domains.seguridad.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.seguridad.domain.entities.token import AuthToken
from app.domains.seguridad.domain.entities.user import UserProfile
from app.core.security.exceptions import (
    InvalidCredentialsException,
    TokenVerificationException,
    TokenExpiredException,
    AuthProviderUnavailableException,
)
from app.core.security.jwks_service import JWKSService


class KeycloakAdapter(AuthProviderPort):
    """
    Adaptador de infraestructura que implementa AuthProviderPort
    para la integración con el servidor OpenID Connect / Keycloak.
    """

    def __init__(self, jwks_service: Optional[JWKSService] = None):
        self._jwks_service = jwks_service or JWKSService()
        self._token_url = settings.TOKEN_URL
        self._issuer = settings.ISSUER
        self._client_id = settings.KEYCLOAK_CLIENT_ID
        self._client_secret = settings.KEYCLOAK_CLIENT_SECRET
        self._timeout = settings.KEYCLOAK_TIMEOUT_SECONDS

    def _handle_token_error_response(self, response: requests.Response, context: str = "credenciales") -> None:
        """
        Analiza la respuesta de error de Keycloak y levanta una excepción con un mensaje claro y descriptivo.
        """
        try:
            error_data = response.json()
            error = error_data.get("error", "")
            error_desc = error_data.get("error_description", "")
        except Exception:
            error = ""
            error_desc = response.text

        if error == "unauthorized_client":
            if "direct access grants" in error_desc.lower():
                raise InvalidCredentialsException(
                    f"El cliente '{self._client_id}' no tiene habilitado 'Direct access grants' en Keycloak. "
                    f"En la consola de Keycloak, ve a Clients -> {self._client_id} -> Settings y activa 'Direct access grants' (o Direct Access Grants Enabled)."
                )
            elif "service account" in error_desc.lower():
                raise InvalidCredentialsException(
                    f"El cliente '{self._client_id}' no tiene habilitado 'Service accounts roles' en Keycloak. "
                    f"En la consola de Keycloak, ve a Clients -> {self._client_id} -> Settings y activa 'Service accounts roles'."
                )
            elif error_desc:
                raise InvalidCredentialsException(f"Cliente Keycloak no autorizado: {error_desc}")
            else:
                raise InvalidCredentialsException("El cliente de Keycloak no está autorizado para esta operación.")

        elif error == "invalid_client":
            raise InvalidCredentialsException(
                f"Credenciales de cliente Keycloak inválidas. Verifique 'KEYCLOAK_CLIENT_ID' y 'KEYCLOAK_CLIENT_SECRET' en el archivo .env ({error_desc or 'Client Secret incorrecto'})."
            )

        elif error == "invalid_grant":
            if "not fully set up" in error_desc.lower():
                raise InvalidCredentialsException(
                    "La cuenta de usuario requiere acciones adicionales en Keycloak (p. ej., actualización de contraseña o verificación de correo)."
                )
            elif "disabled" in error_desc.lower():
                raise InvalidCredentialsException("El usuario está deshabilitado en Keycloak.")
            elif "invalid user credentials" in error_desc.lower():
                raise InvalidCredentialsException("Credenciales incorrectas (usuario o contraseña inválidos).")
            elif error_desc:
                raise InvalidCredentialsException(f"Credenciales incorrectas: {error_desc}")
            else:
                raise InvalidCredentialsException("Credenciales incorrectas.")

        elif error_desc:
            raise InvalidCredentialsException(f"Error de autenticación con Keycloak: {error_desc}")
        else:
            raise InvalidCredentialsException(
                f"Error al autenticar con Keycloak (código HTTP {response.status_code})"
            )

    def _request_token_with_client_credentials(self) -> Dict[str, Any]:
        """Solicita un token usando el flujo Client Credentials."""
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret

        try:
            response = requests.post(self._token_url, data=data, timeout=self._timeout)
        except requests.RequestException as exc:
            raise AuthProviderUnavailableException("No se pudo contactar al servidor Keycloak") from exc

        if response.status_code == 200:
            return response.json()

        self._handle_token_error_response(response, context="client_credentials")
        raise InvalidCredentialsException("Error al autenticar el cliente con Keycloak")

    def authenticate_domain(self, domain: str) -> AuthToken:
        """
        Valida el dominio y obtiene el token de acceso correspondiente mediante Keycloak.
        """
        token_data = self._request_token_with_client_credentials()
        return AuthToken(
            access_token=token_data.get("access_token", ""),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in"),
            refresh_token=token_data.get("refresh_token"),
            refresh_expires_in=token_data.get("refresh_expires_in"),
            scope=token_data.get("scope"),
            domain=domain,
            raw_payload=token_data,
        )

    def authenticate_credentials(self, username: str, password: str) -> AuthToken:
        """
        Solicita un token a Keycloak usando Resource Owner Password Credentials (Direct Access Grant).
        """
        data = {
            "grant_type": "password",
            "client_id": self._client_id,
            "username": username,
            "password": password,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret

        try:
            response = requests.post(self._token_url, data=data, timeout=self._timeout)
        except requests.RequestException as exc:
            raise AuthProviderUnavailableException("No se pudo contactar a Keycloak") from exc

        if response.status_code == 200:
            token_data = response.json()
            return AuthToken(
                access_token=token_data.get("access_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                refresh_expires_in=token_data.get("refresh_expires_in"),
                scope=token_data.get("scope"),
                raw_payload=token_data,
            )

        self._handle_token_error_response(response, context="password")
        raise InvalidCredentialsException("Credenciales incorrectas")

    def refresh_token(self, refresh_token: str) -> AuthToken:
        """
        Solicita un nuevo access_token a Keycloak usando el grant_type 'refresh_token'.
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": refresh_token,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret

        try:
            response = requests.post(self._token_url, data=data, timeout=self._timeout)
        except requests.RequestException as exc:
            raise AuthProviderUnavailableException("No se pudo contactar a Keycloak") from exc

        if response.status_code == 200:
            token_data = response.json()
            return AuthToken(
                access_token=token_data.get("access_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                refresh_expires_in=token_data.get("refresh_expires_in"),
                scope=token_data.get("scope"),
                raw_payload=token_data,
            )

        self._handle_token_error_response(response, context="refresh_token")
        raise InvalidCredentialsException("No se pudo renovar la sesión")

    def verify_token(self, token: str) -> UserProfile:
        """
        Valida el JWT emitido por Keycloak mediante su firma pública JWKS.
        """
        if not token:
            raise TokenVerificationException("Token vacío o no proporcionado")

        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise TokenVerificationException("Token con formato o encabezado inválido") from exc

        kid = header.get("kid")
        signing_key = self._jwks_service.get_signing_key(kid)

        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience="account",
                issuer=self._issuer,
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredException("El token ha expirado") from exc
        except jwt.JWTClaimsError as exc:
            raise TokenVerificationException(f"Claims del token inválidos: {exc}") from exc
        except Exception as exc:
            raise TokenVerificationException(f"Token inválido: {exc}") from exc

        return self._map_payload_to_user_profile(payload)

    def change_password(self, access_token: str, current_password: str, new_password: str) -> None:
        """
        Cambia la contraseña vía la Account REST API de Keycloak (`/realms/{realm}/account/credentials/password`).
        Es self-service: Keycloak valida `current_password` usando el propio access_token del usuario,
        sin requerir credenciales de administrador ni un client con Service accounts habilitado.
        """
        url = f"{self._issuer}/account/credentials/password"

        try:
            response = requests.post(
                url,
                json={
                    "currentPassword": current_password,
                    "newPassword": new_password,
                    "confirmation": new_password,
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise AuthProviderUnavailableException("No se pudo contactar a Keycloak") from exc

        if response.status_code in (200, 204):
            return

        if response.status_code == 401:
            raise TokenExpiredException("La sesión expiró. Vuelve a iniciar sesión para cambiar la contraseña.")

        try:
            error_data = response.json()
            error_message = error_data.get("errorMessage") or error_data.get("error_description") or ""
        except Exception:
            error_message = response.text

        if "invalidPasswordExistingMessage" in error_message:
            raise InvalidCredentialsException("La contraseña actual es incorrecta.")

        if error_message:
            raise InvalidCredentialsException(f"No se pudo cambiar la contraseña: {error_message}")

        raise InvalidCredentialsException(f"No se pudo cambiar la contraseña (código HTTP {response.status_code})")

    @staticmethod
    def _map_payload_to_user_profile(payload: Dict[str, Any]) -> UserProfile:
        username = (
            payload.get("preferred_username")
            or payload.get("clientId")
            or payload.get("sub")
            or "Institucional"
        )
        email = payload.get("email") or "institucional@gamc.gob.bo"
        roles = payload.get("realm_access", {}).get("roles", [])
        client_id = payload.get("azp") or payload.get("clientId")
        sub = payload.get("sub")

        return UserProfile(
            username=username,
            email=email,
            roles=roles,
            client_id=client_id,
            sub=sub,
            claims=payload,
        )
