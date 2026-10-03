"""Validasi skema input — anti degradasi senyap (v2.4.0, F8).

MASALAH YANG DIPERBAIKI (terverifikasi audit):
Workbook dengan header huruf kecil ("Jenis", "Nama Barang") sebelumnya
diproses dengan ``success=True`` — filter JENIS dilewati, stage 3/5/6/7
no-op, semua baris "Normal" padahal ada spike. Pipeline "sehat" dengan
analisa setengah mati, TANPA error apa pun.

Sekarang: `validate_rekap_schema` memeriksa kolom wajib sebelum stage 1.
Missing → `SchemaValidationError` dengan pesan actionable (daftar kolom
hilang + saran near-miss case-insensitive + duplikat header).

Hard error vs warning:
- HARD (run gagal, pesan jelas): kolom wajib hilang, SEMUA kolom hari
  hilang, header duplikat pada kolom wajib.
- WARNING (run lanjut, terlihat di log): sebagian kolom hari hilang.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Kolom wajib (README "Struktur 53 kolom" — bagian ✅ Wajib)
REQUIRED_COLUMNS: tuple[str, ...] = (
    "SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
    "NAMA RESTO", "SATUAN",
)

# Nilai JENIS yang di-keep filter stage 1
VALID_JENIS: tuple[str, ...] = ("SUSUT", "TRIAL", "WASTE")


class SchemaValidationError(ValueError):
    """Input tidak memenuhi kontrak skema — pesan sudah user-friendly."""


def _suggest_near_miss(missing: str, columns: list[Any]) -> str | None:
    """Cari kandidat kolom yang mirip (case / spasi beda) untuk saran perbaikan."""
    norm = lambda s: str(s).strip().upper().replace("  ", " ")
    target = norm(missing)
    best = None
    for col in columns:
        if norm(col) == target and str(col) != missing:
            best = str(col)  # exact match setelah normalisasi (beda case/strip)
    return best


def validate_rekap_schema(
    df: pd.DataFrame,
    key_akhir: int,
    logger=None,
) -> list[str]:
    """Validasi hasil load DATA_WASTE. Raise SchemaValidationError bila wajib hilang.

    Returns:
        list warning (non-fatal) untuk ditampilkan di log/pipeline.
    """
    warnings: list[str] = []
    columns = [str(c) for c in df.columns]

    # --- 1. Header duplikat ---
    seen: dict[str, int] = {}
    dups: list[str] = []
    for col in columns:
        seen[col] = seen.get(col, 0) + 1
        if seen[col] == 2:
            dups.append(col)
    if dups:
        raise SchemaValidationError(
            f"Header kolom DUPLIKAT di sheet input: {dups}. "
            f"pandas membaca kolom kedua sebagai '{dups[0]}.1' — "
            f"hapus/rename kolom duplikat di Excel lalu save ulang."
        )

    # --- 2. Kolom wajib ---
    missing: list[str] = []
    hints: list[str] = []
    col_set = set(columns)
    for req in REQUIRED_COLUMNS:
        if req not in col_set:
            missing.append(req)
            near = _suggest_near_miss(req, columns)
            if near:
                hints.append(f"'{req}' tidak ada, tapi ada '{near}' — "
                             f"rename kolom jadi '{req}' (huruf besar persis)")

    if missing:
        msg = (
            f"Kolom WAJIB hilang dari sheet input: {missing}. "
            f"Struktur standar DATA_WASTE.xlsx butuh kolom: "
            f"{', '.join(REQUIRED_COLUMNS)} + kolom hari '1'..'{key_akhir}'. "
        )
        if hints:
            msg += " Petunjuk: " + "; ".join(hints) + "."
        raise SchemaValidationError(msg)

    # --- 3. Kolom hari ---
    day_cols = [str(i) for i in range(1, key_akhir + 1)]
    have_days = [c for c in day_cols if c in col_set]
    if not have_days:
        raise SchemaValidationError(
            f"Tidak ada kolom hari sama sekali ('1'..'{key_akhir}'). "
            f"Pipeline membaca qty waste per hari dari kolom bernomor 1-31 — "
            f"pastikan header hari berupa ANGKA (1, 2, 3, ...) bukan teks."
        )
    if len(have_days) < len(day_cols):
        missing_days = [c for c in day_cols if c not in col_set]
        w = (f"WARNING skema: kolom hari tidak lengkap — {len(have_days)}/{len(day_cols)} "
             f"ada (hilang: {missing_days[:10]}{'…' if len(missing_days) > 10 else ''}). "
             f"Hari hilang dianggap 0.")
        warnings.append(w)
        if logger:
            logger(w)

    # --- 4. JENIS domain check (soft — filter stage 1 akan buang sisanya) ---
    if "JENIS" in col_set and len(df) > 0:
        jenis_vals = set(df["JENIS"].dropna().astype(str).str.strip().str.upper().unique())
        unknown = jenis_vals - set(VALID_JENIS)
        if unknown and jenis_vals:
            w = (f"WARNING skema: nilai JENIS tidak dikenali: {sorted(unknown)[:8]} "
                 f"— baris ini akan dibuang filter Stage 1 (keep: {', '.join(VALID_JENIS)}).")
            warnings.append(w)
            if logger:
                logger(w)

    return warnings
