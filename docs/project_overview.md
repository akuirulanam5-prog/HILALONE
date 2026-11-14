# HILALONE – Project Overview

**HILALONE** = *Automated Hilal Image Processing*. Aplikasi desktop Windows untuk mengolah citra pengamatan hilal secara otomatis: pengguna memasukkan foto/video, memilih level (Basic/Medium/High), menekan satu tombol, lalu mendapat hasil olahan.

> **Catatan Sinkronisasi Dokumentasi (Review 14 November 2026):** Dokumen ini diselaraskan dengan implementasi aktual `HILALONE v1.0.0` (Python `3.10.11`, PySide6 `6.12.0`), sambil mempertahankan konteks desain dan riwayat keputusan arsitektur awal. Dokumen normatif [AGENTS.md](../AGENTS.md) dan [software_requirements.md](software_requirements.md) tidak diubah pada task sinkronisasi ini.

## 1. Tujuan
Menyediakan pipeline pengolahan citra hilal yang **jujur secara ilmiah** (tidak memalsukan data), **dapat diulang**, dan **mudah dipakai pemula**.

## 2. Ruang Lingkup MVP 1.0
**Termasuk (Implementasi Aktual `v1.0.0`):**
- Input: gambar tunggal (`FITS`, `TIFF`, `RAW`, `PNG`, `JPEG`, `BMP`), urutan banyak gambar/folder (*sequence*), video kontainer (`AVI`, `MP4`, `MOV`), serta rekaman video astronomi `.SER`.
- Pemrosesan inti: validasi format & metadata, smart conversion ke `float32`, flat-field calibration opsional, stacking (multi-frame), background extraction, enhancement, histogram transformation, serta ekspor linear & visual terpisah beserta riwayat proses.
- Fitur pendukung GUI desktop `v1.0.0`: viewer interaktif (zoom/pan/loupe/rotate/flip/mode before-after & negatif), panel/dialog *Histogram & Statistics*, *Curves Adjustment* (PCHIP), *Image Information / FITS Header Editor*, *Console / Processing Log*, serta tema *Standard Dark* dan *Night Vision Red*.

**Tidak termasuk (jangan dikembangkan):** deteksi hilal otomatis, analisis kuantitatif, AI, klasifikasi hilal.

**Larangan teknis:** tanpa registration/alignment, tanpa KOMBAT, tanpa noise reduction, tanpa smoothing/sharpening otomatis, tanpa dark/bias.

## 3. Arsitektur Teknis

Empat modul utama yang terpisah tanggung jawabnya (supaya mudah diuji dan diganti):

```
┌──────────────────────────────────────────────────────────┐
│ GUI Desktop (PySide6) – tampilan, toolbar, accordion,    │
│ viewer, histogram/curves/info dialog, worker threads     │
└────────────────────────────┬─────────────────────────────┘
                             │ memanggil lewat worker thread
┌────────────────────────────▼─────────────────────────────┐
│ Processing & Orchestrator (src/hilalone/processing/)     │
│ – ProcessingPipelineOrchestrator, UnifiedProfileConfig   │
│   background, enhancement, histogram & stacking engine   │
└───────┬──────────────────────────┬───────────────────────┘
        │                          │
┌───────▼────────┐        ┌────────▼───────────┐
│ Input Manager  │        │ Output Manager     │
│ Adapters &     │        │ Writer linear,     │
│ Sequence       │        │ visual & riwayat   │
└────────────────┘        └────────────────────┘
```

### Struktur Folder Aktual (`v1.0.0`)

> **Catatan historis desain awal:** Pada rancangan awal, tipe data dan orchestrator direncanakan berada di folder terpisah `src/hilalone/core/` dan `src/hilalone/pipeline/` (adapter gambar sempat disebut `tiff_png_jpeg.py`), dengan nama simbol konsep seperti `ImageData`, `FrameStack`, `ProcessingResult`, `Profile`, dan `ProcessingPipeline`. Pada implementasi aktual `v1.0.0`, tipe data dan orchestrator ditempatkan langsung di dalam masing-masing paket domain memakai simbol aktual (`ImageInfo` & `LoadedImage` di `input_manager/image_reader.py`, `SequenceFrameEntry` & `SequenceCompatibilityReport` di `input_manager/models.py`, `PipelineResult` & `ProcessingProfile` di `processing/processing_models.py`, `UnifiedProfileConfig` di `processing/profile_manager.py`, `ProcessingPipelineOrchestrator` di `processing/processing_pipeline.py`, serta `StackingResult` & `AutomaticStackingEngine` di `processing/stacking/`), dan format `.SER` memiliki adapter tersendiri (`ser_reader.py`).

