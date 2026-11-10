"""
rekap_import.py — Olah data REKAP MENTAH mentah (in-memory) & ekspor
workbook DATA_WASTE standar.

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

v2.15.0 — SEKALI JALAN (tanpa file antara):
Pipeline kini memanggil dua helper modul ini LANGSUNG pada file mentah,
jadi tombol 🧮 UI cukup SEKALI PROSES (pilih file → pipeline langsung —
tanpa ekspor file olahan antara, tanpa klik Mulai Pipeline kedua kali):
  - ensure_rekap_header()  : perbaiki header tergeser pada frame hasil
    loader (baris judul di atas header — pola fn_rekap_mentah
    stock-monitoring); no-op untuk sheet ber-header normal.
  - inject_bom_from_raw_rows() : tambah kolom inline "TOTAL BOM" dari
    baris JENIS=="BOM" yang ada di sheet mentah (sebelum stage_01
    memfilternya) — prioritas stage_05, sinyal S6/S7 & Rill % to BOM
    hidup. No-op bila kolom TOTAL BOM sudah ada (idempotent) atau tidak
    ada baris BOM (file standar / pure W-S-T).
convert_rekap_mentah() TETAP tersedia sebagai API berdiri-sendiri
(menghasilkan file olahan untuk dipakai manual / diarsip) — UI tidak
 lagi memakainya di jalur utamanya.

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
    _EXCEL_ENGINE,
    _guard_xls,
    _key_str,
    _normalize_columns,
    _read_excel_fast,
    _sheet_tokens,
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

# v2.16.0 — fitur "edit dari pop-up": kolom tersembunyi di df yang menyimpan
# NOMOR BARIS FISIK sheet sumber (1-based; baris 1 = header, data mulai
# baris 2). Dipasang di ensure_rekap_header() (injection point tunggal —
# row-accounting terjadi di sana). Disurvive pipeline stages (kolom biasa,
# tidak di-drop). Tidak ditampilkan (bukan anggota TABLE_COLS/DETAIL_COLS).
# Dipakai waste_anomaly.source_writer.write_day_edits() untuk menulis
# koreksi nilai hari ke baris yang BENAR di file Excel sumber.
SRC_ROW_COL = "__SRC_ROW"

# Kolom header yang dikenali & dikanonikalkan ke UPPERCASE kanonik di
# convert_rekap_mentah (audit v2.18.0 BUG 3 — validasi kolom wajib
# case-insensitive, tapi akses kolom berikutnya exact-case; file
# ber-header "Jenis"/"Nama Resto" lolos validasi lalu crash KeyError).
_CANON_HEADER_COLS = {
    "NAMA RESTO", "JENIS", "NAMA BARANG", "SATUAN", "KETERANGAN",
    "SOURCE DATA", "PIC", "TOTAL",
}

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
    rekap user kadang ber-baris judul di atas header.)

    v2.15.0: nilai header float-integral (1.0 — engine calamine menyerap
    sel numerik jadi float, pola C3-a _normalize_columns) dihitung sebagai
    hari "1".."31" — dulu str(1.0)="1.0" tak pernah match _DAY_SET
    sehingga baris header sah DITOLAK deteksi."""
    if peek is None or peek.empty:
        return None
    for hr in range(min(6, len(peek))):
        headers = [_hdr_norm(h) for h in peek.iloc[hr].tolist()]
        if any(rc not in headers for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG")):
            continue
        n_days = sum(1 for h in headers
                     if h not in ("", "NONE", "NAN") and h in _DAY_SET)
        if n_days >= 3:
            return hr
    return None


def _hdr_norm(h: Any) -> str:
    """Normalisasi SATU nilai header: None/NaN → ""; float integral
    (1.0) → "1"; selain itu str().strip().upper(). (Pola C3-a
    _normalize_columns — dipakai _detect_header_row & _promote_at supaya
    header hari numerik dikenali di engine calamine maupun openpyxl.)"""
    if h is None:
        return ""
    if isinstance(h, float):
        if math.isnan(h):
            return ""
        if math.isfinite(h) and h.is_integer():
            h = int(h)
    return str(h).strip().upper()


def _promote_at(df: pd.DataFrame, hr: int) -> pd.DataFrame:
    """Baris hr jadi header (duplikat diberi suffix _1/_2 — mirror
    _promote_at fn_rekap_mentah; header None → ColumnN).

    v2.15.0: nilai header float-integral (1.0 — engine calamine)
    dinormalisasi ke "1" (pola C3-a _normalize_columns) — dulu
    str(1.0)="1.0" membuat kolom hari tak ditemukan stage berikutnya."""
    headers = df.iloc[hr].tolist()
    body = df.iloc[hr + 1:].reset_index(drop=True)
    new_cols: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(headers):
        if h is None or (isinstance(h, float) and math.isnan(h)):
            h = f"Column{i + 1}"
        elif isinstance(h, float) and math.isfinite(h) and h.is_integer():
            h = int(h)  # 1.0 → 1 → "1" (bukan "1.0")
        h = str(h)
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        new_cols.append(h)
    body.columns = new_cols
    return body


# ============================================================
# v2.18.2 — SHEET SELECTION BERBASIS SKOR (audit data user: "Proses
# dari Folder" → 5 dari 20 file salah baca sheet → Banding Periode
# salah semua).
#
# BUKTI dari file user (HASIL OLAH REKAP MENTAH PROGRAM.xlsx vs
# REKAP MENTAH_RILL YANG SEHARUSNYA.xlsx, folder DEVIASI WEEKLY):
#   ✓ 15 file benar  — sheet REKAP MENTAH riil (2.971 baris/resto,
#     JENIS WASTE/SO/BOM/…; nilai identik dgn rekap riil).
#   ✗ 5 file SALAH (BDGSEK, MLGPAR, KGNSUD, BKSALT, BKSSUD) — yang
#     terbaca sheet SEKSI DEVIASI: kolom NAMA BARANG/KATEGORI/JENIS/
#     SATUAN/hari/Grand Total TANPA SOURCE DATA, JENIS bernomor seksi
#     ('1.DEVIASI'…'8.BARANG KELUAR'), baris kosong interleaved.
#     KGNSUD seharusnya 2.971 baris → terbaca 135 baris seksi
#     '5.LOSS SURPLUS' saja; BDGSEK 1.246 → 211 ('1.DEVIASI').
#
# AKAR MASALAH: bila fase kandidat-nama gagal (sheet rekap riil tidak
# bernama kandidat / header tergeser di bawah baris judul), fallback
# lama mengambil sheet PERTAMA yang cocok schema lenient — sheet seksi
# DEVIASI cocok schema itu dan muncul lebih duluan di workbook.
#
# FIX — nilai SEMUA sheet dgn SKOR BUKTI "rekap riil" lalu ambil
# TERBAIK (bukan pertama):
#   + nama sheet bertoken rekap+mentah (+6) / salah satunya (+3)
#   + kolom SOURCE DATA (+5 — SEMUA format rekap riil user punya;
#     sheet seksi DEVIASI tidak pernah)
#   + kolom NAMA RESTO (+2), PIC (+1), KETERANGAN (+1), STATUS (+1)
#   + fraksi nilai JENIS sampel yang kanonik rekap (WASTE/SO/BOM/…,
#     prefix angka distrip dulu — '2.WASTE' dihitung WASTE) × 4
#   − fraksi baris kosong pada sampel × 2 (ciri sheet seksi)
# Fast-path: sheet kandidat bernama dgn skor ≥ _SCORE_HIGH langsung
# dipakai — file normal (nama + schema sepakat) tak berubah perilaku
# & kecepatan. Skor < _SCORE_MIN = meragukan → WARNING + flag
# low_confidence (best-effort, anti silent-error).
# ============================================================

# Nilai JENIS kanonik sheet rekap riil (terukur dari file user asli:
# TEGAR multi-resto + BJMHAS per-file + varian B.10xx).
_REKAP_JENIS_VALUES = frozenset({
    "WASTE", "SUSUT", "TRIAL", "SO", "SO RIIL STORE", "BOM",
    "BARANG MASUK", "BARANG KELUAR", "STOK AWAL", "STOCK AWAL",
    "RETUR", "REWORK",
})

_SCORE_HIGH = 9.0    # ≥ ini = yakin rekap riil → fast-path (tanpa scan)
_SCORE_MIN = 4.0     # < ini = meragukan → WARNING + flag low_confidence
_PEEK_ROWS = 48      # baris peek per sheet (header ≤6 + sampel JENIS)


def _jenis_canonical(v: Any) -> str:
    """Normalisasi SATU nilai JENIS: strip + upper + buang prefix angka
    ('2.WASTE' → 'WASTE' — mirror normalize_rekap_values v2.17.5).
    None/NaN → '' (baris kosong interleaved tidak dihitung kanonik)."""
    if v is None:
        return ""
    s = str(v).strip().upper()
    if not s or s == "NAN":
        return ""
    return re.sub(r"^\d+\.\s*", "", s)


def _score_rekap_evidence(sheet_name: str, cols_upper: set,
                          jenis_sample: list, n_blank: int = 0) -> float:
    """Skor "seberapa mirip sheet ini rekap mentah RIIL" (makin tinggi
    makin yakin). Bobot: lihat komentar blok v2.18.2 di atas."""
    score = 0.0
    toks = _sheet_tokens(sheet_name)
    if {"rekap", "mentah"} <= toks:
        score += 6.0
    elif toks & {"rekap", "mentah"}:
        score += 3.0
    if "SOURCE DATA" in cols_upper:
        score += 5.0
    if "NAMA RESTO" in cols_upper:
        score += 2.0
    if "PIC" in cols_upper:
        score += 1.0
    if "KETERANGAN" in cols_upper:
        score += 1.0
    if "STATUS" in cols_upper:
        score += 1.0
    vals = [j for j in jenis_sample if j]
    if vals:
        frac = sum(1 for j in vals if j in _REKAP_JENIS_VALUES) / len(vals)
        score += 4.0 * frac
    if jenis_sample:
        score -= 2.0 * (n_blank / len(jenis_sample))
    return score


def _peek_rekap(path, sheet_name: str,
                require_resto: bool) -> tuple[int | None, float]:
    """Peek 1 sheet: deteksi baris header (≤6) + skor bukti rekap.

    Return (header_row, skor) — (None, 0.0) bila tak ada header schema.
    require_resto=True → schema STRICT (NAMA RESTO wajib — jalur file
    tunggal TEGAR); False → LENIENT (jalur folder BJMHAS).
    """
    try:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None,
                            nrows=_PEEK_ROWS, dtype=object)
    except Exception:
        return None, 0.0
    if raw is None or raw.empty:
        return None, 0.0
    if require_resto:
        hr = _detect_header_row(raw)
    else:
        hr = _detect_header_row_lenient(raw)
    if hr is None:
        return None, 0.0
    headers = [_hdr_norm(h) for h in raw.iloc[hr].tolist()]
    cols = {h for h in headers if h not in ("", "NONE", "NAN")}
    # Sampel nilai JENIS (baris setelah header dalam peek) + hitung
    # baris kosong interleaved (ciri sheet seksi DEVIASI).
    jidx = headers.index("JENIS") if "JENIS" in headers else None
    jenis_sample: list = []
    n_blank = 0
    if jidx is not None:
        for row in raw.iloc[hr + 1:].itertuples(index=False, name=None):
            jenis_sample.append(_jenis_canonical(row[jidx]))
            if not any(v is not None and str(v).strip() != "" for v in row):
                n_blank += 1
    score = _score_rekap_evidence(sheet_name, cols, jenis_sample, n_blank)
    return hr, score


