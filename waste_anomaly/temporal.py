"""
temporal.py — analisa temporal: waste per hari, pola weekday (mod-7), efek
peak-day per KETERANGAN, matrix KETERANGAN x hari, dan breakdown per SATUAN.

Modul baru v2.5.0 (gelombang fitur "analisa temporal") — menutup blind spot
#4 dari evaluasi EVAL-DRILLDOWN-ANALISA: 12 sinyal di signals.py tidak punya
dimensi waktu, padahal DATA_WASTE.xlsx punya pola mod-7 kuat — hari dengan
day % 7 di {5, 6} (5, 6, 12, 13, 19, 20, 26, 27) mean-per-baris-aktif 369,7
vs 273,6 untuk hari lain (+35%).

Struktur data masukan (sheet mentah 'Sheet1', kolom string):
  - kolom hari '1'..'31' — waste per hari (NaN = tidak ada waste);
  - 'TOTAL'          = jumlah kolom hari;
  - 'KETERANGAN'     = alasan waste (dimensi matrix heatmap);
  - 'NAMA BARANG'    = item (distinct count di unit_summary);
  - 'SATUAN'         = unit item (dinormalisasi NBSP/zero-width).

Kontrak output (dipakai UI tab analisa temporal — nama kolom JANGAN diubah):
  waste_per_day()        -> day | total | active_rows | mean_per_active
  weekday_pattern()      -> mod_class | days | total | active_rows | ...
  weekday_effect()       -> dict peak_classes / peak_mean / offpeak / ratio
  reason_by_day()        -> KETERANGAN | 1..N (header INT) | Total
  reason_weekday_ratio() -> KETERANGAN | peak_mean | offpeak_mean | ratio ...
  unit_summary()         -> SATUAN | rows | active_rows | items | total | ...

Semua fungsi DEFENSIF: df kosong / kolom wajib hilang / tanpa kolom hari ->
hasil kosong dengan kolom output yang benar — tidak pernah raise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Label khusus kontrak output
_SATUAN_EMPTY = "(kosong)"
_LAINNYA = "Lainnya"


# ============================================================
# HELPERS INTERNAL
# ============================================================

def _day_cols(df: pd.DataFrame) -> list[str]:
    """Kolom hari yang ada di df (nama '1'..'31' string), urut int naik.

    Header non-standar tetap dikenali lewat bentuk string-nya (int 5 dari
    engine lain dihitung sebagai hari '5'); duplikat bentuk apa pun dihitung
    sekali. Input bukan DataFrame -> list kosong.
    """
    if not isinstance(df, pd.DataFrame):
        return []
    found: dict[int, str] = {}
    for col in df.columns:
        name = str(col).strip()
        if not name.isdigit():
            continue
        try:
            day = int(name)
        except ValueError:
            continue
        if 1 <= day <= 31 and day not in found:
            found[day] = name
    return [found[d] for d in sorted(found)]


def _frame_ok(df: object) -> bool:
    """True bila df adalah DataFrame non-kosong (guard anti None / tipe lain)."""
    return isinstance(df, pd.DataFrame) and not df.empty


def _col(df: pd.DataFrame, name: object) -> pd.Series | None:
    """Kolom `name` sebagai Series; None bila hilang, duplikat -> ambil pertama."""
    if name not in df.columns:
        return None
    raw = df[name]
    if isinstance(raw, pd.DataFrame):  # nama kolom duplikat
        raw = raw.iloc[:, 0]
    return raw


def _day_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Series numerik untuk kolom hari `name` (errors='coerce', NaN tetap NaN).

    Fallback bentuk header lain dengan nilai hari sama (int 5 atau '05' untuk
    nama '5'); kolom benar-benar hilang -> Series NaN sepanjang df (jumlah 0,
    tidak dihitung aktif).
    """
    raw = _col(df, name)
    if raw is None:
        try:
            target = int(name)
        except ValueError:
            target = None
        if target is not None:
            for col in df.columns:
                try:
                    if int(str(col).strip()) == target:
                        raw = _col(df, col)
                        break
                except ValueError:
                    continue
    if raw is None:
        return pd.Series(np.nan, index=pd.RangeIndex(len(df)), dtype=float)
    return pd.to_numeric(raw, errors="coerce")


