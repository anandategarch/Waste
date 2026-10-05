"""app.py — MainWindow + main() (v2.6.0 rebuild PySide6).

Struktur:
- Toolbar: toggle sidebar filter (☰ Filter / Ctrl+Shift+F, v2.8.0) +
  Export Excel + Bantuan
- Sidebar kiri: filter (cari, cabang, status, keterangan, rentang hari,
  chip aktif) + profil filter tersimpan — bisa disembunyikan/dimunculkan
  (v2.8.0: tabel & chart memakai lebar penuh saat sidebar disembunyikan)
- QTabWidget 4 view (v2.9.0: + Hari Mencurigakan): Anomali (default) ·
  Hari Mencurigakan · Banding Periode · Pipeline — render lazy per-view (H2)
- Status bar: pesan status + hitungan baris/anomali permanen
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.filters import (
    delete_profile,
    list_profile_names,
    restore_filters,
    save_profile,
    snapshot_filters,
)
from waste_anomaly.logging_setup import setup_logging
from waste_anomaly.utils import load_config, norm_text

from .shared import APP_DIR, APP_TITLE, APP_VERSION, bundle_res_dir, fmt_id
from .state import AppContext
from .theme import QSS
from .view_anomali import AnomaliView
from .view_hari import HariView
from .view_periode import PeriodeView
from .view_pipeline import PipelineView
from .widgets import Card, WLabel
from .workers import ExportWorker

_HELP_HTML = """
<h2>Panduan Singkat</h2>
<p><b>Alur kerja:</b> tab <b>Pipeline</b> → pilih workbook → <b>Mulai Pipeline</b>
→ buka tab <b>Anomali</b> untuk mulai memburu anomali.</p>
<h3>Tab Anomali (pemburu anomali)</h3>
<ul>
<li>Tabel anomali ter-ranking (skor tertinggi di atas; klik header kolom untuk sort).</li>
<li>Klik baris → <b>pop-up detail</b>: 12 sinyal, angka pembanding, % to BOM (waste vs penjualan), peta nilai per hari 1–31, dan konteks lengkap.</li>
<li>Tombol drill-down di pop-up: fokus cabang / item / alasan dari baris terpilih; klik 2× baris = fokus cabang+item.</li>
<li>"Skor ≥" menyembunyikan anomali ber-skor rendah (skor maksimum = 19).</li>
</ul>
<h3>Tab Hari Mencurigakan (v2.9.0)</h3>
<ul>
<li>Jawaban untuk: "potensi salah angka terjadi di <b>tanggal berapa</b> (1–31)?"</li>
<li>Bukti hari = angka jauh di atas cabang lain di hari sama (mis. 404×), atau ≥ 50% waste sebulan di satu hari, atau pola 10× (salah ketik), atau waste cuma 1 hari.</li>
<li>Kolom ALASAN HARI merangkum buktinya dalam satu kalimat; klik baris = pop-up dengan peta hari.</li>
<li><b>Bila ada file bulan lalu</b> (tab Banding Periode): muncul kolom <b>NILAI BULAN LALU</b> — nilai tanggal yang sama bulan sebelumnya + berapa kali lipatnya.</li>
</ul>
<h3>Filter (sidebar kiri)</h3>
<ul>
<li>Cari, cabang, status, keterangan, rentang hari — berlaku di tab Anomali & Hari Mencurigakan.</li>
<li>Profil filter bisa disimpan & dipulihkan.</li>
<li>Sidebar bisa disembunyikan (☰ Filter / Ctrl+Shift+F) — tabel memakai lebar penuh.</li>
</ul>
<h3>Tab lain</h3>
<ul>
<li><b>Banding Periode</b> (v2.10.0) — bulan berjalan vs <b>daftar file bulan lalu</b>
(1 file = 1 bulan, format REKAP MENTAH — kuantiti tanpa BOM). Nama bulan dibaca
otomatis dari nama file; daftar <b>diingat</b> antar sesi; dimuat di latar belakang.
Banding per bulan atau vs <b>Tipikal</b> (median beberapa bulan): ringkasan,
cabang/item bergerak, item baru/hilang — semua murni kuantiti.</li>
<li><b>Tabel & pop-up rincian</b> (v2.10.2) — tombol <b>⤢ Perbesar Tabel</b>
(ciyutkan daftar file) & <b>⛶ Layar Penuh</b> (tabel tab aktif satu monitor; Esc
kembali). <b>Klik 2× baris</b> di semua tab banding = pop-up rantai rincian
<b>Total → resto → item → per hari</b> ("total naik — resto mana — item apa —
hari berapa").</li>
<li><b>Kolom perubahan di tab Anomali</b> (v2.10.2) — bila ada pembanding:
kolom <b>BULAN LALU</b>, <b>PERUBAHAN %</b> (+35,5% / BARU) & kategori
<b>PERUBAHAN</b> (filter "Perubahan:") — memisahkan <b>lonjakan baru</b>
(kandidat salah input) dari <b>waste kronis</b> (tinggi tiap bulan).</li>
</ul>
<h3>💡 Bingung istilah?</h3>
<p><b>Hover (arahkan mouse & diamkan)</b> di: judul kolom tabel, label metrik pop-up,
chip sinyal S1–S12, kartu KPI, dan kontrol filter — muncul penjelasan singkat
bahasa sehari-hari (mis. "% to BOM = waste dibanding penjualan").</p>
<p><b>Export</b>: tombol <b>💾 Export Excel</b> di toolbar (selalu tersedia) —
laporan lengkap termasuk sheet analisa (Waste per Hari, Money View, Data Quality).</p>
<p>Semua teks dirancang anti-terpotong: teks panjang otomatis berpindah
baris; tabel tanpa cap baris.</p>
"""


class MainWindow(QMainWindow):
    """Jendela utama: toolbar + sidebar filter (bisa di-hide) + 4 tab view + status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION} — Pencari Anomali Waste")
        self._set_icon()

        self.ctx = AppContext(load_config(), self)
        self._export_worker: ExportWorker | None = None
        self._exporting = False
        # v2.8.0: ukuran splitter tersimpan saat sidebar disembunyikan
        # (dipulihkan saat sidebar dimunculkan kembali).
        self._sidebar_sizes: list[int] = []

        # Ukuran awal: clamp ke layar (M15) + posisi tengah
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            w = min(1500, max(1024, screen.width() - 100))
            h = min(900, max(700, screen.height() - 80))
            self.resize(w, h)
            self.move(max(0, (screen.width() - w) // 2),
                      max(0, (screen.height() - h) // 2))
        self.setMinimumSize(1024, 700)

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._wire_context()

        # Ctrl+F → fokus kotak Cari
        shortcut = QAction(self)
        shortcut.setShortcut("Ctrl+F")
        shortcut.triggered.connect(self._focus_search)
        self.addAction(shortcut)

    # ------------------------------------------------------------
    # BANGUN UI
    # ------------------------------------------------------------
    def _set_icon(self) -> None:
        for icon_path in (bundle_res_dir() / "assets" / "app_icon_64.png",
                          APP_DIR / "assets" / "app_icon_64.png"):
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

    def _build_toolbar(self) -> None:
        bar = self.addToolBar("Utama")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        title = QLabel(f"  📊 {APP_TITLE}  ")
        title.setStyleSheet("color:#f1f5f9; font-size:15px; font-weight:700; background:transparent;")
        bar.addWidget(title)
        sep = QWidget()
        sep.setFixedWidth(12)
        bar.addWidget(sep)

        act_export = QAction("💾 Export Excel", self)
        act_export.setToolTip("Simpan laporan Excel (6 sheet inti + sheet analisa)")
        act_export.triggered.connect(self._export_excel)
        bar.addAction(act_export)
        self._act_export = act_export

        act_help = QAction("❓ Bantuan", self)
        act_help.triggered.connect(self._show_help)
        bar.addAction(act_help)

        # v2.8.0: toggle sidebar filter — disembunyikan → QTabWidget (tabel/
        # chart) memakai lebar penuh jendela; dimunculkan → ukuran splitter
        # tersimpan dipulihkan. Checkable supaya status terlihat jelas.
        act_filter = QAction("☰ Filter", self)
        act_filter.setCheckable(True)
        act_filter.setChecked(True)
        act_filter.setShortcut("Ctrl+Shift+F")
        act_filter.setToolTip(
            "Sembunyikan/tampilkan sidebar filter (Ctrl+Shift+F) — "
            "saat disembunyikan, tabel & chart memakai lebar penuh.")
        act_filter.toggled.connect(self._toggle_sidebar)
        bar.addAction(act_filter)
        self._act_filter = act_filter

    def _build_body(self) -> None:
        split = QSplitter(Qt.Orientation.Horizontal, self)
        self._split = split  # v2.8.0: referensi utk toggle sidebar
        split.addWidget(self._build_sidebar())
        self._tabs = QTabWidget(split)
        # v2.8.0: 8 → 5 view (Uang/Peer/Kualitas Data dihapus); v2.8.1:
        # 5 → 3 view — Jelajah & Waktu dihapus total bersama modul chart/
        # dashboard (keputusan user). Cek data_quality TETAP jalan di
        # pipeline & export; sheet analisa temporal/money/DQ tetap diexport.
        self._views: list[tuple[str, QWidget]] = [
            ("Anomali", AnomaliView(self.ctx)),
            ("Hari Mencurigakan", HariView(self.ctx)),
            ("Banding Periode", PeriodeView(self.ctx)),
            ("Pipeline", PipelineView(self.ctx)),
        ]
        for name, view in self._views:
            self._tabs.addTab(view, name)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        # Anti-terpotong: bila tab bar sempit, teks di-elide dengan '…'
        # (konvensi jelas) + tombol panah scroll — TIDAK pernah dipotong
        # mentah mid-character. 4 tab (v2.9.0) masih muat di jendela
        # normal; jendela sempit memakai tombol scroll.
        self._tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self._tabs.setUsesScrollButtons(True)
        split.setSizes([300, 1200])
        # v2.6.1: sidebar menyusut PROPORSIONAL saat window kecil (dulu
        # menahan ~300px & memiskinkan view → tabel kehilangan ruang; di
        # window 1024 viewport tabel cuma 662px). Rasio 3:12 ≈ 300:1200.
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 12)
        self._sidebar.setMinimumWidth(230)
        self._sidebar.setMaximumWidth(380)
        self.setCentralWidget(split)

    def _build_sidebar(self) -> QWidget:
        self._sidebar = QScrollArea()
        self._sidebar.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # ===== Kartu FILTER =====
        filt = Card(host)
        fl = QVBoxLayout(filt)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(8)
        t = WLabel("🔍 Filter Drill-Down", filt)
        t.setObjectName("cardTitle")
        fl.addWidget(t)

        fl.addWidget(WLabel("Cari (semua kolom):", filt))
        self._ent_search = QLineEdit(filt)
        self._ent_search.setPlaceholderText("ketik lalu tunggu 0,3 detik…")
        self._ent_search.setClearButtonEnabled(True)
        # v2.9.0: tooltip kontrol filter (permintaan user — semua istilah
        # mudah dicerna).
        self._ent_search.setToolTip(
            "Cari bebas di SEMUA kolom: nama cabang, nama item, alasan…\n"
            "Berlaku otomatis setelah Anda berhenti mengetik 0,3 detik.\n"
            "Kosongkan (tombol ✕) untuk menghapus pencarian.")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_search)
        self._ent_search.textChanged.connect(
            lambda _t: self._search_timer.start())
        self._ent_search.returnPressed.connect(self._apply_search_now)
        fl.addWidget(self._ent_search)

        fl.addWidget(WLabel("Cabang:", filt))
        self._cb_cabang = QComboBox(filt)
        self._cb_cabang.setMaximumWidth(260)
        self._cb_cabang.setToolTip(
            "Pilih satu cabang (drill-down) — '(Semua)' = tanpa filter cabang.\n"
            "Pilihan selalu dari data PENUH, tidak menyusut saat ada filter lain.")
        self._cb_cabang.currentIndexChanged.connect(
            lambda _i: self._on_combo("cabang", self._cb_cabang))
        fl.addWidget(self._cb_cabang)

        fl.addWidget(WLabel("Status anomali:", filt))
        self._cb_status = QComboBox(filt)
        self._cb_status.setToolTip(
            "Prioritas Tinggi = skor ≥ 8 (paling layak diperiksa) ·\n"
            "Potensi Anomali = skor 5–7 · Perlu Review = skor 3–4 ·\n"
            "Normal = skor < 3 (kebanyakan baris).")
        for s in ("(Semua)", "Prioritas Tinggi", "Potensi Anomali",
                  "Perlu Review", "Normal"):
            self._cb_status.addItem(s)
        self._cb_status.currentIndexChanged.connect(
            lambda _i: self._on_combo("status", self._cb_status))
        fl.addWidget(self._cb_status)

        fl.addWidget(WLabel("Keterangan (alasan):", filt))
        self._cb_ket = QComboBox(filt)
        self._cb_ket.setMaximumWidth(260)
        self._cb_ket.setToolTip(
            "Alasan pencatatan waste (kolom KETERANGAN):\n"
            "mis. Alat/Mesin, Cancel Nota, Over Stock, Eksternal…")
        self._cb_ket.currentIndexChanged.connect(
            lambda _i: self._on_combo("keterangan", self._cb_ket))
        fl.addWidget(self._cb_ket)

        rng = QWidget(filt)
        rl = QVBoxLayout(rng)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        self._chk_hari = QCheckBox("Rentang hari kejadian (HARI MAX)", rng)
        self._chk_hari.setToolTip(
            "Batasi anomali yang NILAI TERBESARNYA jatuh di rentang tanggal ini.\n"
            "Contoh: 13–15 = hanya anomali yang puncaknya di tanggal 13, 14, atau 15.\n"
            "Gunakan bersama tab Hari Mencurigakan untuk mengisolasi tanggal.")
        self._chk_hari.toggled.connect(self._on_hari_toggled)
        rl.addWidget(self._chk_hari)
        spins = QWidget(rng)
        sl = QHBoxLayout(spins)
        sl.setContentsMargins(8, 0, 0, 0)
        sl.setSpacing(6)
        self._spin_dmin = QSpinBox(spins)
        self._spin_dmax = QSpinBox(spins)
        for s in (self._spin_dmin, self._spin_dmax):
            s.setRange(1, 31)
            s.setToolTip("Tanggal awal/akhir (1–31) rentang hari kejadian.")
            s.valueChanged.connect(self._on_hari_changed)
        sl.addWidget(self._spin_dmin)
        sl.addWidget(WLabel("–", spins))
        sl.addWidget(self._spin_dmax)
        sl.addStretch(1)
        rl.addWidget(spins)
        fl.addWidget(rng)

        self._btn_clear = QPushButton("✕ Hapus Semua Filter", filt)
        self._btn_clear.setToolTip(
            "Hapus semua filter, pencarian, dan rentang hari —\n"
            "kembali ke tampilan anomali penuh.\n"
            "(Saat proses, muncul indikator ⏳ + cursor sibuk — bukan hang.)")
        self._btn_clear.clicked.connect(self._clear_filters)
        fl.addWidget(self._btn_clear)

        self._lbl_chips = WLabel("Tidak ada filter aktif.", filt)
        self._lbl_chips.setObjectName("hint")
        self._lbl_chips.setToolTip(
            "Daftar filter yang sedang aktif (chip ringkas).")
        fl.addWidget(self._lbl_chips)
        lay.addWidget(filt)

        # ===== Kartu PROFIL =====
        prof = Card(host)
        pl2 = QVBoxLayout(prof)
        pl2.setContentsMargins(12, 10, 12, 10)
        pl2.setSpacing(8)
        t2 = WLabel("Profil Filter Tersimpan", prof)
        t2.setObjectName("cardTitle")
        t2.setToolTip(
            "Profil = foto (snapshot) SEMUA filter yang sedang aktif —\n"
            "disimpan ke file, bisa dipulihkan kapan saja.\n"
            "Cocok utk kombinasi filter yang sering dipakai.")
        pl2.addWidget(t2)
        self._cb_profile = QComboBox(prof)
        self._cb_profile.setMaximumWidth(260)
        self._cb_profile.setToolTip("Pilih profil → filter dipulihkan seketika.")
        self._cb_profile.currentIndexChanged.connect(self._on_profile_picked)
        pl2.addWidget(self._cb_profile)
        prow = QWidget(prof)
        prl = QHBoxLayout(prow)
        prl.setContentsMargins(0, 0, 0, 0)
        prl.setSpacing(8)
        b_save = QPushButton("Simpan", prow)
        b_save.setToolTip("Simpan kombinasi filter aktif sebagai profil (beri nama).")
        b_save.clicked.connect(self._save_profile)
        prl.addWidget(b_save)
        b_del = QPushButton("Hapus", prow)
        b_del.setToolTip("Hapus profil terpilih dari daftar.")
        b_del.clicked.connect(self._delete_profile)
        prl.addWidget(b_del)
        pl2.addWidget(prow)
        pl2.addWidget(WLabel("Profil = snapshot semua filter aktif (filters.json).", prof))
        lay.addWidget(prof)

        lay.addStretch(1)
        self._sidebar.setWidget(host)
        self._refresh_profile_combo()
        return self._sidebar

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._lbl_status = QLabel("Siap.", self)
        sb.addWidget(self._lbl_status, 1)
        self._lbl_perm = QLabel("—", self)
        sb.addPermanentWidget(self._lbl_perm)

    # ------------------------------------------------------------
    # SIDEBAR HIDE/UNHIDE (v2.8.0)
    # ------------------------------------------------------------
    def _toggle_sidebar(self, visible: bool) -> None:
        """Sembunyikan/munculkan sidebar filter.

        Saat disembunyikan: ukuran splitter disimpan dulu, lalu sidebar
        di-hidden — QSplitter memberi seluruh lebar ke QTabWidget (tabel
        & chart memakai lebar penuh; kolom JENIS yang tadinya responsif
        disembunyikan di 1024px ikut tampil). Saat dimunculkan: ukuran
        tersimpan dipulihkan (rasio 3:12 tetap berlaku bila belum tersimpan).
        """
        if visible:
            self._sidebar.setHidden(False)
            if any(self._sidebar_sizes):
                self._split.setSizes(self._sidebar_sizes)
            self.ctx.set_status("✓ Panel filter dimunculkan", "done")
        else:
            self._sidebar_sizes = self._split.sizes()
            self._sidebar.setHidden(True)
            self.ctx.set_status(
                "✓ Panel filter disembunyikan — Ctrl+Shift+F utk memunculkan",
                "done")

    # ------------------------------------------------------------
    # KONTEKS → UI
    # ------------------------------------------------------------
    def _wire_context(self) -> None:
        self.ctx.status.connect(self._on_status)
        # log_line: subscriber sesungguhnya = panel log PipelineView
        # (view_pipeline.py: ctx.log_line.connect(self._append_log)).
        self.ctx.data_ready.connect(self._on_data_ready)
        self.ctx.filters_changed.connect(self._sync_filter_widgets)

    def _on_status(self, text: str, kind: str) -> None:
        color = {"done": "#16a34a", "error": "#dc2626"}.get(kind, "#64748b")
        self._lbl_status.setStyleSheet(f"color:{color};")
        self._lbl_status.setText(text)

    def _on_data_ready(self) -> None:
        df = self.ctx.df
        if df is None:
            return
        # Populate dropdown dari df PENUH (DD-M3 — pilihan tidak menyusut saat drill)
        if "NAMA RESTO" in df.columns:
            names = sorted(df["NAMA RESTO"].dropna().astype(str).unique())
            self._fill_combo(self._cb_cabang, names)
        if "KETERANGAN" in df.columns:
            kets = sorted({norm_text(v) for v in df["KETERANGAN"].dropna().astype(str)})
            self._fill_combo(self._cb_ket, kets)
        # V26-H2: set_dataset sudah me-reset filter, tapi _fill_combo
        # me-retain teks lama → combo/search/chip sidebar masih menampilkan
        # filter LAMA padahal state None (widget berbohong). Sinkronkan ke
        # state reset (blockSignals → tanpa loop sinyal).
        self._sync_filter_widgets()
        # Permanent status: baris + anomali + waktu run
        total = len(df)
        if "ANOMALY STATUS" in df.columns:
            n_anom = int((df["ANOMALY STATUS"] != "Normal").sum())
        else:
            n_anom = 0
        run_t = self.ctx.last_run_time
        tstr = run_t.strftime("%H:%M:%S") if run_t else "—"
        self._lbl_perm.setText(
            f"{fmt_id(total)} baris • {fmt_id(n_anom)} anomali • run {tstr}")
        self._act_export.setEnabled(True)

    def _fill_combo(self, combo: QComboBox, values: list[str]) -> None:
        combo.blockSignals(True)
        current = combo.currentText()
        combo.clear()
        combo.addItem("(Semua)")
        combo.addItems(values)
        if current:
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
        combo.blockSignals(False)

    # ------------------------------------------------------------
    # FILTER WIDGETS → STATE
    # ------------------------------------------------------------
    def _apply_search(self) -> None:
        self.ctx.set_search(self._ent_search.text())

    def _apply_search_now(self) -> None:
        self._search_timer.stop()
        self.ctx.set_search(self._ent_search.text())

    def _focus_search(self) -> None:
        self._ent_search.setFocus()
        self._ent_search.selectAll()

    def _on_combo(self, key: str, combo: QComboBox) -> None:
        val = combo.currentText()
        value = None if (not val or val == "(Semua)") else val
        self.ctx.set_filter(key, value)

    def _on_hari_toggled(self, on: bool) -> None:
        if on:
            self.ctx.set_day_range(self._spin_dmin.value(), self._spin_dmax.value())
        else:
            self.ctx.set_day_range(None, None)

    def _on_hari_changed(self) -> None:
        if self._chk_hari.isChecked():
            lo, hi = self._spin_dmin.value(), self._spin_dmax.value()
            if lo > hi:
                lo = hi
            self.ctx.set_day_range(lo, hi)

    def _clear_filters(self) -> None:
        self.ctx.reset_filters()
        self.ctx.filters_changed.emit()
        self._sync_filter_widgets()
        self.ctx.set_status("✓ Semua filter dihapus", "done")

    def _sync_filter_widgets(self) -> None:
        """Sinkronkan widget filter dengan state (mis. setelah drill-down)."""
        self._ent_search.blockSignals(True)
        self._ent_search.setText(self.ctx.search)
        self._ent_search.blockSignals(False)
        self._combo_set(self._cb_cabang, self.ctx.active_filters.get("cabang"))
        self._combo_set(self._cb_status, self.ctx.active_filters.get("status"))
        self._combo_set(self._cb_ket, self.ctx.active_filters.get("keterangan"))
        active = self.ctx.day_min is not None
        self._chk_hari.blockSignals(True)
        self._chk_hari.setChecked(active)
        self._chk_hari.blockSignals(False)
        if active:
            self._spin_dmin.setValue(int(self.ctx.day_min or 1))
            self._spin_dmax.setValue(int(self.ctx.day_max or 31))
        self._lbl_chips.setText(self.ctx.filter_summary() or "Tidak ada filter aktif.")

    def _combo_set(self, combo: QComboBox, value) -> None:
        combo.blockSignals(True)
        if value is None or (isinstance(value, list) and not value):
            combo.setCurrentIndex(0)
        else:
            idx = combo.findText(str(value))
            combo.setCurrentIndex(max(0, idx))
        combo.blockSignals(False)

    # ------------------------------------------------------------
    # PROFIL
    # ------------------------------------------------------------
    def _refresh_profile_combo(self) -> None:
        self._cb_profile.blockSignals(True)
        self._cb_profile.clear()
        self._cb_profile.addItem("(pilih profil)")
        for name in list_profile_names():
            self._cb_profile.addItem(name)
        self._cb_profile.blockSignals(False)

    def _on_profile_picked(self) -> None:
        name = self._cb_profile.currentText()
        if not name or name == "(pilih profil)":
            return
        from waste_anomaly.filters import get_profile
        profile = get_profile(name)
        if not profile:
            QMessageBox.information(self, "Profil", f"Profil '{name}' tidak ditemukan.")
            return
        restored = restore_filters(profile)
        self.ctx.search = restored.get("search", "")
        for k in self.ctx.active_filters:
            self.ctx.active_filters[k] = restored.get(k)
        self.ctx.day_min = restored.get("day_min")
        self.ctx.day_max = restored.get("day_max")
        # Penulisan langsung melewati setter → invalidasi memo filter
        # (v2.7.0) supaya filtered_df() tidak menyajikan cache basi.
        self.ctx.invalidate_filter_cache()
        self.ctx.filters_changed.emit()
        self.ctx.set_status(f"✓ Profil '{name}' dipulihkan", "done")

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Simpan Profil", "Nama profil filter:")
        if not ok or not name.strip():
            return
        name = name.strip()
        existing = list_profile_names()
        if name in existing:
            ans = QMessageBox.question(
                self, "Timpa profil?", f"Profil '{name}' sudah ada. Timpa?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        profile = snapshot_filters(
            search=self.ctx.search,
            cabang=self.ctx.active_filters.get("cabang"),
            item=self.ctx.active_filters.get("item"),
            jenis=self.ctx.active_filters.get("jenis") or [],
            keterangan=self.ctx.active_filters.get("keterangan"),
            status=self.ctx.active_filters.get("status"),
            day_min=self.ctx.day_min, day_max=self.ctx.day_max,
        )
        if save_profile(name, profile):
            self._refresh_profile_combo()
            self.ctx.set_status(f"✓ Profil '{name}' disimpan", "done")
        else:
            QMessageBox.critical(self, "Error Profil",
                                 f"Gagal simpan profil '{name}'.")

    def _delete_profile(self) -> None:
        name = self._cb_profile.currentText()
        if not name or name == "(pilih profil)":
            return
        ans = QMessageBox.question(
            self, "Hapus Profil", f"Hapus profil '{name}'?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        if delete_profile(name):
            self._refresh_profile_combo()
            self.ctx.set_status(f"✓ Profil '{name}' dihapus", "done")

    # ------------------------------------------------------------
    # TAB
    # ------------------------------------------------------------
    def _on_tab_changed(self, _index: int) -> None:
        widget = self._tabs.currentWidget()
        on_shown = getattr(widget, "on_shown", None)
        if callable(on_shown):
            try:
                on_shown()
            except Exception as e:  # noqa: BLE001 — render 1 tab ≠ crash app
                self.ctx.set_status(f"⚠ Render tab gagal: {e}", "error")

    # ------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------
    def _export_excel(self) -> None:
        if self._exporting:
            return
        df = self.ctx.df
        if df is None or df.empty:
            QMessageBox.information(self, "Export",
                                    "Belum ada data. Jalankan pipeline dulu.")
            return
        from PySide6.QtWidgets import QFileDialog
        initialdir = Path.home() / "Documents"
        if not initialdir.exists():
            initialdir = Path.home()
        suggested = f"Waste_Anomaly_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Laporan Excel", str(initialdir / suggested),
            "Excel files (*.xlsx);;All files (*.*)")
        if not path:
            return
        self._exporting = True
        self._act_export.setEnabled(False)
        self.ctx.set_status("Menyimpan laporan Excel…", "running")
        self.ctx.log(f"=== Export Excel → {path} ===")
        self._export_worker = ExportWorker(
            df, path, dict(self.ctx.config), self.ctx.key_akhir,
            list(self.ctx.log_lines[-200:]), self)
        self._export_worker.set_log(self.ctx.log)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        # V26-L7: worker QThread selesai → deleteLater (aman post-finish;
        # guard re-entry pakai flag _exporting, bukan referensi worker).
        self._export_worker.finished.connect(self._export_worker.deleteLater)
        self._export_worker.start()

    def _on_export_done(self, result: dict) -> None:
        self._exporting = False
        self._act_export.setEnabled(True)
        if result.get("success"):
            out = result.get("output_path", "")
            n_extra = result.get("extra_sheets_count", 0)
            self.ctx.set_status(f"✓ Laporan Excel tersimpan: {out}", "done")
            self.ctx.log(f"=== Export selesai: {out} ===")
            QMessageBox.information(
                self, "Export Selesai",
                f"Laporan Excel ({6 + n_extra} sheet) tersimpan:\n{out}")
        else:
            self._on_export_failed(result.get("error", "Unknown error"))

    def _on_export_failed(self, err: str) -> None:
        self._exporting = False
        self._act_export.setEnabled(True)
        self.ctx.set_status(f"⚠ Export gagal: {err}", "error")
        self.ctx.log(f"!!! Export gagal: {err}")
        QMessageBox.critical(self, "Export Gagal", err)

    # ------------------------------------------------------------
    # LAIN-LAIN
    # ------------------------------------------------------------
    def _show_help(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Bantuan — Waste Anomaly Detection")
        dlg.resize(640, 560)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser(dlg)
        browser.setHtml(_HELP_HTML)
        lay.addWidget(browser)
        close = QPushButton("Tutup", dlg)
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        # V26-H1: kumpulkan SEMUA worker yang masih hidup — dulu hanya
        # pipeline view + export yang dicek; worker banding periode
        # (kini HistoryWorker, v2.10.0) tercakup lewat atribut kontrak
        # _running/_worker milik view — iterasi _views = tahan urutan.
        busy: list[tuple[str, object]] = []
        for name, view in self._views:
            if getattr(view, "_running", False):
                worker = getattr(view, "_worker", None)
                if worker is not None:
                    busy.append((name, worker))
        if self._exporting and self._export_worker is not None:
            busy.append(("Export Excel", self._export_worker))
        if busy:
            ans = QMessageBox.question(
                self, "Proses masih berjalan",
                "Pipeline/export/perbandingan masih berjalan. Tetap keluar?")
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # Batal yang bisa dibatalkan + tunggu (maks 5 detik/worker) —
            # bila masih hidup, log warning lalu lanjut keluar.
            for name, worker in busy:
                if hasattr(worker, "cancel"):
                    worker.cancel()
                if not worker.wait(5000):
                    self.ctx.log(
                        f"⚠ closeEvent: worker '{name}' masih berjalan setelah "
                        "5 detik — keluar paksa (QThread dihancurkan saat jalan).")
        event.accept()


def _qt_excepthook(exc_type, exc_value, exc_tb) -> None:
    """Semua exception tak tertangani → log file (F11) + stderr."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        import logging
        logging.getLogger("waste_anomaly.ui").error("Unhandled exception:\n%s", text)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> int:
    setup_logging()
    sys.excepthook = _qt_excepthook
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setApplicationName(APP_TITLE)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
