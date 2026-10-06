"""profile.py — profil baris (pola waktu) + kelebihan vs tipikal (v2.13.0).

Riset (Task R1, data asli 25.901 baris) menemukan tensi sentral: top-20
baris waste terbesar SEMUA kronis (17-30 hari aktif) dengan skor anomali
0-6 — sinyal S1..S12 menangkap LONJAKAN sesaat, sedangkan mayoritas nilai
waste ada di baris stabil tiap hari. Tab anomali belum menjawab pertanyaan
audit pertama: "ini salah input / kecurigaan, atau memang bocor setiap
hari?" Modul ini menambah dua lensa baris (murni ADDITIF — kolom baru,
tidak mengubah kolom/nilai yang ada, golden count tak bergeser):

- PROFIL (Stage 15b)     : klasifikasi pola waktu baris, istilah awam:
    "Tiap Hari"   — Count Hari >= PROFIL_DAILY_MIN (default 20) — bocor
                    hampir setiap hari (masalah proses/kronis).
    "Kadang"      — 2 .. (min-1) hari aktif.
    "Sekali Ini"  — tepat 1 hari (episodik — kandidat salah input /
                    kejadian tunggal; sepupu sinyal S10).
    "—"           — TOTAL 0/kosong (baris placeholder) atau data hari
                    tidak bisa dihitung.
  "— Baru" (suffix, view) : pasangan cabang×item tidak ada / nol di bulan
    pembanding (muncul sebagai pilihan pembanding terisi — baca kolom
    BULAN LALU hasil change_vs_history). Tanpa pembanding: tak ada suffix.

- KELEBIHAN (Stage 15b)  : TOTAL bulanan − tipikal (median) cabang lain
  pada item SEJENIS sama (grup peer = NAMA BARANG + JENIS + KETERANGAN +
  SOURCE DATA — sama dengan stage 6). Median dihitung HANYA dari peer
  aktif (TOTAL > 0) — pelajaran benchmark v2.5.0: median campur baris nol
  (90,6% data) mematikan perbandingan justru untuk event langka. Baris
  valid bila peer aktif >= TH_PEER_MIN (default 3) — di bawah itu sample
  terlalu kecil → kosong. Nilai NEGATIF = lebih hemat dari tipikal
  (jujur ditampilkan apa adanya). Hanya dihitung untuk baris TOTAL > 0.
  Kolom pendamping PEER MEDIAN (AKTIF) + PEER AKTIF (jumlah) untuk
  transparansi di pop-up detail.

Semua fungsi DEFENSIF: kolom hilang / df kosong → kolom keluaran tetap
dibuat dengan nilai kosong ("—" / NaN), tidak pernah raise. Perhitungan
vektor (numpy where + groupby transform) — 25,9 ribu baris ≈ puluhan ms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Konstanta kontrak (dibaca UI/tooltip — JANGAN diubah sembarangan).
PROFIL_COL = "PROFIL"
KELEBIHAN_COL = "KELEBIHAN"
PEER_MEDIAN_AKTIF_COL = "PEER MEDIAN (AKTIF)"
PEER_AKTIF_COL = "PEER AKTIF"

# Nilai PROFIL kanonik (domain — funnel filter menampilkan nilai ini).
PROFIL_TIAP_HARI = "Tiap Hari"
PROFIL_KADANG = "Kadang"
PROFIL_SEKALI_INI = "Sekali Ini"
PROFIL_KOSONG = "—"

# Suffix pembanding (annotate_profile_vs_history).
PROFIL_BARU_SUFFIX = " — Baru"

# Default pola: sama kunci grup peer stage 6 (grup perbandingan konsisten).
_PEER_KEYS = ("NAMA BARANG", "JENIS", "KETERANGAN", "SOURCE DATA")
# Nama publik (dipakai insights.money_ranking — grup persentil peer sama).
PEER_KEYS = _PEER_KEYS

# Kolom output yang SELALU dibuat modul ini.
PROFILE_COLS = [
    PROFIL_COL, KELEBIHAN_COL, PEER_MEDIAN_AKTIF_COL, PEER_AKTIF_COL,
]


def _count_hari(df: pd.DataFrame, key_akhir: int) -> pd.Series:
    """Jumlah hari aktif (>0) per baris — dari kolom Count Hari bila ada,
    dihitung ulang dari kolom hari '1'..'31' bila kolom itu hilang."""
    if "Count Hari" in df.columns:
        return pd.to_numeric(df["Count Hari"], errors="coerce").fillna(0)
    day_cols = [str(d) for d in range(1, int(key_akhir) + 1)
                if str(d) in df.columns]
    if not day_cols:
        return pd.Series(0.0, index=df.index)
    num = df[day_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return (num > 0).sum(axis=1)


def annotate_profile(
    df: pd.DataFrame,
    key_akhir: int,
    config: dict,
) -> pd.DataFrame:
    """Tambah PROFIL + KELEBIHAN + kolom peer-aktif (additive, vektor).

    Args:
        df: DataFrame detail hasil pipeline (minimal TOTAL; Count Hari dan
            kolom kunci peer opsional — hilang → nilai kosong).
        key_akhir: hari terakhir periode (fallback hitung hari aktif).
        config: dict config — ambil ``thresholds.PROFIL_DAILY_MIN`` (default
            20) dan ``TH_PEER_MIN`` (default 3).

    Returns:
        DataFrame dengan 4 kolom tambahan (lihat modul docstring).
        Tidak pernah raise; df kosong → kolom tetap terbuat.
    """
    out = df.copy()
    n = len(out)
    th = dict(config.get("thresholds") or {})
    try:
        daily_min = int(th.get("PROFIL_DAILY_MIN", 20))
    except (TypeError, ValueError):
        daily_min = 20
    daily_min = max(daily_min, 2)
    try:
        peer_min = int(th.get("TH_PEER_MIN", 3))
    except (TypeError, ValueError):
        peer_min = 3

    # ---- PROFIL: klasifikasi pola waktu (istilah awam) ----------------
    out[PROFIL_COL] = PROFIL_KOSONG
    if n:
        total = pd.to_numeric(out.get("TOTAL"), errors="coerce") \
            if "TOTAL" in out.columns else pd.Series(np.nan, index=out.index)
        nday = _count_hari(out, key_akhir)
        aktif = total.notna() & (total > 0)
        profil = pd.Series(PROFIL_KOSONG, index=out.index, dtype=object)
        profil[np.asarray(aktif) & np.asarray(nday >= daily_min)] = \
            PROFIL_TIAP_HARI
        mid = np.asarray(aktif) & np.asarray(nday >= 2) & np.asarray(
            nday < daily_min)
        profil[mid] = PROFIL_KADANG
        once = np.asarray(aktif) & np.asarray(nday == 1)
        profil[once] = PROFIL_SEKALI_INI
        out[PROFIL_COL] = profil

    # ---- KELEBIHAN vs tipikal cabang lain (peer AKTIF) ----------------
    out[KELEBIHAN_COL] = np.nan
    out[PEER_MEDIAN_AKTIF_COL] = np.nan
    out[PEER_AKTIF_COL] = 0
    if n and "TOTAL" in out.columns and all(k in out.columns for k in _PEER_KEYS):
        total = pd.to_numeric(out["TOTAL"], errors="coerce")
        aktif = total.notna() & (total > 0)
        if bool(aktif.any()):
            keys = [out[k].astype(str) for k in _PEER_KEYS]
            work = pd.DataFrame({k.name: k.to_numpy() for k in keys})
            work["_total"] = total.to_numpy()
            grp = work[aktif.to_numpy()].groupby(
                list(work.columns[:-1]), sort=False, dropna=False)["_total"]
            med = grp.transform("median")
            cnt = grp.transform("size")
            # align: hitung pada subset aktif → hasil punya index subset
            med_full = pd.Series(np.nan, index=out.index)
            cnt_full = pd.Series(0, index=out.index, dtype=float)
            idx = np.flatnonzero(aktif.to_numpy())
            med_full.iloc[idx] = med.to_numpy()
            cnt_full.iloc[idx] = cnt.to_numpy()
            ok = (cnt_full >= peer_min) & (med_full > 0)
            kelebihan = pd.Series(np.nan, index=out.index)
            sel = np.asarray(aktif) & np.asarray(ok)
            kelebihan[sel] = total[sel] - med_full[sel]
            out[KELEBIHAN_COL] = kelebihan
            out[PEER_MEDIAN_AKTIF_COL] = med_full.where(
                np.asarray(aktif) & np.asarray(med_full.notna()))
            out[PEER_AKTIF_COL] = cnt_full.astype(int)
    return out


def annotate_profile_vs_history(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah suffix "— Baru" pada PROFIL untuk baris yang TIDAK ada /
    nol di bulan pembanding (butuh kolom BULAN LALU hasil
    change_vs_history; tanpa kolom itu → df dikembalikan apa adanya).

    Idempoten: baris yang sudah ber-suffix tidak di-suffix dua kali.
    """
    if (df is None or df.empty or PROFIL_COL not in df.columns
            or "BULAN LALU" not in df.columns):
        return df
    out = df.copy()
    bulan_lalu = pd.to_numeric(out["BULAN LALU"], errors="coerce")
    baru = ~bulan_lalu.notna().to_numpy() | (bulan_lalu.fillna(0).to_numpy() <= 0)
    profil = out[PROFIL_COL].astype(str)
    sudah = profil.str.endswith(PROFIL_BARU_SUFFIX).to_numpy()
    profil_new = np.where(
        baru & ~sudah & (profil != PROFIL_KOSONG).to_numpy(),
        profil + PROFIL_BARU_SUFFIX, profil)
    out[PROFIL_COL] = profil_new
    return out
