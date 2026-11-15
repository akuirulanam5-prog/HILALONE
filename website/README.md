# Website Resmi HILALONE

Website resmi, dokumentasi produk singkat, dan pusat distribusi installer Windows untuk **HILALONE — Automated Hilal Image Processing** (`v1.0.0`).

---

## Teknologi

- **Framework**: React 19 + TypeScript
- **Bundler**: Vite (`outDir: dist`)
- **Ikon**: `lucide-react`
- **Styling**: CSS Design Tokens kustom (Deep Navy astronomical palette, grid responsif, `prefers-reduced-motion`)
- **Target Hosting**: Vercel (Root Directory: `website/`)

---

## Struktur Direktori

```text
website/
├─ public/
│  ├─ branding/          # Turunan WebP/PNG logo Standard Dark & Night Vision Red
│  ├─ screenshots/       # Tangkapan layar nyata PySide6 HILALONE v1.0.0 (1600w & 800w WebP)
│  ├─ apple-touch-icon.png
│  ├─ favicon.ico
│  └─ og-image.png
├─ src/
│  ├─ components/        # Navbar, HeroVisualShowcase, ScreenshotLightbox, SectionHeader
│  ├─ data/              # siteConfig.ts (konfigurasi rilis terpusat) & hilaloneData.ts
│  ├─ sections/          # Hero, About, Features, Gallery, Workflow, Integrity, Roadmap, Specs, Download, FAQ, Footer
│  ├─ styles/            # tokens.css & global.css
│  ├─ App.tsx
│  └─ main.tsx
├─ index.html
├─ package.json
├─ tsconfig.json
├─ vercel.json
└─ vite.config.ts
```

---

## Menjalankan Secara Lokal

```bash
cd website
npm install
npm run dev
```

Buka URL lokal yang ditampilkan Vite (umumnya `http://localhost:5173`).

---

## Type Check & Production Build

```bash
cd website
npm run typecheck
npm run build
npm run preview
```

Hasil build statis berada di `website/dist/` dan diabaikan oleh Git (`.gitignore`), terpisah sepenuhnya dari direktori `dist/` aplikasi desktop Python.

---

## Mengaktifkan Tautan Installer Resmi

Saat berkas installer `HILALONE_Setup.exe` telah diterbitkan di GitHub Releases, perbarui berkas terpusat `src/data/siteConfig.ts`:

- `downloadAvailable`: ubah menjadi `true`
- `downloadUrl`: isi URL aset `.exe` resmi GitHub Releases
- `fileSize`, `releaseDate`, dan `sha256`: isi sesuai metadata rilis terverifikasi

---

## Deployment ke Vercel

1. Impor repositori `akuirulanam5-prog/HILALONE` ke Vercel.
2. Atur **Root Directory** menjadi `website`.
3. Pastikan **Framework Preset** = `Vite`, **Build Command** = `npm run build`, dan **Output Directory** = `dist` (sesuai `vercel.json`).
4. Setelah domain produksi ditetapkan, tambahkan tag `<link rel="canonical">` / nilai `canonicalUrl` sesuai domain resmi.
