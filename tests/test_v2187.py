"""test_v2187.py — v2.18.7: 3 permintaan user (Anomali + Follow Up).

[J] "di tab anomali kasih kolom tambahan itu jenis nya waste, susut atau
    trial, kolom anomali score hapus aja."
    Kolom JENIS (WASTE/SUSUT/TRIAL) kini SELALU tampil (keluar dari
    narrow_hide — pola tab Hari v2.12.3; dulu tersembunyi responsif di
    viewport sempit sehingga user tak melihatnya). ANOMALY SCORE keluar
    dari TABLE_COLS (kolom tabel dihapus) — skor TETAP jadi dasar ranking
    (sort_desc), filter "Skor ≥", dan tampil di pop-up detail.

[F] "di tab anomali aku bisa pilih tampilkan yang sudah masuk follow up
    atau tampilkan semua."
    Combo "Tampilkan:" (Semua / ✓ Sudah masuk Follow Up) — filter LOKAL
    view (KPI & tab lain tak tersentuh). Saat aktif, lepas centang ✓ =
    baris LANGSUNG hilang (override _on_followup_changed → render ulang);
    reset otomatis via tombol ✕ Hapus Filter & dataset baru (hook
    _reset_view_controls).

[I] "misal aku export hasil follow up besok aku bisa import lagi atas
    hasil export tersebut dengan format yang sama dan otomatis centang.
    import ITL itu hapus aja belum kepakai."
    📥 Impor File Ekspor: baca file 💾 Ekspor APA ADANYA (sheet FOLLOW
    UP) → sidik jari per baris → add_followup_many = auto-centang.
    Fitur "Impor Hasil TL" (⑯ v2.13.3) DIHAPUS TOTAL bersama state-nya
    (followup_resolved.json, apply_followup_resolved, kolom STATUS
    TL/PIC) — test_v2133.py ikut dihapus.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# Fixture — view Anomali 3 baris (WASTE/SUSUT/TRIAL, skor beda)
# ============================================================

def _df_anomali() -> pd.DataFrame:
    data = {str(d): 0.0 for d in range(1, 31)}
    data["5"] = 90.0
    data["24"] = 819.0
    return pd.DataFrame([
        {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
         "KETERANGAN": "Cancel Nota", "NAMA BARANG": "MIE",
         "NAMA RESTO": "RESTO 1", "SATUAN": "GR",
         "ANOMALY STATUS": "Prioritas Tinggi", "ANOMALY SCORE": 12,
         **data, "TOTAL": float(sum(data.values()))},
        {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "TRIAL",
         "KETERANGAN": "Handling", "NAMA BARANG": "KOPI",
         "NAMA RESTO": "RESTO 2", "SATUAN": "GR",
         "ANOMALY STATUS": "Potensi Anomali", "ANOMALY SCORE": 9,
         **{str(d): 0.5 for d in range(1, 31)}, "TOTAL": 15.0},
        {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "SUSUT",
         "KETERANGAN": "Alat/Mesin", "NAMA BARANG": "TEH",
         "NAMA RESTO": "RESTO 2", "SATUAN": "GR",
         "ANOMALY STATUS": "Perlu Review", "ANOMALY SCORE": 4,
         **{str(d): 1.0 for d in range(1, 31)}, "TOTAL": 30.0},
    ])


def _make_view():
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    app = _qapp()
    ctx = AppContext({})
    ctx.set_dataset(_df_anomali(), {"key_akhir": 30})
    view = AnomaliView(ctx)
    view.show()
    view.refresh()
    app.processEvents()
    return view, ctx


def _fps():
    from waste_anomaly.followup import fingerprint_series
    return [str(v) for v in fingerprint_series(_df_anomali()).tolist()]


def _n_data(dfm: pd.DataFrame) -> int:
    """v2.19.3 — jumlah baris DATA murni (baris pemisah grup __SEP dari
    layout sampel tidak dihitung)."""
    if "__SEP" in dfm.columns:
        return sum(1 for v in dfm["__SEP"].tolist() if v is not True)
    return len(dfm)


# ============================================================
# [J] KOLOM KETERANGAN TAMPIL · KOLOM SKOR DIHAPUS
# ============================================================

class TestKeteranganTampilSkorDihapus:

    def test_table_cols_kontrak(self):
        """v2.20.1 — kolom pertama tabel Anomali KETERANGAN (bukan JENIS):
        alasan pencatatan (Alat/Mesin, Cancel Nota, ..., SUSUT, TRIAL).
        ANOMALY SCORE tetap keluar; layout sampel user lengkap;
        BULAN LALU/PERUBAHAN % digabung (SOURCE DATA GABUNGAN + kolom
        gabungan total bulan lalu & selisih). JENIS tetap di df model
        (kunci grup + sort + funnel global 'jenis' di tab Hari) —
        disembunyikan dari tabel Anomali."""
        from ui.view_anomali import TABLE_COLS
        assert "ANOMALY SCORE" not in TABLE_COLS
        assert "KETERANGAN" in TABLE_COLS
        assert "JENIS" not in TABLE_COLS  # v2.20.1: diganti KETERANGAN
        for col in ("KETERANGAN", "NAMA BARANG", "NAMA RESTO",
                    "SOURCE DATA GABUNGAN", "TOTAL", "% to BOM",
                    "TOTAL BULAN LALU & % Selisih", "Selisih Bulan Lalu",
                    "PERUBAHAN", "ANOMALY STATUS", "PROFIL"):
            assert col in TABLE_COLS, col
        # kolom layout lama yang diganti/digabung
        assert "BULAN LALU" not in TABLE_COLS
        assert "PERUBAHAN %" not in TABLE_COLS

    def test_keterangan_tampil_jenis_disembunyikan(self):
        """KETERANGAN tampak di tabel (bukan narrow_hide); JENIS kini
        disembunyikan dari tabel Anomali (tetap di df model utk kunci
        grup/sort/funnel global); skor disembunyikan sebagai kolom
        non-tabel TAPI tetap ada di df model (pop-up/ranking)."""
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        cols = list(dfm.columns)
        assert "ANOMALY SCORE" in dfm.columns  # tetap di df (pop-up detail)
        assert view._table.isColumnHidden(cols.index("ANOMALY SCORE")), (
            "kolom skor harus disembunyikan (dihapus dari tabel)")
        assert "KETERANGAN" in dfm.columns
        assert not view._table.isColumnHidden(cols.index("KETERANGAN")), (
            "kolom KETERANGAN harus selalu tampak (v2.20.1)")
        assert "KETERANGAN" not in (view._table._narrow_hide or []), (
            "KETERANGAN tak boleh masuk narrow_hide")
        # JENIS tetap di df (kunci grup + sort layout sampel) tapi
        # disembunyikan dari tabel Anomali sebab kolom pertama kini
        # KETERANGAN (permintaan user "kolom jenis diganti KETERANGAN").
        assert "JENIS" in dfm.columns
        assert view._table.isColumnHidden(cols.index("JENIS")), (
            "kolom JENIS kini disembunyikan dari tabel Anomali (v2.20.1)")
        # v2.19.0: narrow_hide kini SOURCE DATA GABUNGAN + PERUBAHAN.
        assert "SOURCE DATA GABUNGAN" in view._table._narrow_hide
        view.close()

    def test_nilai_keterangan_terbaca_vocabulary(self):
        """Isi kolom KETERANGAN = alasan pencatatan (vocabulary user v2.20.1:
        Alat/Mesin, Cancel Nota, Handling, Kualitas, Kualitas Eksternal,
        Kualitas Internal, Over Stock, SUSUT, TRIAL) — nilai dibaca
        langsung dari tabel tanpa pop-up. SUSUT/TRIAL muncul via fallback
        KETERANGAN kosong -> JENIS (grouping.py). v2.19.3 — baris PEMISAH
        grup (NaN) dikecualikan."""
        view, _ = _make_view()
        dfm = view._table.model().dataframe
        ket = ([v for v, s in zip(dfm["KETERANGAN"].tolist(),
                                  dfm["__SEP"].tolist())
                if s is not True]
               if "__SEP" in dfm.columns else dfm["KETERANGAN"].tolist())
        vocab = {"Alat/Mesin", "Cancel Nota", "Handling", "Kualitas",
                 "Kualitas Eksternal", "Kualitas Internal", "Over Stock",
                 "SUSUT", "TRIAL"}
        assert set(ket) <= vocab, (
            f"nilai KETERANGAN di luar vocabulary user: {set(ket) - vocab}")
        assert set(ket), "KETERANGAN tak boleh kosong di tabel"
        view.close()

    def test_ranking_tetap_berdasar_skor(self):
        """v2.19.3 — DITULIS ULANG JUJUR: urutan DEFAULT tabel kini
        LAYOUT SAMPEL TAMPILAN BARU (permintaan user: grup per item +
        baris kosong pemisah): urut (KETERANGAN, NAMA BARANG, NAMA RESTO)
        (v2.21.0 — kunci pertama JENIS → KETERANGAN, permintaan user
        "grouping pakai keterangan terus nama barang"), bukan skor turun.
        Sort by skor TETAP tersedia (SortControl/klik judul — model.sort
        separator-aware)."""
        view, _ = _make_view()
        dfm = view._table._model.dataframe
        # Default: urut grup — TEH(Alat/Mesin) < MIE(Cancel Nota) <
        # KOPI(Handling) (KETERANGAN alfabetis) + pemisah kosong antar grup.
        ket_vals = ([v for v, s in zip(dfm["KETERANGAN"].tolist(),
                                      dfm["__SEP"].tolist())
                     if s is not True]
                    if "__SEP" in dfm.columns
                    else dfm["KETERANGAN"].tolist())
        assert ket_vals == sorted(ket_vals)
        if "__SEP" in dfm.columns:
            assert any(v is True for v in dfm["__SEP"].tolist()), (
                "layout sampel: baris pemisah antar grup harus ada")
            assert not dfm["__SEP"].tolist()[0]  # tidak di depan grup pertama
        # Sort by skor masih jalan (pemisah dibuang — tabel ter-ranked).
        from PySide6.QtCore import Qt
        skor_col = list(dfm.columns).index("ANOMALY SCORE")
        view._table._model.sort(skor_col, Qt.SortOrder.DescendingOrder)
        dfm2 = view._table._model.dataframe
        skor2 = pd.to_numeric(dfm2["ANOMALY SCORE"])
        assert int(skor2.iloc[0]) == 12 and int(skor2.iloc[-1]) == 4
        assert int(skor2.iloc[0]) == int(skor2.max())
        view.close()


# ============================================================
# [F] COMBO "TAMPILKAN:" — SUDAH FOLLOW UP / SEMUA
# ============================================================

class TestComboTampilkan:

    def test_kombo_default_dua_pilihan(self):
        view, _ = _make_view()
        assert view._cb_followup.count() == 2
        assert view._cb_followup.currentIndex() == 0
        assert view._cb_followup.currentData() is None  # Semua (bawaan)
        view.close()

    def test_filter_sudah_follow_up(self):
        """Pilih ✓ Sudah masuk Follow Up → tabel hanya baris tercentang;
        kembali ke Semua → tabel penuh (3 grup data).
        v2.19.3 — jumlah baris dihitung per DATA (pemisah dikecualikan)."""
        view, ctx = _make_view()
        fps = _fps()
        ctx.add_followup_many([fps[0]])  # MIE (skor tertinggi)
        view._cb_followup.setCurrentIndex(1)  # → _on_fu_filter → render
        dfm = view._table.model().dataframe
        assert _n_data(dfm) == 1
        assert dfm.iloc[0]["NAMA BARANG"] == "MIE"
        # v2.19.0: label menyebut GRUP (tampilan item×cabang).
        assert "1 grup" in view._lbl_count.text()
        # kembali ke Semua
        view._cb_followup.setCurrentIndex(0)
        assert _n_data(view._table.model().dataframe) == 3
        view.close()

    def test_pesan_0_baris_kontekstual(self):
        """Filter FU aktif + belum ada centangan → pesan menjelaskan
        penyebab follow-up (bukan menyalahkan funnel/skor umum)."""
        view, _ = _make_view()
        view._cb_followup.setCurrentIndex(1)
        assert view._table.model().rowCount() == 0
        txt = view._lbl_count.text()
        assert txt.startswith("0 anomali lolos filter"), txt
        assert "Follow Up" in txt, txt
        view.close()

    def test_lepas_centang_langsung_hilang(self):
        """Saat filter FU aktif, lepas centang ✓ (dari mana pun) = baris
        LANGSUNG hilang dari tabel — override _on_followup_changed
        me-render ulang (bukan hanya segarkan ✓ in-place).
        v2.19.3 — jumlah baris dihitung per DATA (pemisah dikecualikan)."""
        view, ctx = _make_view()
        fps = _fps()
        ctx.add_followup_many([fps[0], fps[1]])  # MIE + KOPI
        view._cb_followup.setCurrentIndex(1)
        assert _n_data(view._table.model().dataframe) == 2
        # lepas satu centang (jalur ctx — sama dgn klik ✓ di tabel)
        ctx.toggle_followup(fps[0], False)
        _qapp().processEvents()
        dfm = view._table.model().dataframe
        assert _n_data(dfm) == 1
        assert dfm.iloc[0]["NAMA BARANG"] == "KOPI"
        view.close()

    def test_reset_lewat_tombol_hapus_filter(self):
        """✕ Hapus Filter me-reset combo ke 'Semua' (tooltip menjanjikan
        SEMUA — hook _reset_view_controls).
        v2.19.3 — jumlah baris dihitung per DATA (pemisah dikecualikan)."""
        view, ctx = _make_view()
        ctx.add_followup_many([_fps()[0]])
        view._cb_followup.setCurrentIndex(1)
        assert view._cb_followup.currentIndex() == 1
        view._btn_clear.click()
        assert view._cb_followup.currentIndex() == 0
        assert view._cb_followup.currentData() is None
        assert _n_data(view._table.model().dataframe) == 3
        view.close()

    def test_hook_mixin_bukan_salinan(self):
        """Kontrak konsolidasi v2.13.8 tetap utuh: _on_followup_changed
        resolve ke MILIK mixin (identitas fungsi); view hanya meng-override
        hook kecil _followup_filter_active (pola _reset_view_controls)."""
        from ui.followup_table import FollowupTableMixin
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        assert (AnomaliView._on_followup_changed
                is FollowupTableMixin._on_followup_changed)
        assert (AnomaliView._followup_filter_active
                is not FollowupTableMixin._followup_filter_active)
        assert (HariView._followup_filter_active
                is FollowupTableMixin._followup_filter_active)
        view, _ = _make_view()
        assert view._followup_filter_active() is False  # Semua (bawaan)
        view._cb_followup.setCurrentIndex(1)
        assert view._followup_filter_active() is True
        view.close()

    def test_reset_di_dataset_baru(self):
        """Dataset baru tak mewarisi pilihan combo run lama (pola A2
        combo Kategori PERUBAHAN)."""
        view, ctx = _make_view()
        ctx.add_followup_many([_fps()[0]])
        view._cb_followup.setCurrentIndex(1)
        ctx.set_dataset(_df_anomali(), {"key_akhir": 30})  # → refresh()
        assert view._cb_followup.currentIndex() == 0
        assert view._cb_followup.currentData() is None
        view.close()


# ============================================================
# [I] IMPOR FILE EKSPOR — round-trip auto-centang
# ============================================================

def _fu_rows() -> pd.DataFrame:
    return pd.DataFrame({
        "SOURCE DATA": ["W1", "W2"],
        "JENIS": ["WASTE", "SUSUT"],
        "KETERANGAN": ["Cancel Nota", "Alat/Mesin"],
        "NAMA BARANG": ["AYAM", "BEBEK"],
        "NAMA RESTO": ["R1", "R2"],
        "SATUAN": ["PCS", "KG"],
        "TOTAL": [30.0, 15.0], "AVG": [1.0, 0.5], "MAX": [20.0, 15.0],
        "1": [10, 0], "2": [20, 0], "4": [0, 15],
    })


def _export_file(tmp: Path) -> Path:
    """File ekspor ASLI (jalur produksi export_followup_xlsx)."""
    from waste_anomaly.followup import FP_COL, export_followup_xlsx, \
        fingerprint_series
    df = _fu_rows()
    df[FP_COL] = fingerprint_series(df)
    path = tmp / "Waste_FollowUp_uji.xlsx"
    export_followup_xlsx(df, str(path), {}, set())
    return path


class TestReadFollowupExportFps:

    def test_round_trip_file_ekspor(self):
        """File hasil export_followup_xlsx dibaca kembali APA ADANYA →
        sidik jari identik dgn fingerprint_series baris sumber (urutan
        + nilai)."""
        import tempfile
        from waste_anomaly.followup import fingerprint_series, \
            read_followup_export_fps
        with tempfile.TemporaryDirectory() as td:
            p = _export_file(Path(td))
            res = read_followup_export_fps(str(p))
            assert not res.get("error"), res
            assert res["n_rows"] == 2
            expect = [str(v) for v in fingerprint_series(_fu_rows())]
            assert res["fps"] == expect

    def test_pic_terisi_tetap_dibaca_semua_baris(self):
        """Bedanya dgn 'Impor Hasil TL' (lama): kolom PIC/KATEGORI/
        PENYEBAB yang kebetulan terisi DIABAIKAN — SEMUA baris file
        dikembalikan (impor = pulihkan centangan, bukan status)."""
        import tempfile
        from waste_anomaly.followup import read_followup_export_fps
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ekspor_terisi.xlsx"
            df = _fu_rows()
            df["PIC"] = ["Tegar", None]
            df["KATEGORI"] = ["Proses", None]
            df["PENYEBAB TERJADINYA WASTE"] = ["salah timbang", None]
            df.to_excel(p, sheet_name="FOLLOW UP", index=False)
            res = read_followup_export_fps(str(p))
            assert not res.get("error"), res
            assert res["n_rows"] == 2 and len(res["fps"]) == 2

    def test_kolom_centang_dan_duplikat_dedup(self):
        """Kolom '✓' ekspor diabaikan; baris kembar identik menyatu
        (dedup — pola select_followup_rows)."""
        import tempfile
        from waste_anomaly.followup import CHECK_COL, \
            read_followup_export_fps
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ekspor_dup.xlsx"
            df = pd.concat([_fu_rows(), _fu_rows().iloc[[0]]],
                           ignore_index=True)
            df.insert(0, CHECK_COL, [True, True, True])
            df.to_excel(p, sheet_name="FOLLOW UP", index=False)
            res = read_followup_export_fps(str(p))
            assert not res.get("error"), res
            assert res["n_rows"] == 3
            assert len(res["fps"]) == 2  # baris kembar identik menyatu

    def test_error_jujur(self):
        """File absen / sheet salah / kolom kunci hilang → "error"
        (defensif, tidak pernah raise — pola fitur lama)."""
        import tempfile
        from waste_anomaly.followup import read_followup_export_fps
        assert read_followup_export_fps(
            "/tmp/tidak_ada_12345.xlsx").get("error")
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "nosheet.xlsx"
            pd.DataFrame({"A": [1]}).to_excel(p1, index=False,
                                              sheet_name="Sheet1")
            assert read_followup_export_fps(str(p1)).get("error")
            p2 = Path(td) / "salahkolom.xlsx"
            pd.DataFrame({"TOTAL": [1.0]}).to_excel(
                p2, index=False, sheet_name="FOLLOW UP")
            res = read_followup_export_fps(str(p2))
            assert res.get("error") and "Kolom kunci" in res["error"]


class TestImporMemulihkanDaftar:
    """Alur user: ekspor hari ini → (besok) daftar kosong → Impor File
    Ekspor → semua baris otomatis tercentang kembali."""

    def _view(self, tmp: Path):
        from ui.state import AppContext
        from ui.view_followup import FollowUpView
        app = _qapp()
        ctx = AppContext({}, followup_path=str(tmp / "f.json"))
        ctx.set_dataset(_fu_rows(), {"key_akhir": 31})
        from waste_anomaly.followup import fingerprint_series
        fps = [str(v) for v in fingerprint_series(_fu_rows())]
        ctx.add_followup_many(fps)
        view = FollowUpView(ctx)
        view.show()
        view.refresh()
        app.processEvents()
        return view, ctx, fps

    def test_auto_centang_end_to_end(self, tmp_path, monkeypatch):
        from PySide6.QtWidgets import QFileDialog
        from waste_anomaly.followup import CHECK_COL, export_followup_xlsx
        view, ctx, fps = self._view(tmp_path)
        # 1) ekspor (format produksi, warna ikut)
        p = str(tmp_path / "ekspor_kemarin.xlsx")
        export_followup_xlsx(view._rows, p, view._red, view._amber)
        # 2) "besok": daftar kosong (mis. ganti komputer / kosongkan)
        ctx.clear_followup()
        _qapp().processEvents()
        assert len(ctx.followup_keys) == 0
        assert view._table.model().rowCount() == 0
        # 3) impor file ekspor → otomatis centang
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            classmethod(lambda cls, *a, **k: (p, "")))
        import ui.view_followup as vfm
        infos: list = []
        monkeypatch.setattr(
            vfm.QMessageBox, "information",
            lambda *a, **k: infos.append(a)
            or vfm.QMessageBox.StandardButton.Ok)
        view._on_import()
        _qapp().processEvents()
        assert len(ctx.followup_keys) == 2
        assert view._table.model().rowCount() == 2
        dfm = view._table.model().dataframe
        assert dfm[CHECK_COL].astype(bool).all()
        assert infos, "dialog ringkasan impor harus muncul"
        view.close()

    def test_impor_error_dialog(self, tmp_path, monkeypatch):
        """File salah → dialog kritis + daftar tak berubah."""
        from PySide6.QtWidgets import QFileDialog
        view, ctx, _fps = self._view(tmp_path)
        ctx.clear_followup()
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            classmethod(lambda cls, *a, **k: (str(tmp_path / "takada.xlsx"),
                                              "")))
        import ui.view_followup as vfm
        crits: list = []
        monkeypatch.setattr(
            vfm.QMessageBox, "critical",
            lambda *a, **k: crits.append(a)
            or vfm.QMessageBox.StandardButton.Ok)
        view._on_import()
        assert crits, "file absen harus memunculkan dialog error"
        assert len(ctx.followup_keys) == 0
        view.close()

    def test_tombol_dan_tooltip(self):
        """Tombol pengganti 'Impor Hasil TL': teks + tooltip menjelaskan
        auto-centang file ekspor (permintaan user)."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            view, _ctx, _fps = self._view(Path(td))
            btn = view._btn_import
            assert "Impor File Ekspor" in btn.text()
            assert "otomatis di-CENTANG kembali" in btn.toolTip()
            assert "Ekspor Excel" in btn.toolTip()
            view.close()


