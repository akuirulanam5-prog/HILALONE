# Panduan Sistem Pembaruan Desktop & Prosedur Rilis HILALONE

Dokumen ini menjelaskan arsitektur modul pembaruan aplikasi (**Desktop Update System**), cara kerja menu **Help**, jaminan keamanan & penanganan jaringan, konsistensi versi lintas berkas, serta prosedur publikasi rilis resmi di GitHub Releases untuk kedua developer HILALONE.

---

## 1. Arsitektur Update Checker

Sistem pembaruan dirancang modular mengikuti `AGENTS.md` (GUI terpisah dari logika bisnis dan komunikasi jaringan; proses berat/jaringan berjalan pada background thread tanpa dependensi eksternal tambahan):

```text
MainWindow (Menu Help: Check for Updates / Automatic Update Check / Report / About)
   │  └─ QTimer startup (10s post-show, frozen only) + reminder (24h)
   │
   ├── UpdateWorker (QThread)  ──────────────────┐
   │      • CHECK_ONLY                           │ HTTPS + Timeout + Stdlib Only
   │      • DOWNLOAD_AND_VERIFY (progress + SHA) ▼
   │                                    github_updater.py + version.py + update_preferences.py
   │                                      • GitHub Releases API (/releases/latest)
   │                                      • SemVer major.minor.patch comparison
   │                                      • QSettings interval 24h & snooze (config.ini)
   │                                      • Asset filter: HILALONE_Setup*.exe
   │                                      • Unduh ke %LOCALAPPDATA%\HILALONE\updates\
   │                                      • Validasi digest SHA-256 & ukuran byte
   ├── UpdateNotificationDialog (Update Now / Later)
   ├── UpdateDialog (QDialog)             • Eksekusi aman via subprocess.Popen
   └── AboutDialog  (QDialog, terpisah dari ImageInformationDialog)
```

### Berkas Terkait
- `src/hilalone/updates/models.py` — Konstanta URL GitHub resmi, model metadata rilis (`ReleaseInfo`, `ReleaseAsset`, `UpdateCheckResult`, `DownloadResult`), enum `UpdateStatus`, dan hierarki exception berbahasa Indonesia (`UpdateError`).
- `src/hilalone/updates/version.py` — Parser dan pembanding versi semantik (`SemVer`, `parse_version`, `is_newer_version`).
- `src/hilalone/updates/github_updater.py` — Layanan HTTPS GitHub API, pemilihan aset installer Windows, validasi `digest` & perhitungan SHA-256 streaming, serta peluncuran aman installer Inno Setup.
- `src/hilalone/updates/update_preferences.py` — Pengelolaan preferensi `QSettings` (`auto_update_check_enabled`, `last_update_check`, `next_update_reminder`, `last_notified_version`), batas interval 24 jam, dan logika tunda notifikasi.
- `src/hilalone/updates/update_worker.py` — `UpdateWorker(QThread)` untuk memeriksa pembaruan dan mengunduh installer di latar belakang tanpa membekukan GUI.
- `src/hilalone/gui/about_dialog.py` — Dialog khusus **About HILALONE** (logo tema aktif, versi `__version__`, tagline ilmiah, website, repository GitHub, dan copyright), mendukung tema Standard Dark & Night Vision Red.
- `src/hilalone/gui/update_notification_dialog.py` — Dialog notifikasi ringan saat startup menemukan rilis stabil lebih baru (`Update Now` / `Later`).
- `src/hilalone/gui/update_dialog.py` — Dialog informasi pembaruan, catatan rilis, ukuran installer, progress bar unduhan, proteksi mode pengembangan (source), dan konfirmasi instalasi.
- `src/hilalone/gui/main_window.py` — Penambahan menu **Help** (`Check for Updates...`, `Automatic Update Check`, `Report an Issue...`, `About HILALONE...`), penjadwalan `QTimer`, serta lifecycle shutdown aman.

---

## 2. Cara Kerja Automatic Update Notification, Pemeriksaan Versi & Seleksi Installer

