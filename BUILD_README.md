# Panduan Build & Deployment Windows — HILALONE v1.0.0

Dokumen ini menjelaskan cara membangun, menguji, membersihkan, dan mendistribusikan aplikasi desktop Windows **HILALONE v1.0.0** menggunakan virtual environment proyek (`C:\Hilalone\.venv`).

## 1. Struktur Build & File Terkait
- `src\hilalone\main.py` — Entry point utama (`hilalone.main:main`).
- `HILALONE.spec` — Konfigurasi build PyInstaller (mode `ONE-DIR`, windowed, ikon resmi, metadata versi `1.0.0.0`).
- `file_version_info.txt` — Metadata versi Windows executable (`HILALONE.exe`).
- `requirements-runtime.txt` — Daftar dependensi runtime terkunci untuk Python 3.10.11 64-bit.
- `requirements-build.txt` — Daftar dependensi runtime + toolchain PyInstaller pada `.venv`.
- `build_windows.bat` — Skrip otomatis build `ONE-DIR` ke `dist\HILALONE\` beserta validasi pra-build dan log (`build\pyinstaller_build.log`).
- `clean_build.bat` — Menghapus artefak build (`build\` dan `dist\HILALONE`) tanpa menyentuh source code, aset, tes, `.venv`, atau data pengguna.
- `HILALONE.iss` — Skrip Inno Setup 6 untuk membuat installer `release\HILALONE_Setup.exe` setelah distribusi `ONE-DIR` lulus pengujian.

## 2. Langkah Build Windows Executable (ONE-DIR)
1. Pastikan virtual environment `.venv` tersedia dan dependensi build sudah terpasang (`requirements-build.txt`).
2. Jalankan dari Command Prompt / PowerShell di root proyek:
   ```bat
   build_windows.bat
   ```
3. Hasil build berada di:
   - Aplikasi utama (tanpa console): `dist\HILALONE\HILALONE.exe`
   - Peluncur diagnostik (menampilkan console & log): `dist\HILALONE\HILALONE_Diagnostic.bat`
   - Log proses build PyInstaller: `build\pyinstaller_build.log`

## 3. Mode Diagnostik, Konfigurasi & Lokasi Penyimpanan Data Pengguna
- **Normal (`HILALONE.exe`)**: berjalan tanpa jendela terminal.
- **Diagnostik (`HILALONE_Diagnostic.bat` atau `HILALONE.exe --diagnostic`)**: membuka jendela console untuk menampilkan pesan diagnostik real-time.
- **Lokasi log & konfigurasi pengguna** (tanpa memerlukan hak Administrator, tidak pernah menulis ke folder bundle `_internal`/`_MEIPASS` atau `Program Files`):
  - Log runtime & crash log: `%LOCALAPPDATA%\HILALONE\logs\hilalone.log` dan `crash.log`
  - Preferensi tema & direktori terakhir: `%LOCALAPPDATA%\HILALONE\config.ini`
- Berkas hasil pemrosesan / stacking / snapshot disimpan hanya ke direktori pilihan pengguna melalui dialog simpan.

## 4. Uji Distribusi Bersih (Clean Distribution Test)
1. Salin seluruh isi folder `dist\HILALONE` (beserta `_internal`) ke folder pengujian terpisah di luar `C:\Hilalone`, misalnya `C:\Temp\HILALONE_Test`.
2. Jalankan `HILALONE.exe` langsung dari folder tersebut tanpa mengaktifkan `.venv`.
3. Pastikan logo Standard Dark / Night Vision Red tampil, format input/ekspor bekerja, dan tidak ada error DLL yang hilang.

## 5. Pembuatan Windows Installer (Setelah Build ONE-DIR Lulus Uji)
Setelah Inno Setup 6 terpasang:
```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" HILALONE.iss
```
Hasil installer akan dibuat di `release\HILALONE_Setup.exe`. Instalasi default bersifat *per-user* (`%LOCALAPPDATA%\Programs\HILALONE`) sehingga tidak membutuhkan hak Administrator dan tidak menghapus konfigurasi/log pengguna saat uninstall.
