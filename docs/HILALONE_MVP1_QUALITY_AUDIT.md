# LAPORAN AUDIT KUALITAS PERANGKAT LUNAK, UI/UX & VALIDASI ILMIAH
# PROYEK HILALONE — FINALISASI DAN PENINGKATAN KUALITAS MVP 1.0

**Dokumen**: `docs/HILALONE_MVP1_QUALITY_AUDIT.md`
**Aplikasi**: HILALONE (Automated Astronomical & Crescent Moon Image Processing)
**Lingkungan**: Python 3.10.11 (64-bit), PySide6 6.12.0 *(tercatat 6.8+ pada audit awal)*, NumPy 2.2.6, Astropy 6.1.7, SciPy 1.15.3, scikit-image 0.25.2, rawpy 0.27.1, PyAV 17.1.0, tifffile 2025.5.10, Pillow 12.3.0
**Prinsip Utama**: *"Enhance the Signal, Never Invent the Signal"*
**Tanggal Audit**: 12 November 2026
**Tanggal Review Status**: 14 November 2026 *(lihat Bagian 5 untuk hasil verifikasi pasca-audit)*

---

## 1. Ringkasan Eksekutif & Kondisi Aktual

Aplikasi HILALONE telah mengimplementasikan seluruh pilar inti MVP 1.0 sesuai batasan arsitektur ilmiah (`AGENTS.md`):
1. **Input Readers & Sequence Manager**:
   - Mendukung berkas gambar tunggal (FITS, TIFF, RAW, PNG, JPEG), sequence banyak gambar, direktori folder, berkas video (AVI, MP4, MOV), dan rekaman video astronomi murni (.SER).
   - Penguraian metadata komprehensif (header FITS terstruktur, EXIF Camera RAW, trailer timestamp SER, container video AV).
   - Seluruh pembacaan berkas sumber bersifat *read-only* dengan proteksi integritas SHA-256 dan penutupan handle file yang disiplin.
2. **Processing Pipeline & Stacking Engine**:
   - Tiga profil pemrosesan terintegrasi: `BASIC` (Mean streaming, Background Polynomial Deg 1, Linear MTF), `MEDIUM` (Sigma-Clipped Mean Median & MAD, Polynomial Deg 2 / TPS RBF, CLAHE, Asinh MTF), dan `HIGH` (Quality-Weighted Robust Stacking, Auto Robust Mesh RBF, Adaptive Asinh MTF).
   - Pemrosesan *bounded-memory strip* untuk sequence besar tanpa menghabiskan RAM.
   - Penolakan outlier dan pembobotan kualitas pada citra RGB dihitung pada kanal luminansi bersama (*luminance-aware*) untuk mencegah *color shift*.
   - Kalibrasi Flat-Field opsional dengan validasi dimensi, kanal, dan proteksi pembagian nol.
   - Pemisahan mutlak antara data master ilmiah linear (`float32`), hasil turunan nonlinear (`enhanced_result`), dan pratinjau visual (`display_result`).
3. **Antarmuka Pengguna (UI/UX) Desktop**:
   - Penataan antarmuka utama berbasis *Image Viewer* terluas di pusat layar dengan navigasi pan, zoom fit/100%/loupe, rotasi, dan flip.
   - Panel inspeksi kanan (*Right Sidebar*) menggunakan sistem **Collapsible Accordion** eksklusif dengan *Nested Accordions* bertingkat dan *dynamic summary badges*.
   - Jendela sekunder independen: *Image Information Dialog (FITS Header Editor)*, *Histogram Window & Statistics*, *Curves Adjustment Window*, *Console/Processing Log Panel*, dan *Flat Info Dialog*.
   - Dukungan tema *Standard Dark Theme* dan *Night Vision Red Theme* (palet merah monokromatik astronomi).

---

## 2. Inventarisasi Temuan Masalah & Tingkat Prioritas

Berdasarkan audit menyeluruh terhadap 10 aspek kualitas, ditemukan sejumlah poin yang perlu diperbaiki dan ditingkatkan:

