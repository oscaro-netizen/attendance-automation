from cryptography.fernet import Fernet
from app.core.config import settings
import os

# For a production app, the ENCRYPTION_KEY should be managed by a secrets manager
# and not just an environment variable, but this is a significant improvement over plaintext.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Generate a key for demonstration purposes if not provided
    # In production, this MUST be set and persistent
    ENCRYPTION_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_password(password: str) -> str:
    """Encrypts a plaintext password."""
    return cipher_suite.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Decrypts an encrypted password."""
    return cipher_suite.decrypt(encrypted_password.encode()).decode()
