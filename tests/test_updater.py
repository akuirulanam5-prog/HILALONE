"""Pengujian unit komprehensif untuk modul pembaruan HILALONE (`hilalone.updates`).

Seluruh komunikasi HTTPS/GitHub API dimock secara lokal tanpa koneksi internet.
"""

from __future__ import annotations

from email.message import Message
import hashlib
import http.client
import io
import json
from pathlib import Path
import socket
from unittest.mock import MagicMock
import urllib.error
import urllib.request

import pytest

from hilalone import __version__
from hilalone.updates.github_updater import (
    check_for_updates,
    compute_file_sha256,
    download_verified_installer,
    fetch_latest_release,
    get_updates_dir,
    launch_installer,
    parse_release_payload,
    parse_sha256_digest,
    select_windows_installer_asset,
    verify_file_sha256,
)
from hilalone.updates.models import (
    GITHUB_LATEST_RELEASE_API_URL,
    ReleaseAsset,
    ReleaseInfo,
    UpdateIntegrityError,
    UpdateNetworkError,
    UpdateNotFoundError,
    UpdateRateLimitError,
    UpdateStatus,
    UpdateTimeoutError,
)
from hilalone.updates.update_worker import UpdateWorker, UpdateWorkerMode
from hilalone.updates.version import SemVer, is_newer_version, parse_version


class _FakeResponse:
    """Respons HTTP palsu untuk memock ``urllib.request.urlopen``."""

    def __init__(
        self,
        data: bytes,
        *,
        url: str = "https://api.github.com/repos/akuirulanam5-prog/HILALONE/releases/latest",
        headers: dict[str, str] | None = None,
        chunked_error_after: int | None = None,
    ) -> None:
        self._buf = io.BytesIO(data)
        self._url = url
        self._chunked_error_after = chunked_error_after
        self._bytes_read = 0
        msg = Message()
        for k, v in (headers or {}).items():
            msg[k] = v
        self.headers = msg

    def geturl(self) -> str:
        return self._url

    def read(self, n: int = -1) -> bytes:
        chunk = self._buf.read(n)
        self._bytes_read += len(chunk)
        if (
            self._chunked_error_after is not None
            and self._bytes_read >= self._chunked_error_after
        ):
            raise http.client.IncompleteRead(partial=chunk, expected=len(self._buf.getvalue()))
        return chunk

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _make_release_payload(
    *,
    tag_name: str = "v1.1.0",
    draft: bool = False,
    prerelease: bool = False,
    asset_name: str = "HILALONE_Setup_v1.1.0.exe",
    asset_bytes: bytes = b"dummy-installer-payload",
    digest: str | None = "AUTO",
    include_exe_asset: bool = True,
) -> dict[str, object]:
    computed_hex = hashlib.sha256(asset_bytes).hexdigest()
    final_digest = f"sha256:{computed_hex}" if digest == "AUTO" else digest

    assets: list[dict[str, object]] = [
        {
            "name": "HILALONE-source.zip",
            "browser_download_url": "https://github.com/akuirulanam5-prog/HILALONE/archive/refs/tags/v1.1.0.zip",
            "size": 1234,
            "content_type": "application/zip",
        }
    ]
    if include_exe_asset:
        asset_dict: dict[str, object] = {
            "name": asset_name,
            "browser_download_url": (
                f"https://github.com/akuirulanam5-prog/HILALONE/releases/download/{tag_name}/{asset_name}"
            ),
            "size": len(asset_bytes),
            "content_type": "application/vnd.microsoft.portable-executable",
        }
        if final_digest is not None:
            asset_dict["digest"] = final_digest
        assets.append(asset_dict)

    return {
        "tag_name": tag_name,
        "name": f"HILALONE {tag_name}",
        "body": "Perbaikan pipeline dan menu Help.",
        "published_at": "2026-11-20T10:00:00Z",
        "html_url": f"https://github.com/akuirulanam5-prog/HILALONE/releases/tag/{tag_name}",
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
    }


# ==============================================================================
# 1. Version Parsing & SemVer Comparison
# ==============================================================================
def test_parse_version_and_normalization() -> None:
    v1 = parse_version("v1.0.0")
    assert v1.major == 1
    assert v1.minor == 0
    assert v1.patch == 0
    assert v1.core_tuple == (1, 0, 0)
    assert v1.normalized == "1.0.0"
    assert not v1.is_prerelease

    v2 = parse_version("V2.3")
    assert v2.core_tuple == (2, 3, 0)

    v_pre = parse_version("v1.1.0-rc.2+win64")
    assert v_pre.is_prerelease
    assert v_pre.normalized == "1.1.0-rc.2"

    with pytest.raises(ValueError):
        parse_version("invalid-tag")


