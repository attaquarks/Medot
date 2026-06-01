"""Envelope encryption for credentials.

    master key (OS keychain)  ──wraps──>  per-row data key  ──encrypts──>  secret

Why envelope rather than one global key:
  * each credential row gets its own random data key (limits blast radius)
  * rotating the master key only re-wraps small data keys, not every secret
  * the master key never touches the database or any file on disk

On a laptop the master key is auto-generated on first run and stored in the OS
keychain via `keyring`. For headless/server installs set `AIA_MASTER_KEY`.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.fernet import Fernet

from ..config import get_settings

_SERVICE = "aia"
_ACCOUNT = "master_key"


def load_or_create_master_key() -> bytes:
    """Return the 32-byte urlsafe master key, creating & persisting it if absent.

    Resolution order:
      1. AIA_MASTER_KEY env (headless/server installs)
      2. OS keychain entry  (laptop installs — the normal path)
      3. generate a new key, store it in the keychain, return it
    """
    settings = get_settings()
    if settings.master_key:
        return settings.master_key.encode()

    try:
        import keyring

        existing = keyring.get_password(_SERVICE, _ACCOUNT)
        if existing:
            return existing.encode()
        key = Fernet.generate_key()
        keyring.set_password(_SERVICE, _ACCOUNT, key.decode())
        return key
    except Exception:
        # Keychain unavailable (e.g. headless container with no env key set):
        # fall back to a key file with 0600 perms so the system still runs.
        path = os.path.join(os.path.expanduser("~"), ".aia_master.key")
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read().strip()
        key = Fernet.generate_key()
        with open(path, "wb") as fh:
            fh.write(key)
        os.chmod(path, 0o600)
        return key


class CredentialCipher:
    """Encrypt/decrypt secrets with envelope encryption.

    Stored blob layout (all base64, '.'-joined):  <wrapped_data_key>.<ciphertext>
    """

    def __init__(self, master_key: bytes):
        self._master = Fernet(master_key)

    def encrypt(self, plaintext: str) -> str:
        data_key = Fernet.generate_key()
        ciphertext = Fernet(data_key).encrypt(plaintext.encode())
        wrapped = self._master.encrypt(data_key)
        return f"{_b64(wrapped)}.{_b64(ciphertext)}"

    def decrypt(self, blob: str) -> str:
        wrapped_b64, ct_b64 = blob.split(".", 1)
        data_key = self._master.decrypt(_unb64(wrapped_b64))
        return Fernet(data_key).decrypt(_unb64(ct_b64)).decode()

    def rotate_master(self, new_master_key: bytes, blob: str) -> str:
        """Re-wrap a row's data key under a new master key (no secret re-encrypt)."""
        wrapped_b64, ct_b64 = blob.split(".", 1)
        data_key = self._master.decrypt(_unb64(wrapped_b64))
        rewrapped = Fernet(new_master_key).encrypt(data_key)
        return f"{_b64(rewrapped)}.{ct_b64}"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode())


@lru_cache
def get_cipher() -> CredentialCipher:
    return CredentialCipher(load_or_create_master_key())
