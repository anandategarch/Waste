"""
charts.py — generator grafik untuk tab Visualisasi.

Menggunakan matplotlib + FigureCanvasTkAgg untuk embed di Tkinter.
Setiap fungsi return Figure yang siap di-embed.

Dipanggil oleh ui_app.py saat user buka tab Visualisasi.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import matplotlib
# Lazy set backend — di-overridden ke TkAgg oleh ui_app.py saat dibutuhkan
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

# Lazy import FigureCanvasTkAgg — hanya ketika embed ke Tkinter (di UI).
# Di headless test environment, import ini bisa gagal karena tidak ada Tcl/Tk.
_FigureCanvasTkAgg = None


def _get_canvas_class():
    """Lazy load FigureCanvasTkAgg. Dipanggil hanya dari embed_figure()."""
    global _FigureCanvasTkAgg
    if _FigureCanvasTkAgg is None:
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        _FigureCanvasTkAgg = FigureCanvasTkAgg
    return _FigureCanvasTkAgg


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

PALETTE_KATEGORI = [
    "#0f766e", "#be185d", "#b45309", "#15803d",
    "#7c2d12", "#475569", "#9333ea", "#0891b2",
    "#ca8a04", "#db2777", "#65a30d", "#4b5563",
]

PALETTE_ACCENT = "#0f766e"   # teal-700 (utama)
PALETTE_SECONDARY = "#be185d" # pink-700
PALETTE_NEUTRAL = "#475569"

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


# ============================================================
# CHART 1 — PIE: Distribusi Status Anomali
# ============================================================

def chart_status_pie(df: pd.DataFrame) -> Figure:
    """Pie chart distribusi ANOMALY STATUS."""
    fig = Figure(figsize=(6, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    if "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df["ANOMALY STATUS"].value_counts()
    # Urutan tetap: Prioritas Tinggi > Potensi Anomali > Perlu Review > Normal
    order = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    counts = counts.reindex([s for s in order if s in counts.index])
    colors = [PALETTE_STATUS.get(s, PALETTE_NEUTRAL) for s in counts.index]

    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=counts.index,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%\n({int(round(pct/100*counts.sum()))})",  # round to avoid off-by-one
        startangle=90,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9, color="#1e293b", fontweight="bold"),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
    ax.set_title("Distribusi Status Anomali", pad=12)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 2 — BAR: Waste Total per Cabang
# ============================================================

def chart_waste_per_cabang(df: pd.DataFrame) -> Figure:
    """Bar chart total waste per NAMA RESTO."""
    fig = Figure(figsize=(7, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=False)["TOTAL"].sum().sort_values(ascending=False)
    bars = ax.bar(g.index.astype(str), g.values, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{val:.1f}", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#0f172a")
    ax.set_title("Total Waste per Cabang", pad=12)
    ax.set_ylabel("Total Waste (qty)")
    ax.set_xlabel("Cabang")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 3 — HORIZONTAL BAR: Top 10 Items
# ============================================================

def chart_top_items(df: pd.DataFrame, top_n: int = 10) -> Figure:
    """Horizontal bar chart top N item by TOTAL waste."""
    fig = Figure(figsize=(7, 5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = (df.groupby("NAMA BARANG", dropna=False)["TOTAL"].sum()
         .sort_values(ascending=True).tail(top_n))
    bars = ax.barh(g.index.astype(str), g.values, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {val:.1f}", ha="left", va="center", fontsize=8, fontweight="bold", color="#0f172a")
    ax.set_title(f"Top {top_n} Item dengan Waste Tertinggi", pad=12)
    ax.set_xlabel("Total Waste (qty)")
    ax.set_ylabel("")
    fig.tight_layout()
    return fig


# ============================================================
# CHART 4 — STACKED BAR: Anomali Status per Cabang
# ============================================================

def chart_status_per_cabang(df: pd.DataFrame) -> Figure:
    """Stacked bar: distribusi status anomali per cabang."""
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    pivot = pd.crosstab(df["NAMA RESTO"], df["ANOMALY STATUS"])
    order = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    cols = [c for c in order if c in pivot.columns]
    pivot = pivot[cols]
    colors = [PALETTE_STATUS.get(c, PALETTE_NEUTRAL) for c in cols]

    pivot.plot(kind="bar", stacked=True, ax=ax, color=colors, edgecolor="white", linewidth=1)
    ax.set_title("Distribusi Status Anomali per Cabang", pad=12)
    ax.set_ylabel("Jumlah Baris")
    ax.set_xlabel("Cabang")
    ax.legend(title="Status", loc="upper right", bbox_to_anchor=(1.0, 1.0))
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 5 — PARETO: Alasan (KETERANGAN)
# ============================================================

def chart_pareto_keterangan(df: pd.DataFrame) -> Figure:
    """Pareto chart: bar TOTAL per KETERANGAN + cumulative line."""
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    ax2 = ax.twinx()

    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = df.groupby("KETERANGAN", dropna=False)["TOTAL"].sum().sort_values(ascending=False)
    cum = g.cumsum() / g.sum() * 100 if g.sum() > 0 else g * 0

    bars = ax.bar(range(len(g)), g.values, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(g.index.astype(str), rotation=30, ha="right")
    ax.set_ylabel("Total Waste (qty)")
    ax.set_title("Pareto: Kontribusi Waste per KETERANGAN", pad=12)

    # Cumulative line
    ax2.plot(range(len(g)), cum.values, color=PALETTE_SECONDARY, marker="o", linewidth=2, markersize=5)
    ax2.set_ylabel("Cumulative %", color=PALETTE_SECONDARY)
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis="y", colors=PALETTE_SECONDARY)
    ax2.axhline(80, color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.text(len(g) - 1, 82, "80%", ha="right", fontsize=8, color="#94a3b8")

    # Label di atas bar
    for i, v in enumerate(g.values):
        ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=7, color="#0f172a")

    fig.tight_layout()
    return fig


# ============================================================
# CHART 6 — HEATMAP: Waste per Cabang × Item
# ============================================================

def chart_heatmap_cabang_item(df: pd.DataFrame) -> Figure:
    """Heatmap matrix Cabang × Item, value = TOTAL waste."""
    fig = Figure(figsize=(8, 5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    pivot = df.pivot_table(
        index="NAMA BARANG", columns="NAMA RESTO",
        values="TOTAL", aggfunc="sum", fill_value=0,
    )
    if pivot.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Urutkan item by total desc
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

    im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns.astype(str), rotation=30, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.astype(str))
    ax.set_title("Heatmap Waste per Cabang × Item", pad=12)
    ax.set_xlabel("Cabang")
    ax.set_ylabel("Item")

    # Annotate
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            v = pivot.values[i, j]
            if v > 0:
                color = "white" if v > pivot.values.max() * 0.6 else "#0f172a"
                ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                        fontsize=7, color=color, fontweight="bold")

    fig.colorbar(im, ax=ax, label="Total Waste (qty)", shrink=0.8)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 7 — BAR: Anomali Reasons Frequency
# ============================================================

def chart_reasons_frequency(df: pd.DataFrame) -> Figure:
    """Bar chart frekuensi ANOMALY REASONS (split by ' | ')."""
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "ANOMALY REASONS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counter = Counter()
    for reasons in df["ANOMALY REASONS"].dropna():
        if reasons:
            for r in str(reasons).split(" | "):
                r = r.strip()
                if r:
                    counter[r] += 1

    if not counter:
        ax.text(0.5, 0.5, "Tidak ada alasan anomali terdeteksi", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    items = sorted(counter.items(), key=lambda x: x[1])
    labels = [x[0] for x in items]
    values = [x[1] for x in items]
    bars = ax.barh(labels, values, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {val}", ha="left", va="center", fontsize=8, fontweight="bold", color="#0f172a")
    ax.set_title("Frekuensi Penyebab Anomali", pad=12)
    ax.set_xlabel("Jumlah Baris")
    fig.tight_layout()
    return fig


# ============================================================
# CHART 8 — SCATTER: MAX vs TOTAL (outlier detection)
# ============================================================

def chart_scatter_max_total(df: pd.DataFrame) -> Figure:
    """Scatter plot MAX vs TOTAL, warna per ANOMALY STATUS."""
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "MAX" not in df.columns or "TOTAL" not in df.columns or "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Plot per status supaya legend muncul
    plotted = False
    for status, color in PALETTE_STATUS.items():
        sub = df[df["ANOMALY STATUS"] == status]
        if sub.empty:
            continue
        ax.scatter(sub["TOTAL"], sub["MAX"], c=color, label=status,
                   alpha=0.7, edgecolors="white", linewidth=0.5, s=60)
        plotted = True

    if not plotted:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Garis identitas (MAX = TOTAL) — single-day dominance
    max_val = max(df["TOTAL"].max(), df["MAX"].max())
    if pd.isna(max_val) or max_val <= 0:
        max_xy = 1.0
    else:
        max_xy = float(max_val) * 1.05
    ax.plot([0, max_xy], [0, max_xy], "--", color="#94a3b8", linewidth=0.8, alpha=0.7, label="MAX = TOTAL (single-day)")

    ax.set_title("Scatter: MAX vs TOTAL — Deteksi Outlier", pad=12)
    ax.set_xlabel("TOTAL Waste (qty)")
    ax.set_ylabel("MAX Waste (qty, single day)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 9 — BOX PLOT: Distribusi TOTAL per JENIS
# ============================================================

def chart_box_total_per_jenis(df: pd.DataFrame) -> Figure:
    """Box plot distribusi TOTAL per JENIS (SUSUT/TRIAL/WASTE)."""
    fig = Figure(figsize=(6, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "JENIS" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    data = []
    labels = []
    for jenis in ["WASTE", "SUSUT", "TRIAL"]:
        sub = df[df["JENIS"] == jenis]["TOTAL"].dropna()
        if not sub.empty:
            data.append(sub.values)
            labels.append(jenis)

    if not data:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.5,
                    medianprops=dict(color="#0f172a", linewidth=2))
    for patch, color in zip(bp["boxes"], PALETTE_KATEGORI[:len(data)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
        patch.set_edgecolor("white")
        patch.set_linewidth(1.5)

    ax.set_title("Distribusi TOTAL Waste per JENIS", pad=12)
    ax.set_ylabel("TOTAL Waste (qty)")
    ax.set_xlabel("JENIS")
    fig.tight_layout()
    return fig


# ============================================================
# CHART 10 — BAR: Anomali Score per Cabang (avg + max)
# ============================================================

def chart_score_per_cabang(df: pd.DataFrame) -> Figure:
    """Grouped bar: avg & max ANOMALY SCORE per cabang."""
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "ANOMALY SCORE" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=False)["ANOMALY SCORE"].agg(["mean", "max"]).reset_index()
    g = g.sort_values("max", ascending=False)
    x = np.arange(len(g))
    w = 0.35
    b1 = ax.bar(x - w/2, g["mean"], w, label="Rata-rata", color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, g["max"], w, label="Max", color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(g["NAMA RESTO"].astype(str), rotation=20)
    ax.set_title("Anomali Score per Cabang (Avg vs Max)", pad=12)
    ax.set_ylabel("Anomali Score")
    ax.set_xlabel("Cabang")
    ax.legend()
    # Threshold lines
    ax.axhline(8, color=PALETTE_STATUS["Prioritas Tinggi"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(5, color=PALETTE_STATUS["Potensi Anomali"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(3, color=PALETTE_STATUS["Perlu Review"], linestyle="--", linewidth=0.8, alpha=0.5)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 11 — STACKED BAR: KATEGORI ANOMALI per Cabang
# ============================================================

def chart_kategori_per_cabang(df: pd.DataFrame) -> Figure:
    """Stacked bar KATEGORI ANOMALI per cabang."""
    fig = Figure(figsize=(7, 4.5), dpi=100)
    ax = fig.add_subplot(111)

    if "NAMA RESTO" not in df.columns or "KATEGORI ANOMALI" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    pivot = pd.crosstab(df["NAMA RESTO"], df["KATEGORI ANOMALI"])
    colors = PALETTE_KATEGORI[:len(pivot.columns)]
    pivot.plot(kind="bar", stacked=True, ax=ax, color=colors, edgecolor="white", linewidth=1)
    ax.set_title("Kategori Anomali per Cabang", pad=12)
    ax.set_ylabel("Jumlah Baris")
    ax.set_xlabel("Cabang")
    ax.legend(title="Kategori", loc="upper right")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    return fig


# ============================================================
# CHART 12 — DONUT: Share JENIS (WASTE/SUSUT/TRIAL)
# ============================================================

def chart_jenis_donut(df: pd.DataFrame) -> Figure:
    """Donut chart distribusi JENIS (count baris)."""
    fig = Figure(figsize=(5, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    if "JENIS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df["JENIS"].value_counts()
    colors = PALETTE_KATEGORI[:len(counts)]
    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=counts.index.astype(str),
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%\n({int(pct/100*counts.sum())})",
        startangle=90,
        wedgeprops=dict(width=0.4, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9, color="#1e293b", fontweight="bold"),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
    ax.set_title("Distribusi JENIS Waste", pad=12)
    fig.tight_layout()
    return fig


# ============================================================
# EMBED HELPER
# ============================================================

def embed_figure(parent: Any, fig: Figure):
    """Embed Figure ke Tkinter parent. Return canvas widget."""
    canvas_cls = _get_canvas_class()
    canvas = canvas_cls(fig, master=parent)
    canvas.draw()
    return canvas


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
