from abc import ABC, abstractmethod


class DirectoryProviderPort(ABC):
    """
    Port (abstract interface) for direct write operations against the
    institutional directory (LDAP/Samba4 via Zentyal), outside the normal
    Keycloak authentication flow.

    Exists because Keycloak's LDAP federation to Zentyal does not propagate
    password changes back to the directory: Keycloak remains the only
    authenticator (CLAUDE.md, Section 5), but the directory stores the
    real password of an institutional user.
    """

    @abstractmethod
    def reset_password(self, username: str, new_password: str) -> None:
        """
        Force a password change for `username` directly in the directory,
        using a service account with administrative privileges.
        Does not validate the user's current password — not self-service.
        """
        pass
