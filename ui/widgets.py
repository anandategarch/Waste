"""widgets.py — blok bangunan UI anti-terpotong (v2.6.0).

Jaminan struktural "tidak ada teks terpotong":
- WLabel: word-wrap default — teks selalu pindah baris, bukan terpotong
- DataTable: QTableView virtualized (tanpa cap 500 baris), lebar kolom dari
  sampel isi + wrap teks panjang + tooltip sel
- KpiCard/KpiStrip: kartu KPI dengan wrap

v2.8.1: MplCanvas / ChartCard / place_charts_responsive DIHAPUS —
infrastruktur chart hanya dipakai view Jelajah & Waktu (dihapus total).
Import matplotlib juga hilang dari jalur start-up UI.
v2.12.4: SlicerBar / FlowLayout DIHAPUS — funnel filter di header tabel
(v2.12.3) kini satu-satunya UI filter tabel (permintaan user: sidebar
filter kiri + slicer chip dihapus, semua kolom punya funnel).
"""
from __future__ import annotations

import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager

import pandas as pd
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QPushButton,
    QSizePolicy,
)

from .models import (
    DELTA_PCT_COLS,
    PCT_COLS,
    RATIO_X_COLS,
    PandasTableModel,
    fmt_cell,
    fmt_delta_pct,
    fmt_pct,
    fmt_ratio_x,
)
from .shared import fmt_id
from .theme import (
    C_BORDER,
    STATUS_COLORS,
    UI_FONT_FAMILY,
    UI_FONT_PX,
)


# ============================================================
# v2.12.3 — FILTER DI HEADER TABEL (Excel AutoFilter ala app ini)
# ============================================================
# Permintaan user: "daripada aku harus pakai slicer bisa gak ditampilkan
# semacam filter di header tabelnya? dan ada opsi sort gitu" — ikon
# funnel di ujung kanan judul kolom → menu: tombol sort (naik/turun) +
# daftar nilai bercentang + kotak cari. Semantik: nilai TERCENTANG =
# ikut tampil; semua tercentang = filter kolom lepas.
#
# v2.12.4 — funnel di SEMUA KOLOM (permintaan user: "harusnya semua
# kolom punya filter"): setup_header_filters(all_cols=True) menggambar
# funnel di SETIAP kolom tabel (kecuali kolom identitas yang di-skip —
# mis. kolom centang ✓). Kolom yang ada di mapping cols tetap
# memakai kunci ctx (state global lintas-tab); sisanya = kunci = nama
# kolom (filter lokal milik view).

_HF_ACTIVE = "#dc2626"   # funnel terisi merah = kolom sedang terfilter
_HF_IDLE = "#94a3b8"     # funnel garis tipis = tanpa filter
_HF_BG = "#f8fafc"       # background QSS QHeaderView::section (backing)
_HF_MAX_ITEMS = 400      # batas item daftar (kolom ribuan nilai → cari)
# v2.12.5: LEBBAR ZONA FUNNEL di ujung kanan section. Judul kolom
# dilukis Qt DI DALAM rect yang disempitkan sebesar zona ini (teks
# ter-ELIDE sebelum funnel — tidak pernah terpotong/tertutup ikon;
# v2.12.3-4 melukis teks di rect PENUH lalu menutup ekornya dgn
# backing → judul tampak terpotong di kolom lantai-lebar).
_HF_STRIP = 22
# v2.12.5: jeda lindungan setelah menu funnel tertutup — klik ganda
# "artefak" (klik penutup menu di-replay Qt ke baris tabel sebagai
# tekan#1, klik ke-2 user menjadi tekan#2 pada posisi sama → Qt
# menyintesis klik-ganda → pop-up drill detail terbuka sendiri)
# ditelan supaya tidak muncul saat/ setelah apply filter. Rentang =
# interval dobel-klik OS + margin (user tak mungkin mengarjakan
# klik-ganda sah sesegera itu setelah menutup menu).
_HF_HIDE_GUARD_S = 0.6


