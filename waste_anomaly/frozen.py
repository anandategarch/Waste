"""frozen.py — resolusi path PyInstaller (mode exe) vs development (v2.4.1).

MASALAH (ditemukan saat double-check v2.4.0): jalur file yang DITULIS
aplikasi dulunya resolve dari ``Path(__file__)``:

    waste_anomaly/utils.py   → CONFIG_PATH  (config.json — threshold user)
    ui/shared.py             → APP_DIR      (folder data/ + "Buka Folder Sample")

Di exe PyInstaller, ``__file__`` modul menunjuk ke dir ekstraksi temp
``_MEIPASS`` yang DIHAPUS saat aplikasi ditutup. Akibatnya: threshold yang
disimpan user lewat tab Konfigurasi dan profil filter hilang senyap setelah
exe ditutup — kebalikan dari klaim BUILD_EXE.bat ("config.json disimpan
berdampingan dengan exe").

Konvensi sekarang (dipakai semua modul):
    - File WRITABLE (config sidecar, followup.json, folder data/, logs) →
      folder EXE:      ``exe_dir()``  (``Path(sys.executable).parent``).
    - Resource READ-ONLY bundled (ikon, config default) →
      ``bundle_dir()`` (``sys._MEIPASS``; repo root saat dev).
    - ``is_frozen()`` untuk cabang perilaku lain.

Semua fungsi dinamis (dibaca saat runtime) supaya bisa diuji unit dengan
monkeypatch — lihat tests/test_frozen_paths.py.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True saat berjalan sebagai exe PyInstaller (``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """Folder yang BERISI executable — target file writable (sidecar).

    Dev mode: repo root (parent dari paket waste_anomaly/).
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """Dir resource bundled PyInstaller (``sys._MEIPASS``) — read-only.

    Dev mode: repo root (resource asli memang ada di situ — path sama
    dengan exe_dir(), pencarian ikon memeriksa keduanya).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent
