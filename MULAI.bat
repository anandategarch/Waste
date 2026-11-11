@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

REM v2.17.0 - Waste Anomaly Detection (5 tab: Pipeline, Anomali, Hari
REM Mencurigakan, Banding Periode, Follow Up).
REM
REM v2.17.6 - jalankan TANPA jendela CMD hitam (pythonw + ui_app.pyw).
REM Double-click ui_app.pyw JUGA langsung buka GUI (no console).
REM Untuk DEBUG dgn console (lihat log stdout): python ui_app.py
REM v2.18.1 - chcp 65001: pesan error UTF-8 Indonesia tidak jadi
REM mojibake di console OEM codepage (pola SETUP/BUILD_EXE).
REM v2.18.2 - Proses dari Folder: pemilihan sheet rekap berbasis
REM skor (file dgn sheet seksi DEVIASI tak lagi salah baca).
REM v2.18.3 - kolom TOTAL blank di file gabungan folder kini
REM diisi otomatis (jumlah kolom hari; sel sumber kosong).
REM v2.18.4 - Banding Periode: match resto lintas sumber
REM (nama file 'BJMHAS' = kode DBS '1216.BJMHAS').
REM v2.18.5 - Banding Periode: hanya cabang yang ada di KEDUA bulan
REM (resto baru/tutup disembunyikan); sort Naik = besar dulu;
REM filter: klik-ganda nilai = pilih hanya itu; tab Scorecard
REM Cabang dihapus (permintaan user).
REM v2.18.6 - Pop-up detail hanya terbuka via KLIK-GANDA/Enter
REM (klik tunggal tak sengaja tak lagi memunculkan pop-up);
REM pop-up banding (resto/item) kini punya kolom centang
REM Follow Up.

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
