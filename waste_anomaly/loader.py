"""
loader.py — pemuat data input dari workbook Excel.

Setara dengan Excel.CurrentWorkbook() + query referensi M code:
  - Source = DATA_WASTE (named range atau sheet)
  - BOM lookup = query "2  22 05" (BOM master)
  - DATABASE_SATUAN (master expected helper per kategori)

Strategi: coba multiple nama sheet / named range. Bila gagal, raise dengan pesan jelas.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from .utils import load_config


# ============================================================
# DETEKSI NAMA SHEET / NAMED RANGE
# ============================================================

def list_sheets(workbook_path: str | os.PathLike) -> list[str]:
    """List semua sheet di workbook (openpyxl, read-only)."""
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    sheets = list(wb.sheetnames)
    wb.close()
    return sheets


def list_named_ranges(workbook_path: str | os.PathLike) -> dict[str, str]:
    """Return dict {name: "SheetName!A1:Z100"} untuk semua defined name."""
    wb = load_workbook(workbook_path, data_only=True)
    names: dict[str, str] = {}
    try:
        for name, defn in wb.defined_names.items():
            # defn.value berbentuk "Sheet1!$A$1:$Z$100"
            names[name] = str(defn.value)
    except Exception:
        # Kompatibilitas openpyxl lama (wb.defined_names adalah NamedRangeList)
        try:
            for defn in wb.defined_names.definedName:
                names[defn.name] = defn.value
        except Exception:
            pass
    wb.close()
    return names


def find_sheet(names_candidates: list[str], available: list[str]) -> str | None:
    """Cari sheet yang cocok (case-insensitive, exact dulu, lalu contains)."""
    available_lower = [s.lower() for s in available]
    # Exact
    for cand in names_candidates:
        cl = cand.lower().strip()
        if cl in available_lower:
            return available[available_lower.index(cl)]
    # Contains (akomodasi nama sheet dengan prefix/suffix)
    for cand in names_candidates:
        cl = cand.lower().strip()
        for i, s in enumerate(available_lower):
            if cl in s:
                return available[i]
    return None


def resolve_sheet_for(
    purpose: str,
    config: dict,
    available_sheets: list[str],
    named_ranges: dict[str, str],
) -> tuple[str, str | None]:
    """
    Resolve sheet untuk tujuan `purpose` ('rekap_mentah' | 'bom' | 'database_satuan').
    Return: (sheet_name, named_range_ref_or_None).

    Strategi:
      1. Cari named range dengan nama kandidat (priority).
      2. Cari sheet dengan nama kandidat.
      3. Raise kalau tidak ketemu.
    """
    candidates = config.get("input_sheets", {}).get(purpose, [])
    if not candidates:
        # Default minimal
        candidates = {
            "rekap_mentah": ["REKAP_MENTAH", "Rekap Mentah"],
            "bom": ["BOM", "2  22 05", "MASTER BOM"],
            "database_satuan": ["DATABASE_SATUAN", "Database Satuan"],
        }.get(purpose, [])

    # 1. Named range
    for cand in candidates:
        if cand in named_ranges:
            ref = named_ranges[cand]
            # Ambil sheet dari ref "SheetName!$A$1:$Z$100"
            sheet = ref.split("!")[0].strip("'").strip('"')
            return sheet, ref

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
# LOAD 1: DATA_WASTE (input utama)
# ============================================================

def load_rekap_mentah(
    workbook_path: str | os.PathLike,
    config: dict,
    logger=None,
) -> pd.DataFrame:
    """Load DATA_WASTE (input utama pipeline). Setara Source = Excel.CurrentWorkbook(){[Name="DATA_WASTE"]}[Content]."""
    sheets = list_sheets(workbook_path)
    named = list_named_ranges(workbook_path)
    sheet, ref = resolve_sheet_for("rekap_mentah", config, sheets, named)
    if logger:
        logger(f"[loader] DATA_WASTE: sheet='{sheet}', named_range={ref!r}")

    # Baca sheet penuh (header baris pertama)
    df = pd.read_excel(workbook_path, sheet_name=sheet, header=0)
    df = _normalize_columns(df)
    if logger:
        logger(f"[loader] DATA_WASTE loaded: {len(df)} rows, {len(df.columns)} cols")
    return df


# ============================================================
# LOAD 2: BOM (query "2  22 05")
# ============================================================

def load_bom(
    workbook_path: str | os.PathLike,
    config: dict,
    logger=None,
) -> pd.DataFrame:
    """
    Load BOM lookup. Setara BOMLookup di M code (Table.Distinct dari query "2  22 05").
    Kolom yang diharapkan: outlet (Nomor #), item (Nama Barang), total_bom (TOTAL BOM).
    """
    sheets = list_sheets(workbook_path)
    named = list_named_ranges(workbook_path)
    try:
        sheet, ref = resolve_sheet_for("bom", config, sheets, named)
    except ValueError:
        if logger:
            logger("[loader] BOM sheet tidak ditemukan — BOM join dilewati (TOTAL BOM = None)")
        return pd.DataFrame(columns=["Nomor #", "Nama Barang", "TOTAL BOM"])

    if logger:
        logger(f"[loader] BOM: sheet='{sheet}', named_range={ref!r}")

    df = pd.read_excel(workbook_path, sheet_name=sheet, header=0)
    df = _normalize_columns(df)

    # Resolve nama kolom sesuai konfigurasi (kemungkinan beberapa alias)
    bom_cfg = config.get("bom_columns", {})
    outlet_col = _find_column(df.columns, bom_cfg.get("outlet", ["Nomor #"]))
    item_col = _find_column(df.columns, bom_cfg.get("item", ["Nama Barang"]))
    total_col = _find_column(df.columns, bom_cfg.get("total_bom", ["TOTAL BOM"]))

    if not item_col or not total_col:
        if logger:
            logger(
                f"[loader] WARNING: BOM missing item/total col. "
                f"outlet={outlet_col}, item={item_col}, total={total_col}"
            )
        return pd.DataFrame(columns=["Nomor #", "Nama Barang", "TOTAL BOM"])

    # Normalisasi nama ke kanvas yang seragam
    out = pd.DataFrame()
    out["Nomor #"] = df[outlet_col] if outlet_col else None
    out["Nama Barang"] = df[item_col]
    out["TOTAL BOM"] = pd.to_numeric(df[total_col], errors="coerce")

    # Strip whitespace sebelum dedup (konsisten dengan stage_05_bom join)
    out["Nomor #"] = out["Nomor #"].astype(str).str.strip()
    out["Nama Barang"] = out["Nama Barang"].astype(str).str.strip()

    # Distinct by (Nomor #, Nama Barang) — setara Table.Distinct di M
    out = out.drop_duplicates(subset=["Nomor #", "Nama Barang"], keep="first")
    if logger:
        logger(f"[loader] BOM loaded: {len(out)} distinct (outlet, item)")
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
    """
    sheets = list_sheets(workbook_path)
    named = list_named_ranges(workbook_path)
    try:
        sheet, ref = resolve_sheet_for("database_satuan", config, sheets, named)
    except ValueError:
        if logger:
            logger("[loader] DATABASE_SATUAN sheet tidak ditemukan — STATUS jadi 'Cek'")
        return pd.DataFrame(columns=["NAMA ITEM"])

    if logger:
        logger(f"[loader] DATABASE_SATUAN: sheet='{sheet}', named_range={ref!r}")

    df = pd.read_excel(workbook_path, sheet_name=sheet, header=0)
    df = _normalize_columns(df)

    # Resolve kolom item
    satuan_cfg = config.get("satuan_columns", {})
    item_col = _find_column(df.columns, satuan_cfg.get("item_key", ["NAMA ITEM"]))
    if not item_col:
        if logger:
            logger("[loader] WARNING: DATABASE_SATUAN tidak punya kolom NAMA ITEM")
        return pd.DataFrame(columns=["NAMA ITEM"])
    out = df.rename(columns={item_col: "NAMA ITEM"})
    # Strip whitespace sebelum dedup (konsisten dengan stage_09_satuan join)
    out["NAMA ITEM"] = out["NAMA ITEM"].astype(str).str.strip()
    # Distinct by NAMA ITEM (setara Table.Distinct)
    out = out.drop_duplicates(subset=["NAMA ITEM"], keep="first")
    if logger:
        logger(f"[loader] DATABASE_SATUAN loaded: {len(out)} distinct items")
    return out


# ============================================================
# HELPER INTERNAL
# ============================================================

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalisasi nama kolom: strip whitespace, hilangkan BOM char."""
    new_cols = []
    for c in df.columns:
        if isinstance(c, str):
            s = c.replace("\ufeff", "").strip()
            new_cols.append(s)
        else:
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
