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
_MONTH_RE = re.compile(
    r"\b(JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|"
    r"OKTOBER|NOVEMBER|DESEMBER|JANUARY|MARCH|MAY|JUNE|JULY|AUGUST|"
    r"OCTOBER|DECEMBER)(?![A-Za-z])[ \-_]*(\d{4})?",
    re.IGNORECASE,
)

# Kontrak kolom agregat pembanding (dipakai UI + test).
AGG_COLS = ["NAMA RESTO", "NAMA BARANG", "TOTAL", "HARI AKTIF"]
JENIS_TOTALS_COLS = ["JENIS", "TOTAL"]

# Kolom bukti hari vs history (tab Hari Mencurigakan).
HIST_DAY_COLS = ["NILAI BULAN LALU", "RASIO VS BULAN LALU",
                 "TIPIKAL BEBERAPA BULAN"]

DEFAULT_TH_HIST_RATIO = 3.0


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


def _aggregate(kept: pd.DataFrame, key_akhir: int) -> pd.DataFrame:
    """Agregat kuantiti per (NAMA RESTO × NAMA BARANG).

    Nilai hari dijumlah lintas baris keterangan; TOTAL = jumlah hari;
    HARI AKTIF = banyak hari > 0. Murni vektor (groupby + sum).
    """
    day_cols = _day_cols_of(kept)
    empty = pd.DataFrame(columns=AGG_COLS + [str(d) for d in range(1, 32)])
    if kept.empty or not day_cols or "NAMA BARANG" not in kept.columns:
        return empty
    if "NAMA RESTO" not in kept.columns:
        kept = kept.assign(**{"NAMA RESTO": ""})

    num = kept[day_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
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


def _jenis_totals(kept: pd.DataFrame) -> pd.DataFrame:
    """TOTAL kuantiti per JENIS (SUSUT/TRIAL/WASTE) — tabel 'Per JENIS'."""
    empty = pd.DataFrame(columns=JENIS_TOTALS_COLS)
    if kept.empty or "JENIS" not in kept.columns:
        return empty
    day_cols = _day_cols_of(kept)
    if not day_cols:
        return empty
    num = kept[day_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    tmp = pd.DataFrame({
        "JENIS": kept["JENIS"].astype(str).str.strip().str.upper(),
        "TOTAL": num.sum(axis=1).to_numpy(),
    })
    return tmp.groupby("JENIS", as_index=False, dropna=False).agg(
        TOTAL=("TOTAL", "sum"))


def _month_dict(agg: pd.DataFrame, jenis: pd.DataFrame, label: str,
                key_akhir: int, rows_kept: int, rows_raw: int = 0) -> dict:
    """Bentuk standar entri bulan (kontrak konsumen UI/test)."""
    return {
        "label": label,
        "key_akhir": int(key_akhir) if key_akhir else 31,
        "agg": agg,
        "jenis_totals": jenis,
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
        agg = _aggregate(kept, ka)
        d = _month_dict(agg, _jenis_totals(kept), base["label"] or p.stem,
                        ka, len(kept), len(raw))
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
    agg = _aggregate(kept, ka)
    d = _month_dict(agg, _jenis_totals(kept), label, ka, len(kept), len(df))
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
        m = m.fillna({"TOTAL_x": 0.0, "TOTAL_y": 0.0})
        m = m.rename(columns={"TOTAL_x": "Bulan Ini",
                              "TOTAL_y": "Pembanding"})
        m["Selisih"] = m["Bulan Ini"] - m["Pembanding"]
        m["Perubahan %"] = [_pct(c, base) for c, base
                            in zip(m["Bulan Ini"], m["Pembanding"])]
        per_jenis = m.sort_values("Bulan Ini", ascending=False).reset_index(
            drop=True)[JENIS_COLS]

    # ---- cabang / item / baru / hilang ----
    key = ["NAMA RESTO", "NAMA BARANG"]
    empty_items = pd.DataFrame(columns=ITEM_COLS)
    empty_new = pd.DataFrame(columns=NEW_ITEM_COLS)
    empty_gone = pd.DataFrame(columns=GONE_ITEM_COLS)
    if ta.empty and tb.empty:
        branch = pd.DataFrame(columns=BRANCH_COLS)
        items, new_items, gone_items = empty_items, empty_new, empty_gone
    else:
        ga = ta.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
        gb = tb.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
        mb = ga.merge(gb, on="NAMA RESTO", how="outer")
        mb = mb.fillna({"TOTAL_x": 0.0, "TOTAL_y": 0.0}).rename(
            columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
        mb["Selisih"] = mb["Bulan Ini"] - mb["Pembanding"]
        mb["Perubahan %"] = [_pct(c, base) for c, base
                             in zip(mb["Bulan Ini"], mb["Pembanding"])]
        mb = mb.reindex(mb["Selisih"].abs().sort_values(
            ascending=False).index).head(top_n)
        branch = mb.reset_index(drop=True)[BRANCH_COLS]

        m = ta.merge(tb, on=key, how="outer")
        m = m.fillna({"TOTAL_x": 0.0, "TOTAL_y": 0.0}).rename(
            columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
        m["Selisih"] = m["Bulan Ini"] - m["Pembanding"]
        m["Perubahan %"] = [_pct(c, base) for c, base
                            in zip(m["Bulan Ini"], m["Pembanding"])]
        m = m.reindex(m["Selisih"].abs().sort_values(
            ascending=False).index).head(top_n)
        items = m.reset_index(drop=True)[ITEM_COLS]
        # Baru = hanya di bulan INI (tidak ada bulan lalu); hilang = sebaliknya.
        full = ta.merge(tb, on=key, how="outer")
        full = full.fillna({"TOTAL_x": 0.0, "TOTAL_y": 0.0}).rename(
            columns={"TOTAL_x": "Bulan Ini", "TOTAL_y": "Pembanding"})
        new_items = full[full["Pembanding"] <= 0][
            key + ["Bulan Ini"]].sort_values(
            "Bulan Ini", ascending=False).head(
            top_n).reset_index(drop=True)[NEW_ITEM_COLS]
        gone_items = full[full["Bulan Ini"] <= 0][
            key + ["Pembanding"]].sort_values(
            "Pembanding", ascending=False).head(
            top_n).reset_index(drop=True)[GONE_ITEM_COLS]

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

    labels = [str(m.get("label") or "?") for m in ok]
    d = _month_dict(wide, jenis_typ, "Tipikal", ka_typ, len(wide), 0)
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
