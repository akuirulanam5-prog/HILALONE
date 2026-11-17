# HILALONE — Standar Sistem Pencatatan Ilmiah (`HILALONE_LOGGING_STANDARD.md`)

**Aplikasi**: HILALONE — Automated Hilal Image Processing  
**Versi**: 1.1.2  
**Paket Sumber**: `src/hilalone/core/logging/` & `src/hilalone/gui/console_panel.py`  
**Prinsip Utama**: *"Enhance the Signal, Never Invent the Signal."*

---

## 1. Tujuan Logging

Sistem **HILALONE Scientific Processing Log** dirancang bukan sekadar sebagai penampil status umum, melainkan sebagai **catatan audit pengolahan citra astronomi** yang:
1. Menjelaskan apa yang sedang dikerjakan aplikasi dan modul mana yang aktif.
2. Mencatat data sumber, dimensi, tipe numerik, bit depth, dan metadata observasi yang benar-benar tersedia pada berkas asli.
3. Mencatat parameter algoritma yang benar-benar diterapkan pada setiap tahap (Flat Calibration, Stacking, Background Extraction, CLAHE Enhancement, Histogram Transformation, dan Curve Transformation).
4. Memisahkan secara transparan cabang data ilmiah linear (`LINEAR`) dari cabang turunan nonlinear (`ENHANCED_DERIVED`) dan cabang tampilan layar (`DISPLAY`).
5. Melaporkan frame yang dikecualikan beserta alasan spesifiknya (ketidakcocokan struktural, galat decoding, pilihan pengguna, atau penolakan outlier algoritma).
6. Menyediakan penyimpanan permanen (`.log` dan `.jsonl`), kemampuan pencarian, pemfilteran, penyalinan, dan ekspor untuk pengguna umum, pengamat/peneliti astronomi, serta pengembang.

---

## 2. Struktur Format Pesan

Setiap peristiwa dicatat menggunakan format satu baris yang konsisten:

```text
[TIMESTAMP] [LEVEL] [MODULE] MESSAGE | DETAILS
```

Apabila tidak ada bagian `DETAILS`, pemisah `|` dihilangkan:

```text
[TIMESTAMP] [LEVEL] [MODULE] MESSAGE
```

Untuk judul bagian tahapan (`SECTION`):

```text
=== NAMA TAHAPAN ===
```

**Ketentuan Format**:
- **Timestamp Console UI**: menggunakan milidetik `HH:MM:SS.mmm` (contoh: `[20:15:03.125]`).
- **Timestamp Berkas Permanen (`.log` & `.jsonl`)**: menggunakan ISO 8601 lengkap dengan offset zona waktu lokal `YYYY-MM-DDTHH:MM:SS.mmm+HH:MM` (contoh: `2026-11-17T20:15:03.125+07:00`).
- **Pemisahan Waktu**: sistem membedakan dengan tegas antara (a) timestamp kejadian log, (b) waktu observasi pada metadata citra (`DATE-OBS`), dan (c) durasi eksekusi pemrosesan yang dihitung menggunakan *monotonic timer* (`time.monotonic()` / `time.perf_counter()`).

---

## 3. Log Level

Sistem mendukung 10 kategori level/status:

| Level | Fungsi & Penggunaan | Tampil Default (`NORMAL`) |
| :--- | :--- | :---: |
| `DEBUG` | Diagnostik teknis internal (alokasi buffer, detail strip, diagnostik mendalam) | Tersembunyi (aktif di `DEBUG`) |
| `INFO` | Aktivitas normal, pembukaan berkas, metadata sumber, dan parameter tahapan | Ya |
| `SUCCESS` | Konfirmasi bahwa suatu tahapan atau operasi berhasil diselesaikan | Ya |
| `WARNING` | Anomali nonfatal yang perlu diketahui pengguna (mis. frame inkompatibel atau keyword opsional tidak tersedia) | Ya |
| `ERROR` | Kegagalan operasi atau tahapan yang menghentikan proses saat ini | Ya |
| `CRITICAL` | Masalah fatal tingkat aplikasi/sistem | Ya |
| `PROGRESS` | Perkembangan pekerjaan panjang dengan pembatasan frekuensi (*rate-limited*) | Ya |
| `SECTION` | Pembatas judul bagian proses (`=== ... ===`) | Ya |
| `CANCELLED` | Proses dihentikan secara sengaja atas permintaan pengguna (bukan `ERROR`) | Ya |
| `SKIPPED` | Tahapan opsional dilewati secara sengaja atau sesuai mode alur kerja (bukan `WARNING`/`ERROR`) | Ya |

