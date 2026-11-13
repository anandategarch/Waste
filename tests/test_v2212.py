"""test_v2212.py — regresi deep audit final v2.21.1 (pasca-grouping
keterangan v2.21.0).

Mengunci 5 perbaikan hasil 3 audit paralel (ubah nilai / follow up /
model+funnel+sort):

[A] SORT HEADER STABIL (KRITIS) — model.sort kini mergesort STABLE:
    klik judul KETERANGAN (kolom pertama tabel + kunci pemisah
    (KETERANGAN, NAMA BARANG)) dgn quicksort tak-stabil lama
    memfragmentasi blok (ket×barang) → insert_group_separators
    membanjiri tabel dgn pemisah palsu (audit empiris 6 ket×40 item×
    30 resto = 7.200 baris: ±1.081 pemisah, seharusnya 239).

[B] FILTER KETERANGAN '(KOSONG)' LINTAS-TAB:
    - _apply_filters: NaN baris kini dinormalisasi '' (dulu
      astype(str) → teks "nan" → pilihan '(kosong)' funnel tak pernah
      cocok → 0 baris di tab Hari/KPI).
    - _keterangan_group_mask (tab Anomali): pilihan '(kosong)' kini
      mencocokkan klaster FALLBACK (KETERANGAN == JENIS representatif
      — SUSUT/TRIAL); dulu vs={'nan'} tak pernah cocok → tab Anomali
      0 baris.

[C] TOMBOL 'Fokus alasan ini' vs NILAI FALLBACK — _keterangan_is_
    fallback: grup 1-anggota ber-keterangan = JENIS ('SUSUT'/'TRIAL')
    tak lagi menawarkan fokus (nilai itu tak ada di baris mentah →
    filter global 0 baris → tab Hari/KPI kosong).

[D] STAGING 'Update nilai' BER-KETERANGAN — kolom 'Keterangan' (index
    2) + entry staging membawa keterangan; entri beda klaster alasan
    utk item×resto sama kini TERBEDAKAN; entry lama tanpa kunci →
    kolom kosong (backward compat). Label entry = keterangan·barang·
    resto.

[E] POP-UP RINGKAS TAK 'SUSUT · SUSUT' — dedup jenis==keterangan.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _suppress_msgbox(monkeypatch):
    """Monkeypatch SEMUA static QMessageBox + instance exec() (anti
    modal hang di offscreen) — pola test_v2195."""
    from PySide6.QtWidgets import QMessageBox
    SB = QMessageBox.StandardButton
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: SB.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: SB.Yes)
    monkeypatch.setattr(QMessageBox, "exec", lambda *a, **kw: SB.Yes)


# ============================================================
# [A] SORT HEADER STABIL — mergesort + pemisah tak banjir
# ============================================================

def _df_sort_fixture() -> pd.DataFrame:
    """6 keterangan × 8 barang × 5 resto = 240 baris, urut GROUP_KEYS.
    KETERANGAN fallback SUSUT/TRIAL ikut (JENIS == KETERANGAN)."""
    kets = ["Alat/Mesin", "Cancel Nota", "Handling", "Kualitas",
            "SUSUT", "TRIAL"]
    barangs = [f"ITEM{i:02d}" for i in range(8)]
    restos = ["R1", "R2", "R3", "R4", "R5"]
    rows = []
    for ket in kets:
        jenis = "WASTE" if ket not in ("SUSUT", "TRIAL") else ket
        for brg in barangs:
            for rst in restos:
                rows.append({
                    "KETERANGAN": ket, "NAMA BARANG": brg,
                    "NAMA RESTO": rst, "JENIS": jenis,
                    "TOTAL": float(len(rows) % 97),
                })
    return pd.DataFrame(rows)


def _n_sep(df: pd.DataFrame) -> int:
    from ui.grouping import SEP_COL
    return int(sum(1 for v in df[SEP_COL].tolist() if v is True))


class TestSortHeaderStabil:
    def _model(self):
        from ui.models import PandasTableModel
        from ui.grouping import insert_group_separators, SEP_COL, SEP_KEYS
        df = _df_sort_fixture().sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        disp = insert_group_separators(df)
        m = PandasTableModel(disp)
        m.set_separator_column(SEP_COL, group_keys=SEP_KEYS)
        return m

    def test_sort_keterangan_pemisah_tepat(self):
        """Sort by kolom KETERANGAN (kunci SEP pertama) → pemisah =
        jumlah grup (ket×barang) − 1 = 47 — BUKAN banjir pemisah palsu
        (fragmentasi blok oleh sort tak-stabil)."""
        from PySide6.QtCore import Qt
        m = self._model()
        kcol = list(m.dataframe.columns).index("KETERANGAN")
        m.sort(kcol, Qt.AscendingOrder)
        df = m.dataframe
        assert len(df) == 240 + 47  # data + pemisah
        assert _n_sep(df) == 47

    def test_sort_keterangan_blok_kontigu(self):
        """Stabilitas: dlm tiap blok KETERANGAN urutan (BARANG, RESTO)
        pra-sort TERJAGA → tiap blok (ket×barang) KONTIGU (tak terpotong
        pemisah di tengah blok)."""
        from PySide6.QtCore import Qt
        m = self._model()
        kcol = list(m.dataframe.columns).index("KETERANGAN")
        m.sort(kcol, Qt.AscendingOrder)
        df = m.dataframe[~m.dataframe["__SEP"].map(
            lambda vv: isinstance(vv, bool) and vv)]
        # Blok (ket, barang) harus kontigu: label berubah tepat 47×.
        lab = list(zip(df["KETERANGAN"], df["NAMA BARANG"]))
        changes = sum(1 for i in range(1, len(lab))
                      if lab[i] != lab[i - 1])
        assert changes == 47
        # Dlm blok ket, urutan barang tetap urut fixture (pra-sort terjaga).
        for ket, sub in df.groupby("KETERANGAN", sort=False):
            assert list(sub["NAMA BARANG"]) == sorted(
                sub["NAMA BARANG"], key=barangs_index)
        # Urutan blok ket = alfabetis (sort Naik).
        assert list(dict.fromkeys(df["KETERANGAN"])) == sorted(
            set(df["KETERANGAN"]))

    def test_sort_keterangan_descending_stabil(self):
        """Sort Turun: blok ket terbalik, blok barang tetap kontigu."""
        from PySide6.QtCore import Qt
        m = self._model()
        kcol = list(m.dataframe.columns).index("KETERANGAN")
        m.sort(kcol, Qt.DescendingOrder)
        df = m.dataframe
        assert _n_sep(df) == 47
        data = df[~df["__SEP"].map(lambda v: isinstance(v, bool) and v)]
        assert list(dict.fromkeys(data["KETERANGAN"])) == sorted(
            set(data["KETERANGAN"]), reverse=True)

    def test_sort_skor_pemisah_dibuang(self):
        """Sort kolom non-grup (TOTAL) → pemisah dibuang (tabel ranked
        polos) — kontrak v2.19.3 tetap."""
        from PySide6.QtCore import Qt
        m = self._model()
        tcol = list(m.dataframe.columns).index("TOTAL")
        m.sort(tcol, Qt.DescendingOrder)
        df = m.dataframe
        assert len(df) == 240
        assert _n_sep(df) == 0


def barangs_index(b: str) -> int:
    """Urutan kanonik barang fixture (ITEM00..ITEM07)."""
    return int(b.replace("ITEM", ""))


# ============================================================
# [B] FILTER KETERANGAN '(KOSONG)' — level baris & level grup
# ============================================================

class TestApplyFiltersKeteranganKosong:
    def _raw(self) -> pd.DataFrame:
        return pd.DataFrame({
            "JENIS": ["WASTE", "SUSUT", "WASTE", "TRIAL", "WASTE"],
            "KETERANGAN": ["Handling", np.nan, "Cancel Nota", np.nan,
                           "Over Stock"],
            "NAMA BARANG": ["A", "B", "C", "D", "E"],
        })

    def test_nan_filter_menangkan_baris_kosong(self):
        """Pilihan '(kosong)' (NaN) cocok dgn baris keterangan kosong —
        dulu 0 baris (NaN baris jadi teks 'nan' oleh astype(str))."""
        from ui.shared import _apply_filters
        out = _apply_filters(self._raw(), {"keterangan": [float("nan")]})
        assert list(out["NAMA BARANG"]) == ["B", "D"]

    def test_nan_dan_nilai_campuran(self):
        from ui.shared import _apply_filters
        out = _apply_filters(
            self._raw(), {"keterangan": [float("nan"), "Handling"]})
        assert list(out["NAMA BARANG"]) == ["A", "B", "D"]

    def test_nilai_skalar_dan_normalisasi_spasi(self):
        from ui.shared import _apply_filters
        out = _apply_filters(self._raw(), {"keterangan": "Handling"})
        assert list(out["NAMA BARANG"]) == ["A"]
        # Spasi tersembunyi (NBSP/ganda) tetap cocok (norm_text).
        raw = pd.DataFrame({
            "JENIS": ["WASTE"], "KETERANGAN": ["\xa0Handling\xa0 "]})
        out = _apply_filters(raw, {"keterangan": "Handling"})
        assert len(out) == 1


class TestKeteranganGroupMask:
    """_keterangan_group_mask — fungsi murni mask grup (dipakai
    _grp_global_mask utk filter global 'keterangan' tab Anomali)."""

    def _shown(self) -> pd.DataFrame:
        # Grup: 2 keterangan ASLI + 2 klaster FALLBACK (ket == jenis).
        return pd.DataFrame({
            "KETERANGAN": ["Handling", "Cancel Nota", "SUSUT", "TRIAL"],
            "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL"],
            "TOTAL": [10.0, 20.0, 30.0, 40.0],
        })

    def test_kosong_menangkan_klaster_fallback(self):
        """Pilihan '(kosong)' (NaN) → klaster SUSUT/TRIAL (fallback)
        tampil — dulu tab Anomali 0 baris (vs={'nan'} tak pernah cocok)."""
        from ui.view_anomali import _keterangan_group_mask
        m = _keterangan_group_mask(self._shown(), [float("nan")])
        assert list(m) == [False, False, True, True]

    def test_nilai_langsung_tunggal(self):
        from ui.view_anomali import _keterangan_group_mask
        m = _keterangan_group_mask(self._shown(), ["Handling"])
        assert list(m) == [True, False, False, False]

    def test_campuran_kosong_dan_nilai(self):
        from ui.view_anomali import _keterangan_group_mask
        m = _keterangan_group_mask(
            self._shown(), ["Handling", float("nan")])
        assert list(m) == [True, False, True, True]

    def test_tanpa_kolom_keterangan_none(self):
        from ui.view_anomali import _keterangan_group_mask
        df = pd.DataFrame({"JENIS": ["WASTE"]})
        assert _keterangan_group_mask(df, ["Handling"]) is None
        assert _keterangan_group_mask(None, ["Handling"]) is None

    def test_spasi_dinormalisasi(self):
        from ui.view_anomali import _keterangan_group_mask
        df = pd.DataFrame({"KETERANGAN": [" Handling "],
                           "JENIS": ["WASTE"]})
        m = _keterangan_group_mask(df, ["Handling"])
        assert list(m) == [True]


# ============================================================
# [C] TOMBOL 'Fokus alasan ini' vs fallback
# ============================================================

class TestKeteranganIsFallback:
    def test_fallback_terdeteksi(self):
        from ui.view_anomali import _keterangan_is_fallback
        rec = pd.Series({"JENIS": "SUSUT", "KETERANGAN": "SUSUT"})
        assert _keterangan_is_fallback(rec) is True

    def test_keterangan_asli_bukan_fallback(self):
        from ui.view_anomali import _keterangan_is_fallback
        rec = pd.Series({"JENIS": "WASTE", "KETERANGAN": "Handling"})
        assert _keterangan_is_fallback(rec) is False

    def test_keterangan_kosong_bukan_fallback(self):
        from ui.view_anomali import _keterangan_is_fallback
        rec = pd.Series({"JENIS": "WASTE", "KETERANGAN": np.nan})
        assert _keterangan_is_fallback(rec) is False

    def test_rec_none_aman(self):
        from ui.view_anomali import _keterangan_is_fallback
        assert _keterangan_is_fallback(None) is False


# ============================================================
# [D] STAGING 'Update nilai' BER-KETERANGAN
# ============================================================

class TestUpdateViewKeterangan:
    def _entry(self, **over):
        e = {
            "source": "/tmp/REKAP MENTAH_TEGAR.xlsx", "src_rows": [5],
            "day_edits": {"5": 55.0}, "day_orig": {"5": 100.0},
            "jenis": "WASTE", "barang": "AYAM", "resto": "R1",
            "keterangan": "Handling",
        }
        e.update(over)
        return e

    def test_kolom_keterangan_ada_dan_terisi(self):
        """Tabel staging punya kolom 'Keterangan' (index 2, setelah
        'File sumber') — entri beda klaster alasan kini TERBEDAKAN."""
        _qapp()
        from ui.state import AppContext
        from ui.view_update import UpdateView, _COLS
        ctx = AppContext({})
        ctx.add_update(self._entry())
        view = UpdateView(ctx)
        try:
            assert "Keterangan" in _COLS
            assert _COLS.index("Keterangan") == 2
            assert view._table.columnCount() == len(_COLS)
            assert view._table.item(0, 2).text() == "Handling"
            # Item tetap jenis · barang (index 3).
            assert "AYAM" in view._table.item(0, 3).text()
            # Status index 7, Ditambahkan index 8.
            assert "Pending" in view._table.item(0, 7).text()
        finally:
            view.deleteLater()

    def test_entri_dua_klaster_terbedakan(self):
        """2 entri item×resto SAMA beda keterangan (Handling vs Cancel
        Nota) → kolom Keterangan membedakan (dulu label baris kembar)."""
        _qapp()
        from ui.state import AppContext
        from ui.view_update import UpdateView
        ctx = AppContext({})
        ctx.add_update(self._entry(keterangan="Handling"))
        ctx.add_update(self._entry(keterangan="Cancel Nota",
                                   src_rows=[6]))
        view = UpdateView(ctx)
        try:
            assert view._table.item(0, 2).text() == "Handling"
            assert view._table.item(1, 2).text() == "Cancel Nota"
        finally:
            view.deleteLater()

    def test_entri_lama_tanpa_keterangan_kolom_kosong(self):
        """Backward compat: entry pra-v2.21.1 tanpa kunci 'keterangan'
        → kolom kosong (tak crash)."""
        _qapp()
        from ui.state import AppContext
        from ui.view_update import UpdateView
        ctx = AppContext({})
        e = self._entry()
        del e["keterangan"]
        ctx.add_update(e)
        view = UpdateView(ctx)
        try:
            assert view._table.item(0, 2).text() == ""
        finally:
            view.deleteLater()

    def test_label_entry_keterangan_barang_resto(self, monkeypatch):
        """_on_stage_edits: label entry = KETERANGAN · BARANG · RESTO
        + entry membawa keterangan (identitas grup v2.21.0)."""
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        src_path = "/tmp/REKAP MENTAH_TEGAR.xlsx"
        ctx = AppContext({})
        ctx.summary = {"workbook_path": src_path}
        rec = pd.Series({
            "NAMA RESTO": "R1", "NAMA BARANG": "AYAM", "JENIS": "WASTE",
            "KETERANGAN": "Handling", "__SRC_ROW": 5,
            "ANOMALY STATUS": "Normal", "ANOMALY SCORE": 0,
        })
        panel = DetailPanel(ctx)
        panel.show_record(rec)

        class FakeSP:
            def __init__(self, v): self._v = v
            def value(self): return self._v
            def setEnabled(self, b): pass
        panel._day_orig = {"5": 100.0}
        panel._day_edits = {"5": FakeSP(55.0)}
        _suppress_msgbox(monkeypatch)  # confirm exec() → Yes
        try:
            panel._on_stage_edits()
        finally:
            panel.deleteLater()
        assert ctx.pending_count() == 1
        e = ctx.pending_updates[0]
        assert e["keterangan"] == "Handling"
        assert e["label"] == "Handling · AYAM · R1"


# ============================================================
# [E] POP-UP RINGKAS — dedup 'SUSUT · SUSUT'
# ============================================================

class TestSummaryRowsDedup:
    def test_fallback_tak_dobel(self):
        """Grup fallback (JENIS == KETERANGAN) → 'SUSUT' sekali — bukan
        'SUSUT · SUSUT'."""
        from ui.view_anomali import _summary_rows
        rec = pd.Series({
            "JENIS": "SUSUT", "KETERANGAN": "SUSUT", "TOTAL": 12.0,
        })
        rows = _summary_rows(rec)
        label_val = dict((lbl, val) for lbl, val, _ in rows)
        assert label_val.get("Jenis & alasan catatan") == "SUSUT"

    def test_asli_tetap_join(self):
        from ui.view_anomali import _summary_rows
        rec = pd.Series({
            "JENIS": "WASTE", "KETERANGAN": "Handling", "TOTAL": 12.0,
        })
        rows = _summary_rows(rec)
        label_val = dict((lbl, val) for lbl, val, _ in rows)
        assert label_val.get("Jenis & alasan catatan") == \
            "WASTE · Handling"
