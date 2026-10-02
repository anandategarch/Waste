"""
ui_app.py — Tkinter professional dashboard untuk Waste Anomaly Detection.

Versi: 2.0.0  (PROFESSIONAL REBUILD)

Fitur baru:
  - Layout dashboard-style (KPI cards + filter bar + drill-down table + interactive charts)
  - KPI cards: total baris, prioritas, potensi, perlu review, total waste, cabang count
  - Filter bar: search + dropdown cabang/JENIS/KETERANGAN/status + clear filter
  - Interactive charts: klik bar/slice → auto-filter table + re-render charts lain (drill-down)
  - Active filter chips (clickable untuk remove)
  - Detail table dengan pagination + sortable columns
  - Export buttons (Excel + PNG charts)

Tabs:
  1. Dashboard     — KPI + filter + interactive charts + drill-down table
  2. Hasil         — preview tabel hasil (Detail/Anomali/Cabang/Top/Pareto)
  3. Visualisasi   — 12 grafik matplotlib (full charts gallery)
  4. Ringkasan     — summary run terakhir
  5. Konfigurasi   — threshold editor
  6. Bantuan       — instruksi pakai + 12 sinyal + troubleshooting
  7. Run Pipeline  — pilih workbook + Key Akhir + Run + log
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Set matplotlib backend ke TkAgg SEBELUM import charts (untuk embedded rendering)
import matplotlib
matplotlib.use("TkAgg")

# Pastikan module lokal ke-import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.utils import load_config, CONFIG_PATH
from waste_anomaly import charts as wa_charts
from waste_anomaly import dashboard as wa_dash
from waste_anomaly import filters as wa_filters

APP_VERSION = "2.1.0"
APP_TITLE = "Waste Anomaly Detection — Pro Dashboard"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = APP_DIR / "output" / "Waste_Anomaly_Report.xlsx"

# ============================================================
# STYLE
# ============================================================
FONT_NAME = "Segoe UI"
MONO_NAME = "Consolas"
F_APP_TITLE = (FONT_NAME, 14, "bold")
F_CARD = (FONT_NAME, 10, "bold")
F_BODY = (FONT_NAME, 9)
F_HINT = (FONT_NAME, 8)
F_LOG = (MONO_NAME, 9)
F_KPI_NUM = (FONT_NAME, 18, "bold")
F_KPI_LABEL = (FONT_NAME, 8)

C_BG = "#f1f5f9"            # slate-100
C_CARD = "#ffffff"           # white
C_HEADER = "#0f172a"        # slate-900
C_FOOTER = "#e2e8f0"        # slate-200
C_TERM_BG = "#0b1220"
C_BORDER = "#e2e8f0"
C_HOVER = "#f8fafc"

# Status colors (match charts.py)
C_STATUS = {
    "Prioritas Tinggi": ("#dc2626", "#fef2f2"),  # (fg, bg-light)
    "Potensi Anomali":  ("#ea580c", "#fff7ed"),
    "Perlu Review":     ("#b45309", "#fffbeb"),
    "Normal":           ("#16a34a", "#f0fdf4"),
}


# ============================================================
# POPUP LOG WINDOW
# ============================================================

class SimpleLogPopup(tk.Toplevel):
    def __init__(self, parent, title="Log Proses"):
        super().__init__(parent)
        self.title(title)
        self.geometry("800x500")
        self.minsize(600, 300)
        self._build()

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        self.text = tk.Text(
            frm, wrap="word", state="disabled",
            bg=C_TERM_BG, fg="#d1d5db", font=F_LOG,
            padx=10, pady=10, relief="flat",
        )
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(frm_btn, text="Bersihkan", command=self.clear).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Salin Log", command=self.copy_log).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Tutup", command=self.withdraw).pack(side="right", padx=4)

    def append(self, msg: str):
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def copy_log(self):
        content = self.text.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)


# ============================================================
# KPI CARD WIDGET
# ============================================================

class KPICard(tk.Frame):
    """KPI card dengan angka besar + label + warna tema."""

    def __init__(self, parent, label: str, value: str = "0", color: str = "#0f172a", bg: str = "#ffffff"):
        super().__init__(parent, bg=bg, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
        self._label_var = tk.StringVar(value=label)
        self._value_var = tk.StringVar(value=value)
        self._color = color

        # Padding
        self.columnconfigure(0, weight=1)
        # Label
        lbl = tk.Label(self, textvariable=self._label_var, font=F_KPI_LABEL,
                       fg="#64748b", bg=bg, anchor="w")
        lbl.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        # Value
        self.val_lbl = tk.Label(self, textvariable=self._value_var, font=F_KPI_NUM,
                                fg=color, bg=bg, anchor="w")
        self.val_lbl.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

    def set_value(self, value: str):
        self._value_var.set(value)

    def set_color(self, color: str):
        self._color = color
        self.val_lbl.configure(fg=color)


# ============================================================
# FILTER CHIP WIDGET (clickable untuk remove)
# ============================================================

class FilterChip(tk.Frame):
    """Chip kecil menampilkan active filter; klik × untuk remove."""

    def __init__(self, parent, label: str, on_remove):
        super().__init__(parent, bg="#fef3c7", relief="flat",
                         highlightbackground="#fcd34d", highlightthickness=1)
        self._on_remove = on_remove
        tk.Label(self, text=label, font=F_HINT, fg="#92400e", bg="#fef3c7").pack(side="left", padx=(6, 2), pady=2)
        btn = tk.Label(self, text="×", font=(FONT_NAME, 10, "bold"), fg="#92400e", bg="#fef3c7",
                       cursor="hand2")
        btn.pack(side="left", padx=(0, 6))
        btn.bind("<Button-1>", lambda e: on_remove())


# ============================================================
# MAIN APP
# ============================================================

class WasteAnomalyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("1400x880")
        self.minsize(1100, 700)
        self.configure(bg=C_BG)

        # State
        self.config = load_config()
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.log_popup: SimpleLogPopup | None = None
        self.last_output_path: str | None = None
        self.last_summary: dict | None = None
        self._preview_dfs: dict[str, "pd.DataFrame"] = {}

        # Drill-down state: dict filter_key -> value (None artinya no filter)
        # jenis: list[str] (multi-select), day_min/day_max: int 1-31
        self.active_filters: dict[str, str | list[str] | None] = {
            "cabang": None, "item": None, "jenis": [],
            "keterangan": None, "status": None,
        }
        self.day_min: int | None = None  # filter HARI MAX dalam range
        self.day_max: int | None = None

        # Filter profile state
        self._filter_profiles: dict[str, dict] = {}

        self._build_styles()
        self._build_header()
        self._build_tabs()
        self._build_footer()
        self.after(100, self._drain_queue)

    # --------------------------------------------------------
    # STYLES
    # --------------------------------------------------------
    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=C_BG)
        style.configure("Card.TFrame", background=C_CARD)
        style.configure("TLabel", background=C_BG, font=F_BODY, foreground="#1F2937")
        style.configure("Card.TLabel", background=C_CARD, font=F_BODY, foreground="#1F2937")
        style.configure("CardTitle.TLabel", background=C_CARD, font=F_CARD, foreground=C_HEADER)
        style.configure("Hint.TLabel", background=C_BG, font=F_HINT, foreground="#6B7280")
        style.configure("TButton", font=F_BODY, padding=4)
        style.configure("Accent.TButton", font=(FONT_NAME, 9, "bold"), padding=6)
        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 6), font=F_BODY)
        style.map("TNotebook.Tab",
                  background=[("selected", C_CARD)],
                  foreground=[("selected", C_HEADER)])
        style.configure("TEntry", fieldbackground=C_CARD, padding=3)
        style.configure("TCombobox", padding=3)
        # Treeview
        style.configure("Treeview", font=F_BODY, rowheight=22, background=C_CARD, fieldbackground=C_CARD)
        style.configure("Treeview.Heading", font=(FONT_NAME, 9, "bold"), background="#f1f5f9", foreground=C_HEADER)
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", C_HEADER)])

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------
    def _build_header(self):
        hdr = tk.Frame(self, bg=C_HEADER, height=50)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        lbl = tk.Label(hdr, text=f"  📊  {APP_TITLE}", font=F_APP_TITLE, fg="white", bg=C_HEADER)
        lbl.pack(side="left", padx=16, pady=10)
        sub = tk.Label(hdr, text=f"v{APP_VERSION}  •  Replika Power Query M code  •  12 sinyal anomali + drill-down",
                       font=F_HINT, fg="#94a3b8", bg=C_HEADER)
        sub.pack(side="left", padx=8)

    # --------------------------------------------------------
    # TABS
    # --------------------------------------------------------
    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Tab 1: Dashboard (PRO)
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="📊 Dashboard")
        self._build_dashboard_tab(tab1)

        # Tab 2: Compare Cabang (NEW v2.1)
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="⚖ Compare Cabang")
        self._build_compare_tab(tab2)

        # Tab 3: Hasil
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="📋 Hasil")
        self._build_result_tab(tab3)

        # Tab 4: Visualisasi (12 chart gallery)
        tab4 = ttk.Frame(nb)
        nb.add(tab4, text="📈 Visualisasi")
        self._build_viz_tab(tab4)

        # Tab 5: Ringkasan
        tab5 = ttk.Frame(nb)
        nb.add(tab5, text="🗂 Ringkasan")
        self._build_summary_tab(tab5)

        # Tab 6: Run Pipeline
        tab6 = ttk.Frame(nb)
        nb.add(tab6, text="▶ Run Pipeline")
        self._build_run_tab(tab6)

        # Tab 7: Konfigurasi
        tab7 = ttk.Frame(nb)
        nb.add(tab7, text="⚙ Konfigurasi")
        self._build_config_tab(tab7)

        # Tab 8: Bantuan
        tab8 = ttk.Frame(nb)
        nb.add(tab8, text="❓ Bantuan")
        self._build_help_tab(tab8)

        # Load saved filter profiles
        self._filter_profiles = wa_filters.load_profiles()

    # --------------------------------------------------------
    # TAB 1: DASHBOARD (PRO — drill-down)
    # --------------------------------------------------------
    def _build_dashboard_tab(self, parent):
        """Dashboard layout: KPI cards row + filter bar + interactive charts + drill-down table."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        # ===== Row 0: KPI cards =====
        kpi_frame = tk.Frame(parent, bg=C_BG)
        kpi_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        kpi_frame.columnconfigure(0, weight=1, uniform="kpi")
        kpi_frame.columnconfigure(1, weight=1, uniform="kpi")
        kpi_frame.columnconfigure(2, weight=1, uniform="kpi")
        kpi_frame.columnconfigure(3, weight=1, uniform="kpi")
        kpi_frame.columnconfigure(4, weight=1, uniform="kpi")
        kpi_frame.columnconfigure(5, weight=1, uniform="kpi")

        self.kpi_total = KPICard(kpi_frame, "TOTAL BARIS", "0", "#0f172a")
        self.kpi_total.grid(row=0, column=0, sticky="ew", padx=2)
        self.kpi_prioritas = KPICard(kpi_frame, "PRIORITAS TINGGI", "0", "#dc2626")
        self.kpi_prioritas.grid(row=0, column=1, sticky="ew", padx=2)
        self.kpi_potensi = KPICard(kpi_frame, "POTENSI ANOMALI", "0", "#ea580c")
        self.kpi_potensi.grid(row=0, column=2, sticky="ew", padx=2)
        self.kpi_review = KPICard(kpi_frame, "PERLU REVIEW", "0", "#b45309")
        self.kpi_review.grid(row=0, column=3, sticky="ew", padx=2)
        self.kpi_waste = KPICard(kpi_frame, "TOTAL WASTE", "0", "#0f766e")
        self.kpi_waste.grid(row=0, column=4, sticky="ew", padx=2)
        self.kpi_cabang = KPICard(kpi_frame, "CABANG", "0", "#9333ea")
        self.kpi_cabang.grid(row=0, column=5, sticky="ew", padx=2)

        # ===== Row 1: Filter bar (extended v2.1) =====
        filter_frame = tk.Frame(parent, bg=C_CARD, relief="flat",
                               highlightbackground=C_BORDER, highlightthickness=1)
        filter_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        filter_frame.columnconfigure(13, weight=1)

        # --- Row 0 of filter: search + cabang + status + clear ---
        tk.Label(filter_frame, text="🔍 Filter Drill-Down:", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).grid(row=0, column=0, padx=(10, 6), pady=6, sticky="w")

        tk.Label(filter_frame, text="Cari:", font=F_BODY, bg=C_CARD).grid(row=0, column=1, padx=2)
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._apply_dashboard_filter())
        ttk.Entry(filter_frame, textvariable=self.var_search, width=20).grid(row=0, column=2, padx=2)

        tk.Label(filter_frame, text="Cabang:", font=F_BODY, bg=C_CARD).grid(row=0, column=3, padx=(8, 2))
        self.var_filter_cabang = tk.StringVar(value="(Semua)")
        self._cb_cabang = ttk.Combobox(filter_frame, textvariable=self.var_filter_cabang, width=15, state="readonly")
        self._cb_cabang.grid(row=0, column=4, padx=2)
        self._cb_cabang.bind("<<ComboboxSelected>>", lambda e: self._on_filter_dropdown_change("cabang", self.var_filter_cabang.get()))

        tk.Label(filter_frame, text="Status:", font=F_BODY, bg=C_CARD).grid(row=0, column=5, padx=(8, 2))
        self.var_filter_status = tk.StringVar(value="(Semua)")
        self._cb_status = ttk.Combobox(filter_frame, textvariable=self.var_filter_status, width=14, state="readonly")
        self._cb_status["values"] = ["(Semua)", "Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
        self._cb_status.grid(row=0, column=6, padx=2)
        self._cb_status.bind("<<ComboboxSelected>>", lambda e: self._on_filter_dropdown_change("status", self.var_filter_status.get()))

        self.btn_clear_filter = ttk.Button(filter_frame, text="✕ Clear Filter", command=self._clear_all_filters)
        self.btn_clear_filter.grid(row=0, column=14, sticky="e", padx=10)

        # --- Row 1 of filter: JENIS checkboxes + Day range + profile save/load (NEW v2.1) ---
        tk.Label(filter_frame, text="JENIS:", font=F_BODY, bg=C_CARD).grid(row=1, column=0, padx=(10, 6), pady=4, sticky="w")

        # JENIS multi-select checkboxes
        jenis_frame = tk.Frame(filter_frame, bg=C_CARD)
        jenis_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=2, pady=4)
        self._jenis_vars: dict[str, tk.BooleanVar] = {}
        for j in ["WASTE", "SUSUT", "TRIAL"]:
            v = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(jenis_frame, text=j, variable=v, bg=C_CARD, font=F_BODY,
                              command=self._on_jenis_changed)
            cb.pack(side="left", padx=2)
            self._jenis_vars[j] = v

        # Day range filter (HARI MAX in range)
        tk.Label(filter_frame, text="Hari MAX:", font=F_BODY, bg=C_CARD).grid(row=1, column=3, padx=(8, 2))
        self.var_day_min = tk.IntVar(value=1)
        self.var_day_max = tk.IntVar(value=31)
        day_frame = tk.Frame(filter_frame, bg=C_CARD)
        day_frame.grid(row=1, column=4, columnspan=2, sticky="w", padx=2, pady=4)
        ttk.Spinbox(day_frame, from_=1, to=31, textvariable=self.var_day_min, width=4,
                     command=self._on_day_range_changed).pack(side="left")
        tk.Label(day_frame, text=" – ", bg=C_CARD, font=F_BODY).pack(side="left")
        ttk.Spinbox(day_frame, from_=1, to=31, textvariable=self.var_day_max, width=4,
                     command=self._on_day_range_changed).pack(side="left")
        tk.Label(day_frame, text="(filter HARI MAX di range)", bg=C_CARD, font=F_HINT, fg="#94a3b8").pack(side="left", padx=4)

        # Profile save/load
        tk.Label(filter_frame, text="Profil:", font=F_BODY, bg=C_CARD).grid(row=1, column=7, padx=(8, 2))
        self.var_profile_name = tk.StringVar()
        self._cb_profiles = ttk.Combobox(filter_frame, textvariable=self.var_profile_name, width=18, state="readonly")
        self._cb_profiles.grid(row=1, column=8, padx=2)
        self._refresh_profile_dropdown()
        ttk.Button(filter_frame, text="💾 Load", command=self._load_selected_profile).grid(row=1, column=9, padx=2)
        ttk.Button(filter_frame, text="💾 Save As…", command=self._save_profile_dialog).grid(row=1, column=10, padx=2)
        ttk.Button(filter_frame, text="🗑", width=3, command=self._delete_selected_profile).grid(row=1, column=11, padx=2)

        # Active filter chips container (row 2)
        self.chips_frame = tk.Frame(filter_frame, bg=C_CARD)
        self.chips_frame.grid(row=2, column=0, columnspan=15, sticky="ew", padx=10, pady=(0, 6))
        self.chips_frame.columnconfigure(0, weight=1)

        # ===== Row 2: Interactive charts (3 charts) =====
        charts_frame = tk.Frame(parent, bg=C_BG)
        charts_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        charts_frame.columnconfigure(0, weight=1, uniform="chart")
        charts_frame.columnconfigure(1, weight=1, uniform="chart")
        charts_frame.columnconfigure(2, weight=1, uniform="chart")

        self._dash_chart_frames = []
        for i in range(3):
            f = tk.Frame(charts_frame, bg=C_CARD, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
            f.grid(row=0, column=i, sticky="nsew", padx=2)
            f.columnconfigure(0, weight=1)
            f.rowconfigure(1, weight=1)
            self._dash_chart_frames.append(f)

        # ===== Row 3: Drill-down detail table =====
        detail_frame = tk.Frame(parent, bg=C_CARD, relief="flat",
                                highlightbackground=C_BORDER, highlightthickness=1)
        detail_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)

        # Header
        hdr = tk.Frame(detail_frame, bg=C_CARD)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        tk.Label(hdr, text="📋 Drill-Down Detail Table", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).pack(side="left")
        self.lbl_detail_count = tk.Label(hdr, text="(belum ada data)", font=F_HINT, fg="#6B7280", bg=C_CARD)
        self.lbl_detail_count.pack(side="left", padx=8)
        ttk.Button(hdr, text="Export Excel", command=self._export_filtered_excel).pack(side="right", padx=4)

        # Treeview with scrollbars
        tree_wrap = tk.Frame(detail_frame, bg=C_CARD)
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.tree_dashboard = ttk.Treeview(tree_wrap, show="headings")
        sb_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_dashboard.yview)
        sb_x = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree_dashboard.xview)
        self.tree_dashboard.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree_dashboard.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        # Bind click on treeview row to drill-down (set filter to that row's cabang+item)
        self.tree_dashboard.bind("<Double-1>", self._on_tree_double_click)

        # Status placeholder
        self._dash_canvases = []
        self._set_dashboard_placeholder()

    def _set_dashboard_placeholder(self):
        """Tampilkan placeholder sebelum run pipeline."""
        for widget in self._dash_chart_frames:
            for c in widget.winfo_children():
                c.destroy()
        for f in self._dash_chart_frames:
            tk.Label(f, text="📊\n\nBelum ada data.\n\nJalankan pipeline\ndi tab 'Run Pipeline'.",
                     font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center").grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        # Clear tree
        self.tree_dashboard.delete(*self.tree_dashboard.get_children())
        self.tree_dashboard["columns"] = ["info"]
        self.tree_dashboard.heading("info", text="info")
        self.tree_dashboard.insert("", "end", values=["(jalankan pipeline untuk lihat data)"])

    # --------------------------------------------------------
    # FILTER LOGIC (drill-down)
    # --------------------------------------------------------
    def _on_filter_dropdown_change(self, key: str, value: str):
        if value == "(Semua)":
            self.active_filters[key] = None
        else:
            self.active_filters[key] = value
        self._apply_dashboard_filter()

    def _on_jenis_changed(self):
        """Update active_filters['jenis'] dari checkboxes (multi-select)."""
        selected = [j for j, v in self._jenis_vars.items() if v.get()]
        self.active_filters["jenis"] = selected if selected else []
        self._apply_dashboard_filter()

    def _on_day_range_changed(self):
        """Update day_min/day_max dari spinboxes."""
        try:
            dmin = int(self.var_day_min.get())
            dmax = int(self.var_day_max.get())
            if dmin < 1: dmin = 1
            if dmax > 31: dmax = 31
            if dmin > dmax: dmin, dmax = dmax, dmin
            self.day_min = dmin if (dmin != 1 or dmax != 31) else None
            self.day_max = dmax if (dmin != 1 or dmax != 31) else None
        except (ValueError, TypeError):
            self.day_min = None
            self.day_max = None
        self._apply_dashboard_filter()

    def _on_chart_click(self, key: str, value: str | None):
        """Handler untuk klik chart. value=None artinya clear filter ini."""
        self.active_filters[key] = value
        # Sync dropdown UI
        if key == "cabang":
            self.var_filter_cabang.set(value if value else "(Semua)")
        elif key == "status":
            self.var_filter_status.set(value if value else "(Semua)")
        self._apply_dashboard_filter()

    def _clear_all_filters(self):
        for k in self.active_filters:
            if k == "jenis":
                self.active_filters[k] = []
            else:
                self.active_filters[k] = None
        self.day_min = None
        self.day_max = None
        self.var_search.set("")
        self.var_filter_cabang.set("(Semua)")
        self.var_filter_status.set("(Semua)")
        self.var_day_min.set(1)
        self.var_day_max.set(31)
        for v in self._jenis_vars.values():
            v.set(False)
        self._apply_dashboard_filter()

    def _apply_dashboard_filter(self):
        """Apply all active filters + re-render charts + table."""
        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            return

        filtered = df.copy()
        for key, val in self.active_filters.items():
            if val is None or (isinstance(val, list) and not val):
                continue
            if key == "cabang" and "NAMA RESTO" in filtered.columns:
                filtered = filtered[filtered["NAMA RESTO"] == val]
            elif key == "item" and "NAMA BARANG" in filtered.columns:
                filtered = filtered[filtered["NAMA BARANG"] == val]
            elif key == "jenis" and "JENIS" in filtered.columns and isinstance(val, list):
                filtered = filtered[filtered["JENIS"].isin(val)]
            elif key == "keterangan" and "KETERANGAN" in filtered.columns:
                filtered = filtered[filtered["KETERANGAN"] == val]
            elif key == "status" and "ANOMALY STATUS" in filtered.columns:
                filtered = filtered[filtered["ANOMALY STATUS"] == val]

        # Apply day range filter (HARI MAX in [day_min, day_max])
        if (self.day_min is not None and self.day_max is not None
                and "HARI MAX" in filtered.columns):
            hari_max = pd.to_numeric(filtered["HARI MAX"], errors="coerce")
            filtered = filtered[
                hari_max.between(self.day_min, self.day_max, inclusive="both")
                | hari_max.isna()  # keep rows where HARI MAX is null
            ]

        # Apply search
        search = self.var_search.get().strip().lower()
        if search:
            mask = filtered.apply(
                lambda row: any(search in str(v).lower() for v in row.values),
                axis=1,
            )
            filtered = filtered[mask]

        # Update chips
        self._update_filter_chips()
        # Re-render charts & table
        self._render_dashboard_charts(filtered)
        self._render_dashboard_table(filtered)

    def _update_filter_chips(self):
        for c in self.chips_frame.winfo_children():
            c.destroy()
        active_items = []
        for k, v in self.active_filters.items():
            if v is None or (isinstance(v, list) and not v):
                continue
            if isinstance(v, list):
                active_items.append((k, ", ".join(v)))
            else:
                active_items.append((k, v))
        # Add day range chip
        if self.day_min is not None and self.day_max is not None:
            active_items.append(("Hari MAX", f"{self.day_min}-{self.day_max}"))
        # Add search chip
        search = self.var_search.get().strip()
        if search:
            active_items.append(("search", f'"{search}"'))

        if not active_items:
            tk.Label(self.chips_frame, text="Tidak ada filter aktif. Klik bar chart di atas untuk drill-down.",
                     font=F_HINT, fg="#94a3b8", bg=C_CARD).grid(row=0, column=0, sticky="w")
            return
        col = 0
        for k, v in active_items:
            chip = FilterChip(self.chips_frame, f"{k}: {v}",
                              on_remove=lambda key=k: self._remove_filter(key))
            chip.grid(row=0, column=col, sticky="w", padx=2)
            col += 1

    def _remove_filter(self, key: str):
        if key == "jenis":
            self.active_filters[key] = []
            for v in self._jenis_vars.values():
                v.set(False)
        elif key == "Hari MAX":
            self.day_min = None
            self.day_max = None
            self.var_day_min.set(1)
            self.var_day_max.set(31)
        elif key == "search":
            self.var_search.set("")
            return  # already triggers apply via trace
        else:
            self.active_filters[key] = None
            if key == "cabang":
                self.var_filter_cabang.set("(Semua)")
            elif key == "status":
                self.var_filter_status.set("(Semua)")
        self._apply_dashboard_filter()

    # --------------------------------------------------------
    # FILTER PROFILE MANAGEMENT (NEW v2.1)
    # --------------------------------------------------------
    def _refresh_profile_dropdown(self):
        names = wa_filters.list_profile_names()
        self._cb_profiles["values"] = names
        if names and not self.var_profile_name.get():
            self.var_profile_name.set(names[0])

    def _save_profile_dialog(self):
        """Prompt user for profile name, save current filter state."""
        from tkinter import simpledialog
        name = simpledialog.askstring("Save Profile", "Nama profil filter:",
                                       parent=self,
                                       initialvalue=self.var_profile_name.get() or "Profil Baru")
        if not name:
            return
        profile = wa_filters.snapshot_filters(
            search=self.var_search.get().strip(),
            cabang=self.active_filters.get("cabang"),
            item=self.active_filters.get("item"),
            jenis=self.active_filters.get("jenis") or [],
            keterangan=self.active_filters.get("keterangan"),
            status=self.active_filters.get("status"),
            day_min=self.day_min,
            day_max=self.day_max,
        )
        if wa_filters.save_profile(name, profile):
            self._filter_profiles = wa_filters.load_profiles()
            self._refresh_profile_dropdown()
            self.var_profile_name.set(name)
            messagebox.showinfo("Profile", f"Profil '{name}' disimpan.")
        else:
            messagebox.showerror("Profile Error", f"Gagal simpan profil '{name}'.")

    def _load_selected_profile(self):
        """Load selected profile from dropdown."""
        name = self.var_profile_name.get()
        if not name:
            messagebox.showwarning("Profile", "Pilih profil dulu.")
            return
        profile = wa_filters.get_profile(name)
        if not profile:
            messagebox.showerror("Profile", f"Profil '{name}' tidak ditemukan.")
            return
        # Restore state
        self.var_search.set(profile.get("search", ""))
        cabang = profile.get("cabang")
        self.var_filter_cabang.set(cabang if cabang else "(Semua)")
        status = profile.get("status")
        self.var_filter_status.set(status if status else "(Semua)")
        jenis = profile.get("jenis", [])
        for j, v in self._jenis_vars.items():
            v.set(j in jenis)
        self.active_filters = {
            "cabang": cabang,
            "item": profile.get("item"),
            "jenis": jenis,
            "keterangan": profile.get("keterangan"),
            "status": status,
        }
        self.day_min = profile.get("day_min")
        self.day_max = profile.get("day_max")
        if self.day_min and self.day_max:
            self.var_day_min.set(self.day_min)
            self.var_day_max.set(self.day_max)
        else:
            self.var_day_min.set(1)
            self.var_day_max.set(31)
        self._apply_dashboard_filter()
        messagebox.showinfo("Profile", f"Profil '{name}' di-load.")

    def _delete_selected_profile(self):
        """Delete selected profile from dropdown."""
        name = self.var_profile_name.get()
        if not name:
            return
        if not messagebox.askyesno("Hapus Profil", f"Hapus profil '{name}'?"):
            return
        if wa_filters.delete_profile(name):
            self._filter_profiles = wa_filters.load_profiles()
            self._refresh_profile_dropdown()
            messagebox.showinfo("Profile", f"Profil '{name}' dihapus.")

    # --------------------------------------------------------
    # RENDER DASHBOARD CHARTS (interactive)
    # --------------------------------------------------------
    def _render_dashboard_charts(self, df: pd.DataFrame):
        # Destroy existing
        self._dash_canvases = []
        for widget, frame in zip([wa_dash.chart_status_bar_interactive,
                                   wa_dash.chart_cabang_bar_interactive,
                                   wa_dash.chart_top_items_interactive],
                                  self._dash_chart_frames):
            for c in frame.winfo_children():
                c.destroy()

        if df.empty:
            for f in self._dash_chart_frames:
                tk.Label(f, text="(tidak ada data\nuntuk filter ini)",
                         font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center").grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            return

        # Build active_filter tuple untuk highlight
        def _af(key):
            return (key, self.active_filters.get(key))

        # Chart 1: Status bar (interactive)
        f0 = self._dash_chart_frames[0]
        fig0 = wa_dash.chart_status_bar_interactive(df, on_click=self._on_chart_click, active_filter=_af("status"))
        c0 = wa_charts.embed_figure(f0, fig0)
        c0.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("status", fig0, c0))

        # Chart 2: Cabang bar (interactive)
        f1 = self._dash_chart_frames[1]
        fig1 = wa_dash.chart_cabang_bar_interactive(df, on_click=self._on_chart_click, active_filter=_af("cabang"))
        c1 = wa_charts.embed_figure(f1, fig1)
        c1.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("cabang", fig1, c1))

        # Chart 3: Top items (interactive)
        f2 = self._dash_chart_frames[2]
        fig2 = wa_dash.chart_top_items_interactive(df, on_click=self._on_chart_click, active_filter=_af("item"))
        c2 = wa_charts.embed_figure(f2, fig2)
        c2.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("item", fig2, c2))

    # --------------------------------------------------------
    # RENDER DASHBOARD TABLE
    # --------------------------------------------------------
    def _render_dashboard_table(self, df: pd.DataFrame):
        # Reset
        self.tree_dashboard.delete(*self.tree_dashboard.get_children())
        if df.empty:
            self.tree_dashboard["columns"] = ["info"]
            self.tree_dashboard.heading("info", text="info")
            self.tree_dashboard.insert("", "end", values=["(tidak ada baris untuk filter ini)"])
            self.lbl_detail_count.configure(text="0 baris")
            return

        # Pilih kolom utama untuk tampil (lainnya ada di Excel export)
        display_cols = [
            "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
            "TOTAL", "MAX", "Count Hari",
            "ANOMALY SCORE", "ANOMALY STATUS", "ANOMALY REASONS",
            "KATEGORI ANOMALI", "RANGKING WASTE",
        ]
        cols = [c for c in display_cols if c in df.columns]
        self.tree_dashboard["columns"] = cols
        for c in cols:
            self.tree_dashboard.heading(c, text=c, command=lambda col=c: self._sort_treeview(col))
            self.tree_dashboard.column(c, width=110, stretch=False)

        # Limit to 500 rows for performance
        rows_to_show = df[cols].head(500)
        # Track row tags for status coloring
        status_col_idx = cols.index("ANOMALY STATUS") if "ANOMALY STATUS" in cols else None
        for row_idx, row in enumerate(rows_to_show.itertuples(index=False, name=None)):
            vals = []
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 3))
                else:
                    vals.append(v)
            tag = ""
            if status_col_idx is not None and vals[status_col_idx] in C_STATUS:
                tag = f"status_{row_idx % 2}"
                # Use status name as tag for coloring
                tag = vals[status_col_idx].replace(" ", "_").lower()
            self.tree_dashboard.insert("", "end", values=vals, tags=(tag,) if tag else ())

        # Configure tag colors
        for status, (fg, bg) in C_STATUS.items():
            tag = status.replace(" ", "_").lower()
            self.tree_dashboard.tag_configure(tag, background=bg, foreground=fg)

        count = len(df)
        self.lbl_detail_count.configure(text=f"{count} baris (showing first {min(500, count)})")

    def _sort_treeview(self, col: str):
        """Sort treeview by column (toggle asc/desc)."""
        items = [(self.tree_dashboard.set(k, col), k) for k in self.tree_dashboard.get_children("")]
        try:
            # Try numeric sort
            items.sort(key=lambda t: float(t[0]) if t[0] not in ("", None) else 0.0, reverse=getattr(self, "_sort_desc", False))
        except (ValueError, TypeError):
            items.sort(key=lambda t: str(t[0]), reverse=getattr(self, "_sort_desc", False))
        for i, (_, k) in enumerate(items):
            self.tree_dashboard.move(k, "", i)
        self._sort_desc = not getattr(self, "_sort_desc", False)

    def _on_tree_double_click(self, event):
        """Double-click row → drill-down: set filter cabang + item dari row."""
        selection = self.tree_dashboard.selection()
        if not selection:
            return
        item = selection[0]
        vals = self.tree_dashboard.item(item, "values")
        if not vals:
            return
        cols = self.tree_dashboard["columns"]
        # Cari NAMA RESTO & NAMA BARANG
        try:
            cabang = vals[cols.index("NAMA RESTO")] if "NAMA RESTO" in cols else None
            item_name = vals[cols.index("NAMA BARANG")] if "NAMA BARANG" in cols else None
        except (ValueError, IndexError):
            return
        if cabang and cabang != "(Semua)":
            self.active_filters["cabang"] = cabang
            self.var_filter_cabang.set(cabang)
        if item_name:
            self.active_filters["item"] = item_name
        self._apply_dashboard_filter()

    def _export_filtered_excel(self):
        """Export current filtered rows to Excel."""
        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            messagebox.showinfo("Export", "Belum ada data. Run pipeline dulu.")
            return
        # Apply current filters
        filtered = df.copy()
        for key, val in self.active_filters.items():
            if val is None:
                continue
            col_map = {"cabang": "NAMA RESTO", "item": "NAMA BARANG", "jenis": "JENIS",
                       "keterangan": "KETERANGAN", "status": "ANOMALY STATUS"}
            col_name = col_map.get(key)
            if col_name and col_name in filtered.columns:
                filtered = filtered[filtered[col_name] == val]
        search = self.var_search.get().strip().lower()
        if search:
            mask = filtered.apply(lambda row: any(search in str(v).lower() for v in row.values), axis=1)
            filtered = filtered[mask]

        path = filedialog.asksaveasfilename(
            title="Export Filtered Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=f"filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not path:
            return
        try:
            filtered.to_excel(path, index=False, engine="openpyxl")
            messagebox.showinfo("Export", f"{len(filtered)} baris diekspor ke:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # --------------------------------------------------------
    # UPDATE KPI CARDS
    # --------------------------------------------------------
    def _update_kpi_cards(self, df: pd.DataFrame, summary: dict):
        total = len(df)
        if "ANOMALY STATUS" in df.columns:
            prioritas = int((df["ANOMALY STATUS"] == "Prioritas Tinggi").sum())
            potensi = int((df["ANOMALY STATUS"] == "Potensi Anomali").sum())
            review = int((df["ANOMALY STATUS"] == "Perlu Review").sum())
            normal = int((df["ANOMALY STATUS"] == "Normal").sum())
        else:
            prioritas = potensi = review = normal = 0
        if "TOTAL" in df.columns:
            total_waste = float(df["TOTAL"].sum())
        else:
            total_waste = 0
        cabang = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 0

        self.kpi_total.set_value(f"{total:,}")
        self.kpi_prioritas.set_value(f"{prioritas:,}")
        self.kpi_potensi.set_value(f"{potensi:,}")
        self.kpi_review.set_value(f"{review:,}")
        self.kpi_waste.set_value(f"{total_waste:,.1f}")
        self.kpi_cabang.set_value(f"{cabang:,}")

        # Populate cabang dropdown
        if "NAMA RESTO" in df.columns:
            cabangs = sorted(df["NAMA RESTO"].dropna().astype(str).unique().tolist())
            self.var_filter_cabang.set("(Semua)")
            # Find combobox widget (we set it earlier but easier to use ttk.Combobox reference)
            # We need a stored reference — let's fetch from filter_frame
            # Quick fix: store on init
            if hasattr(self, "_cb_cabang"):
                self._cb_cabang["values"] = ["(Semua)"] + cabangs
            # Update Compare tab dropdowns too
            if hasattr(self, "_cb_compare_a"):
                self._cb_compare_a["values"] = cabangs
                self._cb_compare_b["values"] = cabangs

    # --------------------------------------------------------
    # TAB 2: COMPARE CABANG (NEW v2.1)
    # --------------------------------------------------------
    def _build_compare_tab(self, parent):
        """Side-by-side comparison of 2 cabang with 4 charts."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Card 1: selector
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1,
                      highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="⚖ Compare Cabang — Side-by-Side Analysis",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text="Pilih 2 cabang untuk dibandingkan. Lihat chart + metrics di bawah.",
                 font=F_HINT, fg="#6B7280", bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 8))

        selector = tk.Frame(c1, bg=C_CARD)
        selector.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(selector, text="Cabang A:", font=F_BODY, bg=C_CARD).pack(side="left", padx=2)
        self.var_compare_a = tk.StringVar()
        self._cb_compare_a = ttk.Combobox(selector, textvariable=self.var_compare_a, width=22, state="readonly")
        self._cb_compare_a.pack(side="left", padx=4)
        self._cb_compare_a.bind("<<ComboboxSelected>>", lambda e: self._render_compare_charts())

        tk.Label(selector, text="vs", font=F_BODY, bg=C_CARD, fg="#6B7280").pack(side="left", padx=8)
        tk.Label(selector, text="Cabang B:", font=F_BODY, bg=C_CARD).pack(side="left", padx=2)
        self.var_compare_b = tk.StringVar()
        self._cb_compare_b = ttk.Combobox(selector, textvariable=self.var_compare_b, width=22, state="readonly")
        self._cb_compare_b.pack(side="left", padx=4)
        self._cb_compare_b.bind("<<ComboboxSelected>>", lambda e: self._render_compare_charts())

        ttk.Button(selector, text="⟳ Refresh", command=self._render_compare_charts).pack(side="left", padx=8)
        ttk.Button(selector, text="Export PNG…", command=self._export_compare_charts).pack(side="left", padx=4)

        # Card 2: charts grid 2x2
        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1,
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

        # Card 3: metrics summary
        c3 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1,
                      highlightbackground=C_BORDER, highlightthickness=1)
        c3.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c3, text="📋 Metrics Summary", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_compare_metrics = tk.Label(c3, text="(pilih 2 cabang dulu)",
                                            bg=C_CARD, fg="#475569", font=F_BODY,
                                            anchor="w", justify="left")
        self.lbl_compare_metrics.pack(fill="x", padx=16, pady=(0, 12))

        # Placeholder
        self._compare_canvases = []
        for f in self._compare_chart_frames:
            tk.Label(f, text="⚖\n\nPilih Cabang A & B\nuntuk lihat comparison.",
                     font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)

    def _render_compare_charts(self):
        """Render 4 comparison charts for selected cabangs."""
        a = self.var_compare_a.get()
        b = self.var_compare_b.get()
        df = self._preview_dfs.get("Detail")

        # Destroy existing
        for f in self._compare_chart_frames:
            for c in f.winfo_children():
                c.destroy()
        self._compare_canvases = []

        if not a or not b or a == b:
            for f in self._compare_chart_frames:
                tk.Label(f, text="⚖\n\nPilih 2 cabang\nberbeda.",
                         font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center").grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.lbl_compare_metrics.configure(text="(pilih 2 cabang berbeda)")
            return
        if df is None or df.empty:
            for f in self._compare_chart_frames:
                tk.Label(f, text="(belum ada data)",
                         font=F_BODY, fg="#6B7280", bg=C_CARD).grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            return

        # Chart 1: Total waste per JENIS
        f0 = self._compare_chart_frames[0]
        fig0 = wa_dash.chart_compare_total_waste(df, a, b)
        c0 = wa_charts.embed_figure(f0, fig0)
        c0.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("total_waste", fig0))

        # Chart 2: Status comparison
        f1 = self._compare_chart_frames[1]
        fig1 = wa_dash.chart_compare_status(df, a, b)
        c1 = wa_charts.embed_figure(f1, fig1)
        c1.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("status", fig1))

        # Chart 3: Top items comparison
        f2 = self._compare_chart_frames[2]
        fig2 = wa_dash.chart_compare_top_items(df, a, b)
        c2 = wa_charts.embed_figure(f2, fig2)
        c2.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("top_items", fig2))

        # Chart 4: Metrics comparison
        f3 = self._compare_chart_frames[3]
        fig3 = wa_dash.chart_compare_score(df, a, b)
        c3 = wa_charts.embed_figure(f3, fig3)
        c3.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._compare_canvases.append(("metrics", fig3))

        # Update metrics summary text
        a_sub = df[df["NAMA RESTO"] == a]
        b_sub = df[df["NAMA RESTO"] == b]
        def _fmt(label, val_a, val_b, fmt="{:.1f}"):
            try:
                diff = float(val_a) - float(val_b)
                pct = (diff / float(val_b) * 100) if float(val_b) != 0 else 0
                sign = "↑" if diff > 0 else ("↓" if diff < 0 else "=")
                return f"{label}: A={fmt.format(float(val_a))} | B={fmt.format(float(val_b))} | {sign} {abs(diff):.1f} ({pct:+.1f}%)"
            except (ValueError, TypeError, ZeroDivisionError):
                return f"{label}: A={val_a} | B={val_b}"
        lines = [
            f"Cabang A: {a}  •  Cabang B: {b}",
            "",
            _fmt("Total Waste", a_sub["TOTAL"].sum() if "TOTAL" in a_sub.columns else 0,
                  b_sub["TOTAL"].sum() if "TOTAL" in b_sub.columns else 0, fmt="{:.0f}"),
            _fmt("Avg Waste/Barang", a_sub["TOTAL"].mean() if "TOTAL" in a_sub.columns else 0,
                  b_sub["TOTAL"].mean() if "TOTAL" in b_sub.columns else 0, fmt="{:.2f}"),
            _fmt("Max Single Day", a_sub["MAX"].max() if "MAX" in a_sub.columns else 0,
                  b_sub["MAX"].max() if "MAX" in b_sub.columns else 0, fmt="{:.1f}"),
            _fmt("Avg Anomali Score", a_sub["ANOMALY SCORE"].mean() if "ANOMALY SCORE" in a_sub.columns else 0,
                  b_sub["ANOMALY SCORE"].mean() if "ANOMALY SCORE" in b_sub.columns else 0),
            _fmt("Max Anomali Score", a_sub["ANOMALY SCORE"].max() if "ANOMALY SCORE" in a_sub.columns else 0,
                  b_sub["ANOMALY SCORE"].max() if "ANOMALY SCORE" in b_sub.columns else 0),
            f"Jumlah Prioritas: A={int((a_sub['ANOMALY STATUS'] == 'Prioritas Tinggi').sum()) if 'ANOMALY STATUS' in a_sub.columns else 0} | B={int((b_sub['ANOMALY STATUS'] == 'Prioritas Tinggi').sum()) if 'ANOMALY STATUS' in b_sub.columns else 0}",
            f"Jumlah Item: A={a_sub['NAMA BARANG'].nunique() if 'NAMA BARANG' in a_sub.columns else 0} | B={b_sub['NAMA BARANG'].nunique() if 'NAMA BARANG' in b_sub.columns else 0}",
        ]
        self.lbl_compare_metrics.configure(text="\n".join(lines))

    def _export_compare_charts(self):
        if not self._compare_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Pilih 2 cabang dulu.")
            return
        folder = filedialog.askdirectory(title="Pilih folder untuk simpan PNG")
        if not folder:
            return
        saved = 0
        a = self.var_compare_a.get() or "A"
        b = self.var_compare_b.get() or "B"
        for name, fig in self._compare_canvases:
            safe = f"compare_{a}_vs_{b}_{name}".replace(" ", "_").replace("/", "-")
            path = Path(folder) / f"{safe}.png"
            try:
                fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
                saved += 1
            except Exception as e:
                print(f"Failed save {name}: {e}", file=sys.stderr)
        messagebox.showinfo("Export", f"{saved} chart comparison disimpan ke:\n{folder}")

    # --------------------------------------------------------
    # TAB 3: HASIL (preview all sheets)
    # --------------------------------------------------------
    def _build_result_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Preview Hasil", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_result_sheet = tk.StringVar(value="Detail")
        ttk.Radiobutton(frm, text="Detail", variable=self.var_result_sheet, value="Detail", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Anomali Prioritas", variable=self.var_result_sheet, value="Anomali", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Per Cabang", variable=self.var_result_sheet, value="Cabang", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Top Items", variable=self.var_result_sheet, value="Top", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Pareto", variable=self.var_result_sheet, value="Pareto", command=self._refresh_preview).pack(side="left", padx=4)

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
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
        sheet_map = {
            "Detail": "Detail", "Anomali": "Anomali Prioritas",
            "Cabang": "Per Cabang", "Top": "Top Items", "Pareto": "Pareto Alasan",
        }
        sheet = sheet_map.get(self.var_result_sheet.get(), "Detail")
        df = self._preview_dfs.get(sheet)
        self.tree.delete(*self.tree.get_children())
        if df is None or df.empty:
            self.tree["columns"] = ["info"]
            self.tree.heading("info", text="info")
            self.tree.insert("", "end", values=["(tidak ada data — jalankan pipeline dulu)"])
            return
        cols = list(df.columns)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=str(c))
            self.tree.column(c, width=120, stretch=False)
        for row in df.head(500).itertuples(index=False, name=None):
            vals = []
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 4))
                else:
                    vals.append(v)
            self.tree.insert("", "end", values=vals)

    # --------------------------------------------------------
    # TAB 3: VISUALISASI (12 chart gallery)
    # --------------------------------------------------------
    def _build_viz_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        c = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c.columnconfigure(0, weight=1)
        c.rowconfigure(1, weight=1)

        hdr = tk.Frame(c, bg=C_CARD)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        tk.Label(hdr, text="Visualisasi & Grafik — 12 Chart Gallery", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(side="left")
        tk.Label(hdr, text="matplotlib • auto-update setelah run pipeline", font=F_HINT, fg="#6B7280", bg=C_CARD).pack(side="left", padx=12)
        self.btn_viz_refresh = ttk.Button(hdr, text="⟳ Refresh Grafik", command=self._refresh_viz)
        self.btn_viz_refresh.pack(side="right", padx=4)
        self.btn_viz_export = ttk.Button(hdr, text="Export Semua PNG…", command=self._export_all_charts)
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
        canvas.create_window((0, 0), window=self._viz_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        def _on_wheel(e):
            if hasattr(e, "num") and e.num:
                direction = -1 if e.num == 4 else 1
                canvas.yview_scroll(direction, "units")
            else:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel)
        canvas.bind_all("<Button-5>", _on_wheel)

        self._viz_placeholder = tk.Label(
            self._viz_inner,
            text="\nBelum ada data visualisasi.\n\nJalankan pipeline di tab 'Run Pipeline' terlebih dahulu,\nlalu klik '⟳ Refresh Grafik' di atas.",
            font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center",
            padx=40, pady=60,
        )
        self._viz_placeholder.pack(fill="x", padx=16, pady=16)
        self._viz_canvases: list = []

    def _refresh_viz(self):
        for widget in self._viz_inner.winfo_children():
            widget.destroy()
        self._viz_canvases = []

        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            self._viz_placeholder = tk.Label(
                self._viz_inner,
                text="\nBelum ada data visualisasi.\n\nJalankan pipeline di tab 'Run Pipeline' terlebih dahulu,\nlalu klik '⟳ Refresh Grafik' di atas.",
                font=F_BODY, fg="#6B7280", bg=C_CARD, justify="center",
                padx=40, pady=60,
            )
            self._viz_placeholder.pack(fill="x", padx=16, pady=16)
            return

        cols_per_row = 2
        for idx, (title, desc, fn) in enumerate(wa_charts.ALL_CHARTS):
            row = idx // cols_per_row
            col = idx % cols_per_row
            card = tk.Frame(self._viz_inner, bg=C_CARD, relief="solid", borderwidth=1,
                            highlightbackground=C_BORDER, highlightthickness=1)
            card.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(1, weight=1)
            title_frame = tk.Frame(card, bg="#f8fafc")
            title_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
            tk.Label(title_frame, text=f"📊 {title}", font=(FONT_NAME, 9, "bold"),
                     fg=C_HEADER, bg="#f8fafc").pack(side="left", padx=8, pady=6)
            tk.Label(title_frame, text=desc, font=F_HINT, fg="#6B7280", bg="#f8fafc").pack(side="left", padx=8)
            try:
                fig = fn(df)
                canvas_widget = wa_charts.embed_figure(card, fig)
                canvas_widget.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
                self._viz_canvases.append((title, fig, canvas_widget))
            except Exception as e:
                err = tk.Label(card, text=f"Error render:\n{e}",
                              font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left")
                err.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c_i in range(cols_per_row):
            self._viz_inner.columnconfigure(c_i, weight=1, minsize=420)

    def _export_all_charts(self):
        if not self._viz_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        folder = filedialog.askdirectory(title="Pilih folder untuk simpan PNG")
        if not folder:
            return
        saved = 0
        for title, fig, _ in self._viz_canvases:
            safe = title.replace(" ", "_").replace("/", "-").replace("×", "x")
            path = Path(folder) / f"{safe}.png"
            try:
                fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
                saved += 1
            except Exception as e:
                print(f"Failed save {title}: {e}", file=sys.stderr)
        messagebox.showinfo("Export", f"{saved} chart disimpan ke:\n{folder}")

    # --------------------------------------------------------
    # TAB 4: RINGKASAN
    # --------------------------------------------------------
    def _build_summary_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Ringkasan Run Terakhir", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_summary = tk.Label(c1, text="(belum ada run)", bg=C_CARD, fg="#475569", font=F_BODY, anchor="w", justify="left")
        self.lbl_summary.pack(fill="x", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)
        self.tree_summary = ttk.Treeview(c2, show="tree headings")
        self.tree_summary.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    def _update_summary_tab(self, summary: dict):
        msg = (
            f"Waktu Run     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total Baris   : {summary.get('total_rows', 0)}\n"
            f"Cabang Unik   : {summary.get('cabang_count', 0)}\n"
            f"Item Unik     : {summary.get('item_count', 0)}\n"
            f"Anomali       : {summary.get('prioritas_count', 0)} prioritas • "
            f"{summary.get('potensi_count', 0)} potensi • "
            f"{summary.get('review_count', 0)} review • "
            f"{summary.get('normal_count', 0)} normal\n"
            f"Output        : {summary.get('output_path', '-')}"
        )
        self.lbl_summary.configure(text=msg)
        df = self._preview_dfs.get("Per Cabang")
        self.tree_summary.delete(*self.tree_summary.get_children())
        if df is None or df.empty:
            return
        cols = list(df.columns)
        self.tree_summary["columns"] = cols
        for c in cols:
            self.tree_summary.heading(c, text=str(c))
            self.tree_summary.column(c, width=140, stretch=False)
        for row in df.itertuples(index=False, name=None):
            vals = []
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 4))
                else:
                    vals.append(v)
            self.tree_summary.insert("", "end", values=vals)

    # --------------------------------------------------------
    # TAB 5: RUN PIPELINE
    # --------------------------------------------------------
    def _build_run_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Input Workbook", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_workbook = tk.StringVar()
        ttk.Entry(frm, textvariable=self.var_workbook).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frm, text="Browse…", command=self._browse_workbook).pack(side="left", padx=4)
        ttk.Button(frm, text="Buka Folder Sample", command=self._open_data_folder).pack(side="left", padx=4)

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c2, text="Parameter", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm2 = ttk.Frame(c2)
        frm2.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frm2, text="Key Akhir (1-31):").pack(side="left", padx=(0, 8))
        self.var_key_akhir = tk.IntVar(value=self.config.get("default_key_akhir", 31))
        ttk.Spinbox(frm2, from_=1, to=31, textvariable=self.var_key_akhir, width=6).pack(side="left", padx=4)
        tk.Label(frm2, text="(hanya hari 1..N dianalisa)", font=F_HINT, foreground="#6B7280").pack(side="left", padx=8)
        tk.Label(frm2, text="Output:").pack(side="left", padx=(20, 8))
        self.var_output = tk.StringVar(value=str(DEFAULT_OUTPUT))
        ttk.Entry(frm2, textvariable=self.var_output, width=50).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frm2, text="Browse…", command=self._browse_output).pack(side="left")

        c3 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c3.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(3, weight=1)
        tk.Label(c3, text="Kontrol", font=F_CARD, fg=C_HEADER, bg=C_CARD).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        frm3 = ttk.Frame(c3)
        frm3.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        self.btn_run = ttk.Button(frm3, text="▶ Mulai Pipeline", style="Accent.TButton", command=self._start_pipeline)
        self.btn_run.pack(side="left", padx=4)
        self.btn_log = ttk.Button(frm3, text="Log Proses", command=self._show_log_popup)
        self.btn_log.pack(side="left", padx=4)
        self.btn_open_out = ttk.Button(frm3, text="Buka Output", command=self._open_output)
        self.btn_open_out.pack(side="left", padx=4)
        self.btn_open_out_dir = ttk.Button(frm3, text="Buka Folder Output", command=self._open_output_folder)
        self.btn_open_out_dir.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(c3, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        self.lbl_status = tk.Label(c3, text="Idle. Pilih workbook dan klik Mulai Pipeline.", bg=C_CARD, fg="#475569", font=F_BODY, anchor="w")
        self.lbl_status.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 12))

    # --------------------------------------------------------
    # TAB 6: KONFIGURASI
    # --------------------------------------------------------
    def _build_config_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Threshold & Konfigurasi", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text=f"Di-load dari: {CONFIG_PATH}", font=F_HINT, fg="#6B7280", bg=C_CARD).pack(anchor="w", padx=16)
        tk.Label(c1, text="Edit nilai threshold di bawah, lalu klik Simpan untuk apply ke config.json.", font=F_HINT, fg="#6B7280", bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        canvas = tk.Canvas(c2, bg=C_CARD, highlightthickness=0)
        sb = ttk.Scrollbar(c2, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=C_CARD)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._config_vars: dict[str, tk.Entry] = {}
        thresholds = self.config.get("thresholds", {})
        for i, (key, val) in enumerate(sorted(thresholds.items())):
            tk.Label(inner, text=key, bg=C_CARD, font=F_BODY, width=24, anchor="w").grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            var = tk.StringVar(value=str(val))
            ttk.Entry(inner, textvariable=var, width=12).grid(row=i, column=1, padx=4, pady=2, sticky="w")
            self._config_vars[key] = var

        btn_frame = tk.Frame(inner, bg=C_CARD)
        btn_frame.grid(row=len(thresholds) + 1, column=0, columnspan=2, padx=12, pady=12, sticky="w")
        ttk.Button(btn_frame, text="Simpan config.json", command=self._save_config).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Reset Default", command=self._reset_config).pack(side="left", padx=4)

    def _save_config(self):
        try:
            new_th = {}
            for k, var in self._config_vars.items():
                raw = var.get().strip()
                try:
                    new_th[k] = int(raw)
                except ValueError:
                    try:
                        new_th[k] = float(raw)
                    except ValueError:
                        messagebox.showerror("Config Error", f"Nilai untuk {k} tidak valid: {raw}")
                        return
            self.config["thresholds"] = new_th
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Config", f"Disimpan ke {CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Config Error", str(e))

    def _reset_config(self):
        default_cfg = {
            "thresholds": {
                "TH_SPIKE": 3, "TH_MAX_AVG_AKTIF": 2.5, "TH_MAX_MEDIAN": 3,
                "TH_MAX_SECOND": 3, "TH_MAX_SHARE_WARN": 0.50,
                "TH_MAX_SHARE_HIGH": 0.70, "TH_MAX_BOM_WARN": 0.25,
                "TH_MAX_BOM_HIGH": 0.50, "TH_TOTAL_BOM_WARN": 0.50,
                "TH_TOTAL_BOM_HIGH": 1.00, "TH_PEER_MIN": 3,
                "TH_PEER_WARN": 2, "TH_PEER_HIGH": 3, "TH_LAST_SHARE": 0.70,
            }
        }
        for k, var in self._config_vars.items():
            if k in default_cfg["thresholds"]:
                var.set(str(default_cfg["thresholds"][k]))

    # --------------------------------------------------------
    # TAB 7: BANTUAN
    # --------------------------------------------------------
    def _build_help_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c1.columnconfigure(0, weight=1)
        c1.rowconfigure(0, weight=1)

        txt = tk.Text(c1, wrap="word", relief="flat", bg=C_CARD, fg="#1F2937", font=F_BODY, padx=20, pady=16)
        sb = ttk.Scrollbar(c1, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        help_text = f"""{APP_TITLE} v{APP_VERSION}

=== CARA PAKAI ===

1. Siapkan workbook Excel berisi 3 sheet/named-range:
   • REKAP_MENTAH   — data waste harian (kolom 1..31 + NAMA RESTO + NAMA BARANG + JENIS + KETERANGAN + SATUAN + dll)
   • BOM            — master Bill of Materials (Nomor #, Nama Barang, TOTAL BOM)
   • DATABASE_SATUAN — master helper value per kategori (NAMA ITEM + 11 kolom kategori)

2. Tab "Run Pipeline":
   • Browse... → pilih workbook Excel
   • Isi Key Akhir (1..31) — cutoff hari terakhir periode analisa
   • (Optional) ganti path output Excel
   • Klik "Mulai Pipeline"

3. Setelah selesai, tab "Dashboard" otomatis ter-isi:
   • KPI cards di atas (total, prioritas, potensi, waste, cabang)
   • 3 chart interaktif (klik bar untuk filter)
   • Drill-down table dengan sortable columns + status coloring

=== DRILL-DOWN (NEW v2.0) ===

Cara drill-down:
  1. Klik bar/slice di chart interaktif → auto-filter table + re-render chart lain
  2. Pilih dropdown Cabang/Status → filter langsung
  3. Ketik di Search box → filter free-text semua kolom
  4. Active filter chips muncul di atas table (klik × untuk remove)
  5. Double-click baris di table → drill-down ke cabang+item baris itu
  6. Klik header kolom table → sort asc/desc

Contoh workflow analisa:
  - Klik bar "Prioritas Tinggi" → lihat semua baris prioritas
  - Klik bar cabang "RESTO.PWKTAM" → fokus ke cabang itu
  - Klik bar top item "Bawang Putih" → lihat detail per-hari item itu
  - Search "Cancel Nota" → filter semua baris dengan keterangan itu

=== OUTPUT EXCEL — 6 SHEET ===

• Detail             — semua baris (kolom mengikuti M code Final order)
• Anomali Prioritas  — hanya Prioritas Tinggi + Potensi Anomali
• Per Cabang         — ringkasan per NAMA RESTO
• Top Items          — top 20 item by TOTAL waste
• Pareto Alasan      — group by KETERANGAN + cumulative %
• Log Run            — timestamp + parameter + log lines

=== 12 SINYAL ANOMALI ===

S1  Spike vs AVG                 : MAX/AVG >= 3
S2  MAX vs AVG Aktif             : MAX/AVG_AKTIF >= 2.5 (>= 4 → skor 2)
S3  MAX vs Median Aktif          : MAX/MEDIAN >= 3 (skor 2)
S4  MAX Share                    : MAX/TOTAL >= 0.50 (1) / 0.70 (2)
S5  MAX vs Second Max            : MAX/SECOND_MAX >= 3
S6  MAX / BOM                    : MAX/TOTAL_BOM >= 0.25 (1) / 0.50 (2)
S7  TOTAL / BOM                  : TOTAL/TOTAL_BOM >= 0.50 (1) / 1.00 (2)
S8  Peer MAX                     : MAX/PeerMedMax >= 2 (1) / 3 (2)
S9  Peer TOTAL                   : TOTAL/PeerMedTot >= 3
S10 Single-day event             : Count=1 & (MaxBOM >= 0.10 atau MaxPeer >= 2)
S11 Last Day Share               : LastDay/TOTAL >= 0.70
S12 Scale Signal                 : heuristic rasio (8-12/80-120/800-1200/8000-12000)

Composite Score (max 19):
• >= 8  : Prioritas Tinggi
• >= 5  : Potensi Anomali
• >= 3  : Perlu Review
• else  : Normal

=== TROUBLESHOOTING ===

• "Tidak menemukan sheet untuk 'rekap_mentah'"
  → Pastikan workbook punya sheet REKAP_MENTAH / Rekap Mentah / REKAP.
     Atau edit waste_anomaly/config.json → input_sheets untuk tambah nama kandidat.

• "BOM sheet tidak ditemukan"
  → BOM join dilewati; TOTAL BOM jadi None dan sinyal BOM (S6/S7) tidak trigger.
     Tambahkan sheet BOM / MASTER BOM untuk mengaktifkan.

• Tab Dashboard kosong
  → Pastikan sudah run pipeline di tab "Run Pipeline" dulu.

=== KONTAK ===

Source: https://github.com/anandategarch/Waste
Pattern referensi: https://github.com/anandategarch/Inventory-Adjusment
"""
        txt.insert("1.0", help_text)
        txt.configure(state="disabled")

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------
    def _build_footer(self):
        ftr = tk.Frame(self, bg=C_FOOTER, height=26)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)
        self.lbl_footer = tk.Label(
            ftr, text=f"Ready  •  v{APP_VERSION}  •  {datetime.now().strftime('%Y-%m-%d')}",
            bg=C_FOOTER, fg="#475569", font=F_HINT,
        )
        self.lbl_footer.pack(side="left", padx=12, pady=4)

    # --------------------------------------------------------
    # ACTIONS — Run Pipeline
    # --------------------------------------------------------
    def _browse_workbook(self):
        path = filedialog.askopenfilename(
            title="Pilih Workbook Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if path:
            self.var_workbook.set(path)
            if not self.var_output.get():
                self.var_output.set(str(DEFAULT_OUTPUT))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Pilih Output Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if path:
            self.var_output.set(path)

    def _open_data_folder(self):
        data_dir = APP_DIR / "data"
        data_dir.mkdir(exist_ok=True)
        self._open_path_in_explorer(data_dir)

    def _open_output_folder(self):
        out_dir = Path(self.var_output.get()).parent if self.var_output.get() else APP_DIR / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._open_path_in_explorer(out_dir)

    def _open_output(self):
        if not self.last_output_path:
            messagebox.showinfo("Output", "Belum ada output. Jalankan pipeline dulu.")
            return
        self._open_path_in_explorer(Path(self.last_output_path))

    @staticmethod
    def _open_path_in_explorer(path: Path):
        path = Path(path)
        try:
            if sys.platform.startswith("win"):
                if path.is_dir():
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    os.startfile(str(path.parent))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}" 2>/dev/null &')
        except Exception:
            pass

    def _show_log_popup(self):
        if self.log_popup is None:
            self.log_popup = SimpleLogPopup(self)
        self.log_popup.deiconify()
        self.log_popup.lift()
        self.log_popup.focus_force()

    def _start_pipeline(self):
        wb_path = self.var_workbook.get().strip()
        if not wb_path or not Path(wb_path).exists():
            messagebox.showerror("Input Error", "Workbook belum dipilih atau tidak ditemukan.")
            return
        try:
            ka = int(self.var_key_akhir.get())
            if not (1 <= ka <= 31):
                raise ValueError("Key Akhir harus antara 1 dan 31.")
        except Exception:
            messagebox.showerror("Input Error", "Key Akhir harus angka antara 1 dan 31.")
            return
        out_path = self.var_output.get().strip()
        if not out_path:
            messagebox.showerror("Input Error", "Output path belum diisi.")
            return

        self.btn_run.configure(state="disabled")
        self.progress["value"] = 0
        self._set_status("Starting...", "running")

        self._show_log_popup()
        if self.log_popup:
            self.log_popup.clear()
            self.log_popup.append("=== Mulai Pipeline ===")

        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(wb_path, ka, out_path),
            daemon=True,
        )
        self.worker_thread.start()

    def _worker_run(self, wb_path: str, key_akhir: int, out_path: str):
        try:
            summary = run_pipeline(
                workbook_path=wb_path,
                key_akhir=key_akhir,
                output_path=out_path,
                progress_callback=lambda msg, pct: self.ui_queue.put(("log", msg, pct)),
            )
            self.ui_queue.put(("done", summary, None))
        except Exception as e:
            self.ui_queue.put(("error", str(e), None))

    def _drain_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                tag = item[0]
                if tag == "log":
                    _, msg, pct = item
                    if self.log_popup:
                        self.log_popup.append(msg)
                    if pct is not None:
                        self.progress["value"] = float(pct)
                    self._set_status(msg, "running")
                elif tag == "done":
                    _, summary, _ = item
                    self._on_pipeline_done(summary)
                elif tag == "error":
                    _, err, _ = item
                    self._on_pipeline_error(err)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _on_pipeline_done(self, summary: dict):
        self.btn_run.configure(state="normal")
        if not summary.get("success"):
            self._on_pipeline_error(summary.get("error", "Unknown error"))
            return
        self.progress["value"] = 100
        self.last_output_path = summary.get("output_path")
        self.last_summary = summary
        self._set_status(
            f"Done. {summary.get('total_rows', 0)} baris, "
            f"{summary.get('anomali_count', 0)} anomali prioritas, "
            f"output: {self.last_output_path}", "done"
        )
        if self.log_popup:
            self.log_popup.append(f"=== DONE ===")
            self.log_popup.append(f"Total baris: {summary.get('total_rows', 0)}")
            self.log_popup.append(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
            self.log_popup.append(f"Output: {self.last_output_path}")
        # Load preview + update dashboard
        self._load_preview_data(self.last_output_path)
        self._update_summary_tab(summary)
        # Update dashboard (KPI + charts + table)
        df = self._preview_dfs.get("Detail")
        if df is not None and not df.empty:
            self._update_kpi_cards(df, summary)
            # Reset filters
            self._clear_all_filters()
        try:
            self._refresh_viz()
        except Exception as e:
            print(f"[viz auto-refresh] {e}", file=sys.stderr)
        messagebox.showinfo(
            "Pipeline Selesai",
            f"Pipeline selesai!\n\n"
            f"Total baris diproses: {summary.get('total_rows', 0)}\n"
            f"Anomali prioritas: {summary.get('prioritas_count', 0)}\n"
            f"Potensi anomali: {summary.get('potensi_count', 0)}\n"
            f"Perlu review: {summary.get('review_count', 0)}\n\n"
            f"Output: {self.last_output_path}\n\n"
            f"Buka tab 'Dashboard' untuk analisa drill-down.",
        )

    def _on_pipeline_error(self, err: str):
        self.btn_run.configure(state="normal")
        self._set_status(f"ERROR: {err}", "error")
        if self.log_popup:
            self.log_popup.append(f"!!! ERROR: {err}")
        messagebox.showerror("Pipeline Error", err)

    def _set_status(self, msg: str, kind: str = "running"):
        colors = {"running": "#0369a1", "done": "#16a34a", "error": "#dc2626"}
        self.lbl_status.configure(fg=colors.get(kind, "#475569"))
        self.lbl_status.configure(text=msg)
        self.lbl_footer.configure(text=f"{msg[:80]}  •  v{APP_VERSION}")

    # --------------------------------------------------------
    # LOAD PREVIEW DATA
    # --------------------------------------------------------
    def _load_preview_data(self, xlsx_path: str):
        try:
            import pandas as pd
            sheets = ["Detail", "Anomali Prioritas", "Per Cabang", "Top Items", "Pareto Alasan"]
            self._preview_dfs = {}
            xls = pd.ExcelFile(xlsx_path)
            for s in sheets:
                if s in xls.sheet_names:
                    self._preview_dfs[s] = pd.read_excel(xls, sheet_name=s)
            self._refresh_preview()
        except Exception as e:
            messagebox.showwarning("Preview", f"Gagal load preview: {e}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    app = WasteAnomalyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
