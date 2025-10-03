"""MCP 配置管理"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class MCPServerConfig:
    """单个 MCP 服务器配置"""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":
        """从字典创建配置"""
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env"),
            enabled=data.get("enabled", True)
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "command": self.command,
            "args": self.args,
        }
        if self.env:
            result["env"] = self.env
        if not self.enabled:
            result["enabled"] = self.enabled
        return result


@dataclass
class MCPConfig:
    """MCP 总配置"""

    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """从字典创建配置"""
        mcp_servers = data.get("mcpServers", {})
        servers = {
            name: MCPServerConfig.from_dict(name, config)
            for name, config in mcp_servers.items()
        }
        return cls(servers=servers)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "mcpServers": {
                name: config.to_dict()
                for name, config in self.servers.items()
            }
        }

    def add_server(self, config: MCPServerConfig) -> None:
        """添加 MCP 服务器"""
        self.servers[config.name] = config

    def remove_server(self, name: str) -> None:
        """移除 MCP 服务器"""
        if name in self.servers:
            del self.servers[name]

    def get_enabled_servers(self) -> Dict[str, MCPServerConfig]:
        """获取所有启用的服务器"""
        return {
            name: config
            for name, config in self.servers.items()
            if config.enabled
        }


def load_mcp_config(config_path: str = "mcp_config.json") -> MCPConfig:
    """从文件加载 MCP 配置

    Args:
        config_path: 配置文件路径，默认为 mcp_config.json

    Returns:
        MCPConfig 实例
    """
    if not os.path.exists(config_path):
        return MCPConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MCPConfig.from_dict(data)
    except Exception as e:
        print(f"⚠️ 加载 MCP 配置失败: {e}，使用空配置")
        return MCPConfig()


def save_mcp_config(config: MCPConfig, config_path: str = "mcp_config.json") -> bool:
    """保存 MCP 配置到文件

    Args:
        config: MCP 配置对象
        config_path: 配置文件路径

    Returns:
        是否保存成功
    """
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ 保存 MCP 配置失败: {e}")
        return False
