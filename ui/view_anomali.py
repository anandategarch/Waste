"""view_anomali.py — view utama (default): perburuan anomali (v2.6.0).

Landing pertama aplikasi: tabel anomali TER-RANKING (skor turun) + KPI
terfilter. Semua teks word-wrap; tabel tanpa cap baris; kolom auto-width
+ wrap.

v2.8.1: panel detail inline DIGANTI pop-up — klik baris tabel membuka
jendela pop-up non-modal berisi 12 sinyal + peer + uang + tombol
drill-down. Tabel kini memenuhi SELURUH tinggi view (tanpa splitter).
Kolom "% to BOM" (waste dibanding penjualan kuantiti) ditambahkan ke
tabel per-ranking; kolom rasio ditampilkan sebagai persen.
"""
from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .models import (
    COLUMN_TOOLTIPS,
    DELTA_PCT_COLS,
    PCT_COLS,
    RATIO_X_COLS,
    fmt_cell,
    fmt_delta_pct,
    fmt_pct,
    fmt_ratio_x,
)
from waste_anomaly.period_history import CHANGE_CATEGORIES, change_vs_history
from .shared import fmt_id
from .state import AppContext
from .widgets import (
    Card, DataTable, KpiStrip, SlicerBar, StatusChip, WLabel, busy_feedback,
    status_chip_for,
)
from waste_anomaly.signals import SIGNAL_PARTS

# Kolom tabel anomali — ramping (detail lengkap ada di pop-up detail).
# v2.6.1: 10 → 7 kolom (MAX / HARI MAX / RANGKING WASTE duplikatif).
# v2.8.1: 7 → 8 — "% to BOM" (waste vs penjualan kuantiti) ditambahkan
# setelah TOTAL sesuai permintaan user: rasio per-ranking terlihat langsung
# di tabel. Nilai 'Cek' = item tanpa data penjualan (tak bisa dihitung).
TABLE_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO", "NAMA BARANG",
    "JENIS", "KETERANGAN", "TOTAL", "% to BOM",
    # v2.10.2: muncul hanya bila pembanding bulan lalu tersedia (kolom
    # ditambahkan ADDITIF oleh change_vs_history — tanpa pembanding tabel
    # identik v2.10.1, pola view Hari Mencurigakan).
    "BULAN LALU", "PERUBAHAN %", "PERUBAHAN",
]

# 12 sinyal — label ringkas utk chip + fragmen teks ANOMALY REASONS
# (sumber tunggal fragmen: SIGNAL_PARTS di waste_anomaly/signals.py).
# v2.7.0 (lanjutan V26-C1): kolom _s1.._s12 DI-DROP pipeline sebelum df
# sampai UI, jadi status terpicu chip dibaca dari fragmen di teks
# ANOMALY REASONS; nilai _s* hanya fallback bila kolom ada (fixture
# test sintetis) — sebelum fix ini 12 chip SELALU abu-abu di data riil.
# v2.9.0 (permintaan user "permudah istilah"): label tanpa jargon;
# penjelasan lengkap tiap sinyal ada di _CHIP_TIPS (tooltip chip).
_CHIP_LABELS = {
    "_s1": "S1 · Lonjakan vs rata-rata",
    "_s2": "S2 · Lonjakan vs hari aktif",
    "_s3": "S3 · Lonjakan vs nilai tengah",
    "_s4": "S4 · Terpusat di satu hari",
    "_s5": "S5 · Jauh di atas hari kedua",
    "_s6": "S6 · Puncak vs BOM",
    "_s7": "S7 · Total vs BOM",
    "_s8": "S8 · Puncak vs cabang lain",
    "_s9": "S9 · Total vs cabang lain",
    "_s10": "S10 · Waste hanya 1 hari",
    "_s11": "S11 · Menumpuk di hari terakhir",
    "_s12": "S12 · Pola 10× (salah ketik?)",
}

