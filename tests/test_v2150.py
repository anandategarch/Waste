"""test_v2150.py — fitur v2.15.0: SEKALI JALAN — pilih file REKAP MENTAH
mentah → pipeline LANGSUNG dijalankan padanya, TANPA file olahan antara
(perintah user: "bisa gak sekali proses aja semua diproses? ini kan aku 2x
proses > 1. proses rekap mentah 2. proses pipeline. aku mau sekali proses
aja dan gak perlu export hasil olahan proses rekap mentah nya").

Implementasi: pipeline.py memanggil tiga helper waste_anomaly/rekap_import
di fase LOAD — ensure_rekap_header (perbaiki header tergeser) +
normalize_rekap_values (JENIS kanonis + identity strip + hari kosong → 0 —
mirror pembersihan convert_rekap_mentah v2.14.0) + inject_bom_from_raw_rows
(kolom inline TOTAL BOM dari baris JENIS=="BOM" sebelum stage_01
memfilternya). UI: tombol 🧮 "Olah & Jalankan REKAP MENTAH…" → dialog →
kolom workbook diisi path MENTAH → _start() LANGSUNG (mesin run lama:
worker QThread + progres + ⏹ Batalkan + ringkasan + render tab lain).

[R150-1] ensure_rekap_header: passthrough identitas utk header normal
         (file standar tak tersentuh); repair header tergeser (baris
         judul + kosong di atas header → dipromosi, nilai float 1.0
         dihitung hari "1" — bug calamine C3-a); header tak terdeteksi →
         passthrough (validate_rekap_schema yang bicara jujur).
[R150-2] normalize_rekap_values: JENIS 'waste ' → 'WASTE' (baris selamat
         filter stage_01 exact-match); identity di-strip ('GR ' → 'GR',
         NaN tetap NaN); hari kosong → 0 (baris hari-kosong-semua TIDAK
         terbuang filter TOTAL-notna stage_02); TRIGGER jujur: file
         standar W/S/T bersih → passthrough IDENTITAS (objek sama —
         SATUAN 'GR ' historis DATA_WASTE tak tersentuh, golden aman);
         sheet non-waste (BOM/SO) memicu walau JENIS bersih.
[R150-3] inject_bom_from_raw_rows: kolom inline TOTAL BOM dari baris
         JENIS=="BOM" (groupby resto×barang jumlah hari; kunci _key_str
         dua sisi; duplikat di-SUM; kunci kosong di-skip); no-op TOTAL
         BOM sudah ada (idempotent — file olahan/output re-run); no-op
         tanpa baris BOM; tanpa pasangan → NaN (bukan 0); caller frame
         tak termutasi (pola M6); log hitungan match hanya baris W/S/T.
[R150-4] run_pipeline pada file MENTAH == run_pipeline pada file OLAHAN
         converter (GOLDEN PARITY: jumlah baris + TOTAL BOM + Rill % to
         BOM + ANOMALY STATUS identik; baris log injeksi muncul di jalur
         mentah & TIDAK muncul di jalur olahan — idempotent).
[R150-5] file mentah ber-sheet DATABASE_SATUAN → HELPER/STATUS hidup
         (stage_09/09 join); header tergeser + BOM sekaligus (dua helper
         kompatibel satu run).
[R150-6] FILE ASLI user (skip-if-missing): run_pipeline LANGSUNG pada
         "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx" → angka golden
         2-langkah v2.14.0: 25.722 baris (WASTE 18.771 · SUSUT 2.204 ·
         TRIAL 4.747) + TOTAL BOM non-null 25.028 + 62 prioritas.
[R150-7] UI: tombol 🧮 teks+tooltip baru; klik → dialog → kolom workbook
         = path MENTAH → _start() dipanggil → PipelineWorker dibuat dgn
         path mentah (bukan worker olah terpisah); guard tolak ramah saat
         pipeline berjalan; log menyebut "sekali proses";
         RekapImportWorker tetap importable (API berdiri-sendiri — UI
         tidak lagi memakainya).
[R150-8] Manifest dua-arah tetap (workers.py::RekapImportWorker);
         Bantuan F1 menyebut alur sekali jalan; versi 2.15.0 sinkron
         semua situs; CRLF .bat utuh.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Offscreen SEBELUM import PySide6 (kontrak suite).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
REAL_REKAP = REPO / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx"

# Fixture builder dipakai ulang dari test_v2140 (satu sumber kebenaran
# bentuk file mentah sintetis: 6 baris W/S/T + 4 baris non-waste).
from tests.test_v2140 import (  # noqa: E402
    _build_rekap,
    _build_rekap_shifted,
    _qapp,
    _row,
    _synthetic_rows,
)

_DAYS = [str(d) for d in range(1, 32)]


# ============================================================
# [R150-1] — ensure_rekap_header
# ============================================================

class TestEnsureRekapHeader:

    def test_passthrough_header_normal(self, tmp_path):
        """Kolom sudah valid → nilai existing tak tersentuh + __SRC_ROW
        dipasang (v2.16.0: passthrough kini menambah kolom __SRC_ROW =
        baris fisik Excel 1-based; baris 1 = header, data mulai baris 2).
        Sebelum v2.16.0: passthrough identitas objek (out is df). Kini
        out = salinan df + kolom __SRC_ROW (anti side-effect ke pemanggil)."""
        from waste_anomaly.loader import _read_excel_fast, _normalize_columns
        from waste_anomaly.rekap_import import ensure_rekap_header, SRC_ROW_COL
        src = _build_rekap(tmp_path / "r.xlsx")
        df = _normalize_columns(
            _read_excel_fast(src, sheet_name="REKAP MENTAH", header=0))
        n = len(df)
        out = ensure_rekap_header(df)
        # __SRC_ROW dipasang
        assert SRC_ROW_COL in out.columns, "__SRC_ROW harus dipasang"
        # Nilai existing tak tersentuh (kolom & data sama)
        assert list(out.columns[:-1]) == list(df.columns), (
            "kolom existing tak boleh berubah")
        pd.testing.assert_frame_equal(
            out.drop(columns=[SRC_ROW_COL]), df)
        # __SRC_ROW = 2..n+1 (baris Excel: header=row1, data=row2+)
        assert list(out[SRC_ROW_COL]) == list(range(2, n + 2)), (
            "__SRC_ROW harus = baris Excel 2..n+1")
        # Idempoten: panggil ulang tak merusak
        out2 = ensure_rekap_header(out)
        assert list(out2[SRC_ROW_COL]) == list(range(2, n + 2))

    def test_repair_header_tergeser(self, tmp_path):
        """Baris judul + kosong di atas header → dipromosi; kolom hari
        float (calamine 1.0) tetap jadi '1'..'31'; data baris utuh."""
        from waste_anomaly.loader import _read_excel_fast
        from waste_anomaly.rekap_import import ensure_rekap_header
        src = _build_rekap_shifted(tmp_path / "shifted.xlsx")
        df = _read_excel_fast(src, sheet_name="Rekap Februari", header=0)
        out = ensure_rekap_header(df)
        cols = [str(c) for c in out.columns]
        for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG", "SATUAN"):
            assert rc in cols, f"kolom {rc} hilang pasca-promote: {cols[:10]}"
        n_days = sum(1 for c in cols if c in {str(d) for d in range(1, 32)})
        assert n_days == 31, f"kolom hari harus '1'..'31' (dapat {n_days})"
        assert "REKAP WASTE BULANAN" not in out.iloc[0].astype(str).tolist()
        # 10 baris data sintetis utuh (judul & header tak ikut jadi data)
        assert len(out) == 10
        assert set(out["JENIS"].dropna().unique()) >= {"WASTE", "BOM"}

    def test_header_tak_terdeteksi_passthrough(self):
        """Frame tanpa schema rekap di 6 baris pertama → passthrough
        apa adanya + __SRC_ROW dipasang (v2.16.0). Kolom existing tak
        berubah; __SRC_ROW = 2..n+1 (asumsi header baris-1 Excel)."""
        from waste_anomaly.rekap_import import ensure_rekap_header, SRC_ROW_COL
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        out = ensure_rekap_header(df)
        assert SRC_ROW_COL in out.columns
        assert list(out.columns[:-1]) == ["A", "B"]
        assert list(out[SRC_ROW_COL]) == [2, 3]

    def test_frame_kosong_passthrough(self):
        """Frame kosong/None → dikembalikan apa adanya (tak ada baris
        utk dipasangi __SRC_ROW)."""
        from waste_anomaly.rekap_import import ensure_rekap_header
        df = pd.DataFrame()
        assert ensure_rekap_header(df) is df
        assert ensure_rekap_header(None) is None


# ============================================================
# [R150-2] — normalize_rekap_values
# ============================================================

class TestNormalizeRekapValues:

    def _raw_frame(self):
        return pd.DataFrame(_synthetic_rows())

    def test_jenis_kanonis_baris_selamat(self):
        """'waste ' → 'WASTE' — tanpa ini baris terbuang filter stage_01
        (exact-match) padahal converter v2.14.0 menyelamatkannya."""
        from waste_anomaly.rekap_import import normalize_rekap_values
        out = normalize_rekap_values(self._raw_frame())
        jenis = set(out["JENIS"].dropna().unique())
        assert "waste " not in jenis
        assert jenis == {"WASTE", "SUSUT", "TRIAL", "BOM", "SO",
                         "BARANG MASUK"}
        # baris varian tetap ada (bukan dibuang)
        assert (out["JENIS"] == "WASTE").sum() == 4

    def test_identity_strip_nan_tetap(self):
        from waste_anomaly.rekap_import import normalize_rekap_values
        out = normalize_rekap_values(self._raw_frame())
        # SATUAN 'GR ' → 'GR'
        assert "GR " not in set(out["SATUAN"].dropna().astype(str))
        assert "GR" in set(out["SATUAN"].dropna().astype(str))
        # KETERANGAN NaN tetap NaN (bukan 'nan')
        assert out["KETERANGAN"].isna().sum() >= 1

    def test_hari_kosong_jadi_nol(self):
        """Sel hari kosong/teks → 0 numerik (parity file olahan: converter
        menulis day_filled; file standar user M-code memang 0-eksplisit).
        Baris hari-kosong-semua TIDAK terbuang stage_02 (TOTAL=0)."""
        from waste_anomaly.rekap_import import normalize_rekap_values
        raw = self._raw_frame()
        raw.loc[1, "5"] = None      # sel kosong di tengah data
        raw.loc[1, "31"] = "abc"    # teks sampah → 0 (coerce dulu)
        out = normalize_rekap_values(raw)
        assert pd.isna(out.loc[1, "5"]) is False
        assert out.loc[1, "5"] == 0
        assert out.loc[1, "31"] == 0
        day_cols = [c for c in out.columns
                    if c in {str(d) for d in range(1, 32)}]
        assert out[day_cols].isna().sum().sum() == 0

    def test_file_standar_bersih_passthrough_identitas(self):
        """TRIGGER jujur: JENIS semua W/S/T bersih → objek SAMA dikembalikan
        (DATA_WASTE standar — termasuk SATUAN 'GR ' historisnya — tak
        tersentuh; golden test lama aman)."""
        from waste_anomaly.rekap_import import normalize_rekap_values
        df = pd.DataFrame([
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR ", {1: 5}),
            _row("1041.BDGUKU", "ITEM X", "SUSUT", "SUSUT", "GR ", {2: 3}),
        ])
        out = normalize_rekap_values(df)
        assert out is df, "file standar harus passthrough identitas"
        assert out.loc[0, "SATUAN"] == "GR "  # historis tak di-strip

    def test_sheet_non_waste_bersih_tetap_memicu(self):
        """Sheet ber-JENIS bersih tapi ada baris non-waste (BOM/SO — ciri
        sheet mentah 'semua jenis') → normalisasi jalan walau JENIS semua
        kanonis (strip identity tetap dipakai)."""
        from waste_anomaly.rekap_import import normalize_rekap_values
        df = pd.DataFrame([
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR ", {1: 5}),
            _row("1041.BDGUKU", "ITEM X", "BOM", "BOM", "GR ", {1: 100}),
        ])
        out = normalize_rekap_values(df)
        assert out is not df
        assert out.loc[0, "SATUAN"] == "GR"

    def test_jenis_nan_tidak_memicu(self):
        """JENIS NaN sendirian BUKAN ciri sheet mentah — passthrough
        (stage_01 tetap membuangnya via isin, perilaku lama)."""
        from waste_anomaly.rekap_import import normalize_rekap_values
        df = pd.DataFrame([
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR ", {1: 5}),
        ])
        df.loc[0, "JENIS"] = None
        assert normalize_rekap_values(df) is df


# ============================================================
# [R150-3] — inject_bom_from_raw_rows
# ============================================================

class TestInjectBomFromRawRows:

    def test_inline_total_bom_nilai(self):
        """BOM 1041×ITEM X = 1000; 1042×ITEM Y = 250 — join ke baris W/S/T;
        tanpa pasangan → NaN (bukan 0 — beda dgn % to BOM guard)."""
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        df = pd.DataFrame(_synthetic_rows())
        out = inject_bom_from_raw_rows(df)
        assert "TOTAL BOM" in out.columns
        m = (out["NAMA RESTO"] == "1041.BDGUKU") & (out["JENIS"] == "TRIAL")
        assert out.loc[m, "TOTAL BOM"].iloc[0] == 1000.0
        m2 = (out["NAMA RESTO"] == "1042.KWGGAL") & (out["JENIS"] == "SUSUT")
        assert out.loc[m2, "TOTAL BOM"].iloc[0] == 250.0

    def test_noop_kolom_sudah_ada(self):
        """Idempotent: TOTAL BOM sudah ada (file olahan / output re-run)
        → passthrough identitas — nilai tak diganggu."""
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        df = pd.DataFrame(_synthetic_rows())
        df["TOTAL BOM"] = 999.0
        out = inject_bom_from_raw_rows(df)
        assert out is df
        assert (df["TOTAL BOM"] == 999.0).all()

    def test_noop_tanpa_baris_bom(self):
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        df = pd.DataFrame([
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR", {1: 5}),
        ])
        assert inject_bom_from_raw_rows(df) is df

    def test_duplikat_bom_dijumlah_kunci_kosong_diskip(self):
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        rows = [
            _row("1041.BDGUKU", "ITEM X", "BOM", "BOM", "GR", {1: 100}),
            _row("1041.BDGUKU", "ITEM X", "BOM", "BOM", "GR", {2: 50}),
            _row(None, "ITEM X", "BOM", "BOM", "GR", {1: 999}),   # kunci kosong
            _row("1041.BDGUKU", None, "BOM", "BOM", "GR", {1: 999}),
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR", {3: 7}),
        ]
        out = inject_bom_from_raw_rows(pd.DataFrame(rows))
        m = out["JENIS"] == "WASTE"
        assert out.loc[m, "TOTAL BOM"].iloc[0] == 150.0

    def test_caller_tak_termutasi(self):
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        df = pd.DataFrame(_synthetic_rows())
        inject_bom_from_raw_rows(df)
        assert "TOTAL BOM" not in df.columns, "frame caller tak boleh termutasi (M6)"

    def test_log_hitungan_match_hanya_wst(self):
        """Log 'N baris data (W/S/T) ber-TOTAL BOM' menghitung HANYA baris
        W/S/T (semantik bom_matched converter — baris BOM/SO ikut kena
        join tapi memang dibuang stage_01)."""
        from waste_anomaly.rekap_import import inject_bom_from_raw_rows
        logs: list[str] = []
        df = pd.DataFrame(_synthetic_rows())
        inject_bom_from_raw_rows(df, logger=logs.append)
        joined = " ".join(logs)
        assert "6 baris data (W/S/T) ber-TOTAL BOM" in joined
        assert "2.369" not in joined


# ============================================================
# [R150-4] — run_pipeline file MENTAH == file OLAHAN (GOLDEN PARITY)
# ============================================================

class TestPipelineSekaliJalan:

    def test_parity_mentah_vs_olahan(self, tmp_path):
        """Jantung fitur: SATU run pipeline pada file mentah ==
        convert dulu lalu pipeline (2-langkah v2.14.0) — baris, TOTAL BOM,
        Rill, status anomali identik; log injeksi muncul di jalur mentah
        & TIDAK di jalur olahan (idempotent)."""
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.rekap_import import convert_rekap_mentah
        from waste_anomaly.utils import load_config
        raw = _build_rekap(
            tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
        s_raw = run_pipeline(str(raw), key_akhir=31)
        assert s_raw["success"], s_raw.get("error")
        conv = convert_rekap_mentah(str(raw), config=load_config())
        s_conv = run_pipeline(conv["out_path"], key_akhir=31)
        assert s_conv["success"]

        df1, df2 = s_raw["df"], s_conv["df"]
        assert len(df1) == len(df2) == 6
        key = ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
               "SOURCE DATA"]
        a = df1.sort_values(key).reset_index(drop=True)
        b = df2.sort_values(key).reset_index(drop=True)
        for col in ("TOTAL BOM", "TOTAL", "Rill % to BOM", "AVG", "MAX",
                    "Count Hari"):
            assert np.allclose(a[col].fillna(-1), b[col].fillna(-1)), col
        assert a["ANOMALY STATUS"].tolist() == b["ANOMALY STATUS"].tolist()
        # BOM hidup di jalur mentah (tanpa injeksi: kolom absen → 0 sinyal)
        assert int(df1["TOTAL BOM"].notna().sum()) == 6
        assert (df1["Rill % to BOM"] > 0).any()
        # log injeksi: mentah YA, olahan TIDAK (TOTAL BOM inline sudah ada)
        assert "TOTAL BOM inline" in s_raw["log"]
        assert "TOTAL BOM inline" not in s_conv["log"]

    def test_header_tergeser_dan_bom_sekaligus(self, tmp_path):
        """Dua helper kompatibel satu run: header tergeser diperbaiki,
        lalu BOM diinjeksi — file 'paling mentah' tetap teranalisa penuh."""
        from waste_anomaly.pipeline import run_pipeline
        src = _build_rekap_shifted(tmp_path / "shifted.xlsx")
        s = run_pipeline(str(src), key_akhir=31)
        assert s["success"], s.get("error")
        assert len(s["df"]) == 6
        assert int(s["df"]["TOTAL BOM"].notna().sum()) == 6
        assert "header tergeser" in s["log"]
        assert "TOTAL BOM inline" in s["log"]

    def test_database_satuan_helper_hidup(self, tmp_path):
        """File mentah + sheet DATABASE_SATUAN → stage_09 join jalan:
        HELPER/STATUS dihitung (bukan null semua)."""
        from waste_anomaly.pipeline import run_pipeline
        # Kolom helper persis kontrak stage_09 (CANCEL NOTA/SUSUT/TRIAL/
        # HANDLING/... + KUALITAS — category_map KETERANGAN 'Kualitas').
        satuan_rows = [{
            "NAMA ITEM": "ITEM X", "SUSUT": 0, "TRIAL": 0,
            "HANDLING": 0, "KUALITAS": 1,
        }]
        src = _build_rekap(
            tmp_path / "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx",
            satuan_rows=satuan_rows)
        s = run_pipeline(str(src), key_akhir=31)
        assert s["success"], s.get("error")
        df = s["df"]
        assert "HELPER" in df.columns
        # baris WASTE-Kualitas ITEM X → helper 1 (kategori map Kualitas)
        m = (df["NAMA BARANG"] == "ITEM X") & (df["JENIS"] == "WASTE") \
            & (df["KETERANGAN"] == "Kualitas")
        assert df.loc[m, "HELPER"].notna().any()
        assert (df.loc[m, "HELPER"] == 1).any()
        assert "DATABASE_SATUAN loaded" in s["log"]

    def test_file_standar_tak_tersentuh(self):
        """File standar (sample_workbook.xlsx — JENIS bersih + BOM via
        sheet terpisah): TIGA helper REPAIR no-op — log tanpa pesan repair,
        hasil == perilaku pra-v2.15.0 (golden lama tak bergeser).

        v2.16.0: __SRC_ROW dipasang UNIVERSAL (semua file, including
        standar) — pesan "[rekap_import] pasang __SRC_ROW" BOLEH muncul
        (injeksi metadata, bukan repair data). Fragmen repair spesifik
        ('header tergeser', 'TOTAL BOM inline', 'dinormalisasi') tetap
        tak boleh muncul di file standar."""
        sample = REPO / "sample_workbook.xlsx"
        if not sample.exists():
            pytest.skip("sample_workbook.xlsx tidak ada")
        from waste_anomaly.pipeline import run_pipeline
        s = run_pipeline(str(sample), key_akhir=31)
        assert s["success"], s.get("error")
        assert s["total_rows"] > 0
        # Fragmen REPAIR spesifik — tak boleh muncul di file standar.
        # (v2.16.0: "rekap_import" dihapus dari daftar — modul itu kini
        # selalu dipanggil utk injeksi __SRC_ROW, bukan tanda repair.)
        for frag in ("header tergeser", "TOTAL BOM inline", "dinormalisasi"):
            assert frag not in s["log"], f"file standar tersentuh repair: {frag}"

    def test_status_baris_kosong_selamat(self, tmp_path):
        """Baris WASTE tanpa nilai hari (sheet mentah: sel kosong) →
        hari 0 → TOTAL 0 → baris TETAP ADA dgn Status2 'Kosong' (parity
        converter; TANPA normalisasi baris ini terbuang stage_02)."""
        from waste_anomaly.pipeline import run_pipeline
        rows = [
            _row("1041.BDGUKU", "ITEM X", "WASTE", "Kualitas", "GR",
                 {1: 10, 5: 30}),
            _row("1041.BDGUKU", "ITEM Z", "WASTE", "Handling", "GR", {}),
            _row("1041.BDGUKU", "ITEM X", "BOM", "BOM", "GR", {1: 100}),
        ]
        # kosongkan semua hari baris ITEM Z (None, bukan 0)
        for r in rows:
            if r["NAMA BARANG"] == "ITEM Z":
                for d in _DAYS:
                    r[d] = None
        src = _build_rekap(tmp_path / "r.xlsx", rows=rows)
        s = run_pipeline(str(src), key_akhir=31)
        assert s["success"], s.get("error")
        df = s["df"]
        assert (df["NAMA BARANG"] == "ITEM Z").any(), (
            "baris hari-kosong-semua terbuang — parity converter rusak")
        z = df[df["NAMA BARANG"] == "ITEM Z"]
        assert int(z["TOTAL"].iloc[0]) == 0


# ============================================================
# [R150-6] — FILE ASLI user (golden 2-langkah v2.14.0)
# ============================================================

class TestFileAsli:

    def test_file_asli_golden_sekali_jalan(self):
        """run_pipeline LANGSUNG pada file mentah asli 54.160 baris →
        angka IDENTIK jalur 2-langkah v2.14.0 (E2E worklog: convert 14
        dtk + pipeline 18 dtk): 25.722 baris · W 18.771 · S 2.204 ·
        T 4.747 · TOTAL BOM non-null 25.028 · 62 prioritas."""
        if not REAL_REKAP.exists():
            pytest.skip("file asli user tidak ada di repo")
        from waste_anomaly.pipeline import run_pipeline
        s = run_pipeline(str(REAL_REKAP), key_akhir=31)
        assert s["success"], s.get("error")
        assert s["total_rows"] == 25722
        vc = s["df"]["JENIS"].value_counts().to_dict()
        assert vc == {"WASTE": 18771, "TRIAL": 4747, "SUSUT": 2204}
        assert int(s["df"]["TOTAL BOM"].notna().sum()) == 25028
        assert s["prioritas_count"] == 62
        assert "TOTAL BOM inline" in s["log"]
        assert "dinormalisasi" in s["log"]


# ============================================================
# [R150-7] — UI sekali jalan
# ============================================================

class _PWStub:
    """Stub PipelineWorker — kontrak sinyal dipakai view (progress/done/
    failed/finished + deleteLater); start no-op; argumen konstruktur
    direkam supaya test membuktikan worker dibuat dgn path MENTAH."""

    class _Sig:
        def __init__(self):
            self._slots = []

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *a):
            for s in self._slots:
                s(*a)

    progress = None
    done = None
    failed = None
    finished = None
    created: list = []

    def __init__(self, workbook, key_akhir, parent=None):
        type(self).progress = self._Sig()
        type(self).done = self._Sig()
        type(self).failed = self._Sig()
        type(self).finished = self._Sig()
        self.workbook = workbook
        self.key_akhir = key_akhir
        type(self).created.append((workbook, key_akhir))

    def deleteLater(self):
        pass

    def start(self):
        pass


class TestUiSekaliJalan:

    def _view(self, ctx):
        import ui.view_pipeline as vp
        return vp.PipelineView(ctx)

    def test_tombol_dan_tooltip(self):
        app = _qapp()
        from ui.state import AppContext
        view = self._view(AppContext({}))
        try:
            btn = view._btn_import
            assert "Olah & Jalankan REKAP MENTAH" in btn.text()
            assert "REKAP MENTAH_01-31" in btn.toolTip()
            assert "SEKALI JALAN" in btn.toolTip()
        finally:
            view.close()
            view.deleteLater()

    def test_alur_sekali_jalan_path_mentah_start_langsung(
            self, tmp_path, monkeypatch):
        """Dialog → kolom workbook = path MENTAH → _start() LANGSUNG:
        PipelineWorker dibuat dgn path itu (TIDAK ada worker olah
        terpisah / file antara); mode run aktif (tombol jadi Batalkan)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        ctx = AppContext({})
        view = self._view(ctx)
        raw = _build_rekap(tmp_path / "REKAP MENTAH mentah.xlsx")
        monkeypatch.setattr(
            vp.QFileDialog, "getOpenFileName",
            classmethod(lambda cls, *a, **k: (str(raw), "")))
        _PWStub.created.clear()
        monkeypatch.setattr(vp, "PipelineWorker", _PWStub)
        try:
            view._on_import_rekap()
            app.processEvents()
            # kolom workbook = path MENTAH (bukan file olahan — tidak ada)
            assert view.current_workbook() == str(raw)
            # worker pipeline dibuat dgn path mentah & langsung start
            assert _PWStub.created == [(str(raw), 31)]
            assert view._running, "_start() harus terpanggil (mode run)"
            assert "Batalkan" in view._btn_run.text()
            # log menyebut sekali proses + tidak ada file antara
            lines = " ".join(ctx.log_lines)
            assert "sekali proses" in lines
            assert not any("terolah" in l for l in ctx.log_lines), (
                "log 2-langkah lama ('terolah') tak boleh muncul lagi")
        finally:
            view._running = False
            view._worker = None
            view.close()
            view.deleteLater()

    def test_tolak_saat_pipeline_berjalan(self, monkeypatch):
        """Pipeline berjalan → klik 🧮 = tolak ramah; worker pipeline BARU
        tidak dibuat (guard klik saat run)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        from PySide6.QtWidgets import QMessageBox
        app = _qapp()
        view = self._view(AppContext({}))
        infos: list = []
        monkeypatch.setattr(
            QMessageBox, "information",
            lambda *a, **k: infos.append(a) or QMessageBox.Ok)
        _PWStub.created.clear()
        monkeypatch.setattr(vp, "PipelineWorker", _PWStub)
        monkeypatch.setattr(
            vp.QFileDialog, "getOpenFileName",
            classmethod(lambda cls, *a, **k: ("/tmp/mentah.xlsx", "")))
        try:
            view._running = True
            view._on_import_rekap()
            assert infos, "dialog tolak harus muncul"
            assert _PWStub.created == []
        finally:
            view._running = False
            view.close()
            view.deleteLater()

    def test_dialog_batal_tak_memulai_run(self, monkeypatch):
        """Dialog dibatalkan (path kosong) → TIDAK ada worker, kolom
        workbook tak diisi (bukan run kosong)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        view = self._view(AppContext({}))
        _PWStub.created.clear()
        monkeypatch.setattr(vp, "PipelineWorker", _PWStub)
        monkeypatch.setattr(
            vp.QFileDialog, "getOpenFileName",
            classmethod(lambda cls, *a, **k: ("", "")))
        try:
            view._on_import_rekap()
            app.processEvents()
            assert _PWStub.created == []
            assert view.current_workbook() == ""
            assert not view._running
        finally:
            view.close()
            view.deleteLater()

    def test_worker_rekap_tetap_importable_api(self):
        """RekapImportWorker tetap ada di ui.workers (API berdiri-sendiri
        utk ekspor programatik — UI tidak lagi memakainya; manifest
        test_v270_wave4 + test_v2140 tetap menguncinya)."""
        from PySide6.QtCore import QThread
        from ui.workers import RekapImportWorker
        assert issubclass(RekapImportWorker, QThread)


