# HILALONE – Software Requirements (MVP 1.0)

Kode: **FR** = kebutuhan fungsional, **NFR** = non-fungsional, **CON** = batasan. Prioritas: M (Must), S (Should).

## 1. Kebutuhan Fungsional

### Input (FR-IN)
- FR-IN-01 (M) Mendukung satu gambar, urutan banyak gambar, dan satu video.
- FR-IN-02 (M) Format gambar: FITS, TIFF, PNG, JPEG, RAW (CR2/CR3/NEF/ARW/DNG dll. via rawpy). Video: MP4, MOV, AVI.
- FR-IN-03 (M) Validasi: file ada, bisa dibaca, dimensi valid, bit-depth dikenali; error jelas dalam Bahasa Indonesia.
- FR-IN-04 (M) Arsitektur adapter agar format baru bisa ditambah tanpa mengubah pipeline.
- FR-IN-05 (M) Urutan file multi-frame ditampilkan dan dapat diurutkan/dikecualikan oleh pengguna.
- FR-IN-06 (S) Mengingat metadata (exposure, ISO, tanggal, header FITS) bila tersedia.

### Konversi (FR-CV)
- FR-CV-01 (M) Smart conversion ke representasi internal float32, mempertahankan sifat linear bila sumber linear (FITS, RAW, TIFF 16-bit).
- FR-CV-02 (M) RAW dibaca **tanpa** auto-brightness, tanpa gamma (linear), pengaturan demosaic dicatat.
- FR-CV-03 (M) Peringatan jika sumber non-linear (JPEG/PNG/video ber-gamma): hasil "linear" hanya pendekatan.
- FR-CV-04 (M) Ekstraksi frame video tanpa mengubah resolusi; pengguna dapat memilih rentang/langkah frame.
- FR-CV-05 (M) **Jenis citra dipertahankan**: monochrome tetap monochrome (H×W), RGB tetap RGB (H×W×3). Dilarang mengubah citra menjadi grayscale. Jenis citra (`mono`/`rgb`) dicatat di metadata.
- FR-CV-06 (M) Bila sumber memiliki jumlah kanal selain 1 atau 3 (mis. RGBA), kanal alfa dibuang dan hal itu dicatat/diperingatkan; kanal lain ditolak dengan pesan jelas.

### Flat-field (FR-FL)
- FR-FL-01 (M) Opsional; aktif hanya bila pengguna memberi master flat.
- FR-FL-02 (M) Validasi master flat: ukuran, jumlah kanal, dan peringatan jika orientasi/bit-depth berbeda. Flat dinormalisasi (rata-rata = 1), nilai ≈0 dilindungi.
- FR-FL-03 (M) Tanpa dark/bias.

### Kompatibilitas multi-frame (FR-CP)
- FR-CP-01 (M) Cek ukuran (tinggi × lebar) dan jumlah kanal identik. **Sequence tidak boleh mencampur mono dan RGB**; jika campuran, stacking diblokir dengan pesan jelas (tidak ada konversi otomatis untuk "menyamakan").
- FR-CP-02 (M) Cek orientasi (mis. EXIF orientation / header) konsisten.
- FR-CP-03 (M) Ukur pergeseran translasi (dx, dy) tiap frame terhadap **frame referensi** (default: frame pertama yang valid; dapat dipilih pengguna). Pengukuran bersifat **baca-saja**: frame tidak digeser, ditransformasi, atau diselaraskan. Pada citra RGB, pengukuran memakai luminans turunan sementara (hanya untuk mengukur; data frame tidak diubah).
- FR-CP-04 (M) **Ambang awal maksimum 1 piksel** (besar pergeseran = √(dx²+dy²)). Di atas ambang → peringatan. Nilai ambang disimpan sebagai konfigurasi dan dicatat di laporan.
- FR-CP-05 (M) Bila ada peringatan: tampilkan dan minta keputusan pengguna (batal / lanjut dengan risiko / kecualikan frame). Tidak ada alignment otomatis. Frame tidak boleh dikeluarkan secara diam-diam: setiap frame yang dikecualikan (oleh pengguna atau rejection) **harus dicatat** beserta alasannya.
- FR-CP-06 (M) Status per frame: `OK` (≤ ambang), `MELEBIHI_AMBANG` (> ambang), atau `INDETERMINATE` (pengukuran tidak dapat dipercaya, mis. puncak korelasi lemah/ambigu, frame hampir kosong atau jenuh, kontras terlalu rendah). `INDETERMINATE` wajib memunculkan peringatan dan diperlakukan seperti peringatan pergeseran (butuh keputusan pengguna); tidak boleh dianggap `OK`.
- FR-CP-07 (M) Laporan memuat: frame referensi, dx/dy tiap frame, ukuran pergeseran, status, ambang, dan keputusan pengguna.

