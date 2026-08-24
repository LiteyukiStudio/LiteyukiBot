---
status: "in-progress"
owner: "Nanaloveyuki"
topic: "pypi-project-requirements"
applies-to: "Alpha14 package extraction and package renames"
supersedes:
expires: 20260825
promotes-to: "docs/development/releasing.md after owner confirmation"
---

# PyPI Project Requirements For Alpha14

This is a one-day preparation record. It does not authorize a PyPI or GitHub
mutation. Before creating a project, changing a trusted publisher, uploading,
yanking, transferring ownership, or pushing an upload-triggering tag, present
the exact operation to the user and wait for confirmation.

## Evidence Snapshot

The owner-provided PyPI screenshot on 2026-08-24 shows these owned projects:

- `liteyukibot-v7`
- `liteyukibot-v7-adapter-onebot`
- `liteyukibot-v7-adapter-satori`
- `liteyukibot-v7-agent`
- `liteyukibot-v7-agent-resolver`
- `liteyukibot-v7-commands`
- `liteyukibot-v7-essentials`
- `liteyukibot-v7-functions`
- `liteyukibot-v7-permissions`
- `liteyukibot-v7-profile`
- `liteyukibot-v7-resources`
- `liteyukibot-v7-runtime-adapter`
- `liteyukibot-v7-runtime-astrbot`
- `liteyukibot-v7-runtime-mofox`
- `liteyukibot-v7-runtime-nonebot`
- `liteyukibot-v7-runtime-v6`

The screenshot also shows `yukilog`, which is outside this repository change.
This list is evidence of the screenshot state only; recheck PyPI before acting.

## Pending Trusted Publishers Shown

### liteyukibot-v7-ipc-native

PyPI Project Name: `liteyukibot-v7-ipc-native`
Owner: `LiteyukiStudio`
Repo name: `LiteyukiBot`
Workflow name: `publish-plugins.yaml`
Env name: `pypi-ipc-native`
State: `pending publisher shown in owner screenshot`

### liteyukibot-v7-webui

PyPI Project Name: `liteyukibot-v7-webui`
Owner: `LiteyukiStudio`
Repo name: `LiteyukiBot`
Workflow name: `publish-plugins.yaml`
Env name: `pypi-webui`
State: `pending publisher shown in owner screenshot`

Both mappings also match the current `.github/workflows/publish-plugins.yaml`.

## Existing Source Projects Not Shown

The screenshot does not show these distribution names:

- `liteyukibot-v7-cordis`
- `liteyukibot-v7-runtime-nonebot-api`
- `liteyukibot-v7-runtime-astrbot-api`

Their ownership/availability requires confirmation. They are not configured as
publishable choices in the current `publish-plugins.yaml`, and no environment
name is asserted here.

## Proposed New Or Renamed Projects

Every row below is proposed. None was shown in the screenshot, and the current
workflow does not yet support it. Project ownership/name availability must be
confirmed before implementation, and publisher creation must be separately
confirmed immediately before the PyPI mutation.

| Project Name | Owner | Repo name | Workflow name | Env name | Source |
| --- | --- | --- | --- | --- | --- |
| `liteyukibot-v7-kernel` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-kernel` (proposed) | new package |
| `liteyukibot-v7-broker` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-broker` (proposed) | new package |
| `liteyukibot-v7-daemon` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-daemon` (proposed) | new package |
| `liteyukibot-v7-plugin-manager` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-plugin-manager` (proposed) | new package |
| `liteyukibot-v7-adapter-host` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-adapter-host` (proposed) | rename from runtime-adapter |
| `liteyukibot-v7-bridge-nonebot` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-bridge-nonebot` (proposed) | rename from runtime-nonebot |
| `liteyukibot-v7-bridge-nonebot-api` | `LiteyukiStudio` | `LiteyukiBot` | `publish-plugins.yaml` (proposed) | `pypi-bridge-nonebot-api` (proposed) | rename from runtime-nonebot-api |

## Required Confirmation Payload

Before any PyPI action, report:

1. the exact Project Name and whether it is owned, pending, not shown, or
   proposed;
2. Owner `LiteyukiStudio`, repository `LiteyukiBot`, workflow, and environment;
3. the exact mutation to perform and whether a pushed tag can trigger upload;
4. the local validation already completed;
5. a request for explicit user confirmation for that mutation.
