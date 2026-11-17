import { siteConfig } from "./siteConfig";

export type VerificationStatus = "TERUJI" | "PARSIAL" | "DIRENCANAKAN";

export type FeatureCategory =
  | "Semua"
  | "Input & Sequence"
  | "Kalibrasi & Stacking"
  | "Background & Stretch"
  | "Analisis, Log & Ekspor";

export interface FeatureItem {
  readonly id: string;
  readonly name: string;
  readonly category: Exclude<FeatureCategory, "Semua">;
  readonly iconName:
    | "Files"
    | "FileCode2"
    | "Image"
    | "Camera"
    | "Film"
    | "Images"
    | "FolderOpen"
    | "ListChecks"
    | "Info"
    | "Sparkles"
    | "SlidersHorizontal"
    | "Layers"
    | "Gauge"
    | "ScanLine"
    | "Contrast"
    | "BarChart3"
    | "Activity"
    | "Terminal"
    | "FileOutput"
    | "Moon";
  readonly description: string;
  readonly benefit: string;
  readonly status: VerificationStatus;
  readonly statusNote?: string;
}

export interface ScreenshotItem {
  readonly id: string;
  readonly title: string;
  readonly category: string;
  readonly src1600: string;
  readonly src800: string;
  readonly alt: string;
  readonly caption: string;
  readonly isSyntheticSample: boolean;
}

export interface WorkflowStep {
  readonly stepNumber: string;
  readonly code: string;
  readonly title: string;
  readonly modeTag: "Wajib" | "Multi-Frame / Video / SER" | "Opsional";
  readonly summary: string;
  readonly technicalDetail: string;
  readonly outputs: string;
}

export interface IntegrityLayer {
  readonly code: string;
  readonly title: string;
  readonly dtype: string;
  readonly role: string;
  readonly guarantee: string;
}

export interface RoadmapStage {
  readonly id: string;
  readonly stage: string;
  readonly title: string;
  readonly statusLabel: string;
  readonly statusKind: "active" | "planned";
  readonly summary: string;
  readonly items: readonly { label: string; badge: string }[];
}

export interface TechSpecRow {
  readonly category: string;
  readonly parameter: string;
  readonly detail: string;
  readonly verificationTag: string;
}

export interface FaqItem {
  readonly id: string;
  readonly question: string;
  readonly answer: string;
}

export const HERO_HIGHLIGHTS = [
  { label: "Presisi Internal", value: "float32 Linear" },
  { label: "Profil Otomatis", value: "Basic · Medium · High" },
  { label: "Unit Test Pytest", value: "227 Passed" },
  { label: "Geometri Stacking", value: "Tanpa Warping / Align" },
] as const;

export const ABOUT_PILLARS = [
  {
    title: "Reproducibility",
    description:
      "Tiga profil pemrosesan (Basic, Medium, High) didefinisikan secara deklaratif dengan riwayat parameter dan log berstempel waktu yang dapat ditinjau ulang.",
  },
  {
    title: "Data Integrity",
    description:
      "Berkas sumber selalu dibuka dalam mode baca-saja (read-only) serta dilindungi hash SHA-256, tanpa menimpa maupun memodifikasi citra asli.",
  },
  {
    title: "Scientific Processing",
    description:
      "Data linear ilmiah (FITS/TIFF float32) dipisahkan sepenuhnya dari hasil CLAHE dan transformasi tampilan (MTF/Asinh/GHS) agar nilai fisis tetap jujur.",
  },
  {
    title: "Astronomical Image Analysis",
    description:
      "Dilengkapi pembacaan header FITS, statistik citra, jendela histogram linear/logaritmik, serta profil tema Night Vision Red untuk observasi malam.",
  },
] as const;

export const FEATURE_CATEGORIES: readonly FeatureCategory[] = [
  "Semua",
  "Input & Sequence",
  "Kalibrasi & Stacking",
  "Background & Stretch",
  "Analisis, Log & Ekspor",
];

