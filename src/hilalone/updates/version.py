"""Parser dan pembanding versi semantik (major.minor.patch) untuk HILALONE.

Mendukung tag rilis seperti ``v1.0.0``, ``1.0.0``, ``v1.1``, maupun sufiks
prerelease/build metadata (mis. ``v1.1.0-rc.1``) tanpa memakai perbandingan
string naif.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

_SEMVER_RE = re.compile(
    r"^[vV]?\s*(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)(?:\.(?P<patch>0|[1-9]\d*))?"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _prerelease_sort_key(prerelease: str) -> tuple[tuple[int, int | str], ...]:
    """Mengubah bagian prerelease menjadi tuple pembanding sesuai aturan SemVer."""
    parts: list[tuple[int, int | str]] = []
    for token in prerelease.split("."):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token.lower()))
    return tuple(parts)


@dataclass(frozen=True)
class SemVer:
    """Representasi terstruktur versi aplikasi berdasarkan major, minor, dan patch."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""
    raw: str = ""

    @property
    def is_prerelease(self) -> bool:
        """Mengembalikan True bila versi memiliki penanda prerelease."""
        return bool(self.prerelease)

    @property
    def core_tuple(self) -> tuple[int, int, int]:
        """Tuple angka (major, minor, patch)."""
        return (self.major, self.minor, self.patch)

    @property
    def normalized(self) -> str:
        """Representasi kanonik ``major.minor.patch[-prerelease]`` tanpa awalan ``v``."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{self.prerelease}"
        return base

    def _comparison_key(self) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
        # Versi stabil (is_stable=1) memiliki prioritas lebih tinggi daripada prerelease (0)
        is_stable = 0 if self.prerelease else 1
        pre_key = _prerelease_sort_key(self.prerelease) if self.prerelease else ()
        return (self.major, self.minor, self.patch, is_stable, pre_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._comparison_key() == other._comparison_key()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._comparison_key() < other._comparison_key()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._comparison_key() <= other._comparison_key()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._comparison_key() > other._comparison_key()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._comparison_key() >= other._comparison_key()

    def __str__(self) -> str:
        return self.normalized


def parse_version(version_str: str) -> SemVer:
    """Mem-parsing tag/string versi menjadi objek :class:`SemVer`.

    Menerima awalan opsional ``v`` atau ``V`` (mis. ``v1.0.0`` atau ``1.1.0``).
    Melempar ``ValueError`` apabila format versi tidak valid.
    """
    if not isinstance(version_str, str):
        raise ValueError("Format versi harus berupa teks (str).")

    cleaned = version_str.strip()
    match = _SEMVER_RE.match(cleaned)
    if match is None:
        raise ValueError(f"Format versi tidak valid: '{version_str}'.")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch_raw = match.group("patch")
    patch = int(patch_raw) if patch_raw is not None else 0
    prerelease = match.group("prerelease") or ""
    build = match.group("build") or ""

    return SemVer(
        major=major,
        minor=minor,
        patch=patch,
        prerelease=prerelease,
        build=build,
        raw=cleaned,
    )


def is_newer_version(candidate_version: str | SemVer, current_version: str | SemVer) -> bool:
    """Mengembalikan True apabila ``candidate_version`` lebih baru dari ``current_version``."""
    cand = candidate_version if isinstance(candidate_version, SemVer) else parse_version(candidate_version)
    curr = current_version if isinstance(current_version, SemVer) else parse_version(current_version)
    return cand > curr
