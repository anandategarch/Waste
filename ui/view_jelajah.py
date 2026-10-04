"""view_jelajah.py — view 'Jelajah': chart drill-down interaktif + tabel data
+ 9 chart statistik (gabungan tab Dashboard + Hasil + Viz lama).

Chart interaktif (status/cabang/top item) re-render saat filter berubah;
chart statistik render lazy (saat view dibuka / data baru / tombol segarkan)
supaya UI tetap ringan — pola H2 lama dipertahankan.

v2.7.0 (audit V26-M8): 3 chart statistik duplikat pasangan chart interaktif
(status pie / waste per cabang / top items — sisa merge tab tanpa dedupe)
dihapus; versi interaktif (bisa drill-down) yang dipertahankan.
"""
from __future__ import annotations

import pandas as pd
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

from .shared import fmt_id
from .state import AppContext
from .view_anomali import TABLE_COLS
from .widgets import Card, ChartCard, DataTable, WLabel, place_charts_responsive

SHEET_KEYS = [
    ("Detail", "Detail (semua kolom)"),
    ("Anomali Prioritas", "Anomali Prioritas"),
    ("Per Cabang", "Per Cabang"),
    ("Top Items", "Top Items"),
    ("Pareto Alasan", "Pareto Alasan"),
]

# Pesan placeholder pra-run pertama (V26-M6) — dipakai kartu chart + label
# tabel saat view dibangun; refresh() menggantinya secara alami.
_EMPTY_MSG = "Belum ada data — jalankan pipeline dulu (tab Pipeline)."


def _drill_value_ok(val) -> bool:
    """True bila nilai layak menjadi filter drill-down (V26-M9).

    None dan NaN ditolak: guard lama ``is not None`` membiarkan NaN lolos →
    filter cocok 0 baris → tabel kosong secara senyap. ``pd.isna(None)``
    adalah True → satu cek ganda; list (bukan skalar) tidak bisa dinilai
    ``pd.isna`` secara boolean → dianggap layak (penanganan di tempat lain).
    """
    if val is None:
        return False
    try:
        return not bool(pd.isna(val))
    except (TypeError, ValueError):
        return True


# Chart statistik statis (set Viz lama) — (judul, builder).
# v2.7.0: 3 duplikat DIHAPUS (V26-M8): "Distribusi Status (pie)",
# "Waste per Cabang", "Top Item Penyumbang Waste" — pasangan interaktifnya
# (klik → drill-down) sudah dirender di grid atas; data sama 2× = limbah.
_STAT_CHARTS = [
    ("Pareto Alasan (KETERANGAN)", "pareto_ket"),
    ("Heatmap Cabang × Item", "heatmap"),
    ("Frekuensi Alasan", "reasons_freq"),
    ("Scatter MAX vs TOTAL", "scatter_max"),
    ("Boxplot TOTAL per JENIS", "box_jenis"),
    ("Skor per Cabang", "score_cabang"),
    ("Kategori per Cabang", "kategori"),
    ("Komposisi JENIS (donut)", "jenis_donut"),
    ("Distribusi Fingerprint Skor", "fingerprint"),
]


