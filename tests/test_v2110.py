"""test_v2110.py — regresi v2.11.0: set_filters_multi + semantik list
_apply_filters (state-level).

v2.11.0 dulu membawa SlicerBar (chip multi-select) + combo sidebar
sadar-multi + FlowLayout — SEMUANYA DIHAPUS di v2.12.4 (permintaan
user: sidebar filter kiri & slicer chip dihapus; filter = funnel di
judul kolom tabel, SEMUA kolom punya). Kontrak STATE yang tetap hidup
dan dikunci file ini (dipakai funnel header + drill-down):

Kontrak yang dikunci:
- set_filters_multi: beberapa dimensi → SATU broadcast filters_changed
  (klik beruntun = satu render); kunci asing diabaikan; memo
  filtered_df ter-invalidasi.
- _apply_filters: nilai LIST semua dimensi = gabungan single; list
  keterangan ternormalisasi whitespace ≡ single ternormalisasi
  (kontrak v2.5.1 utuh); list kosong ≡ None (tanpa filter).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _df_slicer() -> pd.DataFrame:
    """Fixture sintetis 6 baris — variasi JENIS / KETERANGAN / STATUS.

    KETERANGAN sengaja memuat varian spasi ('Cancel  Nota ' vs
    'Cancel Nota') — norm_text menyatukan keduanya (kontrak v2.5.1).
    """
    return pd.DataFrame({
        "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL", "WASTE", "SUSUT"],
        "KETERANGAN": ["Cancel Nota", "Cancel  Nota ", "Alat/Mesin",
                       "Over Stock", "Alat/Mesin", "Cancel Nota"],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Potensi Anomali",
                           "Perlu Review", "Normal", "Normal",
                           "Prioritas Tinggi"],
        "TOTAL": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })


# ============================================================
# set_filters_multi (state) — coalesce broadcast
# ============================================================

class TestV2110SetFiltersMulti:
    def _ctx(self):
        _qapp()
        from ui.state import AppContext
        return AppContext({})

    def test_dua_dimensi_satu_broadcast(self):
        ctx = self._ctx()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        n = {"emit": 0}
        ctx.filters_changed.connect(
            lambda: n.__setitem__("emit", n["emit"] + 1))
        ctx.set_filters_multi(
            {"jenis": ["WASTE"], "keterangan": ["Cancel Nota"]})
        assert ctx.active_filters["jenis"] == ["WASTE"]
        assert ctx.active_filters["keterangan"] == ["Cancel Nota"]
        assert n["emit"] == 1  # SATU render — bukan satu per dimensi

    def test_kunci_asing_diabaikan(self):
        ctx = self._ctx()
        before = dict(ctx.active_filters)
        ctx.set_filters_multi({"dimensi_tak_dikenal": ["X"], "status": None})
        assert ctx.active_filters == before

    def test_memo_filtered_df_terinvalidasi(self):
        ctx = self._ctx()
        ctx.set_dataset(_df_slicer(), {"key_akhir": 31})
        assert len(ctx.filtered_df()) == 6
        ctx.set_filters_multi({"jenis": ["SUSUT"]})
        assert len(ctx.filtered_df()) == 2  # bukan salinan memo basi


# ============================================================
# _apply_filters — nilai LIST ≡ gabungan single (semantik v2.5.1)
# ============================================================

class TestV2110ApplyFiltersList:
    def test_status_list_gabungan_single(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        by_list = _apply_filters(
            df, {"status": ["Prioritas Tinggi", "Perlu Review"]})
        a = _apply_filters(df, {"status": "Prioritas Tinggi"})
        b = _apply_filters(df, {"status": "Perlu Review"})
        assert sorted(by_list.index) == sorted(a.index.append(b.index))
        assert len(by_list) == 3

    def test_keterangan_list_ternormalisasi(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        # 'Cancel  Nota ' di data → norm 'Cancel Nota' — list mengenali
        out = _apply_filters(df, {"keterangan": ["Cancel Nota"]})
        assert sorted(out.index) == [0, 1, 5]
        single = _apply_filters(df, {"keterangan": "Cancel Nota"})
        assert sorted(out.index) == sorted(single.index)

    def test_list_kosong_setara_tanpa_filter(self):
        from ui.shared import _apply_filters
        df = _df_slicer()
        a = _apply_filters(
            df, {"jenis": [], "keterangan": [], "status": []})
        b = _apply_filters(df, {})
        assert len(a) == len(b) == 6

