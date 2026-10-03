"""Regression test — golden output pipeline end-to-end pada fixture asli.

Fixture: DATA_WASTE.xlsx yang di-commit di repo (25.901 baris, 20 cabang).
Test ini mengunci baseline M-fidelity: refactor / upgrade pandas / perubahan
threshold yang mengubah angka di bawah AKAN terdeteksi di sini.

GOLDEN (v2.3.2 SETELAH fix F7 — normalisasi 15 digit signifikan; pandas 2.2.3,
numpy 1.26, Python 3.10+):
    total_rows    = 25901
    anomali_count =   399   (status != Normal)
    prioritas     =    41
    potensi       =   358
    review        =   398
    normal        = 25104
    cabang        =    20
    item          =   173

PERUBAHAN GOLDEN dari v2.3.1 (402/361/25099) → v2.3.2 (399/358/25104):
SEBENARNYA bukan regresi — 5 baris berada di boundary threshold dengan
FP-dust (mis. MAX=21.299999999999997, visually 21.3 di Excel). Fix F7
menormalisasi nilai ke 15 digit signifikan = semantik Excel/Power Query.
4 baris dust-false-positive jadi Normal; 1 baris dust-false-negative
(1071.PWKTAM GREEN THAI TEA, rasio 21.3/7.1 = 3.0 persis) kini konsisten
terdeteksi di SEMUA run (dulu hanya terdeteksi di run ke-2 — idempotency
rusak). Detail: tests/test_float_precision.py.

Run:  python -m pytest tests/test_pipeline_regression.py -v
(lambat ~15-25 detik — load Excel + 14 stage; di-CI pisah marker kalau perlu)
"""

from pathlib import Path

import pytest

from waste_anomaly.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "DATA_WASTE.xlsx"

GOLDEN = {
    "total_rows": 25901,
    "anomali_count": 399,
    "prioritas_count": 41,
    "potensi_count": 358,
    "review_count": 398,
    "normal_count": 25104,
    "cabang_count": 20,
    "item_count": 173,
}


pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(), reason="fixture DATA_WASTE.xlsx tidak ada di repo"
)


@pytest.fixture(scope="module")
def summary() -> dict:
    """Satu run pipeline untuk semua test di module ini (~15-25 s)."""
    result = run_pipeline(workbook_path=str(FIXTURE), key_akhir=31)
    assert result.get("success") is True, (
        f"Pipeline gagal — regression terdeteksi!\nLog:\n{result.get('log', '')[-2000:]}"
    )
    return result


class TestGoldenCounts:
    """Angka eksak — perubahan tanpa alasan = regresi."""

    def test_total_rows(self, summary):
        assert summary["total_rows"] == GOLDEN["total_rows"]

    def test_anomali_count(self, summary):
        assert summary["anomali_count"] == GOLDEN["anomali_count"]

    def test_prioritas_count(self, summary):
        assert summary["prioritas_count"] == GOLDEN["prioritas_count"]

    def test_potensi_count(self, summary):
        assert summary["potensi_count"] == GOLDEN["potensi_count"]

    def test_review_count(self, summary):
        assert summary["review_count"] == GOLDEN["review_count"]

    def test_normal_count(self, summary):
        assert summary["normal_count"] == GOLDEN["normal_count"]

    def test_cabang_count(self, summary):
        assert summary["cabang_count"] == GOLDEN["cabang_count"]

    def test_item_count(self, summary):
        assert summary["item_count"] == GOLDEN["item_count"]


class TestPipelineContract:
    """Kontrak API summary dict yang dipakai ui_app.py / CLI."""

    def test_key_akhir_tercatat(self, summary):
        assert summary["key_akhir"] == 31

    def test_config_load_error_none(self, summary):
        # None (string) artinya config.json valid — tidak ada warning korup
        assert summary.get("config_load_error") in (None, "None")

    def test_log_lines_ada(self, summary):
        log = summary.get("log", "")
        assert "Pipeline START" in log
        assert "Pipeline DONE" in log

    def test_df_final_tersedia(self, summary):
        df = summary.get("df")
        assert df is not None
        assert len(df) == GOLDEN["total_rows"]
        # Kolom inti M-canonical harus ada di output final
        for col in ("ANOMALY SCORE", "ANOMALY STATUS", "TOTAL", "KETERANGAN GABUNGAN"):
            assert col in df.columns, f"Kolom output wajib hilang: {col}"

    def test_status_domain_valid(self, summary):
        """Status hanya boleh dari 4 nilai kanonik — typo = anomali hilang."""
        valid = {"Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"}
        statuses = set(summary["df"]["ANOMALY STATUS"].dropna().unique())
        assert statuses <= valid, f"Status tak dikenal: {statuses - valid}"


class TestIdempotency:
    """Re-run pipeline pada output sendiri → hasil harus identik (klaim v2.1.1)."""

    def test_rerun_sama_hasil(self, summary):
        # Ambil hasil df stage final, jadikan input ulang
        df_out = summary["df"]
        import pandas as pd

        # Simpan ke xlsx temp — pipeline baca dari file, bukan df
        tmp = REPO_ROOT / "tests" / "_idempotency_tmp.xlsx"
        try:
            df_out.to_excel(tmp, index=False, sheet_name="DATA_WASTE")
            result2 = run_pipeline(workbook_path=str(tmp), key_akhir=31)
            assert result2["success"] is True
            # Golden counts harus IDENTIK (idempotent = hasil ulang sama)
            for key in ("total_rows", "anomali_count", "prioritas_count",
                        "potensi_count", "review_count", "normal_count"):
                assert result2[key] == GOLDEN[key], (
                    f"Idempotency rusak: {key} = {result2[key]} "
                    f"(harusnya {GOLDEN[key]})"
                )
        finally:
            if tmp.exists():
                tmp.unlink()
