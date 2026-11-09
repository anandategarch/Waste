"""ui_app.pyw — ENTRY POINT TANPA jendela CMD hitam (pythonw).

Double-click file ini (atau shortcut ke file ini) → aplikasi terbuka
langsung sebagai jendela GUI putih (PySide6), TANPA jendela console
CMD hitam. pythonw.exe = python.exe tanpa console window (stdout/stderr
= None — log ditulis ke file logs/waste_anomaly.log + panel log in-app,
bukan console).

v2.17.6 — permintaan user: "waktu dibuka enggak perlu buka jendela cmd
yang hitam itu. kaya di repo Stock-Monitoring. Jadi warna program python
nya putih gitu."

Cara pakai:
  - Double-click ui_app.pyw → aplikasi terbuka (no console).
  - ATAU buat shortcut desktop ke ui_app.pyw (target: pythonw.exe
    ui_app.pyw, atau langsung file .pyw — Windows asosiasi .pyw dgn
    pythonw.exe bila Python terinstall).
  - ATAU jalankan MULAI.bat (sudah diupdate pakai pythonw).

Catatan:
  - stdout/stderr di-guard ke os.devnull (pythonw → None) supaya
    print() tak crash. Log aplikasi tetap ke file (logging_setup
    RotatingFileHandler) + panel log in-app (QPlainTextEdit).
  - Untuk DEBUG dgn console (lihat log stdout), jalankan:
      python ui_app.py   (pakai python.exe, bukan pythonw — ada console)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Defensive: jalan dari cwd mana pun tetap menemukan paket ui/ & waste_anomaly/
sys.path.insert(0, str(Path(__file__).resolve().parent))

# pythonw (no console) → sys.stdout/sys.stderr = None. Redirect ke devnull
# supaya print() / library yg tulis stdout tidak crash (AttributeError).
# Log aplikasi tetap ke file (logging_setup RotatingFileHandler) + panel
# log in-app — bukan console.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# v2.18.0 audit (L-6): kegagalan IMPORT (dependensi hilang / env rusak /
# PySide6 versi salah) di bawah pythonw = TANPA console, TANPA window,
# TANPA log — aplikasi mati senyap total. Tulis crash file berdampingan
# + MessageBox Win32 (best-effort) supaya user tahu apa yang terjadi.
try:
    from ui.app import main
except Exception:
    import traceback
    from datetime import datetime
    _crash = Path(__file__).resolve().parent / "crash_startup.txt"
    try:
        _crash.write_text(
            "Waste Anomaly gagal start — "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
            + traceback.format_exc(),
            encoding="utf-8")
    except OSError:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "Aplikasi gagal start (gagal impor modul).\n"
            "Detail: lihat file crash_startup.txt di folder aplikasi.",
            "Waste Anomaly", 0x10)
    except Exception:
        pass  # non-Windows / headless — crash file sudah ditulis
    raise

if __name__ == "__main__":
    raise SystemExit(main())