### Stacking (FR-ST)
- FR-ST-01 (M) Wajib untuk multi-frame/video.
- FR-ST-02 (M) Basic: mean. Medium: sigma-clipped mean. High: robust berbobot kualitas dengan rejection (mis. winsorized/ sigma-clip + bobot).
- FR-ST-03 (M) Tidak ada transformasi geometris apa pun.
- FR-ST-03a (M) Pada RGB, stacking dilakukan per kanal dengan keputusan rejection/bobot yang konsisten antar kanal (mis. dihitung dari luminans) agar tidak menimbulkan pergeseran warna. Jenis citra hasil sama dengan masukan.
- FR-ST-04 (M) Pemrosesan hemat memori (per-blok/strip) untuk tumpukan besar.
- FR-ST-05 (M) Metrik kualitas frame (mis. median latar, kontras/gradien global) hanya untuk pembobotan, bukan untuk alignment; dilaporkan ke pengguna.
- FR-ST-06 (S) Peta rejection/jumlah frame efektif per piksel disimpan.

### Background extraction (FR-BG)
- FR-BG-01 (M) Polinomial (derajat 1, 2, dan opsional lebih tinggi dengan batas).
- FR-BG-02 (M) RBF dengan sampel latar terpilih (grid + masking).
- FR-BG-03 (M) Estimasi robust otomatis (pemilihan sampel dengan penolakan outlier, termasuk area terang/bulan).
- FR-BG-04 (M) Anti-overcorrection: batas amplitudo koreksi, penolakan sampel pada objek terang, derajat model dibatasi, peringatan jika model menyerap struktur skala besar (mis. busur hilal).
- FR-BG-05 (M) Preview model background dan gambar sebelum/sesudah.
- FR-BG-06 (M) Mode koreksi: subtraksi (default untuk gradien aditif). Model disimpan sebagai berkas.
- FR-BG-06a (M) Pada RGB, model latar dihitung per kanal (menjaga keseimbangan warna latar); pemilihan sampel latar memakai mask bersama berbasis luminans. Mono dipakai langsung.
- FR-BG-07 (S) Pengguna dapat menonaktifkan atau menggambar area masking.

### Enhancement dan stretch (FR-EN)
- FR-EN-01 (M) Basic: global contrast. Medium: CLAHE terbatas (clipLimit & tile konservatif). High: kontras adaptif.
- FR-EN-02 (M) Tanpa denoise, smoothing, sharpening otomatis.
- FR-EN-03 (M) Histogram transformation: MTF otomatis (Basic), asinh+MTF (Medium), GHT/adaptif (High).
- FR-EN-04 (M) Enhancement/stretch hanya memengaruhi keluaran *visual*, bukan keluaran linear.
- FR-EN-05 (M) Parameter otomatis dicatat dan dapat ditinjau.
- FR-EN-06 (M) **Pendekatan luminance-aware untuk RGB**: enhancement dan histogram transformation dihitung/diterapkan pada luminans, lalu perubahan diterapkan ke ketiga kanal dengan rasio warna dipertahankan (informasi warna tidak dibuang). Tidak ada konversi ke grayscale. Pada mono, operasi langsung pada kanal tunggal. Metode rinci (mis. skala rasio R/G/B terhadap L, atau ruang warna terpisah-luminans) dipilih di Fase 4 dengan uji sintetis, dan dicatat di laporan.
- FR-EN-07 (M) Penanganan nilai di luar rentang akibat penskalaan rasio (clipping) harus dicatat; tidak boleh menyebabkan pergeseran warna diam-diam.

