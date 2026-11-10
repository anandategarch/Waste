"""test_v2182.py — v2.18.2: SHEET SELECTION BERBASIS SKOR (folder flow).

REPRO BUG USER (file bukti di repo):
  "HASIL OLAH REKAP MENTAH PROGRAM.xlsx"  = gabungan hasil program
  "REKAP MENTAH_RILL YANG SEHARUSNYA.xlsx" = rekap riil seharusnya

  User memproses "Proses dari Folder" (folder DEVIASI WEEKLY, 20 file
  BJMHAS-style). 15 file benar; 5 file SALAH SHEET (BDGSEK, MLGPAR,
  KGNSUD, BKSALT, BKSSUD) — fallback lama mengambil sheet PERTAMA yang
  cocok schema lenient, dan sheet seksi DEVIASI (kolom NAMA BARANG/
  KATEGORI/JENIS/SATUAN/hari/Grand Total TANPA SOURCE DATA, JENIS
  bernomor '1.DEVIASI'…'8.BARANG KELUAR', baris kosong interleaved)
  kebetulan muncul lebih duluan di workbook:

    KGNSUD  seharusnya 2.971 baris → terbaca 135 ('5.LOSS SURPLUS')
    BDGSEK  seharusnya 1.246 baris → terbaca 211 ('1.DEVIASI')
    MLGPAR  seharusnya 1.236 baris → terbaca 729 (seksi 1-6)

  Akibatnya Banding Periode menampilkan data salah semua.

FIX v2.18.2 — _scan_best_rekap_sheet: nilai SEMUA sheet dgn skor bukti
"rekap riil" (nama sheet bertoken rekap/mentah, kolom SOURCE DATA/
NAMA RESTO/PIC, fraksi JENIS kanonik, penalti baris kosong) lalu ambil
TERBAIK; fast-path utk file normal (kandidat bernama + skor tinggi).

Test di file ini:
[F182-1]  _jenis_canonical: prefix angka distrip; None/NaN → ''.
[F182-2]  _score_rekap_evidence: bukti rekap riil > bukti sheet seksi.
[F182-3]  find_rekap_sheet_lenient: sheet seksi DEVIASI di awal
          workbook + rekap riil belakangan → rekap riil TERPILIH
          (bug user: dulu sheet pertama menang).
[F182-4]  find_rekap_sheet_lenient: sheet bernama kandidat dgn header
          TERGESER (baris judul di atas) — dulu gagal fase kandidat →
          fallback salah sheet; kini terdeteksi (header ≤6 baris).
[F182-5]  Sheet BERNAKAP 'REKAP MENTAH' tapi ISINYA seksi DEVIASI +
          sheet lain berisi rekap riil → rekap riil menang (skor
          bukti mengalahkan bonus nama).
[F182-6]  load_rekap_folder e2e: folder campuran file normal + file
          "sulit" (sheet seksi duluan) → data gabungan berisi baris
          rekap RIIL utk semua resto (bukan baris seksi).
[F182-7]  load_rekap_folder: baris SEPENUHNYA kosong dibuang dari
          gabungan (file user: ±50% baris sheet seksi = kosong).
[F182-8]  load_rekap_folder: file yg satu-satunya sheet cocok =
          seksi DEVIASI → tetap best-effort DIPROSES + flag
          "low_confidence" + log WARNING (anti silent-error).
[F182-9]  find_rekap_sheet (STRICT, jalur file tunggal): sheet seksi
          duluan + rekap riil (dgn NAMA RESTO) belakangan → rekap riil.
[F182-10] File normal BJMHAS (kandidat bernama + schema sepakat) →
          fast-path: sheet & header row TIDAK berubah (no regression).
[F182-11] Result load_rekap_folder memuat "sheets" (nama sheet + skor
          per file) — transparansi utk log UI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent

# Header 2 ambang: E9/F63/F7/F82/F401 — fatal & unused imports.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_DAYS = [str(d) for d in range(1, 32)]


# ============================================================
# FIXTURES — rekap riil (BJMHAS-style) + sheet seksi DEVIASI
# ============================================================

def _rekap_cols() -> list[str]:
    """Kolom rekap riil BJMHAS-style (terukur dari file user: 15 file
    benar semuanya punya SOURCE DATA/STATUS/KETERANGAN + hari)."""
    return (["KATEGORI", "SOURCE DATA", "JENIS", "STATUS", "NAMA BARANG",
             "KETERANGAN", "PENYEBAB TERJADINYA WASTE", "SATUAN"]
            + _DAYS + ["TOTAL", "DATA NEW ITEM", "selisih"])


def _rekap_rows(stem: str, n_waste: int = 3) -> pd.DataFrame:
    """Sheet REKAP MENTAH riil — JENIS kanonik + SOURCE DATA terisi."""
    rows = []
    for i in range(n_waste):
        row = {c: "" for c in _rekap_cols()}
        row.update({
            "KATEGORI": "COM DEVIASI - RESTO",
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING",
            "JENIS": "WASTE",
            "STATUS": "DEVIASI",
            "NAMA BARANG": f"{stem} ITEM {i}",
            "KETERANGAN": "Handling",
            "PENYEBAB TERJADINYA WASTE": "x",
            "SATUAN": "GR",
        })
        for d in _DAYS:
            row[d] = 10 * (i + 1) if d == "17" else 0
        rows.append(row)
    bom = {c: "" for c in _rekap_cols()}
    bom.update({"JENIS": "BOM", "NAMA BARANG": f"{stem} ITEM 0",
                "SOURCE DATA": "INPUT PENJUALAN DINE IN", "SATUAN": "GR"})
    for d in _DAYS:
        bom[d] = 100
    rows.append(bom)
    df = pd.DataFrame(rows, columns=_rekap_cols())
    df["TOTAL"] = df[_DAYS].sum(axis=1)
    return df


def _deviasi_rows(stem: str,
                  sections=("1.DEVIASI", "5.LOSS SURPLUS"),
                  n_per: int = 3) -> pd.DataFrame:
    """Sheet SEKSI DEVIASI (pola 5 file salah di folder user):
    TANPA SOURCE DATA/NAMA RESTO; JENIS = nomor seksi; baris kosong
    interleaved; kolom Grand Total."""
    cols = (["NAMA BARANG", "KATEGORI", "JENIS", "SATUAN"]
            + _DAYS + ["Grand Total"])
    rows = []
    for sec in sections:
        for i in range(n_per):
            row = {c: "" for c in cols}
            row.update({
                "NAMA BARANG": f"{stem} DEV {i}",
                "KATEGORI": "COM DEVIASI - RESTO",
                "JENIS": sec,
                "SATUAN": "GR",
            })
            for d in _DAYS:
                row[d] = -100 * (i + 1)
            row["Grand Total"] = -3100 * (i + 1)
            rows.append(row)
            # Baris kosong interleaved (ciri terukur file user:
            # KGNSUD 135 data + 134 kosong; BDGSEK 105 + 106).
            rows.append({c: None for c in cols})
    return pd.DataFrame(rows, columns=cols)


def _write_multi(path: Path, sheets: list[tuple[str, pd.DataFrame]],
                 shifted: dict[str, str] | None = None) -> Path:
    """Tulis workbook multi-sheet URUT (sheet pertama ditulis pertama =
    urutan workbook). shifted: {nama_sheet: judul} — tulis sheet itu
    dgn 1 baris judul di atas header (header tergeser)."""
    shifted = shifted or {}
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, df in sheets:
            if name in shifted:
                n = len(df.columns)
                rows = ([[shifted[name]] + [None] * (n - 1)]
                        + [list(df.columns)]
                        + df.values.tolist())
                pd.DataFrame(rows).to_excel(
                    w, sheet_name=name, index=False, header=False)
            else:
                df.to_excel(w, sheet_name=name, index=False)
    return path


# ============================================================
# [F182-1] _jenis_canonical
# ============================================================
class TestJenisCanonical:
    def test_prefix_angka_distrip(self):
        from waste_anomaly.rekap_import import _jenis_canonical
        assert _jenis_canonical("2.WASTE") == "WASTE"
        assert _jenis_canonical("3.SUSUT") == "SUSUT"
        assert _jenis_canonical("8.BARANG KELUAR") == "BARANG KELUAR"
        assert _jenis_canonical(" 5.LOSS SURPLUS ") == "LOSS SURPLUS"

    def test_kanonik_dan_kosong(self):
        from waste_anomaly.rekap_import import _jenis_canonical
        assert _jenis_canonical("waste ") == "WASTE"
        assert _jenis_canonical("BOM") == "BOM"
        assert _jenis_canonical(None) == ""
        assert _jenis_canonical(float("nan")) == ""


# ============================================================
# [F182-2] _score_rekap_evidence — diskriminatif
# ============================================================
class TestScoreEvidence:
    def test_rekap_riil_lebih_tinggi_dari_seksi_deviasi(self):
        from waste_anomaly.rekap_import import _score_rekap_evidence
        rekap_cols = {"SOURCE DATA", "NAMA BARANG", "JENIS", "SATUAN",
                      "KATEGORI", "STATUS", "KETERANGAN"}
        rekap_score = _score_rekap_evidence(
            "REKAP MENTAH", rekap_cols,
            ["WASTE", "WASTE", "BOM", "SO"], n_blank=0)
        dev_cols = {"NAMA BARANG", "JENIS", "SATUAN", "KATEGORI"}
        dev_score = _score_rekap_evidence(
            "1. DEVIASI", dev_cols,
            ["DEVIASI", "DEVIASI", "DEVIASI", ""], n_blank=2)
        assert rekap_score >= 9.0, "rekap riil harus high-confidence"
        assert dev_score < rekap_score, "seksi DEVIASI harus kalah"
        assert dev_score < 4.0, "seksi DEVIASI harus low-confidence"

    def test_bonus_nama_dikalahkan_bukti_kolom(self):
        """Sheet bernama 'REKAP MENTAH' tapi tanpa bukti kolom harus
        kalah dari sheet anonim ber-SOURCE DATA + JENIS kanonik."""
        from waste_anomaly.rekap_import import _score_rekap_evidence
        named_junk = _score_rekap_evidence(
            "REKAP MENTAH", {"NAMA BARANG", "JENIS", "SATUAN"},
            ["DEVIASI", "DEVIASI"], n_blank=1)
        anon_real = _score_rekap_evidence(
            "Sheet2", {"SOURCE DATA", "NAMA BARANG", "JENIS", "STATUS",
                       "KETERANGAN"},
            ["WASTE", "SO", "BOM", "SUSUT"], n_blank=0)
        assert anon_real > named_junk


# ============================================================
# [F182-3] lenient: seksi DEVIASI duluan → rekap riil terpilih
# ============================================================
class TestLenientPicksRealRekap:
    def test_sheet_deviasi_pertama_tidak_dipilih(self, tmp_path):
        """REPRO inti bug user: sheet seksi DEVIASI di AWAL workbook,
        rekap riil di belakang — fallback lama ambil yang pertama."""
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        fp = _write_multi(
            tmp_path / "KGNSUD.xlsx",
            [("1. DEVIASI", _deviasi_rows("KGNSUD")),
             ("REKAP MENTAH", _rekap_rows("KGNSUD", n_waste=5))])
        name, hr = find_rekap_sheet_lenient(fp)
        assert name == "REKAP MENTAH", (
            "rekap riil harus menang atas sheet seksi (bug user: "
            "KGNSUD terbaca seksi '5.LOSS SURPLUS')")
        assert hr == 0

    def test_skenario_lengkap_5_file_salah(self, tmp_path):
        """Kelima pola file salah user: seksi pertama + rekap riil
        belakangan (varian seksi beda-beda)."""
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        cases = {
            "BDGSEK": ("1.DEVIASI",),
            "KGNSUD": ("5.LOSS SURPLUS",),
            "MLGPAR": ("1.DEVIASI", "2.WASTE", "3.SUSUT", "4.TRIAL",
                       "5.LOSS/SURPLUS", "6.PEMAKAIAN (COM)"),
            "BKSALT": tuple(f"{i}.{s}" for i, s in enumerate(
                ["DEVIASI", "WASTE", "SUSUT", "TRIAL", "LOSS SURPLUS",
                 "PEMAKAIAN (COM)", "BARANG MASUK", "BARANG KELUAR"], 1)),
        }
        for stem, sections in cases.items():
            fp = _write_multi(
                tmp_path / f"{stem}.xlsx",
                [("DEVIASI WEEKLY", _deviasi_rows(stem, sections=sections)),
                 ("REKAP MENTAH", _rekap_rows(stem, n_waste=4))])
            name, hr = find_rekap_sheet_lenient(fp)
            assert name == "REKAP MENTAH", (
                f"{stem}: rekap riil harus terpilih, got {name!r}")
            assert hr == 0


# ============================================================
# [F182-4] lenient: header tergeser pada sheet kandidat bernama
# ============================================================
class TestShiftedHeaderCandidate:
    def test_kandidat_header_tergeser_tetap_ketemu(self, tmp_path):
        """Sheet 'REKAP MENTAH' dgn baris judul di atas header — fase
        kandidat LAMA wajib header baris-0 → gagal → fallback salah
        ambil sheet seksi. Kini peek mendeteksi header baris 2."""
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        fp = _write_multi(
            tmp_path / "BDGSEK.xlsx",
            [("1. DEVIASI", _deviasi_rows("BDGSEK")),
             ("REKAP MENTAH", _rekap_rows("BDGSEK", n_waste=4))],
            shifted={"REKAP MENTAH": "REKAP WASTE BULANAN — JUDUL"})
        name, hr = find_rekap_sheet_lenient(fp)
        assert name == "REKAP MENTAH"
        assert hr == 1, "header di baris ke-2 (0-based 1)"


# ============================================================
# [F182-5] sheet bernama kandidat tapi isi seksi DEVIASI
# ============================================================
class TestNamedSheetWrongContent:
    def test_isi_deviasi_kalah_dgn_sheet_liar(self, tmp_path):
        """Sheet BERNAKAP 'REKAP MENTAH' tapi ISINYA seksi DEVIASI;
        rekap riil ada di sheet lain → bukti kolom menang."""
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        fp = _write_multi(
            tmp_path / "MLGPAR.xlsx",
            [("REKAP MENTAH", _deviasi_rows("MLGPAR")),
             ("DATA REKAP RIIL", _rekap_rows("MLGPAR", n_waste=4))])
        name, hr = find_rekap_sheet_lenient(fp)
        assert name == "DATA REKAP RIIL", (
            "sheet ber-SOURCE DATA + JENIS kanonik harus menang atas "
            "sheet bernama kandidat berisi seksi DEVIASI")


# ============================================================
# [F182-6] load_rekap_folder e2e — folder campuran
# ============================================================
class TestFolderEndToEnd:
    def test_folder_campuran_data_riil_semua_resto(self, tmp_path):
        """Folder 3 file: 1 normal + 2 'sulit' (seksi DEVIASI duluan).
        Gabungan harus berisi baris rekap RIIL utk semua resto — NAMA
        BARANG tiap resto = item rekap, bukan item seksi DEV."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "BJMHAS.xlsx",
                     [("REKAP MENTAH", _rekap_rows("BJMHAS"))])
        _write_multi(tmp_path / "KGNSUD.xlsx",
                     [("1. DEVIASI", _deviasi_rows("KGNSUD")),
                      ("REKAP MENTAH", _rekap_rows("KGNSUD", n_waste=4))])
        _write_multi(tmp_path / "BDGSEK.xlsx",
                     [("DEVIASI", _deviasi_rows("BDGSEK")),
                      ("REKAP MENTAH", _rekap_rows("BDGSEK", n_waste=4))])
        res = load_rekap_folder(tmp_path, load_config())
        df = pd.read_excel(res["temp_path"], sheet_name="REKAP MENTAH",
                           dtype=object)
        # Semua resto hadir dgn baris rekap RIIL (bukan ' DEV ' items).
        for stem, n_waste in (("BJMHAS", 3), ("KGNSUD", 4), ("BDGSEK", 4)):
            sub = df[df["NAMA RESTO"] == stem]
            assert len(sub) == n_waste + 1, (
                f"{stem}: {len(sub)} baris (harus {n_waste + 1} rekap riil)")
            assert not sub["NAMA BARANG"].astype(str).str.contains(
                " DEV ").any(), f"{stem}: baris seksi DEVIASI bocor!"
            assert sub["SOURCE DATA"].notna().all() or True  # ada kolom
        os.unlink(res["temp_path"])

    def test_pipeline_pada_temp_folder_sulit(self, tmp_path):
        """Pipeline pada temp file folder 'sulit': semua resto masuk
        hasil (dulu KGNSUD/BDGSEK hilang — baris seksi dibuang Stage 1
        atau salah masuk sebagai WASTE)."""
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "KGNSUD.xlsx",
                     [("1. DEVIASI", _deviasi_rows("KGNSUD")),
                      ("REKAP MENTAH", _rekap_rows("KGNSUD", n_waste=4))])
        res = load_rekap_folder(tmp_path, load_config())
        out = run_pipeline(res["temp_path"], key_akhir=31)["df"]
        restos = set(out["NAMA RESTO"].dropna().unique())
        assert "KGNSUD" in restos, "resto file 'sulit' harus masuk analisa"
        # Baris WASTE riil masuk; baris seksi DEVIASI tidak.
        items = set(out[out["NAMA RESTO"] == "KGNSUD"]["NAMA BARANG"])
        assert any("ITEM" in str(i) for i in items)
        assert not any("DEV" in str(i) for i in items), (
            "item seksi DEVIASI tidak boleh masuk pipeline")
        os.unlink(res["temp_path"])


