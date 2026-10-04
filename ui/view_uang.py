"""view_uang.py — view 'Uang': di mana uang terbuang (P2 v2.5.0).

Chart: top baris waste terbesar (money top), Pareto item.
Tabel: Money View (top 100), benchmark item vs peer aktif, profil alasan.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .state import AppContext
from .widgets import Card, ChartCard, DataTable, WLabel, place_charts_responsive


class UangView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._dirty = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._split = QSplitter(Qt.Orientation.Vertical, self)
        lay.addWidget(self._split, 1)

        charts_host = QWidget(self._split)
        chl = QVBoxLayout(charts_host)
        chl.setContentsMargins(0, 0, 0, 0)
        chl.setSpacing(8)
        ttl = WLabel("Money View — baris & item waste terbesar (qty sebagai proksi nilai)", charts_host)
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
        self._c_money = ChartCard("Top Baris Waste Terbesar (satuan per bar)")
        self._c_pareto = ChartCard("Pareto Item (80/20)")
        scroll.setWidget(inner)
        scroll.setMinimumHeight(340)
        chl.addWidget(scroll)
        self._chart_scroll = scroll
        note = WLabel(
            "Catatan: agregat mencampur satuan (GR/PCS/PACK/…) — angka lintas satuan indikatif saja; "
            "satuan dominan tercantum di judul. Share% dihitung dari TOTAL seluruh baris.", charts_host)
        note.setObjectName("hint")
        chl.addWidget(note)

        table_host = QWidget(self._split)
        thl = QVBoxLayout(table_host)
        thl.setContentsMargins(0, 0, 0, 0)
        thl.setSpacing(8)
        self._tabs = QTabWidget(table_host)
        self._t_money = DataTable()
        self._tabs.addTab(self._page(self._t_money, "Top 100 baris waste terbesar + skor fokus (magnitude di-rank pada baris aktif TOTAL>0)"), "Money View")
        self._t_bench = DataTable()
        self._tabs.addTab(self._page(self._t_bench, "Benchmark item × cabang vs peer AKTIF (median hanya cabang ber-waste)"), "Benchmark Item")
        self._t_reason = DataTable()
        self._tabs.addTab(self._page(self._t_reason, "Profil alasan per cabang (pivot TOTAL per cabang × KETERANGAN)"), "Profil Alasan")
        thl.addWidget(self._tabs, 1)

        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        ctx.data_ready.connect(self._on_data_ready)

    def _page(self, table: DataTable, note: str) -> QWidget:
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
            for c in (self._c_money, self._c_pareto):
                c.set_message("(belum ada data — jalankan pipeline dulu)")
            for t in (self._t_money, self._t_bench, self._t_reason):
                t.set_dataframe(None)
            return
        from waste_anomaly import charts as wa_charts
        from waste_anomaly import priority as wa_priority
        figs: dict[str, object] = {}
        for key, card, fn in (
            ("money", self._c_money, lambda: wa_charts.chart_money_top(df, top_n=15)),
            ("pareto", self._c_pareto, lambda: wa_charts.chart_item_pareto(df, top_n=20)),
        ):
            try:
                fig = fn()
                figs[key] = fig
                card.replace_fig(fig)
            except Exception as e:  # noqa: BLE001
                card.set_message(f"Gagal render:\n{e}", error=True)
        self._chart_entries = [
            (self._c_money, figs.get("money")),
            (self._c_pareto, figs.get("pareto")),
        ]
        self._replay_layout()
        for table, fn in (
            (self._t_money, lambda: wa_priority.money_view(df, top_n=100)),
            (self._t_bench, lambda: wa_priority.benchmark_items(df)),
            (self._t_reason, lambda: wa_priority.reason_profile(df)),
        ):
            try:
                out = fn()
                table.set_dataframe(out if out is not None else None)
            except Exception as e:  # noqa: BLE001
                table.set_dataframe(None)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Tabel Uang", f"Gagal membangun tabel:\n{e}")
