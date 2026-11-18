# HILALONE — Standar Scientific Processing Timeline & Report (`HILALONE_PROCESSING_REPORT_STANDARD.md`)

**Aplikasi**: HILALONE — Automated Hilal Image Processing  
**Versi Aplikasi**: 1.1.3  
**Versi Skema Laporan**: `2.0` (`REPORT_SCHEMA_VERSION = "2.0"`)  
**Modul Sumber**: `src/hilalone/processing/processing_history.py`, `src/hilalone/core/logging/workflow_timeline.py`, `src/hilalone/core/logging/aligned_summary.py`, & `src/hilalone/output_manager/pipeline_writer.py`  
**Prinsip Utama**: *"Enhance the Signal, Never Invent the Signal."*

---

## 1. Tujuan Processing Report

Sistem **HILALONE Scientific Processing Timeline & Report (Schema v2.0)** dirancang untuk merekam jejak audit ilmiah (*scientific data provenance*) secara utuh dari awal hingga akhir sesi pengolahan citra:
- **DARI**: Pengguna pertama kali menekan tombol *Open Image* (atau memilih sequence sumber citra).
- **HINGGA**: Berkas foto hasil pemrosesan berhasil ditulis dan diverifikasi di penyimpanan, diikuti pembuatan berkas laporan JSON pendamping (`*_processing_report.json`).

Laporan ini menjawab empat pertanyaan ilmiah utama secara objektif:
1. **DATA**: Citra atau sequence apa yang diproses, bagaimana struktur piksel dan metadatanya, tanpa menduplikasi nama berkas kontainer video/SER?
2. **PROCESS**: Metode, rumus, dan parameter aktual apa yang diterapkan pada setiap subproses, serta cabang data mana yang dihasilkan?
3. **TIME**: Kapan setiap interaksi pengguna dan operasi komputasi dimulai/selesai, berapa lama durasi tiap tahap, berapa lama aplikasi berada dalam kondisi *idle* menunggu tindakan berikutnya, dan berapa total waktu *end-to-end*?
4. **OUTPUT**: Berkas apa yang dihasilkan, di mana disimpan, berapa ukurannya, berapa lama dialog penyimpanan vs penulisan disk aktual, dan apakah berkas terverifikasi di disk?

---

## 2. Arsitektur Schema v2.0

Setiap berkas `*_processing_report.json` disusun dalam struktur JSON UTF-8 berindentasi 2 spasi yang terdiri atas bagian-bagian utama berikut:

```json
{
  "report_metadata": {},
  "session_information": {},
  "source_data": {},
  "user_interaction_timeline": [],
  "timeline_interpretation_note": "...",
  "workflow_idle_intervals": [],
  "processing_pipeline": {},
  "scientific_data_branches": {},
  "output_information": {},
  "timing_summary": {},
  "human_readable_timeline": [],
  "human_readable_summary": [],
  "warnings": [],
  "scientific_notes": []
}
```

Seluruh interaksi pengguna dipisahkan secara tegas dari parameter algoritma ilmiah maupun durasi komputasi backend.

---

## 3. Report Metadata (`report_metadata`)

Mencatat identitas unik dokumen laporan:
- `report_name`: `"HILALONE Scientific Processing Report"`
- `schema_version`: `"2.0"`
- `report_id`: ID unik per laporan (`RPT-YYYYMMDD-HHMMSS-XXXXXX`), tidak pernah statis.
- `run_id`: ID unik eksekusi pemrosesan (`RUN-YYYYMMDD-HHMMSS-XXXXXX`).
- `generated_at`: Timestamp ISO-8601 zona waktu lokal saat laporan dibuat (`YYYY-MM-DDTHH:MM:SS.mmm+HH:MM`).
- `generated_at_utc`: Timestamp referensi UTC (`YYYY-MM-DDTHH:MM:SS.mmmZ`).
- `application`: `"HILALONE"`
- `application_version`: Versi aplikasi aktif.

---

## 4. Session Information (`session_information`)

