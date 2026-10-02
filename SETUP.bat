@echo off
setlocal
chcp 65001 >nul
title Waste Anomaly Detection - SETUP (One-Time)
color 0B
cls
echo ============================================================
echo   SETUP - Install Dependencies (One-Time)
echo ============================================================
echo.
echo  Menginstall dependencies untuk Waste Anomaly Detection:
echo    - pandas         (data processing)
echo    - numpy           (numerical computation)
echo    - openpyxl        (Excel metadata - list_sheets)
echo    - python-calamine (Excel READ engine cepat - Rust-based, 7-10x faster)
echo    - matplotlib      (visualisasi grafik)
echo.
echo  Tekan ENTER untuk mulai install...
pause >nul

echo.
echo [1/2] Install Python packages...
python -m pip install --upgrade pip
python -m pip install pandas numpy openpyxl python-calamine matplotlib
if errorlevel 1 (
    echo [ERROR] Gagal install Python packages. Cek instalasi Python Anda.
    echo         Pastikan Python 3.10+ terpasang: python --version
    pause
    exit /b 1
)

echo.
echo [2/2] Verifikasi instalasi...
python -c "import pandas, numpy, openpyxl, matplotlib; import python_calamine; print('OK: pandas', pandas.__version__, '| numpy', numpy.__version__, '| openpyxl', openpyxl.__version__, '| matplotlib', matplotlib.__version__, '| calamine OK')"
if errorlevel 1 (
    echo [ERROR] Verifikasi gagal. Coba install ulang manual.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   SETUP SELESAI!
echo   Sekarang jalankan MULAI.bat untuk membuka aplikasi.
echo ============================================================
echo.
pause
endlocal
