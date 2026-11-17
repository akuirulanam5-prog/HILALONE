@echo off
setlocal EnableDelayedExpansion
rem ============================================================================
rem  HILALONE v1.0 — Windows Build Script (PyInstaller ONE-DIR)
rem  Menggunakan virtual environment proyek (.venv) dan HILALONE.spec
rem ============================================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV_ACTIVATE=%ROOT%.venv\Scripts\activate.bat"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
set "SPEC_FILE=%ROOT%HILALONE.spec"
set "BUILD_LOG=%ROOT%build\pyinstaller_build.log"
set "STAGE_DIST=%ROOT%build\dist_stage"
set "STAGE_WORK=%ROOT%build\work"
set "FINAL_DIST=%ROOT%dist\HILALONE"

echo ==============================================================
echo  HILALONE v1.0 - Windows Executable Build (ONE-DIR)
echo ==============================================================

if not exist "%PYTHON_EXE%" (
    echo [GALAT] Virtual environment tidak ditemukan di:
    echo         %PYTHON_EXE%
    exit /b 1
)

if exist "%VENV_ACTIVATE%" (
    call "%VENV_ACTIVATE%"
)

echo [1/7] Memeriksa versi Python dan PyInstaller...
for /f "tokens=2 delims= " %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PY_VER=%%v"
echo       Python terdeteksi: %PY_VER%
echo %PY_VER% | findstr /b "3.10." >nul
if errorlevel 1 (
    echo [GALAT] Versi Python harus 3.10.x, terdeteksi %PY_VER%.
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [GALAT] PyInstaller belum terpasang di .venv.
    echo         Jalankan: .venv\Scripts\python.exe -m pip install pyinstaller
    exit /b 1
)
for /f %%p in ('"%PYTHON_EXE%" -m PyInstaller --version 2^>^&1') do set "PI_VER=%%p"
echo       PyInstaller terdeteksi: %PI_VER%

echo [2/7] Memeriksa file spec dan aset branding wajib...
if not exist "%SPEC_FILE%" (
    echo [GALAT] Berkas spec tidak ditemukan: %SPEC_FILE%
    exit /b 1
)
for %%F in (
    "assets\branding\hilalone_app_icon.ico"
    "assets\branding\hilalone_app_icon_night_red.ico"
    "assets\branding\hilalone_icon_standard.png"
    "assets\branding\hilalone_icon_night_red.png"
    "assets\branding\hilalone_logo_standard.png"
    "assets\branding\hilalone_logo_night_red_separate.png"
    "assets\branding\hilalone_logo_night_red.png"
    "file_version_info.txt"
) do (
    if not exist "%%~F" (
        echo [GALAT] Aset atau file wajib tidak ditemukan: %%~F
        exit /b 1
    )
)

echo [3/7] Menjalankan pre-build validation (versi dan uji branding/smoke)...
"%PYTHON_EXE%" -c "import sys; sys.path.insert(0, 'src'); import hilalone, PySide6, numpy, astropy, tifffile, rawpy, av, scipy, skimage; print('Versi aplikasi:', hilalone.__version__)"
if errorlevel 1 (
    echo [GALAT] Validasi modul runtime gagal.
    exit /b 1
)
set "QT_QPA_PLATFORM=offscreen"
"%PYTHON_EXE%" -m pytest tests\test_branding_and_resources.py tests\test_environment.py -q
if errorlevel 1 (
    echo [GALAT] Pre-build validation tests gagal. Build dibatalkan.
    exit /b 1
)

if not exist "%ROOT%build" mkdir "%ROOT%build"
if not exist "%ROOT%dist" mkdir "%ROOT%dist"
if exist "%STAGE_WORK%" rmdir /s /q "%STAGE_WORK%"
if exist "%STAGE_DIST%" rmdir /s /q "%STAGE_DIST%"

echo [4/7] Menjalankan PyInstaller (ONE-DIR ke staging terlebih dahulu)...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --workpath "%STAGE_WORK%" --distpath "%STAGE_DIST%" "%SPEC_FILE%" > "%BUILD_LOG%" 2>&1
if errorlevel 1 (
    echo [GALAT] PyInstaller gagal. Periksa log lengkap di:
    echo         %BUILD_LOG%
    type "%BUILD_LOG%" | findstr /i "ERROR Traceback failed"
    exit /b 1
)

if not exist "%STAGE_DIST%\HILALONE\HILALONE.exe" (
    echo [GALAT] HILALONE.exe tidak ditemukan pada hasil staging!
    exit /b 1
)

echo [5/7] Memindahkan hasil build terverifikasi ke dist\HILALONE...
if exist "%FINAL_DIST%" rmdir /s /q "%FINAL_DIST%"
move /y "%STAGE_DIST%\HILALONE" "%FINAL_DIST%" >nul
if errorlevel 1 (
    echo [GALAT] Gagal memindahkan hasil build ke %FINAL_DIST%. Pastikan HILALONE.exe tidak sedang berjalan.
    exit /b 1
)
if exist "%STAGE_DIST%" rmdir /s /q "%STAGE_DIST%"

echo [6/7] Menambahkan peluncur mode diagnostik HILALONE_Diagnostic.bat...
(
    echo @echo off
    echo setlocal
    echo set "APP_DIR=%%~dp0"
    echo echo Memulai HILALONE dalam mode diagnostik ^(console + crash log^)...
    echo echo Log tersimpan di %%LOCALAPPDATA%%\HILALONE\logs\
    echo "%%APP_DIR%%HILALONE.exe" --diagnostic %%*
) > "%FINAL_DIST%\HILALONE_Diagnostic.bat"

echo [7/7] Verifikasi akhir hasil distribusi...
if not exist "%FINAL_DIST%\HILALONE.exe" (
    echo [GALAT] HILALONE.exe tidak ditemukan di %FINAL_DIST%
    exit /b 1
)

echo.
echo ==============================================================
echo  BUILD BERHASIL!
echo  Executable utama : %FINAL_DIST%\HILALONE.exe
echo  Mode diagnostik  : %FINAL_DIST%\HILALONE_Diagnostic.bat
echo  Build log        : %BUILD_LOG%
echo ==============================================================
exit /b 0
