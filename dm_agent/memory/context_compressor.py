"""上下文压缩器 - 每 N 轮对话自动压缩上下文"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..clients.base_client import BaseLLMClient


class ContextCompressor:

    """
    每 N 轮对话自动压缩上下文

    上下文压缩器用于管理长时间对话中的token消耗问题。通过定期压缩历史对话记录，
    保持重要的上下文信息同时减少token使用量，从而支持更长的对话序列。
    
    Attributes:
        client (Optional[BaseLLMClient]): LLM客户端，用于生成摘要（当前未使用）
        compress_every (int): 每多少轮对话触发一次压缩
        keep_recent (int): 保留最近的对话轮数
        turn_count (int): 对话轮数计数器
    """

    def __init__(
        self, client: Optional[BaseLLMClient] = None, compress_every: int = 5, keep_recent: int = 3
    ):
        """
        初始化上下文压缩器
        
        Args:
            client (Optional[BaseLLMClient], optional): LLM 客户端（用于生成摘要），当前实现中未使用
            compress_every (int, optional): 每多少轮对话触发一次压缩，默认为5轮
            keep_recent (int, optional): 保留最近的对话轮数，默认为3轮
            
        Examples:
            >>> compressor = ContextCompressor(compress_every=3, keep_recent=2)
            >>> print(compressor.compress_every)
            3
        """
        self.client = client
        self.compress_every = compress_every
        self.keep_recent = keep_recent
        self.turn_count = 0  # 对话轮数计数

    def should_compress(self, history: List[Dict[str, str]]) -> bool:
        """
        判断是否需要压缩对话历史
        
        通过统计用户消息数量来确定当前对话轮数，当达到设定阈值时返回True
        
        Args:
            history (List[Dict[str, str]]): 对话历史列表，每个元素包含role和content键
            
        Returns:
            bool: 当对话轮数达到压缩阈值时返回True，否则返回False
            
        Examples:
            >>> history = [
            ...     {"role": "user", "content": "你好"},
            ...     {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"},
            ...     {"role": "user", "content": "分析一下这个项目"}
            ... ]
            >>> compressor = ContextCompressor(compress_every=2)
            >>> compressor.should_compress(history)
            True
        """
        # 统计用户消息数量（每个用户消息代表一轮对话）
        user_messages = [msg for msg in history if msg.get("role") == "user"]
        self.turn_count = len(user_messages)

        # 每 N 轮压缩一次
        return self.turn_count >= self.compress_every

    def compress(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        压缩对话历史
        
        采用提取关键信息的策略，保留最近N轮对话，将之前的对话历史压缩为摘要信息
        
        Args:
            history (List[Dict[str, str]]): 原始对话历史列表
            
        Returns:
            result (List[Dict[str, str]]): 压缩后的对话历史列表
            
        Examples:
            >>> history = [
            ...     {"role": "system", "content": "你是一个代码助手"},
            ...     {"role": "user", "content": "分析项目结构"},
            ...     {"role": "assistant", "content": "正在分析..."},
            ...     {"role": "user", "content": "读取文件A"},
            ...     {"role": "assistant", "content": "已读取文件A"},
            ...     {"role": "user", "content": "读取文件B"},
            ...     {"role": "assistant", "content": "已读取文件B"}
            ... ]
            >>> compressor = ContextCompressor(keep_recent=1)
            >>> compressed = compressor.compress(history)
            >>> len(compressed)
            4  # 系统消息 + 摘要 + 最近1轮对话(2条消息)
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
        提取式摘要：从对话历史中提取关键信息
        
        通过正则表达式识别和提取对话中的关键信息，包括文件路径、工具调用、错误信息和完成的任务
        
        Args:
            messages (List[Dict[str, str]]): 需要提取信息的对话消息列表
            
        Returns:
            str: 格式化的关键信息摘要字符串
            
        Examples:
            >>> messages = [
            ...     {"role": "user", "content": "读取文件：main.py"},
            ...     {"role": "assistant", "content": "执行工具 read_file，输入：{'path': 'main.py'}"},
            ...     {"role": "user", "content": "观察：成功读取文件"}
            ... ]
            >>> compressor = ContextCompressor()
            >>> summary = compressor._extract_key_information(messages)
            >>> "涉及文件" in summary
            True
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
        """
        获取压缩统计信息
        
        计算并返回压缩前后的统计信息，包括消息数量、压缩率和节省的消息数
        
        Args:
            original (List[Dict[str, str]]): 原始对话历史
            compressed (List[Dict[str, str]]): 压缩后的对话历史
            
        Returns:
            stats (Dict[str, Any]): 包含压缩统计信息的字典
                - original_messages (int): 原始消息数量
                - compressed_messages (int): 压缩后消息数量
                - compression_ratio (float): 压缩率 (0-1之间)
                - saved_messages (int): 节省的消息数量
                
        Examples:
            >>> original = [{"role": "user", "content": "1"}, {"role": "assistant", "content": "2"}]
            >>> compressed = [{"role": "user", "content": "历史对话摘要：..."}]
            >>> stats = compressor.get_compression_stats(original, compressed)
            >>> stats["saved_messages"]
            1
        """
        return {
            "original_messages": len(original),
            "compressed_messages": len(compressed),
            "compression_ratio": (
                1 - len(compressed) / len(original) if len(original) > 0 else 0
            ),
            "saved_messages": len(original) - len(compressed),
        }
