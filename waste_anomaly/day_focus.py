"""
day_focus.py — bukti hari-mencurigakan (v2.9.0, Stage 15).

Melanjutkan pembuktian read-only v2.8.3 (skrip analisa data asli): 74,1%
anomali DAPAT dilokalisasi ke hari tertentu (1-31). Modul ini mengubah
bukti itu menjadi kolom pipeline permanen:

- HARI TERSANGKA        : nomor hari (1-31) nilai terbesar baris (= HARI MAX).
- NILAI HARI TERSANGKA  : nilai waste pada hari itu.
- TIPIKAL CABANG LAIN   : median nilai item SAMA di hari SAMA pada outlet lain
                          yang aktif (> 0) — pembanding lintas-cabang PER HARI.
- N CABANG PEMBANDING   : banyaknya outlet pembanding pada hari itu.
- RASIO VS CABANG LAIN  : NILAI ÷ TIPIKAL — berapa kali lipat vs cabang lain.
- SHARE HARI TERSANGKA  : porsi nilai hari itu dari TOTAL bulanan.
- BUKTI HARI            : YES bila ada >= 1 bukti kuat:
                          rasio >= TH_HARI_PEER_RATIO (default 5x)
                          ATAU share >= TH_MAX_SHARE_WARN (50%)
                          ATAU pola 10x (SCALE SIGNAL)
                          ATAU waste hanya 1 hari (SINGLE DAY).
- ALASAN HARI           : kalimat ringkas siap-baca, mis.
                          "Hari 24: nilai 808 — 404x cabang lain (tipikal 2);
                           91% dari total bulanan".

Dihitung HANYA untuk baris anomali (ANOMALY STATUS != Normal) yang punya
HARI MAX — baris lain diberi nilai kosong (BUKTI HARI = "NO"). Perhitungan
vektor (stack + merge + groupby), dijalankan di worker thread pipeline —
tidak menambah beban thread UI.

Contoh dramatis dari data asli (pembuktian v2.8.3):
  MIE (V.20) 1042.KWGGAL hari-24 = 808 vs tipikal cabang lain 2,0 (404x);
  KRUPUK MIE (V.40) 1137.CKGPAH hari-26 = 2.400 vs 14 (171x, share 100%).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import day_columns

# Kolom output yang SELALU dibuat (nilai kosong bila tak bisa dihitung).
DAY_FOCUS_COLS = [
    "HARI TERSANGKA", "NILAI HARI TERSANGKA", "TIPIKAL CABANG LAIN",
    "N CABANG PEMBANDING", "RASIO VS CABANG LAIN", "SHARE HARI TERSANGKA",
    "BUKTI HARI", "ALASAN HARI",
]


def _fmt_num(v: float, ndigits: int = 0) -> str:
    """Format angka gaya Indonesia (pemisah ribuan '.')."""
    s = f"{v:,.{ndigits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_ratio(r: float) -> str:
    """404.0 -> '404x'; 8.5 -> '8,5x'."""
    if r >= 10:
        return f"{r:,.0f}x".replace(",", ".")
    return f"{r:,.1f}".replace(".", ",") + "x"


def annotate_day_evidence(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Tambah 8 kolom bukti-hari (lihat docstring modul).

    Murni additive: tidak mengubah kolom/nilai yang sudah ada — golden
    counts pipeline tidak berubah. Baris Normal diberi kolom kosong.
    """
    out = df.reset_index(drop=True)  # copy + index posisi 0..n-1
    n = len(out)

    # Kolom output default kosong (aman utk df tanpa hari/identitas)
    out["HARI TERSANGKA"] = np.nan
    out["NILAI HARI TERSANGKA"] = np.nan
    out["TIPIKAL CABANG LAIN"] = np.nan
    out["N CABANG PEMBANDING"] = 0
    out["RASIO VS CABANG LAIN"] = np.nan
    out["SHARE HARI TERSANGKA"] = np.nan
    out["BUKTI HARI"] = "NO"
    out["ALASAN HARI"] = ""
    if n == 0:
        return out

    th = dict((config.get("thresholds") or {}))
    th_ratio = float(th.get("TH_HARI_PEER_RATIO", 5.0))
    th_share = float(th.get("TH_MAX_SHARE_WARN", 0.50))

    day_cols = [c for c in day_columns(key_akhir) if c in out.columns]
    if (not day_cols or "NAMA BARANG" not in out.columns
            or "ANOMALY STATUS" not in out.columns
            or "HARI MAX" not in out.columns):
        return out

    # ---- [1] kandidat: baris anomali dengan HARI MAX valid ----------------
    status = out["ANOMALY STATUS"].astype(str)
    anom_mask = (status != "Normal").to_numpy()
    hari_max = pd.to_numeric(out["HARI MAX"], errors="coerce")
    valid = anom_mask & hari_max.notna().to_numpy()
    cand_idx = np.flatnonzero(valid)
    if len(cand_idx) == 0:
        return out

    item_key = out["NAMA BARANG"].astype(str)
    resto_key = (out["NAMA RESTO"].astype(str)
                 if "NAMA RESTO" in out.columns
                 else pd.Series([""] * n))

    day_num = hari_max.to_numpy()[cand_idx].astype(int)
    # pastikan hari tersangka masih dalam lingkup kolom hari yang dipakai
    in_scope = np.array([str(d) in day_cols for d in day_num])
    cand_idx = cand_idx[in_scope]
    day_num = day_num[in_scope]
    if len(cand_idx) == 0:
        return out

    # ---- [2] NILAI hari tersangka + SHARE (dari matriks hari kandidat) ----
    cand_days = out.iloc[cand_idx][day_cols].apply(
        pd.to_numeric, errors="coerce")
    day_pos = np.array([day_cols.index(str(d)) for d in day_num])
    nilai = cand_days.to_numpy()[np.arange(len(cand_idx)), day_pos]
    total = pd.to_numeric(out["TOTAL"], errors="coerce").to_numpy()
    share = np.where(
        (nilai > 0) & (total[cand_idx] > 0),
        nilai / np.where(total[cand_idx] > 0, total[cand_idx], 1), np.nan,
    )
    out.iloc[cand_idx, out.columns.get_loc("HARI TERSANGKA")] = day_num
    out.iloc[cand_idx, out.columns.get_loc("NILAI HARI TERSANGKA")] = nilai
    out.iloc[cand_idx, out.columns.get_loc("SHARE HARI TERSANGKA")] = share

    # ---- [3] peer per (item x hari): median + banyak outlet lain ----------
    # Tabel panjang nilai aktif (>0) hanya untuk baris item relevan —
    # ukurannya kecil (baris item anomali x hari aktif).
    items_needed = set(item_key.to_numpy()[cand_idx])
    rel_rows = np.flatnonzero(item_key.isin(items_needed).to_numpy())
    day_vals = out.iloc[rel_rows][day_cols].apply(
        pd.to_numeric, errors="coerce")
    day_vals.index = rel_rows          # label = posisi df penuh
    day_vals.columns.name = "_day"
    active = day_vals.stack()          # (row, day) -> nilai, NaN ter-drop
    if len(active):
        active = active[active > 0]
    if len(active) == 0:
        _finalize_reasons(out, cand_idx, th_ratio, th_share)
        return out

    long_df = active.reset_index()
    long_df.columns = ["_row", "_day", "_val"]
    long_df["_item"] = item_key.to_numpy()[long_df["_row"].to_numpy()]
    long_df["_resto"] = resto_key.to_numpy()[long_df["_row"].to_numpy()]

    cand = pd.DataFrame({
        "_row": cand_idx,
        "_item": item_key.to_numpy()[cand_idx],
        "_resto": resto_key.to_numpy()[cand_idx],
        "_day": [str(d) for d in day_num],
    })
    m = cand.merge(long_df, on=["_item", "_day"], how="left")
    m = m[m["_resto_x"] != m["_resto_y"]]  # outlet sendiri dikeluarkan
    if len(m):
        stats = m.groupby("_row_x").agg(
            _tip=("_val", "median"), _n=("_resto_y", "nunique"))
        pos = stats.index.to_numpy()
        tipikal = np.full(n, np.nan)
        tipikal[pos] = stats["_tip"].to_numpy()
        npeer = np.zeros(n, dtype=int)
        npeer[pos] = stats["_n"].to_numpy().astype(int)
        ratio = np.where(
            (tipikal[cand_idx] > 0) & (nilai > 0),
            nilai / np.where(tipikal[cand_idx] > 0, tipikal[cand_idx], 1),
            np.nan,
        )
    else:
        tipikal = np.full(n, np.nan)
        npeer = np.zeros(n, dtype=int)
        ratio = np.full(len(cand_idx), np.nan)
    out.iloc[cand_idx, out.columns.get_loc("TIPIKAL CABANG LAIN")] = \
        tipikal[cand_idx]
    out.iloc[cand_idx, out.columns.get_loc("N CABANG PEMBANDING")] = \
        npeer[cand_idx]
    out.iloc[cand_idx, out.columns.get_loc("RASIO VS CABANG LAIN")] = ratio

    _finalize_reasons(out, cand_idx, th_ratio, th_share)
    return out


