"""MCP 配置管理"""

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPServerConfig:
    """
    表示单个MCP服务器的配置信息，包括启动命令、参数、环境变量等

    Attributes:
        name (str): MCP服务器名称，用作唯一标识符
        command (str): 启动MCP服务器的命令（如'npx'、'python'等）
        args (List[str]): 命令行参数列表
        env (Optional[Dict[str, str]]): 环境变量字典，None表示使用默认环境
        enabled (bool): 服务器是否启用，默认为True
    """

    # MCP服务器启动名称
    name: str
    # 启动命令
    command: str
    # 命令行参数
    args: list[str] = field(default_factory=list)
    # 环境变量
    env: dict[str, str] | None = None
    # 服务器是否启用
    enabled: bool = True
    # 单次 JSON-RPC 请求的超时秒数
    timeout: float = 5.0

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "MCPServerConfig":
        """
        从字典数据创建MCPServerConfig实例

        Args:
            name (str): 服务器名称
            data (Dict[str, Any]): 包含配置信息的字典

        Returns:
            MCPServerConfig: 创建的配置实例

        Examples:
            >>> data = {"command": "npx", "args": ["@playwright/mcp@latest"], "enabled": True}
            >>> config = MCPServerConfig.from_dict("playwright", data)
            >>> config.command
            'npx'
        """
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env"),
            enabled=data.get("enabled", True),
            timeout=float(data.get("timeout", 5.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        将配置转换为字典格式，便于序列化存储

        Returns:
            result (Dict[str, Any]): 包含配置信息的字典

        Examples:
            >>> config = MCPServerConfig("test", "npx", ["tool"], {"DEBUG": "1"}, True)
            >>> data = config.to_dict()
            >>> "command" in data and "args" in data
            True
        """
        result: dict[str, Any] = {
            "command": self.command,
            "args": self.args,
        }
        if self.env:
            result["env"] = self.env
        if not self.enabled:
            result["enabled"] = self.enabled
        if self.timeout != 5.0:
            result["timeout"] = self.timeout
        return result


@dataclass
class MCPConfig:
    """
    管理所有MCP服务器的配置集合，提供对多个MCP服务器配置的统一管理接口

    Attributes:
        servers (Dict[str, MCPServerConfig]): 服务器名称到配置的映射字典
    """

    servers: dict[str, MCPServerConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPConfig":
        """
        从字典数据创建MCPConfig实例

        Args:
            data (Dict[str, Any]): 包含MCP配置信息的字典，应包含'mcpServers'键

        Returns:
            MCPConfig: 创建的总配置实例

        Examples:
            >>> data = {
            ...     "mcpServers": {
            ...         "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}
            ...     }
            ... }
            >>> config = MCPConfig.from_dict(data)
            >>> len(config.servers)
            1
        """
        mcp_servers = data.get("mcpServers", {})
        servers = {
            name: MCPServerConfig.from_dict(name, config) for name, config in mcp_servers.items()
        }
        return cls(servers=servers)

    def to_dict(self) -> dict[str, Any]:
        """
        将总配置转换为字典格式

        Returns:
            Dict[str, Any]: 包含所有服务器配置的字典

        Examples:
            >>> server_config = MCPServerConfig("test", "npx", ["tool"])
            >>> config = MCPConfig(servers={"test": server_config})
            >>> data = config.to_dict()
            >>> "mcpServers" in data
            True
        """
        return {"mcpServers": {name: config.to_dict() for name, config in self.servers.items()}}

    def get_enabled_servers(self) -> dict[str, MCPServerConfig]:
        """
        获取所有启用的服务器配置

        Returns:
            enabled_servers (Dict[str, MCPServerConfig]): 包含所有启用服务器配置的字典

        Examples:
            >>> server1 = MCPServerConfig("enabled_server", "npx", ["tool"], enabled=True)
            >>> server2 = MCPServerConfig("disabled_server", "npm", ["tool"], enabled=False)
            >>> config = MCPConfig(servers={"enabled_server": server1, "disabled_server": server2})
            >>> enabled_servers = config.get_enabled_servers()
            >>> enabled_servers
            {"enabled_server" : {"command": "npx", "args": ["tool"] , "enabled": True}}
            >>> "enabled_server" in enabled_servers
            True
        """
        return {name: config for name, config in self.servers.items() if config.enabled}


def load_mcp_config(config_path: str = "mcp_config.json") -> MCPConfig:
    """
    从文件加载MCP配置

    如果配置文件不存在，则返回空的MCPConfig实例。如果文件存在但解析失败，则打印警告并返回空配置。

    Args:
        config_path (str, optional): 配置文件路径，默认为"mcp_config.json"

    Returns:
        MCPConfig: 加载的配置实例或空配置实例

    Examples:
        >>> config = load_mcp_config("nonexistent.json")
        >>> isinstance(config, MCPConfig)
        True
    """
    if not os.path.exists(config_path):
        return MCPConfig()

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return MCPConfig.from_dict(data)
    except Exception as e:
        print(f"⚠️ 加载 MCP 配置失败: {e}，使用空配置")
        return MCPConfig()
