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

import sys
from pathlib import Path

# Pastikan repo root ada di sys.path saat pytest dijalankan dari mana pun
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
