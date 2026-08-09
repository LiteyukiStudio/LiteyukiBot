from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from scripts.check_release import ReleaseIdentity, read_release_identity, validate_release

import liteyuki
import liteyukibot


def test_import_namespaces_use_distribution_version() -> None:
    expected = importlib.metadata.version("liteyukibot-v7")

    assert liteyukibot.__version__ == expected
    assert liteyuki.__version__ == expected


def test_current_release_identity_accepts_matching_tag() -> None:
    identity = read_release_identity(Path("pyproject.toml"))

    validate_release(identity, tag=f"v{identity.version}")
    assert identity.distribution == "liteyukibot-v7"


@pytest.mark.parametrize(
    ("identity", "tag", "message"),
    [
        (ReleaseIdentity("liteyukibot", "7.0.0a2"), None, "project.name"),
        (ReleaseIdentity("liteyukibot-v7", "7.0.0a2"), "v7.0.0a1", "release tag"),
    ],
)
def test_release_identity_rejects_mismatches(
    identity: ReleaseIdentity,
    tag: str | None,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_release(identity, tag=tag)
