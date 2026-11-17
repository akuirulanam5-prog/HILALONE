"""Pengujian unit dan GUI untuk Automatic Update Notification HILALONE.

Seluruh pengecekan jaringan menggunakan mock tanpa menghubungi GitHub API nyata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import threading
import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from hilalone import __version__
from hilalone.gui.main_window import MainWindow
from hilalone.gui.update_dialog import UpdateDialog
from hilalone.gui.update_notification_dialog import UpdateNotificationDialog
from hilalone.updates.models import (
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckResult,
    UpdateNetworkError,
    UpdateStatus,
)
from hilalone.updates.update_preferences import (
    AUTO_UPDATE_STARTUP_DELAY_MS,
    UpdatePreferences,
    format_iso_utc,
    load_update_preferences,
    record_check_timestamp,
    save_update_preferences,
    should_run_automatic_check,
    should_show_update_notification,
    snooze_update_reminder,
)
from hilalone.updates.version import parse_version


def _make_release_result(
    tag: str = "v1.1.0",
    *,
    draft: bool = False,
    prerelease: bool = False,
    body: str = "- Fitur baru\n- Perbaikan bug",
) -> UpdateCheckResult:
    data = b"auto-notif-dummy-setup"
    sha = hashlib.sha256(data).hexdigest()
    asset = ReleaseAsset(
        name=f"HILALONE_Setup_{tag}.exe",
        download_url=f"https://github.com/akuirulanam5-prog/HILALONE/releases/download/{tag}/HILALONE_Setup_{tag}.exe",
        size=95_195_800,
        digest=f"sha256:{sha}",
    )
    ver = parse_version(tag)
    release = ReleaseInfo(
        tag_name=tag,
        version=ver,
        name=f"HILALONE {tag}",
        body=body,
        published_at="2026-11-22T12:00:00Z",
        html_url=f"https://github.com/akuirulanam5-prog/HILALONE/releases/tag/{tag}",
        draft=draft,
        prerelease=prerelease,
        assets=(asset,),
    )
    is_avail = not draft and not prerelease and not ver.is_prerelease and ver > parse_version(__version__)
    return UpdateCheckResult(
        status=UpdateStatus.UPDATE_AVAILABLE if is_avail else UpdateStatus.UP_TO_DATE,
        local_version=__version__,
        release=release,
        installer_asset=asset if is_avail else None,
        message=f"Pembaruan HILALONE {tag} tersedia." if is_avail else "Sudah versi terbaru.",
    )


# ==============================================================================
# 1. Unit Tests Preferensi & Penjadwalan 24 Jam (update_preferences.py)
# ==============================================================================
def test_preferences_default_enabled_and_disable_persistence(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.ini"

    # File konfigurasi belum ada -> default aktif
    prefs = load_update_preferences(cfg_path)
    assert prefs.auto_update_check_enabled is True
    assert prefs.last_update_check == ""
    assert prefs.next_update_reminder == ""
    assert prefs.last_notified_version == ""

    # Nonaktifkan lalu baca ulang
    disabled = UpdatePreferences(auto_update_check_enabled=False)
    save_update_preferences(disabled, cfg_path)
    reloaded = load_update_preferences(cfg_path)
    assert reloaded.auto_update_check_enabled is False
    assert should_run_automatic_check(reloaded, is_frozen=True) is False


def test_24h_interval_and_dev_environment_guards() -> None:
    base_now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    prefs = UpdatePreferences(auto_update_check_enabled=True)

    # Environment pengembangan (is_frozen=False) dilarang menjalankan auto check
    assert should_run_automatic_check(prefs, now=base_now, is_frozen=False) is False

    # Frozen + belum pernah cek -> diizinkan
    assert should_run_automatic_check(prefs, now=base_now, is_frozen=True) is True

    # Setelah cek dijalankan, dalam 24 jam berikutnya tidak boleh mengulang
    prefs_checked = record_check_timestamp(prefs, now=base_now)
    assert (
        should_run_automatic_check(
            prefs_checked, now=base_now + timedelta(hours=23, minutes=59), is_frozen=True
        )
        is False
    )

    # Tepat/lewat 24 jam -> boleh cek kembali
    assert (
        should_run_automatic_check(
            prefs_checked, now=base_now + timedelta(hours=24), is_frozen=True
        )
        is True
    )


def test_notification_version_logic_later_snooze_and_different_version() -> None:
    t0 = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    prefs = UpdatePreferences()

    # Draft / prerelease / versi lokal sama atau lebih rendah tidak memicu notifikasi
    assert should_show_update_notification(prefs, "v1.2.0", draft=True, now=t0) is False
    assert should_show_update_notification(prefs, "v1.2.0", prerelease=True, now=t0) is False
    assert should_show_update_notification(prefs, "v1.2.0-rc.1", now=t0) is False
    assert should_show_update_notification(prefs, f"v{__version__}", now=t0) is False
    assert should_show_update_notification(prefs, "v0.9.0", now=t0) is False

    # Versi stabil baru -> memicu notifikasi
    assert should_show_update_notification(prefs, "v1.1.0", now=t0) is True

    # Pengguna klik Later untuk 1.1.0 -> ditunda 24 jam, TIDAK memblokir versi berbeda (1.2.0)
    snoozed = snooze_update_reminder(prefs, "v1.1.0", now=t0)
    assert snoozed.last_notified_version == "1.1.0"
    assert should_show_update_notification(snoozed, "v1.1.0", now=t0 + timedelta(hours=12)) is False
    assert should_show_update_notification(snoozed, "v1.2.0", now=t0 + timedelta(hours=12)) is True
    # Setelah >= 24 jam -> pengingat 1.1.0 kembali diizinkan
    assert should_show_update_notification(snoozed, "v1.1.0", now=t0 + timedelta(hours=24)) is True


# ==============================================================================
# 2. GUI Lifecycle, Startup Timer, Update Now, Later & QThread Safety
# ==============================================================================
def test_startup_timer_dev_vs_frozen_and_toggle(qapp: QApplication, tmp_path: Path) -> None:
    # 1. Mode development (is_frozen=False): show() tidak memulai timer otomatis
    win_dev = MainWindow()
    try:
        assert win_dev._startup_update_timer.interval() == AUTO_UPDATE_STARTUP_DELAY_MS
        assert win_dev._startup_update_timer.isActive() is False
        win_dev.show()
        qapp.processEvents()
        assert win_dev._startup_update_timer.isActive() is False
        assert win_dev.run_automatic_update_check() is False
    finally:
        win_dev.close()

    # 2. Mode frozen: MainWindow baru dibuat BELUM memulai cek; show() menjadwalkan QTimer 10s
    cfg_path = tmp_path / "hilalone_cfg.ini"
    win_frozen = MainWindow()
    win_frozen._update_config_path = cfg_path
    win_frozen._is_frozen_checker = lambda: True
    try:
        assert win_frozen._startup_update_timer.isActive() is False
        win_frozen.show()
        qapp.processEvents()
        assert win_frozen._startup_update_timer.isActive() is True
        assert win_frozen._startup_update_timer.interval() == 10_000

        # Pengguna dapat menonaktifkan automatic update check lewat menu Help / method
        win_frozen.toggle_automatic_update_check(False)
        assert win_frozen.act_auto_update_check.isChecked() is False
        assert win_frozen._startup_update_timer.isActive() is False
        assert load_update_preferences(cfg_path).auto_update_check_enabled is False
        assert win_frozen.run_automatic_update_check() is False
    finally:
        win_frozen.close()


def test_auto_check_available_triggers_notification_update_now_and_later(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / "cfg_auto.ini"
    t0 = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Ok))

    res_110 = _make_release_result("v1.1.0")
    win = MainWindow()
    win._update_config_path = cfg_path
    win._is_frozen_checker = lambda: True
    win._now_provider = lambda: t0
    win.show()
    qapp.processEvents()

    try:
        # 1. Jalankan auto check saat timer dipicu -> membuka UpdateNotificationDialog
        win._startup_update_timer.stop()
        started = win.run_automatic_update_check(check_func=lambda local_version: res_110, now=t0)
        assert started is True

        deadline = time.perf_counter() + 3.0
        while win.update_notification_dialog is None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        notif = win.update_notification_dialog
        assert isinstance(notif, UpdateNotificationDialog)
        assert notif.isVisible()
        assert f"v{__version__}" in notif.lbl_current_ver.text()
        assert notif.lbl_latest_ver.text() == "v1.1.0"
        assert "2026-11-22" in notif.lbl_release_date.text()
        assert "Fitur baru" in notif.notes_summary_edit.toPlainText()

        # 2. Klik Later -> menutup notifikasi, menyimpan reminder 24 jam, & aktifkan reminder timer
        notif.btn_later.click()
        qapp.processEvents()
        assert notif.isVisible() is False
        assert win._reminder_update_timer.isActive() is True

        saved_prefs = load_update_preferences(cfg_path)
        assert saved_prefs.last_notified_version == "1.1.0"
        assert saved_prefs.next_update_reminder != ""
        assert saved_prefs.last_update_check == format_iso_utc(t0)

        # Dalam < 24 jam, auto check tidak berulang
        assert (
            win.run_automatic_update_check(
                check_func=lambda local_version: res_110,
                now=t0 + timedelta(hours=5),
            )
            is False
        )

        # Manual Help -> Check for Updates TETAP berjalan kapan saja walau dalam periode 24h & ditunda
        win.check_for_updates_interactive(check_func=lambda local_version: res_110)
        deadline = time.perf_counter() + 3.0
        while win.update_dialog is None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        assert isinstance(win.update_dialog, UpdateDialog)
        assert win.update_dialog.isVisible()
        win.update_dialog.close()
        win.update_dialog = None

        # 3. Setelah >= 24 jam atau saat versi berbeda (v1.2.0) tersedia -> Update Now membuka UpdateDialog
        res_120 = _make_release_result("v1.2.0", body="Pembaruan besar v1.2.0")
        t_next = t0 + timedelta(hours=25)
        win._now_provider = lambda: t_next
        assert win.run_automatic_update_check(check_func=lambda local_version: res_120, now=t_next) is True

        deadline = time.perf_counter() + 3.0
        while (
            win.update_notification_dialog is None
            or win.update_notification_dialog.check_result.release.tag_name != "v1.2.0"
        ) and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        notif2 = win.update_notification_dialog
        assert notif2 is not None and notif2.lbl_latest_ver.text() == "v1.2.0"
        notif2.btn_update_now.click()
        qapp.processEvents()
        assert isinstance(win.update_dialog, UpdateDialog)
        assert win.update_dialog.isVisible()
        assert win.update_dialog.lbl_latest_ver.text() == "v1.2.0"
    finally:
        win.close()


def test_auto_check_errors_and_up_to_date_stay_silent_and_no_dialog_after_close(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / "cfg_silent.ini"
    popups: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **kw: popups.append("warn")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **kw: popups.append("info")))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **kw: popups.append("crit")))

    t0 = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    win = MainWindow()
    win._update_config_path = cfg_path
    win._is_frozen_checker = lambda: True
    win._now_provider = lambda: t0
    win.show()
    win._startup_update_timer.stop()
    qapp.processEvents()

    try:
        # 1. Error jaringan saat auto check tidak memunculkan dialog pengganggu
        def _offline(local_version: str) -> UpdateCheckResult:
            raise UpdateNetworkError("Offline test error")

        assert win.run_automatic_update_check(check_func=_offline, now=t0) is True
        deadline = time.perf_counter() + 3.0
        while win._update_worker is not None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert popups == []
        assert win.update_notification_dialog is None
        assert any("gagal" in e.action.lower() for e in win.log_manager.entries)

        # 2. Up to date pada auto check tidak memunculkan popup maupun notifikasi
        t1 = t0 + timedelta(hours=25)
        win._now_provider = lambda: t1
        up_res = _make_release_result(f"v{__version__}")
        assert win.run_automatic_update_check(check_func=lambda local_version: up_res, now=t1) is True
        deadline = time.perf_counter() + 3.0
        while win._update_worker is not None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert popups == []
        assert win.update_notification_dialog is None

        # 3. Saat pemrosesan/stacking aktif: notifikasi boleh tampil tetapi instalasi tidak force close
        t_busy = t1 + timedelta(hours=25)
        win._now_provider = lambda: t_busy
        busy_flag = True
        win._is_stacking_running = lambda: busy_flag  # type: ignore[method-assign]
        res_125 = _make_release_result("v1.2.5")
        assert win.run_automatic_update_check(check_func=lambda local_version: res_125, now=t_busy) is True
        deadline = time.perf_counter() + 3.0
        while win.update_notification_dialog is None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert win.update_notification_dialog is not None
        win.update_notification_dialog.btn_update_now.click()
        qapp.processEvents()
        assert win.update_dialog is not None
        win.update_dialog.btn_download_install.click()
        assert any(p == "warn" for p in popups)
        assert not win._was_closed
        win.update_dialog.close()
        win.update_dialog = None
        if win.update_notification_dialog is not None:
            win.update_notification_dialog.close()
            win.update_notification_dialog = None
        busy_flag = False

        # 4. Tidak duplikat worker bila worker masih berjalan & aman ditutup di closeEvent
        t2 = t_busy + timedelta(hours=25)
        win._now_provider = lambda: t2
        started_evt = threading.Event()
        release_evt = threading.Event()

        def _slow_update(local_version: str) -> UpdateCheckResult:
            started_evt.set()
            release_evt.wait(timeout=0.25)
            return _make_release_result("v1.3.0")

        assert win.run_automatic_update_check(check_func=_slow_update, now=t2) is True
        assert started_evt.wait(timeout=1.5)
        # Worker aktif -> panggilan kedua tidak boleh spawn worker duplikat
        assert win.run_automatic_update_check(check_func=_slow_update, now=t2) is False
        win.close()
        release_evt.set()
        qapp.processEvents()
        # Simulasikan sinyal terlambat setelah MainWindow ditutup: dialog tidak boleh muncul
        win._on_update_available(_make_release_result("v1.3.0"))
        qapp.processEvents()
        assert win.update_notification_dialog is None
    finally:
        win.close()