def _scan_best_rekap_sheet(path, config: dict | None, require_resto: bool,
                           logger=None) -> tuple[str, int, float]:
    """Resolve sheet rekap TERBAIK berbasis skor (v2.18.2).

    1. FAST-PATH: sheet kandidat config (loader.find_sheet) di-peek —
       header terdeteksi (boleh tergeser ≤6 baris, PERBAIKAN vs lama
       yang wajib baris-0) & skor ≥ _SCORE_HIGH → langsung dipakai
       (file normal: nama + schema sepakat — nol biaya scan).
    2. FULL-SCAN: peek SEMUA sheet → skor → ambil TERTINGGI (seri:
       kandidat bernama didahulukan via seed, lalu urutan workbook).
    Raise RekapImportError bila tak ada sheet rekap sama sekali.
    Return (nama_sheet, header_row, skor).
    """
    path = Path(path)
    sheets = list_sheets(path)
    if not sheets:
        raise RekapImportError(
            f"Workbook tidak punya sheet yang bisa dibaca: {path.name}")
    if config is None:
        config = load_config()
    candidates = list(config.get("input_sheets", {}).get("rekap_mentah", []))
    # Tambahan eksplisit "REKAP MENTAH" (nama sheet file user asli —
    # kandidat config memakai varian underscore/case lain).
    for extra in ("REKAP MENTAH", "rekap mentah"):
        if extra not in candidates:
            candidates.append(extra)
    named = find_sheet(candidates, sheets)

    best_name: str | None = None
    best_hr: int | None = None
    best_score = 0.0

    # 1. Fast-path — kandidat bernama dgn bukti kuat
    if named is not None:
        try:
            hr, score = _peek_rekap(path, named, require_resto)
        except Exception as exc:  # anti diam — log lalu lanjut scan
            _log(logger, f"[rekap_scan] WARNING: sheet kandidat {named!r} "
                         f"gagal di-peek: {exc}")
            hr, score = None, 0.0
        if hr is not None and score >= _SCORE_HIGH:
            _log(logger, f"[rekap_scan] {path.name}: sheet '{named}' "
                         f"(kandidat, header baris {hr + 1}, skor "
                         f"{score:.1f})")
            return named, hr, score
        if hr is not None:  # seed scan — jangan peek ulang sheet ini
            best_name, best_hr, best_score = named, hr, score

    # 2. Full-scan — nilai semua sheet, ambil terbaik
    for sn in sheets:
        if sn == named:
            continue  # sudah di-peek di atas (seed)
        try:
            hr, score = _peek_rekap(path, sn, require_resto)
        except Exception as exc:
            _log(logger, f"[rekap_scan] WARNING: sheet {sn!r} gagal "
                         f"di-peek: {exc}")
            continue
        if hr is None:
            continue
        if best_name is None or score > best_score:
            best_name, best_hr, best_score = sn, hr, score

    if best_name is None or best_hr is None:
        if require_resto:
            raise RekapImportError(
                f"Sheet REKAP MENTAH tidak ditemukan di {path.name}. Cari "
                f"sheet ber-kolom NAMA RESTO + JENIS + NAMA BARANG + kolom "
                f"hari 1-31 (sheet tersedia: {', '.join(sheets[:8])}"
                f"{'…' if len(sheets) > 8 else ''}).")
        raise RekapImportError(
            f"Sheet REKAP MENTAH (lenient) tidak ditemukan di {path.name}. "
            f"Cari sheet ber-kolom JENIS + NAMA BARANG + hari 1-31.")

    via = "kandidat" if best_name == named else "scan skor"
    _log(logger, f"[rekap_scan] {path.name}: sheet '{best_name}' ({via}, "
                 f"header baris {best_hr + 1}, skor {best_score:.1f})")
    if best_score < _SCORE_MIN:
        _log(logger, f"[rekap_scan] WARNING: {path.name} — sheet "
                     f"'{best_name}' skor rendah ({best_score:.1f} < "
                     f"{_SCORE_MIN}): tanpa kolom SOURCE DATA / JENIS tak "
                     f"kanonik — kemungkinan BUKAN sheet rekap mentah "
                     f"penuh. Periksa isi file.")
    return best_name, best_hr, best_score


