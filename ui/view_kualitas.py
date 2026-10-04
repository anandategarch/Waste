"""view_kualitas.py — view 'Kualitas Data': apakah data bisa dipercaya? (P6).

Tabel temuan pemeriksaan (NBSP satuan, varian SOURCE, prefix KETERANGAN,
waste-tanpa-BOM, split-source, baris negatif) + tombol segarkan.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, DataTable, WLabel


class KualitasView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._dirty = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("Pemeriksaan Kualitas Data", card)
        ttl.setObjectName("cardTitle")
        cl.addWidget(ttl)
        hint = WLabel(
            "Temuan fragmentasi/inkonsistensi yang bisa membuat analisa menyesatkan "
            "(varian spasi tersembunyi, label kembar visual, waste tanpa BOM, dst.). "
            "Semua kolom bisa di-sort — penjelasan tiap temuan di kolom Detail, "
            "contoh baris terdampak di kolom Contoh.", card)
        hint.setObjectName("hint")
        cl.addWidget(hint)
        row = QWidget(card)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        self._btn_refresh = QPushButton("🔄 Segarkan Pemeriksaan", row)
        self._btn_refresh.clicked.connect(lambda: self.refresh())
        rl.addWidget(self._btn_refresh)
        self._lbl_count = WLabel("", row)
        self._lbl_count.setObjectName("hint")
        rl.addWidget(self._lbl_count, 1)
        cl.addWidget(row)
        self._table = DataTable(card)
        cl.addWidget(self._table, 1)
        lay.addWidget(card, 1)
        ctx.data_ready.connect(self._on_data_ready)
        # V26-M6: empty-state pra-run pertama (sejajar view chart lain)
        self._lbl_count.setText("Belum ada data — jalankan pipeline dulu.")

    def on_shown(self) -> None:
        if self._dirty:
            self.refresh()

    def _on_data_ready(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        self._dirty = False
        df = self._ctx.df
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_count.setText("Belum ada data — jalankan pipeline dulu.")
            return
        try:
            from waste_anomaly import data_quality as wa_dq
            import pandas as pd
            checks = wa_dq.run_checks(df, key_akhir=self._ctx.key_akhir)
            if not checks:
                self._table.set_dataframe(None)
                self._lbl_count.setText("0 temuan — data bersih 🎉")
                return
            out = pd.DataFrame([
                {
                    "Severity": r.severity, "Kode": r.code, "Judul": r.title,
                    "Jumlah": r.count, "Detail": r.detail,
                    "Contoh": " | ".join(r.sample),
                }
                for r in checks
            ])
            self._table.set_dataframe(out)
            self._lbl_count.setText(
                f"{fmt_id(len(out))} temuan — {fmt_id(int(out['Jumlah'].sum()))} baris terdampak")
        except Exception as e:  # noqa: BLE001
            self._table.set_dataframe(None)
            self._lbl_count.setText(f"Gagal menjalankan pemeriksaan: {e}")
