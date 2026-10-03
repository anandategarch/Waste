"""Unit test — normalisasi kunci join `_key_str` (loader.py).

Ini mengunci bug-fix F1 (v2.3.2): float integral dari cell numerik Excel
(1049.0, hasil engine calamine / openpyxl) HARUS dinormalisasi jadi "1049"
— bukan "1049.0" — supaya join BOM dengan kode outlet string tetap match.
"""

import math

import numpy as np
import pandas as pd
import pytest

from waste_anomaly.loader import _key_str


class TestKeyStrBasics:
    def test_string_dipreserve_dan_distrip(self):
        assert _key_str("  B.1001.MLGPAR  ") == "B.1001.MLGPAR"

    def test_int_jadi_str(self):
        assert _key_str(1049) == "1049"

    def test_float_integral_tanpa_desimal(self):
        # dtype trap inti bug F1: cell numerik dibaca sebagai float
        assert _key_str(1049.0) == "1049"
        assert _key_str(31.0) == "31"

    def test_float_non_integral_tetap_presisi(self):
        assert _key_str(12.5) == "12.5"

    def test_whitespace_string_kosong(self):
        assert _key_str("") == ""
        assert _key_str("   ") == ""


class TestKeyStrNullSemantics:
    """None/NaN/NaT/pd.NA → None (bukan "nan") — cegah join palsu (H9-a)."""

    @pytest.mark.parametrize("null_value", [None, np.nan, pd.NA, pd.NaT])
    def test_null_jadi_none(self, null_value):
        assert _key_str(null_value) is None

    def test_float_nan_jadi_none(self):
        assert _key_str(float("nan")) is None

    def test_float_inf_bukan_none(self):
        # inf bukan null — biarkan str() yang menangani (tidak crash)
        result = _key_str(math.inf)
        assert isinstance(result, str)


class TestKeyStrRoundTrip:
    def test_join_numerik_vs_string_match(self):
        """Skenario bug asli: outlet numerik di data, string di sheet BOM."""
        df_data = pd.DataFrame({"NAMA RESTO": [1049.0, 1102.0]})
        df_bom = pd.DataFrame({"Nomor #": ["1049", "1102"]})

        keys_data = df_data["NAMA RESTO"].map(_key_str)
        keys_bom = df_bom["Nomor #"].map(_key_str)

        # Sebelum fix: "1049.0" != "1049" → 0 match → sinyal S6/S7 mati senyap
        assert set(keys_data) == set(keys_bom)

    def test_join_tidak_match_null(self):
        """Sel kosong tidak boleh join palsu dengan "nan" string di sisi lain."""
        df_data = pd.DataFrame({"NAMA RESTO": [np.nan, "1049"]})
        df_bom = pd.DataFrame({"Nomor #": ["nan", "1049"]})

        keys_data = df_data["NAMA RESTO"].map(_key_str)
        keys_bom = df_bom["Nomor #"].map(_key_str)

        matched = set(keys_data.dropna()) & set(keys_bom.dropna())
        # "nan" string di BOM tidak boleh match None dari data
        assert matched == {"1049"}
