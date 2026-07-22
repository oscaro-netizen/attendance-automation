"""
Symmetric encryption for MarsOS credentials stored in the `employees` table.

The key comes from `settings.ENCRYPTION_KEY` (a required setting) rather than
being read from the environment directly, so there is a single source of truth
for configuration. A missing or malformed key is a hard startup failure: the
previous behaviour of silently generating an ephemeral key meant every stored
password decrypted into garbage at runtime instead of failing loudly at boot.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_KEY_HELP = (
    "ENCRYPTION_KEY must be a valid 32-byte url-safe base64 Fernet key. "
    "Generate one with: "
    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
)


class CredentialDecryptionError(Exception):
    """Raised when a stored credential cannot be decrypted with the configured key."""


def _build_cipher() -> Fernet:
    try:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:  # malformed / wrong-length key
        raise RuntimeError(_KEY_HELP) from exc


cipher_suite = _build_cipher()


def encrypt_password(password: str) -> str:
    """Encrypts a plaintext password."""
    return cipher_suite.encrypt(password.encode()).decode()


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypts a stored credential.

    Raises `CredentialDecryptionError` if the ciphertext was produced with a
    different key (e.g. ENCRYPTION_KEY was rotated without re-encrypting rows),
    so callers can report a specific failure instead of treating it as an
    absent password.
    """
    try:
        return cipher_suite.decrypt(encrypted_password.encode()).decode()
    except (InvalidToken, TypeError, ValueError) as exc:
        raise CredentialDecryptionError(
            "Stored credential could not be decrypted with the configured ENCRYPTION_KEY"
        ) from exc
