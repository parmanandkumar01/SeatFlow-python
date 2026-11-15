"""Low-level AES-256-GCM encryption helpers.

Provides authenticated symmetric encryption and decryption using
the cryptography library. All sensitive data is encrypted with
AES-256-GCM using a randomly generated 12-byte nonce per operation.

Output format: base64(nonce || ciphertext || tag)
"""

from __future__ import annotations

import base64
import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# AES-256 key size in bytes
KEY_SIZE: Final[int] = 32
# GCM nonce (IV) size in bytes
NONCE_SIZE: Final[int] = 12
# GCM authentication tag size in bytes (AESGCM standard)
TAG_SIZE: Final[int] = 16


class EncryptionError(Exception):
    """Raised for encryption or decryption failures."""


class Encryption:
    """Low-level AES-256-GCM encrypt/decrypt operations.

    Uses a raw 32-byte key. Key derivation (Argon2id) is handled
    separately by the password_hash module.
    """

    def __init__(self, key: bytes) -> None:
        """Initialize with a 32-byte encryption key.

        Args:
            key: 32-byte AES-256 key.

        Raises:
            ValueError: If key is not 32 bytes.
        """
        if len(key) != KEY_SIZE:
            raise ValueError(f"Encryption key must be {KEY_SIZE} bytes, got {len(key)}")
        self._key = key
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a UTF-8 string and return base64-encoded ciphertext.

        Format: base64(nonce || ciphertext || tag)

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded string containing nonce + ciphertext + tag.

        Raises:
            EncryptionError: If encryption fails.
        """
        try:
            nonce = os.urandom(NONCE_SIZE)
            plaintext_bytes = plaintext.encode("utf-8")
            ciphertext_with_tag = self._aesgcm.encrypt(nonce, plaintext_bytes, None)
            combined = nonce + ciphertext_with_tag
            return base64.b64encode(combined).decode("ascii")
        except Exception as exc:
            raise EncryptionError(f"Encryption failed: {exc}") from exc

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a base64-encoded ciphertext and return the plaintext string.

        Expected format: base64(nonce || ciphertext || tag)

        Args:
            ciphertext_b64: Base64-encoded encrypted string.

        Returns:
            The decrypted plaintext string.

        Raises:
            EncryptionError: If decryption or authentication fails
                (e.g., tampered data, wrong key).
        """
        try:
            combined = base64.b64decode(ciphertext_b64)
            nonce = combined[:NONCE_SIZE]
            ciphertext_with_tag = combined[NONCE_SIZE:]
            plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext_with_tag, None)
            return plaintext_bytes.decode("utf-8")
        except (InvalidTag, ValueError, Exception) as exc:
            raise EncryptionError(f"Decryption failed: data may be tampered or key incorrect") from exc

    def wipe_key(self) -> None:
        """Overwrite the in-memory key with zeros.

        Best-effort key cleanup. Python bytes objects are immutable,
        so this replaces the reference with zeros; the actual memory
        may not be immediately zeroed due to Python's memory manager.
        """
        self._key = b"\x00" * KEY_SIZE  # type: ignore[assignment]
        self._aesgcm = AESGCM(self._key)  # type: ignore[arg-type]