| ID | Aspek | Komponen / Lokasi | Deskripsi Masalah | Prioritas |
|---|---|---|---|---|
| **ISSUE-01** | UI/UX & Astronomi | `src/hilalone/gui/top_panels.py:FrameListPanel` | Frame list tidak membedakan status visual antara frame Kompatibel, Inkompatibel, dan Error. Frame error tetap dapat tercentang secara default. | **P1 (High)** |
| **ISSUE-02** | Stabilitas & Log | `src/hilalone/gui/main_window.py:3790, 1154` & `histogram_window.py:601` | Blok `try-except` menangkap `Exception` dan mengeksekusi `pass` tanpa mencatat peringatan/galat ke `LogManager`. | **P1 (High)** |
| **ISSUE-03** | Performance & QA | `tests/` (modul baru) | Belum tersedianya modul performance benchmark terotomatisasi untuk mengukur durasi dan alokasi memori aktual sebelum dan sesudah optimasi. | **P1 (High)** |
| **ISSUE-04** | Kompatibilitas Qt6 | `image_viewer.py:242, 651, 664, 677` & `main_window.py:1586` | Penggunaan method usang `QImage.mirrored(bool, bool)` dan `QMouseEvent.pos()` yang memicu 19 `DeprecationWarning` di PySide6 6.8+. | **P2 (Medium)** |
| **ISSUE-05** | Responsivitas UI | `top_panels.py` & `main_window.py` | Tinggi kaku `setFixedHeight(145)` pada Top Panels dapat memotong ruang vertikal Image Viewer pada layar 1366×768 dengan Display Scaling 125%/150%. | **P2 (Medium)** |
| **ISSUE-06** | Aksesibilitas UI | `styles.py` | Kurangnya indikator fokus keyboard visual yang tegas (`:focus { outline: ... }`) pada kontrol antarmuka tombol, combobox, dan checkbox. | **P2 (Medium)** |
| **ISSUE-07** | Design System | `styles.py` | Nilai warna dan token desain tertanam langsung (*hardcoded strings*) dalam blok QSS besar tanpa struktur dataclass token terpusat. | **P2 (Medium)** |
| **ISSUE-08** | Terminologi Ilmiah | `top_panels.py` & `main_window.py` | Sebagian label numerik dan waktu belum menyertakan satuan metrik eksplisit (misal `s`, `ms`, `fps`, `ADU`). | **P2 (Medium)** |
| **ISSUE-09** | Polishing Visual | Dialog & Header | Detail spasi mikro (padding/margin) pada header tombol dialog sekunder agar selaras sempurna dengan 4px/8px grid system. | **P3 (Low)** |

> **Catatan Review 14 November 2026:** Tabel dan uraian pada Bagian 2–4 di bawah dipertahankan sesuai catatan audit awal (12 November 2026). Untuk status implementasi kode, cakupan unit test, bukti baseline runtime (`225 passed, 3 skipped`), serta rincian `ISSUE-09`, lihat **Bagian 5**.

---

## 3. Rincian Masalah, Bukti, Dampak, dan Rencana Perbaikan

### ISSUE-01: Pemisahan Status Frame List (Kompatibel, Inkompatibel, Error)
- **Lokasi**: `src/hilalone/gui/top_panels.py:FrameListPanel`
- **Kondisi Aktual**:
  Di `populate_sequence()`, teks item hanya ditulis `[{idx + 1:04d}] {entry.file_name}` dan seluruh frame langsung dicentang `Qt.CheckState.Checked`.
- **Bukti**:
  Master prompt Bagian V Aspek 3 & Bagian VIII Aspek 6 menegaskan:
  > *"Pastikan ada pemisahan yang benar antara: Frame aktif untuk dilihat, Frame terpilih untuk diproses, Frame kompatibel, dan Frame yang mengalami error. Jangan menyamakan keempat status tersebut."*
- **Dampak terhadap Pengguna**:
  Pengguna tidak mengetahui jika terdapat frame yang korup atau inkompatibel di dalam daftar tanpa memeriksa pesan validasi modal, dan frame yang rusak berisiko ikut tercentang.
- **Rekomendasi Perbaikan**:
  1. Sertakan badge status Bahasa Indonesia pada teks: `f"[{idx + 1:04d}] {entry.file_name}  [{entry.status_badge_indonesian()}]"`.
  2. Tambahkan warna foreground spesifik: merah muda `#f87171` untuk status ERROR, kuning kecokelatan `#facc15` untuk INCOMPATIBLE, dan teks normal `#e2e8f0` untuk COMPATIBLE.
  3. Frame dengan status ERROR tidak dicentang secara default (*unchecked*).
  4. Berikan tooltip lengkap yang menampilkan `issues` dan `notes` saat mouse diarahkan ke item.
