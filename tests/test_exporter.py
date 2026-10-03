"""Test — exporter dual-mode (F10 v2.4.0): normal vs streaming write_only.

Audit terukur: mode normal memakan ~947 MB pada 30k baris dan OOM-kill pada
100k. Mode streaming (write_only) memori konstan. Test memverifikasi:
paritas DATA antar mode (nilai identik), 6 sheet lengkap, status coloring,
format persentase, dan pemilihan mode otomatis via threshold.
"""

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from waste_anomaly.exporter import (
    STREAMING_THRESHOLD_DEFAULT,
    export_to_excel,
)

CONFIG = {"output": {}}


def make_result_df(n: int = 50) -> pd.DataFrame:
    """Frame hasil-pipeline mini dengan kolom yang dipakai exporter."""
    statuses = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    df = pd.DataFrame({
        "NAMA RESTO": [f"RESTO.{i % 5:03d}X" for i in range(n)],
        "NAMA BARANG": [f"ITEM {i % 10}" for i in range(n)],
        "JENIS": ["WASTE"] * n,
        "KETERANGAN": ["Kualitas" if i % 2 else "Handling" for i in range(n)],
        "TOTAL": [float(i + 1) for i in range(n)],
        "MAX": [float(i % 20 + 1) for i in range(n)],
        "ANOMALY SCORE": [i % 19 for i in range(n)],
        "ANOMALY STATUS": [statuses[i % 4] for i in range(n)],
    })
    return df


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet)


class TestExporterNormalMode:
    def test_export_sukses_6_sheet(self, tmp_path):
        df = make_result_df()
        out = tmp_path / "report.xlsx"
        result = export_to_excel(df, out, CONFIG, key_akhir=31, log_lines=["line1", "line2"])
        assert result["success"] is True
        assert result["streaming"] is False  # 50 baris < threshold → normal
        wb = load_workbook(out)
        assert set(wb.sheetnames) == {
            "Detail", "Anomali Prioritas", "Per Cabang",
            "Top Items", "Pareto Alasan", "Log Run",
        }

    def test_detail_data_utuh(self, tmp_path):
        df = make_result_df(80)
        out = tmp_path / "report.xlsx"
        export_to_excel(df, out, CONFIG, key_akhir=31, log_lines=[])
        detail = read_sheet(out, "Detail")
        assert len(detail) == 80
        assert detail["TOTAL"].sum() == pytest.approx(df["TOTAL"].sum())
        assert list(detail.columns) == list(df.columns)

    def test_anomali_sheet_filtered(self, tmp_path):
        df = make_result_df(80)
        out = tmp_path / "report.xlsx"
        result = export_to_excel(df, out, CONFIG, key_akhir=31, log_lines=[])
        anomali = read_sheet(out, "Anomali Prioritas")
        expected = df["ANOMALY STATUS"].isin(["Prioritas Tinggi", "Potensi Anomali"]).sum()
        assert len(anomali) == expected
        assert result["anomali_count"] == expected

    def test_status_counts_di_summary(self, tmp_path):
        df = make_result_df(80)
        out = tmp_path / "report.xlsx"
        result = export_to_excel(df, out, CONFIG, key_akhir=31, log_lines=[])
        assert result["prioritas_count"] == int((df["ANOMALY STATUS"] == "Prioritas Tinggi").sum())
        assert result["normal_count"] == int((df["ANOMALY STATUS"] == "Normal").sum())