export const FEATURES: readonly FeatureItem[] = [
  {
    id: "multi-format-input",
    name: "Multi-Format Image Input",
    category: "Input & Sequence",
    iconName: "Files",
    description: "Arsitektur adapter terpadu untuk PNG, JPEG, BMP, TIFF, FITS, RAW kamera, Video, dan SER dalam satu alur kerja.",
    benefit: "Memudahkan pengamat membuka berbagai hasil rekaman teleskop maupun kamera tanpa konversi manual.",
    status: "TERUJI",
  },
  {
    id: "fits-reader",
    name: "FITS Reader & Multi-HDU",
    category: "Input & Sequence",
    iconName: "FileCode2",
    description: "Membaca citra FITS (.fit, .fits, .fts) via Astropy lengkap dengan pemilihan HDU gambar dan pembacaan header FITS.",
    benefit: "Menjaga nilai intensitas asli sensor astronomi serta metadata instrumen dan eksposur.",
    status: "TERUJI",
  },
  {
    id: "tiff-reader",
    name: "TIFF Reader (Float/16-bit)",
    category: "Input & Sequence",
    iconName: "Image",
    description: "Menggunakan tifffile untuk membaca TIFF mono/RGB 8, 16, dan 32-bit float termasuk pemilihan halaman pada multi-page TIFF.",
    benefit: "Menghindari kuantisasi paksa ke 8-bit sehingga rentang dinamis citra linear tetap terjaga.",
    status: "TERUJI",
  },
  {
    id: "raw-reader",
    name: "Camera RAW Reader",
    category: "Input & Sequence",
    iconName: "Camera",
    description: "Adapter rawpy (LibRaw) untuk CR2, CR3, NEF, ARW, DNG, ORF, RAF, RW2, PEF, dan SRW dalam mode linear tanpa auto-brightness.",
    benefit: "Membaca sinyal mentah kamera dengan gamma=(1, 1) dan pemisahan data sensor dari preview.",
    status: "PARSIAL",
    statusNote: "LibRaw (0.22.1) terbundel & lolos uji mock/error, belum diuji langsung dengan berkas RAW kamera asli.",
  },
  {
    id: "video-ser-reader",
    name: "Video & SER Reader",
    category: "Input & Sequence",
    iconName: "Film",
    description: "Ekstraksi frame streaming dari MP4, MOV, dan AVI melalui PyAV terbundel, serta pembacaan format astronomi SER (.ser).",
    benefit: "Memungkinkan pengolahan rekaman video planet/bulan berdurasi panjang tanpa memasang FFmpeg terpisah.",
    status: "TERUJI",
  },
  {
    id: "multiple-images",
    name: "Multiple Images Sequence",
    category: "Input & Sequence",
    iconName: "Images",
    description: "Memuat banyak berkas gambar sekaligus menjadi satu sequence tervalidasi dalam memori terkendali.",
    benefit: "Mempercepat penggabungan burst foto pengamatan hilal menjadi satu sesi stacking.",
    status: "TERUJI",
  },
  {
    id: "folder-sequence",
    name: "Folder Sequence",
    category: "Input & Sequence",
    iconName: "FolderOpen",
    description: "Memindai seluruh berkas citra kompatibel di dalam satu direktori dengan pengurutan natural maupun waktu.",
    benefit: "Praktis saat mengelola puluhan hingga ratusan frame dari sesi akuisisi lapangan.",
    status: "TERUJI",
  },
  {
    id: "frame-list-selection",
    name: "Frame List & Selection",
    category: "Input & Sequence",
    iconName: "ListChecks",
    description: "Menampilkan daftar frame lengkap dengan status Kompatibel, Inkompatibel, atau Error serta kotak centang seleksi.",
    benefit: "Pengguna tetap memegang kendali penuh atas frame mana yang disertakan atau dikecualikan.",
    status: "TERUJI",
  },
  {
    id: "image-information",
    name: "Image & Sensor Information",
    category: "Input & Sequence",
    iconName: "Info",
    description: "Panel sidebar dimensi, kanal (mono tetap mono, RGB tetap RGB), bit-depth, orientasi, serta dialog inspeksi/editor header FITS.",
    benefit: "Memverifikasi konsistensi tipe data sumber sebelum menjalankan pemrosesan.",
    status: "TERUJI",
  },
  {
    id: "flat-calibration",
    name: "Optional Flat Calibration",
    category: "Kalibrasi & Stacking",
    iconName: "Sparkles",
    description: "Kalibrasi flat-field opsional menggunakan normalisasi median dan proteksi pembagian nol setelah cek kecocokan dimensi/kanal.",
    benefit: "Mengoreksi vignetting optik dan noda debu sensor tanpa mengubah data tanpa master flat.",
    status: "TERUJI",
  },
  {
    id: "master-flat",
    name: "Single & Sequence Master Flat",
    category: "Kalibrasi & Stacking",
    iconName: "SlidersHorizontal",
    description: "Mendukung pemuatan single master flat maupun pembuatan master flat dari kumpulan foto, folder, video, atau berkas SER.",
    benefit: "Fleksibel menyesuaikan workflow pengambilan frame flat di lapangan.",
    status: "TERUJI",
  },
  {
    id: "image-stacking",
    name: "Automatic Image Stacking",
    category: "Kalibrasi & Stacking",
    iconName: "Layers",
    description: "Mean, Sigma-Clipped Mean, dan Quality-Weighted Robust stacking per-strip plus pengukuran pergeseran baca-saja (Phase Correlation FFT).",
    benefit: "Menurunkan noise acak latar langit sambil menolak frame campur mono/RGB dan tanpa alignment paksa.",
    status: "TERUJI",
  },
  {
    id: "profiles",
    name: "Basic, Medium, High Profile",
    category: "Kalibrasi & Stacking",
    iconName: "Gauge",
    description: "Tiga profil terpadu dengan parameter stacking, background, enhancement, dan stretch yang terstruktur beserta catatan risikonya.",
    benefit: "Pemula cukup memilih satu profil tanpa menyetel puluhan angka secara manual.",
    status: "TERUJI",
  },
  {
    id: "background-extraction",
    name: "Background Extraction",
    category: "Background & Stretch",
    iconName: "ScanLine",
    description: "Polinomial Derajat 1/2, Thin Plate Spline RBF, dan Auto Robust Mesh RBF dengan Protected ROI dan peringatan anti-overcorrection.",
    benefit: "Meredam gradien langit senja tanpa menyerap sabit hilal yang redup.",
    status: "TERUJI",
  },
  {
    id: "image-enhancement",
    name: "Luminance-Aware Enhancement",
    category: "Background & Stretch",
    iconName: "Contrast",
    description: "Engine CLAHE terbatas/adaptif yang menghitung penyesuaian pada kanal luminans RGB tanpa denoise, smoothing, atau sharpening otomatis.",
    benefit: "Meningkatkan kontras struktur redup sambil mempertahankan keseimbangan warna asli.",
    status: "TERUJI",
  },
  {
    id: "histogram-transformation",
    name: "Histogram Transformation",
    category: "Background & Stretch",
    iconName: "Activity",
    description: "Peregangan Linear + MTF, Asinh + MTF, Adaptive Asinh + MTF, serta GHS + MTF khusus cabang tampilan.",
    benefit: "Membuat sinyal redup di atas latar langit tampak jelas di layar tanpa menyentuh master linear.",
    status: "TERUJI",
  },
  {
    id: "histogram-window",
    name: "Histogram Window & Statistics",
    category: "Analisis, Log & Ekspor",
    iconName: "BarChart3",
    description: "Grafik histogram Linear & Logarithmic dengan zoom, pilihan bins, statistik Min/Max/Mean/Median/StdDev/Percentile, serta ekspor PNG/CSV.",
    benefit: "Membantu mengevaluasi distribusi sinyal, latar langit, dan potensi saturasi piksel.",
    status: "TERUJI",
  },
  {
    id: "console-log",
    name: "Console & Processing Log",
    category: "Analisis, Log & Ekspor",
    iconName: "Terminal",
    description: "Panel log terstruktur real-time untuk tiap tahap input, validasi, kalibrasi, dan pipeline dengan ekspor TXT, CSV, serta JSON.",
    benefit: "Menjaga transparansi setiap proses dan mempermudah pelacakan galat atau laporan audit.",
    status: "TERUJI",
  },
  {
    id: "scientific-export",
    name: "Scientific & Visual Export",
    category: "Analisis, Log & Ekspor",
    iconName: "FileOutput",
    description: "Menyimpan master linear (.fits/.tif float32 dengan header riwayat) secara terpisah dari hasil visual (.png) dan Quick Snapshot.",
    benefit: "Melindungi keaslian data ilmiah dengan aturan anti-overwrite berkas sumber.",
    status: "TERUJI",
  },
  {
    id: "night-vision-red",
    name: "Night Vision Red Theme",
    category: "Analisis, Log & Ekspor",
    iconName: "Moon",
    description: "Mode tema merah astronomi beserta aset logo dan ikon khusus yang preferensinya tersimpan otomatis di konfigurasi pengguna.",
    benefit: "Mengurangi silau layar saat aplikasi digunakan pada kondisi pengamatan senja atau malam.",
    status: "TERUJI",
  },
];

