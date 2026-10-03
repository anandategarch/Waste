"""
priority.py — money view + prioritas magnitude (gelombang fitur v2.5.0).

Motivasi (temuan EVAL-DRILLDOWN-ANALISA): baris berstatus "Prioritas Tinggi"
hanya membawa ~0,5% dari total waste, sementara baris waste terbesar
(KULIT PANGSIT 299.855 GR, SURAI NAGA 295.937, dst.) berstatus "Normal".
Skor anomali 12-sinyal dan magnitude TIDAK sejalan — modul ini menambah
lensa "magnitude first" di atas df detail hasil pipeline:

- focus_score / focus_class : prioritas gabungan per baris 0..100
  (60% percentile rank TOTAL + 40% skor anomali 0..19).
- money_view                : tabel Pareto baris waste terbesar APA PUN
  status anomalinya (Share %, Kumulatif %, FOCUS SCORE / FOCUS CLASS).
- benchmark_items           : benchmark item x cabang vs peer AKTIF — median
  hanya dari cabang yang benar-benar punya waste. Memperbaiki celah lama:
  peer median yang dihitung termasuk cabang nol (90,6% baris TOTAL=0)
  membuat sinyal peer mati justru untuk event langka.
- reason_profile / reason_share : profil alasan (KETERANGAN) per cabang.
- susut_benchmark           : ranking SUSUT per cabang.

Urutan kolom output PERSIS kontrak di tiap docstring — ui/ bergantung
padanya. Semua fungsi DEFENSIF: df kosong / kolom wajib hilang → hasil
kosong dengan kolom output yang tetap, tidak pernah raise.
"""

from __future__ import annotations

import pandas as pd

# ============================================================
# KONSTANTA KONTRAK (dibaca ui/)
# ============================================================

MAX_ANOMALY_SCORE = 19
FOCUS_HIGH = 70.0
FOCUS_MID = 50.0

# Bobot focus_score: 60% magnitude + 40% anomali.
MAG_WEIGHT = 0.60
ANOM_WEIGHT = 0.40

MONEY_VIEW_COLUMNS = [
    "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN", "SATUAN",
    "TOTAL", "MAX", "Count Hari", "ANOMALY SCORE", "ANOMALY STATUS",
    "Share %", "Kumulatif %", "FOCUS SCORE", "FOCUS CLASS",
]

BENCHMARK_ITEMS_COLUMNS = [
    "NAMA BARANG", "NAMA RESTO", "TOTAL", "Peer Aktif",
    "Peer Median (aktif)", "Rasio vs Peer", "Flag",
]

SUSUT_BENCHMARK_COLUMNS = [
    "NAMA RESTO", "SUSUT", "Share Cabang %", "Rank",
]

REASON_PROFILE_STATIC_COLUMNS = [
    "NAMA RESTO", "TOTAL", "SUSUT %", "Alasan Dominan",
]

# 10 kolom dasar yang wajib ada di input money_view (output minus turunan).
_MONEY_VIEW_BASE = MONEY_VIEW_COLUMNS[:10]


# ============================================================
# HELPER DEFENSIF
# ============================================================

