"""
loader.py — pemuat data input dari workbook Excel.

Setara dengan Excel.CurrentWorkbook() + query referensi M code:
  - Source = DATA_WASTE (named range atau sheet)
  - BOM lookup = query "2  22 05" (BOM master)
  - DATABASE_SATUAN (master expected helper per kategori)

Strategi: coba multiple nama sheet / named range. Bila gagal, raise dengan pesan jelas.

Performance: pakai engine=calamine (Rust-based, 7-10x lebih cepat dari openpyxl)
kalau python-calamine ter-install; fallback ke openpyxl (default pandas).
Semua kwargs read (skiprows/nrows/usecols) ditangani engine-agnostic oleh pandas.

Fix log (v2.3.1):
  - C3-a: header numerik dari engine calamine (float 1.0) dinormalisasi ke "1".
  - C3-b: join key numerik (mis. outlet 1049.0) dinormalisasi via _key_str().
  - H6  : find_sheet pakai token utuh + wajib unik (anti salah-sheet).
  - H7  : named ranges dicek PER-PURPOSE (bukan gabungan kandidat semua purpose).
  - H9-a: BOM tanpa kolom outlet → return frame kosong + warning (bukan key "nan").
  - H9-c: load_bom log diagnosable (row count, distinct keys, kolom ketemu/tidak).
  - M9  : cache meta di-key (path, mtime, size) — file swap tidak pakai cache basi.
  - M10 : named-range ref benar-benar dipakai (baca range saja, bukan sheet penuh).
  - L   : list_named_ranges read-only + log kegagalan (return None = gagal baca);
          guard .xls dengan pesan jelas.
"""

from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Pilih engine Excel read: calamine (cepat) → fallback openpyxl (default pandas)
try:
    import python_calamine  # noqa: F401
    _EXCEL_ENGINE = "calamine"
except ImportError:
    _EXCEL_ENGINE = None  # pandas pakai default (openpyxl)

# openpyxl hanya untuk list_sheets/list_named_ranges (metadata, bukan bulk read)
from openpyxl import load_workbook

_log = logging.getLogger(__name__)


def _float15(x: Any) -> Any:
    """Bulatkan satu float ke 15 digit signifikan (semantik penyimpanan Excel).

    Excel menyimpan/menampilkan maksimal 15 digit signifikan. File hasil
    ekspor tool lain bisa mengandung 'FP dust' (mis. 21.299999999999997) yang
    secara visual = 21.3 di Excel tapi TIDAK sama sebagai double — rasio di
    ambang threshold (21.3/7.1 = 3.0) bisa flip tanpa alasan. Normalisasi ini
    membuat nilai pipeline = nilai yang user lihat di Excel.
    """
    try:
        if pd.isna(x):  # NaN / NaT / pd.NA — lewat apa adanya
            return x
        x_f = float(x)
        if math.isinf(x_f):
            return x
        return float(f"{x_f:.15g}")
    except (TypeError, ValueError):
        return x  # bukan float murni — biarkan


def _normalize_float_precision(df: pd.DataFrame) -> pd.DataFrame:
    """Normalisasi semua kolom float ke 15 digit signifikan (in-place safe).

    Fix idempotency F7 (v2.3.2): tanpa ini, run-1 vs run-ulang bisa menghasilkan
    skor anomali BERBEDA untuk data yang sama ( nilai dust 21.299999999999997
    ditulis ulang oleh openpyxl sebagai "21.3" → run kedua baca nilai bersih →
    sinyal S3/S5 flip di boundary ). Terkonfirmasi: 402 → 403 anomali.

    v2.13.7 (perf-audit B): "%.15g" mencetak PERSIS nilai float yang seluruh
    nilainya bilangan bulat < 10^15 (≤ 15 digit signifikan) → normalisasi
    terbukti no-op → kolom DILEWATI tanpa kerja per-sel (.map lama = 771 ms
    per workbook 54k×31 — kolom hari 1-31 didominasi bilangan bulat).
    Kolom ber-desimal tetap dinormalisasi per-sel dengan _float15 —
    semantik identik.
    """
    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_float_dtype(s):
            continue
        arr = s.to_numpy()
        finite = np.isfinite(arr)
        if not finite.any():
            continue  # semua NaN/inf — passthrough (map lama juga)
        vals = arr[finite]
        if (np.all(np.abs(vals) < 1e15)
                and np.all(vals == np.trunc(vals))):
            continue  # bulat ≤ 15 digit → "%.15g" identik → no-op terbukti
        arr[finite] = np.array([_float15(v) for v in vals])
        df[col] = arr
    return df


