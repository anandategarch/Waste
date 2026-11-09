"""insights.py — analisa agregat level CABANG utk tab Scorecard (v2.13.1).

Riset R1 (data asli) menemukan pertanyaan audit yang belum terjawab oleh
tab mana pun: "kunjungi cabang mana dulu, bawa bukti apa, berapa yang
bisa dihemat?" Modul ini menghitung bahan jawabannya (semua DEFENSIF:
kolom hilang / df kosong / tanpa pembanding → hasil kosong berformat,
tidak pernah raise; perhitungan vektor):

- resto_intensity(df)     : per cabang — waste vs BOM (%), median peer,
  KELEBIHAN vs median (unit-aware per baris: waste_i/BOM_i satu satuan
  → agregat = rata-rata tertimbang BOM dari rasio baris; catatan SATUAN
  jujur di konstanta). Data asli: median 0,29%, kelebihan total 1,26
  juta unit = 13,7% waste.
- money_ranking(df, top_n): peringkat baris berdasarkan KELEBIHAN (bukan
  TOTAL) — "uang yang bisa dicegah" per baris; kolom SATUAN tampil
  supaya campuran GR/PCS terbaca jujur.
- coverage_report(df, months): detektor INPUT KOSONG — item umum (dilaporkan
  ≥ mayoritas cabang) yang TIDAK dilaporkan satu cabang (data asli:
  B.1001.MLGPAR absen 35/40 item umum). Verdict jujur dgn pembanding:
  "Berhenti Input" (aktif bulan lalu, kosong sekarang) vs "Memang Tak
  Pernah" (kosong dua-duanya) vs "Perlu Pembanding".
- systemic_days(df, key_akhir): hari yang naik di BANYAK cabang sekaligus
  (≥ max(3, 15% cabang)) — penanda masalah BERSAMA (pengiralan/hari
  besar/POS), bukan kecurigaan satu cabang; jadi konteks menafsirkan
  hari tersangka. Data asli bulan berjalan: 0 hari sistemik (semua
  lonjakan lokal) — itu sendiri informasi.
- weekday_real(df, label) : pola hari-KALENDER asli (Senin..Minggu) dari
  label bulan (detect_month_label). Fix proxy mod-7 riset R1: kelas
  mod-7 sama = hari kalender BERBEDA antar bulan (2026-08-01 Sabtu vs
  2026-09-01 Selasa) → banding lintas bulan tak apple-to-apple.
- scorecard(df, months, key_akhir, config): tabel komposit per cabang
  (intensitas + kelebihan + alasan dominan + profil campuran + hari
  tersangka + pasangan baru/pulih + verdict input) — sort kelebihan desc
  = urutan kunjungan audit.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from .period_history import label_parseable, month_sort_key
from .profile import PEER_KEYS

# Nama bulan Indonesia + varian → nomor bulan (konsisten dgn period_history).
_BULAN = {
    "januari": 1, "jan": 1, "februari": 2, "feb": 2, "maret": 3, "mar": 3,
    "april": 4, "apr": 4, "mei": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "aug": 8, "sep": 9, "september": 9,
    "oktober": 10, "oct": 10, "okt": 10, "november": 11, "nov": 11,
    "desember": 12, "des": 12, "dec": 12,
}

_HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Kontrak kolom (UI membaca urutan PERSIS — JANGAN diubah sembarangan).
INTENSITY_COLS = [
    "NAMA RESTO", "TOTAL WASTE", "TOTAL BOM", "INTENSITAS %",
    "TIPIKAL CABANG %", "KELEBIHAN", "KELEBIHAN %", "SATUAN CATATAN",
]
MONEY_COLS = [
    "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SATUAN",
    "TOTAL", "TIPIKAL CABANG LAIN", "KELEBIHAN", "RASIO",
    "DI ATAS % CABANG", "PROFIL", "ANOMALY STATUS",
]
COVERAGE_COLS = [
    "NAMA RESTO", "ITEM UMUM TAK INPUT", "CONTOH ITEM",
    "STATUS INPUT",
]
SYSTEMIC_COLS = [
    "HARI", "CABANG TERPENGARUH", "N", "DAFTAR CABANG",
]
WEEKDAY_COLS = ["HARI", "TOTAL", "N HARI", "RATA PER HARI"]
SCORECARD_COLS = [
    "RANK", "NAMA RESTO", "KELEBIHAN", "STATUS INPUT",
    "TOTAL WASTE", "INTENSITAS %", "ANOMALI", "HARI TERSANGKA",
    "ALASAN DOMINAN", "ITEM TIAP HARI", "BARU", "PULIH", "TREN",
]
# v2.17.0 rombak P0: KELEBIHAN (sinyal utama action) + STATUS INPUT
# (keputusan audit) ditarik ke depan (kanan NAMA RESTO) — sebelumnya
# KELEBIHAN di posisi 4 & STATUS INPUT di 11 (hampir terakhir). Tabel
# scorecard = prioritas tindak lanjut; sinyal action wajib terbaca dulu.
# ⑧ tren multi-bulan: label kolom bebas (label bulan pembanding) + TREN.
TREND_BASE_COLS = ["NAMA RESTO", "TREN"]

# Label SATUAN jujur utk agregat BOM-tertimbang.
_SATUAN_NOTE = ("campuran satuan — tiap baris dibandingkan dgn BOM "
                "satuan yang sama, lalu rata-rata tertimbang BOM")

_VERDICT_STOP = "Berhenti Input"
_VERDICT_NEVER = "Memang Tak Pernah"
_VERDICT_NEED = "Perlu Pembanding"
_VERDICT_OK = "Lengkap"


def _num(df: pd.DataFrame, col: str) -> pd.Series | None:
    if col not in df.columns:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _text(df: pd.DataFrame, col: str) -> pd.Series | None:
    if col not in df.columns:
        return None
    return df[col].fillna("").astype(str).str.strip()


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


# ============================================================
# INTENSITAS PER CABANG (waste vs BOM) + KELEBIHAN vs MEDIAN
# ============================================================

def resto_intensity(df: pd.DataFrame) -> pd.DataFrame:
    """Per cabang: TOTAL WASTE, TOTAL BOM, INTENSITAS % (waste/BOM ×100),
    TIPIKAL CABANG % (median intensitas), KELEBIHAN (unit) & % di atas
    tipikal, SATUAN CATATAN (kejujuran metode).

    - Hanya baris TOTAL BOM > 0 dipakai utk intensitas (baris tanpa BOM
      tak punya penyebut); cabang tanpa bari BOM sama sekali → intensitas
      NaN + catatan 'Cek' (tak bisa dihitung).
    - KELEBIHAN = max(0, intensitas − median) × BOM cabang itu —
      "bila cabang main di level tipikal, berapa waste yang hilang".
      Bukan perjanjian hukum — alat prioritisasi.
    - Sort KELEBIHAN desc (tanpa NaN), lalu TOTAL WASTE desc.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(INTENSITY_COLS)
    need = ("NAMA RESTO", "TOTAL", "TOTAL BOM")
    if any(c not in df.columns for c in need):
        return _empty(INTENSITY_COLS)

    resto = _text(df, "NAMA RESTO")
    total = _num(df, "TOTAL").fillna(0.0)
    bom = _num(df, "TOTAL BOM")
    has_bom = bom.notna() & (bom > 0)

    work = pd.DataFrame({
        "NAMA RESTO": resto.to_numpy(),
        "TOTAL WASTE": total.to_numpy(),
        "BOM_OK": has_bom.to_numpy(),
        "BOM": bom.fillna(0.0).to_numpy(),
    })
    g = work.groupby("NAMA RESTO", sort=True).agg(
        **{
            "TOTAL WASTE": ("TOTAL WASTE", "sum"),
            "TOTAL BOM": ("BOM", "sum"),
            "N BOM ROW": ("BOM_OK", "sum"),
        })
    g = g[g["TOTAL WASTE"] > 0]
    if g.empty:
        return _empty(INTENSITY_COLS)
    inten = (g["TOTAL WASTE"] / g["TOTAL BOM"].where(g["TOTAL BOM"] > 0)
             * 100.0)
    med = float(np.nanmedian(inten.to_numpy())) if inten.notna().any() else np.nan
    kelebihan = ((inten - med).clip(lower=0) / 100.0
                 * g["TOTAL BOM"].where(g["TOTAL BOM"] > 0))
    kelebihan_pct = (inten - med).clip(lower=0)
    out = pd.DataFrame({
        "NAMA RESTO": g.index.to_numpy(),
        "TOTAL WASTE": g["TOTAL WASTE"].to_numpy(),
        "TOTAL BOM": g["TOTAL BOM"].to_numpy(),
        "INTENSITAS %": inten.round(3).to_numpy(),
        "TIPIKAL CABANG %": med,
        "KELEBIHAN": kelebihan.round(1).to_numpy(),
        "KELEBIHAN %": kelebihan_pct.round(3).to_numpy(),
        "SATUAN CATATAN": np.where(
            g["N BOM ROW"] > 0, _SATUAN_NOTE, "Cek — tidak ada data BOM"),
    })
    out = out.sort_values(
        ["KELEBIHAN", "TOTAL WASTE"], ascending=False, na_position="last",
        kind="stable")
    return out.reset_index(drop=True)[INTENSITY_COLS]