def find_rekap_sheet(path: Path, config: dict,
                     logger=None) -> tuple[str, int]:
    """Resolve sheet rekap STRICT + baris header (0 = baris pertama).

    v2.18.2: delegasi ke _scan_best_rekap_sheet (seleksi berbasis
    skor — lihat blok komentar v2.18.2). Schema strict = NAMA RESTO
    + JENIS + NAMA BARANG + ≥3 hari; kandidat bernama kini juga lolos
    bila header TERGESER (baris judul di atas — dulu wajib baris-0,
    gagal → fallback ambil sheet pertama yang cocok). Kontrak return
    TETAP (nama_sheet, header_row)."""
    sn, hr, _score = _scan_best_rekap_sheet(
        path, config, require_resto=True, logger=logger)
    return sn, hr


# ============================================================
# v2.17.2 — FOLDER FLOW: proses file BJMHAS-style dari folder
# (permintaan user: "proses file langsung dari folder DEVIASI WEEKLY").
# File BJMHAS = sheet REKAP MENTAH TANPA kolom NAMA RESTO (resto identity
# = nama file). Deteksi lenient + sintesis NAMA RESTO dari filename.
# ============================================================

def _detect_header_row_lenient(peek: pd.DataFrame) -> int | None:
    """Cari baris header rekap — VARIAN LENIENT (TANPA NAMA RESTO wajib).

    File format BJMHAS (folder DEVIASI WEEKLY): sheet REKAP MENTAH punya
    JENIS + NAMA BARANG + hari 1-31 TAPI tanpa kolom NAMA RESTO (resto
    identity = nama file). Schema lenient: JENIS + NAMA BARANG + ≥3 hari.
    NAMA RESTO disintesis dari nama file di load_rekap_folder.
    """
    if peek is None or peek.empty:
        return None
    for hr in range(min(6, len(peek))):
        headers = [_hdr_norm(h) for h in peek.iloc[hr].tolist()]
        if any(rc not in headers for rc in ("JENIS", "NAMA BARANG")):
            continue
        n_days = sum(1 for h in headers
                     if h not in ("", "NONE", "NAN") and h in _DAY_SET)
        if n_days >= 3:
            return hr
    return None


