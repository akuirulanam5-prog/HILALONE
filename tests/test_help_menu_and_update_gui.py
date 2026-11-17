"""Pengujian integrasi GUI untuk menu Help, AboutDialog, Report an Issue, dan UpdateDialog."""

from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from hilalone import __version__
from hilalone.gui.about_dialog import AboutDialog
from hilalone.gui.info_dialog import ImageInformationDialog
from hilalone.gui.main_window import MainWindow
from hilalone.gui.update_dialog import UpdateDialog
from hilalone.updates.models import (
    DownloadResult,
    GITHUB_NEW_ISSUE_URL,
    OFFICIAL_WEBSITE_URL,
    ReleaseAsset,
    ReleaseInfo,
    UpdateCheckResult,
    UpdateStatus,
)
from hilalone.updates.version import parse_version


def _make_sample_update_result() -> UpdateCheckResult:
    data = b"sample-setup-exe"
    sha = hashlib.sha256(data).hexdigest()
    asset = ReleaseAsset(
        name="HILALONE_Setup_v1.2.0.exe",
        download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.2.0/HILALONE_Setup_v1.2.0.exe",
        size=95_195_800,
        digest=f"sha256:{sha}",
    )
    release = ReleaseInfo(
        tag_name="v1.2.0",
        version=parse_version("v1.2.0"),
        name="HILALONE v1.2.0",
        body="- Pembaruan menu Help\n- Perbaikan stabilitas",
        published_at="2026-11-20T09:30:00Z",
        html_url="https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.2.0",
        draft=False,
        prerelease=False,
        assets=(asset,),
    )
    return UpdateCheckResult(
        status=UpdateStatus.UPDATE_AVAILABLE,
        local_version=__version__,
        release=release,
        installer_asset=asset,
        message="Pembaruan HILALONE v1.2.0 tersedia.",
    )


def test_help_menu_available_after_view_with_expected_actions(qapp: QApplication) -> None:
    win = MainWindow()
    try:
        mb = win.menuBar()
        top_menus = [act.text() for act in mb.actions()]
        assert top_menus == ["Open Image", "Image Processing", "Tools", "View", "Help"]

        help_action = mb.actions()[-1]
        help_menu = help_action.menu()
        assert help_menu is not None

        items = [act.text() for act in help_menu.actions() if not act.isSeparator()]
        assert items == [
            "Check for Updates...",
            "Automatic Update Check",
            "Report an Issue...",
            "About HILALONE...",
        ]
        assert win.act_auto_update_check.isCheckable() is True
        assert win.act_auto_update_check.isChecked() is True
    finally:
        win.close()


def test_about_dialog_displays_required_fields_and_themes(qapp: QApplication) -> None:
    win = MainWindow()
    try:
        win.show_about_dialog()
        dlg = win.about_dialog
        assert dlg is not None
        assert isinstance(dlg, AboutDialog)
        assert not isinstance(dlg, ImageInformationDialog)
        assert dlg.isVisible()

        assert dlg.logo_label.pixmap() is not None
        assert not dlg.logo_label.pixmap().isNull()
        assert dlg.name_label.text() == "HILALONE"
        assert "Automated Hilal Image Processing" in dlg.subtitle_label.text()
        assert __version__ in dlg.version_label.text()
        assert "Enhance the Signal, Never Invent the Signal" in dlg.tagline_label.text()
        assert OFFICIAL_WEBSITE_URL in dlg.website_link_label.text()
        assert "https://github.com/akuirulanam5-prog/HILALONE" in dlg.github_link_label.text()
        assert "HILALONE Project" in dlg.copyright_label.text()

        # Pastikan pergantian tema ke Night Vision Red & kembali tidak crash dan memperbarui logo
        win.toggle_night_vision_theme(True, persist=False)
        qapp.processEvents()
        assert not dlg.logo_label.pixmap().isNull()
        win.toggle_night_vision_theme(False, persist=False)
        qapp.processEvents()
    finally:
        if win.about_dialog is not None:
            win.about_dialog.close()
        win.close()


def test_report_issue_opens_correct_github_url_with_mock(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened_urls: list[str] = []

    def _mock_open_url(url: QUrl) -> bool:
        opened_urls.append(url.toString())
        return True

    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(_mock_open_url))

    win = MainWindow()
    try:
        win.act_report_issue.trigger()
        assert opened_urls == [GITHUB_NEW_ISSUE_URL]
    finally:
        win.close()


def test_check_for_updates_runs_nonblocking_in_background_worker(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    release_event = threading.Event()
    started_event = threading.Event()

    up_to_date_res = UpdateCheckResult(
        status=UpdateStatus.UP_TO_DATE,
        local_version=__version__,
        release=None,
        installer_asset=None,
        message=f"HILALONE sudah menggunakan versi terbaru (v{__version__}).",
    )

    def _slow_mock_check(local_version: str = __version__) -> UpdateCheckResult:
        started_event.set()
        release_event.wait(timeout=3.0)
        return up_to_date_res

    info_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda parent, title, text: info_calls.append((title, text))),
    )

    try:
        t0 = time.perf_counter()
        win.check_for_updates_interactive(check_func=_slow_mock_check)
        elapsed_call = time.perf_counter() - t0
        # Harus segera kembali ke event loop GUI (non-blocking)
        assert elapsed_call < 0.2
        assert win.act_check_updates.isEnabled() is False
        assert "Checking" in win.act_check_updates.text()

        # GUI tetap responsif memproses event sementara worker menunggu jaringan
        assert started_event.wait(timeout=1.5)
        for _ in range(5):
            qapp.processEvents()

        # Lepaskan worker lalu tunggu selesai di event loop
        release_event.set()
        deadline = time.perf_counter() + 3.0
        while not info_calls and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert len(info_calls) == 1
        assert __version__ in info_calls[0][1]
        assert win.act_check_updates.isEnabled() is True
        assert win.act_check_updates.text() == "Check for Updates..."
    finally:
        release_event.set()
        if win._update_worker is not None:
            win._update_worker.wait(1500)
        win.close()


