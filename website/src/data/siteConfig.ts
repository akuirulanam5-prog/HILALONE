export interface SiteConfig {
  readonly appName: string;
  readonly fullTitle: string;
  readonly tagline: string;
  readonly philosophy: string;
  readonly version: string;
  readonly mvpStage: string;
  readonly platform: string;
  readonly downloadAvailable: boolean;
  readonly downloadUrl: string | null;
  readonly installerFilename: string;
  readonly fileSize: string | null;
  readonly supportedWindows: string;
  readonly releaseDate: string | null;
  readonly sha256: string | null;
  readonly releasePageUrl: string | null;
  readonly releaseHighlights: readonly string[];
  readonly githubUrl: string;
  readonly repoIsPublic: boolean;
  readonly canonicalUrl: string | null;
  readonly copyrightHolder: string;
  readonly copyrightYear: string;
}

export const siteConfig: SiteConfig = {
  appName: "HILALONE",
  fullTitle: "HILALONE — Automated Hilal Image Processing",
  tagline: "Scientific Astronomical Image Processing Software",
  philosophy: "Enhance the Signal, Never Invent the Signal.",
  version: "1.1.3",
  mvpStage: "MVP 1.0",
  platform: "Windows Desktop (64-bit)",

  // Konfigurasi terpusat distribusi installer Windows.
  downloadAvailable: true,
  downloadUrl:
    "https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.3/HILALONE_Setup_v1.1.3.exe",
  installerFilename: "HILALONE_Setup_v1.1.3.exe",
  fileSize: "88,1 MB (92.398.103 byte)",
  supportedWindows: "Windows 10 (64-bit, teruji) · Target Windows 11 (64-bit, belum diuji langsung)",
  releaseDate: "18 November 2026",
  sha256: "5942f4905c854c79db5413c35c9f584b93119edd035f4dff1d9b6bcdeabda4d7",
  releasePageUrl: "https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.1.3",
  releaseHighlights: [
    "Scientific Processing Timeline & Report Schema v2.0 (*_processing_report.json) yang merekam perjalanan lengkap pengolahan citra sejak Open Image hingga foto hasil tersimpan.",
    "Pencatatan User Interaction Timeline, Workflow Idle Interval, Save Transaction (memisahkan durasi dialog Save dari durasi tulis disk), serta deduplikasi sumber Video/SER.",
    "Tipografi Ringkasan Tiga Kolom Sejajar (format_aligned_summary) dengan tanda titik dua (:) sejajar vertikal di 5 bagian utama, line-wrapping rapi, dan pewarnaan status semantik.",
    "Console Log Ilmiah terpusat (mode Detail Normal/Verbose/Debug, format durasi '0.00 s', ekspor otomatis ke folder sumber citra) & Desktop Auto-Update System (SHA-256).",
  ],

  // Repositori GitHub publik (terverifikasi HTTP 200, private=false)
  githubUrl: "https://github.com/akuirulanam5-prog/HILALONE",
  repoIsPublic: true,

  // URL produksi resmi Vercel
  canonicalUrl: "https://hilalone-website.vercel.app",

  copyrightHolder: "HILALONE Project",
  copyrightYear: "2026",
};
