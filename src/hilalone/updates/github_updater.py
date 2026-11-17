"""Layanan pembaruan HILALONE terintegrasi dengan GitHub Releases (HTTPS + SHA-256).

Seluruh komunikasi jaringan memakai Python standard library (``urllib``, ``ssl``,
``json``, ``hashlib``, ``subprocess``) tanpa menambah dependency eksternal.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
from typing import Any, Callable, Sequence
import urllib.error
import urllib.parse
import urllib.request

from hilalone import __version__
from hilalone.gui.resources import get_user_data_dir
from hilalone.updates.models import (
    DEFAULT_API_TIMEOUT_SEC,
    DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    DownloadResult,
    GITHUB_LATEST_RELEASE_API_URL,
    GITHUB_RELEASES_PAGE_URL,
    INSTALLER_ASSET_EXTENSION,
    INSTALLER_ASSET_PREFIX,
    ReleaseAsset,
    ReleaseInfo,
    UpdateCancelledError,
    UpdateCheckResult,
    UpdateError,
    UpdateIntegrityError,
    UpdateNetworkError,
    UpdateNotFoundError,
    UpdateRateLimitError,
    UpdateStatus,
    UpdateTimeoutError,
)
from hilalone.updates.version import parse_version

logger = logging.getLogger(__name__)

_SHA256_DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$", re.IGNORECASE)
_DOWNLOAD_CHUNK_SIZE = 65536


def is_frozen_app() -> bool:
    """Mengembalikan True hanya bila aplikasi berjalan dari bundle executable PyInstaller."""
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def get_updates_dir(user_data_dir: Path | None = None) -> Path:
    """Mengembalikan direktori penyimpanan installer sementara di data pengguna.

    Secara default di Windows memakai ``%LOCALAPPDATA%\\HILALONE\\updates``.
    Tidak pernah menulis ke direktori bundle ``_MEIPASS`` atau folder instalasi.
    """
    base_dir = Path(user_data_dir) if user_data_dir is not None else get_user_data_dir()
    return base_dir / "updates"


def _validate_https_url(url: str) -> str:
    """Memastikan URL valid dan wajib memakai skema HTTPS."""
    if not isinstance(url, str) or not url.strip():
        raise UpdateNetworkError("URL pembaruan tidak valid atau kosong.")
    cleaned = url.strip()
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise UpdateNetworkError(
            f"Demi keamanan, koneksi pembaruan wajib memakai HTTPS (URL ditolak: {cleaned})."
        )
    return cleaned


def _build_request(url: str, *, accept: str) -> urllib.request.Request:
    """Membangun HTTP GET Request dengan header standar GitHub API."""
    safe_url = _validate_https_url(url)
    return urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": f"HILALONE-Desktop/{__version__}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )


def _open_https(
    request: urllib.request.Request,
    *,
    timeout_sec: float,
    opener: Callable[..., Any] | None = None,
) -> Any:
    """Membuka URL HTTPS dengan validasi TLS dan pemeriksaan URL hasil redirect."""
    if opener is not None:
        if hasattr(opener, "open"):
            resp = opener.open(request, timeout=timeout_sec)
        else:
            resp = opener(request, timeout=timeout_sec)
    else:
        ssl_context = ssl.create_default_context()
        resp = urllib.request.urlopen(request, timeout=timeout_sec, context=ssl_context)

    geturl_fn = getattr(resp, "geturl", None)
    if callable(geturl_fn):
        final_url = geturl_fn()
        if isinstance(final_url, str) and final_url.strip():
            parsed = urllib.parse.urlparse(final_url.strip())
            if parsed.scheme.lower() != "https":
                close_fn = getattr(resp, "close", None)
                if callable(close_fn):
                    close_fn()
                raise UpdateNetworkError(
                    "Redirect ke protokol non-HTTPS terdeteksi dan diblokir demi keamanan."
                )
    return resp


def _is_rate_limit_http_error(exc: urllib.error.HTTPError, body_text: str = "") -> bool:
    """Mendeteksi apakah respons HTTP 403/429 berasal dari pembatasan kuota GitHub API."""
    if exc.code == 429:
        return True
    if exc.code != 403:
        return False
    headers = getattr(exc, "headers", None)
    if headers is not None:
        remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
        if remaining == "0":
            return True
    return "rate limit" in body_text.lower()


def _translate_network_exception(exc: Exception, *, context: str) -> UpdateError:
    """Mengubah exception jaringan standard library menjadi UpdateError Bahasa Indonesia."""
    if isinstance(exc, UpdateError):
        return exc

    if isinstance(exc, urllib.error.HTTPError):
        body_text = ""
        try:
            raw_body = exc.read()
            if isinstance(raw_body, bytes):
                body_text = raw_body.decode("utf-8", errors="replace")
        except Exception:
            body_text = ""

        if _is_rate_limit_http_error(exc, body_text):
            return UpdateRateLimitError(
                "Batas permintaan GitHub API (rate limit) tercapai. "
                "Silakan tunggu beberapa menit sebelum mencoba kembali."
            )
        if exc.code == 404:
            return UpdateNotFoundError(
                "Rilis terbaru atau berkas installer HILALONE tidak ditemukan pada GitHub Releases (HTTP 404)."
            )
        return UpdateNetworkError(
            f"Gagal {context}: server GitHub merespons HTTP {exc.code}."
        )

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return UpdateTimeoutError(
                f"Waktu koneksi habis (timeout) saat {context}. Periksa kestabilan internet Anda."
            )
        if isinstance(reason, ssl.SSLError):
            return UpdateNetworkError(
                f"Verifikasi sertifikat keamanan TLS/HTTPS gagal saat {context}."
            )
        return UpdateNetworkError(
            f"Tidak dapat terhubung ke GitHub saat {context}. "
            "Pastikan perangkat terhubung ke internet."
        )

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return UpdateTimeoutError(
            f"Waktu koneksi habis (timeout) saat {context}. Periksa kestabilan internet Anda."
        )

    if isinstance(exc, http.client.IncompleteRead):
        return UpdateIntegrityError(
            "Unduhan installer terputus sebelum seluruh data selesai diterima."
        )

    if isinstance(exc, (http.client.HTTPException, ssl.SSLError, OSError)):
        return UpdateNetworkError(f"Gangguan jaringan saat {context}: {exc}")

    return UpdateError(f"Gagal {context}: {exc}")


def parse_sha256_digest(digest: str | None) -> str:
    """Memvalidasi dan mengekstrak hash hex SHA-256 dari metadata ``digest`` aset rilis."""
    if not isinstance(digest, str) or not digest.strip():
        raise UpdateIntegrityError(
            "Metadata digest SHA-256 tidak tersedia pada rilis GitHub. "
            "Demi keamanan, installer tidak dapat diverifikasi atau dijalankan."
        )
    match = _SHA256_DIGEST_RE.match(digest.strip())
    if match is None:
        raise UpdateIntegrityError(
            f"Format metadata digest SHA-256 tidak valid: '{digest}'. "
            "Demi keamanan, installer tidak dijalankan."
        )
    return match.group(1).lower()


def parse_release_payload(payload: dict[str, Any]) -> ReleaseInfo:
    """Mengubah JSON payload GitHub Releases API menjadi objek :class:`ReleaseInfo`."""
    if not isinstance(payload, dict):
        raise UpdateError("Format metadata rilis GitHub tidak valid (bukan objek JSON).")

    tag_name = str(payload.get("tag_name") or "").strip()
    if not tag_name:
        raise UpdateError("Metadata rilis GitHub tidak memiliki field 'tag_name'.")

    try:
        parsed_ver = parse_version(tag_name)
    except ValueError as err:
        raise UpdateError(f"Tag rilis GitHub tidak dapat diparsing sebagai versi: {err}") from err

    raw_assets = payload.get("assets")
    if raw_assets is None:
        raw_assets = []
    if not isinstance(raw_assets, list):
        raise UpdateError("Metadata rilis GitHub memiliki field 'assets' yang tidak valid.")

    assets: list[ReleaseAsset] = []
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        asset_name = str(item.get("name") or "").strip()
        dl_url = str(item.get("browser_download_url") or "").strip()
        if not asset_name or not dl_url:
            continue
        raw_size = item.get("size", 0)
        try:
            asset_size = max(0, int(raw_size or 0))
        except (TypeError, ValueError):
            asset_size = 0
        raw_digest = item.get("digest")
        digest_str = str(raw_digest).strip() if isinstance(raw_digest, str) and raw_digest.strip() else None
        content_type = str(item.get("content_type") or "").strip()
        assets.append(
            ReleaseAsset(
                name=asset_name,
                download_url=dl_url,
                size=asset_size,
                digest=digest_str,
                content_type=content_type,
            )
        )

    html_url = str(payload.get("html_url") or GITHUB_RELEASES_PAGE_URL).strip()
    return ReleaseInfo(
        tag_name=tag_name,
        version=parsed_ver,
        name=str(payload.get("name") or tag_name).strip(),
        body=str(payload.get("body") or "").strip(),
        published_at=str(payload.get("published_at") or "").strip(),
        html_url=html_url,
        draft=bool(payload.get("draft", False)),
        prerelease=bool(payload.get("prerelease", False)),
        assets=tuple(assets),
    )


def select_windows_installer_asset(release: ReleaseInfo) -> ReleaseAsset:
    """Memilih aset installer Windows (``HILALONE_Setup*.exe``) dari metadata rilis.

    Tidak pernah memilih arsip source code (``.zip`` atau ``.tar.gz``).
    """
    candidates = [
        asset
        for asset in release.assets
        if Path(asset.name).name == asset.name
        and asset.name.startswith(INSTALLER_ASSET_PREFIX)
        and asset.name.lower().endswith(INSTALLER_ASSET_EXTENSION)
    ]
    if not candidates:
        raise UpdateNotFoundError(
            "Asset installer Windows (HILALONE_Setup*.exe) tidak ditemukan pada rilis ini."
        )

    # Prioritaskan installer bernomor versi jika lebih dari satu aset cocok
    candidates.sort(
        key=lambda a: (
            1 if f"v{release.version.normalized}" in a.name else 0,
            1 if "_v" in a.name else 0,
            a.size,
        ),
        reverse=True,
    )
    selected = candidates[0]
    _validate_https_url(selected.download_url)
    return selected


def fetch_latest_release(
    api_url: str = GITHUB_LATEST_RELEASE_API_URL,
    *,
    timeout_sec: float = DEFAULT_API_TIMEOUT_SEC,
    opener: Callable[..., Any] | None = None,
) -> ReleaseInfo:
    """Mengambil dan mem-parsing metadata rilis stabil terbaru dari GitHub Releases API."""
    request = _build_request(api_url, accept="application/vnd.github+json")
    try:
        with _open_https(request, timeout_sec=timeout_sec, opener=opener) as resp:
            raw_bytes = resp.read()
    except Exception as exc:
        raise _translate_network_exception(exc, context="memeriksa pembaruan") from exc

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"Respons JSON GitHub Releases tidak dapat dibaca: {exc}") from exc

    return parse_release_payload(payload)


def evaluate_release_for_update(
    release: ReleaseInfo,
    *,
    local_version: str = __version__,
) -> UpdateCheckResult:
    """Membandingkan rilis GitHub yang diperoleh dengan versi aplikasi yang berjalan."""
    local_sem = parse_version(local_version)

    if release.draft or release.prerelease or release.version.is_prerelease:
        return UpdateCheckResult(
            status=UpdateStatus.PRERELEASE_SKIPPED,
            local_version=local_sem.normalized,
            release=release,
            installer_asset=None,
            message=(
                f"Rilis {release.tag_name} berstatus draft/prerelease sehingga tidak ditawarkan "
                "sebagai pembaruan reguler."
            ),
        )

    if release.version > local_sem:
        installer_asset = select_windows_installer_asset(release)
        return UpdateCheckResult(
            status=UpdateStatus.UPDATE_AVAILABLE,
            local_version=local_sem.normalized,
            release=release,
            installer_asset=installer_asset,
            message=(
                f"Pembaruan HILALONE v{release.version.normalized} tersedia "
                f"(versi saat ini: v{local_sem.normalized})."
            ),
        )

    return UpdateCheckResult(
        status=UpdateStatus.UP_TO_DATE,
        local_version=local_sem.normalized,
        release=release,
        installer_asset=None,
        message=f"HILALONE sudah menggunakan versi terbaru (v{local_sem.normalized}).",
    )


def check_for_updates(
    local_version: str = __version__,
    *,
    api_url: str = GITHUB_LATEST_RELEASE_API_URL,
    timeout_sec: float = DEFAULT_API_TIMEOUT_SEC,
    opener: Callable[..., Any] | None = None,
) -> UpdateCheckResult:
    """Memeriksa ketersediaan pembaruan aplikasi terhadap GitHub Releases terbaru."""
    release = fetch_latest_release(api_url, timeout_sec=timeout_sec, opener=opener)
    return evaluate_release_for_update(release, local_version=local_version)


def compute_file_sha256(
    file_path: Path,
    *,
    chunk_size: int = _DOWNLOAD_CHUNK_SIZE,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    """Menghitung hash SHA-256 (lowercase hex) dari berkas pada disk secara streaming."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while True:
            if cancel_check is not None and cancel_check():
                raise UpdateCancelledError("Validasi file installer dibatalkan oleh pengguna.")
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def verify_file_sha256(
    file_path: Path,
    expected_digest_or_hex: str | None,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    """Memverifikasi kecocokan SHA-256 berkas hasil unduhan terhadap metadata rilis.

    Menerima format metadata GitHub ``sha256:<hex64>`` atau string hex SHA-256 64 karakter.
    Melempar :class:`UpdateIntegrityError` bila digest kosong, tidak valid, atau tidak cocok.
    """
    if isinstance(expected_digest_or_hex, str) and re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_digest_or_hex.strip()
    ):
        expected_hex = expected_digest_or_hex.strip().lower()
    else:
        expected_hex = parse_sha256_digest(expected_digest_or_hex)

    actual_hex = compute_file_sha256(file_path, cancel_check=cancel_check)
    if not hmac.compare_digest(actual_hex, expected_hex):
        raise UpdateIntegrityError(
            "Validasi integritas SHA-256 gagal: hash file hasil unduhan tidak cocok "
            f"dengan metadata rilis (harapan: {expected_hex[:12]}..., aktual: {actual_hex[:12]}...)."
        )
    return actual_hex


