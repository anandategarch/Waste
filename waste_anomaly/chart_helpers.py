"""
chart_helpers.py — Shared utilities untuk matplotlib charts (v2.3.1).

Fix all UI/UX issues dari deep audit:
- Pattern A: Edge clipping (text cut di edges)
- Pattern B: Legend collision with data
- Pattern C: Long label handling (cabang codes + item names)
- Pattern D: Data label clipping (top of bars)
- Pattern E: Rotation issues
- Pattern F: Color contrast (adaptive text color)
- Pattern G: Chart ratio (dynamic figsize)
- Pattern H: Text too small

Usage:
    from .chart_helpers import apply_layout, fmt_cabang, fmt_item, place_legend_outside, add_ylim_headroom
"""

from __future__ import annotations

import textwrap
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure


# ============================================================
# LABEL FORMATTERS (Pattern C: Long label handling)
# ============================================================

def fmt_cabang(code: str | Any, max_len: int = 10) -> str:
    """Abbreviate cabang code to last segment after '.'.
    
    'B.1001.MLGPAR' → 'MLGPAR' (last segment)
    '1137.CKGPAH' → 'CKGPAH'
    'ShortCode' → 'ShortCode' (no change if already short)
    
    Args:
        code: cabang code string
        max_len: if last segment still longer than this, truncate with '...'
    
    Returns:
        Abbreviated cabang code
    """
    if code is None:
        return ""
    s = str(code).strip()
    if "." in s:
        last = s.rsplit(".", 1)[-1]
    else:
        last = s
    if len(last) > max_len:
        return last[:max_len - 3] + "..."
    return last


def fmt_item(name: str | Any, width: int = 20, max_lines: int = 2) -> str:
    """Wrap long item names with textwrap.
    
    'TOPPING DAUN KERING MIE - RESTO (V.20)' →
        'TOPPING DAUN KERING\nMIE - RESTO (V.20)'
    
    Preserves versioning info (V.20, V.30) which is critical for triage.
    
    Args:
        name: item name string
        width: max chars per line
        max_lines: max number of lines (excess truncated with '...')
    
    Returns:
        Wrapped item name (may contain newlines)
    """
    if name is None:
        return ""
    s = str(name).strip()
    if len(s) <= width:
        return s
    wrapped = textwrap.fill(s, width=width)
    lines = wrapped.split("\n")
    if len(lines) > max_lines:
        # Truncate to max_lines, add '...' at end of last line
        truncated = lines[:max_lines]
        last_line = truncated[-1]
        if len(last_line) > width - 3:
            last_line = last_line[:width - 3]
        truncated[-1] = last_line + "..."
        return "\n".join(truncated)
    return wrapped


def fmt_reason(text: str | Any, width: int = 25) -> str:
    """Wrap anomaly reason text for axis labels.
    
    'MAX jauh di atas AVG aktif' → 'MAX jauh di atas\nAVG aktif'
    """
    if text is None:
        return ""
    s = str(text).strip()
    if len(s) <= width:
        return s
    return textwrap.fill(s, width=width)


# ============================================================
# LAYOUT HELPERS (Pattern A: Edge clipping)
# ============================================================

def apply_layout(
    fig: Figure,
    ax,
    *,
    rotate_x: bool = False,
    rotation: int = 45,
    legend_outside: bool = False,
    top_pad: float = 0.88,
    bottom_pad: float = 0.18,
    left_pad: float = 0.14,
    right_pad: float = 0.88,
    labelpad: int = 10,
    x_fontsize: int = 8,
    y_fontsize: int = 8,
) -> None:
    """Apply standard layout fixes to a matplotlib axes.
    
    Fixes:
    - Pattern A: Edge clipping via subplots_adjust + tight_layout
    - Pattern B: Legend collision via place_legend_outside
    - Pattern E: Rotation issues via rotate_x + ha='right'
    - Pattern H: Text too small via fontsize enforcement
    
    Args:
        fig: Figure object
        ax: Axes object
        rotate_x: if True, rotate x-tick labels
        rotation: rotation angle in degrees (default 45)
        legend_outside: if True, move legend outside plot area
        top_pad: top margin (0-1)
        bottom_pad: bottom margin (0-1)
        left_pad: left margin (0-1)
        right_pad: right margin (0-1)
        labelpad: padding between axis label and ticks
        x_fontsize: minimum x-tick label font size
        y_fontsize: minimum y-tick label font size
    """
    # Pattern A: Edge clipping — apply explicit margins
    try:
        fig.subplots_adjust(
            top=top_pad, bottom=bottom_pad,
            left=left_pad, right=right_pad,
        )
    except Exception:
        pass  # fig might not support subplots_adjust in edge cases

    # Pattern E: Rotation — rotate x-tick labels if requested
    if rotate_x:
        for label in ax.get_xticklabels():
            label.set_rotation(rotation)
            label.set_horizontalalignment('right')
            label.set_rotation_mode('anchor')
        # Ensure font size is readable (Pattern H)
        ax.tick_params(axis='x', labelsize=x_fontsize)
    
    # Pattern H: Enforce minimum font size for y-ticks
    ax.tick_params(axis='y', labelsize=y_fontsize)
    
    # Pattern A: Axis label padding
    ax.xaxis.labelpad = labelpad
    ax.yaxis.labelpad = labelpad
    
    # Pattern B: Move legend outside if requested
    if legend_outside:
        place_legend_outside(ax)


