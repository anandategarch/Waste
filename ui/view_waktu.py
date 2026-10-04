"""view_waktu.py — view 'Waktu': pola temporal waste (P1 v2.5.0).

Chart: waste per hari, efek hari (mod-7), heatmap alasan×hari.
Tabel: waste per hari, pola mingguan, rasio peak-day per alasan.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, ChartCard, DataTable, WLabel, place_charts_responsive


class WaktuView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._dirty = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._split = QSplitter(Qt.Orientation.Vertical, self)
        lay.addWidget(self._split, 1)

        # ===== Chart (atas) =====
        charts_host = QWidget(self._split)
        chl = QVBoxLayout(charts_host)
        chl.setContentsMargins(0, 0, 0, 0)
        chl.setSpacing(8)
        ttl = WLabel("Pola Waktu — kapan waste terjadi?", charts_host)
        ttl.setObjectName("cardTitle")
        chl.addWidget(ttl)
        scroll = QScrollArea(charts_host)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        from PySide6.QtWidgets import QGridLayout
        self._chart_grid = QGridLayout(inner)
        self._chart_grid.setContentsMargins(0, 0, 0, 0)
        self._chart_grid.setSpacing(8)
        self._chart_grid.setColumnStretch(0, 1)
        self._chart_grid.setColumnStretch(1, 1)
        self._c_per_day = ChartCard("Waste per Hari")
        self._c_weekday = ChartCard("Efek Hari (kelas hari mod-7)")
        self._c_heatmap = ChartCard("Heatmap Alasan × Hari")
        scroll.setWidget(inner)
        scroll.setMinimumHeight(340)
        chl.addWidget(scroll)
        self._chart_scroll = scroll
        note = WLabel(
            "Catatan: kelas hari dihitung dari posisi hari mod-7 (asumsi hari-1 = kelas 0); "
            "hubungannya dengan Sabtu/Minggu kalender tergantung posisi hari pertama periode.", charts_host)
        note.setObjectName("hint")
        chl.addWidget(note)

        # ===== Tabel (bawah) =====
        table_host = QWidget(self._split)
        thl = QVBoxLayout(table_host)
        thl.setContentsMargins(0, 0, 0, 0)
        thl.setSpacing(8)
        self._tabs = QTabWidget(table_host)
        self._t_per_day = DataTable()
        self._tabs.addTab(self._make_page(self._t_per_day, "Agregat waste per hari (jumlah & tanggal)"), "Per Hari")
        self._t_weekday = DataTable()
        self._tabs.addTab(self._make_page(self._t_weekday, "Pola mingguan (kelas hari mod-7)"), "Pola Mingguan")
        self._t_ratio = DataTable()
        self._tabs.addTab(self._make_page(self._t_ratio, "Rasio peak-day per alasan (min 30 entri aktif — kategori kecil disembunyikan)"), "Rasio Alasan")
        thl.addWidget(self._tabs, 1)

        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        ctx.data_ready.connect(self._on_data_ready)

    def _make_page(self, table: DataTable, note: str) -> QWidget:
        page = Card()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(12, 10, 12, 10)
        pl.setSpacing(6)
        n = WLabel(note, page)
        n.setObjectName("hint")
        pl.addWidget(n)
        pl.addWidget(table, 1)
        return page

    def _replay_layout(self) -> None:
        w = max(self.width() - 24, 200)  # lebar view final saat resizeEvent
        place_charts_responsive(self._chart_grid, getattr(self, "_chart_entries", []), w)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Deferred: saat event ini tiba, layout anak belum dihitung ulang —
        # viewport masih berukuran LAMA → keputusan 1/2 kolom basi. Tunda
        # ke tick berikutnya (setelah layout pass) supaya lebar final.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._replay_layout)

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
            for c in (self._c_per_day, self._c_weekday, self._c_heatmap):
                c.set_message("(belum ada data — jalankan pipeline dulu)")
            for t in (self._t_per_day, self._t_weekday, self._t_ratio):
                t.set_dataframe(None)
            return
        ka = self._ctx.key_akhir
        from waste_anomaly import charts as wa_charts
        from waste_anomaly import temporal as wa_temporal
        figs: dict[str, object] = {}
        for key, card, fn in (
            ("per_day", self._c_per_day, lambda: wa_charts.chart_waste_per_day(df, key_akhir=ka)),
            ("weekday", self._c_weekday, lambda: wa_charts.chart_weekday_effect(df, key_akhir=ka)),
            ("heatmap", self._c_heatmap, lambda: wa_charts.chart_reason_day_heatmap(df, key_akhir=ka)),
        ):
            try:
                fig = fn()
                figs[key] = fig
                card.replace_fig(fig)
            except Exception as e:  # noqa: BLE001 — 1 chart ≠ jatuhkan view
                card.set_message(f"Gagal render:\n{e}", error=True)
        # Penempatan responsif (2 kolom ↔ 1 kolom bila sempit)
        self._chart_entries = [
            (self._c_per_day, figs.get("per_day")),
            (self._c_weekday, figs.get("weekday")),
            (self._c_heatmap, figs.get("heatmap")),
        ]
        self._replay_layout()
        for table, fn in (
            (self._t_per_day, lambda: wa_temporal.waste_per_day(df, key_akhir=ka)),
            (self._t_weekday, lambda: wa_temporal.weekday_pattern(df, key_akhir=ka)),
            (self._t_ratio, lambda: wa_temporal.reason_weekday_ratio(df, key_akhir=ka)),
        ):
            try:
                out = fn()
                table.set_dataframe(out if out is not None else None)
            except Exception as e:  # noqa: BLE001
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Tabel Waktu", f"Gagal membangun tabel:\n{e}")
                table.set_dataframe(None)
