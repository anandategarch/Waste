"""Tab 1 Dashboard: KPI, filter bar, chart interaktif, drill-down.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import CHIP_LABELS
from .shared import C_BG
from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_STATUS
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from .widgets import FilterChip
from .widgets import KPICard
from .shared import _LOGGER
from .shared import _apply_filters
from datetime import datetime
from tkinter import filedialog
from tkinter import messagebox
import pandas as pd
from tkinter import simpledialog
import tkinter as tk
from tkinter import ttk
from waste_anomaly import charts as wa_charts
from waste_anomaly import dashboard as wa_dash
from waste_anomaly import filters as wa_filters


class DashboardTabMixin:
    """Tab 1 Dashboard: KPI, filter bar, chart interaktif, drill-down."""

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
                _LOGGER.debug("Suppressed: Suppressed tk.TclError", exc_info=True)


    def _on_search_changed(self):
        """H1: debounce 300ms — tiap keystroke tidak re-render 3 chart + 500-row table."""
        if self._suppress_trace:
            return
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                _LOGGER.debug("Suppressed: Suppressed Exception", exc_info=True)
            self._search_after_id = None
        self._search_after_id = self.after(300, self._search_debounced)


    def _search_debounced(self):
        self._search_after_id = None
        self._apply_dashboard_filter()


    def _search_apply_now(self):
        """L11: Enter di kotak Cari → terapkan filter SEKARANG (bypass debounce)."""
        if self._suppress_trace:
            return "break"
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                _LOGGER.debug("Suppressed: Suppressed Exception", exc_info=True)
            self._search_after_id = None
        self._apply_dashboard_filter()
        return "break"


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



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
