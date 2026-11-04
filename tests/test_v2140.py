"""test_v2140.py — fitur v2.14.0: OLAH REKAP MENTAH (menggantikan olahan
manual Excel user; perintah user: "Jadi nanti aku tinggal pilih file
REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR excel nanti python olahin jadi
data waste atau yaudah olah sesuai kebutuhan data").

Modul baru waste_anomaly/rekap_import.py + tombol UI "🧮 Olah REKAP
MENTAH…" (tab Pipeline, worker background RekapImportWorker). Struktur
diturunkan dari analisis file asli user (REKAP MENTAH 54.160 baris × 42
kolom berisi SEMUA JENIS; DATA_WASTE.xlsx standar 25.901 × 53) + mirror
fn_rekap_mentah.py repo stock-monitoring (deteksi schema + promote
header) + fn_2205.py = sumber query "2  22 05" (BOM master) di M code.

[RIMP-1]  find_rekap_sheet: kandidat config token-match sheet "REKAP
          MENTAH" (nama sheet file user asli — varian spasi; kandidat
          config memakai "Rekap Mentah"/"REKAP_MENTAH").
[RIMP-2]  Fallback deteksi schema: sheet beda nama + header TERGESER
          (baris judul di atas header — pola fn_rekap_mentah) tetap
          terbaca; kandidat bernama-sama-tapi-beda-isi tidak dipakai
          mentah-mentah (validasi schema dulu).
[RIMP-3]  Konversi: saring JENIS W/S/T (case/whitespace-toleran),
          baris BOM/SO/BARANG MASUK/STOK AWAL dibuang; 53 kolom urutan
          standar README; identity passthrough di-strip; NaN KETERANGAN
          tetap None (bukan "nan").
[RIMP-4]  Kolom hitungan semantika stage_02: TOTAL=sum hari, AVG=mean
          skipna, MAX=max, Count Hari=count>0, Status2 Kosong/Isi.
[RIMP-5]  BOM dua arah: baris JENIS=="BOM" → (a) kolom inline TOTAL BOM
          (prioritas stage_05 v2.3.0) + (b) sheet "BOM" (Nomor #/Nama
          Barang/TOTAL BOM — kandidat loader); join key _key_str dua
          sisi (outlet numerik "1049.0" → "1049").
[RIMP-6]  % to BOM & Rill % to BOM di-guard TOTAL BOM>0 (semantika
          stage_05); baris tanpa BOM = 0 (bukan NaN/div0).
[RIMP-7]  DATABASE_SATUAN: sheet sumber DISALIN bila ada; tanpa sheet =
          tanpa sheet output (loader toleran).
[RIMP-8]  Nama output default dari label bulan nama file ("REKAP MENTAH_
          01-31 AGUSTUS 2026_TEGAR" → "DATA_WASTE Agustus 2026.xlsx" —
          banding periode bisa mem-parse bulannya kembali) + guard anti
          menimpa file SUMBER + tolak out_path == source eksplisit.
[RIMP-9]  Error ramah (RekapImportError): file hilang / sheet rekap tak
          ada / kolom wajib hilang / tanpa baris W-S-T / file .xls.
[RIMP-10] END-TO-END: workbook hasil olahan → run_pipeline HIJAU (loader
          menemukan sheet DATA_WASTE + BOM; TOTAL BOM inline bertahan
          melewati stage_01; Rill % to BOM dihitung; prioritas > 0).
[RIMP-11] File asli user (skip-if-missing): 54.160 → 25.722 baris
          (WASTE 18.771 · SUSUT 2.204 · TRIAL 4.747 — angka GOLDEN dari
          analisis file asli) + 2.369 pasangan BOM.
[RIMP-12] Worker QThread: RekapImportWorker done→dict ringkasan / failed
          →(pesan, traceback); subclass QThread (kontrak test_ui_structure).
[RIMP-13] UI: tombol 🧮 ada + alur penuh (dialog → worker → kolom
          workbook terisi + log ringkasan + status ok + tombol pulih);
          klik saat pipeline berjalan = tolak ramah; gagal → dialog
          kritis + tombol pulih + log.
[RIMP-14] Manifest dua-arah: workers.py::RekapImportWorker terdaftar;
          Bantuan F1 menyebut tombol; versi 2.14.0 sinkron semua situs.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import pytest

# Offscreen SEBELUM import PySide6 (kontrak suite).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
REAL_REKAP = REPO / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx"

_DAYS = [str(d) for d in range(1, 32)]


def _qapp():
    import sys
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# FIXTURES — workbook rekap mentah sintetis (kecil, cepat)
# ============================================================

def _row(resto, item, jenis, ket, satuan, days, source="WASTE BAHAN DAN PACKAGING"):
    vals = {str(d): 0 for d in range(1, 32)}
    for d, v in (days or {}).items():
        vals[str(d)] = v
    return {
        "KATEGORI": "COM DEVIASI - RESTO", "SOURCE DATA": source,
        "JENIS": jenis, "STATUS": "DEVIASI", "NAMA BARANG": item,
        "KETERANGAN": ket, "PENYEBAB TERJADINYA WASTE": item,
        "SATUAN": satuan, **vals, "NAMA RESTO": resto, "PIC": "TEGAR",
        "TOTAL": float(sum(vals.values())),
    }


def _synthetic_rows():
    """6 baris W/S/T + 4 baris non-waste (BOM×2, SO, BARANG MASUK)."""
    return [
        # (resto, item, jenis, keterangan, satuan, hari-nonzero)
        _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR", {1: 10, 5: 30}),
        _row("1041.BDGUKU", "ITEM X", "WASTE", "Handling", "GR ", {}),
        _row("1041.BDGUKU", "ITEM X", "WASTE", None, "GR", {2: 4}),   # NaN keterangan
        _row("1041.BDGUKU", "ITEM X", "TRIAL", "TRIAL", "GR", {3: 5}),
        _row("1042.KWGGAL", "ITEM Y", "SUSUT", "SUSUT", "GR", {4: 7}),
        _row("1042.KWGGAL", "ITEM Y", "waste ", "Over Stock", "GR", {}),  # case+spasi
        # non-waste — harus DIBUANG dari DATA_WASTE…
        _row("1041.BDGUKU", "ITEM X", "BOM", "BOM", "GR",
             {d: 100 for d in range(1, 11)}),          # BOM total 1000
        _row("1042.KWGGAL", "ITEM Y", "BOM", "BOM", "GR", {1: 250}),
        _row("1041.BDGUKU", "ITEM X", "SO", "SO", "GR", {1: 999}),
        _row("1041.BDGUKU", "ITEM X", "BARANG MASUK", None, "GR", {1: 5}),
    ]


def _build_rekap(path: Path, sheet_name="REKAP MENTAH",
                 rows=None, satuan_rows=None):
    """Tulis workbook rekap mentah sintetis (+DATABASE_SATUAN opsional)."""
    rows = _synthetic_rows() if rows is None else rows
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet_name, index=False)
        if satuan_rows is not None:
            pd.DataFrame(satuan_rows).to_excel(
                w, sheet_name="DATABASE_SATUAN", index=False)
    return path


def _build_rekap_shifted(path: Path):
    """Workbook ber-baris judul pra-header: baris 1 judul, baris 2 kosong,
    baris 3 header rekap, baris 4+ data (header=None → tulis mentah)."""
    rows = _synthetic_rows()
    df = pd.DataFrame(rows)
    n_cols = len(df.columns)
    head = ["REKAP WASTE BULANAN"] + [None] * (n_cols - 1)
    blank = [None] * n_cols
    data = [list(r.values()) for r in rows]
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        frame = pd.DataFrame([head, blank, list(df.columns)] + data)
        frame.to_excel(w, sheet_name="Rekap Februari", index=False,
                       header=False)
    return path


# ============================================================
# [RIMP-1]/[RIMP-2] — find_rekap_sheet
# ============================================================

class TestFindRekapSheet:

    def test_kandidat_token_match_spasi(self, tmp_path):
        """Sheet 'REKAP MENTAH' (spasi — nama file user asli) ketemu lewat
        kandidat config 'Rekap Mentah' fase TOKEN (loader.find_sheet)."""
        from waste_anomaly.rekap_import import find_rekap_sheet
        from waste_anomaly.utils import load_config
        src = _build_rekap(tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
        sheet, hr = find_rekap_sheet(src, load_config())
        assert (sheet, hr) == ("REKAP MENTAH", 0)

    def test_fallback_deteksi_schema_header_tergeser(self, tmp_path):
        """Sheet beda nama + 2 baris judul pra-header → deteksi schema
        menemukan header baris 3 (pola fn_rekap_mentah stock-monitoring)."""
        from waste_anomaly.rekap_import import find_rekap_sheet
        from waste_anomaly.utils import load_config
        src = _build_rekap_shifted(tmp_path / "rekap_shifted.xlsx")
        sheet, hr = find_rekap_sheet(src, load_config())
        assert sheet == "Rekap Februari"
        assert hr == 2  # 0-based: baris ke-3 = header

    def test_kandidat_tanpa_schema_dilewati_ke_fallback(self, tmp_path):
        """Sheet bernama cocok kandidat TAPI tak ber-schema rekap (mis.
        'Sheet1' berisi apa pun) → tidak dipakai mentah-mentah; scan
        menemukan sheet rekap yang benar."""
        from waste_anomaly.rekap_import import find_rekap_sheet
        src = tmp_path / "mixed.xlsx"
        rows = _synthetic_rows()
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(src, engine="openpyxl") as w:
            pd.DataFrame({"Foo": [1, 2]}).to_excel(
                w, sheet_name="Sheet1", index=False)  # kandidat ke-4 config
            df.to_excel(w, sheet_name="DATA", index=False)  # sheet rekap
        from waste_anomaly.utils import load_config
        sheet, hr = find_rekap_sheet(src, load_config())
        assert sheet == "DATA"

    def test_tanpa_sheet_rekap_error_ramah(self, tmp_path):
        from waste_anomaly.rekap_import import RekapImportError, find_rekap_sheet
        src = tmp_path / "bukan_rekap.xlsx"
        pd.DataFrame({"A": [1]}).to_excel(src, index=False)
        with pytest.raises(RekapImportError, match="Sheet REKAP MENTAH"):
            find_rekap_sheet(src, {})


# ============================================================
# [RIMP-3]/[RIMP-4]/[RIMP-5]/[RIMP-6] — konversi inti
# ============================================================

class TestConvertCore:

    @pytest.fixture()
    def converted(self, tmp_path):
        from waste_anomaly.rekap_import import convert_rekap_mentah
        src = _build_rekap(tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
        out = tmp_path / "out.xlsx"
        result = convert_rekap_mentah(str(src), out_path=str(out))
        dw = pd.read_excel(out, sheet_name="DATA_WASTE")
        bom = pd.read_excel(out, sheet_name="BOM")
        return result, dw, bom

    def test_saring_jenis_53_kolom_urutan_standar(self, converted):
        result, dw, bom = converted
        # 6 baris W/S/T lolos; BOM/SO/BARANG MASUK dibuang
        assert len(dw) == 6
        assert result["rows_kept"] == 6
        assert result["rows_raw"] == 10
        assert set(dw["JENIS"].unique()) == {"WASTE", "SUSUT", "TRIAL"}
        # Urutan 53 kolom standar README (15 identitas+hitungan + 31 hari + 7 ekor)
        expected = (["STATUS", "HELPER", "MAX TOTAL", "AVG TOTAL", "TOTAL BOM",
                     "% to BOM", "TOTAL", "AVG", "MAX", "SOURCE DATA", "JENIS",
                     "KETERANGAN", "NAMA BARANG", "NAMA RESTO", "SATUAN"]
                    + _DAYS
                    + ["Status2", "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR",
                       "SOURCE DATA GABUNGAN", "Count Hari", "RANGKING WASTE",
                       "Rill % to BOM"])
        assert list(dw.columns) == expected, "urutan kolom bukan standar 53"

    def test_identity_passthrough_strip_dan_nan(self, converted):
        _, dw, _ = converted
        # SATUAN 'GR ' (trailing space) di-strip — pola fn_rekap_mentah
        assert set(dw["SATUAN"].unique()) == {"GR"}
        # JENIS 'waste ' (case+spasi) dinormalisasi
        assert "waste " not in set(dw["JENIS"].unique())
        # KETERANGAN NaN tetap kosong (bukan string 'nan')
        ket_vals = set(dw["KETERANGAN"].dropna().unique())
        assert "nan" not in ket_vals
        assert dw["KETERANGAN"].isna().sum() == 1  # baris keterangan None

    def test_statistik_semantika_stage02(self, converted):
        _, dw, _ = converted
        row_x_kualitas = dw[(dw["NAMA BARANG"] == "ITEM X")
                            & (dw["KETERANGAN"] == "Kualitas")].iloc[0]
        assert row_x_kualitas["TOTAL"] == 40.0          # 10 + 30
        assert row_x_kualitas["MAX"] == 30.0
        assert row_x_kualitas["Count Hari"] == 2        # hari > 0
        assert abs(row_x_kualitas["AVG"] - 40.0 / 31) < 1e-9  # mean(skipna) 31 hari
        assert row_x_kualitas["Status2"] == "Isi"
        # Baris all-zero → Kosong
        row_zero = dw[(dw["KETERANGAN"] == "Handling")
                      & (dw["NAMA BARANG"] == "ITEM X")].iloc[0]
        assert row_zero["Status2"] == "Kosong"
        assert row_zero["Count Hari"] == 0
        assert row_zero["TOTAL"] == 0

    def test_bom_inline_prioritas_stage05(self, converted):
        _, dw, _ = converted
        row_x = dw[(dw["NAMA BARANG"] == "ITEM X")
                   & (dw["KETERANGAN"] == "Kualitas")].iloc[0]
        # ITEM X @1041.BDGUKU: BOM 10 hari × 100 = 1000
        assert row_x["TOTAL BOM"] == 1000.0
        assert abs(row_x["% to BOM"] - 40.0 / 1000) < 1e-9
        assert abs(row_x["Rill % to BOM"] - 40.0 / 1000) < 1e-9
        row_y = dw[(dw["NAMA BARANG"] == "ITEM Y")
                   & (dw["KETERANGAN"] == "SUSUT")].iloc[0]
        assert row_y["TOTAL BOM"] == 250.0
        assert abs(row_y["% to BOM"] - 7.0 / 250) < 1e-9

    def test_bom_sheet_tulis_kandidat_loader(self, converted):
        _, dw, bom = converted
        # Sheet BOM: kolom kontrak loader (Nomor #/Nama Barang/TOTAL BOM)
        assert list(bom.columns) == ["Nomor #", "Nama Barang", "TOTAL BOM"]
        assert len(bom) == 2  # (1041.BDGUKU, ITEM X) + (1042.KWGGAL, ITEM Y)
        got = {(r["Nomor #"], r["Nama Barang"]): r["TOTAL BOM"]
               for _, r in bom.iterrows()}
        assert got[("1041.BDGUKU", "ITEM X")] == 1000.0
        assert got[("1042.KWGGAL", "ITEM Y")] == 250.0

    def test_bom_tak_match_guard_nol(self, tmp_path):
        """Baris data tanpa pasangan BOM → TOTAL BOM kosong (None cell),
        % to BOM = 0 (bukan NaN/div0) — semantika stage_05 guard."""
        from waste_anomaly.rekap_import import convert_rekap_mentah
        rows = [_row("999.NO BOM", "ITEM Q", "WASTE", "Kualitas", "GR", {1: 3})]
        src = _build_rekap(tmp_path / "r.xlsx", rows=rows)
        out = tmp_path / "o.xlsx"
        convert_rekap_mentah(str(src), out_path=str(out))
        dw = pd.read_excel(out, sheet_name="DATA_WASTE")
        assert pd.isna(dw["TOTAL BOM"].iloc[0])
        assert dw["% to BOM"].iloc[0] == 0
        assert dw["Rill % to BOM"].iloc[0] == 0

    def test_kolom_output_mcode_dibiarkan_kosong(self, converted):
        """STATUS/HELPER/MAX TOTAL/AVG TOTAL/GABUNGAN/RANGKING = output
        M-code user — pipeline menghitung ulang; dikosongkan jujur."""
        _, dw, _ = converted
        for col in ("STATUS", "HELPER", "MAX TOTAL", "AVG TOTAL",
                    "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR",
                    "SOURCE DATA GABUNGAN", "RANGKING WASTE"):
            assert dw[col].isna().all(), f"{col} seharusnya kosong"


# ============================================================
# [RIMP-7] — DATABASE_SATUAN disalin
# ============================================================

class TestSatuanCopy:

    def test_sheet_satuan_disalin(self, tmp_path):
        from waste_anomaly.rekap_import import convert_rekap_mentah
        satuan_rows = [{"NAMA ITEM": "ITEM X", "SUSUT": 1, "HANDLING": 2}]
        src = _build_rekap(tmp_path / "r.xlsx", satuan_rows=satuan_rows)
        out = tmp_path / "o.xlsx"
        result = convert_rekap_mentah(str(src), out_path=str(out))
        xl = pd.ExcelFile(out)
        assert "DATABASE_SATUAN" in xl.sheet_names
        sat = pd.read_excel(out, sheet_name="DATABASE_SATUAN")
        assert sat["NAMA ITEM"].iloc[0] == "ITEM X"
        assert result["satuan_sheet"] == "DATABASE_SATUAN"

    def test_tanpa_satuan_tanpa_sheet(self, tmp_path):
        from waste_anomaly.rekap_import import convert_rekap_mentah
        src = _build_rekap(tmp_path / "r.xlsx")
        out = tmp_path / "o.xlsx"
        result = convert_rekap_mentah(str(src), out_path=str(out))
        xl = pd.ExcelFile(out)
        assert "DATABASE_SATUAN" not in xl.sheet_names
        assert result["satuan_sheet"] is None


# ============================================================
# [RIMP-8] — nama output default + guard anti menimpa
# ============================================================

class TestOutPath:

    def test_default_nama_dari_label_bulan(self, tmp_path):
        """'REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx' → 'DATA_WASTE
        Agustus 2026.xlsx' di folder sumber (label parse-able banding)."""
        from waste_anomaly.rekap_import import convert_rekap_mentah
        src = _build_rekap(tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
        result = convert_rekap_mentah(str(src))
        assert Path(result["out_path"]) == tmp_path / "DATA_WASTE Agustus 2026.xlsx"
        assert result["month_label"] == "Agustus 2026"
        assert Path(result["out_path"]).exists()

    def test_guard_anti_menimpa_sumber(self, tmp_path):
        """Sumber kebetulan bernama persis output default → suffix
        '(olah)' — file sumber tidak pernah ditimpa."""
        from waste_anomaly.rekap_import import convert_rekap_mentah
        src = _build_rekap(tmp_path / "DATA_WASTE Agustus 2026.xlsx")
        result = convert_rekap_mentah(str(src))
        assert Path(result["out_path"]).name == "DATA_WASTE Agustus 2026 (olah).xlsx"
        # sumber masih utuh (10 baris mentah)
        raw = pd.read_excel(src, sheet_name="REKAP MENTAH")
        assert len(raw) == 10

    def test_tolak_out_path_sama_dengan_sumber(self, tmp_path):
        from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
        src = _build_rekap(tmp_path / "r.xlsx")
        with pytest.raises(RekapImportError, match="menimpa"):
            convert_rekap_mentah(str(src), out_path=str(src))


# ============================================================
# [RIMP-9] — error ramah
# ============================================================

class TestErrorsRamah:

    def test_file_hilang(self):
        from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
        with pytest.raises(RekapImportError, match="tidak ditemukan"):
            convert_rekap_mentah("/tmp/tidak_ada_12345.xlsx")

    def test_kolom_wajib_hilang(self, tmp_path):
        """KETERANGAN dihapus dari rekap → pesan menyebut kolom hilang
        (file output harus selalu lolos validate_rekap_schema)."""
        from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
        rows = _synthetic_rows()
        df = pd.DataFrame(rows).drop(columns=["KETERANGAN"])
        src = tmp_path / "r.xlsx"
        df.to_excel(src, sheet_name="REKAP MENTAH", index=False)
        with pytest.raises(RekapImportError, match="KETERANGAN"):
            convert_rekap_mentah(str(src), out_path=str(tmp_path / "o.xlsx"))

    def test_tanpa_baris_waste(self, tmp_path):
        """Rekap hanya berisi SO/BOM → tidak ada data waste → error jujur
        (bukan file kosong diam-diam)."""
        from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
        rows = [_row("A", "ITEM X", "SO", "SO", "GR", {1: 1}),
                _row("A", "ITEM X", "BOM", "BOM", "GR", {1: 1})]
        src = _build_rekap(tmp_path / "r.xlsx", rows=rows)
        with pytest.raises(RekapImportError, match="Tidak ada baris"):
            convert_rekap_mentah(str(src), out_path=str(tmp_path / "o.xlsx"))

    def test_file_xls_ditolak_ramah(self, tmp_path):
        from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
        src = tmp_path / "lama.xls"
        src.write_bytes(b"dummy")
        with pytest.raises(RekapImportError, match=r"\.xls"):
            convert_rekap_mentah(str(src))


# ============================================================
# [RIMP-10] — END-TO-END: hasil olahan → pipeline penuh
# ============================================================

class TestEndToEndPipeline:

    def test_run_pipeline_pada_file_olahan(self, tmp_path):
        """JANJI INTI fitur: file mentah → olah → Mulai Pipeline langsung
        hijau; TOTAL BOM inline bertahan melewati stage_01 (dipakai
        stage_05); Rill % to BOM dihitung; ada baris prioritas."""
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.rekap_import import convert_rekap_mentah
        src = _build_rekap(tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
        result = convert_rekap_mentah(str(src))
        summary = run_pipeline(result["out_path"], key_akhir=31)
        df = summary["df"]
        assert summary["total_rows"] == 6
        assert int(df["TOTAL BOM"].notna().sum()) == 6  # semua baris ber-BOM
        assert (df["Rill % to BOM"] > 0).any()
        # Spike 30 di hari-5 (vs rata-rata 40/31) tertangkap engine:
        # 1 baris Perlu Review di data sintetis mini (Prioritas butuh
        # skor ≥ STATUS_PRIORITAS=8 — data 6 baris tak sampai; flag
        # review membuktikan deteksi jalan ujung-ke-ujung).
        assert summary["review_count"] == 1

    def test_loader_menemukan_sheet_kandidat(self, tmp_path):
        """Loader.resolve_sheet_for menemukan 'DATA_WASTE' & 'BOM' lewat
        kandidat config (nama sheet output = kandidat #1, fase exact)."""
        from waste_anomaly.loader import load_bom, load_rekap_mentah
        from waste_anomaly.rekap_import import convert_rekap_mentah
        from waste_anomaly.utils import load_config
        src = _build_rekap(tmp_path / "r.xlsx")
        result = convert_rekap_mentah(str(src))
        cfg = load_config()
        dw = load_rekap_mentah(result["out_path"], cfg)
        bom = load_bom(result["out_path"], cfg)
        assert len(dw) == 6
        assert len(bom) == 2 and set(bom.columns) == {
            "Nomor #", "Nama Barang", "TOTAL BOM"}


# ============================================================
# [RIMP-11] — file asli user (skip-if-missing)
# ============================================================

class TestFileAsli:

    @pytest.mark.skipif(not REAL_REKAP.exists(), reason="file asli tidak ada")
    def test_file_asli_angka_golden(self, tmp_path):
        """Angka GOLDEN dari analisis file asli (v2.14.0): 54.160 baris
        mentah → 25.722 W/S/T (WASTE 18.771 · SUSUT 2.204 · TRIAL 4.747),
        2.369 pasangan BOM, 20 cabang, sheet 'REKAP MENTAH', label
        'Agustus 2026'. Berubah tanpa alasan = regresi."""
        from waste_anomaly.rekap_import import convert_rekap_mentah
        out = tmp_path / "golden.xlsx"
        result = convert_rekap_mentah(str(REAL_REKAP), out_path=str(out))
        assert result["sheet"] == "REKAP MENTAH"
        assert result["rows_raw"] == 54160
        assert result["rows_kept"] == 25722
        assert result["jenis_counts"] == {
            "WASTE": 18771, "SUSUT": 2204, "TRIAL": 4747}
        assert result["bom_pairs"] == 2369
        assert result["resto_count"] == 20
        assert result["month_label"] == "Agustus 2026"
        assert result["day_count"] == 31
        # 53 kolom + BOM tinggi match (25028 dari analisis asli)
        dw = pd.read_excel(out, sheet_name="DATA_WASTE")
        assert len(dw.columns) == 53
        assert int(dw["TOTAL BOM"].notna().sum()) == 25028


# ============================================================
# [RIMP-12] — RekapImportWorker (QThread)
# ============================================================

class TestRekapImportWorker:

    def test_subclass_qthread_dan_sinyal(self):
        from PySide6.QtCore import QThread
        from ui.workers import RekapImportWorker
        assert issubclass(RekapImportWorker, QThread)

    def test_run_done_emit_ringkasan(self, tmp_path):
        """Worker sungguhan (bukan stub): file sintetis → done ber-dict
        ringkasan lengkap; failed tidak terpicu."""
        from ui.workers import RekapImportWorker
        app = _qapp()
        src = _build_rekap(tmp_path / "r.xlsx")
        out = tmp_path / "o.xlsx"
        w = RekapImportWorker(str(src), out_path=str(out))
        got: dict = {}
        w.done.connect(lambda r: got.__setitem__("done", r))
        w.failed.connect(lambda e, t: got.__setitem__("failed", (e, t)))
        w.start()
        deadline = time.time() + 60
        while w.isRunning() and time.time() < deadline:
            app.processEvents()
        for _ in range(20):
            app.processEvents()  # drain queued signal lintas thread
        assert "done" in got and "failed" not in got, got
        assert got["done"]["rows_kept"] == 6
        assert Path(got["done"]["out_path"]).exists()

    def test_run_rekap_import_error_failed_ramah(self, tmp_path):
        """RekapImportError → failed dengan pesan ramah + traceback KOSONG
        (tidak ada yang perlu dicocokkan — kontrak worker)."""
        from ui.workers import RekapImportWorker
        app = _qapp()
        w = RekapImportWorker(str(tmp_path / "tidak_ada.xlsx"))
        got: dict = {}
        w.done.connect(lambda r: got.__setitem__("done", r))
        w.failed.connect(lambda e, t: got.__setitem__("failed", (e, t)))
        w.start()
        deadline = time.time() + 30
        while w.isRunning() and time.time() < deadline:
            app.processEvents()
        for _ in range(20):
            app.processEvents()  # drain queued signal lintas thread
        assert "failed" in got and "done" not in got, got
        assert "tidak ditemukan" in got["failed"][0]
        assert got["failed"][1] == ""


# ============================================================
# [RIMP-13] — UI: tombol + alur + gagal
# ============================================================

class _RIWStub:
    """Stub worker emit sinkron (pola _PWStub test_v21315) — view hanya
    butuh done/failed/finished connect + start()."""

    class _Sig:
        def __init__(self):
            self._slots = []

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *a):
            for s in self._slots:
                s(*a)

    done = None
    failed = None
    finished = None

    def __init__(self, source, out_path=None, config=None, parent=None):
        type(self).done = self._Sig()
        type(self).failed = self._Sig()
        type(self).finished = self._Sig()
        self.source = source
        self.out_path = out_path

    def deleteLater(self):
        pass  # stub — view memasang finished→deleteLater

    def start(self):
        type(self).done.emit({
            "out_path": self.out_path or "/tmp/olah_hasil.xlsx",
            "source": self.source,
            "sheet": "REKAP MENTAH",
            "rows_raw": 10, "rows_kept": 6,
            "jenis_counts": {"WASTE": 3, "SUSUT": 1, "TRIAL": 1},
            "bom_pairs": 2, "bom_matched": 6,
            "resto_count": 2, "item_count": 2,
            "month_label": "Agustus 2026",
            "day_count": 31, "satuan_sheet": None,
        })
        type(self).finished.emit()


class _RIWStubFail(_RIWStub):
    def start(self):
        type(self).failed.emit("Sheet REKAP MENTAH tidak ditemukan", "")
        type(self).finished.emit()


class TestUiAlur:
    """v2.15.0 — DITULIS ULANG JUJUR: alur 2-langkah v2.14.0 (worker
    RekapImportWorker mengolah → ekspor → kolom workbook terisi →
    petunjuk Mulai Pipeline) diganti SEKALI JALAN atas permintaan user
    ("aku mau sekali proses aja dan gak perlu export hasil olahan
    proses rekap mentah nya"): tombol 🧮 kini mengisi kolom workbook
    dgn path MENTAH lalu memanggil _start() langsung — pipeline
    memanggil rekap_import di fase LOAD (tanpa file antara). Detail
    alur baru dikunci test_v2150.py [R150-7]; kelas ini memastikan
    KONTRAK LAMA yang masih berlaku: tombol hidup, guard saat run,
    worker API utuh."""

    def _view(self, ctx):
        import ui.view_pipeline as vp
        return vp.PipelineView(ctx)

    def test_tombol_ada_dan_tooltip(self):
        app = _qapp()
        from ui.state import AppContext
        view = self._view(AppContext({}))
        try:
            btn = view._btn_import
            assert btn is not None
            # v2.15.0: "Olah & Jalankan REKAP MENTAH…" (sekali jalan;
            # dulu v2.14.0 "Olah REKAP MENTAH…" 2-langkah ber-ekspor)
            assert "REKAP MENTAH" in btn.text()
            assert "REKAP MENTAH_01-31" in btn.toolTip()
        finally:
            view.close()
            view.deleteLater()

    def test_tolak_saat_pipeline_berjalan(self, monkeypatch):
        """Pipeline _running=True → tolak ramah (dialog info), worker
        TIDAK dibuat (guard klik saat run — kontrak D29 lama)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        from PySide6.QtWidgets import QMessageBox
        app = _qapp()
        view = self._view(AppContext({}))
        infos: list = []
        monkeypatch.setattr(
            QMessageBox, "information",
            lambda *a, **k: infos.append(a) or QMessageBox.Ok)
        created: list = []

        class _Never:
            def __init__(self, *a, **k):
                created.append(a)

        monkeypatch.setattr(vp, "PipelineWorker", _Never)
        try:
            view._running = True
            view._on_import_rekap()
            assert infos and not created
        finally:
            view._running = False
            view.close()
            view.deleteLater()


# ============================================================
# [RIMP-14] — manifest + bantuan + versi 2.14.0
# ============================================================

class TestManifestBantuanVersi:

    def test_manifest_dua_arah_worker_baru(self):
        manifest = (REPO / "tests" / "fixtures" /
                    "ui_methods_manifest.txt").read_text(encoding="utf-8")
        assert "workers.py::RekapImportWorker" in manifest

    def test_modul_baru_ada_dan_init(self):
        assert (REPO / "waste_anomaly" / "rekap_import.py").exists()
        from waste_anomaly import __all__ as wa_all
        assert "rekap_import" in wa_all

    def test_bantuan_menyebut_tombol(self):
        """F1 Bantuan seksi Tab Pipeline menyebut tombol rekap mentah +
        alur singkatnya (regresi dokumentasi — pola B24 gel-6).
        v2.15.0 — DITULIS ULANG JUJUR: label tombol kini 'Olah & Jalankan
        REKAP MENTAH…' (sekali jalan, tanpa file antara)."""
        src = (UI / "app.py").read_text(encoding="utf-8")
        assert "Jalankan REKAP MENTAH" in src
        assert "REKAP MENTAH_01-31" in src  # contoh nama file user

    def test_versi_2140_sinkron(self):
        """v2.15.0 — DITULIS ULANG JUJUR: pin dinaikkan bersama fitur
        sekali-jalan (test_v2150 [R150-8] mengunci detailnya)."""
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        cfg = load_config()
        assert APP_VERSION == __version__ == cfg.get("version") == "2.17.0"
        init_src = (REPO / "waste_anomaly" / "__init__.py").read_text(
            encoding="utf-8")
        assert "Versi: 2.17.0" in init_src
        mulai = (REPO / "MULAI.bat").read_bytes()
        assert b"v2.17.0" in mulai
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "v2.17.0" in readme

    def test_crlf_bat_utuh(self):
        """MULAI.bat/SETUP.bat tetap CRLF penuh (kontrak gelombang 1-6)."""
        for bat in ("MULAI.bat", "SETUP.bat"):
            raw = (REPO / bat).read_bytes()
            txt = raw.decode("utf-8", errors="replace")
            n_lf = txt.count("\n")
            n_crlf = txt.count("\r\n")
            assert n_lf == n_crlf, f"{bat}: CRLF rusak ({n_crlf}/{n_lf})"
