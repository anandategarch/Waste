"""Unit test — normalisasi presisi float 15 digit signifikan (loader, F7 v2.3.2).

Mengunci fix idempotency: file input bisa mengandung FP dust (mis. 21.299999999999997)
yang visually = 21.3 di Excel. Tanpa normalisasi, run-1 vs run-ulang menghasilkan
skor anomali BEDA untuk data yang sama (sinyal boundary flip: 21.3/7.1 = 3.0).
"""

import math

import numpy as np
import pandas as pd

from waste_anomaly.loader import _float15, _normalize_float_precision


class TestFloat15:
    def test_fp_dust_dibersihkan(self):
        assert _float15(21.299999999999997) == 21.3

    def test_nilai_bersih_tidak_berubah(self):
        assert _float15(21.3) == 21.3
        assert _float15(42.5) == 42.5
        assert _float15(0.1) == 0.1

    def test_nilai_presisi_wajar_dipertahankan(self):
        # 15 digit signifikan masih presisi — hanya dust digit 16-17 yang dibuang
        assert _float15(12.3456789012345) == 12.3456789012345

    def test_nan_inf_lewat(self):
        assert math.isnan(_float15(float("nan")))
        assert _float15(float("inf")) == float("inf")
        assert _float15(float("-inf")) == float("-inf")

    def test_int_dan_string_tidak_disentuh(self):
        assert _float15(7) == 7
        # non-numeric string dikembalikan apa adanya (numeric-string tidak
        # pernah terjadi di praktik — fungsi ini hanya dipakai kolom float)
        assert _float15("abc") == "abc"


class TestNormalizeFloatPrecision:
    def test_kolom_float_dinormalisasi(self):
        df = pd.DataFrame({"a": [21.299999999999997, 42.5], "b": ["x", "y"]})
        out = _normalize_float_precision(df)
        assert out["a"].iloc[0] == 21.3
        assert out["b"].iloc[0] == "x"  # kolom string tak tersentuh

    def test_kolom_int_presisi_tidak_berubah(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        out = _normalize_float_precision(df)
        assert list(out["a"]) == [1, 2, 3]

    def test_kolom_nan_aman(self):
        df = pd.DataFrame({"a": [np.nan, 1.5]})
        out = _normalize_float_precision(df)
        assert out["a"].isna().iloc[0]
        assert out["a"].iloc[1] == 1.5


class TestIdempotencyBoundary:
    """Skenario bug asli end-to-end: dust 21.299... vs 21.3 di ambang S3."""

    def test_ratio_boundary_stabil_setelah_normalisasi(self):
        dust = 21.299999999999997
        clean = _float15(dust)
        median_aktif = 7.1

        # Sebelum normalisasi: dust ratio < 3 (sinyal MATI) padahal visual = 3.0
        assert dust / median_aktif < 3.0
        # Setelah normalisasi (semantik Excel): ratio >= 3 (sinyal HIDUP, konsisten
        # dengan apa yang Power Query / Excel user lihat)
        assert clean / median_aktif >= 3.0

    def test_round_trip_excel_tidak_mengubah_nilai(self):
        """openpyxl menulis float dengan %.15g — nilai ternormalisasi stabil."""
        value = _float15(21.299999999999997)  # 21.3
        # Simulasi tulis-Excel (%.15g) lalu baca-Excel (float())
        roundtrip = float(f"{value:.15g}")
        assert roundtrip == value  # stabil — inilah inti idempotency