def _header_font() -> QFont:
    """Font judul kolom SEBAGAIMANA DILUKIS QSS — family chain + 13px +
    weight 600 (theme: UI_FONT_*). Dipakai _auto_columns utk lantai
    lebar jujur: ``self.font()`` TIDAK mewarisi font QSS (di Windows
    default 9pt vs QSS 13px → pengukuran kurang ~8% → ekor judul
    terpotong funnel; terbukti piksel: "ANOMALY SCORE" 111 vs 124)."""
    fam = [p.strip().strip('"') for p in UI_FONT_FAMILY.split(",")]
    f = QFont()
    f.setFamilies(fam)
    f.setPixelSize(UI_FONT_PX)
    f.setWeight(QFont.Weight.DemiBold)
    return f


def _paint_funnel(painter: QPainter, rect: QRect, active: bool) -> None:
    """Ikon funnel kecil DI DALAM zona strip kanan section (v2.12.5:
    tanpa backing — zona strip sudah dikosongkan dari teks oleh
    paintSection, jadi tidak ada lagi yang perlu ditutup)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx = float(rect.right()) - 12.0
    cy = float(rect.center().y())
    pts = QPolygonF([
        QPointF(cx - 5.0, cy - 4.0), QPointF(cx + 5.0, cy - 4.0),
        QPointF(cx + 2.0, cy + 2.0), QPointF(cx + 2.0, cy + 5.0),
        QPointF(cx - 2.0, cy + 5.0), QPointF(cx - 2.0, cy + 2.0),
    ])
    if active:
        painter.setPen(QColor(_HF_ACTIVE))
        painter.setBrush(QColor(_HF_ACTIVE))
    else:
        # idle: fill terang + outline gelap — terlihat jelas tanpa anti-
        # alias yang menipiskan garis 1px (diukur: outline polos nyaris tak
        # terbaca di background #f8fafc).
        painter.setPen(QColor("#64748b"))
        painter.setBrush(QColor("#cbd5e1"))
    painter.drawPolygon(pts)
    painter.restore()


# ============================================================
# v2.13.12 (gel-3 B9) — formatter nilai MENU FUNNEL = formatter SEL
# ============================================================
# Audit B9: menu funnel menampilkan float MENTAH ('1505252.0235695317')
# di samping sel tabel yang terformat ('+1.505.252,0%') — dua angka
# "beda" untuk kolom yang sama. Nilai menu kini diformat persis
# konvensi model _cell_text (PCT_COLS → fmt_pct, DELTA_PCT_COLS →
# fmt_delta_pct, RATIO_X_COLS → fmt_ratio_x, lainnya fmt_cell).
# None/NaN → '(kosong)' (fmt_* mengembalikan '' utk kosong) — dan
# value_counts(dropna=False) menawarkannya sebagai pilihan filter.

def _menu_value_fmt(col: str):
    """Formatter nilai menu funnel utk kolom ``col`` — SAMA formatter
    dgn sel tabelnya (konvensi model _cell_text). Return callable
    value → teks tampilan; dipakai _HeaderFilterMenu/_open_menu."""
    if col in PCT_COLS:
        return fmt_pct
    if col in DELTA_PCT_COLS:
        return fmt_delta_pct
    if col in RATIO_X_COLS:
        return fmt_ratio_x
    return fmt_cell


class _HeaderFilterMenu(QMenu):
    """Menu filter per kolom (v2.12.3) — filter nilai + opsi sort.

    Susunannya: [↗ Urut Naik] [↘ Urut Turun] · [kotiak cari] · daftar
    nilai (jumlah barisnya) · [☑ Pilih Semua] [Selesai]. Live-apply
    di-DEBOUNCE 120 ms — centang beruntun = satu broadcast. Menu tetap
    terbuka saat tabel ter-update di belakangnya (QMenu menutup saat
    klik di luar / tombol Selesai).
    """

    def __init__(self, view: QTableView, col: str, key: str,
                 counts: "OrderedDict[object, int]",
                 state: list | None, apply_fn, parent: QWidget,
                 fmt=None) -> None:
        super().__init__(parent)
        self._view = view
        self._col = col
        self._key = key
        self._counts = counts
        self._apply = apply_fn
        # v2.13.12 (gel-3 B9): formatter nilai = formatter sel tabel
        # kolom itu (None → fmt_cell — perilaku lama utk pemanggil lama).
        self._fmt = fmt if callable(fmt) else fmt_cell
        self._checked: dict[object, bool] = {}
        st = set(state) if state else None
        for v in counts:
            self._checked[v] = True if st is None else (v in st)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._apply_now)

        w = QWidget(self)
        w.setFixedWidth(290)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # — Baris sort (permintaan "ada opsi sort") —
        srow = QWidget(w)
        sl = QHBoxLayout(srow)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        b_up = QPushButton("↗ Urut Naik", srow)
        b_dn = QPushButton("↘ Urut Turun", srow)
        b_up.setToolTip("Urutkan tabel menurut kolom ini, terkecil/"
                        "A→Z duluan (klik judul kolom juga bisa).")
        b_dn.setToolTip("Urutkan tabel menurut kolom ini, terbesar/"
                        "Z→A duluan (klik judul kolom juga bisa).")
        b_up.clicked.connect(lambda: self._sort(Qt.SortOrder.AscendingOrder))
        b_dn.clicked.connect(lambda: self._sort(Qt.SortOrder.DescendingOrder))
        sl.addWidget(b_up, 1)
        sl.addWidget(b_dn, 1)
        lay.addWidget(srow)

        # — Kotak cari (kolom barang bisa ribuan nilai) —
        self._ed = QLineEdit(w)
        self._ed.setPlaceholderText("Cari nilai… (huruf besar/kecil sama)")
        self._ed.setClearButtonEnabled(True)
        self._ed.textChanged.connect(self._populate)
        lay.addWidget(self._ed)

        # — Daftar nilai bercentang —
        self._lw = QListWidget(w)
        self._lw.setMaximumHeight(300)
        self._lw.setToolTip(
            "Nilai TERCENTANG = ikut tampil (semantik slicer — chip di "
            "baris slicer ikut sinkron).\nSemua tercentang = filter kolom "
            "ini lepas.\nAngka dalam kurung = jumlah baris.")
        self._lw.itemChanged.connect(self._on_item)
        lay.addWidget(self._lw, 1)

        # — Baris aksi —
        arow = QWidget(w)
        al = QHBoxLayout(arow)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        b_all = QPushButton("☑ Pilih Semua", arow)
        b_all.setToolTip("Centang semua nilai = lepas filter kolom ini.")
        b_all.clicked.connect(self._pick_all)
        b_ok = QPushButton("Selesai ✓", arow)
        b_ok.clicked.connect(self.close)
        al.addWidget(b_all, 1)
        al.addWidget(b_ok, 1)
        lay.addWidget(arow)

        wa = QWidgetAction(self)
        wa.setDefaultWidget(w)
        self.addAction(wa)
        self._populate("")

    # ------------------------------------------------------------
    def _populate(self, term: str) -> None:
        self._lw.blockSignals(True)
        self._lw.clear()
        term = (term or "").strip().lower()
        shown = 0
        rest = 0
        for v, n in self._counts.items():
            # v2.13.12 (gel-3 B9): dua wujud nilai — mentah (utk cari &
            # UserRole round-trip) dan TERFORMAT (utk tampilan, sama
            # dgn sel tabelnya; None/NaN → '(kosong)').
            raw = "" if v is None else str(v)
            disp = self._fmt(v)
            if not disp:
                disp = "(kosong)"
            hay = (disp + "\n" + raw).lower()
            if term and term not in hay:
                continue
            if shown >= _HF_MAX_ITEMS:
                rest += 1
                continue
            it = QListWidgetItem()
            if len(disp) > 48:
                disp = disp[:45] + "…"
            it.setText(f"{disp}   ({fmt_id(n)})")
            # UserRole = nilai MENTAH (None dipertahankan sebagai kunci
            # isin — round-trip teruji di test_v21312).
            it.setData(Qt.ItemDataRole.UserRole, v)
            it.setToolTip(f"{disp} — {fmt_id(n)} baris")
            it.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEnabled)
            it.setCheckState(
                Qt.CheckState.Checked if self._checked.get(v, True)
                else Qt.CheckState.Unchecked)
            self._lw.addItem(it)
            shown += 1
        if rest:
            note = QListWidgetItem(f"… {fmt_id(rest)} nilai lain — pakai "
                                  "kotak cari")
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lw.addItem(note)
        # v2.13.12 (gel-3 A8): 0-baris TIDAK lagi dead-end senyap —
        # (a) kolom tanpa nilai sama sekali karena SEMUA baris tersaring
        #     filter lain → catatan arahan melepas filter;
        # (b) hasil cari 0 → catatan coba kata kunci lain (bukan tutup).
        if not self._counts:
            note = QListWidgetItem(
                "0 baris cocok — lepas filter lain untuk melihat semua")
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lw.addItem(note)
        elif term and shown == 0 and rest == 0:
            note = QListWidgetItem(
                "0 nilai cocok — coba kata kunci lain")
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lw.addItem(note)
        self._lw.blockSignals(False)

    def _on_item(self, item: QListWidgetItem) -> None:
        v = item.data(Qt.ItemDataRole.UserRole)
        if v is None and "(kosong)" not in item.text():
            return  # baris catatan non-interaktif
        self._checked[v] = (item.checkState() == Qt.CheckState.Checked)
        self._timer.start()  # debounce — centang beruntun = 1 broadcast

    def _pick_all(self) -> None:
        for v in self._counts:
            self._checked[v] = True
        self._populate(self._ed.text())
        self._apply_now()

    def _apply_now(self) -> None:
        if self._apply is None:
            return
        allc = all(self._checked.get(v, True) for v in self._counts)
        if allc:
            self._apply(self._col, self._key, None)
        else:
            vals = [v for v in self._counts if self._checked.get(v, True)]
            self._apply(self._col, self._key, vals)

    def _sort(self, order: Qt.SortOrder) -> None:
        m = self._view.model()
        df = getattr(m, "dataframe", None)
        if df is None or self._col not in list(df.columns):
            return
        idx = list(df.columns).index(self._col)
        self._view.sortByColumn(idx, order)
        self.close()


class FilterHeader(QHeaderView):
    """Header QTableView + ikon funnel filter per kolom (v2.12.3).

    Kolom terdaftar di ``tabel._hf_cols`` digambar funnel di ujung kanan
    judul; KLIK FUNNEL = menu nilai + sort (klik area judul seperti biasa
    = sort — perilaku lama utuh). Funnel TERISI MERAH = kolom sedang
    terfilter (status dibaca per-paint via ``tabel._hf_state`` — selalu
    segar, sinkron dgn chip slicer karena satu sumber state).
    Tabel TANPA mapping (default) tampil & berperilaku PERSIS header
    bawaan — funnel tak digambar, klik = sort."""

    def __init__(self, parent: QTableView) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)

    def _table(self) -> QTableView | None:
        p = self.parent()
        return p if isinstance(p, QTableView) else None

    def _col_name(self, logical: int) -> str | None:
        """Nama kolom KANONIK (df model — bukan alias headerData)."""
        m = self.model()
        if m is None:
            return None
        df = getattr(m, "dataframe", None)
        if df is None or logical < 0 or logical >= len(df.columns):
            return None
        return str(df.columns[logical])

    # ------------------------------------------------------------
    def paintSection(self, painter, rect, logical):
        """v2.12.5 — judul TIDAK PERNAH tertutup funnel.

        Kolom ber-funnel: Qt melukis judul (+ panah sort) di DALAM rect
        yang disempitkan ``_HF_STRIP`` px dari kanan → teks ter-elide
        sebelum strip, lalu strip dilukis manual: bg QSS #f8fafc + ikon
        funnel + border kanan/bawah (replica QSS) — visual satu section
        utuh. Kolom tanpa funnel: super() murni (perilaku bawaan).
        (v2.12.3-4: super() dgn rect PENUH lalu backing menutup
        [right-32, right-12] → ekor judul bold tertutup = "nama header
        terpotong" + panah sort ikut tertutup.)"""
        t = self._table()
        name = self._col_name(logical)
        funnel = t is not None and t._hf_has(name)
        if not funnel:
            super().paintSection(painter, rect, logical)
            return
        state = None
        try:
            if t._hf_state is not None:
                state = t._hf_state(name)
        except Exception:  # noqa: BLE001 — state_fn view tak boleh crash paint
            state = None
        r = QRect(rect)
        r.adjust(0, 0, -_HF_STRIP, 0)
        super().paintSection(painter, r, logical)
        # strip kanan: bg + border (replica QSS section) + ikon
        strip = QRect(r.right() + 1, rect.top(),
                      rect.right() - r.right(), rect.height())
        painter.save()
        painter.fillRect(strip, QColor(_HF_BG))
        painter.setPen(QColor(C_BORDER))
        painter.drawLine(strip.right(), strip.top(),
                         strip.right(), strip.bottom())
        painter.drawLine(strip.left(), strip.bottom(),
                         strip.right(), strip.bottom())
        painter.restore()
        _paint_funnel(painter, rect, active=bool(state))

    def _hit_funnel(self, pos) -> int | None:
        logical = self.logicalIndexAt(pos.toPoint())
        if logical < 0:
            return None
        t = self._table()
        name = self._col_name(logical)
        if t is None or not t._hf_has(name):
            return None
        x0 = self.sectionViewportPosition(logical)
        w = self.sectionSize(logical)
        fx = pos.x()
        # v2.12.5: zona = strip kanan (ikon berpusat di right-12).
        if w >= 60 and x0 + w - _HF_STRIP - 2 <= fx <= x0 + w - 2:
            return logical
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            logical = self._hit_funnel(e.position())
            if logical is not None:
                self._open_menu(logical)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        if self._hit_funnel(e.position()) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def leaveEvent(self, e):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(e)

    # ------------------------------------------------------------
    def _open_menu(self, logical: int) -> None:
        t = self._table()
        if t is None:
            return
        name = self._col_name(logical)
        if not t._hf_has(name):
            return
        m = self.model()
        df = getattr(m, "dataframe", None)
        if df is None or name not in df.columns:
            return
        series = df[name]
        # v2.13.12 (gel-3 B9): dropna=False — nilai KOSONG ditawarkan
        # sebagai pilihan ('(kosong)') alih-alih dibuang senyap (dulu:
        # filter kolom tanpa memilih NaN = NaN ikut hilang diam-diam;
        # uncheck nilai terakhir pun men-deselect baris kosong tanpa
        # peringatan). None/NaN tampil '(kosong)', UserRole tetap mentah.
        vc = series.value_counts(dropna=False)
        counts: "OrderedDict[object, int]" = OrderedDict(
            (k, int(v)) for k, v in vc.items())
        # v2.13.12 (gel-3 A8): counts kosong (0 baris lolos filter lain)
        # — menu TETAP dibuka dgn catatan '0 baris cocok' (dulu: return
        # senyap = klik funnel tanpa umpan balik = dead-end).
        state = None
        try:
            if t._hf_state is not None:
                state = t._hf_state(name)
        except Exception:  # noqa: BLE001
            state = None
        key = t._hf_cols.get(name, name)
        menu = _HeaderFilterMenu(t, name, key, counts, state,
                                  t._hf_apply, self,
                                  fmt=_menu_value_fmt(name))
        self._menu = menu  # deterministik (test/automation) + jaga umur
        # v2.12.5: menu tertutup → catat waktu + rect global menu di
        # tabel — mouseDoubleClickEvent menelan klik-ganda artefak yang
        # jatuh di bekas area menu (klik ke-2 user di posisi tombol
        # yang sama, kini baris tabel) supaya pop-up detail tidak
        # terbuka sendiri pasca apply/sort/tutup menu.
        menu.aboutToHide.connect(t._note_hf_menu_hidden)
        pos = self.mapToGlobal(QPoint(
            int(self.sectionViewportPosition(logical)),
            int(self.height())))
        menu.popup(pos)


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
    """QLabel dengan word-wrap aktif default — teks tidak pernah terpotong.

    v2.12.2 (bug): ``setSizePolicy`` eksplisit lama TIDAK sengaja
    menghapus flag ``heightForWidth`` yang dipasang ``setWordWrap`` —
    layout jadi tak tahu label bisa "menyusut mengikuti lebar" dan
    memberinya sizeHint "persegi" (hint 2 baris = 28px diberi 112px).
    Terukur di data asli: hint bawah tabel Anomali mencuri 84px — tabel
    jatuh ke batas minimum 200px (6-7 baris terlihat) di laptop. Flag
    dipulihkan → semua kartu di SEMUA tab mendapat tinggi label jujur
    (diukur: tabel +11px pada 1366×700 sebelum fix slicer; semua tab
    ikut untung — hint ada di setiap kartu).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None,
                 muted: bool = False) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sp = QSizePolicy(QSizePolicy.Policy.Preferred,
                         QSizePolicy.Policy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        if muted:
            self.setObjectName("muted")


# ============================================================
# TABEL DATA
# ============================================================

class DataTable(QTableView):
    """QTableView + PandasTableModel — tanpa cap baris, sort klik header,
    kolom auto-width dari sampel, tooltip + wrap utk teks panjang."""

    double_clicked = Signal(object)  # pd.Series (record baris)
    # v2.13.5: klik baris APA PUN — termasuk baris YANG SAMA (pop-up
    # detail bisa dibuka ulang setelah ditutup). Diferensiasi vs sinyal
    # QTableView.clicked: klik pada sel kolom centang ✓ TIDAK diteruskan
    # (sedang memasukkan/mencabut baris — pop-up justru mengganggu).
    row_clicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = PandasTableModel(parent=self)
        self.setModel(self._model)
        # v2.12.3: header khusus — funnel filter per kolom (opt-in via
        # setup_header_filters; tabel TANPA mapping tampil & perilaku
        # PERSIS header bawaan — funnel tak digambar, klik judul = sort).
        self.setHorizontalHeader(FilterHeader(self))
        # v2.12.3: wiring filter header (kosong = semua tabel lama utuh)
        self._hf_cols: dict[str, str] = {}
        self._hf_all = False   # v2.12.4: funnel utk SEMUA kolom (auto)
        self._hf_skip: set[str] = set()  # v2.12.4: kolom tanpa funnel
        self._hf_apply = None
        self._hf_state = None
        # v2.13.5: tekanan mouse terakhir di sel ✓ — window sempit saat
        # mousePressEvent (currentRowChanged memicu sinkron di dalamnya;
        # view memeriksa suppress_row_popup() supaya klik sel ✓ pada baris
        # BARU pun tak membuka pop-up detail — alur centang massal murni).
        self._press_check = False
        # v2.12.5: (waktu, rect-global menu funnel terakhir tertutup)
        # — sumber guard klik-ganda artefak (lihat mouseDoubleClickEvent)
        self._hf_hide: tuple[float, QRect | None] = (-1e9, None)
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
        self._no_wrap = False  # v2.12.1: tabel lebar/raksasa — wrap mati, tinggi seragam
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
        # v2.13.5: relay clicked → row_clicked (kecuali sel kolom ✓).
        self.clicked.connect(self._on_clicked)
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
        if not (0 < n <= 3000) or self._no_wrap:
            return  # v2.12.1: wrap mati → tinggi seragam, tak ada yang diukur
        fm = self.fontMetrics()
        default_h = self.verticalHeader().defaultSectionSize()
        self._in_fit = True  # jangan picu sectionResized-handler saat setRowHeight
        try:
            for r in range(n):
                need = default_h
                for c in range(model.columnCount()):
                    if self.isColumnHidden(c):  # v2.6.1: kolom responsif tak dihitung
                        continue
                    # v2.12.1: text_at = jalur bulk snapshot numpy —
                    # pengukuran tinggi menyentuh SEMUA sel (mis. 797×41 =
                    # 32 ribu); data() Qt (pandas iat per sel) terukur 1,7
                    # dtk utk itu di data asli — terlalu lambat di jalur klik.
                    text = model.text_at(r, c)
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

    def mousePressEvent(self, e) -> None:
        """v2.13.5 — tandai bila tekanan jatuh di sel kolom ✓.

        Flag hidup HANYA selama pemanggilan super() (currentRowChanged
        memicu SINKRON di dalamnya — view membaca suppress_row_popup()
        di jendela itu); dibersihkan di finally supaya tak ada state basi
        yang salah menekan pop-up navigasi keyboard berikutnya.

        v2.13.9 — tekan#1 REPLAY pasca menu funnel juga DITELAN.
        Klik yang MENUTUP menu funnel di-replay Qt ke tabel sebagai
        tekan tunggal (mekanisme v2.12.5 §dok mouseDoubleClickEvent);
        guard v2.12.5 hanya menelan klik-GANDA artefak — tekan#1 lolos
        → baris terseleksi → currentRowChanged → pop-up detail terbuka
        tanpa niat user. Laporan user v2.13.8 "masih ada bug pada klik
        filter muncul pop up" — terbukti empiris (tests/repro_filter_
        popup_2139.py: klik tunggal 0 ms pasca-tutup-menu → popup
        visible True). Dalam jendela _HF_HIDE_GUARD_S setelah menu
        tertutup, tekan kiri pada tabel diabaikan TOTAL (tanpa seleksi);
        klik sah sesudah jendela itu utuh (kontrol repro [4] hijau)."""
        if (e.button() == Qt.MouseButton.LeftButton
                and time.monotonic() - self._hf_hide[0] < _HF_HIDE_GUARD_S):
            e.accept()
            return
        idx = self.indexAt(e.position().toPoint())
        self._press_check = bool(
            idx.isValid() and not self._relay_row_click_ok(idx))
        try:
            super().mousePressEvent(e)
        finally:
            self._press_check = False

    def suppress_row_popup(self) -> bool:
        """True bila tekanan mouse yang sedang diproses ada di sel ✓ —
        view pop-up detail memeriksa ini agar centang = aksi murni."""
        return self._press_check

    def _on_double(self, index) -> None:
        rec = self._model.record(index.row())
        if rec is not None:
            self.double_clicked.emit(rec)
        # v2.13.5: klik-2× TIDAK lagi dipakai utk filter (dihapus dari
        # view atas permintaan user) — diteruskan ke row_clicked supaya
        # pop-up detail TETAP terbuka pada pasangan klik cepat (Qt hanya
        # memancarkan clicked utk tekan#1; tekan#2 = DblClick tanpa
        # clicked — tanpa relay ini, klik-ulang-cepat-baris-sama tidak
        # membuka apa-apa). Guard ✓ tetap: klik-2× sel centang = tetap
        # murni aksi centang.
        if self._relay_row_click_ok(index):
            self.row_clicked.emit(index)

    def _relay_row_click_ok(self, index) -> bool:
        """Klik (tunggal/ganda) pada sel ✓ → jangan relay ke row_clicked
        (user sedang memasukkan/mencabut baris follow-up — pop-up detail
        justru mengganggu alur centang massal)."""
        m = self._model
        check = getattr(m, "_check_col", None)
        if check is None or not index.isValid():
            return True
        cols = getattr(m, "_cols", None)
        if not cols and m.dataframe is not None:
            cols = list(m.dataframe.columns)
        hit_check = bool(
            cols and 0 <= index.column() < len(cols)
            and cols[index.column()] == check)
        return not hit_check

    def _on_clicked(self, index) -> None:
        """v2.13.5 — relay QTableView.clicked → row_clicked.

        clicked memicu di SETIAP tekan-lepas valid — termasuk klik baris
        YANG SAMA (currentRowChanged diam saat index tak berubah; tanpa
        relay ini pop-up detail tak bisa dibuka ulang setelah ditutup X
        — keluhan user "klik 1× pop-up kadang tidak muncul")."""
        if self._relay_row_click_ok(index):
            self.row_clicked.emit(index)

    # ------------------------------------------------------------
    # v2.12.5 — klik ganda artefak pasca menu funnel ditelan
    # ------------------------------------------------------------
    def _note_hf_menu_hidden(self) -> None:
        """Menu funnel barusan tertutup (aboutToHide) — catat waktu +
        area global menu (rect masih tersedia saat sinyal ini)."""
        hdr = self.horizontalHeader()
        m = getattr(hdr, "_menu", None)
        rect = None
        if m is not None:
            try:
                rect = QRect(m.frameGeometry())  # salinan (global)
            except Exception:  # noqa: BLE001 — geometry basi tak fatal
                rect = None
        self._hf_hide = (time.monotonic(), rect)

    def mouseDoubleClickEvent(self, e) -> None:
        """Telan klik-ganda "hantu" pasca menu funnel tertutup.

        Mekanisme keluhan user ("apply filter → pop-up drill detail
        muncul sendiri") — terbukti empiris: (1) menu funnel menutupi
        baris tabel; klik penutup menu yang jatuh di luar menu
        DI-REPLAY Qt ke baris tabel sebagai tekan#1; (2) klik ke-2
        user (pilih baris / kebiasaan dobel-klik tombol menu) pada
        posisi sama = tekan#2 → Qt menyintesis klik-ganda →
        doubleClicked → pop-up detail terbuka tanpa niat user.
        (Qt hanya memancarkan doubleClicked bila tekan#1 mengenai
        baris yang sama — itulah kenapa pasangan tekan ini efektif
        memicunya.) Solusi: dalam selang <interval-dobel-klik + margin
        setelah menu funnel tertutup, klik-ganda pada tabel ini
        DIABAIKAN (klik tunggal pilih-baris tetap hidup). Klik ganda
        sah sesudah selang itu tidak terganggu."""
        ts, _rect = self._hf_hide
        if time.monotonic() - ts < _HF_HIDE_GUARD_S:
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def setup_header_filters(self, cols: "dict[str, str] | None",
                             apply_fn=None, state_fn=None,
                             all_cols: bool = False,
                             skip: "list[str] | tuple[str, ...] | None" = None) -> None:
        """v2.12.3 — kolom yang diberi ikon funnel filter di header.

        cols: {nama kolom KANONIK: kunci filter}. ``apply_fn(col, key,
        values|None)`` dipanggil menu saat menerapkan (None = lepas);
        ``state_fn(col)`` → list nilai terpilih (None = tanpa filter) —
        dibaca saat MELUKIS funnel (aktif = terisi merah). None/{} =
        matikan semua funnel (tabel perilaku bawaan).

        v2.12.4: ``all_cols=True`` — funnel digambar di SEMUA kolom df
        (kecuali nama di ``skip`` — mis. kolom centang ✓ / kolom
        identitas tersembunyi). Kolom yang tetap ada di mapping ``cols``
        memakai kunci mapping-nya (state global); kolom lain memakai
        NAMA KOLOM sebagai kunci (apply_fn menentukan semantiknya —
        filter lokal milik view)."""
        self._hf_cols = dict(cols or {})
        self._hf_all = bool(all_cols)
        self._hf_skip = {str(s) for s in (skip or ())}
        self._hf_apply = apply_fn
        self._hf_state = state_fn
        self.horizontalHeader().viewport().update()

    def _hf_has(self, name: str | None) -> bool:
        """v2.12.4 — apakah kolom ini digambar funnel (mapping / all)."""
        if name is None:
            return False
        return name in self._hf_cols or (
            self._hf_all and name not in self._hf_skip)

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
        # v2.12.1 (perf): tabel LEBAR juga (>24 kolom tampak — mis. rekap
        # Follow Up 797×41): pengukuran tinggi per sel = 32 ribu panggilan
        # ukur (~0,35 dtk sandbox, 2-4× di laptop user) DI TIAP render;
        # sel hari/angka tidak pernah wrap — hanya kolom teks panjang yang
        # ter-elide (tooltip penuh, konvensi yang sama). Diukur: lepas ✓ di
        # tab Follow Up (refresh per klik) 0,53 dtk → ~0,14 dtk.
        big = df is not None and (
            len(df) > 3000
            or (self._visible_cols is not None
                and len(self._visible_cols) > 24))
        self._no_wrap = big
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
        # v2.12.5: JUDUL dilukis QSS dgn font-weight 600 — fontMetrics
        # widget (weight 400) mengukur 8-12% LEBIH PENDEK dari yang
        # dilukis (bukti piksel: "ANOMALY SCORE" adv 111 vs terlukis
        # 124 → lantai kurang → ekor judul tertutup funnel = "nama
        # header terpotong"). Ukur judul dgn font QSS yang benar.
        hfm = QFontMetrics(_header_font())
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
            hw = hfm.horizontalAdvance(names[c]) + 26
            # v2.12.3: kolom ber-funnel butuh zona strip kanan supaya
            # judul + panah sort ter-elide SEBELUM ikon (v2.12.5: strip
            # kini direservasi struktural oleh paintSection — teks tak
            # pernah dilukis di bawahnya; v2.12.3-4 backing menutup
            # ekornya = terpotong).
            # v2.12.4: berlaku juga mode all_cols (SEMUA kolom ber-funnel).
            if self._hf_has(names[c]):
                hw += _HF_STRIP
            floors.append(min(max(min_w, hw), cap))
            w = hw
            for r in range(n_rows):
                # v2.12.1: text_at = jalur bulk snapshot (lihat _refit_rows).
                text = model.text_at(r, c)
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
                       if 0 < model.rowCount() <= 3000 and not self._no_wrap
                       else [])
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