Merekam identitas sesi dan kronologi utama:
- `session_id`: ID sesi aplikasi (`SES-YYYYMMDD-HHMMSS-XXXXXX`).
- `run_id`: ID eksekusi pemrosesan aktif.
- `application_version`: Versi HILALONE.
- `operating_system`: Nama dan versi sistem operasi.
- `system_architecture`: Arsitektur prosesor (`AMD64` / `x64`).
- `python_version`: Versi runtime Python (`3.10.11`).
- `processing_profile`: Profil pemrosesan (`BASIC`, `MEDIUM`, `HIGH`).
- `input_mode`: Mode masukan (`SINGLE`, `MULTI`, `VIDEO`, `SER`).
- `session_start_timestamp`: Waktu ISO-8601 lokal saat pengguna pertama kali memulai pembukaan sumber citra pada sesi tersebut.
- `session_end_timestamp`: Waktu ISO-8601 lokal saat berkas foto hasil selesai ditulis dengan sukses ke disk.
- `final_status`: Status akhir (`SUCCESS`, `PARTIAL`, `FAILED`, `CANCELLED`).
- `report_generation_note`: Penjelasan eksplisit bahwa laporan dibuat setelah berkas foto hasil berhasil disimpan dan diverifikasi di disk.
- `user_selected_configuration`: Konfigurasi pemrosesan yang dipilih pengguna.

---

## 5. Source Data & Deduplikasi Sumber (`source_data`)

Memisahkan informasi sumber citra dari parameter pemrosesan dan **mencegah duplikasi nama berkas kontainer**:
- `input_mode`: Mode input (`SINGLE`, `MULTI`, `VIDEO`, `SER`).
- `file_count`: Jumlah berkas sumber unik di disk.
- `total_decoded_frames`: Jumlah total frame yang didekode/dimuat.
- `resolution`, `width`, `height`, `channels`, `dtype`, `bit_depth`, `is_cfa_mosaic`, `cfa_pattern`.
- `files`: Daftar berkas sumber unik. Setiap item memiliki:
  - `source_id`: `"SOURCE_001"`, `"SOURCE_002"`, dst.
  - `filename`, `format`, `decoded_frame_count`, `resolution`, `width`, `height`, `channels`, `dtype`, `bit_depth`.
  - Metadata spesifik yang benar-benar tersedia pada berkas asli (`fits_metadata`, `raw_metadata`, `video_metadata`, `ser_metadata`).
- **Aturan Deduplikasi Video/SER**: Jika 1 berkas video (`hilal.avi`) menghasilkan 52 frame, `files` hanya berisi **1 entri** dengan `"decoded_frame_count": 52` dan `"total_decoded_frames": 52` (nama berkas tidak diulang 52 kali).

---

## 6. User Interaction Timeline (`user_interaction_timeline`)

Merekam kronologi tindakan pengguna yang bermakna bagi workflow pengolahan citra serta operasi backend:
- Kategori `event_type`:
  - `USER_ACTION`: Saat pengguna menekan tombol atau mengubah pengaturan.
  - `OPERATION_STARTED`: Saat backend benar-benar memulai komputasi/pembacaan/penulisan.
  - `OPERATION_COMPLETED`: Saat backend menyelesaikan tugas.
  - `OPERATION_FAILED`: Saat operasi gagal.
  - `OPERATION_SKIPPED`: Saat tahapan opsional sengaja dilewati.
