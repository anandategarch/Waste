@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Waste Anomaly Detection
color 0A
cls
echo ============================================================
echo   WASTE ANOMALY DETECTION - v2.8.0
echo ============================================================
echo.
echo  PySide6 anomaly workbench - 5 view:
echo    1. Anomali   - tabel anomali ter-ranked skor + detail
echo                   12 sinyal + drill-down 1-klik
echo    2. Jelajah   - chart interaktif klik-untuk-filter + tabel
echo                   data + 9 chart statistik
echo    3. Waktu     - pola waste per hari + kelas hari mod-7
echo    4. Banding   - compare periode bulan-ke-bulan
echo    5. Pipeline  - run/batal + editor threshold + log
echo.
echo  Sidebar filter bisa disembunyikan: Ctrl+Shift+F
echo  Panel detail bisa dirikan: tombol Rapikan Detail
echo.
echo  Pastikan SETUP.bat sudah dijalankan minimal sekali.
echo.
echo  Tekan ENTER untuk membuka UI...
pause >nul

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" ui_app.py
) else (
    REM v2.7.0: fallback launcher "py -3" bila "python" tidak ada di PATH
    REM (konsisten dgn SETUP.bat).
    where python >nul 2>&1
    if errorlevel 1 (
        py -3 ui_app.py
    ) else (
        python ui_app.py
    )
)
if errorlevel 1 (
    echo.
    echo [ERROR] Gagal menjalankan UI. Pastikan:
    echo   - Python terinstall: python --version
    echo   - SETUP.bat sudah dijalankan minimal sekali
    echo   - Kalau SETUP.bat selesai tanpa error tapi UI tetap gagal,
    echo     jalankan ulang SETUP.bat agar .venv dibuat dengan benar.
    pause
)
endlocal
