"""
dashboard.py — chart interaktif untuk drill-down.

Setiap chart adalah InteractiveChart class yang:
1. Render figure matplotlib
2. Tangkap event klik (button_press_event)
3. Emit filter signal ke callback
4. Highlight bar yang di-klik

Pola: user klik bar/slice → callback update filter → UI refresh table + re-render charts lain
"""

from __future__ import annotations

from typing import Any, Callable

# NOTE: backend diset di ui_app.py (matplotlib.use("TkAgg")) sebelum import dashboard
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

# Import palette dari charts.py
from .charts import (
    PALETTE_STATUS, PALETTE_KATEGORI, PALETTE_ACCENT, PALETTE_SECONDARY, PALETTE_NEUTRAL,
)


FilterCallback = Callable[[str, str | None], None]
"""Callback signature: (filter_key, value) -> None. value=None artinya clear filter."""


# ============================================================
# HELPER: build ax with consistent style
# ============================================================

def _styled_axes(fig: Figure):
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(colors="#475569", labelsize=8)
    ax.grid(True, color="#e2e8f0", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.title.set_color("#0f172a")
    ax.title.set_fontweight("bold")
    ax.title.set_fontsize(10)
    return ax


# ============================================================
# INTERACTIVE: Bar chart — click bar to filter by that value
# ============================================================

def chart_status_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> Figure:
    """Bar chart distribusi ANOMALY STATUS. Klik bar → filter by status."""
    fig = Figure(figsize=(5.5, 3.2), dpi=100)
    ax = _styled_axes(fig)

    if "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df["ANOMALY STATUS"].value_counts()
    order = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    counts = counts.reindex([s for s in order if s in counts.index]).fillna(0).astype(int)

    # Highlight active filter
    active_val = active_filter[1] if active_filter and active_filter[0] == "status" else None
    colors = []
    for s in counts.index:
        base = PALETTE_STATUS.get(s, PALETTE_NEUTRAL)
        if active_val and s != active_val:
            base = "#cbd5e1"  # gray out non-active
        colors.append(base)

    bars = ax.bar(counts.index.astype(str), counts.values, color=colors,
                   edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{int(val)}", ha="center", va="bottom", fontsize=9,
                fontweight="bold", color="#0f172a")
    ax.set_title("Klik Bar untuk Filter Status", pad=10)
    ax.set_ylabel("Jumlah Baris")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()

    # Wire click event
    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(bars):
                if bar.contains(event)[0]:
                    val = counts.index[i]
                    new_val = None if active_val == val else val
                    on_click("status", new_val)
                    return
        fig.canvas.mpl_connect("button_press_event", _on_pick)

    return fig


# ============================================================
# INTERACTIVE: Waste per Cabang bar — click to filter
# ============================================================

def chart_cabang_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> Figure:
    """Bar chart waste per NAMA RESTO. Klik bar → filter by cabang."""
    fig = Figure(figsize=(6, 3.2), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=False)["TOTAL"].sum().sort_values(ascending=False)
    active_val = active_filter[1] if active_filter and active_filter[0] == "cabang" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_ACCENT)

    bars = ax.bar(g.index.astype(str), g.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{val:.0f}", ha="center", va="bottom", fontsize=8,
                fontweight="bold", color="#0f172a")
    ax.set_title("Klik Bar untuk Filter Cabang", pad=10)
    ax.set_ylabel("Total Waste")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()

    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(bars):
                if bar.contains(event)[0]:
                    val = g.index[i]
                    new_val = None if active_val == val else val
                    on_click("cabang", new_val)
                    return
        fig.canvas.mpl_connect("button_press_event", _on_pick)
    return fig


# ============================================================
# INTERACTIVE: Top items horizontal bar — click to filter
# ============================================================

def chart_top_items_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
    top_n: int = 10,
) -> Figure:
    """Horizontal bar top items. Klik → filter by NAMA BARANG."""
    fig = Figure(figsize=(6, 4), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = (df.groupby("NAMA BARANG", dropna=False)["TOTAL"].sum()
         .sort_values(ascending=True).tail(top_n))
    active_val = active_filter[1] if active_filter and active_filter[0] == "item" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_SECONDARY)

    bars = ax.barh(g.index.astype(str), g.values, color=colors,
                   edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {val:.1f}", ha="left", va="center", fontsize=8,
                fontweight="bold", color="#0f172a")
    ax.set_title(f"Top {top_n} Item — Klik untuk Filter", pad=10)
    ax.set_xlabel("Total Waste")
    fig.tight_layout()

    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(bars):
                if bar.contains(event)[0]:
                    val = g.index[i]
                    new_val = None if active_val == val else val
                    on_click("item", new_val)
                    return
        fig.canvas.mpl_connect("button_press_event", _on_pick)
    return fig


