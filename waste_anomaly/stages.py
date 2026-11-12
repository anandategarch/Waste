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

import warnings

import numpy as np
import pandas as pd

# v2.3.1: 9 unused imports dibuang (safe_count, safe_count_active, safe_div,
# safe_max, safe_mean, safe_median, second_max, position_of, to_text) — tidak
# ada call site di file ini (verifikasi grep sebelum removal). `warnings`
# (stdlib) ditambahkan untuk suppress RuntimeWarning np.nanmean (M4).
from .loader import _key_str
from .utils import clamp, day_columns


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
    # PENTING (v2.3.0): TOTAL BOM TIDAK di-drop — user pakai kolom ini sebagai BOM source
    # (sama dengan sheet BOM terpisah). Jadi keep TOTAL BOM dari input data.
    # PENTING (v2.3.1, H4): HELPER & STATUS juga TIDAK di-drop. Re-derivation di
    # Stage 10 butuh DATABASE_SATUAN yang sering tidak ada — tanpa ini, re-run
    # pipeline di file output menghancurkan ±21.355 nilai HELPER/STATUS.
    # Stage 10 hanya menghitung ulang keduanya kalau HELPER absen di input
    # (input rekap mentah), jadi behavior first-run tidak berubah.
    derived_cols_to_drop = [
        # Stage 1 original drops (M code). STATUS TIDAK di-drop — lihat catatan H4 di atas.
        "PIC", "KATEGORI", "PENYEBAB TERJADINYA WASTE", "TOTAL",
        # Stage 2 outputs
        "MAX", "AVG", "MAX TOTAL", "AVG TOTAL", "% to BOM",
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
        # Stage 9/10 outputs — HELPER sengaja TIDAK di-drop (H4, v2.3.1,
        # dipreservasi dari input untuk re-run; lihat catatan blok atas)
        # Stage 11 outputs
        "MAX / BOM", "TOTAL / BOM",
        "ANOMALY SCORE", "ANOMALY STATUS", "ANOMALY REASONS",
        "KATEGORI ANOMALI", "RANGKING WASTE",
        # Stage 9 helper columns (dari DATABASE_SATUAN)
        "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
        "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
        "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
        # NOTE: TOTAL BOM sengaja TIDAK di-drop — dipakai sebagai BOM source inline
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
    # M4 (v2.3.1): np.nanmean pada baris all-NaN memunculkan spam RuntimeWarning
    # "Mean of empty slice" (np.errstate TIDAK menutup warning Python) —
    # suppress lokal dengan warnings.catch_warnings.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with np.errstate(invalid="ignore", all="ignore"):
            avg_aktif_arr = np.where(count_hari_arr > 0,
                                      np.nanmean(np.where(aktif_mask_np, filled, np.nan), axis=1),
                                      np.nan)
    # MEDIAN AKTIF & SECOND MAX — v2.13.7 (perf-audit B): matrix numpy
    # penuh menggantikan 2 loop per-baris (dulu median/second-max loop
    # 25.901 baris). Identik: sort naik per baris dengan NaN di akhir,
    # posisi median = (cnt-1)//2 & cnt//2 (np.median utk genap = rata
    # dua tengah); second max = elemen ke-(cnt-2) (np.partition[-2]).
    masked = np.where(aktif_mask_np, filled, np.nan)
    srt = np.sort(masked, axis=1)  # NaN di akhir tiap baris
    cnt = aktif_mask_np.sum(axis=1)
    rows_idx = np.arange(len(filled))
    with np.errstate(invalid="ignore"):
        med_lo = srt[rows_idx, np.maximum((cnt - 1) // 2, 0)]
        med_hi = srt[rows_idx, np.maximum(cnt // 2, 0)]
        median_aktif_arr = np.where(
            cnt > 0,
            np.where((cnt % 2) == 0, (med_lo + med_hi) / 2, med_hi),
            np.nan)
        second_max_arr = np.where(
            cnt >= 2,
            srt[rows_idx, np.maximum(cnt - 2, 0)],
            np.nan)

    # HARI MAX: NOMOR HARI (dari nama kolom) tempat MAX pertama muncul (kalau MAX > 0)
    # M2 (v2.3.1): dulu mengembalikan posisi dalam day_cols (idx+1) — hanya
    # kebetulan benar untuk kolom hari kontigu "1".."31"; untuk kolom hari
    # sparse (mis. hanya "1","5","30") hasilnya off. Sekarang nomor hari
    # diambil dari nama kolomnya, bukan posisi.
    # v2.13.7 (perf-audit B): day_matrix.iloc[i] PER BARIS (akses termahal
    # pandas — 201 ms) → matriks numpy sekali + argmax vektor.
    day_np = day_matrix.to_numpy(dtype=float)
    day_col_nums = np.array([int(float(c)) for c in day_cols])
    valid_max = max_arr > 0  # max_arr sudah tanpa NaN (baris 182 di atas)
    match = (day_np == max_arr[:, None]) & nonnull_mask_np
    has_match = match.any(axis=1)
    first_idx = np.argmax(match, axis=1)  # 0 bila tak ada (dilindungi mask)
    hm = valid_max & has_match
    nums = day_col_nums[np.where(hm, first_idx, 0)]
    hari_max_arr = np.array(
        [int(n) if keep else None for n, keep in zip(nums.tolist(), hm)],
        dtype=object)

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
    # M1 (v2.3.1): input invalid (num/den NaN atau den <= 0) sekarang → NaN
    # (null), sesuai semantik display M ("if x > 0 then ... else null"),
    # bukan 0.0. Aman untuk sinyal: signals.py hanya memakai perbandingan
    # >= threshold terhadap kolom-kolom ini (NaN >= t == False, sama seperti
    # 0.0 >= t untuk semua threshold > 0), jadi ANOMALY SCORE/STATUS tidak
    # berubah. _scale_signal di bawah juga hanya perbandingan (NaN → "NO").
    def _safe_ratio(num, den):
        result = np.full(num.shape, np.nan, dtype=float)
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
    # v2.19.8 — W-6 (audit): ganti band diskrit [8,12]∪[80,120]∪... yg
    # punya dead zone (mis. ratio 172 ∈ (120,800) tak kena padahal pola
    # 100× typo asli) dgn log10-rounding tolerance ±100% (log10(2)=0.301):
    # 10× flags 5-20, 100× flags 50-200, 1000× flags 500-2000, dst. Floor
    # sr>=8 utk hindari noise rendah. 172 → log10=2.236, round=2, diff=0.236
    # < 0.301 → YES (100× typo) — sebelumnya luput.
    import math as _math
    _LOG10_2 = _math.log10(2.0)  # ~0.301 — tolerance ±100% sekitar 10^k
    def _scale_signal(sr):
        if sr >= 8:
            try:
                lg = _math.log10(sr)
            except (ValueError, TypeError):
                return "NO"
            if abs(lg - round(lg)) <= _LOG10_2:
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

    v2.3.1 (H1/H2/H3/M3): KONTRIBUSI TERBESAR aggregate by KETERANGAN dulu
    (sesuai M code, bukan baris tunggal teratas); kolom GABUNGAN memakai nama
    spasi sesuai FINAL_COLUMN_ORDER; parts GABUNGAN diurutkan kontribusi
    (TOTAL_REASON desc); placeholder all-null "KONTRIBUSI_TERBESAR" dihapus.
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
    # M3 (v2.3.1): urutan parts KETERANGAN/SOURCE DATA GABUNGAN mengikuti
    # kontribusi (TOTAL_REASON menurun) seperti M, bukan urutan key groupby
    # (alfabetis). Sort STABIL sebelum groupby pendek supaya urutan nilai
    # distinct di tiap group = urutan kontribusi (tie → first occurrence).
    rt = rt.sort_values("TOTAL_REASON", ascending=False, kind="stable")

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

    # v2.13.7 (perf-audit B): GABUNGAN tanpa lambda-Python per grup
    # (dulu 12,6k panggilan _join_distinct) — nilai non-null di-dedup
    # per (grup, nilai) lalu di-gabung groupby.agg(", ".join) level-C.
    # Urutan nilai = urutan kemunculan di rt (kontribusi menurun) —
    # IDENTIK dict.fromkeys preserve-order; grup tanpa nilai → NaN → ""
    # (fillna di bawah, replika return "" _join_distinct lama).
    def _gabungan_frame(col: str) -> pd.DataFrame:
        d = (rt.loc[rt[col].notna().to_numpy(),
                    group_keys_short + [col]]
             .drop_duplicates(subset=group_keys_short + [col], keep="first"))
        if d.empty:
            return d
        g = (d.groupby(group_keys_short, dropna=False, sort=True)[col]
             .agg(", ".join).reset_index())
        return g

    ket_g = _gabungan_frame("_ket_for_gabungan")
    src_g = _gabungan_frame("_src_for_gabungan")
    rs = rt[group_keys_short].drop_duplicates(subset=group_keys_short,
                                               keep="first")
    rs = rs.merge(ket_g, on=group_keys_short, how="left",
                  validate="many_to_one")
    rs = rs.merge(src_g, on=group_keys_short, how="left",
                  validate="many_to_one")
    rs = rs.rename(columns={"_ket_for_gabungan": "KETERANGAN GABUNGAN",
                            "_src_for_gabungan": "SOURCE DATA GABUNGAN"})
    rs["KETERANGAN GABUNGAN"] = rs["KETERANGAN GABUNGAN"].fillna("")
    rs["SOURCE DATA GABUNGAN"] = rs["SOURCE DATA GABUNGAN"].fillna("")

    # KONTRIBUSI TERBESAR (hanya WASTE groups) — H1 (v2.3.1): aggregate
    # BY KETERANGAN (sum TOTAL_REASON per KETERANGAN) baru ambil terbesar;
    # pct = sum(keterangan top) / grand_total.
    # v2.13.7 (perf-audit B): loop 2.500 grup × mask-python (±1,9 dtk
    # data asli; 2.503× _getitem_bool_array di cProfile) → vektor penuh:
    # satu groupby 4-kunci + stable-sort + drop_duplicates. Semantik
    # idxmax dipertahankan: groupby mengurutkan (short, KETERANGAN)
    # naik → sort STABLE desc nilai mempertahankan urutan KETERANGAN
    # di antara tie → drop_duplicates keep='first' = nilai terbesar,
    # tie → KETERANGAN terkecil — REPLIKA idxmax di index terurut.
    # (Sebelum fix: 1.605 dari 6.899 baris non-null beda vs output M.)
    valid_mask = (is_waste & rt["TOTAL_REASON"].notna()
                  & (rt["TOTAL_REASON"] > 0) & ket_nonempty)
    fw = rt.loc[valid_mask.to_numpy(),
                group_keys_short + ["KETERANGAN", "TOTAL_REASON"]]
    if fw.empty:
        rs["KONTRIBUSI TERBESAR"] = None
    else:
        ket_tot = (fw.groupby(group_keys_short + ["KETERANGAN"],
                              dropna=False)["TOTAL_REASON"].sum()
                   .reset_index())
        ket_tot = ket_tot.sort_values("TOTAL_REASON", ascending=False,
                                      kind="stable")
        top = ket_tot.drop_duplicates(subset=group_keys_short, keep="first")
        grand = (fw.groupby(group_keys_short, dropna=False)["TOTAL_REASON"]
                 .sum().reset_index(name="_grand"))
        top = top.merge(grand, on=group_keys_short, how="left",
                        validate="many_to_one")
        top = top[top["_grand"] != 0]  # replika guard grand_total == 0
        if top.empty:
            rs["KONTRIBUSI TERBESAR"] = None
        else:
            ratio = (top["TOTAL_REASON"].to_numpy(dtype=float)
                     / top["_grand"].to_numpy(dtype=float))
            pct = np.round(ratio * 100, 0)  # half-even, sama round() Python
            top = top.assign(**{"KONTRIBUSI TERBESAR": [
                f"{k} {int(p)}%"
                for k, p in zip(top["KETERANGAN"].tolist(),
                                pct.tolist())]})
            rs = rs.merge(top[group_keys_short + ["KONTRIBUSI TERBESAR"]],
                          on=group_keys_short, how="left",
                          validate="many_to_one")
            # NaN → None (replika dict.get None; kontrak pd.isna utuh)
            rs["KONTRIBUSI TERBESAR"] = rs["KONTRIBUSI TERBESAR"].where(
                rs["KONTRIBUSI TERBESAR"].notna(), None)

    # Cleanup helper cols
    rt = rt.drop(columns=["_waste_valid", "_ket_for_gabungan",
                          "_src_for_gabungan"], errors="ignore")

    # Merge back to df (left join) — defensive: drop kolom yang akan di-merge dulu
    # (v2.13.7: df.copy() pra-merge dihapus — drop() & merge() sudah
    # menghasilkan frame baru, salinan penuh 25,9rb×105 redundan)
    cols_to_merge = ["KETERANGAN GABUNGAN", "SOURCE DATA GABUNGAN",
                     "KONTRIBUSI TERBESAR"]
    df_clean = df
    for c in cols_to_merge:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    out = df_clean.merge(rs, on=group_keys_short, how="left",
                         validate="many_to_one")
    # M5 (v2.3.1): lookup merge — rs unique per group key (hasil groupby)
    # → many_to_one. Row order kiri terjaga (left join).
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
    out = df_clean.merge(gt, on=group_keys, how="left", validate="many_to_one")
    # M5 (v2.3.1): lookup merge — gt unique per group key (hasil groupby) → m:1.
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
    v2.3.0: TOTAL BOM bisa dari 2 sumber:
      1. Kolom TOTAL BOM yang sudah ada di DATA_WASTE.xlsx (prioritas — user pakai ini)
      2. Sheet BOM terpisah (fallback kalau kolom TOTAL BOM tidak ada di data)
    Left-join df dengan BOM pada (NAMA RESTO == Nomor #) AND (NAMA BARANG == Nama Barang).
    Hasil: TOTAL BOM + Rill % to BOM = TOTAL / TOTAL BOM.
    """
    # v2.3.0: Kalau TOTAL BOM sudah ada di df (dari kolom input data), pakai itu langsung
    # dan skip merge dengan sheet BOM terpisah
    if "TOTAL BOM" in df.columns:
        # Coerce TOTAL BOM ke numeric (kalau ada string kosong)
        df = df.copy()
        df["TOTAL BOM"] = pd.to_numeric(df["TOTAL BOM"], errors="coerce")
        # Compute Rill % to BOM = TOTAL / TOTAL BOM (guarded)
        df["Rill % to BOM"] = np.where(
            (df["TOTAL"].notna()) & (df["TOTAL BOM"].notna()) & (df["TOTAL BOM"] > 0),
            df["TOTAL"] / df["TOTAL BOM"],
            0.0,
        )
        return df

    # Fallback: pakai sheet BOM terpisah (kalau ada)
    if bom_df is None or bom_df.empty:
        # M6 (v2.3.1): copy dulu supaya early-return tidak memutasi df pemanggil
        # (sebelumnya df["TOTAL BOM"] = np.nan menulis ke frame caller).
        df = df.copy()
        df["TOTAL BOM"] = np.nan
        df["Rill % to BOM"] = 0.0
        return df

    # Siapkan BOM untuk join — normalisasi kunci via _key_str (F1 v2.3.2):
    # float integral dari cell numerik (1049.0) → "1049" (bukan "1049.0");
    # None/NaN → None (bukan "nan") supaya tidak join palsu. Kedua sisi join
    # memakai normalisasi identik — sebelumnya outlet numerik TIDAK PERNAH
    # match → sinyal S6/S7 mati diam-diam.
    bom = bom_df.copy()
    bom["Nomor #"] = bom["Nomor #"].map(_key_str)
    bom["Nama Barang"] = bom["Nama Barang"].map(_key_str)
    bom = bom.dropna(subset=["Nomor #", "Nama Barang"])

    df_join = df.copy()
    # Defensive: drop TOTAL BOM dari df kalau sudah ada (idempotent), supaya merge tidak buat _x/_y
    if "TOTAL BOM" in df_join.columns:
        df_join = df_join.drop(columns=["TOTAL BOM"])
    # Normalisasi kunci sisi data — None untuk sel kosong. CATATAN
    # (audit v2.18.0, koreksi komentar lama): pandas merge JUGA
    # mematch-kan NA==NA pada kunci — keamanan baris kosong TIDAK
    # datang dari sini, melainkan dari dropna sisi BOM di atas
    # (kunci None di sisi lookup sudah dibuang → baris df kosong
    # tetap dipertahankan di output tanpa pasangan BOM).
    df_join["NAMA RESTO"] = df_join["NAMA RESTO"].map(_key_str)
    df_join["NAMA BARANG"] = df_join["NAMA BARANG"].map(_key_str)

    out = df_join.merge(
        # M5 (v2.3.1): lookup merge many_to_one — kunci join sisi BOM di-dedupe
        # (keep first) supaya BOM dengan kunci ganda tidak me-multiply baris df
        # (semantik lookup M: satu baris BOM per outlet+item).
        bom[["Nomor #", "Nama Barang", "TOTAL BOM"]].drop_duplicates(
            subset=["Nomor #", "Nama Barang"], keep="first"),
        left_on=["NAMA RESTO", "NAMA BARANG"],
        right_on=["Nomor #", "Nama Barang"],
        how="left",
        validate="many_to_one",
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
        # M6 (v2.3.1): copy dulu supaya early-return tidak memutasi df pemanggil.
        df = df.copy()
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
    out = df_clean.merge(peer_stats, on=keys_short, how="left", validate="many_to_one")
    # M5 (v2.3.1): lookup merge — peer_stats unique per keys_short (groupby) → m:1.
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
        # M6 (v2.3.1): copy dulu supaya early-return tidak memutasi df pemanggil.
        df = df.copy()
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
    out = df_clean.merge(top_df, on=keys, how="left", validate="many_to_one")
    # M5 (v2.3.1): lookup merge — top_df unique per keys (groupby) → m:1.
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

    v2.3.1 (C2/M5/M6): sat di-proyeksikan hanya ke kolom yang dibutuhkan
    (NAMA ITEM + helper cols) supaya kolom yang tabrakan dengan df (mis.
    SATUAN, NAMA BARANG) tidak kena suffix _x/_y dan menggeser kolom kanonik;
    merge memakai validate=many_to_one dengan NAMA ITEM di-dedupe.
    """
    expected_helper_cols = [
        "CANCEL NOTA", "SUSUT", "TRIAL", "HANDLING",
        "KUALITAS EKSTERNAL", "KUALITAS", "KUALITAS INTERNAL",
        "EKSTERNAL", "INTERNAL", "ALAT MESIN", "OVERSTOCK",
    ]
    if satuan_df is None or satuan_df.empty:
        # M6 (v2.3.1): copy dulu supaya early-return tidak memutasi df pemanggil.
        df = df.copy()
        for c in expected_helper_cols:
            df[c] = np.nan
        return df

    sat = satuan_df.copy()
    # Pastikan ada kolom NAMA ITEM
    if "NAMA ITEM" not in sat.columns:
        # M6 (v2.3.1): idem — jangan mutasi df pemanggil.
        df = df.copy()
        for c in expected_helper_cols:
            df[c] = np.nan
        return df

    # Strip & uppercase-lowercase untuk matching.
    # v2.18.0 audit (BUG 2): kunci join NA-safe via kolom sekali-pakai —
    # dulu ``df_join["NAMA BARANG"] = ....astype(str)`` MENIMPA kolom
    # kanonik dengan literal "<NA>" (StringDtype pd.NA) yang lalu bocor
    # ke seluruh output (tabel/export/join history). Kini kolom kanonik
    # tak tersentuh; kunci kosong di-drop dari sisi lookup (pola
    # stage_05 dropna — kunci kosong tak bisa di-join bermakna).
    si = sat["NAMA ITEM"]
    sat["_sat_key"] = (si.astype("object").where(si.notna(), "")
                       .astype(str).str.strip())
    df_join = df.copy()
    # Defensive: drop helper cols dari df kalau sudah ada (idempotent case)
    for c in expected_helper_cols:
        if c in df_join.columns:
            df_join = df_join.drop(columns=[c])
    nb = df_join["NAMA BARANG"]
    df_join["_nb_key"] = (nb.astype("object").where(nb.notna(), "")
                         .astype(str).str.strip())

    # C2 (v2.3.1): JANGAN merge seluruh frame sat. Dulu, kolom sat yang
    # tabrakan dengan df (SATUAN, NAMA BARANG, dst.) otomatis kena suffix
    # _x/_y dan kolom kanonik (mis. SATUAN dari df) hilang diam-diam.
    # Proyeksikan sat hanya ke kolom yang dibutuhkan: join key + helper cols,
    # dan buang dari proyeksi kolom yang masih ada di df (defense berlapis).
    sat_cols = ["NAMA ITEM"] + [c for c in expected_helper_cols if c in sat.columns]
    sat_cols = [c for c in sat_cols if c == "NAMA ITEM" or c not in df_join.columns]
    sat_proj = sat[sat_cols + ["_sat_key"]]
    # M5 (v2.3.1): lookup merge many_to_one — NAMA ITEM di-dedupe (keep
    # first) supaya entry ganda di DATABASE_SATUAN tidak me-multiply baris df
    # (semantik lookup M: satu baris per item).
    sat_proj = sat_proj.drop_duplicates(subset=["_sat_key"], keep="first")
    # Kunci kosong (blank/NA) tak bermakna — drop dari sisi lookup
    # (anti join palsu blank-item ↔ blank-item).
    sat_proj = sat_proj[sat_proj["_sat_key"] != ""]
    out = df_join.merge(
        sat_proj,
        left_on="_nb_key",
        right_on="_sat_key",
        how="left",
        validate="many_to_one",
    )
    # Drop kolom join sekali-pakai + NAMA ITEM duplikat (dari satuan)
    out = out.drop(
        columns=[c for c in ("NAMA ITEM", "_sat_key", "_nb_key")
                 if c in out.columns])
    # Pastikan semua helper col ada (kalau satuan tidak punya semua)
    for c in expected_helper_cols:
        if c not in out.columns:
            out[c] = np.nan
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
    # C2 (v2.3.1): check duplikat diperkuat — pasangan kolom _x/_y pasca-merge
    # adalah tanda tabrakan nama yang lolos dari proyeksi di atas. Fail loud
    # (ValueError) — jangan biarkan kolom kanonik hilang diam-diam seperti dulu.
    _suffixed_x = [c for c in out.columns if isinstance(c, str) and c.endswith("_x")]
    _collisions = [c[:-2] for c in _suffixed_x if (c[:-2] + "_y") in out.columns]
    if _collisions:
        raise ValueError(
            "stage_09_satuan: merge menghasilkan kolom bertabrak (_x/_y): "
            f"{_collisions} — kolom kanonik berisiko tertimpa. Periksa sheet DATABASE_SATUAN."
        )
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

    v2.3.1 (C1/H4): df kosong tidak crash; HELPER/STATUS dari input
    (re-run pipeline di file output) dipreservasi — re-derivation butuh
    DATABASE_SATUAN yang sering tidak ada. % to BOM selalu dihitung ulang
    (derived murni dari TOTAL/TOTAL BOM).
    """
    # C1 (v2.3.1): df kosong (mis. semua baris terfilter di Stage 2) —
    # df.apply(..., result_type="expand") mengembalikan frame 0-kolom dan
    # assignment .columns di bawah melempar "ValueError: Length mismatch".
    # Guard: buat kolom kosong dan return early (tidak ada yang bisa dihitung).
    if df.empty:
        out = df.copy()
        for c in ("HELPER", "STATUS", "% to BOM"):
            if c not in out.columns:
                out[c] = None
        return out

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

    def _status_value(helper_value_num, max_value_num):
        # STATUS logic dari M code
        if helper_value_num is None:
            return None
        if (helper_value_num == 1 and max_value_num >= 0) or (helper_value_num == 0 and max_value_num == 0):
            return "Sesuai"
        return "Tidak Sesuai"

    # v2.13.7 (perf-audit B): apply(axis=1) membangun Series PER BARIS
    # (25.901 × ~3 kolom lookup = 207 ms) → transkripsi kolom-numpy.
    # Logika per-baris DISALIN PERSIS cabang demi cabang (semantik
    # None-vs-NaN, urutan pengecekan, try/except sama sekali tak berubah).
    def _col_vals(name: str):
        """Kolom sbg numpy 1D — nama duplikat → kolom pertama (replika
        _scalar row.get lama); kolom absen → None (row.get → None)."""
        if name not in df.columns:
            return None
        c = df[name]
        if isinstance(c, pd.DataFrame):  # nama kolom duplikat
            c = c.iloc[:, 0]
        return c.to_numpy()

    def _pct_bom_list() -> list:
        # 1) % to BOM — INDEPENDEN dari KETERANGAN (sesuai M code)
        # M11 (v2.3.1): kolom ini SENGAJA mixed dtype (float, "Cek", None)
        # — replika output M ("Cek" = TOTAL/TOTAL BOM tidak diketahui,
        # null = BOM 0).
        tot = _col_vals("TOTAL")
        bom = _col_vals("TOTAL BOM")
        n = len(df)
        out = [None] * n
        for i in range(n):
            t = None if tot is None else tot[i]
            b = None if bom is None else bom[i]
            if (t is None or b is None
                    or (isinstance(b, float) and np.isnan(b))):
                out[i] = "Cek"
                continue
            try:
                if float(b) == 0:
                    out[i] = None  # try ... otherwise null di M code
                else:
                    out[i] = float(t) / float(b)
            except (ValueError, TypeError):
                out[i] = None
        return out

    def _status_from_carried_list() -> list:
        # HELPER carried tapi STATUS absen: derivasi STATUS dari HELPER
        # terpreservasi + MAX saat ini (logika AddHelper M).
        hel = _col_vals("HELPER")
        mx = _col_vals("MAX")
        n = len(df)
        out = [None] * n
        for i in range(n):
            hv = None if hel is None else hel[i]
            try:
                hv_num = (None if hv is None
                          or (isinstance(hv, float) and np.isnan(hv))
                          else float(hv))
            except (ValueError, TypeError):
                hv_num = None
            mv = None if mx is None else mx[i]
            mv_num = (float(mv) if mv is not None
                      and not (isinstance(mv, float) and np.isnan(mv)) else 0)
            out[i] = _status_value(hv_num, mv_num)
        return out

    def _helper_status_lists() -> tuple[list, list]:
        # 2) HELPER & STATUS — bergantung KETERANGAN (jalur rekap mentah:
        # HELPER tidak dibawa dari input).
        ket = _col_vals("KETERANGAN")
        mx = _col_vals("MAX")
        cat_cols: dict[str, np.ndarray | None] = {}
        n = len(df)
        helpers: list = [None] * n
        statuses: list = [None] * n
        for i in range(n):
            k = None if ket is None else ket[i]
            if (k is None or (isinstance(k, float) and np.isnan(k))
                    or str(k).strip() == ""):
                continue
            col = cat_map.get(str(k).strip())
            if col is None or col not in df.columns:
                continue
            if col not in cat_cols:
                cat_cols[col] = _col_vals(col)
            hv = cat_cols[col][i]
            # Coerce ke numerik (None stays None)
            try:
                if hv is None or (isinstance(hv, float) and np.isnan(hv)):
                    hv_num = None
                else:
                    hv_num = float(hv)
            except (ValueError, TypeError):
                hv_num = None
            mv = None if mx is None else mx[i]
            mv_num = (float(mv) if mv is not None
                      and not (isinstance(mv, float) and np.isnan(mv)) else 0)
            helpers[i] = hv_num
            statuses[i] = _status_value(hv_num, mv_num)
        return helpers, statuses

    # H4 (v2.3.1): HELPER dibawa dari input (Stage 1 sekarang keep HELPER/STATUS
    # — re-run pipeline di file output, DATABASE_SATUAN sering tidak ada).
    # Preserve HELPER & STATUS dari input; hanya % to BOM — derived murni dari
    # TOTAL/TOTAL BOM — yang selalu dihitung ulang. Behavior lama (hitung
    # fresh saat HELPER absen, mis. input rekap mentah) tetap terjaga di bawah.
    # (v2.13.7: df.copy() pra-drop dihapus — drop() sudah menghasilkan frame
    # baru; assignment kolom jatuh ke salinan drop, bukan input df.)
    df_clean = df
    if "HELPER" in df_clean.columns:
        df_clean = df_clean.drop(columns=["% to BOM"], errors="ignore")
        if "STATUS" not in df_clean.columns:
            df_clean = df_clean.assign(
                STATUS=_status_from_carried_list())
        df_clean = df_clean.assign(**{"% to BOM": _pct_bom_list()})
        return df_clean

    # Defensive: drop HELPER/STATUS/% to BOM dari df kalau sudah ada (idempotent case)
    for c in ["HELPER", "STATUS", "% to BOM"]:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    helpers, statuses = _helper_status_lists()
    helper_records = pd.DataFrame(
        {"HELPER": helpers, "STATUS": statuses,
         "% to BOM": _pct_bom_list()})
    out = pd.concat([df_clean.reset_index(drop=True),
                     helper_records.reset_index(drop=True)], axis=1)
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
# STAGE 12.5 — WASTE FINGERPRINT per item (NEW v2.3.0)
# ============================================================
# Setara W11 fingerprint dari Inventory-Control: untuk setiap item (NAMA BARANG),
# klasifikasikan komposisi loss-nya:
#   W = Σ TOTAL untuk JENIS=WASTE
#   S = Σ TOTAL untuk JENIS=SUSUT
#   T = Σ TOTAL untuk JENIS=TRIAL
#   explained = W + S + T
#   shareW = W / explained, shareS = S / explained, shareT = T / explained
#   class = max-share → W-DOMINANT / S-DOMINANT / T-DOMINANT (atau null kalau explained=0)
# Tambahan: SISTEMATIK FLAG per item
#   isSistematik = daysActive >= ceil(KeyAkhir/2) AND cabangActive >= 2
# ============================================================

def stage_12_5_fingerprint(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Compute Waste Fingerprint + Sistematik Flag per item (NAMA BARANG).
    Adaptasi dari Inventory-Control W11 fingerprint.ts + sistematik.ts.
    """
    if "NAMA BARANG" not in df.columns or "JENIS" not in df.columns or "TOTAL" not in df.columns:
        # Tidak bisa compute, return apa adanya
        return df

    # Aggregate per item: W, S, T sums
    item_pivot = df.pivot_table(
        index="NAMA BARANG",
        columns="JENIS",
        values="TOTAL",
        aggfunc="sum",
        fill_value=0,
    )
    # Ensure kolom W/S/T ada
    for col in ["WASTE", "SUSUT", "TRIAL"]:
        if col not in item_pivot.columns:
            item_pivot[col] = 0
    item_pivot = item_pivot[["WASTE", "SUSUT", "TRIAL"]].copy()
    item_pivot.columns = ["W", "S", "T"]
    item_pivot["explained"] = item_pivot["W"] + item_pivot["S"] + item_pivot["T"]
    item_pivot["shareW"] = np.where(item_pivot["explained"] > 0, item_pivot["W"] / item_pivot["explained"], 0)
    item_pivot["shareS"] = np.where(item_pivot["explained"] > 0, item_pivot["S"] / item_pivot["explained"], 0)
    item_pivot["shareT"] = np.where(item_pivot["explained"] > 0, item_pivot["T"] / item_pivot["explained"], 0)

    # Class: max-share wins, ties break W > S > T (deterministic per spec Inventory-Control)
    def _classify(row):
        if row["explained"] <= 0:
            return None
        w, s, t = row["shareW"], row["shareS"], row["shareT"]
        if w >= s and w >= t:
            return "W-DOMINANT"
        if s >= t:
            return "S-DOMINANT"
        return "T-DOMINANT"
    item_pivot["FINGERPRINT CLASS"] = item_pivot.apply(_classify, axis=1)

    # Reset index supaya NAMA BARANG jadi kolom
    item_pivot = item_pivot.reset_index()

    # Compute SISTEMATIK FLAG per item
    # v2.19.8 — W-5 (audit-1) + B-1 (audit-2): DUA variabel utk DUA konsumen
    # (satu variabel utk keduanya merusak QUADRANT — persistence bisa >1):
    #   - daysActiveNet = SUM Count Hari per item lintas resto — LUAS
    #     jaringan, utk SISTEMATIK (threshold absolute
    #     SISTEMATIK_MIN_DAYS default 5 — BUKAN ceil(key_akhir/2) yg mati
    #     pada file pendek; audit-1 W-5).
    #   - daysActive = MAX Count Hari per item — persistence PER-OUTLET,
    #     utk stage_12_6 QUADRANT (daysActive/key_akhir harus ≤ 1; SUM bisa
    #     >1 → semua item aktif jadi QUADRANT=SISTEMIK palsu — audit-2 B-1).
    # cabangActive ≥ 2 tetap (item muncul di ≥2 resto).
    sistematik_min_days = int(config.get("SISTEMATIK_MIN_DAYS", 5))
    if "Count Hari" in df.columns and "NAMA RESTO" in df.columns:
        sistematik_df = df.groupby("NAMA BARANG", dropna=False).agg(
            daysActive=("Count Hari", "max"),      # per-outlet (QUADRANT)
            daysActiveNet=("Count Hari", "sum"),   # network breadth (SISTEMATIK)
            cabangActive=("NAMA RESTO", "nunique"),
            totalWaste=("TOTAL", "sum"),
        ).reset_index()
    else:
        sistematik_df = item_pivot[["NAMA BARANG"]].copy()
        sistematik_df["daysActive"] = 0
        sistematik_df["daysActiveNet"] = 0
        sistematik_df["cabangActive"] = 0
        sistematik_df["totalWaste"] = 0

    # Sistematik threshold: daysActiveNet (sum) >= SISTEMATIK_MIN_DAYS AND cabangActive >= 2
    sistematik_df["SISTEMATIK"] = np.where(
        (sistematik_df["daysActiveNet"] >= sistematik_min_days) & (sistematik_df["cabangActive"] >= 2),
        "YES", "NO"
    )
    sistematik_df["SISTEMATIK DAYS THRESHOLD"] = sistematik_min_days

    # Merge fingerprint + sistematik ke df utama (left join on NAMA BARANG)
    # Pertama, drop kolom yang akan di-merge dari df kalau sudah ada (idempotent)
    cols_to_merge = ["W", "S", "T", "explained", "shareW", "shareS", "shareT", "FINGERPRINT CLASS",
                    "daysActive", "daysActiveNet", "cabangActive", "totalWaste", "SISTEMATIK", "SISTEMATIK DAYS THRESHOLD"]
    df_clean = df.copy()
    for c in cols_to_merge:
        if c in df_clean.columns:
            df_clean = df_clean.drop(columns=[c])
    # M5 (v2.3.1): lookup merges — item_pivot (pivot_table) dan sistematik_df
    # (groupby) unique per NAMA BARANG → many_to_one. Row order kiri terjaga.
    out = df_clean.merge(item_pivot, on="NAMA BARANG", how="left", validate="many_to_one")
    out = out.merge(sistematik_df, on="NAMA BARANG", how="left", validate="many_to_one")
    # Defensive: pastikan tidak ada duplicate columns
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
    return out


# ============================================================
# STAGE 12.6 — QUADRANT CLASSIFICATION per item (NEW v2.3.0)
# ============================================================
# Setara W3 Quadrant dari Inventory-Control: scatter plot
#   X = prevalence (% cabang yang punya waste item itu)
#   Y = persistence (% hari item itu aktif dari KeyAkhir)
# 4 quadrant:
#   SISTEMIK     = high prevalence × high persistence (recipe/process problem)
#   MUSIMAN      = high prevalence × low persistence (seasonal spike)
#   LOKAL-KRONIS = low prevalence × high persistence (one outlet recurring)
#   INSIDEN      = low prevalence × low persistence (one-off)
# Threshold: 50% (configurable via QUADRANT_THRESHOLD di config)
# ============================================================

def stage_12_6_quadrant(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Compute Quadrant Classification per item.
    Adaptasi dari Inventory-Control W3 quadrant-card.tsx.
    """
    if "NAMA BARANG" not in df.columns:
        return df

    # Reuse aggregates dari stage 12.5 kalau ada
    if "cabangActive" not in df.columns or "daysActive" not in df.columns:
        return df  # stage 12.5 belum jalan

    # Total cabang unik di seluruh dataset (untuk prevalence %)
    if "NAMA RESTO" not in df.columns:
        return df
    total_cabang = df["NAMA RESTO"].nunique()
    if total_cabang == 0:
        return df

    # Threshold (50% by default, configurable)
    quadrant_threshold = config.get("thresholds", {}).get("QUADRANT_THRESHOLD", 0.5)

    # Hitung per row (karena cabangActive & daysActive sudah broadcast dari stage 12.5)
    df = df.copy()
    df["_prevalence"] = df["cabangActive"] / total_cabang  # 0..1
    df["_persistence"] = np.where(
        key_akhir > 0,
        df["daysActive"] / key_akhir,
        0
    )

    # Quadrant logic — v2.13.7 (perf-audit B): apply(axis=1) 25.901 baris
    # (213 ms) → np.select vektor; NaN memicu semua kondisi False →
    # "INSIDEN", identik cabang demi cabang kode lama.
    p = df["_prevalence"].to_numpy()
    s = df["_persistence"].to_numpy()
    df["QUADRANT"] = np.select(
        [(p >= quadrant_threshold) & (s >= quadrant_threshold),
         (p >= quadrant_threshold) & (s < quadrant_threshold),
         (p < quadrant_threshold) & (s >= quadrant_threshold)],
        ["SISTEMIK", "MUSIMAN", "LOKAL-KRONIS"],
        default="INSIDEN",
    )

    # Cleanup helper cols
    df = df.drop(columns=["_prevalence", "_persistence"], errors="ignore")
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
