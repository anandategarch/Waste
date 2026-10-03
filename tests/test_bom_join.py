"""Unit test — stage_05_bom (join BOM dengan kunci normalisasi _key_str).

Mengunci bug-fix F1 (v2.3.2): sebelumnya stages.py pakai `astype(str)` di
kedua sisi — outlet numerik (1049.0) tidak PERNAH match dengan "1049" di
sheet BOM → TOTAL BOM semua NaN → sinyal S6/S7 mati diam-diam.
"""

import numpy as np
import pandas as pd

from waste_anomaly.stages import stage_05_bom

CONFIG = {"thresholds": {}}


def _make_df(resto: list, item: str = "AYAM WHOLE") -> pd.DataFrame:
    """Frame minimal untuk stage_05_bom — TANPA kolom TOTAL BOM supaya
    jalur join sheet BOM benar-benar dieksekusi (kolom TOTAL BOM di df
    membuat stage_05 short-circuit)."""
    return pd.DataFrame({
        "NAMA RESTO": resto,
        "NAMA BARANG": [item] * len(resto),
        "JENIS": ["WASTE"] * len(resto),
        "KETERANGAN": ["Kualitas"] * len(resto),
        "SOURCE DATA": ["WASTE BAHAN DAN PACKAGING"] * len(resto),
        "TOTAL": [100.0] * len(resto),
        # day columns dummy — stage_05 tidak membacanya
        "1": [10.0] * len(resto),
    })


def _make_bom(resto: list, item: str, bom_qty: float) -> pd.DataFrame:
    return pd.DataFrame({
        "Nomor #": resto,
        "Nama Barang": [item] * len(resto),
        "TOTAL BOM": [bom_qty] * len(resto),
    })


class TestBomJoinNumericOutlet:
    """Skenario bug asli: kode outlet numerik di data, string di BOM."""

    def test_numerik_vs_string_match(self):
        df = _make_df([1049.0, 1102.0])
        bom = _make_bom(["1049", "1102"], "AYAM WHOLE", 200.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)

        # Sebelum fix: semua NaN (join gagal senyap)
        assert out["TOTAL BOM"].notna().all(), (
            "Join BOM gagal untuk outlet numerik — bug F1 kambuh! "
            "TOTAL BOM semua NaN → sinyal S6/S7 mati."
        )
        assert (out["TOTAL BOM"] == 200.0).all()
        # Rill % to BOM = TOTAL / TOTAL BOM = 100/200 = 0.5
        assert np.allclose(out["Rill % to BOM"], 0.5)

    def test_float_int_sisi_bom_vs_int_sisi_data(self):
        """Kebalikan: data string, BOM numerik — juga harus match."""
        df = _make_df(["1049"])
        bom = _make_bom([1049.0], "AYAM WHOLE", 400.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)
        assert out["TOTAL BOM"].notna().all()

    def test_whitespace_distrip_kedua_sisi(self):
        df = _make_df(["  1049  "])
        bom = _make_bom([" 1049 "], "AYAM WHOLE", 500.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)
        assert out["TOTAL BOM"].notna().all()


class TestBomJoinSafety:
    def test_outlet_tidak_ada_di_bom_nan(self):
        df = _make_df(["9999"])
        bom = _make_bom(["1049"], "AYAM WHOLE", 200.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)
        assert out["TOTAL BOM"].isna().all()
        assert (out["Rill % to BOM"] == 0.0).all()

    def test_bom_kosong_tidak_crash(self):
        df = _make_df(["1049"])
        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=None)
        assert "TOTAL BOM" in out.columns
        assert out["TOTAL BOM"].isna().all()

    def test_row_count_tidak_berubah(self):
        """Join harus many_to_one — jumlah baris data HARUS identik."""
        df = _make_df(["1049", "1102", "1102", "9999"])
        bom = _make_bom(["1049", "1102"], "AYAM WHOLE", 200.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)
        assert len(out) == len(df), (
            "Row count berubah — BOM duplicate tidak ter-dedupe / join meledak"
        )

    def test_sel_kosong_outlet_tidak_join_palsu(self):
        """NAMA RESTO kosong (NaN) → tidak boleh match "nan" di BOM."""
        df = _make_df([np.nan])
        bom = _make_bom(["nan"], "AYAM WHOLE", 200.0)

        out = stage_05_bom(df, key_akhir=31, config=CONFIG, bom_df=bom)
        assert out["TOTAL BOM"].isna().all()
        assert len(out) == 1  # baris kosong tetap dipertahankan, tidak di-drop
