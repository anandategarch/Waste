"""
charts.py — generator grafik matplotlib (galeri statis + analisa).

Setiap fungsi return Figure yang siap di-embed — embedding dilakukan oleh
ui/widgets.MplCanvas (FigureCanvasQTAgg, PySide6) di dalam ChartCard
(sejak v2.6.0; helper embed FigureCanvasTkAgg lama dihapus di v2.7.0 —
UI Tkinter sudah tidak ada).

NOTE (L14 dependency pin): modul ini membutuhkan matplotlib >= 3.9
(chart_box_total_per_jenis memakai boxplot(tick_labels=...); kwarg
"labels" dihapus di matplotlib 3.9). Pin dicatat di requirements.txt.

Semua figure dibangun langsung dari matplotlib.figure.Figure — tidak ada
pyplot global state (plt hanya dipakai untuk rcParams global).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Callable

# plt hanya dipakai untuk rcParams global, bukan untuk membuat figure
# (semua figure dibangun dari objek Figure murni — aman multi-embed).
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Patch

# v2.3.1 helpers — fix semua UI/UX issues (Pattern A-H)
from .chart_helpers import (
    apply_layout,
    disambiguate_labels,
    fmt_cabang,
    fmt_item,
    fmt_reason,
    place_legend_outside,
    add_ylim_headroom,
    add_xlim_headroom,
    dynamic_figsize,
    adaptive_text_color,
    fmt_number_short,
)

# v2.5.0 — analisa temporal (P1) + money view (P2) sebagai sumber agregat.
# Keduanya modul murni tanpa dependensi balik ke charts.py (bebas siklus).
from . import temporal as _temporal
from . import priority as _priority

# Drill-down click handler: (filter_key, value) -> None — kontrak sama
# dengan dashboard.FilterCallback supaya satu handler dipakai lintas tab.
DrillCallback = Callable[[str, "str | None"], None]

_LOGGER = logging.getLogger("waste_anomaly.charts")


def _dominant_unit_note(df: pd.DataFrame, top: int = 2) -> str:
    """v2.5.1 (MO-M1): catatan satuan dominan untuk chart agregat TOTAL.

    Agregat TOTAL mencampur SATUAN (GR 98,7% + PCS/PACK/ML/... di data
    riil) — 1 PCS ≠ 1 GR. Catatan 'GR 98,7% • PCS 1,0%' di judul membuat
    campuran eksplisit, bukan tersembunyi di label '(qty)'.
    Return '' bila kolom SATUAN tidak ada / kosong (chart tetap jalan).
    """
    if "SATUAN" not in df.columns or "TOTAL" not in df.columns or df.empty:
        return ""
    try:
        total = pd.to_numeric(df["TOTAL"], errors="coerce").fillna(0.0)
        sat = df["SATUAN"].astype(str).str.replace("\xa0", "", regex=False).str.strip()
        sat = sat.where(sat.ne("") & sat.ne("nan"), "(kosong)")
        share = total.groupby(sat).sum().sort_values(ascending=False)
        grand = float(share.sum())
        if grand <= 0 or share.empty:
            return ""
        parts = [f"{u} {v / grand * 100:.1f}%" for u, v in share.head(top).items()]
        return " • ".join(parts)
    except Exception:  # noqa: BLE001 — catatan best-effort
        return ""

# ============================================================
# STYLE
# ============================================================

# Palette tanpa indigo/blue (sesuai panduan UI)
# Amber-700 (bukan amber-500) untuk contrast WCAG AA dengan white text
PALETTE_STATUS = {
    "Prioritas Tinggi": "#dc2626",   # red-600
    "Potensi Anomali": "#ea580c",   # orange-600
    "Perlu Review":    "#b45309",   # amber-700 (was amber-500; kontras lebih baik)
    "Normal":          "#16a34a",   # green-600
}

# Urutan kanonik status (dipakai pie, stacked bar, scatter)
STATUS_ORDER = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]

# M11: marker berbeda per kelas status — encoding redundan untuk colorblind
# (pasangan red-600/green-600 dan orange-600/amber-700 confusable by hue saja).
# Status tak dikenal → marker "v" + PALETTE_NEUTRAL.
STATUS_MARKERS = {
    "Prioritas Tinggi": "D",
    "Potensi Anomali": "s",
    "Perlu Review": "^",
    "Normal": "o",
}

PALETTE_KATEGORI = [
    "#0f766e", "#be185d", "#b45309", "#15803d",
    "#7c2d12", "#475569", "#9333ea", "#0891b2",
    "#ca8a04", "#db2777", "#65a30d", "#4b5563",
]

PALETTE_ACCENT = "#0f766e"   # teal-700 (utama)
PALETTE_SECONDARY = "#be185d" # pink-700
PALETTE_NEUTRAL = "#475569"

# H5: mapping warna JENIS yang stabil — di-export untuk dashboard.py/ui_app.py.
JENIS_COLORS = {
    "WASTE": "#dc2626",    # red-600
    "SUSUT": "#0f766e",    # teal-700
    "TRIAL": "#b45309",    # amber-700
    "LAINNYA": "#64748b",  # slate-500 — bucket "other"
}

# Warna bucket "Lainnya" — kategori/reason di luar kapasitas palette (M5/M6)
COLOR_LAINNYA = JENIS_COLORS["LAINNYA"]

# M1: threshold skor anomali untuk chart_score_per_cabang — nilai FALLBACK.
# Nilai efektif dibaca dari config.json (thresholds.STATUS_PRIORITAS /
# STATUS_POTENSI / STATUS_REVIEW, kini tersedia) via load_config; lihat
# _load_status_thresholds() di bawah.
STATUS_THRESHOLDS = (8, 5, 3)   # (Prioritas, Potensi, Review)

# Cache threshold efektif (dibaca sekali; config jarang berubah saat runtime)
_THRESHOLD_CACHE: tuple[int, int, int] | None = None


def _load_status_thresholds() -> tuple[int, int, int]:
    """Ambil threshold skor (prioritas, potensi, review).

    Sumber: config.json → thresholds.STATUS_PRIORITAS / STATUS_POTENSI /
    STATUS_REVIEW (via utils.load_config). Bila key hilang / config rusak /
    nilai invalid, fallback ke literal STATUS_THRESHOLDS = (8, 5, 3).
    """
    global _THRESHOLD_CACHE
    if _THRESHOLD_CACHE is None:
        pri, pot, rev = STATUS_THRESHOLDS
        try:
            # Lazy import — hindari dependency import-time ke utils
            from .utils import load_config
            th = (load_config() or {}).get("thresholds", {}) or {}
            pri = int(th.get("STATUS_PRIORITAS", pri))
            pot = int(th.get("STATUS_POTENSI", pot))
            rev = int(th.get("STATUS_REVIEW", rev))
        except Exception:
            pass  # best-effort: keep literals (load_config sudah warn-on-fail)
        _THRESHOLD_CACHE = (pri, pot, rev)
    return _THRESHOLD_CACHE


# M6: jumlah maksimum reason yang ditampilkan; sisanya → bucket "Lainnya"
MAX_REASONS = 14

# Styling global matplotlib
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#cbd5e1",
    "axes.labelcolor": "#1e293b",
    "axes.titlecolor": "#0f172a",
    "axes.titleweight": "bold",
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.color": "#475569",
    "ytick.color": "#475569",
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "legend.frameon": False,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "axes.grid": True,
    "grid.color": "#e2e8f0",
    "grid.linewidth": 0.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _restore_legend_title(ax, title: str | None) -> None:
    """Set title on existing legend (place_legend_outside doesn't preserve it).

    NOTE (L3): dashboard.py punya salinan helper ini (file itu di-handle
    agent lain) — jaga keduanya tetap sinkron bila perilaku berubah.
    """
    if not title:
        return
    leg = ax.get_legend()
    if leg is not None:
        leg.set_title(title)


def _empty_figure(msg: str = "Tidak ada data", figsize: tuple = (7, 4.5)) -> Figure:
    """Empty-state figure standar: satu pesan di tengah, axes off."""
    fig = Figure(figsize=figsize, dpi=100)
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, msg, ha="center", va="center",
            color=PALETTE_NEUTRAL, fontsize=10)
    ax.set_axis_off()
    return fig


def _connect_click(fig: Figure, handler) -> None:
    """Connect 'button_press_event' + simpan cid di fig._waste_cids (fix M9).

    Kontrak identik dengan dashboard._connect_click — teardown UI
    (base.py _dispose_chart_registry) memutus semua listener via
    fig._waste_cids, jadi listener tidak bocor saat chart di-swap.
    """
    cid = fig.canvas.mpl_connect("button_press_event", handler)
    cids = getattr(fig, "_waste_cids", None)
    if cids is None:
        cids = []
        fig._waste_cids = cids
    cids.append(cid)


def _wire_patch_click(fig: Figure, patches, labels, on_click, key: str) -> None:
    """Wire klik pada patch (bar/wedge) → on_click(key, label ASLI).

    P8 v2.5.0: drill-down dari chart statis (tab Visualisasi). Hit-test
    memakai patch.contains(event) (koordinat display). Nilai yang dikirim
    adalah nilai kolom ASLI — bukan label truncation di sumbu — supaya
    cocok dengan filter data. Klik area kosong/legend → diabaikan.
    """
    pairs = list(zip(patches, labels))

    def _handler(event):
        for patch, label in pairs:
            try:
                # contains() return TUPLE (bool, dict) — tuple non-kosong
                # selalu truthy, jadi WAJIB unpack [0] (bug dashboard tidak
                # ada karena sudah pakai [0]; ini menjaga konsistensi).
                if patch.contains(event)[0]:
                    on_click(key, str(label))
                    return
            except Exception:  # noqa: BLE001 — event aneh diabaikan saja
                # v2.5.1 (DD-M5): tetap tercatat — dulu ditelan senyap,
                # klik mati tanpa jejak log sama sekali.
                _LOGGER.warning(
                    "_wire_patch_click key=%s label=%r gagal", key, label,
                    exc_info=True,
                )
                return

    _connect_click(fig, _handler)


# ============================================================
# CHART 1 — PIE: Distribusi Status Anomali
# ============================================================

def chart_status_pie(df: pd.DataFrame, on_click: DrillCallback | None = None) -> Figure:
    """Pie chart distribusi ANOMALY STATUS.

    H3 fix: status di luar 4 kanonik TETAP ditampilkan sebagai slice berwarna
    netral + entri legend. Sebelumnya reindex() membuang status tak dikenal
    secara diam-diam — input [Normal, UNKNOWN, UNKNOWN] salah tampil
    "Normal 100%".
    P8 (v2.5.0): on_click != None → klik wedge mem-filter status (drill-down
    lintas-tab; kontrak (filter_key, value) sama dengan dashboard).
    """
    if "ANOMALY STATUS" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(6, 4.2))

    counts = df["ANOMALY STATUS"].value_counts()
    # Urutan tetap: Prioritas Tinggi > Potensi Anomali > Perlu Review > Normal,
    # lalu status tak dikenal (dijaga, tidak dibuang).
    known = [s for s in STATUS_ORDER if s in counts.index]
    unknown = [s for s in counts.index if s not in STATUS_ORDER]
    counts = counts.reindex(known + unknown)
    if counts.empty:
        return _empty_figure("Tidak ada data", figsize=(6, 4.2))
    colors = [PALETTE_STATUS.get(s, PALETTE_NEUTRAL) for s in counts.index]

    fig = Figure(figsize=(6, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    # Pattern D: pctdistance closer to center, labeldistance slightly outside
    # Pattern C: count moved to legend (less text inside the pie)
    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=counts.index,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        pctdistance=0.72,
        labeldistance=1.08,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9, color="#1e293b", fontweight="bold"),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
    ax.set_title("Distribusi Status Anomali", pad=12)
    # Pattern B: legend outside with counts
    ax.legend(
        wedges,
        [f"{s} ({c})" for s, c in zip(counts.index, counts.values)],
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        fontsize=8,
        frameon=True,
        edgecolor="#cbd5e1",
        facecolor="white",
        framealpha=0.95,
    )
    # Pie charts: keep tight_layout (rule 6) + manual margins for legend
    fig.tight_layout(pad=2.0)
    fig.subplots_adjust(top=0.92, right=0.70)
    if on_click is not None:
        _wire_patch_click(fig, wedges, list(counts.index), on_click, "status")
    return fig


# ============================================================
# CHART 2 — BAR: Waste Total per Cabang
# ============================================================

def chart_waste_per_cabang(df: pd.DataFrame, on_click: DrillCallback | None = None) -> Figure:
    """Bar chart total waste per NAMA RESTO.

    C1 fix: bar di-plot posisional (np.arange + set_xticklabels) — label
    display hasil truncation fmt_cabang yang duplikat tidak lagi menumpuk
    beberapa bar pada satu posisi x (dulu bar saling menimpa diam-diam).
    Label duplikat juga diberi suffix "#k" agar tetap bisa dibedakan.
    P8 (v2.5.0): on_click != None → klik bar mem-filter cabang.
    """
    # Pattern G: wider figure for many cabangs
    n_cabangs = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 5
    fig_w = max(7.0, min(14.0, 0.5 * n_cabangs + 3))
    fig = Figure(figsize=(fig_w, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=True)["TOTAL"].sum().sort_values(ascending=False)
    # v2.5.1 (DD-M5): dropna=True — grup NaN ('nan' via astype-str di label)
    # tidak bisa difilter (equality vs NaN selalu False) → dead-end klik.
    # Pattern C: abbreviate cabang codes on x-axis + disambiguate collisions
    cabang_labels = disambiguate_labels([fmt_cabang(c) for c in g.index.astype(str)])
    x = np.arange(len(g))
    bars = ax.bar(x, g.values, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(cabang_labels)
    # Pattern D: data labels using fmt_number_short, rotate 90° if >10 bars
    # L6: skip label untuk bar nol (konsisten di semua bar chart)
    label_rotation = 90 if len(bars) > 10 else 0
    for bar, val in zip(bars, g.values):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                fmt_number_short(val), ha="center", va="bottom",
                fontsize=7, fontweight="bold", color="#0f172a",
                rotation=label_rotation)
    ax.set_title("Total Waste per Cabang", pad=12)
    ax.set_ylabel("Total Waste (qty)")
    ax.set_xlabel("Cabang")
    # Pattern D: add 20% headroom so rotated data labels don't clip
    add_ylim_headroom(ax, factor=1.20)
    # Pattern A + E: margins + rotation
    apply_layout(fig, ax, rotate_x=True, bottom_pad=0.22)
    if on_click is not None:
        # Label ASLI (bukan truncation) → filter cocok dengan data.
        _wire_patch_click(fig, bars, list(g.index.astype(str)), on_click, "cabang")
    return fig


# ============================================================
# CHART 3 — HORIZONTAL BAR: Top 10 Items
# ============================================================

def chart_top_items(df: pd.DataFrame, top_n: int = 10,
                    on_click: DrillCallback | None = None) -> Figure:
    """Horizontal bar chart top N item by TOTAL waste.

    M4 fix: tinggi figure dihitung dari jumlah item HASIL agregasi (len(g)),
    bukan top_n yang diminta — dataset kecil tidak lagi mendapat figure
    7-inch yang setengah kosong.
    C1 fix: barh posisional — label ter-wrap yang identik tidak menimpa bar.
    P8 (v2.5.0): on_click != None → klik bar mem-filter item.
    """
    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(7.0, 4.0))

    g = (df.groupby("NAMA BARANG", dropna=True)["TOTAL"].sum()
         .sort_values(ascending=True).tail(top_n))
    # v2.5.1 (DD-M5): dropna=True — grup NaN tidak bisa difilter (dead-end klik).
    if g.empty:
        return _empty_figure("Tidak ada data", figsize=(7.0, 4.0))

    # Pattern G: dynamic figure height based on ACTUAL item count (M4)
    fig_w, fig_h = dynamic_figsize(len(g), base_w=7.0, per_item_h=0.4, min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)

    # Pattern C: wrap long item names on y-axis + disambiguate collisions
    item_labels = disambiguate_labels([fmt_item(name) for name in g.index.astype(str)])
    y = np.arange(len(g))
    bars = ax.barh(y, g.values, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(item_labels)
    # Pattern D: data labels with short format (L6: skip zero bars)
    for bar, val in zip(bars, g.values):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {fmt_number_short(val)}", ha="left", va="center",
                fontsize=8, fontweight="bold", color="#0f172a")
    ax.set_title(f"Top {len(g)} Item dengan Waste Tertinggi", pad=12)
    ax.set_xlabel("Total Waste (qty)")
    ax.set_ylabel("")
    # Pattern D: add headroom for data labels
    add_xlim_headroom(ax, factor=1.10, side="right")
    # Pattern A: more left padding for wrapped multi-line item labels
    apply_layout(fig, ax, left_pad=0.30, bottom_pad=0.12)
    if on_click is not None:
        _wire_patch_click(fig, bars, list(g.index.astype(str)), on_click, "item")
    return fig


# ============================================================
# CHART 4 — STACKED BAR: Anomali Status per Cabang
# ============================================================

def chart_status_per_cabang(df: pd.DataFrame) -> Figure:
    """Stacked bar: distribusi status anomali per cabang.

    C3 fix: kolom pivot difilter ke urutan kanonik DULU, lalu status tak
    dikenal DITAMBAHKAN kembali (warna PALETTE_NEUTRAL) — sebelumnya status
    unknown dibuang diam-diam; input all-unknown → "TypeError: no numeric
    data to plot". Kolom kosong total → empty-state "Tidak ada data".
    M11: edge gelap tipis antar segmen (boundary luminance untuk pasangan
    warna red-600/orange-600/amber-700/green-600 yang confusable).
    """
    if "NAMA RESTO" not in df.columns or "ANOMALY STATUS" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(7, 4.5))

    pivot = pd.crosstab(df["NAMA RESTO"], df["ANOMALY STATUS"])
    # C3: canonical order first, unknown statuses appended (never dropped)
    cols = [c for c in STATUS_ORDER if c in pivot.columns] + \
           [c for c in pivot.columns if c not in STATUS_ORDER]
    if pivot.empty or not cols:
        return _empty_figure("Tidak ada data", figsize=(7, 4.5))
    pivot = pivot[cols]
    colors = [PALETTE_STATUS.get(c, PALETTE_NEUTRAL) for c in cols]

    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    pivot.plot(kind="bar", stacked=True, ax=ax, color=colors,
               edgecolor="#1e293b", linewidth=0.5)
    # Pattern C: abbreviate cabang codes (+ disambiguate collisions)
    ax.set_xticklabels(disambiguate_labels([fmt_cabang(str(idx)) for idx in pivot.index]))
    ax.set_title("Distribusi Status Anomali per Cabang", pad=12)
    ax.set_ylabel("Jumlah Baris")
    ax.set_xlabel("Cabang")
    ax.legend(title="Status")
    # Pattern D: headroom for stacked totals
    add_ylim_headroom(ax)
    # Pattern A + B + E: margins, legend outside, rotation
    apply_layout(fig, ax, rotate_x=True, legend_outside=True, bottom_pad=0.22, right_pad=0.75)
    # Restore legend title (place_legend_outside doesn't preserve it)
    _restore_legend_title(ax, "Status")
    return fig


# ============================================================
# CHART 5 — PARETO: Alasan (KETERANGAN)
# ============================================================

def chart_pareto_keterangan(df: pd.DataFrame, on_click: DrillCallback | None = None) -> Figure:
    """Pareto chart: bar TOTAL per KETERANGAN + cumulative line.

    M3 fix: ax2 = ax.twinx() dibuat SETELAH empty-data guard — sebelumnya
    dibuat sebelum guard, sehingga early-return menyisakan y-axis kedua
    (orphan) yang tetap terlihat di figure empty-state.
    P8 (v2.5.0): on_click != None → klik bar mem-filter KETERANGAN.
    """
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig

    g = df.groupby("KETERANGAN", dropna=True)["TOTAL"].sum().sort_values(ascending=False)
    # v2.5.1 (DD-M5): dropna=True — grup NaN tidak bisa difilter (dead-end klik).
    if g.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig
    cum = g.cumsum() / g.sum() * 100 if g.sum() > 0 else g * 0

    bars = ax.bar(range(len(g)), g.values, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    ax.set_xticks(range(len(g)))
    # Pattern C: wrap long KETERANGAN reasons (+ disambiguate collisions)
    ax.set_xticklabels(disambiguate_labels([fmt_reason(str(k)) for k in g.index]))
    ax.set_ylabel("Total Waste (qty)")
    ax.set_title("Pareto: Kontribusi Waste per KETERANGAN", pad=12)

    # Cumulative line (twin axis) — dibuat setelah semua guard (M3)
    ax2 = ax.twinx()
    ax2.plot(range(len(g)), cum.values, color=PALETTE_SECONDARY, marker="o", linewidth=2, markersize=5)
    # Pattern A: labelpad to give ax2.ylabel breathing room
    ax2.set_ylabel("Cumulative %", color=PALETTE_SECONDARY, labelpad=12)
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis="y", colors=PALETTE_SECONDARY, labelsize=8)
    ax2.axhline(80, color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.text(len(g) - 1, 82, "80%", ha="right", fontsize=8, color="#94a3b8")

    # Label di atas bar (Pattern D: short format + headroom; L6: skip bar nol)
    for i, v in enumerate(g.values):
        if v == 0 or pd.isna(v):
            continue
        ax.text(i, v, fmt_number_short(v), ha="center", va="bottom",
                fontsize=7, color="#0f172a")

    add_ylim_headroom(ax)
    # Pattern A + E: rotation 30 (less than 45 because labels are wrapped to 2 lines)
    apply_layout(fig, ax, rotate_x=True, rotation=30, bottom_pad=0.20)
    if on_click is not None:
        _wire_patch_click(fig, bars, list(g.index.astype(str)), on_click, "keterangan")
    return fig


# ============================================================
# CHART 6 — HEATMAP: Waste per Cabang × Item
# ============================================================

def chart_heatmap_cabang_item(df: pd.DataFrame) -> Figure:
    """Heatmap matrix Cabang × Item, value = TOTAL waste.

    M2 fix: grid dimatikan untuk axes image (rcParams global axes.grid:True
    menggambar gridline DI ATAS imshow); colorbar dibuat dengan fraction/pad
    compact SETELAH layout final, dan grid colorbar juga dimatikan.
    M7 fix: kolom (cabang) dibatasi top-20 by total waste selain cap baris
    (top-30 item); truncasi dicatat di judul ("+N cabang lain").
    L4: fontsize anotasi sel dinaikkan 6 → 8 (minimum Pattern H modul).
    """
    # Validate input first (so we can size the figure dynamically based on data)
    if "NAMA RESTO" not in df.columns or "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(8, 5))

    pivot = df.pivot_table(
        index="NAMA BARANG", columns="NAMA RESTO",
        values="TOTAL", aggfunc="sum", fill_value=0,
    )
    if pivot.empty:
        return _empty_figure("Tidak ada data", figsize=(8, 5))

    # Urutkan item by total desc + cap rows top-30 (Pattern G)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
    max_items, max_cabangs = 30, 20
    n_items_hidden = max(0, len(pivot) - max_items)
    pivot = pivot.head(max_items)
    # M7: cap columns too — top cabangs by total waste
    col_order = pivot.sum(axis=0).sort_values(ascending=False).index
    n_cabangs_hidden = max(0, len(col_order) - max_cabangs)
    pivot = pivot[col_order[:max_cabangs]]
    n_items = len(pivot)
    n_cols = len(pivot.columns)

    title = "Heatmap Waste per Cabang × Item"
    hidden_notes = []
    if n_items_hidden:
        hidden_notes.append(f"+{n_items_hidden} item lain")
    if n_cabangs_hidden:
        hidden_notes.append(f"+{n_cabangs_hidden} cabang lain")
    if hidden_notes:
        title += " (" + ", ".join(hidden_notes) + ")"

    # Pattern G: dynamic figsize based on items/columns shown
    base_w = max(10.0, min(16.0, 0.5 * n_cols + 2))
    fig_w, fig_h = dynamic_figsize(n_items, base_w=base_w, per_item_h=0.45, min_h=6.0, max_h=16)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)

    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd")
    # M2: global axes.grid:True → gridlines over the image; turn it off
    ax.grid(False)
    ax.set_xticks(range(n_cols))
    # Pattern C: abbreviate cabang codes
    ax.set_xticklabels([fmt_cabang(str(c)) for c in pivot.columns])
    ax.set_yticks(range(n_items))
    # Pattern C: wrap long item names — use shorter width for heatmap (15 chars, 2 lines max)
    ax.set_yticklabels([fmt_item(str(name), width=15, max_lines=2) for name in pivot.index])
    ax.set_title(title, pad=12)
    ax.set_xlabel("Cabang")
    ax.set_ylabel("Item")

    # Pattern F: adaptive text color (white on dark cells, black on light)
    # Only annotate TOP 50 cells by value to avoid clutter
    max_val = float(pivot.values.max()) if pivot.values.size > 0 else 0.0
    text_threshold = max_val * 0.6  # white text above 60% of max
    # Flatten values, find top 50 cells to annotate
    flat_vals = []
    for i in range(len(pivot.index)):
        for j in range(n_cols):
            v = pivot.values[i, j]
            if v > 0:
                flat_vals.append((v, i, j))
    flat_vals.sort(reverse=True)
    cells_to_annotate = set((i, j) for _, i, j in flat_vals[:50])
    for i, j in cells_to_annotate:
        v = pivot.values[i, j]
        color = adaptive_text_color(v, text_threshold, max_val)
        ax.text(j, i, fmt_number_short(v, decimals=0), ha="center", va="center",
                fontsize=8, color=color, fontweight="bold")

    # M2: layout final dulu, lalu colorbar compact (fraction/pad) — dibuat
    # paling akhir sehingga shrink yang ditimbulkannya bersifat final dan
    # kecil; tidak ada subplots_adjust usang setelahnya. Grid colorbar off.
    apply_layout(fig, ax, rotate_x=True, rotation=90, bottom_pad=0.20,
                 left_pad=0.28, right_pad=0.92, x_fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03,
                        label="Total Waste (qty)")
    cbar.ax.grid(False)
    return fig


# ============================================================
# CHART 7 — BAR: Anomali Reasons Frequency
# ============================================================

def chart_reasons_frequency(df: pd.DataFrame) -> Figure:
    """Bar chart frekuensi ANOMALY REASONS (split by ' | ').

    M6 fix: dibatasi top MAX_REASONS (14); sisanya diagregasi ke bucket
    "Lainnya" (sum, bar warna netral) — ratusan reason berbeda dulu
    menghasilkan figure 60-inch yang tidak terbaca.
    C1 fix: barh posisional — label ter-wrap identik tidak menimpa bar.
    """
    if "ANOMALY REASONS" not in df.columns or df.empty:
        return _empty_figure("Tidak ada alasan anomali terdeteksi", figsize=(7, 4.5))

    counter = Counter()
    for reasons in df["ANOMALY REASONS"].dropna():
        if reasons:
            for r in str(reasons).split(" | "):
                r = r.strip()
                if r:
                    counter[r] += 1

    if not counter:
        return _empty_figure("Tidak ada alasan anomali terdeteksi", figsize=(7, 4.5))

    items = sorted(counter.items(), key=lambda x: x[1])   # ascending
    # M6: cap at top MAX_REASONS + "Lainnya" bucket (sum of the tail)
    n_hidden = 0
    if len(items) > MAX_REASONS:
        keep = items[-(MAX_REASONS - 1):]
        n_hidden = len(items) - len(keep)
        lainnya_total = sum(v for _, v in items[:n_hidden])
        items = [("Lainnya", lainnya_total)] + keep

    # Pattern C: wrap reason text on y-axis (+ disambiguate collisions)
    labels = [fmt_reason(x[0]) for x in items]
    values = [x[1] for x in items]
    # Pattern G: dynamic figsize based on number of reasons shown
    fig_w, fig_h = dynamic_figsize(len(items), base_w=7.0, per_item_h=0.4, min_h=4.0, max_h=14.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)
    y = np.arange(len(items))
    bar_colors = [COLOR_LAINNYA if lab == "Lainnya" else PALETTE_ACCENT for lab in labels]
    bars = ax.barh(y, values, color=bar_colors, edgecolor="white", linewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    for bar, val in zip(bars, values):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {val}", ha="left", va="center", fontsize=8,
                fontweight="bold", color="#0f172a")
    title = "Frekuensi Penyebab Anomali"
    if n_hidden:
        title += f" (top {len(items) - 1} + {n_hidden} lainnya)"
    ax.set_title(title, pad=12)
    ax.set_xlabel("Jumlah Baris")
    # Pattern D: headroom for data labels
    add_xlim_headroom(ax, factor=1.10, side="right")
    # Pattern A: extra left padding for wrapped reason labels
    apply_layout(fig, ax, left_pad=0.30, bottom_pad=0.12)
    return fig


# ============================================================
# CHART 8 — SCATTER: MAX vs TOTAL (outlier detection)
# ============================================================

def chart_scatter_max_total(df: pd.DataFrame) -> Figure:
    """Scatter plot MAX vs TOTAL, warna per ANOMALY STATUS.

    M11 fix: setiap kelas status mendapat marker berbeda (o/s/^/D) sebagai
    encoding redundan — pasangan warna red-600/green-600 dan
    orange-600/amber-700 confusable untuk colorblind bila hue saja.
    Status tak dikenal ikut diplot (marker "v", PALETTE_NEUTRAL).
    """
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "MAX" not in df.columns or "TOTAL" not in df.columns or "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig

    # Plot per status supaya legend muncul.
    # Urutan: kanonik dulu, lalu status tak dikenal dari data (tidak dibuang).
    present = list(pd.unique(df["ANOMALY STATUS"].dropna()))
    status_list = [s for s in STATUS_ORDER if s in present] + \
                  [s for s in present if s not in STATUS_ORDER]
    plotted = False
    for status in status_list:
        sub = df[df["ANOMALY STATUS"] == status]
        if sub.empty:
            continue
        ax.scatter(sub["TOTAL"], sub["MAX"],
                   c=PALETTE_STATUS.get(status, PALETTE_NEUTRAL),
                   label=str(status),
                   marker=STATUS_MARKERS.get(status, "v"),
                   alpha=0.7, edgecolors="white", linewidth=0.5, s=60)
        plotted = True

    if not plotted:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig

    # Garis identitas (MAX = TOTAL) — single-day dominance
    max_val = max(df["TOTAL"].max(), df["MAX"].max())
    if pd.isna(max_val) or max_val <= 0:
        max_xy = 1.0
    else:
        max_xy = float(max_val) * 1.05
    ax.plot([0, max_xy], [0, max_xy], "--", color="#94a3b8", linewidth=0.8, alpha=0.7,
            label="MAX = TOTAL (single-day)")

    ax.set_title("Scatter: MAX vs TOTAL — Deteksi Outlier", pad=12)
    ax.set_xlabel("TOTAL Waste (qty)")
    ax.set_ylabel("MAX Waste (qty, single day)")
    # Pattern B: legend outside, lower-right (so it doesn't cover high-value points)
    place_legend_outside(ax, loc="lower right", bbox_to_anchor=(1.02, 0.0))
    apply_layout(fig, ax, left_pad=0.16, bottom_pad=0.14, right_pad=0.75)
    return fig


# ============================================================
# CHART 9 — BOX PLOT: Distribusi TOTAL per JENIS
# ============================================================

def chart_box_total_per_jenis(df: pd.DataFrame) -> Figure:
    """Box plot distribusi TOTAL per JENIS.

    M12 fix: kategori JENIS diderivasi dari data (kanonik WASTE/SUSUT/TRIAL
    dulu, lalu JENIS lain yang benar-benar ada) — bukan hardcoded 3 item.
    L14: memakai boxplot(tick_labels=...) → butuh matplotlib >= 3.9.
    Warna box pakai JENIS_COLORS (H5); JENIS ekstra fallback ke
    PALETTE_KATEGORI lalu netral — warna tidak pernah dipakai ulang (M5).
    """
    if "JENIS" not in df.columns or "TOTAL" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(6, 4.5))

    present = [str(j) for j in df["JENIS"].dropna().unique()]
    canonical = ["WASTE", "SUSUT", "TRIAL"]
    # M12: canonical order first, then extra JENIS actually present in data
    jenis_order = [j for j in canonical if j in present] + \
                  sorted(j for j in present if j not in canonical)

    data = []
    labels = []
    for jenis in jenis_order:
        sub = df[df["JENIS"] == jenis]["TOTAL"].dropna()
        if not sub.empty:
            data.append(sub.values)
            labels.append(jenis)

    if not data:
        return _empty_figure("Tidak ada data", figsize=(6, 4.5))

    fig = Figure(figsize=(6, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.5,
                    medianprops=dict(color="#0f172a", linewidth=2))
    # H5/M5: stable JENIS_COLORS mapping; extras cycle the kategori palette
    extra = [c for c in PALETTE_KATEGORI if c not in set(JENIS_COLORS.values())]
    box_colors = []
    for i, j in enumerate(labels):
        if j in JENIS_COLORS:
            box_colors.append(JENIS_COLORS[j])
        elif extra:
            box_colors.append(extra[i % len(extra)])
        else:
            box_colors.append(PALETTE_NEUTRAL)
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
        patch.set_edgecolor("white")
        patch.set_linewidth(1.5)

    ax.set_title("Distribusi TOTAL Waste per JENIS", pad=12)
    ax.set_ylabel("TOTAL Waste (qty)")
    ax.set_xlabel("JENIS")
    apply_layout(fig, ax, left_pad=0.16, bottom_pad=0.15, top_pad=0.88)
    return fig


# ============================================================
# CHART 10 — BAR: Anomali Score per Cabang (avg + max)
# ============================================================

def chart_score_per_cabang(df: pd.DataFrame) -> Figure:
    """Grouped bar: avg & max ANOMALY SCORE per cabang.

    M1 fix: threshold line (config: thresholds.STATUS_PRIORITAS /
    STATUS_POTENSI / STATUS_REVIEW, fallback 8/5/3) kini punya label
    ("≥ 8 Prioritas", "≥ 5 Potensi", "≥ 3 Review") sehingga muncul di
    legend — sebelumnya magic number tanpa penjelasan.
    """
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "ANOMALY SCORE" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center",
                color=PALETTE_NEUTRAL, fontsize=10)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=False)["ANOMALY SCORE"].agg(["mean", "max"]).reset_index()
    g = g.sort_values("max", ascending=False)
    x = np.arange(len(g))
    w = 0.35
    b1 = ax.bar(x - w/2, g["mean"], w, label="Rata-rata", color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, g["max"], w, label="Max", color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    # Pattern C: abbreviate cabang codes (+ disambiguate collisions)
    ax.set_xticklabels(disambiguate_labels([fmt_cabang(str(c)) for c in g["NAMA RESTO"]]))
    ax.set_title("Anomali Score per Cabang (Avg vs Max)", pad=12)
    ax.set_ylabel("Anomali Score")
    ax.set_xlabel("Cabang")
    # Threshold lines — M1: labeled so they show up in the legend.
    # Values from config (STATUS_PRIORITAS/POTENSI/REVIEW), fallback 8/5/3.
    t_pri, t_pot, t_rev = _load_status_thresholds()
    ax.axhline(t_pri, color=PALETTE_STATUS["Prioritas Tinggi"], linestyle="--",
               linewidth=0.8, alpha=0.5, label=f"≥ {t_pri} Prioritas")
    ax.axhline(t_pot, color=PALETTE_STATUS["Potensi Anomali"], linestyle="--",
               linewidth=0.8, alpha=0.5, label=f"≥ {t_pot} Potensi")
    ax.axhline(t_rev, color=PALETTE_STATUS["Perlu Review"], linestyle="--",
               linewidth=0.8, alpha=0.5, label=f"≥ {t_rev} Review")
    # Pattern D: headroom for tallest bar (Max)
    add_ylim_headroom(ax)
    # Pattern A + B + E: margins, legend outside, rotation.
    # Legend dibuat di sini (place_legend_outside) — mencakup bar + threshold.
    apply_layout(fig, ax, rotate_x=True, legend_outside=True, bottom_pad=0.22, right_pad=0.75)
    return fig


# ============================================================
# CHART 11 — STACKED BAR: KATEGORI ANOMALI per Cabang
# ============================================================

def chart_kategori_per_cabang(df: pd.DataFrame) -> Figure:
    """Stacked bar KATEGORI ANOMALI per cabang.

    M5 fix: bila jumlah kategori melebihi kapasitas PALETTE_KATEGORI (12),
    hanya top-(N-1) by total yang digambar individual; sisanya diagregasi
    ke segmen "Lainnya" (warna netral) — warna tidak pernah dipakai ulang
    secara diam-diam.
    M11: edge gelap tipis antar segmen (redundant boundary).
    """
    if "NAMA RESTO" not in df.columns or "KATEGORI ANOMALI" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(7, 4.5))

    pivot = pd.crosstab(df["NAMA RESTO"], df["KATEGORI ANOMALI"])
    if pivot.empty:
        return _empty_figure("Tidak ada data", figsize=(7, 4.5))

    # M5: collapse tail categories into "Lainnya" beyond palette capacity
    max_cols = len(PALETTE_KATEGORI)
    collapsed = False
    if pivot.shape[1] > max_cols:
        collapsed = True
        bucket = "Lainnya"
        totals = pivot.sum(axis=0).sort_values(ascending=False)
        keep = [c for c in totals.index[:max_cols - 1]]
        if bucket in pivot.columns and bucket not in keep:
            # kategori asli bernama "Lainnya" ada tapi tidak masuk top — sisakan
            # slot agar bucket tetap satu kolom (tidak dobel)
            keep = keep[:max_cols - 2]
        rest = [c for c in pivot.columns if c not in keep]
        out = pivot[keep].copy()
        if rest:
            bucket_vals = pivot[rest].sum(axis=1)
            if bucket in out.columns:
                out[bucket] = out[bucket] + bucket_vals
            else:
                out[bucket] = bucket_vals
        pivot = out

    cols = list(pivot.columns)
    colors = [
        COLOR_LAINNYA if c == "Lainnya"
        else (PALETTE_KATEGORI[i] if i < len(PALETTE_KATEGORI) else COLOR_LAINNYA)
        for i, c in enumerate(cols)
    ]

    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    pivot.plot(kind="bar", stacked=True, ax=ax, color=colors,
               edgecolor="#1e293b", linewidth=0.5)
    # Pattern C: abbreviate cabang codes (+ disambiguate collisions)
    ax.set_xticklabels(disambiguate_labels([fmt_cabang(str(idx)) for idx in pivot.index]))
    title = "Kategori Anomali per Cabang"
    if collapsed:
        title += " (kategori lain digabung ke 'Lainnya')"
    ax.set_title(title, pad=12)
    ax.set_ylabel("Jumlah Baris")
    ax.set_xlabel("Cabang")
    ax.legend(title="Kategori")
    # Pattern A + B + E: margins, legend outside, rotation
    apply_layout(fig, ax, rotate_x=True, legend_outside=True, bottom_pad=0.22, right_pad=0.75)
    # Restore legend title
    _restore_legend_title(ax, "Kategori")
    return fig


# ============================================================
# CHART 12 — DONUT: Share JENIS (WASTE/SUSUT/TRIAL)
# ============================================================

def chart_jenis_donut(df: pd.DataFrame) -> Figure:
    """Donut chart distribusi JENIS (count baris).

    H5 fix: warna slice memakai mapping JENIS_COLORS (stabil, di-export
    untuk dashboard/UI) — bukan potongan PALETTE_KATEGORI posisional.
    M5 (safety): bila JENIS unik melebihi kapasitas palette, slice ekstra
    diagregasi ke bucket "Lainnya".
    """
    if "JENIS" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(5, 4.2))

    counts = df["JENIS"].value_counts()
    # M5 (safety): collapse beyond palette capacity into a "Lainnya" slice
    max_slices = len(PALETTE_KATEGORI)
    if len(counts) > max_slices:
        keep = counts.iloc[:max_slices - 1]
        rest_sum = int(counts.iloc[max_slices - 1:].sum())
        counts = pd.concat([keep, pd.Series({"Lainnya": rest_sum})])
    if counts.empty:
        return _empty_figure("Tidak ada data", figsize=(5, 4.2))

    # H5: stable JENIS_COLORS; unknown JENIS fall back to kategori palette,
    # then neutral — never silently reusing colors
    extra = [c for c in PALETTE_KATEGORI if c not in set(JENIS_COLORS.values())]
    colors = []
    for i, j in enumerate(counts.index):
        if j == "Lainnya":
            colors.append(JENIS_COLORS["LAINNYA"])
        elif j in JENIS_COLORS:
            colors.append(JENIS_COLORS[j])
        elif extra:
            colors.append(extra[i % len(extra)])
        else:
            colors.append(PALETTE_NEUTRAL)

    fig = Figure(figsize=(5, 4.2), dpi=100)
    ax = fig.add_subplot(111)
    # Pattern D + C: closer pct, count moved to legend
    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=counts.index.astype(str),
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        pctdistance=0.72,
        labeldistance=1.08,
        wedgeprops=dict(width=0.4, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9, color="#1e293b", fontweight="bold"),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
    ax.set_title("Distribusi JENIS Waste", pad=12)
    # Pattern B: legend outside with counts
    ax.legend(
        wedges,
        [f"{s} ({c})" for s, c in zip(counts.index, counts.values)],
        loc="center left",
        bbox_to_anchor=(0.92, 0.5),
        fontsize=8,
        frameon=True,
        edgecolor="#cbd5e1",
        facecolor="white",
        framealpha=0.95,
    )
    # Donut: keep tight_layout (rule 6) + manual margins for legend
    fig.tight_layout(pad=2.0)
    fig.subplots_adjust(top=0.92, right=0.70)
    return fig


# ============================================================
# CHART 13 (v2.5.0 P1) — BAR: Waste per Hari + highlight hari peak
# ============================================================

def chart_waste_per_day(df: pd.DataFrame, key_akhir: int | None = None) -> Figure:
    """Bar chart total waste per hari 1..N; hari di kelas peak mingguan
    di-highlight merah (P1 — analisa temporal).

    Sumber: temporal.waste_per_day + temporal.weekday_effect. Judul mencatat
    efek peak (mis. \"+35% di hari 5,6,12,13,...\") supaya pola mingguan
    terlihat tanpa chart terpisah.
    """
    per_day = _temporal.waste_per_day(df, key_akhir=key_akhir)
    if per_day.empty:
        return _empty_figure("Tidak ada data", figsize=(9, 4.5))

    effect = _temporal.weekday_effect(df, key_akhir=key_akhir)
    peak = effect.get("peak_classes") or ()

    n = len(per_day)
    fig_w = max(8.0, min(14.0, 0.35 * n + 2))
    fig = Figure(figsize=(fig_w, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    x = np.arange(n)
    colors = [
        "#dc2626" if int(d) % 7 in peak else PALETTE_ACCENT
        for d in per_day["day"]
    ]
    bars = ax.bar(x, per_day["total"], color=colors,
                  edgecolor="white", linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([str(d) for d in per_day["day"]])
    for bar, val in zip(bars, per_day["total"]):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                fmt_number_short(val), ha="center", va="bottom",
                fontsize=6, color="#0f172a", rotation=90)

    title = "Total Waste per Hari (bulan)"
    # v2.5.1 (MO-M1): satuan dominan eksplisit — agregat lintas satuan
    # hanya indikatif; tanpa ini label '(qty)' menyembunyikan campuran.
    unit_note = _dominant_unit_note(df)
    if unit_note:
        title += f"  [{unit_note}]"
    if peak:
        ratio = effect.get("ratio")
        days_str = ", ".join(
            str(int(d)) for d in per_day["day"] if int(d) % 7 in peak
        )
        if ratio and ratio == ratio:  # NaN-safe
            title += f" — hari peak +{ratio * 100 - 100:.0f}% ({days_str})"
        else:
            title += f" — hari peak: {days_str}"
    ax.set_title(title, pad=12)
    ax.set_ylabel("Total Waste (qty)")
    ax.set_xlabel("Hari (tanggal dalam bulan)")
    add_ylim_headroom(ax, factor=1.22)
    apply_layout(fig, ax, bottom_pad=0.14)
    return fig


# ============================================================
# CHART 14 (v2.5.0 P1) — BAR: Efek kelas hari (mod 7)
# ============================================================

def chart_weekday_effect(df: pd.DataFrame, key_akhir: int | None = None) -> Figure:
    """Bar mean-per-baris-aktif per kelas hari (day % 7) + garis rata-rata
    keseluruhan (P1). Dua kelas peak diberi warna aksen berbeda."""
    pat = _temporal.weekday_pattern(df, key_akhir=key_akhir)
    if pat.empty:
        return _empty_figure("Tidak ada data", figsize=(7, 4.5))
    effect = _temporal.weekday_effect(df, key_akhir=key_akhir)
    peak = effect.get("peak_classes") or ()

    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    x = np.arange(len(pat))
    colors = [
        "#dc2626" if int(m) in peak else PALETTE_ACCENT
        for m in pat["mod_class"]
    ]
    bars = ax.bar(x, pat["mean_per_active"], color=colors,
                  edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    # v2.6.0: label hari dipadatkan ("1, 8, 15, 22, 29" → "1,8,15,22,29") —
    # 7 kelas × label panjang saling tumpang tindih pada lebar desain 7 in.
    ax.set_xticklabels([
        f"mod {int(m)}\n({str(days).replace(' ', '')})"
        for m, days in zip(pat["mod_class"], pat["days"])
    ])
    for bar, val in zip(bars, pat["mean_per_active"]):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{val:.0f}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="#0f172a")
    overall = (
        pat["total"].sum() / pat["active_rows"].sum()
        if pat["active_rows"].sum() > 0 else 0.0
    )
    ax.axhline(overall, color="#94a3b8", linestyle="--", linewidth=1.0, alpha=0.8)
    ax.text(len(pat) - 0.4, overall, f"rata² {overall:.0f}",
            ha="right", va="bottom", fontsize=8, color="#64748b")
    ax.set_title("Rata-rata Waste per Baris Aktif per Kelas Hari (mod 7)",
                 pad=12)
    # v2.5.1 (MO-M1): satuan dominan eksplisit di judul.
    unit_note = _dominant_unit_note(df)
    if unit_note:
        ax.set_title(
            f"Rata-rata Waste per Baris Aktif per Kelas Hari (mod 7)  [{unit_note}]",
            pad=12,
        )
    ax.set_ylabel("Mean per baris aktif")
    ax.set_xlabel("Kelas hari (hari % 7)")
    add_ylim_headroom(ax, factor=1.15)
    apply_layout(fig, ax, bottom_pad=0.22)
    return fig


# ============================================================
# CHART 15 (v2.5.0 P1) — HEATMAP: Alasan (KETERANGAN) × Hari
# ============================================================

def chart_reason_day_heatmap(df: pd.DataFrame, key_akhir: int | None = None,
                             top_n: int = 9) -> Figure:
    """Heatmap KETERANGAN × hari — kapan tiap alasan terjadi (P1).

    Pola seperti 'Cancel Nota naik di hari ramai' / 'Kualitas Internal
    spike tanggal 9' terlihat langsung di matriks ini.
    """
    mat = _temporal.reason_by_day(df, key_akhir=key_akhir, top_n=top_n)
    if mat.empty:
        return _empty_figure("Tidak ada data", figsize=(9, 5))
    keterangan = mat["KETERANGAN"].astype(str).tolist()
    day_cols = [c for c in mat.columns if c not in ("KETERANGAN", "Total")]
    values = mat[day_cols].to_numpy(dtype=float)

    n_rows = len(keterangan)
    n_cols = len(day_cols)
    fig_w = max(9.0, min(16.0, 0.42 * n_cols + 2))
    fig_h = max(4.0, min(9.0, 0.5 * n_rows + 2))
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)
    im = ax.imshow(values, aspect="auto", cmap="YlOrRd")
    ax.grid(False)
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([str(c) for c in day_cols], fontsize=7)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([fmt_reason(k, width=18) for k in keterangan])
    ax.set_title("Heatmap Alasan × Hari (total waste per hari)", pad=12)
    ax.set_xlabel("Hari (tanggal dalam bulan)")
    ax.set_ylabel("Alasan (KETERANGAN)")

    max_val = float(values.max()) if values.size else 0.0
    flat = sorted(
        ((values[i, j], i, j) for i in range(n_rows) for j in range(n_cols)
         if values[i, j] > 0),
        reverse=True,
    )
    for _, i, j in flat[:50]:
        v = values[i, j]
        color = adaptive_text_color(v, max_val * 0.6, max_val)
        ax.text(j, i, fmt_number_short(v, decimals=0), ha="center",
                va="center", fontsize=7, color=color, fontweight="bold")

    apply_layout(fig, ax, left_pad=0.26, bottom_pad=0.14,
                 right_pad=0.92, x_fontsize=7)
    cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03,
                        label="Total Waste (qty)")
    cbar.ax.grid(False)
    return fig


# ============================================================
# CHART 16 (v2.5.0 P2) — PARETO: Item (dengan satuan di label)
# ============================================================

def chart_item_pareto(df: pd.DataFrame, top_n: int = 20) -> Figure:
    """Pareto per NAMA BARANG: bar TOTAL + garis kumulatif (P2 money view).

    Label menyertakan satuan dominan item (mis. 'KULIT PANGSIT (GR)') —
    agregat lintas item mencampur satuan, jadi satuan harus eksplisit.
    """
    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        return _empty_figure("Tidak ada data", figsize=(8, 4.5))
    g = (df.groupby("NAMA BARANG", dropna=False)["TOTAL"].sum()
         .sort_values(ascending=False).head(top_n))
    if g.empty:
        return _empty_figure("Tidak ada data", figsize=(8, 4.5))

    # Satuan dominan per item (mode) — bila kolom SATUAN ada.
    if "SATUAN" in df.columns:
        sat_map = (
            df.dropna(subset=["SATUAN"])
            .groupby("NAMA BARANG")["SATUAN"]
            .agg(lambda s: s.mode().iat[0] if not s.mode().empty else "")
            .to_dict()
        )
    else:
        sat_map = {}

    grand = df["TOTAL"].sum()
    cum = g.cumsum() / grand * 100 if grand and grand > 0 else g * 0

    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    labels = [
        f"{fmt_item(str(name))} ({sat_map.get(name, '?')})"
        for name in g.index
    ]
    ax.bar(range(len(g)), g.values, color=PALETTE_ACCENT,
           edgecolor="white", linewidth=1.5)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(disambiguate_labels(labels))
    ax.set_ylabel("Total Waste (qty)")
    ax.set_title(f"Pareto Item — Top {len(g)} (satuan di label)", pad=12)

    ax2 = ax.twinx()
    ax2.plot(range(len(g)), cum.values, color=PALETTE_SECONDARY,
             marker="o", linewidth=2, markersize=4)
    ax2.set_ylabel("Kumulatif % (dari total)", color=PALETTE_SECONDARY, labelpad=12)
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis="y", colors=PALETTE_SECONDARY, labelsize=8)
    ax2.axhline(80, color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.text(len(g) - 1, 82, "80%", ha="right", fontsize=8, color="#94a3b8")

    for i, v in enumerate(g.values):
        if v == 0 or pd.isna(v):
            continue
        ax.text(i, v, fmt_number_short(v), ha="center", va="bottom",
                fontsize=7, color="#0f172a")
    add_ylim_headroom(ax)
    apply_layout(fig, ax, rotate_x=True, rotation=30, bottom_pad=0.22)
    return fig


# ============================================================
# CHART 17 (v2.5.0 P2) — HORIZONTAL BAR: Top Money Rows
# ============================================================

def chart_money_top(df: pd.DataFrame, top_n: int = 15) -> Figure:
    """Top-N baris waste terbesar APA PUN statusnya, diwarnai FOCUS CLASS
    (P2 — 'money view'): Fokus Utama merah, Sekunder oranye, Rutin netral.

    Menjawab gap audit: baris Prioritas Tinggi hanya 0,5% waste; baris
    uang terbesar justru berstatus Normal.
    """
    mv = _priority.money_view(df, top_n=top_n)
    if mv.empty:
        return _empty_figure("Tidak ada data", figsize=(8, 5))
    mv = mv.sort_values("TOTAL", ascending=True)  # barh bawah→atas menaik
    focus_colors = {
        "Fokus Utama": "#dc2626",
        "Fokus Sekunder": "#ea580c",
        "Rutin": PALETTE_NEUTRAL,
    }
    labels = [
        f"{fmt_item(str(it))} @ {fmt_cabang(str(cb))} ({str(sat)})"
        for it, cb, sat in zip(mv["NAMA BARANG"], mv["NAMA RESTO"], mv["SATUAN"])
    ]
    # v2.5.1 (MO-M1): SATUAN per bar — panjang bar lintas satuan (1 PCS ≠
    # 1 GR) tidak dibandingkan seolah satu skala; bar PCS kecil tetap
    # terlihat konteksnya.
    n = len(mv)
    fig_w, fig_h = dynamic_figsize(n, base_w=8.0, per_item_h=0.42,
                                   min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = fig.add_subplot(111)
    y = np.arange(n)
    colors = [focus_colors.get(str(f), PALETTE_NEUTRAL) for f in mv["FOCUS CLASS"]]
    bars = ax.barh(y, mv["TOTAL"].astype(float), color=colors,
                   edgecolor="white", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(disambiguate_labels(labels))
    for bar, val, score in zip(bars, mv["TOTAL"], mv["FOCUS SCORE"]):
        if val == 0 or pd.isna(val):
            continue
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {fmt_number_short(val)} (F{score:.0f})", ha="left",
                va="center", fontsize=7, fontweight="bold", color="#0f172a")
    ax.set_title(f"Top {n} Waste Terbesar — warna = FOCUS CLASS", pad=12)
    # v2.5.1 (MO-M1): xlabel jujur — panjang bar = jumlah qty SATUAN masing-
    # masing baris (satuan di label y), bukan satu skala nilai.
    ax.set_xlabel("TOTAL waste (qty satuan masing-masing — satuan di label)")
    handles = [Patch(facecolor=c, edgecolor="white", label=l)
               for l, c in focus_colors.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=False)
    add_xlim_headroom(ax, factor=1.18, side="right")
    apply_layout(fig, ax, left_pad=0.34, bottom_pad=0.10)
    return fig


# ============================================================
# PUBLIC ALIASES — nama pendek yang stabil (dipakai test/wiring UI)
# ============================================================

chart_pareto_alasan = chart_pareto_keterangan
chart_heatmap = chart_heatmap_cabang_item
chart_box_total = chart_box_total_per_jenis


# ============================================================
# REGISTRY — semua chart yang tersedia
# ============================================================

ALL_CHARTS = [
    ("Distribusi Status", "Pie: status anomali", chart_status_pie),
    ("Waste per Cabang", "Bar: total waste per cabang", chart_waste_per_cabang),
    ("Top 10 Items", "Horizontal bar: item dengan waste tertinggi", chart_top_items),
    ("Status per Cabang", "Stacked bar: distribusi status per cabang", chart_status_per_cabang),
    ("Pareto Alasan", "Bar + line: 80/20 keterangan", chart_pareto_keterangan),
    ("Heatmap Cabang×Item", "Matrix: waste per pasangan cabang-item", chart_heatmap_cabang_item),
    ("Frekuensi Penyebab", "Bar: alasan anomali terdeteksi", chart_reasons_frequency),
    ("Scatter MAX vs TOTAL", "Outlier detection: MAX vs TOTAL", chart_scatter_max_total),
    ("Box TOTAL per JENIS", "Distribusi TOTAL per jenis waste", chart_box_total_per_jenis),
    ("Score per Cabang", "Avg & max anomali score per cabang", chart_score_per_cabang),
    ("Kategori per Cabang", "Stacked bar: kategori anomali per cabang", chart_kategori_per_cabang),
    ("Distribusi JENIS", "Donut: distribusi jenis waste", chart_jenis_donut),
]