- **Cara Menguji**:
  Buka sequence dengan frame buatan yang sengaja dibuat korup atau berbeda dimensi, verifikasi badge status muncul jelas di list, frame error tidak dicentang, dan tooltip menampilkan detail masalah.

---

### ISSUE-02: Silent Exception Catching pada Area GUI dan Ekspor
- **Lokasi**:
  - `src/hilalone/gui/main_window.py:3790` (`_get_or_compute_preview_for_mode`)
  - `src/hilalone/gui/main_window.py:1154` (`_get_current_active_scientific_data`)
  - `src/hilalone/gui/histogram_window.py:601` (`_export_graph_png`)
- **Kondisi Aktual**:
  Eksepsi ditangkap dengan `except Exception: pass` tanpa pencatatan ke konsol log terpusat.
- **Bukti**:
  Aturan arsitektur Bagian III Aspek 1 nomor 6: *"Apakah ada error yang ditelan tanpa dilaporkan?"*
- **Dampak terhadap Pengguna**:
  Bila terjadi galat komputasi preview on-the-fly (misalnya out-of-memory pada citra raksasa), aplikasi diam-diam menampilkan citra asli tanpa memberitahu pengguna mengapa preview yang dipilih gagal dihitung.
- **Rekomendasi Perbaikan**:
  Teruskan detail kegagalan ke `self.log_manager.warning(...)` atau `self.log_manager.error(...)` sebelum mengembalikan fallback aman.
- **Cara Menguji**:
  Simulasikan kegagalan data pada kalkulasi preview dan periksa apakah entri galat tercatat secara kronologis di Console Log Panel.

---

### ISSUE-03: Performance Baseline & Pengukuran Benchmark Terstandarisasi
- **Lokasi**: Modul pengujian `tests/`
- **Kondisi Aktual**:
  Belum ada script benchmark terukur untuk mencatat waktu (detik) dan memori puncak (MB) pada pipeline stacking dan processing.
- **Bukti**:
  Aturan Bagian I nomor 10 dan Bagian IV: *"Jangan menjanjikan peningkatan kecepatan tanpa pengukuran... Catat ukuran input, jumlah frame, dimensi citra, tipe data, metode pemrosesan, waktu, dan memori menggunakan median."*
- **Dampak terhadap Pengguna**:
  Tidak adanya angka baseline ilmiah yang terdokumentasi untuk membuktikan komitmen efisiensi komputasi HILALONE.
- **Rekomendasi Perbaikan**:
  Buat modul benchmark independen `tests/test_performance_benchmarks.py` yang menguji algoritma Stacking (Basic, Medium, High), Background Extraction (Poly 1, Poly 2, TPS RBF), Image Enhancement (CLAHE), Histogram Transformation, dan Master Flat Normalization dengan pengukuran waktu median (`time.perf_counter()`) dan alokasi memori (`tracemalloc`).
- **Cara Menguji**:
  Jalankan benchmark melalui pytest dan catat hasilnya ke laporan akhir.

---

### ISSUE-04: Penggunaan API Usang PySide6 (Deprecation Warnings)
- **Lokasi**:
  - `src/hilalone/gui/image_viewer.py:242, 253` (`mirrored(True, False)` / `mirrored(False, True)`)
  - `src/hilalone/gui/main_window.py:1586, 1598` (`mirrored(...)`)
  - `src/hilalone/gui/image_viewer.py:651, 664, 677` (`event.pos()`)
  - `tests/test_image_viewer_toolbar.py:89, 99, 109` (`QMouseEvent(...)`)
- **Kondisi Aktual**:
  Tercatat 19 peringatan *DeprecationWarning* selama eksekusi pytest.
- **Bukti**:
  Log pytest: `Function: 'QImage.mirrored(bool, bool) const' is marked as deprecated` dan `Function: 'QMouseEvent.pos() const' is marked as deprecated`.
- **Dampak terhadap Pengguna**:
  Berpotensi terjadi *breaking change* pada update PySide6 berikutnya dan mencemari log pengujian.
- **Rekomendasi Perbaikan**:
  1. Gunakan transformasi modern `img.transformed(QTransform().scale(-1, 1))` untuk flip horizontal dan `img.transformed(QTransform().scale(1, -1))` untuk flip vertikal.
  2. Gunakan `event.position().toPoint()` untuk koordinat posisi mouse di PySide6 6.x.
  3. Perbarui konstruktor pengujian `QMouseEvent`.
