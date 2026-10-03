"""Tab 5 Hasil: preview tabel + export laporan Excel.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_CARD
from .shared import F_HINT
from pathlib import Path
from datetime import datetime
from waste_anomaly.exporter import export_to_excel
from tkinter import filedialog
from tkinter import messagebox
import pandas as pd
import threading
import tkinter as tk
from tkinter import ttk


class ResultTabMixin:
    """Tab 5 Hasil: preview tabel + export laporan Excel."""

    def _build_result_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # L12: borderwidth dihapus (highlightthickness=1 = border tunggal)
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        hdr = tk.Frame(c1, bg=C_CARD)
        hdr.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(hdr, text="Preview Hasil", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(side="left")
        # H8: row-count label — truncation 500-baris tidak lagi diam-diam
        self.lbl_result_count = tk.Label(hdr, text="(belum ada data)", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_result_count.pack(side="left", padx=8)
        # H6: export laporan Excel 6-sheet (pipeline sekarang in-memory)
        self.btn_export_excel = ttk.Button(hdr, text="💾 Export Laporan Excel…",
                                           command=self._export_excel_report)
        self.btn_export_excel.pack(side="right", padx=4)
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_result_sheet = tk.StringVar(value="Detail")
        ttk.Radiobutton(frm, text="Detail", variable=self.var_result_sheet, value="Detail", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Anomali Prioritas", variable=self.var_result_sheet, value="Anomali", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Per Cabang", variable=self.var_result_sheet, value="Cabang", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Top Items", variable=self.var_result_sheet, value="Top", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Pareto", variable=self.var_result_sheet, value="Pareto", command=self._refresh_preview).pack(side="left", padx=4)

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(c2, show="headings")
        sb_y = ttk.Scrollbar(c2, orient="vertical", command=self.tree.yview)
        sb_x = ttk.Scrollbar(c2, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")


    def _refresh_preview(self):
        """Radio sheet diganti → render ulang tree (sort state sheet di-reset —
        kolom antar sheet beda makna)."""
        sheet_map = {
            "Detail": "Detail", "Anomali": "Anomali Prioritas",
            "Cabang": "Per Cabang", "Top": "Top Items", "Pareto": "Pareto Alasan",
        }
        sheet = sheet_map.get(self.var_result_sheet.get(), "Detail")
        self._tree_sort_states.pop(str(self.tree), None)
        self._render_result_tree(self._preview_dfs.get(sheet), sheet)


    def _render_result_tree(self, df: pd.DataFrame, sheet: str):
        """Populate tab Hasil — M24 (helper populate) + M5 (sort heading) +
        L17 (sheet kosong tetap tampilkan kolom asli + baris "(kosong)")."""
        tree = self.tree
        tree.delete(*tree.get_children(""))
        if df is None:
            tree["columns"] = ["info"]
            tree.heading("info", text="info")
            tree.insert("", "end", values=["(tidak ada data — jalankan pipeline dulu)"])
            self.lbl_result_count.configure(text="(belum ada data)")
            return

        cols = list(df.columns)
        df = self._apply_tree_sort_state(df, tree)
        self._populate_tree(
            tree, df, cols, width=120, ndigits=4, cap=500,
            get_df=lambda: self._preview_dfs.get(sheet),
            render_fn=lambda d, s=sheet: self._render_result_tree(d, s),
        )
        # H8: label jumlah baris — 500-cap tampil saat tercapai (L17: "(kosong)")
        count = len(df)
        if count == 0:
            self.lbl_result_count.configure(text="(kosong)")
        else:
            self.lbl_result_count.configure(
                text=f"Menampilkan {min(500, count)} baris (dari {count})"
            )


    def _export_excel_report(self):
        """Export laporan Excel 6-sheet dari df pipeline (in-memory)."""
        df = self._pipeline_df
        if df is None:
            df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            messagebox.showinfo("Export", "Belum ada data. Run pipeline dulu.")
            return
        if self._export_running:
            return  # jangan double-export

        initialdir = Path.home() / "Documents"
        if not initialdir.exists():
            initialdir = Path.home()
        suggested = f"Waste_Anomaly_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Export Laporan Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=str(initialdir),
            initialfile=suggested,
        )
        if not path:
            return

        key_akhir = self._last_key_akhir
        log_lines = list(self._log_lines[-200:])
        config_snapshot = dict(self.config)  # read-only snapshot untuk thread

        self._export_running = True
        self.btn_export_excel.configure(state="disabled")
        self._set_status("Menyimpan laporan Excel…", "running")
        self.log(f"=== Export Excel → {path} (6 sheet) ===")

        def _worker():
            try:
                result = export_to_excel(df, path, config_snapshot, key_akhir, log_lines)
            except Exception as e:  # defensive — kontrak exporter dict
                result = {"success": False, "error": str(e), "output_path": path}
            self.ui_queue.put(("export_done", result, None))

        threading.Thread(target=_worker, daemon=True).start()


    def _on_export_done(self, result: dict):
        """Hasil export Excel dari worker thread (via ui_queue)."""
        self._export_running = False
        if hasattr(self, "btn_export_excel"):
            self.btn_export_excel.configure(state="normal")
        if not isinstance(result, dict):
            result = {"success": False, "error": str(result), "output_path": ""}
        if result.get("success"):
            out = result.get("output_path", "")
            self._set_status(f"✓ Laporan Excel tersimpan: {out}", "done")
            self.log(f"=== Export selesai: {out} ===")
            messagebox.showinfo("Export Selesai", f"Laporan Excel (6 sheet) tersimpan:\n{out}")
        else:
            err = result.get("error", "Unknown error")
            self._set_status(f"⚠ Export gagal: {err}", "error")
            self.log(f"!!! Export gagal: {err}")
            messagebox.showerror("Export Gagal", err)



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