def _read_excel_fast(path, sheet_name, **kwargs):
    """Wrapper untuk pd.read_excel dengan engine optimal (calamine jika ada).

    F7 (v2.3.2): semua hasil baca dinormalisasi ke 15 digit signifikan supaya
    konsisten antar engine (calamine vs openpyxl) dan idempotent terhadap
    round-trip tulis-ulang Excel.
    """
    if _EXCEL_ENGINE:
        df = pd.read_excel(path, sheet_name=sheet_name, engine=_EXCEL_ENGINE, **kwargs)
    else:
        df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
    return _normalize_float_precision(df)


def _guard_xls(workbook_path: str | os.PathLike) -> None:
    """Tolak file .xls (Excel lama, format BIFF) dengan pesan jelas.

    openpyxl/pandas-calamine hanya mendukung .xlsx/.xlsm/.xlsb; tanpa guard ini
    user dapat error teknis membingungkan dari xlrd/openpyxl.
    """
    if Path(workbook_path).suffix.lower() == ".xls":
        raise ValueError("File .xls (Excel lama) tidak didukung — save as .xlsx dulu")


# ============================================================
# KEY NORMALIZATION (join BOM / DATABASE_SATUAN)
# ============================================================

def _key_str(value: Any) -> str | None:
    """Normalisasi nilai sel jadi string key join.

    Dipakai untuk key BOM ('Nomor #' / 'Nama Barang') dan key DATABASE_SATUAN
    ('NAMA ITEM'). stages.py bisa import helper ini supaya kedua sisi join
    memakai normalisasi identik.

    Aturan:
      - None / NaN / NaT / pd.NA → None (bukan string "nan" — mencegah join
        palsu antara sel kosong; H9-a).
      - float integral (mis. 1049.0 dari cell numerik / engine calamine)
        → "1049" (bukan "1049.0" — dtype trap C3-b).
      - nilai lain → str(value).strip().
    """
    if value is None:
        return None
    try:
        if pd.isna(value):  # NaN / NaT / pd.NA (scalar)
            return None
    except (TypeError, ValueError):
        pass  # non-scalar — biarkan str() yang menangani
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# ============================================================
# DETEKSI NAMA SHEET / NAMED RANGE
# ============================================================