def find_rekap_sheet_lenient(path, config: dict | None = None,
                             logger=None) -> tuple[str, int]:
    """Resolve sheet rekap + header row — VARIAN LENIENT (TANPA NAMA RESTO).

    v2.18.2: delegasi ke _scan_best_rekap_sheet (seleksi berbasis
    skor — lihat blok komentar v2.18.2). Schema lenient = JENIS +
    NAMA BARANG + ≥3 hari (file BJMHAS tidak punya NAMA RESTO — resto
    dari filename). FIX bug user: fallback lama ambil sheet PERTAMA
    yang cocok schema — sheet seksi DEVIASI (JENIS '1.DEVIASI'…
    '8.BARANG KELUAR', tanpa SOURCE DATA) yang kebetulan muncul lebih
    duluan terpilih → 5/20 file salah data. Kini SEMUA sheet
    dinilai skornya; rekap riil menang.
    Dipakai load_rekap_folder. Return (nama_sheet, header_row).
    Raise RekapImportError bila tak ada sheet rekap.
    """
    sn, hr, _score = _scan_best_rekap_sheet(
        path, config, require_resto=False, logger=logger)
    return sn, hr


def _fill_total_column(df: pd.DataFrame) -> int:
    """v2.18.3: isi sel TOTAL kosong dengan jumlah kolom hari (in-place).

    Latar — bug user "kolom total pada file hasil program (proses dari
    folder) kok blank?": TOTAL di file gabungan selama ini PASSTHROUGH
    mentah sheet sumber. Terukur di file bukti (HASIL OLAH REKAP MENTAH
    PROGRAM.xlsx, 48.202 baris): (a) 22 sel TOTAL kosong di file sumber
    sendiri (baris STOK AWAL/BARANG MASUK — sel TOTAL memang tak diisi
    orang), (b) sheet tanpa kolom TOTAL → kolom union concat = NaN utk
    seluruh baris file itu. Semantik pengisian = jumlah kolom hari
    '1'..'31' yang ada (identik "TOTAL KESELURUHAN" Power Query user &
    stage_02): sel hari kosong dihitung 0 (skipna), baris TANPA satu
    pun nilai hari → TOTAL tetap kosong (min_count=1 — jujur, tanpa
    fabrikasi 0). TOTAL non-kosong dipertahankan (terukur: sumber
    akurat — 0 selisih vs jumlah hari pada 2.000 baris sampel).

    Return banyak sel yang diisi. Mutasi in-place (frame gabungan
    internal load_rekap_folder — bukan API publik).
    """
    day_cols = [c for c in df.columns if c in _DAY_SET]
    if not day_cols:
        return 0
    day_sum = df[day_cols].apply(pd.to_numeric, errors="coerce").sum(
        axis=1, min_count=1)
    if "TOTAL" in df.columns:
        tot = pd.to_numeric(df["TOTAL"], errors="coerce")
        blank = tot.isna()
        n = int(blank.sum())
        if n:
            df["TOTAL"] = tot.where(~blank, day_sum)
        return n
    # Tak ada file pun yang punya kolom TOTAL → tambah di akhir (union
    # concat menempatkan kolom ekstra di belakang — konsisten).
    df["TOTAL"] = day_sum
    return int(len(df))