# ============================================================
# INTERACTIVE: Pareto KETERANGAN — click to filter
# ============================================================

def chart_keterangan_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
    top_n: int = 12,
) -> Figure:
    """Bar chart TOTAL per KETERANGAN (top N). Klik → filter."""
    fig = Figure(figsize=(7, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = (df.groupby("KETERANGAN", dropna=False)["TOTAL"].sum()
         .sort_values(ascending=False).head(top_n))
    active_val = active_filter[1] if active_filter and active_filter[0] == "keterangan" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_ACCENT)

    bars = ax.bar(range(len(g)), g.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(g.index.astype(str), rotation=30, ha="right", fontsize=8)
    for i, val in enumerate(g.values):
        ax.text(i, val, f"{val:.0f}", ha="center", va="bottom", fontsize=7, color="#0f172a")
    ax.set_title("Top Alasan — Klik Bar untuk Filter", pad=10)
    ax.set_ylabel("Total Waste")
    fig.tight_layout()

    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(bars):
                if bar.contains(event)[0]:
                    val = g.index[i]
                    new_val = None if active_val == val else val
                    on_click("keterangan", new_val)
                    return
        fig.canvas.mpl_connect("button_press_event", _on_pick)
    return fig


# ============================================================
# INTERACTIVE: JENIS donut — click to filter
# ============================================================

def chart_jenis_donut_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> Figure:
    """Donut JENIS. Klik slice → filter by JENIS."""
    fig = Figure(figsize=(4.5, 3.2), dpi=100)
    ax = fig.add_subplot(111)

    if "JENIS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df["JENIS"].value_counts()
    active_val = active_filter[1] if active_filter and active_filter[0] == "jenis" else None

    colors = []
    for j in counts.index:
        base = PALETTE_KATEGORI[hash(str(j)) % len(PALETTE_KATEGORI)]
        if active_val and j != active_val:
            base = "#cbd5e1"
        colors.append(base)

    wedges, texts, autotexts = ax.pie(
        counts.values, labels=counts.index.astype(str), colors=colors,
        autopct=lambda pct: f"{pct:.1f}%\n({int(round(pct/100*counts.sum()))})",
        startangle=90,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=9, color="#1e293b", fontweight="bold"),
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(8)
    ax.set_title("JENIS — Klik Slice untuk Filter", pad=10)
    fig.tight_layout()

    if on_click:
        def _on_pick(event):
            for i, w in enumerate(wedges):
                if event.inaxes == ax:
                    # Cek apakah klik di dalam wedge
                    contains, _ = w.contains(event)
                    if contains:
                        val = counts.index[i]
                        new_val = None if active_val == val else val
                        on_click("jenis", new_val)
                        return
        fig.canvas.mpl_connect("button_press_event", _on_pick)
    return fig


# ============================================================
# INTERACTIVE: Score per Cabang — click to filter
# ============================================================

def chart_score_per_cabang_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> Figure:
    """Grouped bar avg & max score per cabang."""
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "ANOMALY SCORE" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    g = df.groupby("NAMA RESTO", dropna=False)["ANOMALY SCORE"].agg(["mean", "max"]).reset_index()
    g = g.sort_values("max", ascending=False)
    active_val = active_filter[1] if active_filter and active_filter[0] == "cabang" else None

    x = np.arange(len(g))
    w = 0.35
    colors_avg = ["#cbd5e1" if (active_val and c != active_val) else PALETTE_ACCENT for c in g["NAMA RESTO"]]
    colors_max = ["#cbd5e1" if (active_val and c != active_val) else PALETTE_SECONDARY for c in g["NAMA RESTO"]]

    b1 = ax.bar(x - w/2, g["mean"], w, label="Rata-rata", color=colors_avg, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, g["max"], w, label="Max", color=colors_max, edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(g["NAMA RESTO"].astype(str), rotation=20, fontsize=8)
    ax.set_title("Anomali Score per Cabang — Klik untuk Filter", pad=10)
    ax.set_ylabel("Score")
    ax.legend(fontsize=8, loc="upper right")
    ax.axhline(8, color=PALETTE_STATUS["Prioritas Tinggi"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(5, color=PALETTE_STATUS["Potensi Anomali"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(3, color=PALETTE_STATUS["Perlu Review"], linestyle="--", linewidth=0.8, alpha=0.5)
    fig.tight_layout()

    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(b1):
                if bar.contains(event)[0] or b2[i].contains(event)[0]:
                    val = g["NAMA RESTO"].iloc[i]
                    new_val = None if active_val == val else val
                    on_click("cabang", new_val)
                    return
        fig.canvas.mpl_connect("button_press_event", _on_pick)
    return fig
