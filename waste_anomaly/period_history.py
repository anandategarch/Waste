"""period_history.py — data pembanding periode multi-file (v2.10.0).

User menyimpan workbook per bulan (template standar "REKAP MENTAH": kolom
SOURCE DATA / JENIS / KETERANGAN / NAMA BARANG / NAMA RESTO / SATUAN /
hari 1-31 — TANPA angka BOM). Modul ini membaca file-file itu sebagai
PEMBANDING KUANTITI untuk bulan berjalan:

- load_history_file() : baca 1 workbook → agregat kuantiti per
  (NAMA RESTO × NAMA BARANG): nilai hari 1-31, TOTAL, HARI AKTIF.
  Saringan JENIS WAJIB ({SUSUT, TRIAL, WASTE}) — file mentah berisi SEMUA
  jenis (SO, BOM, BARANG MASUK/KELUAR, STOK AWAL, ...); tanpa saringan,
  angka pembanding tercampur penjualan/stok (terukur di data asli:
  MIE (V.20) @ 1042.KWGGAL hari-24 Agustus = 43.115 bila ikut BOM/SO vs
  194 yang benar — lihat worklog Task 9).
- compare_quantity()  : tabel banding A (bulan berjalan) vs B (1 bulan
  lalu ATAU tipikal gabungan) — murni kuantiti, tanpa BOM.
- typical_months()    : baseline "tipikal" = median per (item × hari)
  lintas ≥ 2 bulan pembanding.
- day_evidence_vs_history() : bukti tambahan tab Hari Mencurigakan —
  "NILAI BULAN LALU" (tanggal yang sama bulan sebelumnya) + rasio ×.
- detect_month_label(): nama bulan + tahun dari NAMA FILE (mis.
  "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx" → "Agustus 2026").
- load/save_history_entries(): daftar file diingat antar sesi
  (history_files.json, atomic — pola filters.py).

v2.10.2 — drill-down pop-up + kolom perubahan:
- compare_level()   : tabel banding per level (resto / item / per JENIS /
  per hari) — isi pop-up rantai drill "total naik → resto mana → item apa
  → hari apa" di tab-tab Banding Periode.
- drill_day_detail(): rincian hari 1-31 item×resto A vs B.
- change_vs_history() + classify_change(): kolom BULAN LALU / PERUBAHAN % /
  PERUBAHAN di tabel Anomali — memisahkan lonjakan baru (kandidat salah
  input) dari waste kronis (stabil tinggi). Threshold TH_CHANGE_*.

Semua fungsi defensif: gagal baca → dict berisi "error" (tidak pernah
raise), kolom hilang → hasil kosong berformat. Perhitungan vektor
(load + agregat data asli 54.160 baris ≈ 2-3 dtk di worker thread;
agregatnya sendiri 0,03 dtk).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .day_focus import _fmt_num, _fmt_ratio
from .frozen import exe_dir, is_frozen
from .loader import load_rekap_mentah
from .period_compare import _delta_pct, auto_key_akhir

# Saringan jenis — HARUS sama dengan stage_01 pipeline (stages.py) supaya
# pembanding dan bulan berjalan menghitung buah yang sama.
HISTORY_KEEP_JENIS = ("SUSUT", "TRIAL", "WASTE")

# Nama bulan Indonesia (+ varian Inggris) → nomor bulan.
_MONTHS = {
    "JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5,
    "JUNI": 6, "JULI": 7, "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10,
    "NOVEMBER": 11, "DESEMBER": 12,
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "MAY": 5,
    "JUNE": 6, "JULY": 7, "AUGUST": 8, "OCTOBER": 10, "DECEMBER": 12,
}
# v2.10.3 (audit): lookbehind `(?<![A-Za-z])` menggantikan `\b` — `\b`
# menolak nama bulan yang didahului underscore ("WASTE_SEPTEMBER_2026.xlsx"
# → label hilang diam-diam) karena underscore = word character (tak ada
# word-boundary). Lookbehind non-huruf menerima `_`/digit/spasi/start,
# tetap menolak bulan yang menempel HURUF ("XSEPTEMBER"/"SEPTEMBERS").
_MONTH_RE = re.compile(
    r"(?<![A-Za-z])(JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|"
    r"OKTOBER|NOVEMBER|DESEMBER|JANUARY|MARCH|MAY|JUNE|JULY|AUGUST|"
    r"OCTOBER|DECEMBER)(?![A-Za-z])[ \-_]*(\d{4})?",
    re.IGNORECASE,
)

# Kontrak kolom agregat pembanding (dipakai UI + test).
AGG_COLS = ["NAMA RESTO", "NAMA BARANG", "TOTAL", "HARI AKTIF"]
JENIS_TOTALS_COLS = ["JENIS", "TOTAL"]

# v2.10.2 — agregat tambahan utk drill-down & kolom perubahan anomali:
# agg_jenis : TOTAL per (RESTO × BARANG × JENIS) — drill tab Per Jenis
#             ("resto mana yang menaikkan JENIS ini").
# agg_detail: TOTAL per (RESTO × BARANG × JENIS × KETERANGAN) — kunci
#             pencocokan PERSIS baris tabel Anomali (kolom BULAN LALU /
#             PERUBAHAN % / PERUBAHAN).
AGG_JENIS_COLS = ["NAMA RESTO", "NAMA BARANG", "JENIS", "TOTAL"]
AGG_DETAIL_COLS = ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
                    "TOTAL"]

# Kolom bukti hari vs history (tab Hari Mencurigakan).
HIST_DAY_COLS = ["NILAI BULAN LALU", "RASIO VS BULAN LALU",
                 "TIPIKAL BEBERAPA BULAN"]

DEFAULT_TH_HIST_RATIO = 3.0

# v2.10.2 — kategori "PERUBAHAN" (filter + kolom tabel Anomali).
# Kuadran analitik (permintaan user: "perubahan tinggi atau rendah"):
# lonjakan baru (kandidat salah input) vs waste kronis (stabil tinggi).
CHANGE_CATEGORIES = ["Baru", "Naik Tinggi", "Naik Sedang", "Stabil",
                      "Turun", "Turun Tinggi"]
# Kolom hasil change_vs_history (ditambahkan ADDITIF ke salinan df anomali).
CHANGE_COLS = ["BULAN LALU", "PERUBAHAN %", "PERUBAHAN"]

DEFAULT_TH_CHANGE_HIGH = 50.0    # % — batas "tinggi" (naik/turun)
DEFAULT_TH_CHANGE_STABLE = 20.0  # % — dalam rentang ini = "Stabil"
DEFAULT_TH_CHANGE_MIN_ABS = 10.0 # selisih absolut minimum agar bermakna
                                  # (anti-noise angka kecil: 2 → 6 = +200%
                                  # tapi tak berarti apa-apa)


def _th_change(config: dict | None) -> tuple[float, float, float]:
    """(high, stable, min_abs) dari config['thresholds'] — toleran rusak."""
    try:
        t = dict((config or {}).get("thresholds") or {})
        high = float(t.get("TH_CHANGE_HIGH", DEFAULT_TH_CHANGE_HIGH))
        stable = float(t.get("TH_CHANGE_STABLE", DEFAULT_TH_CHANGE_STABLE))
        mn = float(t.get("TH_CHANGE_MIN_ABS", DEFAULT_TH_CHANGE_MIN_ABS))
    except (TypeError, ValueError):
        return (DEFAULT_TH_CHANGE_HIGH, DEFAULT_TH_CHANGE_STABLE,
                DEFAULT_TH_CHANGE_MIN_ABS)
    return (high if high > 0 else DEFAULT_TH_CHANGE_HIGH,
            stable if stable > 0 else DEFAULT_TH_CHANGE_STABLE,
            mn if mn > 0 else DEFAULT_TH_CHANGE_MIN_ABS)


# ============================================================
# LABEL BULAN DARI NAMA FILE
# ============================================================

def _parse_month(text: str) -> tuple[int, int] | None:
    """Cari token bulan (+ tahun opsional) di sembarang teks.

    Return (tahun, bulan) — tahun 0 bila tidak ada. None bila teks tidak
    memuat nama bulan yang dikenal.
    """
    m = _MONTH_RE.search(str(text or ""))
    if m is None:
        return None
    year = int(m.group(2)) if m.group(2) else 0
    return (year, _MONTHS[m.group(1).upper()])


def month_sort_key(label: str) -> tuple[int, int]:
    """Kunci urut kronologis dari label bulan ("Agustus 2026" → (2026, 8)).

    Label tak terparse → (0, 0) — ditempatkan sebelum bulan yang diketahui
    (urutan combo stabil; tidak memengaruhi bulan yang valid).
    """
    parsed = _parse_month(label or "")
    return parsed if parsed is not None else (0, 0)


def detect_month_label(path: str | os.PathLike) -> str | None:
    """Label bulan ramah dari NAMA FILE workbook pembanding.

    Contoh: "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx" → "Agustus 2026";
    "rekap juli 2025.xlsx" → "Juli 2025"; "DATA.xlsx" → None (UI memakai
    nama file sebagai fallback & boleh dikoreksi manual).
    """
    parsed = _parse_month(Path(path).stem)
    if parsed is None:
        return None
    year, month = parsed
    m = _MONTH_RE.search(Path(path).stem)
    name = m.group(1).capitalize()
    return f"{name} {year}" if year else name


# ============================================================
# AGREGAT KUANTITI
# ============================================================

def _day_cols_of(df: pd.DataFrame) -> list[str]:
    """Kolom hari '1'..'31' yang benar-benar ada di frame (urut)."""
    return [str(d) for d in range(1, 32) if str(d) in df.columns]


def _aggregate(kept: pd.DataFrame, key_akhir: int,
               num: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agregat kuantiti per (NAMA RESTO × NAMA BARANG).

    Nilai hari dijumlah lintas baris keterangan; TOTAL = jumlah hari;
    HARI AKTIF = banyak hari > 0. Murni vektor (groupby + sum).

    v2.13.7 (perf-audit B): ``num`` = kolom hari SUDAH coerce-numerik —
    pemanggil (load_history_file / aggregate_current) menghitung SEKALI
    lalu membagi ke 4 agregat (dulu to_numeric 31 kolom × 54k baris
    dihitung 4× per file pembanding). None = hitung sendiri (kontrak
    test lama tetap jalan).
    """
    day_cols = _day_cols_of(kept)
    empty = pd.DataFrame(columns=AGG_COLS + [str(d) for d in range(1, 32)])
    if kept.empty or not day_cols or "NAMA BARANG" not in kept.columns:
        return empty
    if "NAMA RESTO" not in kept.columns:
        kept = kept.assign(**{"NAMA RESTO": ""})

    if num is None or list(num.columns) != day_cols:
        num = kept[day_cols].apply(pd.to_numeric, errors="coerce")
    num = num.fillna(0.0)
    tmp = pd.DataFrame({
        "NAMA RESTO": kept["NAMA RESTO"].astype(str).str.strip(),
        "NAMA BARANG": kept["NAMA BARANG"].astype(str).str.strip(),
    })
    for c in day_cols:
        tmp[c] = num[c].to_numpy()
    agg = tmp.groupby(["NAMA RESTO", "NAMA BARANG"], as_index=False,
                      dropna=False).sum()
    agg["TOTAL"] = agg[day_cols].sum(axis=1)
    agg["HARI AKTIF"] = (agg[day_cols] > 0).sum(axis=1)
    ka = int(key_akhir) if key_akhir else 31
    agg["HARI DATA"] = ka
    return agg


