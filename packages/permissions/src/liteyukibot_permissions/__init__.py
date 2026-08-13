"""Versioned access policy service for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .plugin import create_plugin
from .service import (
    PERMISSION_SERVICE,
    PUBLIC,
    ManagementPermissionService,
    PermissionAuditService,
    PermissionDecision,
    PermissionService,
    PermissionSnapshot,
    Principal,
)

try:
    __version__ = version("liteyukibot-v7-permissions")
except PackageNotFoundError:
    __version__ = "0.2.0a2"

plugin = create_plugin(__version__)

__all__ = [
    "PERMISSION_SERVICE",
    "PUBLIC",
    "ManagementPermissionService",
    "PermissionAuditService",
    "PermissionDecision",
    "PermissionService",
    "PermissionSnapshot",
    "Principal",
    "__version__",
    "plugin",
]
