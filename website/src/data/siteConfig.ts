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
  version: "1.1.1",
  mvpStage: "MVP 1.0",
  platform: "Windows Desktop (64-bit)",

  // Konfigurasi terpusat distribusi installer Windows.
  downloadAvailable: true,
  downloadUrl:
    "https://github.com/akuirulanam5-prog/HILALONE/releases/download/v1.1.1/HILALONE_Setup_v1.1.1.exe",
  installerFilename: "HILALONE_Setup_v1.1.1.exe",
  fileSize: "88,6 MB (92.887.501 byte)",
  supportedWindows: "Windows 10 (64-bit, teruji) · Target Windows 11 (64-bit, belum diuji langsung)",
  releaseDate: "17 November 2026",
  sha256: "3611673df3eea1de7911b430395da0f99a89e680323ce24709c17236ce56f198",
  releasePageUrl: "https://github.com/akuirulanam5-prog/HILALONE/releases/tag/v1.1.1",

  // Repositori GitHub publik (terverifikasi HTTP 200, private=false)
  githubUrl: "https://github.com/akuirulanam5-prog/HILALONE",
  repoIsPublic: true,

  // URL produksi resmi Vercel
  canonicalUrl: "https://hilalone-website.vercel.app",

  copyrightHolder: "HILALONE Project",
  copyrightYear: "2026",
};
