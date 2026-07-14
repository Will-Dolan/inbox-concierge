import base64
import hashlib

from cryptography.fernet import Fernet

from core.config import get_settings


def _derive_key() -> bytes:
    settings = get_settings()
    key_material = settings.token_encryption_key or settings.session_secret
    digest = hashlib.sha256(key_material.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    return Fernet(_derive_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return Fernet(_derive_key()).decrypt(ciphertext.encode()).decode()