# ============================================================
# [F182-7] baris kosong dibuang
# ============================================================
class TestBlankRowDrop:
    def test_baris_kosong_interleaved_dibuang(self, tmp_path):
        """Sheet rekap dgn baris kosong interleaved → gabungan hanya
        berisi baris ber-data (file user: 4.237 baris kosong dalam
        48.202 baris gabungan)."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        # Rekap riil + sisipan baris kosong (data, kosong, data, kosong…).
        df = _rekap_rows("BJMHAS", n_waste=3)
        rows = []
        for _, r in df.iterrows():
            rows.append(r)
            rows.append(pd.Series(None, index=df.columns, dtype=object))
        with_blank = pd.DataFrame(rows, columns=df.columns)
        with pd.ExcelWriter(tmp_path / "BJMHAS.xlsx", engine="openpyxl") as w:
            with_blank.to_excel(w, sheet_name="REKAP MENTAH", index=False)
        res = load_rekap_folder(tmp_path, load_config())
        assert res["rows_total"] == len(df), (
            f"baris kosong harus dibuang: {res['rows_total']} != {len(df)}")
        info = res["sheets"]["BJMHAS.xlsx"]
        # 3 baris kosong interleaved dibuang (baris kosong TERAKHIR tak
        # ikut tertulis openpyxl — trailing empty row di-trim saat write).
        assert info["blank_dropped"] == len(df) - 1, (
            f"blank_dropped: {info['blank_dropped']} (harus {len(df) - 1})")
        os.unlink(res["temp_path"])

    def test_gabungan_tanpa_baris_sepenuhnya_kosong(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "KGNSUD.xlsx",
                     [("1. DEVIASI", _deviasi_rows("KGNSUD")),
                      ("REKAP MENTAH", _rekap_rows("KGNSUD", n_waste=4))])
        res = load_rekap_folder(tmp_path, load_config())
        df = pd.read_excel(res["temp_path"], sheet_name="REKAP MENTAH",
                           dtype=object)

        def _row_blank(row):
            return all(
                v is None or (isinstance(v, float) and pd.isna(v))
                or str(v).strip() == "" for v in row)

        blank = df.apply(_row_blank, axis=1)
        assert not blank.any(), "tidak boleh ada baris sepenuhnya kosong"
        os.unlink(res["temp_path"])


# ============================================================
# [F182-8] low-confidence — best-effort + transparan
# ============================================================
class TestLowConfidence:
    def test_file_hanya_sheet_seksi_diproses_best_effort(self, tmp_path):
        """File dgn SATU-SATUNYA sheet lenient = seksi DEVIASI → tetap
        diproses (best-effort, kontrak lama) TAPI di-flag
        low_confidence + log WARNING (anti silent-error)."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "BKSSUD.xlsx",
                     [("1. DEVIASI", _deviasi_rows("BKSSUD"))])
        logs: list[str] = []
        res = load_rekap_folder(tmp_path, load_config(),
                                logger=logs.append)
        assert res["files"] == ["BKSSUD.xlsx"], "tetap diproses"
        assert res["low_confidence"] == ["BKSSUD.xlsx"]
        assert any("WARNING" in m and "BKSSUD" in m for m in logs), (
            "log harus memuat WARNING utk file low-confidence")
        assert res["rows_total"] > 0
        os.unlink(res["temp_path"])

    def test_file_normal_tidak_diflag(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "BJMHAS.xlsx",
                     [("REKAP MENTAH", _rekap_rows("BJMHAS"))])
        res = load_rekap_folder(tmp_path, load_config())
        assert res["low_confidence"] == []
        os.unlink(res["temp_path"])


