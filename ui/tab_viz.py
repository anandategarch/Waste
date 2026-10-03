"""Tab 6 Visualisasi: galeri 12 grafik + export PNG.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import C_TITLE_BG
from .shared import FONT_NAME
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox
import sys
import tkinter as tk
from tkinter import ttk
from waste_anomaly import charts as wa_charts


class VizTabMixin:
    """Tab 6 Visualisasi: galeri 12 grafik + export PNG."""

    def _build_viz_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # L12: borderwidth dihapus
        c = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c.columnconfigure(0, weight=1)
        c.rowconfigure(1, weight=1)

        hdr = tk.Frame(c, bg=C_CARD)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        tk.Label(hdr, text="Visualisasi & Grafik — 12 Chart Gallery", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(side="left")
        tk.Label(hdr, text="matplotlib • auto-update setelah run pipeline", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(side="left", padx=12)
        self.btn_viz_refresh = ttk.Button(hdr, text="⟳ Refresh Grafik", command=self._refresh_viz)
        self.btn_viz_refresh.pack(side="right", padx=4)
        self.btn_viz_export = ttk.Button(hdr, text="🖼 Export Semua PNG…", command=self._export_all_charts)
        self.btn_viz_export.pack(side="right", padx=4)

        outer = tk.Frame(c, bg=C_CARD)
        outer.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=C_CARD, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self._viz_scroll_canvas = canvas
        self._viz_inner = tk.Frame(canvas, bg=C_CARD)
        self._viz_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        _viz_window_id = canvas.create_window((0, 0), window=self._viz_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        # M11: width-sync — inner frame mengikuti lebar canvas supaya chart
        # stretch horizontal (dulu hanya _make_scrollable yang punya).
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_viz_window_id, width=e.width))
        # C3: scroll via global wheel dispatcher — bind_all lokal dihapus
        # (dulu menimpa binding tab lain / wheel menggulung canvas tersembunyi)
        canvas._waste_scroll = True  # type: ignore[attr-defined]

        self._make_viz_placeholder()
        self._viz_canvases: list = []


    def _make_viz_placeholder(self):
        """L3: placeholder Visualisasi — dulu dibuat inline 2× identik."""
        self._viz_placeholder = tk.Label(
            self._viz_inner,
            text="\nBelum ada data visualisasi.\n\nJalankan pipeline di tab 'Run Pipeline' terlebih dahulu,\nlalu klik '⟳ Refresh Grafik' di atas.",
            font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center",
            padx=40, pady=60,
        )
        self._viz_placeholder.pack(fill="x", padx=16, pady=16)


    def _refresh_viz(self):
        # H3: dispose figure + canvas lama dulu (leak fix) — registry (key, fig, canvas)
        self._dispose_chart_registry(self._viz_canvases)
        self._viz_canvases = []
        for widget in self._viz_inner.winfo_children():
            widget.destroy()

        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            self._make_viz_placeholder()  # L3: dedupe inline
            return

        # P8 (v2.5.0): 4 chart galeri ini kini bisa DIKLIK → set filter di
        # Dashboard + lompat ke sana (drill-down lintas-tab). Chart lain
        # tetap statis (tidak punya dimensi filter yang natural).
        drillable = {
            wa_charts.chart_status_pie: ("status", "Status"),
            wa_charts.chart_waste_per_cabang: ("cabang", "Cabang"),
            wa_charts.chart_top_items: ("item", "Item"),
            wa_charts.chart_pareto_keterangan: ("keterangan", "Alasan"),
        }

        cols_per_row = 2
        for idx, (title, desc, fn) in enumerate(wa_charts.ALL_CHARTS):
            row = idx // cols_per_row
            col = idx % cols_per_row
            # L12: borderwidth+relief solid dihapus — highlightthickness=1 cukup
            card = tk.Frame(self._viz_inner, bg=C_CARD, relief="flat",
                            highlightbackground=C_BORDER, highlightthickness=1)
            card.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(1, weight=1)
            title_frame = tk.Frame(card, bg=C_TITLE_BG)
            title_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
            drill_note = "" if fn not in drillable else "  👆 klik = drill-down"
            tk.Label(title_frame, text=f"📊 {title}", font=(FONT_NAME, 9, "bold"),
                     fg=C_HEADER, bg=C_TITLE_BG).pack(side="left", padx=8, pady=6)
            tk.Label(title_frame, text=desc + drill_note, font=F_HINT,
                     fg=C_TEXT_MUTED, bg=C_TITLE_BG).pack(side="left", padx=8)
            try:
                kwargs = {}
                if fn in drillable:
                    key, _label = drillable[fn]
                    kwargs["on_click"] = lambda k, v, _key=key: self._on_viz_chart_click(_key, v)
                fig = fn(df, **kwargs)
                canvas_widget = wa_charts.embed_figure(card, fig)
                canvas_widget.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
                self._viz_canvases.append((title, fig, canvas_widget))
            except Exception as e:
                err = tk.Label(card, text=f"Gagal render:\n{e}",  # L6
                              font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left")
                err.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c_i in range(cols_per_row):
            self._viz_inner.columnconfigure(c_i, weight=1, minsize=420)

    def _on_viz_chart_click(self, key: str, value):
        """P8 (v2.5.0): klik bar/wedge di chart galeri → terapkan filter di
        Dashboard + lompat ke tab Dashboard (chart di-render ulang dengan
        highlight oleh mekanisme filter yang sudah ada)."""
        self._on_chart_click(key, value)
        try:
            self.notebook.select(0)  # tab Dashboard
        except Exception:  # noqa: BLE001 — lompatan best-effort
            pass


    def _export_all_charts(self):
        """M24: export PNG via helper shared (dulu loop duplikat; key = judul chart)."""
        if not self._viz_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(self._viz_canvases)


    def _export_figures_png(self, entries, basename_fn=None):
        """M24: export registry (key, fig, canvas) ke PNG dalam folder pilihan.

        basename_fn(key) → basename file (disanitasi lagi); None → pakai key.
        Mengembalikan jumlah file tersimpan (0 bila dibatalkan).
        """
        if not entries:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return 0
        folder = filedialog.askdirectory(title="Pilih folder untuk simpan PNG")
        if not folder:
            return 0
        saved = 0
        for key, fig, _canvas in entries:
            base = self._sanitize_filename(
                basename_fn(key) if basename_fn else key
            )
            path = Path(folder) / f"{base}.png"
            try:
                fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
                saved += 1
            except Exception as e:  # noqa: BLE001 — satu chart gagal ≠ abort semua
                print(f"Gagal simpan {key}: {e}", file=sys.stderr)
                self.log(f"⚠ Gagal simpan chart '{key}': {e}")
        messagebox.showinfo("Export", f"{saved} chart disimpan ke:\n{folder}")
        return saved



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