- **Cara Menguji**:
  Jalankan seluruh test suite dan pastikan peringatan deprecation warning menjadi 0.

---

### ISSUE-05: Responsivitas Layout & Display Scaling
- **Lokasi**: `src/hilalone/gui/top_panels.py` & `src/hilalone/gui/main_window.py`
- **Kondisi Aktual**:
  `OpenImagePanel`, `FrameListPanel`, dan `ImageInfoPanel` memiliki `setFixedHeight(145)` kaku.
- **Bukti**:
  Bagian X Aspek 8: *"Hindari ukuran komponen yang ditentukan secara kaku sehingga memotong konten... Uji 1366 × 768, 1600 × 900, 1920 × 1080 dan Display Scaling 100%, 125%, 150%."*
- **Dampak terhadap Pengguna**:
  Pada resolusi layar 1366×768 dengan Display Scaling 125%/150%, tinggi tetap 145px menyita area vertikal yang cukup besar dari Image Viewer.
- **Rekomendasi Perbaikan**:
  Ganti `setFixedHeight(145)` menjadi batasan adaptif `setMinimumHeight(120)` dan `setMaximumHeight(160)` dengan size policy yang fleksibel, serta pastikan tombol dan teks di dalam panel tetap rapi dengan spasi elastis.
- **Cara Menguji**:
  Uji tampilan jendela pada ukuran resolusi 1366×768 dan pastikan Image Viewer tetap menjadi area dominan tanpa tombol terpotong.

---

### ISSUE-06: Aksesibilitas & Indikator Fokus Keyboard
- **Lokasi**: `src/hilalone/gui/styles.py`
- **Kondisi Aktual**:
  Gaya QSS saat ini belum menyertakan aturan spesifik `:focus` yang seragam untuk navigasi keyboard.
- **Bukti**:
  Bagian XI Aspek 9: *"Keyboard navigation, focus indicator, tab order, disabled state."*
- **Dampak terhadap Pengguna**:
  Navigasi menggunakan tombol `Tab` pada keyboard tidak memperlihatkan cincin fokus (*focus ring*) yang jelas, menyulitkan operator teleskop dalam kondisi minim cahaya.
- **Rekomendasi Perbaikan**:
  Tambahkan aturan `:focus` dengan border/outline `#38bdf8` (Dark Theme) dan `#ef4444` (Night Vision) pada `QPushButton`, `QComboBox`, `QCheckBox`, `QListWidget`, dan `QLineEdit`.
- **Cara Menguji**:
  Gunakan tombol `Tab` pada keyboard untuk berpindah antarkontrol dan amati kejelasan indikator fokus visual.

---

### ISSUE-07: Sentralisasi Token Desain (Design Tokens)
- **Lokasi**: `src/hilalone/gui/styles.py`
- **Kondisi Aktual**:
  Konstanta warna heksadesimal ditulis berulang kali di berbagai bagian string QSS.
- **Bukti**:
  Bagian VI Aspek 4: *"Buat design tokens terpusat untuk: Background, Surface, Elevated surface, Border, Primary text, Secondary text, Accent, Success, Warning, Error, Disabled."*
- **Dampak terhadap Pengguna**:
  Potensi ketidakkonsistenan warna sekunder atau status badge pada penambahan antarmuka baru.
- **Rekomendasi Perbaikan**:
  Definisikan dataclass `DesignTokens` untuk `DARK_THEME` dan `NIGHT_VISION_THEME` di `styles.py` sebagai sumber kebenaran tunggal (*single source of truth*) palet warna HILALONE.
- **Cara Menguji**:
  Periksa konsistensi seluruh kelas gaya antarmuka terhadap token terpusat.

---

### ISSUE-08: Label Satuan & Terminologi Astronomi Eksplisit
- **Lokasi**: `src/hilalone/gui/main_window.py` dan tabel metadata
- **Kondisi Aktual**:
  Sebagian nilai numerik pada tabel inspeksi FITS/Video belum menyertakan satuan metrik baku astronomi secara eksplisit.
- **Bukti**:
  Bagian VIII Aspek 6: *"Nama parameter harus benar. Satuan harus jelas. Definisi harus tepat... Bit depth tidak boleh disamakan dengan storage dtype. Timestamp jelaskan UTC vs lokal."*
