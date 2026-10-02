"""
exporter.py — penulis output Excel multi-sheet dengan formatting.

Sheet:
  1. Detail            — semua baris, kolom mengikuti Final order M code
  2. Anomali Prioritas — hanya Prioritas Tinggi + Potensi Anomali
  3. Per Cabang        — ringkasan per NAMA RESTO
  4. Top Items         — top 20 NAMA BARANG by TOTAL
  5. Pareto Alasan     — group by KETERANGAN, sum TOTAL, cumulative %
  6. Log Run           — timestamp, parameter, summary stats
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


# ============================================================
# STYLE CONSTANTS
# ============================================================

HEADER_FILL = PatternFill(start_color="172033", end_color="172033", fill_type="solid")
HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Segoe UI", size=14, bold=True, color="172033")
BODY_FONT = Font(name="Segoe UI", size=10, color="1F2937")
MONO_FONT = Font(name="Consolas", size=10, color="1F2937")

STATUS_FILLS = {
    "Prioritas Tinggi": PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid"),
    "Potensi Anomali": PatternFill(start_color="EA580C", end_color="EA580C", fill_type="solid"),
    "Perlu Review": PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid"),
    "Normal": PatternFill(start_color="16A34A", end_color="16A34A", fill_type="solid"),
}
STATUS_FONT = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")

THIN_BORDER = Border(
    left=Side(style="thin", color="E5E7EB"),
    right=Side(style="thin", color="E5E7EB"),
    top=Side(style="thin", color="E5E7EB"),
    bottom=Side(style="thin", color="E5E7EB"),
)


# ============================================================
# MAIN ENTRY
# ============================================================

def export_to_excel(
    df: pd.DataFrame,
    output_path: str | os.PathLike,
    config: dict,
    key_akhir: int,
    log_lines: list[str],
) -> dict:
    """Tulis multi-sheet xlsx. Return summary dict."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)  # hapus default sheet

    sheet_cfg = config.get("output", {})

    # ---- 1. Detail ----
    detail_name = sheet_cfg.get("detail_sheet", "Detail")
    _write_sheet(wb, detail_name, df, freeze="A2", status_col="ANOMALY STATUS")

    # ---- 2. Anomali Prioritas ----
    anomali_name = sheet_cfg.get("anomali_sheet", "Anomali Prioritas")
    df_anomali = df[df["ANOMALY STATUS"].isin(["Prioritas Tinggi", "Potensi Anomali"])]
    if not df_anomali.empty:
        df_anomali = df_anomali.sort_values("ANOMALY SCORE", ascending=False)
    _write_sheet(wb, anomali_name, df_anomali, freeze="A2", status_col="ANOMALY STATUS")

    # ---- 3. Per Cabang ----
    per_cabang_name = sheet_cfg.get("per_cabang_sheet", "Per Cabang")
    df_cabang = _build_per_cabang(df)
    _write_sheet(wb, per_cabang_name, df_cabang, freeze="A2")

    # ---- 4. Top Items ----
    top_items_name = sheet_cfg.get("top_items_sheet", "Top Items")
    df_top = _build_top_items(df)
    _write_sheet(wb, top_items_name, df_top, freeze="A2")

    # ---- 5. Pareto Alasan ----
    pareto_name = sheet_cfg.get("pareto_sheet", "Pareto Alasan")
    df_pareto = _build_pareto(df)
    _write_sheet(wb, pareto_name, df_pareto, freeze="A2")

    # ---- 6. Log Run ----
    log_name = sheet_cfg.get("log_sheet", "Log Run")
    df_log = _build_log(df, key_akhir, log_lines)
    _write_sheet(wb, log_name, df_log, freeze="A2")

    # Save
    wb.save(output_path)

    # Build summary return
    total_rows = len(df)
    anomali_count = len(df_anomali)
    prioritas_count = int((df["ANOMALY STATUS"] == "Prioritas Tinggi").sum())
    potensi_count = int((df["ANOMALY STATUS"] == "Potensi Anomali").sum())
    review_count = int((df["ANOMALY STATUS"] == "Perlu Review").sum())
    normal_count = int((df["ANOMALY STATUS"] == "Normal").sum())

    return {
        "total_rows": total_rows,
        "anomali_count": anomali_count,
        "prioritas_count": prioritas_count,
        "potensi_count": potensi_count,
        "review_count": review_count,
        "normal_count": normal_count,
        "cabang_count": int(df["NAMA RESTO"].nunique()) if "NAMA RESTO" in df.columns else 0,
        "item_count": int(df["NAMA BARANG"].nunique()) if "NAMA BARANG" in df.columns else 0,
    }


# ============================================================
# SHEET WRITER (LOW LEVEL)
# ============================================================

