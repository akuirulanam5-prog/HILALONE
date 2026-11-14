"""Hook PyInstaller kustom untuk astropy pada lingkungan tanpa matplotlib/pytest."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def _astropy_module_filter(name: str) -> bool:
    """Kecualikan submodul uji internal dan wcsaxes yang memanggil pytest.importorskip."""
    if name == "astropy.visualization.wcsaxes" or name.startswith("astropy.visualization.wcsaxes."):
        return False
    # astropy.__init__ mengimpor astropy.tests.runner saat startup, jadi wajib dipertahankan.
    if name in {"astropy.tests", "astropy.tests.runner", "astropy.tests.helper"}:
        return True
    parts = name.split(".")
    if "tests" in parts or "testing" in parts or "conftest" in parts:
        return False
    return True


# Data non-.py untuk astropy (kecualikan test data & wcsaxes)
datas = collect_data_files(
    "astropy",
    excludes=[
        "**/tests/**",
        "**/testing/**",
        "**/wcsaxes/**",
    ],
)

# Astropy memuat *_parsetab.py dan *_lextab.py langsung sebagai berkas saat runtime
datas += [
    (path, target)
    for path, target in collect_data_files("astropy", include_py_files=True)
    if path.endswith(("_parsetab.py", "_lextab.py"))
]

datas += copy_metadata("astropy")
datas += copy_metadata("numpy")

hiddenimports = collect_submodules(
    "astropy",
    filter=_astropy_module_filter,
    on_error="ignore",
)
hiddenimports += [
    "astropy.tests",
    "astropy.tests.runner",
    "numpy.lib.recfunctions",
]