export const SCREENSHOTS: readonly ScreenshotItem[] = [
  {
    id: "main-empty-dark",
    title: "Main Image Viewer (Standard Dark)",
    category: "Antarmuka Awal",
    src1600: "/screenshots/main-empty-dark-1600.webp",
    src800: "/screenshots/main-empty-dark-800.webp",
    alt: "Tampilan utama HILALONE v1.1.1 mode Standard Dark dengan ikon dan logo resmi baru serta menu Help.",
    caption:
      "Tampilan awal HILALONE v1.1.1 dalam tema Standard Dark: ikon ringkas baru di header, logo lengkap resmi di tengah viewport, menu Help (Update System), dan panel inspeksi kanan.",
    isSyntheticSample: false,
  },
  {
    id: "processing-result-dark",
    title: "Automated Image Processing & Result",
    category: "Pipeline Otomatis",
    src1600: "/screenshots/processing-result-dark-1600.webp",
    src800: "/screenshots/processing-result-dark-800.webp",
    alt: "Hasil pemrosesan otomatis profil Basic standar pada sequence sintetis 8 frame di HILALONE.",
    caption:
      "Antarmuka hasil pemrosesan otomatis profil Basic standar (8 frame). Catatan jujur: citra di viewer merupakan data uji sintetis (gradien langit, vignetting, dan sabit buatan), bukan foto observasi nyata.",
    isSyntheticSample: true,
  },
  {
    id: "sequence-loaded-dark",
    title: "Image Inspector & Sequence Loaded",
    category: "Input & Sequence",
    src1600: "/screenshots/sequence-loaded-dark-1600.webp",
    src800: "/screenshots/sequence-loaded-dark-800.webp",
    alt: "Tampilan HILALONE setelah memuat 8 frame TIFF sintetis sebelum pemrosesan dengan status kompatibilitas Ready.",
    caption:
      "Sequence 8 frame TIFF sintetis dimuat ke viewer beserta ringkasan kompatibilitas, dimensi (960×720 px), dan tipe sensor (Mono | float32 | 32-bit).",
    isSyntheticSample: true,
  },
  {
    id: "histogram-window",
    title: "Histogram Window & Statistics",
    category: "Analisis Citra",
    src1600: "/screenshots/histogram-window-1600.webp",
    src800: "/screenshots/histogram-window-800.webp",
    alt: "Jendela Histogram HILALONE menampilkan grafik distribusi intensitas dan panel statistik citra lengkap.",
    caption:
      "Jendela Histogram interaktif (skala Linear/Logarithmic, pengaturan Bins & gaya kurva, panel Statistik Citra, serta ekspor grafik PNG dan data CSV) menggunakan data uji sintetis.",
    isSyntheticSample: true,
  },
  {
    id: "console-log-dark",
    title: "Console / Processing Log Panel",
    category: "Transparansi Proses",
    src1600: "/screenshots/console-log-dark-1600.webp",
    src800: "/screenshots/console-log-dark-800.webp",
    alt: "Panel Console Processing Log HILALONE yang mencatat setiap tahap input, stacking, background extraction, enhancement, dan stretch.",
    caption:
      "Panel Console / Processing Log mencatat waktu eksekusi, modul, metode tiap tahap pipeline, dan menyediakan tombol ekspor log ke TXT/CSV/JSON.",
    isSyntheticSample: true,
  },
  {
    id: "processing-result-night",
    title: "Night Vision Red Mode (Processing Result)",
    category: "Tema Astronomi",
    src1600: "/screenshots/processing-result-night-1600.webp",
    src800: "/screenshots/processing-result-night-800.webp",
    alt: "Antarmuka HILALONE dalam tema Night Vision Red menampilkan hasil pemrosesan data sintetis.",
    caption:
      "Tema Night Vision Red menjaga adaptasi gelap pengamat dengan palet merah rendah silau serta ikon dan logo khusus mode malam (menggunakan citra uji sintetis).",
    isSyntheticSample: true,
  },
  {
    id: "main-empty-night",
    title: "Night Vision Red Mode (Initial State)",
    category: "Tema Astronomi",
    src1600: "/screenshots/main-empty-night-1600.webp",
    src800: "/screenshots/main-empty-night-800.webp",
    alt: "Tampilan awal HILALONE v1.1.1 dalam mode Night Vision Red dengan varian logo dan ikon merah baru.",
    caption:
      "Kondisi awal aplikasi pada tema Night Vision Red sebelum citra dibuka, menampilkan varian logo dan ikon resmi baru bertema merah observasi malam.",
    isSyntheticSample: false,
  },
];