def download_verified_installer(
    asset: ReleaseAsset,
    *,
    dest_dir: Path | None = None,
    timeout_sec: float = DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    opener: Callable[..., Any] | None = None,
) -> DownloadResult:
    """Mengunduh installer ke direktori pengguna, memeriksa kelengkapan ukuran, dan validasi SHA-256.

    File diunduh ke berkas sementara ``*.part`` dan hanya dipindahkan menjadi berkas
    ``.exe`` final apabila unduhan selesai penuh, ukuran cocok, dan SHA-256 sesuai.
    """
    _validate_https_url(asset.download_url)
    expected_hex = parse_sha256_digest(asset.digest)

    safe_filename = Path(asset.name).name
    if (
        not safe_filename
        or safe_filename != asset.name
        or not safe_filename.startswith(INSTALLER_ASSET_PREFIX)
        or not safe_filename.lower().endswith(INSTALLER_ASSET_EXTENSION)
    ):
        raise UpdateIntegrityError(f"Nama file installer tidak aman atau tidak valid: '{asset.name}'.")

    target_dir = Path(dest_dir) if dest_dir is not None else get_updates_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / safe_filename
    part_path = target_dir / f"{safe_filename}.part"

    request = _build_request(asset.download_url, accept="application/octet-stream")
    hasher = hashlib.sha256()
    bytes_downloaded = 0

    try:
        with _open_https(request, timeout_sec=timeout_sec, opener=opener) as resp:
            content_length_raw = None
            headers = getattr(resp, "headers", None)
            if headers is not None:
                content_length_raw = headers.get("Content-Length")

            header_size = 0
            if content_length_raw is not None:
                try:
                    header_size = max(0, int(str(content_length_raw).strip()))
                except ValueError:
                    header_size = 0

            reported_total = header_size if header_size > 0 else (asset.size if asset.size > 0 else -1)

            with open(part_path, "wb") as out_fh:
                while True:
                    if cancel_check is not None and cancel_check():
                        raise UpdateCancelledError("Pengunduhan pembaruan dibatalkan oleh pengguna.")
                    chunk = resp.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    out_fh.write(chunk)
                    hasher.update(chunk)
                    bytes_downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(bytes_downloaded, reported_total)

        if cancel_check is not None and cancel_check():
            raise UpdateCancelledError("Pengunduhan pembaruan dibatalkan oleh pengguna.")

        if bytes_downloaded <= 0:
            raise UpdateIntegrityError("File installer hasil unduhan kosong (0 byte).")

        expected_size = asset.size if asset.size > 0 else header_size
        if expected_size > 0 and bytes_downloaded != expected_size:
            raise UpdateIntegrityError(
                f"File hasil unduhan tidak lengkap ({bytes_downloaded} dari {expected_size} byte)."
            )

        actual_hex = hasher.hexdigest().lower()
        if not hmac.compare_digest(actual_hex, expected_hex):
            raise UpdateIntegrityError(
                "Validasi SHA-256 gagal: hash file installer tidak cocok dengan metadata rilis. "
                "File unduhan dihapus demi keamanan."
            )

        os.replace(part_path, final_path)
        return DownloadResult(
            file_path=final_path,
            sha256_hex=actual_hex,
            expected_sha256_hex=expected_hex,
            bytes_downloaded=bytes_downloaded,
        )
    except UpdateCancelledError:
        _safe_unlink(part_path)
        raise
    except Exception as exc:
        _safe_unlink(part_path)
        if isinstance(exc, UpdateError):
            raise
        raise _translate_network_exception(exc, context="mengunduh installer") from exc