def test_version_comparison_numeric_semver_not_string() -> None:
    # Pada perbandingan string naif, "1.0.10" < "1.0.2"; secara numerik harus >
    assert is_newer_version("v1.0.10", "1.0.2") is True
    assert is_newer_version("v1.1.0", "1.0.0") is True
    assert is_newer_version("v2.0.0", "1.99.99") is True
    assert is_newer_version("v1.0.0", "1.0.0") is False
    assert is_newer_version("v0.9.5", "1.0.0") is False
    # Rilis stabil lebih tinggi daripada prerelease dengan angka sama
    assert SemVer(1, 1, 0) > parse_version("v1.1.0-beta.1")
    assert parse_version("v1.1.0-alpha.2") < parse_version("v1.1.0-alpha.10")


# ==============================================================================
# 2. Release Checking, Prerelease & Asset Selection
# ==============================================================================
def test_check_for_updates_up_to_date() -> None:
    payload = _make_release_payload(tag_name="v1.0.0", asset_name="HILALONE_Setup_v1.0.exe")
    raw = json.dumps(payload).encode("utf-8")
    opener = lambda req, timeout=15: _FakeResponse(raw)

    result = check_for_updates(local_version="1.0.0", opener=opener)
    assert result.status == UpdateStatus.UP_TO_DATE
    assert result.is_update_available is False
    assert result.release is not None and result.release.version.normalized == "1.0.0"


def test_check_for_updates_available_and_legacy_installer_compat() -> None:
    # Menguji pengenalan nama installer v1.0 style (`HILALONE_Setup_v1.0.exe`), v1.1.0, dan versi di atas __version__
    payload = _make_release_payload(tag_name="v1.2.0", asset_name="HILALONE_Setup_v1.2.0.exe")
    raw = json.dumps(payload).encode("utf-8")
    opener = lambda req, timeout=15: _FakeResponse(raw)

    result = check_for_updates(local_version=__version__, opener=opener)
    assert result.status == UpdateStatus.UPDATE_AVAILABLE
    assert result.is_update_available is True
    assert result.installer_asset is not None
    assert result.installer_asset.name == "HILALONE_Setup_v1.2.0.exe"

    # Pastikan jalur upgrade dari v1.0.0 ke v1.1.0 serta aset v1.0.0 tetap kompatibel
    payload_110 = _make_release_payload(tag_name="v1.1.0", asset_name="HILALONE_Setup_v1.1.0.exe")
    res_100_to_110 = check_for_updates(
        local_version="1.0.0",
        opener=lambda req, timeout=15: _FakeResponse(json.dumps(payload_110).encode("utf-8")),
    )
    assert res_100_to_110.status == UpdateStatus.UPDATE_AVAILABLE
    assert res_100_to_110.installer_asset is not None
    assert res_100_to_110.installer_asset.name == "HILALONE_Setup_v1.1.0.exe"

    legacy_payload = _make_release_payload(tag_name="v1.0.0", asset_name="HILALONE_Setup_v1.0.exe")
    legacy_release = parse_release_payload(legacy_payload)
    chosen = select_windows_installer_asset(legacy_release)
    assert chosen.name == "HILALONE_Setup_v1.0.exe"


def test_check_for_updates_skips_prerelease_and_draft() -> None:
    for flags in ({"prerelease": True}, {"draft": True}, {"tag_name": "v1.2.0-rc.1"}):
        payload = _make_release_payload(tag_name=flags.get("tag_name", "v1.2.0"), **{
            k: v for k, v in flags.items() if k != "tag_name"
        })
        raw = json.dumps(payload).encode("utf-8")
        result = check_for_updates(
            local_version="1.0.0",
            opener=lambda req, timeout=15, b=raw: _FakeResponse(b),
        )
        assert result.status == UpdateStatus.PRERELEASE_SKIPPED
        assert result.is_update_available is False
        assert result.installer_asset is None


def test_select_windows_installer_asset_not_found() -> None:
    payload = _make_release_payload(tag_name="v1.1.0", include_exe_asset=False)
    release = parse_release_payload(payload)
    with pytest.raises(UpdateNotFoundError):
        select_windows_installer_asset(release)


# ==============================================================================
# 3. Network Errors, Timeout, Rate Limit & HTTPS Security
# ==============================================================================
def test_fetch_latest_release_timeout() -> None:
    def _timeout_opener(req: urllib.request.Request, timeout: float = 15.0) -> object:
        raise urllib.error.URLError(socket.timeout("timed out"))

    with pytest.raises(UpdateTimeoutError):
        fetch_latest_release(GITHUB_LATEST_RELEASE_API_URL, opener=_timeout_opener)


