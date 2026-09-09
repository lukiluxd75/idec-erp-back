from abc import ABC, abstractmethod
from app.domains.seguridad.domain.entities.token import AuthToken
from app.domains.seguridad.domain.entities.user import UserProfile


class AuthProviderPort(ABC):
    """
    Puerto (interfaz abstracta) que define las operaciones de autenticación
    y validación de tokens frente a un proveedor de identidad (IdP).
    """

    @abstractmethod
    def authenticate_domain(self, domain: str) -> AuthToken:
        """
        Valida el dominio institucional y obtiene el token de acceso correspondiente.
        """
        pass

    @abstractmethod
    def authenticate_credentials(self, username: str, password: str) -> AuthToken:
        """
        Autentica un usuario con credenciales directas (Resource Owner Password Credentials).
        """
        pass

    @abstractmethod
    def refresh_token(self, refresh_token: str) -> AuthToken:
        """
        Solicita un nuevo access_token a partir de un refresh_token vigente.
        """
        pass

    @abstractmethod
    def verify_token(self, token: str) -> UserProfile:
        """
        Valida criptográficamente la firma del token JWT y retorna el perfil del usuario.
        """
        pass

    @abstractmethod
    def change_password(self, access_token: str, current_password: str, new_password: str) -> None:
        """
        Cambia la contraseña del usuario dueño del access_token (self-service).
        El proveedor de identidad valida `current_password` internamente.
        """
        pass
