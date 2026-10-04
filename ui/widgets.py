"""widgets.py — blok bangunan UI anti-terpotong (v2.6.0).

Jaminan struktural "tidak ada teks/grafik terpotong":
- WLabel: word-wrap default — teks selalu pindah baris, bukan terpotong
- MplCanvas: ukuran minimum = ukuran desain figure; melebar saat window
  besar; QScrollArea menjamin window kecil → scrollbar, BUKAN chart terpotong
- ChartCard: kartu chart dengan judul wrap + area scroll
- DataTable: QTableView virtualized (tanpa cap 500 baris), lebar kolom dari
  sampel isi + wrap teks panjang + tooltip sel
- KpiCard/KpiStrip: kartu KPI dengan wrap
"""
from __future__ import annotations

from typing import Callable

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from .models import PandasTableModel
from .shared import fmt_id
from .theme import C_TEXT_MUTED, STATUS_COLORS


class Card(QFrame):
    """Kartu dasar (border + radius via QSS objectName 'card')."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class WLabel(QLabel):
    """QLabel dengan word-wrap aktif default — teks tidak pernah terpotong."""

    def __init__(self, text: str = "", parent: QWidget | None = None,
                 muted: bool = False) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        if muted:
            self.setObjectName("muted")


# ============================================================
# MATPLOTLIB CANVAS — jantung jaminan chart tidak terpotong
# ============================================================

class MplCanvas(FigureCanvasQTAgg):
    """Canvas matplotlib dengan lantai ukuran (70% lebar / 90% tinggi desain).

    - Window lebih besar → figure melebar penuh (mengisi ruang)
    - Window lebih kecil → figure mengecil GRADATIF sampai lantai; di bawah
      lantai QScrollArea menampilkan scrollbar — chart TIDAK pernah dipotong
      atau diperas hingga tak terbaca. (Jaminan v2.6.0)
    """

    W_FLOOR = 0.85
    H_FLOOR = 1.0

    def __init__(self, fig: Figure, parent: QWidget | None = None) -> None:
        super().__init__(fig)
        dpi = fig.dpi
        w, h = fig.get_size_inches()
        self._min_w = max(int(w * dpi * self.W_FLOOR), 300)
        self._min_h = max(int(h * dpi * self.H_FLOOR), 220)
        self.setMinimumSize(self._min_w, self._min_h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _sync_size(self) -> None:
        """Sesuaikan ukuran figure dengan canvas (batas bawah = lantai)."""
        dpi = self.figure.dpi
        w = max(self._min_w, self.width()) / dpi
        h = max(self._min_h, self.height()) / dpi
        cur = self.figure.get_size_inches()
        if abs(cur[0] - w) > 0.05 or abs(cur[1] - h) > 0.05:
            self.figure.set_size_inches(w, h, forward=False)
            self.draw_idle()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_size()

    def _draw_idle(self) -> None:
        """Guard race teardown: singleShot matplotlib bisa menembak SETELAH
        canvas di-deleteLater (libshikoken raise RuntimeError) — telan senyap,
        canvas memang sudah dibongkar."""
        try:
            super()._draw_idle()
        except RuntimeError:
            pass


class ChartCard(Card):
    """Kartu berisi satu chart: judul wrap + QScrollArea + MplCanvas.

    ``replace_fig(fig)`` melepas figure lama (dispose + disconnect cid —
    pola H3 anti-leak) lalu menanam figure baru.
    """

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        self._title = WLabel(title, self)
        self._title.setObjectName("cardTitle")
        lay.addWidget(self._title)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        lay.addWidget(self._scroll, 1)
        self._canvas: MplCanvas | None = None
        self._placeholder: QWidget | None = None
        self.set_message("")

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_message(self, msg: str, error: bool = False) -> None:
        """Tampilkan pesan (data kosong / error) menggantikan chart."""
        self._dispose_canvas()
        lbl = WLabel(msg, self)
        lbl.setAlignment(Qt.AlignCenter)
        if error:
            lbl.setStyleSheet("color:#dc2626;")
        else:
            lbl.setStyleSheet(f"color:{C_TEXT_MUTED};")
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(24, 24, 24, 24)
        v.addWidget(lbl, 1)
        self._placeholder = wrap
        self._scroll.setWidget(wrap)

    def replace_fig(self, fig: Figure) -> None:
        self._dispose_canvas()
        if self._placeholder is not None:
            self._placeholder.deleteLater()
            self._placeholder = None
        self._canvas = MplCanvas(fig, self)
        self._scroll.setWidget(self._canvas)

    def _dispose_canvas(self) -> None:
        """Lepas + dispose figure lama (disconnect cid → close figure)."""
        if self._canvas is None:
            return
        fig = self._canvas.figure
        for cid in getattr(fig, "_waste_cids", []):
            try:
                fig.canvas.mpl_disconnect(cid)
            except Exception:
                pass
        self._canvas.setParent(None)
        self._canvas.deleteLater()
        self._canvas = None
        try:
            fig.close()
        except Exception:
            pass

    def disconnect_figs(self) -> None:
        """Dispose tanpa mengganti (dipanggil saat view dibongkar)."""
        self._dispose_canvas()


# ============================================================
# TABEL DATA
# ============================================================

class DataTable(QTableView):
    """QTableView + PandasTableModel — tanpa cap baris, sort klik header,
    kolom auto-width dari sampel, tooltip + wrap utk teks panjang."""

    double_clicked = Signal(object)  # pd.Series (record baris)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = PandasTableModel(parent=self)
        self.setModel(self._model)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)  # teks panjang wrap — baris tumbuh, tidak terpotong
        self.setTextElideMode(Qt.TextElideMode.ElideNone)  # tidak pernah '…'
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self._pending_fit = False
        self._last_fit_w = -1  # v2.6.1: lebar viewport saat fit terakhir
        self._narrow_hide: list[str] = []  # v2.6.1: kolom boleh-disebunyikan
        self.doubleClicked.connect(self._on_double)
        # Sort by header → tinggi baris harus dihitung ulang (baris visual
        # berganti isi; tinggi lama tidak cocok → teks wrap terpotong).
        self.horizontalHeader().sortIndicatorChanged.connect(
            lambda *_: self._refit_rows())

    def _refit_rows(self) -> None:
        """Hitung tinggi baris utk teks wrap (ukuran sendiri — QTableView's
        resizeRowsToContents tidak memperhitungkan wrap multi-baris sehingga
        baris ke-2 terpotong; diukur via QFontMetrics.boundingRect)."""
        model = self._model
        n = model.rowCount()
        if not (0 < n <= 3000):
            return
        fm = self.fontMetrics()
        default_h = self.verticalHeader().defaultSectionSize()
        for r in range(n):
            need = default_h
            for c in range(model.columnCount()):
                if self.isColumnHidden(c):  # v2.6.1: kolom responsif tak dihitung
                    continue
                text = str(model.data(model.index(r, c), Qt.DisplayRole) or "")
                if not text:
                    continue
                w = self.columnWidth(c) - 18  # padding sel (QSS 3px 8px)
                if w < 24:
                    continue
                if fm.horizontalAdvance(text) > w:
                    rect = fm.boundingRect(
                        0, 0, w, 10_000, Qt.TextFlag.TextWordWrap, text)
                    need = max(need, rect.height() + 12)
            if abs(self.rowHeight(r) - need) > 1:
                self.setRowHeight(r, need)

    def _on_double(self, index) -> None:
        rec = self._model.record(index.row())
        if rec is not None:
            self.double_clicked.emit(rec)

    def set_dataframe(self, df: pd.DataFrame | None,
                      sort_desc: str | None = None,
                      narrow_hide: list[str] | None = None) -> None:
        """Tampilkan df; ``sort_desc`` = nama kolom utk sort default DESC.

        ``narrow_hide`` (v2.6.1): nama kolom yang BOLEH disembunyikan —
        secara berurutan — bila lantai header tak muat di viewport sempit
        (tabel responsif). Disembunyikan ≠ terpotong: kolom inti tetap
        tampil; kolom disembunyikan muncul kembali saat window melebar.
        """
        self._narrow_hide = list(narrow_hide or [])
        self._model.set_dataframe(df)
        if sort_desc and df is not None and sort_desc in df.columns:
            col = list(df.columns).index(sort_desc)
            self.horizontalHeader().setSortIndicator(
                col, Qt.DescendingOrder)
            self._model.sort(col, Qt.DescendingOrder)
        self._pending_fit = True
        self._auto_columns()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Kolom belum ter-fit pas saat data pertama kali datang (viewport
        # belum berukuran final) → fit ulang sekali saat ukuran stabil.
        # v2.6.1: re-fit JUGA saat lebar viewport berubah (window di-resize) —
        # tanpa ini kolom memakai lebar window lama: kolom terakhir terpotong
        # di tepi + scrollbar muncul padahal sebenarnya muat. Ambang 24px
        # mencegah loop umpan-balik kemunculan scrollbar (~14px).
        vw = self.viewport().width()
        if vw > 50 and self.isVisible() and (
                self._pending_fit or abs(vw - self._last_fit_w) > 24):
            self._auto_columns()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        vw = self.viewport().width()
        if vw > 50 and (
                self._pending_fit or abs(vw - self._last_fit_w) > 24):
            self._auto_columns()

    def selected_record(self) -> pd.Series | None:
        idx = self.selectionModel().currentIndex()
        if idx.isValid():
            return self._model.record(idx.row())
        return None

    def _auto_columns(self, sample: int = 250, cap: int = 420,
                      min_w: int = 84) -> None:
        """Lebar kolom dari sampel isi + header, lalu di-FIT ke viewport.

        ANTI-TERPOTONG (aturan v2.6.0): bila total lebar melebihi viewport,
        seluruh kolom diskalakan proporsional supaya semua kolom terlihat.

        LANTAI HEADER (aturan v2.6.1): kolom TIDAK pernah menyusut di bawah
        lebar teks HEADERNYA sendiri. Tanpa ini, penyekalaan proporsional di
        jendela sempit memaksa Qt me-elide header TENGAH ("NAMA RESTO" tampil
        "MA REST", "KETERANGAN" → "TERANGA") — terpotong, melanggar jaminan.
        Sel bisa wrap (baris memanjang), header TIDAK bisa — lantai header
        adalah satu-satunya jaminan struktural. Bila jumlah lantai melebihi
        viewport, kolom tetap di lantai + scrollbar horizontal muncul
        (scroll ≠ terpotong; sama seperti sheet ekstrem mis. Detail 53
        kolom — didampingi tooltip + wrap sel)."""
        model = self._model
        n_rows = min(sample, model.rowCount())
        fm = self.fontMetrics()
        widths: list[int] = []
        floors: list[int] = []
        for c in range(model.columnCount()):
            hw = fm.horizontalAdvance(
                str(model.headerData(c, Qt.Horizontal))) + 26
            floors.append(min(max(min_w, hw), cap))
            w = hw
            for r in range(n_rows):
                text = str(model.data(model.index(r, c)) or "")
                if len(text) > 60:
                    text = text[:60]
                w = max(w, fm.horizontalAdvance(text) + 26)
            widths.append(min(w, cap))
        if not widths:
            return
        avail = self.viewport().width() - 4
        if avail < 200:
            avail = 200
        # v2.6.1 RESPONSIVE: bila lantai header tak muat, sembunyikan kolom
        # boleh-disebunyikan (urutan narrow_hide) sampai muat — kolom inti
        # tetap tampil. Bila SETELAH itu masih tak muat → scrollbar
        # horizontal (scroll ≠ terpotong).
        n_cols = model.columnCount()
        hidden: set[int] = set()
        if self._narrow_hide and n_cols:
            names = [str(model.headerData(c, Qt.Horizontal))
                     for c in range(n_cols)]
            total_f = sum(floors)
            for want in self._narrow_hide:
                if total_f <= avail:
                    break
                if want in names:
                    c = names.index(want)
                    if c not in hidden:
                        hidden.add(c)
                        total_f -= floors[c]
        for c in range(n_cols):
            self.setColumnHidden(c, c in hidden)
        keep = [c for c in range(n_cols) if c not in hidden]
        total = sum(widths[c] for c in keep)
        final: dict[int, int] = {}
        if total > avail:
            # Skala proporsional → semua kolom masuk viewport (tidak
            # terpotong), tapi TIDAK menyusut di bawah lantai header (v2.6.1).
            scale = avail / total
            for c in keep:
                final[c] = max(int(widths[c] * scale), floors[c])
            # PASS-2 (v2.6.1): lantai bisa menahan Σ di atas avail padahal
            # kolom konten-lebar masih punya slack — tekan proporsional
            # terhadap slack sampai muat / semua kolom sudah di lantai
            # (baru scrollbar mengambil alih; sel wrap menangani sisanya).
            over = sum(final.values()) - avail
            if over > 0:
                slack = {c: final[c] - floors[c] for c in keep}
                total_slack = sum(slack.values())
                if total_slack > 0:
                    cut = min(over, total_slack)
                    for c in keep:
                        if slack[c] > 0:
                            share = int(round(cut * slack[c] / total_slack))
                            final[c] = max(final[c] - share, floors[c])
            # Sisa pembulatan (≤ beberapa px): potong dari kolom ber-slack
            # terbesar satu-per-satu supaya scrollbar tak muncul sia-sia.
            over = sum(final.values()) - avail
            while over > 0:
                cand = max(keep, key=lambda c: final[c] - floors[c])
                if final[cand] <= floors[cand]:
                    break  # semua di lantai — scrollbar memang tak terhindarkan
                final[cand] -= 1
                over -= 1
        else:
            for c in keep:
                final[c] = widths[c]
        for c in keep:
            self.setColumnWidth(c, final[c])
        self._last_fit_w = self.viewport().width()  # v2.6.1
        if sum(final.values()) <= avail + 2:
            self._pending_fit = False  # sudah pas — tidak perlu fit ulang
        if n_rows == 0 and keep:
            self.setColumnWidth(keep[0], max(final[keep[0]], 240))
        # Wrap baris: teks panjang (RANGKING WASTE, Detail/Contoh KQ) tampil
        # UTUH — tinggi baris dihitung manual (lihat _refit_rows). Di-skip
        # utk tabel raksasa (25k×53) demi kecepatan (tooltip + fit kolom).
        self._refit_rows()


# ============================================================
# KPI
# ============================================================

class KpiCard(QFrame):
    """Kartu KPI: label kecil + angka besar + konteks (wrap)."""

    def __init__(self, title: str, color: str = "#0f172a",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiframe")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._title = WLabel(title, self)
        self._title.setObjectName("hint")
        lay.addWidget(self._title)
        self._value = WLabel("0", self)
        self._value.setStyleSheet(
            f"color:{color}; font-size:20px; font-weight:700; border:none;")
        lay.addWidget(self._value)
        self._context = WLabel("", self)
        self._context.setObjectName("hint")
        lay.addWidget(self._context)

    def set_value(self, text: str) -> None:
        self._value.setText(text)

    def set_context(self, text: str) -> None:
        self._context.setText(text)


class KpiStrip(QWidget):
    """6 KPI + breakdown satuan (logika _update_kpi_values v2.5.1).

    Nilai mengikuti df TERFILTER (DD-M3) — konteks "[X dari N baris]" jujur.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QWidget(self)
        from PySide6.QtWidgets import QGridLayout
        gl = QGridLayout(row)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        self.kpi_total = KpiCard("TOTAL BARIS", "#0f172a")
        self.kpi_prioritas = KpiCard("PRIORITAS TINGGI", "#dc2626")
        self.kpi_potensi = KpiCard("POTENSI ANOMALI", "#ea580c")
        self.kpi_review = KpiCard("PERLU REVIEW", "#b45309")
        self.kpi_waste = KpiCard("TOTAL WASTE", "#0f766e")
        self.kpi_cabang = KpiCard("CABANG", "#9333ea")
        for i, card in enumerate((self.kpi_total, self.kpi_prioritas,
                                  self.kpi_potensi, self.kpi_review,
                                  self.kpi_waste, self.kpi_cabang)):
            gl.addWidget(card, 0, i)
        lay.addWidget(row)
        self.lbl_units = WLabel("", self)
        self.lbl_units.setObjectName("hint")
        lay.addWidget(self.lbl_units)
        self.lbl_context = WLabel("", self)
        self.lbl_context.setObjectName("hint")
        lay.addWidget(self.lbl_context)

    def update_from(self, df: pd.DataFrame, full_len: int) -> None:
        """Perbarui nilai KPI dari df terfilter (konteks = full_len)."""
        if df is None:
            return
        total = len(df)
        if "ANOMALY STATUS" in df.columns:
            prioritas = int((df["ANOMALY STATUS"] == "Prioritas Tinggi").sum())
            potensi = int((df["ANOMALY STATUS"] == "Potensi Anomali").sum())
            review = int((df["ANOMALY STATUS"] == "Perlu Review").sum())
        else:
            prioritas = potensi = review = 0
        total_waste = float(df["TOTAL"].sum()) if "TOTAL" in df.columns else 0.0
        cabang = df["NAMA RESTO"].nunique() if "NAMA RESTO" in df.columns else 0

        self.kpi_total.set_value(fmt_id(total))
        self.kpi_prioritas.set_value(fmt_id(prioritas))
        self.kpi_potensi.set_value(fmt_id(potensi))
        self.kpi_review.set_value(fmt_id(review))
        self.kpi_waste.set_value(fmt_id(total_waste, 1))
        self.kpi_cabang.set_value(fmt_id(cabang))
        self.lbl_context.setText(
            f"[KPI terfilter: {fmt_id(total)} dari {fmt_id(full_len)} baris]")
        # P5: breakdown satuan — total waste mencampur satuan (indikatif)
        self.lbl_units.setText(self._unit_note(df))

    def _unit_note(self, df: pd.DataFrame) -> str:
        try:
            from waste_anomaly.temporal import unit_summary
            us = unit_summary(df)
            if us is None or us.empty:
                return ""
            parts = []
            cols = list(us.columns)
            name_col = cols[0]
            val_col = "Total_Waste" if "Total_Waste" in cols else (
                cols[1] if len(cols) > 1 else None)
            for _, r in us.head(3).iterrows():
                if val_col:
                    parts.append(f"{r[name_col]}: {fmt_id(float(r[val_col]), 1)}")
                else:
                    parts.append(str(r[name_col]))
            if parts:
                return "Satuan — " + " • ".join(parts) + " (agregat lintas satuan, indikatif)"
        except Exception:
            return ""
        return ""