export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  {
    stepNumber: "01",
    code: "IMAGE INPUT",
    title: "Pembacaan Sumber (Read-Only)",
    modeTag: "Wajib",
    summary: "Membaca FITS, TIFF, RAW kamera, PNG/JPEG, folder sequence, video (MP4/MOV/AVI), atau berkas SER.",
    technicalDetail:
      "Adapter memilih pembaca ilmiah yang tepat, mengonversi representasi internal ke float32 tanpa menimpa file sumber, dan menjaga kanal asli (mono tetap mono, RGB tetap RGB).",
    outputs: "original_data (float32) + ImageInfo + metadata EXIF/FITS/SER",
  },
  {
    stepNumber: "02",
    code: "SEQUENCE VALIDATION",
    title: "Cek Kompatibilitas & Pergeseran",
    modeTag: "Multi-Frame / Video / SER",
    summary: "Memeriksa ukuran, jumlah kanal, orientasi, dan mengukur translasi antar frame secara baca-saja.",
    technicalDetail:
      "Sequence campuran mono dan RGB ditolak. Pergeseran (dx, dy) diukur terhadap frame referensi memakai Phase Correlation 2D FFT (ambang 1,0 px) untuk status OK / MELEBIHI_AMBANG / INDETERMINATE tanpa alignment otomatis.",
    outputs: "PreStackValidationReport & PositionStabilityReport",
  },
  {
    stepNumber: "03",
    code: "FRAME SELECTION",
    title: "Seleksi Daftar Frame",
    modeTag: "Multi-Frame / Video / SER",
    summary: "Pengguna meninjau status tiap frame dan dapat mengecualikan frame tertentu sebelum diproses.",
    technicalDetail:
      "Setiap frame yang dikecualikan baik manual maupun oleh validation gate dicatat eksplisit beserta alasannya; tidak ada frame yang hilang diam-diam.",
    outputs: "Daftar indeks frame tervalidasi & excluded_frame_indices",
  },
  {
    stepNumber: "04",
    code: "FLAT CALIBRATION",
    title: "Kalibrasi Master Flat",
    modeTag: "Opsional",
    summary: "Aktif hanya jika opsi Flat Calibration dicentang dan Master Flat kompatibel tersedia.",
    technicalDetail:
      "Memeriksa kecocokan resolusi, kanal, dan orientasi Master Flat (single atau sequence), menormalkan flat dengan median, lalu membagi sinyal light dengan proteksi nilai mendekati nol. Tanpa dark/bias pada MVP 1.0.",
    outputs: "calibrated_data (float32) + FlatCalibrationReport",
  },
  {
    stepNumber: "05",
    code: "IMAGE STACKING",
    title: "Penumpukan Frame Otomatis",
    modeTag: "Multi-Frame / Video / SER",
    summary: "Menggabungkan frame terpilih tanpa transformasi geometris atau warping (dilewati pada Single Image).",
    technicalDetail:
      "Menjalankan Arithmetic Mean (Basic), Iterative Sigma-Clipped Mean Median & MAD (Medium), atau Quality-Weighted Robust Stacking (High) secara bertahap per-strip hemat memori.",
    outputs: "stacked_data (float32) + metrik kualitas frame",
  },
  {
    stepNumber: "06",
    code: "BACKGROUND EXTRACTION",
    title: "Engine 1 — Pemodelan Latar Langit",
    modeTag: "Wajib",
    summary: "Memodelkan dan mengurangkan gradien langit aditif secara terukur (I_linear - B_model).",
    technicalDetail:
      "Menggunakan Polinomial Derajat 1/2, Thin Plate Spline RBF, atau Auto Robust Mesh RBF. Sampel terang dan Wilayah Proteksi (Protected ROI) dikeluarkan dari fitting dengan safeguard peringatan anti-overcorrection.",
    outputs: "linear_result (float32) & background_model",
  },
  {
    stepNumber: "07",
    code: "IMAGE ENHANCEMENT",
    title: "Engine 2 — Peningkatan Kontras Terbatas",
    modeTag: "Wajib",
    summary: "Menjalankan CLAHE terkendali pada salinan turunan tanpa denoise, smoothing, atau sharpening otomatis.",
    technicalDetail:
      "Pada citra RGB, peningkatan kontras dihitung secara luminance-aware dan dipetakan ulang dengan menjaga rasio warna serta mencatat risiko clipping atau amplifikasi derau.",
    outputs: "enhanced_result (float32 turunan nonlinear)",
  },
  {
    stepNumber: "08",
    code: "HISTOGRAM TRANSFORMATION",
    title: "Engine 3 — Display Stretch",
    modeTag: "Wajib",
    summary: "Memetakan rentang dinamis ke tampilan [0.0, 1.0] menggunakan MTF, Asinh + MTF, atau GHS + MTF.",
    technicalDetail:
      "Hanya menyentuh cabang pratinjau tampilan agar struktur sabit redup tampak oleh mata pengamat tanpa mengubah nilai piksel pada linear_result.",
    outputs: "display_result [0.0, 1.0] & pratinjau QImage",
  },
  {
    stepNumber: "09",
    code: "SCIENTIFIC EXPORT",
    title: "Ekspor Terpisah & Audit Riwayat",
    modeTag: "Wajib",
    summary: "Menyimpan master linear, visual display, snapshot layar, log console, dan riwayat parameter.",
    technicalDetail:
      "Keluaran linear (FITS/TIFF float32 + header riwayat) dipisahkan dari keluaran visual (PNG 8-bit & Quick Snapshot) dengan penamaan unik anti-overwrite sumber.",
    outputs: "Berkas *_linear (.fits/.tif), *_display (.png), laporan JSON & log",
  },
];

