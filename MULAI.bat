@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM v2.17.0 - Waste Anomaly Detection (6 tab: Anomali, Follow Up,
REM Hari Mencurigakan, Scorecard Cabang, Banding Periode, Pipeline).
REM
REM v2.17.6 - jalankan TANPA jendela CMD hitam (pythonw + ui_app.pyw).
REM Double-click ui_app.pyw JUGA langsung buka GUI (no console).
REM Untuk DEBUG dgn console (lihat log stdout): python ui_app.py

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
