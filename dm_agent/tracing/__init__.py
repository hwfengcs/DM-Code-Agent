"""Trace capture, analysis, diff, and replay helpers for DM-Code-Agent."""

from .cli import (
    analyze_events,
    analyze_trace_directory,
    diff_events,
    render_trace_directory_markdown,
    summarize_events,
)
from .session import (
    conversation_from_entries,
    find_entry,
    find_entry_index,
    latest_checkpoint_entry,
    load_session_entries,
    message_entries,
    new_entry_id,
    normalize_entries,
    rebuild_context,
)
from .writer import TraceWriter, load_trace_events

__all__ = [
    "TraceWriter",
    "analyze_events",
    "analyze_trace_directory",
    "conversation_from_entries",
    "diff_events",
    "find_entry",
    "find_entry_index",
    "latest_checkpoint_entry",
    "load_session_entries",
    "load_trace_events",
    "message_entries",
    "new_entry_id",
    "normalize_entries",
    "rebuild_context",
    "render_trace_directory_markdown",
    "summarize_events",
]
