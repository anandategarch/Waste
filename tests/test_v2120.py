"""test_v2120.py — regresi v2.12.0: tab Follow Up (centang ✓ → shortlist
rekap + warna hari mencurigakan + ekspor + persistensi).

Kontrak yang dikunci:
- fingerprint_series: deterministik (nilai sama → sidik jari sama, lintas
  dtype int/float); kembar identik menyatu; kembar beda-nilai terbeda;
  kolom absen tak crash. Data asli: 1.871 grup duplikat → sidik jari
  NILAI (bukan kunci bisnis) satu-satunya identitas yang jujur.
- select_followup_rows: mask key + dedup kembar (keep first) + __FP.
- suspicious_days: merah = HARI TERSANGKA (fallback HARI MAX); amber =
  ≥ 2× rata-rata HARI AKTIF (fallback AVG), nilai > 0, bukan hari merah;
  rata-rata ≤ 0/NaN → tanpa amber (guard anti 'semua hari amber').
- Persistensi: roundtrip atomic; file absen → []; korup → backup .bad +
  []; AppContext(followup_path=...) memuat saat konstruksi (badge akurat).
- AppContext: toggle no-op tanpa broadcast; add_followup_many = SATU
  broadcast + duplikat dihitung 0; clear; followup_df (dataset PENUH,
  dedup); prune saat data baru (nilai hari berubah → fp berubah →
  terpangkas); memo fingerprint per data_version.
- PandasTableModel: kolom ✓ flags UserCheckable HANYA kolom itu;
  CheckStateRole dari nilai bool; DisplayRole '' (bukan 'True');
  setData (enum CheckState DAN int 2) flip nilai + dataChanged +
  sinyal check_toggled; kolom lain tak bisa di-setData; sort kolom ✓
  jalan (bool → numeric); penanda (fp, kolom) STABIL melewati sort;
  notify_column_changed meng-emis dataChanged satu kolom.
- AnomaliView: display memo (objek stabil per df — cache fit tetap kena)
  + nilai ✓ disegarkan in-place pasca followup_changed (tanpa reset
  model); klik ✓ (mouse click nyata di rect indikator) → state ctx;
  tombol ☑ Centang yang tampil → add_many SATU broadcast.
- FollowUpView: baris tercentang tampil dgn kolom format rekap
  (TOTAL..SATUAN + hari), lepas centang = keluarkan, kosong = pesan
  arahan, badge MainWindow 'Follow Up (N)'.
- Export: header = kolom rekap + PIC/KATEGORI/PENYEBAB kosong; hari
  tersangka fill merah + font merah tebal; amber fill amber; ✓/__FP
  TIDAK ikut terekspor.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt  # noqa: F401 — dipakai test Qt di bawah

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waste_anomaly.followup import (  # noqa: E402
    CHECK_COL,
    DAY_COLS,
    FP_COL,
    FOLLOWUP_COLS,
    day_cols,
    export_followup_xlsx,
    fingerprint_series,
    load_followup_keys,
    save_followup_keys,
    select_followup_rows,
    suspicious_days,
)


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _data_row_idx(model_df: pd.DataFrame) -> list[int]:
    """v2.19.3 — indeks baris DATA murni (baris pemisah grup __SEP
    dilewati — layout sampel menambah baris kosong antar grup)."""
    if "__SEP" in getattr(model_df, "columns", []):
        return [i for i, v in enumerate(model_df["__SEP"].tolist())
                if v is not True]
    return list(range(len(model_df)))


def _df_fu() -> pd.DataFrame:
    """Fixture 5 baris — kembar identik, kembar beda-nilai, lonjakan.

    Baris 0/1: kembar PERSIS (AYAM, nilai hari sama) → fp sama.
    Baris 2: kunci sama dgn 0/1 tapi nilai hari beda → fp beda.
    Baris 3: BEBEK — HARI TERSANGKA 4, nilai 15 vs AVG AKTIF 7.5
             (2× tepat → amber di hari 2 & 4... 15 == 2×7.5 → amber,
             hari 4 = tersangka → merah menang).
    Baris 4: cuma kolom identitas tanpa hari (guard kolom absen).
    """
    return pd.DataFrame({
        "SOURCE DATA": ["W1", "W1", "W1", "W2", "W3"],
        "JENIS": ["WASTE", "WASTE", "WASTE", "SUSUT", "TRIAL"],
        "KETERANGAN": ["Cancel Nota", "Cancel Nota", "Cancel Nota",
                       "Alat/Mesin", "Over Stock"],
        "NAMA BARANG": ["AYAM", "AYAM", "AYAM", "BEBEK", "CUMI"],
        "NAMA RESTO": ["R1", "R1", "R1", "R2", "R3"],
        "SATUAN": ["PCS", "PCS", "PCS", "KG", "PCS"],
        "TOTAL": [30.0, 30.0, 31.0, 15.0, 0.0],
        "AVG": [30 / 31] * 3 + [15 / 31, 0.0],
        "MAX": [20.0, 20.0, 21.0, 15.0, 0.0],
        "AVG AKTIF": [10.0, 10.0, 10.5, 7.5, 0.0],
        "HARI TERSANGKA": [pd.NA, pd.NA, pd.NA, 4, pd.NA],
        "HARI MAX": [2, 2, 2, 4, pd.NA],
        "1": [10, 10, 10, 0, 0],
        "2": [20, 20, 21, 0, 0],
        "3": [0, 0, 0, 0, 0],
        "4": [0, 0, 0, 15, 0],
    })


# ============================================================
# fingerprint_series — identitas baris stabil
# ============================================================

class TestV2120Fingerprint:
    def test_kembar_identik_menyatu(self):
        fps = fingerprint_series(_df_fu())
        assert fps.iloc[0] == fps.iloc[1]

    def test_kembar_nilai_beda_terbeda(self):
        fps = fingerprint_series(_df_fu())
        assert fps.iloc[0] != fps.iloc[2]  # hari beda → fp beda

    def test_deterministik_dan_dtype_stabil(self):
        df = _df_fu()
        a = fingerprint_series(df)
        b = fingerprint_series(df.copy())
        assert list(a) == list(b)
        # int vs float pada kolom hari → fp SAMA (5 vs 5.0)
        df2 = df.copy()
        df2["1"] = df2["1"].astype(int)
        df3 = df.copy()
        df3["1"] = df3["1"].astype(float)
        assert list(fingerprint_series(df2)) == list(fingerprint_series(df3))

    def test_kolom_absen_tak_crash(self):
        df = _df_fu().drop(columns=["SOURCE DATA", "SATUAN", "2"])
        fps = fingerprint_series(df)
        assert len(fps) == len(df)
        assert fps.notna().all()

    def test_beda_file_sama_nilai(self):
        # dataset 3 hari vs 4 hari: baris dgn hari ke-4 BERNILAI NOL →
        # fp sama (hari kosong tak ikut hash); baris dgn nilai di hari
        # yang hilang (BEBEK 15) → fp berubah (nilai tak ada lagi).
        df = _df_fu()
        df3 = df.drop(columns=["4"])
        a = fingerprint_series(df)
        b = fingerprint_series(df3)
        assert a.iloc[0] == b.iloc[0]  # AYAM: hari 4 = 0
        assert a.iloc[1] == b.iloc[1]
        assert a.iloc[2] == b.iloc[2]
        assert a.iloc[4] == b.iloc[4]  # CUMI: semua hari 0
        assert a.iloc[3] != b.iloc[3]  # BEBEK: 15 di hari 4 hilang


# ============================================================
# select_followup_rows — mask + dedup kembar
# ============================================================

class TestV2120SelectRows:
    def test_mask_dan_dedup(self):
        df = _df_fu()
        fps = fingerprint_series(df)
        keys = [fps.iloc[0], fps.iloc[1], fps.iloc[2]]  # kembar ×2 + beda
        rows = select_followup_rows(df, fps, keys)
        assert len(rows) == 2  # kembar identik menyatu, beda-nilai terpisah
        assert FP_COL in rows.columns
        assert set(rows[FP_COL]) == {fps.iloc[0], fps.iloc[2]}

    def test_key_tak_dikenal_kosong(self):
        df = _df_fu()
        fps = fingerprint_series(df)
        rows = select_followup_rows(df, fps, ["tidak-ada"])
        assert len(rows) == 0


# ============================================================
# suspicious_days — merah (tersangka) + amber (lonjakan)
# ============================================================

class TestV2120SuspiciousDays:
    def test_merah_tersangka_fallback_hari_max(self):
        df = _df_fu()
        fps = fingerprint_series(df)
        red, _amber = suspicious_days(df, fps)
        # baris 3: HARI TERSANGKA 4 → merah
        assert red.get(fps.iloc[3]) == 4
        # baris 0/1: tanpa tersangka → fallback HARI MAX 2
        assert red.get(fps.iloc[0]) == 2

    def test_amber_dua_kali_rata_rata_aktif(self):
        # baris khusus: 6 hari kecil (1×6) + dua puncak (10, 12) →
        # AVG AKTIF 3.5 → ambang 7 → hari 7 (10) amber; hari 8 (12) =
        # tersangka → merah menang; hari 1-6 (1) < ambang.
        df = pd.DataFrame({
            "AVG AKTIF": [3.5], "HARI TERSANGKA": [8], "HARI MAX": [8],
            "1": [1], "2": [1], "3": [1], "4": [1], "5": [1], "6": [1],
            "7": [10], "8": [12],
        })
        fps = fingerprint_series(df)
        red, amber = suspicious_days(df, fps)
        assert red.get(fps.iloc[0]) == 8
        assert (fps.iloc[0], "7") in amber   # 10 ≥ 2×3.5
        assert (fps.iloc[0], "8") not in amber  # merah menang
        for d in ("1", "2", "3", "4", "5", "6"):
            assert (fps.iloc[0], d) not in amber  # 1 < 7

    def test_amber_tidak_menimpa_hari_merah(self):
        df = _df_fu()
        fps = fingerprint_series(df)
        red, amber = suspicious_days(df, fps)
        # baris 3: nilai 15 == 2×7.5 (amber kandidat) TAPI hari 4 merah
        assert red.get(fps.iloc[3]) == 4
        assert (fps.iloc[3], "4") not in amber

    def test_rata_rata_nol_tanpa_amber(self):
        # AVG AKTIF 0 → guard: semua hari bernilai ≥ 0 → TANPA amber
        df = _df_fu()
        fps = fingerprint_series(df)
        _red, amber = suspicious_days(df, fps)
        for fp, _c in amber:
            assert fp != fps.iloc[4]

    def test_tanpa_kolom_hari_kosong(self):
        df = _df_fu().drop(columns=[c for c in DAY_COLS if c in _df_fu().columns])
        fps = fingerprint_series(df)
        red, amber = suspicious_days(df, fps)
        assert red == {} and amber == set()


# ============================================================
# Persistensi followup.json
# ============================================================

class TestV2120Persistence:
    def test_roundtrip_urutan_dipelihara(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fu.json"
            assert save_followup_keys(["b", "a", "c"], p)
            assert load_followup_keys(p) == ["b", "a", "c"]
            assert not p.with_suffix(p.suffix + ".tmp").exists()  # atomic

    def test_file_absen_kosong(self):
        with tempfile.TemporaryDirectory() as td:
            assert load_followup_keys(Path(td) / "nggak-ada.json") == []

    def test_korup_backup_bad_lalu_kosong(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fu.json"
            p.write_text("{bukan json", encoding="utf-8")
            assert load_followup_keys(p) == []
            assert p.with_suffix(p.suffix + ".bad").exists()
            assert not p.exists()  # di-rename, bukan ditimpa

    def test_list_kotor_dibersihkan(self):
        # entri kosong/None dibuang; non-list → korup → kosong
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fu.json"
            p.write_text('{"rows": ["a", "", null, "b"]}', encoding="utf-8")
            assert load_followup_keys(p) == ["a", "b"]
            p.write_text('{"rows": "bukan-list"}', encoding="utf-8")
            assert load_followup_keys(p) == []


# ============================================================
# AppContext — state follow-up
# ============================================================

class TestV2120ContextFollowup:
    def _ctx(self, path=None):
        _qapp()
        from ui.state import AppContext
        return AppContext({}, followup_path=path)

    def test_toggle_noop_tanpa_broadcast(self):
        with tempfile.TemporaryDirectory() as td:
            ctx = self._ctx(str(Path(td) / "f.json"))
            ctx.set_dataset(_df_fu(), {"key_akhir": 31})
            n = {"emit": 0}
            ctx.followup_changed.connect(
                lambda: n.__setitem__("emit", n["emit"] + 1))
            fps = fingerprint_series(_df_fu())
            assert ctx.toggle_followup(str(fps.iloc[0]), True)
            assert n["emit"] == 1
            assert not ctx.toggle_followup(str(fps.iloc[0]), True)  # no-op
            assert n["emit"] == 1  # tanpa broadcast sia-sia
            # lepas centang = perubahan NYATA (bukan no-op)
            assert ctx.toggle_followup(str(fps.iloc[0]), False)
            assert n["emit"] == 2
            assert len(ctx.followup_keys) == 0

    def test_add_many_satu_broadcast_duplikat_nol(self):
        ctx = self._ctx()
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        fps = fingerprint_series(_df_fu())
        n = {"emit": 0}
        ctx.followup_changed.connect(
            lambda: n.__setitem__("emit", n["emit"] + 1))
        added = ctx.add_followup_many([fps.iloc[0], fps.iloc[0], fps.iloc[3]])
        assert added == 2  # duplikat dihitung 0
        assert n["emit"] == 1  # SATU broadcast
        assert len(ctx.followup_keys) == 2
        assert ctx.add_followup_many([fps.iloc[0]]) == 0
        assert n["emit"] == 1

    def test_clear(self):
        ctx = self._ctx()
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
        assert ctx.clear_followup() == 2
        assert ctx.clear_followup() == 0
        assert ctx.followup_keys == []

    def test_followup_df_dedup_dataset_penuh(self):
        ctx = self._ctx()
        df = _df_fu()
        ctx.set_dataset(df, {"key_akhir": 31})
        fps = fingerprint_series(df)
        ctx.add_followup_many([fps.iloc[0], fps.iloc[1], fps.iloc[3]])
        out = ctx.followup_df()
        assert len(out) == 2  # kembar dedup + BEBEK
        # dataset PENUH — baris tanpa ANOMALY STATUS ikut (shortlist menetap)
        assert "NAMA BARANG" in out.columns

    def test_followup_df_none_tanpa_dataset_kosong_tanpa_key(self):
        ctx = self._ctx()
        assert ctx.followup_df() is None
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        assert ctx.followup_df() is not None
        assert len(ctx.followup_df()) == 0

    def test_persist_termuat_saat_konstruksi(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.json"
            save_followup_keys(["x", "y"], p)
            ctx = self._ctx(str(p))
            assert ctx.followup_keys == ["x", "y"]

    def test_toggle_tanpa_path_tak_nulis_disk(self):
        ctx = self._ctx()  # followup_path None (mode test)
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        fps = fingerprint_series(_df_fu())
        ctx.toggle_followup(str(fps.iloc[0]), True)
        assert not Path("followup.json").exists()  # repo tak terkontaminasi

    def test_prune_data_baru(self):
        ctx = self._ctx()
        df = _df_fu()
        ctx.set_dataset(df, {"key_akhir": 31})
        fps = fingerprint_series(df)
        ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
        # data baru: nilai hari baris 3 berubah → fp barunya beda → terpangkas
        df2 = df.copy()
        df2.iloc[3, df2.columns.get_loc("1")] = 99
        ctx.set_dataset(df2, {"key_akhir": 31})
        assert ctx.prune_followup() == 1
        assert len(ctx.followup_keys) == 1
        assert ctx.prune_followup() == 0  # idempoten

    def test_memo_fingerprint_per_data_version(self):
        ctx = self._ctx()
        df = _df_fu()
        ctx.set_dataset(df, {"key_akhir": 31})
        s1 = ctx.fingerprints()
        s2 = ctx.fingerprints()
        assert s1 is s2  # memo — objek sama
        ctx.set_dataset(df.copy(), {"key_akhir": 31})
        assert ctx.fingerprints() is not s1  # version baru → hitung ulang


# ============================================================
# PandasTableModel — kolom ✓ + penanda warna
# ============================================================

class TestV2120ModelCheck:
    def _model(self, df=None):
        _qapp()
        from ui.models import PandasTableModel
        m = PandasTableModel()
        m.set_check_column(CHECK_COL)
        m.set_row_key_column(FP_COL)
        disp = (df if df is not None else _df_fu()).copy()
        fps = fingerprint_series(_df_fu())
        disp[FP_COL] = fps
        disp.insert(0, CHECK_COL, [False] * len(disp))
        m.set_dataframe(disp)
        return m

    def test_flags_hanya_kolom_centang(self):
        from PySide6.QtCore import Qt
        m = self._model()
        assert bool(m.flags(m.index(0, 0)) & Qt.ItemFlag.ItemIsUserCheckable)
        assert not (m.flags(m.index(0, 1)) & Qt.ItemFlag.ItemIsUserCheckable)

    def test_checkstate_dan_display_kosong(self):
        from PySide6.QtCore import Qt
        m = self._model()
        assert m.data(m.index(0, 0), Qt.ItemDataRole.CheckStateRole) \
            == Qt.CheckState.Unchecked
        m.dataframe.iat[0, 0] = True
        assert m.data(m.index(0, 0), Qt.ItemDataRole.CheckStateRole) \
            == Qt.CheckState.Checked
        assert m.data(m.index(0, 0), Qt.DisplayRole) == ""  # bukan 'True'

    def test_setdata_enum_dan_int(self):
        from PySide6.QtCore import Qt
        m = self._model()
        seen: list[tuple[int, bool]] = []
        m.check_toggled.connect(lambda r, c: seen.append((r, c)))
        # jalur PySide6 enum (delegate modern)
        assert m.setData(m.index(1, 0), Qt.CheckState.Checked,
                         Qt.ItemDataRole.CheckStateRole)
        # jalur int 2 (QVariant/Qt lama)
        assert m.setData(m.index(2, 0), 2, Qt.ItemDataRole.CheckStateRole)
        # uncheck via enum
        assert m.setData(m.index(1, 0), Qt.CheckState.Unchecked,
                         Qt.ItemDataRole.CheckStateRole)
        assert seen == [(1, True), (2, True), (1, False)]
        assert bool(m.dataframe.iloc[1][CHECK_COL]) is False
        assert bool(m.dataframe.iloc[2][CHECK_COL]) is True

    def test_setdata_kolom_lain_ditolak(self):
        from PySide6.QtCore import Qt
        m = self._model()
        assert not m.setData(m.index(0, 1), 2, Qt.ItemDataRole.CheckStateRole)

    def test_sort_kolom_centang_jalan(self):
        m = self._model()
        m.dataframe.iat[0, 0] = True
        m.sort(0, Qt.DescendingOrder)
        assert bool(m.dataframe.iloc[0][CHECK_COL]) is True  # True di atas

    def test_penanda_stabil_lewat_sort(self):
        from PySide6.QtGui import QColor
        m = self._model()
        df = m.dataframe
        # pakai baris ber-fp UNIK (BEBEK — kembar 0/1 berbagi fp).
        fp_be = str(df.iloc[3][FP_COL])
        m.set_highlights(red={(fp_be, "4")}, amber=set())
        # sebelum sort: baris 3 sel '4' merah
        bg = m.data(m.index(3, df.columns.get_loc("4")),
                    Qt.ItemDataRole.BackgroundRole)
        assert bg == QColor("#fee2e2")
        # sort berdasarkan hari '2' ASC (BEBEK '2'=0 → pindah ke atas;
        # AYAM 20/21 di bawah) — penanda HARUS ikut barisnya, bukan
        # posisi lama.
        m.sort(df.columns.get_loc("2"), Qt.AscendingOrder)
        hits = [r for r in range(len(m.dataframe))
                if str(m.dataframe.iloc[r][FP_COL]) == fp_be]
        assert len(hits) == 1
        bg2 = m.data(m.index(hits[0], m.dataframe.columns.get_loc("4")),
                     Qt.ItemDataRole.BackgroundRole)
        assert bg2 == QColor("#fee2e2")
        # kolom lain tak berwarna
        bg3 = m.data(m.index(hits[0], m.dataframe.columns.get_loc("1")),
                     Qt.ItemDataRole.BackgroundRole)
        assert bg3 != QColor("#fee2e2")

    def test_notify_column_changed(self):
        m = self._model()
        got: list[tuple[int, int]] = []
        m.dataChanged.connect(lambda a, b: got.append((a.row(), b.row())))
        m.notify_column_changed(CHECK_COL)
        assert got and got[0] == (0, len(m.dataframe) - 1)
        got.clear()
        m.notify_column_changed("kolom-tak-ada")
        assert got == []


# ============================================================
# AnomaliView — ✓ + tombol massal + sinkron in-place
# ============================================================

class TestV2120AnomaliView:
    def _view(self, ctx=None):
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        ctx = ctx or AppContext({})
        view = AnomaliView(ctx)
        return ctx, view

    def test_klik_mouse_centang(self):
        # v2.19.0 — tampilan GRUP: klik ✓ grup = masukkan SEMUA anggota.
        # Fixture _df_fu (5 baris) → 3 grup setelah grouping:
        #   grup-0 AYAM·R1·WASTE (3 anggota: rows 0,1,2; fp unik = 2 krn
        #     rows 0/1 kembar identik);
        #   grup-1 BEBEK·R2·SUSUT (1 anggota: row 3);
        #   grup-2 CUMI·R3·TRIAL  (1 anggota: row 4).
        # Klik grup-1 (1 anggota) → 1 fp masuk follow-up (mirip semantik
        # lama); klik grup-0 → 2 fp (kembar menyatu).
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        from ui.grouping import FPS_COL
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        m = view._table.model()
        assert m.dataframe.columns[0] == CHECK_COL
        assert FPS_COL in m.dataframe.columns  # v2.19.0: grup → __FPS
        # grup-1 = BEBEK (1 anggota) → klik = 1 fp masuk follow-up
        # v2.19.3 — urutan default = GRUP (JENIS alfabetis: BEBEK(SUSUT)
        # di depan, CUMI, AYAM) + pemisah antar grup — cari baris grup
        # by NAMA BARANG (bukan posisi lama).
        bebek_row = next(
            i for i, v in enumerate(m.dataframe["NAMA BARANG"].tolist())
            if v == "BEBEK")
        rect = view._table.visualRect(m.index(bebek_row, 0))
        QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(rect.x() + 8, rect.y() + rect.height() // 2))
        _qapp().processEvents()
        assert len(ctx.followup_keys) == 1
        assert bool(m.dataframe.iloc[bebek_row][CHECK_COL]) is True
        # uncheck klik ulang
        QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(rect.x() + 8, rect.y() + rect.height() // 2))
        _qapp().processEvents()
        assert ctx.followup_keys == []
        view.close()

    def test_tombol_centang_semua_yang_tampil(self):
        # v2.19.0 — tampilan GRUP: 'Centang yang tampil' = masukkan SEMUA
        # anggota SEMUA grup yang tampil (SATU broadcast). Fixture _df_fu
        # 5 baris → 3 grup (AYAM 3-anggota/2-fp-unik + BEBEK + CUMI) →
        # 4 fp unik total (kembar identik AYAM 0/1 menyatu).
        from ui.grouping import FPS_COL
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        view._btn_fu_all.click()
        _qapp().processEvents()
        # kembar identik → fp sama → 4 fp unik (0/1 menyatu)
        assert len(ctx.followup_keys) == 4
        # klik ulang = 0 baru (idempoten) — kumpulkan SEMUA fp anggota grup
        all_fps: list[str] = []
        for fps in view._table.model().dataframe[FPS_COL]:
            if isinstance(fps, tuple):
                all_fps.extend(str(f) for f in fps)
        assert ctx.add_followup_many(all_fps) == 0
        view.close()

    def test_sinkron_inplace_bukan_reset(self):
        """Perubahan dari luar (mis. bulk) → kolom ✓ diperbarui TANPA
        reset model (objek df model tetap — cache fit tak tersentuh).
        v2.19.0 — tampilan GRUP: ✓ grup = ADA anggota tercentang.
        fps.iloc[0] = AYAM row-0 (grup-0 → ✓ True); fps.iloc[3] = BEBEK
        (grup-1 → ✓ True). Grup-2 (CUMI) tak terkena → ✓ False.
        v2.19.3 — tabel kini ber-PEMISAH grup (baris __SEP): indeks posisi
        data diambil lewat _data_row_idx (baris pemisah dilewati)."""
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        m = view._table.model()
        df_obj = m.dataframe
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
        _qapp().processEvents()
        assert m.dataframe is df_obj  # TAK di-reset
        # v2.19.3 — urutan default = GRUP (JENIS alfabetis: BEBEK, CUMI,
        # AYAM) — cek ✓ per NAMA BARANG (bukan posisi lama AYAM/BEBEK/CUMI).
        for nama, expected in (("AYAM", True), ("BEBEK", True),
                               ("CUMI", False)):
            row = next(
                i for i, v in enumerate(m.dataframe["NAMA BARANG"].tolist())
                if v == nama)
            assert bool(m.dataframe.iloc[row][CHECK_COL]) is expected, (
                f"✓ grup {nama} harus {expected}")
        view.close()

    def test_display_memo_objek_stabil(self):
        """Refresh ulang dgn objek df sumber sama → objek display sama
        (cache fit DataTable tetap kena — kontrak anti-lemot v2.9.0)."""
        ctx, view = self._view()
        view.show()
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        view.refresh()
        _qapp().processEvents()
        d1 = view._table.model().dataframe
        view.refresh()
        _qapp().processEvents()
        d2 = view._table.model().dataframe
        assert d1 is d2
        view.close()


# ============================================================
# FollowUpView — tabel rekap + lepas centang
# ============================================================

class TestV2120FollowUpView:
    def _views(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_followup import FollowUpView
        ctx = AppContext({})
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        return ctx, AnomaliView(ctx), FollowUpView(ctx)

    def test_baris_tercentang_tampil_format_rekap(self):
        ctx, av, fv = self._views()
        av.show()
        av.refresh()
        _qapp().processEvents()
        view_fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([view_fps.iloc[0], view_fps.iloc[3]])
        _qapp().processEvents()
        fv.show()
        fv.refresh()
        _qapp().processEvents()
        m = fv._table.model()
        assert m.rowCount() == 2  # kembar menyatu + BEBEK
        cols = list(m.dataframe.columns)
        assert cols[0] == CHECK_COL
        # urutan format rekap PERSIS permintaan user: ✓ + 9 kolom inti
        expected_head = [CHECK_COL] + FOLLOWUP_COLS
        visible = [c for c in cols
                   if c in set(expected_head) | set(day_cols(m.dataframe))]
        assert visible[:len(expected_head)] == expected_head
        assert "4" in cols  # kolom hari ikut
        assert "AYAM" in set(m.dataframe["NAMA BARANG"])
        av.close()
        fv.close()

    def test_lepas_centang_keluarkan_baris(self):
        ctx, av, fv = self._views()
        av.show(); av.refresh(); _qapp().processEvents()
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
        _qapp().processEvents()
        fv.show(); fv.refresh(); _qapp().processEvents()
        m = fv._table.model()
        assert m.rowCount() == 2
        m.setData(m.index(0, 0), 0, Qt.ItemDataRole.CheckStateRole)  # uncheck
        _qapp().processEvents()
        fv.refresh()
        assert m.rowCount() == 1
        assert ctx.followup_keys == [str(fps.iloc[3])]
        av.close(); fv.close()

    def test_popup_basi_ditutup_saat_baris_keluar(self):
        """Bug-hunt 3-a: pop-up detail terbuka → barisnya keluar daftar
        (lepas centang) → refresh WAJIB menutup pop-up (pola V26-L12 —
        tanpa ini pop-up menampilkan baris yang sudah tak ada)."""
        from PySide6.QtCore import QItemSelectionModel
        ctx, av, fv = self._views()
        av.show(); av.refresh(); _qapp().processEvents()
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
        _qapp().processEvents()
        fv.show(); fv.refresh(); _qapp().processEvents()
        m = fv._table.model()
        # v2.18.6: pop-up dibuka lewat KLIK-GANDA (klik 1× tak lagi
        # membuka pop-up — permintaan user); pilih + emit double_clicked.
        fv._table.selectionModel().setCurrentIndex(
            m.index(0, 1),
            QItemSelectionModel.SelectionFlag.SelectCurrent)
        fv._table.double_clicked.emit(m.record(0))
        _qapp().processEvents()
        assert fv._popup.isVisible()
        # lepas centang baris yang sedang ditampilkan pop-up → refresh →
        # pop-up basi harus TERTUTUP
        m.setData(m.index(0, 0), 0, Qt.ItemDataRole.CheckStateRole)
        _qapp().processEvents()
        assert not fv._popup.isVisible()
        av.close(); fv.close()

    def test_kosong_pesan_arahan(self):
        ctx, av, fv = self._views()
        fv.show(); fv.refresh()
        assert fv._table.model().rowCount() == 0
        assert "centang" in fv._lbl_info.text().lower()
        assert not fv._btn_export.isEnabled()
        av.close(); fv.close()


# ============================================================
# Export Excel
# ============================================================

class TestV2120Export:
    def test_header_fill_dan_kolom_serah_terima(self):
        # baris khusus: hari 8 tersangka (merah), hari 7 = 10 ≥ 2×3.5 (amber)
        df = pd.DataFrame({
            "SOURCE DATA": ["W1"], "JENIS": ["WASTE"], "KETERANGAN": ["K"],
            "NAMA BARANG": ["SPIKE"], "NAMA RESTO": ["R9"], "SATUAN": ["PCS"],
            "TOTAL": [28.0], "AVG": [28 / 31], "MAX": [12.0],
            "AVG AKTIF": [3.5], "HARI TERSANGKA": [8], "HARI MAX": [8],
            "1": [1], "2": [1], "3": [1], "4": [1], "5": [1], "6": [1],
            "7": [10], "8": [12],
        })
        fps = fingerprint_series(df)
        rows = select_followup_rows(df, fps, [fps.iloc[0]])
        red, amber = suspicious_days(rows, rows[FP_COL])
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "fu.xlsx")
            export_followup_xlsx(rows, path, red, amber)
            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb["FOLLOW UP"]
            header = [c.value for c in ws[1]]
            # format rekap + hari + kolom serah terima kosong
            for c in FOLLOWUP_COLS:
                assert c in header
            for c in day_cols(df):
                assert c in header
            for c in ("PIC", "KATEGORI", "PENYEBAB TERJADINYA WASTE"):
                assert c in header
            assert CHECK_COL not in header and FP_COL not in header
            # kolom serah terima kosong
            pic_i = header.index("PIC") + 1
            assert ws.cell(row=2, column=pic_i).value is None
            # hari tersangka (8) → fill merah + font tebal merah
            c8 = ws.cell(row=2, column=header.index("8") + 1)
            assert c8.fill.start_color.rgb.endswith("FEE2E2")
            assert c8.font.bold and c8.font.color.rgb.endswith("DC2626")
            # hari 7 (10 ≥ 2×3.5) → amber
            c7 = ws.cell(row=2, column=header.index("7") + 1)
            assert c7.fill.start_color.rgb.endswith("FEF3C7")
            # hari kecil (1) tanpa fill
            c1 = ws.cell(row=2, column=header.index("1") + 1)
            assert not (c1.fill.patternType == "solid")
            # Bug-hunt 3-a: kolom hari int64 (fixture ini) HARUS terekspor
            # NUMERIK — np.int64 bukan subclass int python; tanpa fix,
            # 16/31 kolom hari data asli menjadi teks (SUM/sort Excel rusak)
            for c in ("1", "7", "8"):
                assert ws.cell(row=2, column=header.index(c) + 1).data_type == "n"
            assert ws.cell(
                row=2, column=header.index("TOTAL") + 1).data_type == "n"
            # freeze + autofilter
            assert ws.freeze_panes == "A2"
            assert ws.auto_filter.ref


# ============================================================
# MainWindow — badge tab + bantuan jujur
# ============================================================

class TestV2120MainWindow:
    def test_badge_followup(self):
        _qapp()
        import ui.app as ap
        from ui.app import MainWindow
        # Isolasi disk: arahkan followup.json ke tmp (MainWindow memuat +
        # MENULIS file ini — tanpa ini test mengotori repo).
        with tempfile.TemporaryDirectory() as td:
            saved = ap.followup_path
            ap.followup_path = lambda: Path(td) / "followup.json"
            try:
                win = MainWindow()
                try:
                    idx = win._tabs.indexOf(win._fu_view)
                    # v2.17.0: Follow Up terakhir; v2.18.5: index 4
                    # (tab Scorecard Cabang dihapus — 6 → 5 tab).
                    assert idx == 4
                    assert win._tabs.tabText(idx) == "Follow Up"
                    fps = fingerprint_series(_df_fu())
                    win.ctx.set_dataset(_df_fu(), {"key_akhir": 31})
                    win.ctx.add_followup_many([fps.iloc[0], fps.iloc[3]])
                    _qapp().processEvents()
                    assert win._tabs.tabText(idx) == "Follow Up (2)"
                    win.ctx.clear_followup()
                    _qapp().processEvents()
                    assert win._tabs.tabText(idx) == "Follow Up"
                    # ikut urutan iterasi closeEvent (kontrak _views)
                    names = [n for n, _v in win._views]
                    # v2.18.5: 6 → 5 tab (Scorecard Cabang dihapus)
                    assert "Follow Up" in names and len(names) == 5
                finally:
                    win.close()
            finally:
                ap.followup_path = saved