```
HILALONE/
├─ AGENTS.md                       # Aturan tetap proyek (normatif, tidak diubah)
├─ README.md / BUILD_README.md     # Panduan rilis & panduan build Windows
├─ docs/                           # Dokumentasi proyek, SRS, roadmap, audit
├─ assets/branding/                # Ikon & aset visual resmi Dark / Night Vision
├─ hooks/                          # PyInstaller runtime/bundle hook (hook-astropy.py)
├─ src/hilalone/
│  ├─ __init__.py / __main__.py    # Inisialisasi paket & entry point modul
│  ├─ main.py / _bundle_verify.py  # Entry point GUI (--diagnostic, --bundle-verify)
│  ├─ input_manager/               # Reader terpadu, preview builder & sequence manager
│  │   ├─ models.py                # SequenceFrameEntry, SequenceCompatibilityReport, FrameStatus, InputMode
│  │   ├─ image_reader.py          # ImageInfo, LoadedImage, read_image & dispatcher format
│  │   ├─ preview_builder.py       # Pembuatan preview layar 8-bit terpisah dari float32
│  │   ├─ sequence_manager.py      # Manajemen sequence, sorting, lazy loading & validasi dasar
│  │   └─ adapters/                # fits_reader.py, tiff_reader.py, raw_reader.py,
│  │                               # ser_reader.py, video_reader.py
│  ├─ processing/                  # Pipeline, profil, dan engine pemrosesan ilmiah
│  │   ├─ processing_models.py     # Konfigurasi & PipelineResult (float32 linear vs display)
│  │   ├─ profile_manager.py       # UnifiedProfileConfig BASIC, MEDIUM, HIGH + kustomisasi
│  │   ├─ processing_pipeline.py   # ProcessingPipelineOrchestrator (single-image & sequence)
│  │   ├─ processing_history.py    # Pencatatan metadata, parameter & header FITS riwayat
│  │   ├─ background_engine.py     # Polinomial, TPS RBF, Auto Robust RBF & safeguard ROI
│  │   ├─ enhancement_engine.py    # CLAHE mono & RGB luminance-aware ratio-preserving
│  │   ├─ histogram_engine.py      # Linear MTF, Asinh MTF, Adaptive Asinh MTF, GHS MTF
│  │   └─ stacking/                # AutomaticStackingEngine (engine.py), flat_calibration.py,
│  │                               # models.py (StackingResult), validator.py
│  ├─ output_manager/              # pipeline_writer.py, stacking_writer.py (anti-overwrite)
│  └─ gui/                         # main_window.py, image_viewer.py, top_panels.py,
│                                  # accordion.py, console_panel.py, curves_window.py,
│                                  # histogram_window.py, info_dialog.py, styles.py,
│                                  # state_manager.py, resources.py, icons.py,
│                                  # pipeline_worker.py, stacking_worker.py
├─ tests/                          # 18 berkas test_*.py + conftest.py (228 kasus runtime)
├─ pyproject.toml                  # Konfigurasi pytest (pythonpath=src, testpaths=tests)
├─ requirements*.txt               # requirements.txt, requirements-runtime.txt, requirements-build.txt
└─ HILALONE.spec / HILALONE.iss    # Konfigurasi PyInstaller & Inno Setup 7 (+ skrip .bat Windows)
```

### Penjelasan istilah (untuk pemula)
- **Modul**: satu file/folder Python dengan tugas tunggal.
- **Adapter**: "penerjemah" format; semua format dibaca menjadi satu bentuk data standar sehingga format baru cukup menambah satu adapter.
- **Linear data**: data piksel yang nilainya sebanding dengan cahaya asli. Harus disimpan sebelum di-stretch.
- **Stretch/histogram transformation**: pengubahan kecerahan agar objek redup terlihat; hanya untuk tampilan.
- **Worker thread**: proses di latar belakang agar GUI tidak membeku.