def launch_installer(
    installer_path: Path,
    *,
    expected_sha256: str | None = None,
    popen_func: Callable[..., Any] = subprocess.Popen,
    extra_args: Sequence[str] | None = None,
) -> Any:
    """Menjalankan installer Inno Setup tervalidasi menggunakan ``subprocess.Popen``.

    Selalu memeriksa keberadaan berkas ``.exe`` dan memverifikasi ulang SHA-256 tepat
    sebelum eksekusi apabila ``expected_sha256`` diberikan.
    """
    path = Path(installer_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpdateIntegrityError(
            f"File installer tidak ditemukan atau kosong di: {path}"
        )
    if (
        not path.name.startswith(INSTALLER_ASSET_PREFIX)
        or path.suffix.lower() != INSTALLER_ASSET_EXTENSION
    ):
        raise UpdateIntegrityError(f"Nama berkas installer tidak valid untuk dijalankan: {path.name}")

    # Wajib validasi digest SHA-256 sebelum eksekusi file installer
    verify_file_sha256(path, expected_sha256)

    cmd = [str(path)]
    if extra_args:
        cmd.extend(str(arg) for arg in extra_args)

    popen_kwargs: dict[str, Any] = {"close_fds": True}
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        if creationflags:
            popen_kwargs["creationflags"] = creationflags

    logger.info("Menjalankan installer pembaruan HILALONE: %s", path)
    return popen_func(cmd, **popen_kwargs)


def _safe_unlink(path: Path) -> None:
    """Menghapus berkas sementara secara aman bila ada."""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
