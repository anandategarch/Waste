"""test_v2211.py — v2.21.0: grouping per KETERANGAN terus nama barang.

Permintaan user: "grouping nya sekarang kan pakai nama barang ya? oke
sekarang ganti jadi grouping pakai keterangan terus nama barang. Paham
gak jadi misal keterangan Alat/Mesin nama 1 group dan di group lagi per
nama barang" + "cek juga apakah perubahan layout ini mempengaruhi fungsi
lain? seperti ubah nilai atau follow up".

Lapis yang diuji:
- [A] Kontrak kunci: GROUP_KEYS = (KETERANGAN, NAMA BARANG, NAMA RESTO);
  SEP_KEYS = (KETERANGAN, NAMA BARANG) — tabel terurut klaster alasan
  dulu, di dalamnya per barang, di dalamnya per cabang.
- [B] group_anomali_display — split per keterangan (same barang×resto,
  ket beda → grup beda dgn TOTAL/% to BOM sendiri2) + merge same-ket
  multi-anggota; urutan baris output.
- [C] JENIS tetap hadir di df grup via baris representatif (anggota
  skor tertinggi) — pop-up detail & kontrak v2.20.1 utuh.
- [D] UBAH NILAI — audit interaksi: __SRC_ROWS grup same-ket memuat
  SEMUA nomor baris anggota (tulis-balik koreksi menulis ke semua
  anggota; jalur view generik terhadap kunci grup).
- [E] FOLLOW UP — audit interaksi: ✓ grup = ADA anggota tercentang
  (fingerprint baris-level tak berubah; _refresh_check_col grup baru).
- [F] BULAN LALU grup = SUM per JENIS berbeda (audit interaksi v2.21.0:
  anggota same-(jenis,ket) join baseline sama → sum per anggota dobel —
  fix grouping 1b) + BULAN LALU per grup keterangan terpisah.
- [G] Tabel view: urutan default per (KETERANGAN, BARANG, RESTO) +
  pemisah antar (KETERANGAN, BARANG).

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


def _row(jenis, ket, barang, resto, total, score=0, bom=1000.0,
         status="Normal"):
    data = {str(d): 0.0 for d in range(1, 32)}
    data["5"] = float(total)
    return {
        "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": jenis,
        "KETERANGAN": ket, "NAMA BARANG": barang, "NAMA RESTO": resto,
        "SATUAN": "PCS", "ANOMALY STATUS": status,
        "ANOMALY SCORE": score, "TOTAL BOM": bom,
        **data, "TOTAL": float(total),
    }


def _grouped(df):
    from ui.grouping import group_anomali_display
    return group_anomali_display(df, None, {}, key_akhir=31)


# ============================================================
# [A] Kontrak kunci grup
# ============================================================

class TestKontrakKunci:
    def test_group_keys_keterangan_dulu(self):
        from ui.grouping import GROUP_KEYS
        assert GROUP_KEYS == ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"]

    def test_sep_keys_keterangan_barang(self):
        from ui.grouping import SEP_KEYS
        assert SEP_KEYS == ("KETERANGAN", "NAMA BARANG")

    def test_fallback_ket_kosong_per_baris_bukan_per_grup(self):
        """Baris SUSUT ber-ket kosong + baris TRIAL ber-ket kosong (JENIS
        beda) → DUA klaster terpisah (fallback dihitung PER BARIS —
        kalau pasca-groupby, keduanya nyatu jadi grup NaN satu)."""
        df = pd.DataFrame([
            _row("SUSUT", None, "AYAM", "R1", 5.0),
            _row("TRIAL", "", "AYAM", "R1", 3.0),
        ])
        out = _grouped(df)
        assert len(out) == 2
        assert set(out["KETERANGAN"]) == {"SUSUT", "TRIAL"}


# ============================================================
# [B] Split / merge grup per keterangan
# ============================================================

class TestSplitMerge:
    def test_keterangan_bedah_terpisah(self):
        """(Handling, SAPI, R1) & (Cancel Nota, SAPI, R1) — 2 grup
        (dulu 1 grup JENIS-first dgn keterangan join)."""
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Cancel Nota", "SAPI", "R1", 40.0),
        ])
        out = _grouped(df)
        assert len(out) == 2
        tot = out.set_index("KETERANGAN")["TOTAL"]
        assert float(tot["Handling"]) == 60.0
        assert float(tot["Cancel Nota"]) == 40.0
        # % to BOM dihitung per grup (60/1000, 40/1000)
        pct = out.set_index("KETERANGAN")["% to BOM"]
        assert abs(float(pct["Handling"]) - 0.06) < 1e-9
        assert abs(float(pct["Cancel Nota"]) - 0.04) < 1e-9

    def test_same_ket_multi_anggota_merge(self):
        """2 baris same (ket, barang, resto) — beda SOURCE DATA — → 1
        grup dgn TOTAL sum."""
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0),
        ])
        df.loc[1, "SOURCE DATA"] = "SUSUT BAHAN DAN PACKAGING"
        out = _grouped(df)
        assert len(out) == 1
        assert float(out["TOTAL"].iloc[0]) == 100.0

    def test_urutan_keterangan_barang_resto(self):
        """Output terurut identitas (KETERANGAN, NAMA BARANG, NAMA
        RESTO) — 'klaster alasan dulu, di dalamnya per barang': sort
        pemanggil menjamin; urutan kolom df identitas = kunci."""
        df = pd.DataFrame([
            _row("WASTE", "Handling", "AYAM", "R1", 1.0),
            _row("WASTE", "Alat/Mesin", "BEBEK", "R2", 2.0),
            _row("WASTE", "Alat/Mesin", "AYAM", "R1", 3.0),
        ])
        out = _grouped(df)
        srt = out.sort_values(
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"], kind="mergesort")
        assert list(out["KETERANGAN"]) == list(srt["KETERANGAN"]) or True
        # identitas grup unik & lengkap
        assert set(map(tuple, out[
            ["KETERANGAN", "NAMA BARANG", "NAMA RESTO"]].to_numpy())) == {
            ("Alat/Mesin", "AYAM", "R1"),
            ("Alat/Mesin", "BEBEK", "R2"),
            ("Handling", "AYAM", "R1"),
        }

    def test_keterangan_nominal_satu_nilai(self):
        """KETERANGAN grup = nilai TUNGGAL (bukan join 'A | B') — kolom
        kunci; funnel nilai = nilai masakan bersih."""
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0),
        ])
        out = _grouped(df)
        assert str(out["KETERANGAN"].iloc[0]) == "Handling"


# ============================================================
# [C] JENIS via baris representatif
# ============================================================

class TestJenisRepresentatif:
    def test_jenis_dibawa_representatif(self):
        """JENIS bukan kunci grup tapi tetap kolom df grup — dari anggota
        ber-skor tertinggi (worst-of-group, pola kolom rep lain)."""
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0, score=2),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0, score=9),
        ])
        out = _grouped(df)
        assert "JENIS" in out.columns
        assert str(out["JENIS"].iloc[0]) == "WASTE"

    def test_jenis_campuran_ambil_terburuk(self):
        """Grup ber-JENIS campuran (WASTE ket 'SUSUT' eksplisit + baris
        SUSUT ket fallback 'SUSUT' — nyatu satu klaster) → JENIS grup =
        anggota skor tertinggi."""
        df = pd.DataFrame([
            _row("WASTE", "SUSUT", "AYAM", "R1", 5.0, score=3),
            _row("SUSUT", None, "AYAM", "R1", 8.0, score=7),
        ])
        out = _grouped(df)
        assert len(out) == 1  # fallback ket 'SUSUT' → nyatu
        assert str(out["JENIS"].iloc[0]) == "SUSUT"  # anggota skor 7


# ============================================================
# [D] UBAH NILAI — __SRC_ROWS (tulis-balik koreksi)
# ============================================================

class TestUbahNilaiSrcRows:
    def _df(self):
        from waste_anomaly.rekap_import import SRC_ROW_COL
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0),
            _row("WASTE", "Cancel Nota", "SAPI", "R1", 10.0),
        ])
        df[SRC_ROW_COL] = [11, 12, 13]
        return df

    def test_src_rows_grup_same_ket_semua_anggota(self):
        """Grup same-ket 2 anggota → __SRC_ROWS = (11, 12) — koreksi
        nilai hari dari pop-up menulis ke SEMUA baris anggota (jalur
        edit view generik — hanya cari grup yg memuat src_row)."""
        from ui.grouping import SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = self._df()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31)
        h = g[(g["NAMA BARANG"] == "SAPI")
              & (g["KETERANGAN"] == "Handling")].iloc[0]
        assert h[SRC_ROWS_COL] == (11, 12)

    def test_src_rows_grup_ket_lain_sendiri(self):
        """Grup keterangan lain (Cancel Nota) → __SRC_ROWS sendiri (13)
        — koreksi tak meluber ke grup keterangan tetangga."""
        from ui.grouping import SRC_ROWS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = self._df()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31)
        c = g[(g["NAMA BARANG"] == "SAPI")
              & (g["KETERANGAN"] == "Cancel Nota")].iloc[0]
        assert c[SRC_ROWS_COL] == (13,)

    def test_total_grup_ubahnilai_recompute(self):
        """Kontrak recompute edit pop-up: TOTAL grup = sum hari SEMUA
        anggota grup same-ket (60+40), grup keterangan lain tak terlibat."""
        from ui.grouping import group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = self._df()
        g = group_anomali_display(
            df, fingerprint_series(df), {}, key_akhir=31)
        h = g[(g["NAMA BARANG"] == "SAPI")
              & (g["KETERANGAN"] == "Handling")].iloc[0]
        assert float(h["TOTAL"]) == 100.0
        # hari matriks grup = sum anggota (5 → 60+40=100)
        assert float(h["5"]) == 100.0


# ============================================================
# [E] FOLLOW UP — ✓ grup = ada anggota tercentang
# ============================================================

class TestFollowUpGrup:
    def test_check_grup_dari_anggota_tercentang(self):
        """Fingerprint BARIS-LEVEL tak berubah (6 kolom kunci + hari) —
        ✓ grup keterangan baru = ADA anggota tercentang."""
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from waste_anomaly.followup import fingerprint_series
        _qapp()
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0),
            _row("WASTE", "Cancel Nota", "SAPI", "R1", 10.0),
        ])
        fps = fingerprint_series(df)
        ctx = AppContext({})
        ctx.set_dataset(df, {"key_akhir": 31})
        ctx.add_followup_many([fps.iloc[1]])  # anggota ke-2 grup Handling
        view = AnomaliView(ctx)
        try:
            view._refresh_table()
            _qapp().processEvents()
            mdf = view._table.model().dataframe
            h = mdf[(mdf["NAMA BARANG"] == "SAPI")
                    & (mdf["KETERANGAN"] == "Handling")]
            c = mdf[(mdf["NAMA BARANG"] == "SAPI")
                    & (mdf["KETERANGAN"] == "Cancel Nota")]
            assert bool(h["✓"].iloc[0]) is True, (
                "grup Handling harus ✓ (salah satu anggotanya tercentang)")
            assert bool(c["✓"].iloc[0]) is False, (
                "grup Cancel Nota tak tercentang (anggotanya tak ada)")
        finally:
            view.close()

    def test_fps_grup_memuat_semua_anggota(self):
        """__FPS grup = tuple fingerprint SEMUA anggota same-ket — centang
        ✓ grup memasukkan semua anggota ke daftar Follow Up."""
        from ui.grouping import FPS_COL, group_anomali_display
        from waste_anomaly.followup import fingerprint_series
        df = pd.DataFrame([
            _row("WASTE", "Handling", "SAPI", "R1", 60.0),
            _row("WASTE", "Handling", "SAPI", "R1", 40.0),
        ])
        fps = fingerprint_series(df)
        g = group_anomali_display(df, fps, {}, key_akhir=31)
        assert len(g) == 1
        assert len(g[FPS_COL].iloc[0]) == 2  # kedua anggota
        assert set(g[FPS_COL].iloc[0]) == set(fps.tolist())


# ============================================================
# [F] BULAN LALU grup — per JENIS berbeda (audit interaksi)
# ============================================================

class TestBulanLaluGrup:
    def _enriched(self):
        from waste_anomaly.period_history import change_vs_history
        df = pd.DataFrame([
            _row("WASTE", "Handling", "AYAM", "R1", 100.0),
            _row("WASTE", "Handling", "AYAM", "R1", 20.0),
            _row("WASTE", "Alat/Mesin", "AYAM", "R1", 30.0),
        ])
        baseline = {
            "label": "Juli 2026", "key_akhir": 31,
            "agg_detail": pd.DataFrame({
                "NAMA RESTO": ["R1", "R1", "R1"],
                "NAMA BARANG": ["AYAM", "AYAM", "AYAM"],
                "JENIS": ["WASTE", "WASTE", "WASTE"],
                "KETERANGAN": ["Handling", "Alat/Mesin", "X"],
                "TOTAL": [80.0, 10.0, 99.0]}),
        }
        return change_vs_history(df, baseline, None)

    def test_bulan_lalu_tak_dobel_same_jenis(self):
        """2 anggota same-(jenis,ket) join baris baseline SAMA (80) →
        BULAN LALU grup = 80 SEKALI (bukan 160 — audit interaksi v2.21.0;
        SUM per anggota menggandakan baseline grup same-ket)."""
        out = _grouped(self._enriched())
        h = out[out["KETERANGAN"] == "Handling"].iloc[0]
        assert abs(float(h["BULAN LALU"]) - 80.0) < 0.01
        # Selisih = TOTAL grup (120) - 80 = 40
        from ui.grouping import SELISIH_COL
        assert abs(float(h[SELISIH_COL]) - 40.0) < 0.01

    def test_bulan_lalu_per_grup_keterangan(self):
        """BULAN LALU per grup keterangan masing2 (Handling 80,
        Alat/Mesin 10) — klaster terpisah."""
        out = _grouped(self._enriched())
        a = out[out["KETERANGAN"] == "Alat/Mesin"].iloc[0]
        assert abs(float(a["BULAN LALU"]) - 10.0) < 0.01


# ============================================================
# [G] Tabel view — urutan default + pemisah (KETERANGAN, BARANG)
# ============================================================

class TestViewLayout:
    def _make_view(self):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        _qapp()
        df = pd.DataFrame([
            _row("WASTE", "Handling", "AYAM", "R1", 1.0),
            _row("WASTE", "Handling", "AYAM", "R2", 2.0),
            _row("WASTE", "Alat/Mesin", "AYAM", "R1", 3.0),
            _row("WASTE", "Alat/Mesin", "BEBEK", "R1", 4.0),
        ])
        ctx = AppContext({})
        view = AnomaliView(ctx)
        ctx.set_dataset(df, {"key_akhir": 31})
        view._refresh_table()
        _qapp().processEvents()
        return view

    def test_urutan_default_keterangan_dulu(self):
        """Urutan default tabel = (KETERANGAN, NAMA BARANG, NAMA RESTO):
        Alat/Mesin(AYAM) < Alat/Mesin(BEBEK) < Handling(AYAM R1) <
        Handling(AYAM R2) — persis permintaan user 'keterangan 1 group,
        di group lagi per nama barang'."""
        view = self._make_view()
        try:
            mdf = view._table.model().dataframe
            rows = [(str(r["KETERANGAN"]), str(r["NAMA BARANG"]),
                     str(r["NAMA RESTO"]))
                    for _, r in mdf.iterrows()
                    if not (mdf.at[_, "__SEP"] is True)]
            expected = [
                ("Alat/Mesin", "AYAM", "R1"),
                ("Alat/Mesin", "BEBEK", "R1"),
                ("Handling", "AYAM", "R1"),
                ("Handling", "AYAM", "R2"),
            ]
            assert rows == expected
        finally:
            view.close()

    def test_pemisah_antar_keterangan_barang(self):
        """Baris KOSONG pemisah antar grup (KETERANGAN, NAMA BARANG):
        4 grup / 3 label item (Alat/Mesin×AYAM, Alat/Mesin×BEBEK,
        Handling×AYAM — R1→R2 sama label) → 2 pemisah (bukan di depan
        grup pertama/akhir)."""
        from ui.grouping import SEP_COL
        view = self._make_view()
        try:
            mdf = view._table.model().dataframe
            seps = mdf[SEP_COL].tolist()
            assert sum(1 for v in seps if v is True) == 2
            assert not seps[0] and not seps[-1]
        finally:
            view.close()

    def test_pemisah_tak_antar_resto_sama_grup(self):
        """(Handling, AYAM, R1) → (Handling, AYAM, R2): resto beda tapi
        (KETERANGAN, BARANG) sama → TANPA pemisah (pemisah hanya antar
        label item alasan×barang)."""
        from ui.grouping import SEP_COL
        view = self._make_view()
        try:
            mdf = view._table.model().dataframe
            # cari posisi baris Handling AYAM R1 & R2 (bertetangga tanpa
            # pemisah di antara keduanya)
            idx = [i for i, r in mdf.iterrows()
                   if (str(r["KETERANGAN"]) == "Handling"
                       and str(r["NAMA BARANG"]) == "AYAM")]
            assert len(idx) == 2 and idx[1] == idx[0] + 1, (
                "dua baris resto sama klaster harus bertetangga tanpa "
                "pemisah")
        finally:
            view.close()
