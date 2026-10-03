"""
ui_app.py — ENTRY POINT aplikasi (tetap dipakai MULAI.bat / shortcut lama).

Sejak v2.4.0 kode UI dipecah ke paket `ui/` (anti god-object — dulu satu
class 102 metode / 3.256 baris):

    ui/shared.py       — konstanta + registry font + helper murni
    ui/widgets.py      — SimpleLogPopup, KPICard, FilterChip
    ui/base.py         — infrastruktur app (styling, tab scaffolding, log)
    ui/tab_*.py        — 10 modul tab (dashboard, compare, quadrant, rate,
                         result, viz, summary, run, config, help)
    ui/app.py          — komposisi class WasteAnomalyApp (11 mixin) + main()

File ini tetap menjadi pintu masuk supaya `MULAI.bat` dan kebiasaan user
(`python ui_app.py`) tidak berubah. Semua metode lama dipindah VERBATIM —
perilaku runtime identik.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Defensive: jalan dari cwd mana pun tetap menemukan paket ui/ & waste_anomaly/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.app import WasteAnomalyApp, main  # noqa: E402,F401 — re-export API lama

if __name__ == "__main__":
    main()
