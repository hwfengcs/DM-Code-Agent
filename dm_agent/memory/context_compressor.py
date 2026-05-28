"""Mem0-inspired local memory compression.

The compressor keeps recent messages verbatim, consolidates older messages into
small scoped memories, and injects only memories relevant to the current turn.
It intentionally stays local and deterministic so default tests do not need API
keys or a hosted memory service.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..clients.base_client import BaseLLMClient

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
    scope: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
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
        self._items: Dict[str, MemoryItem] = {}

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> List[MemoryItem]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()

    def add(
        self,
        text: str,
        *,
        type: str = "episodic",
        scope: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
        messages: Sequence[Dict[str, str]],
        *,
        scope: Optional[Dict[str, str]] = None,
        turn: int = 0,
    ) -> List[str]:
        memory_ids: List[str] = []
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
        return memory_ids

    def search(
        self,
        query: str,
        *,
        scope: Optional[Dict[str, str]] = None,
        limit: int = 5,
        turn: Optional[int] = None,
    ) -> List[MemoryHit]:
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
        scored: List[tuple[MemoryItem, float]] = []
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
            scored.append((item, score))

        if not scored and not (query_tokens or query_files):
            scored = [(item, item.importance) for item in scoped_items]

        ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]
        hits: List[MemoryHit] = []
        for rank, (item, score) in enumerate(ranked, start=1):
            item.reinforce(turn=current_turn)
            hits.append(MemoryHit(item=item, score=float(score), rank=rank))
        return hits

    def render(
        self,
        query: str,
        *,
        scope: Optional[Dict[str, str]] = None,
        limit: int = 5,
        turn: Optional[int] = None,
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
            lines.append(f"{hit.rank}. [{item.type} score={hit.score:.3f}{suffix}] {item.text}")
        lines.append("</agent_memory>")
        return "\n".join(lines)

    def _extract_from_message(self, message: Dict[str, str]) -> List[Dict[str, Any]]:
        content = str(message.get("content", ""))
        role = str(message.get("role", ""))
        compact = _compact(content, limit=1200)
        if not compact:
            return []

        memories: List[Dict[str, Any]] = []
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
    def _fingerprint(*, text: str, type: str, scope: Dict[str, str]) -> str:
        payload = "|".join(
            [
                type,
                text.strip().lower(),
                json_like_scope(scope),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class ContextCompressor:
    """Compress conversation history via scoped atomic memories.

    The current run receives recent messages verbatim plus a compact
    ``<agent_memory>`` block of relevant older context. The public API remains
    compatible with the previous compressor.
    """

    def __init__(
        self,
        client: Optional[BaseLLMClient] = None,
        compress_every: int = 5,
        keep_recent: int = 3,
        *,
        memory: Optional[Mem0StyleMemory] = None,
        memory_limit: int = 5,
        scope: Optional[Dict[str, str]] = None,
    ) -> None:
        if compress_every < 1:
            raise ValueError("compress_every must be at least 1")
        if keep_recent < 1:
            raise ValueError("keep_recent must be at least 1")
        self.client = client
        self.compress_every = compress_every
        self.keep_recent = keep_recent
        self.memory = memory or Mem0StyleMemory()
        self.memory_limit = memory_limit
        self.scope = scope or {"agent_id": "dm-code-agent"}
        self.turn_count = 0
        self._compression_count = 0

    @property
    def memory_count(self) -> int:
        return len(self.memory)

    def reset(self) -> None:
        self.memory.clear()
        self.turn_count = 0
        self._compression_count = 0

    def should_compress(self, history: List[Dict[str, str]]) -> bool:
        user_messages = [msg for msg in history if msg.get("role") == "user"]
        self.turn_count = len(user_messages)
        return self.turn_count >= self.compress_every or self.memory_count > 0

    def compress(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not history:
            return []

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
            )

        query = "\n".join(message.get("content", "") for message in recent_messages[-4:])
        memory_block = self.memory.render(
            query,
            scope=self.scope,
            limit=self.memory_limit,
            turn=self._compression_count,
        )
        memory_messages = [{"role": "user", "content": memory_block}] if memory_block else []
        return system_messages + memory_messages + recent_messages

    def get_compression_stats(
        self, original: List[Dict[str, str]], compressed: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        return {
            "original_messages": len(original),
            "compressed_messages": len(compressed),
            "compression_ratio": (1 - len(compressed) / len(original) if len(original) > 0 else 0),
            "saved_messages": len(original) - len(compressed),
            "memory_items": self.memory_count,
        }


def _compact(text: str, *, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _TOKEN_PATTERN.findall(text):
        parts = re.split(r"_+", match)
        for part in parts:
            tokens.extend(_split_camel_case(part))
    return [token.lower() for token in tokens if token]


def _split_camel_case(token: str) -> List[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token).split()
    if len(parts) == 1:
        return parts
    return parts + [token]


def _scope_matches(item_scope: Dict[str, str], requested: Dict[str, str]) -> bool:
    for key, value in requested.items():
        if value and item_scope.get(key) != value:
            return False
    return True


def _merge_metadata(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
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


def json_like_scope(scope: Dict[str, str]) -> str:
    return ";".join(f"{key}={scope[key]}" for key in sorted(scope))
