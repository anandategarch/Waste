"""
dashboard.py — chart interaktif untuk drill-down.

Setiap chart adalah InteractiveChart class yang:
1. Render figure matplotlib
2. Tangkap event klik (button_press_event)
3. Emit filter signal ke callback
4. Highlight bar yang di-klik

Pola: user klik bar/slice → callback update filter → UI refresh table + re-render charts lain

Kontrak return (FIX-DASH):
- Chart interaktif (punya param on_click) → tuple (Figure, on_click);
  on_click adalah callback yang ter-wire (None kalau pemanggil tidak memberikan).
- Chart komparasi / quadrant / fingerprint / rate-league → Figure saja.
"""

from __future__ import annotations

from typing import Callable

# NOTE: backend diset di ui_app.py (matplotlib.use("TkAgg")) sebelum import dashboard
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Patch

# Import palette dari charts.py
from .charts import (
    PALETTE_STATUS, PALETTE_ACCENT, PALETTE_SECONDARY, PALETTE_NEUTRAL,
)

# JENIS_COLORS: mapping warna stabil per-JENIS (milik charts.py; agent charts.py
# menambahkannya secara concurrent). Fallback lokal supaya modul ini tetap
# importable sebelum charts.py diperbarui — nilai HARUS sinkron dengan charts.py.
try:
    from .charts import JENIS_COLORS
except ImportError:  # charts.py belum punya JENIS_COLORS (in-flight)
    JENIS_COLORS = {"WASTE": "#dc2626", "SUSUT": "#0f766e", "TRIAL": "#b45309", "LAINNYA": "#64748b"}

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
    fmt_number_short,
)


FilterCallback = Callable[[str, str | None], None]
"""Callback signature: (filter_key, value) -> None. value=None artinya clear filter."""


# ============================================================
# HELPER: build ax with consistent style
# ============================================================

def _styled_axes(fig: Figure, *subplot_args):
    # *subplot_args diteruskan ke fig.add_subplot (mis. 3, 2, i+1 untuk grid
    # small-multiples di chart_compare_score); tanpa argumen tetap add_subplot(111)
    # sehingga semua call-site lama kompatibel.
    ax = fig.add_subplot(*subplot_args) if subplot_args else fig.add_subplot(111)
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
    """Set title on existing legend (place_legend_outside doesn't preserve it).

    NOTE (L3): sengaja duplikat dengan charts.py:_restore_legend_title — charts.py
    di luar wewenang agent ini; saat refactor berikutnya naikkan ke chart_helpers.py
    supaya single-source.
    """
    if not title:
        return
    leg = ax.get_legend()
    if leg is not None:
        leg.set_title(title)


def _connect_click(fig: Figure, handler: Callable) -> None:
    """Connect 'button_press_event' dan simpan cid di fig._waste_cids (fix M9).

    Tanpa ini, cid hasil mpl_connect tidak pernah disimpan/di-disconnect →
    listener bocor pada setiap re-render. Teardown (ui_app.py) bisa memutus
    semua listener sebuah figure dengan::

        for cid in getattr(fig, "_waste_cids", []):
            fig.canvas.mpl_disconnect(cid)
    """
    cid = fig.canvas.mpl_connect("button_press_event", handler)
    cids = getattr(fig, "_waste_cids", None)
    if cids is None:
        cids = []
        fig._waste_cids = cids
    cids.append(cid)


def _cabang_figwidth(n_cabangs: int) -> float:
    """Lebar figure untuk bar-chart per-cabang — satu sumber di dashboard.py (fix L16).

    charts.py (tab statis, line ~172) memakai formula lain untuk chart type yang
    sama (max(7, min(14, 0.5n+3)) + tinggi 4.5). charts.py off-limits untuk agent
    ini, jadi dashboard.py menyatu ke konvensinya sendiri: grid interaktif lebih
    compact — koefisien 0.4, cap 12.0, tinggi 3.5. Perbedaan disengaja & didokumentasikan
    di sini supaya tidak dianggap drift tak sengaja.
    """
    return max(6.0, min(12.0, 0.4 * n_cabangs + 3))


# ============================================================
# INTERACTIVE: Bar chart — click bar to filter by that value
# ============================================================