### Automatic Update Notification (Startup)
1. **Penjadwalan Non-Blocking**: Setelah `MainWindow` tampil (`showEvent`), HILALONE menjadwalkan `QTimer` selama **10 detik** (`10.000 ms`) agar proses startup dan antarmuka langsung responsif.
2. **Khusus Aplikasi Terinstal**: Pemeriksaan otomatis hanya berjalan pada aplikasi executable terinstal (`is_frozen_app() == True`), tidak pernah berjalan otomatis di development/source environment.
3. **Interval 24 Jam & `QSettings`**: Preferensi disimpan di `%LOCALAPPDATA%\HILALONE\config.ini` (grup `[updates]`):
   - `auto_update_check_enabled` (default `true`): mengaktifkan/menonaktifkan cek otomatis.
   - `last_update_check`: stempel waktu UTC pemeriksaan otomatis terakhir; pemeriksaan otomatis maksimal **1 kali per 24 jam**.
   - `next_update_reminder`: stempel waktu pengingat ulang 24 jam ketika pengguna menekan **Later**.
   - `last_notified_version`: versi terbaru terakhir yang sudah diberitahukan agar notifikasi versi yang sama tidak muncul berulang selama periode tunda.
4. **Penanganan Tenang saat Startup**: Bila tidak ada koneksi internet, timeout, atau rate limit saat pemeriksaan otomatis, aplikasi tidak menampilkan popup galat yang mengganggu — kesalahan hanya dicatat ke log runtime (`logging` dan `LogManager`).
5. **Cara Kerja `Update Now` vs `Later`**:
   - **`Update Now`**: menutup dialog notifikasi ringan lalu membuka `UpdateDialog` lengkap (unduh di background thread, progress bar, validasi SHA-256, dan konfirmasi penutupan sebelum menjalankan installer Inno Setup tanpa silent update). Bila pemrosesan citra/stacking sedang aktif, notifikasi boleh tampil tetapi instalasi wajib menunggu hingga pekerjaan pengguna selesai tanpa menutup paksa aplikasi.
   - **`Later`**: menutup dialog notifikasi, mencatat `next_update_reminder` 24 jam ke depan beserta `last_notified_version`, dan menjadwalkan pengingat ulang setelah 24 jam (`QTimer`). Jika rilis stabil yang lebih baru dengan versi berbeda terbit di GitHub Releases, notifikasi diperbarui dan tetap dapat ditampilkan untuk versi berbeda tersebut.
6. **Cara Menonaktifkan**: Hapus centang pada menu **Help → Automatic Update Check**. Pemeriksaan manual melalui **Help → Check for Updates...** tetap tersedia kapan saja tanpa dibatasi jadwal 24 jam atau status tunda.

### Hubungan dengan GitHub Releases & Pemilihan Asset
1. **Endpoint GitHub API**: Mengirim permintaan HTTPS `GET` (timeout 15 detik) ke:
   `https://api.github.com/repos/akuirulanam5-prog/HILALONE/releases/latest`
2. **Pembandingan Versi (`version.py`)**:
   - Versi aplikasi lokal dibaca dari `hilalone.__version__` (`src/hilalone/__init__.py`).
   - Tag GitHub (mis. `v1.0.0`, `v1.1.0`) diparsing menjadi angka `(major, minor, patch)` tanpa membandingkan string secara leksikografis (`1.0.10` selalu dinilai lebih baru daripada `1.0.2`).
   - Rilis dengan `draft=True`, `prerelease=True`, atau tag prerelease (`-alpha`, `-beta`, `-rc`) dilewati dan tidak ditawarkan sebagai pembaruan reguler.
3. **Pemilihan Asset Installer (`select_windows_installer_asset`)**:
   - Hanya memilih berkas `.exe` yang namanya diawali `HILALONE_Setup` (mis. `HILALONE_Setup_v1.0.exe` maupun `HILALONE_Setup_v1.1.0.exe`).
   - Tidak pernah memilih source code archive (`.zip` / `.tar.gz`).

---

## 3. Keamanan & Penanganan Masalah Jaringan

