"""Tab 4 Rate League: ranking cabang by rate anomali.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BG
from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
from waste_anomaly import charts as wa_charts
from waste_anomaly import dashboard as wa_dash


class RateLeagueTabMixin:
    """Tab 4 Rate League: ranking cabang by rate anomali."""

    def _build_rate_league_tab(self, parent):
        """Tab Rate League: ranking waste_qty / BOM per bahan."""
        # L3: columnconfigure/rowconfigure parent dihapus (child tunggal di-pack)
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        # Header
        hdr = tk.Frame(inner, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(hdr, text="🏆 Rate League — Ranking Waste Rate per Bahan",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(hdr, text="Waste Rate (%) = Waste Qty / BOM Qty × 100. Adaptasi dari Inventory-Control WasteRateLeagueCard.",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 8))
        btn_frame = tk.Frame(hdr, bg=C_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="⟳ Refresh", command=self._render_rate_league).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🖼 Export PNG…", command=self._export_rate_league).pack(side="left", padx=4)
        # Top N selector — H4: StringVar + validate digits (IntVar.get() TclError)
        tk.Label(btn_frame, text="Top N:", font=F_BODY, bg=C_CARD).pack(side="left", padx=(20, 4))
        _vcmd_rl = self.register(self._digits_only)
        self.var_rate_league_top = tk.StringVar(value="15")
        _sb_top = ttk.Spinbox(btn_frame, from_=5, to=50, textvariable=self.var_rate_league_top, width=5,
                              validate="key", validatecommand=(_vcmd_rl, "%P"),
                              command=self._render_rate_league)
        _sb_top.pack(side="left", padx=4)
        _sb_top.bind("<FocusOut>", lambda e: self._render_rate_league())

        # Chart frame
        self._rate_league_chart_frame = tk.Frame(inner, bg=C_CARD, relief="flat",
                                                 highlightbackground=C_BORDER, highlightthickness=1)
        self._rate_league_chart_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self._rate_league_chart_frame.columnconfigure(0, weight=1)
        self._rate_league_chart_frame.rowconfigure(0, weight=1)

        # Placeholder
        tk.Label(self._rate_league_chart_frame, text="🏆\n\nRun pipeline untuk\nlihat Rate League",
                 font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
            row=0, column=0, sticky="nsew", padx=40, pady=40)

        self._rate_league_canvases = []


    def _render_rate_league(self):
        df = self._preview_dfs.get("Detail")
        # H3: dispose figure lama dulu (leak fix) — registry (key, fig, canvas)
        self._dispose_chart_registry(self._rate_league_canvases)
        self._rate_league_canvases = []
        for c in self._rate_league_chart_frame.winfo_children():
            c.destroy()

        if df is None or df.empty:
            tk.Label(self._rate_league_chart_frame, text="(belum ada data — run pipeline dulu)",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=40, pady=40)
            return

        # H4: parse aman — nilai kosong/non-int tidak lagi raise TclError
        top_n = self._safe_int(self.var_rate_league_top, 15)
        try:
            fig = wa_dash.chart_rate_league(df, top_n=top_n)
            canvas = wa_charts.embed_figure(self._rate_league_chart_frame, fig)
            canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            self._rate_league_canvases.append(("rate_league", fig, canvas))
        except Exception as e:
            tk.Label(self._rate_league_chart_frame, text=f"Error: {e}",
                     font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left").grid(
                row=0, column=0, sticky="nsew", padx=8, pady=8)


    def _export_rate_league(self):
        """M24: export PNG via helper shared (dulu loop duplikat)."""
        if not self._rate_league_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(
            self._rate_league_canvases, lambda key: f"rate_league_{key}"
        )



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