# v2.9.0 — tooltip chip sinyal: penjelasan Bahasa awam + angka threshold
# + apa yang biasanya diperiksa. Hover chip = langsung paham.
_CHIP_TIPS = {
    "_s1": ("Nilai waste di satu hari ≥ 3× rata-rata harian item yang sama.\n"
             "Sering karena salah ketik angka (mis. 7 → 70) — cek tanggal "
             "di HARI TERSANGKA."),
    "_s2": ("Nilai terbesar ≥ 2,5× rata-rata HARI YANG ADA WASTENYA saja.\n"
             "Lebih adil dari S1: hari kosong tidak menarik rata-rata turun."),
    "_s3": ("Nilai terbesar ≥ 3× nilai tengah (median) hari aktif.\n"
             "Nilai tengah tahan terhadap 1 hari ekstrem — lonjakan besar "
             "di sini lebih kuat mencurigakan."),
    "_s4": ("≥ 50% waste sebulan terjadi di SATU hari (≥ 70% = skor penuh).\n"
             "Waste terpusat satu tanggal — cek apa kejadian nyata."),
    "_s5": ("Nilai terbesar ≥ 3× nilai terbesar kedua.\n"
             "Puncaknya menjulang sendirian — bukan pola harian biasa."),
    "_s6": ("Nilai terbesar SEHARI ≥ 25% penjualan SEMBULAN (≥ 50% = skor penuh).\n"
             "BOM = qty penjualan (bukan waste)."),
    "_s7": ("Total waste sebulan ≥ 50% penjualan (≥ 100% = skor penuh).\n"
             "BOM = qty penjualan (bukan waste)."),
    "_s8": ("Nilai terbesar ≥ 2× nilai tengah cabang lain, item sama "
             "(≥ 3× = skor penuh). Butuh ≥ 3 cabang pembanding."),
    "_s9": ("Total sebulan ≥ 3× nilai tengah total cabang lain (item sama).\n"
             "Butuh ≥ 3 cabang pembanding."),
    "_s10": ("Waste baris ini hanya terjadi 1 hari sebulan + nilainya besar\n"
              "(≥ 10% penjualan atau ≥ 2× cabang lain)."),
    "_s11": ("≥ 70% waste sebulan menumpuk di HARI TERAKHIR periode.\n"
              "Pola tumpukan akhir bulan — cek input hari terakhir."),
    "_s12": ("Nilai ≈ 10× / 100× / 1000× nilai tengah sendiri — pola khas "
              "salah ketik digit tambahan (7 → 70 → 700).\n"
              "Tab Hari Mencurigakan menunjukkan tanggalnya."),
}
SIGNALS: list[tuple[str, str, str]] = [
    (col, _CHIP_LABELS[col], frag) for col, frag in SIGNAL_PARTS
]

# Metrik konteks yang ditampilkan di detail pop-up (bila kolomnya ada)
DETAIL_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO", "NAMA BARANG",
    "JENIS", "KETERANGAN", "SOURCE DATA", "TOTAL", "MAX", "AVG",
    "HARI MAX", "SATUAN", "TOTAL BOM", "% to BOM", "PEER COUNT",
    "PEER MEDIAN TOTAL", "PEER MEDIAN MAX", "TOTAL / PEER MEDIAN",
    "MAX / PEER MEDIAN MAX", "MAX / BOM", "TOTAL / BOM", "MAX SHARE",
    # v2.10.2: bukti perubahan vs bulan lalu (tampil bila pembanding ada)
    "BULAN LALU", "PERUBAHAN %", "PERUBAHAN",
    "LAST DAY SHARE", "KATEGORI ANOMALI", "RANGKING WASTE",
]


