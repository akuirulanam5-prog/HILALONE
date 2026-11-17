"""Filter tampilan, tingkat verbosity, dan pencarian untuk HILALONE Scientific Processing Log.

Memenuhi Bagian XXII dan XXIV:
  - Filter hanya mengatur tampilan GUI dan ekspor tampilan (Export Visible Log),
    TIDAK PERNAH menghapus catatan log permanen.
  - Mendukung filter kategori: All, Info, Success, Progress, Warning, Error, Critical, Debug.
  - Mendukung tingkat verbosity: NORMAL (default), VERBOSE, DEBUG.
  - Mendukung pencarian berdasarkan kata kunci, nama berkas, modul, Run ID, dan kode error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from hilalone.core.logging.log_event import (
    LogEvent,
    LogLevel,
    LogVerbosity,
)


class ConsoleFilterCategory(str, Enum):
    """Pilihan filter level/kategori pada toolbar Console GUI."""

    ALL = "ALL"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    PROGRESS = "PROGRESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    DEBUG = "DEBUG"


_VERBOSITY_RANK: dict[LogVerbosity, int] = {
    LogVerbosity.NORMAL: 1,
    LogVerbosity.VERBOSE: 2,
    LogVerbosity.DEBUG: 3,
}


@dataclass(frozen=True)
class LogFilterCriteria:
    """Kriteria filter dan pencarian tampilan Console Log."""

    category: ConsoleFilterCategory = ConsoleFilterCategory.ALL
    verbosity: LogVerbosity = LogVerbosity.NORMAL
    search_query: str = ""
    run_id_filter: str | None = None
    module_filter: str | None = None
    preserve_historical_verbosity: bool = False

    def _passes_verbosity(self, event: LogEvent) -> bool:
        """Memeriksa apakah event lolos tingkat verbosity.

        - WARNING, ERROR, dan CRITICAL selalu tampil pada seluruh mode (Bagian 3.D).
        - Jika preserve_historical_verbosity=True, pesan yang memang dihasilkan saat
          mode VERBOSE/DEBUG sedang aktif tetap dipertahankan (tidak dihapus retroaktif
          ketika pengguna kembali ke mode NORMAL, sesuai Bagian 3.E).
        """
        if event.level in (LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL):
            return True
        req_rank = _VERBOSITY_RANK.get(event.min_verbosity, 1)
        cur_rank = _VERBOSITY_RANK.get(self.verbosity, 1)
        if req_rank <= cur_rank:
            return True
        if self.preserve_historical_verbosity:
            emitted_rank = _VERBOSITY_RANK.get(event.emitted_under_verbosity, 1)
            if req_rank <= emitted_rank:
                return True
        return False

    def matches(self, event: LogEvent) -> bool:
        """Memeriksa apakah sebuah ``LogEvent`` lolos kriteria filter saat ini."""
        # 1. Filter Run ID jika ditentukan secara spesifik
        if self.run_id_filter:
            q_run = self.run_id_filter.strip().lower()
            if q_run and q_run not in event.run_id.lower() and q_run not in event.session_id.lower():
                return False

        # 2. Filter Modul jika ditentukan secara spesifik
        if self.module_filter:
            q_mod = self.module_filter.strip().upper()
            if q_mod and event.module.upper() != q_mod:
                return False

        # 3. Filter Kategori Level vs Verbosity
        if self.category == ConsoleFilterCategory.ALL:
            if not self._passes_verbosity(event):
                return False
        elif self.category == ConsoleFilterCategory.INFO:
            if event.level not in (LogLevel.INFO, LogLevel.SKIPPED, LogLevel.CANCELLED, LogLevel.SECTION):
                return False
            if not self._passes_verbosity(event):
                return False
        elif self.category == ConsoleFilterCategory.SUCCESS:
            if event.level != LogLevel.SUCCESS:
                return False
        elif self.category == ConsoleFilterCategory.PROGRESS:
            if event.level != LogLevel.PROGRESS:
                return False
        elif self.category == ConsoleFilterCategory.WARNING:
            if event.level != LogLevel.WARNING:
                return False
        elif self.category == ConsoleFilterCategory.ERROR:
            if event.level != LogLevel.ERROR:
                return False
        elif self.category == ConsoleFilterCategory.CRITICAL:
            if event.level != LogLevel.CRITICAL:
                return False
        elif self.category == ConsoleFilterCategory.DEBUG:
            if event.level != LogLevel.DEBUG:
                return False

        # 4. Pencarian kata kunci (kata kunci, nama berkas, modul, Run ID, error code, detail)
        query = self.search_query.strip().lower()
        if query:
            haystack_parts = [
                event.message.lower(),
                event.module.lower(),
                event.level.value.lower(),
                event.run_id.lower(),
                event.session_id.lower(),
                event.action.lower(),
                event.detail_text.lower(),
            ]
            if event.raw_block:
                haystack_parts.append(event.raw_block.lower())
            if event.details:
                for k, v in event.details.items():
                    if v is not None:
                        haystack_parts.append(f"{str(k).lower()}={str(v).lower()}")
                        haystack_parts.append(str(v).lower())
            combined = " ".join(haystack_parts)
            if query not in combined:
                return False

        return True


def filter_log_events(
    events: Iterable[LogEvent],
    criteria: LogFilterCriteria,
) -> list[LogEvent]:
    """Menyaring daftar LogEvent berdasarkan ``LogFilterCriteria`` dengan mempertahankan urutan."""
    return [ev for ev in events if criteria.matches(ev)]
