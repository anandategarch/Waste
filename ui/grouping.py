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
# v2.19.2 — sidik jari PLURAL baris Excel sumber (paralel __FPS). Tiap grup
# membawa tuple nomor baris fisik sheet REKAP MENTAH semua anggotanya
# (dipasang ensure_rekap_header via __SRC_ROW). Dipakai pop-up detail utk
# menulis-balik koreksi nilai hari: grup 1-anggota → edit langsung (jalur
# v2.16.0 pulih, regresi v2.19.0 diperbaiki); grup multi-anggota → tulis
# koreksi ke SEMUA anggota sekaligus (konfirmasi daftar baris diberikan).
SRC_ROWS_COL = "__SRC_ROWS"
# v2.19.3 — kolom penanda BARIS PEMISAH grup (layout SAMPEL TAMPILAN BARU
# di TABEL tab Anomali — permintaan user: "insert blank line after each
# item label ... kolom jenis dan nama barang"). Baris pemisah: seluruh
# kolom NaN + __SEP=True → model merender baris KOSONG (tak selectable,
# record()=None, tak masuk funnel/klik).
SEP_COL = "__SEP"
# Kunci grup pemisah = label item (JENIS + NAMA BARANG) — pemisah disisipkan
# saat label item BERUBAH antar baris bertetangga (urutan grup dijamin
# oleh sort (JENIS, NAMA BARANG, NAMA RESTO)).
SEP_KEYS = ("JENIS", "NAMA BARANG")

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
    # v2.19.1 (audit bug D): agg KOSONG (df tanpa TOTAL/hari/BULAN LALU —
    # fixture sintetis / df parsial) membuat g.agg({}) melempar
    # ValueError "No objects to concatenate" — pelanggaran kontrak
    # defensif docstring ini sendiri. Kerangka grup dibangun via
    # g.size() (jumlah anggota per grup) lalu kolom hitungannya dibuang.
    if agg:
        out = g.agg(agg).reset_index()
    else:
        out = g.size().to_frame("__n").reset_index().drop(columns="__n")

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
    # v2.20.1 — KETERANGAN fallback ke JENIS bila kosong (permintaan user:
    # "kolom jenis diganti jadi kolom KETERANGAN AJA"). Catatan SUSUT/TRIAL
    # umumnya tak punya sub-alasan — jenisnya itulah keterangannya, jadi
    # KETERANGAN kosong → tampilkan JENIS (SUSUT/TRIAL) supaya kolom
    # KETERANGAN tak pernah blank & vocabularynya utuh (Alat/Mesin, Cancel
    # Nota, Handling, Kualitas, Kualitas Eksternal, Kualitas Internal, Over
    # Stock, SUSUT, TRIAL). Grup homogen-per-JENIS (JENIS = kunci grup) →
    # fallback seragam per grup (tidak mengubah grup WASTE ber-alasan).
    if "KETERANGAN" in out.columns and "JENIS" in out.columns:
        ket = out["KETERANGAN"]
        empty = ket.isna() | (ket.astype(str).str.strip() == "")
        if bool(empty.any()):
            out.loc[empty, "KETERANGAN"] = out.loc[empty, "JENIS"]

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

    # ---------- 6b) RANGKING WASTE grup (v2.20.0) ----------
    # Permintaan user (M code 'TambahRangkingFast'): analisa peringkat
    # waste — Top 3 Total & Top 3 % BOM per item LINTAS CABANG. Lapis
    # GRUP: TopTotal/TopBOM dihitung dari TOTAL grup & % to BOM grup
    # (tabel Anomali = satu baris per item×cabang — total cabang = sum
    # anggotanya), MENIMPA nilai baris representatif (_REP_COLS membawa
    # ranking anggota ber-TOTAL baris; grup multi-anggota berbeda).
    # Label = sumber tunggal waste_anomaly.signals.ranking_waste_label
    # (pencocokan nilai persis List.PositionOf M — duplikat berbagi
    # peringkat). Defensif: error apapun → kolom rep lama dipakai.
    if len(out) and {"JENIS", "NAMA BARANG"} <= set(out.columns):
        try:
            from waste_anomaly.signals import ranking_waste_label
            tot_all = (pd.to_numeric(out["TOTAL"], errors="coerce")
                       if "TOTAL" in out.columns else None)
            pct_all = (pd.to_numeric(out["% to BOM"], errors="coerce")
                       if "% to BOM" in out.columns else None)
            labels = pd.Series("-", index=out.index, dtype=object)
            for _key, sub in out.groupby(
                    ["JENIS", "NAMA BARANG"], sort=False, dropna=False):
                tv = [] if tot_all is None else sorted(
                    (v for v in tot_all.loc[sub.index].tolist() if v == v),
                    reverse=True)[:3]
                bv = [] if pct_all is None else sorted(
                    (v for v in pct_all.loc[sub.index].tolist()
                     if v == v and v > 0),
                    reverse=True)[:3]
                tot_sub = (tot_all.loc[sub.index].tolist()
                           if tot_all is not None
                           else [None] * len(sub))
                pct_sub = (pct_all.loc[sub.index].tolist()
                           if pct_all is not None
                           else [None] * len(sub))
                for idx, t, p in zip(sub.index, tot_sub, pct_sub):
                    labels.at[idx] = ranking_waste_label(t, p, tv, bv)
            out["RANGKING WASTE"] = labels.to_numpy()
        except Exception:  # noqa: BLE001 — ranking opsional, defensif
            pass

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

    # ---------- 9b) __SRC_ROWS anggota (tulis-balik koreksi v2.19.2) --------
    # Tuple nomor baris Excel semua anggota grup (paralel __FPS). Dipakai
    # pop-up detail utk memetakan grup → baris fisik sheet REKAP MENTAH:
    # grup 1-anggota = edit langsung (pulihkan jalur v2.16.0 yg ter-regresi
    # di v2.19.0 krn __FPS selalu tuple); grup multi-anggota = tulis ke
    # SEMUA anggota. NaN/None di __SRC_ROW (dataset pra-v2.16 / fixture)
    # disaring → tuple bersih; bila kosong seluruhnya → tuple () (caller
    # memperlakukan () = tak bisa edit, pesan jujur).
    from waste_anomaly.rekap_import import SRC_ROW_COL as _SRC_ROW_COL
    if _SRC_ROW_COL in df.columns:
        sr = pd.to_numeric(df[_SRC_ROW_COL], errors="coerce")
        by = [df[k] for k in keys]
        t = (sr.groupby(by, dropna=False, sort=False)
             .agg(lambda s: tuple(int(v) for v in s
                                  if v is not None and v == v))
             .rename(SRC_ROWS_COL).reset_index())
        out = out.merge(t, on=keys, how="left", sort=False)

    # ---------- 10) urutan kolom: sampel user dulu, pendamping belakang --
    # v2.20.0: 'RANGKING WASTE' di kanan PROFIL (kolom paling kanan tabel
    # Anomali — permintaan user).
    front = [c for c in (
        keys + [SRC_GAB_COL, "TOTAL", "% to BOM",
                LASTMONTH_COMBINED_COL, SELISIH_COL, "PERUBAHAN",
                "ANOMALY STATUS", "PROFIL", "RANGKING WASTE",
                "ANOMALY SCORE"]
    ) if c in out.columns]
    _internal = {FPS_COL, SRC_ROWS_COL}
    rest = [c for c in out.columns
            if c not in front + list(_internal)]
    tail = [c for c in (FPS_COL, SRC_ROWS_COL) if c in out.columns]
    return out[front + rest + tail]


