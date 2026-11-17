"""Pengelolaan preferensi dan penjadwalan Automatic Update Notification HILALONE.

Menyimpan status aktif/nonaktif pemeriksaan otomatis, waktu cek terakhir,
pengingat tunda (Later 24 jam), dan versi terakhir yang diberitahukan memakai
``QSettings`` berformat INI pada direktori konfigurasi pengguna.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QSettings

from hilalone import __version__
from hilalone.gui.resources import get_user_config_path
from hilalone.updates.github_updater import is_frozen_app
from hilalone.updates.version import parse_version

AUTO_UPDATE_STARTUP_DELAY_MS = 10_000
AUTO_UPDATE_INTERVAL = timedelta(hours=24)
REMINDER_DELAY_INTERVAL = timedelta(hours=24)

KEY_AUTO_UPDATE_CHECK_ENABLED = "updates/auto_update_check_enabled"
KEY_LAST_UPDATE_CHECK = "updates/last_update_check"
KEY_NEXT_UPDATE_REMINDER = "updates/next_update_reminder"
KEY_LAST_NOTIFIED_VERSION = "updates/last_notified_version"


def utc_now() -> datetime:
    """Mengembalikan waktu UTC sadar zona waktu saat ini."""
    return datetime.now(timezone.utc)


def format_iso_utc(dt: datetime) -> str:
    """Memformat datetime menjadi string ISO-8601 UTC."""
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


def parse_iso_utc(raw: str | None) -> datetime | None:
    """Mem-parsing timestamp ISO-8601 ke UTC datetime, atau None bila kosong/tidak valid."""
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class UpdatePreferences:
    """Preferensi dan state jadwal pemeriksaan pembaruan otomatis."""

    auto_update_check_enabled: bool = True
    last_update_check: str = ""
    next_update_reminder: str = ""
    last_notified_version: str = ""


def load_update_preferences(config_path: Path | None = None) -> UpdatePreferences:
    """Membaca preferensi automatic update dari QSettings (default aktif)."""
    cfg = Path(config_path) if config_path is not None else get_user_config_path()
    if not cfg.exists():
        return UpdatePreferences()

    settings = QSettings(str(cfg), QSettings.Format.IniFormat)
    enabled = _to_bool(settings.value(KEY_AUTO_UPDATE_CHECK_ENABLED, True), default=True)
    last_check = str(settings.value(KEY_LAST_UPDATE_CHECK, "") or "").strip()
    next_reminder = str(settings.value(KEY_NEXT_UPDATE_REMINDER, "") or "").strip()
    last_notified = str(settings.value(KEY_LAST_NOTIFIED_VERSION, "") or "").strip()

    return UpdatePreferences(
        auto_update_check_enabled=enabled,
        last_update_check=last_check,
        next_update_reminder=next_reminder,
        last_notified_version=last_notified,
    )


def save_update_preferences(
    prefs: UpdatePreferences,
    config_path: Path | None = None,
) -> None:
    """Menyimpan preferensi automatic update ke QSettings tanpa menghapus kunci lain."""
    cfg = Path(config_path) if config_path is not None else get_user_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    settings = QSettings(str(cfg), QSettings.Format.IniFormat)
    settings.setValue(KEY_AUTO_UPDATE_CHECK_ENABLED, bool(prefs.auto_update_check_enabled))
    settings.setValue(KEY_LAST_UPDATE_CHECK, str(prefs.last_update_check or ""))
    settings.setValue(KEY_NEXT_UPDATE_REMINDER, str(prefs.next_update_reminder or ""))
    settings.setValue(KEY_LAST_NOTIFIED_VERSION, str(prefs.last_notified_version or ""))
    settings.sync()


def should_run_automatic_check(
    prefs: UpdatePreferences,
    *,
    now: datetime | None = None,
    is_frozen: bool | None = None,
    check_interval: timedelta = AUTO_UPDATE_INTERVAL,
) -> bool:
    """Menentukan apakah pemeriksaan pembaruan otomatis boleh dijalankan.

    Aturan:
    - Hanya berjalan pada aplikasi hasil instalasi/frozen (``is_frozen == True``).
    - Tidak berjalan bila ``auto_update_check_enabled`` bernilai False.
    - Maksimal 1 kali setiap 24 jam sejak ``last_update_check``.
    """
    frozen = is_frozen_app() if is_frozen is None else bool(is_frozen)
    if not frozen:
        return False
    if not prefs.auto_update_check_enabled:
        return False

    current_time = now if now is not None else utc_now()
    last_dt = parse_iso_utc(prefs.last_update_check)
    if last_dt is not None:
        elapsed = current_time - last_dt
        if timedelta(0) <= elapsed < check_interval:
            return False

    return True


def should_show_update_notification(
    prefs: UpdatePreferences,
    latest_version_tag: str,
    *,
    local_version: str = __version__,
    draft: bool = False,
    prerelease: bool = False,
    now: datetime | None = None,
) -> bool:
    """Menentukan apakah notifikasi pembaruan boleh ditampilkan untuk rilis yang ditemukan.

    Ketentuan:
    - Tidak menawarkan draft atau prerelease.
    - Tidak menampilkan notifikasi bila versi terbaru <= versi lokal.
    - Jika versi baru berbeda dari ``last_notified_version``, notifikasi tetap ditampilkan.
    - Jika versi sama dan masih dalam periode tunda ``next_update_reminder``, tunda.
    """
    if draft or prerelease:
        return False

    try:
        latest_sem = parse_version(latest_version_tag)
        local_sem = parse_version(local_version)
    except ValueError:
        return False

    if latest_sem.is_prerelease or latest_sem <= local_sem:
        return False

    last_notified_norm = ""
    if prefs.last_notified_version:
        try:
            last_notified_norm = parse_version(prefs.last_notified_version).normalized
        except ValueError:
            last_notified_norm = prefs.last_notified_version.strip()

    if last_notified_norm and latest_sem.normalized != last_notified_norm:
        return True

    reminder_dt = parse_iso_utc(prefs.next_update_reminder)
    if reminder_dt is not None and last_notified_norm == latest_sem.normalized:
        current_time = now if now is not None else utc_now()
        if current_time < reminder_dt:
            return False

    return True


def record_check_timestamp(
    prefs: UpdatePreferences,
    *,
    now: datetime | None = None,
) -> UpdatePreferences:
    """Mencatat waktu pemeriksaan pembaruan terakhir dalam format UTC ISO-8601."""
    current_time = now if now is not None else utc_now()
    return replace(prefs, last_update_check=format_iso_utc(current_time))


def record_notification_shown(
    prefs: UpdatePreferences,
    version_tag: str,
) -> UpdatePreferences:
    """Mencatat versi terbaru yang telah diberitahukan kepada pengguna."""
    try:
        norm = parse_version(version_tag).normalized
    except ValueError:
        norm = version_tag.strip()
    return replace(prefs, last_notified_version=norm)


def snooze_update_reminder(
    prefs: UpdatePreferences,
    version_tag: str,
    *,
    now: datetime | None = None,
    reminder_interval: timedelta = REMINDER_DELAY_INTERVAL,
) -> UpdatePreferences:
    """Menunda pengingat versi yang sama selama 24 jam tanpa menonaktifkan pembaruan selamanya."""
    current_time = now if now is not None else utc_now()
    try:
        norm = parse_version(version_tag).normalized
    except ValueError:
        norm = version_tag.strip()
    return replace(
        prefs,
        last_notified_version=norm,
        next_update_reminder=format_iso_utc(current_time + reminder_interval),
    )
