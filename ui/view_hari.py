"""view_hari.py — view 'Hari Mencurigakan' (v2.9.0).

Tab ke-4 (disetujui user setelah pembuktian read-only v2.8.3: 74% anomali
bisa dilokalisasi ke hari tertentu). Menjawab pertanyaan user:
"misal ada potensi salah angka kamu bisa deteksi gak dia potensi salah
nya di tanggal berapa dari 1-31?"

Data: kolom bukti-hari hasil Stage 15 (waste_anomaly/day_focus.py) —
HARI TERSANGKA, NILAI HARI TERSANGKA, TIPIKAL CABANG LAIN,
RASIO VS CABANG LAIN, SHARE HARI TERSANGKA, ALASAN HARI.

UI:
- 3 KPI ringkas: anomali tampil · ada bukti hari · rasio terbesar
- Combo: hanya baris dengan bukti hari (default) / semua anomali
- Tabel terurut RASIO VS CABANG LAIN (terbesar duluan) — hover judul
  kolom = penjelasan istilah (COLUMN_TOOLTIPS); klik baris = pop-up
  detail 12 sinyal + peta hari 1-31; klik 2× = fokus cabang+item.

Istilah sengaja awam (permintaan user): "tipikal cabang lain", "berapa
kali lipat", "porsi dari total bulanan" — bukan jargon statistik.
"""
from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .shared import fmt_id
from .state import AppContext
from .view_anomali import DetailDialog
from .widgets import Card, DataTable, KpiCard, WLabel, busy_feedback

# Kolom tabel hari-mencurigakan (ramping — detail lengkap di pop-up).
TABLE_COLS = [
    "ANOMALY SCORE", "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
    "HARI TERSANGKA", "NILAI HARI TERSANGKA", "TIPIKAL CABANG LAIN",
    "RASIO VS CABANG LAIN", "SHARE HARI TERSANGKA", "ALASAN HARI",
]


