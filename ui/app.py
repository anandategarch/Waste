"""app.py — MainWindow + main() (v2.6.0 rebuild PySide6).

Struktur:
- Toolbar: Export Excel + Bantuan
- QTabWidget 6 tab (v2.13.1: + Scorecard Cabang): Anomali (default) ·
  Follow Up · Hari Mencurigakan · Scorecard Cabang · Banding Periode ·
  Pipeline — render lazy per-view (H2). Tab Scorecard & Pipeline dibungkus
  QScrollArea (v2.13.6) — konten panjang tetap terjangkau di layar kecil.
- Status bar: pesan status + hitungan baris/anomali permanen

v2.12.4: sidebar filter kiri (v2.8.0) DIHAPUS — filter kini lewat
funnel di judul kolom tabel (SEMUA kolom, v2.12.4) + tombol
✕ Hapus Filter di tab Anomali & Hari. Tabel memakai lebar penuh
jendela.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.logging_setup import setup_logging
from waste_anomaly.utils import load_config

from .shared import APP_DIR, APP_TITLE, APP_VERSION, bundle_res_dir, fmt_id
from .state import AppContext
from .theme import QSS
from .view_anomali import AnomaliView
from .view_followup import FollowUpView
from .view_hari import HariView
from .view_periode import PeriodeView
from .view_pipeline import PipelineView
from .view_scorecard import ScorecardView
from .workers import ExportWorker
from waste_anomaly.followup import followup_path

_HELP_HTML = """
<h2>Panduan Singkat</h2>
<p><b>Alur kerja:</b> tab <b>Pipeline</b> → pilih workbook → <b>Mulai Pipeline</b>
→ buka tab <b>Anomali</b> untuk mulai memburu anomali.</p>
<h3>Tab Anomali (pemburu anomali)</h3>
<ul>
<li>Tabel anomali ter-ranking (skor tertinggi di atas; klik header kolom untuk sort).</li>
<li>Klik baris → <b>pop-up detail ringkas</b> (v2.13.9): <b>Ringkasan</b> (total sebulan, puncak sehari + tanggalnya, vs penjualan, vs cabang lain, vs bulan lalu, peringkat) → <b>sinyal yang terpicu saja</b> (chip merah) → alasan → <b>peta nilai per hari 1–31</b> → tombol tindak lanjut. Seluruh kolom data tetap tersedia lewat tombol <b>▸ Tampilkan semua kolom data</b> di bawah.</li>
<li>Tombol drill-down di pop-up: fokus cabang / item / alasan dari baris terpilih; tombol <b>☑ Masuk Follow Up</b> mengumpulkan baris ke daftar tindak lanjut.</li>
<li><b>Klik 2× baris TIDAK lagi memfilter</b> (v2.13.5) — fokus cabang/item hanya lewat tombol di pop-up, supaya klik 1× selalu membuka pop-up detail.</li>
<li>"Skor ≥" menyembunyikan anomali ber-skor rendah (skor maksimum = 19).</li>
</ul>
<h3>Tab Hari Mencurigakan (v2.9.0)</h3>
<ul>
<li>Jawaban untuk: "potensi salah angka terjadi di <b>tanggal berapa</b> (1–31)?"</li>
<li>Bukti hari = angka jauh di atas cabang lain di hari sama (mis. 404×), atau ≥ 50% waste sebulan di satu hari, atau pola 10× (salah ketik), atau waste cuma 1 hari.</li>
<li>Kolom ALASAN HARI merangkum buktinya dalam satu kalimat; klik baris = pop-up dengan peta hari.</li>
<li><b>Centang ✓ di kolom pertama</b> (v2.13.5) atau tombol <b>☑ Masuk Follow Up</b> di pop-up detail = kumpulkan baris ini ke daftar Follow Up; tombol <b>☑ Centang yang tampil</b> = centang massal hasil filter.</li>
<li><b>Bila ada file bulan lalu</b> (tab Banding Periode): muncul kolom <b>NILAI BULAN LALU</b> — nilai tanggal yang sama bulan sebelumnya + berapa kali lipatnya.</li>
</ul>
<h3>Tab Scorecard Cabang (v2.13.1)</h3>
<ul>
<li>Jawaban untuk pertanyaan manajemen: <b>"kunjungi cabang mana dulu, bawa bukti apa, berapa bisa dihemat?"</b> — tabel per cabang, RANK = urutan kunjungan (urut potensi hemat).</li>
<li>Kolom penting: <b>INTENSITAS %</b> (waste vs penjualan/BOM), <b>KELEBIHAN</b> (potensi hemat vs tipikal cabang lain), <b>ALASAN DOMINAN</b>, <b>HARI TERSANGKA</b>, <b>STATUS INPUT</b> (verdict pelaporan: Lengkap / Berhenti Input / Memang Tak Pernah).</li>
<li><b>Klik 2× baris = rincian cabang</b> (pop-up: top kerugian vs tipikal + profil alasan + verdict input).</li>
<li>KPI: <b>POTENSI HEMAT</b> · <b>INTENSITAS TIPIKAL</b> (median) · <b>CABANG #1</b> · <b>HARI SISTEMIK</b> (hari naik serentak banyak cabang = masalah bersama).</li>
<li>Kartu pendukung: 💰 <b>Top Kerugian vs Tipikal</b> (ranking uang per baris) · 📅 <b>Pola Hari Kalender</b> (Senin–Minggu asli dari nama bulan file) · 🧪 <b>Kualitas Data</b> (pemeriksaan otomatis — arahkan kursor ke sel PENJELASAN utk baca lengkap) · 📈 <b>Tren Bulanan</b> (butuh ≥ 2 file bulan lalu).</li>
<li>Di layar kecil halaman ini <b>bisa digulir</b> (v2.13.6) — semua kartu tetap terjangkau; tombol ⤢ Perbesar Tabel / ⛶ Layar Penuh juga tersedia.</li>
</ul>
<h3>Tab Follow Up (v2.12.0)</h3>
<ul>
<li><b>Centang baris mencurigakan</b> (kolom ✓ di tab Anomali <b>atau tab Hari Mencurigakan</b>, atau tombol ☑ di pop-up detail) → baris terkumpul di tab <b>Follow Up</b> dalam format rekap: TOTAL · AVG · MAX · SOURCE DATA · JENIS · KETERANGAN · NAMA BARANG · NAMA RESTO · SATUAN · hari 1–31.</li>
<li>Tombol <b>☑ Centang yang tampil</b> (tab Anomali & Hari Mencurigakan): centang massal hasil filter saat ini; <b>lepas centang ✓</b> (di semua tab) = keluarkan baris. Centang <b>✓ juga ada di tab Banding Periode</b> (halaman Cabang/Item/Baru): satu centang = semua baris anomali resto/item terkait masuk ke daftar Follow Up yang sama.</li>
<li><b>Hari mencurigakan diberi warna</b>: 🔴 merah = hari tersangka (puncak) · 🟠 amber = ≥ 2× rata-rata hari aktif.</li>
<li>Daftar <b>menetap terhadap filter</b> dan <b>tersimpan otomatis</b> (followup.json) — aman walau aplikasi ditutup; baris yang tak ada lagi di data baru otomatis dipangkas.</li>
<li><b>💾 Ekspor Excel</b>: format rekap + kolom kosong PIC/KATEGORI/PENYEBAB utk diisi petugas (konvensi REKAP MENTAH) — hari mencurigakan ikut berwarna.</li>
</ul>
<h3>Filter (funnel di judul kolom tabel)</h3>
<ul>
<li>SEMUA kolom tabel punya ikon funnel di ujung kanan judulnya — klik = menu: <b>daftar nilai bercentang</b> (angka = jumlah baris), kotak cari, tombol <b>Urut Naik/Turun</b>, dan <b>☑ Pilih Semua</b> (lepas filter kolom itu).</li>
<li>Funnel berwarna <b>merah</b> = kolom itu sedang terfilter. Berlaku di tab Anomali, Hari Mencurigakan, Follow Up (filter tampilan saja — daftar tak berubah), dan Banding Periode (per halaman).</li>
<li>Di tab Anomali & Hari: kolom NAMA RESTO / NAMA BARANG / JENIS / KETERANGAN / STATUS berbagi state yang sama antar kedua tab (dan KPI ikut terfilter); kolom lain = filter tampilan tabel itu saja.</li>
<li>Tombol <b>✕ Hapus Filter</b> (tab Anomali & Hari) = lepas SEMUA filter sekaligus.</li>
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
<li><b>v2.12.2</b> — <b>angka minus otomatis MERAH</b> di semua tabel; kolom
pembanding memakai <b>NAMA BULAN</b> (bukan kata "Pembanding"); tabel banding
menampilkan <b>JENIS</b> (SUSUT/TRIAL/WASTE) per baris cabang/item; tombol
<b>⤢ Perbesar Tabel</b> & <b>⛶ Layar Penuh</b> kini juga ada di tab
<b>Anomali</b>; daftar file banding <b>auto-ciut</b> setelah dimuat (tabel
hasil langsung tinggi penuh).</li>
<li><b>v2.12.4</b> — sidebar filter kiri & slicer chip <b>dihapus</b>:
semua filter lewat <b>funnel di judul kolom</b> (SEMUA kolom punya),
tabel memakai lebar & tinggi penuh.</li>
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
    """Jendela utama: toolbar + 6 tab view + status bar (v2.12.4: tanpa
    sidebar — filter via funnel judul kolom, tabel lebar penuh; v2.13.1:
    + tab Scorecard Cabang)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION} — Pencari Anomali Waste")
        self._set_icon()

        self.ctx = AppContext(load_config(), self,
                              followup_path=followup_path())
        self._export_worker: ExportWorker | None = None
        self._exporting = False

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

    def _build_body(self) -> None:
        # v2.12.4: sidebar filter kiri DIHAPUS (permintaan user — filter
        # lewat funnel judul kolom) → QTabWidget langsung jadi central
        # widget: tabel memakai lebar PENUH jendela tanpa splitter.
        self._tabs = QTabWidget(self)
        # v2.8.0: 8 → 5 view (Uang/Peer/Kualitas Data dihapus); v2.8.1:
        # 5 → 3 view — Jelajah & Waktu dihapus total bersama modul chart/
        # dashboard (keputusan user). Cek data_quality TETAP jalan di
        # pipeline & export; sheet analisa temporal/money/DQ tetap diexport.
        # v2.12.0: 3 → 5 — tab Follow Up (shortlist centangan ✓, setelah
        # Anomali — alur buruan → tindak lanjut).
        self._views: list[tuple[str, QWidget]] = [
            ("Anomali", AnomaliView(self.ctx)),
            ("Follow Up", FollowUpView(self.ctx)),
            ("Hari Mencurigakan", HariView(self.ctx)),
            # v2.13.1: tab Scorecard Cabang (urutan kunjungan audit +
            # kartu pendukung: top kerugian, pola hari kalender, hari
            # sistemik) — setelah Hari Mencurigakan, sebelum Banding.
            ("Scorecard Cabang", ScorecardView(self.ctx)),
            ("Banding Periode", PeriodeView(self.ctx)),
            ("Pipeline", PipelineView(self.ctx)),
        ]
        for name, view in self._views:
            self._tabs.addTab(view, name)
        # v2.12.0: ref view Follow Up (badge jumlah baris di judul tab).
        self._fu_view = self._views[1][1]
        self._update_followup_badge()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        # Anti-terpotong: bila tab bar sempit, teks di-elide dengan '…'
        # (konvensi jelas) + tombol panah scroll — TIDAK pernah dipotong
        # mentah mid-character. 4 tab (v2.9.0) masih muat di jendela
        # normal; jendela sempit memakai tombol scroll.
        self._tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self._tabs.setUsesScrollButtons(True)
        self.setCentralWidget(self._tabs)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._lbl_status = QLabel("Siap.", self)
        sb.addWidget(self._lbl_status, 1)
        self._lbl_perm = QLabel("—", self)
        sb.addPermanentWidget(self._lbl_perm)

    # ------------------------------------------------------------
    # KONTEKS → UI
    # ------------------------------------------------------------
    def _wire_context(self) -> None:
        self.ctx.status.connect(self._on_status)
        # log_line: subscriber sesungguhnya = panel log PipelineView
        # (view_pipeline.py: ctx.log_line.connect(self._append_log)).
        self.ctx.data_ready.connect(self._on_data_ready)
        # v2.12.4: sidebar dihapus — tidak ada widget filter global yang
        # perlu disinkronkan (funnel tabel membaca state saat melukis).
        # v2.12.0: daftar follow-up berubah → badge jumlah di judul tab.
        self.ctx.followup_changed.connect(self._on_followup_changed)

    def _on_status(self, text: str, kind: str) -> None:
        # v2.12.1 (perf): setStyleSheet HANYA saat warna berganti —
        # parse QSS + repolish per pesan (2-6 pesan per interaksi tombol)
        # terukur beberapa ms sia-sia di mesin lambat; teks tetap tiap kali.
        color = {"done": "#16a34a", "error": "#dc2626"}.get(kind, "#64748b")
        if color != getattr(self, "_status_color", None):
            self._lbl_status.setStyleSheet(f"color:{color};")
            self._status_color = color
        self._lbl_status.setText(text)

    def _on_data_ready(self) -> None:
        df = self.ctx.df
        if df is None:
            return
        # v2.12.4: sidebar filter dihapus — tidak ada combo/search yang
        # perlu diisi/disinkronkan; state filter direset oleh set_dataset.
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
        # v2.12.0: dataset baru — pangkas centangan follow-up yang
        # barisnya tak ada lagi (pipeline ulang / file berganti). Stale
        # key tak berbahaya (mask isin), tapi dibuang supaya badge
        # jujur + followup.json tak menumpuk sampah.
        dropped = self.ctx.prune_followup()
        if dropped:
            self.ctx.set_status(
                f"✓ {fmt_id(dropped)} centangan follow-up tidak ada lagi "
                "di data baru — dihapus dari daftar", "done")

    def _on_followup_changed(self) -> None:
        """Daftar follow-up berubah (toggle/bulk/prune) → badge tab."""
        self._update_followup_badge()

    def _update_followup_badge(self) -> None:
        """Judul tab 'Follow Up (N)' — jumlah baris terkumpul."""
        if not hasattr(self, "_fu_view") or self._fu_view is None:
            return
        idx = self._tabs.indexOf(self._fu_view)
        if idx < 0:
            return
        n = len(self.ctx.followup_keys)
        self._tabs.setTabText(idx, f"Follow Up ({fmt_id(n)})" if n
                               else "Follow Up")
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