---

## 4. Semantic Event Type

Pada representasi terstruktur (`LogEvent` dan berkas `.jsonl`), setiap baris memiliki atribut `event_type` (`LogEventType`):
- `MESSAGE`: Pesan informasi umum (`INFO`).
- `SUCCESS`: Konfirmasi keberhasilan tahapan.
- `PROGRESS`: Milestone perkembangan komputasi (`progress_current`, `progress_total`, `percent`).
- `WARNING`: Peringatan nonfatal.
- `ERROR`: Kegagalan tahapan/operasi.
- `CRITICAL`: Kegagalan kritis aplikasi.
- `DEBUG`: Catatan diagnostik internal.
- `SECTION`: Header bagian tahapan.
- `CANCELLED`: Pembatalan oleh pengguna.
- `SKIPPED`: Tahapan opsional yang dilewati.
- `SUMMARY`: Blok ringkasan akhir `PROCESSING SUMMARY`.

---

## 5. Warna Standard Dark

Palet warna semantik untuk tema **Standard Dark** (`STANDARD_DARK_LOG_PALETTE`):

| Kategori | Hex Color | Gaya Font |
| :--- | :--- | :--- |
| `INFO` | `#C7D5E8` | Regular |
| `SUCCESS` | `#65DDA5` | Semibold |
| `WARNING` | `#F0B65C` | Regular |
| `ERROR` | `#FF7777` | Regular |
| `CRITICAL` | `#FF4242` | Semibold |
| `PROGRESS` | `#57CFFF` | Regular |
| `DEBUG` | `#8292AA` | Regular |
| `SECTION` | `#EAF3FF` | Semibold |
| `CANCELLED` | `#F0B65C` | Regular |
| `SKIPPED` | `#94A3B8` | Regular |

---

## 6. Warna Night Vision Red

Palet warna semantik untuk tema **Night Vision Red** (`NIGHT_VISION_RED_LOG_PALETTE`), dirancang menjaga adaptasi gelap mata pengamat tanpa warna hijau/cyan/biru terang:

| Kategori | Hex Color | Gaya Font |
| :--- | :--- | :--- |
| `INFO` | `#D9AAAA` | Regular |
| `SUCCESS` | `#FFA8A8` | Semibold |
| `WARNING` | `#F3A18D` | Regular |
| `ERROR` | `#FF6666` | Regular |
| `CRITICAL` | `#FF3333` | Semibold |
| `PROGRESS` | `#F28F8F` | Regular |
| `DEBUG` | `#A87878` | Regular |
| `SECTION` | `#FFD0D0` | Semibold |
| `CANCELLED` | `#F3A18D` | Regular |
| `SKIPPED` | `#B88686` | Regular |

Pergantian tema memperbarui warna tampilan Console secara real-time tanpa mengubah isi pesan, timestamp, metadata, maupun berkas log permanen di disk.

---

## 7. Module Naming