def _jenis_totals(kept: pd.DataFrame,
                  num: pd.DataFrame | None = None) -> pd.DataFrame:
    """TOTAL kuantiti per JENIS (SUSUT/TRIAL/WASTE) — tabel 'Per JENIS'.

    v2.13.7: ``num`` pra-hitung (lihat _aggregate)."""
    empty = pd.DataFrame(columns=JENIS_TOTALS_COLS)
    if kept.empty or "JENIS" not in kept.columns:
        return empty
    day_cols = _day_cols_of(kept)
    if not day_cols:
        return empty
    if num is None or list(num.columns) != day_cols:
        num = kept[day_cols].apply(pd.to_numeric, errors="coerce")
    tmp = pd.DataFrame({
        "JENIS": kept["JENIS"].astype(str).str.strip().str.upper(),
        "TOTAL": num.sum(axis=1).to_numpy(),
    })
    return tmp.groupby("JENIS", as_index=False, dropna=False).agg(
        TOTAL=("TOTAL", "sum"))


def _base_keys_totals(kept: pd.DataFrame,
                      keys: list[str],
                      num: pd.DataFrame | None = None) -> pd.DataFrame:
    """TOTAL per `keys` + (JENIS[, KETERANGAN]) — vektor, string dinormalkan.

    Dipakai _jenis_item_totals (agg_jenis) & _detail_totals (agg_detail).
    TOTAL dihitung ULANG dari kolom hari (semantik identik _aggregate).
    v2.13.7: ``num`` pra-hitung (lihat _aggregate)."""
    cols = list(keys)
    empty = pd.DataFrame(columns=cols + ["TOTAL"])
    if kept.empty:
        return empty
    day_cols = _day_cols_of(kept)
    if not day_cols:
        return empty
    for c in cols:
        if c not in kept.columns:
            return empty
    if num is None or list(num.columns) != day_cols:
        num = kept[day_cols].apply(pd.to_numeric, errors="coerce")
    num = num.fillna(0.0)
    tmp = {"TOTAL": num.sum(axis=1).to_numpy()}
    for c in cols:
        s = kept[c].astype(str).str.strip()
        if c == "JENIS":
            s = s.str.upper()
        tmp[c] = s
    return pd.DataFrame(tmp).groupby(cols, as_index=False, dropna=False).agg(
        TOTAL=("TOTAL", "sum"))


