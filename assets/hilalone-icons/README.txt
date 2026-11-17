HILALONE - Icon Pack
====================
svg/hilalone-logo.svg   Logo lengkap (ikon + teks, teks sudah jadi path, tanpa font)
svg/hilalone-icon.svg   Ikon saja (untuk app icon / favicon)
png/icon/               Ikon PNG transparan: 16,24,32,48,64,96,128,180,256,512,1024 px
png/logo/               Logo lengkap PNG transparan: 512, 1024, 2048 px
jpg/                    JPG (latar putih / persegi navy penuh), tanpa transparansi
ico/hilalone.ico        Windows icon multi-ukuran (16-256 px)
web/                    favicon.ico, favicon.svg, favicon-16/32, apple-touch-icon,
                        icon-192/512 (PWA) dan manifest.json

Contoh HTML (website):
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">

Electron / desktop:  gunakan ico/hilalone.ico (Windows) dan png/icon/hilalone-icon-512.png atau 1024 (Linux/macOS).
Catatan: untuk ukuran kecil (<=256) dipakai versi ikon tanpa teks agar tetap terbaca.
