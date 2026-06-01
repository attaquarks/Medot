"""Envelope-encryption round-trip + master-key rotation (requires `cryptography`)."""
import pytest

pytest.importorskip("cryptography")
from cryptography.fernet import Fernet  # noqa: E402

from aia.security.crypto import CredentialCipher  # noqa: E402


def test_encrypt_decrypt_roundtrip():
    cipher = CredentialCipher(Fernet.generate_key())
    secret = '{"access_token": "ya29.super-secret", "refresh_token": "1//refresh"}'
    blob = cipher.encrypt(secret)
    assert secret not in blob               # ciphertext, not plaintext
    assert "." in blob                       # wrapped_key.ciphertext layout
    assert cipher.decrypt(blob) == secret


def test_each_row_uses_a_fresh_data_key():
    cipher = CredentialCipher(Fernet.generate_key())
    a = cipher.encrypt("same-plaintext")
    b = cipher.encrypt("same-plaintext")
    assert a != b                            # random per-row data key


def test_master_key_rotation_preserves_secret():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    cipher = CredentialCipher(old_key)
    blob = cipher.encrypt("token-123")
    rewrapped = cipher.rotate_master(new_key, blob)
    assert CredentialCipher(new_key).decrypt(rewrapped) == "token-123"
