@echo off
setlocal
chcp 65001 >nul
title Waste Anomaly Detection
color 0A
cls
echo ============================================================
echo   WASTE ANOMALY DETECTION - v2.3.2
echo ============================================================
echo.
echo  Membuka aplikasi dengan 10 tab (PRO Dashboard v2.3):
echo    1. Dashboard       - KPI + filter + interactive charts + drill-down
echo    2. Compare Cabang - side-by-side 2 cabang (4 chart + metrics)
echo    3. Quadrant       - scatter SISTEMIK/MUSIMAN/LOKAL-KRONIS/INSIDEN
echo    4. Rate League    - ranking cabang by rate anomali
echo    5. Hasil          - preview tabel + Export Laporan Excel (6 sheet)
echo    6. Visualisasi    - 12 grafik matplotlib + export PNG
echo    7. Ringkasan      - ringkasan run terakhir
echo    8. Run Pipeline   - pilih workbook + Key Akhir + jalankan + batal
echo    9. Konfigurasi    - editor threshold (simpan ke config.json)
echo   10. Bantuan      - instruksi pakai + 12 sinyal + drill-down workflow
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