### Kontrol Keamanan Wajib
- **HTTPS-Only**: Baik URL awal maupun URL hasil redirect (mis. ke CDN aset GitHub) divalidasi memakai skema `https://` dengan konteks TLS sistem (`ssl.create_default_context()`).
- **Direktori Pengguna**: Installer diunduh ke `%LOCALAPPDATA%\HILALONE\updates\` (`get_user_data_dir() / "updates"`), tidak pernah menulis ke `_MEIPASS` atau `Program Files`.
- **Unduhan Atomik & Validasi SHA-256**:
  - Data diunduh ke berkas sementara `*.part` sambil menghitung SHA-256 secara streaming.
  - Apabila metadata `digest` (`sha256:<64 hex>`) tidak tersedia atau formatnya tidak valid, proses ditolak dengan galat yang jelas sebelum/tanpa mengeksekusi file.
  - Jika ukuran akhir tidak lengkap atau hash SHA-256 tidak cocok, berkas sementara dihapus dan `UpdateIntegrityError` ditampilkan kepada pengguna.
  - Sebelum `subprocess.Popen` dipanggil, hash SHA-256 berkas `.exe` diverifikasi ulang di disk.
- **Proteksi Environment Pengembangan**: Jika aplikasi dijalankan dari source (`not is_frozen_app()`), pembaruan installer tidak dieksekusi agar environment pengembangan tidak tertimpa; dialog memberikan informasi yang jelas dan pilihan membuka halaman GitHub Releases resmi.

### Penanganan Kondisi Jaringan & Error
| Kondisi | Kelas Exception | Respons ke Pengguna |
|---|---|---|
| Tidak ada koneksi / DNS / TLS gagal | `UpdateNetworkError` | Pesan spesifik bahwa perangkat tidak terhubung ke GitHub via HTTPS |
| Koneksi atau pembacaan habis waktu | `UpdateTimeoutError` | Pesan timeout (`timeout`) agar memeriksa kestabilan internet |
| Kuota API terlampaui (HTTP 403/429) | `UpdateRateLimitError` | Pesan rate limit GitHub API dan anjuran mencoba beberapa menit lagi |
| Release / asset `.exe` tidak ada (HTTP 404) | `UpdateNotFoundError` | Pesan bahwa rilis terbaru atau asset installer Windows tidak ditemukan |
| Unduhan terputus / ukuran tidak cocok | `UpdateIntegrityError` | Penghapusan file `.part` & pesan berkas tidak lengkap |
| Metadata digest hilang / SHA-256 mismatch | `UpdateIntegrityError` | Penolakan mutlak eksekusi installer & pembersihan berkas gagal verifikasi |

---

## 4. Prosedur Instalasi Pembaruan oleh Pengguna

1. Pembaruan dapat dimulai secara otomatis lewat notifikasi (`Update Now` pada `UpdateNotificationDialog` setelah `QTimer` startup 10 detik) maupun secara manual lewat menu **Help → Check for Updates...**.
2. Saat pemeriksaan berlangsung, indikator status muncul sementara `UpdateWorker` memeriksa GitHub Releases tanpa membekukan viewer maupun GUI.
3. Jika memilih **Update Now** (atau pemeriksaan manual menemukan versi baru), `UpdateDialog` menampilkan versi saat ini, versi terbaru, tanggal rilis, ukuran installer, status digest SHA-256, dan catatan rilis.
4. Klik **Download & Install** (atau **Open Release Page** untuk mengunduh manual, atau **Later**).
5. Saat unduhan berjalan, progress bar dan persentase diperbarui secara real-time.
6. Setelah unduhan selesai dan hash SHA-256 cocok, pengguna diminta mengonfirmasi penutupan HILALONE.
7. HILALONE memastikan tidak ada pipeline/stacking worker aktif, menjalankan installer menggunakan `subprocess.Popen`, lalu menutup jendela secara normal (`closeEvent` menyimpan preferensi `config.ini`).
8. Wizard **Inno Setup 7** berjalan seperti instalasi normal. Karena `AppId={{8D6B59C2-4F4B-4D17-9E2E-7A4D53D1B001}}` dan instalasi per-user (`{localappdata}\Programs\HILALONE`) dipertahankan tetap, instalasi memperbarui program dengan aman tanpa menghapus `config.ini`, `logs\`, `updates\`, maupun data citra pengguna di `%LOCALAPPDATA%\HILALONE`.

---

## 5. Konsistensi Versi & Prosedur Publikasi Rilis (Untuk Kedua Developer)

### Lokasi Versi yang Wajib Disinkronkan Saat Rilis Baru
Setiap kenaikan versi (`<X.Y.Z>`, mis. `1.1.0`) wajib diselaraskan pada seluruh berkas berikut:
1. `src/hilalone/__init__.py` → `__version__ = "<X.Y.Z>"` (sumber kebenaran runtime & updater).
2. `pyproject.toml` → `version = "<X.Y.Z>"`.
3. `HILALONE.iss` → `#define MyAppVersion "<X.Y.Z>"` dan `VersionInfoVersion=<X.Y.Z>.0` (**JANGAN ubah `AppId` atau `PrivilegesRequired=lowest`**).
4. `file_version_info.txt` → `filevers=(X, Y, Z, 0)`, `prodvers=(X, Y, Z, 0)`, `FileVersion`, `ProductVersion`.
5. `website/src/data/siteConfig.ts` → `version`, `downloadUrl`, `installerFilename`, `fileSize`, `releaseDate`, `sha256`, `releasePageUrl` (serta catatan versi pada `README.md` / `BUILD_README.md` bila diperbarui).

