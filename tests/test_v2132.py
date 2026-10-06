"""test_v2132.py — v2.13.2 Task 4: persentil peer + Benford + panel DQ.

- ⑨ DI ATAS % CABANG: persentil TOTAL di antara peer AKTIF item sama
  (money_ranking) — 100 = paling boros; tahan skew; padanan robust
  z-score dgn istilah awam.
- ⑪ Benford DQ check (DQ_BENFORD): digit pertama vs Benford — hanya
  dibenderai bila deviasi ≥ 10 pp (data asli: 6,4 pp → TIDAK dibenderai,
  jujur); sampel < 500 → skip.
- ⑩ Panel Kualitas Data di tab Scorecard (resurface run_checks — dulu
  hanya sheet export).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

from waste_anomaly.data_quality import _check_benford, run_checks  # noqa: E402
from waste_anomaly.insights import money_ranking  # noqa: E402


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _peer_df() -> pd.DataFrame:
    """4 cabang item sama dgn TOTAL bertingkat + kolom KELEBIHAN/median."""
    rows = []
    totals = [100.0, 50.0, 25.0, 10.0]
    for r, t in zip(["A", "B", "C", "D"], totals):
        rows.append({
            "NAMA RESTO": r, "NAMA BARANG": "MIE", "JENIS": "WASTE",
            "KETERANGAN": "Handling", "SOURCE DATA": "W",
            "SATUAN": "GR", "TOTAL": t, "Count Hari": 25,
            "KELEBIHAN": t - 8.0, "PEER MEDIAN (AKTIF)": 8.0,
            "PROFIL": "Tiap Hari", "ANOMALY STATUS": "Perlu Review",
        })
    return pd.DataFrame(rows)


# ============================================================
# [A] PERSENTIL PEER (DI ATAS % CABANG)
# ============================================================

class TestPersentilPeer:
    def test_nilai_persentil_bertingkat(self):
        out = money_ranking(_peer_df(), top_n=10)
        # peer aktif = 4 → rank pct: tertinggi 100, lalu 75, 50, 25
        vals = dict(zip(out["NAMA RESTO"], out["DI ATAS % CABANG"]))
        assert vals["A"] == pytest.approx(100.0)
        assert vals["B"] == pytest.approx(75.0)
        assert vals["C"] == pytest.approx(50.0)
        assert vals["D"] == pytest.approx(25.0)

    def test_kunci_peer_hilang_nan(self):
        df = _peer_df().drop(columns=["SOURCE DATA"])
        out = money_ranking(df, top_n=10)
        assert out["DI ATAS % CABANG"].isna().all()
        # kolom lain tetap utuh
        assert "DI ATAS % CABANG" in out.columns

    def test_grup_peer_terpisah(self):
        # TEH berdiri sendiri (peer aktif 1) → persentil 100 tetap sah
        df = _peer_df()
        df.loc[df["NAMA RESTO"] == "D", "NAMA BARANG"] = "TEH"
        out = money_ranking(df, top_n=10)
        teh = out[out["NAMA BARANG"] == "TEH"]
        assert teh["DI ATAS % CABANG"].iloc[0] == pytest.approx(100.0)


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


# ============================================================
# [C] PANEL KUALITAS DATA DI TAB SCORECARD (resurface ⑩)
# ============================================================

FIXTURE = REPO / "DATA_WASTE.xlsx"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture tidak ada")
class TestPanelDQScorecard:
    def test_kartu_dq_terisi_data_asli(self):
        _qapp()
        from waste_anomaly.pipeline import run_pipeline
        from ui.state import AppContext
        from ui.view_scorecard import ScorecardView
        s = run_pipeline(workbook_path=str(FIXTURE), key_akhir=31)
        assert s.get("success") is True
        ctx = AppContext({})
        ctx.set_dataset(s["df"], s)
        view = ScorecardView(ctx)
        view._refresh()
        rows = view._dq_table.model().rowCount()
        # data asli: ≥ 4 warning + info (NBSP/SOURCE_VARIANT/SPLIT/NO_BOM)
        assert rows >= 4, f"DQ card cuma {rows} baris"
        # Benford jujur: TIDAK dibenderai utk data asli (deviasi 6,4pp)
        dqdf = view._dq_table.model().dataframe
        assert "DQ_BENFORD" not in set(dqdf["KODE"])
        view.close()
        view.deleteLater()
