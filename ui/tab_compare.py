"""Tab 2 Compare Cabang: side-by-side 2 cabang.

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
import pandas as pd
import tkinter as tk
from tkinter import ttk
from waste_anomaly import charts as wa_charts
from waste_anomaly import dashboard as wa_dash


class CompareTabMixin:
    """Tab 2 Compare Cabang: side-by-side 2 cabang."""

    def _build_compare_tab(self, parent):
        """Side-by-side comparison of 2 cabang with 4 charts.
        Wrapped in scrollable container (v2.3.0)."""
        # L3: columnconfigure/rowconfigure parent dihapus — child tunggal
        # (container _make_scrollable) di-pack (grid config = no-op).
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        # Card 1: selector — L12: borderwidth dihapus (highlightthickness=1
        # sudah menggambar border tunggal; borderwidth=1 menggambar dua).
        c1 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="⚖ Compare Cabang — Side-by-Side Analysis",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text="Pilih 2 cabang untuk dibandingkan. Lihat chart + metrics di bawah.",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 8))

        selector = tk.Frame(c1, bg=C_CARD)
        selector.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(selector, text="Cabang A:", font=F_BODY, bg=C_CARD).pack(side="left", padx=2)
        self.var_compare_a = tk.StringVar()
        self._cb_compare_a = ttk.Combobox(selector, textvariable=self.var_compare_a, width=22, state="readonly")
        self._cb_compare_a.pack(side="left", padx=4)
        self._cb_compare_a.bind("<<ComboboxSelected>>", lambda e: self._render_compare_charts())

        tk.Label(selector, text="vs", font=F_BODY, bg=C_CARD, fg=C_TEXT_MUTED).pack(side="left", padx=8)
        tk.Label(selector, text="Cabang B:", font=F_BODY, bg=C_CARD).pack(side="left", padx=2)
        self.var_compare_b = tk.StringVar()
        self._cb_compare_b = ttk.Combobox(selector, textvariable=self.var_compare_b, width=22, state="readonly")
        self._cb_compare_b.pack(side="left", padx=4)
        self._cb_compare_b.bind("<<ComboboxSelected>>", lambda e: self._render_compare_charts())

        ttk.Button(selector, text="⟳ Refresh", command=self._render_compare_charts).pack(side="left", padx=8)
        ttk.Button(selector, text="🖼 Export PNG…", command=self._export_compare_charts).pack(side="left", padx=4)

        # Card 2: charts grid 2x2 — L12: borderwidth dihapus
        c2 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1, uniform="cmp")
        c2.columnconfigure(1, weight=1, uniform="cmp")
        c2.rowconfigure(0, weight=1, uniform="cmpr")
        c2.rowconfigure(1, weight=1, uniform="cmpr")

        self._compare_chart_frames = []
        for i in range(4):
            r, col = i // 2, i % 2
            f = tk.Frame(c2, bg=C_CARD, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
            f.grid(row=r, column=col, sticky="nsew", padx=4, pady=4)
            f.columnconfigure(0, weight=1)
            f.rowconfigure(1, weight=1)
            self._compare_chart_frames.append(f)

        # Card 3: metrics summary — L12: borderwidth dihapus
        c3 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c3.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c3, text="📋 Metrics Summary", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_compare_metrics = tk.Label(c3, text="(pilih 2 cabang dulu)",
                                            bg=C_CARD, fg=C_TEXT_MUTED, font=F_BODY,
                                            anchor="w", justify="left")
        self.lbl_compare_metrics.pack(fill="x", padx=16, pady=(0, 12))

        # Placeholder
        self._compare_canvases = []
        for f in self._compare_chart_frames:
            tk.Label(f, text="⚖\n\nPilih Cabang A & B\nuntuk lihat comparison.",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)


    def _render_compare_charts(self):
        """Render 4 comparison charts for selected cabangs."""
        a = self.var_compare_a.get()
        b = self.var_compare_b.get()
        df = self._preview_dfs.get("Detail")

        # H3: dispose figure lama dulu (leak fix) — registry (key, fig, canvas)
        self._dispose_chart_registry(self._compare_canvases)
        self._compare_canvases = []
        # Destroy existing
        for f in self._compare_chart_frames:
            for c in f.winfo_children():
                c.destroy()

        if not a or not b or a == b:
            for f in self._compare_chart_frames:
                tk.Label(f, text="⚖\n\nPilih 2 cabang\nberbeda.",
                         font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.lbl_compare_metrics.configure(text="(pilih 2 cabang berbeda)")
            return
        if df is None or df.empty:
            for f in self._compare_chart_frames:
                tk.Label(f, text="(belum ada data)",
                         font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD).grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            return

        # Chart 1: Total waste per JENIS
        f0 = self._compare_chart_frames[0]
        fig0 = wa_dash.chart_compare_total_waste(df, a, b)
        c0 = wa_charts.embed_figure(f0, fig0)
        c0.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("total_waste", fig0, c0))

        # Chart 2: Status comparison
        f1 = self._compare_chart_frames[1]
        fig1 = wa_dash.chart_compare_status(df, a, b)
        c1 = wa_charts.embed_figure(f1, fig1)
        c1.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("status", fig1, c1))

        # Chart 3: Top items comparison
        f2 = self._compare_chart_frames[2]
        fig2 = wa_dash.chart_compare_top_items(df, a, b)
        c2 = wa_charts.embed_figure(f2, fig2)
        c2.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("top_items", fig2, c2))

        # Chart 4: Metrics comparison
        f3 = self._compare_chart_frames[3]
        fig3 = wa_dash.chart_compare_score(df, a, b)
        c3 = wa_charts.embed_figure(f3, fig3)
        c3.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("metrics", fig3, c3))

        # Update metrics summary text — M16b: dibangun dari daftar tuple
        # (label, val_a, val_b, fmt) diformat dalam SATU loop (dulu 10
        # kondisional inline + fungsi _fmt lokal; tanda persen '+'/'−' proper).
        if "NAMA RESTO" in df.columns:
            a_sub = df[df["NAMA RESTO"] == a]
            b_sub = df[df["NAMA RESTO"] == b]
        else:
            a_sub = df.iloc[0:0]
            b_sub = df.iloc[0:0]

        def _stat(sub, col, fn):
            try:
                return fn(sub[col]) if col in sub.columns else 0
            except Exception:
                return 0

        def _prioritas(sub):
            return _stat(sub, "ANOMALY STATUS",
                         lambda s: int((s == "Prioritas Tinggi").sum()))

        metrics = [
            ("Total Waste", _stat(a_sub, "TOTAL", pd.Series.sum),
             _stat(b_sub, "TOTAL", pd.Series.sum), "{:.0f}"),
            ("Avg Waste/Barang", _stat(a_sub, "TOTAL", pd.Series.mean),
             _stat(b_sub, "TOTAL", pd.Series.mean), "{:.2f}"),
            ("Max Single Day", _stat(a_sub, "MAX", pd.Series.max),
             _stat(b_sub, "MAX", pd.Series.max), "{:.1f}"),
            ("Avg Anomali Score", _stat(a_sub, "ANOMALY SCORE", pd.Series.mean),
             _stat(b_sub, "ANOMALY SCORE", pd.Series.mean), "{:.1f}"),
            ("Max Anomali Score", _stat(a_sub, "ANOMALY SCORE", pd.Series.max),
             _stat(b_sub, "ANOMALY SCORE", pd.Series.max), "{:.1f}"),
            ("Jumlah Prioritas", _prioritas(a_sub), _prioritas(b_sub), "{:.0f}"),
            ("Jumlah Item", _stat(a_sub, "NAMA BARANG", pd.Series.nunique),
             _stat(b_sub, "NAMA BARANG", pd.Series.nunique), "{:.0f}"),
        ]
        lines = [f"Cabang A: {a}  •  Cabang B: {b}", ""]
        lines += [
            self._format_compare_metric(lbl, va, vb, fmt)
            for lbl, va, vb, fmt in metrics
        ]
        self.lbl_compare_metrics.configure(text="\n".join(lines))


    def _export_compare_charts(self):
        """M24: export PNG via helper shared (dulu loop duplikat 4×)."""
        if not self._compare_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Pilih 2 cabang dulu.")
            return
        a = self.var_compare_a.get() or "A"
        b = self.var_compare_b.get() or "B"
        self._export_figures_png(
            self._compare_canvases,
            lambda key: f"compare_{a}_vs_{b}_{key}",
        )



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