def list_sheets(workbook_path: str | os.PathLike) -> list[str]:
    """List semua sheet di workbook (openpyxl, read-only — cepat).

    Raise ValueError jelas untuk file .xls (Excel lama).
    v2.18.0 audit (F-4): try/finally — bila sheetnames raise, handle
    read-only tetap ditutup (pola list_named_ranges di bawah).
    """
    _guard_xls(workbook_path)
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def list_named_ranges(workbook_path: str | os.PathLike) -> dict[str, str] | None:
    """Return dict {name: "SheetName!A1:Z100"} untuk semua defined name (global).

    Perbaikan (audit L):
      - Pakai read_only=True + data_only=True (dulu non-readonly — lambat untuk
        file besar dan rawan lock file).
      - Kegagalan pembacaan di-LOG (warning), tidak di-raise dan tidak
        ditelan diam-diam. Return None kalau workbook/defined-names tidak bisa
        dibaca supaya caller bisa membedakan:
          {}   → workbook valid, tidak punya named ranges
          None → gagal baca (lihat log untuk penyebabnya)
    """
    _guard_xls(workbook_path)
    try:
        wb = load_workbook(workbook_path, read_only=True, data_only=True)
    except Exception as e:
        _log.warning("list_named_ranges: gagal baca workbook %s: %s", workbook_path, e)
        return None
    try:
        names: dict[str, str] = {}
        defined = wb.defined_names
        try:
            items = list(defined.items())  # openpyxl >= 3.1: {name: DefinedName}
        except AttributeError:  # openpyxl lama: DefinedNameList
            items = [(d.name, d) for d in defined.definedName]
        for name, defn in items:
            value = defn if isinstance(defn, str) else getattr(defn, "value", None)
            if value:  # skip defined name tanpa nilai (mis. pure formula error)
                names[str(name)] = str(value)
        return names
    except Exception as e:
        _log.warning("list_named_ranges: gagal baca defined names %s: %s", workbook_path, e)
        return None
    finally:
        wb.close()


# Kandidat sheet default per purpose (dipakai resolve_sheet_for & _resolve_workbook_meta
# supaya logika kandidat SELALU konsisten di kedua tempat — audit H7).
_DEFAULT_SHEET_CANDIDATES: dict[str, list[str]] = {
    "rekap_mentah": ["REKAP_MENTAH", "Rekap Mentah"],
    "bom": ["BOM", "2  22 05", "MASTER BOM"],
    "database_satuan": ["DATABASE_SATUAN", "Database Satuan"],
}


def _purpose_candidates(purpose: str, config: dict) -> list[str]:
    """Kandidat sheet untuk satu purpose: dari config['input_sheets'], fallback default."""
    candidates = config.get("input_sheets", {}).get(purpose)
    if candidates:
        return list(candidates)
    return list(_DEFAULT_SHEET_CANDIDATES.get(purpose, []))


def _resolve_workbook_meta(workbook_path, config):
    """Cache metadata sheet + named range per workbook.

    Perbaikan audit:
      - M9: cache di-key (path, mtime, size) via os.stat — file yang di-swap
        in-place (nama sama, isi baru) tidak resolve metadata basi.
      - H7: named ranges hanya dibaca kalau ADA purpose yang sheet-lookup-nya
        gagal — dulu semua kandidat dari semua purpose digabung, jadi cukup
        SATU sheet match (mis. rekap) untuk skip named ranges seluruhnya,
        padahal BOM/DATABASE_SATUAN mungkin cuma ada sebagai named range.
        Named-range priority tetap dievaluasi per-purpose oleh resolve_sheet_for.
    """
    if not hasattr(_resolve_workbook_meta, "_cache"):
        _resolve_workbook_meta._cache = {}
    stat = os.stat(workbook_path)  # raise jelas kalau file hilang
    key = (str(workbook_path), stat.st_mtime, stat.st_size)
    cache = _resolve_workbook_meta._cache
    cached = cache.get(key)
    if cached is not None:
        return cached
    # Buang entri basi untuk path yang sama (file swap / re-save)
    for stale in [k for k in cache if k[0] == key[0] and k != key]:
        del cache[stale]

    sheets = list_sheets(workbook_path)
    # H7: per-purpose. Named ranges dibaca hanya kalau ada purpose yang
    # sheet-lookup-nya gagal (untuk workbook tanpa named range, ini no-op
    # karena semua sheet match; kalau ada yang gagal, kita cek named ranges).
    purposes = set(config.get("input_sheets", {}).keys()) | set(_DEFAULT_SHEET_CANDIDATES)
    need_named = any(
        find_sheet(_purpose_candidates(p, config), sheets) is None
        for p in purposes
    )
    if need_named:
        named = list_named_ranges(workbook_path)
        if named is None:
            # Gagal baca named ranges (sudah di-log) — lanjut dengan kosong;
            # resolve_sheet_for akan tetap coba sheet lookup per-purpose.
            named = {}
    else:
        named = {}  # semua purpose match sheet → skip list_named_ranges (cepat)
    cache[key] = {
        "sheets": sheets,
        "named": named,
    }
    return cache[key]


