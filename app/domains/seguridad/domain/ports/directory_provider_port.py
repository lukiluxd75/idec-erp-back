from abc import ABC, abstractmethod


class DirectoryProviderPort(ABC):
    """
    Puerto (interfaz abstracta) para operaciones de escritura directa contra el
    directorio institucional (LDAP/Samba4 vía Zentyal), fuera del flujo normal
    de autenticación de Keycloak.

    Existe porque la federación LDAP de Keycloak hacia Zentyal no propaga el
    cambio de contraseña de vuelta al directorio: Keycloak sigue siendo el único
    que autentica (CLAUDE.md, Sección 5), pero es el directorio quien almacena
    la contraseña real de un usuario institucional.
    """

    @abstractmethod
    def reset_password(self, username: str, new_password: str) -> None:
        """
        Fuerza el cambio de contraseña de `username` directamente en el directorio,
        usando una cuenta de servicio con privilegios administrativos.
        No valida la contraseña actual del usuario — no es self-service.
        """
        pass
