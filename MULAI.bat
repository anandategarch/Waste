@echo off
setlocal
chcp 65001 >nul
title Waste Anomaly Detection
color 0A
cls
echo ============================================================
echo   WASTE ANOMALY DETECTION - v1.1.0
echo ============================================================
echo.
echo  Membuka aplikasi dengan 6 tab:
echo    1. Run Pipeline  - pilih workbook + Key Akhir + jalankan
echo    2. Hasil         - preview tabel hasil (Detail/Anomali/Cabang/Top/Pareto)
echo    3. Visualisasi   - 12 grafik matplotlib + export PNG
echo    4. Ringkasan    - ringkasan run terakhir
echo    5. Konfigurasi  - editor threshold (simpan ke config.json)
echo    6. Bantuan      - instruksi pakai + 12 sinyal anomali
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