Seluruh komponen menggunakan penamaan modul kanonik (`LogModule`):
- `SYSTEM`: Inisialisasi aplikasi, OS, runtime Python, dan Qt framework.
- `SESSION`: Manajemen sesi pemrosesan otomatis, Run ID, pembatalan, dan `PROCESSING SUMMARY`.
- `INPUT`: Pembacaan berkas gambar tunggal/jamak dan ekstraksi metadata FITS, TIFF, RAW, Video, serta SER.
- `SEQUENCE`: Pengelolaan daftar frame dan seleksi frame oleh pengguna.
- `VALIDATION`: Pemeriksaan kompatibilitas struktural sequence pra-pemrosesan.
- `CALIBRATION`: Penerapan koreksi Flat-Field pada Light frame.
- `FLAT`: Pembuatan, agregasi, normalisasi, dan diagnostik piksel Master Flat.
- `STACKING`: Integrasi multi-frame (`BASIC`, `MEDIUM`, `HIGH`).
- `BACKGROUND`: Pemodelan permukaan gradien langit dan pengurangan background linear.
- `ENHANCEMENT`: Peningkatan kontras lokal CLAHE pada cabang turunan nonlinear.
- `HISTOGRAM`: Peregangan tampilan (Linear/Asinh/Adaptive Asinh/GHS + MTF) pada cabang `DISPLAY`.
- `CURVE`: Transformasi kurva PCHIP interaktif.
- `DISPLAY`: Perubahan mode pratinjau, perbandingan Before/After, dan tema antarmuka.
- `OUTPUT`: Penulisan dan verifikasi berkas hasil (FITS, TIFF, PNG, dan laporan JSON).
- `VIEWER`: Interaksi tampilan kanvas seperti Normal/Negative View, rotasi, dan flip.
- `LOGGING`: Pencatatan perubahan mode detail (`NORMAL`, `VERBOSE`, `DEBUG`) dan konfigurasi logging.
- `EXPORT`: Pencatatan aktivitas ekspor log (`Export Visible Log`, `Export Complete Log`, dan penentuan folder sumber).
- `ERROR`: Penanganan uncaught exception dan galat global.

---

## 8. Input Logging

Saat membuka **Single Image**, **Multiple Images**, **Folder Sequence**, **Video**, atau **SER**, modul `INPUT` mencatat:
- Nama berkas, format, nama reader (`Astropy FITS Reader`, `tifffile Scientific TIFF Reader`, `rawpy Camera RAW Reader`, `PyAV Video Stream Reader`, `HILALONE SER Binary Reader`, atau `Qt QImageReader`).
- Resolusi (`W × H px`), tata kanal (`Monochrome`, `RGB`, atau `CFA Mosaic`), tipe data (`dtype`), bit depth asli, jumlah frame, dan durasi pemuatan.
- Metadata spesifik yang benar-benar ada pada berkas:
  - **FITS**: `BITPIX`, `NAXIS`, `NAXIS1`, `NAXIS2`, `BUNIT`, `OBJECT`, `TELESCOP`, `INSTRUME`, `EXPTIME`, `DATE-OBS`, `FILTER`.
  - **TIFF**: resolusi, `samples_per_pixel`, `bits_per_sample`, kompresi, `dtype`.
  - **RAW**: model kamera, dimensi sensor, pola CFA, bit depth, `white_level`, ISO.
  - **Video**: container, codec, `pix_fmt`, dimensi, `fps`, `time_base`, durasi, jumlah frame.
  - **SER**: jumlah frame, resolusi, `pixel_depth`, informasi warna/CFA, observer/instrumen/teleskop.

---

## 9. Calibration & Master Flat Logging

Pada tahap **Flat-Field Calibration** (`FLAT` & `CALIBRATION`):
- Mencatat apakah kalibrasi diaktifkan (`ENABLED`) atau dilewati (`[SKIPPED] [CALIBRATION] Flat Calibration skipped. | Reason: Disabled by user`).
- Mencatat jumlah Light frame dan jumlah Flat frame secara terpisah, serta menjelaskan bahwa seluruh frame flat yang valid digabungkan menjadi **satu Master Flat** (`F_norm(x,y) = F(x,y) / median(F_valid)`).
- Mencatat metode agregasi (`Single Master Flat`, `Sigma-Clipped Mean (3.0 sigma)`, atau `Arithmetic Mean`), statistik piksel (`invalid`, `zero/neg`, `NaN/Inf`, `saturated`), status kompatibilitas terhadap Light frame, dan durasi kalibrasi.

---

## 10. Stacking Logging

