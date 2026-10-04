"""view_anomali.py — view utama (default): perburuan anomali (v2.6.0).

Landing pertama aplikasi: tabel anomali TER-RANKING (skor turun) + KPI
terfilter + panel detail baris terpilih (12 sinyal + peer + drill-down).
Semua teks word-wrap; tabel tanpa cap baris; kolom auto-width + wrap.
"""
from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from .models import fmt_cell
from .shared import fmt_id
from .state import AppContext
from .theme import STATUS_COLORS
from .widgets import Card, DataTable, KpiStrip, StatusChip, WLabel, status_chip_for

# Kolom tabel anomali — ramping (detail lengkap ada di panel bawah)
TABLE_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO", "NAMA BARANG",
    "JENIS", "KETERANGAN", "TOTAL", "MAX", "HARI MAX", "RANGKING WASTE",
]

# 12 sinyal — label persis signals.py (bagian REASON TEXT)
SIGNALS: list[tuple[str, str]] = [
    ("_s1", "S1 · Spike vs AVG"),
    ("_s2", "S2 · MAX ≫ AVG aktif"),
    ("_s3", "S3 · MAX ≫ MEDIAN aktif"),
    ("_s4", "S4 · Konsentrasi MAX"),
    ("_s5", "S5 · Gap MAX vs SECOND"),
    ("_s6", "S6 · MAX/BOM tinggi"),
    ("_s7", "S7 · TOTAL/BOM tinggi"),
    ("_s8", "S8 · MAX outlier peer"),
    ("_s9", "S9 · TOTAL outlier peer"),
    ("_s10", "S10 · Single-day event"),
    ("_s11", "S11 · Dominasi hari akhir"),
    ("_s12", "S12 · Potensi salah skala"),
]

# Metrik konteks yang ditampilkan di panel detail (bila kolomnya ada)
DETAIL_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO", "NAMA BARANG",
    "JENIS", "KETERANGAN", "SOURCE DATA", "TOTAL", "MAX", "AVG",
    "HARI MAX", "SATUAN", "TOTAL BOM", "PEER COUNT",
    "PEER MEDIAN TOTAL", "PEER MEDIAN MAX", "TOTAL / PEER MEDIAN",
    "MAX / PEER MEDIAN MAX", "MAX / BOM", "TOTAL / BOM", "MAX SHARE",
    "LAST DAY SHARE", "KATEGORI ANOMALI", "RANGKING WASTE",
]


