# HILALONE — Audit Sistem Logging & Console (`HILALONE_LOGGING_AUDIT.md`)

**Aplikasi**: HILALONE — Automated Hilal Image Processing  
**Versi**: 1.0.0  
**Prinsip Ilmiah**: *"Enhance the Signal, Never Invent the Signal."*

---

## 1. Kondisi Sistem Logging Saat Ini

Sebelum peningkatan sistem menuju **HILALONE Scientific Processing Log**, mekanisme pencatatan aktivitas di dalam proyek HILALONE terbagi menjadi dua jalur yang belum terintegrasi penuh:

1. **Console GUI (`src/hilalone/gui/console_panel.py`)**:
   - Menggunakan kelas `LogManager(QObject)` dan `ConsoleLogPanel(QFrame)` dengan model sederhana `LogEntry(timestamp, level, module, action, detail)`.
   - Hanya mendukung empat level (`INFO`, `SUCCESS`, `WARNING`, `ERROR`) tanpa dukungan `DEBUG`, `CRITICAL`, `PROGRESS`, `SECTION`, `CANCELLED`, dan `SKIPPED`.
   - Format waktu hanya `HH:MM:SS` tanpa milidetik (`%H:%M:%S.mmm`) dan tanpa standar ISO 8601 ber-timezone untuk berkas permanen.
   - Tidak memiliki konsep **Application Session ID** maupun **Processing Run ID** untuk mengelompokkan satu siklus pemrosesan ilmiah.
   - Semua teks di `QPlainTextEdit` ditampilkan dengan satu warna seragam (`#38bdf8` pada Standard Dark atau `#ef4444` pada Night Vision Red), belum menggunakan pewarnaan semantik per jenis pesan/level.
   - Belum memiliki fitur **Filter** (All, Info, Success, Progress, Warning, Error, Critical, Debug), **Verbosity** (`NORMAL`, `VERBOSE`, `DEBUG`), **Search** (kata kunci/modul/Run ID/nama berkas), **Copy Selected**, **Copy All**, **Auto-scroll / Pause Scrolling**, dan **Open Log Folder**.
   - Tombol `Clear Log` memanggil `self._entries.clear()` yang menghapus seluruh riwayat memori sesi aktif alih-alih hanya membersihkan tampilan visual (`Clear Console` view-only).