- **Dampak terhadap Pengguna**:
  Pengguna pemula dapat salah menafsirkan angka eksposur atau frame rate jika tidak ada satuan.
- **Rekomendasi Perbaikan**:
  Pastikan setiap nilai numerik yang ditampilkan diformat dengan satuan yang jelas (misal: `1280 × 960 px`, `30.00 fps`, `20.00 s`, `uint16 storage / 12-bit sensor`).
- **Cara Menguji**:
  Buka berkas FITS, RAW, Video, dan SER; verifikasi seluruh label informasi memiliki satuan yang presisi dan jujur.

---

## 4. Jadwal Eksekusi Perbaikan (Implementation Roadmap)

Sesuai urutan prioritas pada Bagian XIV:

1. **PHASE 1**: Dokumentasi Audit Selesai (`docs/HILALONE_MVP1_QUALITY_AUDIT.md`) - **SELESAI**.
2. **PHASE 2 (Arsitektur & Stabilitas)**:
   - Eliminasi deprecation warnings Qt6 di `image_viewer.py`, `main_window.py`, dan tests.
   - Perbaikan penanganan exception dengan pencatatan terstruktur ke `LogManager`.
   - Pembuatan suite performance benchmark (`tests/test_performance_benchmarks.py`) untuk mengukur baseline waktu & memori.
3. **PHASE 3 (UI/UX Foundation & Design System)**:
   - Sentralisasi `DesignTokens` di `styles.py`.
   - Penerapan fokus keyboard (`:focus`) dan font Segoe UI / Consolas yang konsisten.
4. **PHASE 4 (Data Presentation & Frame List)**:
   - Perbaikan `FrameListPanel`: visualisasi status badge (Kompatibel / Inkompatibel / Error), warna status, proteksi uncheck frame error default, dan tooltip detail.
   - Peningkatan kejelasan satuan astronomi pada seluruh tabel dan card.
5. **PHASE 5 (Responsivitas & Accessibility)**:
   - Penyesuaian fleksibilitas ukuran Top Panels untuk resolusi 1366×768 s.d. 1440p dan Display Scaling 100%–150%.
6. **PHASE 6 (Final Validation & Benchmarking)**:
   - Eksekusi benchmark performa riil (waktu median, alokasi RAM).
   - Eksekusi regresi penuh seluruh test suite (215+ tests).
   - Penyusunan Laporan Akhir Penerimaan Kualitas.

> **Catatan Review 14 November 2026:** Status progres aktual untuk `PHASE 1`–`6` dan `ISSUE-01`–`09` didokumentasikan pada **Bagian 5** tanpa menghapus kronologi jadwal di atas.

---

## 5. Pembaruan Status Verifikasi Pasca-Audit (Review 14 November 2026)

Pembaruan ini menambahkan bukti kode, cakupan unit test, dan hasil eksekusi runtime aktual pada repositori `HILALONE v1.0.0` (branch `docs/sync-v1.0.0-documentation`) sambil mempertahankan seluruh catatan temuan awal tanggal 12 November 2026. Tidak ada temuan yang ditandai **`DONE FULL`** apabila masih terdapat celah pengujian, perbaikan parsial, atau metrik performa/validasi nyata yang belum diukur.

### 5.1 Hasil Pengujian Runtime Baseline Test Suite (`.venv`)

- **Lingkungan Pengujian:** Python `3.10.11` (64-bit), `.venv` dengan `requirements.txt` terpasang *(seluruh runtime lock tercatat di [requirements-runtime.txt](../requirements-runtime.txt), termasuk `pillow==12.3.0` sebagai runtime dependency)*, `PySide6 6.12.0`, git working tree bersih sebelum pembuatan branch `docs/sync-v1.0.0-documentation`.
- **Perintah & Hasil Aktual (Mesin Kontributor):**
  - Mode `QT_QPA_PLATFORM="offscreen"`, `.\.venv\Scripts\python.exe -m pytest -q`:
    **`225 passed, 3 skipped` (`228 test cases`) dalam `61.62 seconds` pada pengujian pertama**.
  - Konfirmasi ulang dengan `pytest -rs -q`: **`225 passed, 3 skipped` dalam `51.63 seconds`**, tanpa output *warnings summary* *(observasi baseline ini tidak diklaim sebagai nol `DeprecationWarning` secara mutlak karena validasi eksplisit `-W default::DeprecationWarning` / `-W error::DeprecationWarning` belum dijalankan)*.
