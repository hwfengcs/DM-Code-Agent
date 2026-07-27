"""Mem0-inspired local memory compression.

The compressor keeps recent messages verbatim, consolidates older messages into
small scoped memories, and injects only memories relevant to the current turn.
It intentionally stays local and deterministic so default tests do not need API
keys or a hosted memory service.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from dm_agent.clients.base_client import BaseLLMClient

from .context_budget import estimate_messages_tokens

MEMORY_TYPES = {"episodic", "semantic", "procedural"}
_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[\u4e00-\u9fff]+")
_FILE_PATTERN = re.compile(
    r"(?<![\w./\\-])([\w./\\-]+\.(?:py|md|toml|json|yaml|yml|txt|ini|cfg|js|ts|tsx|jsx|css|html))"
)
_ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "failure",
    "returncode: 1",
    "AssertionError",
    "错误",
    "失败",
    "异常",
)
_SUCCESS_MARKERS = ("success", "succeeded", "completed", "done", "完成", "成功")


@dataclass
class MemoryItem:
    """One compact memory item extracted from prior messages."""

    id: str
    text: str
    type: str = "episodic"
    scope: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    created_at_turn: int = 0
    last_accessed_turn: int = 0
    access_count: int = 0

    def reinforce(self, *, turn: int, importance_delta: float = 0.05) -> None:
        self.importance = min(1.0, self.importance + importance_delta)
        self.last_accessed_turn = max(self.last_accessed_turn, turn)
        self.access_count += 1


@dataclass(frozen=True)
class MemoryHit:
    """A scored memory search result."""

    item: MemoryItem
    score: float
    rank: int


class Mem0StyleMemory:
    """A small local add/search memory store following Mem0's operating pattern.

    Instead of summarizing all old messages into one fragile paragraph, the store
    turns old context into atomic memories, deduplicates them, reinforces repeated
    facts, and searches by query plus optional scope filters.
    """

    def __init__(self, *, max_items: int = 80) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        self.max_items = max_items
        self.superseded_count = 0
        self._items: dict[str, MemoryItem] = {}

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> list[MemoryItem]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()

    def add(
        self,
        text: str,
        *,
        type: str = "episodic",
        scope: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        turn: int = 0,
    ) -> str:
        text = _compact(text, limit=700)
        if not text:
            return ""
        if type not in MEMORY_TYPES:
            type = "episodic"
        scope = {str(key): str(value) for key, value in (scope or {}).items() if value}
        metadata = dict(metadata or {})
        memory_id = self._fingerprint(text=text, type=type, scope=scope)

        existing = self._items.get(memory_id)
        if existing:
            existing.metadata = _merge_metadata(existing.metadata, metadata)
            existing.reinforce(turn=turn)
            return memory_id

        self._items[memory_id] = MemoryItem(
            id=memory_id,
            text=text,
            type=type,
            scope=scope,
            metadata=metadata,
            importance=max(0.0, min(1.0, importance)),
            created_at_turn=turn,
            last_accessed_turn=turn,
        )
        self._enforce_limit()
        return memory_id

    def add_messages(
        self,
        messages: Sequence[dict[str, str]],
        *,
        scope: dict[str, str] | None = None,
        turn: int = 0,
        invalidate_on_success: bool = False,
    ) -> list[str]:
        memory_ids: list[str] = []
        for message in messages:
            for memory in self._extract_from_message(message):
                memory_id = self.add(
                    memory["text"],
                    type=memory["type"],
                    scope=scope,
                    metadata=memory.get("metadata", {}),
                    importance=float(memory.get("importance", 0.5)),
                    turn=turn,
                )
                if memory_id:
                    memory_ids.append(memory_id)
            if invalidate_on_success:
                content = str(message.get("content", ""))
                if _message_reports_success(content):
                    files = set(_FILE_PATTERN.findall(content))
                    self.supersede_failures(files, turn=turn)
        return memory_ids

    def supersede_failures(self, files: set[str], *, turn: int) -> int:
        """Mark failure memories about ``files`` as superseded by a later success.

        The text (and therefore the dedup fingerprint) stays untouched; the item
        only loses importance and gets a staleness annotation at render time.
        """
        if not files:
            return 0
        superseded = 0
        for item in self._items.values():
            if not item.text.startswith("Observed failure"):
                continue
            if item.metadata.get("superseded_at_turn") is not None:
                continue
            item_files = set(item.metadata.get("files") or [])
            if item_files & files:
                item.metadata["superseded_at_turn"] = turn
                item.importance = max(0.0, item.importance * 0.3)
                superseded += 1
        self.superseded_count += superseded
        return superseded

    def search(
        self,
        query: str,
        *,
        scope: dict[str, str] | None = None,
        limit: int = 5,
        turn: int | None = None,
    ) -> list[MemoryHit]:
        if limit < 1:
            return []
        query_tokens = set(_tokenize(query))
        query_files = set(_FILE_PATTERN.findall(query))
        scoped_items = [
            item for item in self._items.values() if _scope_matches(item.scope, scope or {})
        ]
        current_turn = (
            turn
            if turn is not None
            else max((item.last_accessed_turn for item in scoped_items), default=0)
        )
        scored: list[tuple[MemoryItem, float]] = []
        for item in scoped_items:
            item_tokens = set(_tokenize(_memory_search_text(item)))
            lexical = len(query_tokens & item_tokens) / max(len(query_tokens), 1)
            file_bonus = _file_overlap_bonus(query_files, item)
            has_query_signal = bool(query_tokens or query_files)
            relevance = lexical + file_bonus
            if has_query_signal and relevance <= 0:
                continue
            recency = 1.0 / (1.0 + max(current_turn - item.last_accessed_turn, 0))
            score = (
                relevance
                + item.importance * 0.15
                + min(item.access_count, 5) * 0.02
                + recency * 0.05
            )
            if item.metadata.get("superseded_at_turn") is not None:
                score *= 0.25
            scored.append((item, score))

        if not scored and not (query_tokens or query_files):
            scored = [(item, item.importance) for item in scoped_items]

        ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]
        hits: list[MemoryHit] = []
        for rank, (item, score) in enumerate(ranked, start=1):
            item.reinforce(turn=current_turn)
            hits.append(MemoryHit(item=item, score=float(score), rank=rank))
        return hits

    def render(
        self,
        query: str,
        *,
        scope: dict[str, str] | None = None,
        limit: int = 5,
        turn: int | None = None,
    ) -> str:
        hits = self.search(query, scope=scope, limit=limit, turn=turn)
        if not hits:
            return ""

        lines = [
            "<agent_memory>",
            "Relevant memories from previous context. Treat them as hints; verify before editing.",
        ]
        for hit in hits:
            item = hit.item
            files = item.metadata.get("files") or []
            suffix = f" files={','.join(files[:3])}" if files else ""
            stale_note = (
                " (possibly stale: later success touched these files)"
                if item.metadata.get("superseded_at_turn") is not None
                else ""
            )
            lines.append(
                f"{hit.rank}. [{item.type} score={hit.score:.3f}{suffix}] {item.text}{stale_note}"
            )
        lines.append("</agent_memory>")
        return "\n".join(lines)

    def _extract_from_message(self, message: dict[str, str]) -> list[dict[str, Any]]:
        content = str(message.get("content", ""))
        role = str(message.get("role", ""))
        compact = _compact(content, limit=1200)
        if not compact:
            return []

        memories: list[dict[str, Any]] = []
        files = sorted(set(_FILE_PATTERN.findall(content)))
        if files:
            memories.append(
                {
                    "type": "semantic",
                    "text": "Files mentioned or inspected: " + ", ".join(files[:8]),
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.45,
                }
            )

        task_line = _first_matching_line(content, ("任务：", "Task:", "task:"))
        if task_line:
            memories.append(
                {
                    "type": "episodic",
                    "text": "Current task context: " + _compact(task_line, limit=260),
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.65,
                }
            )

        tool_match = re.search(r"(?:执行工具|Tool)\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        if tool_match:
            memories.append(
                {
                    "type": "episodic",
                    "text": f"Tool used: {tool_match.group(1)}.",
                    "metadata": {"tool": tool_match.group(1), "files": files, "source_role": role},
                    "importance": 0.4,
                }
            )

        error_line = _first_matching_line(content, _ERROR_MARKERS)
        if error_line:
            memories.append(
                {
                    "type": "episodic",
                    "text": "Observed failure: " + _compact(error_line, limit=360),
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.8,
                }
            )

        success_line = _first_matching_line(content, _SUCCESS_MARKERS)
        if success_line:
            memories.append(
                {
                    "type": "episodic",
                    "text": "Completed operation: " + _compact(success_line, limit=320),
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.55,
                }
            )

        if "pytest" in content or "run_tests" in content:
            memories.append(
                {
                    "type": "procedural",
                    "text": "When code changes are made, run the relevant tests and keep failing output available.",
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.7,
                }
            )

        if not memories and len(compact) > 240:
            memories.append(
                {
                    "type": "episodic",
                    "text": "Prior context: " + _compact(compact, limit=360),
                    "metadata": {"files": files, "source_role": role},
                    "importance": 0.35,
                }
            )
        return memories

    def _enforce_limit(self) -> None:
        if len(self._items) <= self.max_items:
            return
        ranked = sorted(
            self._items.values(),
            key=lambda item: (item.importance, item.access_count, item.last_accessed_turn),
            reverse=True,
        )
        self._items = {item.id: item for item in ranked[: self.max_items]}

    @staticmethod
    def _fingerprint(*, text: str, type: str, scope: dict[str, str]) -> str:
        payload = "|".join(
            [
                type,
                text.strip().lower(),
                json_like_scope(scope),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """序列化记忆存储（用于 run 级 checkpoint）。"""
        return {
            "max_items": self.max_items,
            "superseded_count": self.superseded_count,
            "items": [
                {
                    "id": item.id,
                    "text": item.text,
                    "type": item.type,
                    "scope": dict(item.scope),
                    "metadata": dict(item.metadata),
                    "importance": item.importance,
                    "created_at_turn": item.created_at_turn,
                    "last_accessed_turn": item.last_accessed_turn,
                    "access_count": item.access_count,
                }
                for item in self._items.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mem0StyleMemory:
        memory = cls(max_items=int(data.get("max_items", 80)))
        memory.superseded_count = int(data.get("superseded_count", 0))
        for raw in data.get("items", []):
            item = MemoryItem(
                id=str(raw.get("id", "")),
                text=str(raw.get("text", "")),
                type=str(raw.get("type", "episodic")),
                scope={str(k): str(v) for k, v in (raw.get("scope") or {}).items()},
                metadata=dict(raw.get("metadata") or {}),
                importance=float(raw.get("importance", 0.5)),
                created_at_turn=int(raw.get("created_at_turn", 0)),
                last_accessed_turn=int(raw.get("last_accessed_turn", 0)),
                access_count=int(raw.get("access_count", 0)),
            )
            if item.id:
                memory._items[item.id] = item
        return memory


class ContextCompressor:
    """Compress conversation history via scoped atomic memories.

    The current run receives recent messages verbatim plus a compact
    ``<agent_memory>`` block of relevant older context. The public API remains
    compatible with the previous compressor.
    """

    def __init__(
        self,
        client: BaseLLMClient | None = None,
        compress_every: int = 20,
        keep_recent: int = 8,
        *,
        memory: Mem0StyleMemory | None = None,
        memory_limit: int = 5,
        scope: dict[str, str] | None = None,
        token_budget: int = 24000,
        enable_hygiene: bool = False,
        use_llm_summary: bool = False,
    ) -> None:
        if compress_every < 1:
            raise ValueError("compress_every must be at least 1")
        if keep_recent < 1:
            raise ValueError("keep_recent must be at least 1")
        self.client = client
        self.compress_every = compress_every
        self.keep_recent = keep_recent
        # 显式判 None：空记忆的 __len__ 为 0（falsy），`memory or ...` 会把
        # 调用方注入的空实例悄悄替换掉，破坏注入语义。
        self.memory = memory if memory is not None else Mem0StyleMemory()
        self.memory_limit = memory_limit
        self.scope = scope or {"agent_id": "dm-code-agent"}
        # Estimated-token ceiling for the pending history; 0 disables the
        # size-based trigger and falls back to pure message-count cadence.
        self.token_budget = max(0, int(token_budget))
        # Hygiene（默认关）：成功消息使相关失败记忆降权 + 召回 query 锚定任务原文。
        self.enable_hygiene = enable_hygiene
        # LLM 摘要（默认关）：折叠旧消息时额外生成一条语义摘要记忆，出错时静默回退。
        self.use_llm_summary = use_llm_summary
        self.llm_summary_count = 0
        self.llm_summary_error_count = 0
        self.last_trigger: str = ""
        self.last_estimated_tokens: int = 0
        self.turn_count = 0
        self._compression_count = 0
        self._last_compressed_turn_count = 0

    @property
    def memory_count(self) -> int:
        return len(self.memory)

    def reset(self) -> None:
        self.memory.clear()
        self.turn_count = 0
        self._compression_count = 0
        self._last_compressed_turn_count = 0

    def should_compress(self, history: list[dict[str, str]]) -> bool:
        user_messages = [msg for msg in history if msg.get("role") == "user"]
        self.turn_count = len(user_messages)
        non_system_messages = [msg for msg in history if msg.get("role") != "system"]
        has_old_messages = len(non_system_messages) > self.keep_recent * 2
        new_turns_since_last = self.turn_count - self._last_compressed_turn_count
        cadence_reached = new_turns_since_last >= self.compress_every
        self.last_estimated_tokens = estimate_messages_tokens(history)
        over_budget = 0 < self.token_budget < self.last_estimated_tokens
        self.last_trigger = ""
        if has_old_messages and (cadence_reached or over_budget):
            self.last_trigger = "cadence" if cadence_reached else "token_budget"
            return True
        return False

    def compress(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        if not history:
            return []

        self.turn_count = len([msg for msg in history if msg.get("role") == "user"])
        self._last_compressed_turn_count = self.turn_count
        self._compression_count += 1
        system_messages = [msg for msg in history if msg.get("role") == "system"]
        non_system = [msg for msg in history if msg.get("role") != "system"]
        recent_message_count = self.keep_recent * 2
        recent_messages = (
            non_system[-recent_message_count:]
            if len(non_system) > recent_message_count
            else list(non_system)
        )
        older_messages = (
            non_system[:-recent_message_count] if len(non_system) > recent_message_count else []
        )

        if older_messages:
            self.memory.add_messages(
                older_messages,
                scope=self.scope,
                turn=self._compression_count,
                invalidate_on_success=self.enable_hygiene,
            )
            if self.use_llm_summary and self.client is not None:
                self._add_llm_summary(older_messages)

        query = "\n".join(message.get("content", "") for message in recent_messages[-4:])
        if self.enable_hygiene:
            task_anchor = _first_user_content(history)
            if task_anchor:
                query = task_anchor[:400] + "\n" + query
        memory_block = self.memory.render(
            query,
            scope=self.scope,
            limit=self.memory_limit,
            turn=self._compression_count,
        )
        memory_messages = [{"role": "user", "content": memory_block}] if memory_block else []
        return system_messages + memory_messages + recent_messages

    def _add_llm_summary(self, older_messages: list[dict[str, str]]) -> None:
        """Fold older messages into one LLM-written semantic memory (best effort)."""
        digest_lines = [
            f"[{message.get('role', '')}] {_compact(str(message.get('content', '')), limit=400)}"
            for message in older_messages
        ]
        digest = "\n".join(digest_lines)[:6000]
        prompt = [
            {
                "role": "system",
                "content": (
                    "你负责压缩智能体的旧对话上下文。用不超过500字总结以下旧消息中的"
                    "关键事实、涉及文件、已做决定和未解决问题。只输出摘要正文。"
                ),
            },
            {"role": "user", "content": digest},
        ]
        try:
            summary = str(self.client.respond(prompt, temperature=0.0)).strip()
        except Exception:
            self.llm_summary_error_count += 1
            return
        if not summary:
            return
        self.memory.add(
            "Summary of earlier context: " + summary[:500],
            type="semantic",
            scope=self.scope,
            metadata={"source": "llm_summary"},
            importance=0.75,
            turn=self._compression_count,
        )
        self.llm_summary_count += 1

    def get_compression_stats(
        self, original: list[dict[str, str]], compressed: list[dict[str, str]]
    ) -> dict[str, Any]:
        return {
            "original_messages": len(original),
            "compressed_messages": len(compressed),
            "compression_ratio": (1 - len(compressed) / len(original) if len(original) > 0 else 0),
            "saved_messages": len(original) - len(compressed),
            "memory_items": self.memory_count,
        }

    def export_state(self) -> dict[str, Any]:
        """导出压缩器可恢复状态（记忆 + 压缩节奏），用于 checkpoint。"""
        return {
            "memory": self.memory.to_dict(),
            "turn_count": self.turn_count,
            "compression_count": self._compression_count,
            "last_compressed_turn_count": self._last_compressed_turn_count,
            "llm_summary_count": self.llm_summary_count,
            "llm_summary_error_count": self.llm_summary_error_count,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.memory = Mem0StyleMemory.from_dict(state.get("memory") or {})
        self.turn_count = int(state.get("turn_count", 0))
        self._compression_count = int(state.get("compression_count", 0))
        self._last_compressed_turn_count = int(state.get("last_compressed_turn_count", 0))
        self.llm_summary_count = int(state.get("llm_summary_count", 0))
        self.llm_summary_error_count = int(state.get("llm_summary_error_count", 0))


def _compact(text: str, *, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.findall(text):
        parts = re.split(r"_+", match)
        for part in parts:
            tokens.extend(_split_camel_case(part))
    return [token.lower() for token in tokens if token]


def _split_camel_case(token: str) -> list[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token).split()
    if len(parts) == 1:
        return parts
    return [*parts, token]


def _scope_matches(item_scope: dict[str, str], requested: dict[str, str]) -> bool:
    # 仅比较 requested 中取值非空的维度；空值表示「不限定该维度」。
    return all(item_scope.get(key) == value for key, value in requested.items() if value)


def _merge_metadata(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key == "files":
            merged[key] = sorted(set(merged.get(key, [])) | set(value or []))
        elif key not in merged or not merged[key]:
            merged[key] = value
    return merged


def _memory_search_text(item: MemoryItem) -> str:
    fields = [item.text, item.type]
    files = item.metadata.get("files") or []
    fields.extend(str(file) for file in files)
    if "tool" in item.metadata:
        fields.append(str(item.metadata["tool"]))
    return "\n".join(fields)


def _file_overlap_bonus(query_files: set[str], item: MemoryItem) -> float:
    item_files = set(item.metadata.get("files") or [])
    if not query_files or not item_files:
        return 0.0
    return 0.3 if query_files & item_files else 0.0


def _first_matching_line(text: str, markers: Iterable[str]) -> str:
    lowered_markers = [marker.lower() for marker in markers]
    for line in str(text or "").splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in lowered_markers):
            return line.strip()
    return ""


def _message_reports_success(content: str) -> bool:
    lowered = str(content or "").lower()
    return "returncode: 0" in lowered or any(
        marker in lowered for marker in (m.lower() for m in _SUCCESS_MARKERS)
    )


def _first_user_content(history: list[dict[str, str]]) -> str:
    for message in history:
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def json_like_scope(scope: dict[str, str]) -> str:
    return ";".join(f"{key}={scope[key]}" for key in sorted(scope))
