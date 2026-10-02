"""
signals.py — 12 sinyal anomali + composite score + status + reasons + category + ranking.

Setara dengan section 11 (AddAnalysis) dari M code.

Setiap sinyal S1..S12 adalah boolean (0/1/2). Skor dijumlahkan → CompositeScore (max 19).
Status:
  Score >= 8 -> "Prioritas Tinggi"
  Score >= 5 -> "Potensi Anomali"
  Score >= 3 -> "Perlu Review"
  else       -> "Normal"
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import clamp, safe_div


# ============================================================
# MAIN ENTRY
# ============================================================

def compute_signals(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Tambah 12 sinyal + analisa kolom turunan. Setara AddAnalysis di M code."""
    th = config.get("thresholds", {})
    th_spike = th.get("TH_SPIKE", 3)
    th_max_avg_aktif = th.get("TH_MAX_AVG_AKTIF", 2.5)
    th_max_median = th.get("TH_MAX_MEDIAN", 3)
    th_max_second = th.get("TH_MAX_SECOND", 3)
    th_max_share_warn = th.get("TH_MAX_SHARE_WARN", 0.50)
    th_max_share_high = th.get("TH_MAX_SHARE_HIGH", 0.70)
    th_max_bom_warn = th.get("TH_MAX_BOM_WARN", 0.25)
    th_max_bom_high = th.get("TH_MAX_BOM_HIGH", 0.50)
    th_total_bom_warn = th.get("TH_TOTAL_BOM_WARN", 0.50)
    th_total_bom_high = th.get("TH_TOTAL_BOM_HIGH", 1.00)
    th_peer_min = th.get("TH_PEER_MIN", 3)
    th_peer_warn = th.get("TH_PEER_WARN", 2)
    th_peer_high = th.get("TH_PEER_HIGH", 3)
    th_last_share = th.get("TH_LAST_SHARE", 0.70)

    non_handling = config.get("non_handling_list", [
        "Alat/ Mesin", "Cancel Nota", "Eksternal", "Internal", "Over Stock",
    ])

    out = df.copy()

    # Pastikan kolom kalkulasi yang dipakai sinyal ada (None kalau tidak ada)
    for col in [
        "TOTAL", "MAX", "AVG", "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX",
        "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
        "MAX SHARE", "LAST DAY SHARE", "SCALE SIGNAL", "Count Hari",
        "TOTAL BOM", "Rill % to BOM",
        "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
        "TopTotal", "TopBOM",
        "JENIS", "KETERANGAN",
    ]:
        if col not in out.columns:
            out[col] = np.nan

    # Coerce numerik
    numeric_cols = [
        "TOTAL", "MAX", "AVG", "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX",
        "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
        "MAX SHARE", "LAST DAY SHARE", "Count Hari",
        "TOTAL BOM", "Rill % to BOM",
        "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
    ]
    for c in numeric_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # ============================================================
    # PRE-COMPUTE: rasio Max/BOM, Total/BOM, Max/Peer, Total/Peer
    # ============================================================
    out["_MaxBOMRatio"] = np.where(
        (out["MAX"].notna()) & (out["TOTAL BOM"].notna()) & (out["TOTAL BOM"] > 0),
        out["MAX"] / out["TOTAL BOM"], 0.0,
    )
    out["_TotalBOMRatio"] = np.where(
        (out["TOTAL"].notna()) & (out["TOTAL BOM"].notna()) & (out["TOTAL BOM"] > 0),
        out["TOTAL"] / out["TOTAL BOM"], 0.0,
    )
    out["_MaxPeerRatio"] = np.where(
        (out["MAX"].notna()) & (out["PEER MEDIAN MAX"].notna()) & (out["PEER MEDIAN MAX"] > 0),
        out["MAX"] / out["PEER MEDIAN MAX"], 0.0,
    )
    out["_TotalPeerRatio"] = np.where(
        (out["TOTAL"].notna()) & (out["PEER MEDIAN TOTAL"].notna()) & (out["PEER MEDIAN TOTAL"] > 0),
        out["TOTAL"] / out["PEER MEDIAN TOTAL"], 0.0,
    )

    # Helper Series
    count_val = out["Count Hari"].fillna(0)
    peer_count = out["PEER COUNT"].fillna(0)

    # ============================================================
    # SIGNAL 1 — MAX / AVG (TH_SPIKE)
    # ============================================================
    s1 = ((count_val >= 2) & (out["MAX / AVG"] >= th_spike)).astype(int)

    # ============================================================
    # SIGNAL 2 — MAX / AVG AKTIF (TH_MAX_AVG_AKTIF) — score 1 atau 2
    # ============================================================
    s2_cond = (count_val >= 3) & (out["MAX / AVG AKTIF"] >= th_max_avg_aktif)
    s2_score = np.where(s2_cond & (out["MAX / AVG AKTIF"] >= 4), 2,
                np.where(s2_cond, 1, 0))

    # ============================================================
    # SIGNAL 3 — MAX / MEDIAN AKTIF (TH_MAX_MEDIAN)
    # ============================================================
    s3 = np.where(
        (count_val >= 3) & (out["MAX / MEDIAN AKTIF"] >= th_max_median),
        2, 0,
    )

    # ============================================================
    # SIGNAL 4 — MAX SHARE (TH_MAX_SHARE_WARN/HIGH)
    # ============================================================
    s4 = np.where(
        out["MAX SHARE"] >= th_max_share_high, 2,
        np.where(out["MAX SHARE"] >= th_max_share_warn, 1, 0),
    )

    # ============================================================
    # SIGNAL 5 — MAX / SECOND MAX (TH_MAX_SECOND)
    # ============================================================
    s5 = np.where(
        (count_val >= 2) & (out["MAX / SECOND MAX"] >= th_max_second),
        1, 0,
    )

    # ============================================================
    # SIGNAL 6 — MAX / BOM (TH_MAX_BOM_WARN/HIGH)
    # ============================================================
    s6 = np.where(
        out["_MaxBOMRatio"] >= th_max_bom_high, 2,
        np.where(out["_MaxBOMRatio"] >= th_max_bom_warn, 1, 0),
    )

    # ============================================================
    # SIGNAL 7 — TOTAL / BOM (TH_TOTAL_BOM_WARN/HIGH)
    # ============================================================
    s7 = np.where(
        out["_TotalBOMRatio"] >= th_total_bom_high, 2,
        np.where(out["_TotalBOMRatio"] >= th_total_bom_warn, 1, 0),
    )

    # ============================================================
    # SIGNAL 8 — PEER MAX (TH_PEER_WARN/HIGH, gated by TH_PEER_MIN)
    # ============================================================
    peer_ok = peer_count >= th_peer_min
    s8 = np.where(
        peer_ok & (out["_MaxPeerRatio"] >= th_peer_high), 2,
        np.where(peer_ok & (out["_MaxPeerRatio"] >= th_peer_warn), 1, 0),
    )

    # ============================================================
    # SIGNAL 9 — PEER TOTAL (TH_PEER_HIGH, gated by TH_PEER_MIN)
    # ============================================================
    s9 = np.where(
        peer_ok & (out["_TotalPeerRatio"] >= th_peer_high), 1, 0,
    )

    # ============================================================
    # SIGNAL 10 — SINGLE DAY EVENT
    # Count=1 AND (MaxBOMRatio >= 0.10 OR MaxPeerRatio >= TH_PEER_WARN)
    # ============================================================
    s10 = np.where(
        (count_val == 1) & (
            (out["_MaxBOMRatio"] >= 0.10) |
            (out["_MaxPeerRatio"] >= th_peer_warn)
        ),
        1, 0,
    )

    # ============================================================
    # SIGNAL 11 — LAST DAY SHARE (TH_LAST_SHARE)
    # ============================================================
    s11 = np.where(
        out["LAST DAY SHARE"] >= th_last_share, 1, 0,
    )

    # ============================================================
    # SIGNAL 12 — SCALE SIGNAL (YES/NO)
    # ============================================================
    s12 = np.where(out["SCALE SIGNAL"].astype(str) == "YES", 2, 0)

    # ============================================================
    # COMPOSITE SCORE & STATUS
    # ============================================================
    score = (
        s1 + s2_score + s3 + s4 + s5 + s6 + s7 + s8 + s9 + s10 + s11 + s12
    )
    status = np.where(
        score >= 8, "Prioritas Tinggi",
        np.where(score >= 5, "Potensi Anomali",
        np.where(score >= 3, "Perlu Review", "Normal")),
    )

    # ============================================================
    # REASON TEXT (concat tiap sinyal yang triggered)
    # ============================================================
    def _build_reason(row):
        s1v, s2v, s3v, s4v, s5v, s6v, s7v, s8v, s9v, s10v, s11v, s12v = (
            row["_s1"], row["_s2"], row["_s3"], row["_s4"], row["_s5"],
            row["_s6"], row["_s7"], row["_s8"], row["_s9"], row["_s10"],
            row["_s11"], row["_s12"],
        )
        parts = []
        if s1v > 0: parts.append("Spike vs AVG")
        if s2v > 0: parts.append("MAX jauh di atas AVG aktif")
        if s3v > 0: parts.append("MAX jauh di atas MEDIAN aktif")
        if s4v > 0: parts.append("Konsentrasi MAX tinggi")
        if s5v > 0: parts.append("Gap MAX vs SECOND MAX")
        if s6v > 0: parts.append("MAX terhadap BOM tinggi")
        if s7v > 0: parts.append("TOTAL terhadap BOM tinggi")
        if s8v > 0: parts.append("MAX outlier terhadap peer")
        if s9v > 0: parts.append("TOTAL outlier terhadap peer")
        if s10v > 0: parts.append("Single-day event")
        if s11v > 0: parts.append("Dominasi hari terakhir")
        if s12v > 0: parts.append("Potensi salah skala")
        return " | ".join(parts)

    out["_s1"] = s1
    out["_s2"] = s2_score
    out["_s3"] = s3
    out["_s4"] = s4
    out["_s5"] = s5
    out["_s6"] = s6
    out["_s7"] = s7
    out["_s8"] = s8
    out["_s9"] = s9
    out["_s10"] = s10
    out["_s11"] = s11
    out["_s12"] = s12
    out["ANOMALY SCORE"] = score
    out["ANOMALY STATUS"] = status
    out["ANOMALY REASONS"] = out.apply(_build_reason, axis=1)

    # ============================================================
    # KATEGORI ANOMALI
    # if MAX/AVG >= TH_SPIKE -> "Lonjakan Ekstrem (Spike)"
    # elif JENIS="WASTE" & KETERANGAN in NonHandlingList -> "Dominasi Non-Handling"
    # else "Normal"
    # ============================================================
    jenis = out["JENIS"].astype(str)
    ket = out["KETERANGAN"].astype(str)
    is_non_handling = ket.isin(non_handling)
    is_waste = jenis == "WASTE"
    is_spike = out["MAX / AVG"] >= th_spike

    category = np.where(
        is_spike, "Lonjakan Ekstrem (Spike)",
        np.where(
            is_waste & is_non_handling, "Dominasi Non-Handling",
            "Normal",
        ),
    )
    out["KATEGORI ANOMALI"] = category

    # ============================================================
    # RANKING WASTE — Top 3 Total & Top 3 % BOM
    # ============================================================
    out["RANGKING WASTE"] = out.apply(_compute_ranking, axis=1)

    # ============================================================
    # OUTPUT RATIO COLUMNS (untuk display)
    # ============================================================
    out["MAX / BOM"] = out["_MaxBOMRatio"]
    out["TOTAL / BOM"] = out["_TotalBOMRatio"]
    out["TOTAL / PEER MEDIAN"] = out["_TotalPeerRatio"]
    out["MAX / PEER MEDIAN MAX"] = out["_MaxPeerRatio"]

    # Drop temp
    out = out.drop(columns=[
        "_s1", "_s2", "_s3", "_s4", "_s5", "_s6", "_s7",
        "_s8", "_s9", "_s10", "_s11", "_s12",
        "_MaxBOMRatio", "_TotalBOMRatio", "_MaxPeerRatio", "_TotalPeerRatio",
    ], errors="ignore")

    return out


