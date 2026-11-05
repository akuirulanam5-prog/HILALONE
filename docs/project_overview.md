# HILALONE – Project Overview

**HILALONE** = *Automated Hilal Image Processing*. Aplikasi desktop Windows untuk mengolah citra pengamatan hilal secara otomatis: pengguna memasukkan foto/video, memilih level (Basic/Medium/High), menekan satu tombol, lalu mendapat hasil olahan.

## 1. Tujuan
Menyediakan pipeline pengolahan citra hilal yang **jujur secara ilmiah** (tidak memalsukan data), **dapat diulang**, dan **mudah dipakai pemula**.

## 2. Ruang Lingkup MVP 1.0
**Termasuk:** input (gambar tunggal, urutan gambar, video), validasi, konversi, flat-field opsional, stacking (multi-frame), background extraction, enhancement, histogram transformation, ekspor.

**Tidak termasuk (jangan dikembangkan):** deteksi hilal otomatis, analisis kuantitatif, AI, klasifikasi hilal.

**Larangan teknis:** tanpa registration/alignment, tanpa KOMBAT, tanpa noise reduction, tanpa smoothing/sharpening otomatis, tanpa dark/bias.

## 3. Arsitektur Teknis

Empat lapisan terpisah (supaya mudah diuji dan diganti):

```
┌─────────────────────────────────────────────┐
│ GUI (PySide6)  – tampilan, tombol, preview  │
└───────────────┬─────────────────────────────┘
                │ memanggil lewat "Controller"/worker thread
┌───────────────▼─────────────────────────────┐
│ Pipeline Orchestrator – merangkai langkah   │
│  sesuai profil (Basic/Medium/High)          │
└───┬──────────────┬──────────────┬───────────┘
    │              │              │
┌───▼────┐   ┌─────▼──────────┐  ┌▼───────────┐
│ Input  │   │ Processing     │  │ Output     │
│ Manager│   │ Engine         │  │ Manager    │
└────────┘   └────────────────┘  └────────────┘
```

### Struktur folder yang diusulkan
```
Hilalone/
├─ AGENTS.md
├─ docs/
├─ src/hilalone/
│  ├─ core/            # tipe data: ImageData, FrameStack, ProcessingResult, Profile
│  ├─ input_manager/   # adapter per format + validator + kompatibilitas
│  │   └─ adapters/    # fits.py, tiff_png_jpeg.py, raw.py, video.py
│  ├─ processing/
│  │   ├─ calibration/ # flat_field.py
│  │   ├─ stacking/    # mean.py, sigma_clip.py, robust_weighted.py
│  │   ├─ background/  # polynomial.py, rbf.py, robust_auto.py, safeguards.py
│  │   ├─ enhancement/ # global_contrast.py, clahe.py, adaptive.py
│  │   ├─ stretch/     # mtf.py, asinh.py, ght.py
│  │   └─ profiles.py  # definisi Basic/Medium/High
│  ├─ pipeline/        # single_image.py, multi_image.py
│  ├─ output_manager/  # writer linear & visual, laporan/log
│  └─ gui/             # main_window, widgets, workers
├─ tests/
└─ pyproject.toml / requirements.txt
```

### Penjelasan istilah (untuk pemula)
- **Modul**: satu file/folder Python dengan tugas tunggal.
- **Adapter**: "penerjemah" format; semua format dibaca menjadi satu bentuk data standar sehingga format baru cukup menambah satu adapter.
- **Linear data**: data piksel yang nilainya sebanding dengan cahaya asli. Harus disimpan sebelum di-stretch.
- **Stretch/histogram transformation**: pengubahan kecerahan agar objek redup terlihat; hanya untuk tampilan.
- **Worker thread**: proses di latar belakang agar GUI tidak membeku.

## 4. Alur Pipeline

**Single image:** Import & validasi → Smart conversion (ke float32 linear) → Flat (opsional) → Background extraction → Enhancement → Histogram transformation → Ekspor (linear + visual).

**Multi-image/video:** Import & validasi → Konversi / ekstraksi frame → **Cek kompatibilitas** (ukuran, orientasi, stabilitas posisi) → Flat (opsional) → **Stacking** → Background extraction → Enhancement → Histogram transformation → Ekspor.

## 5. Profil
| Aspek | Basic | Medium | High |
|---|---|---|---|
| Background | Polinomial derajat 1 | Polinomial 2 atau RBF | Estimasi robust otomatis |
| Stacking | Mean | Sigma-clipped mean | Robust berbobot kualitas |
| Enhancement | Kontras global | CLAHE terbatas | Kontras adaptif |
| Stretch | MTF otomatis | Asinh + MTF | GHT / adaptif |

## 6. Keputusan Desain Kunci
1. **Data internal float32, rentang 0–1 atau satuan asli** – menghindari kehilangan presisi saat berhitung. Bentuk array: mono `(H, W)`, RGB `(H, W, 3)`.
2. **File sumber read-only** – input tidak pernah dibuka dalam mode tulis; output ke folder terpisah.
3. **Dua keluaran terpisah**: `*_linear` (FITS/TIFF 16/32-bit) dan `*_visual` (PNG/TIFF 8/16-bit).
4. **Tidak ada alignment otomatis** – bila frame tidak cocok, aplikasi memperingatkan dan pengguna memutuskan.
5. **Log proses + metadata** (parameter, versi, hash input) disimpan di samping hasil agar dapat direproduksi.
6. **Profil sebagai konfigurasi data**, bukan percabangan `if` tersebar.

7. **Jenis citra dipertahankan** – mono tetap mono (H×W), RGB tetap RGB (H×W×3); tidak ada konversi ke grayscale. Enhancement dan stretch pada RGB bersifat *luminance-aware* (dihitung dari luminans, diterapkan dengan menjaga rasio warna). Sequence stacking harus seragam (dimensi dan jumlah kanal); campuran mono/RGB ditolak.
8. **Stabilitas posisi = pengukuran saja** – translasi (dx, dy) tiap frame terhadap frame referensi; ambang awal 1 piksel. Di atas ambang → peringatan; pengukuran tak andal → `INDETERMINATE` + peringatan. Tidak ada penggeseran/alignment, dan tidak ada frame hilang tanpa catatan.

## 7. Dependency Rencana

Interpreter proyek: **Python 3.10.11 (64-bit)**. Versi tiap library dipilih yang kompatibel dengan Python 3.10 (beberapa rilis terbaru NumPy/Astropy mensyaratkan Python ≥ 3.11, sehingga versi dikunci dan diperiksa sebelum dipasang). Fungsi tiap library:
| Library | Fungsi |
|---|---|
| PySide6 | Membuat jendela/tombol/preview |
| NumPy | Array angka untuk piksel |
| OpenCV (`opencv-python-headless`) | Operasi citra (CLAHE, resize, I/O PNG/JPEG/TIFF) |
| Astropy | Baca/tulis FITS + header |
| rawpy | Membaca RAW kamera (via LibRaw) |
| PyAV | Dekode video tanpa memasang FFmpeg terpisah |
| SciPy *(usulan, perlu persetujuan)* | RBF interpolation, statistik robust |
| pytest *(pengembangan)* | Pengujian otomatis |

> SciPy tidak ada dalam daftar awal Anda; ditandai sebagai **usulan** karena RBF background lebih andal memakai `scipy.interpolate`. Tidak akan dipasang tanpa persetujuan.