def place_legend_outside(
    ax,
    loc: str = 'upper left',
    bbox_to_anchor: tuple = (1.02, 1.0),
    fontsize: int = 8,
) -> None:
    """Move legend outside the plot area to avoid covering data.
    
    Pattern B fix: legends inside plot area routinely cover high-value
    bars/scatter points. This helper standardizes the outside placement.
    
    Args:
        ax: Axes object
        loc: legend location relative to bbox_to_anchor
        bbox_to_anchor: (x, y) anchor point for legend
        fontsize: legend font size
    """
    legend = ax.legend(
        loc=loc,
        bbox_to_anchor=bbox_to_anchor,
        fontsize=fontsize,
        frameon=True,
        edgecolor='#cbd5e1',
        facecolor='white',
        framealpha=0.95,
    )
    if legend:
        legend.get_frame().set_linewidth(0.5)


def add_ylim_headroom(ax, factor: float = 1.15) -> None:
    """Add headroom above the highest bar/point for data labels.
    
    Pattern D fix: data labels (numbers above bars) get clipped at
    the top edge when ylim is set to exactly max value.
    
    Args:
        ax: Axes object
        factor: multiply current top by this factor (1.15 = 15% headroom)
    """
    ymin, ymax = ax.get_ylim()
    if ymax > 0:
        ax.set_ylim(ymin, ymax * factor)
    elif ymax < 0:
        ax.set_ylim(ymin * factor, ymax * factor)


def add_xlim_headroom(ax, factor: float = 1.10, side: str = 'right') -> None:
    """Add headroom to the right of horizontal bars for data labels.
    
    Pattern D fix: data labels at end of horizontal bars get clipped.
    
    Args:
        ax: Axes object
        factor: multiply current max by this factor
        side: 'right' or 'left'
    """
    xmin, xmax = ax.get_xlim()
    if side == 'right' and xmax > 0:
        ax.set_xlim(xmin, xmax * factor)
    elif side == 'left' and xmin < 0:
        ax.set_xlim(xmin * factor, xmax)


# ============================================================
# DYNAMIC FIGSIZE (Pattern G: Chart ratio)
# ============================================================

def dynamic_figsize(
    n_items: int,
    base_w: float = 7.0,
    per_item_h: float = 0.4,
    min_h: float = 4.0,
    max_h: float = 20.0,
) -> tuple[float, float]:
    """Calculate dynamic figure height based on number of items.
    
    Pattern G fix: fixed figsize causes cramped charts when n_items is large.
    
    Args:
        n_items: number of bars/rows in the chart
        base_w: base figure width
        per_item_h: height per item
        min_h: minimum figure height
        max_h: maximum figure height (cap for very large datasets)
    
    Returns:
        (width, height) tuple
    """
    h = max(min_h, min(max_h, base_w * 0.5 + per_item_h * n_items))
    return (base_w, h)


# ============================================================
# ADAPTIVE TEXT COLOR (Pattern F: Color contrast)
# ============================================================

def adaptive_text_color(value: float, threshold: float, cmap_max: float) -> str:
    """Choose text color based on cell value intensity.
    
    Pattern F fix: black text on dark heatmap cells is unreadable.
    
    Args:
        value: cell value
        threshold: value above which use white text (typically 60% of max)
        cmap_max: maximum value in the colormap
    
    Returns:
        'white' or 'black'
    """
    if cmap_max > 0 and value >= threshold:
        return 'white'
    return 'black'


# ============================================================
# HEATMAP PAGINATION (Pattern G: Chart ratio for large datasets)
# ============================================================

def paginate_heatmap_data(
    df_rows: int,
    df_cols: int,
    max_rows: int = 30,
    max_cols: int = 20,
) -> tuple[int, int, bool]:
    """Determine if heatmap needs pagination.
    
    For large datasets (e.g., 173 items × 20 cabangs), the heatmap is
    fundamentally unreadable. This helper decides whether to paginate
    and how many rows/cols to show.
    
    Args:
        df_rows: number of rows in pivot table (e.g., 173 items)
        df_cols: number of columns (e.g., 20 cabangs)
        max_rows: max rows before pagination kicks in
        max_cols: max cols before truncation
    
    Returns:
        (effective_rows, effective_cols, needs_pagination)
    """
    needs_pag = df_rows > max_rows or df_cols > max_cols
    eff_rows = min(df_rows, max_rows) if needs_pag else df_rows
    eff_cols = min(df_cols, max_cols) if needs_pag else df_cols
    return (eff_rows, eff_cols, needs_pag)


# ============================================================
# NUMBER FORMATTERS
# ============================================================

def fmt_number_short(val: float, decimals: int = 1) -> str:
    """Format large numbers compactly.
    
    2958646.2 → '2.96M'
    80818 → '80.8K'
    532.7 → '533'
    
    Args:
        val: numeric value
        decimals: decimal places for K/M suffix
    
    Returns:
        Formatted string
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    abs_val = abs(val)
    if abs_val >= 1_000_000:
        return f"{val / 1_000_000:.{decimals}f}M"
    elif abs_val >= 1_000:
        return f"{val / 1_000:.{decimals}f}K"
    else:
        if abs_val == int(abs_val):
            return f"{int(val)}"
        return f"{val:.{decimals}f}"


def fmt_number_comma(val: float, decimals: int = 0) -> str:
    """Format number with thousand separators.
    
    2958646 → '2,958,646'
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return f"{val:,.{decimals}f}"
