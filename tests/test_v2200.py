"""test_v2200.py — v2.20.0: heatmap % to BOM + RANGKING WASTE + hide kolom.

3 permintaan user:
1. "kolom % to bom bisa gak diberi warna semacam heat map gitu? tapi
   diabsolutekan dulu ya ... kasih heatmap dan tampilkan nilai asli" —
   background sel dari |nilai| (skala p99 kolom), teks nilai asli.
2. "coba cek kode ini dan tambahkan cuman analisa rangking waste ya" —
   kolom RANGKING WASTE paling kanan tabel Anomali (Top 3 Total &
   Top 3 % BOM per item lintas cabang — padanan langkah
   'TambahRangkingFast' M code user, dihitung LEVEL GRUP).
3. "tambah fitur juga aku bisa hide dan unhide kolom di tab anomali" —
   tombol '⇔ Kolom' (menu centangan + Tampilkan semua kolom).

Lapis yang diuji:
- [A] waste_anomaly.signals.ranking_waste_label — unit label (sumber
  tunggal; dipakai row-level _compute_ranking DAN grup-level grouping).
- [B] ui.grouping.group_anomali_display — RANGKING WASTE GRUP (Top 3
  dari TOTAL grup & % to BOM grup; duplikat berbagi peringkat; 'Cek'
  tak ikut peringkat BOM; multi-anggota = TOTAL sum) + posisi kolom
  (kanan PROFIL).
- [C] ui.models — heatmap _heat_color + PandasTableModel.set_heat_column
  (background |nilai|; teks asli; 'Cek' polos; default MATI).
- [D] ui.widgets.DataTable — width_caps (PROFIL rapat).
- [E] AnomaliView — integrasi: kolom RANGKING WASTE tampak paling
  kanan, heatmap aktif di '% to BOM', hide/unhide kolom via
  _set_column_hidden/_show_all_columns (persisten lintas refresh),
  menu '⇔ Kolom' dibangun benar (centangan per kolom).

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


def _qapp():
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# Fixture data
# ============================================================

def _rank_df() -> pd.DataFrame:
    """4 item × beberapa resto — kasus ranking berbeda per baris.

    AYAM  : 3 resto, TOTAL & % BOM berurutan sama → Top N Total & % BOM.
    BEBEK : R1 tanpa BOM ('Cek') → hanya peringkat Total; R2 Top 1 % BOM.
    CUMI  : 2 resto TOTAL SAMA (duplikat) → berbagi Top 1.
    UDANG : 4 resto → peringkat 4 (R1) tak berlabel ('-').
    SAPI  : multi-anggota (R1 = 60+40 = 100 SUM grup) → Top 1 Total.
    """
    def _row(barang, resto, total, bom, ket="Handling"):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = float(total)
        return {
            "SOURCE DATA": "X", "JENIS": "WASTE", "KETERANGAN": ket,
            "NAMA BARANG": barang, "NAMA RESTO": resto, "SATUAN": "PCS",
            "ANOMALY STATUS": "Normal", "TOTAL BOM": bom,
            "ANOMALY SCORE": 0, **data, "TOTAL": float(total),
        }

    return pd.DataFrame([
        _row("AYAM", "R1", 100.0, 1000.0),
        _row("AYAM", "R2", 50.0, 1000.0),
        _row("AYAM", "R3", 10.0, 1000.0),
        _row("BEBEK", "R1", 7.0, None),
        _row("BEBEK", "R2", 5.0, 100.0),
        _row("CUMI", "R1", 20.0, 100.0),
        _row("CUMI", "R2", 20.0, 100.0),
        _row("UDANG", "R1", 1.0, 100.0),
        _row("UDANG", "R2", 2.0, 100.0),
        _row("UDANG", "R3", 3.0, 100.0),
        _row("UDANG", "R4", 4.0, 100.0),
        _row("SAPI", "R1", 60.0, 1000.0),
        _row("SAPI", "R1", 40.0, 1000.0, ket="Cancel Nota"),
        _row("SAPI", "R2", 50.0, 1000.0),
    ])


def _make_view(df: pd.DataFrame | None = None):
    """Pola _make_view test_v2191 (ctx + set_dataset + refresh)."""
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    _qapp()
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(df if df is not None else _rank_df(),
                    {"key_akhir": 31})
    view._refresh_table()
    _qapp().processEvents()
    return view, ctx


# ============================================================
# [A] ranking_waste_label — unit (sumber tunggal label)
# ============================================================

class TestRankingLabel:
    def test_kedua_peringkat_sama(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(100, 0.5, [100, 50], [0.5, 0.2]) \
            == "Top 1 Total & % BOM"

    def test_kedua_peringkat_bed(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(50, 0.5, [100, 50], [0.5, 0.2]) \
            == "Top 2 Total & Top 1 % BOM"

    def test_hanya_total(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(10, 0.0, [100, 50, 10], [0.9]) \
            == "Top 3 Total"

    def test_hanya_bom(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(1, 0.2, [100, 50], [0.9, 0.2]) \
            == "Top 2 % BOM"

    def test_tidak_masuk_top(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(1, 0.001, [100, 50, 10], [0.9]) == "-"

    def test_none_nan_nol_tak_ikut(self):
        """None/NaN (kedua metrik) dan rasio ≤ 0 → tak masuk peringkat."""
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(None, 0.5, [100], [0.5]) == "Top 1 % BOM"
        assert ranking_waste_label(100, None, [100], [0.5]) == "Top 1 Total"
        assert ranking_waste_label(100, 0.0, [100], []) == "Top 1 Total"
        assert ranking_waste_label(
            float("nan"), float("nan"), [100], [0.5]) == "-"

    def test_duplikat_nilai_berbagi_peringkat(self):
        """Persis List.PositionOf M: pencocokan NILAI — dua nilai sama
        menemukan kemunculan pertama → berbagi peringkat yang sama."""
        from waste_anomaly.signals import ranking_waste_label
        # top [20, 20, 5]: nilai 20 (apapun pemiliknya) → posisi 1
        assert ranking_waste_label(20, 0.2, [20, 20, 5], [0.2]) \
            == "Top 1 Total & % BOM"

    def test_list_kosong_dan_tuple(self):
        from waste_anomaly.signals import ranking_waste_label
        assert ranking_waste_label(100, 0.5, [], []) == "-"
        assert ranking_waste_label(100, 0.5, (100,), (0.5,)) \
            == "Top 1 Total & % BOM"


# ============================================================
# [B] RANGKING WASTE level-GRUP (group_anomali_display)
# ============================================================

class TestGroupRanking:
    def _grouped(self):
        from ui.grouping import group_anomali_display
        df = _rank_df()
        out = group_anomali_display(df, None, {}, key_akhir=31)
        return out

    def test_label_grup_lintas_resto(self):
        """Top 3 Total & % BOM per item lintas resto (padanan
        'TambahRangkingFast' — dihitung dari TOTAL GRUP)."""
        out = self._grouped()
        rk = out.set_index(["NAMA BARANG", "NAMA RESTO"])["RANGKING WASTE"]
        assert rk[("AYAM", "R1")] == "Top 1 Total & % BOM"
        assert rk[("AYAM", "R2")] == "Top 2 Total & % BOM"
        assert rk[("AYAM", "R3")] == "Top 3 Total & % BOM"
        # BEBEK R1 tanpa BOM → 'Cek' → hanya peringkat Total
        assert rk[("BEBEK", "R1")] == "Top 1 Total"
        assert rk[("BEBEK", "R2")] == "Top 2 Total & Top 1 % BOM"
        # CUMI: duplikat TOTAL 20 → berbagi Top 1 (pencocokan nilai)
        assert rk[("CUMI", "R1")] == "Top 1 Total & % BOM"
        assert rk[("CUMI", "R2")] == "Top 1 Total & % BOM"
        # UDANG R1 = peringkat 4 → tak berlabel
        assert rk[("UDANG", "R1")] == "-"
        assert rk[("UDANG", "R4")] == "Top 1 Total & % BOM"

    def test_multi_anggota_total_sum(self):
        """Grup 2-anggota (SAPI R1 60+40) → TOTAL grup = SUM (100)
        yang ikut peringkat — bukan TOTAL anggota per baris."""
        out = self._grouped()
        sapi = out[(out["NAMA BARANG"] == "SAPI")
                   & (out["NAMA RESTO"] == "R1")]
        assert len(sapi) == 1
        assert float(sapi["TOTAL"].iloc[0]) == 100.0
        assert sapi["RANGKING WASTE"].iloc[0] == "Top 1 Total & % BOM"

    def test_posisi_kolom_kanan_profil(self):
        """RANGKING WASTE = kolom paling kanan layout depan (kanan
        PROFIL — permintaan user)."""
        out = self._grouped()
        cols = list(out.columns)
        assert "RANGKING WASTE" in cols
        assert cols.index("RANGKING WASTE") == cols.index("PROFIL") + 1

    def test_pct_cek_tak_masuk_top_bom(self):
        """Baris 'Cek' (tanpa BOM) tak pernah masuk daftar Top % BOM."""
        out = self._grouped()
        bebek = out[out["NAMA BARANG"] == "BEBEK"].reset_index(drop=True)
        cek = bebek[bebek["NAMA RESTO"] == "R1"]
        assert str(cek["% to BOM"].iloc[0]) == "Cek"
        # R2 satu-satunya % BOM numerik → Top 1 % BOM (bukan kalah
        # dari 'Cek' yang tak masuk daftar)
        r2 = bebek[bebek["NAMA RESTO"] == "R2"]
        assert r2["RANGKING WASTE"].iloc[0] == "Top 2 Total & Top 1 % BOM"

    def test_tanpa_kolom_total_tidak_raise(self):
        """Defensif: df tanpa TOTAL/% to BOM → kolom '-' (tanpa raise,
        kontrak group_anomali_display 'tidak pernah raise')."""
        from ui.grouping import group_anomali_display
        df = pd.DataFrame({
            "JENIS": ["W", "W"], "NAMA BARANG": ["X", "X"],
            "NAMA RESTO": ["R1", "R2"], "KETERANGAN": ["a", "b"],
        })
        out = group_anomali_display(df, None, {})
        assert "RANGKING WASTE" in out.columns
        assert (out["RANGKING WASTE"] == "-").all()

    def test_row_level_tak_berubah(self):
        """Kontrak M-fidelity: ranking ROW-LEVEL (signals, dikunci
        regression fixture) TIDAK diubah oleh fitur grup ini."""
        from waste_anomaly.signals import _compute_ranking
        row = pd.Series({
            "TOTAL": 100.0, "Rill % to BOM": 0.5,
            "TopTotal": [100.0, 50.0], "TopBOM": [0.5, 0.2],
        })
        assert _compute_ranking(row) == "Top 1 Total & % BOM"


# ============================================================
# [C] Heatmap model (% to BOM — absolut → warna, teks asli)
# ============================================================

class TestHeatColor:
    def test_stop_ekstrem(self):
        from PySide6.QtGui import QColor
        from ui.models import _heat_color
        assert _heat_color(0.0) == QColor(214, 236, 216)
        assert _heat_color(1.0) == QColor(238, 112, 99)

    def test_clamp_diluar_rentang(self):
        from ui.models import _heat_color
        assert _heat_color(2.0) == _heat_color(1.0)
        assert _heat_color(-0.5) == _heat_color(0.0)

    def test_interpolasi_monoton(self):
        """Intensitas visual naik seiring t: lightness TURUN monoton
        (makin pekat: hijau pucat → kuning → oranye → merah) + hue
        bergeser hijau → merah (t=0 hijau-dominan, t=1 merah-dominan)."""
        from ui.models import _heat_color
        stops = (0.0, 0.35, 0.7, 1.0)
        lights = [_heat_color(t).lightness() for t in stops]
        assert lights == sorted(lights, reverse=True)
        assert lights[-1] < lights[0]
        c0, c1 = _heat_color(0.0), _heat_color(1.0)
        assert c0.green() > c0.red()   # hijau pucat
        assert c1.red() > c1.green()   # merah


class TestModelHeatmap:
    def _model(self):
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({
            "ANOMALY STATUS": ["Normal", "Normal", "Normal",
                               "Prioritas Tinggi", "Normal"],
            "% to BOM": [0.10, -0.10, "Cek", 40.0, 0.0],
        })
        m = PandasTableModel(df)
        return m, Qt

    def test_background_abs_bukan_tanda(self):
        """|+0,10| == |-0,10| → WARNA SAMA (permintaan user:
        'diabsolutekan dulu'); teks tetap nilai asli bertanda."""
        m, Qt = self._model()
        m.set_heat_column("% to BOM")
        col = list(m.dataframe.columns).index("% to BOM")
        bg_pos = m.data(m.index(0, col), Qt.BackgroundRole)
        bg_neg = m.data(m.index(1, col), Qt.BackgroundRole)
        txt_pos = m.data(m.index(0, col), Qt.DisplayRole)
        txt_neg = m.data(m.index(1, col), Qt.DisplayRole)
        assert bg_pos is not None and bg_neg is not None
        assert bg_pos == bg_neg
        assert txt_pos == "10,00%" and txt_neg == "-10,00%"

    def test_cek_tanpa_warna(self):
        """'Cek' non-numerik → TANPA warna heat (jatuh ke tint baris
        status Normal #f0fdf4 — bukan ramp heat)."""
        from PySide6.QtGui import QColor
        m, Qt = self._model()
        m.set_heat_column("% to BOM")
        col = list(m.dataframe.columns).index("% to BOM")
        assert m.data(m.index(2, col), Qt.BackgroundRole) == QColor("#f0fdf4")
        assert m.data(m.index(2, col), Qt.DisplayRole) == "Cek"

    def test_outlier_p99_merah_penuh(self):
        """Nilai ≥ p99 kolom (40,00 vs p99 ≈ 39,9) → merah penuh
        (stop t=1) — TIDAK memucatkan seluruh kolom (skala robust)."""
        from PySide6.QtGui import QColor
        from ui.models import _HEAT_STOPS
        m, Qt = self._model()
        m.set_heat_column("% to BOM")
        col = list(m.dataframe.columns).index("% to BOM")
        bg = m.data(m.index(3, col), Qt.BackgroundRole)
        assert bg == QColor(*_HEAT_STOPS[-1][1])
        # nilai kecil tetap dapat ramp (bukan semua hijau pucat mati)
        bg_small = m.data(m.index(0, col), Qt.BackgroundRole)
        assert bg_small != bg

    def test_default_mati(self):
        """Tanpa set_heat_column → perilaku lama (tint baris status —
        Normal = #f0fdf4, BUKAN warna ramp heat)."""
        from PySide6.QtGui import QColor
        m, Qt = self._model()
        col = list(m.dataframe.columns).index("% to BOM")
        assert m._heat_col is None
        bg = m.data(m.index(0, col), Qt.BackgroundRole)
        assert bg == QColor("#f0fdf4")  # tint Normal — bukan heat ramp

    def test_menimpa_tint_status_kolom_ini(self):
        """Kolom heat menimpa tint baris status (Prioritas Tinggi tetap
        diwarnai heat, bukan tint)."""
        m, Qt = self._model()
        col = list(m.dataframe.columns).index("% to BOM")
        m.set_heat_column(None)  # baseline: tint status jalan
        bg_tint = m.data(m.index(3, col), Qt.BackgroundRole)
        m.set_heat_column("% to BOM")
        bg_heat = m.data(m.index(3, col), Qt.BackgroundRole)
        assert bg_tint is not None
        assert bg_heat is not None and bg_heat != bg_tint

    def test_skala_dihitung_ulang_set_dataframe(self):
        """Dataset berganti → skala p99 baru (nilai sama bisa berbeda
        intensitas — bukan skala basi dari df lama)."""
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel, _heat_color
        m = PandasTableModel(pd.DataFrame({"% to BOM": [1.0]}))
        m.set_heat_column("% to BOM")
        col = 0
        # df baru: nilai 1.0 kini jauh di bawah p99 (100) → lebih pucat
        m.set_dataframe(pd.DataFrame({"% to BOM": [1.0, 100.0]}))
        bg = m.data(m.index(0, col), Qt.BackgroundRole)
        p99 = float(pd.Series([1.0, 100.0]).abs().quantile(0.99))
        assert bg == _heat_color(min(1.0 / p99, 1.0))
        assert bg != _heat_color(1.0)

    def test_baris_pemisah_tanpa_warna(self):
        """Baris pemisah grup (__SEP) → semua role kosong."""
        m, Qt = self._model()
        m.set_heat_column("% to BOM")
        m.set_separator_column("__SEP")
        m.set_dataframe(pd.DataFrame({
            "% to BOM": [0.5, 0.1], "__SEP": [False, True]}))
        col = list(m.dataframe.columns).index("% to BOM")
        assert m.data(m.index(1, col), Qt.BackgroundRole) is None
        assert m.data(m.index(1, col), Qt.DisplayRole) == ""


# ============================================================
# [D] width_caps — PROFIL rapat (DataTable)
# ============================================================

class TestWidthCaps:
    def test_profil_dibatasi_width_caps(self):
        """PROFIL dirapatkan (≤150px) dengan width_caps; tanpa caps
        teks panjang menuntut lebar jauh lebih besar."""
        from ui.widgets import DataTable
        _qapp()
        t = DataTable()
        t.resize(1400, 500)
        t.show()
        _qapp().processEvents()
        df = pd.DataFrame({
            "PROFIL": ["Tiap Hari — Baru " * 6] * 3,
            "RANGKING WASTE": ["Top 1 Total & % BOM"] * 3,
        })
        t.set_dataframe(df.copy(), width_caps={"PROFIL": 150})
        idx = list(t.model().dataframe.columns).index("PROFIL")
        assert not t.isColumnHidden(idx)
        assert t.columnWidth(idx) <= 150
        t.hide()

    def test_tanpa_caps_lebar_ukur(self):
        from ui.widgets import DataTable
        _qapp()
        t = DataTable()
        t.resize(1400, 500)
        t.show()
        _qapp().processEvents()
        df = pd.DataFrame({
            "PROFIL": ["Tiap Hari — Baru " * 6] * 3,
            "RANGKING WASTE": ["Top 1 Total & % BOM"] * 3,
        })
        t.set_dataframe(df.copy())
        idx = list(t.model().dataframe.columns).index("PROFIL")
        assert t.columnWidth(idx) > 150  # konten panjang → kolom lebar
        t.hide()


# ============================================================
# [E] Integrasi AnomaliView
# ============================================================

class TestViewIntegrasi:
    def test_rangking_waste_tampak_paling_kanan(self):
        """Kolom RANGKING WASTE ada di model, TAMPAK, dan berada di
        kanan PROFIL (layout tabel)."""
        from ui.view_anomali import TABLE_COLS
        view, _ctx = _make_view()
        t = view._table
        mdf = t.model().dataframe
        assert "RANGKING WASTE" in mdf.columns
        cols = list(mdf.columns)
        idx_rk = cols.index("RANGKING WASTE")
        idx_profil = cols.index("PROFIL")
        assert idx_rk == idx_profil + 1
        assert not t.isColumnHidden(idx_rk)
        # kontrak TABLE_COLS: tepat setelah PROFIL (paling kanan)
        assert TABLE_COLS.index("RANGKING WASTE") \
            == TABLE_COLS.index("PROFIL") + 1
        # label grup benar-benar terisi (bukan kosong/'-')
        assert set(mdf["RANGKING WASTE"].dropna()) - {"-", ""} != set()
        view.close()

    def test_heatmap_terpasang_di_view(self):
        """Model view memasang heat '% to BOM' → sel numerik berwarna."""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import Qt
        view, _ctx = _make_view()
        m = view._table.model()
        assert m._heat_col == "% to BOM"
        mdf = m.dataframe
        col = list(mdf.columns).index("% to BOM")
        colored = 0
        for r in range(m.rowCount()):
            bg = m.data(m.index(r, col), Qt.BackgroundRole)
            if isinstance(bg, QColor):
                colored += 1
        assert colored > 0
        view.close()

    def test_hide_unhide_kolom(self):
        """Sembunyikan kolom → hidden di tabel TAPI data tetap di model
        (pop-up detail tak terdampak); tampilkan semua → pulih."""
        view, _ctx = _make_view()
        t = view._table
        mdf = t.model().dataframe
        idx = list(mdf.columns).index("PROFIL")
        assert not t.isColumnHidden(idx)

        view._set_column_hidden("PROFIL", True)
        mdf2 = t.model().dataframe
        idx2 = list(mdf2.columns).index("PROFIL")
        assert t.isColumnHidden(idx2)
        assert "PROFIL" in mdf2.columns  # data tetap ada (hanya hidden)

        # sembunyi bertahan melewati refresh lain (persisten)
        view._refresh_table()
        mdf3 = t.model().dataframe
        assert t.isColumnHidden(list(mdf3.columns).index("PROFIL"))

        view._show_all_columns()
        mdf4 = t.model().dataframe
        assert not t.isColumnHidden(list(mdf4.columns).index("PROFIL"))
        view.close()

    def test_alias_tersembunyi_bersama_kanonik(self):
        """Kolom ber-alias judul ('% to BOM' → '[% to BOM]') ikut
        disembunyikan via nama kanonik (alias & kanonik satu kesatuan)."""
        view, _ctx = _make_view()
        t = view._table
        view._set_column_hidden("% to BOM", True)
        mdf = t.model().dataframe
        assert t.isColumnHidden(list(mdf.columns).index("% to BOM"))
        view._show_all_columns()
        mdf = t.model().dataframe
        assert not t.isColumnHidden(list(mdf.columns).index("% to BOM"))
        view.close()

    def test_menu_kolom_dibangun_benar(self):
        """Menu '⇔ Kolom': satu aksi centangan per kolom TABLE_COLS di
        dataset + aksi 'Tampilkan semua kolom'. Dibangun via
        _build_column_menu (TANPA exec — tak membuka loop modal di test);
        toggle aksi PROFIL → kolom tersembunyi lewat sinyal toggled."""
        view, _ctx = _make_view()
        menu = view._build_column_menu()
        actions = list(menu.actions())
        titles = [a.text() for a in actions]
        assert "Tampilkan semua kolom" in titles
        # aksi centangan: judul alias utk TOTAL/% to BOM
        assert "[TOTAL]" in titles and "[% to BOM]" in titles
        assert "RANGKING WASTE" in titles
        assert "PROFIL" in titles
        checkable = [a for a in actions if a.isCheckable()]
        assert checkable and all(a.isChecked() for a in checkable)
        # toggle aksi PROFIL → kolom tersembunyi (lewat sinyal toggled)
        act_profil = next(a for a in actions if a.text() == "PROFIL")
        act_profil.setChecked(False)
        _qapp().processEvents()
        mdf = view._table.model().dataframe
        assert view._table.isColumnHidden(
            list(mdf.columns).index("PROFIL"))
        menu.deleteLater()
        view.close()
