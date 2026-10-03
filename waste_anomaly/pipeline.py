"""
pipeline.py — orchestrator 14 stage M code replica.

Penggunaan dasar:
    from waste_anomaly.pipeline import run_pipeline

    summary = run_pipeline(
        workbook_path="data/rekap.xlsx",
        key_akhir=31,
        output_path="output/Waste_Anomaly_Report.xlsx",  # optional — lihat catatan di bawah
        progress_callback=lambda msg, pct: print(f"[{pct:.0f}%] {msg}"),
    )
    df = summary["df"]  # hasil in-memory (tidak ada file Excel yang ditulis)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import stages
from .loader import load_bom, load_database_satuan, load_rekap_mentah
from .schema import SchemaValidationError, validate_rekap_schema
from .utils import clamp, load_config


class PipelineCancelledError(RuntimeError):
    """Run dibatalkan user via cancel_check — bukan error sistem.

    v2.4.0 (F9): pipeline kini punya hook pembatalan ANTAR STAGE. UI cukup
    pass ``cancel_check=lambda: event.is_set()``; pipeline mengeceknya
    sebelum setiap stage dan raise exception ini. Summary kembali dengan
    ``cancelled=True`` (success=False) — UI menampilkan pesan ramah.
    ``log`` membawa isi log sampai titik pembatalan.
    """

    def __init__(self, msg: str, log: str = ""):
        super().__init__(msg)
        self.log = log


def run_pipeline(
    workbook_path: str | os.PathLike,
    key_akhir: int | None = None,
    output_path: str | os.PathLike | None = None,
    config_path: str | os.PathLike | None = None,
    progress_callback=None,
    cancel_check=None,
) -> dict:
    """
    Jalankan pipeline lengkap. Return summary dict (untuk UI display).

    Args:
        workbook_path: Path ke workbook Excel sumber.
        key_akhir: Hari terakhir periode (1..31). Default dari config (31).
        output_path: accepted for backward-compat; in-memory result only —
            use exporter.export_to_excel separately if needed. Sejak v2.2 pipeline
            tidak menulis file Excel; folder output hanya dibuat bila param ini
            diberikan secara eksplisit.
        config_path: Path ke config.json custom (optional).
        progress_callback: callable(msg: str, pct: float) untuk update UI.
            pct SELALU numeric; baris log tanpa persentase (mis. dari loader)
            mengirim ulang nilai pct terakhir (monotonic, tidak reset ke 0).
        cancel_check: callable() -> bool, opsional (F9 v2.4.0). Dicek ANTAR
            STAGE — return True → pipeline berhenti, summary ``cancelled=True``.
            UI memakai ini supaya tombol "⏹ Batalkan Run" benar-benar efektif
            (dulu flag hanya dicek SETELAH pipeline selesai — pembatalan palsu).

    Returns:
        dict summary. Kunci penting: ``success`` (bool), ``df`` (DataFrame
        hasil), ``log`` (str). Bila dibatalkan: ``success=False`` +
        ``cancelled=True`` + ``error`` (pesan ramah). Bila skema input tidak
        valid: ``success=False`` + ``error`` (kolom wajib yang hilang + saran).
    """
    try:
        return _run_pipeline(
            workbook_path,
            key_akhir=key_akhir,
            output_path=output_path,
            config_path=config_path,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    except PipelineCancelledError as exc:
        return {
            "success": False,
            "cancelled": True,
            "error": str(exc),
            "log": exc.log,
        }


def _run_pipeline(
    workbook_path: str | os.PathLike,
    key_akhir: int | None = None,
    output_path: str | os.PathLike | None = None,
    config_path: str | os.PathLike | None = None,
    progress_callback=None,
    cancel_check=None,
) -> dict:
    config = load_config(config_path)
    if key_akhir is None:
        key_akhir = config.get("default_key_akhir", 31)
    key_akhir = clamp(int(key_akhir), 1, 31)

    # output_path diterima demi backward-compat API (v2.2+ hasil dikembalikan
    # in-memory — tidak ada penulisan file dari pipeline).
    output_path_provided = output_path is not None
    if output_path is None:
        output_path = Path("output") / config.get("output", {}).get(
            "default_filename", "Waste_Anomaly_Report.xlsx"
        )
    output_path = Path(output_path)

    log_lines: list[str] = []

    # Callback contract: progress_callback(msg, pct) — pct selalu numeric.
    # Baris log tanpa persentase (mis. logger dari loader) re-send pct terakhir
    # supaya progress bar UI tidak reset/mundur.
    last_pct = 0.0

    def _log(msg: str, pct: float | None = None):
        nonlocal last_pct
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        log_lines.append(line)
        if progress_callback:
            if pct is None:
                pct = last_pct
            else:
                last_pct = pct
            progress_callback(msg, pct)

    def _gate(stage_label: str, pct: float):
        """Log awal stage + cek cancel (F9 v2.4.0). Raise PipelineCancelledError
        bila user meminta pembatalan — efektif ANTAR STAGE, bukan setelah selesai."""
        _log(f"{stage_label} ...", pct)
        if cancel_check is not None and cancel_check():
            raise PipelineCancelledError(
                f"Run dibatalkan oleh user sebelum {stage_label}",
                log="\n".join(log_lines),
            )

    _log(f"=== Waste Anomaly Pipeline START ===", 0)
    _log(f"Workbook: {workbook_path}", 1)
    _log(f"Key Akhir: {key_akhir} (hanya hari 1..{key_akhir} dipakai)", 2)
    _log(f"Output: {output_path} (in-memory result — file tidak ditulis otomatis)", 3)

    # Hindari side-effect: folder output hanya dibuat bila caller eksplisit
    # memberikan output_path (pipeline sendiri tidak menulis file apa pun).
    if output_path_provided:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log(f"WARNING: gagal membuat folder output '{output_path.parent}': {exc}")

    # ---- LOAD ----
    _log("Loading DATA_WASTE ...", 5)
    df_rekap = load_rekap_mentah(workbook_path, config, logger=_log)

    # ---- VALIDASI SKEMA (F8 v2.4.0) ----
    # Anti degradasi senyap: header lowercase/missing dulunya diproses
    # 'sukses' dengan analisa setengah mati. Sekarang gagal keras + pesan jelas.
    try:
        schema_warnings = validate_rekap_schema(df_rekap, key_akhir, logger=_log)
    except SchemaValidationError as exc:
        _log(f"ERROR skema input: {exc}", 100)
        return {
            "success": False,
            "error": str(exc),
            "key_akhir": key_akhir,
            "log": "\n".join(log_lines),
        }
    for w in schema_warnings:
        _log(w)

    _log("Loading BOM ...", 8)
    df_bom = load_bom(workbook_path, config, logger=_log)

    _log("Loading DATABASE_SATUAN ...", 10)
    df_satuan = load_database_satuan(workbook_path, config, logger=_log)

    # ---- STAGE 1: SOURCE & CLEANUP ----
    _gate("Stage 1 — Source & cleanup", 15)
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
    _gate("Stage 2 — Per-row daily statistics", 20)
    df = stages.stage_02_stats(df, key_akhir, config)
    _log(f"  → {len(df)} baris valid (TOTAL not null)", 25)

    if df.empty:
        # M16: input dengan kolom hari 1-31 kosong/non-numeric menghasilkan 0 baris
        # setelah filter TOTAL.notna() — kembalikan pesan ramah, jangan crash di
        # stage 3+. (Guard serupa juga ada di stages.stage_10 — keduanya aman.)
        _log("ERROR: Tidak ada baris valid setelah filter TOTAL — cek kolom hari 1-31 dan JENIS", 100)
        return {
            "success": False,
            "error": "Tidak ada baris valid setelah filter TOTAL — cek kolom hari 1-31 dan JENIS",
            "key_akhir": key_akhir,
            "log": "\n".join(log_lines),
        }

    # ---- STAGE 3: REASON SUMMARY ----
    _gate("Stage 3 — Reason summary", 30)
    df = stages.stage_03_reason(df, key_akhir, config)

    if df.empty:
        _log("ERROR: Tidak ada baris tersisa setelah Stage 3 (reason summary)", 100)
        return {
            "success": False,
            "error": "Tidak ada baris tersisa setelah Stage 3 (reason summary)",
            "key_akhir": key_akhir,
            "log": "\n".join(log_lines),
        }

    # ---- STAGE 4: GROUP TOTALS ----
    _gate("Stage 4 — Group totals", 35)
    df = stages.stage_04_group(df, key_akhir, config)

    # ---- STAGE 5: BOM JOIN ----
    _gate("Stage 5 — BOM join", 40)
    df = stages.stage_05_bom(df, key_akhir, config, bom_df=df_bom)

    # ---- STAGE 6: PEER SUMMARY ----
    _gate("Stage 6 — Peer summary", 50)
    df = stages.stage_06_peer(df, key_akhir, config)

    # ---- STAGE 7: TOP 3 SUMMARY ----
    _gate("Stage 7 — Top 3 summary", 55)
    df = stages.stage_07_top(df, key_akhir, config)

    # ---- STAGE 8: MERGE (no-op) ----
    df = stages.stage_08_merge(df, key_akhir, config)

    # ---- STAGE 9: DATABASE_SATUAN JOIN ----
    _gate("Stage 9 — DATABASE_SATUAN join", 60)
    df = stages.stage_09_satuan(df, key_akhir, config, satuan_df=df_satuan)

    # ---- STAGE 10: HELPER / STATUS / % TO BOM ----
    _gate("Stage 10 — Helper / STATUS / % to BOM", 65)
    df = stages.stage_10_helper(df, key_akhir, config)

    # ---- STAGE 11: ANOMALY ANALYSIS ----
    _gate("Stage 11 — 12 sinyal anomali", 70)
    df = stages.stage_11_analysis(df, key_akhir, config)

    # ---- STAGE 12: EXPAND (no-op) ----
    df = stages.stage_12_expand(df, key_akhir, config)

    # ---- STAGE 12.5: WASTE FINGERPRINT + SISTEMATIK FLAG (NEW v2.3.0) ----
    _gate("Stage 12.5 — Waste Fingerprint + Sistematik Flag", 75)
    df = stages.stage_12_5_fingerprint(df, key_akhir, config)

    # ---- STAGE 12.6: QUADRANT CLASSIFICATION (NEW v2.3.0) ----
    _gate("Stage 12.6 — Quadrant Classification", 78)
    df = stages.stage_12_6_quadrant(df, key_akhir, config)

    # ---- STAGE 13: CLEANUP ----
    _gate("Stage 13 — Cleanup temporary", 81)
    df = stages.stage_13_cleanup(df, key_akhir, config)

    # ---- STAGE 14: FINAL ORDER ----
    _gate("Stage 14 — Final column order", 84)
    df = stages.stage_14_final(df, key_akhir, config)

    # ---- BUILD SUMMARY (NO Excel export — display directly in UI) ----
    _log("Build summary statistics ...", 88)
    summary = _build_summary(df, key_akhir, log_lines, config=config)

    _log("=== Pipeline DONE ===", 100)

    summary.update({
        "success": True,
        "df": df,  # return DataFrame langsung untuk display di UI (no Excel file)
        "rows_processed": len(df),
        "log": "\n".join(log_lines),
    })
    return summary


def _build_summary(df, key_akhir, log_lines, config: dict | None = None):
    """Build summary dict in-memory (no Excel export).

    v2.3.1 menambahkan field: ``key_akhir`` yang dipakai, ``config_load_error``
    (pass-through dari load_config bila ada) dan ``timestamp`` (ISO, diambil
    saat run selesai). UI membaca dict ini; key tambahan tidak mengganggu.
    """
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
        "key_akhir": key_akhir,
        "config_load_error": (config or {}).get("config_load_error"),
        "timestamp": datetime.now().isoformat(),
    }
