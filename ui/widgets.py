"""widgets.py — blok bangunan UI anti-terpotong (v2.6.0).

Jaminan struktural "tidak ada teks terpotong":
- WLabel: word-wrap default — teks selalu pindah baris, bukan terpotong
- DataTable: QTableView virtualized (tanpa cap 500 baris), lebar kolom dari
  sampel isi + wrap teks panjang + tooltip sel
- KpiCard/KpiStrip: kartu KPI dengan wrap

v2.8.1: MplCanvas / ChartCard / place_charts_responsive DIHAPUS —
infrastruktur chart hanya dipakai view Jelajah & Waktu (dihapus total).
Import matplotlib juga hilang dari jalur start-up UI.
"""
from __future__ import annotations

import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager

import pandas as pd
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHeaderView,
    QLabel,
    QLayout,
    QLayoutItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from .models import PandasTableModel
from .shared import fmt_id
from .theme import STATUS_COLORS
from waste_anomaly.utils import norm_text


# ============================================================
# v2.8.3 — feedback "masih proses" untuk kerja sinkron yang berat
# ============================================================
@contextmanager
def busy_feedback(status_cb=None, label: str = "Memproses"):
    """WaitCursor + pesan status SELAMA kerja sinkron di thread UI.

    Diagnosa freeze apply/unapply filter (data asli 25.901 baris, offscreen):
    rantai set_filter → filters_changed → _refresh_table sinkron 75–460 ms
    di sandbox; di laptop user (Windows, 2-4× lebih lambat) = 1-2+ detik
    UI beku TANPA umpan balik — terasa seperti hang. Helper ini:
    (1) pasang cursor sibuk + pesan status "⏳ …" SEBELUM kerja berat,
    (2) processEvents() agar cursor/pesan benar-benar tergambar dulu,
    (3) pulihkan cursor + laporkan durasi saat selesai.
    Aman bersarang (cursor stack Qt) dan aman dipakai lintas view.
    """
    QApplication.setOverrideCursor(Qt.BusyCursor)
    if status_cb is not None:
        status_cb(f"⏳ {label}…", "busy")
    QApplication.processEvents()
    t0 = time.perf_counter()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()
        if status_cb is not None:
            ms = (time.perf_counter() - t0) * 1000
            status_cb(f"✓ {label} selesai ({ms:.0f} ms)", "done")


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
        self._visible_cols: list[str] | None = None  # v2.7.0: kolom tampak (V26-C1)
        self._in_fit = False  # v2.7.0 (V26-M4): guard umpan-balik sectionResized
        # v2.9.0 (perf): cache hasil _auto_columns+_refit_rows LRU per objek
        # df — unfilter/drill bolak-balik mengembalikan df PERSIS sama (memo
        # state.anomali_df) → lebar kolom + tinggi baris tinggal dipasang
        # ulang TANPA pengukuran (diukur v2.8.3: pengukuran 220-460 ms per
        # render; hit ≈ 10 ms). Entri hanya disimpan saat urutan baris =
        # urutan sort default (deterministik: df sama → urutan sama); sort
        # user mengubah tinggi per baris → entri tak boleh ditimpa.
        self._fit_cache: OrderedDict[tuple, dict] = OrderedDict()
        self._src_df: pd.DataFrame | None = None  # df terakhir (strong ref)
        self._src_key: tuple | None = None
        self._default_order = True  # urutan model == urutan sort default?
        # v2.9.0: waktu (monotonic) fit programatik TERAKHIR — layout
        # Qt yang di-queue bisa memancarkan sectionResized UTk lebar yang
        # BARU kita pasang sendiri SETELAH _in_fit berakhir (deferred);
        # jangan anggap itu drag user (bukti: kolom ANOMALY SCORE idx 77
        # 132→136 tiap pasca-hit) → jendela tenang 300ms.
        self._fit_ts: float = -1.0
        # v2.7.0 (V26-M4/L9): resize kolom manual → tinggi baris wrap harus
        # dihitung ulang; DEBOUNCE 120ms mencegah refit berkali-kali selama
        # drag (flicker). Lebar yang dipasang sendiri oleh _auto_columns /
        # _refit_rows diabaikan via _in_fit (loop umpan-balik).
        self._refit_timer = QTimer(self)
        self._refit_timer.setSingleShot(True)
        self._refit_timer.setInterval(120)
        self._refit_timer.timeout.connect(lambda: self._refit_rows())
        self.doubleClicked.connect(self._on_double)
        # Sort by header → tinggi baris harus dihitung ulang (baris visual
        # berganti isi; tinggi lama tidak cocok → teks wrap terpotong).
        # v2.9.0: juga tandai urutan non-default → entri cache fit untuk
        # df ini tidak boleh ditimpa tinggi urutan lain.
        self.horizontalHeader().sortIndicatorChanged.connect(
            self._on_sort_changed)
        self.horizontalHeader().sectionResized.connect(
            self._on_section_resized)

    def _on_sort_changed(self, *_args) -> None:
        self._default_order = False
        self._refit_rows()

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
        self._in_fit = True  # jangan picu sectionResized-handler saat setRowHeight
        try:
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
        finally:
            self._in_fit = False

    def _on_section_resized(self, logical: int, _old: int, _new: int) -> None:
        """Resize kolom (drag user / program) → jadwal refit tinggi baris.

        Refit di-DEBOUNCE lewat timer single-shot 120ms — selama drag hanya
        timer yang di-restart (bukan refit penuh per piksel → flicker V26-L9).
        v2.9.0: drag user = preferensi manual — entri cache fit utk df ini
        tidak lagi valid (lebar tersimpan ≠ lebar sekarang) → buang supaya
        render berikutnya mengukur ulang jujur, bukan memasang lebar basi.
        KECUALI kolom TERAKHIR: stretchLastSection aktif → kolom terakhir
        diatur OTOMATIS Qt tiap viewport berubah (scrollbar muncul/hilang
        ±14px) — resize itu BUKAN preferensi user; membuang entri di sini
        membuat unfilter berikutnya selalu miss (terbukti diag: unfilter #2
        436ms padahal #1 93ms). Tinggi baris tetap dijadwalkan ulang.
        """
        if self._in_fit:
            return  # lebar dipasang oleh _auto_columns/_refit_rows sendiri
        header = self.horizontalHeader()
        stretch_last = (header.stretchLastSection()
                        and logical == header.count() - 1)
        # v2.9.0: hanya resize kolom YANG KITA KELOLA (kolom tampak — ada
        # di entri widths) LEBIH DARI 300ms setelah fit programatik kita
        # yang dianggap preferensi-drag user. Qt internal (reset model /
        # layout deferred / stretch) me-resize kolom managed & unmanaged
        # di luar _in_fit (terbukti diag: kolom idx 77 ±4px setiap render,
        # bahkan lebar yang BARU kita pasang sendiri) — resize itu TIDAK
        # boleh membuang entri cache (kalau dibuang, unfilter berikutnya
        # selalu miss: 440ms vs 98ms).
        entry = self._fit_cache.get(self._src_key) \
            if self._src_key is not None else None
        managed = entry is not None and logical in entry["widths"]
        quiet = (time.monotonic() - self._fit_ts) < 0.3
        if (entry is not None and not stretch_last and managed and not quiet):
            del self._fit_cache[self._src_key]
        if not quiet and 0 < self._model.rowCount() <= 3000:
            self._refit_timer.start()

    def _on_double(self, index) -> None:
        rec = self._model.record(index.row())
        if rec is not None:
            self.double_clicked.emit(rec)

    def set_dataframe(self, df: pd.DataFrame | None,
                      sort_desc: str | None = None,
                      narrow_hide: list[str] | None = None,
                      visible_cols: list[str] | None = None) -> None:
        """Tampilkan df; ``sort_desc`` = nama kolom utk sort default DESC.

        ``narrow_hide`` (v2.6.1): nama kolom yang BOLEH disembunyikan —
        secara berurutan — bila lantai header tak muat di viewport sempit
        (tabel responsif). Disembunyikan ≠ terpotong: kolom inti tetap
        tampil; kolom disembunyikan muncul kembali saat window melebar.

        ``visible_cols`` (v2.7.0, V26-C1): model tetap memegang df PENUH —
        kolom di LUAR visible_cols disembunyikan (setColumnHidden, persisten
        lintas _auto_columns) tapi TIDAK dibuang. ``selected_record()`` /
        ``double_clicked`` lalu mengembalikan record PENUH (semua kolom) —
        panel detail / drill-down mendapat data lengkap. None/[] = semua
        kolom tampak (perilaku lama — view lain tak terdampak).
        """
        self._narrow_hide = list(narrow_hide or [])
        self._visible_cols = list(visible_cols) if visible_cols else None
        self._model.set_dataframe(df)
        # V26-M3: tabel raksasa (>3000 baris) — _refit_rows di-skip demi
        # kecepatan; bila word-wrap tetap nyala, teks multi-baris TERPOTONG
        # VERTIKAL (tinggi baris tetap default). Ganti strategi: wrap mati +
        # elide kanan '…' — tooltip sel tetap menampilkan teks penuh
        # (konvensi terdokumentasi), baris tidak terpotong.
        big = df is not None and len(df) > 3000
        self.setWordWrap(not big)
        self.setTextElideMode(
            Qt.TextElideMode.ElideRight if big
            else Qt.TextElideMode.ElideNone)
        # v2.9.0 (perf): cari hasil fit utk df PERSIS ini (objek sama via
        # memo state.anomali_df) → render unfilter/drill-balik jadi pasang
        # ulang lebar+tinggi tanpa pengukuran. avail dicek: viewport berubah
        # (window di-resize) → ukur ulang.
        fit: dict | None = None
        if df is not None:
            key = (id(df), len(df), tuple(map(str, df.columns)),
                   tuple(self._visible_cols or ()), tuple(self._narrow_hide))
            cand = self._fit_cache.get(key)
            if cand is not None and cand["ref"]() is df:
                self._fit_cache.move_to_end(key)
                # toleransi ±20px: lebar scrollbar vertikal (~14px) muncul/
                # hilang saat jumlah baris berubah — bukan perubahan window;
                # lebar tersimpan tetap valid (stretch-terakhir menyerap
                # selisih, layout konvergen sendiri).
                if abs((self.viewport().width() - 4) - cand["avail"]) <= 20:
                    fit = cand
            self._src_key = key
        else:
            self._src_key = None
        self._src_df = df
        # v2.9.0: setSortIndicator EMIT sortIndicatorChanged (handler
        # men-set _default_order=False) — set ulang True SETELAH sort
        # bawaan dipasang agar entri cache boleh disimpan (urutan default
        # deterministik: df sama → urutan sort sama).
        if sort_desc and df is not None and sort_desc in df.columns:
            self._default_order = False
            col = list(df.columns).index(sort_desc)
            self.horizontalHeader().setSortIndicator(
                col, Qt.DescendingOrder)
            self._model.sort(col, Qt.DescendingOrder)
            self._default_order = True
        self._pending_fit = True
        self._auto_columns(fit=fit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Kolom belum ter-fit pas saat data pertama kali datang (viewport
        # belum berukuran final) → fit ulang sekali saat ukuran stabil.
        # v2.6.1: re-fit JUGA saat lebar viewport berubah (window di-resize) —
        # tanpa ini kolom memakai lebar window lama: kolom terakhir terpotong
        # di tepi + scrollbar muncul padahal sebenarnya muat. Ambang 24px
        # mencegah loop umpan-balik kemunculan scrollbar (~14px).
        # v2.8.1: scrollbar vertikal dapat muncul SETELAH fit (layout final)
        # menyusutkan viewport ~14px < ambang → fit basi → header lebih
        # panjang dari viewport → sliver scrollbar horizontal. Cek panjang
        # HEADER (otoritatif, tak bergantung timing scrollbar) → re-fit;
        # konvergen (Σ ≤ avail → stretch pas → length == viewport → stabil).
        vw = self.viewport().width()
        dust_overflow = self.horizontalHeader().length() > vw + 2
        if vw > 50 and self.isVisible() and (
                self._pending_fit or abs(vw - self._last_fit_w) > 24
                or dust_overflow):
            self._auto_columns()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        vw = self.viewport().width()
        dust_overflow = self.horizontalHeader().length() > vw + 2
        if vw > 50 and (
                self._pending_fit or abs(vw - self._last_fit_w) > 24
                or dust_overflow):
            self._auto_columns()

    def selected_record(self) -> pd.Series | None:
        idx = self.selectionModel().currentIndex()
        if idx.isValid():
            return self._model.record(idx.row())
        return None

    def _auto_columns(self, sample: int = 250, cap: int = 420,
                      min_w: int = 84, fit: dict | None = None) -> None:
        """Lebar kolom dari sampel isi + header, lalu di-FIT ke viewport.

        v2.9.0 (perf): parameter ``fit`` — entri cache LRU utk df PERSIS
        yang sama (lebar+tinggi+hidden terukur sebelumnya). Bila ada dan
        viewport tak berubah: pasang ulang tanpa pengukuran (unfilter/
        drill-balik; lihat docstring kelas). Bila tidak: jalur ukur penuh
        seperti sebelumnya + simpan hasilnya ke cache.

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
        n_cols = model.columnCount()
        avail = self.viewport().width() - 4
        if avail < 200:
            avail = 200
        # ================= FAST PATH (v2.9.0) =================
        # toleransi avail ±20px = lebar scrollbar (lihat set_dataframe).
        if fit is not None and fit.get("n_cols") == n_cols \
                and abs(avail - fit["avail"]) <= 20:
            self.setUpdatesEnabled(False)  # batch 400+ setRow/ColWidth
            self._in_fit = True
            try:
                for c in range(n_cols):
                    self.setColumnHidden(c, c in fit["hidden"])
                for c, w in fit["widths"].items():
                    self.setColumnWidth(c, w)
                for r, h in enumerate(fit["heights"]):
                    if h > 0:
                        self.setRowHeight(r, h)
            finally:
                self._in_fit = False
                self.setUpdatesEnabled(True)
            self._last_fit_w = self.viewport().width()
            if sum(fit["widths"].values()) <= avail + 2:
                self._pending_fit = False
            self._fit_ts = time.monotonic()  # jendela tenang anti false-drag
            return
        # ================= SLOW PATH (ukur penuh) =================
        n_rows = min(sample, model.rowCount())
        fm = self.fontMetrics()
        names = [str(model.headerData(c, Qt.Horizontal))
                 for c in range(n_cols)]
        # v2.7.0 (V26-C1): kolom di luar visible_cols disembunyikan permanen
        # dan DIKECUALIKAN dari semua perhitungan lebar (lantai/penyekalaan
        # hanya menghitung kolom yang benar-benar tampak).
        if self._visible_cols is not None:
            vis_hidden = {c for c in range(n_cols)
                          if names[c] not in self._visible_cols}
        else:
            vis_hidden = set()
        widths: list[int] = []
        floors: list[int] = []
        for c in range(n_cols):
            if c in vis_hidden:
                widths.append(0)  # placeholder — kolom hidden tak diukur
                floors.append(0)
                continue
            hw = fm.horizontalAdvance(names[c]) + 26
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
        # horizontal (scroll ≠ terpotong). narrow_hide menumpuk DI ATAS
        # visible_cols (kolom yang sudah permanen-hidden tidak dihitung dua
        # kali — floors-nya 0).
        hidden: set[int] = set()
        if self._narrow_hide and n_cols:
            total_f = sum(floors)
            for want in self._narrow_hide:
                if total_f <= avail:
                    break
                if want in names:
                    c = names.index(want)
                    if c not in hidden and c not in vis_hidden:
                        hidden.add(c)
                        total_f -= floors[c]
        keep = [c for c in range(n_cols)
                if c not in hidden and c not in vis_hidden]
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
        # Lebar/status kolom dipasang dalam mode _in_fit → handler
        # sectionResized mengabaikannya (loop umpan-balik, V26-M4).
        self._in_fit = True
        try:
            for c in range(n_cols):
                self.setColumnHidden(c, c in hidden or c in vis_hidden)
            for c in keep:
                self.setColumnWidth(c, final[c])
            self._last_fit_w = self.viewport().width()  # v2.6.1
            if sum(final.values()) <= avail + 2:
                self._pending_fit = False  # sudah pas — tidak perlu fit ulang
            if n_rows == 0 and keep:
                self.setColumnWidth(keep[0], max(final[keep[0]], 240))
        finally:
            self._in_fit = False
        # Wrap baris: teks panjang (RANGKING WASTE, Detail/Contoh KQ) tampil
        # UTUH — tinggi baris dihitung manual (lihat _refit_rows). Di-skip
        # utk tabel raksasa (25k×53) demi kecepatan (tooltip + fit kolom).
        self._refit_rows()
        self._fit_ts = time.monotonic()  # jendela tenang anti false-drag
        # v2.9.0 (perf): simpan hasil fit LRU utk df persis ini — dipakai
        # ulang saat df objek sama muncul lagi (unfilter / drill balik /
        # re-render tanpa perubahan). Hanya urutan default (sort bawaan)
        # yang boleh tersimpan: sort user mengubah tinggi per baris.
        if self._default_order and self._src_key is not None \
                and self._src_df is not None:
            heights = ([self.rowHeight(r) for r in range(model.rowCount())]
                       if 0 < model.rowCount() <= 3000 else [])
            self._fit_cache[self._src_key] = {
                "ref": weakref.ref(self._src_df),
                "avail": avail,
                "n_cols": n_cols,
                "widths": {c: final[c] for c in keep},
                "hidden": set(hidden) | set(vis_hidden),
                "heights": heights,
            }
            self._fit_cache.move_to_end(self._src_key)
            while len(self._fit_cache) > 8:
                self._fit_cache.popitem(last=False)


# ============================================================
# KPI
# ============================================================

class KpiCard(QFrame):
    """Kartu KPI: label kecil + angka besar + konteks (wrap)."""

    def __init__(self, title: str, color: str = "#0f172a",
                 parent: QWidget | None = None,
                 tooltip: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("kpiframe")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._title = WLabel(title, self)
        self._title.setObjectName("hint")
        lay.addWidget(self._title)
        # v2.9.0: penjelasan istilah di tooltip (permintaan user — semua
        # istilah harus mudah dicerna, bukan hanya sinyal S-1).
        if tooltip:
            self.setToolTip(tooltip)
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
        self.kpi_total = KpiCard("TOTAL BARIS", "#0f172a",
                                  tooltip="Banyak baris data yang lolos filter "
                                          "(semua status, termasuk Normal).")
        self.kpi_prioritas = KpiCard("PRIORITAS TINGGI", "#dc2626",
                                     tooltip="Anomali ber-skor ≥ 8 — periksa "
                                             "paling duluan.")
        self.kpi_potensi = KpiCard("POTENSI ANOMALI", "#ea580c",
                                   tooltip="Anomali ber-skor 5–7.")
        self.kpi_review = KpiCard("PERLU REVIEW", "#b45309",
                                  tooltip="Anomali ber-skor 3–4 — sisi batas, "
                                          "cek kalau sempat.")
        self.kpi_waste = KpiCard("TOTAL WASTE", "#0f766e",
                                 tooltip="Jumlah kolom TOTAL baris terfilter. "
                                         "Satuan bisa campur — anggap petunjuk "
                                         " kasar, bukan angka final.")
        self.kpi_cabang = KpiCard("CABANG", "#9333ea",
                                  tooltip="Banyak cabang berbeda pada data "
                                          "terfilter.")
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
            # v2.7.0 (V26-H4): skema unit_summary = SATUAN/rows/active_rows/
            # items/total/share_pct/raw_values — 'Total_Waste' TIDAK pernah
            # ada, fallback lama cols[1]='rows' menampilkan JUMLAH BARIS
            # seolah total waste. Pakai kolom 'total' (waste sesungguhnya)
            # + share_pct utk konteks.
            val_col = "total" if "total" in cols else None
            share_col = "share_pct" if "share_pct" in cols else None
            for _, r in us.head(3).iterrows():
                if val_col:
                    part = f"{r[name_col]}: {fmt_id(float(r[val_col]), 1)}"
                    if share_col:
                        share = float(r[share_col])
                        if share == share:  # bukan NaN
                            pct = f"{share:.1f}".replace(".", ",")
                            part += f" ({pct}%)"
                    parts.append(part)
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


# ============================================================
# v2.11.0 — SLICER: tombol filter kilat multi-select (pola Excel)
# ============================================================

# Dimensi slicer (urutan tampil): kunci state → label baris.
SLICER_DIMS: list[tuple[str, str]] = [
    ("jenis", "JENIS"),
    ("keterangan", "KETERANGAN"),
    ("status", "STATUS"),
]
# Urutan nilai tetap (bukan alfabetis) — WASTE dulu (subjek utama).
_JENIS_ORDER = ["WASTE", "SUSUT", "TRIAL"]
_STATUS_ORDER = ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]
# Debounce klik beruntun (ms) — pola search 300 ms (app.py), lebih cepat
# karena chip = 1 klik saja (bukan mengetik). 3 klik cepat = 1 render.
_SLICER_DEBOUNCE_MS = 150


class FlowLayout(QLayout):
    """Layout yang membungkus item ke baris berikutnya saat sempit.

    v2.11.0: dipakai SlicerBar — baris chip tidak pernah terpotong di
    jendela sempit; chip turun ke baris baru, urutan tetap kiri→kanan.
    (Implementasi pola FlowLayout klasik Qt, dipadatkan.)
    """

    def __init__(self, parent: QWidget | None = None,
                 hspacing: int = 6, vspacing: int = 4) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QLayoutItem | None:
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QLayoutItem | None:
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._do_layout(QRect(0, 0, w, 0), test=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = eff.x(), eff.y()
        line_h = 0
        for item in self._items:
            hint = item.sizeHint()
            nx = x + hint.width() + self._h
            if nx - self._h > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y += line_h + self._v
                line_h = 0
                nx = x + hint.width() + self._h
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + 1


class SlicerBar(QWidget):
    """Baris tombol filter kilat multi-select — JENIS·KETERANGAN·STATUS.

    v2.11.0: dipakai tab Anomali & Hari Mencurigakan (satu komponen,
    DUA instance — state tetap tunggal di ctx.active_filters sehingga
    chip antar-tab otomatis sinkron). Tab Banding Periode sengaja TIDAK
    memakai slicer (membandingkan file bulan, bukan baris data).

    Kontrak:
    - Klik chip = toggle nilai dalam set dimensi; klik beruntun di-
      koalesce debounce _SLICER_DEBOUNCE_MS → SATU set_filters_multi
      (satu broadcast → satu render, bukan satu per klik).
    - Nilai disimpan LIST pada active_filters (semantik _apply_filters
      sudah mendukung list semua dimensi — v2.5.1). Set kosong → []
      utk jenis / None utk keterangan+status (kanonik reset_filters).
    - Sinkron dua arah: combo sidebar (str) → chip aktif tunggal;
      chip → sidebar menampilkan placeholder 'beberapa dipilih'
      (lihat app._combo_set). Reset/profil/drill → semua chip ikut.
    - Sebelum ada data: bar disembunyikan (tanpa ruang kosong).
    """

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._chips: dict[str, dict[str, QToolButton]] = {
            k: {} for k, _ in SLICER_DIMS}
        self._pending: dict[str, list[str]] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_SLICER_DEBOUNCE_MS)
        self._timer.timeout.connect(self._apply_pending)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._rows: dict[str, tuple[QWidget, FlowLayout]] = {}
        for key, label in SLICER_DIMS:
            row = QWidget(self)
            hl = QVBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(2)
            head = QLabel(f"{label}:", row)
            head.setObjectName("muted")
            # child layout TANPA parent — row sudah punya QVBoxLayout
            # (QLayout(parent) akan bentrok: "already has a layout").
            flow = FlowLayout()
            hl.addWidget(head)
            hl.addLayout(flow)
            lay.addWidget(row)
            self._rows[key] = (row, flow)

        # Baris aksi: bersihkan ketiga dimensi slicer sekali klik.
        act = QWidget(self)
        al = FlowLayout()
        act.setLayout(al)
        al.setContentsMargins(0, 0, 0, 0)
        self._btn_clear = QToolButton(act)
        self._btn_clear.setText("✕ Bersihkan slicer")
        self._btn_clear.setObjectName("slicerChip")
        self._btn_clear.setToolTip(
            "Hapus pilihan JENIS + KETERANGAN + STATUS slicer ini\n"
            "(filter lain — cabang, pencarian, rentang hari — tidak disentuh).")
        self._btn_clear.clicked.connect(self._clear)
        al.addWidget(self._btn_clear)
        lay.addWidget(act)

        ctx.filters_changed.connect(self._sync_from_state)
        ctx.data_ready.connect(self._on_data_ready)
        self.setVisible(False)  # muncul begitu ada data

    # ------------------------------------------------------------
    # POPULASI NILAI
    # ------------------------------------------------------------
    def set_dim_values(self, key: str, values: list[str]) -> None:
        """Ganti kumpulan nilai satu dimensi (dataset baru)."""
        row, flow = self._rows[key]
        for btn in self._chips[key].values():
            flow.removeWidget(btn)
            btn.deleteLater()
        self._chips[key].clear()
        active = set(self._effective(key))
        for val in values:
            btn = QToolButton(row)
            btn.setText(val)
            btn.setCheckable(True)
            btn.setObjectName("slicerChip")
            btn.setToolTip(
                f"Klik = tampilkan hanya {val} (klik lagi = lepas).\n"
                "Bisa pilih beberapa sekaligus — hasil = gabungan.")
            if key == "status":
                # warna severity saat tercentang (QSS [sev=...])
                btn.setProperty("sev", val)
            btn.setChecked(val in active)
            btn.clicked.connect(
                lambda checked, k=key, v=val: self._on_chip(k, v, checked))
            flow.addWidget(btn)
            self._chips[key][val] = btn
        row.setVisible(bool(values))
        self.setVisible(any(self._chips[k] for k, _ in SLICER_DIMS))

    def _on_data_ready(self) -> None:
        """Dataset baru → ganti nilai chip (JENIS/KETERANGAN dari data;
        STATUS tetap 4 — filter sudah direset set_dataset)."""
        df = self._ctx.df
        if df is None:
            return
        if "JENIS" in df.columns:
            present = set(df["JENIS"].dropna().astype(str))
            jenis = [v for v in _JENIS_ORDER if v in present] + sorted(
                v for v in present if v not in _JENIS_ORDER)
            self.set_dim_values("jenis", jenis)
        if "KETERANGAN" in df.columns:
            # nilai ternormalisasi — SAMA dgn combo sidebar (app._on_data_ready)
            kets = sorted({norm_text(v)
                           for v in df["KETERANGAN"].dropna().astype(str)})
            self.set_dim_values("keterangan", kets)
        self.set_dim_values("status", list(_STATUS_ORDER))
        self._sync_from_state()

    # ------------------------------------------------------------
    # INTERAKSI CHIP
    # ------------------------------------------------------------
    def _effective(self, key: str) -> list[str]:
        """Set nilai dimensi saat ini (pending menang atas state)."""
        if key in self._pending:
            return list(self._pending[key])
        v = self._ctx.active_filters.get(key)
        if isinstance(v, list):
            return list(v)
        if isinstance(v, str) and v:
            return [v]
        return []

    def _on_chip(self, key: str, value: str, checked: bool) -> None:
        cur = self._effective(key)
        if checked and value not in cur:
            cur.append(value)
        elif not checked and value in cur:
            cur.remove(value)
        else:
            return
        self._pending[key] = cur
        self._timer.start()  # restart — klik beruntun = satu broadcast

    def _apply_pending(self) -> None:
        if not self._pending:
            return
        values = self._canonical(dict(self._pending))
        self._pending.clear()
        self._ctx.set_filters_multi(values)

    def _clear(self) -> None:
        """Klik '✕ Bersihkan slicer' — kosongkan ketiga dimensi."""
        self._timer.stop()
        self._pending.clear()
        self._ctx.set_filters_multi(
            self._canonical({key: [] for key, _ in SLICER_DIMS}))

    def _canonical(self, values: dict) -> dict:
        """[] utk jenis; None utk keterangan/status kosong (kanonik
        reset_filters) + urut stabil → tanda tangan LRU konsisten
        terlepas dari urutan klik."""
        out: dict = {}
        for key, vals in values.items():
            if not vals:
                out[key] = [] if key == "jenis" else None
            else:
                out[key] = sorted(vals)
        return out

    # ------------------------------------------------------------
    # SINKRON DARI STATE (sidebar / profil / drill / reset)
    # ------------------------------------------------------------
    def _sync_from_state(self) -> None:
        for key, chips in self._chips.items():
            if key in self._pending:
                continue  # klik user belum ter-apply — visual menang
            active = set(self._effective(key))
            for val, btn in chips.items():
                btn.setChecked(val in active)

    def chip(self, key: str, value: str) -> QToolButton | None:
        """Akses chip (test/E2E — klik programatik)."""
        return self._chips.get(key, {}).get(value)