Pada tahap **Image Stacking** (`STACKING`):
- Jika mode `Single Image`, dicatat sebagai `[SKIPPED] [STACKING] Image stacking skipped. | Reason: Single Image mode (1 frame)`.
- Jika multi-frame, mencatat profil (`BASIC`, `MEDIUM`, `HIGH`), metode aktual (`ARITHMETIC_MEAN`, `SIGMA_CLIPPED_MEAN`, atau `QUALITY_WEIGHTED_ROBUST`), jumlah frame dipilih, frame dikecualikan beserta alasannya, metode penolakan outlier/pembobotan jika digunakan, progres bertahap (*rate-limited* 10%–100%), tipe data keluaran (`float32`), dimensi keluaran, dan durasi.

---

## 11. Background Logging

Pada tahap **Background Extraction** (`BACKGROUND`):
- Mencatat metode pemodelan aktual (`POLYNOMIAL_DEG_1`, `POLYNOMIAL_DEG_2`, `TPS_RBF`, atau `AUTO_ROBUST_RBF`), ukuran mesh grid, parameter derajat polinomial atau RBF smoothing, jumlah sampel diterima/ditolak, jumlah piksel ROI yang dilindungi (bila ada), rasio reduksi gradien, skor overcorrection, dan durasi.
- Menegaskan bahwa ekstraksi background bersifat **subtractive** pada cabang linear (`I_corr = I_linear - B_model`).

---

## 12. Enhancement Logging

Pada tahap **Image Enhancement** (`ENHANCEMENT`):
- Mencatat status (`ENABLED` atau `SKIPPED`), metode (`CLAHE`), `clip_limit` efektif, ukuran `tile_grid_size`, mode kanal (`MONOCHROME`, `RGB_LUMINANCE_PRESERVING`, atau `CFA_SUBCHANNEL_2X2`), rasio amplifikasi derau, serta pemisahan cabang `Input=LINEAR (float32) -> Output=ENHANCED_DERIVED (float32)` dengan jaminan `linear_result` tetap utuh.

---

## 13. Histogram dan Curve Logging

- **Histogram Transformation (`HISTOGRAM`)**:
  - Mencatat metode peregangan (`LINEAR_MTF`, `ASINH_MTF`, `ADAPTIVE_ASINH_MTF`, `GHS_MTF`), parameter aktual (`vmin`, `vmax`, `mtf_midtone`, `asinh_a`, `ghs_d/b/sp`), rentang keluaran `[0.0, 1.0]`, dan pernyataan eksplisit bahwa transformasi hanya diterapkan pada cabang `DISPLAY` tanpa mengubah data ilmiah linear.
- **Curve Processing (`CURVE`)**:
  - Mencatat kanal yang diproses (`RGB` atau `LUMINANCE`), jumlah titik kontrol di teks Console, koordinat numerik titik kontrol di dalam atribut `details`, cabang data, dan durasi.

---

## 14. Output Logging

Ketika menyimpan hasil (`OUTPUT`), sistem membedakan:
1. `Scientific Master FITS` (`float32` linear)
2. `Scientific TIFF Export` (`float32` linear)
3. `Derived Enhanced FITS/TIFF` (`float32` nonlinear)
4. `Display Preview PNG` (`uint8` visual)

Mencatat nama berkas, format, lokasi penyimpanan lengkap, resolusi, tipe data, rentang nilai `[min, max]`, ukuran berkas dalam byte, durasi penulisan, dan status verifikasi berkas di disk.

---

## 15. Error, Warning, Cancel, dan Skip Handling

- **User Cancellation**: Dicatat dengan level `[CANCELLED]` (bukan `ERROR`).
- **Optional Stage Skipped**: Dicatat dengan level `[SKIPPED]` (bukan `WARNING` atau `ERROR`).
- **Fatal Operation Error**: Dicatat dengan level `[ERROR]` beserta modul, operasi, deskripsi yang jelas bagi pengguna, tipe exception, Run ID, dan saran tindakan aman (`suggested_action`). Traceback lengkap ditulis ke berkas diagnostik (`diagnostic_latest.log`) tanpa membanjiri tampilan Console normal.