def _sheet_tokens(name: str) -> frozenset[str]:
    """Token nama sheet: lowercase, pecah pada non-alfanumerik.

    Contoh: "DATABASE_SATUAN" → {"database", "satuan"}; "Data Waste 2" → {"data", "waste", "2"}.
    """
    return frozenset(
        t for t in re.split(r"[^0-9a-zA-Z]+", str(name).strip().lower()) if t
    )


def find_sheet(names_candidates: list[str], available: list[str]) -> str | None:
    """Cari sheet yang cocok dari daftar kandidat (case-insensitive).

    Perbaikan audit H6 — dua fase:
      1. EXACT (backward compat, tetap prioritas pertama):
         nama sheet == kandidat (case-insensitive, di-strip).
      2. TOKEN: semua token kandidat (pecah pada non-alfanumerik) harus ada
         sebagai TOKEN UTUH di nama sheet. Contoh: kandidat "DATA" TIDAK match
         "DATABASE_SATUAN" karena token sheet {database, satuan} tidak memuat
         token "data" (dulu substring-match salah tangkap sheet ini).
         Kandidat multi-kata ("Data Waste") match sheet yang memuat semua
         token-nya ("Data Waste 2024").

    Fase token WAJIB unik: kalau satu kandidat match beberapa sheet (ambigu),
    kandidat itu dilewati — tidak menebak sheet pertama. Kalau tidak ada
    kandidat yang menghasilkan match unik, return None biar error-path caller
    yang jalan.
    """
    avail = [str(s) for s in available]
    avail_norm = [s.strip().lower() for s in avail]
    # 1. Exact
    for cand in names_candidates:
        cl = str(cand).strip().lower()
        if cl and cl in avail_norm:
            return avail[avail_norm.index(cl)]
    # 2. Token containment — wajib match unik per kandidat
    sheet_tokens = [_sheet_tokens(s) for s in avail]
    for cand in names_candidates:
        cand_tokens = _sheet_tokens(str(cand))
        if not cand_tokens:
            continue
        matches = [i for i, toks in enumerate(sheet_tokens) if cand_tokens.issubset(toks)]
        if len(matches) == 1:
            return avail[matches[0]]
    return None


def _sheet_from_ref(ref: str) -> str:
    """Ambil nama sheet dari ref named range, mis. "'DATA WASTE'!$A$1:$AZ$99" → DATA WASTE.

    Split pada "!" TERAKHIR (nama sheet bisa memuat "!" bila di-quote Excel).
    """
    sheet = ref.rpartition("!")[0]
    return sheet.strip().strip("'").strip('"').strip()


def resolve_sheet_for(
    purpose: str,
    config: dict,
    available_sheets: list[str],
    named_ranges: dict[str, str],
) -> tuple[str, str | None]:
    """
    Resolve sheet untuk tujuan `purpose` ('rekap_mentah' | 'bom' | 'database_satuan').
    Return: (sheet_name, named_range_ref_or_None).

    Strategi (per-purpose — audit H7):
      1. Cari named range dengan nama kandidat (priority, setara M code
         Excel.CurrentWorkbook(){[Name=...]}).
      2. Cari sheet dengan nama kandidat (find_sheet: exact → token unik).
      3. Raise kalau tidak ketemu.

    Kandidat diambil dari config['input_sheets'][purpose]; fallback ke default
    per purpose (sama dengan _resolve_workbook_meta supaya fast-path cache dan
    resolusi final selalu sepaham).
    """
    candidates = _purpose_candidates(purpose, config)

    # 1. Named range (priority)
    for cand in candidates:
        if cand in named_ranges:
            ref = named_ranges[cand]
            return _sheet_from_ref(ref), ref

    # 2. Sheet by name
    sheet = find_sheet(candidates, available_sheets)
    if sheet is None:
        raise ValueError(
            f"Tidak menemukan sheet untuk '{purpose}'. "
            f"Sheet tersedia: {available_sheets}. "
            f"Kandidat yang dicari: {candidates}."
        )
    return sheet, None