def insert_group_separators(
    df: pd.DataFrame,
    keys: tuple[str, ...] = SEP_KEYS,
) -> pd.DataFrame:
    """v2.19.3 — sisipkan BARIS KOSONG pemisah ANTAR grup item.

    Layout SAMPEL TAMPILAN BARU.xlsx di TABEL tab Anomali (permintaan user:
    "insert blank line after each item label ... dari kolom jenis dan nama
    barang"): setelah tiap grup (JENIS, NAMA BARANG) — baris bertetangga dgn
    label item sama — disisipkan SATU baris kosong; pemisah HANYA antar grup
    (tidak sebelum grup pertama, tidak setelah grup terakhir — sama dgn
    sheet Excel 'Anomali Grup').

    Syarat: ``df`` SUDAH diurut supaya baris grup bertetangga (pemanggil
    mem-sort by JENIS, NAMA BARANG, NAMA RESTO; model.sort memakai mergesort
    stable → sort by salah satu kunci grup tetap menjaga kedekatan grup).

    Baris pemisah: SELURUH kolom NaN + ``__SEP``=True (Python bool —
    kontrak model: render kosong, tak selectable, record()=None; funnel &
    klik di-guard). Idempoten: bila __SEP sudah ada → buang dulu, sisip
    ulang (dipakai model.sort saat user sort by kolom grup).

    Return: df baru (index 0..n-1) dgn kolom ``__SEP`` tambahan; df KOSONG
    / tanpa kunci grup / 1 grup tunggal → df asli (tanpa pemisah, dgn
    kolom __SEP=False utk kontrak seragam bila memungkinkan).
    """
    if df is None or df.empty:
        return df
    have = [k for k in keys if k in df.columns]
    if not have:
        return df
    # Idempoten: buang pemisah lama (sort ulang / re-insert).
    if SEP_COL in df.columns:
        try:
            old_sep = df[SEP_COL].map(
                lambda v: isinstance(v, bool) and v)
            if bool(old_sep.any()):
                df = df[~old_sep]
            df = df.drop(columns=[SEP_COL])
        except Exception:  # noqa: BLE001 — dtype eksotis: anggap tak ada
            pass
    # Grup baru dimulai saat label item BERUBAH dari baris sebelumnya.
    # fillna sentinel: pandas ``ne`` menganggap NaN ≠ NaN (dua baris NaN
    # berurutan akan dianggap "berubah" — salah).
    k = df[have].fillna("\x00nan")
    changed = k.ne(k.shift()).any(axis=1)
    insert_before = changed.copy()
    if len(insert_before):
        insert_before.iloc[0] = False  # grup pertama tanpa pemisah di depan
    n_sep = int(insert_before.sum())
    if n_sep == 0:
        # 1 grup tunggal: tanpa pemisah — kolom __SEP tetap dipasang (kontrak
        # seragam: model/funnel boleh asumsi kolom ada).
        out = df.copy()
        out[SEP_COL] = False
        return out
    arr = df.to_numpy(dtype=object)
    n, ncols = arr.shape
    flags = insert_before.to_numpy()
    total = n + n_sep
    out_arr = np.empty((total, ncols + 1), dtype=object)
    out_arr[:, :] = np.nan
    out_arr[:, ncols] = False
    pos = 0
    for i in range(n):
        if flags[i]:
            out_arr[pos, ncols] = True   # baris pemisah: semua kolom NaN
            pos += 1
        out_arr[pos, :ncols] = arr[i]
        out_arr[pos, ncols] = False
        pos += 1
    return pd.DataFrame(out_arr, columns=list(df.columns) + [SEP_COL])
