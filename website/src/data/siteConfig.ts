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
  version: "1.1.2",
  mvpStage: "MVP 1.0",
  platform: "Windows Desktop (64-bit)",

  // Konfigurasi terpusat distribusi installer Windows.
  downloadAvailable: true,
  downloadUrl:
    "https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.2/HILALONE_Setup_v1.1.2.exe",
  installerFilename: "HILALONE_Setup_v1.1.2.exe",
  fileSize: "88,1 MB (92.359.939 byte)",
  supportedWindows: "Windows 10 (64-bit, teruji) · Target Windows 11 (64-bit, belum diuji langsung)",
  releaseDate: "18 November 2026",
  sha256: "237cb88069b970f3fadd5809739d64d404264190bf126483db716fbcd6483e99",
  releasePageUrl: "https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.1.2",
  releaseHighlights: [
    "Scientific Processing Log & Console System terpusat dengan Session ID (SES-...), Run ID (RUN-...), serta penyimpanan permanen otomatis (.log & .jsonl).",
    "Tiga Mode Detail fungsional nyata: Normal (ringkas), Verbose (metadata FITS, rumus & statistik ilmiah tiap tahap), dan Debug (diagnostik teknis array & memori).",
    "Standardisasi seluruh format durasi ke 'Duration: 0.00 s', perbaikan layout tombol Auto-scroll: ON/OFF, dan Export Visible/Complete Log yang otomatis mengarah ke folder sumber citra aktif.",
    "Integrasi Desktop Auto-Update System (menu Help → Check for Updates, verifikasi SHA-256) serta pembaruan ikon & logo resmi Standard Dark dan Night Vision Red.",
  ],

  // Repositori GitHub publik (terverifikasi HTTP 200, private=false)
  githubUrl: "https://github.com/akuirulanam5-prog/HILALONE",
  repoIsPublic: true,

  // URL produksi resmi Vercel
  canonicalUrl: "https://hilalone-website.vercel.app",

  copyrightHolder: "HILALONE Project",
  copyrightYear: "2026",
};