class HariView(QWidget):
    """View 'Hari Mencurigakan': tabel bukti hari per anomali ter-filter."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # KPI ringkas (3 kartu)
        kpi_row = QWidget(self)
        kl = QHBoxLayout(kpi_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(8)
        self._kpi_tampil = KpiCard("ANOMALI TAMPIL", "#0f172a",
                                   tooltip="Banyak baris anomali yang lolos "
                                           "filter & pilihan tampil.")
        self._kpi_bukti = KpiCard("ADA BUKTI HARI", "#dc2626",
                                  tooltip="Anomali yang bisa dilokalisasi ke "
                                          "tanggal tertentu (rasio ≥ 5× cabang "
                                          "lain, atau ≥ 50% waste sebulan di "
                                          "satu hari, atau pola 10× salah "
                                          "ketik, atau waste cuma 1 hari).")
        self._kpi_rasio = KpiCard("RASIO TERBESAR", "#ea580c",
                                  tooltip="Berapa kali lipat nilai hari "
                                          "tersangka vs cabang lain di hari "
                                          "yang sama (baris teratas saat "
                                          "diurut berdasarkan rasio).")
        for card in (self._kpi_tampil, self._kpi_bukti, self._kpi_rasio):
            kl.addWidget(card)
        kl.addStretch(1)
        lay.addWidget(kpi_row)

        # Kartu tabel
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        title = WLabel("📅 Hari Mencurigakan — potensi salah angka per tanggal (1–31)", card)
        title.setObjectName("cardTitle")
        cl.addWidget(title)
        hint = WLabel(
            "💡 Bukti hari = angka besar menumpuk di tanggal tertentu: jauh di atas "
            "cabang lain di hari yang sama, atau ≥ 50% waste sebulan jatuh di satu "
            "hari, atau pola 10× (salah ketik), atau waste cuma 1 hari. Kolom "
            "ALASAN HARI merangkum buktinya — hover judul kolom untuk arti tiap istilah.",
            card)
        hint.setObjectName("hint")
        cl.addWidget(hint)

        # Bar kontrol: combo tampilkan
        ctrl = QWidget(card)
        ctl = QHBoxLayout(ctrl)
        ctl.setContentsMargins(8, 0, 8, 0)
        ctl.setSpacing(10)
        lbl = WLabel("Tampilkan:", ctrl)
        ctl.addWidget(lbl)
        self._cb_mode = QComboBox(ctrl)
        self._cb_mode.addItem("Ada bukti hari (disarankan)")
        self._cb_mode.addItem("Semua anomali")
        self._cb_mode.setToolTip(
            "Default: hanya anomali yang punya bukti hari (lebih fokus).\n"
            "'Semua anomali' = tampilkan juga yang belum bisa dilokalisasi\n"
            "(kolom bukti kosong).")
        self._cb_mode.currentIndexChanged.connect(
            lambda _i: self._on_mode_changed())
        ctl.addWidget(self._cb_mode)
        self._lbl_count = WLabel("", ctrl)
        self._lbl_count.setObjectName("hint")
        ctl.addWidget(self._lbl_count, 1)
        cl.addWidget(ctrl)

        self._table = DataTable(card)
        self._table.setMinimumHeight(200)
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        self._table.double_clicked.connect(self._on_double)
        cl.addWidget(self._table, 1)
        table_hint = WLabel(
            "💡 Klik baris = detail pop-up (12 sinyal + peta hari 1–31) · "
            "klik 2× = fokus cabang+item · klik header = sort",
            card)
        table_hint.setObjectName("hint")
        cl.addWidget(table_hint)
        lay.addWidget(card, 1)

        # Pop-up detail — satu instance dipakai ulang (pola AnomaliView).
        self._popup = DetailDialog(ctx, self)
        # v2.9.0 (perf): memo irisan bukti-hari — kombinasi (df dasar, mode)
        # yang sama mengembalikan objek SAMA → cache fit LRU DataTable
        # (hit) + memo teks model tetap hidup. Strong ref ke df dasar = id
        # tak bisa dipakai ulang selama cache hidup (kunci id() aman).
        self._bukti_cache: tuple[int, int, pd.DataFrame] | None = None

        # Reaksi state — pola lazy H2 (sama dengan AnomaliView).
        self._dirty = True
        self._batch_filters = False
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)

    # ------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------
    def _on_data_ready(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def _on_filters_changed(self) -> None:
        if self._batch_filters:
            return
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_mode_changed(self) -> None:
        if self.isVisible():
            self._refresh_table()

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data baru / filter basi."""
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        """Dataset baru: KPI + tabel (filter sudah direset oleh state)."""
        self._dirty = False
        self._cb_mode.blockSignals(True)
        self._cb_mode.setCurrentIndex(0)
        self._cb_mode.blockSignals(False)
        self._refresh_table()

    def _refresh_table(self) -> None:
        """v2.9.0 — titik tunggal render tabel, dibungkus busy_feedback
        (pola v2.8.3 anti-freeze: cursor sibuk + status ⏳/✓ + durasi)."""
        with busy_feedback(self._ctx.set_status, "Menganalisa hari tersangka"):
            self._refresh_table_impl()

    def _refresh_table_impl(self) -> None:
        self._table.clearSelection()
        self._popup.hide()
        self._popup._panel.clear()
        df = self._ctx.anomali_df()
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_count.setText(
                "Belum ada data — buka tab Pipeline, pilih workbook, jalankan.")
            return
        if "HARI TERSANGKA" not in df.columns:
            # Dataset tanpa kolom bukti hari (fixture sintetis / pipeline lama)
            self._table.set_dataframe(None)
            self._lbl_count.setText(
                "Dataset ini tidak punya kolom bukti hari — jalankan ulang "
                "pipeline (v2.9.0+).")
            self._update_kpi(None, 0, None)
            return
        bukti = (df["BUKTI HARI"].astype(str) == "YES") \
            if "BUKTI HARI" in df.columns else pd.Series(False, index=df.index)
        if self._cb_mode.currentIndex() == 0:
            cached = self._bukti_cache
            if (cached is not None and cached[0] == id(df)
                    and cached[1] == len(df)):
                df_show = cached[2]
            else:
                df_show = df[bukti]
                self._bukti_cache = (id(df), len(df), df_show)
        else:
            df_show = df
        n_bukti_all = int(bukti.sum())
        cols = [c for c in TABLE_COLS if c in df_show.columns]
        self._table.set_dataframe(
            df_show, sort_desc="RASIO VS CABANG LAIN",
            narrow_hide=["JENIS", "KETERANGAN", "ALASAN HARI"],
            visible_cols=cols)
        n_tampil = len(df_show)
        if n_tampil == 0:
            self._lbl_count.setText(
                "0 anomali lolos filter — longgarkan filter / coba "
                "'Semua anomali'.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(n_tampil)} baris tampil • {fmt_id(n_bukti_all)} "
                f"dari {fmt_id(len(df))} anomali punya bukti hari")
        # Rasio terbesar utk KPI (dari df_show — konsisten dgn tabel)
        rasio = None
        if "RASIO VS CABANG LAIN" in df_show.columns:
            r = pd.to_numeric(df_show["RASIO VS CABANG LAIN"],
                              errors="coerce").max()
            if r == r:
                rasio = float(r)
        self._update_kpi(n_tampil, n_bukti_all, rasio)

    def _update_kpi(self, n_tampil: int, n_bukti: int, rasio) -> None:
        self._kpi_tampil.set_value(fmt_id(n_tampil or 0))
        self._kpi_bukti.set_value(fmt_id(n_bukti or 0))
        if rasio is None:
            self._kpi_rasio.set_value("—")
            self._kpi_rasio.set_context("belum ada pembanding hari")
        else:
            self._kpi_rasio.set_value(
                f"{rasio:,.0f}×".replace(",", "."))
            self._kpi_rasio.set_context("vs cabang lain, hari sama")

    # ------------------------------------------------------------
    # INTERAKSI
    # ------------------------------------------------------------
    def _on_selection(self) -> None:
        rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    def _on_double(self, rec: pd.Series) -> None:
        """Klik 2×: fokus cabang+item (pola drill-down AnomaliView + guard
        coalesce V26-L4 — dua filter, satu render)."""
        self._batch_filters = True
        try:
            if rec.get("NAMA RESTO") is not None:
                self._ctx.set_filter("cabang", rec.get("NAMA RESTO"))
            if rec.get("NAMA BARANG") is not None:
                self._ctx.set_filter("item", rec.get("NAMA BARANG"))
        finally:
            self._batch_filters = False
        self._refresh_table()
