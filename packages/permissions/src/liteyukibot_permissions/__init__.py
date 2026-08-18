"""Versioned access policy service for LiteyukiBot v7."""

from importlib.metadata import PackageNotFoundError, version

from .plugin import create_plugin
from .service import (
    PERMISSION_SERVICE,
    PUBLIC,
    AuthorizationInput,
    ManagementPermissionService,
    PermissionAuditService,
    PermissionDecision,
    PermissionService,
    PermissionSnapshot,
    PermissionV2Service,
    Principal,
    authorization_context,
)

try:
    __version__ = version("liteyukibot-v7-permissions")
except PackageNotFoundError:
    __version__ = "0.3.0a1"

plugin = create_plugin(__version__)

__all__ = [
    "PERMISSION_SERVICE",
    "PUBLIC",
    "AuthorizationInput",
    "ManagementPermissionService",
    "PermissionAuditService",
    "PermissionDecision",
    "PermissionService",
    "PermissionSnapshot",
    "PermissionV2Service",
    "Principal",
    "authorization_context",
    "__version__",
    "plugin",
]