### Ekspor (FR-OUT)
- FR-OUT-01 (M) Keluaran linear (sebelum histogram transformation) dalam FITS dan/atau TIFF 16/32-bit float, terpisah dari visual.
- FR-OUT-02 (M) Keluaran visual (PNG/TIFF 16-bit/JPEG opsional).
- FR-OUT-03 (M) Preview background model, peta rejection, dan laporan proses (JSON/teks).
- FR-OUT-04 (M) File sumber tidak pernah diubah/ditimpa; penamaan unik, tolak menulis ke folder yang sama dengan sumber kecuali subfolder output khusus.
- FR-OUT-05 (M) Header FITS keluaran mencatat riwayat proses.

### GUI (FR-UI)
- FR-UI-01 (M) Pilih file/folder/video, pilih profil, satu tombol "Proses".
- FR-UI-02 (M) Progress bar, tombol batal, log, preview hasil dan background model.
- FR-UI-03 (M) Pemrosesan di thread latar; GUI tidak membeku.
- FR-UI-04 (M) Peringatan kompatibilitas ditampilkan jelas.
- FR-UI-05 (M) GUI tidak berisi logika pemrosesan.

## 2. Kebutuhan Non-Fungsional
- NFR-01 Modular: GUI, input, processing, output terpisah; komunikasi lewat tipe data di `core`.
- NFR-02 Windows 10/11 64-bit, Python 3.10.11 (64-bit; keputusan pengguna) di virtual environment (`venv`) terpisah.
- NFR-03 Hasil deterministik: input + parameter sama → output sama.
- NFR-04 Presisi float32 minimal; tidak ada kuantisasi ke 8-bit sebelum ekspor visual.
- NFR-05 Memori: tidak memuat seluruh video sekaligus bila besar; stacking bertahap.
- NFR-06 Kode memiliki pengujian unit memakai data sintetis.
- NFR-07 Pesan galat dan UI berbahasa Indonesia; kode/komentar dapat dua bahasa tetapi docstring penjelasan dalam Indonesia.
- NFR-08 Logging terstruktur ke file.

## 3. Batasan
CON-01 Tanpa registration/alignment. CON-02 Tanpa KOMBAT. CON-03 Tanpa noise reduction/smoothing/sharpening otomatis. CON-04 Tanpa dark/bias. CON-05 Tanpa deteksi hilal, analisis kuantitatif, AI, klasifikasi. CON-06 Sumber tidak diubah. CON-07 Linear dan visual terpisah.

## 4. Kriteria Penerimaan MVP
1. Setiap format target dapat dibuka dan divalidasi (dengan sampel uji).
2. Pipeline single dan multi menghasilkan `linear` + `visual` terpisah.
3. Input multi-frame tak cocok (ukuran/kanal berbeda, mono+RGB campur, pergeseran > 1 px, atau `INDETERMINATE`) memunculkan peringatan dan tidak diam-diam diproses; tidak ada frame yang hilang tanpa catatan.
3a. Mono tetap mono dan RGB tetap RGB di seluruh pipeline dan keluaran.
4. Hash file sumber sama sebelum dan sesudah proses.
5. Background model dapat dipratinjau; uji sintetis membuktikan gradien tereduksi tanpa menghapus sinyal buatan.
6. Tiga profil menghasilkan konfigurasi sesuai tabel di `project_overview.md`.

## 5. Risiko Teknis

### R1. Stacking tanpa registration (RISIKO TERTINGGI)
| Aspek | Penjelasan | Mitigasi |
|---|---|---|
| Pergeseran bumi/langit | Hilal terletak dekat horizon; rotasi bumi menggeser objek antar frame, dan tracking mount bisa tidak sempurna | Ukur pergeseran (FR-CP-03), ambang jelas, peringatan keras, batasi jumlah/durasi frame yang direkomendasikan |
| Blur hasil stack | Pergeseran > ~1 px melebarkan tepi hilal sehingga detail turun | Laporkan estimasi blur; sarankan memakai sebagian frame |
| Sigma-clipping membuang sinyal | Objek bergeser dianggap outlier lalu ditolak, atau hilal dianggap noise | Batas rejection maksimum; simpan peta rejection; High memakai bobot bukan hanya penolakan |
| Atmosfer (seeing) | Frame berbeda terdistorsi secara lokal; tanpa registration tidak bisa dikoreksi | Bobot kualitas; dokumentasikan keterbatasan |
| Video (handheld/tripod goyang) | Pergeseran besar antar frame | Cek stabilitas ketat; blok bila melebihi ambang kecuali pengguna menyetujui |
| Frame video terkompresi | Artefak kompresi/inter-frame, gamma non-linear | Peringatan; rekomendasikan RAW/FITS |
| Memori | Banyak frame besar | Proses per-blok |
| Kesalahan ilmiah | Hasil stack tampak bagus namun menyesatkan | Laporan wajib berisi jumlah frame, frame ditolak, pergeseran |

