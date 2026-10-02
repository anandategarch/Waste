@echo off
setlocal
chcp 65001 >nul
title Waste Anomaly Detection
color 0A
cls
echo ============================================================
echo   WASTE ANOMALY DETECTION - v2.0.0
echo ============================================================
echo.
echo  Membuka aplikasi dengan 7 tab (PRO Dashboard v2.0):
echo    1. Dashboard     - KPI + filter + interactive charts + drill-down
echo    2. Hasil         - preview tabel hasil (Detail/Anomali/Cabang/Top/Pareto)
echo    3. Visualisasi   - 12 grafik matplotlib + export PNG
echo    4. Ringkasan    - ringkasan run terakhir
echo    5. Run Pipeline  - pilih workbook + Key Akhir + jalankan
echo    6. Konfigurasi  - editor threshold (simpan ke config.json)
echo    7. Bantuan      - instruksi pakai + 12 sinyal + drill-down workflow
echo.
echo  Pastikan SETUP.bat sudah dijalankan minimal sekali.
echo.
echo  Tekan ENTER untuk membuka UI...
pause >nul

cd /d "%~dp0"
python ui_app.py
if errorlevel 1 (
    echo.
    echo [ERROR] Gagal menjalankan UI. Pastikan:
    echo   - Python terinstall (python --version ^>= 3.10)
    echo   - SETUP.bat sudah dijalankan (install pandas, numpy, openpyxl)
    pause
)
endlocal
