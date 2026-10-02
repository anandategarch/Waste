"""
pipeline.py — orchestrator 14 stage M code replica.

Penggunaan dasar:
    from waste_anomaly.pipeline import run_pipeline

    summary = run_pipeline(
        workbook_path="data/rekap.xlsx",
        key_akhir=31,
        output_path="output/Waste_Anomaly_Report.xlsx",
        progress_callback=lambda msg, pct: print(f"[{pct:.0f}%] {msg}"),
    )
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import stages
from .loader import load_bom, load_database_satuan, load_rekap_mentah
from .utils import clamp, load_config


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_pipeline(
    workbook_path: str | os.PathLike,
    key_akhir: int | None = None,
    output_path: str | os.PathLike | None = None,
    config_path: str | os.PathLike | None = None,
    progress_callback=None,
) -> dict:
    """
    Jalankan pipeline lengkap. Return summary dict (untuk UI display).

    Args:
        workbook_path: Path ke workbook Excel sumber.
        key_akhir: Hari terakhir periode (1..31). Default dari config (31).
        output_path: Path output Excel. Default: 'output/Waste_Anomaly_Report.xlsx'.
        config_path: Path ke config.json custom (optional).
        progress_callback: callable(msg: str, pct: float) untuk update UI.
    """
    config = load_config(config_path)
    if key_akhir is None:
        key_akhir = config.get("default_key_akhir", 31)
    key_akhir = clamp(int(key_akhir), 1, 31)

    if output_path is None:
        output_path = Path("output") / config.get("output", {}).get(
            "default_filename", "Waste_Anomaly_Report.xlsx"
        )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []

    def _log(msg: str, pct: float | None = None):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        log_lines.append(line)
        if progress_callback:
            progress_callback(msg, pct if pct is not None else 0.0)

    _log(f"=== Waste Anomaly Pipeline START ===", 0)
    _log(f"Workbook: {workbook_path}", 1)
    _log(f"Key Akhir: {key_akhir} (hanya hari 1..{key_akhir} dipakai)", 2)
    _log(f"Output: {output_path}", 3)

    # ---- LOAD ----
    _log("Loading DATA_WASTE ...", 5)
    df_rekap = load_rekap_mentah(workbook_path, config, logger=_log)

    _log("Loading BOM ...", 8)
    df_bom = load_bom(workbook_path, config, logger=_log)

    _log("Loading DATABASE_SATUAN ...", 10)
    df_satuan = load_database_satuan(workbook_path, config, logger=_log)

    # ---- STAGE 1: SOURCE & CLEANUP ----
    _log("Stage 1 — Source & cleanup ...", 15)
    df = stages.stage_01_source(df_rekap, key_akhir, config)
    _log(f"  → {len(df)} baris setelah filter JENIS", 16)

    if df.empty:
        _log("ERROR: Tidak ada baris tersisa setelah filter JENIS (SUSUT/TRIAL/WASTE)", 100)
        return {
            "success": False,
            "error": "Tidak ada baris tersisa setelah filter JENIS",
            "log": "\n".join(log_lines),
        }

    # ---- STAGE 2: PER-ROW STATS ----
    _log("Stage 2 — Per-row daily statistics ...", 20)
    df = stages.stage_02_stats(df, key_akhir, config)
    _log(f"  → {len(df)} baris valid (TOTAL not null)", 25)

    # ---- STAGE 3: REASON SUMMARY ----
    _log("Stage 3 — Reason summary ...", 30)
    df = stages.stage_03_reason(df, key_akhir, config)

    # ---- STAGE 4: GROUP TOTALS ----
    _log("Stage 4 — Group totals ...", 35)
    df = stages.stage_04_group(df, key_akhir, config)

    # ---- STAGE 5: BOM JOIN ----
    _log("Stage 5 — BOM join ...", 40)
    df = stages.stage_05_bom(df, key_akhir, config, bom_df=df_bom)

    # ---- STAGE 6: PEER SUMMARY ----
    _log("Stage 6 — Peer summary ...", 50)
    df = stages.stage_06_peer(df, key_akhir, config)

    # ---- STAGE 7: TOP 3 SUMMARY ----
    _log("Stage 7 — Top 3 summary ...", 55)
    df = stages.stage_07_top(df, key_akhir, config)

    # ---- STAGE 8: MERGE (no-op) ----
    df = stages.stage_08_merge(df, key_akhir, config)

    # ---- STAGE 9: DATABASE_SATUAN JOIN ----
    _log("Stage 9 — DATABASE_SATUAN join ...", 60)
    df = stages.stage_09_satuan(df, key_akhir, config, satuan_df=df_satuan)

    # ---- STAGE 10: HELPER / STATUS / % TO BOM ----
    _log("Stage 10 — Helper / STATUS / % to BOM ...", 65)
    df = stages.stage_10_helper(df, key_akhir, config)

    # ---- STAGE 11: ANOMALY ANALYSIS ----
    _log("Stage 11 — 12 sinyal anomali ...", 70)
    df = stages.stage_11_analysis(df, key_akhir, config)

    # ---- STAGE 12: EXPAND (no-op) ----
    df = stages.stage_12_expand(df, key_akhir, config)

    # ---- STAGE 12.5: WASTE FINGERPRINT + SISTEMATIK FLAG (NEW v2.3.0) ----
    _log("Stage 12.5 — Waste Fingerprint + Sistematik Flag ...", 86)
    df = stages.stage_12_5_fingerprint(df, key_akhir, config)

    # ---- STAGE 12.6: QUADRANT CLASSIFICATION (NEW v2.3.0) ----
    _log("Stage 12.6 — Quadrant Classification ...", 87)
    df = stages.stage_12_6_quadrant(df, key_akhir, config)

    # ---- STAGE 13: CLEANUP ----
    _log("Stage 13 — Cleanup temporary ...", 80)
    df = stages.stage_13_cleanup(df, key_akhir, config)

    # ---- STAGE 14: FINAL ORDER ----
    _log("Stage 14 — Final column order ...", 85)
    df = stages.stage_14_final(df, key_akhir, config)

    # ---- BUILD SUMMARY (NO Excel export — display directly in UI) ----
    _log("Build summary statistics ...", 88)
    summary = _build_summary(df, key_akhir, log_lines)

    _log("=== Pipeline DONE ===", 100)

    summary.update({
        "success": True,
        "df": df,  # return DataFrame langsung untuk display di UI (no Excel file)
        "rows_processed": len(df),
        "key_akhir": key_akhir,
        "log": "\n".join(log_lines),
    })
    return summary


def _build_summary(df, key_akhir, log_lines):
    """Build summary dict in-memory (no Excel export)."""
    import numpy as np
    total_rows = len(df)
    status_col = "ANOMALY STATUS"
    if status_col in df.columns:
        prioritas_count = int((df[status_col] == "Prioritas Tinggi").sum())
        potensi_count = int((df[status_col] == "Potensi Anomali").sum())
        review_count = int((df[status_col] == "Perlu Review").sum())
        normal_count = int((df[status_col] == "Normal").sum())
        anomali_count = prioritas_count + potensi_count
    else:
        prioritas_count = potensi_count = review_count = normal_count = anomali_count = 0
    cabang_count = int(df["NAMA RESTO"].nunique()) if "NAMA RESTO" in df.columns else 0
    item_count = int(df["NAMA BARANG"].nunique()) if "NAMA BARANG" in df.columns else 0
    return {
        "total_rows": total_rows,
        "anomali_count": anomali_count,
        "prioritas_count": prioritas_count,
        "potensi_count": potensi_count,
        "review_count": review_count,
        "normal_count": normal_count,
        "cabang_count": cabang_count,
        "item_count": item_count,
    }
