"""Infrastruktur app: styling, fonts, queue log, tab scaffolding.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import APP_TITLE
from .shared import APP_VERSION
from .shared import C_BG
from .shared import C_CARD
from .shared import C_FOOTER
from .shared import C_HEADER
from .shared import C_TEXT_MAIN
from .shared import C_TEXT_MUTED
from .shared import FONT_NAME
from .shared import app_dir
from .shared import bundle_res_dir
from .shared import F_APP_TITLE
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from pathlib import Path
from .widgets import SimpleLogPopup
from .shared import _LOGGER
from .shared import _pick_font
from datetime import datetime
from waste_anomaly.charts import dispose_figure
from waste_anomaly.utils import load_config
from tkinter import messagebox
import os
import pandas as pd
import queue
from .shared import rebind_fonts
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


class AppBase:
    """Infrastruktur app: styling, fonts, queue log, tab scaffolding."""

    def _init_fonts(self):
        """M17: probe font sistem SEBELUM widget dibangun.

        v2.4.0: nilai font di-rebind via shared.rebind_fonts() — registry
        mem-propagasi ke SEMUA modul mixin (dulu pola `global` bekerja karena
        semua kode ada di satu file god-object).
        """
        font_name = _pick_font(
            ["Segoe UI", "Tahoma", "DejaVu Sans", "Helvetica"], "Segoe UI"
        )
        mono_name = _pick_font(
            ["Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New"],
            "Consolas",
        )
        rebind_fonts(
            FONT_NAME=font_name,
            MONO_NAME=mono_name,
            F_APP_TITLE=(font_name, 14, "bold"),
            F_CARD=(font_name, 10, "bold"),
            F_BODY=(font_name, 9),
            F_HINT=(font_name, 8),
            F_LOG=(mono_name, 9),
            F_KPI_NUM=(font_name, 18, "bold"),
            F_KPI_LABEL=(font_name, 8),
        )

    def __init__(self):
        super().__init__()
        self._init_fonts()  # M17: probe font sistem SEBELUM widget dibangun
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        # L19 (v2.4.0): ikon aplikasi — dulu window pakai ikon default Tk/Tcl.
        # v2.4.1: frozen exe → assets di-bundle di _MEIPASS (bundle_res_dir),
        # dev → repo root (app_dir). Cek keduanya supaya jalan di dua mode.
        try:
            from tkinter import PhotoImage as _PhotoImage
            for _icon_path in (bundle_res_dir() / "assets" / "app_icon_64.png",
                               app_dir() / "assets" / "app_icon_64.png"):
                if _icon_path.exists():
                    self._app_icon = _PhotoImage(file=str(_icon_path))
                    self.iconphoto(True, self._app_icon)
                    break
        except Exception:
            _LOGGER.debug("Ikon aplikasi gagal dimuat (lanjut tanpa ikon)", exc_info=True)
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


    def _build_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            _LOGGER.debug("Suppressed: Exception", exc_info=True)
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
                            _LOGGER.debug("Suppressed: Exception", exc_info=True)
            except Exception:
                _LOGGER.debug("Suppressed: Exception", exc_info=True)
            try:
                if canvas is not None and canvas.get_tk_widget().winfo_exists():
                    canvas.get_tk_widget().destroy()
            except Exception:
                _LOGGER.debug("Suppressed: Exception", exc_info=True)
            dispose_figure(fig)


    def _build_header(self):
        hdr = tk.Frame(self, bg=C_HEADER, height=50)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        lbl = tk.Label(hdr, text=f"  📊  {APP_TITLE}", font=F_APP_TITLE, fg="white", bg=C_HEADER)
        lbl.pack(side="left", padx=16, pady=10)
        sub = tk.Label(hdr, text=f"v{APP_VERSION}  •  Replika Power Query M code  •  12 sinyal anomali + money view + drill-down",
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


    def _current_tab_key(self) -> str:
        """Key tab yang sedang dipilih ('' bila tidak dikenal)."""
        try:
            sel = self.notebook.select()
            return self._tab_key_by_widget.get(str(sel), "")
        except Exception:
            return ""


    def _mark_all_tabs_dirty(self):
        """Tandai semua tab data-dependent perlu render saat dikunjungi."""
        for key in ("dashboard", "temporal", "money", "compare", "quadrant",
                    "rate_league", "hasil", "visualisasi", "quality",
                    "period", "ringkasan"):
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
            elif key == "temporal":
                self._render_temporal()
            elif key == "money":
                self._render_money()
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
            elif key == "quality":
                self._render_quality()
            elif key == "period":
                # P9: tabel period hanya berubah saat user klik Bandingkan;
                # dirty-render tinggal menampilkan hasil tersimpan.
                self._render_period_tables()
            elif key == "ringkasan":
                if self.last_summary:
                    self._update_summary_tab(self.last_summary)
            return None
        except Exception as e:  # render satu tab tidak boleh menjatuhkan app
            return str(e)


    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook = nb

        # Tab 1: Dashboard (PRO)
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="📊 Dashboard")
        self._build_dashboard_tab(tab1)

        # Tab 2: Temporal (NEW v2.5.0 — P1 analisa hari/weekday)
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="📅 Temporal")
        self._build_temporal_tab(tab2)

        # Tab 3: Money View (NEW v2.5.0 — P2/P4/P5 prioritas magnitude)
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="💰 Money View")
        self._build_money_tab(tab3)

        # Tab 4: Compare Cabang (NEW v2.1)
        tab4 = ttk.Frame(nb)
        nb.add(tab4, text="⚖ Compare Cabang")
        self._build_compare_tab(tab4)

        # Tab 5: Quadrant Analysis (NEW v2.3)
        tab5 = ttk.Frame(nb)
        nb.add(tab5, text="🎯 Quadrant")
        self._build_quadrant_tab(tab5)

        # Tab 6: Rate League (NEW v2.3)
        tab6 = ttk.Frame(nb)
        nb.add(tab6, text="🏆 Rate League")
        self._build_rate_league_tab(tab6)

        # Tab 7: Hasil
        tab7 = ttk.Frame(nb)
        nb.add(tab7, text="📋 Hasil")
        self._build_result_tab(tab7)

        # Tab 8: Visualisasi (12 chart gallery)
        tab8 = ttk.Frame(nb)
        nb.add(tab8, text="📈 Visualisasi")
        self._build_viz_tab(tab8)

        # Tab 9: Data Quality (NEW v2.5.0 — P6)
        tab9 = ttk.Frame(nb)
        nb.add(tab9, text="🧹 Data Quality")
        self._build_quality_tab(tab9)

        # Tab 10: Compare Periode (NEW v2.5.0 — P9)
        tab10 = ttk.Frame(nb)
        nb.add(tab10, text="🔀 Compare Periode")
        self._build_period_tab(tab10)

        # Tab 11: Ringkasan
        tab11 = ttk.Frame(nb)
        nb.add(tab11, text="🗂 Ringkasan")
        self._build_summary_tab(tab11)

        # Tab 12: Run Pipeline
        tab12 = ttk.Frame(nb)
        nb.add(tab12, text="▶ Run Pipeline")
        self._build_run_tab(tab12)

        # Tab 13: Konfigurasi
        tab13 = ttk.Frame(nb)
        nb.add(tab13, text="⚙ Konfigurasi")
        self._build_config_tab(tab13)

        # Tab 14: Bantuan
        tab14 = ttk.Frame(nb)
        nb.add(tab14, text="❓ Bantuan")
        self._build_help_tab(tab14)

        # H2: map widget-path tab → key (untuk lazy render via <<NotebookTabChanged>>)
        for _tab, _key in [
            (tab1, "dashboard"), (tab2, "temporal"), (tab3, "money"),
            (tab4, "compare"), (tab5, "quadrant"),
            (tab6, "rate_league"), (tab7, "hasil"), (tab8, "visualisasi"),
            (tab9, "quality"), (tab10, "period"),
            (tab11, "ringkasan"),
        ]:
            self._tab_key_by_widget[str(_tab)] = _key
        # H2: render tab saat pertama kali dikunjungi bila dirty
        nb.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)


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


    def _set_status(self, msg: str, kind: str = "running"):
        colors = {"running": "#0369a1", "done": "#16a34a", "error": "#dc2626"}
        self.lbl_status.configure(fg=colors.get(kind, C_TEXT_MUTED))
        self.lbl_status.configure(text=msg)
        self.lbl_footer.configure(text=f"{msg[:80]}  •  v{APP_VERSION}")


    @staticmethod
    def _winfo_alive(w) -> bool:
        try:
            return bool(w is not None and w.winfo_exists())
        except tk.TclError:
            return False


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
            _LOGGER.debug("Suppressed: window sudah di-destroy (double event)", exc_info=True)


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
            _LOGGER.debug("Suppressed: Exception", exc_info=True)


    def _open_data_folder(self):
        # v2.4.1: app_dir() dinamis — dev: repo root; exe: folder exe
        # (dulu APP_DIR konstanta _MEIPASS → folder sample dibuat di temp dir).
        data_dir = app_dir() / "data"
        data_dir.mkdir(exist_ok=True)
        self._open_path_in_explorer(data_dir)


    @staticmethod
    def _sanitize_filename(name) -> str:
        """L7: bersihkan nama file — karakter ilegal Windows (\\ : ? * " < > |)
        + separator / dan spasi, supaya file PNG aman lintas OS."""
        name = str(name)
        for ch in '\\/:?*"<>|':
            name = name.replace(ch, "-")
        name = name.replace(" ", "_").replace("×", "x")
        return name or "chart"


    @staticmethod
    def _format_cell(v, ndigits: int = 3):
        """M24: format satu nilai sel (dulu loop copy-paste 4×).

        None/NaN-float → ""; float → dibulatkan lalu diformat Indonesia
        (v2.5.1 / IN-L1: ribuan '.', desimal ',' — sebelumnya raw float
        '299855.0' bersebelahan dengan '9.333.117,5' dari Data Quality).
        Sort tabel tetap aman: sorting memakai df mentah via
        _sort_df_for_treeview, bukan teks sel.
        """
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, float):
            from .shared import fmt_id
            if v.is_integer() and abs(v) < 1e15:
                return fmt_id(v, 0)
            return fmt_id(v, ndigits)
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
                _LOGGER.debug("Suppressed: tk.TclError", exc_info=True)


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


    def _on_accel_focus_search(self, event=None):
        """L11: Ctrl+F → pindah ke tab Dashboard + fokus kotak Cari."""
        try:
            self.notebook.select(0)
        except Exception:
            _LOGGER.debug("Suppressed: Exception", exc_info=True)
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



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
