"""
make_sample.py — generate sample workbook untuk testing pipeline.

Membuat 3 sheet:
  - REKAP_MENTAH: ~30 baris (5 cabang x 6 item, mix SUSUT/TRIAL/WASTE)
  - BOM: 6 item dengan TOTAL BOM
  - DATABASE_SATUAN: 6 item dengan 11 kolom kategori

Run: python make_sample.py
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

OUT = Path(__file__).resolve().parent / "sample_workbook.xlsx"

CABANG = ["RESTO.PWKTAM", "RESTO.KWGGAL", "RESTO.BSD", "RESTO.MTR", "RESTO.DPKLIM"]
ITEMS = [
    ("Ayam Fillet", "kg"),
    ("Minyak Goreng", "liter"),
    ("Beras Premium", "kg"),
    ("Cabe Merah", "kg"),
    ("Bawang Putih", "kg"),
    ("Susu Full Cream", "liter"),
]
JENIS_LIST = ["WASTE", "SUSUT", "TRIAL"]
KET_LIST = ["Alat/ Mesin", "Cancel Nota", "Eksternal", "Internal", "Over Stock", "Handling", "Kualitas", "Kualitas Eksternal", "Kualitas Internal", "SUSUT", "TRIAL"]
SOURCE_LIST = ["Audit", "Stock Opname", "Laporan Harian"]


def build_rekap():
    rows = []
    rng = np.random.default_rng(42)
    for cabang in CABANG:
        for item_name, satuan in ITEMS:
            # Pilih JENIS random
            jenis = rng.choice(JENIS_LIST)
            ket = rng.choice(KET_LIST)
            src = rng.choice(SOURCE_LIST)
            # Generate 31 hari — mostly 0, beberapa ada waste
            days = {}
            for d in range(1, 32):
                # 30% chance ada waste
                if rng.random() < 0.30:
                    days[str(d)] = round(float(rng.uniform(0.1, 5.0)), 2)
                else:
                    days[str(d)] = 0
            # Inject 1 spike day supaya sinyal S1/S2 trigger
            spike_day = str(rng.integers(1, 28))
            days[spike_day] = round(float(rng.uniform(10.0, 30.0)), 2)
            # Inject last day dominan untuk beberapa baris (S11)
            if rng.random() < 0.20:
                days["31"] = round(float(days[str(d)] if days.get(str(d)) else 0) + rng.uniform(15.0, 40.0), 2)
            row = {
                "KATEGORI": jenis,
                "SOURCE DATA": src,
                "JENIS": jenis,
                "STATUS": "Approved",
                "NAMA BARANG": item_name,
                "KETERANGAN": ket,
                "PENYEBAB TERJADINYA WASTE": "Expired",
                "SATUAN": satuan,
                **days,
                "TOTAL": sum(v for v in days.values() if v),
                "NAMA RESTO": cabang,
                "PIC": "Staff A",
            }
            rows.append(row)
    df = pd.DataFrame(rows)
    return df


def build_bom():
    rows = []
    for cabang in CABANG:
        for item_name, _ in ITEMS:
            rows.append({
                "Nomor #": cabang,
                "Nama Barang": item_name,
                "TOTAL BOM": float(np.random.default_rng(7).uniform(20, 80)),
            })
    return pd.DataFrame(rows)


def build_satuan():
    rows = []
    for item_name, _ in ITEMS:
        rows.append({
            "NAMA ITEM": item_name,
            "CANCEL NOTA": 1,
            "SUSUT": 1,
            "TRIAL": 1,
            "HANDLING": 1,
            "KUALITAS EKSTERNAL": 1,
            "KUALITAS": 1,
            "KUALITAS INTERNAL": 1,
            "EKSTERNAL": 1,
            "INTERNAL": 1,
            "ALAT MESIN": 1,
            "OVERSTOCK": 1,
        })
    return pd.DataFrame(rows)


def main():
    df_rekap = build_rekap()
    df_bom = build_bom()
    df_satuan = build_satuan()

    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        df_rekap.to_excel(writer, sheet_name="REKAP_MENTAH", index=False)
        df_bom.to_excel(writer, sheet_name="BOM", index=False)
        df_satuan.to_excel(writer, sheet_name="DATABASE_SATUAN", index=False)

    print(f"Sample workbook dibuat: {OUT}")
    print(f"  REKAP_MENTAH: {len(df_rekap)} rows")
    print(f"  BOM: {len(df_bom)} rows")
    print(f"  DATABASE_SATUAN: {len(df_satuan)} rows")


if __name__ == "__main__":
    main()
