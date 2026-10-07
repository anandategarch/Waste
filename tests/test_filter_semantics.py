"""test_filter_semantics.py — semantik filter & format v2.5.1.

Mengunci fix audit v2.5.1 pada lapisan murni (tanpa Tk):
- DD-M1: rentang hari KETAT — baris HARI MAX null (≈ 23.470 baris nol,
  90,6% data riil) tidak lagi lolos filter rentang hari.
- DD-L4: search tidak mencocokkan sel NaN (str(pd.NA)='<NA>', 'nan').
- DQ-M1: filter keterangan mencocokkan varian whitespace (NBSP /
  zero-width / spasi ganda) — dropdown & filter satu kunci.
- IN-L1: fmt_id — konvensi angka Indonesia tunggal.
- utils.norm_text — normalisasi whitespace kunci teks.

Run: python -m pytest tests/test_filter_semantics.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from ui.shared import _apply_filters, fmt_id
from waste_anomaly.utils import norm_text


@pytest.fixture()
def det() -> pd.DataFrame:
    """Detail-like frame: 3 baris aktif + 2 baris nol (HARI MAX null)."""
    return pd.DataFrame({
        "NAMA RESTO": ["R1", "R2", "R1", "R1", "R2"],
        "NAMA BARANG": ["A", "B", "C", "A", "B"],
        "JENIS": ["WASTE", "SUSUT", "TRIAL", "WASTE", "SUSUT"],
        "KETERANGAN": ["Kualitas Internal", "Cancel Nota", "Over Stock",
                       "Kualitas Internal", "Cancel Nota"],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Perlu Review", "Normal",
                           "Normal", "Normal"],
        "TOTAL": [300.0, 200.0, 100.0, 0.0, 0.0],
        "HARI MAX": [5, 10, 25, None, None],
    })


# ============================================================
# v2.13.8 (gel-C): TestDayRangeStrict + TestSearchNaNExcluded DIHAPUS
# — rentang hari & kotak cari dihapus dari UI sejak v2.12.4 (sidebar);
# _apply_filters kini murni semantik funnel (DD-M1/DD-L4/DQ-M1/IN-L1
# yang HIDUP tetap dikunci di bawah).
# ============================================================

class TestTanpaFilterSemuaBaris:
    def test_tanpa_filter_semua_baris(self, det):
        """filters kosong = tanpa filter — semua 5 baris lolos."""
        res = _apply_filters(det, {})
        assert len(res) == 5


# ============================================================
# DQ-M1 — keterangan whitespace-normalized
# ============================================================

class TestKeteranganNormalized:
    @pytest.fixture()
    def nbsp_det(self) -> pd.DataFrame:
        """KETERANGAN dengan varian NBSP/zero-width dari kategori sama.

        NBSP internal = pemisah kata (semantik spasi); zero-width realistis
        menempel pada spasi nyata (artefak input) — dua-duanya menormalkan
        ke kunci yang sama dengan nilai bersih.
        """
        return pd.DataFrame({
            "NAMA RESTO": ["R1", "R2", "R3"],
            "KETERANGAN": ["Kualitas\xa0Internal", "Kualitas Internal",
                           "Kualitas \u200bInternal"],
            "TOTAL": [100.0, 200.0, 50.0],
        })

    def test_filter_nilai_bersih_menangkap_varian(self, nbsp_det):
        res = _apply_filters(nbsp_det, {"keterangan": "Kualitas Internal"})
        assert len(res) == 3  # semua varian tertangkap

    def test_filter_nilai_nbsp_juga_menangkap(self, nbsp_det):
        res = _apply_filters(nbsp_det, {"keterangan": "Kualitas\xa0Internal"})
        assert len(res) == 3

    def test_filter_list_varian(self, nbsp_det):
        res = _apply_filters(
            nbsp_det, {"keterangan": ["Kualitas Internal"]})
        assert len(res) == 3

    def test_kategori_lain_tetap_terpisah(self, det):
        res = _apply_filters(det, {"keterangan": "Over Stock"})
        assert len(res) == 1


# ============================================================
# utils.norm_text
# ============================================================

class TestNormText:
    @pytest.mark.parametrize("raw, expected", [
        ("PACK\xa0", "PACK"),
        (" PACK ", "PACK"),
        ("A  B", "A B"),
        ("GR\u200b", "GR"),
        ("Kualitas Internal", "Kualitas Internal"),
        (None, ""),
        (float("nan"), ""),
    ])
    def test_normalisasi(self, raw, expected):
        assert norm_text(raw) == expected

    def test_tidak_mengubah_huruf(self):
        """casefold BUKAN bagian KETERANGAN — 'dan' vs 'DAN' tetap beda
        (keputusan merge case adalah urusan SOURCE DATA stage, golden)."""
        assert norm_text("DAN") == "DAN"
        assert norm_text("dan") == "dan"


# ============================================================
# IN-L1 — fmt_id
# ============================================================

class TestFmtId:
    @pytest.mark.parametrize("value, dec, expected", [
        (25901, 0, "25.901"),
        (9333117.5, 1, "9.333.117,5"),
        (9333117.5, 0, "9.333.118"),
        (0.0, 1, "0,0"),
        (-1234.5, 1, "-1.234,5"),
        (999.999, 3, "999,999"),
    ])
    def test_format_indonesia(self, value, dec, expected):
        assert fmt_id(value, dec) == expected

    def test_nan_dan_invalid(self):
        assert fmt_id(float("nan")) == ""
        assert fmt_id("bukan angka") == "bukan angka"
