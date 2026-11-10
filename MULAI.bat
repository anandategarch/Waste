@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

REM v2.17.0 - Waste Anomaly Detection (6 tab: Anomali, Follow Up,
REM Hari Mencurigakan, Scorecard Cabang, Banding Periode, Pipeline).
REM
REM v2.17.6 - jalankan TANPA jendela CMD hitam (pythonw + ui_app.pyw).
REM Double-click ui_app.pyw JUGA langsung buka GUI (no console).
REM Untuk DEBUG dgn console (lihat log stdout): python ui_app.py
REM v2.18.1 - chcp 65001: pesan error UTF-8 Indonesia tidak jadi
REM mojibake di console OEM codepage (pola SETUP/BUILD_EXE).
REM v2.18.2 - Proses dari Folder: pemilihan sheet rekap berbasis
REM skor (file dgn sheet seksi DEVIASI tak lagi salah baca).

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" ui_app.pyw
) else (
    where pythonw >nul 2>&1
    if errorlevel 1 (
        where py >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] pythonw / py tidak ditemukan.
            echo   Jalankan SETUP.bat dulu, atau install Python 3.10+.
            pause
        ) else (
            start "" py -3 ui_app.pyw
        )
    ) else (
        start "" pythonw ui_app.pyw
    )
)
endlocal