# ============================================================
# [R150-8] — manifest + Bantuan + versi 2.15.0 + CRLF
# ============================================================

class TestManifestBantuanVersi:

    def test_manifest_dua_arah_utuh(self):
        manifest = (REPO / "tests" / "fixtures" /
                    "ui_methods_manifest.txt").read_text(encoding="utf-8")
        assert "workers.py::RekapImportWorker" in manifest
        assert "workers.py::PipelineWorker" in manifest

    def test_bantuan_menyebut_sekali_jalan(self):
        """F1 Bantuan seksi Tab Pipeline menyebut tombol baru + janji
        SEKALI JALAN tanpa file antara (regresi dokumentasi — pola B24)."""
        src = (UI / "app.py").read_text(encoding="utf-8")
        assert "Jalankan REKAP MENTAH" in src
        assert "REKAP MENTAH_01-31" in src
        assert "SEKALI" in src
        assert "tanpa file olahan antara" in src

    def test_versi_2150_sinkron(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        cfg = load_config()
        assert APP_VERSION == __version__ == cfg.get("version") == "2.18.1"
        init_src = (REPO / "waste_anomaly" / "__init__.py").read_text(
            encoding="utf-8")
        assert "Versi: 2.18.1" in init_src
        mulai = (REPO / "MULAI.bat").read_bytes()
        assert b"v2.17.0" in mulai
        setup = (REPO / "SETUP.bat").read_bytes()
        assert b"v2.17.0" in setup
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        # v2.18.1: README dirapikan (150KB→11KB, d4ea094) — riwayat versi
        # per-rilis dipindah ke commit history; pin README kini versi
        # SAAT INI (pola sama dgn test_v2181). Pin .bat v2.17.0 tetap:
        # sebutan historis fitur pythonw masih ada di kedua file itu.
        assert "v2.18.1" in readme

    def test_crlf_bat_utuh(self):
        """MULAI.bat/SETUP.bat tetap CRLF penuh (kontrak gelombang 1-6)."""
        for bat in ("MULAI.bat", "SETUP.bat"):
            raw = (REPO / bat).read_bytes()
            txt = raw.decode("utf-8", errors="replace")
            n_lf = txt.count("\n")
            n_crlf = txt.count("\r\n")
            assert n_lf == n_crlf, f"{bat}: CRLF rusak ({n_crlf}/{n_lf})"

    def test_pipeline_memanggil_helper_rekap(self):
        """pipeline.py memanggil KETIGA helper di fase LOAD (kontrak
        arsitektur sekali jalan — bukan cuma UI yang mengolah)."""
        src = (REPO / "waste_anomaly" / "pipeline.py").read_text(
            encoding="utf-8")
        for fn in ("ensure_rekap_header", "normalize_rekap_values",
                   "inject_bom_from_raw_rows"):
            assert fn in src, f"pipeline tidak memanggil {fn}"