# ============================================================
# PARSER NAMED RANGE (audit M10)
# ============================================================

_CELL_REF_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


def _col_letter_to_idx(letters: str) -> int:
    """'A' → 1, 'Z' → 26, 'AA' → 27, 'AZ' → 52 (1-based). Raise ValueError kalau bukan huruf."""
    n = 0
    for ch in letters.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"Kolom tidak valid: {letters!r}")
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _col_idx_to_letter(idx: int) -> str:
    """1 → 'A', 26 → 'Z', 27 → 'AA', 52 → 'AZ'."""
    letters = ""
    while idx > 0:
        idx, r = divmod(idx - 1, 26)
        letters = chr(ord("A") + r) + letters
    return letters


def _parse_named_range_ref(ref: str) -> tuple[str, int, int, int, int] | None:
    """Parse ref named range → (sheet, row_start, row_end, col_start, col_end).

    Semua row/col 1-based inclusive. Format yang didukung:
      - "'Sheet Name'!$A$1:$AZ$26000" (openpyxl defined-name style)
      - "SheetName!A1:AZ26000" (dxf style)
    Return None kalau format tidak dikenali — caller fallback ke whole-sheet
    dengan warning (jangan crash).
    """
    if not ref or "!" not in ref:
        return None
    sheet = _sheet_from_ref(ref)
    range_part = ref.rpartition("!")[2].replace("$", "").strip()
    if not range_part or ":" not in range_part:
        return None
    start_s, end_s = (p.strip() for p in range_part.split(":", 1))
    m_start = _CELL_REF_RE.match(start_s)
    m_end = _CELL_REF_RE.match(end_s)
    if not m_start or not m_end:
        return None
    try:
        col_start = _col_letter_to_idx(m_start.group(1))
        row_start = int(m_start.group(2))
        col_end = _col_letter_to_idx(m_end.group(1))
        row_end = int(m_end.group(2))
    except ValueError:
        return None
    if col_end < col_start or row_end < row_start:
        return None
    # Batas wajar worksheet Excel (16384 kolom x 1048576 baris)
    if not (1 <= col_start <= col_end <= 16384) or not (1 <= row_start <= row_end <= 1048576):
        return None
    return sheet, row_start, row_end, col_start, col_end


# ============================================================
# LOAD 1: DATA_WASTE (input utama)
# ============================================================

