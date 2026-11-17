"""Handler logging, rate-limiter progres, dan jembatan sinyal Qt thread-safe untuk HILALONE.

Memenuhi Bagian III, XIII, XXVIII, dan XXIX:
  - Worker thread tidak pernah memodifikasi widget GUI secara langsung.
  - Semua pembaruan Console GUI dikirim melalui sinyal Qt (``Qt.ConnectionType.AutoConnection``
    yang otomatis menjadi ``QueuedConnection`` lintas thread).
  - Rate-limiter progres mencegah ribuan sinyal progres membanjiri GUI atau disk.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from hilalone.core.logging.log_event import LogEvent
    from hilalone.core.logging.logger import HilaloneLogger


class QtLogSignalBridge(QObject):
    """Jembatan sinyal Qt agar pengiriman LogEvent dari worker thread ke GUI 100% thread-safe."""

    event_emitted = Signal(object)       # LogEvent
    view_clear_requested = Signal()
    verbosity_changed = Signal(str)      # LogVerbosity.value


class ProgressRateLimiter:
    """Pembatas laju (rate-limiter) untuk event PROGRESS agar tidak membanjiri Console atau disk.

    Secara default mencatat milestone bermakna (mis. 10%, 25%, 50%, 75%, 100% atau setiap
    kenaikan >= ``min_step_percent``) dan menghindari duplikasi persentase yang sama.
    """

    DEFAULT_MILESTONES: tuple[int, ...] = (10, 25, 50, 75, 100)

    def __init__(self, *, min_step_percent: int = 10, min_interval_sec: float = 0.0) -> None:
        self._lock = threading.Lock()
        self._min_step = max(1, int(min_step_percent))
        self._min_interval_sec = max(0.0, float(min_interval_sec))
        self._last_pct: dict[str, int] = {}
        self._last_time: dict[str, float] = {}
        self._emitted_milestones: dict[str, set[int]] = {}

    def reset(self, key: str | None = None) -> None:
        """Mereset state rate-limiter untuk satu operasi atau seluruh operasi."""
        with self._lock:
            if key is None:
                self._last_pct.clear()
                self._last_time.clear()
                self._emitted_milestones.clear()
            else:
                self._last_pct.pop(key, None)
                self._last_time.pop(key, None)
                self._emitted_milestones.pop(key, None)

    def should_emit(self, key: str, current: int, total: int) -> tuple[bool, int]:
        """Menentukan apakah progres ``(current, total)`` layak dicatat ke Console Log.

        Returns:
            Tuple ``(allow_emit, computed_percentage)``.
        """
        tot = max(1, int(total))
        cur = max(0, min(int(current), tot))
        pct = int(round(100.0 * cur / float(tot)))

        with self._lock:
            prev_pct = self._last_pct.get(key, -1)
            if pct == prev_pct:
                return False, pct

            emitted_set = self._emitted_milestones.setdefault(key, set())
            now = time.monotonic()
            prev_t = self._last_time.get(key, 0.0)

            # Selalu izinkan 100% jika belum pernah dicatat
            if pct >= 100 and 100 not in emitted_set:
                self._last_pct[key] = 100
                self._last_time[key] = now
                emitted_set.add(100)
                return True, 100

            # Periksa apakah mencapai salah satu milestone standar (10, 25, 50, 75, 100)
            for m in self.DEFAULT_MILESTONES:
                if pct >= m and m not in emitted_set and prev_pct < m:
                    # Tandai semua milestone di bawah pct yang terlewati agar tidak ganda
                    for m_sub in self.DEFAULT_MILESTONES:
                        if m_sub <= pct:
                            emitted_set.add(m_sub)
                    self._last_pct[key] = pct
                    self._last_time[key] = now
                    return True, m if abs(pct - m) <= 3 else pct

            # Atau jika kenaikan >= min_step_percent dan melewati min_interval_sec
            if prev_pct >= 0 and (pct - prev_pct) >= self._min_step:
                if (now - prev_t) >= self._min_interval_sec:
                    self._last_pct[key] = pct
                    self._last_time[key] = now
                    return True, pct

            return False, pct


class PythonLoggingBridgeHandler(logging.Handler):
    """Handler standar Python ``logging`` yang meneruskan log ke ``HilaloneLogger`` tanpa loop rekursif."""

    def __init__(self, hilalone_logger: HilaloneLogger) -> None:
        super().__init__()
        self._hilalone_logger = hilalone_logger
        self._in_emit = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._in_emit, "active", False):
            return
        if getattr(record, "from_hilalone_logger", False):
            return
        try:
            self._in_emit.active = True
            msg = self.format(record) if self.formatter else record.getMessage()
            lvl = record.levelname.upper()
            mod = record.name.split(".")[-1].upper() if record.name else "SYSTEM"
            self._hilalone_logger.log(
                lvl,
                mod,
                msg,
                write_to_python_logging=False,
            )
        except Exception:
            pass
        finally:
            self._in_emit.active = False
