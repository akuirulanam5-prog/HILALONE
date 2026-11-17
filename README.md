# HILALONE — Automated Hilal Image Processing

**HILALONE** (v1.1.2) adalah aplikasi desktop Windows berbasis Python dan PySide6 untuk pengolahan citra pengamatan hilal dan bulan sabit muda secara otomatis, ilmiah, dan deterministik dengan prinsip *"Enhance the Signal, Never Invent the Signal"*.

---

## Apa yang Baru di v1.1.2 (Release Highlights)

1. **Professional Scientific Processing Log & Console System (`src/hilalone/core/logging/`)**:
   - Arsitektur logging ilmiah terpusat dengan **Application Session ID (`SES-...`)** dan **Processing Run ID (`RUN-...`)** unik di setiap eksekusi pipeline/stacking.
   - Pencatatan terstruktur dari 17 modul ilmiah (`SYSTEM`, `SESSION`, `INPUT`, `SEQUENCE`, `VALIDATION`, `CALIBRATION`, `FLAT`, `STACKING`, `BACKGROUND`, `ENHANCEMENT`, `HISTOGRAM`, `CURVE`, `DISPLAY`, `OUTPUT`, `VIEWER`, `LOGGING`, `EXPORT`, `UPDATE`, `HELP`, `ERROR`).
   - Penyimpanan log permanen otomatis di `%LOCALAPPDATA%\HILALONE\Logs\` dalam format `.log` (manusia) dan `.jsonl` (terstruktur dengan sanitasi kredensial otomatis) beserta rotasi arsip ukuran 5 MB tanpa penghapusan diam-diam.
2. **Tiga Mode Detail Fungsional (`Normal`, `Verbose`, `Debug`)**:
   - **Normal**: Ringkasan bersih tahapan utama, kompatibilitas frame, progres terukur, lokasi output, dan blok `PROCESSING SUMMARY`.
   - **Verbose**: Rincian parameter ilmiah lengkap (header FITS, statistik Master Flat & rumus normalisasi, parameter sigma-clipping/bobot kualitas stacking, sampel model background, CLAHE tile/clip limit, parameter stretch histogram, dan titik kontrol kurva).
   - **Debug**: Diagnostik teknis internal (`[DEBUG]`) mencakup dimensi array internal, alokasi strip memori, thread eksekusi, serta verifikasi ukuran byte berkas hasil di disk.
3. **Standardisasi Format Durasi (`Duration: 0.00 s`) & Penyempurnaan UI Console**:
   - Seluruh durasi proses yang ditampilkan ke pengguna distandardisasi ke format `Duration: 0.00 s`, sedangkan `.jsonl` mempertahankan nilai numerik presisi penuh `duration_ms`.
   - Perbaikan tata letak responsif tombol `Auto-scroll: ON` / `OFF` berbasis metrik font tebal (`QFontMetrics`) agar tidak pernah terpotong pada ukuran jendela kecil maupun tema **Standard Dark** / **Night Vision Red**.
   - **Export Visible** (`HILALONE_Log_Visible_YYYYMMDD_HHMMSS.log`) dan **Export Complete Log** (`HILALONE_Log_Complete_YYYYMMDD_HHMMSS.log`) kini otomatis mengarah ke **folder sumber citra aktif** (atau fallback ke folder log HILALONE jika belum ada citra yang dibuka) dengan proteksi konfirmasi overwrite.
4. **Desktop Auto-Update System & Pembaruan Branding (v1.1.0 – v1.1.2)**:
   - Menu **Help** (**Check for Updates...**, **Automatic Update Check**, **Report an Issue...**, **About HILALONE...**) terintegrasi langsung dengan GitHub Releases API dan verifikasi checksum **SHA-256**.
   - Pembaruan paket ikon & logo resmi resolusi tinggi untuk **Standard Dark** dan **Night Vision Red**.

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
- [docs/update_and_release_guide.md](docs/update_and_release_guide.md) — Arsitektur sistem pembaruan desktop & checklist rilis developer
- [BUILD_README.md](BUILD_README.md) — Panduan build executable Windows dan installer
