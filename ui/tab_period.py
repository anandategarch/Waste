"""Tab Compare Periode (v2.5.0 P9): bandingkan run saat ini vs workbook
periode lain (bulan sebelumnya) — total, per-JENIS, cabang & item movers,
item baru/hilang.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from pathlib import Path

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from tkinter import filedialog
from tkinter import messagebox
import pandas as pd
import threading
import tkinter as tk
import traceback
from tkinter import ttk
from waste_anomaly.loader import load_rekap_mentah
from waste_anomaly.period_compare import auto_key_akhir, compare_periods
from waste_anomaly.pipeline import run_pipeline


class PeriodTabMixin:
    """Tab Compare Periode: perbandingan dua run (P9 v2.5.0)."""

    def _build_period_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # ===== Card 1: kontrol =====
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="🔀 Compare Periode — Run Saat Ini vs Workbook Lain",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1,
                 text="Pilih workbook periode pembanding (mis. bulan lalu). Pipeline dijalankan di background "
                      "dengan key_akhir otomatis (hari aktif terbesar), lalu dibandingkan per cabang/item.",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD, wraplength=980,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(frm, text="Periode A (saat ini):", font=F_BODY).pack(side="left", padx=(0, 4))
        self.lbl_period_a = tk.Label(frm, text="(belum ada run)", font=F_BODY,
                                     fg=C_HEADER, bg=C_CARD)
        self.lbl_period_a.pack(side="left", padx=(0, 16))
        tk.Label(frm, text="Periode B:", font=F_BODY).pack(side="left", padx=(0, 4))
        self.var_period_b = tk.StringVar()
        ent_b = ttk.Entry(frm, textvariable=self.var_period_b)
        ent_b.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frm, text="Browse…", command=self._browse_period_b).pack(side="left", padx=4)
        self.btn_period_run = ttk.Button(frm, text="🔀 Bandingkan",
                                         style="Accent.TButton",
                                         command=self._start_period_compare)
        self.btn_period_run.pack(side="left", padx=4)
        self.lbl_period_status = tk.Label(c1, text="Siap.", font=F_HINT,
                                          fg=C_TEXT_MUTED, bg=C_CARD, anchor="w")
        self.lbl_period_status.pack(fill="x", padx=16, pady=(4, 12))

        # ===== Card 2: notebook tabel hasil =====
        c2 = tk.Frame(parent, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)
        self.nb_period = ttk.Notebook(c2)
        self.nb_period.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self._period_trees: dict[str, ttk.Treeview] = {}
        self._period_dfs: dict[str, pd.DataFrame | None] = {
            "summary": None, "per_jenis": None, "branch": None,
            "items": None, "new_items": None, "gone_items": None,
        }
        pages = [
            ("summary", "📊 Ringkasan"),
            ("per_jenis", "🧾 Per JENIS"),
            ("branch", "🏬 Cabang Mover"),
            ("items", "📦 Item Mover"),
            ("new_items", "🆕 Item Baru"),
            ("gone_items", "📉 Item Hilang"),
        ]
        for key, title in pages:
            page = ttk.Frame(self.nb_period)
            self.nb_period.add(page, text=title)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(0, weight=1)
            tree = ttk.Treeview(page, show="headings", height=14)
            sb_y = ttk.Scrollbar(page, orient="vertical", command=tree.yview)
            sb_x = ttk.Scrollbar(page, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
            tree.grid(row=0, column=0, sticky="nsew")
            sb_y.grid(row=0, column=1, sticky="ns")
            sb_x.grid(row=1, column=0, sticky="ew")
            tree["columns"] = ["info"]
            tree.heading("info", text="info")
            tree.insert("", "end", values=["(pilih workbook B lalu klik Bandingkan)"])
            self._period_trees[key] = tree

        self._period_running = False
        self._period_result: dict | None = None

    # ------------------------------------------------------------
    # KONTROL
    # ------------------------------------------------------------

    def _browse_period_b(self):
        path = filedialog.askopenfilename(
            title="Pilih Workbook Periode Pembanding (B)",
            filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if path:
            self.var_period_b.set(path)

    def _start_period_compare(self):
        """Validasi input → jalankan pipeline B di background thread."""
        if self._period_running:
            return
        df_a = self._preview_dfs.get("Detail")
        if df_a is None or df_a.empty:
            messagebox.showinfo("Compare Periode",
                                "Belum ada run periode A. Run pipeline dulu.")
            return
        wb_b = self.var_period_b.get().strip()
        if not wb_b or not Path(wb_b).exists():
            messagebox.showerror("Input Error",
                                 "Workbook periode B belum dipilih / tidak ditemukan.")
            return

        label_a = self._period_label_a()
        label_b = Path(wb_b).stem
        config_snapshot = dict(self.config)  # read-only snapshot untuk thread

        self._period_running = True
        self.btn_period_run.configure(state="disabled")
        # Jangan biarkan run utama jalan bersamaan (race state summary).
        if hasattr(self, "btn_run"):
            self.btn_run.configure(state="disabled")
        self.lbl_period_status.configure(
            text=f"Membaca {label_b} & mendeteksi key_akhir otomatis…", fg="#0369a1")
        self.log(f"=== Compare Periode: A={label_a} vs B={label_b} ===")

        def _worker():
            try:
                raw_b = load_rekap_mentah(wb_b, config_snapshot)
                if raw_b is None or raw_b.empty:
                    self.ui_queue.put((
                        "period_done",
                        {"success": False,
                         "error": f"Sheet rekap kosong/tidak terbaca: {wb_b}"},
                        None,
                    ))
                    return
                ka_b = auto_key_akhir(raw_b)
                self.ui_queue.put(("log", f"[periode B] key_akhir otomatis = {ka_b}", None))
                summary_b = run_pipeline(
                    workbook_path=wb_b,
                    key_akhir=ka_b,
                    progress_callback=lambda msg, pct: self.ui_queue.put(
                        ("log", f"[B] {msg}", pct)),
                )
                if not summary_b.get("success"):
                    self.ui_queue.put((
                        "period_done",
                        {"success": False,
                         "error": f"Pipeline periode B gagal: {summary_b.get('error', '?')}"},
                        None,
                    ))
                    return
                df_b = summary_b.get("df")
                result = compare_periods(df_a, df_b, label_a=label_a, label_b=label_b)
                result["success"] = True
                result["key_akhir_b"] = ka_b
                self.ui_queue.put(("period_done", result, None))
            except Exception as e:  # noqa: BLE001 — worker tidak boleh crash app
                self.ui_queue.put((
                    "period_done",
                    {"success": False, "error": str(e),
                     "tb": traceback.format_exc()},
                    None,
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _period_label_a(self) -> str:
        """Label periode A: nama file workbook run terakhir (fallback umum)."""
        try:
            wb = self.var_workbook.get().strip()
            if wb:
                return Path(wb).stem
        except Exception:  # noqa: BLE001 — label best-effort
            pass
        return "Run saat ini"

    # ------------------------------------------------------------
    # HASIL
    # ------------------------------------------------------------

    def _on_period_done(self, result: dict):
        """Handler hasil compare (dipanggil dari ui_queue di thread UI)."""
        self._period_running = False
        self.btn_period_run.configure(state="normal")
        if hasattr(self, "btn_run"):
            self.btn_run.configure(state="normal")
        if not result.get("success"):
            err = result.get("error", "Unknown error")
            self.lbl_period_status.configure(text=f"⚠ Gagal: {err}", fg="#dc2626")
            self.log(f"!!! Compare Periode gagal: {err}")
            if result.get("tb"):
                self.log(result["tb"])
            messagebox.showerror("Compare Periode", err)
            return

        self._period_result = result
        self.lbl_period_a.configure(
            text=f"{result.get('label_a', '?')} (run saat ini)")
        total = result["summary"]
        try:
            s = total.set_index("Metrik")
            ta = float(s.loc["Total Waste", "Periode A"])
            tb_ = float(s.loc["Total Waste", "Periode B"])
            dp = s.loc["Total Waste", "Delta %"]
            dp_txt = "∞" if pd.isna(dp) else f"{dp:+.1f}%"
            self.lbl_period_status.configure(
                text=f"✓ Selesai — Total waste {ta:,.0f} → {tb_:,.0f} ({dp_txt})",
                fg="#16a34a",
            )
        except Exception:  # noqa: BLE001 — status best-effort
            self.lbl_period_status.configure(text="✓ Selesai", fg="#16a34a")

        self._render_period_tables()

    def _render_period_tables(self):
        """Render semua tabel dari self._period_result (jika ada)."""
        result = self._period_result
        if not result:
            for tree in self._period_trees.values():
                tree.delete(*tree.get_children(""))
                tree["columns"] = ["info"]
                tree.heading("info", text="info")
                tree.insert("", "end",
                            values=["(pilih workbook B lalu klik Bandingkan)"])
            return
        for key in ("summary", "per_jenis", "branch", "items",
                    "new_items", "gone_items"):
            self._render_period_tree(key, result.get(key))

    def _render_period_tree(self, key: str, df: pd.DataFrame | None):
        tree = self._period_trees[key]
        tree.delete(*tree.get_children(""))
        if df is None or df.empty:
            tree["columns"] = ["info"]
            tree.heading("info", text="info")
            tree.insert("", "end", values=["(kosong)"])
            return
        self._period_dfs[key] = df
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=str(c))
            anchor = "e" if c not in ("Metrik", "NAMA RESTO", "NAMA BARANG", "JENIS") else "w"
            tree.column(c, width=110 if anchor == "e" else 150, anchor=anchor)
        for _, row in df.iterrows():
            tree.insert("", "end", values=[self._format_cell(row[c]) for c in cols])


# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
