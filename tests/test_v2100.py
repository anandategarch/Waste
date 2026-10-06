"""Test — v2.10.0: periode pembanding multi-file (kuantiti tanpa BOM).

Fitur (disetujui user — worklog Task 9 + jawaban 5 pertanyaan):
1. Banding Periode multi-file: 1 file = 1 bulan, label bulan OTOMATIS dari
   nama file, daftar diingat antar sesi (history_files.json), dimuat di
   background (HistoryWorker + cancel).
2. Banding dua-duanya: per bulan + "Tipikal" (median gabungan ≥ 2 bulan).
3. Murni kuantiti — tanpa angka BOM (saringan JENIS WAJIB: file mentah
   berisi SO/BOM/stok; bukti data asli MIE hari-24: 43115 tanpa saringan
   vs 194 yang benar).
4. Tab Hari Mencurigakan: kolom NILAI BULAN LALU (tanggal sama bulan
   sebelumnya) + RASIO VS BULAN LALU + TIPIKAL BEBERAPA BULAN.

Pengganti kontrak PeriodWorker wave1 (key_akhir pembanding + cancel)
dijaga di TestHistoryWorker.

Headless: QT_QPA_PLATFORM=offscreen sebelum PySide6 (konvensi suite).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
PEM_REAL = REPO / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx"
MAIN_REAL = REPO / "DATA_WASTE.xlsx"

_DAY_COLS = [str(d) for d in range(1, 32)]


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# Fixture workbook pembanding sintetis
# ============================================================

def _wb_bulan(tmp_path: Path, name: str = "REKAP MENTAH JULI 2026.xlsx",
              partial: bool = False) -> Path:
    """Workbook bulan sintetis — replika skala kecil dari bukti MIE asli.

    Item MIE (V.20) @ 1042.KWGGAL:
    - WASTE Handling: hari-24 = 100; hari lain 2
    - WASTE Cancel Nota: hari-24 = 94; hari lain 0
    - BOM (JENIS BOM): hari-24 = 42921 → PENGECEH: tanpa saringan JENIS,
      agregat hari-24 = 43115 (bukti bug saringan), dgn saringan = 194.
    partial=True: waste berhenti di hari 20 (hari 21-31 = 0, tanpa baris
    BOM/SO) → auto_key_akhir = 20.
    """
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): base for d in range(1, 32)}
        data["24"] = float(day24)
        if partial:
            for d in range(21, 32):
                data[str(d)] = 0.0
        rows.append({
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": "MIE (V.20)",
            "NAMA RESTO": "1042.KWGGAL", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 100, 2.0)
    _row("WASTE", "Cancel Nota", 94, 0.0)
    if not partial:
        _row("BOM", "BOM", 42921, 2.0)
        _row("SO", "SO", 5.0, 1.0)
    out = tmp_path / name
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


# ============================================================
# [1] LABEL BULAN DARI NAMA FILE
# ============================================================

class TestDetectMonthLabel:
    def test_nama_file_asli_terdeteksi(self):
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label(
            "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx") == "Agustus 2026"

    def test_variasi_nama(self):
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label("rekap mentah JULI 2025.xlsx") == "Juli 2025"
        assert detect_month_label("DESEMBER.xlsx") == "Desember"
        assert detect_month_label("AGUSTUS2026.xlsx") == "Agustus 2026"
        assert detect_month_label("data Januari 2024 ok.xlsx") == "Januari 2024"
        assert detect_month_label("Data lama MARET.xlsx") == "Maret"

    def test_tanpa_bulan_none(self):
        from waste_anomaly.period_history import detect_month_label
        assert detect_month_label("DATA.xlsx") is None
        assert detect_month_label("REKAP 123.xlsx") is None

    def test_sort_key_kronologis(self):
        from waste_anomaly.period_history import month_sort_key
        keys = ["Agustus 2026", "Juli 2026", "Desember 2025", "??"]
        assert sorted(keys, key=month_sort_key)[:3] == [
            "??", "Desember 2025", "Juli 2026"]
        assert max(["Juli 2026", "Agustus 2026", "Juni 2026"],
                   key=month_sort_key) == "Agustus 2026"


# ============================================================
# [2] LOAD FILE PEMBANDING (saringan JENIS + agregat)
# ============================================================

class TestLoadHistoryFile:
    def test_saringan_jenis_wajib_bukti_mie(self, tmp_path):
        """Inti desain: tanpa saringan JENIS, agregat = 43.115 (ikut BOM/SO);
        dgn saringan = 194 — replika bukti data asli (worklog Task 9)."""
        from waste_anomaly.period_history import load_history_file
        wb = _wb_bulan(tmp_path)
        res = load_history_file(str(wb), {})
        assert res["error"] is None, res["error"]
        agg = res["agg"]
        row = agg[(agg["NAMA BARANG"] == "MIE (V.20)")
                  & (agg["NAMA RESTO"] == "1042.KWGGAL")].iloc[0]
        assert row["24"] == 194.0
        assert row["TOTAL"] == (2 * 30 + 100) + 94  # 2 baris keterangan dijumlah
        assert row["HARI AKTIF"] == 31

    def test_label_dan_key_akhir_dari_file(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        res = load_history_file(str(_wb_bulan(tmp_path)), {})
        assert res["label"] == "Juli 2026"
        assert res["key_akhir"] == 31
        assert res["rows_kept"] == 2  # hanya WASTE — BOM/SO disaring
        assert res["rows_raw"] == 4
        assert res["error"] is None

    def test_bulan_parsial_key_akhir_20(self, tmp_path):
        """Penerus kontrak wave1 FIX 2: key_akhir = hari aktif TERBESAR
        terdeteksi dari data (bukan default 31)."""
        from waste_anomaly.period_history import load_history_file
        res = load_history_file(
            str(_wb_bulan(tmp_path, partial=True)), {})
        assert res["key_akhir"] == 20

    def test_file_hilang_error_bukan_raise(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        res = load_history_file(str(tmp_path / "tidak_ada.xlsx"), {})
        assert res["error"] and "tidak ditemukan" in res["error"]

    def test_format_m_53kolom_juga_diterima(self, tmp_path):
        """File hasil M (dgn kolom turunan) tetap valid sbg pembanding —
        agregat dihitung ULANG dari hari, tidak percaya kolom TOTAL."""
        from waste_anomaly.period_history import load_history_file
        df = pd.DataFrame([
            {"NAMA BARANG": "X", "NAMA RESTO": "R1", "JENIS": "WASTE",
             "KETERANGAN": "Handling",
             **{str(d): 1.0 for d in range(1, 32)},
             "TOTAL": 99999.0,  # pengecoh — harus diabaikan
             "MAX": 1.0, "AVG": 1.0, "% to BOM": 0.5},
        ])
        wb = tmp_path / "REKAP MENTAH JANUARI 2026.xlsx"
        df.to_excel(wb, sheet_name="REKAP MENTAH", index=False)
        res = load_history_file(str(wb), {})
        assert res["error"] is None
        assert res["agg"]["TOTAL"].iloc[0] == 31.0

    def test_kolom_wajib_hilang_error(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        wb = tmp_path / "REKAP MENTAH FEBRUARI 2026.xlsx"
        pd.DataFrame([{"JENIS": "WASTE", "TOTAL": 5.0}]).to_excel(
            wb, sheet_name="REKAP MENTAH", index=False)
        res = load_history_file(str(wb), {})
        assert res["error"]

    def test_path_hasil_persis_string_input(self, tmp_path):
        """v2.10.1 regresi (bug dilaporkan user di Windows): 'path' hasil
        HARUS persis string input pemanggil. str(Path(...)) menormalisasi
        pemisah (Windows: dialog Qt 'C:/a/b.xlsx' → 'C:\\a\\b.xlsx';
        Linux: 'x/./y' → 'x/y') — view mengunci _last_results/_loaded/
        entri dgn string DARI DIALOG, normalisasi bikin kolom Status
        tetap 'belum dimuat' padahal notif memuat sukses."""
        from waste_anomaly.period_history import load_history_file
        wb = _wb_bulan(tmp_path)
        weird = str(wb.parent) + "/./" + wb.name  # pathlib meringkus '/./'
        assert str(Path(weird)) != weird  # prekondisi: kelas mismatch nyata
        res = load_history_file(weird, {})
        assert res["error"] is None, res["error"]
        assert res["path"] == weird


# ============================================================
# [3] AGREGAT BULAN BERJALAN (A)
# ============================================================

class TestAggregateCurrent:
    def _df_a(self) -> pd.DataFrame:
        data = {str(d): 3.0 for d in range(1, 31)}
        data["24"] = 819.0
        return pd.DataFrame([
            {"NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)",
             "JENIS": "WASTE", "KETERANGAN": "Cancel Nota",
             **data, "TOTAL": float(sum(data.values())),
             "ANOMALY STATUS": "Potensi Anomali"},
            {"NAMA RESTO": "R2", "NAMA BARANG": "LAIN", "JENIS": "TRIAL",
             "KETERANGAN": "TRIAL",
             **{str(d): 1.0 for d in range(1, 31)}, "TOTAL": 30.0,
             "ANOMALY STATUS": "Normal"},
        ])

    def test_agregat_dari_df_pipeline(self):
        from waste_anomaly.period_history import aggregate_current
        a = aggregate_current(self._df_a(), 30)
        assert a is not None
        agg = a["agg"]
        mie = agg[agg["NAMA BARANG"] == "MIE (V.20)"].iloc[0]
        assert mie["24"] == 819.0
        assert mie["TOTAL"] == 819.0 + 3.0 * 29
        assert a["label"] == "Bulan Ini"
        assert a["key_akhir"] == 30

    def test_df_tanpa_hari_none(self):
        from waste_anomaly.period_history import aggregate_current
        assert aggregate_current(pd.DataFrame({"A": [1]}), 31) is None
        assert aggregate_current(None, 31) is None


# ============================================================
# [4] PERBANDINGAN KUANTITI A vs B
# ============================================================

def _month(label, ka, rows):
    """Bulan sintetis: rows = [(resto, item, total)]."""
    days = {str(d): 0.0 for d in range(1, 32)}
    agg = pd.DataFrame(
        [{"NAMA RESTO": r, "NAMA BARANG": i, "TOTAL": t, "HARI AKTIF": 3,
          **days} for r, i, t in rows])
    jt = pd.DataFrame({"JENIS": ["WASTE"], "TOTAL": [sum(t for *_,
                                                          t in rows)]})
    return {"label": label, "agg": agg, "jenis_totals": jt, "key_akhir": ka}


class TestCompareQuantity:
    def test_arah_perubahan_benar(self):
        """Arah % = (bulan ini − pembanding) / pembanding — regresi bug
        iterasi-1 v2.10.0 (terbalik −22,2% padahal +28,6%)."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 180.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 140.0)])
        res = compare_quantity(a, b)
        row = res["summary"].set_index("Metrik")
        assert abs(row.loc["Total Waste", "Perubahan %"] - 28.571) < 0.01
        assert row.loc["Total Waste", "Bulan Ini"] == 180.0
        assert row.loc["Total Waste", "Pembanding"] == 140.0

    def test_hari_data_tanpa_persen(self):
        """Beda panjang bulan BUKAN kinerja — kolom Perubahan kosong."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 30, [("R1", "X", 150.0)])
        b = _month("Agustus 2026", 31, [("R1", "X", 155.0)])
        res = compare_quantity(a, b)
        row = res["summary"].set_index("Metrik").loc["Hari Data"]
        assert pd.isna(row["Perubahan %"])
        # normalisasi per hari tetap ada
        wph = res["summary"].set_index("Metrik").loc["Waste per Hari"]
        assert wph["Bulan Ini"] == 5.0 and abs(wph["Pembanding"] - 5.0) < 0.01

    def test_mover_new_gone_dan_arah(self):
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", 31, [
            ("R1", "X", 100.0), ("R1", "Y", 50.0), ("R2", "X", 30.0)])
        b = _month("Juli 2026", 31, [
            ("R1", "X", 80.0), ("R2", "X", 60.0), ("R2", "Z", 10.0)])
        res = compare_quantity(a, b)
        items = res["items"]
        # mover = |selisih| terbesar: R1 Y BARU (+50, pembanding 0) — item
        # baru ikut tabel mover (semantik compare_periods lama, outer+0).
        assert items.iloc[0]["NAMA BARANG"] == "Y"
        assert items.iloc[0]["Selisih"] == 50.0
        rx = items[items["NAMA BARANG"] == "X"].set_index("NAMA RESTO")
        assert rx.loc["R1", "Selisih"] == 20.0
        assert rx.loc["R2", "Selisih"] == -30.0
        # baru = hanya di bulan INI (R1 Y); hilang = hanya bulan lalu (R2 Z)
        assert set(map(tuple, res["new_items"][["NAMA RESTO", "NAMA BARANG"]]
                       .to_numpy())) == {("R1", "Y")}
        assert set(map(tuple, res["gone_items"][["NAMA RESTO", "NAMA BARANG"]]
                       .to_numpy())) == {("R2", "Z")}
        # per_jenis: WASTE 180 vs 150
        pj = res["per_jenis"].set_index("JENIS")
        assert pj.loc["WASTE", "Bulan Ini"] == 180.0
        assert pj.loc["WASTE", "Pembanding"] == 150.0

    def test_cap_top_n(self):
        from waste_anomaly.period_history import compare_quantity
        rows_a = [(f"R{i}", f"I{i}", float(i)) for i in range(30)]
        rows_b = [(f"R{i}", f"I{i}", float(i) + 1) for i in range(30)]
        res = compare_quantity(_month("A", 31, rows_a),
                               _month("B", 31, rows_b), top_n=10)
        assert len(res["items"]) == 10
        assert len(res["new_items"]) == 0

    def test_label_dan_key_akhir_diteruskan(self):
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", 30, [("R", "X", 1.0)]),
                               _month("Tipikal", 31, [("R", "X", 1.0)]))
        assert res["label_a"] == "Bulan Ini"
        assert res["label_b"] == "Tipikal"
        assert res["key_akhir_a"] == 30 and res["key_akhir_b"] == 31


# ============================================================
# [5] TIPIKAL GABUNGAN (median)
# ============================================================

class TestTypicalMonths:
    def test_median_per_item_hari(self, tmp_path):
        from waste_anomaly.period_history import (
            load_history_file, typical_months)
        m1 = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH JULI 2026.xlsx")), {})
        m2 = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")), {})
        m2b = dict(m2)
        # Agustus digandakan dgn nilai beda supaya median ≠ salah satu
        agg = m2b["agg"].copy()
        agg["24"] = 300.0
        m3 = dict(m2b, agg=agg, label="Juni 2026")
        typ = typical_months([m1, m2b, m3])
        assert typ is not None
        row = typ["agg"].iloc[0]
        # hari-24: median(194, 194, 300) = 194; hari biasa: median(2,2,2)=2
        assert row["24"] == 194.0
        assert row["5"] == 2.0
        assert typ["months_count"] == 3
        assert typ["label"] == "Tipikal"

    def test_kurang_dari_2_bulan_none(self):
        from waste_anomaly.period_history import typical_months
        m = _month("Juli 2026", 31, [("R", "X", 10.0)])
        assert typical_months([m]) is None
        assert typical_months([]) is None

    def test_hari_tak_semua_bulan_median_yang_tersedia(self):
        """(item, hari) yang cuma ada di sebagian bulan → median nilai yang
        ada (bukan error)."""
        from waste_anomaly.period_history import typical_months
        a = _month("Juli", 31, [("R", "X", 10.0)])
        # X hanya ada di A; item baru W hanya di B
        b2 = _month("Agustus", 31, [("R", "W", 8.0)])
        typ = typical_months([a, b2])
        assert typ is not None
        keys = set(map(tuple, typ["agg"][["NAMA RESTO", "NAMA BARANG"]]
                       .to_numpy()))
        assert keys == {("R", "X"), ("R", "W")}


# ============================================================
# [6] BUKTI HARI vs BULAN LALU
# ============================================================

def _df_evidence() -> pd.DataFrame:
    data = {str(d): 3.0 for d in range(1, 31)}
    data["24"] = 819.0
    return pd.DataFrame([
        {"NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)",
         "JENIS": "WASTE", "KETERANGAN": "Cancel Nota",
         **data, "TOTAL": float(sum(data.values())),
         "ANOMALY STATUS": "Potensi Anomali", "ANOMALY SCORE": 9,
         "HARI TERSANGKA": 24.0, "NILAI HARI TERSANGKA": 819.0,
         "BUKTI HARI": "YES",
         "ALASAN HARI": "Hari 24: nilai 819 — 404x cabang lain (tipikal 2,0)"},
        {"NAMA RESTO": "R2", "NAMA BARANG": "TANPA HARI", "JENIS": "WASTE",
         "KETERANGAN": "x", **{str(d): 0.0 for d in range(1, 32)},
         "TOTAL": 0.0, "ANOMALY STATUS": "Perlu Review",
         "ANOMALY SCORE": 3, "HARI TERSANGKA": np.nan,
         "BUKTI HARI": "NO", "ALASAN HARI": ""},
    ])


class TestDayEvidenceVsHistory:
    def test_nilai_bulan_lalu_dan_rasio(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file)
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        out = day_evidence_vs_history(_df_evidence(), [bulan])
        row = out.iloc[0]
        assert row["NILAI BULAN LALU"] == 194.0
        assert abs(row["RASIO VS BULAN LALU"] - 819 / 194) < 0.01
        # baris tanpa hari tersangka tetap kosong
        assert pd.isna(out.iloc[1]["NILAI BULAN LALU"])

    def test_bulan_terbaru_dipakai_bukan_urutan_list(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file)
        juli = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH JULI 2026.xlsx")), {})
        # Agustus dgn nilai beda — harus dipakai meski posisi pertama
        ags = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")), {})
        agg = ags["agg"].copy()
        agg["24"] = 77.0
        agustus = dict(ags, agg=agg)
        out = day_evidence_vs_history(_df_evidence(), [agustus, juli])
        assert out.iloc[0]["NILAI BULAN LALU"] == 77.0  # 2026-08 > 2026-07

    def test_tipikal_beberapa_bulan(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file, typical_months)
        juli = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH JULI 2026.xlsx")), {})
        ags = load_history_file(str(_wb_bulan(
            tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")), {})
        agg = ags["agg"].copy()
        agg["24"] = 300.0
        agustus = dict(ags, agg=agg)
        typ = typical_months([juli, agustus])
        out = day_evidence_vs_history(_df_evidence(), [juli, agustus], typ)
        assert out.iloc[0]["TIPIKAL BEBERAPA BULAN"] == 247.0  # median(194,300)

    def test_alasan_ditambah_bila_rasio_kuat(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file)
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        out = day_evidence_vs_history(_df_evidence(), [bulan], config={})
        alasan = str(out.iloc[0]["ALASAN HARI"])
        assert "bulan lalu" in alasan
        assert "819" in alasan and "404x" in alasan  # bukti lama utuh
        # BUKTI HARI tidak diubah (golden count pipeline aman)
        assert (out["BUKTI HARI"] == _df_evidence()["BUKTI HARI"]).all()

    def test_alasan_tidak_ditambah_bila_rasio_lemah(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file)
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        df = _df_evidence()
        df.loc[0, "24"] = 250.0  # 250/194 = 1,29× < 3×
        df.loc[0, "NILAI HARI TERSANGKA"] = 250.0
        out = day_evidence_vs_history(df, [bulan], config={})
        assert "bulan lalu" not in str(out.iloc[0]["ALASAN HARI"])

    def test_threshold_bisa_diatur_config(self, tmp_path):
        from waste_anomaly.period_history import (
            day_evidence_vs_history, load_history_file)
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        df = _df_evidence()
        df.loc[0, "24"] = 250.0
        df.loc[0, "NILAI HARI TERSANGKA"] = 250.0
        out = day_evidence_vs_history(
            df, [bulan], config={"thresholds": {"TH_HARI_HIST_RATIO": 1.1}})
        assert "bulan lalu" in str(out.iloc[0]["ALASAN HARI"])

    def test_tanpa_pembanding_kolom_tetap_kosong(self):
        from waste_anomaly.period_history import day_evidence_vs_history
        out = day_evidence_vs_history(_df_evidence(), [])
        assert "NILAI BULAN LALU" in out.columns
        assert pd.isna(out["NILAI BULAN LALU"]).all()

    def test_df_kosong_dan_tanpa_kolom_hari(self):
        from waste_anomaly.period_history import day_evidence_vs_history
        out = day_evidence_vs_history(pd.DataFrame(), [])
        assert "NILAI BULAN LALU" in out.columns
        df = pd.DataFrame({"NAMA BARANG": ["X"], "HARI TERSANGKA": [3.0]})
        out = day_evidence_vs_history(df, [])
        assert pd.isna(out["NILAI BULAN LALU"]).all()


# ============================================================
# [7] PERSISTENSI DAFTAR FILE
# ============================================================

class TestPersistenceHistory:
    def test_round_trip(self, tmp_path):
        from waste_anomaly.period_history import (
            load_history_entries, save_history_entries)
        p = tmp_path / "history_files.json"
        entries = [{"path": "/a/AGUSTUS 2026.xlsx", "label": "Agustus 2026"},
                   {"path": "/b/juli.xlsx", "label": None}]
        assert save_history_entries(entries, p)
        loaded = load_history_entries(p)
        assert loaded == entries

    def test_file_tak_ada_list_kosong(self, tmp_path):
        from waste_anomaly.period_history import load_history_entries
        assert load_history_entries(tmp_path / "nope.json") == []

    def test_json_korup_dibackup_mulai_bersih(self, tmp_path):
        from waste_anomaly.period_history import load_history_entries
        p = tmp_path / "history_files.json"
        p.write_text("{ bukan json", encoding="utf-8")
        assert load_history_entries(p) == []
        assert list(tmp_path.glob("history_files.json.bak*"))

    def test_atomic_tidak_meninggalkan_tmp(self, tmp_path):
        from waste_anomaly.period_history import save_history_entries
        p = tmp_path / "history_files.json"
        save_history_entries([{"path": "/x.xlsx", "label": None}], p)
        assert not list(tmp_path.glob("*.tmp"))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "entries" in data

    def test_gitignore_menutup_store_user(self):
        src = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert "history_files.json" in src

    def test_path_store_frozen_aware(self, tmp_path, monkeypatch):
        from waste_anomaly import period_history as ph
        monkeypatch.setattr(ph, "is_frozen", lambda: True)
        monkeypatch.setattr(ph, "exe_dir", lambda: tmp_path)
        assert ph.history_store_path() == tmp_path / "history_files.json"
        monkeypatch.setattr(ph, "is_frozen", lambda: False)
        assert ph.history_store_path() == REPO / "history_files.json"


# ============================================================
# [8] HISTORYWORKER (penerus kontrak PeriodWorker wave1)
# ============================================================

class TestHistoryWorker:
    def test_key_akhir_pembanding_terdeteksi_bukan_31(self, tmp_path):
        """Penerus wave1 FIX 2: file dgn data s.d. hari 20 → key_akhir 20
        (bukan default 31) — normalisasi banding memakai hari asli."""
        _qapp()
        from ui.workers import HistoryWorker
        wb = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx", partial=True)
        results: list[list] = []
        failures: list[tuple] = []
        worker = HistoryWorker([{"path": str(wb), "label": None}], {})
        worker.done.connect(results.append)
        worker.failed.connect(lambda e, t: failures.append((e, t)))
        worker.run()  # sinkron — QThread.run() boleh dipanggil langsung
        assert not failures, failures
        assert results and len(results[0]) == 1
        assert results[0][0]["key_akhir"] == 20
        assert results[0][0]["error"] is None

    def test_cancel_sebelum_mulai(self, tmp_path):
        _qapp()
        from ui.workers import HistoryWorker
        wb = _wb_bulan(tmp_path)
        worker = HistoryWorker([{"path": str(wb), "label": None}], {})
        worker.cancel()
        results: list = []
        failures: list[tuple] = []
        worker.done.connect(results.append)
        worker.failed.connect(lambda e, t: failures.append((e, t)))
        worker.run()
        assert results == []
        assert failures and "dibatalkan" in failures[0][0]

    def test_file_gagal_tidak_menghentikan_lainnya(self, tmp_path):
        _qapp()
        from ui.workers import HistoryWorker
        wb_ok = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        wb_ok2 = _wb_bulan(tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")
        entries = [{"path": str(tmp_path / "hilang.xlsx"), "label": None},
                   {"path": str(wb_ok), "label": None},
                   {"path": str(wb_ok2), "label": None}]
        results: list = []
        worker = HistoryWorker(entries, {})
        worker.done.connect(results.append)
        worker.run()
        months = results[0]
        assert len(months) == 3
        assert months[0]["error"]  # file hilang → entri error
        assert months[1]["error"] is None
        assert months[2]["error"] is None

    def test_label_manual_override(self, tmp_path):
        _qapp()
        from ui.workers import HistoryWorker
        wb = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        results: list = []
        worker = HistoryWorker([{"path": str(wb), "label": "Bulan Tua"}], {})
        worker.done.connect(results.append)
        worker.run()
        assert results[0][0]["label"] == "Bulan Tua"
        assert results[0][0]["label_source"] == "manual"

    def test_worker_adalah_qthread_dan_bisa_dibatalkan(self):
        _qapp()
        from PySide6.QtCore import QThread
        from ui.workers import HistoryWorker
        assert issubclass(HistoryWorker, QThread)
        assert hasattr(HistoryWorker, "cancel")

    def test_path_hasil_tepat_spt_entri_nonkanonik(self, tmp_path):
        """v2.10.1 regresi (laporan user Windows): 'path' entri hasil
        HARUS string path entri input PERSIS — view mengunci status
        file, cache mtime, dan combo dgn kunci string itu. str(Path(x))
        menormalisasi pemisah ('C:/a' → 'C:\\a' di Windows; '/./' di
        Linux) → semua lookup meleset → status 'belum dimuat' padahal
        notif sukses."""
        _qapp()
        from ui.workers import HistoryWorker
        wb = _wb_bulan(tmp_path)
        weird = str(wb.parent) + "/./" + wb.name
        results: list = []
        failures: list[tuple] = []
        worker = HistoryWorker([{"path": weird, "label": None}], {})
        worker.done.connect(results.append)
        worker.failed.connect(lambda e, t: failures.append((e, t)))
        worker.run()
        assert not failures, failures
        assert results and results[0][0]["error"] is None
        assert results[0][0]["path"] == weird


# ============================================================
# [9] STATE HISTORY (AppContext)
# ============================================================

class TestStateHistory:
    def test_set_history_versi_dan_sinyal(self):
        _qapp()
        from ui.state import AppContext
        ctx = AppContext({})
        fired: list[int] = []
        ctx.history_ready.connect(lambda: fired.append(ctx.history_version))
        m = _month("Juli 2026", 31, [("R", "X", 5.0)])
        ctx.set_history([m], None)
        assert ctx.history_version == 1 and fired == [1]
        ctx.set_history([], None)
        assert ctx.history_version == 2

    def test_history_months_ok_menyaring_error(self):
        _qapp()
        from ui.state import AppContext
        ctx = AppContext({})
        ok = _month("Juli 2026", 31, [("R", "X", 5.0)])
        bad = {"label": "??", "error": "File tidak ditemukan", "agg": None}
        ctx.set_history([ok, bad], None)
        assert ctx.history_months_ok() == [ok]


# ============================================================
# [10] PERIODEVIEW MULTI-FILE (UI offscreen)
# ============================================================

def _make_periode_view(monkeypatch, tmp_path, entries):
    """PeriodeView dgn store diarahkan ke tmp (tidak menyentuh repo root)."""
    _qapp()
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    from waste_anomaly import period_history as ph
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    ph.save_history_entries(entries, store)
    ctx = AppContext({})
    view = PeriodeView(ctx)
    return view, ctx, store


def _wait_worker(view, app, timeout_s: float = 30.0) -> None:
    t0 = time.perf_counter()
    while view._running:
        app.processEvents()
        time.sleep(0.01)
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("worker pembanding tidak selesai")


class TestPeriodeViewMultiFile:
    def test_auto_muat_tersimpan_dan_tipikal(self, tmp_path, monkeypatch):
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        wb2 = _wb_bulan(tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path,
            [{"path": str(wb1), "label": None},
             {"path": str(wb2), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        # kontrak: 2 bulan termuat + tipikal; render (on_shown path) →
        # combo Terisi SEBELUM data A ada (combo tak menunggu pipeline).
        assert len(ctx.history_months) == 2
        assert ctx.history_typical is not None
        view._refresh_result()
        assert view._cb_b.count() == 3
        assert "Tipikal" in view._cb_b.currentText()
        # tanpa data A → tabel kosong + pesan jelas (bukan crash)
        assert "pipeline" in view._lbl_compare.text().lower()

    def test_banding_render_dgn_data_a(self, tmp_path, monkeypatch):
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path, [{"path": str(wb1), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        # A = bulan berjalan sintetis (bentuk df pipeline)
        data = {str(d): 3.0 for d in range(1, 31)}
        data["24"] = 819.0
        df = pd.DataFrame([
            {"NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)",
             "JENIS": "WASTE", "KETERANGAN": "Cancel Nota",
             **data, "TOTAL": float(sum(data.values()))}])
        ctx.set_dataset(df, {"key_akhir": 30, "total_rows": 1})
        view._refresh_result()
        assert view._tables["summary"]._model.rowCount() == 5
        # 1 bulan → tanpa Tipikal; combo = bulan itu, default = bulan itu
        assert view._cb_b.count() == 1
        assert view._cb_b.currentText() == "Juli 2026"
        items = view._tables["items"]._model.dataframe
        mie = items[items["NAMA BARANG"] == "MIE (V.20)"].iloc[0]
        # total Juli MIE = (100 + 2×30 hari biasa) + 94 = 254
        assert mie["Pembanding"] == 254.0
        assert "Juli 2026" in view._lbl_compare.text()

    def test_combo_ganti_bulan_rerender(self, tmp_path, monkeypatch):
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        wb2 = _wb_bulan(tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path,
            [{"path": str(wb1), "label": None},
             {"path": str(wb2), "label": None}])
        app = _qapp()
        view.show()
        app.processEvents()
        _wait_worker(view, app)
        df = pd.DataFrame([
            {"NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "MIE (V.20)",
             "JENIS": "WASTE", "KETERANGAN": "x",
             **{str(d): 1.0 for d in range(1, 32)}, "TOTAL": 31.0}])
        ctx.set_dataset(df, {"key_akhir": 31, "total_rows": 1})
        view._refresh_result()
        view._cb_b.setCurrentIndex(2)  # Agustus (Tipikal=0, Juli=1)
        app.processEvents()
        assert "Agustus 2026" in view._lbl_compare.text()

    def test_edit_label_tersimpan_dan_combo_sinkron(self, tmp_path,
                                                    monkeypatch):
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx, store = _make_periode_view(
            monkeypatch, tmp_path, [{"path": str(wb1), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        # simulasi klik-2× → dialog "Juni 2026"
        monkeypatch.setattr(
            "ui.view_periode.QInputDialog.getText",
            staticmethod(lambda *a, **k: ("Juni 2026", True)))
        view._on_double(view._tbl_files.model().index(0, 0))
        assert view._entries[0]["label"] == "Juni 2026"
        saved = json.loads(store.read_text(encoding="utf-8"))["entries"]
        assert saved[0]["label"] == "Juni 2026"
        view._refresh_result()
        assert view._cb_b.currentText() == "Juni 2026"

    def test_hapus_entri(self, tmp_path, monkeypatch):
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        wb2 = _wb_bulan(tmp_path, "REKAP MENTAH AGUSTUS 2026.xlsx")
        view, ctx, store = _make_periode_view(
            monkeypatch, tmp_path,
            [{"path": str(wb1), "label": None},
             {"path": str(wb2), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        view._tbl_files.selectRow(0)
        view._on_delete()
        assert len(view._entries) == 1
        saved = json.loads(store.read_text(encoding="utf-8"))["entries"]
        assert len(saved) == 1 and "AGUSTUS" in saved[0]["path"]
        assert len(ctx.history_months) == 1

    def test_file_error_ditandai_bukan_menggagalkan(self, tmp_path,
                                                    monkeypatch):
        wb_ok = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path,
            [{"path": str(tmp_path / "hilang.xlsx"), "label": None},
             {"path": str(wb_ok), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        assert view._tbl_files.item(0, 2).text().startswith("✗")
        assert view._tbl_files.item(1, 2).text().startswith("✓")
        assert len(ctx.history_months_ok()) == 1
        assert "gagal" in view._lbl_status.text()

    def test_reload_pakai_cache_mtime(self, tmp_path, monkeypatch):
        """File tak berubah → tidak dimuat ulang (worker kosong → finalize
        langsung) — jaminan anti-lemat saat menambah file baru."""
        wb1 = _wb_bulan(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path, [{"path": str(wb1), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        assert len(ctx.history_months) == 1
        view._on_reload()  # tanpa clear cache → todo kosong → finalize saja
        _wait_worker(view, app, timeout_s=5)
        assert view._btn_run.isEnabled()
        assert len(ctx.history_months) == 1
        # file BERUBAH (mtime baru) → dimuat ulang
        time.sleep(0.02)
        wb1.touch()
        view._on_reload()
        _wait_worker(view, app)
        assert len(ctx.history_months) == 1

    def test_status_file_bukan_belum_dimuat_path_nonkanonik(
            self, tmp_path, monkeypatch):
        """v2.10.1 regresi (persis laporan user): pilih file pembanding
        → muat → notif '✓ berhasil' TAPI kolom Status masih
        '⏳ belum dimuat'. Sebab: hasil worker dikunci path ternormalisasi
        str(Path(...)) sementara daftar file mengunci string path dialog
        (Windows: '/' ≠ '\\'). Reproduksi Linux: path dgn '/./' —
        kelas mismatch identik. Fix: loader mempertahankan string input."""
        wb = _wb_bulan(tmp_path)
        weird = str(wb.parent) + "/./" + wb.name
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path, [{"path": weird, "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        # gejala user: baris tetap 'belum dimuat' padahal muat sukses
        assert view._tbl_files.item(0, 2).text().startswith("✓"), \
            view._tbl_files.item(0, 2).text()
        assert "aktif" in view._lbl_status.text()  # notif = jujur sekarang
        # konsekuensi tersembunyi bug: combo & banding ikut kosong →
        # pastikan bulan masuk combo (fitur banding benar-benar jalan)
        assert len(ctx.history_months_ok()) == 1
        view._refresh_result()
        assert view._cb_b.count() == 1
        assert view._cb_b.currentText() == "Juli 2026"

    def test_notif_gagal_bila_tak_ada_bulan_aktif(self, tmp_path, monkeypatch):
        """v2.10.1: semua file gagal → status bar '⚠' (bukan '✓ siap')
        supaya notif tidak menyesatkan."""
        view, ctx, _ = _make_periode_view(
            monkeypatch, tmp_path,
            [{"path": str(tmp_path / "hilang.xlsx"), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        assert view._lbl_status.text().startswith("⚠")
        assert len(ctx.history_months_ok()) == 0

    def test_kontrak_lazy_render_dan_busy(self):
        src = (UI / "view_periode.py").read_text(encoding="utf-8")
        assert "def refresh(" in src and "def on_shown(" in src
        assert "busy_feedback(" in src
        assert "_running" in src and "_worker" in src  # closeEvent guard


# ============================================================
# [11] HARI VIEW + BUKTI BULAN LALU
# ============================================================

def _hari_df_v2100() -> pd.DataFrame:
    return _df_evidence()


class TestHariViewHistory:
    def _view(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_hari import HariView
        ctx = AppContext({})
        view = HariView(ctx)
        ctx.set_dataset(_hari_df_v2100(), {"key_akhir": 31})
        return view, ctx

    def test_kolom_bulan_lalu_muncul(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        view, ctx = self._view()
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        ctx.set_history([bulan], None)
        view._refresh_table()
        df = view._table._model.dataframe
        assert "NILAI BULAN LALU" in df.columns
        assert "RASIO VS BULAN LALU" in df.columns
        assert df.iloc[0]["NILAI BULAN LALU"] == 194.0

    def test_tanpa_pembanding_kolom_hilang(self):
        view, _ = self._view()
        view._refresh_table()
        df = view._table._model.dataframe
        assert "NILAI BULAN LALU" not in df.columns

    def test_set_history_merender_ulang_bila_terlihat(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        view, ctx = self._view()
        view.show()
        _qapp().processEvents()
        view._refresh_table()
        assert "NILAI BULAN LALU" not in view._table._model.dataframe.columns
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        ctx.set_history([bulan], None)  # sinyal → render ulang otomatis
        _qapp().processEvents()
        assert "NILAI BULAN LALU" in view._table._model.dataframe.columns

    def test_memo_objek_sama_antar_refresh(self, tmp_path):
        """Anti-lemat: df bukti bulan-lalu di-memo — refresh ulang tanpa
        filter baru memakai objek SAMA (cache fit DataTable kena)."""
        from waste_anomaly.period_history import load_history_file
        view, ctx = self._view()
        bulan = load_history_file(str(_wb_bulan(tmp_path)), {})
        ctx.set_history([bulan], None)
        view._refresh_table()
        df1 = view._table._model.dataframe
        view._refresh_table()
        df2 = view._table._model.dataframe
        assert df1 is df2

    def test_tabel_cols_kontrak_v2100(self):
        from ui.view_hari import TABLE_COLS
        for col in ("NILAI BULAN LALU", "RASIO VS BULAN LALU",
                    "TIPIKAL BEBERAPA BULAN"):
            assert col in TABLE_COLS


# ============================================================
# [12] ISTILAH & FORMAT KOLOM BARU (kebijakan v2.9.0)
# ============================================================

class TestIstilahV2100:
    def test_kamus_tooltip_kolom_baru(self):
        from ui.models import COLUMN_TOOLTIPS
        for col in ("NILAI BULAN LALU", "RASIO VS BULAN LALU",
                    "TIPIKAL BEBERAPA BULAN", "Bulan Ini", "Pembanding",
                    "Selisih", "Perubahan %"):
            tip = COLUMN_TOOLTIPS.get(col)
            assert tip and len(tip) > 10, f"{col} tanpa tooltip"

    def test_rasio_bulan_lalu_format_kali_lipat(self):
        from ui.models import RATIO_X_COLS, fmt_ratio_x
        assert "RASIO VS BULAN LALU" in RATIO_X_COLS
        assert fmt_ratio_x(4.16) == "4,2×"

    def test_kolom_baru_rata_kanan_numerik(self):
        from ui.models import _NUM_COLS
        for col in ("NILAI BULAN LALU", "TIPIKAL BEBERAPA BULAN",
                    "Perubahan %"):
            assert col in _NUM_COLS

    def test_config_ambang_hari_hist(self):
        cfg = json.loads((REPO / "waste_anomaly" / "config.json")
                         .read_text(encoding="utf-8"))
        assert cfg["thresholds"]["TH_HARI_HIST_RATIO"] == 3.0


# ============================================================
# [13] GOLDEN — DATA ASLI (skip bila file tidak ada)
# ============================================================

@pytest.mark.skipif(not PEM_REAL.exists(), reason="file pembanding asli tidak ada")
class TestGoldenPembandingAsli:
    def test_muat_agustus_asli(self):
        from waste_anomaly.period_history import load_history_file
        res = load_history_file(str(PEM_REAL), {})
        assert res["error"] is None, res["error"]
        assert res["label"] == "Agustus 2026"
        assert res["key_akhir"] == 31
        agg = res["agg"]
        row = agg[(agg["NAMA BARANG"] == "MIE (V.20)")
                  & (agg["NAMA RESTO"] == "1042.KWGGAL")].iloc[0]
        # Golden bukti Task 9: hari-24 = 194 (saringan waste), bukan 43.115
        assert row["24"] == 194.0
        assert row["TOTAL"] == 1424.0
        assert res["item_count"] >= 150

    @pytest.mark.skipif(not MAIN_REAL.exists(),
                        reason="DATA_WASTE.xlsx tidak ada")
    def test_bukti_mie_antar_bulan_asli(self):
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.period_history import (
            aggregate_current, day_evidence_vs_history, load_history_file)
        summary = run_pipeline(str(MAIN_REAL), key_akhir=30)
        assert summary.get("success"), summary.get("error")
        a = aggregate_current(summary["df"], 30)
        assert a is not None
        mie = a["agg"][(a["agg"]["NAMA BARANG"] == "MIE (V.20)")
                       & (a["agg"]["NAMA RESTO"] == "1042.KWGGAL")].iloc[0]
        assert mie["24"] == 819.0
        bulan = load_history_file(str(PEM_REAL), {})
        sub = summary["df"][
            (summary["df"]["NAMA BARANG"] == "MIE (V.20)")
            & (summary["df"]["NAMA RESTO"] == "1042.KWGGAL")
            & (summary["df"]["ANOMALY STATUS"] != "Normal")
            & (summary["df"]["HARI TERSANGKA"] == 24)
        ].head(1)
        assert len(sub) == 1
        out = day_evidence_vs_history(sub, [bulan], config={})
        row = out.iloc[0]
        assert row["NILAI HARI TERSANGKA"] == 808.0  # golden v2.9.0
        assert row["NILAI BULAN LALU"] == 194.0
        assert abs(row["RASIO VS BULAN LALU"] - 808 / 194) < 0.01
        assert "bulan lalu" in str(row["ALASAN HARI"])
        # bukti 404x cabang lain tetap utuh (tidak tergantikan)
        assert "404x" in str(row["ALASAN HARI"])
