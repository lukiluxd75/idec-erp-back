import unittest
from unittest.mock import patch, MagicMock
from jose import jwt

from app.core.security.jwks_service import JWKSService
from app.domains.seguridad.infrastructure.keycloak_adapter import KeycloakAdapter
from app.core.security.exceptions import (
    InvalidCredentialsException,
    TokenVerificationException,
    TokenExpiredException,
    AuthProviderUnavailableException,
)


class TestKeycloakAdapter(unittest.TestCase):
    def setUp(self):
        self.mock_jwks_service = MagicMock(spec=JWKSService)
        self.adapter = KeycloakAdapter(jwks_service=self.mock_jwks_service)

    @patch("requests.post")
    def test_authenticate_domain_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token_domain_abc",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        token = self.adapter.authenticate_domain("gamc.gob.bo")

        self.assertEqual(token.access_token, "token_domain_abc")
        self.assertEqual(token.domain, "gamc.gob.bo")

    @patch("requests.post")
    def test_authenticate_credentials_invalid(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_grant", "error_description": "Invalid user credentials"}
        mock_post.return_value = mock_response

        with self.assertRaises(InvalidCredentialsException) as ctx:
            self.adapter.authenticate_credentials("wrong_user", "bad_pass")
        self.assertIn("Credenciales incorrectas", str(ctx.exception))

    @patch("requests.post")
    def test_authenticate_credentials_direct_access_grants_disabled(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "unauthorized_client",
            "error_description": "Client not allowed for direct access grants"
        }
        mock_post.return_value = mock_response

        with self.assertRaises(InvalidCredentialsException) as ctx:
            self.adapter.authenticate_credentials("user", "pass")
        self.assertIn("Direct access grants", str(ctx.exception))

    @patch("requests.post")
    def test_authenticate_credentials_invalid_client_secret(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "invalid_client",
            "error_description": "Invalid client secret"
        }
        mock_post.return_value = mock_response

        with self.assertRaises(InvalidCredentialsException) as ctx:
            self.adapter.authenticate_credentials("user", "pass")
        self.assertIn("Credenciales de cliente Keycloak inválidas", str(ctx.exception))

    @patch("requests.post")
    def test_authenticate_domain_service_account_disabled(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "unauthorized_client",
            "error_description": "Client not enabled to retrieve service account"
        }
        mock_post.return_value = mock_response

        with self.assertRaises(InvalidCredentialsException) as ctx:
            self.adapter.authenticate_domain("gamc.gob.bo")
        self.assertIn("Service accounts roles", str(ctx.exception))

    @patch("jose.jwt.get_unverified_header")
    @patch("jose.jwt.decode")
    def test_verify_token_success(self, mock_decode, mock_header):
        mock_header.return_value = {"kid": "key_123"}
        self.mock_jwks_service.get_signing_key.return_value = {"kid": "key_123", "n": "..."}
        mock_decode.return_value = {
            "preferred_username": "carlos",
            "email": "carlos@gamc.gob.bo",
            "realm_access": {"roles": ["gis_user"]},
            "azp": "app-erp",
            "sub": "uuid-12345",
        }

        profile = self.adapter.verify_token("raw_jwt_str")

        self.assertEqual(profile.username, "carlos")
        self.assertEqual(profile.email, "carlos@gamc.gob.bo")
        self.assertEqual(profile.roles, ["gis_user"])
        self.assertEqual(profile.client_id, "app-erp")


if __name__ == "__main__":
    unittest.main()
