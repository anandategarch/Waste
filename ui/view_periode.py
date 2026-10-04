"""view_periode.py — view 'Banding Periode': run saat ini vs workbook lain (P9).

Workbook B dijalankan di background (key_akhir otomatis = hari aktif terbesar),
lalu dibandingkan per cabang/item dengan normalisasi panjang periode
(waste/hari + kolom 'Hari Data' + caveat beda panjang).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, DataTable, WLabel
from .workers import PeriodWorker

_PAGES = [
    ("summary", "📊 Ringkasan"),
    ("per_jenis", "🧾 Per JENIS"),
    ("branch", "🏬 Cabang Mover"),
    ("items", "📦 Item Mover"),
    ("new_items", "🆕 Item Baru"),
    ("gone_items", "📉 Item Hilang"),
]

# key dict result compare_periods → (df, label)
_RESULT_KEYS = {
    "summary": "summary",
    "per_jenis": "per_jenis",
    "branch": "branch_summary",
    "items": "item_summary",
    "new_items": "new_items",
    "gone_items": "gone_items",
}


class PeriodeView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: PeriodWorker | None = None
        self._running = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("🔀 Banding Periode — Run Saat Ini vs Workbook Lain", card)
        ttl.setObjectName("cardTitle")
        cl.addWidget(ttl)
        hint = WLabel(
            "Pilih workbook periode pembanding (mis. bulan lalu). Pipeline periode B dijalankan "
            "di background dengan key_akhir otomatis (hari aktif terbesar), lalu dibandingkan "
            "per cabang/item — termasuk normalisasi waste/hari bila panjang periode berbeda.", card)
        hint.setObjectName("hint")
        cl.addWidget(hint)
        row = QWidget(card)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(WLabel("Periode A (saat ini):", row))
        self._lbl_a = WLabel("(belum ada run)", row)
        self._lbl_a.setStyleSheet("font-weight:600;")
        rl.addWidget(self._lbl_a)
        rl.addWidget(WLabel("Periode B:", row))
        self._ent_b = QLineEdit(row)
        self._ent_b.setPlaceholderText("Pilih workbook periode pembanding…")
        rl.addWidget(self._ent_b, 1)
        b_browse = QPushButton("Browse…", row)
        b_browse.clicked.connect(self._browse)
        rl.addWidget(b_browse)
        self._btn_run = QPushButton("🔀 Bandingkan", row)
        self._btn_run.setObjectName("accent")
        self._btn_run.clicked.connect(self._run_compare)
        rl.addWidget(self._btn_run)
        cl.addWidget(row)
        self._lbl_status = WLabel("Siap.", card)
        self._lbl_status.setObjectName("hint")
        cl.addWidget(self._lbl_status)
        lay.addWidget(card)

        self._tabs = QTabWidget(self)
        self._tables: dict[str, DataTable] = {}
        for key, title in _PAGES:
            table = DataTable()
            self._tables[key] = table
            page = Card()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(12, 10, 12, 10)
            pl.setSpacing(6)
            pl.addWidget(table, 1)
            self._tabs.addTab(page, title)
        lay.addWidget(self._tabs, 1)

        ctx.data_ready.connect(self._on_data_ready)

    def _on_data_ready(self) -> None:
        if self._ctx.df is not None:
            self._lbl_a.setText(
                f"{fmt_run_label(self._ctx.summary, self._ctx.key_akhir)}")

    def refresh(self) -> None:
        """Kontrak lazy-render: perbarui label periode A dari state."""
        self._on_data_ready()

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka → segarkan label periode A."""
        self._on_data_ready()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih Workbook Periode B", str(Path.home() / "Documents"),
            "Excel files (*.xlsx *.xlsm *.xls);;All files (*.*)")
        if path:
            self._ent_b.setText(path)

    def _run_compare(self) -> None:
        if self._running:
            return
        if self._ctx.df is None:
            QMessageBox.information(self, "Banding Periode",
                                    "Jalankan pipeline periode A dulu (tab Pipeline).")
            return
        wb_b = self._ent_b.text().strip()
        if not wb_b or not Path(wb_b).exists():
            QMessageBox.critical(self, "Input Error",
                                 "Workbook periode B belum dipilih atau tidak ditemukan.")
            return
        self._running = True
        self._btn_run.setEnabled(False)
        self._lbl_status.setText("Menjalankan pipeline periode B di background…")
        self._ctx.set_status("Banding periode: pipeline B berjalan…", "running")
        self._worker = PeriodWorker(self._ctx.df, wb_b, self._ctx.key_akhir, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, result: dict) -> None:
        self._running = False
        self._btn_run.setEnabled(True)
        ka_b = result.get("key_akhir_b")
        self._lbl_status.setText(
            f"✓ Selesai — periode B: {result.get('workbook_b', '?')} "
            f"(key_akhir {ka_b}). Kolom 'Waste per Hari' & 'Hari Data' "
            f"menormalkan beda panjang periode.")
        self._ctx.set_status("✓ Banding periode selesai", "done")
        for key, df_key in _RESULT_KEYS.items():
            df = result.get(df_key)
            self._tables[key].set_dataframe(df if isinstance(df, pd.DataFrame) else None)

    def _on_failed(self, err: str, tb: str) -> None:
        self._running = False
        self._btn_run.setEnabled(True)
        self._lbl_status.setText(f"⚠ Gagal: {err}")
        self._ctx.set_status(f"⚠ Banding periode gagal: {err}", "error")
        if tb:
            self._ctx.log(f"⚠ Banding periode traceback: {tb}")
        QMessageBox.critical(self, "Banding Periode", err)


def fmt_run_label(summary: dict | None, key_akhir: int) -> str:
    label = "(run terakhir)"
    if summary:
        rows = summary.get("total_rows", 0)
        label = f"{fmt_id(rows)} baris • key_akhir {key_akhir}"
    return label