def _missing_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Daftar kolom wajib yang tidak ada di df."""
    return [col for col in required if col not in df.columns]


def _numeric(series: pd.Series) -> pd.Series:
    """Koersi numerik defensif: non-numerik/NaN → 0.0, tanpa raise."""
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _text(series: pd.Series) -> pd.Series:
    """Koersi teks defensif: NaN → string kosong (bukan 'nan').

    v2.5.1 (DQ-M1): whitespace dinormalisasi (NBSP/zero-width/spasi ganda)
    supaya kategori kembar-visual tidak terpecah di groupby/pivot.
    """
    from .utils import norm_text
    return series.fillna("").astype(str).map(norm_text)


# ============================================================
# FOCUS SCORE — prioritas gabungan magnitude + anomali
# ============================================================

def focus_score(df: pd.DataFrame) -> pd.Series:
    """Skor prioritas gabungan 0..100 per BARIS: 60% magnitude + 40% anomali.

    - magnitude_pct = percentile rank TOTAL DI HITUNG DI SUBSET BARIS
      AKTIF (TOTAL > 0) — v2.5.1 (MO-M2): dulu rank dihitung atas SEMUA
      baris termasuk 23.470 baris nol (90,6% data), sehingga semua baris
      aktif menempati percentile 90,6–100 dan komponen '60% magnitude'
      hanya merentang 5,4 poin (54,4–60,0) — daya pembeda magnitudo antar
      baris aktif nyaris nol. Kini baris nol → magnitude 0, baris aktif
      → rank relatif di antara baris aktif (pembeda penuh 0–100).
      method='average', pct=True; subset aktif kosong → semua 0.
    - anomaly_pct = clip(ANOMALY SCORE, 0, MAX_ANOMALY_SCORE)
      / MAX_ANOMALY_SCORE * 100; kolom hilang / NaN → 0.

    Args:
        df: DataFrame detail; kolom TOTAL dan ANOMALY SCORE opsional
            (kolom hilang → komponen terkait bernilai 0).

    Returns:
        Series float 0..100 sejajar index df.
    """
    if df.empty:
        return pd.Series(dtype=float, index=df.index, name="FOCUS SCORE")

    if "TOTAL" in df.columns:
        total = pd.to_numeric(df["TOTAL"], errors="coerce")
        magnitude = pd.Series(0.0, index=df.index)
        active = total > 0
        if bool(active.any()):
            magnitude.loc[active] = (
                total.loc[active].rank(method="average", pct=True) * 100.0
            )
    else:
        magnitude = pd.Series(0.0, index=df.index)

    if "ANOMALY SCORE" in df.columns:
        score = pd.to_numeric(df["ANOMALY SCORE"], errors="coerce")
        anomaly = (
            score.clip(lower=0.0, upper=float(MAX_ANOMALY_SCORE))
            / MAX_ANOMALY_SCORE * 100.0
        ).fillna(0.0)
    else:
        anomaly = pd.Series(0.0, index=df.index)

    out = MAG_WEIGHT * magnitude + ANOM_WEIGHT * anomaly
    return out.astype(float).rename("FOCUS SCORE")


def focus_class(score: float) -> str:
    """Label kelas fokus dari skor focus_score.

    >= FOCUS_HIGH → 'Fokus Utama'; >= FOCUS_MID → 'Fokus Sekunder';
    else 'Rutin'. Skor NaN jatuh ke 'Rutin' (perbandingan False).
    """
    if score >= FOCUS_HIGH:
        return "Fokus Utama"
    if score >= FOCUS_MID:
        return "Fokus Sekunder"
    return "Rutin"


# ============================================================
# MONEY VIEW — tabel prioritas magnitude (Pareto baris terbesar)
# ============================================================

def money_view(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """Tabel prioritas magnitude — baris terbesar APA PUN status anomalinya.

    Hanya baris TOTAL > 0. Kolom output PERSIS ``MONEY_VIEW_COLUMNS``:
    ['NAMA RESTO','NAMA BARANG','JENIS','KETERANGAN','SATUAN','TOTAL','MAX',
    'Count Hari','ANOMALY SCORE','ANOMALY STATUS','Share %','Kumulatif %',
    'FOCUS SCORE','FOCUS CLASS'].

    - Share % = TOTAL / sum(TOTAL seluruh df termasuk baris 0) * 100
      (baris 0 menyumbang 0 — penyebut identik jumlah baris positif;
      level agregasi = BARIS resto×item×jenis×keterangan).
    - Kumulatif % = cumsum Share % (prefix: identik dihitung sebelum /
      sesudah pemotongan top_n).
    - Sort TOTAL desc (stabil); top_n memotong (None = semua).
    - FOCUS SCORE dihitung focus_score(df) pada df PENUH (termasuk baris
      TOTAL=0) supaya skor per baris stabil, tidak bergantung top_n;
      rank magnitude dihitung di subset TOTAL>0 (lihat focus_score).

    Args:
        df: DataFrame detail dengan 10 kolom dasar MONEY_VIEW_COLUMNS.
        top_n: jumlah baris teratas yang ditampilkan; None = semua.

    Returns:
        DataFrame MONEY_VIEW_COLUMNS; kosong (kolom tetap) bila df kosong /
        kolom wajib hilang / tidak ada baris TOTAL > 0.
    """
    if df.empty or _missing_columns(df, _MONEY_VIEW_BASE):
        return pd.DataFrame(columns=MONEY_VIEW_COLUMNS)

    total_num = _numeric(df["TOTAL"])
    denom = float(total_num.sum())
    mask = (total_num > 0).to_numpy()
    if not mask.any() or denom <= 0.0:
        return pd.DataFrame(columns=MONEY_VIEW_COLUMNS)

    focus_vals = focus_score(df).to_numpy()

    work = df.loc[mask].copy()
    work["_sort_total"] = total_num.to_numpy()[mask]
    work["_focus"] = focus_vals[mask]
    work = work.sort_values("_sort_total", ascending=False, kind="stable")
    if top_n is not None:
        work = work.iloc[: max(int(top_n), 0)]
    if work.empty:
        return pd.DataFrame(columns=MONEY_VIEW_COLUMNS)

    share = work["_sort_total"] / denom * 100.0
    out = work[_MONEY_VIEW_BASE].reset_index(drop=True)
    out["TOTAL"] = work["_sort_total"].to_numpy()
    out["Share %"] = share.to_numpy()
    out["Kumulatif %"] = share.cumsum().to_numpy()
    out["FOCUS SCORE"] = work["_focus"].to_numpy()
    out["FOCUS CLASS"] = [focus_class(v) for v in work["_focus"].to_numpy()]
    return out[MONEY_VIEW_COLUMNS]


# ============================================================
# BENCHMARK ITEM — item x cabang vs peer AKTIF
# ============================================================

def benchmark_items(
    df: pd.DataFrame,
    min_peers: int = 3,
    ratio_flag: float = 2.0,
) -> pd.DataFrame:
    """Benchmark item x cabang vs peer AKTIF (median hanya cabang ber-waste).

    - Agregasi dulu: total per (NAMA BARANG, NAMA RESTO) hanya baris
      TOTAL > 0 (baris split SOURCE DATA dijumlah; baris nol tidak masuk).
    - Per item: 'Peer Aktif' = jumlah resto dengan total > 0;
      'Peer Median (aktif)' = median total resto-resto tersebut.
    - Rasio vs Peer = TOTAL / peer median; NaN bila median 0/NaN.
    - Flag: 'Di Atas Peer' (rasio >= ratio_flag DAN Peer Aktif >=
      min_peers); 'Sesuai' (Peer Aktif >= min_peers); 'Peer Kecil'
      (Peer Aktif < min_peers).
    - Sort Rasio desc (NaN di akhir), tie-break TOTAL desc.

    Args:
        df: DataFrame detail (kolom wajib: NAMA BARANG, NAMA RESTO, TOTAL).
        min_peers: jumlah peer aktif minimum agar benchmark dianggap valid.
        ratio_flag: rasio minimum terhadap median untuk 'Di Atas Peer'.

    Returns:
        DataFrame BENCHMARK_ITEMS_COLUMNS; kosong (kolom tetap) bila df
        kosong / kolom wajib hilang / tidak ada baris TOTAL > 0.
    """
    required = ["NAMA BARANG", "NAMA RESTO", "TOTAL"]
    if df.empty or _missing_columns(df, required):
        return pd.DataFrame(columns=BENCHMARK_ITEMS_COLUMNS)

    total = _numeric(df["TOTAL"])
    mask = (total > 0).to_numpy()
    if not mask.any():
        return pd.DataFrame(columns=BENCHMARK_ITEMS_COLUMNS)

    work = pd.DataFrame({
        "NAMA BARANG": df["NAMA BARANG"].to_numpy()[mask],
        "NAMA RESTO": df["NAMA RESTO"].to_numpy()[mask],
        "TOTAL": total.to_numpy()[mask],
    })

    # groupby membuang kunci NaN (defensif, tidak pernah raise)
    agg = work.groupby(
        ["NAMA BARANG", "NAMA RESTO"], as_index=False, sort=True
    )["TOTAL"].sum()

    grp = agg.groupby("NAMA BARANG", sort=True)["TOTAL"]
    agg["Peer Aktif"] = grp.transform("size").astype(int)
    agg["Peer Median (aktif)"] = grp.transform("median")

    med = agg["Peer Median (aktif)"]
    agg["Rasio vs Peer"] = agg["TOTAL"] / med.where(med > 0)

    peers_ok = agg["Peer Aktif"] >= min_peers
    above = peers_ok & (agg["Rasio vs Peer"] >= ratio_flag)
    flag = pd.Series("Peer Kecil", index=agg.index, dtype=object)
    flag[peers_ok] = "Sesuai"
    flag[above] = "Di Atas Peer"
    agg["Flag"] = flag

    # sort dua-pass stabil: kunci kedua dulu (TOTAL desc), lalu kunci utama
    # (Rasio desc, NaN akhir) — hasil = rasio desc, tie-break TOTAL desc.
    res = agg.sort_values("TOTAL", ascending=False, kind="stable")
    res = res.sort_values(
        "Rasio vs Peer", ascending=False, na_position="last", kind="stable"
    )
    res = res.reset_index(drop=True)
    return res[BENCHMARK_ITEMS_COLUMNS]


# ============================================================
# PROFIL ALASAN PER CABANG
# ============================================================

def reason_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Profil alasan per cabang — pivot TOTAL per (NAMA RESTO x KETERANGAN).

    - Kolom dinamis = tiap KETERANGAN unik (nilai sum TOTAL, fillna 0),
      urut kolom by total global desc; lalu kolom statis 'TOTAL' (total
      waste resto, semua JENIS), 'SUSUT %' (share baris JENIS='SUSUT' dari
      TOTAL resto — float saja), 'Alasan Dominan' (keterangan bernilai
      terbesar resto; format 'KETERANGAN (12.3%)' 1 desimal; '(kosong)'
      bila semua 0).
    - Kolom pertama 'NAMA RESTO'; baris = tiap resto unik di df (resto
      yang tidak punya waste tampil dengan profil '(kosong)').
    - Sort 'TOTAL' desc.

    Args:
        df: DataFrame detail (wajib: NAMA RESTO, KETERANGAN, JENIS, TOTAL).

    Returns:
        DataFrame ['NAMA RESTO', <kolom KETERANGAN dinamis>, 'TOTAL',
        'SUSUT %', 'Alasan Dominan']; kosong (kolom statis tetap) bila df
        kosong / kolom wajib hilang.
    """
    required = ["NAMA RESTO", "KETERANGAN", "JENIS", "TOTAL"]
    if df.empty or _missing_columns(df, required):
        return pd.DataFrame(columns=REASON_PROFILE_STATIC_COLUMNS)

    work = pd.DataFrame({
        "NAMA RESTO": _text(df["NAMA RESTO"]).to_numpy(),
        "KETERANGAN": _text(df["KETERANGAN"]).to_numpy(),
        "JENIS": _text(df["JENIS"]).to_numpy(),
        "TOTAL": _numeric(df["TOTAL"]).to_numpy(),
    })

    pivot = work.pivot_table(
        index="NAMA RESTO", columns="KETERANGAN", values="TOTAL",
        aggfunc="sum", fill_value=0.0,
    )
    # Urut kolom keterangan by total global desc (tie: urutan nama asc).
    global_tot = work.groupby("KETERANGAN", sort=True)["TOTAL"].sum()
    order = global_tot.sort_values(ascending=False, kind="stable")
    pivot = pivot.reindex(columns=list(order.index), fill_value=0.0)

    resto_total = work.groupby("NAMA RESTO", sort=True)["TOTAL"].sum()
    susut_total = (
        work.loc[work["JENIS"] == "SUSUT"]
        .groupby("NAMA RESTO", sort=True)["TOTAL"]
        .sum()
    )

    prof = pivot.reset_index()
    tot = prof["NAMA RESTO"].map(resto_total).fillna(0.0)
    sus = prof["NAMA RESTO"].map(susut_total).fillna(0.0)
    prof["TOTAL"] = tot
    prof["SUSUT %"] = (sus / tot.where(tot > 0) * 100.0).fillna(0.0)

    tot_arr = tot.to_numpy()
    if pivot.shape[1] > 0:
        dom_val = pivot.max(axis=1).to_numpy()
        dom_name = pivot.idxmax(axis=1).to_numpy()
        labels = [
            f"{name} ({val / t * 100.0:.1f}%)" if (val > 0.0 and t > 0.0)
            else "(kosong)"
            for name, val, t in zip(dom_name, dom_val, tot_arr)
        ]
    else:
        labels = ["(kosong)"] * len(prof)
    prof["Alasan Dominan"] = labels

    prof = prof.sort_values("TOTAL", ascending=False, kind="stable")
    return prof.reset_index(drop=True)


