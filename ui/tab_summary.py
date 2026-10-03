"""Tab 7 Ringkasan: ringkasan run terakhir.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from datetime import datetime
import pandas as pd
import tkinter as tk
from tkinter import ttk


class SummaryTabMixin:
    """Tab 7 Ringkasan: ringkasan run terakhir."""

    def _build_summary_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # L12: borderwidth dihapus
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Ringkasan Run Terakhir", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_summary = tk.Label(c1, text="(belum ada run)", bg=C_CARD, fg=C_TEXT_MUTED, font=F_BODY, anchor="w", justify="left")
        self.lbl_summary.pack(fill="x", padx=16, pady=(0, 4))
        # M14: warning khusus config_load_error dari pipeline summary
        self.lbl_summary_warn = tk.Label(c1, text="", bg=C_CARD, fg="#b45309", font=F_BODY,
                                         anchor="w", justify="left", wraplength=900)
        # H8: row-count label tabel Per Cabang
        self.lbl_summary_count = tk.Label(c1, text="", bg=C_CARD, fg=C_TEXT_MUTED, font=F_HINT, anchor="w")
        self.lbl_summary_count.pack(fill="x", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)
        self.tree_summary = ttk.Treeview(c2, show="tree headings")
        self.tree_summary.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)


    def _update_summary_tab(self, summary: dict):
        # M14: pakai timestamp run ASLI dari summary (ISO, end-of-run) —
        # fallback ke waktu run tersimpan, bukan datetime.now() render.
        ts = summary.get("timestamp")
        if ts:
            try:
                waktu = datetime.fromisoformat(str(ts)).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                waktu = str(ts)
        else:
            waktu = (self._last_run_time or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        ka = summary.get("key_akhir")
        msg = (
            f"Waktu Run     : {waktu}\n"
            f"Key Akhir     : {ka if ka is not None else '-'}\n"
            f"Total Baris   : {summary.get('total_rows', 0)}\n"
            f"Cabang Unik   : {summary.get('cabang_count', 0)}\n"
            f"Item Unik     : {summary.get('item_count', 0)}\n"
            f"Anomali       : {summary.get('prioritas_count', 0)} prioritas • "
            f"{summary.get('potensi_count', 0)} potensi • "
            f"{summary.get('review_count', 0)} review • "
            f"{summary.get('normal_count', 0)} normal\n"
            f"Output        : (in-memory) — klik '💾 Export Laporan Excel' di tab Hasil"
        )
        self.lbl_summary.configure(text=msg)
        # Warning config_load_error (surfaced, tidak ditelan)
        cfg_err = summary.get("config_load_error")
        if cfg_err:
            self.lbl_summary_warn.configure(text=f"⚠ Config: {cfg_err} — threshold memakai default")
            self.lbl_summary_warn.pack(fill="x", padx=16, pady=(0, 4))
        else:
            self.lbl_summary_warn.configure(text="")
            self.lbl_summary_warn.pack_forget()

        df = self._preview_dfs.get("Per Cabang")
        self._render_summary_tree(df)


    def _render_summary_tree(self, df: pd.DataFrame):
        """Populate tabel Per Cabang di Ringkasan — M24 (helper populate) +
        M5 (sort heading; dipisah dari _update_summary_tab supaya klik sort
        tidak perlu rebuild teks summary)."""
        tree = self.tree_summary
        tree.delete(*tree.get_children(""))
        if df is None:
            self.lbl_summary_count.configure(text="")
            return
        cols = list(df.columns)
        df = self._apply_tree_sort_state(df, tree)
        self._populate_tree(
            tree, df, cols, width=140, ndigits=4, cap=500,
            get_df=lambda: self._preview_dfs.get("Per Cabang"),
            render_fn=self._render_summary_tree,
        )
        # H8: cap 500 baris + label jumlah — tidak lagi diam-diam (L17: kosong)
        count = len(df)
        if count == 0:
            self.lbl_summary_count.configure(text="Per Cabang: (kosong)")
        else:
            self.lbl_summary_count.configure(
                text=f"Per Cabang: menampilkan {min(500, count)} baris (dari {count})"
            )



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