def _write_sheet(
    wb: Workbook,
    sheet_name: str,
    df: pd.DataFrame,
    freeze: str | None = "A2",
    status_col: str | None = None,
):
    """Tulis DataFrame ke sheet baru dengan header stylized + auto-width."""
    if sheet_name in wb.sheetnames:
        # Rename jika sudah ada
        base = sheet_name
        i = 2
        while f"{base} ({i})" in wb.sheetnames:
            i += 1
        sheet_name = f"{base} ({i})"

    ws = wb.create_sheet(title=sheet_name[:31])  # Excel limit 31 char

    if df.empty:
        ws["A1"] = f"(Tidak ada data untuk sheet '{sheet_name}')"
        ws["A1"].font = Font(name="Segoe UI", size=10, italic=True, color="6B7280")
        return

    # Header
    cols = list(df.columns)
    for c_idx, col_name in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=c_idx, value=str(col_name))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    # Body
    for r_idx, row in enumerate(df.itertuples(index=False, name=None), start=2):
        for c_idx, val in enumerate(row, start=1):
            # Handle NaN -> empty
            if val is None or (isinstance(val, float) and np.isnan(val)):
                v = None
            elif isinstance(val, (np.integer,)):
                v = int(val)
            elif isinstance(val, (np.floating,)):
                v = float(val) if not np.isnan(val) else None
            elif isinstance(val, (list, dict)):
                v = str(val)
            else:
                v = val
            cell = ws.cell(row=r_idx, column=c_idx, value=v)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=False)

            # Status coloring
            if status_col and cols[c_idx - 1] == status_col and v in STATUS_FILLS:
                cell.fill = STATUS_FILLS[v]
                cell.font = STATUS_FONT
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # Auto-width (approximate; cap at 40)
    for c_idx, col_name in enumerate(cols, start=1):
        max_len = len(str(col_name))
        # Sample 100 rows max untuk efisiensi
        sample = df[col_name].astype(str).head(100).tolist()
        if sample:
            sample_max = max(len(s) for s in sample)
            max_len = max(max_len, min(sample_max, 60))
        width = min(max_len + 2, 40)
        ws.column_dimensions[get_column_letter(c_idx)].width = width

    # Header row height + freeze
    ws.row_dimensions[1].height = 28
    if freeze:
        ws.freeze_panes = freeze

    # Auto filter pada header
    last_col = get_column_letter(len(cols))
    ws.auto_filter.ref = f"A1:{last_col}{len(df) + 1}"


# ============================================================
# SHEET BUILDERS (ringkasan turunan)
# ============================================================

def _build_per_cabang(df: pd.DataFrame) -> pd.DataFrame:
    """Ringkasan per NAMA RESTO."""
    if "NAMA RESTO" not in df.columns:
        return pd.DataFrame()
    g = df.groupby("NAMA RESTO", dropna=False)
    out = g.agg(
        Total_Barang=("NAMA BARANG", "count"),
        Total_Waste=("TOTAL", "sum"),
        Max_Waste_Single=("MAX", "max"),
        Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
        Anomali_Potensi=("ANOMALY STATUS", lambda x: int((x == "Potensi Anomali").sum())),
        Anomali_Review=("ANOMALY STATUS", lambda x: int((x == "Perlu Review").sum())),
    ).reset_index()
    out = out.rename(columns={
        "NAMA RESTO": "Cabang",
        "Total_Barang": "Jumlah Baris",
        "Total_Waste": "Total Waste (qty)",
        "Max_Waste_Single": "Max Waste Harian",
    })
    out = out.sort_values("Anomali_Prioritas", ascending=False)
    return out


def _build_top_items(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Top N item by TOTAL."""
    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns:
        return pd.DataFrame()
    g = (
        df.groupby(["NAMA BARANG", "JENIS"], dropna=False)
        .agg(
            Total_Waste=("TOTAL", "sum"),
            Max_Waste=("MAX", "max"),
            Cabang_Terpengaruh=("NAMA RESTO", "nunique"),
            Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
        )
        .reset_index()
        .sort_values("Total_Waste", ascending=False)
        .head(top_n)
    )
    g.insert(0, "Rank", range(1, len(g) + 1))
    return g


def _build_pareto(df: pd.DataFrame) -> pd.DataFrame:
    """Pareto alasan (KETERANGAN) — sum TOTAL, cumulative %."""
    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns:
        return pd.DataFrame()
    g = (
        df.groupby("KETERANGAN", dropna=False)
        .agg(Total_Waste=("TOTAL", "sum"), Jumlah_Barang=("NAMA BARANG", "count"))
        .reset_index()
        .sort_values("Total_Waste", ascending=False)
    )
    grand_total = g["Total_Waste"].sum()
    if grand_total > 0:
        g["Persentase"] = (g["Total_Waste"] / grand_total)
        g["Cumulative"] = g["Persentase"].cumsum()
    else:
        g["Persentase"] = 0
        g["Cumulative"] = 0
    return g


def _build_log(df: pd.DataFrame, key_akhir: int, log_lines: list[str]) -> pd.DataFrame:
    """Sheet Log Run — ringkasan + timestamp + log lines."""
    rows = []
    rows.append(("Waktu Run", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    rows.append(("Key Akhir", str(key_akhir)))
    rows.append(("Total Baris Diproses", str(len(df))))
    rows.append(("Cabang Unik", str(df["NAMA RESTO"].nunique()) if "NAMA RESTO" in df.columns else "0"))
    rows.append(("Item Unik", str(df["NAMA BARANG"].nunique()) if "NAMA BARANG" in df.columns else "0"))
    if "ANOMALY STATUS" in df.columns:
        rows.append(("— Status —", ""))
        for status in ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]:
            cnt = int((df["ANOMALY STATUS"] == status).sum())
            rows.append((f"  {status}", str(cnt)))
    rows.append(("", ""))
    rows.append(("=== LOG PIPELINE ===", ""))
    for line in log_lines:
        rows.append(("", line))
    return pd.DataFrame(rows, columns=["Key", "Value"])
