"""
data_quality.py — pemeriksaan data quality otomatis pada df Detail (v2.5.0).

Audit manual (worklog EVAL-DRILLDOWN-ANALISA) menemukan masalah data yang
selama ini lolos dari pipeline dan melemahkan sinyal anomali tanpa terdeteksi:
  - SATUAN 'PACK\\xa0' (2.033 baris) vs 'PACK' (6 baris): duplikat satuan
    tersembunyi — beda karakter tak terlihat, agregasi per satuan terpecah.
  - SOURCE DATA 'WASTE BAHAN dan PACKAGING' (11.654) vs 'WASTE BAHAN DAN
    PACKAGING' (432): sumber sama dengan kapitalisasi beda → peer group
    (stage 7) terfragmentasi.
  - KETERANGAN 'Kualitas' (97) adalah prefix case-insensitive dari
    'Kualitas Internal'/'Kualitas Eksternal' → kategori pecah.
  - 119 baris TOTAL > 0 dengan TOTAL BOM NaN/<= 0 → waste tidak terlihat
    oleh sinyal BOM (S6/S7).
  - Business key (NAMA RESTO, NAMA BARANG, JENIS, KETERANGAN) terpeceh antar
    SOURCE DATA → spike dan rasio BOM per baris terdilusi.
  - 90%+ baris TOTAL = 0 → struktur placeholder normal (konteks, bukan error).

Modul ini murni read-only dan defensif: tidak mengubah df, tidak pernah
raise, dan setiap pemeriksaan di-skip diam-diam bila kolom yang diperlukannya
hilang atau error tak terduga terjadi — pemeriksaan lain tetap berjalan.
Hasil berupa CheckResult (kode stabil + severity + judul + detail + count +
maks 5 contoh) untuk ditampilkan UI v2.5.0 (ikon ditambahkan UI, bukan di
sini). Pemeriksaan tanpa temuan (count == 0) tidak di-emit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

_MAX_SAMPLE = 5
_DAY_NAMES = frozenset(str(d) for d in range(1, 32))
_SPLIT_KEYS = ("NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN")


@dataclass(frozen=True)
class CheckResult:
    """Hasil satu pemeriksaan data quality (immutable).

    Attributes:
        code: kode stabil, mis. 'DQ_NBSP_SATUAN' (tidak berubah antar versi).
        severity: 'error' | 'warning' | 'info' (urutan tampil, lihat
            SEVERITY_ORDER).
        title: judul pendek bahasa Indonesia (tanpa ikon — UI menambahkan).
        detail: 1-3 kalimat penjelasan + rekomendasi singkat.
        count: jumlah baris/grup terdampak (0 bila tidak terdampak).
        sample: maks 5 contoh pendek (string).
    """

    code: str
    severity: str
    title: str
    detail: str
    count: int = 0
    sample: tuple[str, ...] = ()


# ============================================================
# HELPER KECIL (semua defensif — tidak pernah raise)
# ============================================================

def _safe_str(v) -> str:
    """str(v) yang aman: None/NaN -> string kosong, sisanya di-strip."""
    try:
        if v is None or pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        return str(v).strip()
    except Exception:  # noqa: BLE001 — kontrak modul: helper tidak boleh raise
        return ""


def _fmt_num(v) -> str:
    """Format angka gaya Indonesia: ribuan '.', desimal ',' (maks 1 desimal)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if not math.isfinite(f):
        return str(v)
    if f.is_integer():
        return f"{int(f):,}".replace(",", ".")
    return f"{f:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(p: float) -> str:
    """Persentase 1 desimal, koma sebagai desimal (gaya Indonesia)."""
    return f"{p:.1f}".replace(".", ",")


def _col_values(df: pd.DataFrame, col: str) -> list[str]:
    """Nilai kolom sebagai list string posisional; kolom hilang -> ['', ...]."""
    if col not in df.columns:
        return [""] * len(df)
    return [_safe_str(v) for v in df[col].tolist()]


