@echo off
setlocal
chcp 65001 >nul
title Waste Anomaly Detection - BUILD EXE
color 0E
cls
echo ============================================================
echo   BUILD EXE - Waste Anomaly Detection
echo ============================================================
echo.
echo  Membangun file .exe standalone (PyInstaller) supaya aplikasi
echo  bisa dijalankan TANPA install Python di komputer lain.
echo.
echo  Hasil: dist\WasteAnomalyDetection.exe
echo.
echo  Persyaratan:
echo    - Python 3.10+ terpasang + SETUP.bat sudah dijalankan
echo      (build memakai .venv yang dibuat SETUP.bat)
echo    - PyInstaller akan di-install otomatis ke .venv kalau belum ada
echo.
echo  Tekan ENTER untuk mulai build...
pause >nul

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv tidak ditemukan. Jalankan SETUP.bat dulu -
    echo         build memakai virtual environment yang dibuat SETUP.bat.
    pause
    exit /b 1
)
set "PY=%~dp0.venv\Scripts\python.exe"

"%PY%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [1/3] Install PyInstaller...
    "%PY%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Gagal install PyInstaller. Cek koneksi internet.
        pause
        exit /b 1
    )
) else (
    echo [1/3] PyInstaller sudah terpasang.
)

echo.
echo [2/3] Build EXE (±2-5 menit)...
"%PY%" -m PyInstaller waste_anomaly.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build gagal. Baca pesan error di atas.
    echo         Tip: pastikan SETUP.bat sudah dijalankan dan tidak ada
    echo         aplikasi lain yang memakai folder dist\.
    pause
    exit /b 1
)

echo.
echo [3/3] Selesai!
echo.
echo  EXE tersimpan di: dist\WasteAnomalyDetection.exe
echo  Salin file itu ke PC mana pun (tanpa Python) + DATA_WASTE.xlsx Anda.
echo.
echo  CATATAN (v2.4.1): config.json default di-bundle di dalam exe. Saat
echo  pertama kali dijalankan, otomatis disalin ke config.json BERDAMPINGAN
echo  exe — threshold yang diedit lewat tab Konfigurasi + profil filter
echo  (filters.json) + folder data\ + logs\ semuanya TERSIMPAN di situ dan
echo  bertahan setelah aplikasi ditutup.
echo.
pause
endlocal
