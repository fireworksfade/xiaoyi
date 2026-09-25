import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, digest_text = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_decode(salt_text), n=2**14, r=8, p=1
        )
        return hmac.compare_digest(actual, _decode(digest_text))
    except (ValueError, TypeError):
        return False


def opaque_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet(secret_key: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str, secret_key: str) -> str:
    return _fernet(secret_key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None, secret_key: str) -> str | None:
    if not value:
        return None
    return _fernet(secret_key).decrypt(value.encode("ascii")).decode("utf-8")