def _str_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Series string dengan baris NaN tetap NaN (bukan string 'nan')."""
    s = df[col]
    return s.astype(str).where(s.notna())


def _counts(values) -> list[tuple[str, int]]:
    """Distinct value -> jumlah; urut count desc lalu value asc (deterministik)."""
    tally: dict[str, int] = {}
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        tally[v] = tally.get(v, 0) + 1
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))


def _coerce_key_akhir(key_akhir) -> int | None:
    """key_akhir valid 1..31, selain itu None (semua kolom hari diperiksa)."""
    if key_akhir is None:
        return None
    try:
        ka = int(key_akhir)
    except (TypeError, ValueError):
        return None
    return ka if 1 <= ka <= 31 else None


def _day_columns(df: pd.DataFrame, key_akhir) -> list:
    """Kolom hari '1'..'31' yang ada; dibatasi 1..key_akhir bila key_akhir valid."""
    ka = _coerce_key_akhir(key_akhir)
    out = []
    for c in df.columns:
        name = str(c).strip()
        if name not in _DAY_NAMES:
            continue
        if ka is not None and int(name) > ka:
            continue
        out.append(c)
    return out


# ============================================================
# CHECK 1 — DQ_NEGATIVE (error)
# ============================================================

def _check_negative(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Nilai negatif pada kolom TOTAL atau kolom hari '1'..'31' yang ada."""
    day_cols = _day_columns(df, key_akhir)
    parts: list[pd.Series] = []
    if "TOTAL" in df.columns:
        parts.append(pd.to_numeric(df["TOTAL"], errors="coerce"))
    for col in day_cols:
        parts.append(pd.to_numeric(df[col], errors="coerce"))
    if not parts:
        return None

    num = pd.concat(parts, axis=1, ignore_index=True)
    neg = num < 0
    mask = neg.any(axis=1)
    count = int(mask.sum())
    if count == 0:
        return None

    # per baris: nilai negatif terbesar magnitude-nya (paling mencolok)
    worst = num.where(neg).min(axis=1)[mask].sort_values(kind="stable")
    items = _col_values(df, "NAMA BARANG")
    restos = _col_values(df, "NAMA RESTO")
    sample = tuple(
        f"{items[p] or '-'} @ {restos[p] or '-'} = {_fmt_num(v)}"
        for p, v in worst.head(_MAX_SAMPLE).items()
    )
    return CheckResult(
        code="DQ_NEGATIVE",
        severity="error",
        title="Nilai negatif pada TOTAL / kolom hari",
        detail=(
            f"Terdapat {_fmt_num(count)} baris dengan nilai negatif pada kolom "
            "TOTAL atau kolom hari. Nilai negatif tidak valid untuk rekap waste "
            "dan mendistorsi TOTAL/MAX/AVG beserta sinyal turunannya. Periksa "
            "dan perbaiki di sumber, atau konfirmasi bila memang koreksi/retur."
        ),
        count=count,
        sample=sample,
    )


# ============================================================
# CHECK 2 — DQ_NBSP_SATUAN (warning)
# ============================================================