def test_update_dialog_frozen_download_and_safe_close_and_dev_mode(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _make_sample_update_result()

    # 1. Mode pengembangan (is_frozen=False): tidak menjalankan installer, menawarkan Open Release Page
    dev_dlg = UpdateDialog(result, is_frozen=False)
    try:
        assert dev_dlg.lbl_current_ver.text() == f"v{__version__}"
        assert dev_dlg.lbl_latest_ver.text() == "v1.2.0"
        assert "2026-11-20" in dev_dlg.lbl_release_date.text()
        assert "90.8 MB" in dev_dlg.lbl_installer_size.text()
        assert "Pembaruan menu Help" in dev_dlg.notes_edit.toPlainText()
        assert dev_dlg.btn_download_install.text() == "Download & Install"
        assert dev_dlg.btn_open_release.text() == "Open Release Page"
        assert dev_dlg.btn_later.text() == "Later"
        assert dev_dlg.dev_notice_label.isHidden() is False

        info_shown: list[str] = []
        opened_urls: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(
                lambda parent, title, text, buttons=None, default=None: (
                    info_shown.append(text),
                    QMessageBox.StandardButton.Yes,
                )[1]
            ),
        )
        monkeypatch.setattr(
            QDesktopServices,
            "openUrl",
            staticmethod(lambda url: (opened_urls.append(url.toString()), True)[1]),
        )

        dev_dlg.btn_download_install.click()
        assert len(info_shown) == 1
        assert opened_urls == ["https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.2.0"]
    finally:
        dev_dlg.close()

    # 2. Mode terinstal (is_frozen=True): download terverifikasi + konfirmasi + launch + close signal
    installer_file = tmp_path / "HILALONE_Setup_v1.2.0.exe"
    installer_bytes = b"MZ-verified-binary"
    installer_file.write_bytes(installer_bytes)
    sha_hex = hashlib.sha256(installer_bytes).hexdigest()

    launched_calls: list[tuple[Path, str | None]] = []
    close_requested: list[bool] = []

    def _mock_download(asset, *, dest_dir=None, progress_callback=None, cancel_check=None):  # noqa: ANN001
        if progress_callback is not None:
            progress_callback(len(installer_bytes) // 2, len(installer_bytes))
            progress_callback(len(installer_bytes), len(installer_bytes))
        return DownloadResult(
            file_path=installer_file,
            sha256_hex=sha_hex,
            expected_sha256_hex=sha_hex,
            bytes_downloaded=len(installer_bytes),
        )

    def _mock_launch(path: Path, *, expected_sha256: str | None = None) -> None:
        launched_calls.append((path, expected_sha256))

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )

    frozen_dlg = UpdateDialog(
        result,
        is_frozen=True,
        download_dir=tmp_path,
        download_func=_mock_download,
        launch_func=_mock_launch,
    )
    frozen_dlg.install_close_requested.connect(lambda: close_requested.append(True))
    try:
        frozen_dlg.show()
        frozen_dlg.btn_download_install.click()
        deadline = time.perf_counter() + 3.0
        while not launched_calls and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert launched_calls == [(installer_file, sha_hex)]
        assert close_requested == [True]
        assert frozen_dlg.progress_bar.value() == 100
    finally:
        frozen_dlg.close()

    # 3. Mode terinstal saat pemrosesan citra/stacking sedang aktif: tolak update tanpa force close
    busy_warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text: busy_warnings.append(text)),
    )
    busy_dlg = UpdateDialog(
        result,
        is_frozen=True,
        active_processing_checker=lambda: True,
        launch_func=_mock_launch,
    )
    try:
        busy_dlg.btn_download_install.click()
        assert len(busy_warnings) == 1
        assert "masih berjalan" in busy_warnings[0].lower()
    finally:
        busy_dlg.close()


def test_main_window_check_updates_opens_dialog_on_available_and_handles_failure(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hilalone.updates.models import UpdateNetworkError

    win = MainWindow()
    update_res = _make_sample_update_result()
    warnings_shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text: warnings_shown.append((title, text))),
    )

    try:
        # 1. Jika update tersedia, UpdateDialog tampil dan ikut mendukung pergantian tema
        win.check_for_updates_interactive(check_func=lambda local_version: update_res)
        deadline = time.perf_counter() + 3.0
        while win.update_dialog is None and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert win.update_dialog is not None
        assert win.update_dialog.isVisible()
        win.toggle_night_vision_theme(True, persist=False)
        qapp.processEvents()
        win.toggle_night_vision_theme(False, persist=False)
        win.update_dialog.close()

        # 2. Jika gagal jaringan, tampil QMessageBox.warning & tombol Check kembali aktif
        def _fail_check(local_version: str) -> UpdateCheckResult:
            raise UpdateNetworkError("Tidak dapat terhubung ke GitHub.")

        win.check_for_updates_interactive(check_func=_fail_check)
        deadline = time.perf_counter() + 3.0
        while not warnings_shown and time.perf_counter() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert len(warnings_shown) == 1
        assert "Tidak dapat terhubung ke GitHub" in warnings_shown[0][1]
        assert win.act_check_updates.isEnabled() is True
    finally:
        if win.update_dialog is not None:
            win.update_dialog.close()
        win.close()