- **Penjelasan 3 Test yang Dilewati (*Skipped* — Bukan Kegagalan):**
  Ketiga test yang berstatus *skipped* adalah test opsional untuk sampel observasi eksternal yang memang tidak disertakan dalam repositori:
  1. `tests/test_flat_calibration.py:755` (`test_flat_calibration_real_pal8_avi_files`): *"Berkas sampel nyata tidak ditemukan di sistem lokal."* (membutuhkan `C:\Astrofotografer\Stacking beta\bahan pak ahmad junaidi\flat.avi` & `moon.avi`).
  2. `tests/test_raw_reader.py:695` (`test_real_camera_raw_file_if_present`): *"Folder C:\Astrofotografer tidak ditemukan."* (membutuhkan berkas Camera RAW nyata lokal).
  3. `tests/test_tiff_reader.py:207` (`test_real_tes_tif_if_present`): *"Berkas tes.tif tidak tersedia di mesin ini."* (membutuhkan `C:\Astrofotografer\tes.tif`).
- **Pemisahan Baseline Test Suite vs Benchmark Performa Khusus (`ISSUE-03`):**
  - Hasil `225 passed, 3 skipped` membuktikan **baseline fungsional test suite (`offscreen`)** pada 18 berkas test (202 fungsi `def test_` statis / 228 test cases ter-ekspansi `parametrize`).
  - Meskipun ke-5 fungsi benchmark di [test_performance_benchmarks.py](../tests/test_performance_benchmarks.py) ikut lulus dalam `225 passed`, pengujian tersebut pada mode `-q` berjalan menggunakan citra sintetis kecil (`128×128` 6 frame untuk stacking; `256×256` untuk background, CLAHE, histogram, dan flat-field), hanya memvalidasi asersi `assert t_* > 0.0`, serta menahan keluaran `stdout`. Oleh karena itu, **angka durasi median (ms/s) dan alokasi RAM puncak (`tracemalloc` MB) belum diukur melalui sesi benchmark performa khusus (`-s`) dan tidak dikarang pada dokumen ini**.

### 5.2 Matriks Status Verifikasi 4 Lapis per Temuan (`ISSUE-01` s.d. `ISSUE-09`)

