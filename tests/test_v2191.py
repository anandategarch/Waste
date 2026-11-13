"""test_v2191.py — audit layout baru v2.19.0 (tampilan grup tab Anomali).

4 bug ditemukan audit pasca-rilis v2.19.0 — semua mereproduksi dulu fix
(ditulis SEBELUM perbaikan supaya terlihat merah dulu):

- [A] KOLOM BARU TERSEMBUNYI: ``visible_cols`` dihitung dari df LEVEL
  BARIS (sebelum agregasi grup) — kolom khusus grup (SOURCE DATA
  GABUNGAN, TOTAL BULAN LALU & % Selisih, Selisih Bulan Lalu) tak
  pernah ada di df itu → isColumnHidden(True) selamanya. Inti redesain
  tak terlihat user.
- [B] FUNNEL KETERANGAN → 0 BARIS: menu funnel menawarkan nilai JOIN
  grup ('Handling | Cancel Nota') tapi filter GLOBAL level-baris tak
  pernah match nilai baris tunggal → tabel kosong.
- [C] FUNNEL ANOMALY STATUS MEMANGKAS TOTAL: filter global level-baris
  menyaring ANGGOTA grup → TOTAL grup terpangkas diam-diam (140→40) —
  kelas bug yang sama dgn combo PERUBAHAN yang sudah diperbaiki v2.19.0
  (filter harus LEVEL GRUP).
- [D] GROUPING RAISE: ``group_anomali_display`` melempar ValueError bila
  df tanpa TOTAL/hari/BULAN LALU (agg dict kosong) — melanggar kontrak
  docstring "tidak pernah raise".
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
    return QApplication.instance() or QApplication(sys.argv)


def _df_2grup() -> pd.DataFrame:
    """4 baris → 3 grup anomali (v2.21.0 grouping per KETERANGAN dulu):
    (Alat/Mesin, BEBEK, R2) 30 · (Cancel Nota, AYAM, R1) 60 (2 anggota
    same-keterangan: 40 PT + 20 Normal — worst-of-group PT) · (Handling,
    AYAM, R1) 100. TOTAL BOM disertakan supaya % to BOM grup terhitung
    (section-6 grouping)."""
    def _row(jenis, ket, barang, resto, total, status, day=5):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = float(day)
        return {
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": barang, "NAMA RESTO": resto,
            "SATUAN": "PCS", "ANOMALY STATUS": status,
            "TOTAL BOM": 1000.0,
            **data, "TOTAL": float(total),
        }

    return pd.DataFrame([
        _row("WASTE", "Handling", "AYAM", "R1", 100.0, "Perlu Review", 100),
        _row("WASTE", "Cancel Nota", "AYAM", "R1", 40.0,
             "Prioritas Tinggi", 40),
        _row("WASTE", "Cancel Nota", "AYAM", "R1", 20.0,
             "Normal", 20),
        _row("WASTE", "Alat/Mesin", "BEBEK", "R2", 30.0,
             "Potensi Anomali", 30),
    ]).assign(**{
        "HARI TERSANGKA": [5, 5, 5, 5],
        "HARI MAX": [5, 5, 5, 5],
    })


def _make_view(df: pd.DataFrame | None = None):
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    _qapp()
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(df if df is not None else _df_2grup(),
                    {"key_akhir": 31})
    view._refresh_table()
    _qapp().processEvents()
    return view, ctx


# ============================================================
# [A] kolom sampel user TAMPAK (bukan tersembunyi)
# ============================================================

class TestAKolomBaruTampak:
    def test_kolom_sampel_user_tidak_tersembunyi(self):
        """Kolom layout sampel user yang ADA di model harus TAMPAK di
        tabel. Bug A: visible_cols dihitung dari df baris → kolom khusus
        grup (SOURCE DATA GABUNGAN dst.) hidden=True selamanya.
        Kolom baseline (TOTAL BULAN LALU & % Selisih, Selisih Bulan Lalu,
        PERUBAHAN) hanya ada saat pembanding aktif — diuji test berikut.
        v2.20.1: viewport di-resize LEBAR + _auto_columns supaya kolom
        narrow_hide (SOURCE DATA GABUNGAN, PERUBAHAN) TAMPAK — KETERANGAN
        kini lebih lebar dari JENIS (konten 'Kualitas Internal' vs
        'WASTE'), viewport sempit menutup narrow_hide lebih dini."""
        from ui.view_anomali import TABLE_COLS
        view, _ = _make_view()
        view.resize(1800, 700)
        view.show()
        _qapp().processEvents()
        t = view._table
        t._auto_columns()
        _qapp().processEvents()
        mdf = t.model().dataframe
        hidden = []
        for name in TABLE_COLS:
            if name not in mdf.columns:
                continue  # kolom opsional (butuh pembanding) — test bawah
            if t.isColumnHidden(list(mdf.columns).index(name)):
                hidden.append(f"{name}: HIDDEN")
        assert not hidden, (
            f"kolom layout sampel user tersembunyi: {hidden}")
        # kolom inti grup WAJIB ada di model (fixture lengkap):
        for name in ("JENIS", "NAMA BARANG", "NAMA RESTO",
                     "SOURCE DATA GABUNGAN", "TOTAL", "% to BOM",
                     "ANOMALY STATUS", "PROFIL", "KETERANGAN"):
            assert name in mdf.columns, f"{name} hilang dari model grup"
        view.close()

    def test_kolom_gabungan_tampil_saat_baseline_aktif(self):
        """Kolom TOTAL BULAN LALU & % Selisih + Selisih Bulan Lalu hanya
        ada saat pembanding aktif — dan harus TAMPAK saat ada.
        v2.21.0: BULAN LALU per grup KETERANGAN (join per-baris
        change_vs_history per (resto, barang, jenis, keterangan) lalu
        SUM per grup) — grup Handling & Cancel Nota TERPISAH."""
        from ui.grouping import LASTMONTH_COMBINED_COL, SELISIH_COL
        view, ctx = _make_view()
        ctx.set_banding_baseline({
            "label": "Juli 2026", "key_akhir": 31,
            "agg_detail": pd.DataFrame({
                "NAMA RESTO": ["R1", "R1"], "NAMA BARANG": ["AYAM", "AYAM"],
                "JENIS": ["WASTE", "WASTE"],
                "KETERANGAN": ["Handling", "Cancel Nota"],
                "TOTAL": [80.0, 10.0]}),
        })
        view._refresh_table()
        _qapp().processEvents()
        t = view._table
        mdf = t.model().dataframe
        assert LASTMONTH_COMBINED_COL in mdf.columns
        assert SELISIH_COL in mdf.columns
        assert "PERUBAHAN" in mdf.columns
        # Kolom gabungan & selisih BUKAN narrow_hide → wajib tampak.
        # (PERUBAHAN & SOURCE DATA GABUNGAN = narrow_hide by-design v2.19.0
        # — disembunyikan di viewport sempit, dikunci test_v2187.)
        for name in (LASTMONTH_COMBINED_COL, SELISIH_COL):
            assert name not in (t._narrow_hide or [])
            assert not t.isColumnHidden(
                list(mdf.columns).index(name)), f"{name} tersembunyi (bug A)"
        # v2.21.0 — per grup KETERANGAN: (Cancel Nota, AYAM, R1) BULAN LALU
        # 10 (TOTAL 60 → Selisih 50); (Handling, AYAM, R1) BULAN LALU 80
        # (TOTAL 100 → Selisih 20).
        g_cn = mdf[(mdf["NAMA BARANG"] == "AYAM")
                   & (mdf["KETERANGAN"] == "Cancel Nota")].iloc[0]
        assert abs(float(g_cn[LASTMONTH_COMBINED_COL]) - 10.0) < 0.01
        assert abs(float(g_cn[SELISIH_COL]) - 50.0) < 0.01
        g_h = mdf[(mdf["NAMA BARANG"] == "AYAM")
                  & (mdf["KETERANGAN"] == "Handling")].iloc[0]
        assert abs(float(g_h[LASTMONTH_COMBINED_COL]) - 80.0) < 0.01
        assert abs(float(g_h[SELISIH_COL]) - 20.0) < 0.01
        view.close()


# ============================================================
# [B] funnel KETERANGAN — nilai grup (v2.21.0: nilai tunggal), level grup
# ============================================================

class TestBFunnelKeterangan:
    def test_uncheck_nilai_grup_lain_tetap_tampil(self):
        """v2.21.0 — KETERANGAN = KUNCI grup: nilai menu = nilai tunggal
        (bukan join 'Handling | Cancel Nota'). Uncheck 'Handling' → grup
        lain (Alat/Mesin + Cancel Nota) tetap tampil (bukan 0 baris — bug B
        lama: filter nilai-join level baris tak pernah match)."""
        from PySide6.QtCore import Qt
        view, ctx = _make_view()
        view.show()
        _qapp().processEvents()
        m = view._table.model()
        assert m.rowCount() == 5  # 3 grup + 2 baris pemisah
        hdr = view._table.horizontalHeader()
        logical = list(m.dataframe.columns).index("KETERANGAN")
        hdr._open_menu(logical)
        _qapp().processEvents()
        menu = hdr._menu
        it = next(menu._lw.item(i) for i in range(menu._lw.count())
                  if menu._lw.item(i).data(Qt.ItemDataRole.UserRole)
                  == "Handling")
        it.setCheckState(Qt.CheckState.Unchecked)
        menu._apply_now()
        _qapp().processEvents()
        assert m.rowCount() == 3, (
            "bug B: filter nilai level baris → 0 baris; harusnya 2 grup "
            "(Alat/Mesin, Cancel Nota) + 1 pemisah tetap tampil")
        assert m.record(0)["NAMA BARANG"] == "BEBEK"  # Alat/Mesin sort dulu
        view.close()

    def test_filter_keterangan_tak_menulis_state_global(self):
        """Funnel KETERANGAN di tab Anomali = filter LOKAL grup (state
        ctx tak tersentuh — pola kolom non-mapping; KPI tak berubah)."""
        view, ctx = _make_view()
        view._on_header_filter("KETERANGAN", "keterangan", ["Alat/Mesin"])
        _qapp().processEvents()
        assert not any(ctx.active_filters.values()), (
            "bug B: funnel KETERANGAN menulis state global — harus lokal ")
        assert view._hf_state("KETERANGAN") == ["Alat/Mesin"]
        # lepas
        view._on_header_filter("KETERANGAN", "keterangan", None)
        _qapp().processEvents()
        assert view._table.model().rowCount() == 5  # 3 grup + 2 pemisah
        view.close()

    def test_filter_keterangan_total_grup_utuh(self):
        """Filter lokal KETERANGAN menyaring GRUP (bukan anggota) — TOTAL
        grup yang lolos tetap utuh (multi-anggota same-keterangan: 40+20)."""
        view, _ = _make_view()
        view._on_header_filter("KETERANGAN", "keterangan",
                               ["Cancel Nota"])
        _qapp().processEvents()
        m = view._table.model()
        assert m.rowCount() == 1
        assert abs(float(m.record(0)["TOTAL"]) - 60.0) < 0.01, (
            "TOTAL grup Cancel Nota harus utuh 60 (40+20)")
        view.close()

    def test_hapus_filter_melepas_keterangan_lokal(self):
        """✕ Hapus Filter melepas funnel KETERANGAN lokal (janji tooltip
        'Hapus SEMUA filter')."""
        view, _ = _make_view()
        view._on_header_filter("KETERANGAN", "keterangan", ["Alat/Mesin"])
        _qapp().processEvents()
        assert view._hfilters
        view._on_clear_filters()
        _qapp().processEvents()
        assert not view._hfilters
        assert view._table.model().rowCount() == 5  # 3 grup + 2 pemisah
        view.close()


# ============================================================
# [C] funnel ANOMALY STATUS — level grup, TOTAL tak terpangkas
# ============================================================

class TestCFunnelStatus:
    def test_filter_status_total_grup_utuh(self):
        """Filter status=['Prioritas Tinggi'] → grup (Cancel Nota, AYAM,
        R1) (worst-of-group PT, 2 anggota 40 PT + 20 Normal) tampil dgn
        TOTAL UTUH 60 — bukan 40 (anggota PT saja dipangkas)."""
        view, _ = _make_view()
        m = view._table.model()
        view._on_header_filter("ANOMALY STATUS", "status",
                               ["Prioritas Tinggi"])
        _qapp().processEvents()
        assert m.rowCount() == 1, (
            "grup (Cancel Nota, AYAM, R1) worst PT harus tampil")
        assert abs(float(m.record(0)["TOTAL"]) - 60.0) < 0.01, (
            "bug C: TOTAL grup terpangkas diam-diam (harusnya utuh 60)")
        view.close()

    def test_filter_status_lokal_bukan_global(self):
        view, ctx = _make_view()
        view._on_header_filter("ANOMALY STATUS", "status",
                               ["Prioritas Tinggi"])
        _qapp().processEvents()
        assert not any(ctx.active_filters.values()), (
            "bug C: funnel STATUS menulis state global — harus lokal grup")
        view.close()

    def test_filter_status_global_dari_tab_hari_level_grup(self):
        """Filter status GLOBAL (dipasang dari funnel tab Hari — lintas
        tab) diterapkan LEVEL GRUP di tab Anomali: TOTAL utuh."""
        view, ctx = _make_view()
        ctx.set_filter("status", ["Prioritas Tinggi"])  # dari tab Hari
        view._refresh_table()  # view offscreen → refresh eksplisit
        _qapp().processEvents()
        m = view._table.model()
        assert m.rowCount() == 1, "grup (Cancel Nota, AYAM, R1) PT tampil"
        assert abs(float(m.record(0)["TOTAL"]) - 60.0) < 0.01, (
            "bug C lintas-tab: TOTAL grup terpangkas — harus utuh 60")
        view.close()

    def test_filter_keterangan_global_dari_tab_hari_level_grup(self):
        """Filter keterangan GLOBAL (dari tab Hari): grup ber-keterangan
        terpilih tampil dgn TOTAL UTUH (v2.21.0 nilai grup = kunci — isin
        langsung; multi-anggota tak terpangkas)."""
        view, ctx = _make_view()
        ctx.set_filter("keterangan", ["Cancel Nota"])  # dari tab Hari
        view._refresh_table()  # view offscreen → refresh eksplisit
        _qapp().processEvents()
        m = view._table.model()
        # grup (Cancel Nota, AYAM, R1) — 2 anggota 40+20
        assert m.rowCount() == 1, (
            "grup keterangan 'Cancel Nota' harus tampil")
        assert abs(float(m.record(0)["TOTAL"]) - 60.0) < 0.01, (
            "bug C lintas-tab: TOTAL grup terpangkas — harus utuh 60")
        view.close()


# ============================================================
# [D] grouping defensif — agg kosong tak boleh raise
# ============================================================

class TestDGroupingDefensif:
    def test_tanpa_total_dan_hari_tidak_raise(self):
        """df hanya kunci grup (tanpa TOTAL/hari/BULAN LALU) → kerangka
        grup tetap dikembalikan, BUKAN raise ValueError (kontrak
        docstring grouping.py: 'tidak pernah raise')."""
        from ui.grouping import GROUP_KEYS, group_anomali_display
        df = pd.DataFrame({
            "JENIS": ["W", "W", "S"],
            "NAMA BARANG": ["X", "X", "Y"],
            "NAMA RESTO": ["R1", "R1", "R2"],
            "KETERANGAN": ["A", "A", "C"],
        })
        out = group_anomali_display(df, None, {})  # tidak boleh raise
        assert len(out) == 2, "2 grup (A·X·R1, C·Y·R2) harus tampil"
        assert all(k in out.columns for k in GROUP_KEYS)

    def test_df_kosong_tidak_raise(self):
        from ui.grouping import group_anomali_display
        df = pd.DataFrame({"JENIS": [], "NAMA BARANG": [],
                           "NAMA RESTO": [], "KETERANGAN": []})
        out = group_anomali_display(df, None, {})
        assert out is not None and out.empty

    def test_kunci_nan_tidak_raise_grup_tetap_terbentuk(self):
        """Kunci ber-None/NaN (dropna=False) → grup NaN tetap terbentuk
        dan nilai join/SUM benar (merge NaN-key harus tetap match).
        v2.21.0: kunci NaN yg diuji = KETERANGAN (fallback tak jalan
        sebab JENIS juga None) — 2 baris NaN KETERANGAN menyatu."""
        from ui.grouping import group_anomali_display
        df = pd.DataFrame({
            "JENIS": [None, None, "WASTE"],
            "NAMA BARANG": ["AYAM", "AYAM", "BEBEK"],
            "NAMA RESTO": ["R1", "R1", "R2"],
            "KETERANGAN": [None, None, "C"],
            "TOTAL": [10.0, 20.0, 5.0],
        })
        out = group_anomali_display(df, None, {})
        assert len(out) == 2
        ayam = out[out["NAMA BARANG"] == "AYAM"].iloc[0]
        assert abs(float(ayam["TOTAL"]) - 30.0) < 0.01
        # v2.21.0: KETERANGAN = KUNCI grup → 2 baris NaN KETERANGAN
        # menyatu jadi SATU grup NaN (bukan join 'A | B' — join kolom
        # kunci tak dijalankan lagi); grup kedua = ('C', BEBEK, R2).
        assert pd.isna(ayam["KETERANGAN"])
        bebek = out[out["NAMA BARANG"] == "BEBEK"].iloc[0]
        assert str(bebek["KETERANGAN"]) == "C"
