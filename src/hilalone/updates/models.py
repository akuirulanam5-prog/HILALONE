"""Model data, konstanta, dan tipe pengecualian untuk sistem pembaruan HILALONE."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hilalone.updates.version import SemVer


GITHUB_OWNER = "akuirulanam5-prog"
GITHUB_REPO = "HILALONE"
GITHUB_LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
GITHUB_RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
GITHUB_NEW_ISSUE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/issues/new"
OFFICIAL_WEBSITE_URL = "https://hilalone-website.vercel.app"

INSTALLER_ASSET_PREFIX = "HILALONE_Setup"
INSTALLER_ASSET_EXTENSION = ".exe"

DEFAULT_API_TIMEOUT_SEC = 15.0
DEFAULT_DOWNLOAD_TIMEOUT_SEC = 30.0


class UpdateError(Exception):
    """Pengecualian dasar seluruh kegagalan pada sistem pembaruan HILALONE."""


class UpdateNetworkError(UpdateError):
    """Kegagalan komunikasi jaringan atau HTTPS (offline, DNS, TLS, koneksi terputus)."""


class UpdateTimeoutError(UpdateNetworkError):
    """Batas waktu koneksi atau pembacaan data dari GitHub habis (timeout)."""


class UpdateRateLimitError(UpdateError):
    """Batas kuota permintaan (rate limit) GitHub API tercapai."""


class UpdateNotFoundError(UpdateError):
    """Rilis terbaru atau asset installer Windows yang sesuai tidak ditemukan."""


class UpdateIntegrityError(UpdateError):
    """Kegagalan validasi ukuran file, metadata digest, atau kecocokan SHA-256."""


class UpdateCancelledError(UpdateError):
    """Proses pemeriksaan atau pengunduhan pembaruan dibatalkan oleh pengguna."""


class UpdateStatus(str, Enum):
    """Status hasil perbandingan versi lokal terhadap rilis terbaru."""

    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    UP_TO_DATE = "UP_TO_DATE"
    PRERELEASE_SKIPPED = "PRERELEASE_SKIPPED"


@dataclass(frozen=True)
class ReleaseAsset:
    """Representasi satu berkas asset pada rilis GitHub."""

    name: str
    download_url: str
    size: int
    digest: str | None = None
    content_type: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    """Metadata rilis GitHub yang sudah diparsing dan tervalidasi."""

    tag_name: str
    version: SemVer
    name: str
    body: str
    published_at: str
    html_url: str
    draft: bool
    prerelease: bool
    assets: tuple[ReleaseAsset, ...]


@dataclass(frozen=True)
class UpdateCheckResult:
    """Hasil pemeriksaan pembaruan aplikasi terhadap GitHub Releases."""

    status: UpdateStatus
    local_version: str
    release: ReleaseInfo | None
    installer_asset: ReleaseAsset | None
    message: str

    @property
    def is_update_available(self) -> bool:
        """Mengembalikan True hanya bila pembaruan stabil dan installer valid tersedia."""
        return self.status == UpdateStatus.UPDATE_AVAILABLE and self.installer_asset is not None


@dataclass(frozen=True)
class DownloadResult:
    """Hasil pengunduhan dan validasi SHA-256 installer Windows."""

    file_path: Path
    sha256_hex: str
    expected_sha256_hex: str
    bytes_downloaded: int
