"""Test suite Waste Anomaly Detection.

Cara run (dari root repo):
    python -m pytest tests/ -v

Test layers:
1. test_key_normalization — unit: normalisasi kunci join (_key_str, dtype trap F1)
2. test_bom_join — unit: stage_05_bom join numerik vs string (bug F1 v2.3.2)
3. test_pipeline_regression — golden output end-to-end pada fixture
   DATA_WASTE.xlsx (25.901 baris) — mengunci baseline M-fidelity.

GOLDEN NUMBERS (v2.3.2, pandas 2.2.3): kalau angka ini berubah AKIBAT
perubahan kode yang disengaja, update golden + tulis alasannya di commit.
Kalau berubah tanpa alasan → REGRESI, jangan di-update diam-diam.
"""

import gc
import sys
from pathlib import Path

import pytest

# Pastikan repo root ada di sys.path saat pytest dijalankan dari mana pun
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# v2.12.4 — penghancuran widget sisa test yang AMAN (anti segfault)
# ============================================================
# Diagnosa (data asli + 7 file test v2 dijalankan bersamaan): cyclic
# garbage collector Python menghapus widget YATIM (view dibuat test
# sebelumnya tanpa close — C++ side ikut dihapus sinkron oleh shiboken)
# TEPAT SAAT Qt sedang melukis tabel test lain (processEvents di dalam
# busy_feedback → paint → data() → alokasi pandas → gc) → heap rusak →
# Segmentation fault pada GC berikutnya. Di app asli pola ini tak ada
# (semua view berparent ke QTabWidget — tidak pernah jadi yatim);
# ini murni artefak suite yang membuat PULUHAN view per run.
# v2.12.3 "lolos" karena tabel lebih pendek (slicer+hint 120px) —
# pola alokasi paint tak pernah memicu gc di momen fatal; v2.12.4
# (tabel lebih tinggi) memindahkan timing → crash deterministik 3/3.
# Fix di lapisan yang benar (infra test): setiap test menutup +
# deleteLater + processEvents SEMUA widget top-level yang dibuatnya —
# tidak ada yatim yang bisa dihapus gc di tengah paint test lain.
@pytest.fixture(autouse=True)
def _dispose_orphan_widgets():
    app = None
    pre: list = []
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            pre = list(app.topLevelWidgets())
    except Exception:
        app = None
    yield
    if app is None:
        return
    try:
        fresh = [w for w in app.topLevelWidgets()
                 if not any(w is p for p in pre)]
        for w in fresh:
            w.close()
        app.processEvents()
        # deleteLater (bukan delete sinkron) — aman walau event loop
        # sedang memproses; benar-benar dihancurkan oleh processEvents.
        fresh = [w for w in app.topLevelWidgets()
                 if not any(w is p for p in pre)]
        for w in fresh:
            w.deleteLater()
        app.processEvents()
        gc.collect()
        app.processEvents()
    except Exception:
        pass
