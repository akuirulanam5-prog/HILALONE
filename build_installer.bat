@echo off
setlocal EnableDelayedExpansion
rem ============================================================================
rem  HILALONE v1.0.0 - Windows Installer Build Script (Inno Setup 7)
rem  Mengompilasi HILALONE.iss dari dist\HILALONE\ menjadi release\HILALONE_Setup.exe
rem ============================================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "DIST_EXE=%ROOT%dist\HILALONE\HILALONE.exe"
set "ISS_FILE=%ROOT%HILALONE.iss"
set "OUT_EXE=%ROOT%release\HILALONE_Setup.exe"
set "LOG_FILE=%ROOT%build\innosetup_build.log"
set "ISCC_EXE="

echo ==============================================================
echo  HILALONE v1.0.0 - Windows Installer Build (Inno Setup 7)
echo ==============================================================

if not exist "%DIST_EXE%" (
    echo [GALAT] Hasil build ONE-DIR tidak ditemukan di:
    echo         %DIST_EXE%
    echo         Jalankan build_windows.bat terlebih dahulu.
    exit /b 1
)

if not exist "%ISS_FILE%" (
    echo [GALAT] Skrip installer tidak ditemukan: %ISS_FILE%
    exit /b 1
)

for %%P in (
    "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
    "C:\Program Files\Inno Setup 7\ISCC.exe"
) do (
    if exist "%%~P" (
        set "ISCC_EXE=%%~P"
        goto :found_iscc
    )
)

where iscc >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('where iscc') do (
        set "ISCC_EXE=%%~I"
        goto :found_iscc
    )
)

echo [GALAT] Compiler Inno Setup 7 (ISCC.exe) tidak ditemukan.
echo         Pasang Inno Setup 7 terlebih dahulu, misal:
echo         winget install --id JRSoftware.InnoSetup.7 -e --scope user
exit /b 1

:found_iscc
echo [1/3] Compiler ditemukan: %ISCC_EXE%
if not exist "%ROOT%build" mkdir "%ROOT%build"
if not exist "%ROOT%release" mkdir "%ROOT%release"

echo [2/3] Mengompilasi %ISS_FILE% ...
"%ISCC_EXE%" "%ISS_FILE%" > "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [GALAT] Kompilasi Inno Setup 7 gagal. Periksa log lengkap di:
    echo         %LOG_FILE%
    type "%LOG_FILE%" | findstr /b /i "Error"
    exit /b 1
)

echo [3/3] Memverifikasi hasil installer...
if not exist "%OUT_EXE%" (
    echo [GALAT] Installer tidak ditemukan di: %OUT_EXE%
    exit /b 1
)

echo.
echo ==============================================================
echo  BUILD INSTALLER BERHASIL
echo  Installer : %OUT_EXE%
echo  Build log : %LOG_FILE%
echo ==============================================================
exit /b 0