- Field setiap event:
  - `sequence`: Nomor urut kronologis (`1, 2, 3, ...`).
  - `event_id`: `"EVT-0001"`, dst.
  - `event_type`: Kategori event.
  - `action`: Kode tindakan terstandar (`OPEN_IMAGE_CLICKED`, `FILE_SELECTION_COMPLETED`, `APPLY_FLAT_ENABLED`, `FLAT_FILE_SELECTED`, `START_AUTOMATIC_PROCESSING_CLICKED`, `SAVE_CLICKED`, `SAVE_DIALOG_OPENED`, `OUTPUT_FILENAME_CONFIRMED`, `OUTPUT_WRITE_STARTED`, `OUTPUT_WRITE_COMPLETED`, dll.).
  - `timestamp` & `timestamp_utc`.
  - `module`: Modul terkait (`INPUT`, `CALIBRATION`, `FLAT`, `SESSION`, `DISPLAY`, `CURVE`, `OUTPUT`, dll.).
  - `action_result`: `"RECORDED"`, `"STARTED"`, `"COMPLETED"`, `"FAILED"`, `"SKIPPED"`, atau `"CANCELLED"`.
  - `interval_since_previous_action_ms` & `interval_since_previous_action_display`: Selang waktu sejak `USER_ACTION` sebelumnya (`null` untuk aksi pertama).
  - `action_to_operation_latency_ms` & `action_to_operation_latency_display`: Latensi dari klik tombol pemicu hingga `OPERATION_STARTED` di backend.
  - `duration_ms` & `duration_display`: Durasi operasi backend (untuk `OPERATION_COMPLETED`).
- **Catatan Interpretasi Ilmiah (`timeline_interpretation_note`)**: Selang waktu antartindakan pengguna (`interval_since_previous_action_ms`) merupakan waktu berlalu (*elapsed time*) yang dapat mencakup pembacaan berkas, pemrosesan backend, atau ketidakaktifan pengguna — bukan pengukuran psikologis "waktu berpikir".

---

## 7. Workflow Idle Interval (`workflow_idle_intervals`)

Mencatat secara terpisah periode ketika **tidak ada operasi backend aktif** dan aplikasi menunggu tindakan workflow berikutnya dari pengguna:
- `interval_id`: `"IDLE-0001"`, dst.
- `interval_type`: `"WORKFLOW_IDLE_INTERVAL"`
- `started_at`: Timestamp saat operasi sebelumnya selesai.
- `ended_at`: Timestamp saat tindakan pengguna berikutnya dilakukan.
- `duration_ms` & `duration_display`: Durasi tunggu dalam milidetik dan format `"0.00 s"`.
- `preceding_event` & `following_action`.
- `app_window_state`: Status jendela (`"FOREGROUND"` / `"BACKGROUND"`).
- `description`: `"Application was not processing and was waiting for the next workflow action."`
- Jeda penjadwalan mikro di bawah ambang (`< 25 ms`) diabaikan agar tidak menghasilkan derau catatan palsu, dan tidak pernah dicatat selama backend sedang memproses data.

---

## 8. Processing Pipeline (`processing_pipeline`)

Memisahkan seluruh 11 subproses dengan skema seragam (`stage_id`, `stage_name`, `status`, `started_at`, `completed_at`, `duration_ms`, `duration_display`, `input`, `parameters`, `output`, `metrics`, `warnings`, serta `reason` bila `SKIPPED`):
1. `input_loading`: Durasi pembacaan/dekode sumber citra aktual.
2. `input_validation`: Durasi pemeriksaan kompatibilitas struktural, jumlah frame valid, dan daftar frame dikecualikan beserta alasannya.
3. `flat_calibration`: Status, jumlah Light frame, jumlah Flat frame, metode Master Flat, rumus normalisasi, statistik piksel invalid, dan durasi kalibrasi (`duration_ms: null` jika `SKIPPED`).
4. `master_flat_generation`: Metode agregasi, normalisasi, jumlah flat masukan, dimensi keluaran, tipe data, piksel invalid, dan durasi pembuatan.
5. `stacking`: Profil, metode (`ARITHMETIC_MEAN`, `SIGMA_CLIPPED_MEAN`, `QUALITY_WEIGHTED_ROBUST`), frame dipilih/diintegrasikan/dikecualikan, metode penolakan outlier, metode pembobotan, tipe data keluaran (`float32`), dimensi, dan durasi.
6. `background_extraction`: Metode, derajat polinomial (jika polinomial digunakan), ukuran grid, interpolasi, parameter RBF (jika RBF digunakan), jumlah sampel diterima/ditolak, piksel ROI dilindungi, gradien sebelum/sesudah, residual RMS, skor overcorrection, dan durasi.
7. `image_enhancement`: Metode (`CLAHE`), backend, `clip_limit`, `tile_grid`, pemrosesan kanal, metrik derau sebelum/sesudah, kontras lokal sebelum/sesudah, dan durasi.
8. `histogram_transformation`: Metode stretch, `vmin`, `vmax`, batas persentil, parameter MTF, parameter Asinh (hanya jika Asinh digunakan), parameter GHS (hanya jika GHS digunakan), cabang input/output, dan durasi.
9. `curve_processing`: Dicatat `COMPLETED` hanya apabila Curve diterapkan pada sesi tersebut (beserta kanal, jumlah titik kontrol, koordinat titik kontrol, dan durasi); jika tidak digunakan berstatus `SKIPPED` dengan `duration_ms: null`.
10. `display_generation`: Mode tampilan, cabang tampilan, normalisasi, tipe data, rentang keluaran, dan durasi.
11. `output_preparation`: Persiapan cabang data dan proteksi anti-overwrite sebelum penulisan berkas.

