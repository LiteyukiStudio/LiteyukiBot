"""Exercise a built reference plugin through a real isolated NoneBot generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

from liteyukibot.plugin_install import PluginInstallationService
from liteyukibot.plugin_sources import OFFICIAL_SOURCE_ID, PluginSource, PluginSourceStore
from liteyukibot.plugin_store import ArtifactStore, PluginIndex, RuntimeGenerationStore


def _single_wheel(wheel_directory: Path, prefix: str) -> Path:
    """Return the unique wheel matching one normalized distribution prefix.

    Args:
        wheel_directory: Build output containing workspace wheels.
        prefix: Normalized wheel filename prefix including the expected version.

    Returns:
        The single matching wheel path.
    """
    matches = tuple(wheel_directory.glob(f"{prefix}-*.whl"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {prefix} wheel in {wheel_directory}; found {len(matches)}")
    return matches[0].resolve()


def _probe_host(python: Path, generation: Path) -> dict[str, object]:
    """Load one managed plan inside its generation interpreter.

    Args:
        python: Generation virtual environment interpreter.
        generation: Materialized generation root.

    Returns:
        JSON evidence emitted by the external NoneBot process.
    """
    completed = subprocess.run(
        [
            str(python),
            "-c",
            "import json, nonebot, os; "
            "os.environ['LITEYUKI_PLUGIN_GENERATION'] = os.environ['E2E_GENERATION']; "
            "from liteyukibot_runtime_nonebot.host import _managed_load_plan; "
            "plugins, directories = _managed_load_plan(os.environ['E2E_GENERATION']); "
            "nonebot.init(); loaded = [nonebot.load_plugin(name) is not None for name in plugins]; "
            "print(json.dumps({'plugins': plugins, 'directories': directories, 'loaded': loaded}))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "E2E_GENERATION": str(generation)},
    )
    value = json.loads(completed.stdout.strip().splitlines()[-1])
    if not isinstance(value, dict):
        raise RuntimeError("NoneBot host probe did not return a JSON object")
    return value


PUBLIC_SOURCE_ID = "official-public"


def run(wheel_directory: Path, workspace: Path, *, public_index_url: str | None = None) -> dict[str, object]:
    """Build, activate, and load the reference plugin in an external host.

    Args:
        wheel_directory: Directory containing a complete Alpha workspace build.
        workspace: Empty or absent temporary workspace for generation state.
        public_index_url: Optional public index URL. When provided, the plugin
            metadata and wheel are fetched through that source instead of the
            in-memory pre-release fixture.

    Returns:
        JSON-safe evidence describing the activated generation and host probe.

    Security:
        The reference wheel executes as arbitrary Python in a child process with
        the current OS user's privileges. This verifier is intentionally an
        execution test, not a hostile-plugin sandbox.
    """
    wheel_directory = wheel_directory.resolve(strict=True)
    workspace = workspace.resolve()
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError(f"E2E workspace must be empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    wheel = _single_wheel(wheel_directory, "liteyukibot_v7_example_nonebot_plugin-0.1.0")
    service = PluginInstallationService(workspace)
    previous_find_links = os.environ.get("UV_FIND_LINKS")
    os.environ["UV_FIND_LINKS"] = str(wheel_directory)
    try:
        if public_index_url is None:
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            size = wheel.stat().st_size
            index = PluginIndex.parse(
                {
                    "schema": 2,
                    "bundles": [
                        {
                            "id": "liteyuki.reference.nonebot",
                            "version": "0.1.0",
                            "display_name": "LiteyukiBot Reference NoneBot Plugin",
                            "summary": "Executable reference for managed NoneBot generations.",
                            "publisher": {
                                "id": "liteyuki",
                                "name": "Liteyuki Studio",
                                "url": "https://github.com/LiteyukiStudio",
                            },
                            "license": {
                                "expression": "LicenseRef-LSO-Common-1.4",
                                "url": "https://github.com/LiteyukiStudio/LiteyukiBot/blob/main/LICENSE.zh-CN",
                            },
                            "repository": "https://github.com/LiteyukiStudio/LiteyukiBot",
                            "status": "active",
                            "dependencies": [],
                            "facets": [
                                {
                                    "runtime_kind": "nonebot",
                                    "artifacts": [],
                                    "wheels": [
                                        {
                                            "url": f"https://example.invalid/{wheel.name}",
                                            "sha256": digest,
                                            "bytes": size,
                                        }
                                    ],
                                    "platform": {"systems": [], "machines": [], "pythons": []},
                                    "load": {
                                        "plugins": ["liteyukibot_example_nonebot_plugin"],
                                        "directories": [],
                                    },
                                    "capabilities": [],
                                }
                            ],
                        }
                    ],
                }
            )
            ArtifactStore(workspace).import_file(wheel, digest, size)
            source_id = OFFICIAL_SOURCE_ID
            fetch_context: AbstractContextManager[Any] = patch.object(PluginSourceStore, "fetch", return_value=index)
        else:
            PluginSourceStore(workspace).add(PluginSource(PUBLIC_SOURCE_ID, public_index_url))
            source_id = PUBLIC_SOURCE_ID
            fetch_context = nullcontext()
        with fetch_context:
            result = service.install(
                "liteyuki.reference.nonebot",
                runtime_id="nonebot-e2e",
                runtime_kind="nonebot",
                source_id=source_id,
            )
        if public_index_url is not None:
            digest = result.generation.artifacts[0]
            artifact = service.artifacts.require(digest)
            size = artifact.stat().st_size
        generation_path = RuntimeGenerationStore(workspace).path_for("nonebot-e2e", result.generation.id)
        python = RuntimeGenerationStore.python_path(generation_path)
        host = _probe_host(python, generation_path)
        expected_host = {
            "plugins": ["liteyukibot_example_nonebot_plugin"],
            "directories": [],
            "loaded": [True],
        }
        if host != expected_host:
            raise RuntimeError(f"unexpected NoneBot host probe result: {host}")

        orphan = workspace / "orphan.bin"
        orphan.write_bytes(b"orphan")
        orphan_digest = hashlib.sha256(orphan.read_bytes()).hexdigest()
        orphan_path = service.artifacts.import_file(orphan, orphan_digest)
        disabled = service.disable(
            "liteyuki.reference.nonebot",
            runtime_id="nonebot-e2e",
            runtime_kind="nonebot",
        )
        enabled = service.enable(
            "liteyuki.reference.nonebot",
            runtime_id="nonebot-e2e",
            runtime_kind="nonebot",
        )
        if orphan_path.exists():
            raise RuntimeError("managed generation cleanup retained an unreferenced artifact")
        deployment = service.generations.rollback("nonebot-e2e")
        if deployment.runtime_generations.get("nonebot-e2e") != disabled.generation.id:
            raise RuntimeError("managed generation rollback did not restore the disabled generation")
        disabled_path = service.generations.path_for("nonebot-e2e", disabled.generation.id)
        disabled_host = _probe_host(service.generations.python_path(disabled_path), disabled_path)
        if disabled_host != {"plugins": [], "directories": [], "loaded": []}:
            raise RuntimeError(f"disabled generation loaded plugin code: {disabled_host}")
        uninstall = service.uninstall(
            "liteyuki.reference.nonebot",
            runtime_id="nonebot-e2e",
            runtime_kind="nonebot",
        )
        if uninstall.generation is not None:
            raise RuntimeError("final root uninstall did not deactivate the target")
    finally:
        if previous_find_links is None:
            os.environ.pop("UV_FIND_LINKS", None)
        else:
            os.environ["UV_FIND_LINKS"] = previous_find_links

    final_deployment = service.generations.active()
    final_generations = service.generations.list_generations("nonebot-e2e")
    final_artifacts = tuple(service.artifacts.root.iterdir()) if service.artifacts.root.exists() else ()
    if final_deployment.runtime_generations or len(final_generations) != 1 or len(final_artifacts) != 1:
        raise RuntimeError("final managed generation residency is not bounded")
    return {
        "schema": 1,
        "bundle": "liteyuki.reference.nonebot",
        "artifact_sha256": digest,
        "artifact_bytes": size,
        "generation": result.generation.id,
        "python": str(python),
        "host": host,
        "lifecycle": {
            "disabled": disabled.generation.id,
            "enabled": enabled.generation.id,
            "rolled_back": disabled.generation.id,
            "active_after_uninstall": None,
            "retained_generations": len(final_generations),
            "retained_artifacts": len(final_artifacts),
        },
    }


def main() -> int:
    """Parse command-line paths and print external-host E2E evidence.

    Returns:
        Zero when the managed reference plugin loads successfully.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--index-url")
    args = parser.parse_args()
    print(json.dumps(run(args.wheel_dir, args.workspace, public_index_url=args.index_url), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
