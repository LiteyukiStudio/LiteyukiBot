from __future__ import annotations

import getpass
import json
from pathlib import Path

import pytest

import liteyukibot.cli as cli_module
from liteyukibot.config.vault import SecretVault, VaultError


def test_vault_round_trip_rotation_and_secret_free_errors(tmp_path: Path) -> None:
    vault = SecretVault(tmp_path / ".liteyuki")
    vault.initialize("correct horse", {"agent.provider.api_key": "api-value"})

    raw = vault.path.read_text(encoding="utf-8")
    assert "api-value" not in raw
    assert vault.list_names("correct horse") == ("agent.provider.api_key",)

    with pytest.raises(VaultError) as captured:
        vault.read("wrong password")
    assert "api-value" not in str(captured.value)

    vault.rotate("correct horse", "new password")
    assert vault.read("new password") == {"agent.provider.api_key": "api-value"}


def test_vault_rejects_tampered_kdf_before_decryption(tmp_path: Path) -> None:
    vault = SecretVault(tmp_path / ".liteyuki")
    vault.initialize("password", {"agent.provider.api_key": "api-value"})
    document = json.loads(vault.path.read_text(encoding="utf-8"))
    document["kdf"]["n"] = 3
    vault.path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(VaultError, match="unsafe KDF"):
        vault.read("password")


def test_vault_rejects_invalid_secret_names_and_values(tmp_path: Path) -> None:
    vault = SecretVault(tmp_path / ".liteyuki")

    with pytest.raises(VaultError, match="secret name"):
        vault.initialize("password", {"bad name": "value"})
    with pytest.raises(VaultError, match="non-empty"):
        vault.initialize("password", {"valid.name": ""})


def test_cli_vault_commands_never_print_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli_module.main(["init", "--non-interactive"]) == 0
    responses = iter(("password", "password", "api-value", "password"))
    monkeypatch.setattr(getpass, "getpass", lambda _prompt: next(responses))

    assert cli_module.main(["vault", "set", "agent.provider.api_key"]) == 0
    capsys.readouterr()
    assert cli_module.main(["vault", "list"]) == 0
    output = capsys.readouterr().out

    assert "agent.provider.api_key" in output
    assert "api-value" not in output
