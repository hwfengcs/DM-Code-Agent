"""MCP 管理器 - 统一管理多个 MCP 服务器"""

from typing import Dict, List, Optional, Any
from .client import MCPClient
from .config import MCPConfig, MCPServerConfig
from ..tools.base import Tool


class MCPManager:
    """MCP 管理器，负责管理多个 MCP 客户端"""

    def __init__(self, config: Optional[MCPConfig] = None):
        """初始化 MCP 管理器

        Args:
            config: MCP 配置对象（可选）
        """
        self.config = config or MCPConfig()
        self.clients: Dict[str, MCPClient] = {}
        self._tools_cache: List[Tool] = []

    def start_all(self) -> int:
        """启动所有启用的 MCP 服务器

        Returns:
            成功启动的服务器数量
        """
        enabled_servers = self.config.get_enabled_servers()
        success_count = 0

        for name, server_config in enabled_servers.items():
            if self.start_server(name):
                success_count += 1

        if success_count > 0:
            self._rebuild_tools_cache()

        return success_count

    def start_server(self, name: str) -> bool:
        """启动指定的 MCP 服务器

        Args:
            name: 服务器名称

        Returns:
            是否启动成功
        """
        if name in self.clients and self.clients[name].is_running():
            print(f"⚠️ MCP 服务器 '{name}' 已在运行中")
            return True

        server_config = self.config.servers.get(name)
        if not server_config:
            print(f"❌ 未找到 MCP 服务器配置: {name}")
            return False

        if not server_config.enabled:
            print(f"⚠️ MCP 服务器 '{name}' 已禁用")
            return False

        # 创建并启动客户端
        client = MCPClient(
            name=name,
            command=server_config.command,
            args=server_config.args,
            env=server_config.env
        )

        if client.start():
            self.clients[name] = client
            self._rebuild_tools_cache()
            return True

        return False

    def stop_server(self, name: str) -> None:
        """停止指定的 MCP 服务器

        Args:
            name: 服务器名称
        """
        if name in self.clients:
            self.clients[name].stop()
            del self.clients[name]
            self._rebuild_tools_cache()

    def stop_all(self) -> None:
        """停止所有 MCP 服务器"""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()
        self._tools_cache.clear()

    def _rebuild_tools_cache(self) -> None:
        """重建工具缓存"""
        self._tools_cache.clear()

        for server_name, client in self.clients.items():
            if not client.is_running():
                continue

            mcp_tools = client.get_tools()
            for tool_def in mcp_tools:
                # 将 MCP 工具转换为我们的 Tool 对象
                tool_name = tool_def.get("name", "")
                description = tool_def.get("description", "")
                input_schema = tool_def.get("inputSchema", {})

                # 创建工具包装器
                wrapped_tool = self._create_tool_wrapper(
                    server_name=server_name,
                    tool_name=tool_name,
                    description=description,
                    input_schema=input_schema
                )
                self._tools_cache.append(wrapped_tool)

    def _create_tool_wrapper(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any]
    ) -> Tool:
        """创建 MCP 工具的包装器

        Args:
            server_name: MCP 服务器名称
            tool_name: 工具名称
            description: 工具描述
            input_schema: 输入参数 JSON Schema

        Returns:
            Tool 对象
        """
        # 构建完整的工具描述（包含参数信息）
        full_description = f"[MCP:{server_name}] {description}"

        # 如果有输入参数 schema，添加到描述中
        if input_schema and "properties" in input_schema:
            properties = input_schema["properties"]
            required = input_schema.get("required", [])

            params_desc = []
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "")
                is_required = param_name in required

                param_str = f'"{param_name}": {param_type}'
                if not is_required:
                    param_str = f"optional {param_str}"
                if param_desc:
                    param_str += f" ({param_desc})"

                params_desc.append(param_str)

            if params_desc:
                full_description += f". Arguments: {{{', '.join(params_desc)}}}"

        # 创建工具执行函数
        def runner(arguments: Dict[str, Any]) -> str:
            client = self.clients.get(server_name)
            if not client or not client.is_running():
                return f"❌ MCP 服务器 '{server_name}' 未运行"

            result = client.call_tool(tool_name, arguments)
            if result is None:
                return f"❌ 调用 MCP 工具 '{tool_name}' 失败"

            return result

        return Tool(
            name=f"mcp_{server_name}_{tool_name}",
            description=full_description,
            runner=runner
        )

    def get_tools(self) -> List[Tool]:
        """获取所有 MCP 工具

        Returns:
            工具列表
        """
        return self._tools_cache.copy()

    def get_running_servers(self) -> List[str]:
        """获取正在运行的服务器名称列表

        Returns:
            服务器名称列表
        """
        return [
            name for name, client in self.clients.items()
            if client.is_running()
        ]

    def get_server_status(self) -> Dict[str, bool]:
        """获取所有服务器的运行状态

        Returns:
            服务器名称到运行状态的映射
        """
        status = {}
        for name in self.config.servers.keys():
            client = self.clients.get(name)
            status[name] = client.is_running() if client else False
        return status

    def add_server_config(self, config: MCPServerConfig) -> None:
        """添加新的 MCP 服务器配置

        Args:
            config: 服务器配置
        """
        self.config.add_server(config)

    def remove_server_config(self, name: str) -> None:
        """移除 MCP 服务器配置

        Args:
            name: 服务器名称
        """
        # 先停止服务器（如果正在运行）
        self.stop_server(name)
        # 移除配置
        self.config.remove_server(name)