def load_rekap_folder(folder_path, config: dict | None = None,
                      logger=None, cancel_check=None) -> dict:
    """Scan folder file .xlsx → baca sheet REKAP MENTAH tiap file →
    SINTESIS NAMA RESTO dari nama file (bila kolom absen) → GABUNG semua
    → tulis temp .xlsx (sheet "REKAP MENTAH") → return summary.

    Untuk file format BJMHAS (folder DEVIASI WEEKLY): tiap file = 1 resto,
    NAMA RESTO diambil dari stem filename (BJMHAS.xlsx → "BJMHAS"). File
    dgn kolom NAMA RESTO sendiri (format TEGAR) tetap dipakai apa adanya.

    ANTI SILENT-ERROR:
      - File tanpa sheet REKAP MENTAH → dicatat di "skipped" (bukan diam).
      - NAMA RESTO disintesis → dicatat di "synthesized" (transparan).
      - Temp file path dikembalikan — EDIT nilai via pop-up akan menyimpan
        ke temp file INI, BUKAN file asli di folder (file asli utuh). Untuk
        edit file asli, gunakan "Pilih File Sendiri" (format TEGAR).

    Return: {"temp_path": str, "files": [str,...], "rows_total": int,
             "rows_per_file": {name: int}, "synthesized": [name,...],
             "skipped": [(name, reason),...], "engine": str, "elapsed_s": float,
             "sheets": {name: {sheet, score, low_confidence, blank_dropped}},
             "low_confidence": [name,...], "total_filled": int}.
    Raise RekapImportError bila folder tak ada / kosong / tak ada file rekap.
    """
    import tempfile
    folder = Path(folder_path)
    if not folder.is_dir():
        raise RekapImportError(
            f"Folder tidak ditemukan: {folder_path}")
    if config is None:
        config = load_config()
    # Scan .xlsx (skip Excel lock temp ~$ + hidden)
    xlsx_files = sorted(
        p for p in folder.glob("*.xlsx")
        if not p.name.startswith("~$") and not p.name.startswith("."))
    if not xlsx_files:
        raise RekapImportError(
            f"Tidak ada file .xlsx di folder: {folder}")
    # Engine detection (transparan — log engine yg dipakai).
    engine_used = _EXCEL_ENGINE if _EXCEL_ENGINE else "openpyxl"
    _log(logger, f"[rekap_folder] scan {len(xlsx_files)} file .xlsx di "
                 f"{folder} (engine={engine_used}, parallel)")
    import time
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.monotonic()

    def _process_one(fp: Path):
        """Baca 1 file → (name, df|None, synth, error|None, info|None).
        Thread-safe: calamine (Rust) aman paralel; openpyxl I/O release
        GIL sebagian. v2.18.0: cancel_check dicek ANTAR-FILE (pola
        HistoryWorker) — raise RekapImportError ramah; file antrean
        berikutnya langsung batal (cek di baris pertama tiap file).
        v2.18.2: (a) sheet dipilih _scan_best_rekap_sheet (SKOR — lihat
        blok komentar v2.18.2; dulu sheet seksi DEVIASI bisa terpilih
        bila lebih duluan); (b) baris SEPENUHNYA kosong dibuang (ciri
        sheet seksi DEVIASI — baris kosong interleaved); (c) info sheet
        (nama/skor/low_confidence) dikembalikan utk transparansi UI."""
        if cancel_check is not None and cancel_check():
            raise RekapImportError("Scan folder dibatalkan pengguna")
        try:
            sn, hr, score = _scan_best_rekap_sheet(
                fp, config, require_resto=False, logger=None)
        except RekapImportError as exc:
            return (fp.name, None, False, str(exc), None)
        try:
            # _read_excel_fast: calamine bila ada (8,5x cepat), fallback
            # openpyxl. dtype=object jaga nilai mentah (hari 0/teks).
            raw = _read_excel_fast(fp, sheet_name=sn, header=hr,
                                   dtype=object)
        except Exception as exc:
            return (fp.name, None, False, f"gagal baca sheet {sn!r}: {exc}",
                    None)
        raw = _normalize_columns(raw)
        # v2.18.2 — buang baris SEPENUHNYA kosong (semua kolom None/"
        # empty") SEBELUM sintesis NAMA RESTO: sheet seksi DEVIASI di
        # file user ber-baris kosong interleaved (±50% baris) — baris
        # itu tak membawa data apa pun & menggembungkan file gabungan.
        n_blank = 0
        if len(raw):
            not_blank = pd.Series(False, index=raw.index)
            for c in raw.columns:
                s = raw[c]
                nb = s.notna()
                if not nb.any():
                    continue
                vals = s[nb].astype(str).str.strip()
                nb = nb.copy()
                nb.loc[vals.index] = nb.loc[vals.index] & vals.ne("")
                not_blank = not_blank | nb
            n_blank = int((~not_blank).sum())
            if n_blank:
                raw = raw.loc[not_blank].copy()
        synth = False
        # v2.18.0 audit (BUG 8): deteksi case-INSENSITIVE — file dgn
        # kolom "Nama Resto" (title-case) lolos deteksi header lenient
        # TAPI lolos juga cek exact-case lama → nilai resto ASLI dibuang
        # & diganti nama file + kolom kembar di concat union. Kini kolom
        # case-variant di-rename ke kanonik; nilai asli dipertahankan.
        resto_col = next((c for c in raw.columns
                          if str(c).strip().upper() == "NAMA RESTO"), None)
        if resto_col is None:
            raw["NAMA RESTO"] = fp.stem
            synth = True
        elif resto_col != "NAMA RESTO":
            raw = raw.rename(columns={resto_col: "NAMA RESTO"})
        info = {"sheet": sn, "score": round(float(score), 1),
                "low_confidence": bool(score < _SCORE_MIN),
                "blank_dropped": n_blank}
        return (fp.name, raw, synth, None, info)

    # PARALLEL — baca multiple file sekaligus (max 4 worker).
    max_w = min(4, len(xlsx_files))
    proc_results: list[tuple] = []
    with ThreadPoolExecutor(max_workers=max_w) as ex:
        proc_results = list(ex.map(_process_one, xlsx_files))
    elapsed = time.monotonic() - t0

    frames: list[tuple[str, pd.DataFrame, bool]] = []
    skipped: list[tuple[str, str]] = []
    sheets_info: dict[str, dict] = {}
    low_confidence: list[str] = []
    for name, df, synth, err, info in proc_results:
        if err is not None:
            skipped.append((name, err))
            _log(logger, f"[rekap_folder] {name} dilewati: {err}")
        else:
            frames.append((name, df, synth))
            if info:
                sheets_info[name] = info
                if info.get("low_confidence"):
                    low_confidence.append(name)
                extra = ""
                if info.get("blank_dropped"):
                    extra = (f", {info['blank_dropped']} baris kosong "
                             f"dibuang")
                _log(logger, f"[rekap_folder] {name}: {len(df)} baris "
                             f"(sheet '{info.get('sheet', '?')}'{extra})")
                if info.get("low_confidence"):
                    _log(logger, f"[rekap_folder] WARNING {name}: sheet "
                                 f"'{info.get('sheet')}' skor rendah "
                                 f"({info.get('score')}) — kemungkinan "
                                 f"BUKAN rekap mentah penuh; periksa "
                                 f"isi file.")
            else:
                _log(logger, f"[rekap_folder] {name}: {len(df)} baris")
    if not frames:
        names = ", ".join(n for n, _ in skipped) or "(none)"
        raise RekapImportError(
            f"Tidak ada file dengan sheet REKAP MENTAH di folder {folder}. "
            f"File dilewati: {names}")
    # Gabung semua frame (kolom union — fillna NaN bila beda struktur)
    combined = pd.concat([f for _, f, _ in frames], ignore_index=True,
                         sort=False)
    # v2.18.3 — ISI sel TOTAL kosong di gabungan (bug user: "kolom
    # total pada file hasil program kok blank?"). Passthrough mentah
    # meninggalkan celah dari sel TOTAL kosong di sumber + kolom union
    # NaN (file tanpa kolom TOTAL). Analisa TIDAK terpengaruh (stage_02
    # & Banding Periode selalu menghitung ulang TOTAL dari kolom hari
    # dgn key_akhir) — ini murni kejujuran file hasil gabungan.
    n_total_filled = _fill_total_column(combined)
    if n_total_filled:
        _log(logger, f"[rekap_folder] kolom TOTAL diisi: {n_total_filled} "
                     f"sel kosong → jumlah kolom hari")
    # Tulis temp file (sheet "REKAP MENTAH" — siap di-feed run_pipeline;
    # find_rekap_sheet STRICT akan deteksi karena NAMA RESTO kini ada).
    # v2.17.5 — openpyxl WRITE-ONLY mode (~5-10x lebih cepat dari normal
    # pd.ExcelWriter untuk data besar: 52k baris × 42 kolom = ~20s→~3s).
    # calamine tidak bisa TULIS (hanya baca), jadi openpyxl write-only =
    # tercepat utk menulis. Write-only: append per-baris, tak simpan sel
    # di memori — hemat RAM + cepat.
    import tempfile
    from openpyxl import Workbook
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".xlsx", prefix="rekap_folder_")
    os.close(tmp_fd)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("REKAP MENTAH")
    ws.append(list(combined.columns))
    for row in combined.itertuples(index=False, name=None):
        # NaN → None (openpyxl tulis sel kosong, bukan "nan" string).
        # np.integer/np.floating → Python native (openpyxl write-only
        # terima int/float/str/None/bool).
        ws.append([None if (isinstance(v, float) and v != v) else v
                   for v in row])
    wb.save(tmp_path)
    _log(logger, f"[rekap_folder] gabungan {len(combined)} baris → "
                 f"{tmp_path} ({len(frames)} file, {elapsed:.1f}s, "
                 f"engine={engine_used})")
    return {
        "temp_path": tmp_path,
        "files": [n for n, _, _ in frames],
        "rows_total": len(combined),
        "rows_per_file": {n: len(f) for n, f, _ in frames},
        "synthesized": [n for n, _, s in frames if s],
        "skipped": skipped,
        "engine": engine_used,
        "elapsed_s": round(elapsed, 2),
        # v2.18.2 — transparansi sheet per file (nama sheet terpilih,
        # skor bukti rekap, jumlah baris kosong dibuang) + daftar file
        # yg sheet-nya meragukan (skor < _SCORE_MIN — UI menampilkan
        # warning; anti silent-error).
        "sheets": sheets_info,
        "low_confidence": low_confidence,
        # v2.18.3 — transparansi isi-ulang kolom TOTAL (anti
        # silent-error; UI mencatat di log folder).
        "total_filled": n_total_filled,
    }


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


