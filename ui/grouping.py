"""grouping.py — agregasi tampilan tab Anomali per item×cabang (v2.19.0).

Redesain tampilan tab Anomali atas permintaan user ("redesain tampilan
tab anomali seperti tampilan di file SAMPEL TAMPILAN BARU.xlsx"): tabel
kini SATU BARIS per pasangan (JENIS × NAMA BARANG × NAMA RESTO) — dulu
satu baris per kombinasi (JENIS × BARANG × RESTO × KETERANGAN × SOURCE
DATA) sehingga item yang sama terpecah banyak baris.

Sampel user (11 kolom, urutan persis):
    JENIS · NAMA BARANG · NAMA RESTO · SOURCE DATA GABUNGAN · [TOTAL] ·
    [% to BOM] · TOTAL BULAN LALU & % Selisih · Selisih Bulan Lalu ·
    PERUBAHAN · ANOMALY STATUS · PROFIL

Agregasi murni di LAPISAN TAMPILAN (view) — pipeline/skor/sinyal tetap
dihitung per baris detail seperti sebelumnya (kontrak export & test
golden tak tersentuh). Fungsi ini DEFENSIF: kolom hilang → kolom keluaran
kosong, tidak pernah raise.

Aturan agregasi per grup (penjelasan lengkap tiap kolom di kolom komentar
fungsi group_anomali_display): SUM utk TOTAL/hari/BULAN LALU, join unik
utk SOURCE DATA/KETERANGAN/ANOMALY REASONS, MAX utk skor, status paling
parah, baris representatif (skor tertinggi) utk kolom peer, statistik
hari dihitung ulang dari matriks terjumlah, PROFIL dari hari aktif.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from waste_anomaly.period_history import classify_change
from waste_anomaly.profile import (
    PROFIL_BARU_SUFFIX,
    PROFIL_KADANG,
    PROFIL_KOSONG,
    PROFIL_SEKALI_INI,
    PROFIL_TIAP_HARI,
)

# Default ambang PROFIL 'Tiap Hari' (nilai yang sama dengan
# waste_anomaly/profile.py — konstanta tak diekspor di sana).
_DEFAULT_PROFIL_DAILY_MIN = 20

# Kunci grup tampilan (urutan kolom identitas sampel user).
GROUP_KEYS = ["JENIS", "NAMA BARANG", "NAMA RESTO"]

# Nama kolom keluaran khusus tampilan grup (kontrak view/model/test).
SRC_GAB_COL = "SOURCE DATA GABUNGAN"
LASTMONTH_COMBINED_COL = "TOTAL BULAN LALU & % Selisih"
SELISIH_COL = "Selisih Bulan Lalu"
FPS_COL = "__FPS"

# Urutan status dari paling ringan → paling parah (worst-of-group).
_STATUS_RANK = {"Normal": 0, "Perlu Review": 1, "Potensi Anomali": 2,
                "Prioritas Tinggi": 3}
_STATUS_NAME = {v: k for k, v in _STATUS_RANK.items()}

# Kolom metrik yang diambil dari baris representatif (anggota ber-skor
# tertinggi) — grup peer per KETERANGAN memang beda antar anggota, satu
# angka wajib dipilih utk pop-up detail; pilihan paling relevan utk
# investigasi = anggota terburuk grup.
_REP_COLS = [
    "SATUAN", "TOTAL BOM",
    "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
    "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX",
    "MAX / BOM", "TOTAL / BOM",
    "KELEBIHAN", "PEER MEDIAN (AKTIF)", "PEER AKTIF",
    "KATEGORI ANOMALI", "RANGKING WASTE",
    # v2.19.0 — rasio hari (fallback bila df TAK punya kolom hari 1..31
    # sehingga section-5 tak menjalankan kalkulasi segar dari matriks
    # terjumlah; fixture test sintetis & data tanpa sheet hari). Bila
    # hari ADA, section-5 menimpa dgn nilai yg dihitung dari matriks grup.
    "MAX SHARE", "LAST DAY SHARE",
]


def _join_unique(series: pd.Series, sep: str = ", ") -> str:
    """Gabung nilai unik non-kosong (urut kemunculan pertama)."""
    seen: set[str] = set()
    out: list[str] = []
    for v in series:
        if v is None or v is pd.NA or v is pd.NaT:
            continue
        s = str(v).strip()
        if not s or s.lower() == "nan":
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return sep.join(out)


def _day_columns(df: pd.DataFrame) -> list[str]:
    """Kolom hari '1'..'31' yang benar-benar ada di df (urut numerik)."""
    names = set(map(str, df.columns))
    return [str(d) for d in range(1, 32) if str(d) in names]


def _safe_div(a, b):
    """Pembagian elemen-wise; penyebut 0/NaN → NaN (bukan inf/raise)."""
    a = pd.to_numeric(pd.Series(a), errors="coerce")
    b = pd.to_numeric(pd.Series(b), errors="coerce")
    b = b.where(b != 0)
    return (a / b).to_numpy()


def group_anomali_display(
    df: pd.DataFrame,
    fps: pd.Series | None,
    config: dict | None,
    key_akhir: int = 31,
    has_baseline: bool = False,
) -> pd.DataFrame:
    """Agregasi df anomali → tampilan per (JENIS, NAMA BARANG, NAMA RESTO).

    Args:
        df: df baris-detail hasil filter + enrich BULAN LALU (level baris).
        fps: sidik jari per baris df (fingerprint_series, index align) —
            dipakai utk kolom __FPS (follow-up grup = semua anggota).
        config: config aktif (threshold PROFIL_DAILY_MIN & TH_CHANGE_*).
        key_akhir: hari terakhir periode (penyebut AVG; default 31).
        has_baseline: True bila pembanding bulan lalu aktif (mengaktifkan
            kolom BULAN LALU/selisih/perubahan + suffix PROFIL ' — Baru').

    Returns:
        DataFrame grup (index baru 0..n-1): kolom agregat + __FPS;
        DataFrame KOSONG bila df kosong / tanpa kunci grup.
    """
    if df is None or df.empty or not all(k in df.columns for k in GROUP_KEYS):
        return pd.DataFrame()

    cfg = config or {}
    try:
        profil_min = int((cfg.get("thresholds") or {}).get(
            "PROFIL_DAILY_MIN", _DEFAULT_PROFIL_DAILY_MIN))
    except (TypeError, ValueError):
        profil_min = _DEFAULT_PROFIL_DAILY_MIN
    try:
        key_akhir = max(1, int(key_akhir))
    except (TypeError, ValueError):
        key_akhir = 31

    keys = GROUP_KEYS
    days = [c for c in _day_columns(df) if int(c) <= key_akhir]
    g = df.groupby(keys, dropna=False, sort=False)

    # ---------- 1) SUM: TOTAL + hari + BULAN LALU ----------
    agg: dict[str, str] = {}
    if "TOTAL" in df.columns:
        agg["TOTAL"] = "sum"
    for c in days:
        agg[c] = "sum"
    if "BULAN LALU" in df.columns:
        agg["BULAN LALU"] = "sum"
    out = g.agg(agg).reset_index()

    # ---------- 2) join teks unik (merge on keys — tahan NaN) ----------
    for col, sep in (("SOURCE DATA", ", "), ("KETERANGAN", " | "),
                     ("ANOMALY REASONS", " | ")):
        if col in df.columns:
            t = (g[col].agg(lambda s: _join_unique(s, sep))
                 .reset_index())
            out = out.merge(t, on=keys, how="left", sort=False)
    # SOURCE DATA GABUNGAN = kolom tampilan sampel user (isi join di atas)
    if "SOURCE DATA" in out.columns:
        out[SRC_GAB_COL] = out["SOURCE DATA"]

    # ---------- 3) skor MAX + status paling parah ----------
    if "ANOMALY SCORE" in df.columns:
        t = g["ANOMALY SCORE"].max().reset_index()
        out = out.merge(t, on=keys, how="left", sort=False)
    # v2.19.0 — kolom sinyal _s1.._s12 (0/1 indikator) di-MAX per grup:
    # grup dianggap memicu sinyal bila ADA anggota yang memicu (konsisten
    # dgn ANOMALY SCORE max + ANOMALY REASONS join). Tanpa ini pop-up
    # detail grup menampilkan 0 sinyal terpicu padahal anggota punya
    # (regresi test_v270_wave2 — chip sinyal hidup).
    sig_cols = [c for c in df.columns
                if str(c).startswith("_s") and c[2:].isdigit()
                and 1 <= int(c[2:]) <= 12]
    if sig_cols:
        t = g[sig_cols].max().reset_index()
        out = out.merge(t, on=keys, how="left", sort=False)
    if "ANOMALY STATUS" in df.columns:
        rank = df["ANOMALY STATUS"].map(_STATUS_RANK)
        by = [df[k] for k in keys]
        t = (rank.groupby(by, dropna=False, sort=False).max()
             .rename("ANOMALY STATUS").reset_index())
        t["ANOMALY STATUS"] = t["ANOMALY STATUS"].map(
            lambda v: _STATUS_NAME.get(v, "") if v == v and v >= 0 else "")
        out = out.merge(t, on=keys, how="left", sort=False)

    # ---------- 4) baris representatif (anggota skor tertinggi) ---------
    rep_cols = [c for c in _REP_COLS if c in df.columns]
    # Fallback % to BOM: tanpa TOTAL BOM rasio tak bisa dihitung ulang —
    # bawa nilai baris representatif (fixture / data tanpa sheet BOM).
    if "% to BOM" in df.columns and "TOTAL BOM" not in df.columns:
        rep_cols.append("% to BOM")
    if rep_cols:
        if "ANOMALY SCORE" in df.columns:
            sc = pd.to_numeric(df["ANOMALY SCORE"], errors="coerce")
            tmp = df.assign(__sc=sc.fillna(-1)).sort_values(
                "__sc", ascending=False)
        else:
            tmp = df
        rep = tmp.drop_duplicates(subset=keys, keep="first")
        t = rep[keys + rep_cols]
        out = out.merge(t, on=keys, how="left", sort=False)

    # ---------- 5) statistik hari dari matriks TERJUMLAH ----------
    if days:
        arr = (out[days].apply(pd.to_numeric, errors="coerce")
               .fillna(0.0).to_numpy(dtype=float))
        tot = np.sum(arr, axis=1)
        cnt = (arr > 0).sum(axis=1)
        mx = arr.max(axis=1)
        hari_max = np.argmax(arr, axis=1) + 1
        srt = np.sort(arr, axis=1)
        second = np.where(cnt >= 2, srt[:, -2], np.nan)
        last = arr[:, -1]
        out["MAX"] = mx
        out["HARI MAX"] = hari_max
        out["Count Hari"] = cnt
        out["SECOND MAX"] = second
        out["AVG"] = _safe_div(tot, key_akhir)
        out["AVG AKTIF"] = np.where(cnt > 0, _safe_div(tot, cnt), np.nan)
        out["MEDIAN AKTIF"] = [
            float(np.median(r[r > 0])) if (r > 0).any() else np.nan
            for r in arr]
        out["MAX SHARE"] = _safe_div(mx, tot)
        out["LAST DAY SHARE"] = _safe_div(last, tot)
        out["NILAI HARI TERAKHIR"] = last
        out["MAX / AVG"] = _safe_div(mx, out["AVG"])
        out["MAX / AVG AKTIF"] = _safe_div(mx, out["AVG AKTIF"])
        out["MAX / MEDIAN AKTIF"] = _safe_div(mx, out["MEDIAN AKTIF"])
        out["MAX / SECOND MAX"] = _safe_div(mx, second)

    # ---------- 6) % to BOM grup ----------
    if "TOTAL" in out.columns and "TOTAL BOM" in out.columns:
        ratio = _safe_div(out["TOTAL"], out["TOTAL BOM"])
        out["% to BOM"] = [(r if r == r else "Cek") for r in ratio]
    # else: nilai baris representatif sudah dibawa rep_cols (fallback).

    # ---------- 7) PROFIL grup (dari hari aktif terjumlah) ----------
    if "Count Hari" in out.columns:
        cnt = pd.to_numeric(out["Count Hari"], errors="coerce").fillna(0)
        profil = np.where(cnt >= max(profil_min, 2), PROFIL_TIAP_HARI, "")
        profil = np.where((profil == "") & (cnt >= 2), PROFIL_KADANG, profil)
        profil = np.where((profil == "") & (cnt == 1), PROFIL_SEKALI_INI,
                          profil)
        out["PROFIL"] = np.where(profil == "", PROFIL_KOSONG, profil)

    # ---------- 8) kolom banding bulan lalu (bila pembanding aktif) ------
    if "BULAN LALU" in out.columns and "TOTAL" in out.columns:
        bl = pd.to_numeric(out["BULAN LALU"], errors="coerce").fillna(0.0)
        tot = pd.to_numeric(out["TOTAL"], errors="coerce")
        # Grup tanpa riwayat (semua anggota NaN → SUM 0) = BARU — pola
        # change_vs_history ('BARU' = pembanding 0/tidak ada).
        has_hist = bl > 0
        bl_safe = bl.where(has_hist)
        out[SELISIH_COL] = (tot - bl_safe).to_numpy()
        # Kolom gabungan NUMERIK (nilai = total bulan lalu; teks sel
        # '1.969,1 (-30%)' diformat model — ui/models.py) supaya SORT
        # numerik klik-header/SortControl tetap benar.
        out[LASTMONTH_COMBINED_COL] = bl_safe.to_numpy()
        out["PERUBAHAN %"] = (_safe_div(tot - bl_safe, bl_safe) * 100.0)
        out["PERUBAHAN"] = [classify_change(t, b, cfg)
                            for t, b in zip(tot.tolist(),
                                            bl_safe.tolist())]
        # suffix PROFIL ' — Baru' utk grup ber-nilai tanpa riwayat (pola
        # annotate_profile_vs_history level baris).
        if has_baseline and "PROFIL" in out.columns:
            baru = (~has_hist) & (tot.fillna(0) > 0)
            out.loc[baru, "PROFIL"] = (
                out.loc[baru, "PROFIL"].astype(str) + PROFIL_BARU_SUFFIX)

    # ---------- 9) sidik jari anggota (follow-up grup = semua anggota) ---
    if fps is not None and len(fps) == len(df):
        by = [df[k] for k in keys]
        t = (fps.groupby(by, dropna=False, sort=False)
             .agg(lambda s: tuple(str(v) for v in s))
             .rename(FPS_COL).reset_index())
        out = out.merge(t, on=keys, how="left", sort=False)

    # ---------- 10) urutan kolom: sampel user dulu, pendamping belakang --
    front = [c for c in (
        keys + [SRC_GAB_COL, "TOTAL", "% to BOM",
                LASTMONTH_COMBINED_COL, SELISIH_COL, "PERUBAHAN",
                "ANOMALY STATUS", "PROFIL", "ANOMALY SCORE"]
    ) if c in out.columns]
    rest = [c for c in out.columns
            if c not in front + [FPS_COL]]
    return out[front + rest + ([FPS_COL] if FPS_COL in out.columns else [])]