class DetailPanel(Card):
    """Panel detail satu baris anomali: identitas + sinyal + drill-down."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._title = WLabel("Pilih baris anomali di tabel atas untuk melihat detail lengkapnya (12 sinyal, peer, uang).", self)
        self._title.setObjectName("cardTitle")
        lay.addWidget(self._title)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self._scroll, 1)
        self._content = QWidget()
        self._scroll.setWidget(self._content)

    def show_record(self, rec: pd.Series) -> None:
        """Render ulang konten detail dari record baris terpilih."""
        # Buang konten lama
        old = self._content.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        else:
            from PySide6.QtWidgets import QVBoxLayout as _VL
            old = _VL(self._content)

        lay = old
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        cabang = fmt_cell(rec.get("NAMA RESTO"))
        item_name = fmt_cell(rec.get("NAMA BARANG"))
        status = fmt_cell(rec.get("ANOMALY STATUS"))
        skor = fmt_cell(rec.get("ANOMALY SCORE"))
        self._title.setText(f"Anomali — Skor {skor} — {cabang} — {item_name}")

        # Baris identitas: chip status + skor
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        hl.addWidget(status_chip_for(status))
        skor_lbl = QLabel(f"Skor {skor} dari 19", head)
        skor_lbl.setStyleSheet("font-weight:700;")
        hl.addWidget(skor_lbl)
        hl.addStretch(1)
        lay.addWidget(head)

        # Grid 12 sinyal — chip merih bila terpicu
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        for i, (col, label) in enumerate(SIGNALS):
            val = rec.get(col, 0)
            try:
                val = float(pd.to_numeric(pd.Series([val])).iloc[0])
            except Exception:
                val = 0.0
            triggered = val and val > 0
            if triggered:
                fg, bg = "#dc2626", "#fef2f2"
                text = f"{label} ✓ ({fmt_id(val, 0)})"
            else:
                fg, bg = "#64748b", "#f1f5f9"
                text = label
            gl.addWidget(StatusChip(text, fg, bg), i // 3, i % 3)
        lay.addWidget(grid)

        # Alasan (teks lengkap ANOMALY REASONS)
        reasons = fmt_cell(rec.get("ANOMALY REASONS"))
        if reasons:
            lay.addWidget(self._section("Alasan terdeteksi"))
            lay.addWidget(WLabel(reasons))

        # Metrik konteks (QFormLayout — wrap, tidak terpotong)
        lay.addWidget(self._section("Konteks & pembanding"))
        metrics = QWidget()
        fl = QFormLayout(metrics)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for col in DETAIL_COLS:
            if col in ("ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO",
                       "NAMA BARANG", "ANOMALY REASONS"):
                continue
            if col in rec.index:
                key = QLabel(f"{col}:", metrics)
                key.setStyleSheet("color:#64748b;")
                val_lbl = WLabel(fmt_cell(rec.get(col)), metrics)
                val_lbl.setStyleSheet("font-weight:600;")
                fl.addRow(key, val_lbl)
        lay.addWidget(metrics)

        # Tombol drill-down (filter langsung dari baris ini)
        lay.addWidget(self._section("Drill-down dari baris ini"))
        btns = QWidget()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        if rec.get("NAMA RESTO") is not None:
            b = QPushButton("🏬 Fokus cabang ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA RESTO"):
                              self._ctx.set_filter("cabang", v))
            bl.addWidget(b)
        if rec.get("NAMA BARANG") is not None:
            b = QPushButton("📦 Fokus item ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA BARANG"):
                              self._ctx.set_filter("item", v))
            bl.addWidget(b)
        if rec.get("KETERANGAN") is not None and str(rec.get("KETERANGAN")) not in ("", "nan"):
            b = QPushButton("🏷 Fokus alasan ini")
            b.clicked.connect(lambda _=False, v=str(rec.get("KETERANGAN")).strip():
                              self._ctx.set_filter("keterangan", v))
            bl.addWidget(b)
        bl.addStretch(1)
        lay.addWidget(btns)
        lay.addStretch(1)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#0f172a; font-weight:700; border:none; background:transparent;")
        return lbl


class AnomaliView(QWidget):
    """View 'Anomali': KPI + tabel ranking + panel detail + ambang skor."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # KPI strip (nilai mengikuti filter — DD-M3)
        self._kpi = KpiStrip(self)
        lay.addWidget(self._kpi)

        # Bar kontrol: ambang skor + jumlah anomali
        ctrl = QWidget(self)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(8, 0, 8, 0)
        cl.setSpacing(10)
        lbl = WLabel("Anomali dengan skor ≥", ctrl)
        cl.addWidget(lbl)
        self._spin_score = QSpinBox(ctrl)
        self._spin_score.setRange(0, 19)
        self._spin_score.setValue(0)
        self._spin_score.setToolTip(
            "Sembunyikan anomali ber-skor rendah (0 = tampilkan semua).\n"
            "Skor komposit maksimum = 19 (S1..S12).")
        self._spin_score.valueChanged.connect(self._on_score_changed)
        cl.addWidget(self._spin_score)
        self._lbl_count = WLabel("", ctrl)
        self._lbl_count.setObjectName("hint")
        cl.addWidget(self._lbl_count, 1)
        lay.addWidget(ctrl)

        # Splitter: tabel (atas) + detail (bawah)
        self._split = QSplitter(Qt.Orientation.Vertical, self)
        table_card = Card(self._split)
        tcl = QVBoxLayout(table_card)
        tcl.setContentsMargins(12, 10, 12, 10)
        tcl.setSpacing(6)
        title = WLabel("Tabel Anomali Ter-ranking (klik header utk sort; pilih baris utk detail)", table_card)
        title.setObjectName("cardTitle")
        tcl.addWidget(title)
        self._table = DataTable(table_card)
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        self._table.double_clicked.connect(self._on_double)
        tcl.addWidget(self._table, 1)
        hint = WLabel("💡 Klik 2× baris untuk fokus cabang+item sekaligus", table_card)
        hint.setObjectName("hint")
        tcl.addWidget(hint)

        self._detail = DetailPanel(ctx, self._split)
        self._split.setStretchFactor(0, 3)
        self._split.setStretchFactor(1, 2)
        self._split.setSizes([420, 260])
        lay.addWidget(self._split, 1)

        # Reaksi state — pola lazy H2: view tak terlihat → tandai dirty,
        # render saat dibuka (on_shown). View default biasanya terlihat saat
        # pipeline selesai → render langsung.
        self._dirty = True
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)

    def _on_data_ready(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def _on_filters_changed(self) -> None:
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data baru / filter basi."""
        if self._dirty:
            self.refresh()

    # ------------------------------------------------------------
    def refresh(self) -> None:
        """Dataset baru: KPI + tabel (filter sudah direset oleh state)."""
        self._dirty = False
        self._spin_score.blockSignals(True)
        self._spin_score.setValue(0)
        self._ctx.score_min = 0
        self._spin_score.blockSignals(False)
        self._refresh_kpi()
        self._refresh_table()

    def _on_score_changed(self, value: int) -> None:
        self._ctx.set_score_min(value)

    def _refresh_table(self) -> None:
        # Sinkron spin ambang skor (reset eksternal, mis. tombol Hapus Filter)
        if self._spin_score.value() != self._ctx.score_min:
            self._spin_score.blockSignals(True)
            self._spin_score.setValue(self._ctx.score_min)
            self._spin_score.blockSignals(False)
        df = self._ctx.anomali_df()
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_count.setText("Belum ada data — buka tab Pipeline, pilih workbook, jalankan.")
            return
        cols = [c for c in TABLE_COLS if c in df.columns]
        view_df = df[cols] if cols else df
        self._table.set_dataframe(view_df, sort_desc="ANOMALY SCORE")
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if len(view_df) == 0:
            self._lbl_count.setText("0 anomali lolos filter — longgarkan filter atau ambang skor.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(len(view_df))} anomali tampil (dari {fmt_id(full)} baris data)")
        self._refresh_kpi()

    def _refresh_kpi(self) -> None:
        filtered = self._ctx.filtered_df()
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if filtered is not None:
            self._kpi.update_from(filtered, full)

    def _on_selection(self) -> None:
        rec = self._table.selected_record()
        if rec is not None:
            self._detail.show_record(rec)

    def _on_double(self, rec: pd.Series) -> None:
        """Klik 2×: fokus cabang+item sekaligus (drill-down P8)."""
        if rec.get("NAMA RESTO") is not None:
            self._ctx.set_filter("cabang", rec.get("NAMA RESTO"))
        if rec.get("NAMA BARANG") is not None:
            self._ctx.set_filter("item", rec.get("NAMA BARANG"))
