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
  // Aktifkan `downloadAvailable: true` dan isi metadata resmi setelah GitHub Release diterbitkan.
  downloadAvailable: false,
  downloadUrl: null,
  installerFilename: "HILALONE_Setup.exe",
  fileSize: null,
  supportedWindows: "Windows 10 (64-bit, teruji) · Target Windows 11 (64-bit, belum diuji langsung)",
  releaseDate: null,
  sha256: null,
  releasePageUrl: "https://github.com/akuirulanam5-prog/HILALONE/releases",

  // Repositori GitHub publik (terverifikasi HTTP 200, private=false)
  githubUrl: "https://github.com/akuirulanam5-prog/HILALONE",
  repoIsPublic: true,

  // Isi URL produksi setelah domain ditetapkan
  canonicalUrl: null,

  copyrightHolder: "HILALONE Project",
  copyrightYear: "2026",
};