# ============================================================
# [R] IMPOR HASIL TL DIHAPUS TOTAL
# ============================================================

class TestImporHilangDihapus:

    def test_state_tanpa_followup_resolved(self):
        """AppContext tak lagi punya followup_resolved /
        apply_followup_resolved (fitur ⑯ v2.13.3 dihapus)."""
        from ui.state import AppContext
        _qapp()
        ctx = AppContext({})
        assert not hasattr(ctx, "followup_resolved")
        assert not hasattr(ctx, "apply_followup_resolved")

    def test_sumber_bersih(self):
        """followup.py tanpa import_followup_workbook/load/save_resolved;
        help tanpa jejak ITL; FollowUpView tanpa kolom STATUS TL."""
        src_fu = (REPO / "waste_anomaly" / "followup.py").read_text(
            encoding="utf-8")
        assert "def import_followup_workbook" not in src_fu
        assert "def load_resolved" not in src_fu
        assert "def save_resolved" not in src_fu
        from ui.app import _HELP_HTML
        assert "Impor Hasil TL" not in _HELP_HTML
        assert "followup_resolved.json" not in _HELP_HTML
        assert "STATUS TL" not in _HELP_HTML

    def test_tanpa_kolom_status_tl(self):
        """Refresh daftar follow-up TIDAK lagi menambah kolom STATUS
        TL / PIC (dulu muncul bila ada resolusi)."""
        import tempfile
        from ui.state import AppContext
        from ui.view_followup import FollowUpView
        from waste_anomaly.followup import fingerprint_series
        _qapp()
        with tempfile.TemporaryDirectory() as td:
            ctx = AppContext({}, followup_path=str(Path(td) / "f.json"))
            ctx.set_dataset(_fu_rows(), {"key_akhir": 31})
            fps = [str(v) for v in fingerprint_series(_fu_rows())]
            ctx.add_followup_many(fps)
            view = FollowUpView(ctx)
            view.refresh()
            cols = list(view._table.model().dataframe.columns)
            assert "STATUS TL" not in cols and "PIC" not in cols
            assert "selesai" not in view._lbl_info.text()
            view.close()


# ============================================================
# VERSI — pin triple (pola test_v2139)
# ============================================================

class TestVersi:
    def test_versi_pin(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        assert APP_VERSION == __version__ == \
            load_config().get("version") == "2.21.1"
