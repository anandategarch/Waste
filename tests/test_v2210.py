"""test_v2210.py — v2.20.1: kolom KETERANGAN (ganti JENIS) + heatmap gamma.

2 permintaan user:
1. "di tab anomali kolom jenis bisa gak diganti jadi kolom KETERANGAN
   AJA: KETERANGAN — Alat/Mesin, Cancel Nota, Handling, Kualitas, Kualitas
   Eksternal, Kualitas Internal, Over Stock, SUSUT, TRIAL" — kolom
   pertama tabel Anomali KETERANGAN (bukan JENIS); SUSUT/TRIAL muncul via
   fallback KETERANGAN kosong -> JENIS (grouping.py).
2. "warna heat map lebih sensitif lagi dong biar benar-benar beda di
   kolom Persen to bom" — gamma curve (√t) + ramp 5 stop di _heat_color
   supaya nilai kecil/menengah pakai rentang warna hangat (bukan semua
   hijau pucat seperti ramp linear).

Lapis yang diuji:
- [A] ui.view_anomali.TABLE_COLS — KETERANGAN kolom pertama, JENIS keluar.
- [B] ui.grouping.group_anomali_display — fallback KETERANGAN kosong
  (None/"") -> JENIS (SUSUT/TRIAL tetap tampil); WASTE ber-alasan utuh.
- [C] AnomaliView — KETERANGAN tampak + nilai di vocabulary user; JENIS
  disembunyikan dari tabel (tetap di df model).
- [D] ui.models._heat_color — gamma (_HEAT_GAMMA=0,5) + 5 stop; endpoint
  hijau/merah utuh; _heat_color(0,25) = stop t_eff=0,5 (bukti gamma).
- [E] PandasTableModel — gamma membuat nilai kecil (1% skala p99)
  berwarna hangat (red naik jauh di atas endpoint hijau — ramp linear
  hanya +2; gamma +16).

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent

# Vocabulary user v2.20.1 (9 nilai KETERANGAN).
VOCAB = {
    "Alat/Mesin", "Cancel Nota", "Handling", "Kualitas",
    "Kualitas Eksternal", "Kualitas Internal", "Over Stock",
    "SUSUT", "TRIAL",
}


def _qapp():
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


def _row(barang, resto, jenis, ket, total, bom=1000.0):
    """Baris bergaya output pipeline (1 baris per JENIS×BARANG×RESTO)."""
    data = {str(d): 0.0 for d in range(1, 32)}
    data["5"] = float(total)
    return {
        "SOURCE DATA": "X", "JENIS": jenis, "KETERANGAN": ket,
        "NAMA BARANG": barang, "NAMA RESTO": resto, "SATUAN": "PCS",
        "ANOMALY STATUS": "Normal", "TOTAL BOM": bom,
        "ANOMALY SCORE": 0, **data, "TOTAL": float(total),
    }


def _fallback_df() -> pd.DataFrame:
    """3 grup uji fallback KETERANGAN:
    - SUSUT  (KETERANGAN None)  -> fallback "SUSUT"
    - TRIAL  (KETERANGAN "")    -> fallback "TRIAL"
    - WASTE  (KETERANGAN "Handling") -> tetap "Handling" (tak terfallback)
    """
    return pd.DataFrame([
        _row("AYAM", "R1", "SUSUT", None, 5.0),
        _row("BEBEK", "R1", "TRIAL", "", 3.0),
        _row("CUMI", "R1", "WASTE", "Handling", 10.0),
    ])


# ============================================================
# [A] TABLE_COLS — KETERANGAN kolom pertama
# ============================================================

class TestTableColsKeterangan:
    def test_keterangan_kolom_pertama(self):
        from ui.view_anomali import TABLE_COLS
        assert TABLE_COLS[0] == "KETERANGAN"
        assert "KETERANGAN" in TABLE_COLS
        # JENIS diganti (keluar dari TABLE_COLS) — tetap di df model.
        assert "JENIS" not in TABLE_COLS

    def test_rangking_waste_tetap_paling_kanan(self):
        """Kontrak v2.20.0 utuh: RANGKING WASTE tepat setelah PROFIL
        (swap JENIS->KETERANGAN tak menggeser posisi kolom lain)."""
        from ui.view_anomali import TABLE_COLS
        assert TABLE_COLS.index("RANGKING WASTE") \
            == TABLE_COLS.index("PROFIL") + 1

    def test_total_dan_pct_berurutan(self):
        """Kontrak test_v280 index+1 utuh (swap tak menggeser)."""
        from ui.view_anomali import TABLE_COLS
        assert TABLE_COLS.index("% to BOM") \
            == TABLE_COLS.index("TOTAL") + 1


# ============================================================
# [B] group_anomali_display — fallback KETERANGAN kosong -> JENIS
# ============================================================

class TestKeteranganFallback:
    def _grouped(self):
        from ui.grouping import group_anomali_display
        return group_anomali_display(_fallback_df(), None, {}, key_akhir=31)

    def test_susut_kosong_fallback_ke_jenis(self):
        """KETERANGAN None (catatan SUSUT tak ber-sub-alasan) -> tampil
        "SUSUT" (jenisnya itulah keterangannya — vocabulary user)."""
        out = self._grouped()
        row = out[out["NAMA BARANG"] == "AYAM"].iloc[0]
        assert str(row["KETERANGAN"]) == "SUSUT"

    def test_trial_string_kosong_fallback_ke_jenis(self):
        """KETERANGAN "" (string kosong) -> fallback "TRIAL"."""
        out = self._grouped()
        row = out[out["NAMA BARANG"] == "BEBEK"].iloc[0]
        assert str(row["KETERANGAN"]) == "TRIAL"

    def test_waste_beralasan_tak_terfallback(self):
        """WASTE ber-alasan "Handling" tetap "Handling" — fallback HANYA
        bila kosong (tak menimpa alasan WASTE yang valid)."""
        out = self._grouped()
        row = out[out["NAMA BARANG"] == "CUMI"].iloc[0]
        assert str(row["KETERANGAN"]) == "Handling"

    def test_semua_nilai_dalam_vocabulary(self):
        """Setelah fallback, semua nilai KETERANGAN di df grup masuk
        vocabulary 9-nilai user."""
        out = self._grouped()
        vals = {str(v) for v in out["KETERANGAN"].dropna()}
        assert vals <= VOCAB, vals - VOCAB

    def test_tanpa_kolom_keterangan_tidak_raise(self):
        """Defensif: df tanpa KETERANGAN -> kolom tak dibuat, tidak raise
        (kontrak group_anomali_display 'tidak pernah raise')."""
        from ui.grouping import group_anomali_display
        df = pd.DataFrame({
            "JENIS": ["WASTE"], "NAMA BARANG": ["X"],
            "NAMA RESTO": ["R1"], "TOTAL": [1.0],
        })
        out = group_anomali_display(df, None, {})
        assert "KETERANGAN" not in out.columns or len(out) == 0


# ============================================================
# [C] AnomaliView — integrasi kolom KETERANGAN
# ============================================================

class TestViewKeterangan:
    def _make_view(self, df=None):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        _qapp()
        ctx = AppContext({})
        view = AnomaliView(ctx)
        ctx.set_dataset(df if df is not None else _fallback_df(),
                        {"key_akhir": 31})
        view._refresh_table()
        _qapp().processEvents()
        return view

    def test_keterangan_tampak_jenis_disembunyikan(self):
        view = self._make_view()
        try:
            t = view._table
            mdf = t.model().dataframe
            assert "KETERANGAN" in mdf.columns
            ik = list(mdf.columns).index("KETERANGAN")
            assert not t.isColumnHidden(ik), "KETERANGAN harus tampak"
            # JENIS tetap di df (kunci grup) tapi disembunyikan dari tabel.
            assert "JENIS" in mdf.columns
            ij = list(mdf.columns).index("JENIS")
            assert t.isColumnHidden(ij), "JENIS kini disembunyikan (v2.20.1)"
        finally:
            view.close()

    def test_nilai_keterangan_dalam_vocabulary(self):
        view = self._make_view()
        try:
            mdf = view._table.model().dataframe
            ket = ([v for v, s in zip(mdf["KETERANGAN"].tolist(),
                                     mdf["__SEP"].tolist())
                   if s is not True]
                  if "__SEP" in mdf.columns else mdf["KETERANGAN"].tolist())
            vals = {str(v) for v in ket}
            assert vals <= VOCAB, vals - VOCAB
            assert vals, "KETERANGAN tak boleh kosong"
        finally:
            view.close()

    def test_header_kolom_keterangan(self):
        """HeaderData kolom KETERANGAN = 'KETERANGAN' (bukan 'JENIS')."""
        from PySide6.QtCore import Qt
        view = self._make_view()
        try:
            m = view._table.model()
            mdf = m.dataframe
            ik = list(mdf.columns).index("KETERANGAN")
            hdr = m.headerData(ik, Qt.Horizontal, Qt.DisplayRole)
            assert str(hdr) == "KETERANGAN"
        finally:
            view.close()


# ============================================================
# [D] _heat_color — gamma + 5 stop (sensitivitas naik)
# ============================================================

class TestHeatGamma:
    def test_gamma_constant_dan_stops(self):
        from ui.models import _HEAT_GAMMA, _HEAT_STOPS
        assert _HEAT_GAMMA == 0.5
        # 5 stop (dulu 4) — ramp lebih halus.
        assert len(_HEAT_STOPS) == 5
        # endpoint utuh (kontrak test_v2200 test_stop_ekstrem).
        assert _HEAT_STOPS[0][1] == (214, 236, 216)   # hijau pucat
        assert _HEAT_STOPS[-1][1] == (238, 112, 99)   # merah

    def test_endpoint_tak_tergeser_gamma(self):
        """gamma(0)=0, gamma(1)=1 -> endpoint tetap hijau/merah."""
        from PySide6.QtGui import QColor
        from ui.models import _heat_color
        assert _heat_color(0.0) == QColor(214, 236, 216)
        assert _heat_color(1.0) == QColor(238, 112, 99)

    def test_clamp_tetap_berlaku(self):
        from ui.models import _heat_color
        assert _heat_color(2.0) == _heat_color(1.0)
        assert _heat_color(-0.5) == _heat_color(0.0)

    def test_gamma_bukti_heat_color_025_sama_dgn_stop_050(self):
        """Bukti gamma dipakai: _heat_color(0,25) mengevaluasi ramp pada
        t_eff = 0,25 ** 0,5 = 0,50 -> tepat stop (0,50) = (253,200,110).
        Tanpa gamma, _heat_color(0,25) = stop (0,25) = (253,235,170)
        (berbeda) -> tes ini gagal bila gamma tak diterapkan."""
        from PySide6.QtGui import QColor
        from ui.models import _heat_color, _HEAT_STOPS
        # stop pada t=0,50 (index 2) = warna kuning emas
        stop_050 = _HEAT_STOPS[2][1]
        assert _heat_color(0.25) == QColor(*stop_050)

    def test_monoton_lightness_turun(self):
        """Ramp tetap monoton: lightness turun seiring t naik (gamma tak
        merusak urutan warna hijau->kuning->oranye->merah)."""
        from ui.models import _heat_color
        lights = [_heat_color(t).lightness()
                  for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert lights == sorted(lights, reverse=True)
        assert lights[-1] < lights[0]

    def test_warna_pekat_seiring_t(self):
        """Untuk dua t, t lebih besar -> lightness LEBIH RENDAH (warna
        lebih pekat mengarah merah) — sensitivitas: nilai berbeda ->
        warna berbeda. (Red channel ramp tak monoton — hijau&kuning
        sama-sama red≈253; yang membedakan lightness/green.)"""
        from ui.models import _heat_color
        assert _heat_color(0.10).lightness() > _heat_color(0.50).lightness()
        assert _heat_color(0.50).lightness() > _heat_color(1.0).lightness()
        # green channel monoton turun (hijau -> merah)
        assert _heat_color(0.10).green() > _heat_color(0.50).green()


# ============================================================
# [E] PandasTableModel — gamma membuat nilai kecil berwarna
# ============================================================

class TestModelHeatSensitivity:
    def test_nilai_kecil_dapat_warna_hangat(self):
        """v2.20.1 — gamma: nilai 1% dari skala p99 DAPAT warna hangat
        (red naik jauh di atas endpoint hijau). Ramp linear (lama) hanya
        menambah +2 ke red -> tes ini menuntut gamma aktif."""
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel, _heat_color
        m = PandasTableModel(pd.DataFrame({"% to BOM": [1.0, 100.0]}))
        m.set_heat_column("% to BOM")
        col = 0
        bg_small = m.data(m.index(0, col), Qt.BackgroundRole)
        green = _heat_color(0.0)  # endpoint hijau pucat
        assert bg_small is not None
        # gamma mendorong 1%-of-scale ke kuning pucat: red naik >= +10
        # (ramp linear: red hanya +2 -> tes gagal tanpa gamma).
        assert bg_small.red() > green.red() + 10

    def test_dua_nilai_berbeda_warna_berbeda(self):
        """Sensitivitas inti: dua % to BOM berbeda -> background berbeda
        (bukan semua hijau pucat seperti ramp lama di rentang kecil)."""
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({
            "ANOMALY STATUS": ["Normal", "Normal", "Normal"],
            "% to BOM": [0.5, 5.0, 80.0],
        })
        m = PandasTableModel(df)
        m.set_heat_column("% to BOM")
        col = list(m.dataframe.columns).index("% to BOM")
        bgs = [m.data(m.index(i, col), Qt.BackgroundRole) for i in range(3)]
        assert bgs[0] != bgs[1] != bgs[2]
        # nilai tertinggi paling pekat (lightness terendah)
        assert bgs[2].lightness() < bgs[0].lightness()
