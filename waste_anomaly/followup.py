"""followup.py — daftar follow-up baris anomali (v2.12.0).

Konsep: user mencentang baris mencurigakan di tabel Anomali → baris
terkumpul di tab "Follow Up" dalam format rekap (TOTAL · AVG · MAX ·
SOURCE DATA · JENIS · KETERANGAN · NAMA BARANG · NAMA RESTO · SATUAN ·
hari 1..31) — persis kolom inti DATA_WASTE, tanpa agregasi baru (nilai
tampil apa adanya dari barisnya; skor anomali TIDAK diubah).

Modul murni (tanpa Qt) — dipakai ui/state.py + view:

- ``fingerprint_series(df)`` — identitas baris STABIL lintas sesi:
  md5 atas 6 kolom kunci + nilai hari '1'..'31'. Kenapa BUKAN kunci
  bisnis saja: data asli memuat baris KEMBAR (diukur 25.901 baris:
  1.871 grup duplikat, maks 8 baris/grup — 3.760 identik nilai).
  Sidik jari nilai membedakan kembar yang nilainya beda; kembar yang
  PERSIS identik otomatis menyatu (didedup di select_followup_rows).
  Stabilitas dtype: kolom hari dinormalisasi float64 SEBELUM str
  (5 vs 5.0 lintas file → sidik jari sama).
- ``select_followup_rows(df, fps, keys)`` — baris ber-sidik jari ∈ keys
  + dedup kembar (keep first).
- ``suspicious_days(df, fps)`` — hari mencurigakan per baris utk
  penandaan warna (merah = HARI TERSANGKA/HARI MAX — konsisten peta
  hari pop-up detail; amber = nilai ≥ 2× rata-rata HARI AKTIF —
  lonjakan sekunder).
- ``load/save_followup_keys`` — persistensi followup.json (pola
  filters.json: atomic write + backup file korup + frozen-aware path).
- ``export_followup_xlsx`` — sheet "FOLLOW UP": kolom format rekap +
  3 kolom serah-terima kosong (PIC/KATEGORI/PENYEBAB — diisi petugas,
  konvensi REKAP MENTAH); hari mencurigakan diberi fill merah/amber.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .frozen import exe_dir, is_frozen

_LOG = logging.getLogger("waste_anomaly.followup")

# 6 kolom kunci rekap (urutan konvensi M code — group_keys_full).
KEY_COLS = [
    "SOURCE DATA", "JENIS", "KETERANGAN",
    "NAMA BARANG", "NAMA RESTO", "SATUAN",
]
# Kolom hari (dinormalisasi '1'..'31').
DAY_COLS = [str(i) for i in range(1, 32)]

# Kolom identitas tersembunyi di df tampilan (disembunyikan via
# visible_cols — ikut travel saat model di-sort).
FP_COL = "__FP"
CHECK_COL = "✓"

# Format tabel Follow Up — urutan PERSIS permintaan user (v2.12.0):
# TOTAL AVG MAX SOURCE DATA JENIS KETERANGAN NAMA BARANG NAMA RESTO
# SATUAN 1..31.
FOLLOWUP_COLS = [
    "TOTAL", "AVG", "MAX", "SOURCE DATA", "JENIS", "KETERANGAN",
    "NAMA BARANG", "NAMA RESTO", "SATUAN",
]
# Kolom serah-terima kosong di export (diisi petugas follow-up —
# konvensi sheet REKAP MENTAH).
HANDOVER_COLS = ["PIC", "KATEGORI", "PENYEBAB TERJADINYA WASTE"]

# Warna penanda hari (hex tanpa '#'; konsisten peta hari pop-up detail
# view_anomali._day_map: merah #fee2e2/#dc2626; amber = amber-100).
RED_BG, RED_FG = "FEE2E2", "DC2626"
AMBER_BG = "FEF3C7"


# ============================================================
# SIDIK JARI BARIS
# ============================================================

def day_cols(df: pd.DataFrame) -> list[str]:
    """Kolom hari '1'..'31' yang benar-benar ada di df (urut naik)."""
    return [c for c in DAY_COLS if c in df.columns]


def fingerprint_series(df: pd.DataFrame) -> pd.Series:
    """Sidik jari (md5 hex) per baris — 6 kolom kunci + nilai hari NON-NOL.

    Deterministik lintas sesi/file: kolom teks → ``astype(str)``; kolom
    hari → ``to_numeric → float64 → str`` (5 vs 5.0 samar). Hari bernilai
    0/kosong TIDAK ikut hash (segmen kosong) → dataset 30-hari vs 31-hari
    dengan hari ke-31 kosong menghasilkan sidik jari SAMA (baris yang
    sama tetap terlacak); hari bernilai hilang kolomnya → sidik jari
    berubah (nilai memang tak ada lagi — mark wajar terpangkas).
    Index hasil = index df (siap align/isin).
    """
    n = len(df)
    parts: list[pd.Series] = []
    for c in KEY_COLS:
        if c in df.columns:
            parts.append(df[c].astype(str))
        else:
            parts.append(pd.Series(["·"] * n, index=df.index, dtype="object"))
    for c in day_cols(df):
        num = pd.to_numeric(df[c], errors="coerce").astype("float64")
        seg = pd.Series("", index=df.index, dtype="object")
        nz = num.notna() & (num != 0)
        if nz.any():
            seg.loc[nz] = c + ":" + num[nz].astype(str)
        parts.append(seg)
    if not parts:  # degenerate — df tanpa kolom yang dikenal
        return pd.Series([""] * n, index=df.index)
    joined = parts[0].astype(str)
    for p in parts[1:]:
        joined = joined.str.cat(p.astype(str), sep="|")
    # segmen hari kosong (nilai 0/NaN) → run '|…|' kosong → rapikan agar
    # kolom hari yang tak ada ≡ kolom hari bernilai nol.
    joined = joined.str.replace(r"\|{2,}", "|", regex=True).str.rstrip("|")

    def _md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8", "surrogatepass")).hexdigest()

    return joined.map(_md5)


def select_followup_rows(df: pd.DataFrame, fps: pd.Series,
                         keys: Iterable[str]) -> pd.DataFrame:
    """Baris df ber-sidik jari ∈ keys (SALINAN + kolom __FP + dedup).

    - mask via ``fps.isin(set(keys))`` (fps = fingerprint_series(df),
      index identik df).
    - baris kembar identik-nilai → sidik jari sama → didedup
      (keep='first') — daftar follow-up per konten, bukan per salinan.
    """
    mask = fps.isin(set(keys))
    out = df[mask].copy()
    out[FP_COL] = fps[mask]
    if FP_COL in out.columns and len(out) > 1:
        out = out.drop_duplicates(subset=FP_COL, keep="first")
    return out


# ============================================================
# HARI MENCURIGAKAN (penanda warna)
# ============================================================

def suspicious_days(df: pd.DataFrame,
                    fps: pd.Series) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Hari mencurigakan per baris — utk pewarnaan tabel + export.

    Returns:
        red:   {fp: hari} — hari TERSANGKA (fallback HARI MAX) —
               merah, konsisten peta hari pop-up detail (v2.9.0).
        amber: {(fp, kolom_hari)} — nilai ≥ 2× rata-rata hari AKTIF
               (fallback AVG), nilai > 0, bukan hari merah —
               lonjakan sekunder (amber).
    """
    red: dict[str, int] = {}
    amber: set[tuple[str, str]] = set()
    if len(df) == 0:
        return red, amber
    dcols = day_cols(df)
    if not dcols:
        return red, amber
    # hari tersangka per BARIS (pola pop-up detail _day_map): HARI
    # TERSANGKA (hanya baris kandidat anomali) → fallback HARI MAX
    # (hari nilai terbesar) — fallback level NILAI, bukan level kolom.
    ters = hmax = None
    if "HARI TERSANGKA" in df.columns:
        ters = pd.to_numeric(df["HARI TERSANGKA"], errors="coerce")
    if "HARI MAX" in df.columns:
        hmax = pd.to_numeric(df["HARI MAX"], errors="coerce")
    # basis rata-rata: hari aktif lebih adil (hari kosong tak menarik
    # rata-rata turun) — fallback AVG bulanan.
    avg = None
    for src in ("AVG AKTIF", "AVG"):
        if src in df.columns:
            avg = pd.to_numeric(df[src], errors="coerce")
            break
    vals = df[dcols].apply(pd.to_numeric, errors="coerce")
    for i in range(len(df)):
        fp = str(fps.iloc[i])
        rday: int | None = None
        for series in (ters, hmax):
            if series is None:
                continue
            try:
                v = series.iloc[i]
                if v == v and 1 <= float(v) <= 31:  # not NaN + rentang hari
                    rday = int(v)
                    break
            except (TypeError, ValueError):
                continue
        if rday is not None and str(rday) in dcols:
            red[fp] = rday
        base = None
        if avg is not None:
            b = avg.iloc[i]
            if b == b and b > 0:  # not NaN + positif (guard: base 0 → semua amber)
                base = float(b)
        if base is not None:
            threshold = 2.0 * base
            row_vals = vals.iloc[i]
            for c in dcols:
                v = row_vals[c]
                if v == v and v > 0 and float(v) >= threshold:
                    day = int(c)
                    if day != rday:
                        amber.add((fp, c))
    return red, amber


