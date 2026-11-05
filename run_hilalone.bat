@echo off
rem ===========================================================
rem  Peluncur HILALONE (Windows)
rem  - Memakai Python dari .venv (tanpa aktivasi PowerShell).
rem  - PYTHONPATH diarahkan ke folder "src" (src layout).
rem  Cara pakai: klik ganda berkas ini, atau jalankan dari cmd.
rem ===========================================================
setlocal
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [GALAT] Python dari .venv tidak ditemukan:
    echo         %PYTHON_EXE%
    echo Pastikan virtual environment .venv sudah dibuat di folder proyek.
    pause
    exit /b 1
)

set "PYTHONPATH=%ROOT%src"
cd /d "%ROOT%"
"%PYTHON_EXE%" -m hilalone.main
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [GALAT] HILALONE berhenti dengan kode %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
