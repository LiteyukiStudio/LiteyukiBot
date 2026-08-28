from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ACTION = re.compile(r"^\s*(?:- )?uses:\s+[^@\s]+@[0-9a-f]{40}(?:\s+#\s+v[^\s]+)?\s*$", re.MULTILINE)


def test_release_workflow_actions_are_pinned_to_immutable_commits() -> None:
    workflows = tuple(sorted((ROOT / ".github" / "workflows").glob("*.y*ml")))
    assert workflows
    for workflow in workflows:
        lines = [line for line in workflow.read_text(encoding="utf-8").splitlines() if "uses:" in line]
        assert lines
        assert all(_ACTION.match(line) for line in lines), workflow


def test_python_workspace_lockfile_is_present() -> None:
    assert (ROOT / "uv.lock").is_file()


def test_pypi_workflows_exclude_alpha_tags() -> None:
    root_publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    plugin_publish = (ROOT / ".github" / "workflows" / "publish-plugins.yaml").read_text(encoding="utf-8")

    assert '"!v7.*a*"' in root_publish
    for prefix in ("kernel", "cordis", "adapter-onebot"):
        assert f'"!{prefix}-v7.*a*"' in plugin_publish


def test_docker_lifecycle_smoke_checks_exit_and_oom_state() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker.yaml").read_text(encoding="utf-8")

    assert 'exit_code="$(docker wait "$container_id")"' in workflow
    assert 'test "$exit_code" = "0"' in workflow
    assert "{{.State.OOMKilled}}" in workflow
