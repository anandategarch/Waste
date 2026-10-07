"""view_periode.py — view 'Banding Periode' multi-file (v2.10.0).

Desain disetujui user (worklog Task 9 + jawaban 5 pertanyaan):
- Pembanding = DAFTAR workbook (1 file = 1 bulan, template standar
  "REKAP MENTAH" — kuantiti tanpa BOM). Nama bulan dibaca OTOMATIS dari
  nama file ("...AGUSTUS 2026..." → "Agustus 2026"), bisa dikoreksi
  manual (klik 2× baris).
- Dua-duanya: banding vs 1 bulan pilihan + "Tipikal" (median gabungan
  ≥ 2 bulan) — combo di kartu hasil.
- Daftar file DIINGAT antar sesi (history_files.json, atomic — pola
  filters.py); dimuat ulang otomatis di background saat aplikasi dibuka.
- Muat di HistoryWorker (QThread + progress + cancel) — UI tidak beku
  (standar anti-lambat). File gagal → baris merah + pesan, file lain jalan.
- Perbandingan MURNI KUANTITI (compare_quantity): Total Waste, Waste per
  Hari (menormalkan beda 30/31 hari), cabang/item mover, item baru/hilang.

Istilah awam + tooltip di semua kontrol (kebijakan v2.9.0).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.followup import CHECK_COL, FP_COL  # v2.12.2: ✓ di tabel banding
from waste_anomaly.period_history import (
    aggregate_current,
    compare_level,
    compare_quantity,
    detect_month_label,
    drill_day_detail,
    load_history_entries,
    month_sort_key,
    save_history_entries,
    typical_months,
)

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, DataTable, WLabel, busy_feedback
from .workers import HistoryWorker

_PAGES = [
    ("summary", "📊 Ringkasan"),
    ("per_jenis", "🧾 Per Jenis"),
    ("branch", "🏬 Cabang Mover"),
    ("items", "📦 Item Mover"),
    ("new_items", "🆕 Item Baru"),
    ("gone_items", "📉 Item Hilang"),
]

# key dict hasil compare_quantity → (df, label) — kontrak TERKUNCI test
# wave1 (V26-H3): nilai HARUS kunci dict hasil (compare_periods lama maupun
# compare_quantity v2.10.0 memakai nama kunci yang sama).
_RESULT_KEYS = {
    "summary": "summary",
    "per_jenis": "per_jenis",
    "branch": "branch",
    "items": "items",
    "new_items": "new_items",
    "gone_items": "gone_items",
}

# Penanda userData combo: pilihan tipikal gabungan vs index bulan.
_TYPICAL_KEY = "__tipikal__"

# v2.12.2 — halaman hasil banding yang PUNYA centang ✓ follow-up:
# baris cabang / item punya identitas (resto[+barang]) yang bisa dipetakan
# ke baris anomali bulan berjalan. Ringkasan & Per Jenis = level metrik
# (tak ada identitas baris); Item Hilang = sengaja TANPA ✓ (barisnya tak
# ada di bulan berjalan — tak ada baris anomali utk dikumpulkan).
_FU_PAGES = ("branch", "items", "new_items")
# Kolom identitas tersembunyi di df tampilan (list sidik jari per baris).
_FPS_COL = "__FPS"


class BandTableDialog(QDialog):
    """Pop-up tabel banding (v2.10.2) — layar penuh & rantai drill-down.

    Satu kelas untuk dua pemakaian (tabel + judul + rute klik-2× sama):
    - 'Layar Penuh' : salinan tabel tab aktif, jendela maximized (Esc balik).
    - Drill-down    : rantai rincian Total → resto → item → hari (klik 2×
      baris = turun satu level; tabel diganti, breadcrumb di judul jendela).
    Tabel = DataTable biasa (render ≤ ratusan baris = milidetik — aman
    anti-lambat); df di-clone-render, tabel asli di view tak tersentuh.
    """

    def __init__(self, ctx: AppContext, drill_cb, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._drill_cb = drill_cb  # (level, payload, rec) → dikonsumsi view
        self._level: str | None = None
        self._payload: dict = {}
        self._path: list[str] = []
        self.setWindowTitle("Banding Periode")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
        self._lbl_title = WLabel("", self)
        self._lbl_title.setObjectName("cardTitle")
        lay.addWidget(self._lbl_title)
        self._lbl_sub = WLabel("", self)
        self._lbl_sub.setObjectName("hint")
        self._lbl_sub.setWordWrap(True)
        lay.addWidget(self._lbl_sub)
        self._table = DataTable(self)
        self._table.double_clicked.connect(self._on_double)
        lay.addWidget(self._table, 1)
        btn = QPushButton("Tutup (Esc)", self)
        btn.clicked.connect(self.close)
        row = QWidget(self)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addStretch(1)
        rl.addWidget(btn)
        lay.addWidget(row)

    # ------------------------------------------------------------
    def show_table(self, title: str, subtitle: str,
                   df: pd.DataFrame | None, level: str | None = None,
                   payload: dict | None = None, root: bool = False,
                   sort_desc: str | None = None,
                   maximized: bool = False,
                   header_map: dict | None = None) -> None:
        """Tampilkan satu level tabel (root=True = mulai rantai baru).

        header_map (v2.12.2): alias judul kolom tampilan (mis. 'Pembanding'
        → nama bulan) — data tetap nama kanonik."""
        self._level = level
        self._payload = dict(payload or {})
        if root or not self._path:
            self._path = []
        self._path.append(str(title))
        self._lbl_title.setText(str(title))
        self._lbl_sub.setText(str(subtitle))
        self._table.model().set_header_map(header_map)
        with busy_feedback(self._ctx.set_status,
                           "Menampilkan tabel banding"):
            self._table.set_dataframe(df, sort_desc=sort_desc)
        # Breadcrumb jendela (maks 3 segmen + elipsis) — konteks tak hilang.
        crumbs = " › ".join(self._path[-3:])
        self.setWindowTitle(f"Banding Periode — {crumbs}")
        if maximized:
            self.showMaximized()
        else:
            self.resize(1040, 640)
            self.show()
        self.raise_()
        self.activateWindow()

    def _on_double(self, rec: pd.Series) -> None:
        """Klik 2× baris → serahkan ke view (turun level / buka rantai)."""
        if self._drill_cb is not None and self._level is not None:
            self._drill_cb(self._level, self._payload, rec)


class PeriodeView(QWidget):
    """View 'Banding Periode': bulan berjalan vs daftar bulan pembanding."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: HistoryWorker | None = None
        self._running = False
        # Kontrak lazy-render + stale-result (pola lama dipertahankan).
        self._dirty = True
        self._has_result = False
        self._result_version: tuple[int, int] | None = None
        # Daftar file (persisten): [{"path":…, "label":…|None}]
        self._entries: list[dict] = []
        # Cache hasil muat per path (hanya entri SUKSES — entri error
        # di-retry otomatis pada pemuatan berikutnya). Key = path,
        # divalidasi dgn (mtime, size) — file diganti → dimuat ulang.
        self._loaded: dict[str, dict] = {}
        self._loaded_sig: dict[str, tuple] = {}
        self._last_results: dict[str, dict] = {}
        # Memo agregat bulan berjalan (A) — per data_version + key_akhir.
        self._a_cache: tuple[int, int, dict] | None = None
        # Versi history saat combo terakhir diisi ulang — combo selalu
        # disinkronkan di _refresh_result (satu tempat, tanpa render ganda:
        # _finalize hanya set_history; sinyal → _refresh_result → rebuild).
        self._combo_version: int = -1
        # v2.12.2: judul kolom pengganti 'Pembanding' dari render terakhir
        # (dipakai juga oleh pop-up drill & layar penuh).
        self._label_b_disp = "Pembanding"
        # v2.12.2: peta (jenis, resto[, barang]) → [sidik jari anomali]
        # (memo per data_version — dgn metode _fu_maps).
        # v2.12.3 (Opsi A "1 item per resto"): peta CENTANG hanya baris
        # ANOMALI; peta PENUH (_fu_*_full) utk LEPAS centang — membersihkan
        # fps noise warisan v2.12.2 (baris Normal TOTAL=0 yang ikut masuk
        # sebelum saringan ini ada).
        self._fu_item: dict | None = None
        self._fu_branch: dict | None = None
        self._fu_item_full: dict = {}
        self._fu_branch_full: dict = {}
        self._fu_ver: int = -1
        # v2.12.4: funnel LOKAL per HALAMAN hasil banding (SEMUA kolom
        # ber-funnel — permintaan user "semua kolom punya filter").
        # {page: {kolom: nilai terpilih}} — menyaring TAMPILAN tabel
        # halaman itu; bahan render penuh disimpan (_page_src) supaya
        # ganti filter tak perlu compare ulang.
        self._pfilters: dict[str, dict[str, list]] = {
            k: {} for k, _ in _PAGES}
        self._page_src: dict[str, object] = {}
        self._pf_ver: int = -1
        # v2.12.2: muat otomatis saat buka aplikasi → boleh auto-ciut
        # kartu daftar file begitu sukses (kelola file manual = JANGAN
        # ciut sendiri — user sedang melihat daftarnya).
        self._auto_load = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._card_files = self._build_card_files()
        lay.addWidget(self._card_files)
        lay.addWidget(self._build_card_result(), 1)

        # v2.10.2 — pop-up rantai drill-down + jendela layar penuh (satu
        # instance dipakai ulang; parent=self → tetap di atas jendela utama).
        self._drill = BandTableDialog(ctx, self._drill_dispatch, self)
        self._full = BandTableDialog(ctx, self._drill_dispatch, self)
        # Bulan A/B terakhir yang dirender — bahan semua drill-down.
        self._a: dict | None = None
        self._b: dict | None = None
        self._res: dict | None = None

        ctx.data_ready.connect(self._on_data_ready)
        ctx.history_ready.connect(self._on_history_ready)
        # v2.12.2: centangan ✓ berubah di mana pun (tab Anomali / banding /
        # tombol massal) → segarkan kolom ✓ banding in-place.
        ctx.followup_changed.connect(self._on_followup_changed)

        # Muat daftar tersimpan → auto-load background (user: "ya boleh
        # diingat"). Konstruktor berjalan saat app dibuka; worker QThread
        # tidak memblokir UI startup.
        self._entries = load_history_entries()
        self._render_file_list()
        if self._entries:
            self._start_worker()

    # ------------------------------------------------------------
    # BANGUN UI
    # ------------------------------------------------------------
    def _build_card_files(self) -> Card:
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("🔀 Banding Periode — bulan berjalan vs bulan-bulan sebelumnya", card)
        ttl.setObjectName("cardTitle")
        ttl.setToolTip(
            "Tambahkan file rekap bulan lalu (1 file = 1 bulan, format REKAP "
            "MENTAH — cukup kolom nama barang, resto, satuan & hari 1-31, "
            "tanpa angka BOM). Nama bulan dibaca otomatis dari nama file; "
            "klik 2× baris untuk mengoreksi. Semua file dimuat di latar "
            "belakang — aplikasi tetap responsif.")
        cl.addWidget(ttl)

        row = QWidget(card)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self._tbl_files = QTableWidget(0, 3, row)
        self._tbl_files.setHorizontalHeaderLabels(["Bulan", "File", "Status"])
        self._tbl_files.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_files.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_files.verticalHeader().setVisible(False)
        self._tbl_files.setAlternatingRowColors(True)
        head = self._tbl_files.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl_files.setMinimumHeight(120)
        self._tbl_files.setToolTip(
            "Daftar file pembanding (diingat antar sesi).\n"
            "Klik 2× kolom Bulan untuk memberi/koreksi nama bulan.")
        self._tbl_files.doubleClicked.connect(self._on_double)
        rl.addWidget(self._tbl_files, 1)

        btns = QWidget(row)
        bl = QVBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        self._btn_add = QPushButton("＋ Tambah File…", btns)
        self._btn_add.setToolTip(
            "Pilih satu atau beberapa workbook bulan lalu "
            "(bisa multi-pilih sekaligus).\n"
            "Format: REKAP MENTAH — cukup kolom nama barang, resto, "
            "satuan & hari 1-31, tanpa angka BOM.")
        self._btn_add.clicked.connect(self._on_add)
        bl.addWidget(self._btn_add)
        self._btn_del = QPushButton("🗑 Hapus Pilihan", btns)
        self._btn_del.setToolTip("Hapus file terpilih dari daftar pembanding\n"
                                 "(file aslinya tidak dihapus).")
        self._btn_del.clicked.connect(self._on_delete)
        bl.addWidget(self._btn_del)
        self._btn_run = QPushButton("🔄 Muat Ulang", btns)
        self._btn_run.setToolTip("Baca ulang SEMUA file pembanding dari disk\n"
                                 "(mis. setelah file diperbarui).")
        self._btn_run.clicked.connect(self._on_reload)
        bl.addWidget(self._btn_run)
        bl.addStretch(1)
        rl.addWidget(btns)
        cl.addWidget(row, 1)

        self._lbl_a = WLabel("Bulan berjalan: (belum ada run)", card)
        self._lbl_a.setStyleSheet("font-weight:600;")
        cl.addWidget(self._lbl_a)
        self._lbl_status = WLabel("Siap — belum ada file pembanding.", card)
        self._lbl_status.setObjectName("hint")
        self._lbl_status.setWordWrap(True)
        cl.addWidget(self._lbl_status)
        return card

    def _build_card_result(self) -> Card:
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("📈 Hasil Banding (kuantiti — tanpa angka BOM)", card)
        ttl.setObjectName("cardTitle")
        cl.addWidget(ttl)

        ctrl = QWidget(card)
        ctl = QHBoxLayout(ctrl)
        ctl.setContentsMargins(8, 0, 8, 0)
        ctl.setSpacing(10)
        lbl = WLabel("Banding dengan:", ctrl)
        ctl.addWidget(lbl)
        self._cb_b = QComboBox(ctrl)
        self._cb_b.setToolTip(
            "Pilih pembanding:\n"
            "• 'Tipikal' = nilai tengah gabungan beberapa bulan lalu "
            "(butuh ≥ 2 bulan) — untuk deteksi perubahan;\n"
            "• satu bulan tertentu — untuk melihat bulan itu apa adanya.")
        self._cb_b.setMinimumWidth(220)
        self._cb_b.currentIndexChanged.connect(
            lambda _i: self._on_combo_changed())
        ctl.addWidget(self._cb_b)
        self._lbl_compare = WLabel("", ctrl)
        self._lbl_compare.setObjectName("hint")
        ctl.addWidget(self._lbl_compare, 1)
        # v2.10.2 — dua tingkat melebarkan tabel (permintaan user: tabel
        # jangan kecil): (1) ciutkan kartu daftar file → tabel pakai seluruh
        # sisa tinggi; (2) pop-out jendela maximized utk tab aktif (Esc balik).
        self._btn_expand = QPushButton("⤢ Perbesar Tabel", ctrl)
        self._btn_expand.setToolTip(
            "Sembunyikan daftar file pembanding supaya tabel hasil banding "
            "memakai seluruh tinggi tampilan.\nKlik lagi untuk mengembalikan "
            "daftar file.")
        self._btn_expand.clicked.connect(self._on_expand)
        ctl.addWidget(self._btn_expand)
        self._btn_full = QPushButton("⛶ Layar Penuh", ctrl)
        self._btn_full.setToolTip(
            "Buka tabel tab aktif di jendela LAYAR PENUH (tekan Esc atau "
            "Tutup untuk kembali).\nDi jendela itu pun klik 2× baris tetap "
            "membuka pop-up rincian (resto → item → hari).")
        self._btn_full.clicked.connect(self._on_fullscreen)
        ctl.addWidget(self._btn_full)
        cl.addWidget(ctrl)

        self._tabs = QTabWidget(card)
        self._tables: dict[str, DataTable] = {}
        for key, title in _PAGES:
            table = DataTable()
            # v2.10.2: klik 2× baris = pop-up rincian (drill-down) —
            # rantai Total → resto → item → hari (semua tab punya rute).
            table.double_clicked.connect(
                lambda rec, k=key: self._on_tab_double(k, rec))
            # v2.12.2: kolom ✓ follow-up di halaman cabang/item/baru —
            # komponen & mekanisme model SAMA dgn tab Anomali (flip bool
            # in-place + sinyal, tanpa render ulang).
            if key in _FU_PAGES:
                table.model().set_check_column(CHECK_COL)
                table.model().check_toggled.connect(
                    lambda row, checked, k=key: self._on_fu_check(
                        k, row, checked))
            # v2.12.4: funnel LOKAL per halaman — SEMUA kolom ber-funnel
            # (skip ✓ + kolom identitas __FP; state per halaman).
            table.setup_header_filters(
                None,
                lambda col, _key, values, k=key: self._on_page_filter(
                    k, col, values),
                lambda col, k=key: self._pf_state(k, col),
                all_cols=True, skip=(CHECK_COL, _FPS_COL, FP_COL))
            self._tables[key] = table
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(12, 10, 12, 10)
            pl.setSpacing(6)
            pl.addWidget(table, 1)
            self._tabs.addTab(page, title)
        cl.addWidget(self._tabs, 1)
        return card

    # ------------------------------------------------------------
    # KONTRAK LAZY-RENDER
    # ------------------------------------------------------------
    def refresh(self) -> None:
        """Kontrak lazy-render: perbarui label A + render ulang bila basi."""
        self._on_data_ready()

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data/history berubah."""
        if self._dirty or not self._has_result:
            self._refresh_result()

    def _on_data_ready(self) -> None:
        self._lbl_a.setText(
            "Bulan berjalan: " + fmt_run_label(
                self._ctx.summary, self._ctx.key_akhir))
        if self.isVisible():
            self._refresh_result()
        else:
            self._dirty = True

    def _on_history_ready(self) -> None:
        self._render_file_list()
        if self.isVisible():
            self._refresh_result()
        else:
            self._dirty = True

    def _on_combo_changed(self) -> None:
        if self.isVisible():
            self._refresh_result()

    # ------------------------------------------------------------
    # DAFTAR FILE
    # ------------------------------------------------------------
    def _on_add(self) -> None:
        self._auto_load = False  # v2.12.2: kelola file manual → jangan auto-ciut
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Pilih Workbook Pembanding (bisa beberapa)",
            str(Path.home() / "Documents"),
            "Excel files (*.xlsx *.xlsm);;All files (*.*)")
        if not paths:
            return
        added = 0
        for p in paths:
            known = {e["path"] for e in self._entries}
            if p in known:
                continue
            self._entries.append(
                {"path": p, "label": detect_month_label(p)})
            added += 1
        if added:
            save_history_entries(self._entries)
            self._render_file_list()
            self._start_worker()

    def _on_delete(self) -> None:
        rows = sorted({i.row() for i in self._tbl_files.selectedIndexes()},
                      reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(self._entries):
                p = self._entries[r]["path"]
                self._entries.pop(r)
                self._loaded.pop(p, None)
                self._loaded_sig.pop(p, None)
                self._last_results.pop(p, None)
        save_history_entries(self._entries)
        self._render_file_list()
        self._finalize()  # render ulang dgn sisa bulan (tanpa worker bila semua termuat)

    def _on_reload(self) -> None:
        self._auto_load = False  # v2.12.2: kelola file manual → jangan auto-ciut
        if self._running:
            self._cancel()
            return
        self._loaded.clear()
        self._loaded_sig.clear()
        self._start_worker()

    def _on_double(self, index) -> None:
        """Klik 2× baris: koreksi nama bulan (persisten)."""
        r = index.row()
        if not (0 <= r < len(self._entries)):
            return
        ent = self._entries[r]
        cur = ent.get("label") or ""
        auto = detect_month_label(ent["path"]) or ""
        text, ok = QInputDialog.getText(
            self, "Nama Bulan Pembanding",
            "Nama bulan file ini (mis. 'Agustus 2026'):",
            text=cur or auto)
        if not ok:
            return
        text = text.strip()
        if text and text != cur:
            ent["label"] = text
            save_history_entries(self._entries)
            self._render_file_list()
            self._finalize()

    def _render_file_list(self) -> None:
        """Sinkronkan tabel daftar dgn self._entries + status termuat."""
        self._tbl_files.setRowCount(len(self._entries))
        for r, ent in enumerate(self._entries):
            label = ent.get("label") or detect_month_label(ent["path"]) \
                or "(klik 2× utk beri nama)"
            it_l = QTableWidgetItem(str(label))
            it_l.setToolTip(
                "Klik 2× untuk mengoreksi nama bulan ini.\n"
                "Nama dipakai untuk urutan & pilihan pembanding.")
            self._tbl_files.setItem(r, 0, it_l)
            self._tbl_files.setItem(r, 1, QTableWidgetItem(
                Path(ent["path"]).name))
            res = self._last_results.get(ent["path"])
            if res is None:
                status = "⏳ belum dimuat" if not self._running else "⏳ memuat…"
                it_s = QTableWidgetItem(status)
            elif res.get("error"):
                it_s = QTableWidgetItem(f"✗ {res['error']}")
                it_s.setForeground(QColor("#dc2626"))
                it_s.setToolTip(str(res["error"]))
            else:
                n_item = fmt_id(res.get("item_count", 0))
                ka = res.get("key_akhir", "?")
                it_s = QTableWidgetItem(f"✓ {n_item} item • {ka} hari")
                # v2.13.0: jawaban pertanyaan user "pembanding hanya ada
                # hari 30, error?" — BUKAN error; tooltip menjelaskan
                # kenapa 30 hari wajar + sudah dinormalkan.
                ka_note = (""
                           if str(ka).isdigit() and int(ka) >= 31 else
                           "\n\nBulan pendek (30 hari) BUKAN error — "
                           "September/April/Juni/November memang 30 hari. "
                           "Banding tetap adil: metrik 'Waste per Hari' "
                           "membagi total dgn jumlah hari tiap bulan.")
                it_s.setToolTip(
                    f"Berhasil dimuat: {res.get('rows_kept', 0):,} baris "
                    f"waste disaring → {res.get('item_count', 0):,} "
                    f"kombinasi cabang × item.{ka_note}")
            self._tbl_files.setItem(r, 2, it_s)

    # ------------------------------------------------------------
    # WORKER
    # ------------------------------------------------------------
    def _file_sig(self, path: str) -> tuple | None:
        try:
            st = Path(path).stat()
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _start_worker(self) -> None:
        """Muat file yang belum termuat (cache mtime/size) di background."""
        if self._running:
            return
        todo: list[dict] = []
        for ent in self._entries:
            p = ent["path"]
            sig = self._file_sig(p)
            cached = self._loaded.get(p)
            if (cached is not None and sig is not None
                    and self._loaded_sig.get(p) == sig):
                continue  # termuat & file tak berubah → pakai ulang
            todo.append(ent)
        if not todo:
            self._finalize()
            return
        self._running = True
        self._btn_run.setText("⏹ Batalkan")
        self._btn_run.setObjectName("danger")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._btn_add.setEnabled(False)
        self._btn_del.setEnabled(False)
        n = len(todo)
        self._lbl_status.setText(
            f"⏳ Memuat {n} file pembanding di latar belakang…")
        self._ctx.set_status(
            f"Banding periode: memuat {n} file pembanding…", "running")
        self._render_file_list()
        self._worker = HistoryWorker(todo, dict(self._ctx.config), self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _cancel(self) -> None:
        if not self._running or self._worker is None:
            return
        self._worker.cancel()
        self._btn_run.setEnabled(False)
        self._ctx.set_status("⏹ Membatalkan pemuatan pembanding…", "running")

    def _finish(self) -> None:
        self._running = False
        self._worker = None
        self._btn_run.setText("🔄 Muat Ulang")
        self._btn_run.setObjectName("accent")
        self._btn_run.setEnabled(True)
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._btn_add.setEnabled(True)
        self._btn_del.setEnabled(True)

    def _on_progress(self, msg: str, pct: float) -> None:
        self._lbl_status.setText(f"⏳ {msg}")

    def _on_done(self, months: list) -> None:
        self._finish()
        for m in months or []:
            p = m.get("path")
            if not p:
                continue
            self._last_results[p] = m
            if not m.get("error"):
                sig = self._file_sig(p)
                if sig is not None:
                    self._loaded[p] = m
                    self._loaded_sig[p] = sig
                else:  # file menghilang setelah termuat — jangan cache
                    self._loaded.pop(p, None)
                    self._loaded_sig.pop(p, None)
        ok = [m for m in self._last_results.values()
              if not m.get("error")]
        err = [m for m in self._last_results.values() if m.get("error")]
        # v2.10.1: notif jujur — '✓ aktif' hanya bila ada bulan aktif;
        # semua gagal → '⚠' (dulu '✓ 0 bulan aktif' menyesatkan).
        parts = [f"✓ {len(ok)} bulan pembanding aktif"] if ok else []
        if err:
            parts.append(f"⚠ {len(err)} file gagal (lihat kolom Status)")
        if not parts:
            parts = ["Belum ada file pembanding."]
        self._lbl_status.setText(" — ".join(parts) + ".")
        if ok:
            self._ctx.set_status("✓ Pembanding periode siap", "done")
        else:
            self._ctx.set_status(
                "⚠ Semua file pembanding gagal dimuat", "error")
        # v2.12.2: auto-ciut kartu daftar file setelah MUAT OTOMATIK saat
        # buka aplikasi sukses (≥1 bulan) — tabel hasil langsung makan
        # tinggi penuh (dihitung: kartu file 299px + kartu hasil 298px →
        # tabel cuma 72px ≈ 2 baris terlihat meski cuma 1 file). HANYA
        # jalur muat-otomatis: tambah/muat-ulang manual tak menyentuh
        # (user sedang mengelola daftar — tombol ⤢ tetap tersedia).
        if ok and self._auto_load:
            self._card_files.setVisible(False)
            self._btn_expand.setText("⤡ Tampilkan Daftar File")
        self._auto_load = False
        self._finalize()

    def _on_failed(self, err: str, tb: str) -> None:
        self._finish()
        cancelled = "dibatalkan" in err.lower()
        if cancelled:
            self._lbl_status.setText("⏹ Pemuatan pembanding dibatalkan.")
            self._ctx.set_status("⏹ Pemuatan pembanding dibatalkan", "error")
            return
        self._lbl_status.setText(f"⚠ Gagal: {err}")
        self._ctx.set_status(f"⚠ Pembanding gagal: {err}", "error")
        if tb:
            self._ctx.log(f"⚠ HistoryWorker traceback: {tb}")
        QMessageBox.critical(self, "Banding Periode", err)

    # ------------------------------------------------------------
    # v2.10.2 — MELEBARKAN TABEL & DRILL-DOWN POP-UP
    # ------------------------------------------------------------
    def _close_popups(self) -> None:
        """Tutup pop-up drill/layar penuh yang masih terbuka (v2.10.3 audit).

        Dipanggil saat hasil banding digambar ulang atau dikosongkan —
        tabel di pop-up adalah salinan konteks lama; membiarkannya terbuka
        hanya menampilkan angka basi (drill lanjutan memang sudah di-guard
        _a/_b, tapi tampilannya tetap menyesatkan). Best-effort + defensif
        (dialog tak pernah None di __init__; RuntimeError = widget
        sudah di-destroy oleh parent)."""
        for dlg in (getattr(self, "_drill", None),
                    getattr(self, "_full", None)):
            if dlg is None:
                continue
            try:
                if dlg.isVisible():
                    dlg.close()
            except RuntimeError:
                pass

    def _on_expand(self) -> None:
        """Ciutkan / kembalikan kartu daftar file (tabel makan tinggi penuh).

        isHidden() (bukan isVisible()) — toggle harus benar walau view
        induknya sedang tak tampak (di-balik tab lain)."""
        hidden = self._card_files.isHidden()
        self._card_files.setVisible(hidden)
        self._btn_expand.setText(
            "⤢ Perbesar Tabel" if hidden else "⤡ Tampilkan Daftar File")
        self._ctx.set_status(
            "⤡ Daftar file disembunyikan — tabel diperbesar" if not hidden
            else "⤢ Daftar file ditampilkan kembali", "done")

    def _on_fullscreen(self) -> None:
        """Pop-out tabel tab AKTIF di jendela maximized (Esc = kembali)."""
        if self._res is None or self._a is None or self._b is None:
            self._ctx.set_status(
                "Belum ada hasil banding utk dibesarkan — jalankan pipeline "
                "+ muat pembanding dulu", "done")
            return
        i = self._tabs.currentIndex()
        if not (0 <= i < len(_PAGES)):
            return
        key, title = _PAGES[i]
        df = self._res.get(_RESULT_KEYS.get(key, ""))
        sub = (f"{self._a.get('label')} vs {self._b.get('label')} — "
               f"jendela penuh; klik 2× baris = rincian; Esc = kembali")
        self._full.show_table(title, sub, df, level="tab",
                              payload={"tab_key": key}, root=True,
                              maximized=True,
                              header_map={"Pembanding": self._label_b_disp})

    def _on_tab_double(self, key: str, rec: pd.Series) -> None:
        """Klik 2× baris tabel tab → buka rantai drill yang sesuai."""
        if self._a is None or self._b is None:
            return  # tanpa hasil banding tak ada yang bisa dirinci
        if key == "summary":
            metrik = str(rec.get("Metrik") or "").strip()
            if metrik == "Total Waste":
                self._open_resto(
                    "🏬 Resto penyumbang Total Waste", per_day=False)
            elif metrik == "Waste per Hari":
                self._open_resto(
                    "🏬 Resto penyumbang Waste per Hari", per_day=True)
            else:
                self._ctx.set_status(
                    f"Metrik '{metrik}' tidak punya rincian per resto "
                    "(hanya Total Waste & Waste per Hari)", "done")
        elif key == "per_jenis":
            jenis = str(rec.get("JENIS") or "").strip()
            if jenis:
                self._open_resto(
                    f"🏬 Resto penyumbang {jenis} (per jenis)", jenis=jenis)
        elif key == "branch":
            resto = str(rec.get("NAMA RESTO") or "").strip()
            # v2.12.2: baris cabang kini ber-JENIS → drill item langsung
            # ter-filter jenis itu (banding fokus 'jenis apa yang naik').
            jenis = str(rec.get("JENIS") or "").strip() or None
            if resto:
                self._open_items(resto, jenis=jenis, root=True)
        elif key in ("items", "new_items", "gone_items"):
            resto = str(rec.get("NAMA RESTO") or "").strip()
            barang = str(rec.get("NAMA BARANG") or "").strip()
            if resto and barang:
                self._open_day(resto, barang, root=True)

    def _drill_dispatch(self, level: str, payload: dict,
                        rec: pd.Series) -> None:
        """Rute klik-2× dari dalam pop-up (turun level / buka dari full)."""
        if self._a is None or self._b is None:
            return
        if level == "tab":
            self._on_tab_double(str(payload.get("tab_key") or ""), rec)
        elif level == "resto":
            resto = str(rec.get("NAMA RESTO") or "").strip()
            if resto:
                self._open_items(resto, jenis=payload.get("jenis"))
        elif level == "item":
            resto = str(rec.get("NAMA RESTO") or "").strip()
            barang = str(rec.get("NAMA BARANG") or "").strip()
            if resto and barang:
                self._open_day(resto, barang)
        # level "day" = paling dalam — tidak ada rincian lanjutan.

    def _labels_sub(self, extra: str = "") -> str:
        a = self._a.get("label") if self._a else "A"
        b = self._b.get("label") if self._b else "B"
        ka_a = self._a.get("key_akhir") if self._a else "?"
        ka_b = self._b.get("key_akhir") if self._b else "?"
        s = f"{a} ({ka_a} hari) vs {b} ({ka_b} hari)"
        if extra:
            s += f" • {extra}"
        return s

    def _open_resto(self, title: str, jenis: str | None = None,
                    per_day: bool = False) -> None:
        """Level RESTO: siapa yang menaikkan / menurunkan angka."""
        with busy_feedback(self._ctx.set_status,
                           "Menghitung rincian per resto"):
            df = compare_level(self._a, self._b, ["NAMA RESTO"],
                               jenis=jenis, per_day=per_day)
        note = ("nilai dibagi jumlah hari tiap bulan (normalisasi 30/31 hari)"
                if per_day else "urut berdasarkan selisih terbesar")
        if jenis:
            note += f"; hanya JENIS {jenis}"
        sub = self._labels_sub(
            f"{note} • klik 2× resto = rincian itemnya")
        self._drill.show_table(title, sub, df, level="resto",
                               payload={"jenis": jenis}, root=True,
                               header_map={"Pembanding": self._label_b_disp})

    def _open_items(self, resto: str, jenis: str | None,
                    root: bool = False) -> None:
        """Level ITEM: item apa saja di satu resto (naik/turun terbesar)."""
        with busy_feedback(self._ctx.set_status,
                           f"Menghitung rincian item di {resto}"):
            df = compare_level(self._a, self._b,
                               ["NAMA RESTO", "NAMA BARANG"], jenis=jenis)
        if not df.empty:
            df = df[df["NAMA RESTO"].astype(str).str.strip() == resto]
        note = f"hanya JENIS {jenis}" if jenis else "semua jenis digabung"
        sub = self._labels_sub(
            f"{note} • klik 2× item = rincian per hari")
        self._drill.show_table(f"📦 Item di {resto}", sub, df, level="item",
                               payload={"resto": resto, "jenis": jenis},
                               root=root,
                               header_map={"Pembanding": self._label_b_disp})

    def _open_day(self, resto: str, barang: str,
                  root: bool = False) -> None:
        """Level HARI: tanggal berapa yang naik (jawaban 'hari apa?')."""
        with busy_feedback(self._ctx.set_status,
                           "Menghitung rincian per hari"):
            df = drill_day_detail(self._a, self._b, resto, barang)
        n = len(df)
        tot_a = float(df["Bulan Ini"].sum()) if n else 0.0
        tot_b = float(df["Pembanding"].sum()) if n else 0.0
        sub = self._labels_sub(
            f"total {tot_a:,.0f} vs {tot_b:,.0f} • semua jenis digabung "
            "• baris = tanggal")
        self._drill.show_table(
            f"📅 Hari 1–{n} — {barang} @ {resto}", sub, df, level="day",
            root=root, header_map={"Pembanding": self._label_b_disp})

    # ------------------------------------------------------------
    # HASIL BANDING
    # ------------------------------------------------------------
    def _agg_a(self) -> dict | None:
        """Agregat bulan berjalan (A) — memo per data_version + key_akhir."""
        if self._ctx.df is None:
            return None
        key = (self._ctx.data_version, self._ctx.key_akhir)
        if self._a_cache is not None and self._a_cache[:2] == key:
            return self._a_cache[2]
        a = aggregate_current(self._ctx.df, self._ctx.key_akhir)
        if a is not None:
            self._a_cache = (key[0], key[1], a)
        return a

    def _combo_months(self) -> list[dict]:
        """Bulan valid utk combo — urut kronologis (lama → baru)."""
        months = []
        for ent in self._entries:
            m = self._loaded.get(ent["path"]) \
                or self._last_results.get(ent["path"])
            if m and not m.get("error"):
                m = dict(m)
                m["label"] = ent.get("label") or m.get("label") or "?"
                months.append(m)
        months.sort(key=lambda m: month_sort_key(m.get("label")))
        return months

    def _rebuild_combo(self, months: list[dict]) -> None:
        """Isi ulang combo (Tipikal + bulan kronologis) tanpa trigger render
        (setCurrentIndex di dalam blok sinyal — klik user tetap memicu
        render lewat _on_combo_changed)."""
        self._combo_version = self._ctx.history_version
        self._cb_b.blockSignals(True)
        self._cb_b.clear()
        typ = self._ctx.history_typical
        if typ is not None:
            n = typ.get("months_count", 0)
            self._cb_b.addItem(f"📊 Tipikal — median {n} bulan", _TYPICAL_KEY)
        for m in months:
            self._cb_b.addItem(str(m.get("label") or "?"), m)
        if self._cb_b.count() == 0:
            self._cb_b.blockSignals(False)
            return
        # Default: Tipikal (deteksi perubahan) bila ada, else bulan TERBARU.
        idx = 0
        if typ is None and months:
            idx = self._cb_b.count() - 1  # bulan terakhir = terbaru
        self._cb_b.setCurrentIndex(idx)
        self._cb_b.blockSignals(False)

    def _finalize(self) -> None:
        """Susun hasil final (bulan termuat + tipikal) → set_history.

        TIDAK membangun combo di sini: set_history menaikkan versi & memancar
        history_ready → _refresh_result mendeteksi versi beda → combo diisi
        ulang LALU render — satu jalur, urutan selalu benar (label hasil edit
        pun ikut tersinkron)."""
        months = self._combo_months()
        typical = None
        if len(months) >= 2:
            with busy_feedback(self._ctx.set_status,
                               "Menghitung tipikal bulan lalu"):
                typical = typical_months(months)
        self._ctx.set_history(months, typical)

    def _refresh_result(self) -> None:
        """Render hasil banding A vs pilihan combo (titik tunggal).

        Combo disinkronkan LEBIH DULU (sebelum cek data A) supaya daftar
        bulan + Tipikal terlihat seketika walau pipeline belum dijalankan —
        tabel menunggu A, combo tidak."""
        self._dirty = False
        months = self._combo_months()
        if self._combo_version != self._ctx.history_version:
            self._rebuild_combo(months)
        a = self._agg_a()
        if a is None:
            self._clear_tables(
                "Jalankan pipeline dulu (tab Pipeline) — banding butuh data "
                "bulan berjalan.")
            return
        if not months:
            self._clear_tables(
                "Belum ada file pembanding — tambahkan file bulan lalu di atas "
                "(1 file = 1 bulan).")
            return
        data = self._cb_b.currentData()
        if data == _TYPICAL_KEY:
            b = self._ctx.history_typical
        elif isinstance(data, dict):
            b = data
        else:
            b = None
        if b is None:
            b = months[-1]  # fallback: bulan terbaru
        with busy_feedback(self._ctx.set_status,
                           f"Banding {a.get('label')} vs {b.get('label')}"):
            res = compare_quantity(a, b, top_n=100)
        self._has_result = True
        self._result_version = (self._ctx.data_version,
                                self._ctx.history_version)
        # v2.10.2: bahan drill-down pop-up — A/B/hasil TERAKHIR dirender.
        self._a, self._b, self._res = a, b, res
        # v2.10.2: bagikan pilihan baseline ke view lain (tabel Anomali —
        # kolom BULAN LALU/PERUBAHAN memakai pembanding yang sama).
        self._ctx.set_banding_baseline(b)
        # v2.10.3 (audit): konteks banding berganti (run baru / pembanding /
        # combo) — pop-up yang masih terbuka menampilkan salinan konteks
        # LAMA; ditutup supaya tak menyesatkan.
        self._close_popups()
        # v2.12.2: (1) judul kolom 'Pembanding' → NAMA BULAN pilihan
        # (permintaan user — label sudah dihitung compare_quantity, kini
        # dipakai di header kolom, bukan cuma subjudul); (2) halaman
        # cabang/item/baru dapat kolom ✓ follow-up + kolom JENIS (sumber
        # agg_jenis). Alias dipasang di headerData MODEL (data/sort/record
        # tetap nama kanonik 'Pembanding' — kontrak test lama utuh).
        self._label_b_disp = self._col_header_b(b)
        aliases = {"Pembanding": self._label_b_disp}
        # v2.12.4: dataset berganti → nilai funnel halaman bisa jadi tak ada
        # lagi di data baru — reset state lokal (pola AnomaliView).
        if self._pf_ver != self._ctx.data_version:
            self._pf_ver = self._ctx.data_version
            for pf in self._pfilters.values():
                pf.clear()
        for key, df_key in _RESULT_KEYS.items():
            df = res.get(df_key)
            self._tables[key].model().set_header_map(aliases)
            if key in _FU_PAGES:
                out, vis = self._fu_frame(df)
                self._page_src[key] = (out, vis)
                m_df, m_vis = self._page_mask(key)
                self._tables[key].set_dataframe(m_df, visible_cols=m_vis)
            else:
                self._page_src[key] = df if isinstance(df, pd.DataFrame) \
                    else None
                self._tables[key].set_dataframe(self._page_mask(key))
        ka_a = res.get("key_akhir_a")
        ka_b = res.get("key_akhir_b")
        self._lbl_compare.setText(
            f"✓ Bulan berjalan ({ka_a} hari) vs {res.get('label_b')} "
            f"({ka_b} hari) — 'Waste per Hari' menormalkan beda panjang bulan.")

    # ------------------------------------------------------------
    # v2.12.4 — FUNNEL LOKAL PER HALAMAN (SEMUA kolom ber-funnel)
    # ------------------------------------------------------------
    def _on_page_filter(self, page: str, col: str, values) -> None:
        """Menu funnel header halaman → saring TAMPILAN halaman itu saja
        (bahan _page_src tersimpan — tanpa compare ulang; ✓ / drill /
        ekspor tak tersentuh)."""
        pf = self._pfilters.setdefault(page, {})
        if values:
            pf[col] = list(values)
        else:
            pf.pop(col, None)
        src = self._page_src.get(page)
        if src is None:
            return
        if page in _FU_PAGES:
            m_df, m_vis = self._page_mask(page)
            if isinstance(m_df, pd.DataFrame):
                self._tables[page].set_dataframe(m_df, visible_cols=m_vis)
        elif isinstance(src, pd.DataFrame):
            self._tables[page].set_dataframe(self._page_mask(page))
        self._ctx.set_status(
            f"⧩ Filter tampilan ({len(pf)} kolom) diterapkan di halaman "
            "ini — hasil banding tak berubah", "done")

    def _pf_state(self, page: str, col: str):
        """Status funnel kolom utk MELUKIS (aktif = terisi merah)."""
        v = self._pfilters.get(page, {}).get(col)
        return list(v) if v else None

    def _page_mask(self, page: str):
        """Bahan halaman + mask isin funnel lokal → SIAP set_dataframe.

        FU page: bahan (df, vis) → kembalikan (masked, vis); halaman lain:
        kembalikan df masked. Tabel banding ≤ ratusan baris — mask murah."""
        src = self._page_src.get(page)
        fu = page in _FU_PAGES
        if fu and isinstance(src, tuple):
            df, vis = src[0], src[1]
        else:
            df, vis = src, None
        pf = self._pfilters.get(page) or {}
        if not isinstance(df, pd.DataFrame) or not pf:
            return (df, vis) if fu else df
        m = pd.Series(True, index=df.index)
        for col, vals in pf.items():
            if col in df.columns and vals:
                m &= df[col].isin(vals)
        out = df[m]
        return (out, vis) if fu else out

    # ------------------------------------------------------------
    # v2.12.2 — JUDUL KOLOM NAMA BULAN + ✓ FOLLOW-UP DI TABEL BANDING
    # ------------------------------------------------------------
    def _col_header_b(self, b: dict | None) -> str:
        """Judul kolom pengganti kata 'Pembanding' — NAMA BULAN pilihan
        (mis. 'Juli 2026'); tipikal → 'Tipikal — median N bulan'."""
        if not b:
            return "Pembanding"
        n = b.get("months_count")
        if n:
            return f"Tipikal — median {int(n)} bulan"
        return str(b.get("label") or "Pembanding")

    def _fu_maps(self):
        """Peta baris banding → sidik jari baris anomali bulan berjalan.

        item:   (jenis, resto, barang) → [fp, ...]  (halaman Item/Baru)
        branch: (jenis, resto) → [fp, ...]           (halaman Cabang)
        Memo per data_version — groupby 25.901 baris ≈ 0,1-0,2 dtk SEKALI
        per dataset (pipeline nyata sudah bawa followup_fps dari worker →
        fingerprints() = memo hit, tanpa md5 ulang). Normalisasi kunci =
        konvensi _aggregate/_jenis_item_totals (strip + JENIS upper).

        v2.12.3 (Opsi A — "1 item aja per resto"): peta CENTANG hanya
        memuat baris ber-ANOMALY STATUS ≠ 'Normal'. Data asli: 797 dari
        25.901 baris adalah anomali — tanpa saringan, 1 centang item
        memasukkan 6-14 baris (maks 34) yang 97%-nya baris placeholder
        Normal TOTAL=0 (5 KETERANGAN standar × duplikat pengajuan);
        terukur: 75% item×resto punya TEPAT 1 baris anomali → centang
        = "1 item per resto". Kolom ANOMALY STATUS absen (fixture test)
        → fallback perilaku lama PERSIS (semua baris). Peta PENUH tetap
        dibangun untuk LEPAS centang (lihat _on_fu_check)."""
        c = self._ctx
        if c.df is None:
            return None
        if (self._fu_item is not None and self._fu_ver == c.data_version):
            return self._fu_item, self._fu_branch
        fps = c.fingerprints()
        if fps is None:
            return None
        d = c.df

        def _build(frame: pd.DataFrame,
                   fp_series: pd.Series) -> tuple[dict, dict]:
            n = len(frame)

            def _col(name: str) -> pd.Series:
                if name in frame.columns:
                    return frame[name].astype(str).str.strip()
                return pd.Series([""] * n, index=frame.index,
                                 dtype="object")

            base = pd.DataFrame({
                "JENIS": _col("JENIS").str.upper().to_numpy(),
                "NAMA RESTO": _col("NAMA RESTO").to_numpy(),
                "NAMA BARANG": _col("NAMA BARANG").to_numpy(),
                "__FP": fp_series.astype(str).to_numpy(),
            })
            it = base.groupby(
                ["JENIS", "NAMA RESTO", "NAMA BARANG"],
                sort=False)["__FP"].apply(list).to_dict()
            br = base.groupby(
                ["JENIS", "NAMA RESTO"], sort=False)["__FP"].apply(
                    list).to_dict()
            return it, br

        # Peta PENUH (semua baris dataset) — dipakai saat LEPAS centang.
        self._fu_item_full, self._fu_branch_full = _build(d, fps)
        # v2.12.3 Opsi A: peta CENTANG = hanya baris anomali.
        d2, fps2 = d, fps
        if "ANOMALY STATUS" in d.columns:
            st = d["ANOMALY STATUS"].astype(str).str.strip()
            m = st.ne("Normal") & st.ne("") & st.ne("nan") & st.ne("None")
            if bool(m.any()):
                d2, fps2 = d[m], fps[m]
        self._fu_item, self._fu_branch = _build(d2, fps2)
        self._fu_ver = c.data_version
        return self._fu_item, self._fu_branch

    def _fu_frame(self, df):
        """Salinan render + kolom ✓ + __FPS utk halaman centang (kolom
        data tetap nama kanonik — alias judul dipasang terpisah di
        headerData model).

        Centang = SEMUA baris anomali (jenis, resto[, barang]) yang cocok
        sudah masuk follow-up; lepas = keluarkan semuanya sekaligus
        (remove_followup_many — satu broadcast, satu tulis disk)."""
        if not isinstance(df, pd.DataFrame):
            return None, None
        if df.empty:
            return df, None
        maps = self._fu_maps()
        item_map, branch_map = maps if maps else ({}, {})
        fset = self._ctx.followup_set()
        out = df.copy()
        fps_col: list = []
        checked: list = []
        for rec in out.to_dict("records"):
            jenis = str(rec.get("JENIS") or "").strip().upper()
            resto = str(rec.get("NAMA RESTO") or "").strip()
            if _FPS_COL in out.columns and _FPS_COL in rec:
                fps = list(rec[_FPS_COL] or [])
            elif "NAMA BARANG" in rec:
                barang = str(rec.get("NAMA BARANG") or "").strip()
                fps = item_map.get((jenis, resto, barang), [])
            else:
                fps = branch_map.get((jenis, resto), [])
            fps_col.append(list(fps))
            checked.append(bool(fps) and all(f in fset for f in fps))
        out[_FPS_COL] = fps_col
        out.insert(0, CHECK_COL, checked)
        vis = [CHECK_COL] + [c for c in out.columns
                              if c not in (CHECK_COL, _FPS_COL)]
        return out, vis

    def _on_fu_check(self, page: str, row: int, checked: bool) -> None:
        """Klik ✓ baris banding → (v2.12.3 Opsi A) CENTANG = masukkan
        SEMUA baris ANOMALI terkait (jenis, resto[, barang]) — baris
        Normal TOTAL=0 tidak ikut; LEPAS = keluarkan SEMUA baris item
        itu (anomali + fps noise warisan v2.12.2) sekaligus — satu
        broadcast, satu tulis disk."""
        m = self._tables[page].model()
        rec = m.record(row)
        fps = rec.get(_FPS_COL) if rec is not None else None
        if not fps:
            # Baris tanpa pasangan anomali (mis. item di luar run saat
            # ini, atau item tanpa baris anomali — semua Normal) →
            # kembalikan centangan visual (state tak berubah).
            mdf = m.dataframe
            if (mdf is not None and CHECK_COL in mdf.columns
                    and 0 <= row < len(mdf)):
                col = mdf.columns.get_loc(CHECK_COL)
                mdf.iat[row, col] = False
                # v2.13.8 (audit E5): notify_column_changed MENYINKRONKAN
                # snapshot numpy model — dulu dataChanged.emit manual
                # mem-bypass snapshot (nilai basi tersimpan utk sel itu).
                m.notify_column_changed(CHECK_COL)
            self._ctx.set_status(
                "Item ini tidak punya baris anomali di bulan berjalan "
                "(semua Normal) — tidak ada yang perlu ditindaklanjuti.",
                "done")
            return
        if checked:
            n = self._ctx.add_followup_many(fps)
            total = len(self._ctx.followup_keys)
            self._ctx.set_status(
                f"✓ {fmt_id(n)} baris anomali masuk Follow Up — total "
                f"{fmt_id(total)}", "done")
        else:
            # Lepas: keluarkan anomali fps + SEMUA fps item ini yang
            # mungkin tersimpan dari centangan v2.12.2 (saat itu belum
            # tersaring — ikut membawa baris Normal). Peta penuh =
            # kebalikan saringan Opsi A.
            jenis = str(rec.get("JENIS") or "").strip().upper()
            resto = str(rec.get("NAMA RESTO") or "").strip()
            barang = rec.get("NAMA BARANG")
            maps = self._fu_maps()
            if maps is not None:
                if barang is not None:
                    extra = self._fu_item_full.get(
                        (jenis, resto, str(barang).strip()), [])
                else:
                    extra = self._fu_branch_full.get((jenis, resto), [])
            else:
                extra = []
            remove_all = list(dict.fromkeys(list(fps) + list(extra)))
            n = self._ctx.remove_followup_many(remove_all)
            total = len(self._ctx.followup_keys)
            self._ctx.set_status(
                f"✓ {fmt_id(n)} baris dikeluarkan dari Follow Up — total "
                f"{fmt_id(total)}", "done")

    def _on_followup_changed(self) -> None:
        """✓ berubah di mana pun (tab Anomali / banding / massal) →
        segarkan kolom ✓ banding IN-PLACE (dataChanged satu kolom —
        pola AnomaliView._on_followup_changed; cache fit tak tersentuh)."""
        fset = self._ctx.followup_set()
        for page in _FU_PAGES:
            m = self._tables[page].model()
            mdf = m.dataframe
            if (mdf is not None and len(mdf) > 0
                    and CHECK_COL in mdf.columns
                    and _FPS_COL in mdf.columns):
                mdf[CHECK_COL] = [
                    bool(fs) and all(f in fset for f in fs)
                    for fs in mdf[_FPS_COL]]
                m.notify_column_changed(CHECK_COL)

    def _clear_tables(self, msg: str) -> None:
        for table in self._tables.values():
            table.set_dataframe(None)
        self._page_src.clear()  # v2.12.4: bahan funnel halaman ikut kosong
        self._lbl_compare.setText(msg)
        self._has_result = False
        # v2.10.2: bahan drill ikut dikosongkan (pop-up tak membuka data basi).
        self._a, self._b, self._res = None, None, None
        # v2.10.3 (audit): pop-up yang masih terbuka menampilkan tabel data
        # lama — ditutup (drill sudah di-guard _a/_b None, tapi TAMPILAN
        # tabel lamanya tetap menyesatkan bila dibiarkan).
        self._close_popups()


def fmt_run_label(summary: dict | None, key_akhir: int) -> str:
    label = "(run terakhir)"
    if summary:
        rows = summary.get("total_rows", 0)
        # v2.12.2: 'key_akhir' = jargon internal — pakai istilah awam.
        label = f"{fmt_id(rows)} baris • {key_akhir} hari data"
    return label