# ============================================================
# PERSISTENSI (followup.json — pola filters.json)
# ============================================================

def followup_path() -> Path:
    """Jalur followup.json (dinamis, frozen-aware — pola profiles_path)."""
    if is_frozen():
        return exe_dir() / "followup.json"
    return Path(__file__).resolve().parent.parent / "followup.json"


def _backup_corrupt_file(p: Path) -> None:
    """File korup di-rename .bad (tidak hilang) — pola filters.py.

    os.replace menimpa .bad lama → hanya salinan korup TERBARU yang
    disimpan (tidak menumpuk)."""
    try:
        os.replace(p, p.with_suffix(p.suffix + ".bad"))
    except OSError:
        pass  # rename gagal (file terkunci?) — muat ulang dari nol


def load_followup_keys(path: Path | str | None = None) -> list[str]:
    """Muat daftar sidik jari tersimpan (urutan centang dipertahankan).

    File absen → []. File korup → backup .bad + [] (bukan crash).
    """
    p = Path(path) if path else followup_path()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("bentuk 'rows' bukan list")
        keys = [str(k) for k in rows if k]
        return keys
    except (json.JSONDecodeError, ValueError, OSError) as e:
        _LOG.warning("followup.json korup (%s) — mulai dari daftar kosong", e)
        _backup_corrupt_file(p)
        return []


