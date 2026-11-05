# HILALONE – Development Roadmap (MVP 1.0)

Prinsip: **satu fase kecil → diuji → disetujui → lanjut**. Jangan membuat seluruh aplikasi sekaligus. Setiap fase punya hasil yang bisa dicek.

| Fase | Fokus | Hasil / Kriteria selesai |
|---|---|---|
| 0 | Persiapan | `venv` dibuat, struktur folder, `pyproject`/`requirements`, git, pytest berjalan (tes kosong lulus). Setiap dependency dijelaskan sebelum dipasang |
| 1 | Core & tipe data | Tipe data (`ImageData` mono/RGB, `FrameStack` dengan validasi dimensi+kanal, `ProcessingResult`, `Profile`), konfigurasi profil, logging |
| 2 | Input Manager – gambar | Adapter TIFF/PNG/JPEG, FITS, RAW; validator; uji dengan file sintetis; sumber read-only terbukti (hash) |
| 3 | Output Manager | Penulis linear (FITS/TIFF float) dan visual (PNG/TIFF), laporan JSON, aturan tak menimpa sumber |
| 4 | Stretch & enhancement | MTF otomatis, global contrast → asinh, CLAHE terbatas → adaptif, GHT; uji unit |
| 5 | Background extraction | Polinomial → RBF → robust otomatis; safeguard anti-overcorrection; preview model; uji sintetis |
| 6 | **Pipeline single image** (CLI sederhana tanpa GUI) | Basic/Medium/High pada satu gambar, end-to-end, linear + visual terpisah |
| 7 | Flat-field | Validasi dan penerapan master flat opsional |
| 8 | Input video & multi-image | Ekstraksi frame (PyAV), pengurutan urutan file, cek memori |
| 9 | Cek kompatibilitas | Ukuran, kanal (tolak mono+RGB), orientasi, pergeseran translasi vs frame referensi (hanya mengukur; ambang 1 px; status OK/MELEBIHI_AMBANG/INDETERMINATE), peringatan, pencatatan frame |
| 10 | Stacking | Mean → sigma-clipped → robust berbobot kualitas; peta rejection; tanpa alignment |
| 11 | Pipeline multi-frame | Rangkaian lengkap dengan CLI |
| 12 | GUI | Jendela utama, pemilihan input/profil, tombol Proses, progress, batal, preview, peringatan |
| 13 | Pengujian & dokumentasi | Data nyata, perbandingan antar profil, kriteria penerimaan MVP, panduan pengguna |
| 14 | Packaging (opsional) | Pengemasan `.exe`, uji di mesin bersih |

**Alasan urutan:** Logika dibangun dan diuji **sebelum** GUI (GUI hanya "kulit"). Single image lebih dahulu karena lebih sederhana; multi-frame menambah risiko tertinggi (stacking), jadi dikerjakan setelah dasar stabil. Background extraction diuji lebih awal karena paling berisiko.

## Catatan Perubahan Urutan
- **GUI dasar dan image viewer dikembangkan lebih awal sebagai fondasi Fase 1** (keputusan pengguna): jendela utama, Open/Close Image, viewer, dan panel informasi gambar (PNG/JPG/BMP, TIFF bila didukung Qt). Ini hanya penampil; **tidak ada** pemrosesan citra.
- Tahapan lain **tidak berubah**: Fase 1 (core & tipe data) sampai Fase 11 (pipeline) tetap dikerjakan sesuai tabel. **Fase 12 (GUI penuh)** tetap mencakup pemilihan profil, tombol Proses, progress, batal, preview hasil, dan peringatan; GUI dasar ini menjadi cikal bakalnya.
- Aturan untuk viewer: konversi 8-bit dan rotasi EXIF hanya berlaku pada **preview layar**; data sumber, bit depth asli, dan orientasi asli tetap dicatat dan tidak diubah.

## Keputusan yang Sudah Dikonfirmasi
- Stabilitas posisi = pengukuran translasi saja terhadap frame referensi, ambang awal 1 piksel, status `INDETERMINATE` bila tak andal, tanpa alignment, tanpa frame hilang tanpa catatan.
- Mono tetap mono, RGB tetap RGB; enhancement/stretch luminance-aware; sequence tidak boleh campuran.
- **TIFF memakai `tifffile==2025.5.10`** (versi terakhir yang kompatibel dengan Python 3.10.11). Alasan: Qt memuat TIFF sebagai gambar warna 4 kanal, tidak jujur soal kanal/bit depth, dan menolak gambar besar (batas alokasi 256 MB, mis. TIFF float32 5496×3672). `tifffile` membaca ke array NumPy dengan dtype dan nilai asli.
- **`imagecodecs` ditunda.** Dipasang hanya bila ditemukan TIFF nyata yang tidak terbaca karena kompresi yang butuh codec tambahan (LZW, JPEG, ZSTD, dll.).
- **FITS = prioritas berikutnya setelah TIFF reader selesai dan teruji.** Rencana dependency: `astropy==6.1.7` (kompatibel Python 3.10.11). **Belum dipasang.** Jangan memakai Astropy terbaru tanpa memeriksa kompatibilitas Python; versi dikunci dan diperiksa (`pip install --dry-run`) sebelum instalasi, dan tetap butuh persetujuan.

## Gerbang Keputusan (butuh persetujuan pengguna)
- **Belum diputuskan:** SciPy sebagai dependency tambahan (diputuskan saat Fase 5; sebelum itu tidak dipasang).
- Fase 4: metode luminance-aware yang dipakai (setelah uji sintetis).
- Fase 5: hasil uji background pada contoh hilal nyata.
- Fase 9: validasi ambang 1 piksel dan kriteria `INDETERMINATE` pada data nyata.

## Definisi Selesai tiap Fase
1. Kode kecil, terbaca, dengan penjelasan Indonesia.
2. Tes otomatis lulus.
3. Tidak melanggar `AGENTS.md`.
4. Ringkasan: apa yang dibuat, alasannya, cara mencobanya.

## Langkah Berikutnya
Tinjau empat dokumen, jawab pertanyaan terbuka, lalu mulai **Fase 0**.