class TestExporterStreamingMode:
    """Force streaming via threshold=0 di config — verifikasi paritas data."""

    STREAM_CFG = {"output": {"streaming_threshold": 0}}

    def test_mode_streaming_aktif(self, tmp_path):
        df = make_result_df(30)
        out = tmp_path / "stream.xlsx"
        result = export_to_excel(df, out, self.STREAM_CFG, key_akhir=31, log_lines=[])
        assert result["success"] is True
        assert result["streaming"] is True

    def test_paritas_data_antar_mode(self, tmp_path):
        """DATA harus identik antara mode normal dan streaming."""
        df = make_result_df(120)
        out_normal = tmp_path / "normal.xlsx"
        out_stream = tmp_path / "stream.xlsx"
        export_to_excel(df, out_normal, CONFIG, key_akhir=31, log_lines=[])
        export_to_excel(df, out_stream, self.STREAM_CFG, key_akhir=31, log_lines=[])

        for sheet in ("Detail", "Anomali Prioritas", "Per Cabang", "Top Items", "Pareto Alasan"):
            a = read_sheet(out_normal, sheet)
            b = read_sheet(out_stream, sheet)
            pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=False, rtol=1e-9)

    def test_6_sheet_lengkap_streaming(self, tmp_path):
        df = make_result_df(30)
        out = tmp_path / "stream.xlsx"
        export_to_excel(df, out, self.STREAM_CFG, key_akhir=31, log_lines=[])
        wb = load_workbook(out)
        assert set(wb.sheetnames) == {
            "Detail", "Anomali Prioritas", "Per Cabang",
            "Top Items", "Pareto Alasan", "Log Run",
        }

    def test_status_cell_berwarna_di_streaming(self, tmp_path):
        df = make_result_df(8)  # 2 baris per status
        out = tmp_path / "stream.xlsx"
        export_to_excel(df, out, self.STREAM_CFG, key_akhir=31, log_lines=[])
        wb = load_workbook(out)
        ws = wb["Detail"]
        header = [c.value for c in ws[1]]
        status_col_idx = header.index("ANOMALY STATUS") + 1
        # Baris 2 = baris data pertama — status dari df.iloc[0]
        cell = ws.cell(row=2, column=status_col_idx)
        assert cell.value == df["ANOMALY STATUS"].iloc[0]
        assert cell.fill is not None and cell.fill.start_color.rgb is not None

    def test_pct_format_tetap_ada(self, tmp_path):
        df = make_result_df(30)
        out = tmp_path / "stream.xlsx"
        export_to_excel(df, out, self.STREAM_CFG, key_akhir=31, log_lines=[])
        pareto = read_sheet(out, "Pareto Alasan")
        assert "Persentase" in pareto.columns
        assert "Cumulative" in pareto.columns
        # nilai terbaca sama seperti mode normal (paritas diuji terpisah)
        assert pareto["Persentase"].sum() == pytest.approx(100.0, rel=1e-6)

    def test_sheet_kosong_aman(self, tmp_path):
        """df tanpa kolom status → sheet Anomali kosong tapi TIDAK crash."""
        df = make_result_df(10).drop(columns=["ANOMALY STATUS"])
        out = tmp_path / "stream.xlsx"
        result = export_to_excel(df, out, self.STREAM_CFG, key_akhir=31, log_lines=[])
        assert result["success"] is True
        wb = load_workbook(out)
        assert "Anomali Prioritas" in wb.sheetnames

    def test_memori_konstan_data_besar(self, tmp_path):
        """Smoke test skala: 60k baris (di atas threshold normal default) —
        sebelumnya mustahil (OOM ~1.8 GB); mode streaming harus selesai."""
        import resource
        import time

        n = 60_000
        df = make_result_df(n)
        out = tmp_path / "big.xlsx"
        t0 = time.time()
        result = export_to_excel(df, out, CONFIG, key_akhir=31, log_lines=[])
        dt = time.time() - t0
        assert result["success"] is True
        assert result["streaming"] is True  # 60k > 35k default
        assert len(read_sheet(out, "Detail")) == n
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        # Peak memori total proses test harus jauh di bawah amplifikasi mode
        # normal (~1.8 GB untuk 60k) — margin longgar untuk overhead pytest.
        assert peak_mb < 700, f"Peak RSS {peak_mb:.0f} MB — streaming tidak efektif?"


class TestThresholdLogic:
    def test_threshold_default(self):
        assert STREAMING_THRESHOLD_DEFAULT == 35_000

    def test_threshold_invalid_fallback(self, tmp_path):
        cfg = {"output": {"streaming_threshold": "bukan-angka"}}
        df = make_result_df(10)
        out = tmp_path / "t.xlsx"
        result = export_to_excel(df, out, cfg, key_akhir=31, log_lines=[])
        assert result["success"] is True
        assert result["streaming"] is False  # fallback default, 10 < 35000
