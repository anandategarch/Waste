"""period_compare.py — perbandingan dua periode run (P9 v2.5.0).

Menjawab pertanyaan bisnis bulan-ke-bulan:
- Total waste naik/turun berapa persen?
- Cabang mana yang bergerak paling besar?
- Item×cabang mana yang berubah paling signifikan (top movers)?
- Item apa yang BARU muncul / HILANG vs periode sebelumnya?

Perbandingan bekerja pada level agregat (NAMA RESTO, NAMA BARANG) dari df
Detail hasil pipeline dua run berbeda — kolom TOTAL dan ANOMALY STATUS
dipakai apa adanya; baris TOTAL<=0 diabaikan (struktur placeholder).

Semua fungsi defensif: kolom hilang / df kosong → hasil kosong yang
bendiformasi, tidak pernah raise.
"""
from __future__ import annotations

import pandas as pd

# Kolom output tetap — UI (tab Compare Periode) merender persis kontrak ini.
SUMMARY_COLS = ["Metrik", "Periode A", "Periode B", "Delta %"]
BRANCH_COLS = ["NAMA RESTO", "Total A", "Total B", "Delta", "Delta %"]
ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Total A", "Total B", "Delta", "Delta %"]
NEW_ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Total B"]
GONE_ITEM_COLS = ["NAMA RESTO", "NAMA BARANG", "Total A"]
JENIS_COLS = ["JENIS", "Total A", "Total B", "Delta", "Delta %"]


def auto_key_akhir(raw: pd.DataFrame) -> int:
    """Deteksi hari terakhir periode dari frame mentah: hari kolom '1'..'31'
    terbesar yang punya jumlah nilai > 0. Fallback 31 bila tidak ada kolom
    hari / semua kosong (min 1).

    Dipakai tab Compare Periode supaya file periode B tidak perlu input
    key_akhir manual.
    """
    best = 0
    for col in raw.columns:
        name = str(col).strip()
        if not name.isdigit():
            continue
        day = int(name)
        if not (1 <= day <= 31):
            continue
        try:
            vals = pd.to_numeric(raw[col], errors="coerce")
        except Exception:  # noqa: BLE001, S112 — kolom aneh tidak boleh menggagalkan deteksi
            continue
        if (vals > 0).any():
            best = max(best, day)
    if best >= 1:
        return best
    return 31


def _item_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Agregat TOTAL per (NAMA RESTO, NAMA BARANG), hanya baris TOTAL>0.

    Return frame kolom [NAMA RESTO, NAMA BARANG, TOTAL] atau kosong bila
    kolom kunci tidak ada / tidak ada baris aktif.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["NAMA RESTO", "NAMA BARANG", "TOTAL"])
    if not all(c in df.columns for c in ("NAMA RESTO", "NAMA BARANG", "TOTAL")):
        return pd.DataFrame(columns=["NAMA RESTO", "NAMA BARANG", "TOTAL"])
    sub = df[["NAMA RESTO", "NAMA BARANG", "TOTAL"]].copy()
    sub["TOTAL"] = pd.to_numeric(sub["TOTAL"], errors="coerce").fillna(0)
    sub = sub[sub["TOTAL"] > 0]
    if sub.empty:
        return pd.DataFrame(columns=["NAMA RESTO", "NAMA BARANG", "TOTAL"])
    out = (
        sub.groupby(["NAMA RESTO", "NAMA BARANG"], as_index=False, dropna=False)
        .agg(TOTAL=("TOTAL", "sum"))
    )
    return out


def _delta_pct(new: float, old: float) -> float:
    """Persentase perubahan new vs old. 0.0 bila keduanya 0; NaN (tampil '∞'
    di UI) bila old 0 dan new > 0 — konvensi div-by-zero yang disengaja."""
    if old > 0:
        return (new - old) / old * 100.0
    if new > 0:
        return float("nan")
    return 0.0