### Standar Penamaan File Installer Rilis
- Rilis `v1.0.0` saat ini memakai nama aset `HILALONE_Setup_v1.0.exe` dan tetap didukung penuh.
- Untuk seluruh rilis berikutnya (`v1.1.0` dst.), gunakan standar penamaan konsisten:
  **`HILALONE_Setup_v<X.Y.Z>.exe`** (contoh: `HILALONE_Setup_v1.1.0.exe`).
- Skrip lokal `build_installer.bat` menghasilkan `release\HILALONE_Setup.exe`; salin/rename hasilnya menjadi `release\HILALONE_Setup_v<X.Y.Z>.exe` sebelum diunggah ke GitHub Releases (atau sesuaikan `OutputBaseFilename` + pengecekan `build_installer.bat` bersamaan).

### Checklist 8 Langkah Membuat Rilis Baru (Untuk Kedua Developer)
1. **Merge ke `main`**: pastikan seluruh PR/fitur lulus seluruh `pytest` di branch fitur dan sudah di-merge ke `main`.
2. **Bump version**: perbarui versi secara konsisten di ke-5 lokasi (`src/hilalone/__init__.py`, `pyproject.toml`, `HILALONE.iss`, `file_version_info.txt`, dan konfigurasi website). Pastikan `git diff --check` dan `pytest` kembali lulus.
3. **Build executable ONE-DIR**: aktifkan `.venv` (dengan `requirements-build.txt` terpasang) lalu jalankan `build_windows.bat` hingga `dist\HILALONE\HILALONE.exe` selesai dan uji jalankan (`--bundle-verify` dan uji manual GUI).
4. **Build installer Windows**: jalankan `build_installer.bat` (Inno Setup 7) hingga `release\HILALONE_Setup.exe` terkompilasi, lalu beri nama unggahan `HILALONE_Setup_v<X.Y.Z>.exe`.
5. **Hitung dan verifikasi SHA-256**: jalankan di PowerShell:
   ```powershell
   Get-FileHash .\release\HILALONE_Setup_v<X.Y.Z>.exe -Algorithm SHA256
   ```
   Catat nilai hex SHA-256 untuk verifikasi metadata `digest` aset setelah diunggah ke GitHub Releases.
6. **Buat GitHub Release**: pada GitHub (`akuirulanam5-prog/HILALONE`), buat rilis baru dengan tag `v<X.Y.Z>` dari commit `main`. Biarkan status sebagai **Latest / Stable release** (jangan centang *pre-release* atau *draft* untuk rilis reguler).
7. **Upload installer**: unggah berkas `HILALONE_Setup_v<X.Y.Z>.exe` ke aset rilis tersebut. Setelah terunggah, pastikan field `digest` (`sha256:...`) pada metadata asset di GitHub API (`releases/latest`) tersedia dan sama persis dengan hasil `Get-FileHash`.
8. **Isi release notes & sinkronkan website**: tulis catatan rilis (perubahan, perbaikan bug, SHA-256, instruksi upgrade aman), terbitkan rilis, lalu perbarui `website/src/data/siteConfig.ts` dengan `version`, `downloadUrl`, `fileSize`, `releaseDate`, `sha256`, dan `releasePageUrl` yang baru.