# ============================================================
# CHIP STATUS (detail panel)
# ============================================================

class StatusChip(QFrame):
    """Chip kecil berwarna utk status / sinyal — teks wrap, tidak terpotong."""

    def __init__(self, text: str, fg: str, bg: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:6px; border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lbl = QLabel(text, self)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("background:transparent; color:inherit; border:none;")
        lay.addWidget(lbl)


def status_chip_for(status: str, parent=None) -> StatusChip:
    fg, bg = STATUS_COLORS.get(status, ("#334155", "#f1f5f9"))
    return StatusChip(status, fg, bg, parent)


def place_charts_responsive(grid, entries, width: int) -> None:
    """(Re)tempatkan kartu chart secara responsif (aturan v2.6.0).

    - Lebar cukup (≥ 860px) → 2 kolom; lebih sempit → 1 kolom (jendela
      kecil tidak mempersempit chart hingga terpotong).
    - Chart dengan desain lebar (≥ 700px) SELALU menempati satu baris
      penuh — legend/judul di tepi kanan tidak pernah setengah terpotong.
    - ``entries``: list berurutan (card, fig_atau_None).
    """
    from PySide6.QtWidgets import QGridLayout  # noqa: F401 — tipe grid
    cols = 2 if width >= 860 else 1
    while grid.count():
        grid.takeAt(0)
    # Stretch kolom harus mengikuti jumlah kolom AKTIF — kolom kosong yang
    # memegang stretch membuat chart hanya mendapat setengah lebar (bug).
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1 if cols == 2 else 0)
    row = col = 0
    for card, fig in entries:
        wide = (fig is not None
                and fig.get_size_inches()[0] * fig.dpi >= 700)
        span = 2 if (wide and cols == 2) else 1
        if col + span > cols:
            col = 0
            row += 1
        grid.addWidget(card, row, col, 1, span)
        col += span
        if col >= cols:
            col = 0
            row += 1