class DetailPanel(Card):
    """Panel detail satu baris anomali: identitas + sinyal + drill-down.

    v2.8.1: panel ini tinggal DI DALAM DetailDialog (pop-up) — bukan lagi
    bagian splitter di bawah tabel.
    """

    # Prompt default — dipakai __init__ DAN clear() (V26-L12)
    _PROMPT = ("Klik baris anomali di tabel untuk menampilkan detailnya "
               "di sini (12 sinyal, peer, uang).")

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._title = WLabel(self._PROMPT, self)
        self._title.setObjectName("cardTitle")
        lay.addWidget(self._title)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self._scroll, 1)
        self._content = QWidget()
        self._scroll.setWidget(self._content)

    def clear(self) -> None:
        """Kosongkan panel (V26-L12): df terfilter berubah → record yang
        sedang ditampilkan bisa jadi sudah tidak lolos filter — jangan
        biarkan panel menampilkan data basi (pola teardown show_record)."""
        self._title.setText(self._PROMPT)
        old = self._content.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

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

        # Grid 12 sinyal — chip merah bila terpicu
        reasons_raw = rec.get("ANOMALY REASONS")
        reasons_text = "" if reasons_raw is None else str(reasons_raw)
        if reasons_text in ("nan", "None", "<NA>"):
            reasons_text = ""
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        for i, (col, label, fragment) in enumerate(SIGNALS):
            val = rec.get(col, 0)
            try:
                val = float(pd.to_numeric(pd.Series([val])).iloc[0])
            except Exception:
                val = 0.0
            # v2.7.0: baca dari fragmen ANOMALY REASONS (data riil) ATAU
            # nilai _s* bila kolom hadir (fixture sintetis) — lihat komentar
            # SIGNALS di atas.
            triggered = (val > 0) or (fragment in reasons_text)
            if triggered:
                fg, bg = "#dc2626", "#fef2f2"
                text = (f"{label} ✓ ({fmt_id(val, 0)})" if val > 0
                        else f"{label} ✓")
            else:
                fg, bg = "#64748b", "#f1f5f9"
                text = label
            chip = StatusChip(text, fg, bg)
            # v2.9.0: hover chip = penjelasan sinyal Bahasa awam
            # (permintaan user: tooltip SEMUA istilah, bukan hanya S-1).
            tip = _CHIP_TIPS.get(col, "")
            if tip:
                chip.setToolTip(tip)
            gl.addWidget(chip, i // 3, i % 3)
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
                # v2.9.0: label metrik + nilai dapat tooltip kamus istilah
                tip = COLUMN_TOOLTIPS.get(col)
                if tip:
                    key.setToolTip(tip)
                # v2.8.1: kolom rasio (BOM/SHARE) tampil sebagai persen —
                # '0,00080' mentah tak terbaca manusia.
                val = rec.get(col)
                shown = (fmt_pct(val) if col in PCT_COLS
                         else fmt_delta_pct(val) if col in DELTA_PCT_COLS
                         else fmt_ratio_x(val) if col in RATIO_X_COLS
                         else fmt_cell(val))
                val_lbl = WLabel(shown, metrics)
                val_lbl.setStyleSheet("font-weight:600;")
                if tip:
                    val_lbl.setToolTip(tip)
                fl.addRow(key, val_lbl)
        lay.addWidget(metrics)

        # Peta hari 1-31 (v2.9.0): nilai waste per hari dalam mini-grid —
        # hari tersangka disorot merah. "Grafik batang" tanpa matplotlib:
        # 31 sel kecil (8 per baris) menunjukkan di tanggal mana angka
        # besar itu duduk — jawaban visual utk "potensi salah angka di
        # tanggal berapa".
        lay.addWidget(self._section(
            "Nilai per hari (1–31) — sel merah = hari tersangka"))
        lay.addWidget(self._day_map(rec))

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

    def _day_map(self, rec: pd.Series) -> QWidget:
        """Mini-grid 31 sel: nilai per hari; hari tersangka merah (v2.9.0).

        Sel berisi 'hari: nilai' bila ada wastenya, nomor hari saja (redup)
        bila kosong. Tooltip sel = 'Hari N: nilai X'. Data dari kolom hari
        '1'..'31' (ada di df hasil pipeline) + HARI TERSANGKA / HARI MAX.
        """
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(3)
        day_cols = [c for c in (str(i) for i in range(1, 32))
                    if c in rec.index]
        tersangka = None
        for src in ("HARI TERSANGKA", "HARI MAX"):
            v = rec.get(src)
            try:
                if v is not None and not pd.isna(v):
                    tersangka = int(float(v))
                    break
            except (TypeError, ValueError):
                pass
        for i, name in enumerate(day_cols):
            hari = int(name)
            v = pd.to_numeric(pd.Series([rec.get(name)]),
                              errors="coerce").iloc[0]
            has_val = v == v and v and v > 0
            if has_val:
                text = f"{hari}:{fmt_cell(v, 0)}"
            else:
                text = str(hari)
            cell = QLabel(text)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setMinimumWidth(74)
            if hari == tersangka:
                cell.setStyleSheet(
                    "background:#fee2e2; color:#dc2626; font-weight:700; "
                    "border-radius:4px;")
            elif has_val:
                cell.setStyleSheet(
                    "background:#f1f5f9; color:#334155; "
                    "border-radius:4px;")
            else:
                cell.setStyleSheet(
                    "color:#cbd5e1; background:transparent;")
            tip_val = fmt_cell(v, 1) if has_val else "kosong"
            cell.setToolTip(f"Hari {hari}: {tip_val}")
            gl.addWidget(cell, i // 8, i % 8)
        return host


class DetailDialog(QDialog):
    """Pop-up detail baris anomali (v2.8.1) — pengganti panel inline.

    Non-modal: tabel tetap bisa diklik / di-sort / di-scroll saat pop-up
    terbuka. Satu instance dipakai ulang — setiap klik baris memperbarui
    isi pop-up yang sama (bukan menumpuk jendela baru). Tutup lewat X
    kapan saja; klik baris lain membukanya kembali.
    """

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detail Anomali — 12 Sinyal & Pembanding")
        self.setModal(False)
        self.resize(920, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._panel = DetailPanel(ctx, self)
        lay.addWidget(self._panel)

    def show_record(self, rec: pd.Series) -> None:
        """Tampilkan record di panel + munculkan pop-up di depan."""
        self._panel.show_record(rec)
        self.show()
        self.raise_()
        self.activateWindow()


class AnomaliView(QWidget):
    """View 'Anomali': KPI + tabel ranking (penuh) + pop-up detail."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # KPI strip (nilai mengikuti filter — DD-M3)
        self._kpi = KpiStrip(self)
        lay.addWidget(self._kpi)

        # Bar kontrol: ambang skor + jumlah anomali + filter perubahan
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
        # v2.10.2 — filter kuadran perubahan vs bulan lalu (permintaan user:
        # "analisa dengan perubahan yang tinggi atau rendah"). Filter LOKAL
        # view (bukan state) — kolom PERUBAHAN hanya ada setelah enrich.
        lbl_chg = WLabel("Perubahan:", ctrl)
        lbl_chg.setToolTip(
            "Saring anomali menurut perubahan totalnya vs bulan lalu:\n"
            "• Naik Tinggi = lonjakan baru (kandidat salah input / "
            "kejadian baru);\n"
            "• Stabil = waste kronis (sudah tinggi tiap bulan — masalah "
            "proses, bukan salah ketik);\n"
            "• Baru = belum ada riwayat bulan lalu.\n"
            "Butuh file pembanding di tab 'Banding Periode'.")
        cl.addWidget(lbl_chg)
        self._cb_change = QComboBox(ctrl)
        self._cb_change.addItem("Semua", None)
        for cat in CHANGE_CATEGORIES:
            icon = {"Baru": "🆕", "Naik Tinggi": "🔺", "Naik Sedang": "↗",
                    "Stabil": "➡️", "Turun": "↘", "Turun Tinggi": "🔻"}.get(
                        cat, "")
            self._cb_change.addItem(f"{icon} {cat}", cat)
        self._cb_change.setToolTip(lbl_chg.toolTip())
        self._cb_change.setEnabled(False)  # aktif begitu pembanding ada
        self._cb_change.currentIndexChanged.connect(
            lambda _i: self._on_change_filter())
        cl.addWidget(self._cb_change)
        self._lbl_count = WLabel("", ctrl)
        self._lbl_count.setObjectName("hint")
        cl.addWidget(self._lbl_count, 1)
        lay.addWidget(ctrl)

        # Kartu tabel — memenuhi SELURUH sisa tinggi view (v2.8.1: tanpa
        # splitter/panel inline; detail hadir sebagai pop-up saat baris
        # diklik).
        table_card = Card(self)
        table_card.setMinimumHeight(240)
        tcl = QVBoxLayout(table_card)
        tcl.setContentsMargins(12, 10, 12, 10)
        tcl.setSpacing(6)
        # v2.8.0: judul satu baris (dulu wrap 2-3 baris — makan ±100px).
        title = WLabel("Tabel Anomali Ter-ranking", table_card)
        title.setObjectName("cardTitle")
        tcl.addWidget(title)
        # v2.11.0: slicer multi-select (JENIS·KETERANGAN·STATUS) di atas
        # tabel — state global ctx.active_filters (chip antar-tab sinkron
        # otomatis). Banding Periode sengaja tanpa slicer (file ≠ baris).
        self._slicer = SlicerBar(ctx, table_card)
        tcl.addWidget(self._slicer)
        self._table = DataTable(table_card)
        self._table.setMinimumHeight(200)
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        self._table.double_clicked.connect(self._on_double)
        tcl.addWidget(self._table, 1)
        # v2.8.1: hint baru — perilaku pop-up (dulu: 'pilih baris utk
        # detail' ke panel inline, dihapus bersama splitter).
        hint = WLabel(
            "💡 Klik baris = detail pop-up · klik 2× = fokus cabang+item · klik header = sort · "
            "kolom BULAN LALU/PERUBAHAN muncul bila ada file pembanding (tab Banding Periode)",
            table_card)
        hint.setObjectName("hint")
        tcl.addWidget(hint)
        lay.addWidget(table_card, 1)

        # Pop-up detail (v2.8.1) — satu instance dipakai ulang.
        self._popup = DetailDialog(ctx, self)

        # Reaksi state — pola lazy H2: view tak terlihat → tandai dirty,
        # render saat dibuka (on_shown). View default biasanya terlihat saat
        # pipeline selesai → render langsung.
        self._dirty = True
        # v2.7.0 (V26-L4): guard coalesce — _on_double menerapkan dua filter
        # sekaligus TANPA render perantara (satu render di akhir).
        self._batch_filters = False
        # v2.10.2: versi cache enrich (df + baseline + data/history) —
        # kombinasi sama → salinan berkolom sama dipakai ulang.
        self._change_key: tuple | None = None
        self._change_df: pd.DataFrame | None = None
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)
        # v2.10.2: pembanding siap / pilihan combo berganti → kolom
        # BULAN LALU-PERUBAHAN muncul / dihitung ulang.
        ctx.history_ready.connect(self._on_history_ready)
        ctx.baseline_changed.connect(self._on_baseline_changed)

    def _on_data_ready(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def _on_filters_changed(self) -> None:
        if self._batch_filters:
            return  # render di-coalesce oleh _on_double (V26-L4)
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_history_ready(self) -> None:
        """Pembanding selesai dimuat → kolom perubahan bisa dihitung."""
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_baseline_changed(self) -> None:
        """Combo 'Banding dengan:' berganti → hitung ulang vs bulan itu."""
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_change_filter(self) -> None:
        """Combo kategori perubahan → saring tabel (lokal, tanpa state).

        Tanpa guard isVisible: combo hanya bisa diklik saat view terlihat,
        dan pemanggilan programatik (test / refresh eksternal) tetap bekerja.
        (Pola _on_score_changed — aksi kontrol = refresh langsung.)"""
        self._refresh_table()

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
        """v2.8.3 — titik tunggal SEMUA jalur render tabel (filter/search/
        rentang hari/Hapus Filter/drill-down/dataset baru) dibungkus
        busy_feedback: cursor sibuk + pesan status "⏳ …" dipasang SEBELUM
        kerja berat sinkron (auto-fit kolom + ukur tinggi baris per sel;
        diukur data asli: 75–460 ms sandbox = 1–2+ dtk di laptop user) —
        proses terlihat 'masih jalan', bukan beku senyap. Selesai → durasi
        dilaporkan ke status bar."""
        with busy_feedback(self._ctx.set_status, "Menyaring & menampilkan data"):
            self._refresh_table_impl()

    def _refresh_table_impl(self) -> None:
        # v2.7.0 (V26-L12): dataset/filter berubah → seleksi + detail lama
        # bisa basi (record terpilih mungkin sudah tak lolos filter) —
        # kosongkan keduanya (model reset mengosongkan seleksi).
        # v2.8.1: panel detail kini di pop-up → tutup + kosongkan.
        self._table.clearSelection()
        self._popup.hide()
        self._popup._panel.clear()
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
        # v2.10.2 — kolom perubahan vs bulan lalu (permintaan user: "persen
        # perubahan ke anomali sebagai analisa perubahan tinggi/rendah").
        # Enrich di SALINAN (kontrak 'konsumen hanya membaca' — mem-memo per
        # (df, baseline, versi) supaya refresh dgn state sama mengembalikan
        # objek sama → cache fit DataTable tetap kena).
        baseline = self._ctx.banding_baseline_effective()
        if baseline is not None and not df.empty:
            key = (id(df), self._ctx.data_version, self._ctx.history_version,
                   id(baseline))
            if self._change_key != key:
                with busy_feedback(
                        self._ctx.set_status,
                        "Menghitung perubahan vs bulan lalu"):
                    df = change_vs_history(df, baseline, self._ctx.config)
                self._change_key = key
                self._change_df = df
            else:
                df = self._change_df
        # Filter kategori perubahan (LOKAL view — bukan state): hanya
        # menyaring tampilan, KPI/label lain tidak terpengaruh.
        cat = self._cb_change.currentData() if self._cb_change.isEnabled() \
            else None
        self._cb_change.setEnabled(baseline is not None)
        if cat and "PERUBAHAN" in df.columns:
            df = df[df["PERUBAHAN"] == cat]
        cols = [c for c in TABLE_COLS if c in df.columns]
        # v2.7.0 (V26-C1): model memegang df PENUH (bukan irisan TABLE_COLS
        # lagi) — kolom non-tabel disembunyikan via visible_cols. Record
        # terpilih / double-klik tetap membawa SEMUA kolom (12 sinyal,
        # ANOMALY REASONS, peer, MAX, ...) ke pop-up detail + drill-down.
        # v2.8.1: 8 kolom + sidebar membuat lantai header melebihi viewport
        # laptop (1024) — JENIS & KETERANGAN masuk narrow_hide (disembunyikan
        # responsif saat sempit, muncul lagi saat melebar; alasan tetap ada
        # di pop-up detail) supaya kolom inti + % to BOM tetap muat TANPA
        # scrollbar horizontal.
        # v2.10.2: kolom perubahan ikut narrow_hide — 11 kolom di laptop
        # sempit; kolom PERUBAHAN % tetap prioritas tampak.
        self._table.set_dataframe(df, sort_desc="ANOMALY SCORE",
                                  narrow_hide=["JENIS", "KETERANGAN",
                                               "BULAN LALU", "PERUBAHAN"],
                                  visible_cols=cols)
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if len(df) == 0:
            self._lbl_count.setText("0 anomali lolos filter — longgarkan filter atau ambang skor.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(len(df))} anomali tampil (dari {fmt_id(full)} baris data)")
        self._refresh_kpi()

    def _refresh_kpi(self) -> None:
        filtered = self._ctx.filtered_df()
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if filtered is not None:
            self._kpi.update_from(filtered, full)

    def _on_selection(self) -> None:
        """Klik baris (atau navigasi keyboard) → pop-up detail (v2.8.1)."""
        rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    def _on_double(self, rec: pd.Series) -> None:
        """Klik 2×: fokus cabang+item sekaligus (drill-down P8).

        v2.7.0 (V26-L4): dua set_filter = dua broadcast filters_changed =
        dua render (regresi coalesce v2.5.1 DD-L2). Guard _batch_filters
        menelan render perantara; kedua filter tetap diterapkan lalu tabel
        di-render SEKALI di akhir (tanpa menyentuh ui/state.py).
        """
        self._batch_filters = True
        try:
            if rec.get("NAMA RESTO") is not None:
                self._ctx.set_filter("cabang", rec.get("NAMA RESTO"))
            if rec.get("NAMA BARANG") is not None:
                self._ctx.set_filter("item", rec.get("NAMA BARANG"))
        finally:
            self._batch_filters = False
        self._refresh_table()
