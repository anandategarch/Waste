"""Tab Money View (v2.5.0 P2+P4+P5+P7): prioritas magnitude — top waste
rows apa pun statusnya, Pareto item, benchmark item×cabang vs peer aktif,
breakdown per satuan.

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
from datetime import datetime
from tkinter import filedialog
from tkinter import messagebox
import pandas as pd
import tkinter as tk
from tkinter import ttk
from waste_anomaly import charts as wa_charts
from waste_anomaly import priority as wa_priority
from waste_anomaly import temporal as wa_temporal


class MoneyTabMixin:
    """Tab Money View: prioritas magnitude + benchmark peer (P2/P4/P5)."""

    def _build_money_tab(self, parent):
        """Layout scrollable: unit info + Pareto + money table + benchmark."""
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(3, weight=1)
        inner.rowconfigure(5, weight=1)

        # ===== Card 0: header + unit breakdown (P5) =====
        hdr = tk.Frame(inner, bg=C_CARD, relief="flat",
                       highlightbackground=C_BORDER, highlightthickness=1)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(hdr, text="💰 Money View — Prioritas Magnitude Waste",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(hdr,
                 text="Baris waste TERBESAR apa pun status anomalinya. FOCUS SCORE = 60% magnitude + 40% anomali "
                      "(mengisi gap: baris Prioritas Tinggi hanya ~0,5% total waste, baris uang terbesar justru 'Normal').",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD, wraplength=980,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 4))
        self.lbl_money_units = tk.Label(hdr, text="(belum ada data — run pipeline dulu)",
                                        font=F_BODY, fg=C_HEADER, bg=C_CARD,
                                        anchor="w", justify="left", wraplength=980)
        self.lbl_money_units.pack(fill="x", padx=16, pady=(0, 4))
        btn_frame = tk.Frame(hdr, bg=C_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="⟳ Refresh", command=self._render_money).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🖼 Export PNG…",
                   command=self._export_money_charts).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="💾 Export Tabel CSV…",
                   command=self._export_money_csv).pack(side="left", padx=4)

        # ===== Card 1: chart money top + pareto (side by side) =====
        charts_frame = tk.Frame(inner, bg=C_BG)
        charts_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        charts_frame.columnconfigure(0, weight=1, uniform="mn")
        charts_frame.columnconfigure(1, weight=1, uniform="mn")
        charts_frame.rowconfigure(0, weight=1)
        self._money_chart_frames = []
        for label, col in [("money_top", 0), ("item_pareto", 1)]:
            f = tk.Frame(charts_frame, bg=C_CARD, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
            f.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
            f.columnconfigure(0, weight=1)
            f.rowconfigure(1, weight=1)
            self._money_chart_frames.append((label, f))
            tk.Label(f, text="💰\n\nRun pipeline untuk\nlihat chart",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)
        self._money_canvases: list = []

        # ===== Card 2: header tabel money =====
        h2 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        h2.grid(row=2, column=0, sticky="ew", padx=8, pady=(8, 0))
        tk.Label(h2, text="📋 Top Waste Rows (semua status) — klik header sort ▼/▲",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_money_count = tk.Label(h2, text="(belum ada data)",
                                        font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_money_count.pack(anchor="w", padx=16, pady=(0, 8))

        # Tabel money
        t1 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        t1.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 4))
        t1.columnconfigure(0, weight=1)
        t1.rowconfigure(0, weight=1)
        self.tree_money = ttk.Treeview(t1, show="headings", height=12)
        sb1y = ttk.Scrollbar(t1, orient="vertical", command=self.tree_money.yview)
        sb1x = ttk.Scrollbar(t1, orient="horizontal", command=self.tree_money.xview)
        self.tree_money.configure(yscrollcommand=sb1y.set, xscrollcommand=sb1x.set)
        self.tree_money.grid(row=0, column=0, sticky="nsew")
        sb1y.grid(row=0, column=1, sticky="ns")
        sb1x.grid(row=1, column=0, sticky="ew")
        self.tree_money.bind("<Double-1>", self._on_money_row_double_click)

        # ===== Card 3: header benchmark =====
        h3 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        h3.grid(row=4, column=0, sticky="ew", padx=8, pady=(8, 0))
        tk.Label(h3, text="🎯 Benchmark Item×Cabang vs Peer AKTIF (P4) — klik header sort ▼/▲",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(h3,
                 text="Peer median dihitung HANYA dari cabang yang punya waste pada item itu (bukan termasuk nol) — "
                      "memperbaiki blind-spot peer lama: median 0 mematikan deteksi justru untuk item/langka.",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD, wraplength=980,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 4))
        self.lbl_bench_count = tk.Label(h3, text="(belum ada data)",
                                        font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_bench_count.pack(anchor="w", padx=16, pady=(0, 8))

        # Tabel benchmark
        t2 = tk.Frame(inner, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        t2.grid(row=5, column=0, sticky="nsew", padx=8, pady=(0, 8))
        t2.columnconfigure(0, weight=1)
        t2.rowconfigure(0, weight=1)
        self.tree_bench = ttk.Treeview(t2, show="headings", height=12)
        sb2y = ttk.Scrollbar(t2, orient="vertical", command=self.tree_bench.yview)
        sb2x = ttk.Scrollbar(t2, orient="horizontal", command=self.tree_bench.xview)
        self.tree_bench.configure(yscrollcommand=sb2y.set, xscrollcommand=sb2x.set)
        self.tree_bench.grid(row=0, column=0, sticky="nsew")
        sb2y.grid(row=0, column=1, sticky="ns")
        sb2x.grid(row=1, column=0, sticky="ew")

    # ------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------

    def _render_money(self):
        df = self._preview_dfs.get("Detail")

        # H3: dispose figure lama dulu — registry (key, fig, canvas)
        self._dispose_chart_registry(self._money_canvases)
        self._money_canvases = []
        for _label, f in self._money_chart_frames:
            for c in f.winfo_children():
                c.destroy()

        if df is None or df.empty:
            for _label, f in self._money_chart_frames:
                tk.Label(f, text="(belum ada data — run pipeline dulu)",
                         font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD,
                         justify="center").grid(row=0, column=0, sticky="nsew",
                                                padx=20, pady=20)
            self._render_money_tree(None)
            self._render_bench_tree(None)
            self.lbl_money_units.configure(text="(belum ada data — run pipeline dulu)")
            return

        # P5/P7: unit breakdown + caveat campuran satuan
        units = wa_temporal.unit_summary(df)
        if not units.empty:
            parts = [
                f"{r['SATUAN']}: {r['total']:,.0f} ({r['share_pct']:.1f}%)"
                for _, r in units.iterrows()
            ]
            n_raw = units["raw_values"].astype(str).str.contains(";", regex=False).sum()
            caveat = (
                "  ⚠ ada satuan duplikat akibat spasi tersembunyi — cek tab Data Quality"
                if n_raw > 0 else ""
            )
            self.lbl_money_units.configure(
                text="Breakdown per satuan (agregat lintas satuan hanya indikatif): "
                     + " • ".join(parts) + caveat
            )
        else:
            self.lbl_money_units.configure(text="Kolom SATUAN tidak tersedia.")

        builders = [
            ("money_top", lambda: wa_charts.chart_money_top(df, top_n=15)),
            ("item_pareto", lambda: wa_charts.chart_item_pareto(df, top_n=20)),
        ]
        for (label, f), (_name, builder) in zip(self._money_chart_frames, builders):
            try:
                fig = builder()
                canvas = wa_charts.embed_figure(f, fig)
                canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
                self._money_canvases.append((label, fig, canvas))
            except Exception as e:
                tk.Label(f, text=f"Gagal render:\n{e}", font=F_BODY,
                         fg="#dc2626", bg=C_CARD, justify="left").grid(
                    row=0, column=0, sticky="nsew", padx=8, pady=8)
                self.log(f"⚠ Money chart '{label}' gagal: {e}")

        mv = wa_priority.money_view(df, top_n=100)
        self._render_money_tree(mv)
        bench = wa_priority.benchmark_items(df)
        if len(bench) > 300:
            bench = bench.head(300)
        self._render_bench_tree(bench)

    def _render_money_tree(self, mv: pd.DataFrame | None):
        """Tabel money view — tag baris per FOCUS CLASS (M24/M5 helper)."""
        tree = self.tree_money
        tree.delete(*tree.get_children(""))
        if mv is None or mv.empty:
            self.lbl_money_count.configure(text="(tidak ada data)")
            return
        self._money_display_df = mv
        df = self._apply_tree_sort_state(mv, tree)
        cols = list(df.columns)
        fc_idx = cols.index("FOCUS CLASS") if "FOCUS CLASS" in cols else None

        def _tag_fn(vals):
            if fc_idx is not None and fc_idx < len(vals):
                return str(vals[fc_idx]).lower().replace(" ", "_")
            return ""

        self._populate_tree(
            tree, df, cols, width=95, ndigits=2, cap=100, tag_fn=_tag_fn,
            get_df=lambda: self._money_display_df,
            render_fn=lambda d: self._render_money_tree(d),
        )
        tree.tag_configure("fokus_utama", background="#fef2f2", foreground="#dc2626")
        tree.tag_configure("fokus_sekunder", background="#fff7ed", foreground="#ea580c")
        count = len(df)
        n_utama = int((mv["FOCUS CLASS"] == "Fokus Utama").sum()) if "FOCUS CLASS" in mv.columns else 0
        self.lbl_money_count.configure(
            text=f"{count} baris teratas • {n_utama} Fokus Utama (skor ≥ 70)"
        )

    def _render_bench_tree(self, bench: pd.DataFrame | None):
        """Tabel benchmark item×cabang (M24/M5 helper)."""
        tree = self.tree_bench
        tree.delete(*tree.get_children(""))
        if bench is None or bench.empty:
            self.lbl_bench_count.configure(text="(tidak ada data)")
            return
        self._bench_display_df = bench
        df = self._apply_tree_sort_state(bench, tree)
        cols = list(df.columns)
        flag_idx = cols.index("Flag") if "Flag" in cols else None

        def _tag_fn(vals):
            if flag_idx is not None and flag_idx < len(vals):
                return str(vals[flag_idx]).lower().replace(" ", "_")
            return ""

        self._populate_tree(
            tree, df, cols, width=95, ndigits=2, cap=300, tag_fn=_tag_fn,
            get_df=lambda: self._bench_display_df,
            render_fn=lambda d: self._render_bench_tree(d),
        )
        tree.tag_configure("di_atas_peer", background="#fef2f2", foreground="#dc2626")
        count = len(df)
        n_above = int((bench["Flag"] == "Di Atas Peer").sum()) if "Flag" in bench.columns else 0
        self.lbl_bench_count.configure(
            text=f"{count} pasangan item×cabang • {n_above} 'Di Atas Peer' (≥ 2× median peer aktif)"
        )

    def _on_money_row_double_click(self, event):
        """P8: double-click baris money → drill-down filter cabang+item."""
        selection = self.tree_money.selection()
        if not selection:
            return
        vals = self.tree_money.item(selection[0], "values")
        cols = self.tree_money["columns"]
        try:
            cabang = vals[cols.index("NAMA RESTO")] if "NAMA RESTO" in cols else None
            item = vals[cols.index("NAMA BARANG")] if "NAMA BARANG" in cols else None
        except (ValueError, IndexError):
            return
        if cabang:
            self.active_filters["cabang"] = cabang
            self.var_filter_cabang.set(cabang)
        if item:
            self.active_filters["item"] = item
        self._apply_dashboard_filter()
        self.notebook.select(0)

    # ------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------

    def _export_money_charts(self):
        if not self._money_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(self._money_canvases, lambda key: f"money_{key}")

    def _export_money_csv(self):
        """Export tabel money + benchmark ke CSV (2 file berurutan)."""
        mv = getattr(self, "_money_display_df", None)
        bench = getattr(self, "_bench_display_df", None)
        if (mv is None or mv.empty) and (bench is None or bench.empty):
            messagebox.showinfo("Export", "Belum ada data. Refresh dulu.")
            return
        folder = filedialog.askdirectory(title="Pilih folder untuk simpan CSV")
        if not folder:
            return
        from pathlib import Path
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        saved = []
        try:
            if mv is not None and not mv.empty:
                p = Path(folder) / f"money_view_{stamp}.csv"
                mv.to_csv(p, index=False, encoding="utf-8-sig")
                saved.append(p.name)
            if bench is not None and not bench.empty:
                p = Path(folder) / f"benchmark_peer_{stamp}.csv"
                bench.to_csv(p, index=False, encoding="utf-8-sig")
                saved.append(p.name)
            messagebox.showinfo("Export", f"{len(saved)} file CSV disimpan ke:\n{folder}")
            self.log(f"=== Money view CSV → {folder}: {', '.join(saved)} ===")
        except Exception as e:  # noqa: BLE001 — gagal export ≠ crash app
            messagebox.showerror("Export Error", str(e))


# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