def load_rekap_mentah(
    workbook_path: str | os.PathLike,
    config: dict,
    logger=None,
) -> pd.DataFrame:
    """Load DATA_WASTE (input utama pipeline). Setara Source = Excel.CurrentWorkbook(){[Name="DATA_WASTE"]}[Content].

    Perbaikan audit M10: kalau source ter-resolve via NAMED RANGE, hanya range
    itu yang dibaca (skiprows/usecols/nrows) — dulu ref hanya di-log lalu sheet
    penuh dibaca (baris/kolom di luar range ikut terbaca). Baris PERTAMA range
    dianggap header (header=0 relatif terhadap range — sama seperti semantik
    named range di M code). Kalau ref gagal diparse / gagal dibaca, fallback ke
    whole-sheet dengan warning log.
    """
    _guard_xls(workbook_path)
    meta = _resolve_workbook_meta(workbook_path, config)
    sheets = meta["sheets"]
    named = meta["named"]
    sheet, ref = resolve_sheet_for("rekap_mentah", config, sheets, named)

    range_info = _parse_named_range_ref(ref) if ref else None
    if ref and range_info is not None:
        _rng_sheet, row_start, row_end, col_start, col_end = range_info
        usecols = f"{_col_idx_to_letter(col_start)}:{_col_idx_to_letter(col_end)}"
        if logger:
            logger(
                f"[loader] DATA_WASTE: sheet='{sheet}', named_range={ref!r} "
                f"→ baca range {usecols} baris {row_start}..{row_end} saja"
            )
        try:
            df = _read_excel_fast(
                workbook_path,
                sheet_name=sheet,
                header=0,
                skiprows=row_start - 1,        # baris sebelum range (header = baris 1 range)
                nrows=row_end - row_start,     # jumlah baris DATA di dalam range
                usecols=usecols,
            )
        except Exception as e:
            if logger:
                logger(
                    f"[loader] WARNING: gagal baca range {ref!r} ({type(e).__name__}: {e}) "
                    f"— fallback baca sheet '{sheet}' penuh"
                )
            df = _read_excel_fast(workbook_path, sheet_name=sheet, header=0)
        else:
            # v2.18.0 audit (H-1/BUG 4): named range mulai baris R → df
            # row i = baris FISIK Excel R+1+i. ensure_rekap_header
            # mengasumsikan offset 2 (header baris 1) → __SRC_ROW salah
            # sebesar (R-1) → edit pop-up menulis koreksi ke baris Excel
            # yang SALAH (file sumber korup senyap). Pasang mapping BENAR
            # di sini — idempoten: _attach_src_row tak menimpa kolom
            # numerik utuh, promote jalur mempertahankan nilai baris.
            try:
                from .rekap_import import SRC_ROW_COL  # lazy: rekap_import → loader
            except ImportError:  # pragma: no cover — struktur paket stabil
                SRC_ROW_COL = "__SRC_ROW"
            if SRC_ROW_COL not in df.columns:
                df[SRC_ROW_COL] = range(row_start + 1,
                                        row_start + 1 + len(df))
    else:
        if ref and logger:
            logger(
                f"[loader] WARNING: named range {ref!r} tidak bisa diparse "
                f"— baca sheet '{sheet}' penuh"
            )
        if logger and not ref:
            logger(f"[loader] DATA_WASTE: sheet='{sheet}', named_range=None")
        df = _read_excel_fast(workbook_path, sheet_name=sheet, header=0)

    df = _normalize_columns(df)
    if logger:
        engine_info = f"engine={_EXCEL_ENGINE or 'default'}"
        logger(f"[loader] DATA_WASTE loaded: {len(df)} rows, {len(df.columns)} cols ({engine_info})")
    return df


# ============================================================
# LOAD 2: BOM (query "2  22 05")
# ============================================================

_EMPTY_BOM_COLUMNS = ["Nomor #", "Nama Barang", "TOTAL BOM"]