def _day_range(df: pd.DataFrame, key_akhir: int | None) -> list[int]:
    """Hari (int, urut naik) yang diproses: kolom hari yang ada, dibatasi 1..N.

    N = key_akhir bila diberikan (nilai aneh -> pakai maksimum yang ada);
    selain itu N = hari maksimum yang kolomnya ada.
    """
    days = [int(n) for n in _day_cols(df)]
    if not days or key_akhir is None:
        return days
    try:
        limit = int(key_akhir)
    except (TypeError, ValueError):
        return days
    return [d for d in days if d <= limit]


def _ket_series(df: pd.DataFrame) -> pd.Series | None:
    """KETERANGAN sebagai Series string (NaN -> ''). None bila kolom hilang."""
    raw = _col(df, "KETERANGAN")
    if raw is None:
        return None
    return raw.fillna("").astype(str)


def _empty_frame(columns: dict) -> pd.DataFrame:
    """Frame kosong dengan kolom + dtype persis seperti hasil normal."""
    return pd.DataFrame(columns)


def _norm_unit(value: object) -> str:
    """Normalisasi SATUAN: buang NBSP ('\\xa0') + zero-width ('\\u200b'), strip.

    NaN atau kosong setelah normalisasi -> '(kosong)'.
    """
    if pd.isna(value):
        return _SATUAN_EMPTY
    text = str(value).replace("\xa0", "").replace("\u200b", "").strip()
    return text if text else _SATUAN_EMPTY


# ============================================================
# AGREGAT PER HARI
# ============================================================

def waste_per_day(df: pd.DataFrame, key_akhir: int | None = None) -> pd.DataFrame:
    """Agregat waste per hari.

    Args:
        df: DataFrame dengan kolom hari '1'..'31' (nilai numerik, NaN = kosong).
        key_akhir: batas hari — hanya hari 1..N yang diproses. None -> pakai
            hari maksimum yang kolomnya ada.

    Returns:
        DataFrame kolom 'day' (int), 'total' (float), 'active_rows' (int),
        'mean_per_active' (float):
        total = jumlah kolom hari (NaN dihitung 0); active_rows = baris
        bernilai > 0; mean_per_active = total / active_rows (0 bila 0 aktif).
    """
    days = _day_range(df, key_akhir)
    if not _frame_ok(df) or not days:
        return _empty_frame({
            "day": np.array([], dtype=np.int64),
            "total": np.array([], dtype=np.float64),
            "active_rows": np.array([], dtype=np.int64),
            "mean_per_active": np.array([], dtype=np.float64),
        })
    rows = []
    for day in days:
        vals = _day_series(df, str(day))
        total = float(vals.fillna(0.0).sum())
        active = int((vals > 0).sum())
        mean = total / active if active > 0 else 0.0
        rows.append(
            {"day": day, "total": total, "active_rows": active, "mean_per_active": mean}
        )
    return pd.DataFrame(
        rows, columns=["day", "total", "active_rows", "mean_per_active"]
    )


# ============================================================
# POLA WEEKDAY (day % 7)
# ============================================================