def test_fetch_latest_release_github_api_errors() -> None:
    # HTTP 429 rate limit
    def _rate_limit_opener(req: urllib.request.Request, timeout: float = 15.0) -> object:
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {"X-RateLimit-Remaining": "0"}, io.BytesIO(b"rate limit")
        )

    with pytest.raises(UpdateRateLimitError):
        fetch_latest_release(opener=_rate_limit_opener)

    # HTTP 404 not found
    def _not_found_opener(req: urllib.request.Request, timeout: float = 15.0) -> object:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", Message(), io.BytesIO(b""))

    with pytest.raises(UpdateNotFoundError):
        fetch_latest_release(opener=_not_found_opener)

    # HTTP 500 server error
    def _server_err_opener(req: urllib.request.Request, timeout: float = 15.0) -> object:
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", Message(), io.BytesIO(b""))

    with pytest.raises(UpdateNetworkError):
        fetch_latest_release(opener=_server_err_opener)


def test_https_only_enforced_and_user_updates_dir() -> None:
    updates_dir = get_updates_dir()
    assert updates_dir.name == "updates"
    assert "HILALONE" in str(updates_dir)

    with pytest.raises(UpdateNetworkError):
        fetch_latest_release("http://api.github.com/repos/akuirulanam5-prog/HILALONE/releases/latest")

    # Redirect downgrade ke http:// diblokir
    def _http_redirect_opener(req: urllib.request.Request, timeout: float = 15.0) -> _FakeResponse:
        return _FakeResponse(b"{}", url="http://insecure.example.com/payload.json")

    with pytest.raises(UpdateNetworkError):
        fetch_latest_release(opener=_http_redirect_opener)


