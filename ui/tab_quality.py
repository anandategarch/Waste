"""Tab Data Quality (v2.5.0 P6): pemeriksaan kualitas data otomatis —
satuan tersembunyi (NBSP), varian ejaan SOURCE DATA, fragmentasi
KETERANGAN, waste tanpa BOM, grup terpecah antar SOURCE DATA.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from waste_anomaly import data_quality as wa_dq
import tkinter as tk
from tkinter import ttk


class QualityTabMixin:
    """Tab Data Quality: hasil run_checks(data_quality) dalam tabel."""

    # Ikon severity — modul inti bebas emoji; UI yang menambahkan.
    SEV_ICON = {"error": "❌", "warning": "⚠", "info": "ℹ"}

    def _build_quality_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # Card 1: header
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="🧹 Data Quality — Pemeriksaan Otomatis",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1,
                 text="Isi data yang membuat analisa bocor diam-diam: satuan duplikat karena spasi tersembunyi, "
                      "SOURCE DATA beda kapital yang sama artinya (memecah peer group), KETERANGAN terfragmentasi, "
                      "waste tanpa BOM (tak terlihat sinyal BOM/rate), grup resto×item terpecah antar source "
                      "(me-dilute sinyal spike).",
                 font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD, wraplength=980,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 4))
        self.lbl_quality_summary = tk.Label(c1, text="(belum ada data — run pipeline dulu)",
                                            font=F_BODY, fg=C_HEADER, bg=C_CARD,
                                            anchor="w", justify="left")
        self.lbl_quality_summary.pack(fill="x", padx=16, pady=(0, 4))
        btn_frame = tk.Frame(c1, bg=C_CARD)
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btn_frame, text="⟳ Refresh", command=self._render_quality).pack(side="left", padx=4)

        # Card 2: tabel temuan
        c2 = tk.Frame(parent, bg=C_CARD, relief="flat",
                      highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(1, weight=1)
        tk.Label(c2, text="📋 Temuan (urut: error → warning → info)",
                 font=F_CARD, fg=C_HEADER, bg=C_CARD).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        tree_wrap = tk.Frame(c2, bg=C_CARD)
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.tree_quality = ttk.Treeview(tree_wrap, show="headings", height=12)
        sb_y = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_quality.yview)
        sb_x = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree_quality.xview)
        self.tree_quality.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree_quality.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        # Tag warna per severity
        self.tree_quality.tag_configure("error", background="#fef2f2", foreground="#dc2626")
        self.tree_quality.tag_configure("warning", background="#fff7ed", foreground="#ea580c")
        self.tree_quality.tag_configure("info", background="#f0fdf4", foreground="#16a34a")

    # ------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------

    def _render_quality(self):
        """Jalankan semua pemeriksaan pada Detail df terakhir → tabel.

        v2.5.1 (DD-H1 amplifier): seluruh render dibungkus try/except —
        jalur ini juga dipanggil tombol ⟳ Refresh (callback langsung,
        tanpa wrapper _render_tab); exception kini meninggalkan pesan
        error di tabel, bukan tab kosong + log global saja."""
        try:
            self._render_quality_inner()
        except Exception as e:  # noqa: BLE001
            from .shared import _LOGGER
            _LOGGER.warning("Data Quality render gagal: %s", e, exc_info=True)
            self.log(f"⚠ Data Quality gagal: {e}")
            try:
                tree = self.tree_quality
                tree.delete(*tree.get_children(""))
                tree["columns"] = ["info"]
                tree.heading("info", text="info")
                tree.insert("", "end", values=[f"(gagal render: {e})"])
                self.lbl_quality_summary.configure(
                    text=f"⚠ Gagal render — cek log (logs/ folder)")
            except Exception:  # noqa: BLE001 — widget mungkin belum ada
                pass

    def _render_quality_inner(self):
        df = self._preview_dfs.get("Detail")
        tree = self.tree_quality
        tree.delete(*tree.get_children(""))

        if df is None or df.empty:
            self.lbl_quality_summary.configure(
                text="(belum ada data — run pipeline dulu)")
            tree["columns"] = ["info"]
            tree.heading("info", text="info")
            tree.insert("", "end", values=["(belum ada data — run pipeline dulu)"])
            return

        results = wa_dq.run_checks(df, key_akhir=self._last_key_akhir)

        cols = ["Severity", "Kode", "Judul", "Jumlah", "Detail", "Contoh"]
        tree["columns"] = cols
        widths = {"Severity": 80, "Kode": 150, "Judul": 220, "Jumlah": 70,
                  "Detail": 420, "Contoh": 320}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 100),
                        anchor="w" if c not in ("Jumlah",) else "e")

        n_err = sum(1 for r in results if r.severity == "error")
        n_warn = sum(1 for r in results if r.severity == "warning")
        n_info = sum(1 for r in results if r.severity == "info")

        for r in results:
            icon = self.SEV_ICON.get(r.severity, "•")
            sample = "\n".join(r.sample) if r.sample else ""
            tree.insert("", "end", values=(
                f"{icon} {r.severity}", r.code, r.title, r.count,
                r.detail, sample,
            ), tags=(r.severity,))

        self.lbl_quality_summary.configure(
            text=(
                f"Temuan: {n_err} error • {n_warn} warning • {n_info} info "
                f"(dari {len(results)} pemeriksaan). "
                "Warning tidak memblokir analisa — tapi memengaruhi cakupan peer/BOM. "
                "Perbaiki di file sumber (Excel) lalu run ulang pipeline."
            )
        )
        self.log(f"[data-quality] {n_err} error, {n_warn} warning, {n_info} info")


# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