---

## 9. Output Save Transaction (`output_information`)

Memisahkan secara akurat waktu interaksi dialog dari waktu penulisan berkas ke disk:
- `transaction_id`: ID unik transaksi penyimpanan (`TX-YYYYMMDD-HHMMSS-XXXXXX`).
- `run_id`: ID eksekusi pemrosesan terkait.
- `save_clicked_at`, `save_dialog_opened_at`, `save_dialog_confirmed_at`, `output_write_started_at`, `output_write_completed_at`.
- `save_dialog_duration_ms` & `save_dialog_duration_display`: Waktu dialog pemilihan nama/lokasi berkas terbuka.
- `image_write_duration_ms` & `image_write_duration_display`: Waktu aktual backend menulis dan memverifikasi berkas foto di disk.
- `save_transaction_duration_ms` & `save_transaction_duration_display`: Total waktu dari tombol Save ditekan hingga berkas foto selesai ditulis.
- `output_artifacts`: Daftar artefak foto yang disimpan (`artifact_id`, `filename`, `format`, `save_target`, `data_type`, `bit_depth`, `dimensions`, `path`, `file_size_bytes`, `started_at`, `completed_at`, `duration_ms`, `duration_display`, `save_status`, `verified_on_disk`).
- `companion_json_report`: Metadata keterkaitan laporan JSON dengan artefak foto (`report_id`, `report_filename`, `report_path`, `referenced_artifact_id`, `referenced_image_filename`, `referenced_image_format`, `image_completed_at`, `run_id`).

---

## 10. Timing Summary (`timing_summary`)

Menyajikan ringkasan waktu terpadu:
- `end_to_end_elapsed_ms` / `end_to_end_elapsed_display`: Total waktu sejak *Open Image* diklik hingga foto hasil selesai disimpan.
- `input_loading_ms` / `input_loading_display`: Waktu pemuatan sumber citra.
- `processing_compute_sum_ms` / `processing_compute_sum_display`: Akumulasi durasi tahapan komputasi aktif.
- `automated_pipeline_elapsed_ms` / `automated_pipeline_elapsed_display`: Waktu aktual eksekusi pipeline otomatis.
- `workflow_idle_total_ms` / `workflow_idle_total_display`: Total waktu saat aplikasi menunggu tindakan pengguna tanpa proses backend aktif.
- `user_action_interval_total_ms` / `user_action_interval_total_display`: Total selang waktu antartindakan pengguna (dapat tumpang tindih dengan pemuatan/pemrosesan).
- `save_dialog_duration_ms` / `save_dialog_duration_display`: Durasi dialog Save File terbuka.
- `image_write_duration_ms` / `image_write_duration_display`: Durasi penulisan berkas foto ke disk.
- `metric_definitions`: Kamus penjelasan definisi setiap metrik waktu.

---

## 11. Scientific Data Branches (`scientific_data_branches`)