def reason_share(df: pd.DataFrame, cabang: str) -> pd.Series:
    """Share % TOTAL per KETERANGAN untuk satu cabang (hanya baris TOTAL > 0).

    Sort desc. Series kosong (float, name 'Share %') bila cabang tidak ada
    di df / cabang tidak punya waste / df kosong / kolom wajib hilang.

    Args:
        df: DataFrame detail (wajib: NAMA RESTO, KETERANGAN, TOTAL).
        cabang: nama NAMA RESTO yang mau dianalisa.

    Returns:
        Series float ber-index KETERANGAN, nilai = persen dari total waste
        cabang tersebut (jumlah 100).
    """
    required = ["NAMA RESTO", "KETERANGAN", "TOTAL"]
    empty = pd.Series(dtype=float, name="Share %")
    if df.empty or _missing_columns(df, required):
        return empty

    total = _numeric(df["TOTAL"])
    mask = (total > 0).to_numpy()
    if not mask.any():
        return empty

    resto = _text(df["NAMA RESTO"]).to_numpy()[mask]
    ket = _text(df["KETERANGAN"]).to_numpy()[mask]
    sel = resto == cabang
    if not sel.any():
        return empty

    sub = pd.DataFrame({
        "KETERANGAN": ket[sel],
        "TOTAL": total.to_numpy()[mask][sel],
    })
    sums = sub.groupby("KETERANGAN", sort=True)["TOTAL"].sum()
    denom = float(sums.sum())
    if denom <= 0.0:
        return empty

    out = (sums / denom * 100.0).sort_values(ascending=False, kind="stable")
    return out.astype(float).rename("Share %")


