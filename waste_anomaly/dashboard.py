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

# v2.3.1 helpers — fix semua UI/UX issues (Pattern A-H)
from .chart_helpers import (
    apply_layout,
    fmt_cabang,
    fmt_item,
    fmt_reason,
    place_legend_outside,
    add_ylim_headroom,
    add_xlim_headroom,
    dynamic_figsize,
    adaptive_text_color,
    fmt_number_short,
    fmt_number_comma,
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


def _wrap_title(title: str, max_chars: int = 40) -> str:
    """Wrap long titles containing cabang names with newline.

    Pattern C: long titles overflow the figure when cabang codes are long.
    Splits at the space closest to the midpoint (single split, 2 lines max).
    """
    if len(title) <= max_chars:
        return title
    mid = len(title) // 2
    left_space = title.rfind(" ", 0, mid)
    right_space = title.find(" ", mid)
    if left_space == -1 and right_space == -1:
        return title
    if left_space == -1:
        split_at = right_space
    elif right_space == -1:
        split_at = left_space
    else:
        split_at = left_space if (mid - left_space) <= (right_space - mid) else right_space
    return title[:split_at] + "\n" + title[split_at + 1:]


def _restore_legend_title(ax, title: str | None) -> None:
    """Set title on existing legend (place_legend_outside doesn't preserve it)."""
    if not title:
        return
    leg = ax.get_legend()
    if leg is not None:
        leg.set_title(title)


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
    # Pattern D: headroom so data labels don't clip
    add_ylim_headroom(ax)
    # Pattern A + E: rotate status labels (they're long like "Prioritas Tinggi")
    apply_layout(fig, ax, rotate_x=True, rotation=20, bottom_pad=0.22, top_pad=0.88)

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
    # Pattern G: wider figure for many cabangs
    n_cabangs = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 5
    fig_w = max(6.0, min(12.0, 0.4 * n_cabangs + 3))
    fig = Figure(figsize=(fig_w, 3.5), dpi=100)
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

    # Pattern C: abbreviate cabang codes
    cabang_labels = [fmt_cabang(str(c)) for c in g.index]
    bars = ax.bar(cabang_labels, g.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    # Pattern D: data labels with short format, rotate 90° if >10 bars to prevent overlap
    label_rotation = 90 if len(bars) > 10 else 0
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                fmt_number_short(val), ha="center", va="bottom", fontsize=7,
                fontweight="bold", color="#0f172a",
                rotation=label_rotation)
    ax.set_title("Klik Bar untuk Filter Cabang", pad=10)
    ax.set_ylabel("Total Waste")
    # Pattern D: 20% headroom for rotated labels
    add_ylim_headroom(ax, factor=1.20)
    # Pattern A + E: rotate x labels
    apply_layout(fig, ax, rotate_x=True, bottom_pad=0.22, top_pad=0.88)

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
    # Pattern G: dynamic figsize based on number of items
    fig_w, fig_h = dynamic_figsize(top_n, base_w=6.0, per_item_h=0.4, min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
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

    # Pattern C: wrap long item names
    item_labels = [fmt_item(name) for name in g.index.astype(str)]
    bars = ax.barh(item_labels, g.values, color=colors,
                   edgecolor="white", linewidth=1.5)
    # Pattern D: data labels with short format
    for bar, val in zip(bars, g.values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {fmt_number_short(val)}", ha="left", va="center", fontsize=8,
                fontweight="bold", color="#0f172a")
    ax.set_title(f"Top {top_n} Item — Klik untuk Filter", pad=10)
    ax.set_xlabel("Total Waste")
    # Pattern D: headroom for data labels
    add_xlim_headroom(ax, factor=1.10, side="right")
    # Pattern A: extra left padding for wrapped item labels
    apply_layout(fig, ax, left_pad=0.30, bottom_pad=0.12, top_pad=0.88)

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
    # Pattern C: wrap long KETERANGAN reasons
    ax.set_xticklabels([fmt_reason(str(k)) for k in g.index], fontsize=8)
    # Pattern D: data labels with short format
    for i, val in enumerate(g.values):
        ax.text(i, val, fmt_number_short(val), ha="center", va="bottom",
                fontsize=7, color="#0f172a")
    ax.set_title("Top Alasan — Klik Bar untuk Filter", pad=10)
    ax.set_ylabel("Total Waste")
    # Pattern D: headroom
    add_ylim_headroom(ax)
    # Pattern A + E: rotation 30 (wrapped labels)
    apply_layout(fig, ax, rotate_x=True, rotation=30, bottom_pad=0.22, top_pad=0.88)

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

    # Pattern D + C: closer pct, count moved to legend
    wedges, texts, autotexts = ax.pie(
        counts.values, labels=counts.index.astype(str), colors=colors,
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
    ax.set_title("JENIS — Klik Slice untuk Filter", pad=10)
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
    # Pattern C: abbreviate cabang codes
    ax.set_xticklabels([fmt_cabang(str(c)) for c in g["NAMA RESTO"]], fontsize=8)
    ax.set_title("Anomali Score per Cabang — Klik untuk Filter", pad=10)
    ax.set_ylabel("Score")
    ax.axhline(8, color=PALETTE_STATUS["Prioritas Tinggi"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(5, color=PALETTE_STATUS["Potensi Anomali"], linestyle="--", linewidth=0.8, alpha=0.5)
    ax.axhline(3, color=PALETTE_STATUS["Perlu Review"], linestyle="--", linewidth=0.8, alpha=0.5)
    # Pattern D: headroom for max bar data labels
    add_ylim_headroom(ax)
    # Pattern A + B + E: margins, legend outside, rotation
    apply_layout(fig, ax, rotate_x=True, legend_outside=True, bottom_pad=0.22, right_pad=0.75, top_pad=0.88)

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


# ============================================================
# COMPARISON CHARTS — 2 cabang side-by-side
# ============================================================

def chart_compare_total_waste(
    df: pd.DataFrame,
    cabang_a: str,
    cabang_b: str,
) -> Figure:
    """Side-by-side bar: total waste per JENIS for 2 cabang."""
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns or "JENIS" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Filter each cabang, group by JENIS
    jenis_list = ["WASTE", "SUSUT", "TRIAL"]
    a_vals = []
    b_vals = []
    for j in jenis_list:
        a_vals.append(float(df[(df["NAMA RESTO"] == cabang_a) & (df["JENIS"] == j)]["TOTAL"].sum()))
        b_vals.append(float(df[(df["NAMA RESTO"] == cabang_b) & (df["JENIS"] == j)]["TOTAL"].sum()))

    x = np.arange(len(jenis_list))
    w = 0.38
    b1 = ax.bar(x - w/2, a_vals, w, label=cabang_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, b_vals, w, label=cabang_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    # Pattern D: data labels with short format
    for bar, val in zip(b1, a_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                fmt_number_short(val), ha="center", va="bottom", fontsize=8,
                fontweight="bold", color=PALETTE_ACCENT)
    for bar, val in zip(b2, b_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                fmt_number_short(val), ha="center", va="bottom", fontsize=8,
                fontweight="bold", color=PALETTE_SECONDARY)
    ax.set_xticks(x)
    ax.set_xticklabels(jenis_list)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Total Waste per JENIS — {cabang_a} vs {cabang_b}"), pad=10)
    ax.set_ylabel("Total Waste")
    # Pattern D: headroom for data labels
    add_ylim_headroom(ax)
    # Pattern A + B: margins + legend outside
    apply_layout(fig, ax, legend_outside=True, bottom_pad=0.18, right_pad=0.75, top_pad=0.85)
    return fig


def chart_compare_status(
    df: pd.DataFrame,
    cabang_a: str,
    cabang_b: str,
) -> Figure:
    """Grouped bar: status anomali count for 2 cabang."""
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "ANOMALY STATUS" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    statuses = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    a_sub = df[df["NAMA RESTO"] == cabang_a]
    b_sub = df[df["NAMA RESTO"] == cabang_b]
    a_vals = [int((a_sub["ANOMALY STATUS"] == s).sum()) for s in statuses]
    b_vals = [int((b_sub["ANOMALY STATUS"] == s).sum()) for s in statuses]

    x = np.arange(len(statuses))
    w = 0.38
    b1 = ax.bar(x - w/2, a_vals, w, label=cabang_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, b_vals, w, label=cabang_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    for bar, val in zip(b1, a_vals):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    fmt_number_short(val), ha="center", va="bottom", fontsize=8,
                    fontweight="bold", color=PALETTE_ACCENT)
    for bar, val in zip(b2, b_vals):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    fmt_number_short(val), ha="center", va="bottom", fontsize=8,
                    fontweight="bold", color=PALETTE_SECONDARY)
    ax.set_xticks(x)
    ax.set_xticklabels(statuses, fontsize=8)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Status Anomali — {cabang_a} vs {cabang_b}"), pad=10)
    ax.set_ylabel("Jumlah Baris")
    # Pattern D: headroom
    add_ylim_headroom(ax)
    # Pattern A + B + E: rotation + legend outside + margins
    apply_layout(fig, ax, rotate_x=True, rotation=15, legend_outside=True,
                 bottom_pad=0.22, right_pad=0.75, top_pad=0.85)
    return fig


def chart_compare_top_items(
    df: pd.DataFrame,
    cabang_a: str,
    cabang_b: str,
    top_n: int = 8,
) -> Figure:
    """Horizontal grouped bar: top items by total waste, A vs B side-by-side."""
    # Pattern G: dynamic figsize based on top_n
    fig_w, fig_h = dynamic_figsize(top_n, base_w=7.0, per_item_h=0.45, min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Get all unique items from both cabangs
    items_a = df[df["NAMA RESTO"] == cabang_a].groupby("NAMA BARANG", dropna=False)["TOTAL"].sum()
    items_b = df[df["NAMA RESTO"] == cabang_b].groupby("NAMA BARANG", dropna=False)["TOTAL"].sum()
    all_items = items_a.add(items_b, fill_value=0).sort_values(ascending=True).tail(top_n)
    a_vals = [float(items_a.get(i, 0)) for i in all_items.index]
    b_vals = [float(items_b.get(i, 0)) for i in all_items.index]

    y = np.arange(len(all_items))
    h = 0.38
    b1 = ax.barh(y - h/2, a_vals, h, label=cabang_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.barh(y + h/2, b_vals, h, label=cabang_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    ax.set_yticks(y)
    # Pattern C: wrap long item names
    ax.set_yticklabels([fmt_item(str(name)) for name in all_items.index], fontsize=8)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Top {top_n} Item — {cabang_a} vs {cabang_b}"), pad=10)
    ax.set_xlabel("Total Waste")
    # Pattern D: headroom for data labels (none here but keep ratio consistent)
    add_xlim_headroom(ax, factor=1.10, side="right")
    # Pattern A + B: legend outside + left padding for wrapped labels
    apply_layout(fig, ax, legend_outside=True, left_pad=0.30, bottom_pad=0.12,
                 right_pad=0.75, top_pad=0.88)
    return fig


def chart_compare_score(
    df: pd.DataFrame,
    cabang_a: str,
    cabang_b: str,
) -> Figure:
    """Radar-like comparison: avg/max score, avg waste, count prioritas."""
    fig = Figure(figsize=(5.5, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    a_sub = df[df["NAMA RESTO"] == cabang_a]
    b_sub = df[df["NAMA RESTO"] == cabang_b]

    metrics = ["Avg Score", "Max Score", "Avg Waste", "Max Waste", "Jml Prioritas"]
    a_vals = [
        float(a_sub["ANOMALY SCORE"].mean() if "ANOMALY SCORE" in a_sub.columns else 0),
        float(a_sub["ANOMALY SCORE"].max() if "ANOMALY SCORE" in a_sub.columns else 0),
        float(a_sub["TOTAL"].mean() if "TOTAL" in a_sub.columns else 0),
        float(a_sub["MAX"].max() if "MAX" in a_sub.columns else 0),
        int((a_sub["ANOMALY STATUS"] == "Prioritas Tinggi").sum() if "ANOMALY STATUS" in a_sub.columns else 0),
    ]
    b_vals = [
        float(b_sub["ANOMALY SCORE"].mean() if "ANOMALY SCORE" in b_sub.columns else 0),
        float(b_sub["ANOMALY SCORE"].max() if "ANOMALY SCORE" in b_sub.columns else 0),
        float(b_sub["TOTAL"].mean() if "TOTAL" in b_sub.columns else 0),
        float(b_sub["MAX"].max() if "MAX" in b_sub.columns else 0),
        int((b_sub["ANOMALY STATUS"] == "Prioritas Tinggi").sum() if "ANOMALY STATUS" in b_sub.columns else 0),
    ]

    x = np.arange(len(metrics))
    w = 0.38
    b1 = ax.bar(x - w/2, a_vals, w, label=cabang_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, b_vals, w, label=cabang_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    for bar, val in zip(b1, a_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{val:.1f}", ha="center", va="bottom", fontsize=7,
                fontweight="bold", color=PALETTE_ACCENT)
    for bar, val in zip(b2, b_vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{val:.1f}", ha="center", va="bottom", fontsize=7,
                fontweight="bold", color=PALETTE_SECONDARY)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=8)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Metrics Comparison — {cabang_a} vs {cabang_b}"), pad=10)
    # Pattern D: headroom
    add_ylim_headroom(ax)
    # Pattern A + B + E: rotation + legend outside + margins
    apply_layout(fig, ax, rotate_x=True, rotation=15, legend_outside=True,
                 bottom_pad=0.22, right_pad=0.75, top_pad=0.85)
    return fig


# ============================================================
# QUADRANT CHART (NEW v2.3.0) — Sistemik vs Insiden scatter
# ============================================================

def chart_quadrant_scatter(
    df: pd.DataFrame,
    threshold: float = 0.5,
) -> Figure:
    """Scatter plot: X = prevalence (cabangActive/total), Y = persistence (daysActive/KeyAkhir).
    4 quadrant: SISTEMIK, MUSIMAN, LOKAL-KRONIS, INSIDEN.
    Bubble size = totalWaste.
    """
    fig = Figure(figsize=(7, 5), dpi=100)
    ax = _styled_axes(fig)

    if "cabangActive" not in df.columns or "daysActive" not in df.columns:
        ax.text(0.5, 0.5, "Stage 12.5 belum jalan — run pipeline dulu",
                ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    if "NAMA RESTO" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data NAMA RESTO", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Aggregate per item (1 row per NAMA BARANG)
    item_df = df.drop_duplicates(subset=["NAMA BARANG"]).copy() if "NAMA BARANG" in df.columns else df.copy()
    total_cabang = df["NAMA RESTO"].nunique()
    if total_cabang == 0:
        ax.text(0.5, 0.5, "Tidak ada cabang", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Compute prevalence & persistence (kalau belum ada dari stage 12.6)
    if "_prevalence" not in item_df.columns:
        item_df["_prevalence"] = item_df["cabangActive"] / total_cabang
    if "_persistence" not in item_df.columns:
        # daysActive / KeyAkhir — pakai 31 sebagai default
        item_df["_persistence"] = item_df["daysActive"].fillna(0) / 31

    # Colors per quadrant
    quadrant_colors = {
        "SISTEMIK": "#dc2626",      # red
        "MUSIMAN": "#ea580c",       # orange
        "LOKAL-KRONIS": "#9333ea",  # purple
        "INSIDEN": "#16a34a",       # green
    }
    quadrant_labels = {
        "SISTEMIK": "Sistemik (recipe problem)",
        "MUSIMAN": "Musiman (seasonal)",
        "LOKAL-KRONIS": "Lokal-Kronis (1 outlet recurring)",
        "INSIDEN": "Insiden (one-off)",
    }

    # Determine quadrant per item
    def _get_quadrant(row):
        p = row["_prevalence"]
        s = row["_persistence"]
        if "QUADRANT" in row and pd.notna(row.get("QUADRANT")):
            return row["QUADRANT"]
        if p >= threshold and s >= threshold:
            return "SISTEMIK"
        if p >= threshold and s < threshold:
            return "MUSIMAN"
        if p < threshold and s >= threshold:
            return "LOKAL-KRONIS"
        return "INSIDEN"
    item_df["_quadrant"] = item_df.apply(_get_quadrant, axis=1)

    # Bubble sizes (normalize totalWaste ke 20-200 range)
    if "totalWaste" in item_df.columns:
        tw = item_df["totalWaste"].fillna(0)
        if tw.max() > 0:
            item_df["_size"] = 20 + (tw / tw.max() * 180)
        else:
            item_df["_size"] = 50
    else:
        item_df["_size"] = 50

    # Plot each quadrant — Pattern C: wrap long legend labels with fmt_reason
    for quad, color in quadrant_colors.items():
        sub = item_df[item_df["_quadrant"] == quad]
        if sub.empty:
            continue
        ax.scatter(
            sub["_prevalence"] * 100, sub["_persistence"] * 100,
            s=sub["_size"], c=color, alpha=0.65,
            edgecolors="white", linewidth=1.5,
            label=fmt_reason(quadrant_labels[quad], width=30),
        )

    # Threshold reference lines
    ax.axvline(threshold * 100, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.6)
    ax.axhline(threshold * 100, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.6)

    # Annotate top 5 items by totalWaste — very short labels, adjust position to stay in plot
    if "NAMA BARANG" in item_df.columns and "totalWaste" in item_df.columns:
        top_items = item_df.nlargest(5, "totalWaste")
        for _, row in top_items.iterrows():
            name = str(row["NAMA BARANG"])[:8]
            x_pos = row["_prevalence"] * 100
            y_pos = row["_persistence"] * 100
            # If point is near right edge, place label to the LEFT; else to the right
            if x_pos > 70:
                xytext = (-25, 10)
                ha = "right"
            else:
                xytext = (12, 10)
                ha = "left"
            ax.annotate(
                name,
                (x_pos, y_pos),
                xytext=xytext, textcoords="offset points",
                fontsize=6, color="#0f172a", fontweight="bold",
                ha=ha,
                arrowprops=dict(arrowstyle="-", color="#94a3b8", lw=0.5),
            )

    ax.set_xlabel("Prevalence (% cabang yang punya waste)", fontsize=9)
    ax.set_ylabel("Persistence (% hari aktif)", fontsize=9)
    ax.set_title("Quadrant: Sistemik vs Insiden", pad=10)
    ax.set_xlim(-5, 115)  # extra right margin for annotations
    ax.set_ylim(-5, 115)
    # Pattern B: legend truly outside, right side
    place_legend_outside(ax, loc="center left", bbox_to_anchor=(1.02, 0.5))
    apply_layout(fig, ax, left_pad=0.12, bottom_pad=0.12, right_pad=0.65, top_pad=0.88)
    return fig


# ============================================================
# RATE LEAGUE CHART (NEW v2.3.0) — Ranking waste/BOM per bahan
# ============================================================

def chart_rate_league(
    df: pd.DataFrame,
    top_n: int = 15,
) -> Figure:
    """Horizontal bar: ranking waste_qty/BOM per item.
    Items with waste rate >= 5% dianggap 'blatant'.
    """
    # Pattern G: dynamic figsize based on top_n
    fig_w, fig_h = dynamic_figsize(top_n, base_w=7.0, per_item_h=0.42, min_h=4.5, max_h=14.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA BARANG" not in df.columns or "TOTAL BOM" not in df.columns or "TOTAL" not in df.columns:
        ax.text(0.5, 0.5, "Butuh kolom TOTAL BOM + TOTAL", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Aggregate per item: total waste, total BOM
    item_agg = df.groupby("NAMA BARANG", dropna=False).agg(
        total_waste=("TOTAL", "sum"),
        total_bom=("TOTAL BOM", "sum"),
        cabang_count=("NAMA RESTO", "nunique"),
    ).reset_index()

    # Filter: BOM > 0 (otherwise rate undefined)
    item_agg = item_agg[item_agg["total_bom"] > 0]
    if item_agg.empty:
        ax.text(0.5, 0.5, "Tidak ada item dengan BOM > 0", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Compute waste rate
    item_agg["waste_rate"] = item_agg["total_waste"] / item_agg["total_bom"] * 100  # %

    # Sort by waste rate, take top N
    item_agg = item_agg.sort_values("waste_rate", ascending=True).tail(top_n)

    # Color: >= 5% red (blatant), >= 1% orange (warning), < 1% green
    colors = []
    for rate in item_agg["waste_rate"]:
        if rate >= 5:
            colors.append("#dc2626")
        elif rate >= 1:
            colors.append("#ea580c")
        else:
            colors.append("#16a34a")

    # Pattern C: wrap long item names with fmt_item
    item_labels = [fmt_item(name) for name in item_agg["NAMA BARANG"].astype(str)]
    bars = ax.barh(
        item_labels,
        item_agg["waste_rate"],
        color=colors, edgecolor="white", linewidth=1.5,
    )
    # Pattern D: data labels with short-formatted numbers
    for bar, val, bom, wst in zip(bars, item_agg["waste_rate"], item_agg["total_bom"], item_agg["total_waste"]):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f" {val:.1f}% (waste {fmt_number_short(wst)} / bom {fmt_number_short(bom)})",
                ha="left", va="center", fontsize=7, fontweight="bold", color="#0f172a")

    # Reference line at 5%
    ax.axvline(5, color="#dc2626", linestyle="--", linewidth=1, alpha=0.6, label="5% threshold (blatant)")
    ax.axvline(1, color="#ea580c", linestyle="--", linewidth=0.8, alpha=0.5, label="1% threshold (warning)")

    ax.set_xlabel("Waste Rate (%) = Waste Qty / BOM Qty × 100", fontsize=9)
    ax.set_title(f"Top {top_n} Waste Rate League — per bahan", pad=10)
    # Pattern D: extra headroom for long "(waste X / bom Y)" labels
    add_xlim_headroom(ax, factor=1.25, side="right")
    # Pattern A + B: legend outside + bottom padding + left padding for wrapped items
    apply_layout(fig, ax, legend_outside=True, bottom_pad=0.16,
                 left_pad=0.30, right_pad=0.75, top_pad=0.88)
    return fig


# ============================================================
# FINGERPRINT CHART (NEW v2.3.0) — W/S/T distribution per item class
# ============================================================

def chart_fingerprint_distribution(
    df: pd.DataFrame,
) -> Figure:
    """Bar chart: distribusi item per FINGERPRINT CLASS (W/S/T-DOMINANT)."""
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "FINGERPRINT CLASS" not in df.columns:
        ax.text(0.5, 0.5, "Stage 12.5 belum jalan — run pipeline dulu",
                ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df.drop_duplicates(subset=["NAMA BARANG"])["FINGERPRINT CLASS"].value_counts(dropna=False)
    # Order: W-DOMINANT, S-DOMINANT, T-DOMINANT, None
    order = ["W-DOMINANT", "S-DOMINANT", "T-DOMINANT", None]
    labels = ["W-DOMINANT\n(waste/prep)", "S-DOMINANT\n(susut/cold-chain)", "T-DOMINANT\n(trial/R&D)", "TANPA\nEXPLAINED"]
    counts = counts.reindex([c for c in order if c in counts.index or c is None])
    # Handle None → TANPA EXPLAINED
    if None in counts.index:
        counts = counts.rename(index={None: "TANPA EXPLAINED"})

    colors = ["#dc2626", "#0f766e", "#9333ea", "#94a3b8"]
    bars = ax.bar(range(len(counts)), counts.values, color=colors[:len(counts)],
                   edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, counts.values):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{int(val)}", ha="center", va="bottom", fontsize=10,
                    fontweight="bold", color="#0f172a")
    ax.set_xticks(range(len(counts)))
    ax.set_xticklabels(labels[:len(counts)], fontsize=8)
    ax.set_ylabel("Jumlah Item", fontsize=9)
    ax.set_title("Waste Fingerprint — Distribusi per Class", pad=10)
    # Pattern D: headroom for top data labels
    add_ylim_headroom(ax)
    # Pattern A + H: margins + labelpad
    apply_layout(fig, ax, left_pad=0.14, bottom_pad=0.18, top_pad=0.88)
    return fig
