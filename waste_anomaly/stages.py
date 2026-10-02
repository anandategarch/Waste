"""
stages.py — replika 14 stage dari Power Query M code.

Setiap fungsi menerima DataFrame + config, return DataFrame hasil stage.
Dipanggil berurutan oleh pipeline.run_pipeline().

Mapping stage ke M code:
  stage_01_source  -> Source / SourceNoTotal / SourceTyped / SourceSlim / Filtered
  stage_02_stats    -> AddStats / Stats / ValidStats
  stage_03_reason   -> ReasonTotals / ReasonSummary
  stage_04_group   -> GroupTotals
  stage_05_bom      -> BOMLookup / WithBOMJoin / WithBOM / AddRillBOM
  stage_06_peer     -> PeerOutlet / PeerStats
  stage_07_top      -> TopSummary
  stage_08_merge    -> MergeReason / MergeGroup / MergePeer / MergeTop
  stage_09_satuan   -> SatuanLookup / MergeSatuan / ExpandSatuan
  stage_10_helper   -> AddHelper / ExpandHelper
  stage_11_analysis -> AddAnalysis (12 sinyal + score + status + reasons + category + ranking)
  stage_12_expand   -> ExpandAnalysis
  stage_13_cleanup  -> RemoveTemporary
  stage_14_final    -> Final (reorder columns)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import (
    clamp, day_columns, safe_count, safe_count_active, safe_div,
    safe_max, safe_mean, safe_median, second_max, position_of, to_text,
)


# ============================================================
# STAGE 1 — SOURCE & CLEANUP
# ============================================================

def stage_01_source(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara Source -> SourceNoTotal -> SourceTyped -> SourceSlim -> Filtered.

    1. Drop TOTAL (akan dihitung ulang).
    2. Drop kolom tidak dipakai: PIC, KATEGORI, STATUS, PENYEBAB TERJADINYA WASTE.
    3. Coerce hari 1..31 ke numeric.
    4. Filter JENIS in {SUSUT, TRIAL, WASTE}.
    """
    out = df.copy()

    # Drop TOTAL (akan dihitung ulang)
    if "TOTAL" in out.columns:
        out = out.drop(columns=["TOTAL"])

    # Drop kolom tidak dipakai
    drop_cols = ["PIC", "KATEGORI", "STATUS", "PENYEBAB TERJADINYA WASTE"]
    out = out.drop(columns=[c for c in drop_cols if c in out.columns])

    # Coerce hari 1..31 ke numeric
    all_day_cols = [str(i) for i in range(1, 32) if str(i) in out.columns]
    for c in all_day_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # Coerce kolom teks ke string kanonik
    text_cols = [
        "SOURCE DATA", "JENIS", "NAMA BARANG", "KETERANGAN",
        "SATUAN", "NAMA RESTO",
    ]
    for c in text_cols:
        if c in out.columns:
            out[c] = out[c].astype(str).replace("nan", None).replace("None", None)
            out[c] = out[c].where(out[c].notna() & (out[c] != ""), None)

    # Filter JENIS
    if "JENIS" in out.columns:
        keep = ["SUSUT", "TRIAL", "WASTE"]
        out = out[out["JENIS"].isin(keep)].copy()

    # Reset index setelah filter
    out = out.reset_index(drop=True)
    return out


# ============================================================
# STAGE 2 — PER-ROW DAILY STATISTICS
# ============================================================