export const INTEGRITY_LAYERS: readonly IntegrityLayer[] = [
  {
    code: "A",
    title: "Original Source Data",
    dtype: "float32 (read-only)",
    role: "Salinan awal nilai piksel dari berkas sumber asli.",
    guarantee: "File di disk tidak pernah ditimpa atau dimodifikasi (verifikasi SHA-256 sumber tetap identik).",
  },
  {
    code: "B",
    title: "Calibrated Data",
    dtype: "float32 (opsional)",
    role: "Citra setelah dibagi Master Flat ternormalisasi jika kalibrasi flat diaktifkan.",
    guarantee: "Tetap linear tanpa dark/bias tersembunyi dan selalu mencatat kompatibilitas Master Flat.",
  },
  {
    code: "C / D",
    title: "Scientific Linear Result",
    dtype: "float32 linear",
    role: "Hasil Stacking (multi-frame) dan Background Extraction sebelum CLAHE maupun stretch.",
    guarantee: "Diekspor terpisah ke FITS/TIFF ilmiah lengkap dengan riwayat proses pada header FITS.",
  },
  {
    code: "E",
    title: "Derived Enhanced Data",
    dtype: "float32 nonlinear",
    role: "Salinan terpisah setelah Engine 2 (CLAHE luminance-aware).",
    guarantee: "Tidak pernah menimpa cabang linear_result dan tidak memakai sharpening atau smoothing otomatis.",
  },
  {
    code: "F",
    title: "Display Preview",
    dtype: "float32 [0.0, 1.0] → 8-bit preview",
    role: "Cabang akhir setelah Histogram Transformation (MTF / Asinh / GHS) untuk tampilan layar & ekspor PNG.",
    guarantee: "Meningkatkan keterlihatan visual tanpa mencampurkan kurva stretch ke data linear master.",
  },
];

