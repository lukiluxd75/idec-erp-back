import unittest
from unittest.mock import MagicMock

from app.domains.security.domain.entities.token import AuthToken
from app.domains.security.domain.entities.user import UserProfile
from app.domains.security.domain.entities.rbac import UserEntity
from app.domains.security.domain.exceptions import InvalidDomainException
from app.core.security.exceptions import (
    InvalidCredentialsException,
    TokenVerificationException,
)
from app.domains.security.application.dtos.auth_dto import (
    DomainLoginInputDTO,
    CredentialsLoginInputDTO,
)
from app.domains.security.application.use_cases.authenticate_domain_use_case import AuthenticateDomainUseCase
from app.domains.security.application.use_cases.authenticate_credentials_use_case import AuthenticateCredentialsUseCase
from app.domains.security.application.use_cases.verify_token_use_case import VerifyTokenUseCase
from app.domains.security.application.use_cases.sync_user_rbac_use_case import SyncUserRbacUseCase
from app.domains.security.domain.ports.auth_provider_port import AuthProviderPort
from app.domains.security.domain.ports.user_repository_port import UserRepositoryPort


class TestUseCases(unittest.TestCase):
    def setUp(self):
        self.mock_auth_provider = MagicMock(spec=AuthProviderPort)
        self.mock_user_repo = MagicMock(spec=UserRepositoryPort)

    def test_authenticate_domain_success(self):
        # Arrange
        self.mock_auth_provider.authenticate_domain.return_value = AuthToken(
            access_token="mock_token_123",
            domain="gamc.gob.bo",
        )
        use_case = AuthenticateDomainUseCase(auth_provider=self.mock_auth_provider)
        input_dto = DomainLoginInputDTO(domain="gamc.gob.bo")

        # Act
        result = use_case.execute(input_dto)

        # Assert
        self.assertEqual(result.access_token, "mock_token_123")
        self.assertEqual(result.domain, "gamc.gob.bo")
        self.assertIn("gamc.gob.bo", result.message)
        self.mock_auth_provider.authenticate_domain.assert_called_once_with("gamc.gob.bo")

    def test_authenticate_domain_empty_raises_exception(self):
        use_case = AuthenticateDomainUseCase(auth_provider=self.mock_auth_provider)
        input_dto = DomainLoginInputDTO(domain="   ")

        with self.assertRaises(InvalidDomainException):
            use_case.execute(input_dto)

    def test_authenticate_credentials_success(self):
        # Arrange
        self.mock_auth_provider.authenticate_credentials.return_value = AuthToken(
            access_token="user_access_token_xyz"
        )
        use_case = AuthenticateCredentialsUseCase(auth_provider=self.mock_auth_provider)
        input_dto = CredentialsLoginInputDTO(username="admin", password="password123")

        # Act
        result = use_case.execute(input_dto)

        # Assert
        self.assertEqual(result.access_token, "user_access_token_xyz")
        self.assertEqual(result.message, "Credenciales correctas")
        self.mock_auth_provider.authenticate_credentials.assert_called_once_with("admin", "password123")

    def test_authenticate_credentials_missing_data_raises_exception(self):
        use_case = AuthenticateCredentialsUseCase(auth_provider=self.mock_auth_provider)
        input_dto = CredentialsLoginInputDTO(username="", password="")

        with self.assertRaises(InvalidCredentialsException):
            use_case.execute(input_dto)

    def test_verify_token_success(self):
        # Arrange
        expected_profile = UserProfile(
            username="admin_user",
            email="admin@gamc.gob.bo",
            roles=["admin", "gis_operator"],
            client_id="app-erp",
        )
        self.mock_auth_provider.verify_token.return_value = expected_profile
        use_case = VerifyTokenUseCase(auth_provider=self.mock_auth_provider)

        # Act
        profile = use_case.execute("valid_jwt_token")

        # Assert
        self.assertEqual(profile.username, "admin_user")
        self.assertEqual(profile.email, "admin@gamc.gob.bo")
        self.assertIn("admin", profile.roles)
        self.mock_auth_provider.verify_token.assert_called_once_with("valid_jwt_token")

    def test_verify_token_empty_raises_exception(self):
        use_case = VerifyTokenUseCase(auth_provider=self.mock_auth_provider)

        with self.assertRaises(TokenVerificationException):
            use_case.execute("")

    def test_sync_user_rbac_use_case(self):
        # Arrange: ahora se identifica al usuario por keycloak_sub (JWT.sub), no por
        # nombre, y no se le asignan roles desde Keycloak (CLAUDE.md §5).
        self.mock_user_repo.ensure_user_exists.return_value = UserEntity(
            user_id="11111111-1111-1111-1111-111111111111",
            username="carlos",
            keycloak_sub="kc-sub-carlos",
        )
        self.mock_user_repo.get_user_permissions.return_value = ["mapas.ver", "capas.editar"]
        use_case = SyncUserRbacUseCase(user_repository=self.mock_user_repo)

        # Act
        user_entity, permissions = use_case.execute(
            keycloak_sub="kc-sub-carlos", username="carlos", email="carlos@gamc.gob.bo"
        )

        # Assert
        self.assertEqual(user_entity.username, "carlos")
        self.assertEqual(permissions, ["mapas.ver", "capas.editar"])
        self.mock_user_repo.ensure_user_exists.assert_called_once_with(
            keycloak_sub="kc-sub-carlos", username="carlos", email="carlos@gamc.gob.bo"
        )
        self.mock_user_repo.get_user_permissions.assert_called_once_with("kc-sub-carlos")


if __name__ == "__main__":
    unittest.main()