def chart_status_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> tuple[Figure, FilterCallback | None]:
    """Bar chart distribusi ANOMALY STATUS. Klik bar → filter by status.

    Return: (Figure, on_click) — on_click adalah callback ter-wire
    (None kalau pemanggil tidak memberikan callback).
    """
    fig = Figure(figsize=(5.5, 3.2), dpi=100)
    ax = _styled_axes(fig)

    if "ANOMALY STATUS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    counts = df["ANOMALY STATUS"].value_counts()
    # H3: jangan buang status non-canonical (mis. "UNKNOWN") — status tak
    # dikenal tetap ditampilkan dengan warna netral (PALETTE_NEUTRAL),
    # konsisten dengan fix chart status di charts.py.
    order = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    counts = counts[counts.index.notna()]
    unknown = sorted(s for s in counts.index if s not in order)
    counts = counts.reindex([s for s in order if s in counts.index] + unknown).fillna(0).astype(int)

    # Highlight active filter
    active_val = active_filter[1] if active_filter and active_filter[0] == "status" else None
    colors = []
    for s in counts.index:
        base = PALETTE_STATUS.get(s, PALETTE_NEUTRAL)
        if active_val and s != active_val:
            base = "#cbd5e1"  # gray out non-active
        colors.append(base)

    # C1: plot positionally — label hanya untuk display, bukan koordinat,
    # supaya label duplikat tidak membuat bar menumpuk di satu posisi.
    x = np.arange(len(counts))
    bars = ax.bar(x, counts.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(counts.index.astype(str), fontsize=8)
    for bar, val in zip(bars, counts.values):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{int(val)}", ha="center", va="bottom", fontsize=9,
                    fontweight="bold", color="#0f172a")
    ax.set_title("Klik Bar untuk Filter Status", pad=10)
    ax.set_ylabel("Jumlah Baris")
    # Pattern D: headroom so data labels don't clip
    add_ylim_headroom(ax)
    # Pattern A + E: rotate status labels (they're long like "Prioritas Tinggi")
    apply_layout(fig, ax, rotate_x=True, rotation=20, bottom_pad=0.22, top_pad=0.88)

    # Wire click event (M9: cid disimpan di fig._waste_cids)
    if on_click:
        def _on_pick(event):
            for i, bar in enumerate(bars):
                if bar.contains(event)[0]:
                    val = counts.index[i]
                    new_val = None if active_val == val else val
                    on_click("status", new_val)
                    return
        _connect_click(fig, _on_pick)

    return fig, on_click


# ============================================================
# INTERACTIVE: Waste per Cabang bar — click to filter
# ============================================================