def compare_periods(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    label_a: str = "Periode A",
    label_b: str = "Periode B",
    top_n: int = 100,
) -> dict:
    """Bandingkan dua run pipeline (df Detail).

    Return dict:
      summary   — Metrik × (A, B, Delta %): Total Waste, Baris Aktif,
                  Cabang Aktif, Item Aktif, Prioritas, Potensi, Review.
      per_jenis — TOTAL per JENIS A vs B + Delta.
      branch    — per NAMA RESTO (Total A/B, Delta) sort |Delta| desc, cap top_n.
      items     — per (resto, item) sort |Delta| desc, cap top_n.
      new_items — pasangan hanya muncul di B (Total B > 0).
      gone_items— pasangan hanya muncul di A (Total A > 0).
    Semua tabel memakai konstanta *_COLS di atas.
    """
    empty_jenis = pd.DataFrame(columns=JENIS_COLS)
    empty_branch = pd.DataFrame(columns=BRANCH_COLS)
    empty_items = pd.DataFrame(columns=ITEM_COLS)
    empty_new = pd.DataFrame(columns=NEW_ITEM_COLS)
    empty_gone = pd.DataFrame(columns=GONE_ITEM_COLS)

    def _status_count(df: pd.DataFrame, status: str) -> int:
        if df is None or df.empty or "ANOMALY STATUS" not in df.columns:
            return 0
        try:
            return int((df["ANOMALY STATUS"] == status).sum())
        except Exception:  # noqa: BLE001
            return 0

    ta = _item_totals(df_a)
    tb = _item_totals(df_b)

    total_a = float(ta["TOTAL"].sum()) if not ta.empty else 0.0
    total_b = float(tb["TOTAL"].sum()) if not tb.empty else 0.0

    # ---- summary metrik ----
    def _active_rows(df: pd.DataFrame) -> int:
        if df is None or df.empty or "TOTAL" not in df.columns:
            return 0
        vals = pd.to_numeric(df["TOTAL"], errors="coerce").fillna(0)
        return int((vals > 0).sum())

    def _nunique(df: pd.DataFrame, col: str) -> int:
        if df is None or df.empty or col not in df.columns:
            return 0
        return int(df[col].nunique())

    rows = [
        ("Total Waste", total_a, total_b),
        ("Baris Aktif (>0)", _active_rows(df_a), _active_rows(df_b)),
        ("Cabang Aktif", _nunique(ta, "NAMA RESTO"), _nunique(tb, "NAMA RESTO")),
        ("Item Aktif", _nunique(ta, "NAMA BARANG"), _nunique(tb, "NAMA BARANG")),
        ("Anomali Prioritas", _status_count(df_a, "Prioritas Tinggi"),
         _status_count(df_b, "Prioritas Tinggi")),
        ("Potensi Anomali", _status_count(df_a, "Potensi Anomali"),
         _status_count(df_b, "Potensi Anomali")),
        ("Perlu Review", _status_count(df_a, "Perlu Review"),
         _status_count(df_b, "Perlu Review")),
    ]
    summary = pd.DataFrame(
        [
            {
                "Metrik": m,
                "Periode A": va,
                "Periode B": vb,
                "Delta %": _delta_pct(float(vb), float(va)),
            }
            for m, va, vb in rows
        ],
        columns=SUMMARY_COLS,
    )

    # ---- per JENIS ----
    jenis_frames = []
    for label, df in ((label_a, df_a), (label_b, df_b)):
        if df is None or df.empty or not all(
            c in df.columns for c in ("JENIS", "TOTAL")
        ):
            jenis_frames.append(pd.DataFrame(columns=["JENIS", "TOTAL"]))
            continue
        sub = df[["JENIS", "TOTAL"]].copy()
        sub["TOTAL"] = pd.to_numeric(sub["TOTAL"], errors="coerce").fillna(0)
        sub = sub[sub["TOTAL"] > 0]
        g = sub.groupby("JENIS", as_index=False, dropna=False).agg(TOTAL=("TOTAL", "sum"))
        jenis_frames.append(g)
    ja, jb = jenis_frames
    if ja.empty and jb.empty:
        per_jenis = empty_jenis
    else:
        merged = ja.merge(jb, on="JENIS", how="outer").fillna(0.0)
        merged = merged.rename(columns={"TOTAL_x": "Total A", "TOTAL_y": "Total B"})
        merged["Delta"] = merged["Total B"] - merged["Total A"]
        merged["Delta %"] = [
            _delta_pct(b, a) for a, b in zip(merged["Total A"], merged["Total B"])
        ]
        per_jenis = merged.sort_values("Total B", ascending=False).reset_index(
            drop=True
        )[JENIS_COLS]

    # ---- branch level ----
    if ta.empty and tb.empty:
        branch = empty_branch
    else:
        ga = ta.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
        gb = tb.groupby("NAMA RESTO", as_index=False)["TOTAL"].sum()
        m = ga.merge(gb, on="NAMA RESTO", how="outer").fillna(0.0)
        m = m.rename(columns={"TOTAL_x": "Total A", "TOTAL_y": "Total B"})
        m["Delta"] = m["Total B"] - m["Total A"]
        m["Delta %"] = [_delta_pct(b, a) for a, b in zip(m["Total A"], m["Total B"])]
        m = m.reindex(
            m["Delta"].abs().sort_values(ascending=False).index
        ).head(top_n)
        branch = m.reset_index(drop=True)[BRANCH_COLS]

    # ---- item level ----
    if ta.empty and tb.empty:
        items = empty_items
        new_items = empty_new
        gone_items = empty_gone
    else:
        key = ["NAMA RESTO", "NAMA BARANG"]
        m = ta.merge(tb, on=key, how="outer", suffixes=(" A", " B"))
        # Kolom hasil merge: TOTAL A / TOTAL B (suffix dari kolom TOTAL)
        m = m.rename(columns={"TOTAL A": "Total A", "TOTAL B": "Total B"})
        m[["Total A", "Total B"]] = m[["Total A", "Total B"]].fillna(0.0)
        m["Delta"] = m["Total B"] - m["Total A"]
        m["Delta %"] = [_delta_pct(b, a) for a, b in zip(m["Total A"], m["Total B"])]
        m = m.reindex(
            m["Delta"].abs().sort_values(ascending=False).index
        ).head(top_n)
        items = m.reset_index(drop=True)[ITEM_COLS]
        # Baru = hanya di B (Total A 0 & Total B > 0); Hilang = sebaliknya.
        full = ta.merge(tb, on=key, how="outer", suffixes=(" A", " B"))
        full = full.rename(columns={"TOTAL A": "Total A", "TOTAL B": "Total B"})
        full[["Total A", "Total B"]] = full[["Total A", "Total B"]].fillna(0.0)
        new_items = full[full["Total A"] <= 0][key + ["Total B"]].sort_values(
            "Total B", ascending=False
        ).head(top_n).reset_index(drop=True)[NEW_ITEM_COLS]
        gone_items = full[full["Total B"] <= 0][key + ["Total A"]].sort_values(
            "Total A", ascending=False
        ).head(top_n).reset_index(drop=True)[GONE_ITEM_COLS]

    return {
        "label_a": label_a,
        "label_b": label_b,
        "summary": summary,
        "per_jenis": per_jenis,
        "branch": branch,
        "items": items,
        "new_items": new_items,
        "gone_items": gone_items,
    }
