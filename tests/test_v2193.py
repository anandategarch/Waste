"""test_v2193.py — regresi 2 laporan user pasca-v2.19.2.

[D] SIMPAN KOREKSI WinError 5 (file terkunci Excel):
    User: "GAGAL Simpan Koreksi ... [WinError 5] Access is denied ...
    .tmp_write.10148 -> REKAP MENTAH_...xlsx" — file sumber terbuka di
    Excel mengunci os.replace SETELAH semua kerja tulis (tmp tercecer,
    user baru tahu di akhir). Fix v2.19.3:
      1. PRE-CHECK kunci tulis DI MUKA (os.open O_RDWR sebentar) →
         pesan "TUTUP file-nya dulu (Excel)" SEBELUM kerja jalan.
      2. RETRY os.replace 4×0,4 dtk utk kunci transien (antivirus /
         OneDrive / Excel baru ditutup); kunci permanen → pesan ramah +
         lokasi tmp utk pemulihan manual (asli tetap utuh — atomik).

[E] TABEL tab Anomali tanpa SPASI antar grup:
    User: "tampilan di tab anomali kok gak ada spasi nya? maksudnya
    spasi itu insert blank line after each item label dari kolom jenis
    dan nama barang". Fix v2.19.3: tabel urut (JENIS, NAMA BARANG, NAMA
    RESTO) + BARIS KOSONG pemisah antar grup (JENIS, NAMA BARANG) —
    persis layout SAMPEL TAMPILAN BARU.xlsx / sheet 'Anomali Grup':
      - baris pemisah: seluruh kolom NaN + __SEP=True → render kosong,
        tak selectable, record()=None, tak masuk funnel.
      - model.sort separator-aware: sort kolom GRUP (JENIS/NAMA BARANG)
        → pemisah disisip ulang; sort kolom lain (skor/TOTAL) → pemisah
        dibuang (tabel polos ter-ranked — pemisah tak bermakna).
      - SortControl "(urut default)" kini benar-benar mengembalikan
        urutan default (dulu NO-OP senyap) — apply_default_order().
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


# ============================================================
# fixture df — 2 grup item: AYAM (2 resto) + BEBEK (1 resto)
# (pola test_v2191: kolom hari 1-31 + TOTAL BOM supaya grouping jalan penuh)
# ============================================================

def _df_2grup() -> pd.DataFrame:
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

    # v2.21.0: 3 grup per KETERANGAN dulu — (Cancel Nota, AYAM, R1),
    # (Cancel Nota, BEBEK, R1), (Internal, AYAM, R2).
    return pd.DataFrame([
        _row("SUSUT", "Cancel Nota", "AYAM", "R1", 100.0,
             "Prioritas Tinggi", 100),
        _row("SUSUT", "Internal", "AYAM", "R2", 40.0,
             "Perlu Review", 40),
        _row("SUSUT", "Cancel Nota", "BEBEK", "R1", 30.0,
             "Potensi Anomali", 30),
    ]).assign(**{
        "HARI TERSANGKA": [5, 5, 5],
        "HARI MAX": [5, 5, 5],
    })


def _make_view():
    """AnomaliView ber-dataset 2-grup (pola test_v2191)."""
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    _qapp()
    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(_df_2grup(), {"key_akhir": 31})
    view._refresh_table()
    _qapp().processEvents()
    return view, ctx


# ============================================================
# [E] insert_group_separators — unit
# ============================================================

class TestInsertGroupSeparators:
    def test_pemisah_antar_grup_bukan_pertama_terakhir(self):
        from ui.grouping import insert_group_separators, SEP_COL
        # v2.21.0: sort by kunci grup baru (KETERANGAN dulu) supaya baris
        # grup bertetangga — pemisah antar (KETERANGAN, NAMA BARANG).
        df = _df_2grup().sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        out = insert_group_separators(df)
        seps = out[SEP_COL].tolist()
        # Tidak sebelum grup pertama, tidak setelah grup terakhir.
        assert seps[0] is False and seps[-1] is False
        # 3 grup (CN-AYAM, CN-BEBEK, Internal-AYAM) → 2 pemisah.
        assert sum(1 for v in seps if v is True) == 2
        assert out.iloc[0]["NAMA BARANG"] == "AYAM"  # grup pertama
        # pemisah pertama tepat antara (CN, AYAM) → (CN, BEBEK): barang
        # berubah; pemisah kedua antara (CN, BEBEK) → (Internal, AYAM).
        assert pd.isna(out.iloc[1]["NAMA BARANG"])  # baris sep = NaN semua
        assert out.iloc[2]["NAMA BARANG"] == "BEBEK"
        assert pd.isna(out.iloc[3]["NAMA BARANG"])  # sep kedua
        assert out.iloc[4]["KETERANGAN"] == "Internal"

    def test_pemisah_kolom_semua_nan(self):
        from ui.grouping import insert_group_separators, SEP_COL
        df = _df_2grup().sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        out = insert_group_separators(df)
        sep_row = out[out[SEP_COL] == True].iloc[0]  # noqa: E712
        for c in out.columns:
            if c != SEP_COL:
                assert pd.isna(sep_row[c]), f"kolom {c} harus NaN"

    def test_idempoten(self):
        from ui.grouping import insert_group_separators
        df = _df_2grup().sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        once = insert_group_separators(df)
        twice = insert_group_separators(once)
        assert len(once) == len(twice) == 5  # 3 data + 2 pemisah

    def test_grup_tunggal_tanpa_pemisah(self):
        from ui.grouping import insert_group_separators, SEP_COL
        df = _df_2grup().iloc[0:1].copy()
        out = insert_group_separators(df)
        assert len(out) == 1 and SEP_COL in out.columns

    def test_nan_berurutan_bukan_pemisah_palsu(self):
        """Dua baris NaN KETERANGAN berurutan ≠ grup berubah (pandas ne
        NaN≠NaN — guard fillna sentinel)."""
        from ui.grouping import insert_group_separators, SEP_COL
        df = pd.DataFrame([
            {"KETERANGAN": None, "NAMA BARANG": "X", "TOTAL": 1},
            {"KETERANGAN": None, "NAMA BARANG": "X", "TOTAL": 2},
        ])
        out = insert_group_separators(df)
        assert not any(v is True for v in out[SEP_COL].tolist())


# ============================================================
# [E] model — baris pemisah render kosong + tak selectable
# ============================================================

class TestModelSeparator:
    def _model_with_sep(self):
        from ui.models import PandasTableModel
        from ui.grouping import insert_group_separators, SEP_COL, SEP_KEYS
        df = _df_2grup().sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        disp = insert_group_separators(df)
        m = PandasTableModel(disp)
        m.set_separator_column(SEP_COL, group_keys=SEP_KEYS)
        return m

    def test_display_kosong_untuk_pemisah(self):
        from PySide6.QtCore import Qt
        m = self._model_with_sep()
        sep_row = next(i for i, v in enumerate(m.dataframe["__SEP"].tolist())
                       if v is True)
        for c in range(m.columnCount()):
            assert m.data(m.index(sep_row, c), Qt.DisplayRole) in ("", None)

    def test_flags_tak_selectable_pemisah(self):
        from PySide6.QtCore import Qt
        m = self._model_with_sep()
        sep_row = next(i for i, v in enumerate(m.dataframe["__SEP"].tolist())
                       if v is True)
        f = m.flags(m.index(sep_row, 0))
        assert not (f & Qt.ItemFlag.ItemIsSelectable)
        # data row tetap selectable.
        assert m.flags(m.index(0, 0)) & Qt.ItemFlag.ItemIsSelectable

    def test_record_pemisah_none(self):
        m = self._model_with_sep()
        sep_row = next(i for i, v in enumerate(m.dataframe["__SEP"].tolist())
                       if v is True)
        assert m.record(sep_row) is None
        assert m.record(0)["NAMA BARANG"] == "AYAM"

    def test_sort_non_grup_buang_pemisah(self):
        from PySide6.QtCore import Qt
        m = self._model_with_sep()
        tot = list(m.dataframe.columns).index("TOTAL")
        m.sort(tot, Qt.DescendingOrder)
        assert "__SEP" not in m.dataframe.columns or not any(
            v is True for v in m.dataframe["__SEP"].tolist())
        assert len(m.dataframe) == 3  # data murni

    def test_sort_grup_sisip_ulang_pemisah(self):
        from PySide6.QtCore import Qt
        m = self._model_with_sep()
        nb = list(m.dataframe.columns).index("NAMA BARANG")
        m.sort(nb, Qt.AscendingOrder)
        seps = [v for v in m.dataframe["__SEP"].tolist() if v is True]
        # v2.21.0: 3 grup → sort by NAMA BARANG (kolom grup — stable
        # mergesort) → pemisah disisip ulang antar (KETERANGAN, BARANG):
        # urutan sort [AYAM(CN), AYAM(Internal), BEBEK(CN)] → 2 pemisah.
        assert len(seps) == 2


# ============================================================
# [E] view — tabel tab Anomali ber-spasi + default order
# ============================================================

class TestAnomaliTableSeparators:
    def test_tabel_tab_anomali_punya_pemisah(self):
        from ui.grouping import SEP_COL
        _qapp()
        view, _ = _make_view()
        try:
            m = view._table.model()
            assert SEP_COL in m.dataframe.columns
            seps = m.dataframe[SEP_COL].tolist()
            assert any(v is True for v in seps), (
                "tabel harus punya baris pemisah antar grup (layout sampel)")
            assert not seps[0] and not seps[-1]  # antar grup, bukan tepi
            # Urutan default = (JENIS, NAMA BARANG, NAMA RESTO).
            first = m.record(0)
            assert first["NAMA BARANG"] == "AYAM"
        finally:
            view.close()
            view.deleteLater()

    def test_apply_default_order_pulihkan_pemisah(self):
        from PySide6.QtCore import Qt
        from ui.grouping import SEP_COL
        _qapp()
        view, _ = _make_view()
        try:
            m = view._table.model()
            tot = list(m.dataframe.columns).index("TOTAL")
            m.sort(tot, Qt.DescendingOrder)  # pemisah dibuang
            assert not any(v is True for v in m.dataframe[SEP_COL].tolist())
            view._table.apply_default_order()  # "(urut default)"
            assert any(v is True for v in m.dataframe[SEP_COL].tolist()), (
                "apply_default_order harus mengembalikan layout grup+spasi")
        finally:
            view.close()
            view.deleteLater()

    def test_funnel_tak_menawarkan_nilai_pemisah(self):
        """Menu funnel dibangun dari model df (ber-pemisah) — baris
        pemisah NaN harus DIBUANG dari value_counts (bukan pilihan
        '(kosong)' dgn jumlah fiktif)."""
        from PySide6.QtCore import Qt
        _qapp()
        view, _ = _make_view()
        try:
            m = view._table.model()
            hdr = view._table.horizontalHeader()
            logical = list(m.dataframe.columns).index("NAMA BARANG")
            hdr._open_menu(logical)
            _qapp().processEvents()
            menu = hdr._menu
            labels = [menu._lw.item(i).data(Qt.ItemDataRole.UserRole)
                      for i in range(menu._lw.count())]
            assert "AYAM" in labels and "BEBEK" in labels
            assert all(v is not None for v in labels), (
                "nilai None (baris pemisah) tak boleh jadi pilihan funnel")
        finally:
            view.close()
            view.deleteLater()


# ============================================================
# [D] source_writer — pre-check kunci + retry
# ============================================================

class TestSourceWriterLock:
    def _make_sheet(self, tmp_path) -> Path:
        """Workbook rekap mini: header + 1 baris data hari 1-5."""
        import openpyxl
        p = tmp_path / "REKAP MENTAH_TEST.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "REKAP MENTAH"
        ws.append(["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
                   "NAMA RESTO", "SATUAN", 1, 2, 3, 4, 5])
        ws.append(["WASTE BAHAN DAN PACKAGING", "WASTE", "Cancel Nota",
                   "AYAM", "R1", "GR", 10, 0, 0, 0, 0])
        wb.save(p)
        return p

    def test_precheck_file_readonly(self, tmp_path, monkeypatch):
        """File read-only: Windows → atribut dibersihkan otomatis (v2.19.4
        baru) → write SUKSES; POSIX chmod 444 (no st_fileattributes →
        _clear_readonly no-op) → SourceWriteError 'TERKUNI' SEBELUM tulis
        (tanpa tmp file tercecer)."""
        import stat
        from waste_anomaly.source_writer import (
            SourceWriteError, write_day_edits)
        p = self._make_sheet(tmp_path)
        p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        try:
            if sys.platform.startswith("win"):
                # v2.19.4: chmod 444 di Windows set readonly ATTR →
                # _clear_readonly membersihkan → write berlanjut sukses.
                res = write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                                      backup=False)
                assert res["ok"], "read-only attr dibersihkan → harus sukses"
                leftovers = list(tmp_path.glob("*.tmp_write.*"))
                assert not leftovers, f"tmp tercecer: {leftovers}"
            else:
                # POSIX: os.open O_RDWR read-only → PermissionError juga
                # (kecuali root — CI non-root).
                import os as _os
                if _os.geteuid() != 0:
                    try:
                        write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                                        backup=False)
                        raised = None
                    except SourceWriteError as e:
                        raised = str(e)
                    assert raised is not None, "file read-only harus ditolak"
                    assert "TERKUNI" in raised
                leftovers = list(tmp_path.glob("*.tmp_write.*"))
                assert not leftovers, f"tmp tercecer: {leftovers}"
        finally:
            p.chmod(0o644)

    def test_precheck_file_normal_lolos(self, tmp_path):
        """File writable normal → pre-check diam (tidak raise)."""
        from waste_anomaly.source_writer import write_day_edits
        p = self._make_sheet(tmp_path)
        res = write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                              backup=False)
        assert res["ok"] and res["cells_written"] == 1

    def test_retry_replace_lalu_sukses(self, tmp_path, monkeypatch):
        """os.replace gagal PermissionError 2× (kunci transien antivirus)
        lalu sukses di percobaan ke-3 → tulis TETAP sukses (retry efektif);
        sleep dipersingkat supaya test cepat."""
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        calls = {"n": 0}
        real_replace = os.replace

        def flaky_replace(a, b):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(
                    5, "Access is denied (simulasi kunci transien)")
            return real_replace(a, b)

        monkeypatch.setattr(sw.time, "sleep", lambda *_a: None)
        monkeypatch.setattr(sw.os, "replace", flaky_replace)
        res = sw.write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                                 backup=False)
        assert res["ok"]
        assert calls["n"] == 3  # 2 gagal + 1 sukses

    def test_replace_permanen_pesan_ramah(self, tmp_path, monkeypatch):
        """os.replace SELALU PermissionError + open(src,'r+b') juga diblokir
        (file dibuka Excel — kunci permanen, v2.19.4 fallback in-place juga
        gagal) → SourceWriteError menyebut 'DIBUKA di Excel' + lokasi file
        pemulihan (tmp_write — rename ke _KOREKSI juga diblokir karena
        os.replace monkeypatched selalu gagal); file asli TIDAK berubah."""
        import openpyxl
        import waste_anomaly.source_writer as sw
        p = self._make_sheet(tmp_path)
        monkeypatch.setattr(sw.time, "sleep", lambda *_a: None)
        monkeypatch.setattr(
            sw.os, "replace",
            lambda *_a: (_ for _ in ()).throw(PermissionError(
                5, "Access is denied (simulasi Excel terbuka)")))
        # v2.19.4 — blok fallback in-place: open(src, "r+b") diblokir.
        # Mode "rb"/"r" tetap lolos (openpyxl/zipfile baca tmp + verifikasi).
        real_open = open
        def blocked_open(path, mode="r", *a, **kw):
            if "r+b" in mode and str(path) == str(p):
                raise PermissionError(5, "Access denied (Excel terbuka)")
            return real_open(path, mode, *a, **kw)
        monkeypatch.setattr(sw, "open", blocked_open, raising=False)
        try:
            sw.write_day_edits(str(p), 2, {"3": 55.0}, logger=None,
                               backup=False)
            raised = None
        except sw.SourceWriteError as e:
            raised = str(e)
        assert raised is not None
        assert "DIBUKA di Excel" in raised
        # Lokasi file hasil utk pemulihan (tmp_write — rename ke _KOREKSI
        # juga diblokir os.replace monkeypatched selalu gagal).
        assert "tmp_write" in raised or "_KOREKSI" in raised
        # File asli utuh: nilai hari-3 masih 0 (belum dikoreksi).
        wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        vals = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        wb.close()
        assert vals[8] == 0  # kolom '3' (index 8) masih nilai lama
        # tmp hasil TERSIMPAN (pemulihan manual tersedia).
        leftovers = list(tmp_path.glob("*.tmp_write.*"))
        assert len(leftovers) == 1