## 4. Alur Pipeline

**Single image:** Import & validasi → Smart conversion (ke float32 linear) → Flat (opsional) → Background extraction → Enhancement → Histogram transformation → Ekspor (linear + visual).

**Multi-image/video/SER:** Import & validasi → Konversi / ekstraksi frame → **Cek kompatibilitas** (ukuran, jumlah kanal, metadata/flat) → Flat (opsional) → **Stacking** → Background extraction → Enhancement → Histogram transformation → Ekspor.

> **Stabilitas posisi (`IMPLEMENTATION DEVIATION — PENDING MAINTAINER CONFIRMATION`):** Pada implementasi `v1.0.0`, fungsi pembacaan translasi tersedia di validator, tetapi gerbang cek stabilitas posisi pada jalur utama stacking tidak dijalankan secara bawaan (`check_position_stability=False` / `"position_stability_precheck": "DISABLED"`). Rincian deviasi terhadap dokumen normatif dijelaskan pada Bagian 6 poin 8.

## 5. Profil
Tabel di bawah merangkum konfigurasi bawaan pada [profile_manager.py](../src/hilalone/processing/profile_manager.py) (*beserta perbandingan catatan rancangan awal*):

| Aspek | Basic | Medium | High |
|---|---|---|---|
| Background | Polinomial derajat 1 (`POLYNOMIAL_DEG_1`) | Polinomial derajat 2 (`POLYNOMIAL_DEG_2`; *`TPS_RBF` juga tersedia*) | Estimasi robust otomatis (`AUTO_ROBUST_RBF`) |
| Stacking | Arithmetic Mean streaming (`ARITHMETIC_MEAN`) | Sigma-clipped mean (`SIGMA_CLIPPED_MEAN`) | Robust berbobot kualitas (`QUALITY_WEIGHTED_ROBUST`) |
| Enhancement | CLAHE konservatif terbatas (`clip_limit=0.008`, tile `6×6`) *(rancangan awal: kontras global)* | CLAHE terbatas (`clip_limit=0.014`, tile `8×8`) | CLAHE adaptif (`clip_limit=0.018`, tile `10×10`, `adaptive_parameters=True`) |
| Stretch | Linear MTF otomatis (`LINEAR_MTF`) | Asinh + MTF (`ASINH_MTF`) | Adaptive Asinh + MTF (`ADAPTIVE_ASINH_MTF`) sebagai bawaan; *`GHS_MTF` tersedia lewat kustomisasi lanjutan* |

*(Catatan lintas dokumen: dokumen normatif [AGENTS.md](../AGENTS.md) §8 dan [software_requirements.md](software_requirements.md) tidak diubah pada task ini dan masih menyebut rumusan awal "kontras global" pada Basic serta "GHT/adaptif" pada High.)*

