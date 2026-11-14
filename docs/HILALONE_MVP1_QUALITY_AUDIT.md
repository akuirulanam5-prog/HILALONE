# LAPORAN AUDIT KUALITAS PERANGKAT LUNAK, UI/UX & VALIDASI ILMIAH
# PROYEK HILALONE — FINALISASI DAN PENINGKATAN KUALITAS MVP 1.0

**Dokumen**: `docs/HILALONE_MVP1_QUALITY_AUDIT.md`  
**Aplikasi**: HILALONE (Automated Astronomical & Crescent Moon Image Processing)  
**Lingkungan**: Python 3.10.11 (64-bit), PySide6 6.8+, NumPy, Astropy, SciPy, rawpy, PyAV, tifffile  
**Prinsip Utama**: *"Enhance the Signal, Never Invent the Signal"*  
**Tanggal Audit**: 12 November 2026  

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