def weekday_pattern(df: pd.DataFrame, key_akhir: int | None = None) -> pd.DataFrame:
    """Pola per kelas hari-minggu (day % 7).

    Args:
        df: DataFrame dengan kolom hari '1'..'31'.
        key_akhir: batas hari (lihat waste_per_day).

    Returns:
        DataFrame kolom 'mod_class' (int 0..6), 'days' (str, mis. '5, 12, 19,
        26'), 'total' (float), 'active_rows' (int), 'mean_per_active' (float),
        'ratio_vs_mean' (float). Hanya kelas yang punya >= 1 hari dalam
        rentang data (kelas tanpa hari TIDAK jadi baris). ratio_vs_mean =
        mean_per_active / (total semua hari / active semua hari); 0 bila
        penyebut 0. Sort mod_class naik.
    """
    per_day = waste_per_day(df, key_akhir)
    if per_day.empty:
        return _empty_frame({
            "mod_class": np.array([], dtype=np.int64),
            "days": np.array([], dtype=object),
            "total": np.array([], dtype=np.float64),
            "active_rows": np.array([], dtype=np.int64),
            "mean_per_active": np.array([], dtype=np.float64),
            "ratio_vs_mean": np.array([], dtype=np.float64),
        })
    total_all = float(per_day["total"].sum())
    active_all = int(per_day["active_rows"].sum())
    overall = total_all / active_all if active_all > 0 else 0.0
    mod = per_day["day"].to_numpy() % 7
    rows = []
    for mod_class in range(7):
        chunk = per_day[mod == mod_class]
        if chunk.empty:
            continue
        total = float(chunk["total"].sum())
        active = int(chunk["active_rows"].sum())
        mean = total / active if active > 0 else 0.0
        ratio = mean / overall if overall > 0 else 0.0
        day_list = sorted(int(d) for d in chunk["day"])
        rows.append({
            "mod_class": mod_class,
            "days": ", ".join(str(d) for d in day_list),
            "total": total,
            "active_rows": active,
            "mean_per_active": mean,
            "ratio_vs_mean": ratio,
        })
    return pd.DataFrame(
        rows,
        columns=[
            "mod_class", "days", "total", "active_rows", "mean_per_active",
            "ratio_vs_mean",
        ],
    )


def weekday_effect(df: pd.DataFrame, key_akhir: int | None = None) -> dict:
    """Ringkasan efek hari: pasangan kelas mod BERDAMPINGAN (siklik 6-0-1-2-...)
    dengan rata-rata mean_per_active tertinggi.

    Args:
        df: DataFrame dengan kolom hari '1'..'31'.
        key_akhir: batas hari (lihat waste_per_day).

    Returns:
        dict {'peak_classes': tuple[int, int] | None, 'peak_mean': float,
        'offpeak_mean': float, 'ratio': float | None}:
        peak_mean = rata-rata mean_per_active dua kelas peak; offpeak_mean =
        rata-rata kelas lain (0 bila tidak ada kelas lain); ratio =
        peak_mean/offpeak_mean (None bila offpeak_mean 0). peak_classes None
        bila < 2 kelas ada atau kelas yang ada tidak berdampingan.
    """
    result: dict = {
        "peak_classes": None,
        "peak_mean": 0.0,
        "offpeak_mean": 0.0,
        "ratio": None,
    }
    pattern = weekday_pattern(df, key_akhir)
    if pattern.empty:
        return result
    means = {
        int(row.mod_class): float(row.mean_per_active)
        for row in pattern.itertuples(index=False)
    }
    best: tuple[int, int] | None = None
    best_avg = float("-inf")
    for first in range(7):
        second = (first + 1) % 7
        if first in means and second in means:
            avg = (means[first] + means[second]) / 2.0
            if avg > best_avg:
                best_avg = avg
                best = (first, second)
    if best is None:
        return result
    others = [mean for mod_class, mean in means.items() if mod_class not in best]
    offpeak = sum(others) / len(others) if others else 0.0
    result["peak_classes"] = best
    result["peak_mean"] = best_avg
    result["offpeak_mean"] = offpeak
    result["ratio"] = best_avg / offpeak if offpeak > 0 else None
    return result


# ============================================================
# MATRIX KETERANGAN x HARI (HEATMAP)
# ============================================================

