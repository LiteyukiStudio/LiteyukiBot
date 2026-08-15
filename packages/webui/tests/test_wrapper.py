from __future__ import annotations

from liteyukibot_webui import static_assets


def test_static_assets_directory_is_packaged() -> None:
    assert static_assets().is_dir()
