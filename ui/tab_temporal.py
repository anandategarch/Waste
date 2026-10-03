"""Tab Temporal (v2.5.0 P1): analisa dimensi waktu — waste per hari,
pola kelas hari (mod 7), heatmap alasan×hari, rasio peak per alasan.

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
from waste_anomaly import charts as wa_charts
from waste_anomaly import temporal as wa_temporal
import tkinter as tk
from tkinter import ttk


class TemporalTabMixin:
    """Tab Temporal: analisa per hari / pola mingguan (P1 v2.5.0)."""

    def _build_temporal_tab(self, parent):
        """Layout scrollable: info efek hari + 3 chart + tabel rasio alasan."""
        inner = self._make_scrollable(parent, bg=C_BG)
        inner.columnconfigure(0, weight=3, uniform="tmp")
        inner.columnconfigure(1, weight=2, uniform="tmp")

        # Header + info efek peak
        hdr = tk.Frame(inner, bg=C_CARD, relief="flat",
                       highlightbackground=C_BORDER, highlightthickness=1)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        tk.Label(hdr, text="📅 Temporal — Waste per Hari & Pola Mingguan",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_temporal_info = tk.Label(
            hdr, text="(belum ada data — run pipeline dulu)",
            font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, anchor="w", justify="left",
        )
        self.lbl_temporal_info.pack(fill="x", padx=16, pady=(0, 4))
        btn_frame = tk.Frame(hdr, bg=C_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="⟳ Refresh", command=self._render_temporal).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🖼 Export PNG…",
                   command=self._export_temporal_charts).pack(side="left", padx=4)

        # Chart frames
        self._temporal_chart_frames = []
        for row, col, label in [
            (1, 0, "waste_per_day"),      # full width (colspan 2)
            (2, 0, "weekday_effect"),
            (3, 0, "reason_day_heatmap"), # full width (colspan 2)
        ]:
            f = tk.Frame(inner, bg=C_CARD, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
            if label in ("waste_per_day", "reason_day_heatmap"):
                f.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
            else:
                f.grid(row=row, column=0, sticky="nsew", padx=8, pady=4)
            f.columnconfigure(0, weight=1)
            f.rowconfigure(1, weight=1)
            self._temporal_chart_frames.append((label, f))
            tk.Label(f, text="🕒\n\nRun pipeline untuk\nlihat chart",
                     font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD, justify="center").grid(
                row=0, column=0, sticky="nsew", padx=20, pady=20)

        # Tabel rasio peak per alasan (kanan chart weekday_effect)
        table_frame = tk.Frame(inner, bg=C_CARD, relief="flat",
                               highlightbackground=C_BORDER, highlightthickness=1)
        table_frame.grid(row=2, column=1, sticky="nsew", padx=8, pady=4)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=1)
        tk.Label(table_frame, text="📋 Alasan × Efek Hari Peak (klik header sort ▼/▲)",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_temporal_count = tk.Label(table_frame, text="(belum ada data)",
                                           font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD)
        self.lbl_temporal_count.pack(anchor="w", padx=16)
        tree_wrap = tk.Frame(table_frame, bg=C_CARD)
        tree_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.tree_temporal = ttk.Treeview(tree_wrap, show="headings", height=9)
        sb_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_temporal.yview)
        self.tree_temporal.configure(yscrollcommand=sb_y.set)
        self.tree_temporal.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")

        self._temporal_canvases: list = []

    # ------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------

    def _render_temporal(self):
        """Render semua chart + tabel temporal dari Detail df terakhir."""
        df = self._preview_dfs.get("Detail")
        key_akhir = self._last_key_akhir

        # H3: dispose figure lama dulu (leak fix) — registry (key, fig, canvas)
        self._dispose_chart_registry(self._temporal_canvases)
        self._temporal_canvases = []
        for _label, f in self._temporal_chart_frames:
            for c in f.winfo_children():
                c.destroy()

        if df is None or df.empty:
            self.lbl_temporal_info.configure(
                text="(belum ada data — run pipeline dulu)")
            for _label, f in self._temporal_chart_frames:
                tk.Label(f, text="(belum ada data — run pipeline dulu)",
                         font=F_BODY, fg=C_TEXT_MUTED, bg=C_CARD,
                         justify="center").grid(row=0, column=0, sticky="nsew",
                                                padx=20, pady=20)
            self._render_temporal_table(None)
            return

        # Info efek hari
        # v2.5.1 (TE-M1): label netral + catatan asumsi — data hanya punya
        # kolom hari '1'..'31' (tanggal), BUKAN hari-minggu kalender.
        # Kelas mod 7 ≡ {5,6} memang spike (+35% di data sampel), tapi
        # menyebutnya 'weekend' mengasumsikan posisi kalender hari-1;
        # bila asumsi salah, insight = pasangan hari bersebelahan lain.
        effect = wa_temporal.weekday_effect(df, key_akhir=key_akhir)
        peak = effect.get("peak_classes")
        if peak:
            days = wa_temporal.waste_per_day(df, key_akhir=key_akhir)
            days_str = ", ".join(
                str(int(d)) for d in days["day"] if int(d) % 7 in peak
            )
            ratio = effect.get("ratio")
            ratio_txt = f"+{(ratio - 1) * 100:.0f}%" if ratio and ratio == ratio else "?"
            self.lbl_temporal_info.configure(
                text=(
                    f"Kelas hari peak: {peak[0]} & {peak[1]} (hari {days_str}) — "
                    f"rata-rata waste per baris aktif {ratio_txt} lebih tinggi "
                    f"({effect.get('peak_mean', 0):.1f} vs {effect.get('offpeak_mean', 0):.1f}). "
                    f"Bar merah di chart = hari peak. Catatan: kelas hari = "
                    f"tanggal % 7, BUKAN hari-minggu kalender (tanggal-1 di "
                    f"bulan mana tidak diketahui dari data) — 'pasangan hari "
                    f"bersebelahan' adalah bacaan aman, 'weekend' butuh "
                    f"konfirmasi kalender."
                )
            )
        else:
            self.lbl_temporal_info.configure(
                text="Tidak terdeteksi pola hari-minggu yang jelas pada periode ini.")

        builders = [
            ("waste_per_day", lambda: wa_charts.chart_waste_per_day(df, key_akhir=key_akhir)),
            ("weekday_effect", lambda: wa_charts.chart_weekday_effect(df, key_akhir=key_akhir)),
            ("reason_day_heatmap", lambda: wa_charts.chart_reason_day_heatmap(df, key_akhir=key_akhir)),
        ]
        for (label, f), (_name, builder) in zip(self._temporal_chart_frames, builders):
            try:
                fig = builder()
                canvas = wa_charts.embed_figure(f, fig)
                canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
                self._temporal_canvases.append((label, fig, canvas))
            except Exception as e:  # render satu chart ≠ jatuhkan tab
                tk.Label(f, text=f"Gagal render:\n{e}", font=F_BODY,
                         fg="#dc2626", bg=C_CARD, justify="left").grid(
                    row=0, column=0, sticky="nsew", padx=8, pady=8)
                self.log(f"⚠ Temporal chart '{label}' gagal: {e}")

        # v2.5.1 (DD-H1 amplifier): analisa non-chart diberi isolasi ringan
        # — modul temporal berkontrak 'tidak pernah raise', tapi kontrak
        # itu tidak terkunci test untuk SEMUA jalur; tabel rasio jangan
        # ikut mati bila analisa gagal.
        try:
            ratio_df = wa_temporal.reason_weekday_ratio(df, key_akhir=key_akhir)
        except Exception as e:  # noqa: BLE001
            self.log(f"⚠ Temporal rasio alasan gagal: {e}")
            ratio_df = None
        self._render_temporal_table(ratio_df)

    def _render_temporal_table(self, ratio_df):
        """Tabel alasan × efek peak (M24/M5 helper)."""
        tree = self.tree_temporal
        tree.delete(*tree.get_children(""))
        if ratio_df is None or ratio_df.empty:
            self.lbl_temporal_count.configure(text="(tidak ada data)")
            return
        self._temporal_ratio_df = ratio_df
        df = self._apply_tree_sort_state(ratio_df, tree)
        self._populate_tree(
            tree, df, list(df.columns), width=90, ndigits=2,
            get_df=lambda: self._temporal_ratio_df,
            render_fn=lambda d: self._render_temporal_table(d),
        )
        count = len(df)
        self.lbl_temporal_count.configure(
            text=(
                f"{count} alasan • ratio > 1 = alasan naik di hari peak "
                "• kategori < 30 entri aktif disembunyikan (rasio sampel-"
                "kecil = artefak — lihat tab Data Quality)"
            )
        )

    def _export_temporal_charts(self):
        """M24: export PNG via helper shared."""
        if not self._temporal_canvases:
            from tkinter import messagebox
            messagebox.showinfo("Export", "Belum ada chart. Refresh dulu.")
            return
        self._export_figures_png(self._temporal_canvases, lambda key: f"temporal_{key}")


# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