Mempertahankan pemisahan ketat tiga cabang data ilmiah:
1. `linear_result`: `dtype: "float32"`, `shape`, `min`, `max`, `nature: "SCIENTIFIC_LINEAR_FLOAT32"`, `stage_origin: "BACKGROUND_EXTRACTION"`.
2. `enhanced_result`: `dtype: "float32"`, `shape`, `min`, `max`, `nature: "DERIVED_NONLINEAR_FLOAT32"`, `stage_origin: "IMAGE_ENHANCEMENT_CLAHE"`.
3. `display_result`: `dtype: "float32"`, `shape`, `min`, `max`, `nature: "DISPLAY_NORMALIZED_0_TO_1"`, `stage_origin: "HISTOGRAM_TRANSFORMATION"`.

---

## 12. Standar Timestamp, Durasi, dan Tipografi Ringkasan

- **Timestamp Kejadian**: ISO-8601 milidetik dengan offset zona waktu sistem pengguna (`2026-11-18T10:14:13.125+07:00`).
- **Perhitungan Durasi**: Seluruh durasi dihitung menggunakan *monotonic clock* (`time.perf_counter()`), disimpan presisi penuh dalam `*_ms`, dan ditampilkan untuk manusia dalam format seragam **`0.00 s`** (atau `Duration: 0.00 s` pada baris log tunggal).
- **Tipografi Tiga Kolom Sejajar (`format_aligned_summary`)**:
  - Seluruh blok ringkasan manusia (`PROCESSING SUMMARY`, `OUTPUT SAVE SUMMARY`, berkas `.log`/`.txt`, dan `human_readable_summary`) menggunakan fungsi terpusat `format_aligned_summary()` dengan:
    1. Kolom `LABEL` rata kiri dengan lebar dinamis mengikuti label terpanjang di seluruh blok.
    2. Kolom `SEPARATOR` (` : `) sejajar vertikal sempurna di seluruh bagian (`SESSION INFORMATION`, `INPUT INFORMATION`, `PROCESSING RESULTS`, `OUTPUT INFORMATION`, `TIME SUMMARY`).
    3. Kolom `VALUE` dimulai pada posisi horizontal yang sama, dengan *line wrapping* baris lanjutan tepat di bawah kolom `VALUE`.

---

## 13. Output Pairing & Penanganan Kegagalan

- Setiap penyimpanan berkas citra `nama_berkas.<ext>` secara otomatis menghasilkan pasangan `nama_berkas_processing_report.json` di folder yang sama.
- Apabila terjadi kegagalan I/O saat menulis laporan JSON setelah foto berhasil disimpan:
  - Foto hasil yang sudah tersimpan **tidak pernah dihapus**.
  - Sistem mencatat `WARNING` pada modul `OUTPUT` bahwa foto berhasil disimpan tetapi laporan JSON pendamping gagal dibuat, serta mengembalikan `(saved_image_path, None)`.

---

## 14. Privasi & Keamanan Data Pengguna

- Sistem tidak pernah merekam gerakan mouse, seluruh ketikan keyboard, isi clipboard, password, maupun token/kredensial.
- Seluruh laporan disimpan secara lokal di perangkat pengguna dan tidak pernah dikirim ke server eksternal.

---

## 15. Backward Compatibility (`v1.0` -> `v2.0`)

- Fungsi `load_processing_report(path_or_dict)` di `src/hilalone/processing/processing_history.py` mendukung pembacaan laporan Schema `2.0` maupun arsip laporan Schema `1.0` lama.
- Selain menyediakan 9 bagian utama Schema `2.0`, dokumen JSON `v2.0` juga mempertahankan alias tingkat atas (`profile`, `input_mode`, `source_file_names` yang sudah dideduplikasi, `data_branches`, `flat_calibration`, `automatic_stacking`, `background_extraction`, `image_enhancement`, `histogram_transformation`, `stage_execution_history`) sehingga modul atau skrip analisis yang membaca kunci `v1.0` tetap berjalan tanpa perubahan.

---

## 16. Contoh Ringkasan Teks Terformat (`format_aligned_summary`)