class JelajahView(QWidget):
    """Eksplorasi data: drill chart interaktif + tabel + chart statistik."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._dirty = True
        self._stat_cards: dict[str, ChartCard] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._split = QSplitter(Qt.Orientation.Vertical, self)
        lay.addWidget(self._split, 1)

        # ===== BAGIAN ATAS: chart interaktif + tabel =====
        top = QWidget(self._split)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)

        # 3 chart interaktif — grid adaptif: status+item sejajar, cabang
        # (desain lebar dinamis utk 20 cabang) mengambil satu baris penuh.
        head = WLabel("Chart interaktif — KLIK bar/segmen untuk drill-down (klik ulang = lepas)", top)
        head.setObjectName("cardTitle")
        tl.addWidget(head)
        scroll_i = QScrollArea(top)
        scroll_i.setWidgetResizable(True)
        scroll_i.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ihost = QWidget()
        il = QGridLayout(ihost)
        self._il = il  # referensi utk re-placement responsif
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(8)
        self._c_status = ChartCard("Distribusi Status")
        self._c_cabang = ChartCard("Waste per Cabang")
        self._c_items = ChartCard("Top Item (skor tinggi)")
        il.setColumnStretch(0, 1)
        il.setColumnStretch(1, 1)
        scroll_i.setWidget(ihost)
        self._scroll_inter = scroll_i
        scroll_i.setMinimumHeight(300)
        tl.addWidget(scroll_i)

        # Tabel data (combo sheet)
        table_card = Card(top)
        tcl = QVBoxLayout(table_card)
        tcl.setContentsMargins(12, 10, 12, 10)
        tcl.setSpacing(6)
        trow = QWidget(table_card)
        trl = QHBoxLayout(trow)
        trl.setContentsMargins(0, 0, 0, 0)
        trl.setSpacing(10)
        tttl = WLabel("Tabel Data", trow)
        tttl.setObjectName("cardTitle")
        trl.addWidget(tttl)
        self._combo_sheet = QComboBox(trow)
        for key, label in SHEET_KEYS:
            self._combo_sheet.addItem(label, key)
        # Default = Anomali Prioritas (orientasi anomali; Detail 53 kolom
        # tetap tersedia via combo — didampingi scroll + tooltip)
        self._combo_sheet.setCurrentIndex(1)
        self._combo_sheet.currentIndexChanged.connect(lambda _i: self._refresh_table())
        trl.addWidget(self._combo_sheet)
        self._lbl_rows = WLabel("", trow)
        self._lbl_rows.setObjectName("hint")
        trl.addWidget(self._lbl_rows, 1)
        tcl.addWidget(trow)
        self._table = DataTable(table_card)
        self._table.double_clicked.connect(self._on_double)
        tcl.addWidget(self._table, 1)
        hint = WLabel("💡 Klik 2× baris (Detail/Anomali) untuk fokus cabang+item", table_card)
        hint.setObjectName("hint")
        tcl.addWidget(hint)
        tl.addWidget(table_card, 1)

        # ===== BAGIAN BAWAH: chart statistik (lazy) =====
        bottom = QWidget(self._split)
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        brow = QWidget(bottom)
        brl = QHBoxLayout(brow)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(10)
        bttl = WLabel("Chart Statistik (9)", brow)
        bttl.setObjectName("cardTitle")
        brl.addWidget(bttl)
        btn = QPushButton("🔄 Segarkan Chart Statistik", brow)
        btn.clicked.connect(lambda: self._render_stat_charts())
        brl.addWidget(btn)
        self._lbl_stat_note = WLabel("", brow)
        self._lbl_stat_note.setObjectName("hint")
        brl.addWidget(self._lbl_stat_note, 1)
        bl.addWidget(brow)
        scroll_s = QScrollArea(bottom)
        scroll_s.setWidgetResizable(True)
        shost = QWidget()
        self._stat_grid = QGridLayout(shost)
        self._stat_grid.setContentsMargins(0, 0, 0, 0)
        self._stat_grid.setSpacing(8)
        self._stat_grid.setColumnStretch(0, 1)
        self._stat_grid.setColumnStretch(1, 1)
        for title, key in _STAT_CHARTS:
            self._stat_cards[key] = ChartCard(title)
        scroll_s.setWidget(shost)
        bl.addWidget(scroll_s, 1)

        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        self._split.setSizes([500, 300])

        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)

        # V26-M6: sebelum run pertama, ChartCard dibuat tanpa parent dan grid
        # masih kosong → area view BLANK. Tempatkan kartu SEJAK KONSTRUKSI
        # dengan pesan placeholder; refresh()/render menggantinya alami
        # (replace_fig / set_message — penempatan ulang via place_charts_responsive).
        for c in (self._c_status, self._c_cabang, self._c_items):
            c.set_message(_EMPTY_MSG)
        self._inter_entries = [
            (self._c_status, None), (self._c_cabang, None), (self._c_items, None),
        ]
        for card in self._stat_cards.values():
            card.set_message(_EMPTY_MSG)
        self._stat_entries = [(card, None) for card in self._stat_cards.values()]
        self._lbl_rows.setText(_EMPTY_MSG)
        self._replay_layout()

    def _replay_layout(self) -> None:
        """Re-tempatkan kartu chart sesuai lebar area view saat ini."""
        w = max(self.width() - 24, 200)  # lebar view final saat resizeEvent
        place_charts_responsive(self._il, getattr(self, "_inter_entries", []), w)
        place_charts_responsive(self._stat_grid, getattr(self, "_stat_entries", []), w)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Deferred: saat event ini tiba, layout anak belum dihitung ulang —
        # viewport masih berukuran LAMA → keputusan 1/2 kolom basi. Tunda
        # ke tick berikutnya (setelah layout pass) supaya lebar final.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._replay_layout)

    # ------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------
    def on_shown(self) -> None:
        """Lazy render: view pertama kali dibuka setelah data baru."""
        if self._dirty:
            self.refresh()

    def _on_data_ready(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def _on_filters_changed(self) -> None:
        # Chart interaktif + tabel mengikuti filter (hanya bila terlihat);
        # chart statistik statis TIDAK ikut setiap ketikan (lazy + tombol).
        if self.isVisible():
            self._render_interactive()
            self._refresh_table()
        else:
            self._dirty = True

    def refresh(self) -> None:
        self._dirty = False
        self._render_interactive()
        self._refresh_table()
        self._render_stat_charts()

    # ------------------------------------------------------------
    # CHART INTERAKTIF (klik → filter)
    # ------------------------------------------------------------
    def _render_interactive(self) -> None:
        df = self._ctx.filtered_df()
        if df is None or df.empty:
            for c in (self._c_status, self._c_cabang, self._c_items):
                c.set_message("(tidak ada data untuk filter ini)")
            return
        from waste_anomaly import dashboard as wa_dash

        def _af(key: str):
            return (key, self._ctx.active_filters.get(key))

        def _fig_of(result):
            return result[0] if isinstance(result, tuple) else result

        builds = [
            (self._c_status, wa_dash.chart_status_bar_interactive, _af("status")),
            (self._c_cabang, wa_dash.chart_cabang_bar_interactive, _af("cabang")),
            (self._c_items, wa_dash.chart_top_items_interactive, _af("item")),
        ]
        self._inter_entries = []
        for card, fn, af in builds:
            fig = None
            try:
                result = fn(df, on_click=self._on_chart_click, active_filter=af)
                fig = _fig_of(result)
                card.replace_fig(fig)
            except Exception as e:  # noqa: BLE001 — 1 chart ≠ jatuhkan view
                card.set_message(f"Gagal render:\n{e}", error=True)
            self._inter_entries.append((card, fig))
        self._replay_layout()

    def _on_chart_click(self, key: str, val) -> None:
        """Klik chart: toggle filter (nilai sama → lepas).

        V26-M5: dulunya set_filter → filters_changed → re-render berjalan
        SINKRON di dalam handler button_press_event matplotlib (re-entrancy;
        klik cepat beruntun bisa menggantung). Kini handler hanya menjadwalkan
        pekerjaan ke tick event loop berikutnya lalu langsung kembali —
        klik-ganda-untuk-lepas tetap bekerja (toggle dinilai saat eksekusi).
        """
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._do_chart_click(key, val))

    def _do_chart_click(self, key: str, val) -> None:
        """Eksekusi drill-down sesungguhnya (di LUAR handler event matplotlib)."""
        if not _drill_value_ok(val):  # V26-M9: None/NaN → jangan set filter
            self._ctx.set_status("⚠ Nilai kosong — tidak bisa drill-down", "error")
            return
        if self._ctx.active_filters.get(key) == val:
            self._ctx.set_filter(key, None)
        else:
            self._ctx.set_filter(key, val)

    # ------------------------------------------------------------
    # TABEL
    # ------------------------------------------------------------
    def _refresh_table(self) -> None:
        key = self._combo_sheet.currentData() or "Detail"
        if key == "Anomali Prioritas":
            # Sheet anomali = kolom ramping (orientasi hunting); sheet
            # 'Detail' tetap menyediakan semua 53 kolom via combo.
            df = self._ctx.anomali_df()
            if df is not None and not df.empty:
                cols = [c for c in TABLE_COLS if c in df.columns]
                df = df[cols] if cols else df
        else:
            df = self._ctx.sheets.get(key)
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_rows.setText("Belum ada data — jalankan pipeline di tab Pipeline.")
            return
        self._table.set_dataframe(df, sort_desc="ANOMALY SCORE" if "ANOMALY SCORE" in df.columns else None)
        self._lbl_rows.setText(f"{fmt_id(len(df))} baris (tanpa cap — semua baris di-render)")

    def _on_double(self, rec: pd.Series) -> None:
        # V26-M9: guard NaN-aware — dulu ``is not None`` saja, NaN dari sel
        # lolos → filter 0 baris → tabel kosong senyap.
        for key, col in (("cabang", "NAMA RESTO"), ("item", "NAMA BARANG")):
            val = rec.get(col)
            if _drill_value_ok(val):
                self._ctx.set_filter(key, val)
            elif val is not None:
                self._ctx.set_status("⚠ Nilai kosong — tidak bisa drill-down", "error")

    # ------------------------------------------------------------
    # CHART STATISTIK
    # ------------------------------------------------------------
    def _render_stat_charts(self) -> None:
        df = self._ctx.filtered_df()
        if df is None or df.empty:
            for card in self._stat_cards.values():
                card.set_message("(tidak ada data untuk filter ini)")
            self._lbl_stat_note.setText("")
            return
        from waste_anomaly import charts as wa_charts
        from waste_anomaly import dashboard as wa_dash
        # v2.7.0: status_pie / waste_cabang / top_items DIHAPUS — duplikat
        # pasangan interaktif (V26-M8; lihat catatan di _STAT_CHARTS).
        builders = {
            "pareto_ket": lambda: wa_charts.chart_pareto_keterangan(df),
            "heatmap": lambda: wa_charts.chart_heatmap_cabang_item(df),
            "reasons_freq": lambda: wa_charts.chart_reasons_frequency(df),
            "scatter_max": lambda: wa_charts.chart_scatter_max_total(df),
            "box_jenis": lambda: wa_charts.chart_box_total_per_jenis(df),
            "score_cabang": lambda: wa_charts.chart_score_per_cabang(df),
            "kategori": lambda: wa_charts.chart_kategori_per_cabang(df),
            "jenis_donut": lambda: wa_charts.chart_jenis_donut(df),
            # fingerprint chart hidup di dashboard.py (bukan charts.py)
            "fingerprint": lambda: wa_dash.chart_fingerprint_distribution(df),
        }
        figs: dict[str, object] = {}
        ok = fail = 0
        for key, card in self._stat_cards.items():
            fn = builders.get(key)
            if fn is None:
                continue
            try:
                fig = fn()
                figs[key] = fig
                card.replace_fig(fig)
                ok += 1
            except Exception as e:  # noqa: BLE001 — 1 chart gagal ≠ jatuhkan view
                card.set_message(f"Gagal render:\n{e}", error=True)
                fail += 1
        # Penempatan adaptif & responsif (2 kolom ↔ 1 kolom bila sempit)
        self._stat_entries = [
            (self._stat_cards.get(key), figs.get(key))
            for _title, key in _STAT_CHARTS if self._stat_cards.get(key)
        ]
        self._replay_layout()
        # V26-L13: note lama mengklaim angkanya mengikuti filter aktif, tapi
        # menetap basi — chart statistik memang TIDAK otomatis ikut tiap
        # perubahan filter (lazy + tombol Segarkan); katakan yang selalu benar.
        note = (f"{fmt_id(len(df))} baris saat render terakhir — chart statistik "
                "tidak otomatis mengikuti filter; klik 🔄 Segarkan untuk menerapkan")
        if fail:
            note += f" • {fail} chart gagal render (lihat log)"
        self._lbl_stat_note.setText(note)
