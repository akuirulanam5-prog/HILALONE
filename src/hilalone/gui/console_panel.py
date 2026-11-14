"""Panel Console / Processing Log terstruktur ala Siril untuk HILALONE.

Menyimpan dan menampilkan seluruh aktivitas pemrosesan secara terstruktur:
    [TIMESTAMP] | [LEVEL] | [MODULE] | [ACTION] | [DETAIL]

Mendukung ekspor ke format TXT, CSV, dan JSON serta pembersihan tampilan log
tanpa mengganggu proses backend yang sedang berjalan.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon


class LogLevel(str, Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: LogLevel
    module: str
    action: str
    detail: str

    def format_line(self) -> str:
        return f"{self.timestamp} | {self.level.value:<7} | {self.module:<10} | {self.action} | {self.detail}"


class LogManager(QObject):
    """Manajer log terpusat yang aman dari multiple thread."""

    entry_logged = Signal(object)  # LogEntry
    log_cleared = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[LogEntry] = []

    @property
    def entries(self) -> tuple[LogEntry, ...]:
        return tuple(self._entries)

    def log(
        self,
        level: LogLevel | str,
        module: str,
        action: str,
        detail: str,
    ) -> LogEntry:
        """Mencatat aktivitas baru dengan timestamp presisi."""
        now_str = datetime.now().strftime("%H:%M:%S")
        if isinstance(level, str):
            try:
                lvl = LogLevel(level.upper())
            except ValueError:
                lvl = LogLevel.INFO
        else:
            lvl = level

        entry = LogEntry(
            timestamp=now_str,
            level=lvl,
            module=module.strip(),
            action=action.strip(),
            detail=detail.strip(),
        )
        self._entries.append(entry)
        self.entry_logged.emit(entry)
        return entry

    def info(self, module: str, action: str, detail: str) -> LogEntry:
        return self.log(LogLevel.INFO, module, action, detail)

    def success(self, module: str, action: str, detail: str) -> LogEntry:
        return self.log(LogLevel.SUCCESS, module, action, detail)

    def warning(self, module: str, action: str, detail: str) -> LogEntry:
        return self.log(LogLevel.WARNING, module, action, detail)

    def error(self, module: str, action: str, detail: str) -> LogEntry:
        return self.log(LogLevel.ERROR, module, action, detail)

    def clear(self) -> None:
        self._entries.clear()
        self.log_cleared.emit()

    def export_to_txt(self, path: Path | str) -> Path:
        p = Path(path)
        lines = [e.format_line() for e in self._entries]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def export_to_csv(self, path: Path | str) -> Path:
        p = Path(path)
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Level", "Module", "Action", "Detail"])
            for e in self._entries:
                writer.writerow([e.timestamp, e.level.value, e.module, e.action, e.detail])
        return p

    def export_to_json(self, path: Path | str) -> Path:
        p = Path(path)
        data = [
            {
                "timestamp": e.timestamp,
                "level": e.level.value,
                "module": e.module,
                "action": e.action,
                "detail": e.detail,
            }
            for e in self._entries
        ]
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p


class ConsoleLogPanel(QFrame):
    """Widget panel console/log di bagian bawah aplikasi HILALONE."""

    def __init__(self, log_manager: LogManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consoleCard")
        self.log_manager = log_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Header bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_lbl = QLabel("CONSOLE / PROCESSING LOG")
        title_lbl.setObjectName("sectionHeader")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch(1)

        self.clear_btn = QPushButton("Clear Log")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.setIcon(create_vector_icon("trash-2", size=14))
        self.clear_btn.setIconSize(QSize(14, 14))
        self.clear_btn.setMinimumHeight(28)
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        header_layout.addWidget(self.clear_btn)

        self.export_btn = QPushButton("Export Log...")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.setIcon(create_vector_icon("download", size=14))
        self.export_btn.setIconSize(QSize(14, 14))
        self.export_btn.setMinimumHeight(28)
        self.export_btn.clicked.connect(self._on_export_clicked)
        header_layout.addWidget(self.export_btn)

        self.toggle_hide_btn = QPushButton("Tutup")
        self.toggle_hide_btn.setObjectName("secondaryButton")
        self.toggle_hide_btn.setIcon(create_vector_icon("chevron-down", size=14))
        self.toggle_hide_btn.setIconSize(QSize(14, 14))
        self.toggle_hide_btn.setMinimumHeight(28)
        self.toggle_hide_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.toggle_hide_btn)

        layout.addLayout(header_layout)

        # Log Text Box
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(3000)
        self.text_edit.setMinimumHeight(110)
        layout.addWidget(self.text_edit)

        # Connect signals
        self.log_manager.entry_logged.connect(self._on_entry_logged)
        self.log_manager.log_cleared.connect(self._on_log_cleared)

        # Populate initial entries jika ada
        for e in self.log_manager.entries:
            self._append_entry_text(e)

    def set_night_vision(self, active: bool) -> None:
        """Menyesuaikan warna ikon tombol Console Log Panel dengan status Night Vision."""
        self.clear_btn.setIcon(create_themed_vector_icon("trash-2", night_vision=active, size=14))
        self.export_btn.setIcon(create_themed_vector_icon("download", night_vision=active, size=14))
        self.toggle_hide_btn.setIcon(create_themed_vector_icon("chevron-down", night_vision=active, size=14))

    def _on_entry_logged(self, entry: LogEntry) -> None:
        self._append_entry_text(entry)

    def _append_entry_text(self, entry: LogEntry) -> None:
        self.text_edit.appendPlainText(entry.format_line())

    def _on_log_cleared(self) -> None:
        self.text_edit.clear()

    def _on_clear_clicked(self) -> None:
        self.log_manager.clear()

    def _on_export_clicked(self) -> None:
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Ekspor Console / Processing Log",
            "HILALONE_processing_log.txt",
            "Text File (*.txt);;CSV File (*.csv);;JSON File (*.json);;Semua Berkas (*.*)",
        )
        if not file_path:
            return

        p = Path(file_path)
        ext = p.suffix.lower()
        try:
            if ext == ".csv" or "csv" in selected_filter.lower():
                out_p = self.log_manager.export_to_csv(p)
            elif ext == ".json" or "json" in selected_filter.lower():
                out_p = self.log_manager.export_to_json(p)
            else:
                out_p = self.log_manager.export_to_txt(p)

            QMessageBox.information(
                self,
                "Ekspor Log Berhasil",
                f"Console log berhasil disimpan ke:\n{out_p}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Gagal Ekspor Log",
                f"Terjadi kesalahan saat menyimpan log:\n{exc}",
            )
