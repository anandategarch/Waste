"""Test — validasi skema input (schema.py, F8 v2.4.0) + cancel hook (F9).

Anti degradasi senyap: header lowercase dulunya diproses 'sukses' dengan
analisa setengah mati. Cancel hook: tombol ⏹ kini efektif ANTAR STAGE.
"""

from pathlib import Path

import pandas as pd
import pytest

from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.schema import SchemaValidationError, validate_rekap_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "DATA_WASTE.xlsx"
# v2.18.0: DATA_WASTE.xlsx dihapus dari repo (51d042f) — test cancel ENGINE
# tidak butuh data asli (hanya workbook valid); fallback sample sintetis
# supaya kontrak tetap teruji di CI (pola test_v21313).
WORKBOOK = FIXTURE if FIXTURE.exists() else REPO_ROOT / "sample_workbook.xlsx"


def _good_df(**override) -> pd.DataFrame:
    """Frame dengan skema valid minimal."""
    base = {
        "SOURCE DATA": ["WASTE BAHAN DAN PACKAGING"],
        "JENIS": ["WASTE"],
        "KETERANGAN": ["Kualitas"],
        "NAMA BARANG": ["AYAM WHOLE"],
        "NAMA RESTO": ["B.1001.MLGPAR"],
        "SATUAN": ["GR"],
        "1": [10.0], "2": [20.0], "3": [5.0],
    }
    base.update(override)
    return pd.DataFrame(base)


class TestSchemaValid:
    def test_skema_valid_tanpa_warning(self):
        warnings = validate_rekap_schema(_good_df(), key_akhir=3)
        assert warnings == []

    def test_fixture_asli_lolos(self):
        # v2.18.0: DATA_WASTE.xlsx dihapus dari repo (51d042f) — skip
        # bermartabat bila fixture lokal tak ada (pola test_pipeline_
        # regression), bukan FileNotFoundError merah di CI.
        if not FIXTURE.exists():
            pytest.skip(f"fixture lokal tak ada: {FIXTURE.name}")
        df = pd.read_excel(FIXTURE, sheet_name=0, nrows=5)
        warnings = validate_rekap_schema(df, key_akhir=31)
        # fixture lengkap 53 kolom — tidak boleh ada warning skema
        assert warnings == []


class TestSchemaHardErrors:
    def test_header_lowercase_ditolak(self):
        # Bug audit: sebelumnya 'Jenis' lowercase diproses sukses senyap!
        df = _good_df()
        df = df.rename(columns={"JENIS": "Jenis", "NAMA BARANG": "Nama Barang"})
        with pytest.raises(SchemaValidationError) as ei:
            validate_rekap_schema(df, key_akhir=3)
        msg = str(ei.value)
        assert "JENIS" in msg and "NAMA BARANG" in msg
        # saran near-miss harus menyebut kolom asli
        assert "Jenis" in msg and "Nama Barang" in msg

    def test_kolom_hilang_total(self):
        df = _good_df().drop(columns=["SATUAN"])
        with pytest.raises(SchemaValidationError) as ei:
            validate_rekap_schema(df, key_akhir=3)
        assert "SATUAN" in str(ei.value)

    def test_tanpa_kolom_hari(self):
        df = _good_df().drop(columns=["1", "2", "3"])
        with pytest.raises(SchemaValidationError) as ei:
            validate_rekap_schema(df, key_akhir=3)
        assert "hari" in str(ei.value).lower()

    def test_header_duplikat(self):
        df = _good_df()
        df["1"] = [99.0]  # kolom duplikat '1' → pandas akan mangle jadi '1.1'
        # simulasi header Excel duplikat (sebelum mangle):
        df_dup = df.copy()
        df_dup.columns = list(df_dup.columns[:-1]) + ["1"]
        with pytest.raises(SchemaValidationError) as ei:
            validate_rekap_schema(df_dup, key_akhir=3)
        assert "DUPLIKAT" in str(ei.value)


class TestSchemaWarnings:
    def test_hari_kurang_warning_bukan_error(self):
        df = _good_df().drop(columns=["3"])
        warnings = validate_rekap_schema(df, key_akhir=3)
        assert len(warnings) == 1
        assert "2/3" in warnings[0]

    def test_jenis_asing_warning(self):
        df = _good_df(**{"JENIS": ["RUSAK"]})
        warnings = validate_rekap_schema(df, key_akhir=3)
        assert any("RUSAK" in w for w in warnings)

    def test_logger_dipanggil_untuk_warning(self):
        df = _good_df().drop(columns=["3"])
        called = []
        validate_rekap_schema(df, key_akhir=3, logger=called.append)
        assert len(called) >= 1


class TestSchemaEndToEnd:
    def test_workbook_lowercase_gagal_jelas(self, tmp_path):
        """End-to-end: workbook dengan header lowercase → success=False + pesan
        actionable (bukan 'sukses' dengan analisa mati seperti dulu)."""
        df = _good_df()
        for i in range(4, 32):
            df[str(i)] = 0.0
        df = df.rename(columns={"JENIS": "Jenis"})
        wb = tmp_path / "lowercase.xlsx"
        df.to_excel(wb, index=False, sheet_name="Sheet1")

        result = run_pipeline(workbook_path=str(wb), key_akhir=31)
        assert result["success"] is False
        assert "JENIS" in result["error"]
        assert "Jenis" in result["error"]  # ada saran rename


class TestCancelHook:
    def test_cancel_langsung(self):
        """cancel_check True sejak awal → dibatalkan di gate pertama."""
        if not FIXTURE.exists():
            pytest.skip(f"fixture lokal tak ada: {FIXTURE.name} (v2.18.0)")
        result = run_pipeline(
            workbook_path=str(WORKBOOK),
            key_akhir=31,
            cancel_check=lambda: True,
        )
        assert result["success"] is False
        assert result.get("cancelled") is True
        assert "dibatalkan" in result["error"].lower()
        assert result["log"]  # log tetap terisi sampai titik batal

    def test_cancel_setelah_stage1(self):
        """Cancel aktif setelah Stage 1 selesai → pipeline berhenti di Stage 2
        (bukan menghitung sampai tuntas lalu dibuang — perilaku lama)."""
        state = {"stage1_done": False, "cancel": False}

        def cancel_check() -> bool:
            return state["cancel"]

        # progress callback: aktifkan cancel saat Stage 1 selesai
        def on_progress(msg, pct):
            if "baris setelah filter JENIS" in msg:
                state["cancel"] = True

        result = run_pipeline(
            workbook_path=str(WORKBOOK),
            key_akhir=31,
            progress_callback=on_progress,
            cancel_check=cancel_check,
        )
        assert result["success"] is False
        assert result.get("cancelled") is True
        # log berhenti di Stage 2 — Stage 11 dst TIDAK dijalankan
        assert "Stage 2 —" in result["log"]
        assert "Stage 11" not in result["log"]

    def test_tanpa_cancel_check_perilaku_tidak_berubah(self):
        # v2.18.0: GOLDEN 25.901 baris — butuh fixture DATA_WASTE.xlsx
        # asli (dihapus 51d042f); skip jujur bila tak ada (bukan fallback
        # sample — angka golden tak berlaku utk data sintetis).
        if not FIXTURE.exists():
            pytest.skip("fixture DATA_WASTE.xlsx (golden 25.901) tidak ada")
        """Backward-compat: tanpa cancel_check, pipeline jalan normal penuh."""
        result = run_pipeline(workbook_path=str(WORKBOOK), key_akhir=31)
        assert result["success"] is True
        assert result["total_rows"] == 25901
