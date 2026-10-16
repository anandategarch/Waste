"""
rekap_import.py — Olah file REKAP MENTAH mentah → workbook DATA_WASTE standar.

MASALAH yang diselesaikan (v2.14.0):
User menyimpan rekap bulanan mentah dari sistem (mis. "REKAP MENTAH_01-31
AGUSTUS 2026_TEGAR.xlsx") — satu sheet berisi SEMUA JENIS (WASTE / SUSUT /
TRIAL / BOM / SO / BARANG MASUK / BARANG KELUAR / STOK AWAL / REWORK /
RETUR / ...) ±40-50 ribu baris lebar 42 kolom. Sebelumnya user harus
mengolah MANUAL di Excel (filter + formula + Power Query) supaya jadi
struktur standar DATA_WASTE 53 kolom yang dibaca pipeline. Modul ini
menggantikan olahan manual tersebut — satu panggilan:

    convert_rekap_mentah("REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx")
    → "DATA_WASTE Agustus 2026.xlsx" (siap Mulai Pipeline)

Langkah olahan (mirror olahan manual user, terverifikasi terhadap file
asli 54.160 baris + DATA_WASTE.xlsx standar 25.901 baris):
  1. Cari sheet rekap: kandidat nama sheet dari config (loader.find_sheet
     — token match "Rekap Mentah" ⊆ "REKAP MENTAH") + fallback deteksi
     schema (header ≤6 baris pertama: kolom NAMA RESTO + JENIS + NAMA
     BARANG + ≥3 kolom hari — pola fn_rekap_mentah stock-monitoring).
  2. Saring JENIS ∈ {WASTE, SUSUT, TRIAL} (case/whitespace-toleran) —
     baris non-waste (BOM/SO/stok/retur) dibuang dari sheet DATA_WASTE;
     stage_01 pipeline melakukan saringan IDENTIK, file standar memang
     hanya memuat 3 jenis ini.
  3. Ekstrak baris JENIS == "BOM" → TOTAL BOM per (NAMA RESTO, NAMA
     BARANG) = jumlah kolom hari. Total ini ditulis DUA arah:
     (a) kolom inline "TOTAL BOM" di sheet DATA_WASTE — PRIORITAS
         stage_05 (v2.3.0: "TOTAL BOM TIDAK di-drop — user pakai kolom
         ini sebagai BOM source");
     (b) sheet "BOM" terpisah (Nomor # / Nama Barang / TOTAL BOM) —
         jalur fallback loader; sinyal BOM S6/S7 hidup lewat keduanya.
  4. Kolom turunan inline dengan SEMANTIKA IDENTIK pipeline (supaya nilai
     file hasil olahan == nilai recompute app):
     - TOTAL/Count Hari/Status2 = stage_02 (sum hari; count hari > 0;
       "Kosong" bila TOTAL 0/NaN selain itu "Isi")
     - AVG = stage_02 mean(skipna) kolom hari (bukan TOTAL/31 mentah)
     - MAX = stage_02 max kolom hari
     - % to BOM & Rill % to BOM = stage_05 (TOTAL/TOTAL BOM di-guard
       TOTAL BOM > 0, selain itu 0.0)
  5. Tulis workbook openpyxl MODE write_only (±25 ribu baris × 53 kolom
     ≈ 1,3 juta sel — write-only ±5-10× lebih cepat dari mode normal;
     NaN dikonversi None = sel kosong). Sheet yang ditulis:
     "DATA_WASTE" (53 kolom urutan standar README) + "BOM" + salinan
     "DATABASE_SATUAN" bila workbook sumber memilikinya.

Pipeline tetap IDEMPOTENT: semua kolom turunan di atas akan di-drop &
dihitung ulang oleh stage 1-14 — kolom inline di file olahan supaya file
JUGA berdiri sendiri (bisa dibuka/dianalisa manual user tanpa app).

Kolom yang dibiarkan KOSONG (output M-code user: STATUS, HELPER, MAX
TOTAL, AVG TOTAL, KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA
GABUNGAN, RANGKING WASTE) — semua dihitung ulang pipeline (README tabel
53 kolom: "Opsional (akan dihitung ulang)").
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .loader import (
    _guard_xls,
    _key_str,
    _normalize_columns,
    _read_excel_fast,
    find_sheet,
    list_sheets,
)
from .period_history import detect_month_label
from .utils import load_config

# Saringan JENIS — identik HISTORY_KEEP_JENIS period_history & filter
# stage_01 (satu sumber kebenaran semantik: {WASTE, SUSUT, TRIAL}).
_KEEP_JENIS = ("WASTE", "SUSUT", "TRIAL")

# Kolom wajib schema input (mirror schema.REQUIRED_COLUMNS — converter
# memvalidasi SEBELUM menulis supaya file olahan selalu lolos validate_).
_REQUIRED_COLS = ("SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
                  "NAMA RESTO", "SATUAN")

# Header hari valid: "1".."31" (setelah _normalize_columns header numerik
# calamine 1.0 → "1").
_DAY_SET = {str(d) for d in range(1, 32)}

# Urutan 53 kolom standar README (bagian opsional diisi nilai hitungan /
# dibiarkan kosong; hari mengikuti kolom yang ADA di sumber — jujur,
# tanpa fabrikasi kolom hari yang tidak ada di rekap).
_HEAD_COLS = ["STATUS", "HELPER", "MAX TOTAL", "AVG TOTAL", "TOTAL BOM",
              "% to BOM", "TOTAL", "AVG", "MAX"]
_TAIL_COLS = ["Status2", "KETERANGAN GABUNGAN", "KONTRIBUSI TERBESAR",
              "SOURCE DATA GABUNGAN", "Count Hari", "RANGKING WASTE",
              "Rill % to BOM"]

# Nama sheet output — kandidat #1 config input_sheets supaya loader
# menemukannya lewat fase EXACT (bukan token — tak ada ambiguitas).
_SHEET_DATA = "DATA_WASTE"
_SHEET_BOM = "BOM"
_SHEET_SATUAN = "DATABASE_SATUAN"


class RekapImportError(ValueError):
    """Input rekap tidak bisa diolah — pesan sudah user-friendly
    (pola SchemaValidationError: daftar masalah + saran perbaikan)."""


def _log(logger: Callable[[str], Any] | None, msg: str) -> None:
    if logger is not None:
        logger(msg)


def _day_cols_of(df: pd.DataFrame) -> list[str]:
    """Kolom hari '1'..'31' yang ADA di frame (urutan numerik)."""
    return [c for c in df.columns if c in _DAY_SET]


def _detect_header_row(peek: pd.DataFrame) -> int | None:
    """Cari baris header rekap dalam peek (raw header=None, ≤6 baris).

    Schema wajib: NAMA RESTO + JENIS + NAMA BARANG (case/strip-toleran)
    + ≥3 kolom hari pada baris itu. Return indeks baris atau None.
    (Pola fn_rekap_mentah._detect_rekap_header stock-monitoring — file
    rekap user kadang ber-baris judul di atas header.)"""
    if peek is None or peek.empty:
        return None
    for hr in range(min(6, len(peek))):
        headers = [str(h).strip().upper() if h is not None else ""
                   for h in peek.iloc[hr].tolist()]
        if any(rc not in headers for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG")):
            continue
        n_days = sum(1 for h in headers
                     if h not in ("", "NONE", "NAN") and h in _DAY_SET)
        if n_days >= 3:
            return hr
    return None


def _promote_at(df: pd.DataFrame, hr: int) -> pd.DataFrame:
    """Baris hr jadi header (duplikat diberi suffix _1/_2 — mirror
    _promote_at fn_rekap_mentah; header None → ColumnN)."""
    headers = df.iloc[hr].tolist()
    body = df.iloc[hr + 1:].reset_index(drop=True)
    new_cols: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(headers):
        if h is None or (isinstance(h, float) and math.isnan(h)):
            h = f"Column{i + 1}"
        h = str(h)
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        new_cols.append(h)
    body.columns = new_cols
    return body


def find_rekap_sheet(path: Path, config: dict,
                     logger=None) -> tuple[str, int]:
    """Resolve sheet rekap + baris header (0 = baris pertama).

    1. Kandidat config (loader.find_sheet — exact lalu token unik;
       "Rekap Mentah" token-match sheet "REKAP MENTAH" file user asli).
       Sheet kandidat divalidasi schema (header baris 0); tak lolos →
       lanjut fallback, BUKAN pakai mentah-mentah (sheet kandidat bisa
       kebetulan bernama sama tapi beda isi).
    2. Fallback: scan SEMUA sheet — deteksi baris header schema rekap
       (≤6 baris pertama). Ambil sheet pertama yang lolos.
    Return (nama_sheet, header_row). Raise RekapImportError bila tidak
    ada sheet rekap sama sekali."""
    sheets = list_sheets(path)
    if not sheets:
        raise RekapImportError(
            f"Workbook tidak punya sheet yang bisa dibaca: {path.name}")
    candidates = list(config.get("input_sheets", {}).get("rekap_mentah", []))
    # Tambahan eksplisit "REKAP MENTAH" (nama sheet file user asli —
    # kandidat config memakai varian underscore/case lain).
    for extra in ("REKAP MENTAH", "rekap mentah"):
        if extra not in candidates:
            candidates.append(extra)

    # 1. Kandidat — validasi schema baris-0 sebelum percaya
    try:
        name = find_sheet(candidates, sheets)
    except ValueError:
        name = None
    if name is not None:
        try:
            df0 = _read_excel_fast(path, sheet_name=name, header=0, nrows=6)
        except Exception:
            df0 = None
        if df0 is not None and not df0.empty:
            df0 = _normalize_columns(df0)
            cols = [str(c).strip().upper() for c in df0.columns]
            if all(rc in cols for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG")) \
                    and sum(1 for c in cols if c in _DAY_SET) >= 3:
                _log(logger, f"[rekap_import] sheet '{name}' (kandidat config)")
                return name, 0

    # 2. Fallback — scan semua sheet + deteksi baris header
    for sn in sheets:
        try:
            raw = pd.read_excel(path, sheet_name=sn, header=None, nrows=8,
                                dtype=object)
        except Exception:
            continue
        hr = _detect_header_row(raw)
        if hr is not None:
            _log(logger, f"[rekap_import] sheet '{sn}' (deteksi schema, "
                         f"header baris {hr + 1})")
            return sn, hr

    raise RekapImportError(
        f"Sheet REKAP MENTAH tidak ditemukan di {path.name}. Cari sheet "
        f"ber-kolom NAMA RESTO + JENIS + NAMA BARANG + kolom hari 1-31 "
        f"(sheet tersedia: {', '.join(sheets[:8])}"
        f"{'…' if len(sheets) > 8 else ''}).")


def _sanitize_label(text: str) -> str:
    """Bersihkan label untuk nama file output (buang karakter aneh,
    rapikan spasi ganda; label dari nama file sudah aman — ini jaga
    ekstra untuk stem aneh)."""
    s = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    return re.sub(r"\s+", " ", s).strip()


def _default_out_path(source: Path, label: str | None) -> Path:
    """Nama output default di folder SUMBER: "DATA_WASTE <label>.xlsx"
    (label bulan dari nama file: "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR"
    → "DATA_WASTE Agustus 2026.xlsx" — banding periode bisa mem-parse
    bulannya kembali). Guard anti menimpa file SUMBER (nama sama saat
    sumber memang sudah bernama "DATA_WASTE <label>.xlsx")."""
    stem = _sanitize_label(label or source.stem) or "olahan"
    out = source.with_name(f"DATA_WASTE {stem}.xlsx")
    if out.exists() and source.exists() \
            and out.resolve() == source.resolve():
        out = source.with_name(f"DATA_WASTE {stem} (olah).xlsx")
    return out


def _cell(v: Any) -> Any:
    """Konversi nilai untuk openpyxl write-only: NaN/NaT/None → None
    (sel kosong), numpy integer → int, numpy floating → float."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or (isinstance(v, type(pd.NaT))):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        fv = float(v)
        return None if math.isnan(fv) else fv
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _strip_series(s: pd.Series) -> pd.Series:
    """Strip string + pertahankan NaN (bukan 'nan'): passthrough identitas."""
    return s.where(s.isna(), s.astype(str).str.strip())