export const NON_INVENTION_RULES = [
  "Tidak menggunakan rekonstruksi citra generatif atau model AI untuk menambal maupun menggambar hilal.",
  "Tidak melakukan image registration, rotasi, atau warping geometris otomatis saat stacking (ambang cek pergeseran bersifat baca-saja).",
  "Tidak menjalankan KOMBAT, noise reduction, smoothing, maupun sharpening otomatis pada pipeline MVP 1.0.",
  "Seluruh parameter profil, metode, peringatan overcorrection, serta frame yang dikecualikan dicatat secara transparan.",
] as const;

export const ROADMAP_STAGES: readonly RoadmapStage[] = [
  {
    id: "mvp-1",
    stage: "MVP 1.0",
    title: "Automated Astronomical Image Processing",
    statusLabel: "Diimplementasikan · Build v1.0.0 Tahap Uji Distribusi",
    statusKind: "active",
    summary:
      "Fokus pada pembacaan multi-format ilmiah, validasi kompatibilitas, kalibrasi flat opsional, stacking tanpa alignment, ekstraksi latar, enhancement/stretch terpisah, dan antarmuka desktop Windows.",
    items: [
      { label: "Reader FITS, TIFF, Video (MP4/MOV/AVI), SER, PNG/JPEG & Pipeline", badge: "Teruji" },
      { label: "RAW Kamera Reader (LibRaw / rawpy)", badge: "Parsial (belum uji RAW kamera asli)" },
      { label: "PyInstaller ONE-DIR Build (v1.0.0)", badge: "Teruji di mesin dev terisolasi" },
      { label: "Installer Windows (HILALONE_Setup_v1.0.exe)", badge: "Tersedia (v1.0.0)" },
    ],
  },
  {
    id: "mvp-2",
    stage: "MVP 2.0",
    title: "Scientific Image Analysis & Measurement",
    statusLabel: "Planned (Direncanakan)",
    statusKind: "planned",
    summary:
      "Rencana pengembangan fitur pengukuran ilmiah pada citra terkalibrasi tanpa mengubah integritas data dasar dari MVP 1.0.",
    items: [
      { label: "Pengukuran SNR (Signal-to-Noise Ratio) & kontras lokal terukur", badge: "Planned" },
      { label: "Profil intensitas garis / ROI & alat ukur fotometri dasar", badge: "Planned" },
      { label: "Evaluasi kualitas citra observasi lebih mendalam", badge: "Planned" },
    ],
  },
  {
    id: "mvp-3",
    stage: "MVP 3.0",
    title: "Automatic Hilal Detection & Advanced Research",
    statusLabel: "Planned (Direncanakan)",
    statusKind: "planned",
    summary:
      "Rencana jangka lanjut untuk riset bantuan identifikasi kandidat sabit dan dukungan penelitian visibilitas berbasis data terkalibrasi.",
    items: [
      { label: "Bantuan deteksi kandidat sabit hilal berbasis riset", badge: "Planned" },
      { label: "Fitur riset lanjutan & integrasi alur pengamatan terstandar", badge: "Planned" },
      { label: "Catatan: Belum tersedia di v1.0.0 — tidak mengklaim penentuan visibilitas otomatis", badge: "Penting" },
    ],
  },
];

