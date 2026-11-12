"""test_v2192.py — regresi 3 permintaan user (layout grup + edit pulih + tombol).

Mengunci 3 perbaikan v2.19.2 atas laporan user:

[A] EDIT KUANTITI PULIH DI TAB ANOMALI (regresi v2.19.0):
    v2.19.0 grouping selalu membentuk __FPS tuple (bahkan 1 anggota) →
    `is_group = isinstance(__FPS, tuple)` selalu True → tombol Simpan
    DISABLED total di tab Anomali. v2.19.2 menambah __SRC_ROWS (tuple
    nomor baris Excel anggota) & mengganti kondisi disable: grup
    1-anggota editable (jalur v2.16.0 pulih); multi-anggota tulis ke semua.

[B] SHEET 'Anomali Grup' (layout SAMPEL TAMPILAN BARU.xlsx):
    Exporter menulis sheet baru dgn 11 kolom sampel, urut (JENIS, NAMA
    BARANG, NAMA RESTO), BARIS KOSONG pemisah antar grup (JENIS, NAMA
    BARANG). [TOTAL]/[% to BOM] alias; format ribuan & persen.

[C] TOMBOL 'Pilih REKAP MENTAH' (bukan 'Olah & Jalankan'):
    Label diperjelas supaya dikenali user (sebelumnya terasa "hilang").
    F1 Bantuan + tooltip ikut disegarkan.
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


def _df_groups() -> pd.DataFrame:
    """3 baris → 2 grup: AYAM (2 anggota, alasan beda) + BEBEK (1 anggota)."""
    from waste_anomaly.rekap_import import SRC_ROW_COL

    def _row(jenis, barang, resto, ket, day, total, src_row):
        d = {str(i): 0.0 for i in range(1, 32)}
        d["5"] = float(day)
        return {
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": barang, "NAMA RESTO": resto,
            "SATUAN": "PCS", "ANOMALY STATUS": "Potensi Anomali",
            "TOTAL BOM": 1000.0, SRC_ROW_COL: src_row,
            **d, "TOTAL": float(total),
        }

    return pd.DataFrame([
        _row("SUSUT", "AYAM", "R1", "Cancel Nota", 100, 100, 2),
        _row("SUSUT", "AYAM", "R1", "Internal", 40, 40, 3),    # same item+resto
        _row("SUSUT", "BEBEK", "R2", "Cancel Nota", 30, 30, 4),
    ])


# ============================================================
# [A] __SRC_ROWS grouping + edit pulih
# ============================================================

class TestSrcRowsGrouping:
    """__SRC_ROWS (tuple nomor baris Excel anggota) dipasang grouping."""

    def test_src_rows_col_dipasang(self):
        from ui.grouping import SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = _df_groups()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31, has_baseline=False)
        assert SRC_ROWS_COL in g.columns
        assert FPS_COL_EXISTS(g)

    def test_single_member_satu_src_row(self):
        """Grup 1-anggota → __SRC_ROWS = tuple 1 elemen → editable langsung."""
        from ui.grouping import SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = _df_groups()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31, has_baseline=False)
        bebek = g[g["NAMA BARANG"] == "BEBEK"].iloc[0]
        sr = bebek[SRC_ROWS_COL]
        assert isinstance(sr, tuple) and len(sr) == 1
        assert sr[0] == 4  # __SRC_ROW baris BEBEK

    def test_multi_member_semua_src_rows(self):
        """Grup multi-anggota → __SRC_ROWS = tuple SEMUA anggota."""
        from ui.grouping import SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = _df_groups()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31, has_baseline=False)
        ayam = g[g["NAMA BARANG"] == "AYAM"].iloc[0]
        sr = ayam[SRC_ROWS_COL]
        assert isinstance(sr, tuple) and len(sr) == 2
        assert set(sr) == {2, 3}  # kedua baris AYAM (Cancel + Internal)

    def test_src_rows_paralel_fps(self):
        """__SRC_ROWS & __FPS sepanjang anggota grup (paralel)."""
        from ui.grouping import FPS_COL, SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = _df_groups()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31, has_baseline=False)
        for _, r in g.iterrows():
            fps = r[FPS_COL]
            sr = r[SRC_ROWS_COL]
            assert isinstance(fps, tuple) and isinstance(sr, tuple)
            assert len(fps) == len(sr)  # paralel: 1 fp per anggota per src_row


def FPS_COL_EXISTS(g) -> bool:
    from ui.grouping import FPS_COL
    return FPS_COL in g.columns


# ============================================================
# [B] Sheet 'Anomali Grup' — layout SAMPEL TAMPILAN BARU
# ============================================================

class TestGroupedLayoutSheet:
    """Sheet 'Anomali Grup': 11 kolom sampel + baris KOSONG pemisah antar grup."""

    def _export(self, tmp_path):
        from waste_anomaly.exporter import export_to_excel
        from waste_anomaly.utils import load_config
        import ui.workers as wk
        df = _df_groups()
        gdf = wk._build_grouped_layout_df(df, 31, lambda m: None)
        out = tmp_path / "out.xlsx"
        cfg = load_config()
        res = export_to_excel(df, str(out), cfg, 31, [], grouped_layout_df=gdf)
        assert res["success"]
        return out

    def test_sheet_ada_dengan_11_kolom(self, tmp_path):
        import openpyxl
        out = self._export(tmp_path)
        wb = openpyxl.load_workbook(str(out), read_only=True)
        assert "Anomali Grup" in wb.sheetnames
        ws = wb["Anomali Grup"]
        # 11 header sampel (meski kolom BULAN LALU tak ada data — header tetap)
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        assert header[:4] == ["JENIS", "NAMA BARANG", "NAMA RESTO",
                              "SOURCE DATA GABUNGAN"]
        assert "[TOTAL]" in header and "[% to BOM]" in header
        assert "ANOMALY STATUS" in header and "PROFIL" in header
        assert len(header) == 11
        wb.close()

    def test_baris_kosong_pemisah_antar_grup(self, tmp_path):
        """Baris KOSONG disisipkan antar grup (JENIS, NAMA BARANG), BUKAN
        di depan grup pertama."""
        import openpyxl
        out = self._export(tmp_path)
        wb = openpyxl.load_workbook(str(out), read_only=True)
        ws = wb["Anomali Grup"]
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        # Baris pertama BUKAN kosong (grup pertama langsung tampil).
        assert any(v is not None for v in rows[0])
        # Cari baris kosong pemisah (semua None).
        blanks = [i for i, r in enumerate(rows)
                  if all(v is None or v == "" for v in r)]
        assert len(blanks) >= 1  # minimal 1 pemisah antar 2 grup
        # Baris setelah pemisah = grup baru (NAMA BARANG berbeda).
        first_blank = blanks[0]
        prev_barang = rows[first_blank - 1][1]
        next_barang = rows[first_blank + 1][1]
        assert prev_barang != next_barang
        wb.close()

    def test_urut_per_jenis_barang_resto(self, tmp_path):
        """Baris diurutkan (JENIS, NAMA BARANG, NAMA RESTO)."""
        import openpyxl
        out = self._export(tmp_path)
        wb = openpyxl.load_workbook(str(out), read_only=True)
        ws = wb["Anomali Grup"]
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True)
                     if any(v is not None for v in r)]
        barangs = [r[1] for r in data_rows]
        # AYAM sebelum BEBEK (urut alfabetis).
        assert barangs.index("AYAM") < barangs.index("BEBEK")
        wb.close()

    def test_kolom_internal_tak_bocor(self, tmp_path):
        """__SRC_ROW/__FPS/__SRC_ROWS TIDAK ditulis ke sheet (internal)."""
        import openpyxl
        out = self._export(tmp_path)
        wb = openpyxl.load_workbook(str(out), read_only=True)
        for sn in wb.sheetnames:
            ws = wb[sn]
            header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
            assert "__SRC_ROW" not in header, f"__SRC_ROW bocor di sheet {sn}"
            assert "__FPS" not in header, f"__FPS bocor di sheet {sn}"
            assert "__SRC_ROWS" not in header, f"__SRC_ROWS bocor di sheet {sn}"
        wb.close()


# ============================================================
# [C] Tombol 'Pilih REKAP MENTAH'
# ============================================================

class TestTombolPilihRekapMentah:
    """Label tombol diperjelas 'Pilih REKAP MENTAH' (bukan 'Olah & Jalankan')."""

    def _view(self, ctx):
        from ui.view_pipeline import PipelineView
        return PipelineView(ctx)

    def test_label_tombol_pilih_rekap_mentah(self):
        app = _qapp()
        from ui.state import AppContext
        view = self._view(AppContext({}))
        try:
            assert "Pilih REKAP MENTAH" in view._btn_import.text()
            assert "REKAP MENTAH_01-31" in view._btn_import.toolTip()
            assert "SEKALI JALAN" in view._btn_import.toolTip()
        finally:
            view.close()
            view.deleteLater()

    def test_bantuan_menyebut_pilih_rekap_mentah(self):
        src = (REPO / "ui" / "app.py").read_text(encoding="utf-8")
        assert "Pilih REKAP MENTAH" in src
        assert "SEKALI" in src
        assert "tanpa file olahan antara" in src
