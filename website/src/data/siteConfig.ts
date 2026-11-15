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
  version: "1.0.0",
  mvpStage: "MVP 1.0",
  platform: "Windows Desktop (64-bit)",

  // Konfigurasi terpusat distribusi installer Windows.
  downloadAvailable: true,
  downloadUrl:
    "https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.0.0/HILALONE_Setup_v1.0.exe",
  installerFilename: "HILALONE_Setup_v1.0.exe",
  fileSize: "90,8 MB (95.195.800 byte)",
  supportedWindows: "Windows 10 (64-bit, teruji) · Target Windows 11 (64-bit, belum diuji langsung)",
  releaseDate: "15 November 2026",
  sha256: "dd91fd214d49d6a04fde036687839af9b17e868a03bf7da4196e9788aad4ad2c",
  releasePageUrl: "https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.0.0",

  // Repositori GitHub publik (terverifikasi HTTP 200, private=false)
  githubUrl: "https://github.com/akuirulanam5-prog/HILALONE",
  repoIsPublic: true,

  // URL produksi resmi Vercel
  canonicalUrl: "https://hilalone-website.vercel.app",

  copyrightHolder: "HILALONE Project",
  copyrightYear: "2026",
};
