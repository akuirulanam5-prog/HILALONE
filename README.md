# HILALONE — Automated Hilal Image Processing

**HILALONE** (v1.0.0) adalah aplikasi desktop Windows berbasis Python dan PySide6 untuk pengolahan citra pengamatan hilal dan bulan sabit muda secara otomatis, ilmiah, dan deterministik dengan prinsip *"Enhance the Signal, Never Invent the Signal"*.

---

## Fitur Utama

- **Dukungan Multi-Format Input (Read-Only)**:
  - Gambar tunggal: **FITS** (`astropy`), **TIFF** 8/16/32-bit (`tifffile`), **RAW kamera** (CR2/CR3/NEF/ARW/DNG via `rawpy` / LibRaw), **PNG**, dan **JPEG**.
  - Multi-frame & Video: urutan banyak gambar, direktori folder, video container (**MP4**, **MOV**, **AVI** via PyAV/FFmpeg terbundel), dan format astronomi **SER**.
  - Berkas sumber selalu dibuka dalam mode baca-saja (*read-only*) dan tidak pernah diubah atau ditimpa.
- **Tiga Profil Pemrosesan Otomatis (`BASIC`, `MEDIUM`, `HIGH`)**:
  - **BASIC**: Mean stacking, ekstraksi latar polinomial derajat 1, kontras global, dan MTF otomatis.
  - **MEDIUM**: Sigma-clipped mean stacking, polinomial derajat 2 atau TPS RBF, CLAHE terbatas, dan Asinh + MTF.
  - **HIGH**: Quality-weighted robust stacking, background robust otomatis, kontras adaptif, dan adaptive/GHT stretch.
- **Integritas Ilmiah Citra**:
  - Representasi internal **float32 linear** hingga tahap ekspor visual.
  - Mempertahankan jenis citra asli (**mono tetap mono**, **RGB tetap RGB**) dengan operasi *luminance-aware* untuk mencegah pergeseran warna.
  - Pemisahan tegas antara **hasil linear** (FITS / TIFF) dan **hasil visual** yang di-*stretch* (PNG / TIFF / Snapshot).
  - Pengukuran pergeseran antar frame bersifat baca-saja terhadap frame referensi tanpa alignment/warping otomatis; tidak menggunakan KOMBAT, denoise/sharpening otomatis, dark/bias, maupun deteksi AI.
  - Kalibrasi **Flat-Field opsional** jika master flat yang sesuai tersedia.
- **Antarmuka Desktop Astronomi (PySide6)**:
  - *Image Viewer* interaktif (zoom fit/1:1, pan, rotasi, flip horizontal/vertikal, serta mode **Normal / Negative View**).
  - Panel kontrol bertingkat berbasis *Collapsible Accordion* (`Input & Sequence`, `Automated Image Processing`, `Image Information`, `Sensor Information`).
  - Jendela **Histogram**, **Kurva**, **Info / Header FITS**, dan **Console Log**.
  - Dukungan dua tema antarmuka: **Standard Dark Theme** dan **Night Vision Red Theme** beserta aset branding resmi.

---

## Struktur Proyek

```text
HILALONE/
├─ assets/branding/       # Ikon aplikasi (.ico) dan logo Standard / Night Vision Red (.png)
├─ docs/                  # Dokumen spesifikasi, roadmap, gambaran proyek, & laporan audit
├─ hooks/                 # Hook PyInstaller kustom (astropy)
├─ src/hilalone/
│  ├─ gui/                # Antarmuka PySide6, viewer, panel, dialog, worker thread
│  ├─ input_manager/      # Adapter pembacaaan FITS, TIFF, RAW, SER, Video, sequence manager
│  ├─ output_manager/     # Penulis hasil linear & visual terpisah + riwayat pemrosesan
│  ├─ processing/         # Pipeline otomatis, stacking, flat calibration, background, stretch
│  └─ main.py             # Entry point aplikasi desktop
├─ tests/                 # Pengujian unit & UI (pytest) menggunakan data sintetis
├─ HILALONE.spec          # Konfigurasi build Windows executable (PyInstaller ONE-DIR)
├─ HILALONE.iss           # Skrip Windows Installer (Inno Setup 6)
├─ build_windows.bat      # Otomasi build Windows executable ke dist\HILALONE\
├─ clean_build.bat        # Pembersih artefak build sementara
├─ BUILD_README.md        # Panduan rinci build & distribusi Windows
├─ AGENTS.md              # Aturan arsitektur & batasan ilmiah proyek
├─ pyproject.toml         # Konfigurasi proyek dan pytest
└─ requirements*.txt      # Daftar dependensi terkunci (runtime, build, dev)
```

---

## Kebutuhan Lingkungan Pengembangan

- **Sistem Operasi**: Windows 10 / 11 (64-bit)
- **Python**: `3.10.11` (64-bit) dalam virtual environment terpisah (`.venv`)
- **Pustaka Utama**: `PySide6==6.12.0`, `numpy==2.2.6`, `astropy==6.1.7`, `scipy==1.15.3`, `scikit-image==0.25.2`, `tifffile==2025.5.10`, `rawpy==0.27.1`, `av==17.1.0`, `pillow==12.3.0`.

---

## Menjalankan Aplikasi (Development)

1. Buat dan aktifkan virtual environment Python 3.10.11 (`.venv`), lalu pasang dependensi:
   ```bat
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. Jalankan aplikasi melalui peluncur Windows atau modul Python:
   ```bat
   run_hilalone.bat
   ```
   atau:
   ```powershell
   $env:PYTHONPATH="src"
   .venv\Scripts\python.exe -m hilalone.main
   ```

---

## Menjalankan Pengujian Otomatis

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.venv\Scripts\pytest
```

---

## Build Distribusi Windows (`.exe`)

Pastikan dependensi build terpasang di `.venv` (`requirements-build.txt`), lalu jalankan:

```bat
build_windows.bat
```

Hasil build `ONE-DIR` tersedia di `dist\HILALONE\HILALONE.exe` (serta peluncur `HILALONE_Diagnostic.bat` untuk mode diagnostik/console). Dokumentasi lengkap proses build, uji distribusi bersih, dan pembuatan installer Inno Setup (`HILALONE.iss`) dapat dibaca di [BUILD_README.md](BUILD_README.md).

---

## Dokumentasi Terkait

- [AGENTS.md](AGENTS.md) — Aturan tetap arsitektur dan batasan ilmiah MVP 1.0
- [docs/project_overview.md](docs/project_overview.md) — Arsitektur teknis dan alur pipeline
- [docs/software_requirements.md](docs/software_requirements.md) — Spesifikasi kebutuhan fungsional & non-fungsional
- [docs/development_roadmap.md](docs/development_roadmap.md) — Tahapan pengembangan MVP 1.0
- [docs/HILALONE_MVP1_QUALITY_AUDIT.md](docs/HILALONE_MVP1_QUALITY_AUDIT.md) — Audit kualitas dan validasi ilmiah
- [BUILD_README.md](BUILD_README.md) — Panduan build executable Windows dan installer