def load_bom(
    workbook_path: str | os.PathLike,
    config: dict,
    logger=None,
) -> pd.DataFrame:
    """
    Load BOM lookup. Setara BOMLookup di M code (Table.Distinct dari query "2  22 05").
    Kolom yang diharapkan: outlet (Nomor #), item (Nama Barang), total_bom (TOTAL BOM).

    Perbaikan audit:
      - H9-a: sheet BOM ada tapi kolom outlet TIDAK ada → return frame KOSONG
        + warning jelas. (Dulu: key outlet jadi string "nan" untuk semua baris
        → join gagal diam-diam padahal log bilang "BOM loaded".)
      - H9-c: log diagnosable — jumlah baris sumber, distinct (outlet, item),
        distinct keys, dan kolom mana saja yang ketemu.
      - C3-b: key join dinormalisasi via _key_str (outlet numerik 1049.0 →
        "1049", sel kosong → None, bukan "nan").
    """
    _guard_xls(workbook_path)
    meta = _resolve_workbook_meta(workbook_path, config)
    sheets = meta["sheets"]
    named = meta["named"]
    try:
        sheet, ref = resolve_sheet_for("bom", config, sheets, named)
    except ValueError:
        if logger:
            logger("[loader] BOM sheet tidak ditemukan — BOM join dilewati (TOTAL BOM = None)")
        return pd.DataFrame(columns=_EMPTY_BOM_COLUMNS)

    if logger:
        logger(f"[loader] BOM: sheet='{sheet}', named_range={ref!r}")

    df = _read_excel_fast(workbook_path, sheet_name=sheet, header=0)
    df = _normalize_columns(df)

    # Resolve nama kolom sesuai konfigurasi (kemungkinan beberapa alias)
    bom_cfg = config.get("bom_columns", {})
    outlet_col = _find_column(df.columns, bom_cfg.get("outlet", ["Nomor #"]))
    item_col = _find_column(df.columns, bom_cfg.get("item", ["Nama Barang"]))
    total_col = _find_column(df.columns, bom_cfg.get("total_bom", ["TOTAL BOM"]))

    # H9-a: kolom outlet wajib — tanpa itu join (NAMA RESTO == Nomor #) mustahil.
    if outlet_col is None:
        if logger:
            logger(
                "[loader] WARNING: BOM sheet ditemukan tapi kolom outlet "
                "('Nomor #'/'NAMA RESTO') tidak ada — BOM join dilewati"
            )
        return pd.DataFrame(columns=_EMPTY_BOM_COLUMNS)
    if item_col is None or total_col is None:
        if logger:
            logger(
                f"[loader] WARNING: BOM sheet ditemukan tapi kolom item/total hilang "
                f"(outlet={outlet_col!r}, item={item_col!r}, total={total_col!r}) "
                f"— BOM join dilewati"
            )
        return pd.DataFrame(columns=_EMPTY_BOM_COLUMNS)

    # Normalisasi nama ke kanvas yang seragam — key via _key_str (C3-b):
    # outlet numerik 1049.0 → "1049"; sel kosong → None (bukan "nan").
    out = pd.DataFrame()
    out["Nomor #"] = df[outlet_col].map(_key_str)
    out["Nama Barang"] = df[item_col].map(_key_str)
    out["TOTAL BOM"] = pd.to_numeric(df[total_col], errors="coerce")

    # Distinct by (Nomor #, Nama Barang) — setara Table.Distinct di M
    out = out.drop_duplicates(subset=["Nomor #", "Nama Barang"], keep="first")
    if logger:
        # H9-c: log diagnosable supaya kegagalan join bisa dibedakan dari
        # "BOM memang kosong" / "kolom TOTAL BOM inline all-null di DATA_WASTE"
        # (prioritas stage_05 pakai kolom inline → BOM sheet tak pernah dicek).
        logger(
            f"[loader] BOM loaded: {len(out)} distinct (outlet, item) dari {len(df)} baris "
            f"sheet '{sheet}' (outlet_col={outlet_col!r}, item_col={item_col!r}, "
            f"total_col={total_col!r}, distinct outlet={out['Nomor #'].nunique()}, "
            f"distinct item={out['Nama Barang'].nunique()}, "
            f"total_bom non-null={int(out['TOTAL BOM'].notna().sum())})"
        )
    return out


# ============================================================
# LOAD 3: DATABASE_SATUAN
# ============================================================

