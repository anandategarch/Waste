"""
signals.py — 12 sinyal anomali + composite score + status + reasons + category + ranking.

Setara dengan section 11 (AddAnalysis) dari M code.

Setiap sinyal S1..S12 adalah boolean (0/1/2). Skor dijumlahkan → CompositeScore (max 19).
Status (cutoff dapat diatur di config.json → thresholds; default di bawah):
  Score >= STATUS_PRIORITAS (8) -> "Prioritas Tinggi"
  Score >= STATUS_POTENSI   (5) -> "Potensi Anomali"
  Score >= STATUS_REVIEW    (3) -> "Perlu Review"
  else                          -> "Normal"
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Fragmen teks ANOMALY REASONS per sinyal (S1..S12). Sumber TUNGGAL —
# UI (ui/view_anomali.py, panel detail) memakai konstanta ini untuk
# menentukan chip sinyal mana yang terpicu dari teks ANOMALY REASONS
# (kolom _s1.._s12 sengaja di-drop sebelum df keluar dari pipeline;
# v2.7.0: chip tidak lagi baca _s* yang memang tidak pernah sampai UI).
# v2.9.0 (permintaan user "permudah istilah"): fragmen jadi Bahasa
# Indonesia awam — TANPA jargon (AVG/median/spike/outlier). Urutan &
# arti tidak berubah; penjelasan lengkap tiap sinyal ada di tooltip
# chip (_CHIP_TIPS, ui/view_anomali.py) + tabel README.
SIGNAL_PARTS: list[tuple[str, str]] = [
    ("_s1", "Lonjakan vs rata-rata harian"),
    ("_s2", "Lonjakan vs hari aktif"),
    ("_s3", "Lonjakan vs nilai tengah"),
    ("_s4", "Terpusat di satu hari"),
    ("_s5", "Jauh di atas hari kedua"),
    ("_s6", "Puncak harian vs BOM"),
    ("_s7", "Total bulanan vs BOM"),
    ("_s8", "Puncak vs cabang lain"),
    ("_s9", "Total vs cabang lain"),
    ("_s10", "Waste hanya satu hari"),
    ("_s11", "Menumpuk di hari terakhir"),
    ("_s12", "Pola 10× (mungkin salah ketik)"),
]


# ============================================================
# MAIN ENTRY
# ============================================================

def compute_signals(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
    params: dict | None = None,
) -> pd.DataFrame:
    """Tambah 12 sinyal + analisa kolom turunan. Setara AddAnalysis di M code.

    Args:
        df: DataFrame hasil stage 10 (kolom kalkulasi sudah ada).
        key_akhir: Hari terakhir periode (1..31).
        config: config dict — threshold dibaca dari ``config["thresholds"]``.
        params: optional dict override threshold (key sama dengan thresholds
            di config.json) yang di-merge di atas config. Default None.
            Backward-compatible: dipanggil tanpa params perilaku tidak berubah.
    """
    th = dict(config.get("thresholds", {}) or {})
    if params:
        # override eksplisit di atas config (jangan mutasi config caller)
        th.update(params)
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
    # Status cutoffs + sinyal minor (M13): dulu hardcoded — sekarang dari config
    # (config.json "thresholds"), dengan default yang identik dengan baseline.
    th_status_prioritas = th.get("STATUS_PRIORITAS", 8)
    th_status_potensi = th.get("STATUS_POTENSI", 5)
    th_status_review = th.get("STATUS_REVIEW", 3)
    th_s2_score2_min = th.get("S2_SCORE2_MIN", 4)
    th_s10_bom_min = th.get("S10_BOM_MIN", 0.10)

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
    s2_score = np.where(s2_cond & (out["MAX / AVG AKTIF"] >= th_s2_score2_min), 2,
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
    # Count=1 AND (MaxBOMRatio >= S10_BOM_MIN OR MaxPeerRatio >= TH_PEER_WARN)
    # ============================================================
    s10 = np.where(
        (count_val == 1) & (
            (out["_MaxBOMRatio"] >= th_s10_bom_min) |
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
        score >= th_status_prioritas, "Prioritas Tinggi",
        np.where(score >= th_status_potensi, "Potensi Anomali",
        np.where(score >= th_status_review, "Perlu Review", "Normal")),
    )

    # ============================================================
    # REASON TEXT (concat tiap sinyal yang triggered)
    # NOTE (M14): dahulu df.apply(_build_reason, axis=1) row-wise — hotspot
    # pada 26k baris. Diganti loop per-kolom (12 iterasi vektor) yang
    # terbukti identik: part ditambah berurutan S1..S12 hanya bila skor > 0,
    # disambung " | ", kosong bila tidak ada sinyal.
    # ============================================================
    signal_parts = SIGNAL_PARTS

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
    reasons = np.full(len(out), "", dtype=object)
    for _scol, _label in signal_parts:
        triggered = out[_scol].to_numpy() > 0
        if not triggered.any():
            continue
        existing = reasons[triggered]
        reasons[triggered] = np.where(
            existing != "", existing + " | " + _label, _label
        )
    out["ANOMALY REASONS"] = reasons

    # v2.19.8 — W-2 (audit): KRONIS guard. Baris dgn magnitude TINGGI
    # (TOTAL top-decile + >50% di atas peer median) TAPI tanpa day-spike
    # (score < 3 → Normal) dibump ke "Perlu Review" dgn alasan "Kronis
    # Tinggi". Audit temukan: AYAM CINCANG TOT=46.868 (75% di atas peer)
    # berstatus Normal padahal waste terbesar — label menyesatkan. Score
    # TIDAK diubah (kronis = lensa magnitude, bukan sinyal spike) —
    # konsistensi score<3 + status "Perlu Review" = exception disengaja.
    try:
        total_num = pd.to_numeric(out["TOTAL"], errors="coerce").fillna(0)
        active_mask = total_num > 0
        if active_mask.any() and "_TotalPeerRatio" in out.columns:
            q = float(th.get("KRONIS_TOP_DECILE", 0.9))
            r = float(th.get("KRONIS_PEER_RATIO", 1.5))
            q90 = total_num[active_mask].quantile(q)
            tpr = pd.to_numeric(out["_TotalPeerRatio"], errors="coerce").fillna(0)
            kronis_mask = (
                (status == "Normal")
                & active_mask.to_numpy()
                & (total_num.to_numpy() > q90)
                & (tpr.to_numpy() > r)
            )
            if kronis_mask.any():
                status = np.where(kronis_mask, "Perlu Review", status)
                out["ANOMALY STATUS"] = status
                existing = reasons[kronis_mask]
                reasons[kronis_mask] = np.where(
                    existing != "", existing + " | Kronis Tinggi",
                    "Kronis Tinggi")
                out["ANOMALY REASONS"] = reasons
    except Exception:  # noqa: BLE001 — kronis guard tak boleh crash pipeline
        pass

    # ============================================================
    # KATEGORI ANOMALI
    # if MAX/AVG >= TH_SPIKE -> "Lonjakan Ekstrem (Spike)"
    # elif JENIS="WASTE" & KETERANGAN in NonHandlingList -> "Dominasi Non-Handling"
    # else "Normal"
    # ============================================================
    # M17: fillna("") sebelum astype(str) supaya NaN tidak menjadi string "nan"
    # (hasil perbandingan identik — "nan"/"" sama-sama tidak match WASTE/non_handling).
    jenis = out["JENIS"].fillna("").astype(str)
    ket = out["KETERANGAN"].fillna("").astype(str)
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
    # NOTE (M14): sengaja TIDAK divectorize. Logika _compute_ranking bergantung
    # pada list.index() per baris (TopTotal/TopBOM = list per-group), sehingga
    # padanan groupby-transform tidak dapat dijamin identik — correctness
    # diutamakan (RANGKING WASTE diverifikasi pada regression fixture).
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