def _finalize_reasons(
    out: pd.DataFrame,
    cand_idx: np.ndarray,
    th_ratio: float,
    th_share: float,
) -> None:
    """BUKTI HARI (YES/NO) + ALASAN HARI (kalimat ringkas) utk kandidat.

    Komponen bukti (masukkan ke alasan hanya bila terpicu):
    (a) rasio vs cabang lain >= th_ratio;
    (b) share hari >= th_share;
    (c) SCALE SIGNAL = YES (pola 10x — salah ketik);
    (d) SINGLE DAY = YES (waste cuma 1 hari).
    """
    n = len(out)
    scale_yes = (out["SCALE SIGNAL"].astype(str) == "YES").to_numpy() \
        if "SCALE SIGNAL" in out.columns else np.zeros(n, bool)
    single_yes = (out["SINGLE DAY"].astype(str) == "YES").to_numpy() \
        if "SINGLE DAY" in out.columns else np.zeros(n, bool)
    ratio = pd.to_numeric(out["RASIO VS CABANG LAIN"],
                          errors="coerce").to_numpy()
    share = pd.to_numeric(out["SHARE HARI TERSANGKA"],
                          errors="coerce").to_numpy()
    npeer = pd.to_numeric(out["N CABANG PEMBANDING"],
                          errors="coerce").fillna(0).to_numpy().astype(int)
    nilai = pd.to_numeric(out["NILAI HARI TERSANGKA"],
                          errors="coerce").to_numpy()
    hari = pd.to_numeric(out["HARI TERSANGKA"], errors="coerce").to_numpy()

    bukti = (ratio >= th_ratio) | (share >= th_share) | scale_yes | single_yes
    alasan: list[str] = [""] * n
    for p in cand_idx:
        if not bukti[p]:
            continue
        parts: list[str] = []
        if ratio[p] == ratio[p] and ratio[p] >= th_ratio and npeer[p] > 0:
            tip = pd.to_numeric(out.at[p, "TIPIKAL CABANG LAIN"],
                                errors="coerce")
            tip_s = _fmt_num(float(tip), 1) if tip == tip else "—"
            parts.append(f"{_fmt_ratio(float(ratio[p]))} cabang lain "
                         f"(tipikal {tip_s})")
        if share[p] == share[p] and share[p] >= th_share:
            parts.append(f"{share[p] * 100:.0f}% dari total bulanan")
        if scale_yes[p]:
            parts.append("pola 10x — mungkin salah ketik")
        if single_yes[p]:
            parts.append("waste hanya terjadi hari itu")
        val_s = _fmt_num(float(nilai[p])) if nilai[p] == nilai[p] else "—"
        alasan[p] = (f"Hari {int(hari[p])}: nilai {val_s}"
                     + (" — " + "; ".join(parts) if parts else ""))
    bukti_full = np.zeros(n, bool)
    bukti_full[cand_idx] = bukti[cand_idx]
    out["BUKTI HARI"] = np.where(bukti_full, "YES", "NO")
    out["ALASAN HARI"] = alasan