---

## 16. Lokasi File Log Permanen

Secara default pada Windows, seluruh berkas log disimpan di:

```text
%LOCALAPPDATA%\HILALONE\Logs\
├── application\
│   └── application_latest.log
├── sessions\
│   ├── HILALONE_YYYYMMDD_HHMMSS.log
│   └── HILALONE_YYYYMMDD_HHMMSS.jsonl
└── diagnostics\
    ├── diagnostic_latest.log
    └── crash.log
```

Berkas `application_latest.log` dan `diagnostic_latest.log` memiliki batas ukuran bergulir (default 5 MB) yang secara otomatis diarsipkan ke `*_archive_YYYYMMDD_HHMMSS.log` tanpa pernah menghapus berkas lama secara diam-diam.

---

## 17. Format JSONL

Setiap baris pada `sessions/HILALONE_YYYYMMDD_HHMMSS.jsonl` adalah objek JSON valid:

```json
{"timestamp":"2026-11-17T20:15:03.125+07:00","session_id":"SES-20261117-201500-A1B2C3","run_id":"RUN-20261117-201503-D4E5F6","sequence":12,"level":"INFO","event_type":"MESSAGE","module":"INPUT","message":"Opening Single Image: hilal_01.fits","details":{"filename":"hilal_01.fits","format":"FITS","reader":"Astropy FITS Reader","frame_count":1}}
```

Seluruh key yang mengandung kata sensitif (`password`, `token`, `secret`, `credential`, `api_key`) otomatis disanitasi menjadi `"[REDACTED]"`.

---

## 18. Run ID dan Session ID

- **Application Session ID (`SES-YYYYMMDD-HHMMSS-XXXXXX`)**: Dibuat satu kali saat aplikasi dibuka.
- **Processing Run ID (`RUN-YYYYMMDD-HHMMSS-XXXXXX`)**: Dibuat setiap kali pengguna menjalankan *Mulai Pemrosesan Otomatis* atau *Stacking*. Seluruh log tahapan dan `PROCESSING SUMMARY` dalam satu eksekusi berbagi Run ID yang sama.

---

## 19. Thread Safety

- Worker thread (`PipelineWorker`, `StackingWorker`) tidak pernah memodifikasi widget GUI secara langsung.
- `HilaloneLogger` menggunakan `threading.RLock()` untuk struktur data memori dan penulisan berkas, serta memancarkan sinyal Qt `entry_logged` yang secara otomatis dieksekusi di main thread GUI melalui mekanisme *QueuedConnection* Qt.
- `ProgressRateLimiter` membatasi pengiriman log `PROGRESS` pada milestone bermakna (10%, 25%, 50%, 75%, 100%).

---

## 20. Export Log & Clear Console

