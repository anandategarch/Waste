@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Waste Anomaly Detection - SETUP (One-Time)
color 0B
cls
echo ============================================================
echo   SETUP - Install Dependencies (One-Time) - v2.10.3
echo ============================================================
echo.
echo  Menginstall dependencies untuk Waste Anomaly Detection:
echo    - pandas          (data processing)
echo    - numpy           (numerical computation)
echo    - openpyxl        (Excel I/O)
echo    - python-calamine (Excel READ engine cepat, Rust-based)
echo    - PySide6         (framework UI Qt6)
echo.
echo  Install dilakukan ke .venv lokal di folder ini.
echo  Keuntungan: tidak mencemari Python global, dan menghindari
echo  batas panjang path Windows 260 karakter yang bikin pip gagal
echo  menulis file PySide6 di Python Microsoft Store.
echo.
echo  Tekan ENTER untuk mulai install...
pause >nul

cd /d "%~dp0"

echo [1/5] Cek Python...
REM v2.7.0: fallback launcher "py -3" bila "python" tidak ada di PATH
REM (umum di Windows: python.org installer hanya memasang py.exe).
set "PYCMD="
python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [ERROR] Perintah "python" maupun "py -3" tidak ditemukan di PATH.
    echo         Install Python 3.10+ dari https://python.org atau dari
    echo         Microsoft Store, lalu jalankan SETUP.bat lagi.
    pause
    exit /b 1
)
%PYCMD% --version

echo.
echo [2/5] Buat virtual environment .venv...
if exist ".venv\Scripts\python.exe" (
    echo        .venv sudah ada - dipakai ulang.
) else (
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat .venv. Cek error di atas.
        pause
        exit /b 1
    )
)
set "PY=%~dp0.venv\Scripts\python.exe"

REM v2.7.0: validasi .venv benar-benar bisa jalan — .venv setengah jadi
REM (instalasi python Microsoft Store di-upgrade / antivirus menghapus
REM file) membuat langkah berikutnya gagal dengan pesan membingungkan.
"%PY%" -c "import sys; print(sys.version)"
if errorlevel 1 (
    echo [WARN] .venv rusak / tidak bisa dijalankan.
    echo        Membuat ulang .venv satu kali secara otomatis...
    rd /s /q ".venv"
    %PYCMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat ulang .venv. Hapus folder .venv secara
        echo         manual, lalu jalankan SETUP.bat lagi.
        pause
        exit /b 1
    )
    "%PY%" -c "import sys; print(sys.version)"
    if errorlevel 1 (
        echo [ERROR] .venv baru tetap tidak bisa dijalankan - cek
        echo         instalasi Python %PYCMD%, lalu jalankan SETUP.bat lagi.
        pause
        exit /b 1
    )
)

echo.
echo [3/5] Upgrade pip...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Gagal upgrade pip. Cek koneksi internet, lalu jalankan
    echo         SETUP.bat ulang.
    pause
    exit /b 1
)

echo.
echo [4/5] Install dependencies ke .venv...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pipfail

echo.
echo [5/5] Verifikasi instalasi...
"%PY%" -c "import pandas, numpy, openpyxl, python_calamine, PySide6; print('OK: pandas', pandas.__version__, '| numpy', numpy.__version__, '| openpyxl', openpyxl.__version__, '| PySide6', PySide6.__version__, '| calamine OK')"
if errorlevel 1 (
    echo [ERROR] Verifikasi gagal. Coba jalankan SETUP.bat ulang.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SETUP SELESAI!
echo   Dependensi terpasang di .venv - aplikasi tetap offline.
echo   Sekarang jalankan MULAI.bat untuk membuka aplikasi.
echo ============================================================
echo.
pause
endlocal
exit /b 0

:pipfail
echo.
echo [ERROR] Gagal install Python packages ke .venv.
echo.
echo  Kalau errornya menyebut "No such file or directory" di file
echo  PySide6, itu batas panjang path Windows = 260 karakter
echo  MAX_PATH. Pilih salah satu solusi:
echo.
echo   A. Pindahkan folder repo ini ke path pendek, contoh:
echo         C:\Waste
echo      lalu jalankan SETUP.bat lagi dari lokasi baru.
echo.
echo   B. Aktifkan Windows Long Path support:
echo      1. Jalankan CMD sebagai Administrator
echo      2. Copy perintah ini lalu Enter:
echo         reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f
echo      3. RESTART PC
echo      4. Jalankan SETUP.bat lagi.
echo.
echo  Info lengkap: https://pip.pypa.io/warnings/enable-long-paths
echo.
pause
exit /b 1