export const TECH_SPECS: readonly TechSpecRow[] = [
  {
    category: "Platform & OS",
    parameter: "Windows Desktop (64-bit)",
    detail: "Teruji di Windows 10 Pro 64-bit (Build 19045). Target kompatibilitas mencakup Windows 11 64-bit, namun belum diuji langsung pada Windows 11 maupun PC bersih tanpa lingkungan Python.",
    verificationTag: "Win10 Teruji · Win11 Belum Diuji",
  },
  {
    category: "Arsitektur Runtime",
    parameter: "Python 3.10.11 (64-bit) + PySide6 6.12.0",
    detail: "Arsitektur modular (core, input_manager, processing, output_manager, gui) dengan pemrosesan berat di worker thread dan pengemasan PyInstaller ONE-DIR.",
    verificationTag: "Terverifikasi",
  },
  {
    category: "Pustaka Ilmiah Inti",
    parameter: "NumPy · Astropy · tifffile · rawpy · PyAV",
    detail: "NumPy 2.2.6, Astropy 6.1.7, tifffile 2025.5.10, rawpy 0.27.1 (LibRaw 0.22.1), dan PyAV 17.1.0 (FFmpeg terbundel).",
    verificationTag: "Terkunci di Build",
  },
  {
    category: "Format Input Didukung",
    parameter: "Citra Tunggal, Sequence, Video & SER",
    detail: "FITS (.fit, .fits, .fts), TIFF (.tif, .tiff), RAW (.cr2, .cr3, .nef, .arw, .dng, .orf, .raf, .rw2, .pef, .srw), PNG, JPEG, BMP, Video (.mp4, .mov, .avi), dan SER (.ser).",
    verificationTag: "RAW Parsial · Lainnya Teruji",
  },
  {
    category: "Format Output",
    parameter: "Linear Master vs Visual Display",
    detail: "Linear ilmiah: FITS & TIFF (float32 + riwayat proses). Visual/pratinjau: PNG 8-bit & Quick Snapshot PNG. Laporan/log: JSON, CSV, TXT.",
    verificationTag: "Teruji",
  },
  {
    category: "Penanganan Berkas",
    parameter: "Read-Only Source & Anti-Overwrite",
    detail: "Sumber tidak pernah dimodifikasi, dipindah, atau ditimpa; log runtime & preferensi pengguna ditulis ke %LOCALAPPDATA%\\HILALONE.",
    verificationTag: "Teruji",
  },
  {
    category: "Presisi & Kanal",
    parameter: "float32 Internal · Mono & RGB Terjaga",
    detail: "Tidak ada kuantisasi ke 8-bit sebelum ekspor visual; citra mono tetap mono dan RGB tetap RGB melalui pemrosesan luminance-aware.",
    verificationTag: "Teruji",
  },
];