# ============================================================
# PERINGKAT UANG (berdasar KELEBIHAN — bukan TOTAL)
# ============================================================

def money_ranking(df: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """Top baris berdasarkan KELEBIHAN vs tipikal cabang lain.

    Kolom MONEY_COLS; RASIO = TOTAL ÷ tipikal (×, unit-free). Hanya baris
    dgn KELEBIHAN terisi (peer ≥ 3 + TOTAL > 0) DAN kelebihan > 0.
    DI ATAS % CABANG (⑨ riset R1) = persentil TOTAL baris ini di antara
    peer AKTIF item sama (100 = paling boros, 0 = paling hemat — tahan
    skew, unit-free; padanan robust z-score dgn istilah awam). Sort
    KELEBIHAN desc; SATUAN tampil (campuran GR/PCS jujur — funnel SATUAN
    bisa memilah)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(MONEY_COLS)
    if "KELEBIHAN" not in df.columns:
        return _empty(MONEY_COLS)
    kelebihan = _num(df, "KELEBIHAN")
    mask = kelebihan.notna() & (kelebihan > 0)
    if not mask.any():
        return _empty(MONEY_COLS)
    sub = df.loc[mask.to_numpy()].copy()
    total = pd.to_numeric(sub["TOTAL"], errors="coerce")
    tip = pd.to_numeric(sub["PEER MEDIAN (AKTIF)"], errors="coerce")
    rasio = (total / tip.where(tip > 0)).to_numpy()
    # ⑨ persentil di antara peer AKTIF (grup sama dgn KELEBIHAN) —
    # rank pct di subset aktif, di-map balik ke baris terpilih.
    pctile = np.full(len(sub), np.nan)
    if all(k in df.columns for k in PEER_KEYS):
        total_all = _num(df, "TOTAL").fillna(0.0)
        aktif = (total_all > 0).to_numpy()
        keys = [df[k].astype(str) for k in PEER_KEYS]
        work = pd.DataFrame({k.name: k.to_numpy() for k in keys})
        work["_total"] = total_all.to_numpy()
        wact = work[aktif]
        grp = wact.groupby(list(work.columns[:-1]), sort=False,
                           dropna=False)["_total"]
        rank_pct = grp.rank(pct=True, method="average")
        # posisi subset aktif → baris sub (indeks label asli)
        pos_map = pd.Series(
            rank_pct.to_numpy(),
            index=np.flatnonzero(aktif)).reindex(
            np.flatnonzero(mask.to_numpy()))
        pctile = pos_map.to_numpy(dtype=float) * 100.0
    out = pd.DataFrame({
        "NAMA RESTO": sub["NAMA RESTO"].to_numpy() if "NAMA RESTO" in sub.columns else "",
        "NAMA BARANG": sub["NAMA BARANG"].to_numpy() if "NAMA BARANG" in sub.columns else "",
        "JENIS": sub["JENIS"].to_numpy() if "JENIS" in sub.columns else "",
        "KETERANGAN": sub["KETERANGAN"].to_numpy() if "KETERANGAN" in sub.columns else "",
        "SATUAN": sub["SATUAN"].to_numpy() if "SATUAN" in sub.columns else "",
        "TOTAL": total.to_numpy(),
        "TIPIKAL CABANG LAIN": tip.to_numpy(),
        "KELEBIHAN": kelebihan[mask].to_numpy(),
        "RASIO": rasio,
        "DI ATAS % CABANG": pctile,
        "PROFIL": sub["PROFIL"].to_numpy() if "PROFIL" in sub.columns else "",
        "ANOMALY STATUS": (sub["ANOMALY STATUS"].to_numpy()
                           if "ANOMALY STATUS" in sub.columns else ""),
    })
    out = out.sort_values("KELEBIHAN", ascending=False, kind="stable")
    try:
        n = int(top_n)
    except (TypeError, ValueError):
        n = 100
    if n > 0:
        out = out.iloc[:n]
    return out.reset_index(drop=True)[MONEY_COLS]


# ============================================================
# DETEKTOR INPUT KOSONG (under-reporting)
# ============================================================

def _active_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Pasangan (NAMA RESTO, NAMA BARANG) aktif (TOTAL > 0) unik."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["NAMA RESTO", "NAMA BARANG"])
    need = ("NAMA RESTO", "NAMA BARANG", "TOTAL")
    if any(c not in df.columns for c in need):
        return pd.DataFrame(columns=["NAMA RESTO", "NAMA BARANG"])
    total = pd.to_numeric(df["TOTAL"], errors="coerce").fillna(0.0)
    sub = df.loc[(total > 0).to_numpy(),
                 ["NAMA RESTO", "NAMA BARANG"]].copy()
    sub["NAMA RESTO"] = sub["NAMA RESTO"].astype(str).str.strip()
    sub["NAMA BARANG"] = sub["NAMA BARANG"].astype(str).str.strip()
    return sub.drop_duplicates().reset_index(drop=True)


def _latest_month(months: list[dict]) -> dict | None:
    """Bulan pembanding TERBARU — label terparse terbesar (audit v2.18.0).

    Dua bug lama pada konsumen "bulan terbaru":
    - scorecard BARU/PULIH: max() LEKSIKOGRAFIS ("Mei" > "Juni" krn
      M > J) → angka banding bulan SALAH & kontradiksi dgn TREN di
      baris yang sama (TREN sudah benar pakai month_sort_key).
    - max(month_sort_key) TANPA filter: label tak terparse dapat
      sentinel (9999, 0) yang MENANG max() — file bernama aneh
      terpilih jadi "terbaru".
    Kini: label tak terparse DIKECUALikan; fallback bulan apa pun bila
    tak ada yang terparse (perilaku lama utk kasus 1-file-aneh).
    """
    ok = [m for m in (months or [])
          if m and not m.get("error") and m.get("agg") is not None
          and not m["agg"].empty]
    if not ok:
        return None
    parseable = [m for m in ok if label_parseable(m.get("label"))]
    return max(parseable or ok,
               key=lambda m: month_sort_key(m.get("label")))


def coverage_report(
    df: pd.DataFrame,
    months: list[dict] | None = None,
    min_share: float = 0.75,
) -> pd.DataFrame:
    """Per cabang: item umum yang TIDAK dilaporkan + verdict input.

    Item umum = item dilaporkan aktif oleh ≥ min_share × (jumlah cabang
    pelapor item itu) — sederhananya: dilaporkan oleh mayoritas. Cabang
    dihitung TAK INPUT utk item umum yang pasangannya absen dari daftar
    aktifnya. Verdict (butuh pembanding):
    - "Berhenti Input": pasangan AKTIF bulan pembanding TERBARU tapi
      kosong sekarang (sinyal terkuat — input berhenti bulan ini).
    - "Memang Tak Pernah": absen juga di pembanding (pola lama —
      kemungkinan sah / memang tak menjual).
    - "Perlu Pembanding": tanpa file pembanding tak bisa dibedakan.
    - "Lengkap": tak ada item umum yang absen.
    Sort ITEM UMUM TAK INPUT desc.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(COVERAGE_COLS)
    if "NAMA RESTO" not in df.columns or "NAMA BARANG" not in df.columns:
        return _empty(COVERAGE_COLS)
    pairs = _active_pairs(df)

    # Semua cabang yang ADA di dataset (bukan hanya yang punya baris
    # aktif — cabang tanpa waste sama sekali justru sinyal terkuat
    # utk detektor input kosong; data asli: placeholder 90,6% baris nol).
    resto_all = df["NAMA RESTO"].astype(str).str.strip()
    all_restos = set(resto_all.unique())
    n_restos = len(all_restos)
    if n_restos == 0 or pairs.empty:
        return _empty(COVERAGE_COLS)

    item_resto = pairs.groupby("NAMA BARANG")["NAMA RESTO"].nunique()
    try:
        share = float(min_share)
    except (TypeError, ValueError):
        share = 0.75
    common = item_resto[item_resto >= max(2, round(share * n_restos))]
    common_items = set(common.index)

    have = pairs[pairs["NAMA BARANG"].isin(common_items)]
    reported = {
        r: set(g["NAMA BARANG"]) for r, g in have.groupby("NAMA RESTO")
    }

    # pembanding terbaru utk verdict
    # v2.18.0 audit (L-1): dulu UNION semua bulan pembanding — item aktif
    # 3 bulan lalu tapi absen bulan lalu & sekarang tetap divonis
    # "Berhenti Input" (dokumen & kontrak scorecard: pembanding TERBARU;
    # kontradiksi dgn BARU/PULIH baris yang sama).
    last_pairs: set[tuple[str, str]] = set()
    has_months = False
    _last_m = _latest_month(months)
    if _last_m is not None:
        has_months = True
        agg = _last_m["agg"]
        sub = agg.loc[pd.to_numeric(
            agg.get("TOTAL"), errors="coerce").fillna(0) > 0,
            ["NAMA RESTO", "NAMA BARANG"]].copy() \
            if "TOTAL" in agg.columns else agg[["NAMA RESTO", "NAMA BARANG"]].copy()
        last_pairs.update(
            (str(a).strip(), str(b).strip())
            for a, b in sub.itertuples(index=False))

    rows = []
    for r in sorted(all_restos):
        missing = sorted(common_items - reported.get(r, set()))
        if not missing:
            rows.append({
                "NAMA RESTO": r, "ITEM UMUM TAK INPUT": 0,
                "CONTOH ITEM": "", "STATUS INPUT": _VERDICT_OK})
            continue
        if not has_months:
            verdict = _VERDICT_NEED
        else:
            stop = [it for it in missing if (r, it) in last_pairs]
            verdict = _VERDICT_STOP if stop else _VERDICT_NEVER
        rows.append({
            "NAMA RESTO": r,
            "ITEM UMUM TAK INPUT": len(missing),
            "CONTOH ITEM": "; ".join(missing[:3])
            + ("…" if len(missing) > 3 else ""),
            "STATUS INPUT": verdict,
        })
    out = pd.DataFrame(rows, columns=COVERAGE_COLS)
    out = out.sort_values("ITEM UMUM TAK INPUT", ascending=False,
                          kind="stable")
    return out.reset_index(drop=True)


# ============================================================
# HARI SISTEMIK (naik serentak di banyak cabang)
# ============================================================

def systemic_days(
    df: pd.DataFrame,
    key_akhir: int = 31,
    ratio: float = 2.0,
) -> pd.DataFrame:
    """Hari yang waste harian cabang ≥ ratio × median harian cabang itu
    sendiri, terjadi di ≥ max(3, 15% cabang) — masalah BERSAMA.

    Kolom: HARI (int), CABANG TERPENGARUH (n), N (n — alias tampil),
    DAFTAR CABANG (nama dipisah '; '). Hanya cabang dgn median > 0
    dihitung. Sort HARI asc. Kosong = tidak ada hari sistemik — semua
    lonjakan lokal (informasi itu sendiri)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(SYSTEMIC_COLS)
    if "NAMA RESTO" not in df.columns:
        return _empty(SYSTEMIC_COLS)
    day_cols = [str(d) for d in range(1, int(key_akhir) + 1)
                if str(d) in df.columns]
    if not day_cols:
        return _empty(SYSTEMIC_COLS)

    resto = df["NAMA RESTO"].astype(str).str.strip()
    num = df[day_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    num = num.set_index(resto.to_numpy())
    per_resto = num.groupby(level=0).sum()

    med = per_resto.median(axis=1)
    med = med.where(med > 0)
    elevated = per_resto.gt(med * float(ratio), axis=0)
    n_restos = per_resto.shape[0]
    threshold = max(3, int(np.ceil(0.15 * n_restos)))

    rows = []
    for d in day_cols:
        hits = elevated.index[elevated[d].to_numpy()] if d in elevated.columns else []
        if len(hits) >= threshold:
            rows.append({
                "HARI": int(d), "CABANG TERPENGARUH": len(hits),
                "N": len(hits), "DAFTAR CABANG": "; ".join(map(str, hits)),
            })
    out = pd.DataFrame(rows, columns=SYSTEMIC_COLS)
    if not out.empty:
        out = out.sort_values("HARI", kind="stable").reset_index(drop=True)
    return out


# ============================================================
# POLA HARI KALENDER ASLI (Senin..Minggu)
# ============================================================

def parse_month_label(label: str | None) -> tuple[int, int] | None:
    """'September 2026' → (2026, 9). Toleran huruf besar/kecil, bulan
    singkat; tanpa tahun/tak dikenali → None."""
    if not label:
        return None
    text = str(label).strip().lower()
    year = None
    for tok in text.replace("-", " ").split():
        if tok.isdigit() and len(tok) == 4:
            year = int(tok)
    month = None
    for name, num in _BULAN.items():
        if name in text:
            month = num
            break
    if month is None or year is None:
        return None
    return (year, month)


def weekday_real(df: pd.DataFrame, label: str | None,
                 key_akhir: int = 31) -> pd.DataFrame:
    """Total waste per HARI KALENDER asli (Senin..Minggu) dari label bulan.

    Butuh label bulan+tahun (detect_month_label file, mis. 'September
    2026'); tak terbaca → frame kosong (caller menampilkan pesan jujur).
    Hari > panjang bulan di-skip (31 pada bulan 30-hari). Kolom
    WEEKDAY_COLS: HARI (nama), TOTAL, N HARI (jumlah tanggal masuk kelas),
    RATA PER HARI (TOTAL ÷ N HARI). Urut Senin..Minggu."""
    ym = parse_month_label(label)
    if ym is None or not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(WEEKDAY_COLS)
    year, month = ym
    n_days = calendar.monthrange(year, month)[1]
    day_cols = [str(d) for d in range(1, min(int(key_akhir), n_days) + 1)
                if str(d) in df.columns]
    if not day_cols:
        return _empty(WEEKDAY_COLS)

    totals = {name: 0.0 for name in _HARI_ID}
    counts = {name: 0 for name in _HARI_ID}
    num = df[day_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    per_day = num.sum(axis=0)
    for d in day_cols:
        wd = _HARI_ID[calendar.weekday(year, month, int(d))]
        totals[wd] += float(per_day[d])
        counts[wd] += 1
    rows = []
    for name in _HARI_ID:
        if counts[name] > 0:
            rows.append({
                "HARI": name, "TOTAL": totals[name],
                "N HARI": counts[name],
                "RATA PER HARI": totals[name] / counts[name],
            })
    return pd.DataFrame(rows, columns=WEEKDAY_COLS)


# ============================================================
# TREN MULTI-BULAN PER CABANG (⑧ — butuh ≥ 2 bulan pembanding)
# ============================================================

def branch_trend(df: pd.DataFrame, months: list[dict] | None,
                 threshold: float = 0.10) -> pd.DataFrame:
    """Total waste per cabang lintas bulan pembanding + bulan berjalan.

    Kolom: NAMA RESTO + satu kolom per bulan (label pembanding, urut
    waktu) + 'Bulan Ini' + TREN (vs pembanding TERBARU): '↗ Naik' /
    '↘ Turun' / '→ Stabil' (batas ±threshold, default 10%), 'Baru'
    (nol/tak ada bulan lalu), 'Pulih' (aktif bulan lalu → nol sekarang).
    Butuh ≥ 2 bulan pembanding (series bermakna); kurang → frame kosong
    (caller menampilkan pesan jujur). Sort 'Bulan Ini' desc.
    """
    ok = [m for m in (months or [])
          if m and not m.get("error") and m.get("agg") is not None
          and not m["agg"].empty]
    if len(ok) < 2 or not isinstance(df, pd.DataFrame) or df.empty \
            or "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns:
        return pd.DataFrame(columns=TREND_BASE_COLS)
    ok.sort(key=lambda m: month_sort_key(m.get("label")))
    cols = ["NAMA RESTO"]
    data: dict[str, dict[str, float]] = {}
    for m in ok:
        label = str(m.get("label") or "Pembanding")
        agg = m["agg"]
        tot = pd.to_numeric(agg["TOTAL"], errors="coerce").fillna(0.0) \
            if "TOTAL" in agg.columns else None
        sub = agg[["NAMA RESTO"]].copy()
        sub["_v"] = tot.to_numpy() if tot is not None else 0.0
        sums = sub.groupby(sub["NAMA RESTO"].astype(str).str.strip())[
            "_v"].sum()
        label_u = label if label not in cols else label + " (2)"
        cols.append(label_u)
        for r, v in sums.items():
            data.setdefault(r, {})[label_u] = float(v)
    # bulan berjalan
    resto = df["NAMA RESTO"].astype(str).str.strip()
    total = pd.to_numeric(df["TOTAL"], errors="coerce").fillna(0.0)
    cur = pd.DataFrame({"r": resto.to_numpy(), "v": total.to_numpy()})
    cur_sums = cur.groupby("r")["v"].sum()
    cols.append("Bulan Ini")
    for r, v in cur_sums.items():
        data.setdefault(r, {})["Bulan Ini"] = float(v)
    last_label = cols[-2]  # pembanding terbaru
    rows = []
    all_restos = set(data.keys()) | set(cur_sums.index)
    for r in sorted(all_restos):
        row = {"NAMA RESTO": r}
        for c in cols[1:]:
            row[c] = data.get(r, {}).get(c, 0.0)
        last = row.get(last_label, 0.0)
        nowv = row.get("Bulan Ini", 0.0)
        if last <= 0 and nowv > 0:
            trend = "Baru"
        elif nowv <= 0 and last > 0:
            trend = "Pulih"
        elif last > 0:
            pct = (nowv - last) / last
            if pct > threshold:
                trend = "↗ Naik"
            elif pct < -threshold:
                trend = "↘ Turun"
            else:
                trend = "→ Stabil"
        else:
            trend = "—"
        row["TREN"] = trend
        rows.append(row)
    out = pd.DataFrame(rows, columns=cols + ["TREN"])
    out = out.sort_values("Bulan Ini", ascending=False,
                          kind="stable").reset_index(drop=True)
    return out


# ============================================================
# SCORECARD KOMPOSIT PER CABANG
# ============================================================

def scorecard(
    df: pd.DataFrame,
    months: list[dict] | None = None,
    key_akhir: int = 31,
    config: dict | None = None,
) -> pd.DataFrame:
    """Tabel komposit per cabang (kolom SCORECARD_COLS, sort KELEBIHAN
    desc = urutan prioritas kunjungan).

    Sumber tiap kolom:
    - TOTAL WASTE / INTENSITAS % / KELEBIHAN: resto_intensity (merge).
    - ALASAN DOMINAN: KETERANGAN share terbesar per cabang (format
      'Handling (42,3%)').
    - ITEM TIAP HARI: banyak baris PROFIL ber-prefix 'Tiap Hari' ( aktif).
    - ANOMALI: banyak baris ANOMALY STATUS ≠ Normal.
    - HARI TERSANGKA: banyak baris BUKTI HARI = YES.
    - BARU / PULIH: pasangan (resto,item) aktif-sekarang-tapi-tidak-bulan-
      lalu / sebaliknya — butuh pembanding; tanpa itu kolom 0 dgn pesan
      di kolom BARU ('perlu pembanding' — jujur).
    - STATUS INPUT: verdict coverage_report.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty(SCORECARD_COLS)
    need = ("NAMA RESTO", "TOTAL")
    if any(c not in df.columns for c in need):
        return _empty(SCORECARD_COLS)

    inten = resto_intensity(df)
    cov = coverage_report(df, months)
    base = inten if not inten.empty else None

    resto = df["NAMA RESTO"].astype(str).str.strip()
    total = pd.to_numeric(df["TOTAL"], errors="coerce").fillna(0.0)
    work = pd.DataFrame({"NAMA RESTO": resto.to_numpy(),
                         "TOTAL": total.to_numpy()})
    restos = sorted(work["NAMA RESTO"].unique())

    # agregat per cabang (hanya baris aktif utk alasan/profil/anomali)
    df2 = df.loc[(total > 0).to_numpy()]
    r2 = df2["NAMA RESTO"].astype(str).str.strip()

    alasan_dom = {}
    if "KETERANGAN" in df2.columns:
        ket = df2["KETERANGAN"].fillna("").astype(str).str.strip()
        piv = pd.DataFrame({"r": r2.to_numpy(), "k": ket.to_numpy(),
                            "v": total[(total > 0).to_numpy()].to_numpy()})
        g = piv.groupby(["r", "k"])["v"].sum().reset_index()
        t = g.groupby("r")["v"].sum()
        g["share"] = g["v"] / g["r"].map(t).where(g["r"].map(t) > 0)
        top = g.sort_values(["r", "share"], ascending=[True, False],
                            kind="stable").groupby("r", sort=True).head(1)
        alasan_dom = {}
        for r, k, s in zip(top["r"], top["k"], top["share"]):
            if pd.notna(s) and t.get(r, 0) > 0:
                # v2.18.0 audit (L-2): format persen SATU BAGIAN — dulu
                # .replace(".", ",") menimpa SELURUH string: KETERANGAN
                # "MKT. PROMO 1.5" rusak jadi "MKT, PROMO 1,5".
                pct_txt = f"{s * 100:.1f}".replace(".", ",")
                alasan_dom[r] = f"{k} ({pct_txt}%)"

    profil_cnt: dict[str, int] = {}
    if "PROFIL" in df2.columns:
        prof = df2["PROFIL"].astype(str)
        is_daily = prof.str.startswith("Tiap Hari").to_numpy()
        profil_cnt = pd.Series(is_daily).groupby(r2.to_numpy()).sum().to_dict()

    anom_cnt: dict[str, int] = {}
    if "ANOMALY STATUS" in df2.columns:
        st = df2["ANOMALY STATUS"].astype(str)
        is_anom = (st != "Normal").to_numpy()
        anom_cnt = pd.Series(is_anom).groupby(
            df2["NAMA RESTO"].astype(str).str.strip().to_numpy()).sum().to_dict()

    tersangka_cnt: dict[str, int] = {}
    if "BUKTI HARI" in df.columns:
        bh = df["BUKTI HARI"].astype(str)
        yes = (bh == "YES").to_numpy()
        tersangka_cnt = pd.Series(yes).groupby(
            df["NAMA RESTO"].astype(str).str.strip().to_numpy()).sum().to_dict()

    # BARU / PULIH vs pembanding terbaru
    baru: dict[str, int] = {}
    pulih: dict[str, int] = {}
    has_months = False
    for m in (months or []):
        if m and not m.get("error") and m.get("agg") is not None \
                and not m["agg"].empty:
            has_months = True
    if has_months:
        cur = _active_pairs(df)
        # v2.18.0 audit (H-3): dulu max() LEKSIKOGRAFIS — "Mei 2026" >
        # "Juni 2026" (M > J) → BARU/PULIH dihitung vs bulan SALAH &
        # kontradiksi dgn TREN (blok di bawah — sudah benar pakai
        # month_sort_key). Kini satu helper _latest_month (parse-aware).
        last = _latest_month(months)
        agg = last["agg"]
        tot = pd.to_numeric(agg["TOTAL"], errors="coerce").fillna(0) \
            if "TOTAL" in agg.columns else None
        if tot is not None:
            sub = agg.loc[(tot > 0).to_numpy(),
                          ["NAMA RESTO", "NAMA BARANG"]].copy()
        else:
            sub = agg[["NAMA RESTO", "NAMA BARANG"]].copy()
        sub["NAMA RESTO"] = sub["NAMA RESTO"].astype(str).str.strip()
        sub["NAMA BARANG"] = sub["NAMA BARANG"].astype(str).str.strip()
        last_pairs = set(map(tuple, sub.drop_duplicates().to_numpy()))
        cur_pairs = set(map(tuple, cur.to_numpy()))
        new_pairs = cur_pairs - last_pairs
        gone_pairs = last_pairs - cur_pairs
        baru = {}
        for r, it in new_pairs:
            baru[r] = baru.get(r, 0) + 1
        pulih = {}
        for r, it in gone_pairs:
            pulih[r] = pulih.get(r, 0) + 1

    cov_map = {str(r["NAMA RESTO"]): str(r["STATUS INPUT"])
               for _, r in cov.iterrows()} if not cov.empty else {}

    # ⑧ v2.13.3: TREN per cabang vs pembanding TERBARU (butuh ≥ 1 bulan)
    trend_map: dict[str, str] = {}
    if has_months:
        cur_tot = work.groupby("NAMA RESTO")["TOTAL"].sum()
        last_m = max(
            (m for m in (months or [])
             if m and not m.get("error") and m.get("agg") is not None
             and not m["agg"].empty),
            key=lambda m: month_sort_key(m.get("label")))
        agg = last_m["agg"]
        lt = pd.to_numeric(agg["TOTAL"], errors="coerce") \
            if "TOTAL" in agg.columns else None
        lsub = agg[["NAMA RESTO"]].copy()
        lsub["_v"] = lt.fillna(0.0).to_numpy() if lt is not None else 0.0
        last_tot = lsub.groupby(
            lsub["NAMA RESTO"].astype(str).str.strip())["_v"].sum()
        th = 0.10
        try:
            th = abs(float((config or {}).get("thresholds", {}).get(
                "TH_TREND", 0.10)))
        except (TypeError, ValueError):
            th = 0.10
        for r in restos:
            nowv = float(cur_tot.get(r, 0.0))
            last = float(last_tot.get(r, 0.0))
            if last <= 0 and nowv > 0:
                trend_map[r] = "Baru"
            elif nowv <= 0 and last > 0:
                trend_map[r] = "Pulih"
            elif last > 0:
                pct = (nowv - last) / last
                trend_map[r] = ("↗ Naik" if pct > th
                                else "↘ Turun" if pct < -th
                                else "→ Stabil")
            else:
                trend_map[r] = "—"

    rows = []
    # v2.13.7 (perf-audit B): O(n_resto × n_baris) — work.loc[mask].sum()
    # per cabang (20 × 25.901 scan) → satu groupby. restos ⊆ work by
    # konstruksi → .get(r, 0.0) identik sum() baris-kosong = 0.0.
    tot_by_resto = work.groupby("NAMA RESTO")["TOTAL"].sum()
    for r in restos:
        total_waste = float(tot_by_resto.get(r, 0.0))
        rows.append({
            "RANK": 0, "NAMA RESTO": r, "TOTAL WASTE": total_waste,
            "INTENSITAS %": np.nan, "KELEBIHAN": np.nan,
            "ALASAN DOMINAN": alasan_dom.get(r, "—"),
            "ITEM TIAP HARI": int(profil_cnt.get(r, 0)),
            "ANOMALI": int(anom_cnt.get(r, 0)),
            "HARI TERSANGKA": int(tersangka_cnt.get(r, 0)),
            "BARU": int(baru.get(r, 0)),
            "PULIH": int(pulih.get(r, 0)),
            "STATUS INPUT": cov_map.get(r, "—"),
            "TREN": trend_map.get(r, "—"),
        })
    out = pd.DataFrame(rows, columns=SCORECARD_COLS)
    if base is not None:
        lookup = {
            str(r): (float(iv), float(kv))
            for r, iv, kv in zip(base["NAMA RESTO"], base["INTENSITAS %"],
                                 base["KELEBIHAN"])}
        out["INTENSITAS %"] = [
            lookup.get(r, (np.nan, np.nan))[0]
            for r in out["NAMA RESTO"]]
        out["KELEBIHAN"] = [
            lookup.get(r, (np.nan, np.nan))[1]
            for r in out["NAMA RESTO"]]
    out = out.sort_values(
        ["KELEBIHAN", "TOTAL WASTE"], ascending=False, na_position="last",
        kind="stable").reset_index(drop=True)
    out["RANK"] = range(1, len(out) + 1)
    if not has_months:
        # jujur tanpa pembanding: kolom BARU/PULIH tak bermakna
        out["BARU"] = 0
        out["PULIH"] = 0
    return out[SCORECARD_COLS]