def _jenis_item_totals(kept: pd.DataFrame,
                       num: pd.DataFrame | None = None) -> pd.DataFrame:
    """TOTAL per (RESTO × BARANG × JENIS) — drill tab Per Jenis (v2.10.2)."""
    return _base_keys_totals(kept, ["NAMA RESTO", "NAMA BARANG", "JENIS"],
                             num=num)


def _detail_totals(kept: pd.DataFrame,
                   num: pd.DataFrame | None = None) -> pd.DataFrame:
    """TOTAL per (RESTO × BARANG × JENIS × KETERANGAN) — kunci cocok PERSIS
    baris tabel Anomali (kolom BULAN LALU / PERUBAHAN %, v2.10.2)."""
    return _base_keys_totals(
        kept, ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN"], num=num)


def _month_dict(agg: pd.DataFrame, jenis: pd.DataFrame, label: str,
                key_akhir: int, rows_kept: int, rows_raw: int = 0,
                agg_jenis: pd.DataFrame | None = None,
                agg_detail: pd.DataFrame | None = None) -> dict:
    """Bentuk standar entri bulan (kontrak konsumen UI/test).

    v2.10.2: agg_jenis/agg_detail ADDITIF — None → frame kosong berformat
    (konsumen lama tak terdampak)."""
    return {
        "label": label,
        "key_akhir": int(key_akhir) if key_akhir else 31,
        "agg": agg,
        "jenis_totals": jenis,
        "agg_jenis": (agg_jenis if agg_jenis is not None
                      else pd.DataFrame(columns=AGG_JENIS_COLS)),
        "agg_detail": (agg_detail if agg_detail is not None
                       else pd.DataFrame(columns=AGG_DETAIL_COLS)),
        "resto_count": int(agg["NAMA RESTO"].nunique()) if not agg.empty else 0,
        "item_count": int(agg["NAMA BARANG"].nunique()) if not agg.empty else 0,
        "rows_kept": int(rows_kept),
        "rows_raw": int(rows_raw),
        "error": None,
    }


def _filter_waste(raw: pd.DataFrame) -> pd.DataFrame:
    """Saring JENIS ∈ {SUSUT, TRIAL, WASTE} (case/whitespace-toleran).

    WAJIB sebelum agregat — file mentah memuat juga BOM/SO/stok (lihat
    docstring modul). Frame tanpa kolom JENIS diteruskan apa adanya
    (defensif — pemanggil memeriksa kolom wajib terpisah).
    """
    if "JENIS" not in raw.columns:
        return raw
    jenis = raw["JENIS"].astype(str).str.strip().str.upper()
    return raw[jenis.isin(HISTORY_KEEP_JENIS)].copy()


def load_history_file(path: str | os.PathLike,
                      config: dict | None = None) -> dict:
    """Baca 1 workbook pembanding → entri bulan (dict kontrak _month_dict).

    Gagal baca (file hilang / sheet tak dikenal / kolom wajib absen) →
    dict BERISI "error" (string ramah) — TIDAK pernah raise, file lain
    tetap bisa diproses pemanggil.
    """
    p = Path(path)
    # "path" hasil HARUS string input PEMANGGIL persis (bukan str(Path)):
    # str(Path(x)) menormalisasi pemisah/segmen — di Windows dialog Qt
    # memberi 'C:/a/b.xlsx' tapi pathlib membalikkan 'C:\\a\\b.xlsx';
    # PeriodeView mengunci status/cache/combo dgn string dari dialog →
    # normalisasi bikin baris tetap 'belum dimuat' padahal muat sukses
    # (bug v2.10.0 dilaporkan user; fix v2.10.1).
    base = {"path": str(path), "label": detect_month_label(p),
            "error": None, "label_source": "auto"}
    try:
        if not p.exists():
            base["error"] = f"File tidak ditemukan: {p.name}"
            return base
        raw = load_rekap_mentah(str(p), config if config is not None else {})
        if raw is None or raw.empty:
            base["error"] = f"Sheet data kosong / tidak ditemukan: {p.name}"
            return base
        for col in ("NAMA BARANG",):
            if col not in raw.columns:
                base["error"] = f"Kolom wajib '{col}' tidak ada di {p.name}"
                return base
        if not _day_cols_of(raw):
            base["error"] = f"Kolom hari 1-31 tidak ditemukan di {p.name}"
            return base
        ka = auto_key_akhir(raw)
        kept = _filter_waste(raw)
        # v2.13.7 (perf-audit B): coerce-numerik kolom hari SEKALI untuk
        # 4 agregat (dulu dihitung 4× per file — 31 kolom × 54k baris).
        num = kept[_day_cols_of(kept)].apply(pd.to_numeric, errors="coerce")
        agg = _aggregate(kept, ka, num=num)
        d = _month_dict(agg, _jenis_totals(kept, num=num),
                        base["label"] or p.stem,
                        ka, len(kept), len(raw),
                        agg_jenis=_jenis_item_totals(kept, num=num),
                        agg_detail=_detail_totals(kept, num=num))
        d["path"] = str(path)  # persis input (lihat komentar base di atas)
        d["label_source"] = "auto"
        return d
    except Exception as e:  # noqa: BLE001 — defensif: jangan gagalkan file lain
        base["error"] = f"{type(e).__name__}: {e}"
        return base


def aggregate_current(df: pd.DataFrame | None, key_akhir: int,
                      label: str = "Bulan Ini") -> dict | None:
    """Entri bulan berjalan (A) dari df hasil pipeline.

    Saringan JENIS diterapkan ulang bila kolom ada (idempoten — stage_01
    sudah menyaring; M-output ber-format 53 kolom juga lolos karena
    saringan sama). TOTAL dihitung ULANG dari kolom hari supaya semantik
    identik dengan pembanding (bukan memakai kolom TOTAL M-code).
    """
    if df is None or df.empty or "NAMA BARANG" not in df.columns:
        return None
    if not _day_cols_of(df):
        return None
    ka = int(key_akhir) if key_akhir else 31
    kept = _filter_waste(df)
    if kept.empty:
        kept = df
    # v2.13.7 (perf-audit B): coerce-numerik SEKALI utk 4 agregat.
    num = kept[_day_cols_of(kept)].apply(pd.to_numeric, errors="coerce")
    agg = _aggregate(kept, ka, num=num)
    d = _month_dict(agg, _jenis_totals(kept, num=num), label, ka, len(kept),
                    len(df), agg_jenis=_jenis_item_totals(kept, num=num),
                    agg_detail=_detail_totals(kept, num=num))
    d["path"] = "(run saat ini)"
    return d


# ============================================================
# PERBANDINGAN KUANTITI (A vs B)
# ============================================================

# Kolom output tetap — UI merender persis kontrak ini (pola period_compare).
SUMMARY_COLS = ["Metrik", "Bulan Ini", "Pembanding", "Perubahan %"]
JENIS_COLS = ["JENIS", "Bulan Ini", "Pembanding", "Selisih", "Perubahan %"]
BRANCH_COLS = ["NAMA RESTO", "Bulan Ini", "Pembanding", "Selisih",
               "Perubahan %"]
ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Bulan Ini", "Pembanding",
             "Selisih", "Perubahan %"]