| ID | Status Review (14 Nov 2026) | Implementasi Kode | Unit Test & Celah Spesifik | Runtime & Validasi Nyata |
|---|---|---|---|---|
| **ISSUE-01** | `CODE IMPLEMENTED — UNIT TEST INCOMPLETE` | `FrameListPanel.populate_sequence` ([top_panels.py:183-224](../src/hilalone/gui/top_panels.py#L183-L224)) sudah menampilkan badge `[status]`, warna `#f87171` (ERROR), `#facc15` (INCOMPATIBLE), `#e2e8f0` (COMPATIBLE), status default `Unchecked` bagi frame bermasalah, dan tooltip detail. | `test_frame_list_panel_checkboxes` ([test_redesign_ui.py:321-348](../tests/test_redesign_ui.py#L321-L348)) hanya menguji item `COMPATIBLE`; belum ada unit test widget `FrameListPanel` khusus yang memeriksa badge, warna, dan `Unchecked` untuk status `ERROR`/`INCOMPATIBLE`. | Termasuk dalam keseluruhan baseline suite `offscreen` (`225 passed, 3 skipped` / `228 test cases` di 18 berkas test). |
| **ISSUE-02** | `PARTIALLY FIXED — UNIT TEST MISSING` | Dua lokasi awal di `main_window.py` (`1204-1206` dan `4086-4088`, semula di baris `1154`/`3790`) kini mencatat warning ke `self.log_manager`. **Sisa yang belum diperbaiki**: [histogram_window.py:607-608](../src/hilalone/gui/histogram_window.py#L582-L608) pada `export_table_csv` (bukan `_export_graph_png`) masih berisi `except Exception: return False` tanpa log, dan beberapa blok `except Exception:` di `main_window.py` (`485`, `502`, `592`, `606`, `5057`) belum mencatat ke `LogManager`. | `test_log_manager_and_export` menguji `LogManager` secara umum, namun belum ada unit test yang menyimulasikan gagal preview/ekspor CSV untuk memastikan warning tercatat di `LogManager`. | Termasuk dalam keseluruhan baseline suite `offscreen` (`225 passed, 3 skipped`); skenario gagal spesifik belum diuji. |
| **ISSUE-03** | `BENCHMARK SUITE CREATED — PERFORMANCE METRICS NOT RECORDED` | Modul [test_performance_benchmarks.py](../tests/test_performance_benchmarks.py) sudah tersedia dengan 5 fungsi benchmark memakai `time.perf_counter()` & `tracemalloc`. | Ke-5 fungsi benchmark menguji asersi dasar `t_* > 0.0` pada sampel sintetis kecil (`128×128` dan `256×256`). | Ke-5 fungsi ikut lulus sebagai bagian dari keseluruhan baseline suite (`225 passed, 3 skipped` di 18 berkas test), namun **angka benchmark khusus (`-s`, beban produksi, dan RAM MB)** belum diukur/dicatat. |
| **ISSUE-04** | `CODE FIXED (STATIC) — BASELINE RUNTIME NO WARNINGS SUMMARY — EXPLICIT WARNING VALIDATION PENDING` | **Pemeriksaan statis**: `0` kemunculan `mirrored(` maupun `.pos(` ditemukan di `src/hilalone/` maupun `tests/`. Diganti `QTransform` & `event.position().toPoint()` ([image_viewer.py](../src/hilalone/gui/image_viewer.py#L426-L466), [main_window.py](../src/hilalone/gui/main_window.py#L1827-L1869)), serta `QPointF` pada `tests/test_image_viewer_toolbar.py:89-125`. | Konstruktor test toolbar dimutakhirkan ke `QPointF`; **validasi eksplisit** warning pytest belum memiliki assertion/pengujian terpisah. | **Baseline runtime**: `pytest -q` (`61.62s`) & `pytest -rs -q` (`51.63s`, `225 passed, 3 skipped`) di PySide6 `6.12.0` `offscreen` tidak memunculkan *warnings summary*. Namun observasi ini **tidak diklaim sebagai nol `DeprecationWarning` secara mutlak**; **explicit warning validation** (`-W default::DeprecationWarning` / `-W error::DeprecationWarning`) masih **PENDING**. |
| **ISSUE-05** | `CODE IMPLEMENTED — TARGET RESOLUTION & DPI SCALING TESTS INCOMPLETE` | `setFixedHeight(145)` diganti menjadi `setMinimumHeight(120)` & `setMaximumHeight(155)` pada `OpenImagePanel`, `FrameListPanel`, dan `ImageInfoPanel` ([top_panels.py](../src/hilalone/gui/top_panels.py#L44-L46)), dan panel atas disembunyikan secara default. | `test_responsive_layout_on_small_and_large_windows` ([test_image_viewer_toolbar.py:366-384](../tests/test_image_viewer_toolbar.py#L366-L384)) menguji `1333×768` dan `800×560`; belum menguji `1366×768`, `1600×900`, `1920×1080`, maupun Display Scaling Windows `100%/125%/150%`. | Lulus dalam keseluruhan baseline suite `offscreen` (`225 passed, 3 skipped`); uji visual DPI Scaling `125%/150%` pada Windows non-offscreen belum diverifikasi. |
| **ISSUE-06** | `CODE IMPLEMENTED — ACCESSIBILITY TEST MISSING` | Aturan QSS `:focus` ditambahkan pada `APP_STYLESHEET` (`#38bdf8`, [styles.py:165-173](../src/hilalone/gui/styles.py#L165-L173)) dan `NIGHT_VISION_RED_STYLESHEET` (`#ef4444`, [styles.py:832-840](../src/hilalone/gui/styles.py#L832-L840)). | `test_stylesheets_validity` dan `test_dark_and_night_vision_stylesheets_complete` belum memeriksa aturan `:focus` maupun *tab order*. | Navigasi keyboard `Tab` interaktif non-offscreen belum diverifikasi. |
| **ISSUE-07** | `PARTIALLY IMPLEMENTED — QSS STILL HARDCODED — NO TEST` | Dataclass `DesignTokens` beserta instance `DARK_TOKENS` dan `NIGHT_VISION_TOKENS` telah didefinisikan di [styles.py:24-89](../src/hilalone/gui/styles.py#L24-L89) *(catatan audit awal menyebut `DARK_THEME`/`NIGHT_VISION_THEME`)*. Namun string QSS `APP_STYLESHEET` dan `NIGHT_VISION_RED_STYLESHEET` belum menginterpolasi token tersebut dan masih hardcoded. | Belum ada unit test yang memvalidasi pemakaian atau konsistensi `DesignTokens`. | Stylesheet syntax smoke lulus dalam keseluruhan baseline suite (`225 passed, 3 skipped`). |
| **ISSUE-08** | `PARTIALLY FIXED — FPS UNIT GAP & UNIT TEST PARTIAL` | Sudah diperbaiki: `fits_exptime` (`s`/`ms`/`µs`), `bit_depth` jujur, resolusi `px`, dan video sidebar (`FRAME_RATE` `fps`, `DURATION` `s`). **Celah tersisa**: entri `"FPS"` pada kartu & dialog metadata ([main_window.py:1411](../src/hilalone/gui/main_window.py#L1411), [info_dialog.py:400](../src/hilalone/gui/info_dialog.py#L400)) masih memformat angka tanpa kata `fps`, dan satuan `ADU` belum tampil pada ringkasan GUI. | Teruji parsial melalui `test_exposure_time_formatter_cases`, `test_exposure_time_formatting_preserves_source_fits_header_precision`, `test_16bit_info_text_is_honest`, dan `test_gui_raw_metadata_label_and_honest_bit_depth`; belum ada tes untuk satuan `fps` di dialog/kartu maupun `ADU`. | Lulus dalam keseluruhan baseline suite `offscreen` (`225 passed, 3 skipped`). |
| **ISSUE-09** | `NOT COMPLETED — DETAIL SECTION ADDED IN REVIEW — NO TEST` | *(Uraian temuan ini sebelumnya belum ditulis di Bagian 3 audit awal.)* Pada dialog dan panel sekunder, nilai margin/spacing seperti `14`, `10`, `6`, `2` px masih dipakai di [info_dialog.py:82-83](../src/hilalone/gui/info_dialog.py#L82-L83), [curves_window.py:476-579](../src/hilalone/gui/curves_window.py#L476-L579), [histogram_window.py:346-426](../src/hilalone/gui/histogram_window.py#L346-L426), dan [console_panel.py:153-159](../src/hilalone/gui/console_panel.py#L153-L159), belum seragam kelipatan grid `4px/8px`. | Belum ada unit test khusus untuk konsistensi grid spasi `4px/8px`. | Belum diverifikasi secara visual sebagai kesesuaian grid system. |

### 5.3 Pembaruan Status Jadwal Eksekusi (`PHASE 1`–`PHASE 6`) & Keputusan Maintainer

- **`PHASE 1` (Dokumentasi Audit Awal)**: **SELESAI** (12 November 2026) + diperbarui review status **14 November 2026**.
- **`PHASE 2` s.d. `PHASE 5`**: **`PARTIAL — CODE IMPLEMENTED / TEST & CODE GAPS REMAIN`** (mayoritas perbaikan inti ada dan keseluruhan baseline test suite lulus, namun menyisakan celah kode pada `ISSUE-02`, `ISSUE-07`, `ISSUE-08`, `ISSUE-09`, celah unit test / DPI scaling pada `ISSUE-01`, `02`, `05`, `06`, `07`, `08`, `09`, serta *explicit warning validation* pada `ISSUE-04`).
- **`PHASE 6` (Final Validation & Benchmarking)**: **`BASELINE SUITE VERIFIED (225 PASSED, 3 SKIPPED OFFSCREEN) — PERFORMANCE BENCHMARK METRICS & FINAL ACCEPTANCE REPORT PENDING`** — Baseline regresi pada `.venv` (`Python 3.10.11`, `PySide6 6.12.0`) terkonfirmasi **`225 passed, 3 skipped`** (`228 test cases`, `61.62 seconds` pada pengujian pertama; 3 *skipped* akibat sampel eksternal tidak ada). Namun pengukuran metrik benchmark performa khusus, verifikasi validasi ilmiah data hilal nyata, uji Display Scaling `125%/150%`, serta penyusunan Laporan Akhir Penerimaan Kualitas masih terbuka.
- **Catatan Lintas Dokumen (Pending Maintainer):** Status deviasi *position stability* (`IMPLEMENTATION DEVIATION — PENDING MAINTAINER CONFIRMATION`) serta status CLI (`CLI NOT IMPLEMENTED — PYTHON PIPELINE API AVAILABLE — SCOPE DECISION PENDING`) dijelaskan pada [project_overview.md](project_overview.md) dan [development_roadmap.md](development_roadmap.md) dan masih menunggu keputusan resmi maintainer.
