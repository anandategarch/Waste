"""
ui_app.py — ENTRY POINT aplikasi (tetap dipakai MULAI.bat / shortcut lama).

v2.6.0: UI di-rebuild total dengan PySide6 (lihat paket ui/). Pintu masuk
tetap file ini supaya `python ui_app.py` / MULAI.bat tidak berubah.

Struktur baru:
    ui/shared.py       — konstanta + helper murni (kontrak test lama dijaga)
    ui/theme.py        — palet warna + QSS global
    ui/state.py        — AppContext: state tunggal + signal Qt
    ui/models.py       — PandasTableModel (tabel virtualized tanpa cap)
    ui/workers.py      — pipeline/export/periode di QThread
    ui/widgets.py      — blok anti-terpotong (WLabel, MplCanvas, ChartCard,
                         DataTable, KPI)
    ui/view_*.py       — 8 view (Anomali default, Jelajah, Waktu, Uang,
                         Peer, Kualitas, Banding Periode, Pipeline)
    ui/app.py          — MainWindow + main()
"""

from __future__ import annotations

import sys
from pathlib import Path

# Defensive: jalan dari cwd mana pun tetap menemukan paket ui/ & waste_anomaly/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
