"""Pemformat pesan teks, HTML berwarna, dan serialisasi JSONL untuk HILALONE Scientific Processing Log."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from hilalone.core.logging.log_event import (
    LogEvent,
    LogEventType,
    LogLevel,
    get_log_color,
    is_semibold_level,
)

# Pola sanitasi untuk mencegah bocornya token/password/credential ke dalam log
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|credential|authorization)",
    re.IGNORECASE,
)


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Menyaring key sensitif (token/password/credential) dan nilai kosong dari detail log."""
    if not details:
        return {}
    cleaned: dict[str, Any] = {}
    for k, v in details.items():
        if v is None:
            continue
        key_str = str(k)
        if _SENSITIVE_KEY_RE.search(key_str):
            cleaned[key_str] = "[REDACTED]"
            continue
        if isinstance(v, dict):
            cleaned[key_str] = sanitize_details(v)
        elif isinstance(v, (list, tuple, set)):
            cleaned[key_str] = [
                sanitize_details(x) if isinstance(x, dict) else x
                for x in v
            ]
        elif isinstance(v, (str, int, float, bool)):
            cleaned[key_str] = v
        else:
            cleaned[key_str] = str(v)
    return cleaned


def format_console_line(event: LogEvent) -> str:
    """Memformat satu LogEvent untuk tampilan Console GUI (timestamp milidetik ringkas)."""
    return event.format_line(use_iso_timestamp=False)


def format_persistent_line(event: LogEvent) -> str:
    """Memformat satu LogEvent untuk berkas ``.log`` permanen (timestamp ISO 8601 + timezone)."""
    if event.raw_block is not None:
        return event.raw_block
    if event.level == LogLevel.SECTION or event.event_type == LogEventType.SECTION:
        title = event.message.strip().strip("=").strip()
        return f"[{event.iso_timestamp}] [SECTION] [{event.module}] === {title.upper()} ==="
    return event.format_line(use_iso_timestamp=True)


def format_jsonl_line(event: LogEvent) -> str:
    """Mengubah LogEvent menjadi satu baris JSON valid (JSON Lines) tanpa karakter baris baru di tengah."""
    payload = event.to_jsonl_dict()
    payload["details"] = sanitize_details(payload.get("details"))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def format_html_line(event: LogEvent, *, night_vision: bool = False) -> str:
    """Memformat LogEvent menjadi blok HTML berwarna semantik untuk Console GUI."""
    color = get_log_color(event.level, night_vision=night_vision)
    weight = "600" if is_semibold_level(event.level) else "400"
    line_text = format_console_line(event)
    escaped = html.escape(line_text)
    return (
        f'<span style="color:{color}; font-weight:{weight}; '
        f'white-space:pre-wrap;">{escaped}</span>'
    )
