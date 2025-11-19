"""MCP 客户端 - 负责与单个 MCP 服务器通信"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
from threading import Thread, Lock
from queue import Queue, Empty


class MCPClient: 
    """
    MCP客户端负责与单个MCP服务器进程进行通信，通过标准输入/输出与外部MCP服务器交互，
    实现工具列表获取和工具调用等功能。该客户端使用多线程处理服务器响应，并通过
    JSON-RPC协议与服务器通信。
    
    Attributes:
        name (str): MCP服务器名称
        command (str): 启动命令
        args (List[str]): 命令参数列表
        env (Optional[Dict[str, str]]): 环境变量
        process (Optional[subprocess.Popen]): 服务器进程对象
        tools (List[Dict[str, Any]]): 服务器提供的工具列表
        _lock (Lock): 线程锁，用于保护消息发送过程
        _message_id (int): 消息ID计数器，确保请求与响应匹配
        _stdout_queue (Queue): 标准输出消息队列
        _running (bool): 客户端运行状态标志
        _stdout_thread (Thread): 读取标准输出的后台线程
    """

    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        """
        初始化 MCP 客户端
        
        Args:
            name (str): MCP 服务器名称，用作唯一标识符
            command (str): 启动命令（如 'npx'、'python' 等）
            args (List[str]): 命令参数列表（如 ['@playwright/mcp@latest']）
            env (Optional[Dict[str, str]], optional): 环境变量字典，None表示使用默认环境
            
        Examples:
            >>> client = MCPClient("playwright", "npx", ["@playwright/mcp@latest"])
            >>> client.name
            'playwright'
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self._lock = Lock()
        self._message_id = 0
        self._stdout_queue: Queue = Queue()
        self._running = False

    def start(self) -> bool:
        """
        启动 MCP 服务器进程
        
        根据配置启动MCP服务器子进程，并初始化与服务器的连接，获取可用工具列表。

        Returns:
            bool: 是否启动成功
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> success = client.start()
            >>> isinstance(success, bool)
            True
        """
        try:
            # 构建完整命令
            full_command = [self.command] + self.args

            # 准备环境变量（合并当前环境和自定义环境）
            process_env = os.environ.copy()
            if self.env:
                process_env.update(self.env)

            # Windows 平台特殊处理
            is_windows = sys.platform == 'win32'

            # 启动子进程
            if is_windows:
                # Windows 需要 shell=True 来找到 npx 等命令
                self.process = subprocess.Popen(
                    ' '.join(full_command),  # Windows 下使用字符串命令
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=process_env,
                    shell=True  # Windows 必需
                )
            else:
                # Unix/Linux/macOS
                self.process = subprocess.Popen(
                    full_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=process_env
                )

            # 启动输出读取线程
            self._running = True
            self._stdout_thread = Thread(target=self._read_stdout, daemon=True)
            self._stdout_thread.start()

            # 初始化 MCP 连接并获取工具列表
            if not self._initialize():
                self.stop()
                return False

            print(f"✅ MCP 服务器 '{self.name}' 启动成功，提供 {len(self.tools)} 个工具")
            return True

        except Exception as e:
            print(f"❌ 启动 MCP 服务器 '{self.name}' 失败: {e}")
            return False

    def stop(self) -> None:
        """
        停止 MCP 服务器进程
        
        终止MCP服务器子进程并清理相关资源，确保进程被完全停止。
        
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> client.stop()  # 停止服务器进程
        """
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        print(f"🛑 MCP 服务器 '{self.name}' 已停止")

    def _read_stdout(self) -> None:
        """
        后台线程：读取标准输出
        
        在独立线程中持续读取MCP服务器的标准输出，并将读取到的行放入队列中，
        供主线程处理响应消息使用。该方法在单独的守护线程中运行。
        """
        if not self.process or not self.process.stdout:
            return

        while self._running and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if line:
                    self._stdout_queue.put(line.strip())
            except Exception as e:
                if self._running:
                    print(f"⚠️ 读取 MCP 输出错误: {e}")
                break

    def _send_message(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        发送 JSON-RPC 消息到 MCP 服务器
        
        通过标准输入向MCP服务器发送JSON-RPC格式的请求消息，并等待对应的响应。

        Args:
            method (str): JSON-RPC 方法名，如"initialize"、"tools/list"等
            params (Optional[Dict[str, Any]], optional): 请求参数字典

        Returns:
               Optional[Dict[str, Any]]: 响应数据字典，失败时返回None
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> # response = client._send_message("test_method", {"key": "value"})
            >>> # 注意：这个方法通常由其他方法内部调用
        """
        if not self.process or not self.process.stdin:
            return None

        with self._lock:
            self._message_id += 1
            message = {
                "jsonrpc": "2.0",
                "id": self._message_id,
                "method": method,
            }
            if params:
                message["params"] = params

            try:
                # 发送消息
                # 将消息转为JSON字符串并通过标准输入发送
                self.process.stdin.write(json.dumps(message) + "\n")
                # 刷新缓冲区确保消息立即发送
                self.process.stdin.flush()

                # 等待响应
                timeout_count = 0
                while timeout_count < 50:  # 5 秒超时
                    try:
                        response_line = self._stdout_queue.get(timeout=0.1)
                        response = json.loads(response_line)

                        # 检查是否是我们的响应
                        if response.get("id") == self._message_id:
                            if "error" in response:
                                print(f"❌ MCP 错误: {response['error']}")
                                return None
                            return response.get("result")

                        # 不是我们的响应，放回队列
                        self._stdout_queue.put(response_line)
                    except Empty:
                        timeout_count += 1
                    except json.JSONDecodeError:
                        continue

                print(f"⚠️ MCP 响应超时")
                return None

            except Exception as e:
                print(f"❌ 发送 MCP 消息失败: {e}")
                return None

    def _initialize(self) -> bool:
        """
        初始化 MCP 连接并获取工具列表
        
        发送初始化请求到MCP服务器，建立连接并获取服务器提供的工具列表。

        Returns:
            bool: 是否初始化成功
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> # success = client._initialize()
            >>> # 注意：这个方法通常由start方法内部调用
        """
        # 发送初始化请求
        result = self._send_message("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "dm-code-agent",
                "version": "1.1.0"
            }
        })

        if not result:
            return False

        # 获取工具列表
        tools_result = self._send_message("tools/list")
        if tools_result and "tools" in tools_result:
            self.tools = tools_result["tools"]
            return True

        return False

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """
        调用 MCP 工具
        
        向MCP服务器发送工具调用请求，并返回工具执行结果。

        Args:
            tool_name (str): 工具名称
            arguments (Dict[str, Any]): 工具参数字典

        Returns:
            Optional[str]: 工具执行结果文本，失败时返回None
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> # result = client.call_tool("test_tool", {"param": "value"})
            >>> # 注意：需要服务器实际运行才能调用工具
        """
        result = self._send_message("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if result and "content" in result:
            # 提取内容（可能是数组）
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                # 获取第一个内容项的文本
                first_item = content[0]
                if isinstance(first_item, dict) and "text" in first_item:
                    return first_item["text"]
                return str(first_item)
            return str(content)

        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        获取此 MCP 服务器提供的工具列表
        
        返回服务器提供的工具定义列表的副本，确保外部修改不会影响内部状态。

        Returns:
            tools (List[Dict[str, Any]]): 工具定义列表的副本
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> tools = client.get_tools()
            >>> isinstance(tools, list)
            True
        """
        return self.tools.copy()

    def is_running(self) -> bool:
        """
        检查 MCP 服务器是否正在运行
        
        通过检查子进程是否存在且未终止来判断服务器运行状态。

        Returns:
            bool: 是否运行中
            
        Examples:
            >>> client = MCPClient("test", "echo", ["hello"])
            >>> running = client.is_running()
            >>> isinstance(running, bool)
            True
        """
        return self.process is not None and self.process.poll() is None
