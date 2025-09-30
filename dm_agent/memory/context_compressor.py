"""上下文压缩器 - 每 N 轮对话自动压缩上下文"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..clients.base_client import BaseLLMClient


class ContextCompressor:
    """每 N 轮对话自动压缩上下文"""

    def __init__(
        self, client: Optional[BaseLLMClient] = None, compress_every: int = 5, keep_recent: int = 3
    ):
        """
        初始化上下文压缩器

        Args:
            client: LLM 客户端（用于生成摘要）
            compress_every: 每多少轮对话触发一次压缩
            keep_recent: 保留最近的对话轮数
        """
        self.client = client
        self.compress_every = compress_every
        self.keep_recent = keep_recent
        self.turn_count = 0  # 对话轮数计数

    def should_compress(self, history: List[Dict[str, str]]) -> bool:
        """判断是否需要压缩"""
        # 统计用户消息数量（每个用户消息代表一轮对话）
        user_messages = [msg for msg in history if msg.get("role") == "user"]
        self.turn_count = len(user_messages)

        # 每 N 轮压缩一次
        return self.turn_count >= self.compress_every

    def compress(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        压缩对话历史

        策略：保留最近 N 轮对话，总结之前的历史

        Args:
            history: 对话历史列表

        Returns:
            压缩后的对话历史
        """
        if not history:
            return []

        # 分离系统消息和其他消息
        system_messages = [msg for msg in history if msg.get("role") == "system"]
        non_system = [msg for msg in history if msg.get("role") != "system"]

        # 保留最近的消息（keep_recent 轮 = keep_recent * 2 条消息）
        recent_messages = (
            non_system[-self.keep_recent * 2 :]
            if len(non_system) > self.keep_recent * 2
            else non_system
        )

        # 需要压缩的中间消息
        middle_messages = (
            non_system[: -self.keep_recent * 2] if len(non_system) > self.keep_recent * 2 else []
        )

        # 如果有中间消息，进行压缩
        compressed_middle = []
        if middle_messages:
            summary = self._extract_key_information(middle_messages)
            compressed_middle = [{"role": "user", "content": f"历史对话摘要：\n{summary}"}]

        # 组合：系统消息 + 压缩的中间历史 + 最近消息
        result = system_messages + compressed_middle + recent_messages

        # 重置计数器
        self.turn_count = len([msg for msg in result if msg.get("role") == "user"])

        return result

    def _extract_key_information(self, messages: List[Dict[str, str]]) -> str:
        """
        提取式摘要：提取关键信息

        提取：
        - 文件路径
        - 工具调用
        - 错误信息
        - 完成的任务
        """
        key_info = []

        # 提取文件路径
        file_paths = set()
        for msg in messages:
            content = msg.get("content", "")
            # 查找文件路径模式
            paths = re.findall(
                r"(?:path|文件|读取|创建|编辑)[:：]\s*([^\s,，;；\n]+\.[a-zA-Z]+)", content
            )
            file_paths.update(paths)

        if file_paths:
            key_info.append(f"涉及文件：{', '.join(sorted(file_paths))}")

        # 提取工具调用
        tools_used = set()
        for msg in messages:
            content = msg.get("content", "")
            # 查找工具名称
            if "执行工具" in content:
                tool_match = re.search(r"执行工具\s+(\w+)", content)
                if tool_match:
                    tools_used.add(tool_match.group(1))

        if tools_used:
            key_info.append(f"使用的工具：{', '.join(sorted(tools_used))}")

        # 提取错误信息
        errors = []
        for msg in messages:
            content = msg.get("content", "")
            if any(
                keyword in content
                for keyword in ["错误", "error", "Error", "失败", "异常"]
            ):
                # 提取错误相关的行（限制长度）
                error_lines = [
                    line
                    for line in content.split("\n")
                    if any(
                        kw in line
                        for kw in ["错误", "error", "Error", "失败", "异常"]
                    )
                ]
                errors.extend(error_lines[:2])  # 最多保留 2 条

        if errors:
            key_info.append(f"遇到的错误：\n" + "\n".join(errors))

        # 提取完成的任务
        completed = []
        for msg in messages:
            content = msg.get("content", "")
            if "完成" in content or "成功" in content:
                # 提取相关行
                completed_lines = [
                    line
                    for line in content.split("\n")
                    if "完成" in line or "成功" in line
                ]
                completed.extend(completed_lines[:2])

        if completed:
            key_info.append(f"已完成的操作：\n" + "\n".join(completed))

        # 如果没有提取到任何信息，返回通用摘要
        if not key_info:
            return f"进行了 {len(messages)} 轮对话，讨论了代码相关任务。"

        return "\n\n".join(key_info)

    def get_compression_stats(
        self, original: List[Dict[str, str]], compressed: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """获取压缩统计信息"""
        return {
            "original_messages": len(original),
            "compressed_messages": len(compressed),
            "compression_ratio": (
                1 - len(compressed) / len(original) if len(original) > 0 else 0
            ),
            "saved_messages": len(original) - len(compressed),
        }