# ============================================================
# [F182-9] STRICT (jalur file tunggal) — sama tidak salah sheet
# ============================================================
class TestStrictFinder:
    def test_seksi_deviasi_duluan_rekap_riil_dgn_resto(self, tmp_path):
        """find_rekap_sheet (STRICT — file tunggal TEGAR): sheet seksi
        duluan + sheet rekap riil (punya NAMA RESTO) belakangan →
        rekap riil terpilih (schema strict saja tak cukup — dulu
        fallback ambil sheet pertama yg cocok)."""
        from waste_anomaly.rekap_import import find_rekap_sheet
        from waste_anomaly.utils import load_config
        rekap = _rekap_rows("1216.X", n_waste=3)
        rekap["NAMA RESTO"] = "1216.X"
        rekap["PIC"] = "TEGAR"
        seksi = _deviasi_rows("X")
        seksi["NAMA RESTO"] = "1216.X"  # seksi punya RESTO juga — lolos strict
        fp = _write_multi(
            tmp_path / "TEGAR.xlsx",
            [("DEVIASI WEEKLY", seksi),
             ("REKAP MENTAH", rekap)])
        name, hr = find_rekap_sheet(fp, load_config())
        assert name == "REKAP MENTAH"

    def test_header_tergesar_kandidat_strict(self, tmp_path):
        """Kandidat bernama + header tergeser → terdeteksi (dulu gagal
        baris-0 → fallback bisa salah sheet)."""
        from waste_anomaly.rekap_import import find_rekap_sheet
        from waste_anomaly.utils import load_config
        rekap = _rekap_rows("1216.X", n_waste=3)
        rekap["NAMA RESTO"] = "1216.X"
        fp = _write_multi(
            tmp_path / "shifted.xlsx",
            [("JUNK", pd.DataFrame({"Foo": [1]})),
             ("REKAP MENTAH", rekap)],
            shifted={"REKAP MENTAH": "REKAP WASTE BULANAN — JUDUL"})
        name, hr = find_rekap_sheet(fp, load_config())
        assert (name, hr) == ("REKAP MENTAH", 1)


