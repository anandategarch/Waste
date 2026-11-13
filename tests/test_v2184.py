# -*- coding: utf-8 -*-
"""Regresi v2.18.4 — MATCH RESTO LINTAS SUMBER (Banding Periode).

Pemicu (file user asli): pembanding "REKAP MENTAH_01-07 OKTOBER
2026_TEGAR.xlsx" memakai kode resto DBS/Power Query ('1041.BDGUKU',
'1216.BJMHAS', 'B.1001.MLGPAR' — 20 resto) sedangkan output "Proses dari
Folder" mensintesis NAMA RESTO dari NAMA FILE ('BDGUKU', 'BJMHAS',
'MLGPAR' — 18 resto). Interseksi exact = 0 → SEMUA item tampil
BARU/HILANG palsu di tab Banding Periode (terukur repro: new=100,
gone=100, resto match=0). v2.18.1 hanya memberi PERINGATAN; v2.18.4
benar-benar MATCH via kunci stem kode resto.

Yang dikunci di sini:
  R184-1  _resto_stem: strip prefix kode ('1216.'/'B.1001.') — nama
          wajar bertitik ('V.20', 'NO.1', '12.34') TIDAK distrip.
  R184-2  compare_quantity lintas sumber: branch/items match, 0 palsu
          BARU/HILANG, resto_overlap > 0, warn mati (jalur agg &
          agg_jenis/use_jenis; sisi kosong tak crash).
  R184-3  Kolom display tetap nama ASLI sumber (A menang; baris B-only
          tampil nama B — funnel/export tak berubah).
  R184-4  compare_level (drill pop-up) lintas sumber match.
  R184-5  drill_day_detail: klik display salah satu sisi menemukan
          baris agg sisi lain.
  R184-6  change_vs_history: BULAN LALU terisi lintas sumber.
  R184-7  day_evidence_vs_history: NILAI BULAN LALU terisi lintas
          sumber + anti duplikat varian nama (panjang output utuh).
  R184-8  Kontrak lama utuh: nama SAMA kedua sisi tetap match; resto
          benar-benar beda tetap 0-overlap + warn (skenario v2.18.1).
  R184-9  End-to-end loader asli: workbook pembanding kode DBS vs
          pipeline folder-flow stem → compare match.
  R184-10 Pin versi 2.18.4 sinkron semua situs.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent

CFG = {"input_sheets": {"rekap_mentah": [
    "DATA_WASTE", "Data Waste", "DATA", "Sheet1",
    "REKAP_MENTAH", "Rekap Mentah", "REKAP"]}}


# ============================================================
# Helper — entri bulan sintetis (bentuk _month_dict)
# ============================================================

def _month(label: str, rows: list[dict]) -> dict:
    """Entri bulan dari baris {resto, barang, jenis, ket, total, hari}.

    agg + agg_jenis + agg_detail dibangun konsisten supaya jalur
    use_jenis (v2.12.2) ikut teruji."""
    _alias = {"JENIS": "jenis", "KETERANGAN": "ket"}

    def _frame(keys):
        recs = []
        for r in rows:
            rec = {"NAMA RESTO": r["resto"], "NAMA BARANG": r["barang"],
                   "TOTAL": r["total"]}
            for k in keys:
                src = _alias.get(k, k)
                if src in r:
                    rec[k] = r[src]
            recs.append(rec)
        return pd.DataFrame(recs)

    agg = _frame(["NAMA RESTO", "NAMA BARANG"])
    for d in range(1, 32):
        agg[str(d)] = [r.get("hari", {}).get(str(d), 0.0) for r in rows]
    agg["HARI AKTIF"] = [
        sum(1 for v in r.get("hari", {}).values() if v > 0) for r in rows]
    jenis_tot = {}
    for r in rows:
        jenis_tot[r.get("jenis", "WASTE")] = (
            jenis_tot.get(r.get("jenis", "WASTE"), 0.0) + r["total"])
    return {
        "label": label, "key_akhir": 31, "agg": agg,
        "jenis_totals": pd.DataFrame(
            [{"JENIS": j, "TOTAL": t} for j, t in jenis_tot.items()]),
        "agg_jenis": _frame(["NAMA RESTO", "NAMA BARANG", "JENIS"]),
        "agg_detail": _frame(
            ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN"]),
        "resto_count": len({r["resto"] for r in rows}),
        "item_count": len({r["barang"] for r in rows}),
        "rows_kept": len(rows), "rows_raw": len(rows), "error": None,
    }


_A_ROWS = [
    {"resto": "BJMHAS", "barang": "AYAM FILET", "jenis": "WASTE",
     "ket": "Internal", "total": 100.0, "hari": {"5": 100.0}},
    {"resto": "MLGPAR", "barang": "AYAM FILET", "jenis": "WASTE",
     "ket": "Internal", "total": 50.0, "hari": {"5": 50.0}},
]
_B_ROWS = [
    {"resto": "1216.BJMHAS", "barang": "AYAM FILET", "jenis": "WASTE",
     "ket": "Internal", "total": 80.0, "hari": {"5": 80.0}},
    {"resto": "B.1001.MLGPAR", "barang": "AYAM FILET", "jenis": "WASTE",
     "ket": "Internal", "total": 50.0, "hari": {"5": 50.0}},
]


# ============================================================
# [R184-1] _resto_stem — unit
# ============================================================

class TestRestoStem:
    def test_strip_prefix_kode(self):
        from waste_anomaly.period_history import _resto_stem
        assert _resto_stem("1216.BJMHAS") == "BJMHAS"
        assert _resto_stem("1041.BDGUKU") == "BDGUKU"
        assert _resto_stem("B.1001.MLGPAR") == "MLGPAR"
        assert _resto_stem("B.1012.BDGSEK") == "BDGSEK"
        assert _resto_stem("2.FILTER KOPI") == "FILTER KOPI"

    def test_nama_wajar_tidak_distrip(self):
        """'V.20'/'NO.1'/'12.34' — segmen akhir murni angka ATAU segmen
        depan bukan pola kode → nama utuh (bukan prefix kode resto)."""
        from waste_anomaly.period_history import _resto_stem
        assert _resto_stem("V.20") == "V.20"
        assert _resto_stem("NO.1") == "NO.1"
        assert _resto_stem("12.34") == "12.34"
        assert _resto_stem(".BJMHAS") == ".BJMHAS"   # segmen kosong
        assert _resto_stem("1216.") == "1216."       # stem kosong
        assert _resto_stem("MIE (V.20)") == "MIE (V.20)"

    def test_tanpa_titik_dan_whitespace(self):
        from waste_anomaly.period_history import _resto_stem
        assert _resto_stem("BDGUKU") == "BDGUKU"
        assert _resto_stem("BJMHAS ") == "BJMHAS"    # strip
        assert _resto_stem("") == ""
        assert _resto_stem(None) == ""

    def test_resto_key_series(self):
        from waste_anomaly.period_history import _resto_key
        s = pd.Series(["BJMHAS", "1216.BJMHAS", None, "B.1001.MLGPAR"])
        out = list(_resto_key(s))
        assert out == ["BJMHAS", "BJMHAS", "", "MLGPAR"]


# ============================================================
# [R184-2] compare_quantity — lintas sumber
# ============================================================

class TestCompareQuantityLintasSumber:
    def test_match_penuh_tanpa_baru_hilang_palsu(self):
        """A = stem (folder flow), B = kode DBS, item sama → 0 BARU,
        0 HILANG (dulu SEMUA palsu), branch 2 baris match."""
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", _A_ROWS),
                               _month("Juli 2026", _B_ROWS))
        assert res["resto_overlap"] == 2
        assert res["resto_overlap_warn"] is False
        assert len(res["branch"]) == 2
        assert len(res["items"]) == 2
        assert len(res["new_items"]) == 0
        assert len(res["gone_items"]) == 0
        br = res["branch"].set_index("NAMA RESTO")
        assert abs(br.loc["BJMHAS", "Selisih"] - 20.0) < 1e-9  # 100-80
        assert abs(br.loc["MLGPAR", "Selisih"]) < 1e-9         # 50-50

    def test_use_jenis_jalur_agg_jenis(self):
        """Jalur use_jenis (agg_jenis tersedia — tampil JENIS di tabel
        mover sejak v2.12.2) wajib match lintas sumber juga."""
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", _A_ROWS),
                               _month("Juli 2026", _B_ROWS))
        assert "JENIS" in res["items"].columns  # jalur use_jenis aktif
        assert list(res["items"]["JENIS"]) == ["WASTE", "WASTE"]
        it = res["items"].set_index("NAMA RESTO")
        assert abs(it.loc["BJMHAS", "Bulan Ini"] - 100.0) < 1e-9
        assert abs(it.loc["BJMHAS", "Pembanding"] - 80.0) < 1e-9

    def test_sisi_kosong_tak_crash(self):
        """Satu sisi tanpa data → tabel tetap TERBENTUK (kolom utuh,
        tanpa crash; pola v2.18.1 R181-4). v2.18.5: resto satu-sisi
        disembunyikan → semua tabel 0 baris."""
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", []),
                               _month("Juli 2026", _B_ROWS))
        assert res["resto_overlap_warn"] is False
        assert len(res["gone_items"]) == 0
        assert len(res["new_items"]) == 0
        assert len(res["branch"]) == 0
        assert res["resto_only_b"] == 2  # 2 resto pembanding tersembunyi

    def test_ringkasan_cabang_aktif(self):
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", _A_ROWS),
                               _month("Juli 2026", _B_ROWS))
        s = res["summary"].set_index("Metrik")
        assert int(s.loc["Cabang Aktif", "Bulan Ini"]) == 2
        assert int(s.loc["Cabang Aktif", "Pembanding"]) == 2


# ============================================================
# [R184-3] display tetap nama asli
# ============================================================

class TestDisplayNamaAsli:
    def test_resto_satu_sisi_disembunyikan(self):
        """v2.18.5 (permintaan user: "misal bulan kemarin ada bulan ini
        gak ada gak perlu ditampilkan"): resto B-only (1370.KGNSUD)
        TIDAK tampil di tabel mana pun; resto yang match tampil nama ASLI
        sumber A ("BJMHAS", bukan stem apalagi kode B)."""
        from waste_anomaly.period_history import compare_quantity
        b = _B_ROWS + [
            {"resto": "1370.KGNSUD", "barang": "CABE RAWIT",
             "jenis": "WASTE", "ket": "Internal", "total": 70.0,
             "hari": {"5": 70.0}}]
        res = compare_quantity(_month("Bulan Ini", _A_ROWS),
                               _month("Juli 2026", b))
        # B-only resto disembunyikan dari SEMUA tabel banding
        assert len(res["gone_items"]) == 0
        assert set(res["branch"]["NAMA RESTO"]) == {"BJMHAS", "MLGPAR"}
        # jumlahnya dilaporkan jujur ke pemanggil (UI menampilkan info)
        assert res["resto_only_b"] == 1
        assert res["resto_only_a"] == 0
        # resto match tampil nama A (funnel/export kontrak tak berubah)
        br = res["branch"].set_index("NAMA RESTO")
        assert abs(br.loc["BJMHAS", "Bulan Ini"] - 100.0) < 1e-9

    def test_item_baru_tampil_nama_a(self):
        from waste_anomaly.period_history import compare_quantity
        a = _A_ROWS + [
            {"resto": "BJMHAS", "barang": "TEPUNG", "jenis": "WASTE",
             "ket": "Internal", "total": 30.0, "hari": {"7": 30.0}}]
        res = compare_quantity(_month("Bulan Ini", a),
                               _month("Juli 2026", _B_ROWS))
        assert list(res["new_items"]["NAMA RESTO"]) == ["BJMHAS"]
        assert list(res["new_items"]["NAMA BARANG"]) == ["TEPUNG"]


# ============================================================
# [R184-4] compare_level — drill pop-up
# ============================================================

class TestCompareLevel:
    def test_level_resto_lintas_sumber(self):
        from waste_anomaly.period_history import compare_level
        df = compare_level(_month("Bulan Ini", _A_ROWS),
                           _month("Juli 2026", _B_ROWS), ["NAMA RESTO"])
        assert len(df) == 2
        assert set(df["NAMA RESTO"]) == {"BJMHAS", "MLGPAR"}
        row = df.set_index("NAMA RESTO").loc["BJMHAS"]
        assert abs(row["Bulan Ini"] - 100.0) < 1e-9
        assert abs(row["Pembanding"] - 80.0) < 1e-9

    def test_level_resto_barang(self):
        from waste_anomaly.period_history import compare_level
        df = compare_level(_month("Bulan Ini", _A_ROWS),
                           _month("Juli 2026", _B_ROWS),
                           ["NAMA RESTO", "NAMA BARANG"])
        assert len(df) == 2
        assert set(df["NAMA RESTO"]) == {"BJMHAS", "MLGPAR"}


# ============================================================
# [R184-5] drill_day_detail — rincian hari
# ============================================================

class TestDrillDayDetail:
    def test_dari_nama_sisi_a(self):
        from waste_anomaly.period_history import drill_day_detail
        df = drill_day_detail(_month("Bulan Ini", _A_ROWS),
                              _month("Juli 2026", _B_ROWS),
                              "BJMHAS", "AYAM FILET")
        row = df[df["HARI"] == 5].iloc[0]
        assert row["Bulan Ini"] == 100.0
        assert row["Pembanding"] == 80.0   # dulu 0 (exact-match gagal)

    def test_dari_nama_sisi_b(self):
        """Klik baris display nama B ('1216.BJMHAS') → tetap menemukan
        baris agg sisi A ('BJMHAS')."""
        from waste_anomaly.period_history import drill_day_detail
        df = drill_day_detail(_month("Bulan Ini", _A_ROWS),
                              _month("Juli 2026", _B_ROWS),
                              "1216.BJMHAS", "AYAM FILET")
        row = df[df["HARI"] == 5].iloc[0]
        assert row["Bulan Ini"] == 100.0
        assert row["Pembanding"] == 80.0


# ============================================================
# [R184-6] change_vs_history — BULAN LALU tab Anomali
# ============================================================

class TestChangeVsHistory:
    def test_bulan_lalu_terisi_lintas_sumber(self):
        """Anomali folder-flow ('BJMHAS') + pembanding kode DBS
        ('1216.BJMHAS') → BULAN LALU 80 (dulu NaN → PERUBAHAN 'Baru'
        palsu)."""
        from waste_anomaly.period_history import change_vs_history
        df = pd.DataFrame([{
            "NAMA RESTO": "BJMHAS", "NAMA BARANG": "AYAM FILET",
            "JENIS": "WASTE", "KETERANGAN": "Internal", "TOTAL": 100.0}])
        out = change_vs_history(df, _month("Juli 2026", _B_ROWS))
        assert out["BULAN LALU"].iloc[0] == 80.0
        assert out["PERUBAHAN"].iloc[0] == "Naik Sedang"  # +25%

    def test_varian_nama_b_digabung(self):
        """Baseline dgn 2 varian nama resto sama stem → groupby kunci
        menjumlah (tanpa duplikat baris merge)."""
        from waste_anomaly.period_history import change_vs_history
        b = _month("Juli 2026", _B_ROWS + [
            {"resto": "999.BJMHAS", "barang": "AYAM FILET",
             "jenis": "WASTE", "ket": "Internal", "total": 20.0,
             "hari": {"5": 20.0}}])
        df = pd.DataFrame([{
            "NAMA RESTO": "BJMHAS", "NAMA BARANG": "AYAM FILET",
            "JENIS": "WASTE", "KETERANGAN": "Internal", "TOTAL": 100.0}])
        out = change_vs_history(df, b)
        assert out["BULAN LALU"].iloc[0] == 100.0  # 80 + 20 digabung


# ============================================================
# [R184-7] day_evidence_vs_history — NILAI BULAN LALU tab Hari
# ============================================================

class TestDayEvidenceVsHistory:
    def _df(self):
        return pd.DataFrame([{
            "NAMA RESTO": "BJMHAS", "NAMA BARANG": "AYAM FILET",
            "HARI TERSANGKA": 5, "NILAI HARI TERSANGKA": 100.0,
            "5": 100.0}])

    def test_nilai_bulan_lalu_terisi(self):
        from waste_anomaly.period_history import day_evidence_vs_history
        out = day_evidence_vs_history(self._df(),
                                      [_month("Juli 2026", _B_ROWS)])
        assert out["NILAI BULAN LALU"].iloc[0] == 80.0
        assert abs(out["RASIO VS BULAN LALU"].iloc[0] - 1.25) < 1e-9

    def test_tipikal_varian_nama_anti_duplikat(self):
        """Tipikal dgn 2 varian nama resto (stem sama) → lookup tetap
        1 nilai per kandidat (dulu merge melipatgandakan baris →
        ValueError panjang / nilai salah)."""
        from waste_anomaly.period_history import day_evidence_vs_history
        typ = _month("Tipikal", _B_ROWS + [
            {"resto": "999.BJMHAS", "barang": "AYAM FILET",
             "jenis": "WASTE", "ket": "Internal", "total": 20.0,
             "hari": {"5": 20.0}}])
        out = day_evidence_vs_history(
            self._df(), [_month("Juli 2026", _B_ROWS)], typical=typ)
        assert len(out) == 1
        assert out["NILAI BULAN LALU"].iloc[0] == 80.0
        # first-variant (1216.BJMHAS hari-5 = 80), bukan 80+20
        assert out["TIPIKAL BEBERAPA BULAN"].iloc[0] == 80.0


# ============================================================
# [R184-8] kontrak lama utuh
# ============================================================

class TestKontrakLama:
    def test_nama_sama_kedua_sisi_tetap_match(self):
        """DBS vs DBS (kedua sisi kode) — perilaku pra-v2.18.4 utuh."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", [
            {"resto": "1042.KWGGAL", "barang": "MIE (V.20)",
             "jenis": "WASTE", "ket": "Internal", "total": 100.0,
             "hari": {"5": 100.0}}])
        b = _month("Juli 2026", [
            {"resto": "1042.KWGGAL", "barang": "MIE (V.20)",
             "jenis": "WASTE", "ket": "Internal", "total": 90.0,
             "hari": {"5": 90.0}}])
        res = compare_quantity(a, b)
        assert res["resto_overlap"] == 1
        assert len(res["items"]) == 1
        assert len(res["new_items"]) == 0

    def test_resto_beda_benaran_tetap_0_overlap_warn(self):
        """Skenario v2.18.1 R181-4: set resto memang berbeda (bukan
        beda konvensi) → 0 overlap + warning tetap menyala."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", [
            {"resto": "BJMHAS", "barang": "AYAM FILET", "jenis": "WASTE",
             "ket": "Internal", "total": 100.0, "hari": {"5": 100.0}}])
        b = _month("Juli 2026", [
            {"resto": "1042.KWGGAL", "barang": "AYAM FILET",
             "jenis": "WASTE", "ket": "Internal", "total": 80.0,
             "hari": {"5": 80.0}}])
        res = compare_quantity(a, b)
        assert res["resto_overlap"] == 0
        assert res["resto_overlap_warn"] is True
        # v2.18.5: resto satu-sisi disembunyikan (permintaan user) —
        # tabel kosong, jumlah disembunyi dilaporkan jujur.
        assert len(res["new_items"]) == 0
        assert len(res["gone_items"]) == 0
        assert res["resto_only_a"] == 1
        assert res["resto_only_b"] == 1

    def test_display_kontrak_kolom_tidak_berubah(self):
        """Kolom tabel banding persis kontrak lama (UI merender kunci
        ini — pola period_compare; _month menyediakan agg_jenis →
        prefiks JENIS v2.12.2 ikut kontrak)."""
        from waste_anomaly.period_history import (BRANCH_COLS, GONE_ITEM_COLS,
                                                  ITEM_COLS, NEW_ITEM_COLS,
                                                  SUMMARY_COLS, compare_quantity)
        res = compare_quantity(_month("Bulan Ini", _A_ROWS),
                               _month("Juli 2026", _B_ROWS))
        assert list(res["summary"].columns) == SUMMARY_COLS
        assert list(res["branch"].columns) == ["JENIS"] + BRANCH_COLS
        assert list(res["items"].columns) == ["JENIS"] + ITEM_COLS
        assert list(res["new_items"].columns) == ["JENIS"] + NEW_ITEM_COLS
        assert list(res["gone_items"].columns) == ["JENIS"] + GONE_ITEM_COLS


# ============================================================
# [R184-9] end-to-end loader asli (workbook → compare)
# ============================================================

class TestEndToEndLoader:
    def test_workbook_kode_vs_pipeline_stem(self, tmp_path):
        """Workbook pembanding ASLI (kode '1216.BJMHAS') dimuat
        load_history_file; pipeline folder-flow (stem 'BJMHAS') lewat
        aggregate_current → compare_quantity MATCH (repro mini skenario
        user: Proses dari Folder + REKAP MENTAH_01-07 OKTOBER)."""
        from openpyxl import Workbook
        from waste_anomaly.period_history import (aggregate_current,
                                                  compare_quantity,
                                                  load_history_file)
        cols = ["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
                "NAMA RESTO", "SATUAN"] + [str(d) for d in range(1, 32)]
        wb = Workbook()
        ws = wb.active
        ws.title = "REKAP MENTAH"
        ws.append(cols)
        row = ["WASTE BAHAN DAN PACKAGING", "WASTE", "Internal",
               "AYAM FILET", "1216.BJMHAS", "GR"] + [0] * 31
        row[6 + 5 - 1] = 80.0  # hari-5
        ws.append(row)
        wb_path = tmp_path / "REKAP MENTAH JULI 2026.xlsx"
        wb.save(wb_path)

        b = load_history_file(str(wb_path), CFG)
        assert b["error"] is None, b["error"]

        # sisi A ala folder-flow: stem nama file, TOTAL dari hari
        dfp = pd.DataFrame([{
            "NAMA RESTO": "BJMHAS", "NAMA BARANG": "AYAM FILET",
            "JENIS": "WASTE", "KETERANGAN": "Internal", "SATUAN": "GR",
            **{str(d): (100.0 if d == 5 else 0.0) for d in range(1, 32)},
            "TOTAL": 100.0}])
        a = aggregate_current(dfp, 31, "Bulan Ini")

        res = compare_quantity(a, b)
        assert res["resto_overlap"] == 1
        assert res["resto_overlap_warn"] is False
        assert len(res["new_items"]) == 0
        assert len(res["gone_items"]) == 0
        it = res["items"]
        assert list(it["NAMA RESTO"]) == ["BJMHAS"]
        assert abs(it["Bulan Ini"].iloc[0] - 100.0) < 1e-9
        assert abs(it["Pembanding"].iloc[0] - 80.0) < 1e-9


# ============================================================
# [R184-10] pin versi 2.18.4
# ============================================================

class TestVersiSinkron:
    def test_versi_2184_sinkron(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        cfg = load_config()
        assert APP_VERSION == __version__ == cfg.get("version") == "2.21.1"
        init_src = (REPO / "waste_anomaly" / "__init__.py").read_text(
            encoding="utf-8")
        assert "Versi: 2.18.4" in init_src
        mulai = (REPO / "MULAI.bat").read_bytes()
        assert b"v2.18.4" in mulai
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "v2.18.4" in readme
