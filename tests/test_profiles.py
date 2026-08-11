from __future__ import annotations

from pathlib import Path

import pytest

from liteyukibot.profiles import ProfileError, ProfileManifest, ProfileStore


def _manifest(profile_id: str) -> ProfileManifest:
    return ProfileManifest(
        profile_id,
        "2026-08-11T00:00:00+00:00",
        ("liteyukibot-v7==7.0.0a7",),
        "python",
        {"liteyukibot-v7": "7.0.0a7"},
    )


def _verified(store: ProfileStore, profile_id: str) -> None:
    path = store.profile_path(profile_id)
    ProfileStore.python_path(path).parent.mkdir(parents=True)
    ProfileStore.python_path(path).write_text("", encoding="utf-8")
    store.write_manifest(_manifest(profile_id))


def test_profile_activation_and_rollback_are_atomic_workspace_state(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)
    _verified(store, "first")
    _verified(store, "second")

    store.activate("first")
    store.activate("second")

    assert store.active() == "second"
    assert store.rollback() == "first"
    assert store.active() == "first"
    assert (tmp_path / "liteyuki.lock").is_file()
    assert set(store.digests()) == {"first", "second"}


def test_profile_rejects_unverified_or_unsafe_profiles(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path)
    with pytest.raises(ProfileError, match="only"):
        store.profile_path("../escape")
    with pytest.raises(ProfileError, match="not verified"):
        store.activate("missing")