## 6. Keputusan Desain Kunci
1. **Data internal float32, rentang 0–1 atau satuan asli** – menghindari kehilangan presisi saat berhitung. Bentuk array: mono `(H, W)`, RGB `(H, W, 3)`.
2. **File sumber read-only** – input tidak pernah dibuka dalam mode tulis; output ke folder terpisah.
3. **Dua keluaran terpisah**: `*_linear` (FITS/TIFF 16/32-bit) dan `*_visual` (PNG/TIFF 8/16-bit).
4. **Tidak ada alignment otomatis** – bila frame tidak cocok (ukuran/kanal), aplikasi memperingatkan dan meminta keputusan pengguna (`StackingConfirmationRequiredError` / pengecualian eksplisit).
5. **Log proses + metadata** (parameter, versi, riwayat FITS/JSON) disimpan di samping hasil agar dapat direproduksi.
6. **Profil sebagai konfigurasi data**, bukan percabangan `if` tersebar.
7. **Jenis citra dipertahankan** – mono tetap mono (`H×W`), RGB tetap RGB (`H×W×3`); tidak ada konversi ke grayscale. Enhancement dan stretch pada RGB bersifat *luminance-aware* (`RGB_LUMINANCE_RATIO_PRESERVING` dengan bobot Rec.709 dan skala rasio warna `R:G:B`). Sequence stacking harus seragam (dimensi dan jumlah kanal); campuran mono/RGB ditolak.
8. **Stabilitas posisi** – **`IMPLEMENTATION DEVIATION — PENDING MAINTAINER CONFIRMATION`**:
   - **Persyaratan dalam dokumentasi normatif ([AGENTS.md](../AGENTS.md) §6 & [software_requirements.md](software_requirements.md) `FR-CP-03` s.d. `FR-CP-07`)**: sebelum stacking wajib mengukur pergeseran translasi `(dx, dy)` *read-only* terhadap frame referensi (ambang awal maksimum `1 piksel`), menghasilkan status `OK` / `MELEBIHI_AMBANG` / `INDETERMINATE`, memunculkan peringatan serta meminta keputusan pengguna, tanpa alignment otomatis dan tanpa membuang frame diam-diam.
   - **Implementasi aktual `v1.0.0`**: fungsi pengukuran *read-only* (`measure_frame_translation_readonly`, `measure_sequence_position_stability`, `PositionStabilityStatus`) tetap ada di [validator.py](../src/hilalone/processing/stacking/validator.py), namun [engine.py](../src/hilalone/processing/stacking/engine.py) memperlakukan `check_position_stability` sebagai parameter legasi dan melewati gerbang stabilitas posisi (`"Position stability precheck: DISABLED"`), serta `processing_pipeline.py`, `stacking_worker.py`, dan `main_window.py` menyetel `check_position_stability=False` (tercatat `"position_stability_precheck": "DISABLED"` pada `processing_history.py` dan diuji dalam kondisi nonaktif pada `tests/test_stacking_engine.py`).
   - **Keputusan yang menunggu persetujuan maintainer**: status nonaktif ini **belum ditetapkan sebagai keputusan desain permanen** dan menunggu keputusan maintainer apakah disahkan untuk `v1.0.0` atau diaktifkan/diselaraskan kembali di versi berikutnya.

## 7. Dependency Aktual (`v1.0.0`) & Riwayat Rencana Awal

Interpreter proyek: **Python 3.10.11 (64-bit)** pada virtual environment `.venv`. Seluruh versi library dikunci untuk kompatibilitas Python 3.10 pada [requirements.txt](../requirements.txt), [requirements-runtime.txt](../requirements-runtime.txt), dan [requirements-build.txt](../requirements-build.txt).

> **Catatan historis rencana awal:** Dokumen awal merencanakan `OpenCV (opencv-python-headless)` untuk CLAHE/operasi citra dan menandai `SciPy` sebagai *usulan, perlu persetujuan*. Dalam implementasi `v1.0.0`, **`OpenCV` (`cv2`) tidak pernah dipasang maupun diimpor** (`0` referensi di `src/`, `tests/`, dan `requirements*.txt`); sebagai gantinya fungsi pemrosesan dan interpolasi dijalankan menggunakan **`SciPy` (`scipy==1.15.3`)**, **`scikit-image` (`scikit-image==0.25.2`)**, dan **`Pillow` (`pillow==12.3.0`)**.