def reason_by_day(
    df: pd.DataFrame,
    key_akhir: int | None = None,
    top_n: int = 9,
) -> pd.DataFrame:
    """Matrix KETERANGAN x hari untuk heatmap.

    Args:
        df: DataFrame dengan kolom 'KETERANGAN' + kolom hari '1'..'31'.
        key_akhir: batas hari (lihat waste_per_day). Kolom hari hanya dibuat
            untuk hari yang kolomnya ada (hari tanpa kolom tidak dibuat nol).
        top_n: jumlah baris KETERANGAN teratas berdasarkan total waste.

    Returns:
        DataFrame kolom 'KETERANGAN' (kolom pertama, BUKAN index) + kolom
        hari 1..N (HEADER INT, bukan str) + 'Total'. Baris = top_n KETERANGAN
        by total waste + 1 baris 'Lainnya' (jumlah sisanya) bila ada sisa.
        Nilai = sum kolom hari per KETERANGAN (NaN -> 0). Sort Total desc,
        'Lainnya' selalu terakhir. KETERANGAN NaN diperlakukan sebagai ''.
    """
    days = _day_range(df, key_akhir)
    if not _frame_ok(df) or "KETERANGAN" not in df.columns or not days:
        columns: dict = {"KETERANGAN": np.array([], dtype=object)}
        for day in days:
            columns[day] = np.array([], dtype=np.float64)
        columns["Total"] = np.array([], dtype=np.float64)
        return _empty_frame(columns)
    ket = _ket_series(df)
    day_data = {day: _day_series(df, str(day)).to_numpy() for day in days}
    mat = pd.DataFrame(day_data)
    mat.insert(0, "KETERANGAN", ket.to_numpy())
    agg = mat.groupby("KETERANGAN", sort=True).sum()
    agg["Total"] = agg.sum(axis=1)
    agg = agg.sort_values("Total", ascending=False, kind="stable")
    try:
        keep = max(int(top_n), 0)
    except (TypeError, ValueError):
        keep = 9
    top = agg.head(keep)
    rest = agg.iloc[keep:]
    out = top.reset_index()
    if not rest.empty:
        sums = rest.sum(axis=0)
        row: dict = {"KETERANGAN": _LAINNYA}
        for day in days:
            row[day] = float(sums.get(day, 0.0))
        row["Total"] = float(sums.get("Total", 0.0))
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
    return out.reset_index(drop=True)


# ============================================================
# EFEK PEAK-DAY PER KETERANGAN
# ============================================================

def reason_weekday_ratio(
    df: pd.DataFrame,
    key_akhir: int | None = None,
    peak_classes: tuple[int, int] | None = None,
) -> pd.DataFrame:
    """Efek peak-day per KETERANGAN.

    Args:
        df: DataFrame dengan kolom 'KETERANGAN' + kolom hari '1'..'31'.
        key_akhir: batas hari (lihat waste_per_day).
        peak_classes: pasangan kelas mod peak. None -> auto-detect dari
            weekday_effect() (bila gagal, semua hari dianggap offpeak).

    Returns:
        DataFrame kolom 'KETERANGAN', 'peak_mean' (float), 'offpeak_mean'
        (float), 'ratio' (float), 'total' (float). peak_mean = mean nilai
        per baris aktif (nilai > 0) di hari-hari kelas peak; offpeak_mean
        idem untuk hari lain (0 bila tidak ada nilai aktif). ratio =
        peak_mean/offpeak_mean (NaN bila offpeak 0). total = jumlah waste
        semua hari dalam rentang. Sort ratio desc (NaN paling akhir).
    """
    days = _day_range(df, key_akhir)
    if not _frame_ok(df) or "KETERANGAN" not in df.columns or not days:
        return _empty_frame({
            "KETERANGAN": np.array([], dtype=object),
            "peak_mean": np.array([], dtype=np.float64),
            "offpeak_mean": np.array([], dtype=np.float64),
            "ratio": np.array([], dtype=np.float64),
            "total": np.array([], dtype=np.float64),
        })
    if peak_classes is None:
        peak_classes = weekday_effect(df, key_akhir).get("peak_classes")
    peak_set: set[int] = set()
    if peak_classes is not None:
        try:
            peak_set = {int(c) for c in peak_classes}
        except (TypeError, ValueError):
            peak_set = set()
    ket = _ket_series(df)
    frames = [
        pd.DataFrame({
            "KETERANGAN": ket.to_numpy(),
            "day": day,
            "val": _day_series(df, str(day)).to_numpy(),
        })
        for day in days
    ]
    long = pd.concat(frames, ignore_index=True)
    totals = long.groupby("KETERANGAN", sort=True)["val"].sum()
    active = long[long["val"] > 0].copy()
    active["is_peak"] = np.isin(active["day"].to_numpy() % 7, sorted(peak_set))
    means = active.groupby(["KETERANGAN", "is_peak"], sort=True)["val"].mean()
    means = means.unstack("is_peak")
    idx = totals.index
    peak_mean = (
        means[True].reindex(idx).fillna(0.0).to_numpy(dtype=float)
        if True in means.columns
        else np.zeros(len(idx))
    )
    offpeak_mean = (
        means[False].reindex(idx).fillna(0.0).to_numpy(dtype=float)
        if False in means.columns
        else np.zeros(len(idx))
    )
    out = pd.DataFrame({
        "KETERANGAN": idx.to_numpy(),
        "peak_mean": peak_mean,
        "offpeak_mean": offpeak_mean,
    })
    denom = out["offpeak_mean"].where(out["offpeak_mean"] > 0)
    out["ratio"] = out["peak_mean"] / denom
    out["total"] = totals.to_numpy(dtype=float)
    out = out.sort_values(
        "ratio", ascending=False, na_position="last", kind="stable"
    )
    return out.reset_index(drop=True)


