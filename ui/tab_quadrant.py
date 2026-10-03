"""Tab 3 Quadrant: scatter SISTEMIK/MUSIMAN/LOKAL/INSIDEN.

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


class QuadrantTabMixin:
    """Tab 3 Quadrant: scatter SISTEMIK/MUSIMAN/LOKAL/INSIDEN."""

    def _build_quadrant_tab(self, parent):
        """Tab Quadrant: scatter Sistemik vs Insiden + fingerprint distribution."""
        # L3: columnconfigure/rowconfigure parent dihapus (child tunggal di-pack)
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)

        # Header
        hdr = tk.Frame(inner, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(hdr, text="🎯 Quadrant Analysis — Sistemik vs Insiden",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(hdr, text="Scatter plot prevalence (cabang%) × persistence (hari%). 4 quadrant: SISTEMIK, MUSIMAN, LOKAL-KRONIS, INSIDEN. Adaptasi dari Inventory-Control W3.",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 8))
        # Refresh + export
        btn_frame = tk.Frame(hdr, bg=C_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="⟳ Refresh", command=self._render_quadrant_charts).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🖼 Export PNG…", command=self._export_quadrant_charts).pack(side="left", padx=4)

        # Charts container: 2 charts side-by-side (scatter + fingerprint)
        charts_frame = tk.Frame(inner, bg=C_BG)
        charts_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        charts_frame.columnconfigure(0, weight=2, uniform="q")  # scatter wider
        charts_frame.columnconfigure(1, weight=1, uniform="q")

        self._quadrant_chart_frame = tk.Frame(charts_frame, bg=C_CARD, relief="flat",
                                              highlightbackground=C_BORDER, highlightthickness=1)
        self._quadrant_chart_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._quadrant_chart_frame.columnconfigure(0, weight=1)
        self._quadrant_chart_frame.rowconfigure(1, weight=1)

        self._fingerprint_chart_frame = tk.Frame(charts_frame, bg=C_CARD, relief="flat",
                                                  highlightbackground=C_BORDER, highlightthickness=1)
        self._fingerprint_chart_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self._fingerprint_chart_frame.columnconfigure(0, weight=1)
        self._fingerprint_chart_frame.rowconfigure(1, weight=1)

        # Placeholder
        tk.Label(self._quadrant_chart_frame, text="🎯\n\nRun pipeline untuk\nlihat Quadrant chart",
                 font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
            row=0, column=0, sticky="nsew", padx=20, pady=20)
        tk.Label(self._fingerprint_chart_frame, text="🧬\n\nFingerprint chart",
                 font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
            row=0, column=0, sticky="nsew", padx=20, pady=20)

        # Summary table
        table_frame = tk.Frame(inner, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        table_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        table_frame.columnconfigure(0, weight=1)
        tk.Label(table_frame, text="📋 Items per Quadrant (klik header untuk sort ▼/▲)",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_quadrant_count = tk.Label(table_frame, text="(belum ada data)", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_quadrant_count.pack(anchor="w", padx=16)

        tree_wrap = tk.Frame(table_frame, bg=C_CARD)
        tree_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.tree_quadrant = ttk.Treeview(tree_wrap, show="headings", height=10)
        sb_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_quadrant.yview)
        sb_x = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree_quadrant.xview)
        self.tree_quadrant.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree_quadrant.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        self._quadrant_canvases = []


    def _render_quadrant_charts(self):
        """Render scatter + fingerprint charts di tab Quadrant."""
        df = self._preview_dfs.get("Detail")
        # H3: dispose figure lama dulu (leak fix) — registry (key, fig, canvas)
        self._dispose_chart_registry(self._quadrant_canvases)
        self._quadrant_canvases = []
        # Clear existing
        for f in [self._quadrant_chart_frame, self._fingerprint_chart_frame]:
            for c in f.winfo_children():
                c.destroy()

        if df is None or df.empty:
            tk.Label(self._quadrant_chart_frame, text="(belum ada data — run pipeline dulu)",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)
            tk.Label(self._fingerprint_chart_frame, text="(belum ada data)",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)
            return

        # Chart 1: Quadrant scatter — key_akhir ASLI dari run terakhir (C4-fix:
        # persistence = daysActive/key_akhir; default 31 hanya sebelum run pertama)
        # F4 v2.3.2: threshold kini dari config user (QUADRANT_THRESHOLD) —
        # sebelumnya hardcoded 0.5 di dashboard.py → chart & tabel bisa beda.
        try:
            _quad_th = float(self.config.get("thresholds", {}).get("QUADRANT_THRESHOLD", 0.5))
            fig1 = wa_dash.chart_quadrant_scatter(
                df, key_akhir=self._last_key_akhir, threshold=_quad_th)
            c1 = wa_charts.embed_figure(self._quadrant_chart_frame, fig1)
            c1.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            self._quadrant_canvases.append(("quadrant_scatter", fig1, c1))
        except Exception as e:
            tk.Label(self._quadrant_chart_frame, text=f"Error: {e}",
                     font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left").grid(
                row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Chart 2: Fingerprint distribution
        try:
            fig2 = wa_dash.chart_fingerprint_distribution(df)
            c2 = wa_charts.embed_figure(self._fingerprint_chart_frame, fig2)
            c2.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            self._quadrant_canvases.append(("fingerprint", fig2, c2))
        except Exception as e:
            tk.Label(self._fingerprint_chart_frame, text=f"Error: {e}",
                     font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left").grid(
                row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Update table with items per quadrant
        self._render_quadrant_table(df)


    def _render_quadrant_table(self, df: pd.DataFrame):
        """Aggregate item per-quadrant → render tree (M24/M5 via helper)."""
        tree = self.tree_quadrant
        tree.delete(*tree.get_children(""))
        if df is None or df.empty or "NAMA BARANG" not in df.columns:
            self.lbl_quadrant_count.configure(text="(tidak ada data)")
            return

        # Aggregate per item — default urutan totalWaste desc (HANYA bila belum
        # ada sort aktif dari user; klik heading di-handle helper M5).
        item_df = df.drop_duplicates(subset=["NAMA BARANG"]).copy()
        if ("totalWaste" in item_df.columns
                and not self._tree_sort_states.get(str(tree))):
            item_df = item_df.sort_values("totalWaste", ascending=False)
        self._render_quadrant_tree(item_df)


    def _render_quadrant_tree(self, item_df: pd.DataFrame):
        """Populate tree item-per-quadrant — dipakai render awal + klik sort
        (M5: sort state dipertahankan, sumber = aggregate tersimpan)."""
        tree = self.tree_quadrant
        tree.delete(*tree.get_children(""))
        # df aggregate TANPA sort — sumber untuk klik heading sort
        self._quadrant_display_df = item_df

        item_df = self._apply_tree_sort_state(item_df, tree)
        display_cols = ["NAMA BARANG", "QUADRANT", "FINGERPRINT CLASS", "SISTEMATIK",
                       "cabangActive", "daysActive", "totalWaste", "explained"]
        cols = [c for c in display_cols if c in item_df.columns]
        q_idx = cols.index("QUADRANT") if "QUADRANT" in cols else None

        def _tag_fn(vals):
            if q_idx is not None and q_idx < len(vals) and vals[q_idx]:
                return str(vals[q_idx]).lower().replace("-", "_")
            return ""

        self._populate_tree(
            tree, item_df, cols, width=110, ndigits=3, cap=200, tag_fn=_tag_fn,
            get_df=lambda: self._quadrant_display_df,
            render_fn=self._render_quadrant_tree,
        )

        # Tag colors per quadrant
        tree.tag_configure("sistemik", background="#fee2e2")
        tree.tag_configure("musiman", background="#ffedd5")
        tree.tag_configure("lokal_kronis", background="#ede9fe")
        tree.tag_configure("insiden", background="#dcfce7")

        count = len(item_df)
        self.lbl_quadrant_count.configure(
            text=f"{count} item (menampilkan {min(200, count)} pertama)"
        )


    def _export_quadrant_charts(self):
        """M24: export PNG via helper shared (dulu loop duplikat)."""
        if not self._quadrant_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(
            self._quadrant_canvases, lambda key: f"quadrant_{key}"
        )



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