# ============================================================
# BENCHMARK SUSUT PER CABANG
# ============================================================

def susut_benchmark(df: pd.DataFrame) -> pd.DataFrame:
    """Ranking SUSUT per cabang.

    - SUSUT = sum TOTAL baris JENIS='SUSUT' per resto; hanya resto dengan
      SUSUT > 0.
    - Share Cabang % = SUSUT / total waste resto * 100.
    - Sort SUSUT desc (stabil); Rank = 1..n.

    Args:
        df: DataFrame detail (wajib: NAMA RESTO, JENIS, TOTAL).

    Returns:
        DataFrame SUSUT_BENCHMARK_COLUMNS; kosong (kolom tetap) bila df
        kosong / kolom wajib hilang / tidak ada resto dengan SUSUT > 0.
    """
    required = ["NAMA RESTO", "JENIS", "TOTAL"]
    if df.empty or _missing_columns(df, required):
        return pd.DataFrame(columns=SUSUT_BENCHMARK_COLUMNS)

    work = pd.DataFrame({
        "NAMA RESTO": _text(df["NAMA RESTO"]).to_numpy(),
        "JENIS": _text(df["JENIS"]).to_numpy(),
        "TOTAL": _numeric(df["TOTAL"]).to_numpy(),
    })

    susut = (
        work.loc[work["JENIS"] == "SUSUT"]
        .groupby("NAMA RESTO", sort=True)["TOTAL"]
        .sum()
    )
    susut = susut[susut > 0]
    if susut.empty:
        return pd.DataFrame(columns=SUSUT_BENCHMARK_COLUMNS)

    all_total = (
        work.groupby("NAMA RESTO", sort=True)["TOTAL"].sum().reindex(susut.index)
    )
    share = susut / all_total.where(all_total > 0) * 100.0

    res = pd.DataFrame({
        "NAMA RESTO": susut.index.to_numpy(),
        "SUSUT": susut.to_numpy(),
        "Share Cabang %": share.to_numpy(),
    })
    res = res.sort_values("SUSUT", ascending=False, kind="stable")
    res = res.reset_index(drop=True)
    res["Rank"] = range(1, len(res) + 1)
    return res[SUSUT_BENCHMARK_COLUMNS]
