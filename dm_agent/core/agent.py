"""由 LLM API 驱动的 ReAct 风格智能体。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..clients.base_client import BaseLLMClient
from ..tools.base import Tool
from ..prompts import build_code_agent_prompt
from ..memory.context_compressor import ContextCompressor
from .planner import TaskPlanner, PlanStep
from ..reflection import reflection

@dataclass
class Step:
    """表示智能体的一个推理步骤。"""

    thought: str                 # 智能体的思考过程
    action: str                  # 要执行的动作/工具名称
    action_input: Any            # 动作的输入参数
    observation: str             # 执行动作后的观察结果
    raw: str = ""                # 原始响应内容


class ReactAgent:  
    """
    ReAct Agent 实现了推理(Reasoning)和行动(Action)的循环模式，允许智能体通过与环境交互来解决问题。
    它结合了任务规划、上下文压缩等功能，提供了一个完整的智能体执行框架。
    
    Attributes:
        client (BaseLLMClient): 用于与大语言模型通信的客户端
        tools (Dict[str, Tool]): 可用工具的字典映射，键为工具名称
        tools_list (List[Tool]): 工具列表，用于规划器初始化
        max_steps (int): 最大执行步骤数
        temperature (float): LLM生成文本的温度参数
        system_prompt (str): 系统提示词
        step_callback (Optional[Callable[[int, Step], None]]): 步骤执行回调函数
        enable_planning (bool): 是否启用任务规划功能
        enable_compression (bool): 是否启用上下文压缩功能
        conversation_history (List[Dict[str, str]]): 对话历史记录
        planner (Optional[TaskPlanner]): 任务规划器实例
        compressor (Optional[ContextCompressor]): 上下文压缩器实例
    """

    def __init__(
        self,
        client: BaseLLMClient,
        tools: List[Tool],
        *,
        max_steps: int = 200,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
        step_callback: Optional[Callable[[int, Step], None]] = None,
        enable_planning: bool = True,
        enable_compression: bool = True,
        skill_manager: Optional[Any] = None,
        enable_rag: bool = True,
        rag_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        初始化 ReactAgent 实例
        
        Args:
            client (BaseLLMClient): LLM客户端实例
            tools (List[Tool]): 可用工具列表
            max_steps (int, optional): 最大执行步骤数，默认为200
            temperature (float, optional): LLM生成文本的温度参数，默认为0.0
            system_prompt (Optional[str], optional): 系统提示词，默认为None，将使用默认构建的提示词
            step_callback (Optional[Callable[[int, Step], None]], optional):
                步骤执行回调函数，可用于实时监控执行过程，默认为None
            enable_planning (bool, optional): 是否启用任务规划功能，默认为True
            enable_compression (bool, optional): 是否启用上下文压缩功能，默认为True
            enable_rag (bool, optional): 是否启用RAG功能，默认为True
            rag_config (Optional[Dict[str, Any]], optional): RAG配置字典，包含：
                - model_path: BGE-M3模型路径
                - db_path: Milvus数据库路径
                - data_dir: 文档目录路径
                - llama_parse_api_key: LlamaParse API密钥
            
        Raises:
            ValueError: 当提供的工具列表为空时抛出异常
            
        Examples:
            >>> from dm_agent.clients import OpenAIClient
            >>> from dm_agent.tools import default_tools
            >>> 
            >>> client = OpenAIClient(api_key="your-api-key")
            >>> tools = default_tools()
            >>> agent = ReactAgent(client, tools, max_steps=50)
            >>> result = agent.run("分析项目代码结构")
        """
        if not tools:
            raise ValueError("必须为 ReactAgent 提供至少一个工具。")
        self.client = client

        self.tools = {tool.name: tool for tool in tools}
        self.tools_list = tools
        self.max_steps = max_steps
        self.temperature = temperature
        self.system_prompt = system_prompt or build_code_agent_prompt(tools, "暂无参考内容")
        self.step_callback = step_callback
        self.conversation_history: List[Dict[str, str]] = []

        self.enable_planning = enable_planning
        self.planner = TaskPlanner(client, tools) if enable_planning else None

        self.enable_compression = enable_compression
        self.compressor = ContextCompressor(client, compress_every=5, keep_recent=3) if enable_compression else None

        self.skill_manager = skill_manager
        self._base_system_prompt = self.system_prompt
        self._base_tools = dict(self.tools)

        self.enable_rag = enable_rag
        self.rag_manager = None
        self._log_file_path = Path(__file__).parent.parent / "log" / "logs.txt"
        if enable_rag:
            try:
                from ..rag.rag_manager import RAGManager
                self.rag_manager = RAGManager()
                if rag_config:
                    if "model_path" in rag_config:
                        self.rag_manager._model_path = rag_config["model_path"]
                    if "db_path" in rag_config:
                        self.rag_manager._db_path = rag_config["db_path"]
                    if "data_dir" in rag_config:
                        self.rag_manager._data_dir = rag_config["data_dir"]
                    if "llama_parse_api_key" in rag_config:
                        self.rag_manager._llama_parse_api_key = rag_config["llama_parse_api_key"]

                self.rag_manager.initialize()
            except ImportError:
                print("警告: RAG依赖未安装，跳过RAG初始化")
                self.enable_rag = False
            except Exception as e:
                print(f"警告: RAG初始化失败: {e}")
                self.enable_rag = False

    def _log_conversation_history(self, action_description: str = "conversation_history 变动") -> None:
        """记录 conversation_history 变动到日志文件"""
        try:
            self._log_file_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self._log_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] {action_description}\n")
                f.write(f"{'='*80}\n")
                for idx, msg in enumerate(self.conversation_history, 1):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    f.write(f"\n消息 #{idx} [{role}]:\n")
                    f.write(f"{content}\n")
                f.write(f"\n当前历史记录长度: {len(self.conversation_history)} 条消息\n")
        except Exception as e:
            print(f"⚠️ 日志记录失败: {e}")

    def run(self, task: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
        """
        执行指定任务
        
        该方法实现了完整的ReAct循环，包括任务规划、推理、行动和观察等阶段。它支持上下文压缩以
        控制token消耗，并提供回调机制用于监控执行过程。
        
        Args:
            task (str): 要执行的任务描述
            max_steps (Optional[int], optional): 覆盖默认的最大步骤数
            
        Returns:
            result (Dict[str, Any]): 包含最终答案和执行步骤的字典
                    - final_answer (str): 任务执行的最终结果
                    - steps (List[Dict]): 执行的所有步骤信息列表
                
        Raises:
            ValueError: 当任务不是非空字符串时抛出异常
            
        Examples:
            >>> result = agent.run("帮我分析项目的代码结构")
            >>> print(result["final_answer"])
            '已成功分析项目代码结构...'
        """
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串。")

        steps: List[Step] = []
        limit = max_steps or self.max_steps # 获取最大步骤数

        retry_time = 0
        retry_action: string = ''

        # 技能自动选择
        if self.skill_manager:
            self._apply_skills_for_task(task)

        # RAG检索 - 在任务执行前获取相关文档
        if self.enable_rag and self.rag_manager and self.rag_manager.is_initialized():
            try:
                rag_results = self.rag_manager.search(task, top_k=5)
                if rag_results:
                    formatted_refs = self._format_rag_results(rag_results)
                    # 重新构建包含RAG结果的system_prompt
                    self.system_prompt = build_code_agent_prompt(
                        list(self.tools.values()), 
                        formatted_refs
                    )
                    print(f"🔍 RAG检索到 {len(rag_results)} 条相关文档")
            except Exception as e:
                print(f"⚠️ RAG检索失败: {e}，使用原始prompt")

        # 第一步：生成计划（如果启用）
        plan : List[PlanStep] = []
        if self.enable_planning and self.planner:
            try:
                plan = self.planner.plan(task)
                if plan:
                    plan_text = self.planner.get_progress()
                    print(f"\n📋 生成的执行计划：\n{plan_text}")
            except Exception as e:
                print(f"⚠️ 计划生成失败：{e}，将使用常规模式执行")

        # 添加新任务到对话历史
        task_prompt : str = self._build_user_prompt(task, steps, plan)
        self.conversation_history.append({"role": "user", "content": task_prompt})
        self._log_conversation_history("添加新任务到对话历史")

        for step_num in range(1, limit + 1):
            # 第二步：压缩上下文（如果需要）
            messages_to_send = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

            if self.enable_compression and self.compressor:
                if self.compressor.should_compress(self.conversation_history):
                    print(f"\n🗜️ 压缩对话历史以节省 token...")
                    compressed_history = self.compressor.compress(self.conversation_history)
                    messages_to_send = [{"role": "system", "content": self.system_prompt}] + compressed_history

                    # 显示压缩统计
                    stats = self.compressor.get_compression_stats(
                        self.conversation_history, compressed_history
                    )
                    print(
                        f"   压缩率：{stats['compression_ratio']:.1%}，"
                        f"节省 {stats['saved_messages']} 条消息"
                    )

            # 获取 AI 响应
            raw = self.client.respond(messages_to_send, temperature=self.temperature)

            self.conversation_history.append({"role": "assistant", "content": raw})
            self._log_conversation_history("添加 AI 响应到历史记录")
            try:
                parsed = self._parse_agent_response(raw)
            except ValueError as exc:
                observation = f"解析智能体响应失败：{exc}"
                step = Step(
                    thought="",
                    action="error",
                    action_input={},
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                self.conversation_history.append({"role": "user", "content": f"观察：{observation}"})
                self._log_conversation_history("添加错误观察到历史记录")

                if self.step_callback:
                    self.step_callback(step_num, step)
                continue
            
            # 获取动作、thought 和输入
            action = parsed.get("action", "").strip()
            thought = parsed.get("thought", "").strip()
            action_input = parsed.get("action_input")
            
            # 检查是否完成
            if action == "finish":
                final = self._format_final_answer(action_input)
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation="<finished>",
                    raw=raw,
                )
                steps.append(step)

                self.conversation_history.append({"role": "user", "content": f"任务完成：{final}"})
                self._log_conversation_history("添加任务完成标记到历史记录")

                if self.step_callback:
                    self.step_callback(step_num, step)
                return {"final_answer": final, "steps": [step.__dict__ for step in steps]}
            
            # 检查工具
            tool = self.tools.get(action)
            if tool is None:
                observation = f"未知工具 '{action}'。"
                step = Step(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                    raw=raw,
                )
                steps.append(step)

                self.conversation_history.append({"role": "user", "content": f"观察：{observation}"})
                self._log_conversation_history("添加未知工具观察到历史记录")

                if self.step_callback:
                    self.step_callback(step_num, step)
                continue

            # task_complete 工具可以接受字符串或空参数
            if action == "task_complete":
                if action_input is None:
                    action_input = {}
                elif isinstance(action_input, str):
                    action_input = {"message": action_input}
                elif not isinstance(action_input, dict):
                    action_input = {}
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    observation = f"工具执行失败：{exc}"
            elif action_input is None:
                observation = "工具参数缺失（action_input 为 null）。"
            elif not isinstance(action_input, dict):
                observation = "工具参数必须是 JSON 对象。"
            else:
                try:
                    observation = tool.execute(action_input)
                except Exception as exc:  # noqa: BLE001 - 将工具错误传递给 LLM
                    observation = f"工具执行失败：{exc}"

            step = Step(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                raw=raw,
            )
            steps.append(step)

            # 更新计划进度（如果有计划）
            if plan and self.planner:
                # 查找当前步骤对应的计划步骤
                for plan_step in plan:
                    if plan_step.action == action and not plan_step.completed:
                        self.planner.mark_completed(plan_step.step_number, observation)
                        break

            tool_info = f"执行工具 {action}，输入：{json.dumps(action_input, ensure_ascii=False)}\n观察：{observation}"
            self.conversation_history.append({"role": "user", "content": tool_info})
            self._log_conversation_history(f"添加工具执行结果到历史记录 (工具: {action})")

            if self.step_callback:
                self.step_callback(step_num, step)

            # 检查是否调用了 task_complete 工具
            if action == "task_complete" and not observation.startswith("工具执行失败"):
                return {
                    "final_answer": observation,
                    "steps": [step.__dict__ for step in steps],
                }

            if self.enable_planning and self.planner:
                #检查是否要触发反思机制
                if action == retry_action:
                    retry_time += 1
                    if retry_time >= 2:  # 连续失败3次则触发反思
                        step = Step(
                            thought="由于一些不知名的原因，触发了三次重试重计划机制，需要重新制定计划",
                            action="replan",
                            action_input=action,
                            observation="触发了三次重试重计划机制，需要重新制定计划",
                            raw=raw,
                        )
                        steps.append(step)
                        print(f"\n 触发重新计划中...")
                        plan = self.planner.replan(task, plan, f"连续重试失败，最后一次失败的工具：{action}")
                        if plan:
                            plan_text = self.planner.get_progress()
                            print(f"\n📋 重新生成的执行计划：\n{plan_text}")
                        task_prompt = self._build_user_prompt(task, steps, plan)
                        self.conversation_history.append({"role": "user", "content": task_prompt})
                        self._log_conversation_history("添加重新计划的任务提示到历史记录")
                        retry_action = ""
                        retry_time = 0
                else:
                    retry_time = 0
                    retry_action = action

        return {
            "final_answer": "达到步骤限制但未完成。",
            "steps": [step.__dict__ for step in steps],
        }

    def _apply_skills_for_task(self, task: str) -> None:
        """根据任务自动选择并激活相关技能。"""
        # 恢复基础状态，避免上一次任务的技能残留
        self.system_prompt = self._base_system_prompt
        self.tools = dict(self._base_tools)

        # 自动选择
        selected = self.skill_manager.select_skills_for_task(task)
        if not selected:
            self.skill_manager.deactivate_all()
            return

        # 激活选中技能
        self.skill_manager.activate_skills(selected)

        # 追加技能 prompt
        prompt_addition = self.skill_manager.get_active_prompt_additions()
        if prompt_addition:
            self.system_prompt += prompt_addition

        # 合并技能工具
        skill_tools = self.skill_manager.get_active_tools()
        for tool in skill_tools:
            self.tools[tool.name] = tool

        # 打印激活信息
        display_names = []
        for name in selected:
            skill = self.skill_manager.skills.get(name)
            if skill:
                display_names.append(skill.get_metadata().display_name)
        if display_names:
            print(f"\n🎯 已激活技能：{', '.join(display_names)}")

    def _build_user_prompt(self, task: str, steps: List[Step], plan: List[PlanStep] = None) -> str:
        """
        构建用户提示词
        
        Args:
            task (str): 当前任务描述
            steps (List[Step]): 已执行的步骤列表
            plan (List[PlanStep], optional): 执行计划
            
        Returns:
            prompt (str): 构建好的用户提示词字符串
        """
        lines : List[str] = [f"任务：{task.strip()}"]

        # 如果有计划，添加到提示中
        if plan:
            lines.append("\n执行计划：")
            for plan_step in plan:
                status = "✓" if plan_step.completed else "○"
                lines.append(f"{status} 步骤 {plan_step.step_number}: {plan_step.action} - {plan_step.reason}")

        if steps:
            lines.append("\n之前的步骤：")
            for index, step in enumerate(steps, start=1):
                lines.append(f"步骤 {index} 思考：{step.thought}")
                lines.append(f"步骤 {index} 动作：{step.action}")
                lines.append(f"步骤 {index} 输入：{json.dumps(step.action_input, ensure_ascii=False)}")
                lines.append(f"步骤 {index} 观察：{step.observation}")
        lines.append(
            "\n用 JSON 对象回应：{\"thought\": string, \"action\": string, \"action_input\": object|string}。"
        )
        return "\n".join(lines)

    def _parse_agent_response(self, raw: str) -> Dict[str, Any]:
        """
        解析智能体响应
        
        Args:
            raw (str): 智能体的原始响应字符串
            
        Returns:
            parsed (Dict[str, Any]): 解析后的JSON对象
            
        Raises:
            ValueError: 当响应不是有效的JSON时抛出异常
        """
        candidate = raw.strip()
        if not candidate:
            raise ValueError("模型返回空响应。")
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("响应不是有效的 JSON。")
            snippet = candidate[start : end + 1]
            parsed = json.loads(snippet)
        if not isinstance(parsed, dict):
            raise ValueError("智能体响应的 JSON 必须是对象。")
        return parsed

    def reset_conversation(self) -> None:
        """重置对话历史
        
        清空所有对话历史记录，为新任务做准备。
        """
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史
        
        Returns:
            conversation_history (List[Dict[str, str]]): 对话历史记录的副本
        """
        return self.conversation_history.copy()

    @staticmethod
    def _format_final_answer(action_input: Any) -> str:
        """
        格式化最终答案
        
        Args:
            action_input (Any): finish动作的输入参数
            
        Returns:
            answer (str): 格式化后的最终答案字符串
        """
        if isinstance(action_input, str):
            return action_input
        if isinstance(action_input, dict) and "answer" in action_input:
            value = action_input["answer"]
            if isinstance(value, str):
                return value
        return json.dumps(action_input, ensure_ascii=False)

    def _format_rag_results(self, results: List[Dict[str, Any]]) -> str:
        """
        格式化RAG检索结果
        
        Args:
            results (List[Dict[str, Any]]): RAG检索结果列表
            
        Returns:
            formatted (str): 格式化后的参考内容字符串
        """
        if not results:
            return "暂无参考内容"
        
        formatted = []
        for i, result in enumerate(results, 1):
            text = result.get("text", "")
            metadata = result.get("metadata", {})
            score = result.get("score", 0)
            source = metadata.get("source", "未知来源")
            
            formatted.append(f"[{i}] {text}\n    来源: {source}, 相关度: {score:.4f}")
        
        return "\n\n".join(formatted)
