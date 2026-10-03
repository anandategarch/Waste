"""
ui_app.py — Tkinter professional dashboard untuk Waste Anomaly Detection.

Versi: 2.3.1  (PROFESSIONAL REBUILD + polish FIX-UI-2)

Fitur:
  - Layout dashboard-style (KPI cards + filter bar + drill-down table + interactive charts)
  - KPI cards: total baris, prioritas, potensi, perlu review, total waste, cabang count
  - Filter bar: search + dropdown cabang/status + JENIS multi-select + rentang hari
    (opt-in via checkbox) + profil save/load + active filter chips (klik = remove)
  - Interactive charts: klik bar/slice → auto-filter table + re-render charts lain (drill-down)
  - Detail table dengan sortable columns (per-kolom, numerik-aware, indikator ▼/▲,
    NaN selalu terakhir) + pagination 500 baris + status coloring
  - Export: CSV (tabel terfilter), PNG (semua chart), laporan Excel 6-sheet on-demand
  - Pipeline IN-MEMORY + tombol pembatalan run + export Excel di background thread

Tabs (urutan aktual di notebook):
  1.  📊 Dashboard     — KPI + filter + interactive charts + drill-down table
  2.  ⚖ Compare Cabang — perbandingan 2 cabang (4 chart + metrics summary)
  3.  🎯 Quadrant      — scatter sistemik vs insiden + fingerprint distribution
  4.  🏆 Rate League   — ranking waste rate per bahan
  5.  📋 Hasil         — preview tabel hasil (Detail/Anomali/Cabang/Top/Pareto)
  6.  📈 Visualisasi   — 12 grafik matplotlib (full charts gallery)
  7.  🗂 Ringkasan     — summary run terakhir + tabel Per Cabang
  8.  ▶ Run Pipeline  — pilih workbook + Key Akhir + Run/Batalkan + log
  9.  ⚙ Konfigurasi   — threshold editor
  10. ❓ Bantuan       — instruksi pakai + 12 sinyal + shortcut + troubleshooting
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont  # M17: probe keluarga font saat startup
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Set matplotlib backend ke TkAgg SEBELUM import charts (untuk embedded rendering)
import matplotlib
matplotlib.use("TkAgg")

# Pastikan module lokal ke-import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # untuk pd.isna() di table render + ExcelFile di preview

from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.utils import load_config, CONFIG_PATH
from waste_anomaly import charts as wa_charts
from waste_anomaly.charts import dispose_figure  # H3: teardown figure anti-leak
from waste_anomaly import dashboard as wa_dash
from waste_anomaly import filters as wa_filters
from waste_anomaly.exporter import export_to_excel  # H6: export Excel on-demand dari tab Hasil

APP_VERSION = "2.3.1"  # L2: selaras dengan config.json + docstring
APP_TITLE = "Waste Anomaly Detection — Pro Dashboard"
APP_DIR = Path(__file__).resolve().parent
# (H6) DEFAULT_OUTPUT dihapus — pipeline IN-MEMORY; file Excel dibuat on-demand
# lewat tombol "Export Laporan Excel" di tab Hasil.

# ============================================================
# FONT FALLBACK (M17)
# ============================================================

def _pick_font(candidates: list[str], default: str) -> str:
    """M17: kandidat font pertama yang tersedia di sistem; fallback default.

    Dipanggil sekali saat startup (root Tk sudah ada) — keluarga font di-probe
    via tkfont.families(). Font hardcoded (Segoe UI/Consolas) tidak ada di
    Linux/macOS → Tk fallback ke font sistem yang jelek; di sini kita pilih
    eksplisit: Segoe UI → Tahoma → DejaVu Sans → Helvetica.
    """
    try:
        families = set(tkfont.families())
        for name in candidates:
            if name in families:
                return name
    except Exception:
        pass  # probe gagal (headless) — pakai default
    return default


# ============================================================
# STYLE
# ============================================================
# M17: nilai default — diganti saat startup oleh _init_fonts() memakai
# _pick_font() (probe keluarga font sistem sekali).
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
C_TITLE_BG = "#f8fafc"      # slate-50 — bg title-bar kartu chart (C_HOVER lama dihapus: tak terpakai)

# M18: grays ter-unify — JANGAN pakai literal #6B7280/#64748b/#1F2937/#475569
# lagi; cukup dua konstanta ini untuk semua teks sekunder/utama.
C_TEXT_MUTED = "#64748b"    # slate-500 — hint, label sekunder, status netral
C_TEXT_MAIN = "#1f2937"     # gray-800 — teks utama

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
        # C2: tombol X hanya menyembunyikan popup (semantics sama dengan tombol
        # "Tutup") — reference di app tetap valid, tidak jadi stale lalu TclError.
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        try:
            self.transient(parent)  # M20: ikuti parent — tanpa focus_force()
        except Exception:
            pass
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
        if not self.winfo_exists():  # C2: popup mungkin sudah di-destroy
            return
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        if not self.winfo_exists():  # C2
            return
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
                       fg=C_TEXT_MUTED, bg=bg, anchor="w")
        lbl.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        # Value — L13: wraplength supaya angka panjang wrap ke 2 baris, bukan
        # kepotong (KPI card sempit di layar kecil).
        self.val_lbl = tk.Label(self, textvariable=self._value_var, font=F_KPI_NUM,
                                fg=color, bg=bg, anchor="w", wraplength=120)
        self.val_lbl.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

    def set_value(self, value: str):
        self._value_var.set(value)

    # L3: set_color() dihapus — tidak pernah dipanggil (grep-verified).


# ============================================================
# FILTER CHIP WIDGET (clickable untuk remove)
# ============================================================

class FilterChip(tk.Frame):
    """Chip filter aktif — M7: SELURUH chip clickable (klik di mana pun =
    remove, sama dengan klik ×), cursor hand2 + bg berubah saat hover.
    Glyph × tetap ada sebagai affordance visual."""

    _BG = "#fef3c7"        # amber-100
    _BG_HOVER = "#fde68a"  # amber-200
    _BORDER = "#fcd34d"    # amber-300
    _FG = "#92400e"        # amber-800

    def __init__(self, parent, label: str, on_remove):
        super().__init__(parent, bg=self._BG, relief="flat", cursor="hand2",
                         highlightbackground=self._BORDER, highlightthickness=1)
        self._on_remove_cb = on_remove
        self._lbl = tk.Label(self, text=label, font=F_HINT, fg=self._FG,
                             bg=self._BG, cursor="hand2")
        self._lbl.pack(side="left", padx=(6, 2), pady=2)
        self._x = tk.Label(self, text="×", font=(FONT_NAME, 10, "bold"),
                           fg=self._FG, bg=self._BG, cursor="hand2")
        self._x.pack(side="left", padx=(0, 6))
        # M7: hit area = seluruh chip (frame + kedua label), bukan cuma ×
        for w in (self, self._lbl, self._x):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, _event):
        try:
            self._on_remove_cb()
        except tk.TclError:
            pass  # chip sudah di-destroy oleh handler remove-nya
        return "break"

    def _on_leave(self, _event):
        # Pointer mungkin hanya pindah frame → label anak (memicu Leave frame
        # + Enter label) — matikan hover hanya bila pointer benar-benar keluar.
        try:
            x, y = self.winfo_pointerxy()
            node = self.winfo_containing(x, y)
            while node is not None:
                if node is self:
                    return  # masih di dalam chip
                node = getattr(node, "master", None)
        except tk.TclError:
            pass
        self._set_hover(False)

    def _set_hover(self, hovered: bool):
        bg = self._BG_HOVER if hovered else self._BG
        for w in (self, self._lbl, self._x):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass  # widget mungkin sudah di-destroy


# ============================================================
# PURE FILTER HELPER (M23 — satu implementasi, dipakai Dashboard & CSV export)
# ============================================================

def _apply_filters(df: pd.DataFrame, filters: dict | None,
                   day_min: int | None = None, day_max: int | None = None,
                   search: str = "") -> pd.DataFrame:
    """M23: filter df murni (tanpa side-effect, tanpa render).

    filters: dict key → nilai; None / list kosong di-skip.
      cabang→NAMA RESTO, item→NAMA BARANG, jenis→JENIS (list → isin),
      keterangan→KETERANGAN, status→ANOMALY STATUS.
    day_min/day_max: rentang HARI MAX (inklusif; baris HARI MAX null tetap
    lolos — konsisten perilaku lama).
    search: substring case-insensitive di SEMUA kolom (mask OR, vectorized).
    """
    filtered = df.copy()
    col_map = {
        "cabang": "NAMA RESTO", "item": "NAMA BARANG", "jenis": "JENIS",
        "keterangan": "KETERANGAN", "status": "ANOMALY STATUS",
    }
    for key, val in (filters or {}).items():
        if val is None or (isinstance(val, list) and not val):
            continue
        col = col_map.get(key)
        if not col or col not in filtered.columns:
            continue
        if isinstance(val, list):
            filtered = filtered[filtered[col].isin(val)]
        else:
            filtered = filtered[filtered[col] == val]

    # Rentang hari (HARI MAX in [day_min, day_max])
    if (day_min is not None and day_max is not None
            and "HARI MAX" in filtered.columns):
        hari_max = pd.to_numeric(filtered["HARI MAX"], errors="coerce")
        filtered = filtered[
            hari_max.between(day_min, day_max, inclusive="both")
            | hari_max.isna()  # baris HARI MAX null tetap lolos
        ]

    # Search — vectorized per-column OR mask (H1)
    search = (search or "").strip().lower()
    if search:
        mask = pd.Series(False, index=filtered.index)
        for col in filtered.columns:
            mask |= filtered[col].astype(str).str.lower().str.contains(
                search, regex=False, na=False
            )
        filtered = filtered[mask]
    return filtered


# M6: key filter mentah → label Indonesia untuk chip (dulu chip menampilkan
# "cabang: X" / "search: ..." mentah).
CHIP_LABELS = {
    "cabang": "Cabang", "status": "Status", "item": "Item", "search": "Cari",
    "jenis": "Jenis", "keterangan": "Keterangan", "hari": "Rentang Hari",
    "top": "Top",
}


# ============================================================
# MAIN APP
# ============================================================

class WasteAnomalyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self._init_fonts()  # M17: probe font sistem SEBELUM widget dibangun
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        # M15: ukuran awal di-clamp ke layar + jendela diposisikan di tengah
        # (fix laptop 1366×768 — dulu hardcoded 1500×900 melebihi layar kecil).
        _sw, _sh = self.winfo_screenwidth(), self.winfo_screenheight()
        _w = min(1500, max(1024, _sw - 100))
        _h = min(900, max(700, _sh - 80))
        self.geometry(
            f"{_w}x{_h}+{max(0, (_sw - _w) // 2)}+{max(0, (_sh - _h) // 2)}"
        )
        self.minsize(min(1024, _w), min(700, _h))
        self.resizable(True, True)  # biar user bisa resize sesuai monitor
        self.configure(bg=C_BG)
        # M1: tombol X jangan menutup paksa saat pipeline/export berjalan —
        # konfirmasi dulu (lihat _on_close).
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # State
        self.config = load_config()
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.log_popup: SimpleLogPopup | None = None
        self.last_summary: dict | None = None
        self._preview_dfs: dict[str, "pd.DataFrame"] = {}

        # H6: pipeline IN-MEMORY — df hasil run terakhir disimpan untuk export Excel
        self._pipeline_df: pd.DataFrame | None = None
        self._last_key_akhir: int = 31
        self._last_run_time: datetime | None = None

        # C1: flag pipeline/export berjalan + buffer log (popup-independent)
        self._pipeline_running = False
        self._export_running = False
        self._log_lines: list[str] = []

        # M21: pembatalan run. pipeline.py TIDAK menyediakan hook cancel
        # per-stage (grep 'cancel' kosong) — flag ini dicek worker SETELAH
        # pipeline kembali (lihat _worker_run): hasil dibuang, tidak dirender.
        self._pipeline_cancel = threading.Event()

        # H5: suppress var-trace saat restore programmatic (profil/clear)
        self._suppress_trace = False
        # H1: after-id debounce pencarian
        self._search_after_id: str | None = None

        # H2: lazy per-tab render — tab key → dirty?
        self._tab_render_dirty: dict[str, bool] = {}
        self._tab_key_by_widget: dict[str, str] = {}

        # M5: sort state per-tree — {str(tree): {kolom: "asc"|"desc"}}
        # (dict per kolom; klik kolom lain memulai state baru — lihat
        # _tree_sort_handler).
        self._tree_sort_states: dict[str, dict[str, str]] = {}

        # Drill-down state: dict filter_key -> value (None artinya no filter)
        # jenis: list[str] (multi-select), day_min/day_max: int 1-31
        self.active_filters: dict[str, str | list[str] | None] = {
            "cabang": None, "item": None, "jenis": [],
            "keterangan": None, "status": None,
        }
        self.day_min: int | None = None  # filter HARI MAX dalam range
        self.day_max: int | None = None

        # Filter profile state
        # L3: mirror self._filter_profiles DIHAPUS — sumber kebenaran adalah
        # modul waste_anomaly.filters (list_profile_names/get_profile).

        self._build_styles()
        self._build_header()
        self._build_tabs()
        self._build_footer()

        # C3: SATU dispatcher wheel app-level (menggantikan 5 bind_all yang saling
        # menimpa). Dipasang setelah build supaya tidak menangkap event saat build.
        self.bind_all("<MouseWheel>", self._on_global_wheel)
        self.bind_all("<Button-4>", self._on_global_wheel)   # Linux
        self.bind_all("<Button-5>", self._on_global_wheel)
        # L11: shortcut keyboard — Ctrl+F fokus kotak Cari (pindah ke Dashboard),
        # Ctrl+R refresh semua (guard saat pipeline/export berjalan).
        # Bind level 'all' berjalan SETELAH class binding widget — aman.
        self.bind_all("<Control-f>", self._on_accel_focus_search)
        self.bind_all("<Control-F>", self._on_accel_focus_search)
        self.bind_all("<Control-r>", self._on_accel_refresh)
        self.bind_all("<Control-R>", self._on_accel_refresh)

        self.after(100, self._drain_queue)

    # --------------------------------------------------------
    # M17: FONT INIT (probe sekali di startup)
    # --------------------------------------------------------
    def _init_fonts(self):
        """M17: pilih font pertama yang tersedia (Windows: Segoe UI/Consolas;
        Linux: DejaVu; dsb.) lalu rebuild tuple font global."""
        global FONT_NAME, MONO_NAME
        global F_APP_TITLE, F_CARD, F_BODY, F_HINT, F_LOG, F_KPI_NUM, F_KPI_LABEL
        FONT_NAME = _pick_font(
            ["Segoe UI", "Tahoma", "DejaVu Sans", "Helvetica"], "Segoe UI"
        )
        MONO_NAME = _pick_font(
            ["Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New"],
            "Consolas",
        )
        F_APP_TITLE = (FONT_NAME, 14, "bold")
        F_CARD = (FONT_NAME, 10, "bold")
        F_BODY = (FONT_NAME, 9)
        F_HINT = (FONT_NAME, 8)
        F_LOG = (MONO_NAME, 9)
        F_KPI_NUM = (FONT_NAME, 18, "bold")
        F_KPI_LABEL = (FONT_NAME, 8)

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
        style.configure("TLabel", background=C_BG, font=F_BODY, foreground=C_TEXT_MAIN)
        style.configure("Card.TLabel", background=C_CARD, font=F_BODY, foreground=C_TEXT_MAIN)
        style.configure("CardTitle.TLabel", background=C_CARD, font=F_CARD, foreground=C_HEADER)
        style.configure("Hint.TLabel", background=C_BG, font=F_HINT, foreground=C_TEXT_MUTED)
        style.configure("TButton", font=F_BODY, padding=4)
        # M19: tombol aksen (Refresh header + Run) kini bergaya ttk konsisten tema
        # (dulu: tk.Button raw dengan bg manual — satu-satunya di app).
        style.configure("Accent.TButton", font=(FONT_NAME, 9, "bold"), padding=6,
                        background="#0f766e", foreground="#ffffff")
        style.map("Accent.TButton",
                  background=[("disabled", "#94a3b8"), ("active", "#115e59")],
                  foreground=[("disabled", "#cbd5e1")])
        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 6), font=F_BODY)
        style.map("TNotebook.Tab",
                  background=[("selected", C_CARD)],
                  foreground=[("selected", C_HEADER)])
        style.configure("TEntry", fieldbackground=C_CARD, padding=3)
        style.configure("TCombobox", padding=3)
        # Treeview — M16: rowheight dari metrik font aktual (bukan hardcoded 22,
        # supaya baris tidak kepotong di font sistem yang lebih tinggi).
        try:
            _row_h = tkfont.Font(root=self, font=F_BODY).metrics("linespace") + 6
        except Exception:
            _row_h = 22
        style.configure("Treeview", font=F_BODY, rowheight=_row_h,
                        background=C_CARD, fieldbackground=C_CARD)
        style.configure("Treeview.Heading", font=(FONT_NAME, 9, "bold"),
                        background="#f1f5f9", foreground=C_HEADER)
        style.map("Treeview", background=[("selected", "#dbeafe")],
                  foreground=[("selected", C_HEADER)])

    # --------------------------------------------------------
    # SCROLLABLE CONTAINER HELPER (v2.3.0)
    # --------------------------------------------------------
    @staticmethod
    def _make_scrollable(parent, bg=C_BG):
        """Bungkus parent dengan scrollable Canvas (vertical + horizontal).
        Return: inner_frame (tempat user menaruh widget).
        Canvas otomatis resize dengan parent, scroll-by-wheel + scrollbar.
        """
        # Container untuk Canvas + scrollbars
        container = tk.Frame(parent, bg=bg)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(container, bg=bg, highlightthickness=0, relief="flat")
        sb_y = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        sb_x = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        inner = tk.Frame(canvas, bg=bg)
        canvas_window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Auto-scroll-region on inner resize
        def _on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_configure)

        # Auto-resize inner width to match canvas (so charts stretch horizontally)
        def _on_canvas_configure(event):
            w = event.width
            canvas.itemconfig(canvas_window_id, width=w)
        canvas.bind("<Configure>", _on_canvas_configure)

        # C3: tandai canvas untuk global wheel dispatcher (bind_all tunggal di
        # __init__ — lihat _on_global_wheel). Tidak ada bind_all lokal lagi —
        # dulunya 5 situs bind_all saling menimpa & Treeview double-scroll.
        canvas._waste_scroll = True  # type: ignore[attr-defined]

        return inner

    def _on_global_wheel(self, e):
        """C3: dispatcher wheel TUNGGAL untuk semua scrollable canvas.

        Naik dari event.widget ke tk.Canvas terdekat yang punya
        ``_waste_scroll = True``. Widget dengan scroll sendiri
        (Treeview/Text/Combobox/Spinbox/Entry) di-skip supaya class binding
        mereka jalan dan tidak terjadi double-scroll.
        """
        w = getattr(e, "widget", None)
        # Widget dengan wheel-scroll sendiri — biarkan class binding bekerja
        if isinstance(w, (ttk.Treeview, tk.Text, ttk.Combobox, tk.Spinbox, tk.Entry)):
            return
        # macOS delta kecil (±1..5), Windows ±120 (H9)
        if getattr(e, "delta", 0):
            step = -int(e.delta / 120) if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)
        else:
            step = -1 if getattr(e, "num", 0) == 4 else 1
        while w is not None:
            if isinstance(w, tk.Canvas) and getattr(w, "_waste_scroll", False):
                w.yview_scroll(step, "units")
                return "break"
            w = getattr(w, "master", None)

    # --------------------------------------------------------
    # SAFE PARSE & LOG HELPERS (H4 / C1 / C2)
    # --------------------------------------------------------
    def _safe_int(self, var, default: int) -> int:
        """H4: parse var (StringVar) dengan aman — TclError/ValueError → default."""
        try:
            return int(str(var.get()).strip())
        except (tk.TclError, ValueError, TypeError):
            return default

    def _digits_only(self, value_if_allowed: str) -> bool:
        """H4: validatecommand spinbox/entry — hanya digit (atau kosong)."""
        return value_if_allowed == "" or str(value_if_allowed).isdigit()

    def log(self, msg: str):
        """C2: log popup-independent — buffer internal + append ke popup bila hidup.

        Buffer dipakai ulang untuk sheet "Log Run" saat export Excel (H6).
        """
        self._log_lines.append(str(msg))
        if len(self._log_lines) > 500:
            del self._log_lines[: len(self._log_lines) - 500]
        if self.log_popup is not None:
            try:
                if self.log_popup.winfo_exists():
                    self.log_popup.append(str(msg))
            except tk.TclError:
                self.log_popup = None

    # --------------------------------------------------------
    # H3: CHART DISPOSE HELPER
    # --------------------------------------------------------
    def _dispose_chart_registry(self, entries):
        """H3: teardown (key, fig, canvas) tuple tanpa leak Figure.

        Entry 3-elemen (key, fig, canvas) atau 2-elemen (key, fig).
        Disconnect matplotlib cids (fig._waste_cids) → destroy widget Tk →
        dispose_figure(fig). Semua best-effort — error teardown tidak boleh
        menggagalkan render berikutnya.
        """
        for entry in entries or []:
            fig, canvas = None, None
            if isinstance(entry, (tuple, list)) and len(entry) >= 3:
                _, fig, canvas = entry[0], entry[1], entry[2]
            elif isinstance(entry, (tuple, list)) and len(entry) == 2:
                _, fig = entry
            try:
                if fig is not None:
                    for cid in getattr(fig, "_waste_cids", []):
                        try:
                            fig.canvas.mpl_disconnect(cid)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                if canvas is not None and canvas.get_tk_widget().winfo_exists():
                    canvas.get_tk_widget().destroy()
            except Exception:
                pass
            dispose_figure(fig)

    # --------------------------------------------------------
    # HEADER (with global refresh button)
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

        # Global Refresh button — selalu visible di header kanan
        btn_frame = tk.Frame(hdr, bg=C_HEADER)
        btn_frame.pack(side="right", padx=12, pady=8)
        # M19: ttk.Button bergaya Accent.TButton — konsisten dengan tema app
        # (dulu satu-satunya tk.Button raw dengan warna manual).
        self.btn_global_refresh = ttk.Button(
            btn_frame, text="⟳ Refresh Semua", style="Accent.TButton",
            cursor="hand2", command=self._global_refresh,
        )
        self.btn_global_refresh.pack(side="right")
        # Tooltip-like label
        tk.Label(btn_frame, text="Render ulang Dashboard + Chart:",
                 font=F_HINT, fg="#94a3b8", bg=C_HEADER).pack(side="right", padx=4)

    def _global_refresh(self):
        """Refresh semua tab (H2: lazy) — mark dirty semua tab, render tab AKTIF
        + Ringkasan (murah), error per-tab dikumpulkan ke status (fix M2)."""
        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            messagebox.showinfo("Refresh", "Belum ada data. Run pipeline dulu di tab 'Run Pipeline'.")
            return
        self._mark_all_tabs_dirty()
        errors: list[tuple[str, str]] = []

        # Render tab yang sedang dipilih saja (lazy — tab lain saat dikunjungi)
        cur = self._current_tab_key()
        if cur:
            err = self._render_tab(cur)
            self._tab_render_dirty[cur] = False
            if err:
                errors.append((cur, err))

        # Ringkasan + KPI murah (tekstual) — render langsung
        try:
            if self.last_summary:
                self._update_summary_tab(self.last_summary)
            self._tab_render_dirty["ringkasan"] = False
        except Exception as e:
            errors.append(("ringkasan", str(e)))
        try:
            self._update_kpi_cards(df, self.last_summary or {})
        except Exception as e:
            errors.append(("kpi", str(e)))

        if errors:
            self._set_status(
                f"⚠ {len(errors)} tab gagal refresh: " + ", ".join(k for k, _ in errors), "error"
            )
            for k, e in errors:
                print(f"[refresh {k}] {e}", file=sys.stderr)
                self.log(f"⚠ Refresh tab '{k}' gagal: {e}")
        else:
            self._set_status(f"✓ Refresh semua chart • {len(df)} baris dimuat", "done")

    # --------------------------------------------------------
    # H2: LAZY PER-TAB RENDER
    # --------------------------------------------------------
    def _current_tab_key(self) -> str:
        """Key tab yang sedang dipilih ('' bila tidak dikenal)."""
        try:
            sel = self.notebook.select()
            return self._tab_key_by_widget.get(str(sel), "")
        except Exception:
            return ""

    def _mark_all_tabs_dirty(self):
        """Tandai semua tab data-dependent perlu render saat dikunjungi."""
        for key in ("dashboard", "compare", "quadrant", "rate_league",
                    "hasil", "visualisasi", "ringkasan"):
            self._tab_render_dirty[key] = True

    def _on_notebook_tab_changed(self, event=None):
        """H2: render tab saat pertama kali dikunjungi bila dirty."""
        key = self._current_tab_key()
        if not key or not self._tab_render_dirty.get(key):
            return
        err = self._render_tab(key)
        self._tab_render_dirty[key] = False
        if err:
            self._set_status(f"⚠ Render tab '{key}' gagal: {err}", "error")
            self.log(f"⚠ Render tab '{key}' gagal: {err}")

    def _render_tab(self, key: str) -> str | None:
        """Render satu tab. Return pesan error (str) atau None bila sukses."""
        try:
            if key == "dashboard":
                self._apply_dashboard_filter()
            elif key == "compare":
                self._render_compare_charts()
            elif key == "quadrant":
                self._render_quadrant_charts()
            elif key == "rate_league":
                self._render_rate_league()
            elif key == "hasil":
                self._refresh_preview()
            elif key == "visualisasi":
                self._refresh_viz()
            elif key == "ringkasan":
                if self.last_summary:
                    self._update_summary_tab(self.last_summary)
            return None
        except Exception as e:  # render satu tab tidak boleh menjatuhkan app
            return str(e)

    # --------------------------------------------------------
    # TABS
    # --------------------------------------------------------
    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook = nb

        # Tab 1: Dashboard (PRO)
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="📊 Dashboard")
        self._build_dashboard_tab(tab1)

        # Tab 2: Compare Cabang (NEW v2.1)
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="⚖ Compare Cabang")
        self._build_compare_tab(tab2)

        # Tab 3: Quadrant Analysis (NEW v2.3)
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="🎯 Quadrant")
        self._build_quadrant_tab(tab3)

        # Tab 4: Rate League (NEW v2.3)
        tab4 = ttk.Frame(nb)
        nb.add(tab4, text="🏆 Rate League")
        self._build_rate_league_tab(tab4)

        # Tab 5: Hasil
        tab5 = ttk.Frame(nb)
        nb.add(tab5, text="📋 Hasil")
        self._build_result_tab(tab5)

        # Tab 6: Visualisasi (12 chart gallery)
        tab6 = ttk.Frame(nb)
        nb.add(tab6, text="📈 Visualisasi")
        self._build_viz_tab(tab6)

        # Tab 7: Ringkasan
        tab7 = ttk.Frame(nb)
        nb.add(tab7, text="🗂 Ringkasan")
        self._build_summary_tab(tab7)

        # Tab 8: Run Pipeline
        tab8 = ttk.Frame(nb)
        nb.add(tab8, text="▶ Run Pipeline")
        self._build_run_tab(tab8)

        # Tab 9: Konfigurasi
        tab9 = ttk.Frame(nb)
        nb.add(tab9, text="⚙ Konfigurasi")
        self._build_config_tab(tab9)

        # Tab 10: Bantuan
        tab10 = ttk.Frame(nb)
        nb.add(tab10, text="❓ Bantuan")
        self._build_help_tab(tab10)

        # H2: map widget-path tab → key (untuk lazy render via <<NotebookTabChanged>>)
        for _tab, _key in [
            (tab1, "dashboard"), (tab2, "compare"), (tab3, "quadrant"),
            (tab4, "rate_league"), (tab5, "hasil"), (tab6, "visualisasi"),
            (tab7, "ringkasan"),
        ]:
            self._tab_key_by_widget[str(_tab)] = _key
        # H2: render tab saat pertama kali dikunjungi bila dirty
        nb.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

        # L3: mirror _filter_profiles dihapus — profil dibaca langsung dari
        # modul wa_filters lewat _refresh_profile_dropdown()/get_profile().

    # --------------------------------------------------------
    # M5/M24: SHARED TREE SORT + POPULATE HELPERS
    # --------------------------------------------------------
    # M5/M24-dup: sorting + value-formatting + populate Treeview dulunya
    # di-copy-paste antar 4 tabel (dashboard/quadrant/hasil/ringkasan) dengan
    # logika sort duplikat (_sort_treeview vs _sort_quadrant_tree) — kini
    # SATU set helper dipakai semuanya.
    # --------------------------------------------------------

    @staticmethod
    def _format_cell(v, ndigits: int = 3):
        """M24: format satu nilai sel (dulu loop copy-paste 4×).

        None/NaN-float → ""; float → dibulatkan; lainnya apa adanya.
        """
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, float):
            return round(v, ndigits)
        return v

    @staticmethod
    def _column_is_numeric(df: pd.DataFrame, col) -> bool:
        """M5: True bila SEMUA nilai non-null kolom bisa dikonversi ke float
        (baris null tidak dihitung). Dipakai untuk: sort numerik vs string,
        anchor kolom 'e', dan state awal desc saat klik heading."""
        try:
            if df is None or col not in df.columns:
                return False
            s = df[col].dropna()
            if s.empty:
                return False
            s.astype(float)
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def _sort_df_for_treeview(cls, df: pd.DataFrame, col, state: str) -> pd.DataFrame:
        """M5/L21: sort df per kolom — numerik-aware, NaN SELALU di akhir.

        state: "asc" | "desc". Semua nilai non-null bisa di-float → sort
        numerik; selain itu sort string case-insensitive. Baris NaN/null
        di-mask keluar lalu di-append terakhir — arah sort tidak memindahkan
        mereka (L21).
        """
        if df is None or df.empty or col not in df.columns:
            return df
        ascending = (state == "asc")
        numeric = cls._column_is_numeric(df, col)
        if numeric:
            keys = pd.to_numeric(df[col], errors="coerce")
            na_mask = keys.isna()
        else:
            na_mask = df[col].isna()
            keys = df[col].astype(str).str.lower()
        tmp = df.copy()
        tmp["__waste_na__"] = na_mask.values
        tmp["__waste_key__"] = keys.values
        tmp = tmp.sort_values(
            ["__waste_na__", "__waste_key__"],
            ascending=[True, ascending], kind="mergesort",
        )
        return tmp.drop(columns=["__waste_na__", "__waste_key__"])

    def _apply_tree_sort_state(self, df: pd.DataFrame, tree) -> pd.DataFrame:
        """M5: saat re-render (filter/refresh), sort aktif tree dipertahankan
        bila kolomnya masih ada — urutan tidak reset diam-diam."""
        for col, state in self._tree_sort_states.get(str(tree), {}).items():
            if col in df.columns:
                return self._sort_df_for_treeview(df, col, state)
        return df

    def _apply_sort_indicator(self, tree):
        """M5b: indikator arah sort pada heading — " ▼" desc / " ▲" asc.
        Indikator lama di-strip dulu supaya tidak menumpuk."""
        state = self._tree_sort_states.get(str(tree), {})
        for col in tree["columns"]:
            try:
                base = str(tree.heading(col, "text"))
                for ind in (" ▼", " ▲"):
                    base = base.replace(ind, "")
                if col in state:
                    base += " ▼" if state[col] == "desc" else " ▲"
                tree.heading(col, text=base)
            except tk.TclError:
                pass

    def _tree_sort_handler(self, tree, get_df, render_fn):
        """M5: factory command sort untuk heading satu Treeview.

        get_df() → df sumber (sebelum sort); render_fn(df) → populate ulang
        tree (yang memanggil _apply_tree_sort_state + wiring lagi — tidak
        ada rekursi karena command hanya dieksekusi saat klik).
        Return callable(col) → handler klik heading kolom tsb.
        """
        tid = str(tree)

        def handler_for(col):
            def _on_heading_click():
                df = get_df() if callable(get_df) else get_df
                if df is None or df.empty:
                    return
                prev = self._tree_sort_states.get(tid, {}).get(col)
                if prev is None:
                    # M5a: klik kolom baru — numerik mulai desc, teks mulai asc
                    state = "desc" if self._column_is_numeric(df, col) else "asc"
                else:
                    state = "desc" if prev == "asc" else "asc"
                self._tree_sort_states[tid] = {col: state}
                render_fn(df)
            return _on_heading_click
        return handler_for

    def _wire_tree_sorting(self, tree, get_df, render_fn):
        """M5: pasang heading command sort + indikator untuk semua kolom tree.
        Dipanggil setiap populate (heading command tidak bertahan setelah
        tree['columns'] di-reset)."""
        handler_for = self._tree_sort_handler(tree, get_df, render_fn)
        for col in tree["columns"]:
            if col == "info":
                continue
            tree.heading(col, command=handler_for(col))
        self._apply_sort_indicator(tree)

    def _populate_tree(self, tree, df: pd.DataFrame, cols,
                       *, width=110, ndigits=3, cap=None,
                       tag_fn=None, get_df=None, render_fn=None):
        """M24/M16: SATU implementasi populate Treeview (dulu 4× copy-paste).

        - nilai via _format_cell (ndigits pembulatan per tabel);
        - cap jumlah baris (pagination) — label jumlah diurus caller;
        - tag per baris via tag_fn(vals) → str ("" = tanpa tag);
        - M16: kolom numerik anchor="e"; kolom nama (NAMA/KETERANGAN/ALASAN/
          REASONS) + kolom terakhir stretch=True;
        - get_df + render_fn dipasang untuk sort heading (M5).
        """
        scols = [str(c) for c in cols]
        tree["columns"] = scols
        for i, (c, sc) in enumerate(zip(cols, scols)):
            numeric = self._column_is_numeric(df, c)
            is_last = (i == len(cols) - 1)
            stretch = is_last or any(
                t in str(c).upper() for t in ("NAMA", "KETERANGAN", "ALASAN", "REASONS")
            )
            anchor = "e" if numeric else "w"
            tree.heading(sc, text=str(c), anchor=anchor)
            tree.column(sc, width=width, stretch=stretch, anchor=anchor)
        if df.empty:
            # L17: sheet kosong tetap menampilkan kolom asli + catatan (kosong)
            tree.insert("", "end",
                        values=["(kosong)"] + [""] * max(0, len(scols) - 1))
        else:
            show_df = df.loc[:, list(cols)]
            if cap is not None:
                show_df = show_df.head(cap)
            for row in show_df.itertuples(index=False, name=None):
                vals = [self._format_cell(v, ndigits) for v in row]
                tag = tag_fn(vals) if tag_fn else ""
                tree.insert("", "end", values=vals, tags=(tag,) if tag else ())
        if get_df is not None and render_fn is not None:
            self._wire_tree_sorting(tree, get_df, render_fn)

    # --------------------------------------------------------
    # M24: SHARED PNG EXPORT HELPER (dulu 4 loop duplikat)
    # --------------------------------------------------------
    @staticmethod
    def _sanitize_filename(name) -> str:
        """L7: bersihkan nama file — karakter ilegal Windows (\\ : ? * " < > |)
        + separator / dan spasi, supaya file PNG aman lintas OS."""
        name = str(name)
        for ch in '\\/:?*"<>|':
            name = name.replace(ch, "-")
        name = name.replace(" ", "_").replace("×", "x")
        return name or "chart"

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

    # --------------------------------------------------------
    # M16b: COMPARE METRIC LINE (dulu 10 kondisional inline + _fmt lokal)
    # --------------------------------------------------------
    @staticmethod
    def _format_compare_metric(label: str, val_a, val_b, fmt: str = "{:.1f}") -> str:
        """M16b: satu baris metric A|B + delta + persen.

        Tanda persen memakai '+' untuk ≥0 dan '−' (minus tipografis) untuk
        negatif; NaN → fallback teks tanpa delta.
        """
        try:
            fa, fb = float(val_a), float(val_b)
        except (ValueError, TypeError):
            return f"{label}: A={val_a} | B={val_b}"
        if fa != fa or fb != fb:  # NaN (series kosong dll.)
            return f"{label}: A={val_a} | B={val_b}"
        diff = fa - fb
        pct = (diff / fb * 100) if fb != 0 else 0.0
        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "=")
        sign = "+" if diff >= 0 else "−"
        return (
            f"{label}: A={fmt.format(fa)} | B={fmt.format(fb)} | "
            f"{arrow} {abs(diff):.1f} ({sign}{abs(pct):.1f}%)"
        )

    # --------------------------------------------------------
    # L11: KEYBOARD ACCELERATORS
    # --------------------------------------------------------
    def _on_accel_focus_search(self, event=None):
        """L11: Ctrl+F → pindah ke tab Dashboard + fokus kotak Cari."""
        try:
            self.notebook.select(0)
        except Exception:
            pass
        if hasattr(self, "_ent_search"):
            self._ent_search.focus_set()
        return "break"

    def _on_accel_refresh(self, event=None):
        """L11: Ctrl+R → refresh semua chart; ditolak saat pipeline/export
        masih berjalan (render di tengah run bisa balapan dengan worker)."""
        if self._pipeline_running or self._export_running:
            self._set_status("⚠ Refresh ditunda — pipeline/export sedang berjalan", "error")
            return "break"
        self._global_refresh()
        return "break"

    def _search_apply_now(self):
        """L11: Enter di kotak Cari → terapkan filter SEKARANG (bypass debounce)."""
        if self._suppress_trace:
            return "break"
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        self._apply_dashboard_filter()
        return "break"

    # --------------------------------------------------------
    # TAB 1: DASHBOARD (PRO — drill-down)
    # --------------------------------------------------------
    def _build_dashboard_tab(self, parent):
        """Dashboard layout: KPI cards row + filter bar + interactive charts + drill-down table.
        Wrapped in scrollable container (v2.3.0) — no more cut-off charts."""
        # Wrap seluruh tab content di scrollable Canvas. L3: columnconfigure/
        # rowconfigure pada parent DIHAPUS — satu-satunya child (container
        # _make_scrollable) di-pack, jadi konfigurasi grid-nya no-op.
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=1)
        # Row 3 (table) takes remaining space; rows 0-2 fixed
        inner.rowconfigure(3, weight=1)

        # ===== Row 0: KPI cards =====
        kpi_frame = tk.Frame(inner, bg=C_BG)
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
        filter_frame = tk.Frame(inner, bg=C_CARD, relief="flat",
                               highlightbackground=C_BORDER, highlightthickness=1)
        filter_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        filter_frame.columnconfigure(13, weight=1)

        # --- Row 0 of filter: search + cabang + status + clear ---
        tk.Label(filter_frame, text="🔍 Filter Drill-Down:", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).grid(row=0, column=0, padx=(10, 6), pady=6, sticky="w")

        tk.Label(filter_frame, text="Cari:", font=F_BODY, bg=C_CARD).grid(row=0, column=1, padx=2)
        self.var_search = tk.StringVar()
        # H1: debounce 300ms — trace tidak boleh re-render 3 chart + tabel per keystroke
        self.var_search.trace_add("write", lambda *_: self._on_search_changed())
        self._ent_search = ttk.Entry(filter_frame, textvariable=self.var_search, width=20)
        self._ent_search.grid(row=0, column=2, padx=2)
        # L11: Enter → apply filter segera (bypass debounce)
        self._ent_search.bind("<Return>", lambda _e: self._search_apply_now())

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

        # L6: label aksi konsisten (emoji + istilah teknis dipertahankan)
        self.btn_clear_filter = ttk.Button(filter_frame, text="✕ Clear Filter", command=self._clear_all_filters)
        # L14: pindah ke kolom berbobot (13) supaya tombol ikut tepi kanan
        # (dulu kolom 14 tanpa weight — tidak pernah melebar).
        self.btn_clear_filter.grid(row=0, column=13, sticky="e", padx=10)

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

        # Day range filter (HARI MAX in range) — M3: OPT-IN via checkbox.
        # Dulu rentang 1–31 diam-diam dianggap "tanpa filter" — membingungkan;
        # kini rentang hanya berlaku saat "Aktifkan rentang hari" dicentang.
        tk.Label(filter_frame, text="Hari MAX:", font=F_BODY, bg=C_CARD).grid(row=1, column=3, padx=(8, 2))
        # H4: StringVar + validate digits-only — IntVar.get() bisa raise TclError
        # saat user ketik nilai non-int / mengosongkan spinbox.
        _vcmd = self.register(self._digits_only)
        self.var_day_min = tk.StringVar(value="1")
        self.var_day_max = tk.StringVar(value="31")
        day_frame = tk.Frame(filter_frame, bg=C_CARD)
        day_frame.grid(row=1, column=4, columnspan=2, sticky="w", padx=2, pady=4)
        self.var_day_enabled = tk.BooleanVar(value=False)  # M3
        cb_day = tk.Checkbutton(day_frame, text="Aktifkan rentang hari",
                                variable=self.var_day_enabled, bg=C_CARD,
                                font=F_HINT, command=self._on_day_enabled_toggled)
        cb_day.pack(side="left")
        self._sb_day_min = ttk.Spinbox(day_frame, from_=1, to=31, textvariable=self.var_day_min, width=4,
                                       validate="key", validatecommand=(_vcmd, "%P"),
                                       command=self._on_day_range_changed)
        self._sb_day_min.pack(side="left")
        tk.Label(day_frame, text=" – ", bg=C_CARD, font=F_BODY).pack(side="left")
        self._sb_day_max = ttk.Spinbox(day_frame, from_=1, to=31, textvariable=self.var_day_max, width=4,
                                       validate="key", validatecommand=(_vcmd, "%P"),
                                       command=self._on_day_range_changed)
        self._sb_day_max.pack(side="left")
        # H4: apply juga saat user selesai ketik manual (bukan lewat panah spin)
        self._sb_day_min.bind("<FocusOut>", lambda e: self._on_day_range_changed())
        self._sb_day_max.bind("<FocusOut>", lambda e: self._on_day_range_changed())
        # M3: spinbox mati sampai checkbox dicentang
        self._set_day_spinbox_state(False)

        # Profile save/load
        tk.Label(filter_frame, text="Profil:", font=F_BODY, bg=C_CARD).grid(row=1, column=7, padx=(8, 2))
        self.var_profile_name = tk.StringVar()
        self._cb_profiles = ttk.Combobox(filter_frame, textvariable=self.var_profile_name, width=18, state="readonly")
        self._cb_profiles.grid(row=1, column=8, padx=2)
        self._refresh_profile_dropdown()
        ttk.Button(filter_frame, text="Muat", command=self._load_selected_profile).grid(row=1, column=9, padx=2)
        ttk.Button(filter_frame, text="Simpan Sebagai…", command=self._save_profile_dialog).grid(row=1, column=10, padx=2)
        ttk.Button(filter_frame, text="🗑", width=3, command=self._delete_selected_profile).grid(row=1, column=11, padx=2)

        # Active filter chips container (row 2)
        self.chips_frame = tk.Frame(filter_frame, bg=C_CARD)
        self.chips_frame.grid(row=2, column=0, columnspan=15, sticky="ew", padx=10, pady=(0, 6))
        self.chips_frame.columnconfigure(0, weight=1)

        # ===== Row 2: Interactive charts (3 charts) =====
        charts_frame = tk.Frame(inner, bg=C_BG)
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
        detail_frame = tk.Frame(inner, bg=C_CARD, relief="flat",
                                highlightbackground=C_BORDER, highlightthickness=1)
        detail_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)

        # Header
        hdr = tk.Frame(detail_frame, bg=C_CARD)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        tk.Label(hdr, text="📋 Drill-Down Detail Table", font=F_CARD, fg=C_HEADER,
                 bg=C_CARD).pack(side="left")
        self.lbl_detail_count = tk.Label(hdr, text="(belum ada data)", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_detail_count.pack(side="left", padx=8)
        ttk.Button(hdr, text="💾 Export CSV", command=self._export_filtered_csv).pack(side="right", padx=4)

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

        # L10: hint discoverability drill-down — aksi tersembunyi (double-click
        # + klik chart) sekarang punya petunjuk tepat di bawah tabel.
        tk.Label(
            detail_frame,
            text="💡 Klik 2× baris untuk drill-down cabang+item • klik bar chart untuk filter",
            font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD,
        ).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 6))

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
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
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
        """Update day_min/day_max dari spinboxes (H4: parse aman via _safe_int).
        M3: hanya aktif bila checkbox "Aktifkan rentang hari" dicentang —
        unchecked → day_min/day_max None (tanpa filter)."""
        dmin = self._safe_int(self.var_day_min, 1)
        dmax = self._safe_int(self.var_day_max, 31)
        if dmin < 1:
            dmin = 1
        if dmax > 31:
            dmax = 31
        if dmin > dmax:
            dmin, dmax = dmax, dmin
        if self.var_day_enabled.get():
            self.day_min = dmin
            self.day_max = dmax
        else:
            self.day_min = None
            self.day_max = None
        self._apply_dashboard_filter()

    def _on_day_enabled_toggled(self):
        """M3: checkbox rentang hari — enable/disable spinbox + re-apply."""
        self._set_day_spinbox_state(self.var_day_enabled.get())
        self._on_day_range_changed()

    def _set_day_spinbox_state(self, enabled: bool):
        """M3: enable/disable kedua spinbox rentang hari."""
        state = "normal" if enabled else "disabled"
        for sb in (getattr(self, "_sb_day_min", None),
                   getattr(self, "_sb_day_max", None)):
            if sb is None:
                continue
            try:
                sb.configure(state=state)
            except tk.TclError:
                pass

    # H1: debounce — search box tidak re-render per keystroke
    def _on_search_changed(self):
        """H1: debounce 300ms — tiap keystroke tidak re-render 3 chart + 500-row table."""
        if self._suppress_trace:
            return
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        self._search_after_id = self.after(300, self._search_debounced)

    def _search_debounced(self):
        self._search_after_id = None
        self._apply_dashboard_filter()

    def _on_chart_click(self, key: str, value: str | None):
        """Handler untuk klik chart. value=None artinya clear filter ini.

        M9 (re-entrant): render dipanggil lewat after_idle supaya event handler
        matplotlib selesai PULANG sebelum canvas di-destroy oleh re-render —
        klik chart yang sedang aktif tidak lagi TclError."""
        self.active_filters[key] = value
        # Sync dropdown UI
        if key == "cabang":
            self.var_filter_cabang.set(value if value else "(Semua)")
        elif key == "status":
            self.var_filter_status.set(value if value else "(Semua)")
        self.after_idle(lambda: self._apply_dashboard_filter())

    def _reset_filters_state(self):
        """H5: reset SEMUA state filter TANPA render (untuk restore programmatic)."""
        self._suppress_trace = True
        try:
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
            self.var_day_min.set("1")
            self.var_day_max.set("31")
            # M3: checkbox rentang hari ikut di-reset (spinbox kembali mati)
            self.var_day_enabled.set(False)
            self._set_day_spinbox_state(False)
            for v in self._jenis_vars.values():
                v.set(False)
        finally:
            self._suppress_trace = False

    def _clear_all_filters(self):
        # H5: suppress trace saat restore — SATU render di akhir (bukan 2x + flash)
        self._reset_filters_state()
        self._apply_dashboard_filter()

    def _compute_filtered_df(self) -> pd.DataFrame | None:
        """H1: hitung df terfilter (pure — tanpa render). None bila belum ada data.

        M23: logika filter dipindah ke _apply_filters() — fungsi murni shared
        (dulu duplikat ~20 baris antara filter Dashboard dan export CSV)."""
        df = self._preview_dfs.get("Detail")
        if df is None or df.empty:
            return None
        return _apply_filters(
            df, self.active_filters, self.day_min, self.day_max,
            self.var_search.get(),
        )

    def _apply_dashboard_filter(self):
        """Apply semua filter aktif + re-render chart & tabel Dashboard."""
        filtered = self._compute_filtered_df()
        if filtered is None:
            return
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
        # Add day range chip (M6: key "hari" → label "Rentang Hari"; chip hanya
        # muncul saat rentang aktif — day_min None = tanpa filter)
        if self.day_min is not None and self.day_max is not None:
            active_items.append(("hari", f"{self.day_min}-{self.day_max}"))
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
            # M6: key mentah → label Indonesia ("cabang: X" → "Cabang: X")
            label = CHIP_LABELS.get(k, k)
            chip = FilterChip(self.chips_frame, f"{label}: {v}",
                              on_remove=lambda key=k: self._remove_filter(key))
            chip.grid(row=0, column=col, sticky="w", padx=2)
            col += 1

    def _remove_filter(self, key: str):
        if key == "jenis":
            self.active_filters[key] = []
            for v in self._jenis_vars.values():
                v.set(False)
        elif key in ("hari", "Hari MAX"):  # "Hari MAX": key lama (compat)
            self.day_min = None
            self.day_max = None
            self.var_day_min.set("1")
            self.var_day_max.set("31")
            # M3: uncheck checkbox + matikan spinbox
            self.var_day_enabled.set(False)
            self._set_day_spinbox_state(False)
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
        name = simpledialog.askstring("Simpan Profil", "Nama profil filter:",
                                       parent=self,
                                       initialvalue=self.var_profile_name.get() or "Profil Baru")
        if not name:
            return
        # H7: jangan timpa profil lama secara diam-diam — konfirmasi dulu
        if name in wa_filters.list_profile_names():
            if not messagebox.askyesno("Timpa profil?", f"Profil '{name}' sudah ada. Timpa?"):
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
            # L3: mirror _filter_profiles dihapus — dropdown refresh dari modul
            self._refresh_profile_dropdown()
            self.var_profile_name.set(name)
            messagebox.showinfo("Profil", f"Profil '{name}' disimpan.")
        else:
            messagebox.showerror("Error Profil", f"Gagal simpan profil '{name}'.")

    def _load_selected_profile(self):
        """Load selected profile from dropdown."""
        name = self.var_profile_name.get()
        if not name:
            messagebox.showwarning("Profil", "Pilih profil dulu.")
            return
        profile = wa_filters.get_profile(name)
        if not profile:
            messagebox.showerror("Profil", f"Profil '{name}' tidak ditemukan.")
            return
        # H5: suppress trace selama restore — SEMUA var dipulihkan dulu,
        # SATU render eksplisit di akhir (sebelumnya trace search men-trigger
        # apply di tengah restore → double render + flash state salah).
        self._suppress_trace = True
        try:
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
                self.var_day_min.set(str(self.day_min))
                self.var_day_max.set(str(self.day_max))
                # M3: profil dengan rentang hari → aktifkan checkbox + spinbox
                self.var_day_enabled.set(True)
                self._set_day_spinbox_state(True)
            else:
                self.day_min = None
                self.day_max = None
                self.var_day_min.set("1")
                self.var_day_max.set("31")
                self.var_day_enabled.set(False)
                self._set_day_spinbox_state(False)
        finally:
            self._suppress_trace = False
        self._apply_dashboard_filter()  # H5: SATU render setelah semua var konsisten
        messagebox.showinfo("Profil", f"Profil '{name}' di-load.")

    def _delete_selected_profile(self):
        """Delete selected profile from dropdown."""
        name = self.var_profile_name.get()
        if not name:
            return
        if not messagebox.askyesno("Hapus Profil", f"Hapus profil '{name}'?"):
            return
        if wa_filters.delete_profile(name):
            # L3: mirror _filter_profiles dihapus — dropdown refresh dari modul
            self._refresh_profile_dropdown()
            messagebox.showinfo("Profil", f"Profil '{name}' dihapus.")

    # --------------------------------------------------------
    # RENDER DASHBOARD CHARTS (interactive)
    # --------------------------------------------------------
    def _render_dashboard_charts(self, df: pd.DataFrame):
        # H3: dispose figure + canvas lama SEBELUM buat baru (leak fix).
        # Semua registry disimpan sebagai (key, fig, canvas).
        self._dispose_chart_registry(self._dash_canvases)
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
                         font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                    row=0, column=0, sticky="nsew", padx=20, pady=20)
            return

        # Build active_filter tuple untuk highlight
        def _af(key):
            return (key, self.active_filters.get(key))

        # Chart interaktif sekarang mengembalikan TUPLE (Figure, on_click)
        # (dashboard.py v2.3.2) — ambil elemen Figure-nya.
        def _fig_of(result):
            return result[0] if isinstance(result, tuple) else result

        # Chart 1: Status bar (interactive)
        f0 = self._dash_chart_frames[0]
        fig0 = _fig_of(wa_dash.chart_status_bar_interactive(df, on_click=self._on_chart_click, active_filter=_af("status")))
        c0 = wa_charts.embed_figure(f0, fig0)
        c0.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("status", fig0, c0))

        # Chart 2: Cabang bar (interactive)
        f1 = self._dash_chart_frames[1]
        fig1 = _fig_of(wa_dash.chart_cabang_bar_interactive(df, on_click=self._on_chart_click, active_filter=_af("cabang")))
        c1 = wa_charts.embed_figure(f1, fig1)
        c1.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("cabang", fig1, c1))

        # Chart 3: Top items (interactive)
        f2 = self._dash_chart_frames[2]
        fig2 = _fig_of(wa_dash.chart_top_items_interactive(df, on_click=self._on_chart_click, active_filter=_af("item")))
        c2 = wa_charts.embed_figure(f2, fig2)
        c2.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._dash_canvases.append(("item", fig2, c2))

    # --------------------------------------------------------
    # RENDER DASHBOARD TABLE
    # --------------------------------------------------------
    def _render_dashboard_table(self, df: pd.DataFrame):
        """Populate drill-down table — M24: format+insert via _populate_tree,
        M5: sort per-kolom dengan indikator ▼/▲, L3: tag fiktif
        status_<idx> yang langsung ditimpa dihapus."""
        tree = self.tree_dashboard
        tree.delete(*tree.get_children(""))
        if df is None or df.empty:
            tree["columns"] = ["info"]
            tree.heading("info", text="info")
            tree.insert("", "end", values=["(tidak ada baris untuk filter ini)"])
            self.lbl_detail_count.configure(text="0 baris")
            return

        # M5: pertahankan sort aktif saat re-render (ganti filter/refresh)
        df = self._apply_tree_sort_state(df, tree)

        # Pilih kolom utama untuk tampil (lainnya ada di Excel export)
        display_cols = [
            "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
            "TOTAL", "MAX", "Count Hari",
            "ANOMALY SCORE", "ANOMALY STATUS", "ANOMALY REASONS",
            "KATEGORI ANOMALI", "RANGKING WASTE",
        ]
        cols = [c for c in display_cols if c in df.columns]
        status_col_idx = cols.index("ANOMALY STATUS") if "ANOMALY STATUS" in cols else None

        def _tag_fn(vals):
            if (status_col_idx is not None and status_col_idx < len(vals)
                    and vals[status_col_idx] in C_STATUS):
                return str(vals[status_col_idx]).replace(" ", "_").lower()
            return ""

        self._populate_tree(
            tree, df, cols, width=110, ndigits=3, cap=500, tag_fn=_tag_fn,
            get_df=self._compute_filtered_df,       # M5: sumber sort = filter saat ini
            render_fn=self._render_dashboard_table,  # klik heading → render ulang
        )

        # Status coloring via tag
        for status, (fg, bg) in C_STATUS.items():
            tree.tag_configure(status.replace(" ", "_").lower(), background=bg, foreground=fg)

        count = len(df)
        self.lbl_detail_count.configure(
            text=f"{count} baris (menampilkan {min(500, count)} pertama)"
        )

    # L3: _sort_treeview() DIHAPUS — digantikan shared helper M5
    # (_sort_df_for_treeview + _tree_sort_handler + _wire_tree_sorting).

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

    def _export_filtered_csv(self):
        """Export current filtered rows to CSV (lightweight, no Excel dependency)."""
        filtered = self._compute_filtered_df()
        if filtered is None or filtered.empty:
            messagebox.showinfo("Export", "Belum ada data. Run pipeline dulu.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Filtered CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        try:
            filtered.to_csv(path, index=False, encoding="utf-8-sig")
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
        else:
            # L3: variabel `normal` dihapus — tidak pernah dipakai
            prioritas = potensi = review = 0
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

        # Populate cabang dropdown — M10: JANGAN reset pilihan saat refresh;
        # pertahankan bila nilai masih ada di daftar baru (dulu selalu kembali
        # ke "(Semua)" setiap refresh/re-render).
        if "NAMA RESTO" in df.columns:
            cabangs = sorted(df["NAMA RESTO"].dropna().astype(str).unique().tolist())
            cur = self.var_filter_cabang.get()
            if hasattr(self, "_cb_cabang"):
                new_vals = ["(Semua)"] + cabangs
                self._cb_cabang["values"] = new_vals
                self.var_filter_cabang.set(cur if cur in new_vals else "(Semua)")
            # Update dropdown tab Compare juga (M10: preserve-or-empty)
            if hasattr(self, "_cb_compare_a"):
                cur_a = self.var_compare_a.get()
                cur_b = self.var_compare_b.get()
                self._cb_compare_a["values"] = cabangs
                self._cb_compare_b["values"] = cabangs
                self.var_compare_a.set(cur_a if cur_a in cabangs else "")
                self.var_compare_b.set(cur_b if cur_b in cabangs else "")

    # --------------------------------------------------------
    # TAB 2: COMPARE CABANG (NEW v2.1)
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # TAB 3: QUADRANT ANALYSIS (NEW v2.3.0)
    # --------------------------------------------------------
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
        try:
            fig1 = wa_dash.chart_quadrant_scatter(df, key_akhir=self._last_key_akhir)
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

    # L3/M24-dup: _sort_quadrant_tree() DIHAPUS — duplikat _sort_treeview,
    # keduanya digantikan shared helper M5.

    def _export_quadrant_charts(self):
        """M24: export PNG via helper shared (dulu loop duplikat)."""
        if not self._quadrant_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(
            self._quadrant_canvases, lambda key: f"quadrant_{key}"
        )

    # --------------------------------------------------------
    # TAB 4: RATE LEAGUE (NEW v2.3.0)
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # TAB 5: HASIL (preview all sheets)
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # TAB 6: VISUALISASI (12 chart gallery)
    # --------------------------------------------------------
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
            tk.Label(title_frame, text=f"📊 {title}", font=(FONT_NAME, 9, "bold"),
                     fg=C_HEADER, bg=C_TITLE_BG).pack(side="left", padx=8, pady=6)
            tk.Label(title_frame, text=desc, font=F_HINT, fg=C_TEXT_MUTED, bg=C_TITLE_BG).pack(side="left", padx=8)
            try:
                fig = fn(df)
                canvas_widget = wa_charts.embed_figure(card, fig)
                canvas_widget.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
                self._viz_canvases.append((title, fig, canvas_widget))
            except Exception as e:
                err = tk.Label(card, text=f"Gagal render:\n{e}",  # L6
                              font=F_BODY, fg="#dc2626", bg=C_CARD, justify="left")
                err.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        for c_i in range(cols_per_row):
            self._viz_inner.columnconfigure(c_i, weight=1, minsize=420)

    def _export_all_charts(self):
        """M24: export PNG via helper shared (dulu loop duplikat; key = judul chart)."""
        if not self._viz_canvases:
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(self._viz_canvases)

    # --------------------------------------------------------
    # TAB 7: RINGKASAN
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # TAB 8: RUN PIPELINE
    # --------------------------------------------------------
    def _build_run_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # L12: borderwidth dihapus (semua kartu di bawah sama)
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Input Workbook", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_workbook = tk.StringVar()
        self._ent_workbook = ttk.Entry(frm, textvariable=self.var_workbook)
        self._ent_workbook.pack(side="left", fill="x", expand=True, padx=(0, 8))
        # L11: Enter di kolom workbook → mulai/batalkan run langsung
        self._ent_workbook.bind("<Return>", self._run_from_entry)
        ttk.Button(frm, text="Browse…", command=self._browse_workbook).pack(side="left", padx=4)
        ttk.Button(frm, text="Buka Folder Sample", command=self._open_data_folder).pack(side="left", padx=4)

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c2, text="Parameter", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm2 = ttk.Frame(c2)
        frm2.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frm2, text="Key Akhir (1-31):").pack(side="left", padx=(0, 8))
        # H4: StringVar + validate digits — IntVar.get() TclError kalau kosong;
        # guard config default_key_akhir non-int → fallback 31.
        try:
            _ka_default = int(self.config.get("default_key_akhir", 31))
        except (TypeError, ValueError):
            _ka_default = 31
        if not (1 <= _ka_default <= 31):
            _ka_default = 31
        self.var_key_akhir = tk.StringVar(value=str(_ka_default))
        _vcmd_ka = self.register(self._digits_only)
        ttk.Spinbox(frm2, from_=1, to=31, textvariable=self.var_key_akhir, width=6,
                    validate="key", validatecommand=(_vcmd_ka, "%P")).pack(side="left", padx=4)
        tk.Label(frm2, text="(hanya hari 1..N dianalisa)", font=F_HINT, foreground=C_TEXT_MUTED).pack(side="left", padx=8)
        # H6: baris Output Excel DIHAPUS — pipeline in-memory; laporan dibuat
        # on-demand via "💾 Export Laporan Excel" di tab Hasil.

        c3 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c3.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(3, weight=1)
        tk.Label(c3, text="Kontrol", font=F_CARD, fg=C_HEADER, bg=C_CARD).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        frm3 = ttk.Frame(c3)
        frm3.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        # M21: tombol dua-mode — "▶ Mulai Pipeline" ↔ "⏹ Batalkan Run"
        # (command _on_run_button memutuskan berdasar _pipeline_running).
        self.btn_run = ttk.Button(frm3, text="▶ Mulai Pipeline", style="Accent.TButton", command=self._on_run_button)
        self.btn_run.pack(side="left", padx=4)
        self.btn_log = ttk.Button(frm3, text="Log Proses", command=self._show_log_popup)
        self.btn_log.pack(side="left", padx=4)
        # H6: tombol "Buka Folder Output" / "Buka Downloads" dihapus — tidak ada
        # lagi file output otomatis (pipeline in-memory); CSV/Excel export memilih
        # lokasi sendiri lewat file dialog saat export.
        self.progress = ttk.Progressbar(c3, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        self.lbl_status = tk.Label(c3, text="Siap. Pilih workbook dan klik Mulai Pipeline.", bg=C_CARD, fg=C_TEXT_MUTED, font=F_BODY, anchor="w")
        self.lbl_status.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 12))

    # --------------------------------------------------------
    # TAB 9: KONFIGURASI
    # --------------------------------------------------------
    def _build_config_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # L12: borderwidth dihapus
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Threshold & Konfigurasi", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text=f"Di-load dari: {CONFIG_PATH}", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16)
        tk.Label(c1, text="Edit nilai threshold di bawah, lalu klik Simpan untuk apply ke config.json.", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        canvas = tk.Canvas(c2, bg=C_CARD, highlightthickness=0)
        sb = ttk.Scrollbar(c2, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=C_CARD)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        _cfg_window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        # M12: width-sync — input threshold ikut lebar canvas; C3: wheel via
        # global dispatcher (sebelumnya canvas ini TIDAK bisa di-scroll sama sekali).
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_cfg_window_id, width=e.width))
        canvas._waste_scroll = True  # type: ignore[attr-defined]

        # L3: type hint diperbaiki — isinya StringVar, bukan tk.Entry
        self._config_vars: dict[str, tk.StringVar] = {}
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
    # TAB 10: BANTUAN
    # --------------------------------------------------------
    def _build_help_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # L12: borderwidth dihapus
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c1.columnconfigure(0, weight=1)
        c1.rowconfigure(0, weight=1)

        txt = tk.Text(c1, wrap="word", relief="flat", bg=C_CARD, fg=C_TEXT_MAIN, font=F_BODY, padx=20, pady=16)
        sb = ttk.Scrollbar(c1, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        help_text = f"""{APP_TITLE} v{APP_VERSION}

=== CARA PAKAI ===

1. Siapkan workbook Excel `DATA_WASTE.xlsx` (struktur 53 kolom standar):
   Workflow: Query data → Olah di Excel → Save as DATA_WASTE.xlsx
   • DATA_WASTE (sheet utama) — data waste harian (kolom 1..31 + NAMA RESTO + NAMA BARANG + JENIS + KETERANGAN + SATUAN + dll)
   • BOM (opsional) — master Bill of Materials (Nomor #, Nama Barang, TOTAL BOM)
   • DATABASE_SATUAN (opsional) — master helper per kategori (NAMA ITEM + 11 kolom kategori)
   Sheet name auto-detect: DATA_WASTE / Sheet1 / REKAP_MENTAH / DATA / dll

2. Tab "Run Pipeline":
   • Browse... → pilih workbook Excel (DATA_WASTE.xlsx Anda)
   • Isi Key Akhir (1..31) — cutoff hari terakhir periode analisa
   • Klik "Mulai Pipeline" (hasil diproses IN-MEMORY, tidak menulis file).
     Selama run, tombol berubah menjadi "⏹ Batalkan Run" — pembatalan
     efektif antar stage / saat pipeline selesai (hasil dibuang).

3. Setelah selesai, tab "Dashboard" otomatis ter-isi:
   • KPI cards di atas (total, prioritas, potensi, waste, cabang)
   • 3 chart interaktif (klik bar untuk filter)
   • Drill-down table dengan sortable columns + status coloring

=== DRILL-DOWN (NEW v2.0) ===

Cara drill-down:
  1. Klik bar/slice di chart interaktif → auto-filter table + re-render chart lain
  2. Pilih dropdown Cabang/Status → filter langsung
  3. Ketik di Search box → filter free-text semua kolom
  4. Active filter chips muncul di atas table (klik chip ATAU × untuk remove)
  5. Double-click baris di table → drill-down ke cabang+item baris itu
  6. Klik header kolom table → sort naik/turun (indikator ▼/▲; kolom
     numerik sort angka, teks sort case-insensitive, NaN selalu di akhir)

Rentang hari (HARI MAX): centang "Aktifkan rentang hari" lalu atur 1–31.
Tanpa centang, semua hari ditampilkan (tidak ada filter).

Contoh workflow analisa:
  - Klik bar "Prioritas Tinggi" → lihat semua baris prioritas
  - Klik bar cabang "RESTO.PWKTAM" → fokus ke cabang itu
  - Klik bar top item "Bawang Putih" → lihat detail per-hari item itu
  - Search "Cancel Nota" → filter semua baris dengan keterangan itu

=== OUTPUT LAPORAN EXCEL — 6 SHEET (v2.4) ===

Pipeline berjalan IN-MEMORY (tidak otomatis menulis file Excel).
Untuk membuat laporan Excel 6 sheet:
  1. Buka tab "📋 Hasil" → klik "💾 Export Laporan Excel…"
  2. Pilih lokasi & nama file — default: Documents, nama disarankan
     Waste_Anomaly_Report_YYYYMMDD_HHMM.xlsx
  3. Sheet yang dihasilkan:
     • Detail             — semua baris (kolom mengikuti M code Final order)
     • Anomali Prioritas  — hanya Prioritas Tinggi + Potensi Anomali
     • Per Cabang         — ringkasan per NAMA RESTO
     • Top Items          — top 20 item by TOTAL waste
     • Pareto Alasan      — group by KETERANGAN + cumulative %
     • Log Run            — timestamp + parameter + log lines
  4. Kalau file sedang dibuka di Excel, akan muncul pesan untuk menutupnya
     dulu lalu ulangi.

Export CSV (tabel ter-filter) tersedia di tab Dashboard — "💾 Export CSV".

=== SHORTCUT KEYBOARD (v2.3.1) ===

• Enter di kolom workbook (tab Run Pipeline) → mulai run / batalkan run
• Enter di kotak Cari (tab Dashboard) → terapkan filter segera
  (tanpa menunggu debounce 300 ms)
• Ctrl+F → pindah ke tab Dashboard + fokus kotak Cari
• Ctrl+R → refresh semua chart (ditolak saat pipeline/export berjalan)
• Scroll wheel (mouse) → gulir tab panjang (Dashboard/Visualisasi/
  Konfigurasi); Treeview/Text menggulir sendiri

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
  → Pastikan workbook punya sheet DATA_WASTE / Sheet1 / REKAP_MENTAH.
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
        # L9: footer statis "Siap • v{APP_VERSION} • © 2025" — tanggal dinamis
        # dihapus (membeku kalau app lama terbuka); status live tetap lewat
        # _set_status yang menulis ulang teks footer saat ada event.
        self.lbl_footer = tk.Label(
            ftr, text=f"Siap  •  v{APP_VERSION}  •  © 2025",
            bg=C_FOOTER, fg=C_TEXT_MUTED, font=F_HINT,
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

    def _open_data_folder(self):
        data_dir = APP_DIR / "data"
        data_dir.mkdir(exist_ok=True)
        self._open_path_in_explorer(data_dir)

    # H6: _browse_output / _open_output_folder / _open_output DIHAPUS —
    # pipeline in-memory; export Excel/CSV memilih lokasi via file dialog.

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
        # C2: cek liveness — popup yang di-destroy di-recreate (X sekarang hanya
        # withdraw, tapi guard tetap untuk destroy programmatic/WM).
        if self.log_popup is None or not self._winfo_alive(self.log_popup):
            self.log_popup = SimpleLogPopup(self)
            # Replay buffer log — log() tetap berguna walau popup sempat hilang
            for line in list(self._log_lines):
                self.log_popup.append(line)
        try:
            self.log_popup.deiconify()  # M20: tanpa focus_force()
            self.log_popup.lift()
        except tk.TclError:
            self.log_popup = None

    @staticmethod
    def _winfo_alive(w) -> bool:
        try:
            return bool(w is not None and w.winfo_exists())
        except tk.TclError:
            return False

    # --------------------------------------------------------
    # M1: WM_DELETE_WINDOW + M21: RUN/CANCEL
    # --------------------------------------------------------
    def _on_close(self):
        """M1: tombol X / menu close — konfirmasi bila pipeline atau export
        Excel masih berjalan di background thread (menutup paksa membuang
        hasil run)."""
        if self._pipeline_running or self._export_running:
            if not messagebox.askyesno(
                "Pipeline masih berjalan",
                "Run pipeline belum selesai. Tetap keluar?",
            ):
                return
        try:
            self.destroy()
        except tk.TclError:
            pass  # window sudah di-destroy (double event)

    # M21: tombol Run dua-mode — "▶ Mulai Pipeline" ↔ "⏹ Batalkan Run"
    def _on_run_button(self):
        if self._pipeline_running:
            self._cancel_pipeline()
        else:
            self._start_pipeline()

    def _run_from_entry(self, _event=None):
        """L11: Enter di kolom workbook → aksi tombol Run (mulai/batalkan)."""
        self._on_run_button()
        return "break"

    def _cancel_pipeline(self):
        """M21: set flag cancel — pipeline berhenti di titik berikutnya.

        CATATAN: pipeline.py tidak menyediakan hook cancel mid-stage (grep
        'cancel' kosong), jadi pembatalan efektif ANTAR STAGE / saat pipeline
        selesai — hasil tetap dihitung sampai selesai lalu DIBUANG (tidak
        dirender). Tombol di-disable setelah klik supaya tidak double-cancel.
        """
        if not self._pipeline_running:
            return
        self._pipeline_cancel.set()
        self.btn_run.configure(state="disabled")
        self._set_status("⏹ Membatalkan run… (efektif antar stage / saat selesai)", "running")
        self.log("=== Permintaan batal diterima — hasil akan dibuang saat pipeline kembali ===")

    def _set_run_button(self, mode: str):
        """M21: teks/state tombol run. mode "cancel" = sedang berjalan;
        "start" = idle (normal + label mulai)."""
        if not hasattr(self, "btn_run"):
            return
        if mode == "cancel":
            self.btn_run.configure(text="⏹ Batalkan Run")
        else:
            self.btn_run.configure(text="▶ Mulai Pipeline", state="normal")

    def _finish_run_state(self):
        """C1+M21: pulihkan state run (flag, tombol) — dipanggil di SEMUA jalur
        keluar (done/error/cancel) supaya tombol tidak pernah macet."""
        self._pipeline_running = False
        self._pipeline_cancel.clear()
        self._set_run_button("start")

    def _start_pipeline(self):
        if self._pipeline_running:
            return  # C1: guard double-run (normalnya tombol sudah ke mode cancel)
        wb_path = self.var_workbook.get().strip()
        if not wb_path or not Path(wb_path).exists():
            messagebox.showerror("Input Error", "Workbook belum dipilih atau tidak ditemukan.")
            return
        # H4: parse aman — StringVar + validate digits
        ka = self._safe_int(self.var_key_akhir, -1)
        if not (1 <= ka <= 31):
            messagebox.showerror("Input Error", "Key Akhir harus angka antara 1 dan 31.")
            return

        self._pipeline_running = True
        self._pipeline_cancel.clear()
        # M21: tombol TETAP aktif — berubah jadi "⏹ Batalkan Run" (dulu di-disable,
        # sekarang bisa membatalkan). _finish_run_state memulihkan di semua jalur.
        self._set_run_button("cancel")
        self.progress["value"] = 0
        self._set_status("Memulai…", "running")

        self._show_log_popup()
        if self.log_popup:
            self.log_popup.clear()
        # H6: log lewat self.log() — masuk buffer juga (dipakai sheet Log Run)
        self._log_lines.clear()
        self.log("=== Mulai Pipeline ===")
        self.log(f"Workbook: {wb_path} • Key Akhir: {ka} (in-memory)")

        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(wb_path, ka),
            daemon=True,
        )
        self.worker_thread.start()

    def _worker_run(self, wb_path: str, key_akhir: int):
        """Thread pekerja — pipeline in-memory (output_path param legacy, tidak
        perlu di-pass). Semua hasil/error dikirim balik lewat ui_queue.

        M21: pembatalan — pipeline.py TIDAK punya hook cancel per-stage
        (grep 'cancel' kosong), jadi flag cancel dicek SETELAH run_pipeline()
        kembali: kalau user membatalkan, hasil DIBUANG dan dikirim sebagai
        error "Run dibatalkan pengguna" (tidak dirender)."""
        try:
            summary = run_pipeline(
                workbook_path=wb_path,
                key_akhir=key_akhir,
                progress_callback=lambda msg, pct: self.ui_queue.put(("log", msg, pct)),
            )
            if self._pipeline_cancel.is_set():
                self.ui_queue.put(("error", "Run dibatalkan pengguna", None))
                return
            self.ui_queue.put(("done", summary, None))
        except Exception as e:
            # Sertakan traceback lengkap di queue — ditampilkan di log popup,
            # messagebox hanya pesan singkat (fix worker error detail).
            self.ui_queue.put(("error", str(e), traceback.format_exc()))

    def _drain_queue(self):
        # Reschedule FIRST (fix C1) — polling loop tidak boleh mati oleh
        # exception apa pun, kalau tidak UI freeze + Run button macet disabled.
        self.after(100, self._drain_queue)
        while True:
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._process_queue_item(item)
            except Exception as e:  # noqa: BLE001 — loop must survive anything
                self._set_status(f"⚠ {e}")
                self.log(f"⚠ Error memproses event UI: {e}")

    def _process_queue_item(self, item):
        """Dispatch satu item dari ui_queue (dipisah dari _drain_queue, fix C1)."""
        tag = item[0] if item else None
        if tag == "log":
            _, msg, pct = item
            # C2/H6: lewat self.log() — buffer internal + popup bila hidup
            self.log(msg)
            if pct is not None:
                self.progress["value"] = float(pct)
            self._set_status(msg, "running")
        elif tag == "done":
            _, summary, _ = item
            # C1: pulihkan state tombol/flag SEBELUM render — exception saat
            # render hasil tidak boleh membuat Run button macet disabled.
            self._finish_run_state()
            try:
                self._on_pipeline_done(summary)
            except Exception as e:  # noqa: BLE001 — render hasil best-effort
                self._set_status(f"⚠ Render hasil gagal: {e}", "error")
                self.log(f"⚠ Gagal render hasil pipeline: {e}")
        elif tag == "error":
            _, err, tb = (item + (None,))[:3] if len(item) < 3 else item
            self._finish_run_state()
            self._on_pipeline_error(err, tb)
        elif tag == "export_done":
            _, result, _ = item
            self._on_export_done(result)

    def _on_pipeline_done(self, summary: dict):
        self._finish_run_state()  # C1+M21: flag + tombol pulih di jalur mana pun
        if not summary.get("success"):
            self._on_pipeline_error(summary.get("error", "Unknown error"))
            return
        self.progress["value"] = 100
        # In-memory DataFrame (NO Excel file output)
        df = summary.get("df")
        self.last_summary = summary
        self._last_run_time = datetime.now()
        # Simpan key_akhir ASLI run ini (dipakai quadrant scatter + export Excel)
        try:
            self._last_key_akhir = int(summary.get("key_akhir", 31))
        except (TypeError, ValueError):
            self._last_key_akhir = 31
        rows = summary.get("total_rows", 0)
        self._set_status(f"✓ Pipeline selesai — {rows} baris", "done")
        self.log("=== Selesai ===")  # L6: "DONE" → "Selesai"
        self.log(f"Total baris: {rows}")
        self.log(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
        self.log("Data siap in-memory — export Excel via tab Hasil")
        # Surface config_load_error (tidak ditelan pipeline)
        cfg_err = summary.get("config_load_error")
        if cfg_err:
            self.log(f"⚠ Config load error: {cfg_err} — threshold memakai default")

        # Build preview_dfs dari DataFrame summary (no Excel read).
        # L17: fallback sheet kosong kini memakai kolom ASLI yang diharapkan
        # (dulu df.iloc[0:0] — kolom Detail bocor ke sheet lain → header salah
        # di tab Hasil; sekarang placeholder kolom + baris "(kosong)").
        if df is not None and not df.empty:
            self._pipeline_df = df  # H6: df utk tombol Export Laporan Excel
            self._preview_dfs["Detail"] = df
            # Build derived sheets in-memory
            self._preview_dfs["Anomali Prioritas"] = df[df["ANOMALY STATUS"].isin(
                ["Prioritas Tinggi", "Potensi Anomali"]
            )].sort_values("ANOMALY SCORE", ascending=False) if "ANOMALY STATUS" in df.columns else df.head(0)
            # Per Cabang summary (in-memory) — L17: builder dibungkus try/except
            # supaya kolom pendukung yang hilang (NAMA BARANG/TOTAL/dll.) tidak
            # melempar KeyError; sheet tetap dibuat dengan kolom yang diharapkan.
            _PC_COLS = ["Cabang", "Jumlah_Barang", "Total_Waste", "Max_Waste_Harian",
                        "Anomali_Prioritas", "Anomali_Potensi", "Anomali_Review"]
            if "NAMA RESTO" in df.columns:
                try:
                    self._preview_dfs["Per Cabang"] = (
                        df.groupby("NAMA RESTO", dropna=False).agg(
                            Jumlah_Barang=("NAMA BARANG", "size"),
                            Total_Waste=("TOTAL", "sum"),
                            Max_Waste_Harian=("MAX", "max"),
                            Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                            Anomali_Potensi=("ANOMALY STATUS", lambda x: int((x == "Potensi Anomali").sum())),
                            Anomali_Review=("ANOMALY STATUS", lambda x: int((x == "Perlu Review").sum())),
                        ).reset_index().rename(columns={"NAMA RESTO": "Cabang"})
                        .sort_values("Anomali_Prioritas", ascending=False)
                    )
                except Exception as e:  # kolom pendukung hilang → fallback kosong
                    self.log(f"⚠ Gagal membangun sheet 'Per Cabang': {e}")
                    self._preview_dfs["Per Cabang"] = pd.DataFrame(columns=_PC_COLS)
            else:
                self._preview_dfs["Per Cabang"] = pd.DataFrame(columns=_PC_COLS)
            # Top Items
            _TI_COLS = ["Rank", "NAMA BARANG", "JENIS", "Total_Waste", "Max_Waste",
                        "Cabang_Terpengaruh", "Anomali_Prioritas"]
            if "NAMA BARANG" in df.columns:
                try:
                    self._preview_dfs["Top Items"] = (
                        df.groupby(["NAMA BARANG", "JENIS"], dropna=False).agg(
                            Total_Waste=("TOTAL", "sum"),
                            Max_Waste=("MAX", "max"),
                            Cabang_Terpengaruh=("NAMA RESTO", "nunique"),
                            Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                        ).reset_index().sort_values("Total_Waste", ascending=False).head(20)
                    )
                    self._preview_dfs["Top Items"].insert(0, "Rank", range(1, len(self._preview_dfs["Top Items"]) + 1))
                except Exception as e:  # NAMA RESTO/ANOMALY STATUS hilang → fallback
                    self.log(f"⚠ Gagal membangun sheet 'Top Items': {e}")
                    self._preview_dfs["Top Items"] = pd.DataFrame(columns=_TI_COLS)
            else:
                self._preview_dfs["Top Items"] = pd.DataFrame(columns=_TI_COLS)
            # Pareto
            _PA_COLS = ["KETERANGAN", "Total_Waste", "Jumlah_Barang",
                        "Persentase", "Cumulative"]
            if "KETERANGAN" in df.columns:
                try:
                    pareto_df = (
                        df.groupby("KETERANGAN", dropna=False).agg(
                            Total_Waste=("TOTAL", "sum"),
                            Jumlah_Barang=("NAMA BARANG", "size"),
                        ).reset_index().sort_values("Total_Waste", ascending=False)
                    )
                    grand = pareto_df["Total_Waste"].sum()
                    if grand and grand > 0:
                        pareto_df["Persentase"] = (pareto_df["Total_Waste"] / grand) * 100
                        pareto_df["Cumulative"] = pareto_df["Persentase"].cumsum()
                    else:
                        pareto_df["Persentase"] = 0
                        pareto_df["Cumulative"] = 0
                    self._preview_dfs["Pareto Alasan"] = pareto_df
                except Exception as e:
                    self.log(f"⚠ Gagal membangun sheet 'Pareto Alasan': {e}")
                    self._preview_dfs["Pareto Alasan"] = pd.DataFrame(columns=_PA_COLS)
            else:
                self._preview_dfs["Pareto Alasan"] = pd.DataFrame(columns=_PA_COLS)

        # Ringkasan (murah, tekstual) — render langsung
        self._update_summary_tab(summary)
        # KPI cards (murah) — render langsung
        if df is not None and not df.empty:
            self._update_kpi_cards(df, summary)
            # Reset filter TANPA render (H5) — render ditangani lazy per-tab
            self._reset_filters_state()

        # H2: lazy per-tab render — tandai SEMUA tab dirty, render HANYA tab
        # yang sedang dipilih. Tab lain render saat pertama kali dikunjungi
        # (dulu: ~18 figure di-render sinkron sekaligus → UI nge-freek lama).
        self._mark_all_tabs_dirty()
        self._tab_render_dirty["ringkasan"] = False  # sudah dirender di atas
        cur = self._current_tab_key()
        if cur and cur != "ringkasan":
            err = self._render_tab(cur)
            self._tab_render_dirty[cur] = False
            if err:
                self.log(f"⚠ Render tab '{cur}' gagal: {err}")

        messagebox.showinfo(
            "Pipeline Selesai",
            f"Pipeline selesai!\n\n"
            f"Total baris diproses: {summary.get('total_rows', 0)}\n"
            f"Anomali prioritas: {summary.get('prioritas_count', 0)}\n"
            f"Potensi anomali: {summary.get('potensi_count', 0)}\n"
            f"Perlu review: {summary.get('review_count', 0)}\n\n"
            f"Data siap ditampilkan in-memory (tanpa export Excel).\n"  # L6
            f"Buka tab 'Dashboard' untuk analisa drill-down.",
        )

    def _on_pipeline_error(self, err: str, tb: str | None = None):
        """C1: selalu pulihkan Run button; traceback lengkap ke log popup saja.
        M21: error pembatalan user ditampilkan sebagai info, bukan error."""
        self._finish_run_state()
        cancelled = (err == "Run dibatalkan pengguna")
        if cancelled:
            self._set_status("⏹ Run dibatalkan pengguna", "error")
        else:
            self._set_status(f"ERROR: {err}", "error")
        self.log(f"!!! ERROR: {err}")
        if tb:
            self.log(tb)  # detail traceback di popup log — bukan messagebox
        if cancelled:
            self.log("=== Run dibatalkan — hasil tidak dirender ===")
            messagebox.showinfo("Run Dibatalkan", "Run dibatalkan oleh pengguna — hasil tidak dirender.")
        else:
            messagebox.showerror("Pipeline Error", err)

    # --------------------------------------------------------
    # H6: EXPORT LAPORAN EXCEL (background thread + ui_queue)
    # --------------------------------------------------------
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

    def _set_status(self, msg: str, kind: str = "running"):
        colors = {"running": "#0369a1", "done": "#16a34a", "error": "#dc2626"}
        self.lbl_status.configure(fg=colors.get(kind, C_TEXT_MUTED))
        self.lbl_status.configure(text=msg)
        self.lbl_footer.configure(text=f"{msg[:80]}  •  v{APP_VERSION}")

    # --------------------------------------------------------
    # LOAD PREVIEW DATA — REMOVED in v2.2.0 (data flow in-memory dari pipeline summary)
    # ============================================================


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    app = WasteAnomalyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
