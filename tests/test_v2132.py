"""test_v2132.py — v2.13.2 Task 4 (sisa): Benford DQ check.

- ⑪ Benford DQ check (DQ_BENFORD): digit pertama vs Benford — hanya
  dibenderai bila deviasi ≥ 10 pp (data asli: 6,4 pp → TIDAK dibenderai,
  jujur); sampel < 500 → skip.
- ⑨ DI ATAS % CABANG (persentil peer, money_ranking) dan ⑩ Panel
  Kualitas Data di tab Scorecard DIHAPUS v2.18.5 bersama tab Scorecard
  Cabang & modul waste_anomaly/insights.py (permintaan user).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

from waste_anomaly.data_quality import _check_benford, run_checks  # noqa: E402


# ============================================================
# [B] BENFORD DQ CHECK
# ============================================================

def _benford_df(seed_values: list[float]) -> pd.DataFrame:
    n = len(seed_values)
    data = {str(d): [0.0] * n for d in range(1, 2)}
    for i, v in enumerate(seed_values):
        data["1"][i] = float(v)
    df = pd.DataFrame(data)
    df["NAMA RESTO"] = [f"R{i}" for i in range(n)]
    return df


class TestBenford:
    def test_deviasi_besar_dibenderai(self):
        # 600 nilai berdigit awal 9 (Benford digit-9 ~4,6%) → deviasi > 10pp
        vals = [9 * 10 ** (i % 4) + i for i in range(600)]
        res = _check_benford(_benford_df(vals), 1)
        assert res is not None
        assert res.code == "DQ_BENFORD"
        assert res.severity == "info"

    def test_sampel_kecil_skip(self):
        res = _check_benford(_benford_df([9.0] * 100), 1)
        assert res is None

    def run_benford_naik_di_run_checks(self):
        vals = [9 * 10 ** (i % 4) + i for i in range(600)]
        df = _benford_df(vals)
        checks = run_checks(df, key_akhir=1)
        assert any(c.code == "DQ_BENFORD" for c in checks)

    def test_kolom_hari_hilang_none(self):
        df = pd.DataFrame({"TOTAL": [9.0] * 600})
        assert _check_benford(df, 1) is None