2. **Runtime & Crash File Logging (`src/hilalone/main.py` & `src/hilalone/gui/resources.py`)**:
   - Mengonfigurasi `logging.basicConfig` hanya ke `%LOCALAPPDATA%\HILALONE\logs\hilalone.log` dan `crash.log`.
   - Tidak terhubung dengan `LogManager` di GUI sehingga seluruh catatan yang dikirim ke `self.log_manager.info(...)` di `MainWindow` **tidak pernah ditulis ke berkas log permanen** di disk.
   - Belum memiliki pencatatan terstruktur `.jsonl` (JSON Lines) maupun pemisahan direktori `application/`, `sessions/`, dan `diagnostics/` di `%LOCALAPPDATA%\HILALONE\Logs\`.

---

## 2. Temuan Audit Berdasarkan 10 Kriteria Utama

### 2.1. Bagian yang Sudah Menghasilkan Log
- **Startup dasar (`main.py`)**: Mencatat satu baris `Memulai HILALONE v1.0.0` ke Python `logging`, tetapi tidak tampil di Console GUI.
- **Pembukaan berkas di GUI (`main_window.py`)**:
  - `load_path()`: Mencatat nama berkas, resolusi, dan jumlah kanal untuk Single Image.
  - `_finalize_sequence_open()`: Mencatat mode input, jumlah total frame, dan jumlah frame kompatibel.
  - `close_image()`: Mencatat penutupan citra.
- **Interaksi GUI (`main_window.py`)**:
  - Seleksi checkbox frame di Panel B (`_on_frame_selection_changed`).
  - Pembukaan dialog Histogram, Kurva, dan Image Information.
  - Penerapan kurva (`_on_curves_apply`), rotasi/flip citra, Negative View, Quick Snapshot, dan pergantian tema.
- **Penyelesaian proses di GUI (`main_window.py`)**:
  - `start_flat_calibration()`: Mencatat selesai kalibrasi flat langsung.
  - `_on_stacking_finished()`: Mencatat selesai stacking.
  - `_on_pipeline_finished()`: Mencatat ringkasan singkat `stage_records` setelah seluruh pipeline selesai.
  - `save_stacking_result_to_path()`: Mencatat penyimpanan hasil stacking.

### 2.2. Bagian yang Belum Mencatat Informasi
- **Application Initialization (`SYSTEM`)**: Belum mencatat versi OS/build, arsitektur CPU, versi runtime Python, versi Qt/PySide6, Session ID, dan status inisialisasi modul di Console.
- **Detail Input & Metadata Format Spesifik (`INPUT`)**:
  - Pembaca FITS (`fits_reader.py`), TIFF (`tiff_reader.py`), Camera RAW (`raw_reader.py`), Video (`video_reader.py`), dan SER (`ser_reader.py`) belum mencatat metadata aktual yang tersedia (seperti `BITPIX`, `NAXIS`, `TELESCOP`, `INSTRUME`, `EXPTIME`, `DATE-OBS`, `FILTER`, model kamera, pola CFA, white level, codec video, pixel format, frame rate, atau jumlah frame SER).
- **Validasi Sequence Terperinci (`SEQUENCE` / `VALIDATION`)**:
  - Belum membedakan secara eksplisit di log antara: (1) *structural incompatibility*, (2) *decoding error*, (3) *user selection exclusion*, dan (4) *algorithmic outlier rejection*, beserta alasan spesifik per frame yang dikeluarkan.
- **Pembuatan Master Flat & Kalibrasi Flat (`FLAT` & `CALIBRATION`)**:
  - Saat pengguna memuat Single Master Flat atau Flat Frame Sequence (`set_master_flat_path`, `set_master_flat_sequence`), belum ada log mengenai jumlah frame flat, metode agregasi, rumus normalisasi, jumlah invalid/NaN/Inf/saturated pixels, dan status kompatibilitas terhadap light frame.
  - Saat opsi *Apply Flat Calibration* tidak dicentang, belum ada pencatatan eksplisit berstatus `SKIPPED` (`Reason: Disabled by user`).
- **Tahapan Internal Backend selama Eksekusi (`STACKING`, `BACKGROUND`, `ENHANCEMENT`, `HISTOGRAM`)**:
  - Selama `PipelineWorker` atau `StackingWorker` berjalan, log baru ditulis sekaligus di akhir (`_on_pipeline_finished`), bukan secara real-time saat setiap tahapan dimulai, melaporkan parameter ilmiah aktual, progres bertahap, hingga selesai.
- **Penyimpanan Pipeline (`save_pipeline_result_to_path`)**:
  - Berbeda dengan `save_stacking_result_to_path`, metode `save_pipeline_result_to_path` di `main_window.py` belum mencatat log `OUTPUT` ketika pengguna menyimpan Master Linear FITS, Master Linear TIFF, Derived Enhanced FITS, atau Display Preview PNG, serta belum mencatat ukuran berkas, rentang nilai, durasi tulis, dan status verifikasi berkas.
- **Ringkasan Akhir (`PROCESSING SUMMARY`)**:
  - Belum ada blok ringkasan terstruktur di akhir Automated Processing yang merangkum Run ID, status akhir (`SUCCESS` / `PARTIAL` / `FAILED` / `CANCELLED`), profil, jumlah frame, status tiap tahapan, berkas keluaran, dan total durasi.

### 2.3. Pesan yang Duplikat
- Pada `_on_pipeline_finished`, pengulangan log tahapan setelah proses selesai berpotensi tumpang tindih apabila worker juga mengirim sinyal tahapan. Dengan arsitektur baru, setiap tahapan dicatat tepat satu kali secara real-time berdasarkan event terstruktur ber-Run ID.

### 2.4. Pesan yang Terlalu Umum
- Pesan seperti `"Pemrosesan otomatis selesai"` atau `"Stacking selesai"` belum mencantumkan parameter ilmiah yang benar-benar digunakan (mis. derajat polinomial/RBF smoothing pada Background Extraction, `clip_limit` dan `tile_grid_size` pada CLAHE, metode stretch `vmin`/`vmax`/`asinh_a`/`mtf_m` pada Histogram Transformation, maupun jumlah titik kontrol pada Curve Transformation).
- Nama modul pada kode lama masih tidak seragam (`FRAME_SELECTION`, `DATA`, `TOOLS`, `CURVES`, `FITS`, `METADATA`, `THEME`, `VIEW`, `SNAPSHOT`, `PREVIEW`, `STAGE`, `PIPELINE`) dan perlu distandardisasi ke daftar modul resmi (`SYSTEM`, `SESSION`, `INPUT`, `SEQUENCE`, `VALIDATION`, `CALIBRATION`, `FLAT`, `STACKING`, `BACKGROUND`, `ENHANCEMENT`, `HISTOGRAM`, `CURVE`, `DISPLAY`, `OUTPUT`, `VIEWER`, `ERROR`).

### 2.5. Error dan Pembatalan yang Tidak Dilaporkan ke Console
- `_show_error()` dan `_show_warning()` di `MainWindow` hanya menampilkan `QMessageBox` tanpa mencatat pesan `ERROR` atau `WARNING` ke Console Log.
- `_on_stacking_failed()`, `_on_pipeline_failed()`, `_on_stacking_cancelled()`, dan `_on_pipeline_cancelled()` hanya memperbarui label status bawah tanpa mencatat event `[ERROR]` atau `[CANCELLED]` ke Console Log.
- Kegagalan pemuatan Master Flat (`set_master_flat_path`, `set_master_flat_sequence`) tidak tercatat di Console Log.

### 2.6. Progress yang Tidak Mencerminkan Proses Aktual
- Pada `AutomaticStackingEngine` jalur `BASIC`, `_notify_progress` dipanggil pada **setiap frame** (`for step_idx, frame_idx in enumerate(included_indices)`), yang pada sequence 300–1000 frame akan mengirim ratusan sinyal ke GUI namun tidak tercatat sebagai milestone progres yang terkendali (mis. interval 10%, 25%, 50%, 75%, 100%) di Console Log.
- Diperlukan *rate limiting* (interval persentase 5–10% atau milestone) agar progress di Console informatif dan bebas banjir pesan.

### 2.7. Logging yang Menyentuh GUI dari Worker Thread
- Saat ini `StackingWorker` dan `PipelineWorker` berkomunikasi melalui sinyal Qt (`progress_updated`, `stage_changed`), namun belum memiliki jalur pengiriman `LogEvent` terstruktur yang thread-safe dari backend ke GUI dan ke file writer.
- Pada `start_flat_calibration()`, pemrosesan dijalankan secara sinkron di main thread sambil memanggil `QCoreApplication.processEvents()`.

### 2.8. Pesan yang Berpotensi Memberikan Informasi Keliru
- Saat `Histogram Transformation` atau `Curve Processing` dijalankan, log lama belum menegaskan cabang data (`Input branch` vs `Output branch`). Penting untuk menyatakan secara eksplisit bahwa transformasi histogram bekerja menuju cabang `DISPLAY` (`[0.0, 1.0]`) dan **tidak mengubah** data ilmiah linear (`linear_result`), serta membedakan kapan kurva diterapkan pada pratinjau tampilan vs cabang data aktif.
- Saat `Clear Log` ditekan pada implementasi lama, `LogManager.clear()` menghapus seluruh `self._entries`, sehingga jika pengguna mengekspor log setelah menekan Clear, riwayat sesi ikut hilang.

### 2.9. Log yang Tidak Tersimpan ke File Permanen
- Seluruh aktivitas di `LogManager` hanya hidup di RAM (`list[LogEntry]`) dan hilang begitu aplikasi ditutup.
- Belum ada penyimpanan otomatis ke `%LOCALAPPDATA%\HILALONE\Logs\` dalam format `.log` (teks terbaca manusia) dan `.jsonl` (JSON Lines terstruktur).

### 2.10. Potensi Bottleneck Akibat Terlalu Banyak Pesan
- Pemanggilan `text_edit.appendPlainText()` tanpa rate-limiting pada event frekuensi tinggi atau pemformatan string/statistik mahal di dalam loop frame dapat membebani thread utama Qt.
- Solusi: gunakan rate-limiter untuk event `PROGRESS`, hindari menghitung statistik piksel tambahan hanya untuk logging, lewatkan pembuatan pesan `DEBUG` jika verbosity bukan `DEBUG`, dan gunakan buffered file writing yang thread-safe.

---

## 3. Rancangan Arsitektur Perbaikan (`src/hilalone/core/logging/`)

Kita akan membangun paket inti terpusat di `src/hilalone/core/logging/` dengan komponen:

1. `log_event.py`:
   - Enumerasi `LogLevel` (`DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR`, `CRITICAL`, `PROGRESS`, `SECTION`, `CANCELLED`, `SKIPPED`).
   - Enumerasi `LogEventType` (`MESSAGE`, `SUCCESS`, `PROGRESS`, `SECTION`, `CANCELLED`, `SKIPPED`, `SUMMARY`, `EXCEPTION`).
   - Enumerasi `LogModule` (`SYSTEM`, `SESSION`, `INPUT`, `SEQUENCE`, `VALIDATION`, `CALIBRATION`, `FLAT`, `STACKING`, `BACKGROUND`, `ENHANCEMENT`, `HISTOGRAM`, `CURVE`, `DISPLAY`, `OUTPUT`, `VIEWER`, `ERROR`).
   - Enumerasi `LogVerbosity` (`NORMAL`, `VERBOSE`, `DEBUG`).
   - Dataclass immutable `LogEvent` (lengkap dengan properti kompatibilitas `action` dan `detail` agar seluruh kode dan tes unit lama tetap berjalan mulus).
   - Dataclass `ProcessingRunSummary` untuk pembuatan blok `PROCESSING SUMMARY`.
   - Definisi palet warna resmi **Standard Dark** dan **Night Vision Red**.

2. `log_session.py`:
   - Pengelola `ApplicationSession` (membuat `session_id` saat aplikasi dimulai, menyimpan metadata sistem/runtime) dan `ProcessingRunSession` (membuat `run_id` unik untuk setiap eksekusi Automated Processing / Stacking, melacak waktu mulai/selesai dengan `time.monotonic()`, tahapan, frame, dan hasil akhir).

3. `log_formatter.py`:
   - Pemformatan baris standar Console: `[HH:MM:SS.mmm] [LEVEL] [MODULE] MESSAGE | DETAILS`.
   - Pemformatan baris berkas `.log` permanen dengan timestamp ISO 8601 + timezone offset (`YYYY-MM-DDTHH:MM:SS.mmm+07:00`).
   - Pemformatan `SECTION` (`=== SECTION TITLE ===`) dan blok `PROCESSING SUMMARY`.
   - Serialisasi `.jsonl` (JSON Lines) yang valid dan bersih dari informasi sensitif.
   - Pemformatan HTML/warna semantik untuk `ConsoleLogPanel` sesuai tema aktif.

4. `log_filter.py`:
   - Filter tampilan berdasarkan kategori/level (`ALL`, `INFO`, `SUCCESS`, `PROGRESS`, `WARNING`, `ERROR`, `CRITICAL`, `DEBUG`), tingkat `LogVerbosity` (`NORMAL`, `VERBOSE`, `DEBUG`), Run ID, rentang waktu, dan pencarian teks bebas (kata kunci, nama berkas, modul, Run ID, kode galat).

5. `file_handler.py`:
   - Penulis berkas log permanen thread-safe ke `%LOCALAPPDATA%\HILALONE\Logs\` (dengan dukungan override direktori untuk pengujian unit agar tidak mengotori folder sistem saat pytest berjalan):
     - `application/application_latest.log` (dengan rotasi terukur bila melebihi batas ukuran).
     - `sessions/HILALONE_YYYYMMDD_HHMMSS.log` dan `sessions/HILALONE_YYYYMMDD_HHMMSS.jsonl`.
     - `diagnostics/diagnostic_latest.log` (menyimpan log `DEBUG` dan traceback lengkap ketika terjadi exception).
   - Mekanisme fallback aman jika disk penuh atau izin ditolak (tidak pernah membuat aplikasi crash).

6. `log_handler.py` & `logger.py`:
   - `HilaloneLogger` / `LogManager` terpusat dengan sinyal Qt (`entry_logged`, `view_cleared`, `verbosity_changed`) yang menjamin semua pembaruan widget GUI selalu dieksekusi di main thread Qt via *QueuedConnection* saat dipanggil dari worker thread.
   - Rate-limiter progres (`ProgressRateLimiter`) agar progres dilaporkan pada milestone bermakna (mis. setiap kenaikan ≥10% atau milestone 10%, 25%, 50%, 75%, 100%).

---

## 4. Daftar Modul yang Diintegrasikan

1. `src/hilalone/main.py` — Inisialisasi aplikasi, sistem operasi, arsitektur, Python, Qt, Session ID, dan crash hook.
2. `src/hilalone/gui/console_panel.py` — Redesign Console Log GUI (filter, verbosity, search + counter, Copy Selected, Copy All, Export Visible, Export Complete, Clear Console view-only, Open Log Folder, Auto-scroll / Pause Scrolling, pewarnaan Standard Dark & Night Vision Red real-time).
3. `src/hilalone/gui/main_window.py` — Integrasi menyeluruh untuk Input, Sequence Validation, Flat Calibration, Master Flat, Stacking, Pipeline, Curve, Display/Preview, Output, Cancel, Warning, dan Error.
4. `src/hilalone/gui/pipeline_worker.py` & `src/hilalone/gui/stacking_worker.py` — Penerusan Run ID dan pencatatan tahapan secara thread-safe dari worker thread.
5. `src/hilalone/processing/processing_pipeline.py` — Pencatatan detail ilmiah setiap tahapan pipeline (`VALIDATION`, `CALIBRATION`, `STACKING`, `BACKGROUND`, `ENHANCEMENT`, `HISTOGRAM`) dan penyusunan `PROCESSING SUMMARY`.
6. `src/hilalone/processing/stacking/engine.py` & `src/hilalone/processing/stacking/flat_calibration.py` — Pencatatan pembuatan Master Flat, normalisasi, statistik piksel invalid/NaN/Inf/saturated, parameter profil stacking, dan progres terkendali.
7. `src/hilalone/output_manager/pipeline_writer.py` & `src/hilalone/output_manager/stacking_writer.py` — Pencatatan pembuatan berkas output, ukuran berkas, durasi penulisan, dan verifikasi integritas berkas.