```text
======================================================
                  PROCESSING SUMMARY
======================================================

SESSION INFORMATION
------------------------------------------------------
Run ID                    : RUN-20261118-101413-B01F87
Session ID                : SES-20261118-101000-A1B2C3
Status                    : SUCCESS
Profile                   : BASIC
Input mode                : VIDEO
Session started           : 2026-11-18T10:10:00.120+07:00
Session completed         : 2026-11-18T10:14:19.160+07:00

INPUT INFORMATION
------------------------------------------------------
Input files               : hilal.avi
Input frames              : 52
Compatible frames         : 52
Incompatible frames       : 0
Frames processed          : 52
Frames excluded           : 0

PROCESSING RESULTS
------------------------------------------------------
Flat Calibration          : SKIPPED
Master Flat               : SKIPPED
Image Stacking            : COMPLETED (ARITHMETIC_MEAN)
Background Extraction     : COMPLETED (POLYNOMIAL_DEG_1)
Image Enhancement         : COMPLETED (CLAHE)
Histogram Transformation  : COMPLETED (LINEAR_MTF)
Curve Processing          : NOT USED

OUTPUT INFORMATION
------------------------------------------------------
Output filename           : hilal_linear_basic.fits
Output format             : FITS
Output location           : C:\Hilalone\results\
                            hilal_linear_basic.fits
Data type                 : float32
Save status               : SAVED

TIME SUMMARY
------------------------------------------------------
Input loading duration    : 0.18 s
Processing duration       : 1.42 s
Workflow idle duration    : 4.50 s
Save dialog duration      : 1.20 s
Image write duration      : 0.03 s
Total end-to-end duration : 7.33 s
======================================================
            AUTOMATED PROCESSING COMPLETED
======================================================
```

---

## 17. Daftar Penjelasan Field Utama Schema v2.0

| Bagian | Field Utama | Tipe | Penjelasan |
| :--- | :--- | :--- | :--- |
| `report_metadata` | `report_id`, `run_id`, `schema_version`, `generated_at` | `object` | Identitas unik laporan (`"2.0"`), Run ID, dan waktu pembuatan ISO-8601. |
| `session_information` | `session_id`, `session_start_timestamp`, `session_end_timestamp`, `user_selected_configuration` | `object` | Informasi lingkungan OS/Python, waktu awal buka citra hingga selesai simpan foto, dan konfigurasi pilihan pengguna. |
| `source_data` | `input_mode`, `file_count`, `total_decoded_frames`, `files` | `object` | Daftar berkas sumber unik (`SOURCE_001`, dst.) tanpa duplikasi nama kontainer video/SER. |
| `user_interaction_timeline` | `sequence`, `event_id`, `event_type`, `action`, `timestamp`, `interval_since_previous_action_ms` | `array` | Urutan kronologis tindakan pengguna dan operasi backend beserta latensi mulainya operasi. |
| `workflow_idle_intervals` | `interval_id`, `started_at`, `ended_at`, `duration_ms`, `duration_display` | `array` | Daftar periode saat aplikasi tidak menjalankan proses backend dan menunggu aksi berikutnya. |
| `processing_pipeline` | `input_loading` .. `output_preparation` (11 tahap) | `object` | Detail waktu, input, parameter aktual, output, metrik, dan peringatan untuk setiap tahapan. |
| `scientific_data_branches` | `linear_result`, `enhanced_result`, `display_result` | `object` | Statistik (`dtype`, `shape`, `min`, `max`, `nature`, `stage_origin`) ketiga cabang data ilmiah. |
| `output_information` | `transaction_id`, `save_dialog_duration_ms`, `image_write_duration_ms`, `output_artifacts`, `companion_json_report` | `object` | Rincian transaksi penyimpanan foto dan keterkaitannya dengan laporan JSON pendamping. |
| `timing_summary` | `end_to_end_elapsed_ms`, `input_loading_ms`, `processing_compute_sum_ms`, `workflow_idle_total_ms`, `image_write_duration_ms` | `object` | Ringkasan metrik waktu utama dalam milidetik numerik dan string `"0.00 s"`. |
