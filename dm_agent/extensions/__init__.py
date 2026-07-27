"""DM-Code-Agent 扩展注册接口。"""

from .discovery import (
    ExtensionDiscoveryError,
    ExtensionDiscoveryResult,
    ExtensionLoadFailure,
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
    "discover_extensions",
]