def load_database_satuan(
    workbook_path: str | os.PathLike,
    config: dict,
    logger=None,
) -> pd.DataFrame:
    """
    Load DATABASE_SATUAN. Setara SatuanLookup di M code.
    Mapping NAMA ITEM -> expected helper value per kategori.

    Key 'NAMA ITEM' dinormalisasi via _key_str (C3-b) supaya konsisten dengan
    normalisasi key BOM dan tidak menghasilkan string "nan" untuk sel kosong.
    """
    _guard_xls(workbook_path)
    meta = _resolve_workbook_meta(workbook_path, config)
    sheets = meta["sheets"]
    named = meta["named"]
    try:
        sheet, ref = resolve_sheet_for("database_satuan", config, sheets, named)
    except ValueError:
        if logger:
            # Pesan akurat (audit L, loader.py:268 lama menulis "STATUS jadi 'Cek'"
            # padahal bukan itu yang terjadi): tanpa DATABASE_SATUAN, kolom kategori
            # (SUSUT/TRIAL/HANDLING/...) tidak tersedia → stage_10 menghitung HELPER
            # & STATUS ulang jadi null (stage_01 memang drop HELPER/STATUS dari input);
            # '% to BOM' tetap dihitung stage_10 dari TOTAL/TOTAL BOM ("Cek" bila null).
            logger(
                "[loader] DATABASE_SATUAN sheet tidak ditemukan — kolom kategori tidak "
                "tersedia: HELPER/STATUS dihitung ulang stage_10 jadi null (input HELPER/"
                "STATUS di-drop stage_01), '% to BOM' tetap dihitung dari TOTAL BOM"
            )
        return pd.DataFrame(columns=["NAMA ITEM"])

    if logger:
        logger(f"[loader] DATABASE_SATUAN: sheet='{sheet}', named_range={ref!r}")

    df = _read_excel_fast(workbook_path, sheet_name=sheet, header=0)
    df = _normalize_columns(df)

    # Resolve kolom item
    satuan_cfg = config.get("satuan_columns", {})
    item_col = _find_column(df.columns, satuan_cfg.get("item_key", ["NAMA ITEM"]))
    if not item_col:
        if logger:
            logger("[loader] WARNING: DATABASE_SATUAN tidak punya kolom NAMA ITEM")
        return pd.DataFrame(columns=["NAMA ITEM"])
    out = df.rename(columns={item_col: "NAMA ITEM"})
    # Strip key via _key_str (konsisten dengan join stage_09 dan key BOM)
    out["NAMA ITEM"] = out["NAMA ITEM"].map(_key_str)
    # Distinct by NAMA ITEM (setara Table.Distinct)
    out = out.drop_duplicates(subset=["NAMA ITEM"], keep="first")
    if logger:
        logger(f"[loader] DATABASE_SATUAN loaded: {len(out)} distinct items")
    return out


# ============================================================
# HELPER INTERNAL
# ============================================================

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalisasi nama kolom: strip whitespace, hilangkan BOM char.

    Perbaikan C3-a: header numerik bisa datang sebagai float (engine calamine
    menyerapkan cell numerik jadi float, mis. 1.0..31.0). str(1.0) = "1.0" →
    stage_01 tidak menemukan kolom hari "1".."31" → crash/wrong output.
    Maka float integral di-cast ke int DULU baru ke str: 1.0 → "1".
    (openpyxl memberi header numerik sebagai int/str — juga aman di sini.)
    """
    new_cols = []
    for c in df.columns:
        if isinstance(c, str):
            s = c.replace("\ufeff", "").strip()
            new_cols.append(s)
        else:
            if isinstance(c, float) and math.isfinite(c) and c.is_integer():
                c = int(c)
            new_cols.append(str(c))
    df.columns = new_cols
    return df


def _find_column(available: list[str], candidates: list[str]) -> str | None:
    """Cari kolom yang cocok dari daftar kandidat (exact case-insensitive dulu, lalu contains)."""
    avail_lower = [str(c).lower().strip() for c in available]
    for cand in candidates:
        cl = cand.lower().strip()
        if cl in avail_lower:
            return available[avail_lower.index(cl)]
    # Contains
    for cand in candidates:
        cl = cand.lower().strip()
        for i, s in enumerate(avail_lower):
            if cl and cl in s:
                return available[i]
    return None
