"""Verify the published distribution without importing the source checkout."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _module_version(module_name: str) -> str:
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise RuntimeError(f"{module_name} does not expose __file__")
    if Path(module_file).resolve().is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {module_file}")
    version = getattr(module, "__version__", None)
    if not isinstance(version, str):
        raise RuntimeError(f"{module_name} does not expose a string __version__")
    return version


def _verify_module_location(module_name: str) -> None:
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        raise RuntimeError(f"{module_name} does not expose __file__")
    if Path(module_file).resolve().is_relative_to(SOURCE_ROOT):
        raise RuntimeError(f"workspace source import detected: {module_file}")


def _verify_removed_runtime_surface(distribution_name: str) -> None:
    """Reject a root wheel that still ships the retired child Runtime package.

    Args:
        distribution_name: Installed root distribution name.

    Returns:
        None.

    Notes:
        Both metadata and import discovery are checked so packaging and import
        regressions fail the isolated-install verifier.
    """
    distribution = importlib.metadata.distribution(distribution_name)
    files = distribution.files or ()
    if any(tuple(path.parts[:2]) == ("liteyukibot", "runtime") for path in files):
        raise RuntimeError("installed root distribution still contains liteyukibot.runtime")
    if importlib.util.find_spec("liteyukibot.runtime") is not None:
        raise RuntimeError("retired liteyukibot.runtime package remains importable")


def _verify_cli_first_surface(distribution_name: str) -> None:
    """Reject root artifacts that still expose retired package surfaces."""

    requirements = importlib.metadata.requires(distribution_name) or ()
    retired = ("liteyukibot-v7-broker", "liteyukibot-v7-runtime", "liteyukibot-v7-webui")
    if any(requirement.lower().split("[", 1)[0].startswith(retired) for requirement in requirements):
        raise RuntimeError("installed root distribution depends on a retired package")
    for module_name in ("liteyukibot_broker", "liteyukibot_runtime_adapter", "liteyukibot_webui"):
        if importlib.util.find_spec(module_name) is not None:
            raise RuntimeError(f"root installation unexpectedly provides {module_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", default="liteyukibot-v7")
    parser.add_argument("--expected-version")
    parser.add_argument("--expect-kernel", action="store_true")
    parser.add_argument("--expect-cordis", action="store_true")
    parser.add_argument("--expect-adapter-onebot", action="store_true")
    parser.add_argument("--expect-no-legacy-runtime", action="store_true")
    args = parser.parse_args()

    distribution_version = importlib.metadata.version(args.distribution)
    expected_version = args.expected_version or distribution_version
    observed = {
        args.distribution: distribution_version,
        "liteyukibot": _module_version("liteyukibot"),
    }
    if args.expect_kernel:
        observed["liteyukibot-v7-kernel"] = importlib.metadata.version("liteyukibot-v7-kernel")
        observed["liteyukibot_kernel"] = _module_version("liteyukibot_kernel")
    if args.expect_cordis:
        observed["liteyukibot-v7-cordis"] = importlib.metadata.version("liteyukibot-v7-cordis")
        _verify_module_location("liteyukibot_cordis")
    if args.expect_adapter_onebot:
        observed["liteyukibot-v7-adapter-onebot"] = importlib.metadata.version("liteyukibot-v7-adapter-onebot")
        _verify_module_location("liteyukibot_adapter_onebot")
    _verify_cli_first_surface(args.distribution)
    if args.expect_no_legacy_runtime:
        _verify_removed_runtime_surface(args.distribution)
    mismatches = {
        name: version for name, version in observed.items() if version != expected_version
    }
    if mismatches:
        rendered = ", ".join(f"{name}={version}" for name, version in mismatches.items())
        raise RuntimeError(f"expected {expected_version}; observed {rendered}")

    print(json.dumps({"expected": expected_version, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