# ============================================================
# BREAKDOWN PER SATUAN
# ============================================================

def unit_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Breakdown per SATUAN (dinormalisasi: ganti '\\xa0' dan '\\u200b' dengan
    '', lalu strip; nilai kosong setelah normalisasi -> '(kosong)').

    Args:
        df: DataFrame dengan kolom 'SATUAN' + 'TOTAL' (wajib — salah satu
            hilang -> frame kosong) dan 'NAMA BARANG' (opsional; items = 0
            bila kolom hilang).

    Returns:
        DataFrame kolom 'SATUAN' (normalized), 'rows' (int), 'active_rows'
        (int, TOTAL > 0), 'items' (int, NAMA BARANG unik), 'total' (float),
        'share_pct' (float, total/total semua satuan x 100; 0 bila total 0),
        'raw_values' (str '; '.join nilai asli unik). Sort total desc.
    """
    satuan_col = _col(df, "SATUAN")
    total_col = _col(df, "TOTAL")
    if not _frame_ok(df) or satuan_col is None or total_col is None:
        return _empty_frame({
            "SATUAN": np.array([], dtype=object),
            "rows": np.array([], dtype=np.int64),
            "active_rows": np.array([], dtype=np.int64),
            "items": np.array([], dtype=np.int64),
            "total": np.array([], dtype=np.float64),
            "share_pct": np.array([], dtype=np.float64),
            "raw_values": np.array([], dtype=object),
        })
    raw = satuan_col.to_numpy()
    norm = pd.Series(raw).map(_norm_unit).to_numpy()
    total = pd.to_numeric(total_col, errors="coerce").fillna(0.0).to_numpy()
    item_col = _col(df, "NAMA BARANG")
    items = (
        item_col.to_numpy()
        if item_col is not None
        else np.full(len(df), None, dtype=object)
    )
    work = pd.DataFrame({
        "SATUAN": norm,
        "raw": raw,
        "item": items,
        "total": total,
        "active": total > 0,
    })
    grand = float(work["total"].sum())
    rows = []
    for name, group in work.groupby("SATUAN", sort=True):
        group_total = float(group["total"].sum())
        raw_unique = [str(v) for v in pd.unique(group["raw"]) if not pd.isna(v)]
        rows.append({
            "SATUAN": name,
            "rows": len(group),
            "active_rows": int(group["active"].sum()),
            "items": int(group["item"].nunique()),
            "total": group_total,
            "share_pct": group_total / grand * 100.0 if grand != 0 else 0.0,
            "raw_values": "; ".join(raw_unique),
        })
    out = pd.DataFrame(
        rows,
        columns=[
            "SATUAN", "rows", "active_rows", "items", "total", "share_pct",
            "raw_values",
        ],
    )
    return out.sort_values("total", ascending=False, kind="stable").reset_index(
        drop=True
    )
