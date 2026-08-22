"""Authenticated local secret vaults for runtime child processes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..exceptions import LiteyukiError

_FORMAT_VERSION = 1
_AAD = b"liteyukibot.secrets.v1"
_KEY_LENGTH = 32
_SALT_LENGTH = 16
_NONCE_LENGTH = 12
_MAX_KDF_MEMORY = 64 * 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class VaultError(LiteyukiError):
    """Raised for a vault failure without ever including secret material."""


class SecretVault:
    """Encrypt named runtime secrets in an authenticated local vault file.

    The vault protects secrets at rest and detects modification. It does not
    isolate secrets from code running with the same user and filesystem access.
    """

    filename = "secrets.v1.json"

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        """Initialize the secret vault.

        Args:
            directory: The directory value used by the operation.

        Returns:
            None.
        """
        self.directory = Path(directory).resolve()
        self.path = self.directory / self.filename

    def initialize(self, password: str, values: Mapping[str, str] = {}) -> None:
        """Create a new vault without overwriting an existing secret file.

        Args:
            password: Non-empty password used to derive the encryption key.
            values: Initial validated secret names and plaintext values.

        Returns:
            None.

        Security:
            Plaintext values are held briefly in process memory. The capability
            is retained because child runtimes need provisioned credentials;
            authenticated encryption and owner-only atomic writes protect the
            persistent form.
        """
        if self.path.exists():
            raise VaultError(f"secret vault already exists: {self.path}")
        self._write(password, self._validate_values(values))

    def read(self, password: str) -> dict[str, str]:
        """Authenticate, decrypt, and validate all named vault values.

        Args:
            password: Password used to derive the candidate decryption key.

        Returns:
            Fresh mapping of secret names to plaintext values.

        Security:
            This intentionally returns plaintext to trusted runtime setup code.
            AES-GCM authentication rejects a wrong password or modified file;
            error messages never include decrypted material.
        """
        try:
            raw = self.path.read_bytes()
        except OSError as error:
            raise VaultError(f"cannot read secret vault: {self.path}") from error
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VaultError("secret vault has an invalid JSON format") from error
        return self._decrypt_document(document, password)

    def set(self, password: str, name: str, value: str) -> None:
        """Set the secret vault operation.

        Args:
            password: The password value used by the operation.
            name: Stable name used to identify the value.
            value: Value to validate, transform, or store.

        Returns:
            None.
        """
        values = self.read(password) if self.path.exists() else {}
        values[name] = value
        self._write(password, self._validate_values(values))

    def delete(self, password: str, name: str) -> bool:
        """Delete the secret vault operation.

        Args:
            password: The password value used by the operation.
            name: Stable name used to identify the value.

        Returns:
            Whether the requested condition is satisfied.
        """
        values = self.read(password)
        if name not in values:
            return False
        del values[name]
        self._write(password, values)
        return True

    def list_names(self, password: str) -> tuple[str, ...]:
        """List names.

        Args:
            password: The password value used by the operation.

        Returns:
            The `tuple[str, ...]` result produced by the operation.
        """
        return tuple(sorted(self.read(password)))

    def rotate(self, password: str, replacement_password: str) -> None:
        """Re-encrypt the current vault under a replacement password.

        Args:
            password: The password value used by the operation.
            replacement_password: The replacement password value used by the operation.

        Returns:
            None.
        """
        self._write(replacement_password, self.read(password))

    @classmethod
    def _validate_values(cls, values: Mapping[str, str]) -> dict[str, str]:
        """Validate values.

        Args:
            values: The values value used by the operation.

        Returns:
            The `dict[str, str]` result produced by the operation.

        Notes:
            Internal implementation detail for `SecretVault._validate_values`. It delegates to `items`,
            `fullmatch` while keeping intermediate state local to the owning operation.
        """
        result: dict[str, str] = {}
        for name, value in values.items():
            if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
                raise VaultError("secret name must use letters, digits, dots, underscores, or hyphens")
            if not isinstance(value, str) or not value:
                raise VaultError(f"secret {name!r} must be a non-empty string")
            result[name] = value
        return result

    def _write(self, password: str, values: Mapping[str, str]) -> None:
        """Encrypt and atomically replace the vault with owner-only permissions.

        Args:
            password: Password used for scrypt key derivation.
            values: Validated plaintext values to serialize and encrypt.

        Returns:
            None.

        Notes:
            A fresh salt and nonce are generated for every rewrite. The temporary
            file is flushed and atomically replaced before best-effort permission
            normalization.

        Security:
            Writing secrets is inherently sensitive but required for runtime
            credential provisioning. AES-256-GCM, scrypt, fresh randomness,
            authenticated format metadata, and mode `0600` bound the risk.
        """
        encoded_password = self._password_bytes(password)
        salt = secrets.token_bytes(_SALT_LENGTH)
        kdf = {"name": "scrypt", "salt": _encode(salt), "n": 16384, "r": 8, "p": 1}
        key = self._derive(encoded_password, kdf)
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        plaintext = json.dumps(dict(values), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, _AAD)
        document = {
            "version": _FORMAT_VERSION,
            "kdf": kdf,
            "cipher": {
                "name": "AES-256-GCM",
                "nonce": _encode(nonce),
                "ciphertext": _encode(ciphertext),
            },
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                descriptor = -1
                output.write(
                    json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if descriptor != -1:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()

    def _decrypt_document(self, document: Any, password: str) -> dict[str, str]:
        """Validate vault metadata and decrypt authenticated ciphertext.

        Args:
            document: Untrusted JSON value loaded from the vault file.
            password: Password used to derive the candidate key.

        Returns:
            Validated plaintext secret mapping.

        Notes:
            Format, cipher, nonce, ciphertext, KDF, authentication tag, JSON
            shape, and secret identifiers are checked in that order.

        Security:
            Vault files are attacker-controlled input at this boundary. KDF
            parameters are bounded before derivation and authentication failures
            do not reveal whether ciphertext or password was wrong.
        """
        if not isinstance(document, Mapping) or document.get("version") != _FORMAT_VERSION:
            raise VaultError("secret vault has an unsupported format version")
        kdf = document.get("kdf")
        cipher = document.get("cipher")
        if not isinstance(kdf, Mapping) or not isinstance(cipher, Mapping):
            raise VaultError("secret vault is missing required encryption metadata")
        if cipher.get("name") != "AES-256-GCM":
            raise VaultError("secret vault uses an unsupported cipher")
        nonce = _decode(cipher.get("nonce"), "cipher nonce")
        ciphertext = _decode(cipher.get("ciphertext"), "ciphertext")
        if len(nonce) != _NONCE_LENGTH or len(ciphertext) <= 16:
            raise VaultError("secret vault contains invalid authenticated ciphertext")
        key = self._derive(self._password_bytes(password), kdf)
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
        except InvalidTag as error:
            raise VaultError("secret vault password is incorrect or vault data was modified") from error
        try:
            values = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise VaultError("secret vault plaintext is invalid") from error
        if not isinstance(values, Mapping):
            raise VaultError("secret vault plaintext must be an object")
        return self._validate_values(values)

    @staticmethod
    def _password_bytes(password: str) -> bytes:
        """Implement the password bytes operation for the secret vault.

        Args:
            password: The password value used by the operation.

        Returns:
            The `bytes` result produced by the operation.

        Notes:
            Internal implementation detail for `SecretVault._password_bytes`. It delegates to `encode` while
            keeping intermediate state local to the owning operation.
        """
        if not isinstance(password, str) or not password:
            raise VaultError("vault password must not be empty")
        return password.encode("utf-8")

    @staticmethod
    def _derive(password: bytes, kdf: Mapping[str, Any]) -> bytes:
        """Implement the derive operation for the secret vault.

        Args:
            password: The password value used by the operation.
            kdf: The kdf value used by the operation.

        Returns:
            The `bytes` result produced by the operation.

        Notes:
            Internal implementation detail for `SecretVault._derive`. It delegates to `get`, `_decode`,
            `scrypt` while keeping intermediate state local to the owning operation.
        """
        if kdf.get("name") != "scrypt":
            raise VaultError("secret vault uses an unsupported key derivation function")
        salt = _decode(kdf.get("salt"), "KDF salt")
        n = kdf.get("n")
        r = kdf.get("r")
        p = kdf.get("p")
        if (
            not isinstance(n, int)
            or isinstance(n, bool)
            or n < 2**14
            or n > 2**18
            or n & (n - 1)
            or not isinstance(r, int)
            or isinstance(r, bool)
            or not 1 <= r <= 64
            or not isinstance(p, int)
            or isinstance(p, bool)
            or not 1 <= p <= 16
            or not _SALT_LENGTH <= len(salt) <= 64
            or 128 * n * r > _MAX_KDF_MEMORY // 2
        ):
            raise VaultError("secret vault contains unsafe KDF parameters")
        try:
            return hashlib.scrypt(
                password,
                salt=salt,
                n=n,
                r=r,
                p=p,
                dklen=_KEY_LENGTH,
                maxmem=_MAX_KDF_MEMORY,
            )
        except ValueError as error:
            raise VaultError("secret vault KDF parameters are unavailable on this system") from error


def _encode(value: bytes) -> str:
    """Encode the component operation.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_encode`. It delegates to `decode`, `b64encode` while
        keeping intermediate state local to the owning operation.
    """
    return base64.b64encode(value).decode("ascii")


def _decode(value: Any, name: str) -> bytes:
    """Decode the component operation.

    Args:
        value: Value to validate, transform, or store.
        name: Stable name used to identify the value.

    Returns:
        The `bytes` result produced by the operation.

    Notes:
        Internal implementation detail for `_decode`. It delegates to `b64decode`, `encode` while
        keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, str):
        raise VaultError(f"secret vault {name} must be base64 text")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise VaultError(f"secret vault {name} is not valid base64") from error


__all__ = ["SecretVault", "VaultError"]
