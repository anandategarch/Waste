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
    3. Drop semua derived/output columns (idempotent — pipeline bisa di-run di file output).
    4. Coerce hari 1..31 ke numeric.
    5. Filter JENIS in {SUSUT, TRIAL, WASTE}.
    """
    out = df.copy()

    # Drop semua derived/output columns supaya pipeline idempotent.
    # M code asli hanya drop TOTAL, tapi kalau user load file OUTPUT M code,
    # kolom-kolom hasil pipeline sudah ada → collision saat recompute.
    # Solusi: drop semua derived columns (akan dihitung ulang oleh stages berikutnya).
    derived_cols_to_drop = [
        # Stage 1 original drops
        "PIC", "KATEGORI", "STATUS", "PENYEBAB TERJADINYA WASTE", "TOTAL",
        # Stage 2 outputs
        "MAX", "AVG", "MAX TOTAL", "AVG TOTAL", "TOTAL BOM", "% to BOM",
        "Status2", "Count Hari",
        "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX", "HARI MAX",
        "MAX - AVG", "MAX - AVG AKTIF",
        "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
        "MAX SHARE", "NILAI HARI TERAKHIR", "LAST DAY SHARE",
        "SINGLE DAY", "SCALE SIGNAL",
        # Stage 3 outputs
        "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR", "SOURCE DATA GABUNGAN",
        # Stage 5 outputs
        "Rill % to BOM",
        # Stage 6 outputs
        "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
        "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX",
        # Stage 7 outputs
        "TopTotal", "TopBOM",
        # Stage 9/10 outputs
        "HELPER",
        # Stage 11 outputs
        "MAX / BOM", "TOTAL / BOM",
        "ANOMALY SCORE", "ANOMALY STATUS", "ANOMALY REASONS",
        "KATEGORI ANOMALI", "RANGKING WASTE",
        # Stage 9 helper columns (dari DATABASE_SATUAN)
        "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
        "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
        "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
    ]
    cols_to_drop = [c for c in derived_cols_to_drop if c in out.columns]
    if cols_to_drop:
        out = out.drop(columns=cols_to_drop)

    # Sanity: pastikan tidak ada duplicate columns tersisa
    if out.columns.duplicated().any():
        # Drop duplicate columns (keep first)
        out = out.loc[:, ~out.columns.duplicated()]

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
            out[c] = out[c].astype("string")
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
    Setara AddStats. Vektorisasi penuh dengan pandas axis=1 + numpy (v2.2.0).
    Hitung statistik hari 1..KeyAkhir untuk semua baris sekaligus (C-level).
    """
    out = df.copy()
    day_cols = day_columns(key_akhir)
    day_cols = [c for c in day_cols if c in out.columns]

    if not day_cols:
        # Tidak ada kolom hari — semua stats null
        for col in ["TOTAL", "MAX", "AVG", "Count Hari", "Status2",
                    "AVG AKTIF", "MEDIAN AKTIF", "SECOND MAX", "HARI MAX",
                    "MAX - AVG", "MAX - AVG AKTIF",
                    "MAX / AVG", "MAX / AVG AKTIF", "MAX / MEDIAN AKTIF", "MAX / SECOND MAX",
                    "MAX SHARE", "NILAI HARI TERAKHIR", "LAST DAY SHARE",
                    "SINGLE DAY", "SCALE SIGNAL"]:
            out[col] = None
        return out  # Tidak ada filter ValidStats karena TOTAL = null → semua drop nanti

    # Coerce hari ke numeric matrix (NaN untuk null)
    day_matrix = out[day_cols].apply(pd.to_numeric, errors="coerce")
    # Replace NaN ke 0 untuk sum/max (tapi track null mask untuk AvgAktif/MedianAktif)
    filled = day_matrix.fillna(0).to_numpy()
    # Mask nilai non-null & > 0 (untuk aktif_list)
    aktif_mask = (day_matrix.notna()) & (day_matrix > 0)
    aktif_mask_np = aktif_mask.to_numpy()
    # Non-null mask (untuk non_null list = M's List.Sum/List.Max behavior)
    nonnull_mask_np = day_matrix.notna().to_numpy()

    # ===== Statistik dasar (vectorized) =====
    # TOTAL = sum(non_null) — null kalau semua null
    total_arr = np.where(nonnull_mask_np.any(axis=1), filled.sum(axis=1), np.nan)
    # MAX = max(non_null) — null kalau semua null
    max_arr = np.where(nonnull_mask_np.any(axis=1),
                       np.where(nonnull_mask_np, filled, -np.inf).max(axis=1),
                       np.nan)
    # Replace -inf back to 0 (downstream guard, sama seperti M behavior)
    max_arr = np.where(np.isinf(max_arr) | np.isnan(max_arr), 0, max_arr)
    # AVG = mean(non_null) — null kalau semua null
    with np.errstate(invalid="ignore"):
        avg_arr = np.where(nonnull_mask_np.any(axis=1),
                           day_matrix.mean(axis=1, skipna=True),
                           np.nan)
    # CountHari = count(aktif > 0)
    count_hari_arr = aktif_mask_np.sum(axis=1)
    # AVG AKTIF = mean(aktif > 0) — null kalau tidak ada aktif
    with np.errstate(invalid="ignore", all="ignore"):
        avg_aktif_arr = np.where(count_hari_arr > 0,
                                  np.nanmean(np.where(aktif_mask_np, filled, np.nan), axis=1),
                                  np.nan)
    # MEDIAN AKTIF = median(aktif > 0) — null kalau tidak ada aktif
    def _nanmedian_rowwise(arr, mask):
        """Median per-row dari nilai where mask=True, NaN otherwise."""
        result = np.empty(arr.shape[0])
        for i in range(arr.shape[0]):
            vals = arr[i][mask[i]]
            result[i] = np.median(vals) if len(vals) > 0 else np.nan
        return result
    median_aktif_arr = _nanmedian_rowwise(filled, aktif_mask_np)

    # SECOND MAX: dari aktif_list, nilai terbesar ke-2
    # Pakai np.partition (O(n) per row, lebih cepat dari sort)
    def _second_max_rowwise(arr, mask):
        result = np.empty(arr.shape[0])
        for i in range(arr.shape[0]):
            vals = np.sort(arr[i][mask[i]])[::-1]  # desc sort
            result[i] = vals[1] if len(vals) >= 2 else np.nan
        return result
    second_max_arr = _second_max_rowwise(filled, aktif_mask_np)

    # HARI MAX: posisi (1-based) dari MAX di hari_list (kalau MAX > 0)
    # Cari idx dari nilai max di setiap row (hanya kalau max > 0)
    hari_max_arr = np.empty(len(out), dtype=object)
    for i in range(len(out)):
        if not np.isnan(max_arr[i]) and max_arr[i] > 0:
            # Cari posisi pertama yang sama dengan max
            row_vals = day_matrix.iloc[i].to_numpy()
            mask_match = (row_vals == max_arr[i]) & nonnull_mask_np[i]
            if mask_match.any():
                hari_max_arr[i] = int(np.argmax(mask_match)) + 1  # 1-based
            else:
                hari_max_arr[i] = None
        else:
            hari_max_arr[i] = None

    # LastDayValue: nilai hari ke-KeyAkhir
    key_akhir_text = str(clamp(int(key_akhir), 1, 31))
    if key_akhir_text in day_cols:
        last_day_value_arr = day_matrix[key_akhir_text].to_numpy()
    else:
        last_day_value_arr = np.full(len(out), np.nan)

    # Status2
    status2_arr = np.where(np.isnan(total_arr) | (total_arr == 0), "Kosong", "Isi")

    # Gap (max - avg)
    max_minus_avg_arr = np.where(
        ~np.isnan(max_arr) & ~np.isnan(avg_arr),
        max_arr - avg_arr, np.nan)
    max_minus_avg_aktif_arr = np.where(
        ~np.isnan(max_arr) & ~np.isnan(avg_aktif_arr),
        max_arr - avg_aktif_arr, np.nan)

    # Ratios (guarded dengan > 0)
    def _safe_ratio(num, den):
        result = np.zeros_like(num, dtype=float)
        valid = ~np.isnan(num) & ~np.isnan(den) & (den > 0)
        result[valid] = num[valid] / den[valid]
        return result
    max_avg_ratio_arr = _safe_ratio(max_arr, avg_arr)
    max_avg_aktif_ratio_arr = _safe_ratio(max_arr, avg_aktif_arr)
    max_median_ratio_arr = _safe_ratio(max_arr, median_aktif_arr)
    max_second_ratio_arr = _safe_ratio(max_arr, second_max_arr)
    max_share_arr = _safe_ratio(max_arr, total_arr)
    # LastDayShare: butuh last_day_value > 0 juga
    lds_valid = (~np.isnan(last_day_value_arr)) & (last_day_value_arr > 0)
    last_day_share_arr = np.where(
        ~np.isnan(total_arr) & (total_arr > 0) & lds_valid,
        last_day_value_arr / np.where(total_arr > 0, total_arr, 1),
        0.0)
    last_day_share_arr = np.where(np.isnan(total_arr) | (total_arr <= 0), 0.0, last_day_share_arr)

    # SingleDay
    single_day_arr = np.where(count_hari_arr == 1, "YES", "NO")

    # Scale signal (heuristic — deteksi kelipatan 10x dari median)
    scale_ratio_arr = _safe_ratio(max_arr, median_aktif_arr)
    def _scale_signal(sr):
        if sr >= 8:
            for lo, hi in [(8, 12), (80, 120), (800, 1200), (8000, 12000)]:
                if lo <= sr <= hi:
                    return "YES"
        return "NO"
    scale_signal_arr = np.array([_scale_signal(s) for s in scale_ratio_arr], dtype=object)

    # Assign semua kolom ke DataFrame
    out["TOTAL"] = total_arr
    out["MAX"] = max_arr
    out["AVG"] = avg_arr
    out["Count Hari"] = count_hari_arr
    out["Status2"] = status2_arr
    out["AVG AKTIF"] = avg_aktif_arr
    out["MEDIAN AKTIF"] = median_aktif_arr
    out["SECOND MAX"] = second_max_arr
    out["HARI MAX"] = hari_max_arr
    out["MAX - AVG"] = max_minus_avg_arr
    out["MAX - AVG AKTIF"] = max_minus_avg_aktif_arr
    out["MAX / AVG"] = max_avg_ratio_arr
    out["MAX / AVG AKTIF"] = max_avg_aktif_ratio_arr
    out["MAX / MEDIAN AKTIF"] = max_median_ratio_arr
    out["MAX / SECOND MAX"] = max_second_ratio_arr
    out["MAX SHARE"] = max_share_arr
    out["NILAI HARI TERAKHIR"] = last_day_value_arr
    out["LAST DAY SHARE"] = last_day_share_arr
    out["SINGLE DAY"] = single_day_arr
    out["SCALE SIGNAL"] = scale_signal_arr

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
    Setara ReasonTotals + ReasonSummary. Vektorisasi dengan groupby.agg() + pre-computed helper cols.
    Performance: 5-15x lebih cepat dari manual loop (v2.2.0).
    """
    # ReasonTotals: sum TOTAL by full group — keep null semantics
    group_keys_full = ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SOURCE DATA"]
    if not all(k in df.columns for k in group_keys_full):
        return df

    rt = (
        df[group_keys_full + ["TOTAL"]]
        .groupby(group_keys_full, dropna=False, as_index=False)
        .agg(TOTAL_REASON=("TOTAL", "sum"))
    )

    # ReasonSummary: roll-up to (NAMA RESTO, NAMA BARANG, JENIS)
    group_keys_short = ["NAMA RESTO", "NAMA BARANG", "JENIS"]

    # Pre-compute helper columns SEKALI sebelum groupby (cepat)
    # Filter WASTE-only rows (TOTAL_REASON > 0)
    is_waste = rt["JENIS"] == "WASTE"
    rt["_waste_valid"] = is_waste & rt["TOTAL_REASON"].notna() & (rt["TOTAL_REASON"] > 0)
    # Mask non-empty KETERANGAN
    ket_nonempty = rt["KETERANGAN"].notna() & (rt["KETERANGAN"].astype(str).str.strip() != "")
    src_nonempty = rt["SOURCE DATA"].notna() & (rt["SOURCE DATA"].astype(str).str.strip() != "")
    # Untuk WASTE: gabungan hanya dari baris _waste_valid
    # Untuk non-WASTE: gabungan dari semua baris non-empty
    rt["_ket_for_gabungan"] = np.where(
        is_waste,
        np.where(rt["_waste_valid"] & ket_nonempty, rt["KETERANGAN"], None),
        np.where(ket_nonempty, rt["KETERANGAN"], None)
    )
    rt["_src_for_gabungan"] = np.where(
        is_waste,
        np.where(rt["_waste_valid"] & src_nonempty, rt["SOURCE DATA"], None),
        np.where(src_nonempty, rt["SOURCE DATA"], None)
    )

    # Groupby dengan agg — pakai lambda sederhana untuk join distinct values
    def _join_distinct(series):
        """Join distinct non-null values dengan ', '."""
        vals = [v for v in series if v is not None and (not isinstance(v, float) or not np.isnan(v))]
        if not vals:
            return ""
        return ", ".join(list(dict.fromkeys(vals)))  # distinct preserve order

    def _kontribusi_terbesar(group_df):
        """Top keterangan + % untuk WASTE only."""
        jenis_val = group_df["JENIS"].iloc[0] if not group_df.empty else None
        if jenis_val != "WASTE":
            return None
        # Filter: TOTAL_REASON > 0 + KETERANGAN non-empty
        f = group_df[
            group_df["TOTAL_REASON"].notna() & (group_df["TOTAL_REASON"] > 0)
            & ket_nonempty[group_df.index]
        ]
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

    # Vektorisasi: pakai agg dengan lambda sederhana (group dipanggil jauh lebih sedikit)
    rs = (
        rt.groupby(group_keys_short, dropna=False, as_index=False)
        .agg(
            KETERANGAN_GABUNGAN=("_ket_for_gabungan", _join_distinct),
            SOURCE_DATA_GABUNGAN=("_src_for_gabungan", _join_distinct),
            KONTRIBUSI_TERBESAR=("KETERANGAN", lambda x: None),  # placeholder, dihitung terpisah
        )
    )
    # Drop kolom placeholder kosong
    if "KONTRIBUSI TERBESAR" in rs.columns:
        rs = rs.drop(columns=["KONTRIBUSI TERBESAR"])

    # Hitung KONTRIBUSI TERBESAR terpisah (hanya untuk WASTE groups)
    waste_groups = rt[is_waste].groupby(group_keys_short, dropna=False)
    kontribusi_map = {}
    for key, t in waste_groups:
        f = t[t["TOTAL_REASON"].notna() & (t["TOTAL_REASON"] > 0)
              & t["KETERANGAN"].notna() & (t["KETERANGAN"].astype(str).str.strip() != "")]
        if f.empty:
            continue
        grand_total = f["TOTAL_REASON"].sum()
        if grand_total == 0:
            continue
        f_sorted = f.sort_values("TOTAL_REASON", ascending=False)
        top_ket = f_sorted["KETERANGAN"].iloc[0]
        top_total = f_sorted["TOTAL_REASON"].iloc[0]
        pct_val = round(float(top_total / grand_total) * 100, 0)
        kontribusi_map[key] = f"{top_ket} {int(pct_val)}%"

    # Assign ke kolom baru berdasarkan group key
    def _lookup_kontribusi(row):
        key = (row["NAMA RESTO"], row["NAMA BARANG"], row["JENIS"])
        return kontribusi_map.get(key)
    rs["KONTRIBUSI TERBESAR"] = rs.apply(_lookup_kontribusi, axis=1) if len(rs) > 0 else None

    # Cleanup helper cols
    rt = rt.drop(columns=["_waste_valid", "_ket_for_gabungan", "_src_for_gabungan"], errors="ignore")

    # Merge back to df (left join) — defensive: drop kolom yang akan di-merge dulu
    cols_to_merge = ["KETERANGAN GABUNGAN", "SOURCE DATA GABUNGAN", "KONTRIBUSI TERBESAR"]
    df_clean = df.copy()
    for c in cols_to_merge:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    out = df_clean.merge(rs, on=group_keys_short, how="left")
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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
    # Defensive: drop MAX TOTAL/AVG TOTAL dari df kalau sudah ada (idempotent case)
    df_clean = df.copy()
    for c in ["MAX TOTAL", "AVG TOTAL"]:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    out = df_clean.merge(gt, on=group_keys, how="left")
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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

    # Siapkan BOM untuk join (strip whitespace untuk match robust)
    bom = bom_df.copy()
    bom["Nomor #"] = bom["Nomor #"].astype(str).str.strip()
    bom["Nama Barang"] = bom["Nama Barang"].astype(str).str.strip()

    df_join = df.copy()
    # Defensive: drop TOTAL BOM dari df kalau sudah ada (idempotent), supaya merge tidak buat _x/_y
    if "TOTAL BOM" in df_join.columns:
        df_join = df_join.drop(columns=["TOTAL BOM"])
    df_join["NAMA RESTO"] = df_join["NAMA RESTO"].astype(str).str.strip()
    df_join["NAMA BARANG"] = df_join["NAMA BARANG"].astype(str).str.strip()

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
    # Defensive: pastikan tidak ada duplicate columns pasca-merge
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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

    # Defensive: drop peer columns dari df kalau sudah ada (idempotent case)
    df_clean = df.copy()
    for c in ["PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX"]:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    out = df_clean.merge(peer_stats, on=keys_short, how="left")
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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

    # Defensive: drop TopTotal/TopBOM dari df kalau sudah ada (idempotent case)
    df_clean = df.copy()
    for c in ["TopTotal", "TopBOM"]:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    out = df_clean.merge(top_df, on=keys, how="left")
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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
    # Defensive: drop helper cols dari df kalau sudah ada (idempotent case)
    for c in expected_helper_cols:
        if c in df_join.columns:
            df_join = df_join.drop(columns=[c])
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
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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
        # Defensive helper: kalau ada duplicate columns, row.get() return Series.
        # Paksa ambil scalar value (iloc[0]) supaya float() tidak error.
        def _scalar(v):
            if isinstance(v, pd.Series):
                return v.iloc[0] if len(v) > 0 else None
            return v

        # 1) % to BOM — INDEPENDEN dari KETERANGAN (sesuai M code)
        total_value = _scalar(row.get("TOTAL"))
        bom_value = _scalar(row.get("TOTAL BOM"))
        if (total_value is None or bom_value is None
                or (isinstance(bom_value, float) and np.isnan(bom_value))):
            pct_bom = "Cek"
        else:
            try:
                if float(bom_value) == 0:
                    pct_bom = None  # try ... otherwise null di M code
                else:
                    pct_bom = float(total_value) / float(bom_value)
            except (ValueError, TypeError):
                pct_bom = None

        # 2) HELPER & STATUS — bergantung KETERANGAN
        ket = _scalar(row.get("KETERANGAN"))
        if ket is None or (isinstance(ket, float) and np.isnan(ket)) or str(ket).strip() == "":
            return None, None, pct_bom
        col = cat_map.get(str(ket).strip())
        if col is None or col not in df.columns:
            return None, None, pct_bom
        helper_value = _scalar(row.get(col))
        # Coerce ke numerik (None stays None)
        try:
            if helper_value is None or (isinstance(helper_value, float) and np.isnan(helper_value)):
                helper_value_num = None
            else:
                helper_value_num = float(helper_value)
        except (ValueError, TypeError):
            helper_value_num = None
        # STATUS logic dari M code
        max_value = _scalar(row.get("MAX"))
        max_value_num = float(max_value) if max_value is not None and not (isinstance(max_value, float) and np.isnan(max_value)) else 0
        if helper_value_num is None:
            status_value = None
        else:
            if (helper_value_num == 1 and max_value_num >= 0) or (helper_value_num == 0 and max_value_num == 0):
                status_value = "Sesuai"
            else:
                status_value = "Tidak Sesuai"
        return helper_value_num, status_value, pct_bom

    # Defensive: drop HELPER/STATUS/% to BOM dari df kalau sudah ada (idempotent case)
    df_clean = df.copy()
    for c in ["HELPER", "STATUS", "% to BOM"]:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    helper_records = df_clean.apply(_resolve_helper, axis=1, result_type="expand")
    helper_records.columns = ["HELPER", "STATUS", "% to BOM"]
    out = pd.concat([df_clean.reset_index(drop=True), helper_records.reset_index(drop=True)], axis=1)
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
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