- **Export Visible Log**: Mengekspor baris log yang sedang tampil sesuai filter/pencarian aktif ke format `.log`, `.jsonl`, `.txt`, `.csv`, atau `.json` dengan pola nama default `HILALONE_Log_Visible_YYYYMMDD_HHMMSS.log`.
- **Export Complete Log**: Mengekspor seluruh catatan sesi sejak aplikasi dibuka tanpa terpengaruh filter ataupun tombol Clear Console dengan pola nama default `HILALONE_Log_Complete_YYYYMMDD_HHMMSS.log`.
- **Penentuan Folder Awal Dialog Ekspor**:
  - Jika pengguna sedang membuka berkas atau sequence (`Single Image`, `Multiple Images`, `Folder Sequence`, `Video`, atau `SER`), dialog Save File otomatis mengarah ke **folder sumber citra aktif**.
  - Jika belum ada citra atau sequence yang dibuka, dialog Save File mengarah ke folder fallback `%LOCALAPPDATA%\HILALONE\Logs\` dan sistem mencatat `[INFO] [EXPORT] No active source directory. Using default HILALONE log folder.`.
  - Jika nama berkas tujuan sudah ada, sistem menampilkan konfirmasi overwrite sebelum menimpa berkas lama.
- **Clear Console**: Hanya membersihkan tampilan layar GUI (`Console view cleared. Session log remains available.`) dan tidak pernah menghapus riwayat sesi di memori maupun berkas log permanen di disk.

---

## 21. Standardisasi Format Durasi & Logging Verbosity

### A. Format Durasi Terpusat (`format_duration`)
- Seluruh durasi yang ditampilkan pada Console UI, berkas `.log`/`.txt`, serta blok `PROCESSING SUMMARY` wajib menggunakan fungsi terpusat `format_duration(duration_ms=...)` dengan format seragam:
  - `Duration: 0.00 s` (contoh: `264.1 ms -> Duration: 0.26 s`, `1207 ms -> Duration: 1.21 s`).
- Pada berkas terstruktur `.jsonl`, nilai numerik presisi penuh tetap dipertahankan dalam field `"duration_ms"` (contoh: `"duration_ms": 264.1`) tanpa pembulatan kehilangan presisi.

### B. Detail Mode (`NORMAL`, `VERBOSE`, `DEBUG`)
Pengguna dapat memilih tingkat kedalaman secara langsung dari dropdown **Detail** di Console tanpa merestart aplikasi:
1. `Normal` (Default): Menampilkan ringkasan operasi utama (`INFO`, `SUCCESS`, `PROGRESS`, `WARNING`, `ERROR`, `CRITICAL`, `SECTION`, `CANCELLED`, dan `SKIPPED`).
2. `Verbose`: Menginstruksikan setiap modul menghasilkan parameter ilmiah lengkap (header FITS, rincian frame sequence, statistik flat, bobot/sigma stacking, parameter model background, CLAHE tile/clip limit, parameter stretch histogram, dan koordinat titik kontrol kurva).
3. `Debug`: Menginstruksikan setiap modul menghasilkan diagnostik teknis internal (`DEBUG`), seperti path lengkap, ukuran berkas byte, dtype & shape array (`float32`), rentang nilai `[min, max]`, serta rincian eksekusi internal.
- Setiap perubahan Detail Mode dicatat secara eksplisit: `[INFO] [LOGGING] Detail mode changed: NORMAL -> VERBOSE.`.
- `WARNING`, `ERROR`, dan `CRITICAL` selalu ditampilkan pada ketiga mode (`Normal`, `Verbose`, `Debug`).

---

## 22. Contoh Log Lengkap

```text
=== HILALONE APPLICATION STARTUP ===
[20:15:00.102] [INFO] [SYSTEM] HILALONE v1.0.0 initialized. | version=1.0.0, session_id=SES-20261117-201500-9F8A12
[20:15:00.105] [INFO] [SYSTEM] Operating system: Windows. | os_release=10, os_build=10.0.19045
[20:15:00.106] [INFO] [SYSTEM] Architecture: AMD64.
[20:15:00.107] [INFO] [SYSTEM] Python runtime: 3.10.11.
[20:15:00.109] [INFO] [SYSTEM] Qt framework initialized (Qt 6.7.2, PySide6 6.7.2).
[20:15:00.111] [SUCCESS] [SYSTEM] Logging initialized.
[20:15:00.112] [SUCCESS] [SYSTEM] Application startup completed. | Duration: 0.01 s
[20:15:10.420] [INFO] [INPUT] Opening Multiple Images: hilal_001.fits | filename=hilal_001.fits, format=FITS, reader=Astropy FITS Reader, frame_count=4
[20:15:10.422] [INFO] [INPUT] Format: FITS | Reader: Astropy FITS Reader.
[20:15:10.423] [INFO] [INPUT] Resolution: 1920 × 1080 px | Channels: Monochrome (1 channel). | width=1920, height=1080, channels=1
[20:15:10.425] [INFO] [INPUT] Data type: uint16 | Bit depth: 16-bit. | dtype=uint16, bit_depth=16
[20:15:10.430] [SUCCESS] [INPUT] Multiple Images loaded successfully. | filename=hilal_001.fits, frame_count=4, Duration: 0.02 s
=== SEQUENCE VALIDATION ===
[20:15:10.432] [INFO] [SEQUENCE] Total frames detected: 4. | total_frames=4, mode=MULTI
[20:15:10.433] [INFO] [SEQUENCE] Checking structural compatibility...
[20:15:10.435] [SUCCESS] [SEQUENCE] Compatible frames: 4. | compatible_frames=4
[20:15:10.436] [INFO] [SEQUENCE] Incompatible frames: 0.
[20:15:10.437] [INFO] [SEQUENCE] Decoding errors: 0.
[20:15:10.439] [SUCCESS] [VALIDATION] Sequence validation completed. | readiness=READY, Duration: 0.02 s
=== AUTOMATED PROCESSING PIPELINE ===
[20:15:15.100] [INFO] [SESSION] Starting automated processing | Run ID: RUN-20261117-201515-4C7D2E | Profile: BASIC.
=== FLAT FIELD CALIBRATION ===
[20:15:16.210] [SKIPPED] [CALIBRATION] Flat Calibration skipped. | Reason: Disabled by user | reason=Disabled by user
=== IMAGE STACKING ===
[20:15:16.212] [INFO] [STACKING] Starting image integration.
[20:15:16.214] [INFO] [STACKING] Profile: BASIC | Method: ARITHMETIC_MEAN. | profile=BASIC, method=ARITHMETIC_MEAN, input_frames=4, selected_frames=4, excluded_frames=0
[20:15:16.216] [SUCCESS] [STACKING] Image integration completed. | output_dtype=float32, output_dimensions=1920×1080 px (1 ch), Duration: 0.41 s
=== BACKGROUND EXTRACTION ===
[20:15:16.218] [INFO] [BACKGROUND] Starting background modeling | Method: POLYNOMIAL_DEG_1 | Interpolation: 2D Polynomial Surface (degree=1).
[20:15:16.220] [SUCCESS] [BACKGROUND] Background model generated. | gradient_reduction_ratio=89.4%, overcorrection_score=0.012
[20:15:16.221] [SUCCESS] [BACKGROUND] Background extraction completed (subtractive correction on linear branch). | Duration: 0.19 s
=== IMAGE ENHANCEMENT ===
[20:15:16.223] [INFO] [ENHANCEMENT] Method: CLAHE | Status: ENABLED. | clip_limit=0.008, tile_grid_size=8×8, channel_mode=MONOCHROME, input_branch=LINEAR (float32), output_branch=ENHANCED_DERIVED (float32)
[20:15:16.225] [SUCCESS] [ENHANCEMENT] Enhancement completed (scientific linear_result branch preserved unmodified). | noise_amplification_ratio=1.18, Duration: 0.09 s
=== HISTOGRAM TRANSFORMATION ===
[20:15:16.227] [INFO] [HISTOGRAM] Stretch method: LINEAR_MTF | Input branch: ENHANCED_DERIVED -> Output branch: DISPLAY.
[20:15:16.228] [INFO] [HISTOGRAM] Display transformation applies only to DISPLAY branch; scientific linear data remains unchanged.
[20:15:16.230] [SUCCESS] [HISTOGRAM] Display transformation completed. | Duration: 0.05 s
====================================================
              PROCESSING SUMMARY
====================================================
Run ID              : RUN-20261117-201515-4C7D2E
Status              : SUCCESS
Profile             : BASIC
Input frames        : 4
Frames processed    : 4
Frames excluded     : 0
Flat Calibration    : SKIPPED
Image Stacking      : COMPLETED
Background          : COMPLETED
Enhancement         : COMPLETED
Histogram           : COMPLETED
Curve               : NOT USED
Output              : In-memory (Ready to Save)
Duration            : 0.74 s
====================================================
       AUTOMATED PROCESSING COMPLETED
====================================================
[20:15:16.235] [SUCCESS] [SESSION] Automated processing completed successfully. | Run ID: RUN-20261117-201515-4C7D2E | Profile: BASIC | Duration: 0.74 s
```