# ============================================================
# HELPER: RANKING WASTE
# ============================================================

def _compute_ranking(row: pd.Series) -> str:
    """Setara RankingWaste logic di M code.
    Top 3 dalam group (JENIS, NAMA BARANG) berdasarkan TOTAL & % BOM.
    """
    current_total = row.get("TOTAL")
    current_bom_ratio = row.get("Rill % to BOM")
    top_total_list = row.get("TopTotal")
    top_bom_list = row.get("TopBOM")

    # Position in top list (1-based); 0 kalau tidak ada
    pos_total = 0
    if current_total is not None and not (isinstance(current_total, float) and np.isnan(current_total)) and isinstance(top_total_list, list):
        try:
            idx = top_total_list.index(current_total)
            pos_total = idx + 1
        except ValueError:
            pos_total = 0

    pos_bom = 0
    if current_bom_ratio is not None and not (isinstance(current_bom_ratio, float) and np.isnan(current_bom_ratio)) and current_bom_ratio > 0 and isinstance(top_bom_list, list):
        try:
            idx = top_bom_list.index(current_bom_ratio)
            pos_bom = idx + 1
        except ValueError:
            pos_bom = 0

    is_top_total = 1 <= pos_total <= 3
    is_top_bom = 1 <= pos_bom <= 3

    if is_top_total and is_top_bom:
        if pos_total == pos_bom:
            return f"Top {pos_total} Total & % BOM"
        return f"Top {pos_total} Total & Top {pos_bom} % BOM"
    if is_top_total:
        return f"Top {pos_total} Total"
    if is_top_bom:
        return f"Top {pos_bom} % BOM"
    return "-"