def chart_cabang_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> tuple[Figure, FilterCallback | None]:
    """Bar chart waste per NAMA RESTO. Klik bar → filter by cabang.

    Return: (Figure, on_click).
    """
    # Pattern G + L16: lebar dinamis via helper terpusat (konsisten internal)
    n_cabangs = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 5
    fig = Figure(figsize=(_cabang_figwidth(n_cabangs), 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    # H4: dropna=True — grup NaN membuat bar "nan" yang bila diklik memancarkan
    # on_click("cabang", nan) → filter match 0 baris → dashboard blank.
    g = df.groupby("NAMA RESTO", dropna=True)["TOTAL"].sum().sort_values(ascending=False)
    if g.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click
    active_val = active_filter[1] if active_filter and active_filter[0] == "cabang" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_ACCENT)

    # Pattern C: abbreviate cabang codes.
    # C1: bar diposisikan dengan np.arange — fmt_cabang bisa menghasilkan label
    # display duplikat (mis. banyak "B.10xx.ABCDEFGH…" → "ABCDEFG..."); karena
    # label tidak lagi dipakai sebagai koordinat, tiap bar punya posisi sendiri.
    # Click-mapping tetap urut: bar ke-i ↔ g.index[i].
    cabang_labels = [fmt_cabang(str(c)) for c in g.index]
    x = np.arange(len(g))
    bars = ax.bar(x, g.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(cabang_labels, fontsize=8)
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
            for i, bar in enumerate(bars):  # bar ke-i ↔ g.index[i] (C1)
                if bar.contains(event)[0]:
                    val = g.index[i]
                    new_val = None if active_val == val else val
                    on_click("cabang", new_val)
                    return
        _connect_click(fig, _on_pick)
    return fig, on_click


# ============================================================
# INTERACTIVE: Top items horizontal bar — click to filter
# ============================================================

def chart_top_items_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
    top_n: int = 10,
) -> tuple[Figure, FilterCallback | None]:
    """Horizontal bar top items. Klik → filter by NAMA BARANG.

    Return: (Figure, on_click).
    """
    # Pattern G: dynamic figsize based on number of items
    fig_w, fig_h = dynamic_figsize(top_n, base_w=6.0, per_item_h=0.4, min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    # H4: dropna=True — grup item NaN menghasilkan bar "nan" yang bila diklik
    # memancarkan on_click("item", nan) → filter 0 baris.
    g = (df.groupby("NAMA BARANG", dropna=True)["TOTAL"].sum()
         .sort_values(ascending=True).tail(top_n))
    if g.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click
    active_val = active_filter[1] if active_filter and active_filter[0] == "item" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_SECONDARY)

    # Pattern C: wrap long item names.
    # C1: posisi barh pakai np.arange — fmt_item bisa menghasilkan label
    # duplikat setelah wrap/truncate; label display ≠ koordinat.
    # Click-mapping tetap urut: bar ke-i ↔ g.index[i].
    item_labels = [fmt_item(name) for name in g.index.astype(str)]
    y = np.arange(len(g))
    bars = ax.barh(y, g.values, color=colors,
                   edgecolor="white", linewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(item_labels, fontsize=8)
    # Pattern D: data labels with short format
    for bar, val in zip(bars, g.values):
        if val > 0:
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
            for i, bar in enumerate(bars):  # bar ke-i ↔ g.index[i] (C1)
                if bar.contains(event)[0]:
                    val = g.index[i]
                    new_val = None if active_val == val else val
                    on_click("item", new_val)
                    return
        _connect_click(fig, _on_pick)
    return fig, on_click


# ============================================================
# INTERACTIVE: Pareto KETERANGAN — click to filter
# ============================================================

def chart_keterangan_bar_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
    top_n: int = 12,
) -> tuple[Figure, FilterCallback | None]:
    """Bar chart TOTAL per KETERANGAN (top N). Klik → filter.

    Return: (Figure, on_click).
    """
    fig = Figure(figsize=(7, 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    # H4: dropna=True — hindari bar "nan" + klik yang mem-filter 0 baris.
    g = (df.groupby("KETERANGAN", dropna=True)["TOTAL"].sum()
         .sort_values(ascending=False).head(top_n))
    if g.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click
    active_val = active_filter[1] if active_filter and active_filter[0] == "keterangan" else None

    colors = []
    for c in g.index:
        if active_val and c != active_val:
            colors.append("#cbd5e1")
        else:
            colors.append(PALETTE_ACCENT)

    # C1: posisi bar sudah pakai range(len(g)) — urutan bar ↔ g.index terjaga.
    bars = ax.bar(range(len(g)), g.values, color=colors,
                  edgecolor="white", linewidth=1.5)
    ax.set_xticks(range(len(g)))
    # Pattern C: wrap long KETERANGAN reasons
    ax.set_xticklabels([fmt_reason(str(k)) for k in g.index], fontsize=8)
    # Pattern D: data labels with short format
    for i, val in enumerate(g.values):
        if val > 0:
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
        _connect_click(fig, _on_pick)
    return fig, on_click


# ============================================================
# INTERACTIVE: JENIS donut — click to filter
# ============================================================

def chart_jenis_donut_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> tuple[Figure, FilterCallback | None]:
    """Donut JENIS. Klik slice → filter by JENIS.

    Return: (Figure, on_click).
    """
    fig = Figure(figsize=(4.5, 3.2), dpi=100)
    ax = fig.add_subplot(111)

    if "JENIS" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    counts = df["JENIS"].value_counts()
    active_val = active_filter[1] if active_filter and active_filter[0] == "jenis" else None

    colors = []
    for j in counts.index:
        # H5: warna JENIS stabil via JENIS_COLORS (charts.py) — hash(str(j))
        # tidak stabil antar-run (PYTHONHASHSEED), bisa collision, dan tak
        # konsisten dengan tab statis. JENIS tak dikenal → LAINNYA/netral.
        base = JENIS_COLORS.get(str(j), JENIS_COLORS.get("LAINNYA", "#64748b"))
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
        _connect_click(fig, _on_pick)
    return fig, on_click


# ============================================================
# INTERACTIVE: Score per Cabang — click to filter
# ============================================================

def chart_score_per_cabang_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> tuple[Figure, FilterCallback | None]:
    """Grouped bar avg & max score per cabang. Return: (Figure, on_click)."""
    # L16: lebar dinamis via helper terpusat — chart type per-cabang yang sama
    # dengan chart_cabang_bar_interactive, jadi formula-nya disatukan.
    n_cabangs = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 5
    fig = Figure(figsize=(_cabang_figwidth(n_cabangs), 3.5), dpi=100)
    ax = _styled_axes(fig)

    if "NAMA RESTO" not in df.columns or "ANOMALY SCORE" not in df.columns or df.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click

    # H4: dropna=True — grup NaN cabang → klik mem-filter 0 baris.
    g = df.groupby("NAMA RESTO", dropna=True)["ANOMALY SCORE"].agg(["mean", "max"]).reset_index()
    g = g.sort_values("max", ascending=False)
    if g.empty:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig, on_click
    active_val = active_filter[1] if active_filter and active_filter[0] == "cabang" else None

    x = np.arange(len(g))
    w = 0.35
    colors_avg = ["#cbd5e1" if (active_val and c != active_val) else PALETTE_ACCENT for c in g["NAMA RESTO"]]
    colors_max = ["#cbd5e1" if (active_val and c != active_val) else PALETTE_SECONDARY for c in g["NAMA RESTO"]]

    b1 = ax.bar(x - w/2, g["mean"], w, label="Rata-rata", color=colors_avg, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, g["max"], w, label="Max", color=colors_max, edgecolor="white", linewidth=1.5)
    ax.set_xticks(x)
    # Pattern C: abbreviate cabang codes — C1: sudah positional (np.arange),
    # label duplikat dari fmt_cabang tidak menumpuk bar.
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
        _connect_click(fig, _on_pick)
    return fig, on_click


def chart_avg_per_cabang_interactive(
    df: pd.DataFrame,
    on_click: FilterCallback | None = None,
    active_filter: tuple[str, str | None] | None = None,
) -> tuple[Figure, FilterCallback | None]:
    """Alias publik untuk chart_score_per_cabang_interactive.

    Nama alternatif untuk wiring UI / smoke test; perilaku & return kontrak sama:
    (Figure, on_click).
    """
    return chart_score_per_cabang_interactive(df, on_click=on_click, active_filter=active_filter)


# ============================================================
# COMPARISON CHARTS — 2 cabang side-by-side
# ============================================================

def _compare_subsets(
    df: pd.DataFrame,
    cabang_a: str | pd.DataFrame,
    cabang_b: str | None,
    b_label: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """Resolve argumen chart komparasi → (a_sub, b_sub, label_a, label_b).

    Dua mode panggilan (keduanya backward-compatible):
    1. Legacy (ui_app.py): (df, cabang_a, cabang_b) — cabang_a/cabang_b string
       nama cabang; subset difilter dari df lewat NAMA RESTO. b_label (opsional)
       mengoverride legend label B.
    2. Dua-subset: (df_a, df_b, label_a, label_b) — cabang_a berupa DataFrame
       (data B), cabang_b menjadi label A, b_label label B. Memungkinkan
       perbandingan dua view/filter apa pun, bukan hanya 2 cabang dalam 1 df.
    """
    if isinstance(cabang_a, pd.DataFrame):
        a_sub = df
        b_sub = cabang_a
        label_a = str(cabang_b) if cabang_b is not None else "A"
        label_b = str(b_label) if b_label is not None else "B"
    else:
        if "NAMA RESTO" in df.columns:
            a_sub = df[df["NAMA RESTO"] == cabang_a]
            b_sub = df[df["NAMA RESTO"] == cabang_b] if cabang_b is not None else df.iloc[0:0]
        else:
            a_sub = df.iloc[0:0]
            b_sub = df.iloc[0:0]
        label_a = str(cabang_a)
        label_b = str(b_label) if b_label is not None else str(cabang_b)
    return a_sub, b_sub, label_a, label_b


def chart_compare_total_waste(
    df: pd.DataFrame,
    cabang_a: str | pd.DataFrame,
    cabang_b: str | None = None,
    b_label: str | None = None,
) -> Figure:
    """Side-by-side bar: total waste per JENIS for 2 cabang.

    Mode panggilan (lihat _compare_subsets): legacy (df, cabang_a, cabang_b)
    atau dua-subset (df_a, df_b, label_a, label_b).

    M12: kategori JENIS diturunkan dari data — urutan dikenal
    (WASTE/SUSUT/TRIAL) di dulu, lalu JENIS lain yang benar-benar muncul di
    salah satu cabang (sorted) — bukan list hardcoded 3 kategori.
    """
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    two_df_mode = isinstance(cabang_a, pd.DataFrame)
    if ((not two_df_mode and "NAMA RESTO" not in df.columns)
            or "TOTAL" not in df.columns or "JENIS" not in df.columns):
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Resolve subsets (legacy 2-cabang atau dua-subset) lalu group by JENIS
    a_sub, b_sub, label_a, label_b = _compare_subsets(df, cabang_a, cabang_b, b_label)
    if a_sub.empty and b_sub.empty:
        ax.text(0.5, 0.5, "Tidak ada data untuk kedua cabang", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    known_jenis = ["WASTE", "SUSUT", "TRIAL"]
    present = set(a_sub["JENIS"].dropna()) | set(b_sub["JENIS"].dropna())
    jenis_list = [j for j in known_jenis if j in present] + sorted(present - set(known_jenis))
    if not jenis_list:
        ax.text(0.5, 0.5, "Tidak ada data JENIS", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig
    a_map = a_sub.groupby("JENIS")["TOTAL"].sum()
    b_map = b_sub.groupby("JENIS")["TOTAL"].sum()
    a_vals = [float(a_map.get(j, 0.0)) for j in jenis_list]
    b_vals = [float(b_map.get(j, 0.0)) for j in jenis_list]

    x = np.arange(len(jenis_list))
    w = 0.38
    b1 = ax.bar(x - w/2, a_vals, w, label=label_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, b_vals, w, label=label_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    # Pattern D: data labels with short format — L5: skip label nol
    # (dulu chart ini menggambar "0" di bar kosong, tidak konsisten dengan
    # chart_compare_status yang skip nol)
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
    ax.set_xticklabels(jenis_list)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Total Waste per JENIS — {label_a} vs {label_b}"), pad=10)
    ax.set_ylabel("Total Waste")
    # Pattern D: headroom for data labels
    add_ylim_headroom(ax)
    # Pattern A + B: margins + legend outside
    apply_layout(fig, ax, legend_outside=True, bottom_pad=0.18, right_pad=0.75, top_pad=0.85)
    return fig


def chart_compare_status(
    df: pd.DataFrame,
    cabang_a: str | pd.DataFrame,
    cabang_b: str | None = None,
    b_label: str | None = None,
) -> Figure:
    """Grouped bar: status anomali count for 2 cabang.

    Mode panggilan (lihat _compare_subsets): legacy (df, cabang_a, cabang_b)
    atau dua-subset (df_a, df_b, label_a, label_b).
    """
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    two_df_mode = isinstance(cabang_a, pd.DataFrame)
    if (not two_df_mode and "NAMA RESTO" not in df.columns) or "ANOMALY STATUS" not in df.columns:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    statuses = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
    a_sub, b_sub, label_a, label_b = _compare_subsets(df, cabang_a, cabang_b, b_label)
    a_vals = [int((a_sub["ANOMALY STATUS"] == s).sum()) for s in statuses]
    b_vals = [int((b_sub["ANOMALY STATUS"] == s).sum()) for s in statuses]

    x = np.arange(len(statuses))
    w = 0.38
    b1 = ax.bar(x - w/2, a_vals, w, label=label_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.bar(x + w/2, b_vals, w, label=label_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
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
    ax.set_title(_wrap_title(f"Status Anomali — {label_a} vs {label_b}"), pad=10)
    ax.set_ylabel("Jumlah Baris")
    # Pattern D: headroom
    add_ylim_headroom(ax)
    # Pattern A + B + E: rotation + legend outside + margins
    apply_layout(fig, ax, rotate_x=True, rotation=15, legend_outside=True,
                 bottom_pad=0.22, right_pad=0.75, top_pad=0.85)
    return fig


def chart_compare_top_items(
    df: pd.DataFrame,
    cabang_a: str | pd.DataFrame,
    cabang_b: str | None = None,
    b_label: str | None = None,
    top_n: int = 8,
) -> Figure:
    """Horizontal grouped bar: top items by total waste, A vs B side-by-side.

    Mode panggilan (lihat _compare_subsets): legacy (df, cabang_a, cabang_b)
    atau dua-subset (df_a, df_b, label_a, label_b). b_label sengaja di depan
    top_n supaya arg posisi ke-4 = label B (konvensi mode dua-subset).
    """
    # Pattern G: dynamic figsize based on top_n
    fig_w, fig_h = dynamic_figsize(top_n, base_w=7.0, per_item_h=0.45, min_h=4.0, max_h=10.0)
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    ax = _styled_axes(fig)

    two_df_mode = isinstance(cabang_a, pd.DataFrame)
    if ((not two_df_mode and "NAMA RESTO" not in df.columns)
            or "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns):
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Get all unique items from both cabangs
    # H4 (konsistensi): dropna=True — item NaN tidak berguna untuk drill-down &
    # menghasilkan tick "nan".
    a_sub, b_sub, label_a, label_b = _compare_subsets(df, cabang_a, cabang_b, b_label)
    items_a = a_sub.groupby("NAMA BARANG", dropna=True)["TOTAL"].sum()
    items_b = b_sub.groupby("NAMA BARANG", dropna=True)["TOTAL"].sum()
    all_items = items_a.add(items_b, fill_value=0).sort_values(ascending=True).tail(top_n)
    a_vals = [float(items_a.get(i, 0)) for i in all_items.index]
    b_vals = [float(items_b.get(i, 0)) for i in all_items.index]

    y = np.arange(len(all_items))
    h = 0.38
    b1 = ax.barh(y - h/2, a_vals, h, label=label_a, color=PALETTE_ACCENT, edgecolor="white", linewidth=1.5)
    b2 = ax.barh(y + h/2, b_vals, h, label=label_b, color=PALETTE_SECONDARY, edgecolor="white", linewidth=1.5)
    ax.set_yticks(y)
    # Pattern C: wrap long item names
    ax.set_yticklabels([fmt_item(str(name)) for name in all_items.index], fontsize=8)
    # L5/L6: value labels — chart ini dulu tanpa label sama sekali (inconsistent
    # dengan chart compare lain); skip label nol untuk konsistensi.
    for bar, val in zip(b1, a_vals):
        if val > 0:
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                    f" {fmt_number_short(val)}", ha="left", va="center", fontsize=8,
                    fontweight="bold", color=PALETTE_ACCENT)
    for bar, val in zip(b2, b_vals):
        if val > 0:
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                    f" {fmt_number_short(val)}", ha="left", va="center", fontsize=8,
                    fontweight="bold", color=PALETTE_SECONDARY)
    # Pattern C: wrap long title with cabang names
    ax.set_title(_wrap_title(f"Top {top_n} Item — {label_a} vs {label_b}"), pad=10)
    ax.set_xlabel("Total Waste")
    # Pattern D: headroom for data labels
    add_xlim_headroom(ax, factor=1.10, side="right")
    # Pattern A + B: legend outside + left padding for wrapped labels
    apply_layout(fig, ax, legend_outside=True, left_pad=0.30, bottom_pad=0.12,
                 right_pad=0.75, top_pad=0.88)
    return fig


def chart_compare_score(
    df: pd.DataFrame,
    cabang_a: str | pd.DataFrame,
    cabang_b: str | None = None,
    b_label: str | None = None,
) -> Figure:
    """Small-multiples comparison (fix H1): 2 kolom × 3 baris mini-subplot.

    Dulu semua metrik (score 0-19, waste qty ribuan, count) dicampur di satu
    sumbu-y linear → tidak terbaca. Sekarang tiap metrik punya subplot + skala
    sendiri: Avg Score, Max Score, Avg Waste, Max Waste, Jml Prioritas,
    Jml Item — masing-masing 2 bar (A vs B) dengan label nilai asli.
    Return tetap Figure (kontrak chart komparasi).

    Mode panggilan (lihat _compare_subsets): legacy (df, cabang_a, cabang_b)
    atau dua-subset (df_a, df_b, label_a, label_b).
    """
    two_df_mode = isinstance(cabang_a, pd.DataFrame)
    if not two_df_mode and "NAMA RESTO" not in df.columns:
        fig = Figure(figsize=(5.5, 3.5), dpi=100)
        ax = _styled_axes(fig)
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    a_sub, b_sub, label_a, label_b = _compare_subsets(df, cabang_a, cabang_b, b_label)
    if a_sub.empty and b_sub.empty:
        fig = Figure(figsize=(5.5, 3.5), dpi=100)
        ax = _styled_axes(fig)
        ax.text(0.5, 0.5, "Tidak ada data untuk kedua cabang", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    def _num(sub: pd.DataFrame, col: str, how: str) -> float:
        """Aggregate aman: kolom hilang / sub kosong / hasil NaN → 0.0."""
        if col not in sub.columns or sub.empty:
            return 0.0
        val = sub[col].nunique() if how == "nunique" else sub[col].agg(how)
        return float(val) if pd.notna(val) else 0.0

    def _prioritas(sub: pd.DataFrame) -> float:
        if "ANOMALY STATUS" not in sub.columns:
            return 0.0
        return float((sub["ANOMALY STATUS"] == "Prioritas Tinggi").sum())

    # (nama metrik, ylabel/satuan, nilai A, nilai B, formatter label)
    metrics: list[tuple[str, str, float, float, Callable[[float], str]]] = [
        ("Avg Score", "Score (rata-rata)",
         _num(a_sub, "ANOMALY SCORE", "mean"), _num(b_sub, "ANOMALY SCORE", "mean"),
         lambda v: f"{v:.1f}"),
        ("Max Score", "Score (maksimum)",
         _num(a_sub, "ANOMALY SCORE", "max"), _num(b_sub, "ANOMALY SCORE", "max"),
         lambda v: f"{v:.1f}"),
        ("Avg Waste", "TOTAL per baris",
         _num(a_sub, "TOTAL", "mean"), _num(b_sub, "TOTAL", "mean"),
         fmt_number_short),
        ("Max Waste", "MAX harian",
         _num(a_sub, "MAX", "max"), _num(b_sub, "MAX", "max"),
         fmt_number_short),
        ("Jml Prioritas", "Baris Prioritas Tinggi",
         _prioritas(a_sub), _prioritas(b_sub),
         lambda v: f"{int(v)}"),
        ("Jml Item", "Item unik (NAMA BARANG)",
         _num(a_sub, "NAMA BARANG", "nunique"), _num(b_sub, "NAMA BARANG", "nunique"),
         lambda v: f"{int(v)}"),
    ]

    fig = Figure(figsize=(7.0, 7.5), dpi=100)
    for i, (name, unit, va, vb, fmt) in enumerate(metrics):
        ax = _styled_axes(fig, 3, 2, i + 1)
        x = np.arange(2)
        ax.bar(x, [va, vb], 0.5, color=[PALETTE_ACCENT, PALETTE_SECONDARY],
               edgecolor="white", linewidth=1.5)
        ax.set_xticks(x)
        # Pattern C: abbreviate cabang codes for the mini-subplot x labels
        ax.set_xticklabels([fmt_cabang(label_a), fmt_cabang(label_b)], fontsize=8)
        for xi, v in zip(x, [va, vb]):
            if v > 0:  # L5: skip label nol
                ax.text(xi, v, fmt(v), ha="center", va="bottom", fontsize=8,
                        fontweight="bold", color="#0f172a")
        ax.set_title(name, fontsize=9)
        ax.set_ylabel(unit, fontsize=8)  # H1: ylabel eksplisit per metrik
        # Pattern D: headroom for data labels
        add_ylim_headroom(ax)

    # Pattern C: wrap long title with cabang names
    fig.suptitle(_wrap_title(f"Metrics Comparison — {label_a} vs {label_b}"),
                 fontsize=10, fontweight="bold", color="#0f172a")
    # Legend level-figure (dua warna A vs B) supaya tiap subplot tidak perlu
    # legend sendiri.
    fig.legend(
        handles=[
            Patch(facecolor=PALETTE_ACCENT, edgecolor="white", label=label_a),
            Patch(facecolor=PALETTE_SECONDARY, edgecolor="white", label=label_b),
        ],
        loc="lower center", ncol=2, fontsize=8, frameon=True,
    )
    # Pattern A: margins — ruang untuk suptitle (atas) + legend (bawah)
    fig.tight_layout(rect=(0.02, 0.06, 0.98, 0.92))
    return fig


# ============================================================
# QUADRANT CHART (NEW v2.3.0) — Sistemik vs Insiden scatter
# ============================================================

def chart_quadrant_scatter(
    df: pd.DataFrame,
    threshold: float = 0.5,
    key_akhir: int = 31,
) -> Figure:
    """Scatter plot: X = prevalence (cabangActive/total), Y = persistence (daysActive/KeyAkhir).
    4 quadrant: SISTEMIK, MUSIMAN, LOKAL-KRONIS, INSIDEN.
    Bubble size = totalWaste.

    key_akhir (fix C4): jumlah hari periode dari pipeline (config "key_akhir").
    Persistence dihitung daysActive / max(1, key_akhir) — konsisten dengan
    stages.stage_12_6_quadrant. Default 31 hanya backward-compat; ui_app.py
    (agent lain akan wire) harus pass key_akhir asli supaya titik tidak jatuh
    di quadrant yang salah secara visual saat key_akhir != 31.
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
    # M10: drop_duplicates sudah mengembalikan salinan — .copy() redundan dihapus.
    item_df = df.drop_duplicates(subset=["NAMA BARANG"]) if "NAMA BARANG" in df.columns else df.copy()
    total_cabang = df["NAMA RESTO"].nunique()
    if total_cabang == 0:
        ax.text(0.5, 0.5, "Tidak ada cabang", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    # Compute prevalence & persistence (kalau belum ada dari stage 12.6)
    if "_prevalence" not in item_df.columns:
        item_df["_prevalence"] = item_df["cabangActive"] / total_cabang
    if "_persistence" not in item_df.columns:
        # C4: daysActive / key_akhir (bukan hardcoded /31) — dulu titik bisa
        # jatuh di quadrant salah saat key_akhir != 31. max(1, key_akhir)
        # mencegah div-by-zero.
        item_df["_persistence"] = item_df["daysActive"].fillna(0) / max(1, key_akhir)

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

    # M8 + M10: klasifikasi quadrant di-vectorize dengan np.select — semantik
    # identik dengan rule per-row stages.py stage_12.6 (p/s >= atau < threshold;
    # NaN perbandingan → False → INSIDEN, sama seperti versi row-wise).
    # M8: nilai QUADRANT tak dikenal/NaN tidak lagi menyebabkan item DIBUANG
    # (dulu 0 collection ter-plot) — fallback dihitung dari prevalence/persistence.
    p = pd.to_numeric(item_df["_prevalence"], errors="coerce").to_numpy(dtype=float)
    s = pd.to_numeric(item_df["_persistence"], errors="coerce").to_numpy(dtype=float)
    fallback = np.select(
        [(p >= threshold) & (s >= threshold),
         (p >= threshold) & (s < threshold),
         (p < threshold) & (s >= threshold)],
        ["SISTEMIK", "MUSIMAN", "LOKAL-KRONIS"],
        default="INSIDEN",
    )
    valid_quads = ["SISTEMIK", "MUSIMAN", "LOKAL-KRONIS", "INSIDEN"]
    if "QUADRANT" in item_df.columns:
        q = item_df["QUADRANT"]
        known = q.notna() & q.isin(valid_quads)
        item_df["_quadrant"] = np.where(known, q.astype(str).to_numpy(), fallback)
    else:
        item_df["_quadrant"] = fallback

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
    quads_plotted = 0
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
        quads_plotted += 1

    if quads_plotted == 0:
        ax.text(0.5, 0.5, "Tidak ada item untuk diklasifikasikan",
                ha="center", va="center", color=PALETTE_NEUTRAL)

    # Threshold reference lines
    ax.axvline(threshold * 100, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.6)
    ax.axhline(threshold * 100, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.6)

    # No annotations on scatter — the table below already lists items per quadrant.
    # Annotations on a 173-item scatter always overlap regardless of positioning.

    ax.set_xlabel("Prevalence (% cabang yang punya waste)", fontsize=9)
    ax.set_ylabel("Persistence (% hari aktif)", fontsize=9)
    ax.set_title("Quadrant: Sistemik vs Insiden", pad=10)
    ax.set_xlim(-5, 120)  # extra margin for annotations
    ax.set_ylim(-5, 120)
    # Pattern B: legend truly outside, right side.
    # M8: skip legend kalau tidak ada artist ber-label — place_legend_outside
    # mem-warning "No artists with labels" & bikin legend kosong.
    if quads_plotted > 0:
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
    """Bar chart: distribusi item per FINGERPRINT CLASS (W/S/T-DOMINANT).

    C2: label & warna bar dibangun dari kelas yang benar-benar ada di data
    (dict lookup per kelas, NaN → "TANPA EXPLAINED") — bukan slicing list
    fix-order, supaya kelas yang absen tidak menggeser label/warna bar
    berikutnya dan tidak ada phantom slot.
    """
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = _styled_axes(fig)

    # H2: guard KEDUA kolom — dulu hanya FINGERPRINT CLASS yang dicek, NAMA
    # BARANG yang hilang menyebabkan KeyError di drop_duplicates.
    if "FINGERPRINT CLASS" not in df.columns or "NAMA BARANG" not in df.columns:
        ax.text(0.5, 0.5, "Stage 12.5 belum jalan — run pipeline dulu",
                ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    counts = df.drop_duplicates(subset=["NAMA BARANG"])["FINGERPRINT CLASS"].value_counts(dropna=False)
    # Canonicalize keys: None/NaN → "TANPA EXPLAINED" (item tanpa explained
    # dari stage 12.5); kelas tak dikenal tetap ditampilkan (warna netral).
    agg: dict[str, int] = {}
    for k, v in counts.items():
        key = "TANPA EXPLAINED" if pd.isna(k) else str(k)
        agg[key] = agg.get(key, 0) + int(v)

    label_map = {
        "W-DOMINANT": "W-DOMINANT\n(waste/prep)",
        "S-DOMINANT": "S-DOMINANT\n(susut/cold-chain)",
        "T-DOMINANT": "T-DOMINANT\n(trial/R&D)",
        "TANPA EXPLAINED": "TANPA\nEXPLAINED",
    }
    color_map = {
        "W-DOMINANT": "#dc2626",
        "S-DOMINANT": "#0f766e",
        "T-DOMINANT": "#9333ea",
        "TANPA EXPLAINED": "#94a3b8",
    }
    known_order = ["W-DOMINANT", "S-DOMINANT", "T-DOMINANT", "TANPA EXPLAINED"]
    # Urutan: kelas dikenal dulu, lalu kelas tak dikenal (sorted, deterministik).
    keys = [k for k in known_order if k in agg] + sorted(k for k in agg if k not in known_order)
    if not keys:
        ax.text(0.5, 0.5, "Tidak ada data", ha="center", va="center", color=PALETTE_NEUTRAL)
        ax.set_axis_off()
        return fig

    vals = [agg[k] for k in keys]
    labels = [label_map.get(k, k) for k in keys]
    colors = [color_map.get(k, "#94a3b8") for k in keys]

    x = np.arange(len(keys))
    bars = ax.bar(x, vals, color=colors,
                   edgecolor="white", linewidth=1.5)
    for bar, val in zip(bars, vals):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{int(val)}", ha="center", va="bottom", fontsize=10,
                    fontweight="bold", color="#0f172a")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Jumlah Item", fontsize=9)
    ax.set_title("Waste Fingerprint — Distribusi per Class", pad=10)
    # Pattern D: headroom for top data labels
    add_ylim_headroom(ax)
    # Pattern A + H: margins + labelpad
    apply_layout(fig, ax, left_pad=0.14, bottom_pad=0.18, top_pad=0.88)
    return fig