| Kategori | Library & Versi Terkunci | Bukti Berkas & Fungsi Utama |
|---|---|---|
| **Runtime dependencies** *(diimpor langsung di `src/hilalone/`)* | `PySide6==6.12.0`, `numpy==2.2.6`, `scipy==1.15.3`, `scikit-image==0.25.2`, `astropy==6.1.7`, `tifffile==2025.5.10`, `rawpy==0.27.1`, `av==17.1.0`, `pillow==12.3.0` | Delapan paket pertama tercantum di [requirements.txt](../requirements.txt) & [requirements-runtime.txt](../requirements-runtime.txt) untuk GUI Qt6, array `float32`, interpolasi RBF/PCHIP, CLAHE (`equalize_adapthist`), FITS, TIFF ilmiah, RAW kamera (LibRaw), dan video kontainer (PyAV). **`pillow==12.3.0`** adalah **runtime dependency aktif** karena diimpor langsung di [background_engine.py:286](../src/hilalone/processing/background_engine.py#L286) (`from PIL import Image as _PILImage` untuk resize bicubic TPS RBF) serta [\_bundle\_verify.py:16](../src/hilalone/_bundle_verify.py#L16) dan dibundel di [HILALONE.spec:30-33](../HILALONE.spec#L30-L33). Pada [requirements-runtime.txt](../requirements-runtime.txt) (lock runtime produksi & build `.exe`), `pillow==12.3.0` dikunci eksplisit di kelompok pendukung runtime, sedangkan [requirements.txt](../requirements.txt) (daftar instalasi dev/test `.venv`) belum mencantumkannya secara eksplisit dan terpasang sebagai dependensi transitif runtime di `.venv` *(tidak diubah pada task dokumentasi ini)*. |
| **Development / test dependencies** | `pytest==9.2.0` | Tercatat di [requirements.txt](../requirements.txt) untuk menjalankan test suite; tidak dimasukkan ke [requirements-runtime.txt](../requirements-runtime.txt) dan dikecualikan di [HILALONE.spec](../HILALONE.spec). |
| **Build dependencies** | `pyinstaller==6.22.3`, `pyinstaller-hooks-contrib==2026.10` *(plus Inno Setup 7 melalui [HILALONE.iss](../HILALONE.iss))* | Tercatat di [requirements-build.txt](../requirements-build.txt) (yang mengimpor `-r requirements-runtime.txt`) untuk mengompilasi bundel ONE-DIR `HILALONE.exe` dan installer `HILALONE_Setup.exe`. |
| **Transitive dependencies** | **Runtime transitif** ([requirements-runtime.txt](../requirements-runtime.txt)): `PySide6_Addons==6.12.0`, `PySide6_Essentials==6.12.0`, `shiboken6==6.12.0`, `astropy-iers-data==0.2026.10.19.0.52.1`, `pyerfa==2.0.1.5`, `ImageIO==2.38.0`, `lazy_loader==0.6`, `networkx==3.4.2`, `packaging==26.3`, `PyYAML==6.0.3`<br>**Build transitif** ([requirements-build.txt](../requirements-build.txt)): `altgraph==0.17.5`, `pefile==2024.8.26`, `pywin32-ctypes==0.2.3` | Dependensi turunan otomatis dari `PySide6`, `astropy`, `scikit-image`, dan `pyinstaller` *(tidak diimpor langsung di `src/hilalone/`, kecuali konfigurasi bundling data/hiddenimports `astropy-iers-data` dan `erfa` di [HILALONE.spec](../HILALONE.spec) & [hooks/hook-astropy.py](../hooks/hook-astropy.py))*. |

## 8. Baseline Test Suite Aktual (`.venv`)
- **Lingkungan verifikasi:** Python `3.10.11`, PySide6 `6.12.0`, `.venv` terpasang dari [requirements.txt](../requirements.txt), mode `QT_QPA_PLATFORM="offscreen"`.
- **Hasil pengujian pertama (`pytest -q`):** **`225 passed, 3 skipped`** dari **`228 test cases`** dalam **`61.62 seconds`** *(dikonfirmasi ulang via `pytest -rs -q` dalam `51.63s` tanpa output warnings summary)*.
- **Penjelasan 3 test dilewati (*skipped*):** ketiga test tersebut bukan kegagalan, melainkan test integrasi opsional yang mencari berkas sampel observasi eksternal lokal yang tidak tersedia di repositori (`tests/test_flat_calibration.py`, `tests/test_raw_reader.py`, dan `tests/test_tiff_reader.py` ke direktori `C:\Astrofotografer`).
- **Catatan batas pengujian:** hasil di atas adalah baseline test suite fungsional/offscreen; pengukuran **benchmark performa khusus** (waktu median & memori puncak per metode) serta **validasi ilmiah data hilal nyata** belum dicatat dan berada pada status review audit terpisah (lihat [HILALONE_MVP1_QUALITY_AUDIT.md](HILALONE_MVP1_QUALITY_AUDIT.md)).