def _find_satuan_sheet(path: Path, config: dict) -> str | None:
    """Sheet DATABASE_SATUAN di workbook SUMBER (bila ada → disalin)."""
    try:
        sheets = list_sheets(path)
        candidates = list(config.get("input_sheets", {}).get(
            "database_satuan", []))
        return find_sheet(candidates, sheets)
    except Exception:  # noqa: BLE001 — best-effort, sheet opsional
        return None


def convert_rekap_mentah(source: str | os.PathLike,
                         out_path: str | os_PathLike | None = None,
                         config: dict | None = None,
                         logger=None) -> dict:
    """Olah file REKAP MENTAH mentah → workbook DATA_WASTE standar.

    Return dict ringkasan (out_path, sheet, rows_raw, rows_kept,
    jenis_counts, bom_pairs, bom_matched, resto_count, item_count,
    month_label, day_count, satuan_sheet) — dipakai UI untuk log +
    dialog ringkasan + auto-isi kolom workbook.

    Raise RekapImportError (pesan ramah) untuk: file hilang / sheet rekap
    tak ada / kolom wajib absen. Error lain (file korup dkk) diteruskan
    apa adanya — diterjemahkan friendly_file_error di batas UI (pola D7).
    """
    src = Path(source)
    if not src.exists():
        raise RekapImportError(f"File tidak ditemukan: {src}")
    try:
        _guard_xls(src)
    except ValueError as e:
        # Guard .xls sudah berpesan jelas — dibungkus RekapImportError
        # supaya worker memperlakukannya jalur ramah (tanpa traceback).
        raise RekapImportError(str(e)) from e
    cfg = config if config is not None else load_config()

    sheet, header_row = find_rekap_sheet(src, cfg, logger=logger)
    if header_row == 0:
        raw = _read_excel_fast(src, sheet_name=sheet, header=0)
    else:
        # Header bergeser (baris judul di atas) — baca raw lalu promote
        # di memori (mirror _promote_at fn_rekap_mentah stock-monitoring).
        raw_full = pd.read_excel(src, sheet_name=sheet, header=None,
                                 dtype=object)
        raw = _promote_at(raw_full, header_row)
    raw = _normalize_columns(raw)
    rows_raw = len(raw)
    _log(logger, f"[rekap_import] terbaca {rows_raw} baris × "
                 f"{len(raw.columns)} kolom dari sheet '{sheet}'")

    # --- Validasi kolom wajib (sebelum mengolah — file output harus
    # selalu lolos validate_rekap_schema pipeline) ---
    cols_upper = {str(c).strip().upper(): c for c in raw.columns}
    missing = [rc for rc in _REQUIRED_COLS if rc not in cols_upper]
    day_cols = _day_cols_of(raw)
    if missing:
        raise RekapImportError(
            f"Kolom wajib hilang dari sheet '{sheet}': {missing}. Rekap "
            f"mentah butuh kolom: {', '.join(_REQUIRED_COLS)} + kolom hari "
            f"1-31. Cek header sheet (baris judul di atas header?).")
    if len(day_cols) < 3:
        raise RekapImportError(
            f"Kolom hari 1-31 tidak ditemukan di sheet '{sheet}' (header "
            f"hari harus ANGKA 1..31). Kolom yang ada: "
            f"{[str(c) for c in raw.columns[:12]]}…")

    # --- Saring JENIS WASTE/SUSUT/TRIAL (strip+upper — mirror
    # _filter_waste period_history / stage_01) ---
    jenis_norm = raw["JENIS"].astype(str).str.strip().str.upper()
    keep_mask = jenis_norm.isin(_KEEP_JENIS)
    kept = raw[keep_mask].copy()
    if kept.empty:
        raise RekapImportError(
            f"Tidak ada baris JENIS WASTE/SUSUT/TRIAL di sheet '{sheet}' "
            f"(nilai JENIS unik: {sorted(set(jenis_norm.dropna().unique()))[:8]}…) "
            f"— tidak ada data waste untuk diolah.")
    jenis_counts = jenis_norm[keep_mask].value_counts().to_dict()
    _log(logger, f"[rekap_import] saring JENIS: {rows_raw} → {len(kept)} baris "
                 f"({', '.join(f'{k}: {v}' for k, v in sorted(jenis_counts.items()))})")

    # --- BOM: ekstrak JENIS=="BOM" → TOTAL BOM per (NAMA RESTO, NAMA
    # BARANG) — ditulis inline (prioritas stage_05) + sheet BOM ---
    bom_rows = raw[jenis_norm == "BOM"]
    bom_map: dict[tuple[str | None, str | None], float] = {}
    if not bom_rows.empty:
        bom_num = bom_rows[day_cols].apply(pd.to_numeric, errors="coerce")
        bom_tot = bom_num.fillna(0).sum(axis=1)
        k_resto = bom_rows["NAMA RESTO"].map(_key_str)
        k_barang = bom_rows["NAMA BARANG"].map(_key_str)
        for r, b, t in zip(k_resto, k_barang, bom_tot):
            if r is None or b is None:
                continue  # kunci kosong — tidak bisa di-join (pola H9-a)
            key = (r, b)
            bom_map[key] = bom_map.get(key, 0.0) + float(t)
    _log(logger, f"[rekap_import] BOM: {len(bom_rows)} baris JENIS=BOM → "
                 f"{len(bom_map)} pasangan (resto, barang)")

    # --- Statistik kolom hari (semantika stage_02) ---
    day_num = kept[day_cols].apply(pd.to_numeric, errors="coerce")
    day_filled = day_num.fillna(0)
    total = day_filled.sum(axis=1)
    with np.errstate(invalid="ignore"):
        avg = day_num.mean(axis=1, skipna=True)   # mean non-null (stage_02)
    mx = day_filled.max(axis=1)
    count_hari = (day_filled > 0).sum(axis=1)
    status2 = np.where(total == 0, "Kosong", "Isi")

    # --- TOTAL BOM inline: join key _key_str dua sisi (pola F1 v2.3.2 —
    # outlet numerik 1049.0 → "1049"; None → None tak join palsu) ---
    resto_key = kept["NAMA RESTO"].map(_key_str)
    barang_key = kept["NAMA BARANG"].map(_key_str)
    bom_inline = pd.Series(
        [bom_map.get((r, b)) for r, b in zip(resto_key, barang_key)],
        index=kept.index, dtype="float64")
    bom_matched = int(bom_inline.notna().sum())

    # % to BOM & Rill % to BOM (semantika stage_05 — di-guard > 0)
    pct_bom = pd.Series(0.0, index=kept.index)
    guard = bom_inline.notna() & (bom_inline > 0) & total.notna()
    pct_bom[guard] = total[guard] / bom_inline[guard]

    # --- Rakit frame output urutan standar 53 kolom ---
    out = pd.DataFrame(index=kept.index)
    out["STATUS"] = None
    out["HELPER"] = None
    out["MAX TOTAL"] = None
    out["AVG TOTAL"] = None
    out["TOTAL BOM"] = bom_inline
    out["% to BOM"] = pct_bom
    out["TOTAL"] = total
    out["AVG"] = avg
    out["MAX"] = mx
    out["SOURCE DATA"] = _strip_series(kept["SOURCE DATA"])
    out["JENIS"] = jenis_norm[keep_mask]
    out["KETERANGAN"] = _strip_series(kept["KETERANGAN"])
    out["NAMA BARANG"] = _strip_series(kept["NAMA BARANG"])
    out["NAMA RESTO"] = _strip_series(kept["NAMA RESTO"])
    out["SATUAN"] = _strip_series(kept["SATUAN"])
    for c in day_cols:
        out[c] = day_filled[c]
    out["Status2"] = status2
    out["KETERANGAN GABUNGAN"] = None
    out["KONTRIBUSI TERBESAR"] = None
    out["SOURCE DATA GABUNGAN"] = None
    out["Count Hari"] = count_hari
    out["RANGKING WASTE"] = None
    out["Rill % to BOM"] = pct_bom.copy()
    out = out.reset_index(drop=True)

    # --- DATABASE_SATUAN: salin bila sumber punya (opsional — tanpa ini
    # HELPER/STATUS dihitung ulang jadi null, pipeline tetap jalan) ---
    satuan_sheet = _find_satuan_sheet(src, cfg)
    satuan_df = None
    if satuan_sheet is not None:
        try:
            satuan_df = _normalize_columns(
                _read_excel_fast(src, sheet_name=satuan_sheet, header=0))
            _log(logger, f"[rekap_import] DATABASE_SATUAN '{satuan_sheet}' "
                         f"disalin ({len(satuan_df)} baris)")
        except Exception as e:  # noqa: BLE001 — best-effort
            _log(logger, f"[rekap_import] WARNING: gagal baca sheet "
                         f"DATABASE_SATUAN '{satuan_sheet}' — dilewati ({e})")
            satuan_df = None

    # --- Tulis workbook (openpyxl write-only — cepat utk ±25rb×53) ---
    label = detect_month_label(src)
    out_file = Path(out_path) if out_path is not None \
        else _default_out_path(src, label)
    if out_file.resolve() == src.resolve():
        raise RekapImportError(
            "Path output sama dengan file sumber — tolak menimpa "
            f"sumber: {out_file}")
    from openpyxl import Workbook

    wb = Workbook(write_only=True)

    ws = wb.create_sheet(_SHEET_DATA)
    ws.append(list(out.columns))
    for row in out.itertuples(index=False, name=None):
        ws.append([_cell(v) for v in row])

    ws_bom = wb.create_sheet(_SHEET_BOM)
    ws_bom.append(["Nomor #", "Nama Barang", "TOTAL BOM"])
    for (r, b), t in sorted(bom_map.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        ws_bom.append([r, b, _cell(t)])

    if satuan_df is not None:
        ws_sat = wb.create_sheet(_SHEET_SATUAN)
        ws_sat.append([str(c) for c in satuan_df.columns])
        for row in satuan_df.itertuples(index=False, name=None):
            ws_sat.append([_cell(v) for v in row])

    wb.save(str(out_file))

    summary = {
        "out_path": str(out_file),
        "source": str(source),
        "sheet": sheet,
        "rows_raw": int(rows_raw),
        "rows_kept": int(len(out)),
        "jenis_counts": {k: int(v) for k, v in jenis_counts.items()},
        "bom_pairs": int(len(bom_map)),
        "bom_matched": bom_matched,
        "resto_count": int(out["NAMA RESTO"].nunique()),
        "item_count": int(out["NAMA BARANG"].nunique()),
        "month_label": label,
        "day_count": len(day_cols),
        "satuan_sheet": satuan_sheet,
    }
    _log(logger, f"[rekap_import] selesai → {out_file} "
                 f"({len(out)} baris, {len(out.columns)} kolom)")
    return summary