def stage_02_stats(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara AddStats. Untuk tiap baris, hitung statistik hari 1..KeyAkhir:
    TOTAL, MAX, AVG, AVG AKTIF, MEDIAN AKTIF, SECOND MAX, HARI MAX,
    rasio, share, single-day, scale-signal.
    """
    out = df.copy()
    day_cols = day_columns(key_akhir)
    # Hanya kolom hari yang ada di df
    day_cols = [c for c in day_cols if c in out.columns]

    # List of lists — untuk statistik per baris
    hari_lists = out[day_cols].values.tolist() if day_cols else [[] for _ in range(len(out))]

    records = []
    for row_vals in hari_lists:
        # HariList: nilai asli (None untuk NaN)
        hari_list = [None if (isinstance(v, float) and np.isnan(v)) else v for v in row_vals]
        # AktifList: non-null & > 0
        aktif_list = [v for v in hari_list if v is not None and v > 0]
        # Sorted desc untuk SecondMax
        sorted_aktif = sorted(aktif_list, reverse=True)

        total = sum(aktif_list)  # List.Sum(HariList) skip null
        max_value = sorted_aktif[0] if sorted_aktif else 0
        # AvgValue = List.Average(HariList) — di M List.Average skip null
        non_null = [v for v in hari_list if v is not None]
        avg_value = float(np.mean(non_null)) if non_null else 0
        count_hari = len(aktif_list)
        avg_aktif = float(np.mean(aktif_list)) if aktif_list else None
        median_aktif = float(np.median(aktif_list)) if aktif_list else None
        second_max_val = sorted_aktif[1] if len(sorted_aktif) >= 2 else None
        hari_max = None
        if max_value and max_value > 0:
            for i, v in enumerate(hari_list):
                if v is not None and v == max_value:
                    hari_max = i + 1  # 1-based
                    break
        else:
            max_value = 0  # konsisten dengan M code (try otherwise 0)

        # LastDayValue: nilai hari ke-KeyAkhir
        key_akhir_text = str(clamp(int(key_akhir), 1, 31))
        last_day_value = None
        # Ambil dari row asli (hari list) berdasarkan posisi
        if day_cols:
            idx = day_cols.index(key_akhir_text) if key_akhir_text in day_cols else None
            if idx is not None:
                v = hari_list[idx] if idx < len(hari_list) else None
                last_day_value = v if (v is not None and v > 0) else None

        status2 = "Kosong" if total == 0 else "Isi"

        # Gap
        max_minus_avg = (max_value - avg_value) if (max_value and avg_value is not None) else None
        max_minus_avg_aktif = (
            (max_value - avg_aktif) if (max_value is not None and avg_aktif is not None) else None
        )

        # Ratios
        max_avg_ratio = safe_div(max_value, avg_value) if avg_value else 0
        max_avg_aktif_ratio = safe_div(max_value, avg_aktif)
        max_median_ratio = safe_div(max_value, median_aktif)
        max_second_ratio = safe_div(max_value, second_max_val)

        # Shares
        max_share = safe_div(max_value, total) if total else 0
        last_day_share = safe_div(last_day_value, total) if (total and last_day_value) else 0

        # Single day
        single_day = "YES" if count_hari == 1 else "NO"

        # Scale signal (heuristic dari M code — deteksi kelipatan 10× dari median)
        scale_ratio = safe_div(max_value, median_aktif) if median_aktif else 0
        scale_signal = "NO"
        if scale_ratio >= 8:
            in_band = any(
                lo <= scale_ratio <= hi
                for lo, hi in [(8, 12), (80, 120), (800, 1200), (8000, 12000)]
            )
            if in_band:
                scale_signal = "YES"

        records.append({
            "TOTAL": total,
            "MAX": max_value,
            "AVG": avg_value,
            "Count Hari": count_hari,
            "Status2": status2,
            "AVG AKTIF": avg_aktif,
            "MEDIAN AKTIF": median_aktif,
            "SECOND MAX": second_max_val,
            "HARI MAX": hari_max,
            "MAX - AVG": max_minus_avg,
            "MAX - AVG AKTIF": max_minus_avg_aktif,
            "MAX / AVG": max_avg_ratio,
            "MAX / AVG AKTIF": max_avg_aktif_ratio,
            "MAX / MEDIAN AKTIF": max_median_ratio,
            "MAX / SECOND MAX": max_second_ratio,
            "MAX SHARE": max_share,
            "NILAI HARI TERAKHIR": last_day_value,
            "LAST DAY SHARE": last_day_share,
            "SINGLE DAY": single_day,
            "SCALE SIGNAL": scale_signal,
        })

    stats_df = pd.DataFrame(records)
    out = pd.concat([out.reset_index(drop=True), stats_df], axis=1)

    # ValidStats: hanya baris dengan TOTAL <> null
    out = out[out["TOTAL"].notna()].reset_index(drop=True)
    return out


# ============================================================
# STAGE 3 — REASON SUMMARY
# ============================================================

def stage_03_reason(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara ReasonTotals + ReasonSummary. Group by (NAMA RESTO, NAMA BARANG, JENIS, KETERANGAN, SOURCE DATA)
    lalu roll-up ke (NAMA RESTO, NAMA BARANG, JENIS) untuk:
      - KETERANGAN GABUNGAN (concat distinct)
      - SOURCE DATA GABUNGAN (concat distinct)
      - KONTRIBUSI TERBESAR (top keterangan + %)
    """
    # ReasonTotals: sum TOTAL by full group
    group_keys_full = ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SOURCE DATA"]
    if not all(k in df.columns for k in group_keys_full):
        # Kolom kurang, return df apa adanya
        return df

    rt = (
        df[group_keys_full + ["TOTAL"]]
        .assign(TOTAL=lambda x: x["TOTAL"].fillna(0))
        .groupby(group_keys_full, dropna=False, as_index=False)
        .agg(TOTAL_REASON=("TOTAL", "sum"))
    )

    # ReasonSummary: roll-up to (NAMA RESTO, NAMA BARANG, JENIS)
    group_keys_short = ["NAMA RESTO", "NAMA BARANG", "JENIS"]

    def _keterangan_gabungan(jenis_val: str, t: pd.DataFrame) -> str:
        f = t.copy()
        if jenis_val == "WASTE":
            f = f[(f["TOTAL_REASON"].notna()) & (f["TOTAL_REASON"] > 0)]
        x = [k for k in f["KETERANGAN"].tolist() if k is not None and str(k).strip() != ""]
        x = list(dict.fromkeys(x))  # distinct preserve order
        return ", ".join(x)

    def _source_data_gabungan(jenis_val: str, t: pd.DataFrame) -> str:
        f = t.copy()
        if jenis_val == "WASTE":
            f = f[(f["TOTAL_REASON"].notna()) & (f["TOTAL_REASON"] > 0)]
        x = [k for k in f["SOURCE DATA"].tolist() if k is not None and str(k).strip() != ""]
        x = list(dict.fromkeys(x))
        return ", ".join(x)

    def _kontribusi_terbesar(jenis_val: str, t: pd.DataFrame) -> str | None:
        if jenis_val == "WASTE":
            f = t[
                (t["TOTAL_REASON"].notna()) & (t["TOTAL_REASON"] > 0)
                & (t["KETERANGAN"].notna()) & (t["KETERANGAN"].astype(str).str.strip() != "")
            ].copy()
        else:
            f = pd.DataFrame(columns=t.columns)
        if f.empty:
            return None
        grand_total = f["TOTAL_REASON"].sum()
        if grand_total == 0:
            return None
        f_sorted = f.sort_values("TOTAL_REASON", ascending=False)
        top_ket = f_sorted["KETERANGAN"].iloc[0]
        top_total = f_sorted["TOTAL_REASON"].iloc[0]
        pct_val = round(float(top_total / grand_total) * 100, 0)
        return f"{top_ket} {int(pct_val)}%"

    # Iterasi manual per group (lebih aman & terkontrol dibanding apply dengan include_groups)
    rs_rows = []
    for key, t in rt.groupby(group_keys_short, dropna=False):
        nama_resto, nama_barang, jenis = key if isinstance(key, tuple) else (key, None, None)
        rs_rows.append({
            "NAMA RESTO": nama_resto,
            "NAMA BARANG": nama_barang,
            "JENIS": jenis,
            "KETERANGAN GABUNGAN": _keterangan_gabungan(jenis, t),
            "SOURCE DATA GABUNGAN": _source_data_gabungan(jenis, t),
            "KONTRIBUSI TERBESAR": _kontribusi_terbesar(jenis, t),
        })
    rs = pd.DataFrame(rs_rows)

    # Merge back to df (left join)
    out = df.merge(rs, on=group_keys_short, how="left")
    return out


# ============================================================
# STAGE 4 — GROUP TOTALS
# ============================================================

def stage_04_group(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara GroupTotals. Group by (KETERANGAN, NAMA BARANG, SOURCE DATA).
      - MAX TOTAL = max of TOTAL
      - AVG TOTAL = max of AVG (catatan: M code pakai List.Max([AVG]), sesuai komentar "LOGIKA LAMA")
    """
    group_keys = ["KETERANGAN", "NAMA BARANG", "SOURCE DATA"]
    if not all(k in df.columns for k in group_keys):
        return df
    if "TOTAL" not in df.columns or "AVG" not in df.columns:
        return df

    gt = (
        df[group_keys + ["TOTAL", "AVG"]]
        .groupby(group_keys, dropna=False, as_index=False)
        .agg({"TOTAL": "max", "AVG": "max"})
        .rename(columns={"TOTAL": "MAX TOTAL", "AVG": "AVG TOTAL"})
    )
    out = df.merge(gt, on=group_keys, how="left")
    return out


# ============================================================
# STAGE 5 — BOM JOIN
# ============================================================

def stage_05_bom(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
    bom_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Setara BOMLookup + WithBOMJoin + WithBOM + AddRillBOM.
    Left-join df dengan BOM pada (NAMA RESTO == Nomor #) AND (NAMA BARANG == Nama Barang).
    Hasil: TOTAL BOM + Rill % to BOM = TOTAL / TOTAL BOM.
    """
    if bom_df is None or bom_df.empty:
        df["TOTAL BOM"] = np.nan
        df["Rill % to BOM"] = 0.0
        return df

    # Siapkan BOM untuk join
    bom = bom_df.copy()
    bom["Nomor #"] = bom["Nomor #"].astype(str)
    bom["Nama Barang"] = bom["Nama Barang"].astype(str)

    df_join = df.copy()
    df_join["NAMA RESTO"] = df_join["NAMA RESTO"].astype(str)
    df_join["NAMA BARANG"] = df_join["NAMA BARANG"].astype(str)

    out = df_join.merge(
        bom[["Nomor #", "Nama Barang", "TOTAL BOM"]],
        left_on=["NAMA RESTO", "NAMA BARANG"],
        right_on=["Nomor #", "Nama Barang"],
        how="left",
    )
    # Drop kolom join dari BOM (Nomor #, Nama Barang sudah ada NAMA RESTO, NAMA BARANG)
    out = out.drop(columns=["Nomor #", "Nama Barang"], errors="ignore")

    # Rill % to BOM = TOTAL / TOTAL BOM (guarded)
    out["TOTAL BOM"] = pd.to_numeric(out["TOTAL BOM"], errors="coerce")
    out["Rill % to BOM"] = np.where(
        (out["TOTAL"].notna()) & (out["TOTAL BOM"].notna()) & (out["TOTAL BOM"] > 0),
        out["TOTAL"] / out["TOTAL BOM"],
        0.0,
    )
    return out


# ============================================================
# STAGE 6 — PEER SUMMARY
# ============================================================

def stage_06_peer(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara PeerOutlet + PeerStats.

    PeerOutlet: group by (NAMA RESTO, NAMA BARANG, JENIS, KETERANGAN, SOURCE DATA) -> sum TOTAL, max MAX.
    PeerStats: roll-up to (NAMA BARANG, JENIS, KETERANGAN, SOURCE DATA) -> PEER COUNT, PEER MEDIAN TOTAL, PEER MEDIAN MAX.
    """
    keys_full = ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SOURCE DATA"]
    keys_short = ["NAMA BARANG", "JENIS", "KETERANGAN", "SOURCE DATA"]

    if not all(k in df.columns for k in keys_full):
        df["PEER COUNT"] = np.nan
        df["PEER MEDIAN TOTAL"] = np.nan
        df["PEER MEDIAN MAX"] = np.nan
        return df

    peer_outlet = (
        df[keys_full + ["TOTAL", "MAX"]]
        .assign(TOTAL=lambda x: x["TOTAL"].fillna(0))
        .assign(MAX=lambda x: x["MAX"].fillna(0))
        .groupby(keys_full, dropna=False, as_index=False)
        .agg(PEER_TOTAL_OUTLET=("TOTAL", "sum"), PEER_MAX_OUTLET=("MAX", "max"))
    )

    peer_stats = (
        peer_outlet.groupby(keys_short, dropna=False, as_index=False)
        .agg(
            **{
                "PEER COUNT": ("PEER_TOTAL_OUTLET", "count"),
                "PEER MEDIAN TOTAL": ("PEER_TOTAL_OUTLET", "median"),
                "PEER MEDIAN MAX": ("PEER_MAX_OUTLET", "median"),
            }
        )
    )

    out = df.merge(peer_stats, on=keys_short, how="left")
    return out


# ============================================================
# STAGE 7 — TOP 3 SUMMARY
# ============================================================

def stage_07_top(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara TopSummary. Group by (JENIS, NAMA BARANG):
      - TopTotal: list 3 nilai TOTAL tertinggi
      - TopBOM: list 3 nilai Rill % to BOM tertinggi (>0)
    Disimpan sebagai list Python; di-expand di stage_08 (kolom TopTotal, TopBOM).
    """
    keys = ["JENIS", "NAMA BARANG"]
    if not all(k in df.columns for k in keys):
        df["TopTotal"] = None
        df["TopBOM"] = None
        return df

    def _top_total(t: pd.DataFrame) -> list:
        vals = [v for v in t["TOTAL"].dropna().tolist() if v is not None]
        vals_sorted = sorted(vals, reverse=True)
        return vals_sorted[:3]

    def _top_bom(t: pd.DataFrame) -> list:
        if "Rill % to BOM" not in t.columns:
            return []
        vals = [v for v in t["Rill % to BOM"].dropna().tolist() if v is not None and v > 0]
        vals_sorted = sorted(vals, reverse=True)
        return vals_sorted[:3]

    top_df = (
        df.groupby(keys, dropna=False)
        .apply(lambda t: pd.Series({"TopTotal": _top_total(t), "TopBOM": _top_bom(t)}), include_groups=False)
        .reset_index()
    )

    out = df.merge(top_df, on=keys, how="left")
    return out


# ============================================================
# STAGE 8 — MERGE SUMMARIES (NO-OP, sudah di-merge inline di stage 3-7)
# ============================================================

def stage_08_merge(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Semua merge sudah dilakukan inline di stage 3-7. Return as-is."""
    return df


# ============================================================
# STAGE 9 — DATABASE_SATUAN JOIN
# ============================================================

def stage_09_satuan(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
    satuan_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Setara SatuanLookup + MergeSatuan + ExpandSatuan.
    Left-join df dengan DATABASE_SATUAN pada NAMA BARANG == NAMA ITEM.
    Bawa kolom helper per kategori: SUSUT, TRIAL, HANDLING, KUALITAS EKSTERNAL,
    KUALITAS, KUALITAS INTERNAL, EKSTERNAL, INTERNAL, ALAT MESIN, OVERSTOCK, CANCEL NOTA.
    """
    expected_helper_cols = [
        "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
        "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
        "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
    ]
    if satuan_df is None or satuan_df.empty:
        for c in expected_helper_cols:
            df[c] = np.nan
        return df

    sat = satuan_df.copy()
    # Pastikan ada kolom NAMA ITEM
    if "NAMA ITEM" not in sat.columns:
        for c in expected_helper_cols:
            df[c] = np.nan
        return df

    # Strip & uppercase-lowercase untuk matching
    sat["NAMA ITEM"] = sat["NAMA ITEM"].astype(str).str.strip()
    df_join = df.copy()
    df_join["NAMA BARANG"] = df_join["NAMA BARANG"].astype(str).str.strip()

    out = df_join.merge(
        sat,
        left_on="NAMA BARANG",
        right_on="NAMA ITEM",
        how="left",
    )
    # Drop kolom NAMA ITEM duplikat (dari satuan)
    if "NAMA ITEM" in out.columns:
        out = out.drop(columns=["NAMA ITEM"])
    # Pastikan semua helper col ada (kalau satuan tidak punya semua)
    for c in expected_helper_cols:
        if c not in out.columns:
            out[c] = np.nan
    return out


# ============================================================
# STAGE 10 — HELPER / STATUS / % TO BOM
# ============================================================

def stage_10_helper(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """
    Setara AddHelper + ExpandHelper.
    HelperValue: lookup dari kolom kategori yang sesuai (mis. KETERANGAN="SUSUT" -> kolom SUSUT).
    STATUS: "Sesuai" bila (Helper=1 & MAX>=0) atau (Helper=0 & MAX=0); else "Tidak Sesuai".
    % to BOM: TOTAL / TOTAL BOM (guarded).
    """
    cat_map = config.get("satuan_columns", {}).get("category_map", {
        "SUSUT": "SUSUT",
        "TRIAL": "TRIAL",
        "Alat/ Mesin": "ALAT MESIN",
        "Cancel Nota": "CANCEL NOTA",
        "Eksternal": "EKSTERNAL",
        "Internal": "INTERNAL",
        "Handling": "HANDLING",
        "Kualitas Eksternal": "KUALITAS EKSTERNAL",
        "Kualitas Internal": "KUALITAS INTERNAL",
        "Over Stock": "OVERSTOCK",
        "Kualitas": "KUALITAS",
    })

    def _resolve_helper(row: pd.Series):
        ket = row.get("KETERANGAN")
        if ket is None or (isinstance(ket, float) and np.isnan(ket)) or str(ket).strip() == "":
            return None, None, "Cek"
        col = cat_map.get(str(ket).strip())
        if col is None or col not in df.columns:
            return None, None, "Cek"
        helper_value = row.get(col)
        # Coerce ke 0/1 numerik
        try:
            helper_value_num = float(helper_value) if helper_value is not None and not (isinstance(helper_value, float) and np.isnan(helper_value)) else None
        except (ValueError, TypeError):
            helper_value_num = None
        # STATUS logic dari M code
        max_value = row.get("MAX")
        max_value_num = float(max_value) if max_value is not None and not (isinstance(max_value, float) and np.isnan(max_value)) else 0
        if helper_value_num is None:
            status_value = None
        else:
            if (helper_value_num == 1 and max_value_num >= 0) or (helper_value_num == 0 and max_value_num == 0):
                status_value = "Sesuai"
            else:
                status_value = "Tidak Sesuai"
        # % to BOM
        total_value = row.get("TOTAL")
        bom_value = row.get("TOTAL BOM")
        if total_value is None or bom_value is None or (isinstance(bom_value, float) and np.isnan(bom_value)):
            pct_bom = "Cek"
        else:
            try:
                pct_bom = float(total_value) / float(bom_value)
            except (ValueError, TypeError, ZeroDivisionError):
                pct_bom = None
        return helper_value_num, status_value, pct_bom

    helper_records = df.apply(_resolve_helper, axis=1, result_type="expand")
    helper_records.columns = ["HELPER", "STATUS", "% to BOM"]
    out = pd.concat([df.reset_index(drop=True), helper_records.reset_index(drop=True)], axis=1)
    return out


# ============================================================
# STAGE 11 — ANALISA ANOMALI (12 SINYAL) — Dipanggil dari signals.py
# ============================================================

def stage_11_analysis(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Wrapper ke signals.compute_signals(). Lihat signals.py."""
    from .signals import compute_signals
    return compute_signals(df, key_akhir, config)


# ============================================================
# STAGE 12 — EXPAND ANALYSIS (NO-OP — sudah di-expand di signals)
# ============================================================

def stage_12_expand(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    return df


# ============================================================
# STAGE 13 — REMOVE TEMPORARY
# ============================================================

def stage_13_cleanup(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Setara RemoveTemporary. Drop kolom helper sementara."""
    temp_cols = [
        "TopTotal", "TopBOM",
        "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
        "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
        "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
    ]
    return df.drop(columns=[c for c in temp_cols if c in df.columns], errors="ignore")


# ============================================================
# STAGE 14 — FINAL COLUMN ORDER
# ============================================================

FINAL_COLUMN_ORDER = [
    # OUTPUT LAMA
    "STATUS", "HELPER", "MAX TOTAL", "AVG TOTAL", "TOTAL BOM", "% to BOM",
    "TOTAL", "AVG", "MAX",
    "SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG", "NAMA RESTO", "SATUAN",
    # Days 1..31 (di-extend dinamis)
    *([str(i) for i in range(1, 32)]),
    "Status2",
    "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR", "SOURCE DATA GABUNGAN",
    "Count Hari",
    "RANGKING WASTE", "KATEGORI ANOMALI", "Rill % to BOM",
    # ANALISA BARU
    "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX", "HARI MAX",
    "MAX - AVG", "MAX - AVG AKTIF",
    "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
    "MAX SHARE",
    "MAX / BOM", "TOTAL / BOM",
    "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
    "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX",
    "NILAI HARI TERAKHIR", "LAST DAY SHARE",
    "SINGLE DAY", "SCALE SIGNAL",
    "ANOMALY SCORE", "ANOMALY STATUS", "ANOMALY REASONS",
]


def stage_14_final(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Setara Final = Table.ReorderColumns(...). Hanya ambil kolom yang ada di df."""
    desired = []
    for c in FINAL_COLUMN_ORDER:
        if c in df.columns:
            desired.append(c)
    # Tambah kolom non-listed yang masih ada di df (mis. turunan baru), letakkan di akhir
    extra = [c for c in df.columns if c not in desired]
    return df[desired + extra]