Keputusan (dikonfirmasi pengguna): pengukuran pergeseran translasi terhadap frame referensi (mis. phase correlation) **bukan alignment**; ia hanya membaca, tidak mengubah frame. Ambang awal 1 piksel; di atasnya → peringatan; pengukuran tak andal → `INDETERMINATE` + peringatan. Frame tidak boleh dibuang tanpa catatan.

Keterbatasan pengukuran yang harus diwaspadai: (a) hanya translasi — rotasi/skala/distorsi lokal tidak terukur; (b) objek redup dan latar rata membuat korelasi lemah → `INDETERMINATE`; (c) akurasi sub-piksel bergantung metode dan noise, sehingga ambang 1 piksel perlu divalidasi dengan data nyata di Fase 9; (d) pergeseran kecil antar frame dapat menumpuk menjadi blur walau tiap frame ≤ 1 px terhadap referensi — pergeseran maksimum dan sebarannya dilaporkan.

### R2. Background extraction pada citra hilal (RISIKO TINGGI)
| Risiko | Penjelasan | Mitigasi |
|---|---|---|
| Overcorrection | Hilal tipis, redup, dan melengkung, bisa terserap model (terutama RBF/polinomial tinggi) | Derajat dibatasi, regularisasi/smoothing RBF, batas amplitudo, deteksi penyerapan struktur |
| Sampel tercemar | Matahari terbenam/langit senja, awan, bulan sabit, dan tepi terang masuk sebagai sampel latar | Masking berbasis kecerahan dan gradien, sigma-rejection iteratif |
| Gradien senja kuat dan non-polinomial | Langit dekat horizon bergradien tajam vertikal | Medium/High memakai RBF/robust; ukuran sampel cukup |
| Efek tepi RBF | Ekstrapolasi tak stabil di sudut | Sampel sampai tepi, batas nilai model |
| Banyak profil, hasil beda | Pengguna bingung | Preview model, laporan |
| Penguatan noise | Subtraksi latar + stretch kuat menonjolkan noise | Tidak ada denoise (larangan); stretch konservatif, peringatan |
| Ketergantungan pada flat | Tanpa flat, vignetting tampak sebagai gradien dan bisa dikoreksi tidak tepat | Gunakan flat bila ada; subtraksi hanya untuk gradien aditif |

### R3. Risiko lain
- **Linearitas data**: JPEG/video sudah di-gamma; "linear" tidak benar-benar linear. → peringatan, label di metadata.
- **RAW**: demosaic dan white balance memengaruhi linearitas. → parameter tetap & dicatat.
- **Citra warna (diputuskan)**: jenis asli dipertahankan; enhancement/stretch luminance-aware. Risiko: penskalaan rasio dapat menjenuhkan kanal atau menguatkan noise warna pada latar gelap. → clipping dicatat, uji sintetis di Fase 4, tanpa denoise (larangan).
- **Sequence campuran mono/RGB**: ditolak (FR-CP-01).
- **Stretch otomatis tidak stabil** pada citra hampir gelap. → batas nilai, uji sintetis.
- **PySide6 dan thread**: operasi berat di GUI thread membuat aplikasi membeku. → worker thread.
- **Packaging** (PyInstaller) dengan rawpy/PyAV/OpenCV bisa rumit. → uji packaging dini (di luar MVP bila perlu).
- **Lisensi**: PySide6 (LGPL), PyAV/FFmpeg, LibRaw — perlu diperiksa saat distribusi.
- **Pemula**: kompleksitas. → fase kecil, tiap fase diuji sebelum lanjut.

