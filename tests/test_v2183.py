"""test_v2183.py — v2.18.3: ISI KOLOM TOTAL BLANK (folder flow).

REPRO BUG USER (pesan: "kolom total pada file hasil program yaitu
proses dari folder kok blank ya? dan sebagian ada sih"):

  File bukti "HASIL OLAH REKAP MENTAH PROGRAM.xlsx" (48.202 baris,
  44 kolom) = gabungan hasil load_rekap_folder pra-fix. Kolom TOTAL
  bercelah di 3.659 baris, DUA penyebab terukur:

    (a) 3.637 baris dari 5 resto salah-sheet (BDGSEK/BKSALT/BKSSUD/
        KGNSUD/MLGPAR — sheet seksi tanpa kolom TOTAL; union concat
        → NaN). Akar masalah ini sudah difix v2.18.2 (pemilihan sheet
        berbasis skor).
    (b) 22 baris resto benar: sel TOTAL memang kosong DI FILE SUMBER
        (17 STOK AWAL + 5 BARANG MASUK — sel TOTAL tak diisi orang;
        nilai hari ADA, contoh TGRBIN "CABE RAWIT - RESTO (V.20)"
        hari 1-3 = 20.000/15.000/15.000 tapi TOTAL blank). TOTAL
        passthrough mentah → blank ikut ke file gabungan.

  Analisa TIDAK pernah salah karenanya (stage_02 & Banding Periode
  menghitung ulang TOTAL dari kolom hari sesuai key_akhir) — tapi file
  hasil yang dilihat user terlihat rusak.

FIX v2.18.3 — _fill_total_column(combined) di load_rekap_folder:
  - sel TOTAL kosong/non-numerik → diisi jumlah kolom hari '1'..'31'
    yang ada (skipna; semantik identik "TOTAL KESELURUHAN" Power Query
    user & stage_02);
  - baris TANPA satu pun nilai hari → TOTAL tetap kosong (min_count=1
    — jujur, tanpa fabrikasi 0);
  - TOTAL non-kosong dipertahankan (terukur file bukti: sumber akurat,
    0 selisih vs jumlah hari pada 2.000 baris sampel);
  - kolom TOTAL tidak ada di SEMUA file → kolom DITAMBAH;
  - summary["total_filled"] + log folder (anti silent-error).

Test di file ini:
[F183-1] _fill_total_column: sel TOTAL kosong → diisi jumlah hari;
          sel terisi dipertahankan apa adanya.
[F183-2] _fill_total_column: TOTAL teks non-numerik → diisi; TOTAL
          teks angka → dinormalisasi numerik.
[F183-3] _fill_total_column: baris tanpa SATU PUN nilai hari → TOTAL
          tetap kosong (anti fabrikasi 0).
[F183-4] _fill_total_column: kolom TOTAL tidak ada → DITAMBAH =
          jumlah hari utk semua baris berdata.
[F183-5] _fill_total_column: tanpa kolom hari → no-op (return 0).
[F183-6] load_rekap_folder e2e: file dgn sel TOTAL kosong (pola bukti
          user: STOK AWAL ber-hari tapi TOTAL blank) → temp gabungan
          TOTAL terisi = jumlah hari; summary["total_filled"] > 0.
[F183-7] load_rekap_folder e2e: folder campuran — file A punya kolom
          TOTAL (sebagian blank), file B TANPA kolom TOTAL → semua
          baris ber-hari ber-TOTAL terisi; baris tanpa data hari tetap
          blank; temp file dibaca ulang mempertahankan nilai.
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
# FIXTURES — pola terukur dari file bukti user
# ============================================================

def _rekap_cols(with_total: bool = True) -> list[str]:
    """Kolom rekap riil BJMHAS-style (sama fixture v2.18.2; TOTAL
    bisa dilepas utk kasus sheet tanpa kolom TOTAL)."""
    cols = (["KATEGORI", "SOURCE DATA", "JENIS", "STATUS", "NAMA BARANG",
             "KETERANGAN", "PENYEBAB TERJADINYA WASTE", "SATUAN"]
            + _DAYS + ["DATA NEW ITEM", "selisih"])
    if with_total:
        # Posisi TOTAL di file user: setelah hari, sebelum DATA NEW
        # ITEM — sisip utk identik struktur.
        i = cols.index("DATA NEW ITEM")
        cols.insert(i, "TOTAL")
    return cols


def _rekap_rows(stem: str, n_waste: int = 2,
                blank_total_jenis: tuple[str, ...] = ("STOK AWAL",),
                with_total_col: bool = True) -> pd.DataFrame:
    """Sheet REKAP MENTAH riil. Baris JENIS di blank_total_jenis
    diberi nilai hari TAPI sel TOTAL dibiarkan kosong (pola file
    bukti: STOK AWAL/BARANG MASUK — hari ada, TOTAL blank)."""
    rows = []
    for i in range(n_waste):
        row = {c: "" for c in _rekap_cols(with_total_col)}
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
    # Baris TOTAL-blank (pola bukti user): hari terisi, TOTAL kosong.
    for jenis in blank_total_jenis:
        row = {c: "" for c in _rekap_cols(with_total_col)}
        row.update({
            "KATEGORI": "STOK",
            "SOURCE DATA": jenis,
            "JENIS": jenis,
            "STATUS": "",
            "NAMA BARANG": f"{stem} BARANG {jenis}",
            "KETERANGAN": "",
            "PENYEBAB TERJADINYA WASTE": "",
            "SATUAN": "PCS",
        })
        # Terukur: GGPDAA 'VANILLA LATTE - JS' hari-1 blank, hari lain
        # 0 — dan TGRBIN BARANG MASUK hari 1-3 berisi besar.
        row["1"] = 20000
        row["2"] = 15000
        row["3"] = 15000
        for d in _DAYS[3:]:
            row[d] = 0
        if with_total_col:
            row["TOTAL"] = None  # ← sel TOTAL kosong di sumber
        rows.append(row)
    # Baris BOM (utk kelengkapan pola sumber).
    bom = {c: "" for c in _rekap_cols(with_total_col)}
    bom.update({"JENIS": "BOM", "NAMA BARANG": f"{stem} ITEM 0",
                "SOURCE DATA": "INPUT PENJUALAN DINE IN", "SATUAN": "GR"})
    for d in _DAYS:
        bom[d] = 100
    if with_total_col:
        bom["TOTAL"] = 3100
    rows.append(bom)
    df = pd.DataFrame(rows, columns=_rekap_cols(with_total_col))
    if with_total_col:
        # WASTE/BOM: TOTAL terisi = jumlah hari (pola sumber akurat).
        mask = df["JENIS"].isin(["WASTE", "BOM"])
        df.loc[mask, "TOTAL"] = df.loc[mask, _DAYS].sum(axis=1)
    return df


def _write_single(path: Path, df: pd.DataFrame) -> Path:
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="REKAP MENTAH", index=False)
    return path


# ============================================================
# [F183-1..5] _fill_total_column — unit
# ============================================================
class TestFillTotalColumn:
    def test_sel_kosong_diisi_terisi_dipertahankan(self):
        from waste_anomaly.rekap_import import _fill_total_column
        df = pd.DataFrame({
            "NAMA BARANG": ["A", "B", "C"],
            "1": [10, 0, 5], "2": [20, 0, None], "3": [30, 0, None],
            "TOTAL": [60.0, 0.0, None],  # C: blank (pola bukti user)
        })
        n = _fill_total_column(df)
        assert n == 1, "hanya sel C yang kosong"
        assert df["TOTAL"].tolist() == [60.0, 0.0, 5.0], (
            "A/B dipertahankan; C diisi sum hari non-null")
        # A tidak dihitung ulang salah: nilai asli menang.
        assert df.loc[0, "TOTAL"] == 60.0

    def test_total_teks_nonnumerik(self):
        from waste_anomaly.rekap_import import _fill_total_column
        df = pd.DataFrame({
            "NAMA BARANG": ["A", "B"],
            "1": [7, 3], "2": [8, None],
            "TOTAL": ["abc", "5"],  # teks sampah & teks angka
        })
        n = _fill_total_column(df)
        assert n == 1, "'abc' → coerce NaN → diisi; '5' tetap (5.0)"
        assert df["TOTAL"].tolist() == [15.0, 5.0]
        assert pd.api.types.is_numeric_dtype(df["TOTAL"])

    def test_baris_tanpa_nilai_hari_total_tetap_kosong(self):
        """Anti fabrikasi 0: baris tanpa SATU PUN nilai hari → TOTAL
        blank (jujur — belum ada data), bukan 0 palsu."""
        from waste_anomaly.rekap_import import _fill_total_column
        df = pd.DataFrame({
            "NAMA BARANG": ["ADA", "KOSONG"],
            "1": [10, None], "2": [None, None], "3": [None, None],
            "TOTAL": [None, None],
        })
        _fill_total_column(df)
        assert df.loc[0, "TOTAL"] == 10.0
        assert pd.isna(df.loc[1, "TOTAL"]), (
            "baris tanpa nilai hari sama sekali → TOTAL tetap NaN")

    def test_kolom_total_tidak_ada_ditambah(self):
        from waste_anomaly.rekap_import import _fill_total_column
        df = pd.DataFrame({
            "NAMA BARANG": ["A", "B"],
            "1": [10, 1], "2": [20, 2], "3": [30, None],
        })
        n = _fill_total_column(df)
        assert n == 2, "kolom ditambah → semua baris terisi"
        assert "TOTAL" in df.columns
        assert df["TOTAL"].tolist() == [60.0, 3.0]

    def test_tanpa_kolom_hari_noop(self):
        from waste_anomaly.rekap_import import _fill_total_column
        df = pd.DataFrame({"NAMA BARANG": ["A"], "TOTAL": [None]})
        before = df.copy(deep=True)
        assert _fill_total_column(df) == 0
        pd.testing.assert_frame_equal(df, before, check_dtype=False)


# ============================================================
# [F183-6] load_rekap_folder e2e — TOTAL blank pola bukti user
# ============================================================
class TestFolderTotalFilled:
    def test_sel_total_blank_sumber_diterisi(self, tmp_path):
        """File dgn sel TOTAL kosong (pola bukti: STOK AWAL ber-hari
        20.000/15.000/15.000 tapi TOTAL blank) → temp gabungan TOTAL
        terisi = jumlah hari; summary['total_filled'] transparan."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_single(tmp_path / "TGRBIN.xlsx", _rekap_rows("TGRBIN"))
        res = load_rekap_folder(tmp_path, load_config())
        assert res["total_filled"] == 1, (
            "1 baris STOK AWAL ber-TOTAL blank harus diisi")
        df = pd.read_excel(res["temp_path"], sheet_name="REKAP MENTAH",
                           dtype=object)
        tot = pd.to_numeric(df["TOTAL"], errors="coerce")
        day_sum = (df[_DAYS].apply(pd.to_numeric, errors="coerce")
                   .sum(axis=1, min_count=1))
        # SEMUA baris berdata kini TOTAL == jumlah hari (blank terisi,
        # terisi dipertahankan — sumber akurat).
        assert (tot.dropna() == day_sum.dropna()).all(), (
            "TOTAL file gabungan harus = jumlah kolom hari di semua "
            "baris berdata")
        stok = df[df["JENIS"] == "STOK AWAL"]
        assert len(stok) == 1
        assert pd.to_numeric(stok["TOTAL"]).iloc[0] == 50000.0, (
            "20.000+15.000+15.000 = 50.000 (pola TGRBIN bukti user)")
        os.unlink(res["temp_path"])

    def test_folder_campuran_dengan_dan_tanpa_kolom_total(self, tmp_path):
        """File A punya kolom TOTAL (sebagian blank), file B TANPA
        kolom TOTAL sama sekali → union concat dulu membuat baris B
        NaN semua; kini baris B terisi jumlah hari (bukan blank)."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_single(tmp_path / "BJMHAS.xlsx",
                      _rekap_rows("BJMHAS", blank_total_jenis=("STOK AWAL",)))
        _write_single(tmp_path / "KWGGAL.xlsx",
                      _rekap_rows("KWGGAL", n_waste=1,
                                  blank_total_jenis=(),
                                  with_total_col=False))
        res = load_rekap_folder(tmp_path, load_config())
        # 1 sel blank (STOK AWAL BJMHAS) + seluruh baris KWGGAL
        # (2 baris: WASTE + BOM — file tanpa kolom TOTAL).
        assert res["total_filled"] == 1 + 2
        df = pd.read_excel(res["temp_path"], sheet_name="REKAP MENTAH",
                           dtype=object)
        tot = pd.to_numeric(df["TOTAL"], errors="coerce")
        day_sum = (df[_DAYS].apply(pd.to_numeric, errors="coerce")
                   .sum(axis=1, min_count=1))
        merged = pd.DataFrame({"tot": tot, "ds": day_sum}).dropna()
        assert len(merged) == len(df), "semua baris berdata punya TOTAL"
        assert (merged["tot"] == merged["ds"]).all()
        # Baris KWGGAL (file tanpa kolom TOTAL) — bukan NaN lagi.
        kwg = df[df["NAMA RESTO"] == "KWGGAL"]
        assert kwg["TOTAL"].notna().all(), (
            "baris dari file tanpa kolom TOTAL harus terisi (dulu NaN "
            "akibat union concat)")
        os.unlink(res["temp_path"])

    def test_pipeline_tak_berubah_numerik(self, tmp_path):
        """Anti-regresi: TOTAL terisi di file gabungan TIDAK mengubah
        hasil analisa (stage_02 tetap menghitung ulang dgn key_akhir)
        — bandingkan TOTAL frame pipeline vs jumlah hari 1..31."""
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_single(tmp_path / "BJMHAS.xlsx", _rekap_rows("BJMHAS"))
        res = load_rekap_folder(tmp_path, load_config())
        out = run_pipeline(res["temp_path"], key_akhir=31)["df"]
        day_sum = (out[_DAYS].apply(pd.to_numeric, errors="coerce")
                   .fillna(0).sum(axis=1))
        assert (out["TOTAL"] == day_sum).all(), (
            "stage_02 tetap sumber kebenaran TOTAL — identik jumlah hari")
        os.unlink(res["temp_path"])
