"""Trace capture, analysis, diff, and replay helpers for DM-Code-Agent."""

from .analysis import analyze_events, analyze_trace_directory
from .fork import fork_session
from .render import render_trace_directory_markdown
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
from .summary import diff_events, summarize_events
from .writer import SessionWriter, TraceWriter, load_trace_events

__all__ = [
    "SessionWriter",
    "TraceWriter",
    "analyze_events",
    "analyze_trace_directory",
    "conversation_from_entries",
    "diff_events",
    "find_entry",
    "find_entry_index",
    "fork_session",
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