def _check_nbsp_satuan(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """SATUAN kotor (NBSP/zero-width/spasi ganda/leading-trailing) atau
    duplikat tersembunyi: ejaan berbeda yang sama setelah whitespace
    dinormalisasi (mis. 'PACK\\xa0' vs 'PACK')."""
    if "SATUAN" not in df.columns:
        return None
    raw = _str_series(df, "SATUAN")
    if int(raw.notna().sum()) == 0:
        return None

    dirty = (
        raw.str.contains("\xa0", regex=False, na=False)
        | raw.str.contains("\u200b", regex=False, na=False)
        | raw.str.contains("  ", regex=False, na=False)
        | (raw.str.strip() != raw)
    )
    norm = (
        raw.str.replace("\xa0", " ", regex=False)
        .str.replace("\u200b", " ", regex=False)
        .str.split()
        .str.join(" ")
    )
    grp = pd.DataFrame({"raw": raw, "norm": norm}).dropna(subset=["raw"])
    nunique = grp.groupby("norm", dropna=False)["raw"].nunique()
    coll_norms = nunique[nunique >= 2].index
    affected = (dirty | norm.isin(coll_norms)) & raw.notna()
    count = int(affected.sum())
    if count == 0:
        return None

    sample = tuple(
        f"{v!r} ({n} baris)" for v, n in _counts(raw[affected])[:_MAX_SAMPLE]
    )
    return CheckResult(
        code="DQ_NBSP_SATUAN",
        severity="warning",
        title="Satuan duplikat tersembunyi (karakter tak terlihat)",
        detail=(
            f"Terdapat {_fmt_num(count)} baris SATUAN dengan karakter tak "
            "terlihat (non-breaking space/zero-width/spasi ganda/spasi di "
            "ujung) atau yang hanya berbeda whitespace dari ejaan satuan lain "
            "— duplikat satuan tersembunyi yang memecah agregasi per satuan. "
            "Normalisasi SATUAN di sumber: hapus karakter tak terlihat dan "
            "rapikan spasi."
        ),
        count=count,
        sample=sample,
    )


# ============================================================
# CHECK 3 — DQ_SOURCE_VARIANT (warning)
# ============================================================

def _check_source_variant(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Kelompok SOURCE DATA (casefold+strip) dengan >= 2 ejaan mentah berbeda."""
    if "SOURCE DATA" not in df.columns:
        return None
    raw = _str_series(df, "SOURCE DATA")
    key = raw.str.strip().str.casefold()
    grp = pd.DataFrame({"raw": raw, "key": key}).dropna(subset=["raw"])

    nunique = grp.groupby("key", dropna=False)["raw"].nunique()
    variant = nunique[nunique >= 2]
    if variant.empty:
        return None
    sizes = grp.groupby("key", dropna=False).size()
    affected = key.isin(variant.index)
    count = int(affected.sum())
    if count == 0:
        return None

    ordered_keys = sorted(variant.index, key=lambda k: (-int(sizes[k]), str(k)))
    sample = []
    for k in ordered_keys[:_MAX_SAMPLE]:
        parts = [
            f"{v} ({n})"
            for v, n in _counts(grp.loc[grp["key"] == k, "raw"])[:_MAX_SAMPLE]
        ]
        sample.append(" ~ ".join(parts))
    return CheckResult(
        code="DQ_SOURCE_VARIANT",
        severity="warning",
        title="SOURCE DATA beda kapitalisasi/whitespace",
        detail=(
            f"Terdapat {_fmt_num(count)} baris dalam {_fmt_num(len(variant))} "
            "kelompok SOURCE DATA yang ditulis dengan kapitalisasi/whitespace "
            "berbeda untuk sumber yang sama. Peer group (yang memuat SOURCE "
            "DATA) dan agregasi per sumber ikut terpecah. Seragamkan penulisan "
            "SOURCE DATA di sumber."
        ),
        count=count,
        sample=tuple(sample),
    )


# ============================================================
# CHECK 4 — DQ_KETERANGAN_PREFIX (info)
# ============================================================

def _check_keterangan_prefix(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Keterangan yang merupakan prefix case-insensitive dari keterangan lain
    (panjang beda, bukan sekadar beda kapitalisasi)."""
    if "KETERANGAN" not in df.columns:
        return None
    ket = _str_series(df, "KETERANGAN").str.strip()
    valid = ket.notna() & (ket != "")
    distinct = sorted(set(ket[valid]))
    if len(distinct) < 2:
        return None

    by_casefold: dict[str, list[str]] = {}
    for v in distinct:
        by_casefold.setdefault(v.casefold(), []).append(v)
    pairs: list[tuple[str, str]] = []
    for b in distinct:
        kb = b.casefold()
        for i in range(1, len(kb)):
            for a in by_casefold.get(kb[:i], ()):
                if a != b:
                    pairs.append((a, b))
    if not pairs:
        return None

    shorter = {a for a, _ in pairs}
    mask = valid & ket.isin(shorter)
    count = int(mask.sum())
    if count == 0:
        return None

    rows_map = dict(_counts(ket[mask]))
    pairs_sorted = sorted(
        pairs, key=lambda ab: (-rows_map.get(ab[0], 0), ab[0], ab[1])
    )
    sample = tuple(f"{a} ⊂ {b}" for a, b in pairs_sorted[:_MAX_SAMPLE])
    contoh = "; ".join(f"'{a}' ⊂ '{b}'" for a, b in pairs_sorted[:3])
    return CheckResult(
        code="DQ_KETERANGAN_PREFIX",
        severity="info",
        title="KETERANGAN terfragmentasi (prefix)",
        detail=(
            f"Terdapat {_fmt_num(count)} baris dengan keterangan pecah yang "
            f"merupakan prefix case-insensitive dari keterangan lain ({contoh}). "
            "Kategori jadi terfragmentasi dan analisa per-alasan terpecah. "
            "Rapikan kategori KETERANGAN di sumber: arahkan baris pendek ke "
            "nilai yang lebih spesifik."
        ),
        count=count,
        sample=sample,
    )


# ============================================================
# CHECK 5 — DQ_WASTE_NO_BOM (warning)
# ============================================================

def _check_waste_no_bom(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Baris TOTAL > 0 dengan TOTAL BOM NaN atau <= 0 (tak terlihat oleh
    sinyal BOM)."""
    if "TOTAL" not in df.columns or "TOTAL BOM" not in df.columns:
        return None
    total = pd.to_numeric(df["TOTAL"], errors="coerce")
    bom = pd.to_numeric(df["TOTAL BOM"], errors="coerce")
    mask = (total > 0) & (bom.isna() | (bom <= 0))
    count = int(mask.sum())
    if count == 0:
        return None

    qty = float(total[mask].sum())
    items = _col_values(df, "NAMA BARANG")
    restos = _col_values(df, "NAMA RESTO")
    order = total[mask].sort_values(ascending=False, kind="stable")
    sample = tuple(
        f"{items[p] or '-'} @ {restos[p] or '-'} ({_fmt_num(v)})"
        for p, v in order.head(_MAX_SAMPLE).items()
    )
    return CheckResult(
        code="DQ_WASTE_NO_BOM",
        severity="warning",
        title="Waste aktif tanpa BOM",
        detail=(
            f"Terdapat {_fmt_num(count)} baris waste aktif (TOTAL > 0) dengan "
            f"TOTAL BOM NaN atau <= 0; total qty yang terdampak {_fmt_num(qty)}. "
            "Baris ini tidak terlihat oleh sinyal BOM (S6/S7) dan kolom "
            "% to BOM. Lengkapi master BOM untuk item/outlet terdampak, atau "
            "tandai sebagai non-BOM."
        ),
        count=count,
        sample=sample,
    )


# ============================================================
# CHECK 6 — DQ_SPLIT_SOURCE (warning)
# ============================================================

def _check_split_source(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Grup business key (NAMA RESTO, NAMA BARANG, JENIS, KETERANGAN) dengan
    >= 2 baris aktif (TOTAL > 0) — biasanya terpecah antar SOURCE DATA."""
    for col in (*_SPLIT_KEYS, "TOTAL"):
        if col not in df.columns:
            return None
    total = pd.to_numeric(df["TOTAL"], errors="coerce")
    active = df[total > 0]
    if len(active) == 0:
        return None

    sizes = active.groupby(list(_SPLIT_KEYS), dropna=False).size()
    multi = sizes[sizes >= 2]
    count = len(multi)
    if count == 0:
        return None

    multi = multi.sort_values(ascending=False, kind="stable")
    sample = tuple(
        f"{_safe_str(r) or '-'} / {_safe_str(i) or '-'} / {_safe_str(k) or '-'} "
        f"→ {int(n)} baris aktif"
        for (r, i, _jenis, k), n in multi.head(_MAX_SAMPLE).items()
    )
    return CheckResult(
        code="DQ_SPLIT_SOURCE",
        severity="warning",
        title="Business key terpecah (banyak baris aktif)",
        detail=(
            f"Terdapat {_fmt_num(count)} grup business key (NAMA RESTO, "
            "NAMA BARANG, JENIS, KETERANGAN) dengan >= 2 baris aktif "
            "(TOTAL > 0), umumnya karena satu business key terpecah antar "
            "SOURCE DATA. Sinyal spike dan rasio BOM dihitung per baris "
            "sehingga magnitudo terdilusi. Pertimbangkan agregasi ulang per "
            "business key atau penyatuan SOURCE DATA yang sama."
        ),
        count=count,
        sample=sample,
    )


# ============================================================
# CHECK 7 — DQ_ZERO_ROWS (info)
# ============================================================

def _check_zero_rows(df: pd.DataFrame, key_akhir) -> CheckResult | None:
    """Baris TOTAL 0/NaN — struktur placeholder normal (info, bukan error)."""
    if "TOTAL" not in df.columns:
        return None
    total = pd.to_numeric(df["TOTAL"], errors="coerce")
    mask = total.isna() | (total == 0)
    count = int(mask.sum())
    if count == 0:
        return None

    pct = 100.0 * count / max(len(df), 1)
    return CheckResult(
        code="DQ_ZERO_ROWS",
        severity="info",
        title="Baris TOTAL nol (struktur placeholder)",
        detail=(
            f"Terdapat {_fmt_num(count)} dari {_fmt_num(len(df))} baris "
            f"({_fmt_pct(pct)}%) dengan TOTAL 0/NaN. Ini struktur normal "
            "workbook rekap (placeholder resto × item × alasan), bukan error "
            "data — tidak perlu tindakan. Angka ini berguna sebagai konteks: "
            "baris nol ikut memengaruhi peer median dan persentase anomali."
        ),
        count=count,
        sample=(),
    )


# ============================================================
# MAIN ENTRY
# ============================================================

_ALL_CHECKS = (
    _check_negative,
    _check_nbsp_satuan,
    _check_source_variant,
    _check_keterangan_prefix,
    _check_waste_no_bom,
    _check_split_source,
    _check_zero_rows,
)


def run_checks(detail: pd.DataFrame, key_akhir: int | None = None) -> list[CheckResult]:
    """Jalankan SEMUA pemeriksaan data quality pada df Detail (post-pipeline).

    Urutan hasil: severity (error→warning→info), lalu code alfabetis.
    Kolom yang diperiksa hilang → check terkait di-skip (tidak muncul).
    Tidak pernah raise.

    Args:
        detail: DataFrame Detail hasil pipeline (kolom hasil pipeline boleh
            tidak ada — pemeriksaan terkait di-skip). df hanya dibaca,
            tidak pernah diubah.
        key_akhir: hari terakhir periode (1..31). Bila valid, kolom hari di
            atas key_akhir tidak ikut diperiksa (DQ_NEGATIVE) karena di luar
            periode analisa. None → semua kolom hari ikut.

    Returns:
        list[CheckResult] — hanya pemeriksaan dengan temuan (count > 0);
        df kosong / None → list kosong.
    """
    if detail is None:
        return []
    try:
        if len(detail) == 0:
            return []
        df = detail.reset_index(drop=True)
    except Exception:  # noqa: BLE001 — input aneh → hasil kosong, bukan error
        return []
    if not isinstance(df, pd.DataFrame):
        return []

    results: list[CheckResult] = []
    for check in _ALL_CHECKS:
        try:
            res = check(df, key_akhir)
        except Exception:  # noqa: BLE001, S112 — skip diam-diam sesuai kontrak
            continue
        if res is not None and res.count > 0:
            results.append(res)

    results.sort(key=lambda r: (SEVERITY_ORDER.get(r.severity, 99), r.code))
    return results
