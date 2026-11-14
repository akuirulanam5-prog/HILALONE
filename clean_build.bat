@echo off
setlocal
rem ============================================================================
rem  HILALONE — Pembersih Artefak Build (Aman: Tidak Menyentuh Source / Data)
rem ============================================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo Membersihkan artefak build sementara HILALONE...

if exist "%ROOT%build" (
    echo   Menghapus folder build\
    rmdir /s /q "%ROOT%build"
)

if exist "%ROOT%dist\HILALONE" (
    echo   Menghapus folder dist\HILALONE\
    rmdir /s /q "%ROOT%dist\HILALONE"
)

if exist "%ROOT%dist\HILALONE.exe" (
    echo   Menghapus berkas dist\HILALONE.exe
    del /q "%ROOT%dist\HILALONE.exe"
)

echo Selesai. Source code (src\), aset (assets\), tes (tests\), venv (.venv\),
echo serta data pengguna tetap aman dan tidak disentuh.
exit /b 0