export const FAQ_ITEMS: readonly FaqItem[] = [
  {
    id: "what-is-hilalone",
    question: "Apa itu HILALONE?",
    answer:
      "HILALONE (Automated Hilal Image Processing) adalah perangkat lunak desktop Windows untuk membaca, memvalidasi, menumpuk (stacking), mengoreksi latar langit, dan menampilkan citra astronomi—khususnya pengamatan hilal—secara transparan dan deterministik.",
  },
  {
    id: "target-users",
    question: "Untuk siapa aplikasi ini dikembangkan?",
    answer:
      "HILALONE ditujukan bagi pengamat hilal (tim rukyat), peneliti, dosen, mahasiswa astronomi/ilmu falak, serta pegiat astrofotografi yang membutuhkan alur pengolahan citra sederhana namun tetap jujur secara ilmiah.",
  },
  {
    id: "supported-formats",
    question: "Format file apa yang didukung?",
    answer:
      "Mendukung berkas gambar tunggal maupun sequence berupa FITS (.fit/.fits/.fts), TIFF (.tif/.tiff), PNG, JPEG, BMP, serta format kamera RAW (.cr2, .cr3, .nef, .arw, .dng, dan lainnya via LibRaw). Untuk video mendukung MP4, MOV, AVI, dan format video astronomi SER (.ser).",
  },
  {
    id: "what-is-stacking",
    question: "Apa kegunaan Image Stacking?",
    answer:
      "Image Stacking menggabungkan banyak frame pengamatan yang kompatibel (ukuran dan kanal sama) untuk menurunkan derau acak latar langit sehingga sinyal sabit yang redup lebih bersih. Pada MVP 1.0, stacking dijalankan tanpa alignment/warping paksa dan pergeseran diukur secara baca-saja.",
  },
  {
    id: "what-is-flat",
    question: "Apa kegunaan Flat Calibration?",
    answer:
      "Flat Calibration bersifat opsional untuk mengoreksi ketidakseragaman pencahayaan optik (vignetting) dan bayangan debu pada sensor menggunakan Master Flat tunggal maupun sequence frame flat ternormalisasi.",
  },
  {
    id: "fits-support",
    question: "Apakah HILALONE mendukung FITS?",
    answer:
      "Ya. HILALONE membaca berkas FITS (termasuk pemilihan Multi-HDU dan pemeriksaan header FITS) maupun menulis hasil master ilmiah linear dalam format FITS float32 lengkap dengan catatan riwayat proses di header.",
  },
  {
    id: "linear-vs-display",
    question: "Apa perbedaan Scientific Master (Linear) dan Display Preview?",
    answer:
      "Scientific Master (linear_result) menyimpan nilai piksel float32 sebelum enhancement CLAHE maupun peregangan histogram (MTF/Asinh/GHS) sehingga aman untuk penyimpanan data ilmiah. Display Preview hanyalah representasi visual untuk memudahkan pengamatan layar dan ekspor PNG.",
  },
  {
    id: "auto-visibility",
    question: "Apakah HILALONE menentukan visibilitas hilal secara otomatis?",
    answer:
      "Belum. Pada versi MVP 1.0 ini HILALONE berfokus murni pada pengolahan citra astronomi yang jujur. Fitur analisis pengukuran (MVP 2.0) dan bantuan deteksi hilal (MVP 3.0) masih berada dalam tahap rencana pengembangan dan belum tersedia.",
  },
  {
    id: "how-to-download",
    question: "Bagaimana mengunduh aplikasi?",
    answer:
      `Anda dapat mengunduh paket installer resmi Windows (${siteConfig.installerFilename}) secara langsung melalui tombol Unduh di bagian Distribusi Aplikasi pada halaman ini atau melalui halaman GitHub Releases resmi beserta verifikasi checksum SHA-256.`,
  },
  {
    id: "report-bugs",
    question: "Bagaimana melaporkan bug atau memberi masukan?",
    answer:
      "Anda dapat membuka isu (Issue) pada repositori GitHub resmi HILALONE dengan menyertakan deskripsi langkah kejadian serta ekspor log dari panel Console Log atau berkas di %LOCALAPPDATA%\\HILALONE\\logs\\ jika terjadi kendala.",
  },
];