NEW_ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Bulan Ini"]
GONE_ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Pembanding"]


def _totals_by(agg: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Agregat TOTAL per keys dari frame agg pembanding/bulan-ini."""
    if agg is None or agg.empty or not all(k in agg.columns for k in keys):
        return pd.DataFrame(columns=keys + ["TOTAL"])
    sub = agg[keys + ["TOTAL"]].copy()
    return sub.groupby(keys, as_index=False, dropna=False).agg(
        TOTAL=("TOTAL", "sum"))


def compare_quantity(a: dict, b: dict, top_n: int = 100) -> dict:
    """Banding bulan berjalan (A) vs pembanding (B) — murni kuantiti.

    B bisa 1 bulan lalu ATAU tipikal gabungan (dict bentuk sama).
    Return dict tabel: summary, per_jenis, branch, items, new_items,
    gone_items + label_a/label_b/key_akhir_a/key_akhir_b (pola
    compare_periods — view merender kunci yang sama).
    """
    label_a = str(a.get("label") or "Bulan Ini")
    label_b = str(b.get("label") or "Pembanding")
    ka_a = int(a.get("key_akhir") or 31)
    ka_b = int(b.get("key_akhir") or 31)

    ta = _totals_by(a.get("agg"), ["NAMA RESTO", "NAMA BARANG"])
    tb = _totals_by(b.get("agg"), ["NAMA RESTO", "NAMA BARANG"])
    total_a = float(ta["TOTAL"].sum()) if not ta.empty else 0.0
    total_b = float(tb["TOTAL"].sum()) if not tb.empty else 0.0

    def _pct(cur: float, base: float) -> float:
        return _delta_pct(cur, base)

    rows = [
        ("Total Waste", total_a, total_b),
        ("Waste per Hari",
         total_a / ka_a if ka_a > 0 else 0.0,
         total_b / ka_b if ka_b > 0 else 0.0),
        ("Cabang Aktif",
         int(ta["NAMA RESTO"].nunique()) if not ta.empty else 0,
         int(tb["NAMA RESTO"].nunique()) if not tb.empty else 0),
        ("Item Aktif",
         int(ta["NAMA BARANG"].nunique()) if not ta.empty else 0,
         int(tb["NAMA BARANG"].nunique()) if not tb.empty else 0),
        # "Hari Data" BUKAN metrik kinerja (Agustus 31 vs September 30 hari
        # ≠ naik 3,3%) — kolom Perubahan sengaja kosong; "Waste per Hari"
        # di atas sudah menormalkan beda panjang bulan.
        ("Hari Data", ka_a, ka_b, None),
    ]
    summary = pd.DataFrame(
        [{"Metrik": r[0], "Bulan Ini": r[1], "Pembanding": r[2],
          # Tuple 4-elemen = penanda Perubahan eksplisit (None = kosong).
          "Perubahan %": (r[3] if len(r) > 3
                          else _pct(float(r[1]), float(r[2])))}
         for r in rows], columns=SUMMARY_COLS)
    # v2.13.4 (fix "hari 30 error"): kolom float64 mengubah None→NaN,
    # lalu fmt_delta_pct menampilkan NaN sebagai 'BARU' — baris 'Hari
    # Data' (mis. 30 vs 31 hari) tampak seperti error "bulan 30 hari".
    # Bangun ulang kolom sebagai OBJECT supaya None TETAP None →
    # fmt_delta_pct(None) = '' (kosong, sesuai desain awal). NaN asli
    # dari _pct(base=0) tetap NaN → 'BARU' (benar: tanpa riwayat).
    # Kontrak isna(None)=True → test lama (pd.isna) tetap hijau.
    summary["Perubahan %"] = pd.Series(
        [(r[3] if len(r) > 3 else _pct(float(r[1]), float(r[2])))
         for r in rows], dtype=object)

    # ---- per JENIS ----
    ja = a.get("jenis_totals")
    jb = b.get("jenis_totals")
    if (ja is None or ja.empty) and (jb is None or jb.empty):
        per_jenis = pd.DataFrame(columns=JENIS_COLS)
    else:
        ja = ja if ja is not None and not ja.empty else pd.DataFrame(
            columns=JENIS_TOTALS_COLS)
        jb = jb if jb is not None and not jb.empty else pd.DataFrame(
            columns=JENIS_TOTALS_COLS)
        m = ja.merge(jb, on="JENIS", how="outer")
        # v2.13.4: coerce numerik dulu (pola compare_level) — fillna pada
        # kolom object memicu FutureWarning downcasting pandas 3.x.
        for _c in ("TOTAL_x", "TOTAL_y"):
            m[_c] = pd.to_numeric(m[_c], errors="coerce").fillna(0.0)
        m = m.rename(columns={"TOTAL_x": "Bulan Ini",
                              "TOTAL_y": "Pembanding"})
        m["Selisih"] = m["Bulan Ini"] - m["Pembanding"]
        m["Perubahan %"] = [_pct(c, base) for c, base
                            in zip(m["Bulan Ini"], m["Pembanding"])]
        per_jenis = m.sort_values("Bulan Ini", ascending=False).reset_index(
            drop=True)[JENIS_COLS]

    # ---- cabang / item / baru / hilang ----
    # v2.12.2 — JENIS tampil di tabel mover (permintaan user: "tampilkan
    # jenisnya — entah itu SUSUT/TRIAL/WASTE"). agg_jenis (TOTAL per
    # RESTO×BARANG×JENIS) SUDAH dihitung loader file + aggregate_current +
    # typical_months — dipakai bila tersedia di A/B; bulan TANPA agg_jenis
    # (fixture test lama) jatuh ke perilaku lama PERSIS (tanpa kolom JENIS)
    # → golden v2.10.0 tak tersentuh. Item yang sama tercatat di 2 jenis
    # (mis. WASTE + TRIAL) kini jadi 2 baris terpisah — pemisahannya tak
    # lagi tersembunyi di dalam gabungan.
    use_jenis = any(
        (m.get("agg_jenis") is not None
         and not m.get("agg_jenis").empty
         and "JENIS" in list(m.get("agg_jenis").columns))
        for m in (a, b))

    def _tot_jenis(m: dict) -> pd.DataFrame:
        aj = m.get("agg_jenis")
        if (aj is None or aj.empty
                or "JENIS" not in list(aj.columns)
                or "NAMA RESTO" not in list(aj.columns)):
            return pd.DataFrame(columns=AGG_JENIS_COLS)
        return aj[AGG_JENIS_COLS].copy()

    if use_jenis:
        ta = _tot_jenis(a)
        tb = _tot_jenis(b)
    else:
        ta = _totals_by(a.get("agg"), ["NAMA RESTO", "NAMA BARANG"])
        tb = _totals_by(b.get("agg"), ["NAMA RESTO", "NAMA BARANG"])
    key = (["JENIS", "NAMA RESTO", "NAMA BARANG"] if use_jenis
           else ["NAMA RESTO", "NAMA BARANG"])
    branch_cols = (["JENIS"] if use_jenis else []) + BRANCH_COLS
    item_cols = (["JENIS"] if use_jenis else []) + ITEM_COLS
    new_cols = (["JENIS"] if use_jenis else []) + NEW_ITEM_COLS
    gone_cols = (["JENIS"] if use_jenis else []) + GONE_ITEM_COLS
    empty_items = pd.DataFrame(columns=item_cols)
    empty_new = pd.DataFrame(columns=new_cols)
    empty_gone = pd.DataFrame(columns=gone_cols)
    if ta.empty and tb.empty:
        branch = pd.DataFrame(columns=branch_cols)
        items, new_items, gone_items = empty_items, empty_new, empty_gone
    else:
        if use_jenis:
            ga = ta.groupby(["JENIS", "NAMA RESTO"], as_index=False,
                            dropna=False)["TOTAL"].sum()
            gb = tb.groupby(["JENIS", "NAMA RESTO"], as_index=False,
                            dropna=False)["TOTAL"].sum()
            on = ["JENIS", "NAMA RESTO"]
        else:
            ga = ta.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
            gb = tb.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
            on = "NAMA RESTO"
        mb = ga.merge(gb, on=on, how="outer")
        # v2.13.4: coerce numerik dulu (pola compare_level) — FutureWarning
        # downcasting fillna pada kolom object tidak muncul lagi.
        for _c in ("TOTAL_x", "TOTAL_y"):
            mb[_c] = pd.to_numeric(mb[_c], errors="coerce").fillna(0.0)
        mb = mb.rename(
            columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
        mb["Selisih"] = mb["Bulan Ini"] - mb["Pembanding"]
        mb["Perubahan %"] = [_pct(c, base) for c, base
                             in zip(mb["Bulan Ini"], mb["Pembanding"])]
        mb = mb.reindex(mb["Selisih"].abs().sort_values(
            ascending=False).index).head(top_n)
        branch = mb.reset_index(drop=True)[branch_cols]

        m = ta.merge(tb, on=key, how="outer")
        # v2.13.4: coerce numerik dulu (pola compare_level).
        for _c in ("TOTAL_x", "TOTAL_y"):
            m[_c] = pd.to_numeric(m[_c], errors="coerce").fillna(0.0)
        m = m.rename(columns={"TOTAL_x": "Bulan Ini",
                              "TOTAL_y": "Pembanding"})
        m["Selisih"] = m["Bulan Ini"] - m["Pembanding"]
        m["Perubahan %"] = [_pct(c, base) for c, base
                            in zip(m["Bulan Ini"], m["Pembanding"])]
        m = m.reindex(m["Selisih"].abs().sort_values(
            ascending=False).index).head(top_n)
        items = m.reset_index(drop=True)[item_cols]
        # Baru = hanya di bulan INI (tidak ada bulan lalu); hilang = sebaliknya.
        full = ta.merge(tb, on=key, how="outer")
        # v2.13.4: coerce numerik dulu (pola compare_level).
        for _c in ("TOTAL_x", "TOTAL_y"):
            full[_c] = pd.to_numeric(full[_c], errors="coerce").fillna(0.0)
        full = full.rename(
            columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
        new_items = full[full["Pembanding"] <= 0][
            key + ["Bulan Ini"]].sort_values(
            "Bulan Ini", ascending=False).head(
            top_n).reset_index(drop=True)[new_cols]
        gone_items = full[full["Bulan Ini"] <= 0][
            key + ["Pembanding"]].sort_values(
            "Pembanding", ascending=False).head(
            top_n).reset_index(drop=True)[gone_cols]

    return {
        "label_a": label_a,
        "label_b": label_b,
        "key_akhir_a": ka_a,
        "key_akhir_b": ka_b,
        "summary": summary,
        "per_jenis": per_jenis,
        "branch": branch,
        "items": items,
        "new_items": new_items,
        "gone_items": gone_items,
    }


# ============================================================
# DRILL-DOWN POP-UP (v2.10.2)
# ============================================================
# Rantai drill (permintaan user): "secara total naik → resto mana yang
# naik → sampai item apa". Semua level = tabel banding bentuk SAMA
# (Bulan Ini / Pembanding / Selisih / Perubahan %), sumber agregat beda:
# - level resto : _totals_by(agg, ["NAMA RESTO"]) — sumber 'agg'
# - level item  : _totals_by(agg, ["NAMA RESTO","NAMA BARANG"]) — 'agg'
# - level item per JENIS : 'agg_jenis' (RESTO×BARANG×JENIS)
# - level hari  : kolom hari '1'..'31' baris (RESTO×BARANG) di 'agg'
# LEVEL_DAY_COLS dipakai tabel hari (drill paling dalam).

DRILL_LEVEL_COLS = ["NAMA RESTO", "Bulan Ini", "Pembanding", "Selisih",
                    "Perubahan %"]
DRILL_ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Bulan Ini", "Pembanding",
                   "Selisih", "Perubahan %"]
DAY_DETAIL_COLS = ["HARI", "Bulan Ini", "Pembanding", "Selisih"]


def compare_level(a: dict, b: dict, keys: list[str],
                  jenis: str | None = None, per_day: bool = False,
                  top_n: int | None = None) -> pd.DataFrame:
    """Tabel banding per level — isi pop-up drill-down (v2.10.2).

    a/b = entri bulan (dict _month_dict — bulan berjalan / pembanding /
    tipikal). keys ⊆ {NAMA RESTO, NAMA BARANG}; jenis None → sumber 'agg'
    (semua jenis digabung), jenis 'WASTE' → sumber 'agg_jenis' difilter
    JENIS itu (drill dari tab Per Jenis).
    per_day=True → nilai dibagi key_akhir bulan masing-masing (menormalkan
    beda 30/31 hari — dipakai drill metrik 'Waste per Hari').
    top_n=None → SEMUA baris (drill = jawaban lengkap, bukan top-100).
    Urutan: |Selisih| menurun (kontributor terbesar dulu).
    """
    out_cols = list(keys) + ["Bulan Ini", "Pembanding", "Selisih",
                             "Perubahan %"]
    use_jenis = jenis is not None
    src_key = "agg_jenis" if use_jenis else "agg"

    def _tot(src: dict) -> pd.DataFrame:
        frame = src.get(src_key) if isinstance(src, dict) else None
        if frame is None or frame.empty or not all(
                k in frame.columns for k in keys):
            return pd.DataFrame(columns=list(keys) + ["TOTAL"])
        sub = frame[keys + ["TOTAL"]].copy()
        if use_jenis and "JENIS" in frame.columns:
            j = frame["JENIS"].astype(str).str.strip().str.upper()
            sub = sub[j == str(jenis).strip().upper()]
        if sub.empty:
            return pd.DataFrame(columns=list(keys) + ["TOTAL"])
        return sub.groupby(keys, as_index=False, dropna=False).agg(
            TOTAL=("TOTAL", "sum"))

    ga, gb = _tot(a), _tot(b)
    if ga.empty and gb.empty:
        return pd.DataFrame(columns=out_cols)
    m = ga.merge(gb, on=keys, how="outer")
    # Outer merge menghasilkan NaN; angka coerced numerik dulu (hindari
    # FutureWarning fillna object + tahan kolom object dari frame lama).
    for c in ("TOTAL_x", "TOTAL_y"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0.0)
    m = m.rename(columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
    if per_day:
        ka_a = int(a.get("key_akhir") or 31) or 31
        ka_b = int(b.get("key_akhir") or 31) or 31
        m["Bulan Ini"] = m["Bulan Ini"] / ka_a
        m["Pembanding"] = m["Pembanding"] / ka_b
    m["Selisih"] = m["Bulan Ini"] - m["Pembanding"]
    m["Perubahan %"] = [_delta_pct(float(c), float(p)) for c, p
                        in zip(m["Bulan Ini"], m["Pembanding"])]
    m = m.reindex(m["Selisih"].abs().sort_values(ascending=False).index)
    if top_n is not None:
        m = m.head(int(top_n))
    return m.reset_index(drop=True)[out_cols]


def drill_day_detail(a: dict, b: dict, resto: str,
                     barang: str) -> pd.DataFrame:
    """Rincian HARI 1..N item×resto: Bulan Ini vs Pembanding (v2.10.2).

    Jawaban "hari apa yang naik" — level drill paling dalam. Item tanpa
    catatan di salah satu bulan → sisi itu 0 (bukan NaN) supaya Selisih
    terbaca. Panjang = max(key_akhir A, key_akhir B).
    """
    ka = max(int(a.get("key_akhir") or 31) or 31,
             int(b.get("key_akhir") or 31) or 31)
    days = list(range(1, ka + 1))

    def _series(src: dict) -> np.ndarray:
        agg = src.get("agg")
        if agg is None or agg.empty:
            return np.zeros(len(days), dtype=float)
        rk = str(resto).strip()
        ik = str(barang).strip()
        sub = agg[(agg["NAMA RESTO"].astype(str).str.strip() == rk)
                  & (agg["NAMA BARANG"].astype(str).str.strip() == ik)]
        if sub.empty:
            return np.zeros(len(days), dtype=float)
        row = sub.iloc[0]
        out = np.zeros(len(days), dtype=float)
        for i, d in enumerate(days):
            if str(d) in sub.columns:
                v = pd.to_numeric(row[str(d)], errors="coerce")
                out[i] = float(v) if pd.notna(v) else 0.0
        return out

    cur, base = _series(a), _series(b)
    df = pd.DataFrame({
        "HARI": days,
        "Bulan Ini": cur[:len(days)],
        "Pembanding": base[:len(days)],
    })
    df["Selisih"] = df["Bulan Ini"] - df["Pembanding"]
    return df[DAY_DETAIL_COLS]


# ============================================================
# KOLOM PERUBAHAN utk TABEL ANOMALI (v2.10.2)
# ============================================================

def classify_change(cur: float, base: float,
                    config: dict | None = None) -> str:
    """Kategori perubahan total baris vs bulan lalu (PERUBAHAN).

    Aturan (semua threshold bisa diatur config TH_CHANGE_*):
    - 'Baru'         : tak ada riwayat (base NaN/≤0) & sekarang ada nilai.
    - 'Naik Tinggi'  : naik ≥ TH_CHANGE_HIGH % DAN selisih ≥ MIN_ABS
                       (lonjakan baru — kandidat salah input/kejadian baru).
    - 'Turun Tinggi' : turun ≤ −HIGH % DAN selisih ≥ MIN_ABS.
    - 'Stabil'       : |Δ%| ≤ TH_CHANGE_STABLE ATAU selisih < MIN_ABS
                       (angka kecil = noise; waste kronis turun di sini).
    - 'Naik Sedang'/'Turun' : di antaranya.
    NaN/None di kurva → 'Stabil' (netral, tak menuduh).
    """
    high, stable, mn = _th_change(config)
    try:
        cur = float(cur)
    except (TypeError, ValueError):
        return "Stabil"
    if pd.isna(cur):
        return "Stabil"
    if pd.isna(base):
        return "Baru" if cur > 0 else "Stabil"
    try:
        base = float(base)
    except (TypeError, ValueError):
        return "Baru" if cur > 0 else "Stabil"
    if base <= 0:
        return "Baru" if cur > 0 else "Stabil"
    delta = cur - base
    if abs(delta) < mn:
        return "Stabil"
    pct = delta / base * 100.0
    if pct >= high:
        return "Naik Tinggi"
    if pct <= -high:
        return "Turun Tinggi"
    if pct > stable:
        return "Naik Sedang"
    if pct < -stable:
        return "Turun"
    return "Stabil"


def change_vs_history(df: pd.DataFrame, baseline: dict | None,
                      config: dict | None = None) -> pd.DataFrame:
    """Tambah kolom perubahan vs bulan lalu ke SALINAN df anomali (additive).

    Kolom (CHANGE_COLS):
    - BULAN LALU  : total baris yang PERSIS sama (resto×item×jenis×keterangan)
                    di bulan pembanding — pencocokan string abaikan
                    besar/kecil huruf & spasi. NaN = belum ada bulan lalu.
    - PERUBAHAN % : (TOTAL − BULAN LALU) ÷ BULAN LALU × 100 (skala 0-100,
                    konvensi _delta_pct — NaN = tanpa riwayat, tampil 'BARU').
    - PERUBAHAN   : kategori classify_change (filter kuadran tinggi/rendah).

    Kontrak: df input TIDAK dimutasi (state.anomali_df — 'konsumen hanya
    membaca'); baseline None / kolom wajib absen → kolom NaN penuh
    (tabel identik tanpa pembanding — pola day_evidence_vs_history).
    """
    out = df.copy()
    n = len(out)
    out["BULAN LALU"] = np.nan
    out["PERUBAHAN %"] = np.nan
    out["PERUBAHAN"] = "Stabil"
    if n == 0 or baseline is None or "NAMA BARANG" not in out.columns:
        return out
    if "TOTAL" not in out.columns:
        return out

    base_frame = baseline.get("agg_detail")
    if base_frame is None or base_frame.empty:
        return out

    # Kunci join: selalu resto+barang; +JENIS & +KETERANGAN bila dua sisi
    # punya kolomnya (M-output 53 kolom punya keduanya → cocok PERSIS).
    keys = ["NAMA RESTO", "NAMA BARANG"]
    if "JENIS" in out.columns and "JENIS" in base_frame.columns:
        keys.append("JENIS")
    if "KETERANGAN" in out.columns and "KETERANGAN" in base_frame.columns:
        keys.append("KETERANGAN")
    if not all(k in base_frame.columns for k in keys):
        return out

    def _norm(frame: pd.DataFrame) -> pd.DataFrame:
        tmp = pd.DataFrame(index=frame.index)
        for k in keys:
            s = frame[k].astype(str).str.strip()
            if k in ("JENIS",):
                s = s.str.upper()
            elif k == "KETERANGAN":
                s = s.str.casefold()
            tmp[k] = s
        return tmp

    cand = _norm(out)
    # Base dibangun dari agg_detail (string sudah dinormalkan _base_keys_totals
    # utk JENIS; KETERANGAN casefold di sini agar konsisten dua sisi).
    # Bila kunci lebih KASAR (JENIS/KETERANGAN absen di df anomali), baris
    # detail dg kunci sama DIGABUNG (sum) — tanpa ini left-merge menduplikasi
    # baris (3 baris anomali × 2 baris detail = 5 → ValueError panjang).
    bmap = _norm(base_frame).copy()
    bmap["__base"] = pd.to_numeric(
        base_frame["TOTAL"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bmap = bmap.groupby(keys, as_index=False, dropna=False).agg(
        __base=("__base", "sum"))
    m = cand.merge(bmap, on=keys, how="left")
    base_vals = m["__base"].to_numpy(dtype=float)

    out["BULAN LALU"] = base_vals
    cur_vals = pd.to_numeric(
        out["TOTAL"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(
            base_vals > 0,
            (cur_vals - base_vals) / np.where(base_vals > 0, base_vals, 1)
            * 100.0,
            np.where(cur_vals > 0, np.nan, 0.0))
    out["PERUBAHAN %"] = pct
    out["PERUBAHAN"] = [classify_change(c, b, config)
                        for c, b in zip(cur_vals, base_vals)]
    return out


# ============================================================
# TIPIKAL GABUNGAN (median lintas bulan)
# ============================================================

def typical_months(months: list[dict]) -> dict | None:
    """Baseline tipikal = MEDIAN per (item × hari) lintas bulan pembanding.

    Butuh ≥ 2 bulan valid (1 bulan = identik bulan itu sendiri, tak ada
    "tipikal"). Return dict bentuk sama dgn entri bulan (label "Tipikal")
    atau None bila syarat tak terpenuhi.
    """
    ok = [m for m in (months or [])
          if m and not m.get("error") and m.get("agg") is not None
          and not m["agg"].empty]
    if len(ok) < 2:
        return None
    longs = []
    totals = []
    jenis_frames = []
    for m in ok:
        agg = m["agg"]
        day_cols = [c for c in agg.columns if str(c).isdigit()
                    and 1 <= int(c) <= 31]
        if not day_cols:
            continue
        long = agg.melt(id_vars=["NAMA RESTO", "NAMA BARANG"],
                        value_vars=day_cols, var_name="_day",
                        value_name="_val")
        longs.append(long)
        totals.append(agg[["NAMA RESTO", "NAMA BARANG", "TOTAL"]])
        jt = m.get("jenis_totals")
        if jt is not None and not jt.empty:
            jenis_frames.append(jt)
    if len(longs) < 2:
        return None

    all_long = pd.concat(longs, ignore_index=True)
    g = all_long.groupby(["NAMA RESTO", "NAMA BARANG", "_day"], as_index=False
                         ).agg(_med=("_val", "median"))
    wide = g.pivot(index=["NAMA RESTO", "NAMA BARANG"], columns="_day",
                   values="_med").reset_index()
    wide.columns.name = None
    for d in range(1, 32):
        if str(d) not in wide.columns:
            wide[str(d)] = np.nan
    wide = wide[["NAMA RESTO", "NAMA BARANG"] + [str(d) for d in range(1, 32)]]
    wide["TOTAL"] = wide[[str(d) for d in range(1, 32)]].median(axis=1)
    wide["HARI AKTIF"] = (wide[[str(d) for d in range(1, 32)]]
                          .apply(pd.to_numeric, errors="coerce")
                          .fillna(0) > 0).sum(axis=1)
    kas = [int(m.get("key_akhir") or 31) for m in ok]
    ka_typ = int(np.median(kas))
    wide["HARI DATA"] = ka_typ

    all_tot = pd.concat(totals, ignore_index=True)
    med_tot = all_tot.groupby(["NAMA RESTO", "NAMA BARANG"], as_index=False
                              ).agg(TOTAL=("TOTAL", "median"))
    wide = wide.drop(columns=["TOTAL"]).merge(
        med_tot, on=["NAMA RESTO", "NAMA BARANG"], how="left")
    wide["TOTAL"] = wide["TOTAL"].fillna(0.0)

    if jenis_frames:
        aj = pd.concat(jenis_frames, ignore_index=True)
        jenis_typ = aj.groupby("JENIS", as_index=False).agg(
            TOTAL=("TOTAL", "median"))
    else:
        jenis_typ = pd.DataFrame(columns=JENIS_TOTALS_COLS)

    # v2.10.2 — tipikal agg_jenis & agg_detail (median TOTAL per kunci):
    # dipakai drill tab Per Jenis + kolom BULAN LALU/PERUBAHAN tabel Anomali
    # saat combo memilih 'Tipikal'. Bulan tanpa agregat itu (dict lama /
    # frame kosong) dikecualikan — median bahan yang ada saja.
    def _typ_by(group_keys: list[str], src: str) -> pd.DataFrame:
        frames = [m.get(src) for m in ok]
        frames = [f for f in frames
                  if f is not None and not f.empty
                  and all(c in f.columns for c in group_keys + ["TOTAL"])]
        if not frames:
            return pd.DataFrame(columns=group_keys + ["TOTAL"])
        allf = pd.concat(frames, ignore_index=True)
        return allf.groupby(group_keys, as_index=False, dropna=False).agg(
            TOTAL=("TOTAL", "median"))

    agg_jenis_typ = _typ_by(["NAMA RESTO", "NAMA BARANG", "JENIS"],
                            "agg_jenis")
    agg_detail_typ = _typ_by(
        ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN"],
        "agg_detail")

    labels = [str(m.get("label") or "?") for m in ok]
    d = _month_dict(wide, jenis_typ, "Tipikal", ka_typ, len(wide), 0,
                    agg_jenis=agg_jenis_typ, agg_detail=agg_detail_typ)
    d["label_detail"] = "Tipikal — median " + " + ".join(labels)
    d["months_count"] = len(ok)
    d["path"] = "(gabungan " + " + ".join(labels) + ")"
    return d


# ============================================================
# BUKTI HARI vs BULAN LALU (tab Hari Mencurigakan)
# ============================================================

def day_evidence_vs_history(df: pd.DataFrame, months: list[dict],
                            typical: dict | None = None,
                            config: dict | None = None) -> pd.DataFrame:
    """Tambah kolom bukti hari vs pembanding bulan lalu (additive).

    Kolom baru (baris tanpa hari tersangka / item tanpa history → kosong):
    - NILAI BULAN LALU      : nilai item sama, cabang sama, TANGGAL sama,
                              bulan pembanding TERBARU.
    - RASIO VS BULAN LALU   : NILAI HARI TERSANGKA ÷ nilai bulan lalu.
    - TIPIKAL BEBERAPA BULAN: median tanggal sama lintas bulan (≥ 2 bulan).

    ALASAN HARI diberi tambahan kalimat bila rasio ≥ TH_HARI_HIST_RATIO
    (default 3×) — bukti TAMBAHAN; BUKTI HARI (YES/NO) TIDAK diubah
    (stays murni hasil Stage 15 → golden count tak bergeser).
    """
    out = df.copy()
    n = len(out)
    out["NILAI BULAN LALU"] = np.nan
    out["RASIO VS BULAN LALU"] = np.nan
    if typical is not None:
        out["TIPIKAL BEBERAPA BULAN"] = np.nan
    if n == 0 or "HARI TERSANGKA" not in out.columns:
        return out

    ok = [m for m in (months or [])
          if m and not m.get("error") and m.get("agg") is not None
          and not m["agg"].empty]
    if not ok:
        return out

    hari = pd.to_numeric(out["HARI TERSANGKA"], errors="coerce")
    day_cols = _day_cols_of(out)
    if not day_cols or "NAMA BARANG" not in out.columns:
        return out
    idx = np.flatnonzero(hari.notna().to_numpy())
    if len(idx) == 0:
        return out
    day_num = hari.to_numpy()[idx].astype(int)
    in_scope = np.array([str(d) in day_cols for d in day_num])
    idx = idx[in_scope]
    day_num = day_num[in_scope]
    if len(idx) == 0:
        return out

    # Nilai hari tersangka dihitung ULANG dari matriks hari (robust —
    # tidak bergantung kolom NILAI HARI TERSANGKA yang mungkin kosong).
    sub = out.iloc[idx][day_cols].apply(pd.to_numeric, errors="coerce")
    day_pos = np.array([day_cols.index(str(d)) for d in day_num])
    nilai = sub.to_numpy()[np.arange(len(idx)), day_pos]

    resto = (out["NAMA RESTO"].astype(str).str.strip().to_numpy()
             if "NAMA RESTO" in out.columns
             else np.array([""] * n))
    barang = out["NAMA BARANG"].astype(str).str.strip().to_numpy()
    cand = pd.DataFrame({
        "_pos": idx,
        "_rk": resto[idx],
        "_ik": barang[idx],
        "_day": [str(d) for d in day_num],
    })

    def _lookup(source: dict) -> np.ndarray:
        agg = source["agg"]
        dcols = [c for c in agg.columns if str(c).isdigit()
                 and 1 <= int(c) <= 31]
        if not dcols:
            return np.full(len(cand), np.nan)
        long = agg.melt(id_vars=["NAMA RESTO", "NAMA BARANG"],
                        value_vars=dcols, var_name="_day",
                        value_name="_val")
        long["_rk"] = long["NAMA RESTO"].astype(str).str.strip()
        long["_ik"] = long["NAMA BARANG"].astype(str).str.strip()
        m = cand.merge(long[["_rk", "_ik", "_day", "_val"]],
                       on=["_rk", "_ik", "_day"], how="left")
        return m["_val"].to_numpy(dtype=float)

    # Bulan lalu = bulan pembanding TERBARU (label terparse terbesar).
    latest = max(ok, key=lambda m: month_sort_key(m.get("label")))
    last_vals = _lookup(latest)
    out.iloc[idx, out.columns.get_loc("NILAI BULAN LALU")] = last_vals
    ratio = np.where((last_vals > 0) & (nilai > 0),
                     nilai / np.where(last_vals > 0, last_vals, 1), np.nan)
    out.iloc[idx, out.columns.get_loc("RASIO VS BULAN LALU")] = ratio

    if typical is not None:
        typ_vals = _lookup(typical)
        out.iloc[idx, out.columns.get_loc("TIPIKAL BEBERAPA BULAN")] = typ_vals

    # Tambahan kalimat di ALASAN HARI (bila kolom ada & rasio kuat).
    th = DEFAULT_TH_HIST_RATIO
    try:
        cfg_th = dict((config or {}).get("thresholds") or {})
        th = float(cfg_th.get("TH_HARI_HIST_RATIO", DEFAULT_TH_HIST_RATIO))
    except (TypeError, ValueError):
        th = DEFAULT_TH_HIST_RATIO
    if "ALASAN HARI" in out.columns:
        col_alasan = out.columns.get_loc("ALASAN HARI")
        for p, r, v in zip(idx, ratio, last_vals):
            if r == r and r >= th:
                tip = _fmt_ratio(float(r))
                val_s = _fmt_num(float(v)) if v == v else "—"
                extra = f" ; {tip} bulan lalu ({val_s})"
                # Akses POSISIONAL (p = np.flatnonzero) — index df asli
                # bisa non-kontigu (slice anomali), .at label-based salah.
                cur = out.iat[p, col_alasan]
                cur = str(cur) if pd.notna(cur) and str(cur).strip() else ""
                if "bulan lalu" not in cur:
                    out.iat[p, col_alasan] = cur + extra
    return out


# ============================================================
# PERSISTENSI DAFTAR FILE (diingat antar sesi)
# ============================================================

HISTORY_STORE_NAME = "history_files.json"


def history_store_path() -> Path:
    """Jalur history_files.json (frozen-aware — pola filters.py).

    Dev: repo root. Exe PyInstaller: berdampingan dgn exe (bukan _MEIPASS
    yang terhapus saat exit — lihat frozen.py).
    """
    if is_frozen():
        return exe_dir() / HISTORY_STORE_NAME
    return Path(__file__).resolve().parent.parent / HISTORY_STORE_NAME


def _backup_corrupt(p: Path) -> None:
    """Rename file korup ke .bak (best-effort — pola filters.py)."""
    try:
        bak = p.with_name(p.name + ".bak")
        if bak.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            bak = p.with_name(f"{p.name}.bak.{stamp}")
        os.replace(p, bak)
    except OSError:
        pass


def load_history_entries(path: Path | str | None = None) -> list[dict]:
    """Muat daftar file pembanding tersimpan → [{"path":…, "label":…}].

    File korup → di-backup lalu mulai bersih (pola filters.py). Selalu
    list (tidak pernah raise).
    """
    p = Path(path) if path else history_store_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", []) if isinstance(data, dict) else []
        out = []
        for e in entries:
            if isinstance(e, dict) and e.get("path"):
                out.append({"path": str(e["path"]),
                            "label": (str(e["label"])
                                      if e.get("label") else None)})
        return out
    except json.JSONDecodeError:
        _backup_corrupt(p)
        return []
    except OSError:
        return []


def save_history_entries(entries: list[dict],
                         path: Path | str | None = None) -> bool:
    """Simpan daftar file pembanding (atomic: .tmp → os.replace)."""
    p = Path(path) if path else history_store_path()
    tmp = p.with_name(p.name + ".tmp")
    clean = [{"path": str(e.get("path", "")),
              "label": e.get("label") or None}
             for e in (entries or []) if e.get("path")]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"entries": clean}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False
