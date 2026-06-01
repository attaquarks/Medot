"""Security primitives: master-key management, envelope encryption, audit logging.

Threat model (laptop install): protect OAuth tokens & API keys at rest so that a
stolen disk image or a leaked DB dump does not expose accounts. The master key is
held in the OS keychain (Keychain / Credential Manager / Secret Service), NOT on
disk. Every credential row is encrypted with a per-row data key wrapped by the
master key (envelope encryption).
"""
from .crypto import CredentialCipher, get_cipher, load_or_create_master_key
from .audit import audit

__all__ = ["CredentialCipher", "get_cipher", "load_or_create_master_key", "audit"]
