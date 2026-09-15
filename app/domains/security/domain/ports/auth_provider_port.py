from abc import ABC, abstractmethod
from app.domains.security.domain.entities.token import AuthToken
from app.domains.security.domain.entities.user import UserProfile


class AuthProviderPort(ABC):
    """
    Port (abstract interface) defining authentication and token-validation
    operations against an identity provider (IdP).
    """

    @abstractmethod
    def authenticate_domain(self, domain: str) -> AuthToken:
        """
        Validate the institutional domain and obtain the corresponding access token.
        """
        pass

    @abstractmethod
    def authenticate_credentials(self, username: str, password: str) -> AuthToken:
        """
        Authenticate a user with direct credentials (Resource Owner Password Credentials).
        """
        pass

    @abstractmethod
    def refresh_token(self, refresh_token: str) -> AuthToken:
        """
        Request a new access_token from a valid refresh_token.
        """
        pass

    @abstractmethod
    def verify_token(self, token: str) -> UserProfile:
        """
        Cryptographically validate the JWT signature and return the user profile.
        """
        pass

    @abstractmethod
    def change_password(self, access_token: str, current_password: str, new_password: str) -> None:
        """
        Change the password of the access_token owner (self-service).
        The identity provider validates `current_password` internally.
        """
        pass