def save_followup_keys(keys: list[str],
                       path: Path | str | None = None) -> bool:
    """Simpan daftar sidik jari (atomic: tulis .tmp → replace)."""
    p = Path(path) if path else followup_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "rows": list(keys)}, f,
                      ensure_ascii=False, indent=0)
        os.replace(tmp, p)
        return True
    except OSError as e:
        _LOG.warning("gagal simpan followup.json: %s", e)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


# ============================================================
# EXPORT EXCEL
# ============================================================

def export_followup_xlsx(rows: pd.DataFrame, path: str,
                         red: dict[str, int],
                         amber: set[tuple[str, str]]) -> str:
    """Tulis sheet 'FOLLOW UP' — format rekap + kolom serah-terima.

    - Kolom: FOLLOWUP_COLS + hari yang ada + HANDOVER_COLS (kosong).
    - Hari merah (tersangka) → fill FEE2E2 + font DC2626 tebal;
      amber (≥ 2× rata-rata hari aktif) → fill FEF3C7.
    - Freeze header + auto-filter (nyaman di-sort di Excel).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    fill_red = PatternFill("solid", start_color=RED_BG)
    fill_amber = PatternFill("solid", start_color=AMBER_BG)
    font_red = Font(bold=True, color=RED_FG)
    font_head = Font(bold=True)

    cols = ([c for c in FOLLOWUP_COLS if c in rows.columns]
            + day_cols(rows)
            + [c for c in HANDOVER_COLS])
    wb = Workbook()
    ws = wb.active
    ws.title = "FOLLOW UP"
    ws.append(cols)
    for cell in ws[1]:
        cell.font = font_head
        cell.alignment = Alignment(horizontal="center")
    fps = rows[FP_COL] if FP_COL in rows.columns else None
    for i in range(len(rows)):
        fp = str(fps.iloc[i]) if fps is not None else ""
        rday = red.get(fp)
        excel_row = i + 2
        for j, c in enumerate(cols):
            if c in HANDOVER_COLS:
                v = None
            elif c in rows.columns:
                v = rows[c].iloc[i]
                if pd.isna(v):
                    v = None
                elif isinstance(v, (np.integer, np.floating)):
                    # Bug-hunt 3-a: np.int64 BUKAN subclass int python —
                    # tanpa ini 16/31 kolom hari di data asli (int64)
                    # terekspor sebagai TEKS ('0'), SUM/sort Excel rusak
                    # (jebakan yang sama dgn V26-M1 models.py).
                    v = v.item()  # int tetap int, float tetap float
                elif isinstance(v, (int, float)):
                    v = float(v)
                else:
                    v = str(v)
            else:
                v = None
            cell = ws.cell(row=excel_row, column=j + 1, value=v)
            if c in DAY_COLS and v is not None:
                day = int(c)
                if rday is not None and day == rday:
                    cell.fill = fill_red
                    cell.font = font_red
                elif (fp, c) in amber:
                    cell.fill = fill_amber
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = (f"A1:{get_column_letter(len(cols))}"
                          f"{len(rows) + 1}")
    for j, c in enumerate(cols, start=1):
        width = 10 if c in DAY_COLS else (
            26 if c in ("NAMA BARANG", "KETERANGAN", "SOURCE DATA",
                        "PENYEBAB TERJADINYA WASTE") else 16)
        ws.column_dimensions[get_column_letter(j)].width = width
    wb.save(path)
    return path