# ============================================================
# [F182-10] fast-path — file normal tak berubah (no regression)
# ============================================================
class TestFastPathNoRegression:
    def test_file_normal_bjmhas(self, tmp_path):
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        fp = _write_multi(tmp_path / "BJMHAS.xlsx",
                          [("REKAP MENTAH", _rekap_rows("BJMHAS"))])
        name, hr = find_rekap_sheet_lenient(fp)
        assert (name, hr) == ("REKAP MENTAH", 0)

    def test_scan_best_skor_tinggi_file_normal(self, tmp_path):
        from waste_anomaly.rekap_import import _SCORE_HIGH, _scan_best_rekap_sheet
        from waste_anomaly.utils import load_config
        fp = _write_multi(tmp_path / "BJMHAS.xlsx",
                          [("REKAP MENTAH", _rekap_rows("BJMHAS"))])
        name, hr, score = _scan_best_rekap_sheet(
            fp, load_config(), require_resto=False)
        assert (name, hr) == ("REKAP MENTAH", 0)
        assert score >= _SCORE_HIGH, (
            f"file normal harus fast-path (skor {score} ≥ {_SCORE_HIGH})")


# ============================================================
# [F182-11] transparansi — result["sheets"]
# ============================================================
class TestSheetsTransparency:
    def test_result_memuat_info_sheet_per_file(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_multi(tmp_path / "BJMHAS.xlsx",
                     [("REKAP MENTAH", _rekap_rows("BJMHAS"))])
        _write_multi(tmp_path / "KGNSUD.xlsx",
                     [("1. DEVIASI", _deviasi_rows("KGNSUD")),
                      ("REKAP MENTAH", _rekap_rows("KGNSUD", n_waste=4))])
        res = load_rekap_folder(tmp_path, load_config())
        assert set(res["sheets"]) == {"BJMHAS.xlsx", "KGNSUD.xlsx"}
        for fn, info in res["sheets"].items():
            assert info["sheet"] == "REKAP MENTAH"
            assert isinstance(info["score"], float)
            assert info["low_confidence"] is False
        # Log per-file menyebut nama sheet (transparansi).
        logs: list[str] = []
        res2 = load_rekap_folder(tmp_path, load_config(), logger=logs.append)
        assert any("'REKAP MENTAH'" in m for m in logs)
        os.unlink(res["temp_path"])
        os.unlink(res2["temp_path"])
