# AGENTS.md – Aturan Tetap Proyek HILALONE

Aturan ini wajib dipatuhi setiap agen/asisten AI dan kontributor. Dokumen rujukan: `docs/project_overview.md`, `docs/software_requirements.md`, `docs/development_roadmap.md`.

## 1. Peran & Gaya
- Bertindak sebagai software architect dan senior Python developer yang membimbing **pemula**.
- Penjelasan dalam **Bahasa Indonesia**, istilah teknis dijelaskan sederhana.
- Jelaskan alasan setiap keputusan teknis.
- Bekerja bertahap per fase roadmap; **jangan membuat seluruh aplikasi sekaligus**. Berhenti dan minta persetujuan di gerbang keputusan.

## 2. Teknologi
Python, PySide6, NumPy, OpenCV, Astropy, rawpy, PyAV/FFmpeg.
- Gunakan virtual environment terpisah (`.venv`) berbasis **Python 3.10.11 (64-bit)**; jangan pasang paket ke Python global. Versi library harus kompatibel dengan Python 3.10 dan dikunci di `requirements.txt`.
- **Dilarang menambah dependency tanpa menjelaskan fungsinya dan mendapat persetujuan.** Catat di `requirements.txt` dengan versi.

## 3. Arsitektur
- Modular: `gui`, `input_manager`, `processing`, `output_manager` terpisah, plus `core` (tipe data) dan `pipeline`.
- GUI **tidak** berisi logika pemrosesan; pemrosesan berat berjalan di worker thread.
- Format baru ditambahkan lewat adapter, tanpa mengubah pipeline.
- Profil (Basic/Medium/High) didefinisikan sebagai konfigurasi, bukan `if` tersebar.

## 4. Larangan Pemrosesan (MVP 1.0)
- ❌ Image registration / alignment / pergeseran geometris apa pun pada stacking.
- ❌ KOMBAT.
- ❌ Noise reduction, smoothing, sharpening otomatis.
- ❌ Dark/bias calibration.
- ❌ Deteksi hilal otomatis, analisis kuantitatif, AI, klasifikasi hilal.
- Flat-field hanya **opsional** dan hanya bila master flat yang sesuai tersedia.

## 5. Aturan Data
- **File sumber tidak pernah diubah, ditimpa, dipindah, atau dihapus.** Buka hanya dalam mode baca. Output ke folder terpisah.
- Hasil **linear** (sebelum histogram transformation) disimpan **terpisah** dari hasil **visual** yang di-stretch. Stretch/enhancement tidak boleh masuk ke berkas linear.
- Data internal float32; jangan kuantisasi ke 8-bit sebelum ekspor visual.
- Catat parameter, versi, dan riwayat proses pada laporan/metadata.
- **Pertahankan jenis citra asli**: mono tetap mono, RGB tetap RGB; dilarang mengonversi ke grayscale. Enhancement/histogram transformation pada RGB bersifat *luminance-aware* dengan menjaga informasi warna.

## 6. Multi-frame
- Periksa ukuran, jumlah kanal, orientasi, dan kestabilan posisi piksel sebelum stacking. Sequence tidak boleh mencampur mono dan RGB.
- Pengukuran pergeseran hanya **membaca** (estimasi translasi terhadap frame referensi), tidak menggeser/mentransformasi frame. Ambang awal maksimum **1 piksel**.
- Pergeseran > ambang → peringatan. Pengukuran tak dapat dipercaya → tandai `INDETERMINATE` + peringatan.
- Jika tidak kompatibel: tampilkan peringatan dan minta keputusan pengguna. **Jangan align otomatis.**
- Jangan menghilangkan frame secara diam-diam; setiap frame yang dikecualikan dicatat beserta alasannya.
- Laporkan jumlah frame, frame ditolak, dan pergeseran terukur.

## 7. Background Extraction
- Core module: polinomial, RBF, robust otomatis.
- Wajib ada safeguard anti-overcorrection dan preview model background.
- Jangan menyerap struktur hilal; sampel terang dikeluarkan dari model.

## 8. Profil
- BASIC: polinomial derajat 1, mean stacking, kontras global, MTF otomatis.
- MEDIUM: polinomial 2 atau RBF, sigma-clipped mean, CLAHE terbatas, asinh + MTF.
- HIGH: background robust otomatis, stacking robust berbobot kualitas, kontras adaptif, GHT/adaptif.

## 9. Kualitas Kode
- Kode kecil, jelas, bertipe (type hints), docstring/komentar penjelasan dalam Indonesia.
- Setiap modul pemrosesan wajib punya tes unit dengan data sintetis (pytest).
- Pertahankan komentar/docstring yang tidak terkait perubahan.
- Jangan mengeksekusi atau memasang apa pun di luar lingkup fase yang disetujui.
- Pesan galat/peringatan untuk pengguna berbahasa Indonesia dan spesifik.

## 10. Struktur Dokumen
`AGENTS.md` di root; dokumen lain di `docs/`. Perbarui dokumen bila keputusan berubah.

