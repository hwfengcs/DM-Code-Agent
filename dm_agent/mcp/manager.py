"""MCP 管理器 - 统一管理多个 MCP 服务器"""

from typing import Dict, List, Optional, Any
from .client import MCPClient
from .config import MCPConfig, MCPServerConfig
from ..tools.base import Tool


class MCPManager:
    """
    MCP管理器提供了对多个MCP（Model Control Protocol）服务器的统一管理接口，
    包括启动、停止服务器以及获取可用工具等功能。它维护了所有运行中的MCP客户端
    并缓存它们提供的工具，以便系统可以方便地访问这些外部工具。
    
    Attributes:
        config (MCPConfig): MCP配置对象，包含所有服务器的配置信息
        clients (Dict[str, MCPClient]): 服务器名称到客户端实例的映射
        _tools_cache (List[Tool]): 缓存的工具列表，提高工具访问效率
    """

    def __init__(self, config: Optional[MCPConfig] = None):
        """
        初始化 MCP 管理器
        
        Args:
            config (Optional[MCPConfig], optional): MCP 配置对象，如果未提供则使用默认空配置
            
        """
        self.config = config or MCPConfig()
        self.clients: Dict[str, MCPClient] = {}
        self._tools_cache: List[Tool] = []

    def start_all(self) -> int:
        """
        启动所有启用的 MCP 服务器
        
        遍历配置中所有启用的服务器，并尝试启动它们。成功启动后重建工具缓存。

        Returns:
            success_count (int): 成功启动的服务器数量
            
        Examples:
            >>> manager = MCPManager()
            >>> started_count = manager.start_all()
            >>> isinstance(started_count, int)
            True
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
        """
        启动指定的 MCP 服务器
        
        检查服务器是否已经在运行，如果未运行则根据配置创建并启动新的客户端实例。

        Args:
            name (str): 服务器名称

        Returns:
            bool: 是否启动成功
            
        Examples:
            >>> manager = MCPManager()
            >>> success = manager.start_server("nonexistent_server")
            >>> isinstance(success, bool)
            True
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
        """
        停止指定的 MCP 服务器
        
        停止指定名称的MCP服务器进程，并从客户端字典中移除，最后重建工具缓存。

        Args:
            name (str): 服务器名称
            
        Examples:
            >>> manager = MCPManager()
            >>> manager.stop_server("test_server")  # 即使服务器不存在也不会出错
        """
        if name in self.clients:
            self.clients[name].stop()
            del self.clients[name]
            self._rebuild_tools_cache()

    def stop_all(self) -> None:
        """
        停止所有 MCP 服务器
        
        停止所有正在运行的MCP服务器进程，并清空客户端字典和工具缓存。
        
        Examples:
            >>> manager = MCPManager()
            >>> manager.stop_all()  # 停止所有服务器
        """
        for client in self.clients.values():
            client.stop()
        self.clients.clear()
        self._tools_cache.clear()

    def _rebuild_tools_cache(self) -> None:
        """
        重建工具缓存
        
        遍历所有运行中的MCP客户端，获取它们提供的工具，并将这些工具转换为系统
        可用的Tool对象，存储在工具缓存中以提高访问效率。
        """
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
        """
        创建 MCP 工具的包装器
        
        将MCP服务器提供的工具封装为系统可用的Tool对象，包括构建工具描述和执行函数。

        Args:
            server_name (str): MCP 服务器名称
            tool_name (str): 工具名称
            description (str): 工具描述
            input_schema (Dict[str, Any]): 输入参数 JSON Schema

        Returns:
            Tool: 封装后的Tool对象
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
            """
            工具执行函数
            
            Args:
                arguments (Dict[str, Any]): 工具执行参数
                
            Returns:
                str: 工具执行结果
            """
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
        """
        获取所有 MCP 工具
        
        返回当前缓存的所有MCP工具的副本，确保外部修改不会影响内部缓存。

        Returns:
            List[Tool]: 工具列表的副本
            
        Examples:
            >>> manager = MCPManager()
            >>> tools = manager.get_tools()
            >>> isinstance(tools, list)
            True
        """
        return self._tools_cache.copy()

    def get_running_servers(self) -> List[str]:
        """
        获取正在运行的服务器名称列表
        
        返回当前所有正在运行的MCP服务器名称列表。

        Returns:
            List[str]: 服务器名称列表
            
        Examples:
            >>> manager = MCPManager()
            >>> running = manager.get_running_servers()
            >>> isinstance(running, list)
            True
        """
        return [
            name for name, client in self.clients.items()
            if client.is_running()
        ]

    def get_server_status(self) -> Dict[str, bool]:
        """
        获取所有服务器的运行状态
        
        返回配置中所有服务器的运行状态映射。

        Returns:
            status (Dict[str, bool]): 服务器名称到运行状态的映射
            
        Examples:
            >>> manager = MCPManager()
            >>> status = manager.get_server_status()
            >>> isinstance(status, dict)
            True
        """
        status = {}
        for name in self.config.servers.keys():
            client = self.clients.get(name)
            status[name] = client.is_running() if client else False
        return status

    def add_server_config(self, config: MCPServerConfig) -> None:
        """
        添加新的 MCP 服务器配置
        
        将新的服务器配置添加到管理器的配置中。

        Args:
            config (MCPServerConfig): 服务器配置
            
        Examples:
            >>> from dm_agent.mcp.config import MCPServerConfig
            >>> manager = MCPManager()
            >>> config = MCPServerConfig("test", "npx", ["tool"])
            >>> manager.add_server_config(config)  # 添加配置
        """
        self.config.add_server(config)

    def remove_server_config(self, name: str) -> None:
        """
        移除 MCP 服务器配置
        
        先停止指定的服务器（如果正在运行），然后从配置中移除。

        Args:
            name (str): 服务器名称
            
        Examples:
            >>> manager = MCPManager()
            >>> manager.remove_server_config("test_server")  # 移除配置
        """
        # 先停止服务器（如果正在运行）
        self.stop_server(name)
        # 移除配置
        self.config.remove_server(name)