# ============================================================
# v2.15.0 — SEKALI JALAN: helper dipakai pipeline.py langsung
# pada file REKAP MENTAH mentah (tanpa file antara)
# ============================================================

def _looks_like_rekap_header(cols_upper: list[str]) -> bool:
    """Kolom frame SUDAH jadi header rekap yang valid? (case-toleran)."""
    return (
        all(rc in cols_upper for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG"))
        and sum(1 for c in cols_upper if c in _DAY_SET) >= 3
    )


def ensure_rekap_header(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """v2.15.0: perbaiki header TERGESER pada frame hasil loader (header=0).

    Sheet rekap kadang ber-baris judul di atas header (pola
    fn_rekap_mentah stock-monitoring). Loader membaca header=0 → kolom
    jadi judul sampah & baris PERTAMA data = header asli. Fungsi ini:
      1. Cepat: kolom sudah valid (NAMA RESTO + JENIS + NAMA BARANG + ≥3
         hari) → passthrough IDENTITAS (no-op — file standar tak
         tersentuh, nol biaya dijalur normal).
      2. Bangun grid mentar dari frame: baris 0 = header palsu (judul),
         baris 1.. = data (header asli ada di antaranya).
      3. Deteksi baris header schema (≤6 baris — _detect_header_row).
         Ketemu → _promote_at + _normalize_columns; TIDAK ketemu →
         passthrough apa adanya (validate_rekap_schema akan memberi
         pesan error jujur — fungsi ini bukan tempat menebak).

    v2.16.0 — fitur "edit dari pop-up": pasang kolom tersembunyi
    SRC_ROW_COL ("__SRC_ROW") = nomor baris FISIK sheet sumber (1-based;
    baris 1 = header, data mulai baris 2). Row-accounting di sini (titik
    tunggal — kedua jalur tahu offset Excel). Passthrough: df row i =
    Excel row i+2. Promote jalur: output row j = grid row hr+1+j = Excel
    row hr+j+2. Kolom ini survive pipeline stages (biasa, tidak di-drop)
    dan dipakai source_writer.write_day_edits() untuk tulis koreksi ke
    baris yang BENAR. Idempoten: bila sudah ada, tidak ditimpa.
    """
    if df is None or df.empty:
        return df
    cols_upper = [str(c).strip().upper() for c in df.columns]
    if _looks_like_rekap_header(cols_upper):
        return _attach_src_row(df, offset_first=2, logger=logger)

    n = len(df.columns)
    head = pd.DataFrame([list(df.columns)], columns=list(range(n)))
    body = df.reset_index(drop=True)
    body.columns = list(range(n))
    grid = pd.concat([head, body], ignore_index=True)
    hr = _detect_header_row(grid)
    if hr is None:
        return _attach_src_row(df, offset_first=2, logger=logger)
    out = _normalize_columns(_promote_at(grid, hr))
    _log(logger, f"[rekap_import] header tergeser — baris {hr} data "
                 f"dipromosi jadi header (pola fn_rekap_mentah)")
    # Promote jalur: output row j = grid row hr+1+j = Excel row hr+j+2.
    # offset_first = hr+2 (baris Excel pertama data setelah header dipromosi).
    return _attach_src_row(out, offset_first=hr + 2, logger=logger)


def _attach_src_row(df: pd.DataFrame, offset_first: int,
                    logger=None) -> pd.DataFrame:
    """v2.16.0: pasang kolom SRC_ROW_COL = baris fisik Excel (1-based).

    offset_first = nomor baris Excel untuk df row 0 (baris-1 Excel =
    header; data mulai baris 2 → offset_first=2 utk passthrough).
    Idempoten: bila kolom sudah ada & berupa numerik, TIDAK ditimpa
    (re-run pipeline / re-load tidak merusak mapping). Bukan inplace
    (salin dulu — anti side-effect ke df pemanggil).
    """
    if df is None or df.empty:
        return df
    if SRC_ROW_COL in df.columns:
        # Sudah ada — validasi numerik; bila bukan numerik, bangun ulang.
        ok = pd.api.types.is_numeric_dtype(df[SRC_ROW_COL])
        if ok and not df[SRC_ROW_COL].isna().any():
            return df  # mapping utuh — jangan ganggu
        _log(logger, f"[rekap_import] {SRC_ROW_COL} ada tapi rusak "
                     f"(non-numerik/NaN) — bangun ulang")
        df = df.drop(columns=[SRC_ROW_COL])
    out = df.copy()
    n = len(out)
    out[SRC_ROW_COL] = range(offset_first, offset_first + n)
    _log(logger, f"[rekap_import] pasang {SRC_ROW_COL}: baris Excel "
                 f"{offset_first}..{offset_first + n - 1} ({n} baris)")
    return out


def _bom_map_from_rows(raw: pd.DataFrame,
                       day_cols: list[str]) -> dict[tuple[str, str], float]:
    """TOTAL BOM per (NAMA RESTO, NAMA BARANG) dari baris JENIS=="BOM".

    Satu sumber kebenaran utk convert_rekap_mentah (v2.14.0) DAN
    inject_bom_from_raw_rows (v2.15.0): groupby jumlah kolom hari, kunci
    _key_str dua sisi (outlet numerik 1049.0 → "1049"; None → skip —
    pola H9-a: kunci kosong tak bisa di-join)."""
    bom_map: dict[tuple[str, str], float] = {}
    if raw is None or raw.empty or "JENIS" not in raw.columns:
        return bom_map
    jenis_norm = raw["JENIS"].astype(str).str.strip().str.upper()
    bom_rows = raw[jenis_norm == "BOM"]
    if bom_rows.empty:
        return bom_map
    bom_num = bom_rows[day_cols].apply(pd.to_numeric, errors="coerce")
    bom_tot = bom_num.fillna(0).sum(axis=1)
    k_resto = bom_rows["NAMA RESTO"].map(_key_str)
    k_barang = bom_rows["NAMA BARANG"].map(_key_str)
    for r, b, t in zip(k_resto, k_barang, bom_tot):
        if r is None or b is None:
            continue  # kunci kosong — tidak bisa di-join (pola H9-a)
        key = (r, b)
        bom_map[key] = bom_map.get(key, 0.0) + float(t)
    return bom_map


def _bom_inline_series(df: pd.DataFrame,
                       bom_map: dict) -> pd.Series:
    """Kolom inline "TOTAL BOM" utk frame data W/S/T (NaN tanpa pasangan)."""
    resto_key = df["NAMA RESTO"].map(_key_str)
    barang_key = df["NAMA BARANG"].map(_key_str)
    return pd.Series(
        [bom_map.get((r, b)) for r, b in zip(resto_key, barang_key)],
        index=df.index, dtype="float64")


# Kolom identity yang di-strip converter pada file olahan (v2.14.0 —
# "identity passthrough di-strip" pola fn_rekap_mentah). Jalur sekali-
# jalan v2.15.0 melakukan strip YANG SAMA supaya hasil pipeline pada
# file mentah == hasil pipeline pada file olahan (parity penuh).
_IDENTITY_COLS = ("SOURCE DATA", "KETERANGAN", "NAMA BARANG",
                  "NAMA RESTO", "SATUAN")


def normalize_rekap_values(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """v2.15.0: normalisasi nilai identity sheet REKAP MENTAH — mirror
    pembersihan convert_rekap_mentah (v2.14.0) supaya jalur sekali-jalan
    menghasilkan analisa IDENTIK dengan jalur 2-langkah lama
    (olah → export → pipeline):

      - JENIS dinormalisasi strip+upper ('waste ' → 'WASTE') — tanpa
        ini baris JENIS tak-kanonik TERBUANG di filter stage_01
        (exact-match) padahal converter menyelamatkannya;
      - kolom identity (SOURCE DATA/KETERANGAN/NAMA BARANG/NAMA RESTO/
        SATUAN) di-strip — 'GR ' → 'GR' (grup satuan/keterangan sama
        dgn file olahan; NaN tetap NaN).

    TRIGGER jujur — hanya sheet MENTAH yang tersentuh: frame memuat
    nilai JENIS non-waste eksplisit (BOM/SO/STOK AWAL — ciri sheet
    rekap "semua jenis") ATAU varian JENIS tak-kanonik. File standar
    DATA_WASTE (W/S/T bersih) → passthrough IDENTITAS — perilaku
    historis (termasuk SATUAN 'GR ' yang memang tidak pernah di-strip
    di file standar) tak berubah, golden test aman.

    Selain identity, kolom HARI (1..31) sel kosong/teks → 0 numerik —
    parity file olahan converter (coerce lalu fillna(0)) DAN parity
    file standar buatan proses M-code user (terukur: DATA_WASTE.xlsx
    23.470 dari 25.901 baris ber-hari semua-0 eksplisit, hanya 1 sel
    null — proses olahan user MEMANG mengisi 0). Tanpa ini: baris
    hari-kosong-semua TERBUANG di filter TOTAL-notna stage_02
    (25.722 → 25.692 di file asli) dan AVG berubah semantik di sel
    kosong parsial (mean non-null ≠ mean semua-kolom).

    Return SALINAN bila ada perubahan (caller tak termutasi — pola M6).
    """
    if df is None or df.empty or "JENIS" not in df.columns:
        return df
    s = df["JENIS"]
    # v2.17.5 — strip prefix angka kategori ('2.WASTE'→'WASTE',
    # '3.SUSUT'→'SUSUT', '4.TRIAL'→'TRIAL'). File resto tertentu pakai
    # JENIS ber-prefix angka (template Power Query variant — '1.DEVIASI',
    # '2.WASTE', '3.SUSUT', '4.TRIAL', '5.LOSS SURPLUS', dst.). Tanpa
    # strip ini, '2.WASTE' dianggap BUKAN WASTE → dibuang filter Stage 1
    # → resto hilang dari analisa (bug 17/20 — hanya 17 resto masuk dari
    # 20 file). Strip dilakukan SETELAH upper+strip supaya '2.waste '→
    # 'WASTE' (prefix+spasi keduanya dibersihkan).
    norm = s.where(
        s.isna(),
        s.astype(str).str.strip().str.upper()
        .str.replace(r"^\d+\.\s*", "", regex=True))
    # Sheet mentah = ada nilai JENIS eksplisit di luar {W,S,T}
    # (BOM/SO/stok — baris ini memang akan dibuang stage_01) ATAU ada
    # varian tak-kanonik ('waste '). NaN TIDAK memicu (bukan ciri mentah).
    nonkeep = norm.notna() & ~norm.isin(_KEEP_JENIS)
    dirty = s.notna() & (norm != s)
    if not (nonkeep.any() or dirty.any()):
        return df
    out = df.copy()
    out["JENIS"] = norm
    n_strip = 0
    for col in _IDENTITY_COLS:
        if col not in out.columns:
            continue
        c = out[col]
        if c.dtype != object and not pd.api.types.is_string_dtype(c):
            continue
        stripped = c.where(c.isna(), c.astype(str).str.strip())
        n_strip += int((stripped.fillna("") != c.fillna("")).sum())
        out[col] = stripped
    # Hari kosong/teks → 0 numerik (mirror converter: coerce DULU baru
    # fillna — teks 'abc' pun jadi 0, bukan NaN yang lolos ke stage_02
    # dgn semantik 'sum non-null' yang beda).
    n_fill = 0
    for col in _day_cols_of(out):
        coerced = pd.to_numeric(out[col], errors="coerce")
        n_fill += int(coerced.isna().sum())
        out[col] = coerced.fillna(0)
    n_jenis = int(dirty.sum())
    _log(logger, f"[rekap_import] nilai sheet mentah dinormalisasi "
                 f"(parity olahan v2.14.0): JENIS {n_jenis} baris "
                 f"kanonisasi + {n_strip} sel identity di-strip + "
                 f"{n_fill} sel hari kosong → 0")
    return out


def inject_bom_from_raw_rows(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """v2.15.0: tambah kolom inline "TOTAL BOM" dari baris JENIS=="BOM"
    sheet mentah — dipanggil pipeline SEBELUM stage_01 (stage_01
    memfilter baris BOM keluar; tanpa injeksi ini sinyal S6/S7 mati di
    file mentah karena kolom TOTAL BOM tidak ada & sheet BOM terpisah
    tidak ada di file rekap).

    Guard (idempotent + jujur):
      - "TOTAL BOM" SUDAH ada di kolom → passthrough identitas (file
        standar / hasil olahan / re-run output — stage_05 memakai kolom
        inline itu, nilai tak diganggu).
      - Tanpa "JENIS" / tanpa baris JENIS=="BOM" → passthrough (file
        pure W-S-T: stage_05 jatuh ke jalur sheet BOM seperti biasa).
      - Tanpa "NAMA RESTO"/"NAMA BARANG" → passthrough (frame tak bisa
        di-join; validate_rekap_schema akan bicara).
    Return SALINAN frame dengan kolom baru (caller frame tak termutasi —
    pola M6 stage_05).
    """
    if df is None or df.empty:
        return df
    if "TOTAL BOM" in df.columns:
        return df
    if "JENIS" not in df.columns or "NAMA RESTO" not in df.columns \
            or "NAMA BARANG" not in df.columns:
        return df
    day_cols = _day_cols_of(df)
    if not day_cols:
        return df
    jenis_norm = df["JENIS"].astype(str).str.strip().str.upper()
    n_bom_rows = int((jenis_norm == "BOM").sum())
    if n_bom_rows == 0:
        return df
    bom_map = _bom_map_from_rows(df, day_cols)
    if not bom_map:
        return df
    out = df.copy()
    bom_inline = _bom_inline_series(out, bom_map)
    out["TOTAL BOM"] = bom_inline
    # Hitung match hanya pada baris DATA (W/S/T) — semantik bom_matched
    # converter; baris BOM/SO ikut kena join tapi memang dibuang stage_01
    # (menghitungnya menyesatkan: '51.364 baris data' padahal datanya
    # 25 ribu).
    keep_mask = jenis_norm.isin(_KEEP_JENIS)
    n_matched = int(bom_inline[keep_mask].notna().sum())
    _log(logger, f"[rekap_import] TOTAL BOM inline dari {n_bom_rows} baris "
                 f"JENIS=BOM → {len(bom_map)} pasangan (resto, barang); "
                 f"{n_matched} baris data (W/S/T) ber-TOTAL BOM — sinyal "
                 f"S6/S7 & Rill % to BOM aktif (v2.15.0 sekali jalan)")
    return out


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
                         out_path: str | os.PathLike | None = None,
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
    # v2.18.0 audit (BUG 3): KANONIKALISASI HEADER ke UPPERCASE kanonik.
    # Validasi kolom wajib di bawah case-INSENSITIVE, tapi akses kolom
    # berikutnya exact-case ("JENIS", "SOURCE DATA", …) — file ber-header
    # "Jenis"/"Nama Resto" lolos validasi lalu crash KeyError mentah.
    _ren = {}
    for _c in raw.columns:
        _cu = str(_c).strip().upper()
        if _cu in _CANON_HEADER_COLS and str(_c).strip() != _cu:
            _ren[_c] = _cu
    if _ren:
        raw = raw.rename(columns=_ren)
        # case-variant kembar ("Jenis" + "JENIS") → duplikat pasca-rename;
        # keep first (pola pandas mangling).
        raw = raw.loc[:, ~raw.columns.duplicated()]
        _log(logger, f"[rekap_import] header case-variant dinormalisasi: "
                     f"{_ren}")
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
    # BARANG) — ditulis inline (prioritas stage_05) + sheet BOM
    # (v2.15.0: logika diekstrak ke _bom_map_from_rows — dipakai BERSAMA
    # inject_bom_from_raw_rows jalur sekali-jalan pipeline; satu sumber
    # kebenaran) ---
    bom_map = _bom_map_from_rows(raw, day_cols)
    n_bom_rows = int((jenis_norm == "BOM").sum())
    _log(logger, f"[rekap_import] BOM: {n_bom_rows} baris JENIS=BOM → "
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
    # outlet numerik 1049.0 → "1049"; None → None tak join palsu)
    # (v2.15.0: _bom_inline_series — shared dgn inject_bom_from_raw_rows) ---
    bom_inline = _bom_inline_series(kept, bom_map)
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