def test_fetch_latest_release_via_default_urlopen_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _make_release_payload(tag_name="v1.2.0", asset_name="HILALONE_Setup_v1.2.0.exe")
    raw = json.dumps(payload).encode("utf-8")

    def _fake_urlopen(req: urllib.request.Request, timeout: float = 15.0, context=None):  # noqa: ANN001
        assert req.full_url == GITHUB_LATEST_RELEASE_API_URL
        assert context is not None
        return _FakeResponse(raw, url=req.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    rel = fetch_latest_release()
    assert rel.tag_name == "v1.2.0"

    # Uji simulasi tidak ada internet (URLError DNS/socket)
    def _offline_urlopen(req: urllib.request.Request, timeout: float = 15.0, context=None):  # noqa: ANN001
        raise urllib.error.URLError(OSError("Name resolution failed"))

    monkeypatch.setattr(urllib.request, "urlopen", _offline_urlopen)
    with pytest.raises(UpdateNetworkError):
        fetch_latest_release()


# ==============================================================================
# 4. Download, Digest SHA-256 Validation & Safe Installer Execution
# ==============================================================================
def test_download_verified_installer_valid_sha256(tmp_path: Path) -> None:
    installer_bytes = b"MZ" + (b"HILALONE-SETUP-TEST" * 500)
    expected_hex = hashlib.sha256(installer_bytes).hexdigest()
    asset = ReleaseAsset(
        name="HILALONE_Setup_v1.1.0.exe",
        download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.0/HILALONE_Setup_v1.1.0.exe",
        size=len(installer_bytes),
        digest=f"sha256:{expected_hex.upper()}",
    )

    progress_events: list[tuple[int, int]] = []
    opener = lambda req, timeout=30: _FakeResponse(
        installer_bytes,
        url=asset.download_url,
        headers={"Content-Length": str(len(installer_bytes))},
    )

    dl = download_verified_installer(
        asset,
        dest_dir=tmp_path,
        progress_callback=lambda cur, tot: progress_events.append((cur, tot)),
        opener=opener,
    )
    assert dl.file_path == tmp_path / "HILALONE_Setup_v1.1.0.exe"
    assert dl.file_path.exists()
    assert not (tmp_path / "HILALONE_Setup_v1.1.0.exe.part").exists()
    assert dl.sha256_hex == expected_hex
    assert dl.bytes_downloaded == len(installer_bytes)
    assert len(progress_events) >= 1
    assert progress_events[-1] == (len(installer_bytes), len(installer_bytes))
    assert compute_file_sha256(dl.file_path) == expected_hex


def test_download_fails_on_invalid_or_missing_sha256_and_incomplete_file(tmp_path: Path) -> None:
    installer_bytes = b"MZ-installer-content"
    wrong_hex = "0" * 64

    # 1. Hash tidak cocok -> raise UpdateIntegrityError dan file tidak tersisa
    bad_hash_asset = ReleaseAsset(
        name="HILALONE_Setup_v1.1.0.exe",
        download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.0/HILALONE_Setup_v1.1.0.exe",
        size=len(installer_bytes),
        digest=f"sha256:{wrong_hex}",
    )
    with pytest.raises(UpdateIntegrityError):
        download_verified_installer(
            bad_hash_asset,
            dest_dir=tmp_path,
            opener=lambda req, timeout=30: _FakeResponse(installer_bytes, url=bad_hash_asset.download_url),
        )
    assert not (tmp_path / "HILALONE_Setup_v1.1.0.exe").exists()
    assert not (tmp_path / "HILALONE_Setup_v1.1.0.exe.part").exists()

    # 2. Metadata digest tidak tersedia atau format invalid
    for invalid_digest in (None, "", "md5:1234", "sha256:abcd"):
        no_digest_asset = ReleaseAsset(
            name="HILALONE_Setup_v1.1.0.exe",
            download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.0/HILALONE_Setup_v1.1.0.exe",
            size=len(installer_bytes),
            digest=invalid_digest,
        )
        with pytest.raises(UpdateIntegrityError):
            download_verified_installer(
                no_digest_asset,
                dest_dir=tmp_path,
                opener=lambda req, timeout=30: _FakeResponse(installer_bytes, url=no_digest_asset.download_url),
            )

    # 3. Download gagal / terputus di tengah jalan
    valid_hex = hashlib.sha256(installer_bytes).hexdigest()
    good_asset = ReleaseAsset(
        name="HILALONE_Setup_v1.1.0.exe",
        download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.0/HILALONE_Setup_v1.1.0.exe",
        size=len(installer_bytes),
        digest=f"sha256:{valid_hex}",
    )
    with pytest.raises(UpdateIntegrityError):
        download_verified_installer(
            good_asset,
            dest_dir=tmp_path,
            opener=lambda req, timeout=30: _FakeResponse(
                installer_bytes,
                url=good_asset.download_url,
                chunked_error_after=4,
            ),
        )
    assert not (tmp_path / "HILALONE_Setup_v1.1.0.exe.part").exists()

    # 4. Ukuran file lebih pendek daripada asset.size (incomplete)
    with pytest.raises(UpdateIntegrityError):
        download_verified_installer(
            good_asset,
            dest_dir=tmp_path,
            opener=lambda req, timeout=30: _FakeResponse(b"MZ-short", url=good_asset.download_url),
        )


def test_launch_installer_refuses_execution_when_validation_fails(tmp_path: Path) -> None:
    exe_path = tmp_path / "HILALONE_Setup_v1.1.0.exe"
    payload = b"valid-setup-binary"
    exe_path.write_bytes(payload)
    good_sha = hashlib.sha256(payload).hexdigest()

    popen_mock = MagicMock()

    # Hash salah -> installer TIDAK boleh dijalankan
    with pytest.raises(UpdateIntegrityError):
        launch_installer(exe_path, expected_sha256="f" * 64, popen_func=popen_mock)
    assert popen_mock.call_count == 0

    # Tanpa digest -> installer TIDAK boleh dijalankan
    with pytest.raises(UpdateIntegrityError):
        launch_installer(exe_path, expected_sha256=None, popen_func=popen_mock)
    assert popen_mock.call_count == 0

    # Hash cocok -> verify_file_sha256 lulus dan Popen dipanggil
    assert verify_file_sha256(exe_path, good_sha) == good_sha
    launch_installer(exe_path, expected_sha256=good_sha, popen_func=popen_mock)
    assert popen_mock.call_count == 1
    assert popen_mock.call_args[0][0] == [str(exe_path)]


def test_update_worker_signals_for_check_and_download(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    # 1. Worker check tersedia -> emits check_completed & update_available
    payload = _make_release_payload(tag_name="v1.1.0", asset_name="HILALONE_Setup_v1.1.0.exe")
    raw = json.dumps(payload).encode("utf-8")
    check_worker = UpdateWorker(
        mode=UpdateWorkerMode.CHECK_ONLY,
        local_version="1.0.0",
        check_func=lambda local_version: check_for_updates(
            local_version=local_version,
            opener=lambda req, timeout=15: _FakeResponse(raw),
        ),
    )
    available_results = []
    check_worker.update_available.connect(available_results.append)
    check_worker.run()
    qapp.processEvents()
    assert len(available_results) == 1
    assert available_results[0].installer_asset.name == "HILALONE_Setup_v1.1.0.exe"

    # 2. Worker download gagal digest -> emits hash_verification_finished(False, ...) & download_failed
    bad_asset = ReleaseAsset(
        name="HILALONE_Setup_v1.1.0.exe",
        download_url="https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.0/HILALONE_Setup_v1.1.0.exe",
        size=10,
        digest=None,
    )
    dl_worker = UpdateWorker(
        mode=UpdateWorkerMode.DOWNLOAD_AND_VERIFY,
        asset=bad_asset,
        dest_dir=tmp_path,
    )
    hash_events = []
    failed_msgs = []
    dl_worker.hash_verification_finished.connect(lambda ok, msg: hash_events.append((ok, msg)))
    dl_worker.download_failed.connect(failed_msgs.append)
    dl_worker.run()
    qapp.processEvents()
    assert hash_events and hash_events[0][0] is False
    assert len(failed_msgs) == 1
