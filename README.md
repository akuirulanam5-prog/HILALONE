# HILALONE — Automated Hilal Image Processing

**HILALONE** (v1.1.3) adalah aplikasi desktop Windows berbasis Python dan PySide6 untuk pengolahan citra pengamatan hilal dan bulan sabit muda secara otomatis, ilmiah, dan deterministik dengan prinsip *"Enhance the Signal, Never Invent the Signal"*.

---

## Apa yang Baru di v1.1.3 (Release Highlights)

1. **Scientific Processing Timeline & Report Schema v2.0 (`*_processing_report.json`)**:
   - Struktur laporan JSON penelitian generasi baru (`schema_version: "2.0"`) yang merekam perjalanan lengkap pengolahan citra sejak pengguna menekan **Open Image** (`session_start_timestamp`) hingga berkas foto hasil selesai ditulis dan diverifikasi di disk (`session_end_timestamp`).
   - Memisahkan **9 bagian ilmiah utama**: `report_metadata`, `session_information`, `source_data` (dengan deduplikasi otomatis sehingga 1 berkas Video/SER dengan $N$ frame dicatat sebagai 1 entri berkas sumber dengan `decoded_frame_count = N`), `user_interaction_timeline`, `workflow_idle_intervals` (waktu tunggu saat tidak ada proses backend aktif), `processing_pipeline` (11 sub-tahap terpisah), `scientific_data_branches`, `output_information` (memisahkan durasi dialog Save dari durasi tulis disk aktual), dan `timing_summary`.
   - Mendukung pembacaan arsip laporan Schema `v1.0` lama melalui `load_processing_report()`.
2. **Tipografi & Alignment Ringkasan Tiga Kolom Sejajar (`format_aligned_summary`)**:
   - Seluruh ringkasan manusia (`PROCESSING SUMMARY`, `OUTPUT SAVE SUMMARY`, berkas `.log`/`.txt`, dan `human_readable_summary`) kini dikelompokkan ke dalam 5 bagian (`SESSION INFORMATION`, `INPUT INFORMATION`, `PROCESSING RESULTS`, `OUTPUT INFORMATION`, `TIME SUMMARY`) dengan seluruh tanda titik dua (` : `) sejajar vertikal sempurna dan *line-wrapping* nilai panjang tepat di bawah kolom `VALUE`.
   - Pewarnaan semantik selektif pada Console (hanya nilai status yang diwarnai khusus di tema **Standard Dark** & **Night Vision Red**, serta teks murni bebas ANSI saat diekspor ke `.log`/`.txt`).
3. **Professional Scientific Processing Log & Console System (`src/hilalone/core/logging/`)**:
   - Arsitektur logging ilmiah terpusat dengan **Application Session ID (`SES-...`)**, **Processing Run ID (`RUN-...`)**, serta tiga mode Detail fungsional (**Normal**, **Verbose**, dan **Debug**).
   - Standardisasi seluruh format durasi ke **`0.00 s` / `Duration: 0.00 s`**, perbaikan tata letak tombol `Auto-scroll: ON/OFF`, dan pengarahan otomatis dialog **Export Visible / Complete Log** ke folder sumber citra aktif.
4. **Desktop Auto-Update System & Pembaruan Branding (v1.1.0 – v1.1.3)**:
   - Menu **Help** (**Check for Updates...**, **Automatic Update Check**, **Report an Issue...**, **About HILALONE...**) terintegrasi langsung dengan GitHub Releases API dan verifikasi checksum **SHA-256**.

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
  - Jendela **Histogram**, **Kurva**, **Info / Header FITS**, **Console Log**, serta menu **Help** (**Check for Updates**, **Report an Issue**, **About HILALONE**) yang terintegrasi dengan GitHub Releases.
  - Dukungan dua tema antarmuka: **Standard Dark Theme** dan **Night Vision Red Theme** beserta aset branding resmi.

---

## Struktur Proyek

```text
HILALONE/
├─ assets/
│  ├─ branding/           # Ikon ringkas, ikon (.ico), dan logo lengkap Standard / Night Vision Red
│  └─ hilalone-icons/     # Paket sumber resmi ikon & logo (SVG, PNG, ICO, Web)
├─ docs/                  # Dokumen spesifikasi, roadmap, gambaran proyek, & laporan audit
├─ hooks/                 # Hook PyInstaller kustom (astropy)
├─ src/hilalone/
│  ├─ core/logging/       # Sistem Scientific Processing Log terpusat (.log, .jsonl, filter, session)
│  ├─ gui/                # Antarmuka PySide6, viewer, panel, dialog, worker thread
│  ├─ input_manager/      # Adapter pembacaaan FITS, TIFF, RAW, SER, Video, sequence manager
│  ├─ output_manager/     # Penulis hasil linear & visual terpisah + riwayat pemrosesan
│  ├─ processing/         # Pipeline otomatis, stacking, flat calibration, background, stretch
│  ├─ updates/            # Pemeriksa pembaruan GitHub Releases, verifikasi SHA-256 & worker
│  └─ main.py             # Entry point aplikasi desktop
├─ tests/                 # Pengujian unit & UI (pytest) menggunakan data sintetis
├─ HILALONE.spec          # Konfigurasi build Windows executable (PyInstaller ONE-DIR)
├─ HILALONE.iss           # Skrip Windows Installer (Inno Setup 7)
├─ build_windows.bat      # Otomasi build Windows executable ke dist\HILALONE\
├─ build_installer.bat    # Otomasi kompilasi Windows installer ke release\HILALONE_Setup.exe
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

Hasil build `ONE-DIR` tersedia di `dist\HILALONE\HILALONE.exe` (serta peluncur `HILALONE_Diagnostic.bat` untuk mode diagnostik/console).

Untuk membuat Windows Installer (`release\HILALONE_Setup.exe`) menggunakan **Inno Setup 7** setelah `dist\HILALONE` siap:

```bat
build_installer.bat
```

Dokumentasi lengkap proses build, uji distribusi bersih, dan pembuatan installer Inno Setup 7 ([HILALONE.iss](HILALONE.iss)) dapat dibaca di [BUILD_README.md](BUILD_README.md).

---

## Dokumentasi Terkait

- [AGENTS.md](AGENTS.md) — Aturan tetap arsitektur dan batasan ilmiah MVP 1.0
- [docs/project_overview.md](docs/project_overview.md) — Arsitektur teknis dan alur pipeline
- [docs/software_requirements.md](docs/software_requirements.md) — Spesifikasi kebutuhan fungsional & non-fungsional
- [docs/development_roadmap.md](docs/development_roadmap.md) — Tahapan pengembangan MVP 1.0
- [docs/HILALONE_MVP1_QUALITY_AUDIT.md](docs/HILALONE_MVP1_QUALITY_AUDIT.md) — Audit kualitas dan validasi ilmiah
- [docs/HILALONE_LOGGING_AUDIT.md](docs/HILALONE_LOGGING_AUDIT.md) — Audit sistem logging & rancangan arsitektur Console Log
- [docs/HILALONE_LOGGING_STANDARD.md](docs/HILALONE_LOGGING_STANDARD.md) — Standar format Scientific Processing Log & Console System
- [docs/HILALONE_PROCESSING_REPORT_STANDARD.md](docs/HILALONE_PROCESSING_REPORT_STANDARD.md) — Standar Scientific Processing Timeline & Report Schema v2.0
- [docs/update_and_release_guide.md](docs/update_and_release_guide.md) — Arsitektur sistem pembaruan desktop & checklist rilis developer
- [BUILD_README.md](BUILD_README.md) — Panduan build executable Windows dan installer
