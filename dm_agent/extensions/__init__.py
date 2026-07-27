"""DM-Code-Agent 扩展注册接口。"""

from .discovery import (
    ExtensionDiscoveryError,
    ExtensionDiscoveryResult,
    ExtensionLoadFailure,
    create_builtin_registry,
    discover_extensions,
)
from .registry import ExtensionAPI, ExtensionRegistry, ExtensionSetup, ProviderFactory
from .trust import ProjectTrustDecision, ProjectTrustStore

__all__ = [
    "ExtensionAPI",
    "ExtensionDiscoveryError",
    "ExtensionDiscoveryResult",
    "ExtensionLoadFailure",
    "ExtensionRegistry",
    "ExtensionSetup",
    "ProjectTrustDecision",
    "ProjectTrustStore",
    "ProviderFactory",
    "create_builtin_registry",
    "discover_extensions",
]
