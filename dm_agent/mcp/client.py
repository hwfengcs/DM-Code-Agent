"""MCP 客户端 - 负责与单个 MCP 服务器通信"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
from threading import Thread, Lock
from queue import Queue, Empty


class MCPClient:
    """MCP 客户端，负责与单个 MCP 服务器进程通信"""

    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        """初始化 MCP 客户端

        Args:
            name: MCP 服务器名称
            command: 启动命令（如 'npx'）
            args: 命令参数列表（如 ['@playwright/mcp@latest']）
            env: 环境变量（可选）
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
        """启动 MCP 服务器进程

        Returns:
            是否启动成功
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
        """停止 MCP 服务器进程"""
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
        """后台线程：读取标准输出"""
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
        """发送 JSON-RPC 消息到 MCP 服务器

        Args:
            method: JSON-RPC 方法名
            params: 参数字典

        Returns:
            响应数据，失败返回 None
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
                self.process.stdin.write(json.dumps(message) + "\n")
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
        """初始化 MCP 连接并获取工具列表

        Returns:
            是否初始化成功
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
        """调用 MCP 工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果，失败返回 None
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
        """获取此 MCP 服务器提供的工具列表

        Returns:
            工具定义列表
        """
        return self.tools.copy()

    def is_running(self) -> bool:
        """检查 MCP 服务器是否正在运行

        Returns:
            是否运行中
        """
        return self.process is not None and self.process.poll() is None
