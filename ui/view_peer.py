"""view_peer.py — view 'Peer': posisi cabang/item terhadap pembanding.

Isi (gabungan tab Quadrant + Rate League + Compare lama):
- Scatter kuadran (sistemik/musiman/lokal-kronis/insiden) + rate league
- Tabel benchmark SUSUT per cabang + share alasan per cabang (pilih cabang)
- Banding 2 cabang (A vs B) → 4 chart perbandingan
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .state import AppContext
from .widgets import Card, ChartCard, DataTable, WLabel, place_charts_responsive

# Pesan placeholder pra-run pertama (V26-M6)
_EMPTY_MSG = "Belum ada data — jalankan pipeline dulu (tab Pipeline)."


class PeerView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._dirty = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._split = QSplitter(Qt.Orientation.Vertical, self)
        lay.addWidget(self._split, 1)

        # ===== ATAS: kuadran + rate league =====
        top = QWidget(self._split)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        ttl = WLabel("Analisa Peer — seberapa sistemik waste cabang/item?", top)
        ttl.setObjectName("cardTitle")
        tl.addWidget(ttl)
        scroll = QScrollArea(top)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._chart_grid = QGridLayout(inner)
        self._chart_grid.setContentsMargins(0, 0, 0, 0)
        self._chart_grid.setSpacing(8)
        self._chart_grid.setColumnStretch(0, 1)
        self._chart_grid.setColumnStretch(1, 1)
        self._c_quadrant = ChartCard("Kuadran Anomali (prevalensi × persistensi)")
        self._c_rate = ChartCard("Rate League — waste/BOM per item")
        scroll.setWidget(inner)
        scroll.setMinimumHeight(400)
        tl.addWidget(scroll)

        # ===== TENGAH: banding 2 cabang =====
        mid = Card(self._split)
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(12, 10, 12, 10)
        ml.setSpacing(8)
        mttl = WLabel("Banding 2 Cabang (A vs B)", mid)
        mttl.setObjectName("cardTitle")
        ml.addWidget(mttl)
        mhint = WLabel("Pilih dua cabang lalu klik Bandingkan — 4 chart side-by-side.", mid)
        mhint.setObjectName("hint")
        ml.addWidget(mhint)
        row = QWidget(mid)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self._cb_a = QComboBox(row)
        self._cb_b = QComboBox(row)
        for cb in (self._cb_a, self._cb_b):
            cb.setMinimumWidth(220)
            rl.addWidget(cb)
        b_run = QPushButton("🔀 Bandingkan", row)
        b_run.setObjectName("accent")
        b_run.clicked.connect(self._render_compare)
        rl.addWidget(b_run)
        rl.addStretch(1)
        ml.addWidget(row)
        self._compare_host = QWidget(mid)
        self._compare_lay = QGridLayout(self._compare_host)
        self._compare_lay.setContentsMargins(0, 0, 0, 0)
        self._compare_lay.setSpacing(8)
        self._c_cmp: list[ChartCard] = []
        ml.addWidget(self._compare_host)

        # ===== BAWAH: tabel peer =====
        bottom = QWidget(self._split)
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        brow = QWidget(bottom)
        brl = QHBoxLayout(brow)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(8)
        bttl = WLabel("Tabel Peer", brow)
        bttl.setObjectName("cardTitle")
        brl.addWidget(bttl)
        brl.addWidget(WLabel("Cabang:", brow))
        self._cb_share = QComboBox(brow)
        self._cb_share.setMinimumWidth(220)
        self._cb_share.currentIndexChanged.connect(lambda _i: self._render_share())
        brl.addWidget(self._cb_share)
        bl.addWidget(brow)
        t_row = QWidget(bottom)
        trl = QHBoxLayout(t_row)
        trl.setContentsMargins(0, 0, 0, 0)
        trl.setSpacing(8)
        self._t_susut = DataTable()
        self._t_share = DataTable()
        for t in (self._t_susut, self._t_share):
            card = Card(t_row)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(6)
            t.setParent(card)
            cl.addWidget(t, 1)
            trl.addWidget(card)
        bl.addWidget(t_row, 1)

        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 1)
        self._split.setStretchFactor(2, 2)
        ctx.data_ready.connect(self._on_data_ready)

        # V26-M6: tempatkan kartu chart SEJAK KONSTRUKSI dengan pesan
        # placeholder — dulu kartu baru ber-parent saat render pertama sukses
        # → area view BLANK sebelum run pertama. refresh() mengganti alami.
        for c in (self._c_quadrant, self._c_rate):
            c.set_message(_EMPTY_MSG)
        self._chart_entries = [(self._c_quadrant, None), (self._c_rate, None)]
        self._replay_layout()

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
        # populate combo cabang (dari df penuh — tidak menyusut saat drill)
        if df is not None and "NAMA RESTO" in df.columns:
            names = sorted(df["NAMA RESTO"].dropna().astype(str).unique())
            for cb in (self._cb_a, self._cb_b, self._cb_share):
                cb.blockSignals(True)
                cb.clear()
                cb.addItem("(pilih cabang)")
                cb.addItems(names)
                cb.blockSignals(False)
        if df is None:
            for c in (self._c_quadrant, self._c_rate):
                c.set_message("(belum ada data — jalankan pipeline dulu)")
            self._t_susut.set_dataframe(None)
            self._t_share.set_dataframe(None)
            return
        from waste_anomaly import dashboard as wa_dash
        from waste_anomaly import priority as wa_priority
        figs: dict[str, object] = {}
        for key, card, fn in (
            ("quadrant", self._c_quadrant,
             lambda: wa_dash.chart_quadrant_scatter(df, key_akhir=self._ctx.key_akhir)),
            ("rate", self._c_rate,
             lambda: wa_dash.chart_rate_league(df, top_n=15)),
        ):
            try:
                fig = fn()
                figs[key] = fig
                card.replace_fig(fig)
            except Exception as e:  # noqa: BLE001
                card.set_message(f"Gagal render:\n{e}", error=True)
        # Penempatan responsif (kedua chart berdesain lebar → baris penuh)
        self._chart_entries = [
            (self._c_quadrant, figs.get("quadrant")),
            (self._c_rate, figs.get("rate")),
        ]
        self._replay_layout()
        try:
            self._t_susut.set_dataframe(wa_priority.susut_benchmark(df))
        except Exception as e:  # noqa: BLE001
            self._t_susut.set_dataframe(None)
        self._render_share()
        self._clear_compare()

    def _render_share(self) -> None:
        df = self._ctx.df
        if df is None:
            self._t_share.set_dataframe(None)
            return
        cabang = self._cb_share.currentText()
        if not cabang or cabang == "(pilih cabang)":
            self._t_share.set_dataframe(None)
            return
        try:
            from waste_anomaly import priority as wa_priority
            share = wa_priority.reason_share(df, cabang)
            import pandas as pd
            out = share.reset_index() if isinstance(share, pd.Series) else share
            self._t_share.set_dataframe(out if out is not None and len(out) else None)
        except Exception as e:  # noqa: BLE001
            self._t_share.set_dataframe(None)

    # ------------------------------------------------------------
    # COMPARE A/B
    # ------------------------------------------------------------
    def _clear_compare(self) -> None:
        for card in self._c_cmp:
            self._compare_lay.removeWidget(card)
            card.disconnect_figs()
            card.deleteLater()
        self._c_cmp = []

    def _render_compare(self) -> None:
        df = self._ctx.df
        if df is None:
            return
        a = self._cb_a.currentText()
        b = self._cb_b.currentText()
        if not a or a == "(pilih cabang)" or not b or b == "(pilih cabang)":
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Banding", "Pilih dua cabang (A dan B) dulu.")
            return
        self._clear_compare()
        from waste_anomaly import dashboard as wa_dash
        builds = [
            ("Total Waste per JENIS", wa_dash.chart_compare_total_waste),
            ("Distribusi Status", wa_dash.chart_compare_status),
            ("Top Item", wa_dash.chart_compare_top_items),
            ("Skor per Cabang", wa_dash.chart_compare_score),
        ]
        for i, (title, fn) in enumerate(builds):
            card = ChartCard(f"{title} — {a} vs {b}")
            self._compare_lay.addWidget(card, i // 2, i % 2)
            self._c_cmp.append(card)
            try:
                card.replace_fig(fn(df, a, b))
            except Exception as e:  # noqa: BLE001
                card.set_message(f"Gagal render:\n{e}", error=True)
