"""app.py — MainWindow + main() (v2.6.0 rebuild PySide6).

Struktur:
- Toolbar: Ekspor Excel + Bantuan
- QTabWidget 6 tab (v2.13.1: + Scorecard Cabang): Anomali (default) ·
  Follow Up · Hari Mencurigakan · Scorecard Cabang · Banding Periode ·
  Pipeline — render lazy per-view (H2). Tab Scorecard & Pipeline dibungkus
  QScrollArea (v2.13.6) — konten panjang tetap terjangkau di layar kecil.
- Status bar: pesan status + hitungan permanen — total baris + DUA
  definisi anomali dilabeli (non-Normal vs prioritas+potensi,
  v2.13.11 gel-2 D3) + waktu run

v2.12.4: sidebar filter kiri (v2.8.0) DIHAPUS — filter kini lewat
funnel di judul kolom tabel (SEMUA kolom, v2.12.4) + tombol
✕ Hapus Filter di tab Anomali & Hari. Tabel memakai lebar penuh
jendela.
"""
from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
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

from .shared import (
    APP_DIR,
    APP_TITLE,
    APP_VERSION,
    LOG_RUN_LINES,
    bundle_res_dir,
    fmt_id,
)
from .state import AppContext
from .theme import QSS
from .icons import Icon, make_qicon
from .view_anomali import AnomaliView
from .view_followup import FollowUpView
from .view_hari import HariView
from .view_periode import PeriodeView
from .view_pipeline import PipelineView
from .view_scorecard import ScorecardView
from .workers import ExportWorker
from waste_anomaly.followup import followup_path

def _build_help_html(config: dict | None = None) -> str:
    """Bangun HTML Bantuan (F1) dari config aktif.

    v2.13.12 (gel-3): (D8) seksi baru "Tab Pipeline (tempat semua
    dimulai)" — tab paling operasional dulunya TAK TERDOKUMENTASIKAN
    (threshold/pratinjau/cancel/log); (D9) fitur 📥 Impor Hasil TL
    (v2.13.3) kini terdokumentasi; (D19) 10 token versi (v2.9.0..
    v2.13.9) dibersihkan jadi teks fitur-deskriptif — Bantuan = panduan
    CARA PAKAI, bukan changelog mini; (C18) angka ambang dari config
    aktif (bukan hardcode). _HELP_HTML = snapshot import-time
    load_config() — kompatibilitas import lama; ctx aplikasi juga
    memuat config sekali di startup (angka startup == angka bantuan).
    """
    # v2.13.12 (gel-3 C18): angka ambang dari config AKTIF (fallback
    # default engine bila korup string/None — models._th), ×100 utk
    # persen, format int polos/float koma-ID (models._fmt_th). Dulu
    # hardcode "≥ 50%" padahal TH_MAX_SHARE_WARN user-editable.
    from .models import _fmt_th, _th
    share_warn = _fmt_th(_th(config, "TH_MAX_SHARE_WARN", 0.5) * 100)
    return f"""
<h2>Panduan Singkat</h2>
<p><b>Alur kerja:</b> tab <b>Pipeline</b> → pilih workbook → <b>Mulai Pipeline</b>
→ buka tab <b>Anomali</b> untuk mulai memburu anomali.</p>
<p><b>Shortcut:</b> <b>Ctrl+1..Ctrl+6</b> pindah tab (sesuai urutan) ·
<b>Ctrl+E</b> ekspor Excel · <b>F1</b> bantuan ini.</p>
<h3>Tab Pipeline (tempat semua dimulai)</h3>
<ul>
<li>Isi <b>Input Workbook</b>: tombol <b>Telusuri…</b> memilih file Excel rekap
(mis. DATA_WASTE.xlsx), atau <b>Pakai Sample</b> mengisi file contoh dari folder
aplikasi. Menekan <b>Enter</b> di kolom workbook langsung menjalankan pipeline.</li>
<li><b>🧮 Olah &amp; Jalankan REKAP MENTAH…</b>: punya file rekap <b>mentah</b>
bulanan (mis. "REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx" — masih berisi
SEMUA jenis: WASTE/SUSUT/TRIAL/BOM/SO/stok; baris judul di atas header pun
boleh)? Klik tombol ini, pilih filenya — <b>semuanya diproses SEKALI
JALAN</b>: saringan WASTE/SUSUT/TRIAL + <b>TOTAL BOM</b> diambil dari baris
BOM + normalisasi nilai + seluruh analisa pipeline berjalan LANGSUNG pada
file mentah tersebut — <b>tanpa file olahan antara</b> dan tanpa klik Mulai
Pipeline lagi (dulu dua proses terpisah: olah dulu, baru jalankan). Progres,
log per-stage, tombol ⏹ Batalkan, dan ringkasan run bekerja seperti biasa.
Jalur file DATA_WASTE standar (Telusuri… → Mulai Pipeline) tetap didukung.</li>
<li><b>📁 Proses dari Folder…</b> (v2.17.2): punya <b>FOLDER</b> berisi file
.xlsx format <b>BJMHAS</b> (sheet "REKAP MENTAH" <b>TANPA</b> kolom NAMA
RESTO — resto identity = nama file; mis. folder "DEVIASI WEEKLY" berisi
BJMHAS.xlsx, BDGUKU.xlsx, dst.)? Klik tombol ini, pilih foldernya —
<b>semua file .xlsx dipindai</b>, sheet REKAP MENTAH diekstrak, <b>NAMA
RESTO disintesis dari nama file</b> (BJMHAS.xlsx → "BJMHAS"), lalu
<b>DIGABUNG</b> jadi satu dataset multi-resto. Pipeline berjalan pada
file gabungan (sementara). Catatan: <b>edit nilai via pop-up menyimpan
ke file sementara INI</b>, bukan file asli di folder (file asli utuh) —
untuk edit file asli, gunakan tombol 🧮 Pilih File Sendiri dgn format
REKAP MENTAH_..._TEGAR.</li>
<li><b>Key Akhir (1–31)</b>: hanya hari 1..N yang dianalisa — bulan berjalan
yang belum penuh cukup diisi sampai tanggal terakhirnya.</li>
<li>Kartu <b>Threshold &amp; Konfigurasi</b> (config.json): nilai ambang
pembentuk sinyal/skor. <b>👀 Pratinjau Ambang</b> menghitung dampak nilai form
SAAT INI (jumlah baris per status) tanpa menyimpan; <b>Simpan config.json</b>
menulis nilai baru; <b>Reset Default</b> mengembalikan form ke bawaan (belum
disimpan). Perubahan <b>berlaku mulai run BERIKUTNYA</b>.</li>
<li><b>▶ Mulai Pipeline ↔ ⏹ Batalkan Run</b> — satu tombol dua-mode;
pembatalan efektif di gerbang antar-stage (tidak perlu menunggu run
selesai).</li>
<li>Selama run: <b>progres</b> (persentase) + <b>log proses</b> per stage
terlihat di kartu "Ringkasan Run &amp; Log Proses".</li>
<li>Setelah selesai: <b>Ringkasan Run</b> menampilkan total baris, prioritas,
potensi, jumlah cabang/item, dst. — hasil siap di tab lain.</li>
</ul>
<h3>Tab Anomali (pemburu anomali)</h3>
<ul>
<li>Tabel anomali ter-ranking (skor tertinggi di atas; klik header kolom untuk sort).</li>
<li>Klik baris → <b>pop-up detail ringkas</b>: <b>Ringkasan</b> (total sebulan, puncak sehari + tanggalnya, vs penjualan, vs cabang lain, vs bulan lalu, peringkat) → <b>sinyal yang terpicu saja</b> (chip merah) → alasan → <b>peta nilai per hari 1–31</b> → tombol tindak lanjut. Seluruh kolom data tetap tersedia lewat tombol <b>▸ Tampilkan semua kolom data</b> di bawah.</li>
<li>Tombol drill-down di pop-up: fokus cabang / item / alasan dari baris terpilih; tombol <b>☑ Masuk Follow Up</b> mengumpulkan baris ke daftar tindak lanjut.</li>
<li><b>Klik 2× baris TIDAK memfilter</b> — fokus cabang/item hanya lewat tombol di pop-up, supaya klik 1× selalu membuka pop-up detail.</li>
<li>"Skor ≥" menyembunyikan anomali ber-skor rendah (skor maksimum = 19).</li>
</ul>
<h3>Tab Hari Mencurigakan</h3>
<ul>
<li>Jawaban untuk: "potensi salah angka terjadi di <b>tanggal berapa</b> (1–31)?"</li>
<li>Bukti hari = angka jauh di atas cabang lain di hari sama (mis. 404×), atau ≥ {share_warn}% waste sebulan di satu hari, atau pola 10× (salah ketik), atau waste cuma 1 hari.</li>
<li>Kolom ALASAN HARI merangkum buktinya dalam satu kalimat; klik baris = pop-up dengan peta hari.</li>
<li><b>Centang ✓ di kolom pertama</b> atau tombol <b>☑ Masuk Follow Up</b> di pop-up detail = kumpulkan baris ini ke daftar Follow Up; tombol <b>☑ Centang yang tampil</b> = centang massal hasil filter.</li>
<li><b>Bila ada file bulan lalu</b> (tab Banding Periode): muncul kolom <b>NILAI BULAN LALU</b> — nilai tanggal yang sama bulan sebelumnya + berapa kali lipatnya.</li>
</ul>
<h3>Tab Scorecard Cabang</h3>
<ul>
<li>Jawaban untuk pertanyaan manajemen: <b>"kunjungi cabang mana dulu, bawa bukti apa, berapa bisa dihemat?"</b> — tabel per cabang, RANK = urutan kunjungan (urut potensi hemat).</li>
<li>Kolom penting: <b>INTENSITAS %</b> (waste vs penjualan/BOM), <b>KELEBIHAN</b> (potensi hemat vs tipikal cabang lain), <b>ALASAN DOMINAN</b>, <b>HARI TERSANGKA</b>, <b>STATUS INPUT</b> (verdict pelaporan: Lengkap / Berhenti Input / Memang Tak Pernah).</li>
<li><b>Klik 2× baris = rincian cabang</b> (pop-up: top kerugian vs tipikal + profil alasan + verdict input).</li>
<li>KPI: <b>POTENSI HEMAT</b> · <b>INTENSITAS TIPIKAL</b> (median) · <b>CABANG #1</b> · <b>HARI SISTEMIK</b> (hari naik serentak banyak cabang = masalah bersama).</li>
<li>Kartu pendukung: 💰 <b>Top Kerugian vs Tipikal</b> (ranking uang per baris) · 📅 <b>Pola Hari Kalender</b> (Senin–Minggu asli dari nama bulan file) · 🧪 <b>Kualitas Data</b> (pemeriksaan otomatis — arahkan kursor ke sel PENJELASAN utk baca lengkap) · 📈 <b>Tren Bulanan</b> (butuh ≥ 2 file bulan lalu).</li>
<li>Di layar kecil halaman ini <b>bisa digulir</b> — semua kartu tetap terjangkau; tombol ⤢ Perbesar Tabel / ⛶ Layar Penuh juga tersedia.</li>
</ul>
<h3>Tab Follow Up</h3>
<ul>
<li><b>Centang baris mencurigakan</b> (kolom ✓ di tab Anomali <b>atau tab Hari Mencurigakan</b>, atau tombol ☑ di pop-up detail) → baris terkumpul di tab <b>Follow Up</b> dalam format rekap: TOTAL · AVG · MAX · SOURCE DATA · JENIS · KETERANGAN · NAMA BARANG · NAMA RESTO · SATUAN · hari 1–31.</li>
<li>Tombol <b>☑ Centang yang tampil</b> (tab Anomali &amp; Hari Mencurigakan): centang massal hasil filter saat ini; <b>lepas centang ✓</b> (di semua tab) = keluarkan baris. Centang <b>✓ juga ada di tab Banding Periode</b> (halaman Cabang/Item/Baru): satu centang = semua baris anomali resto/item terkait masuk ke daftar Follow Up yang sama.</li>
<li><b>Hari mencurigakan diberi warna</b>: 🔴 merah = hari tersangka (puncak) · 🟠 amber = ≥ 2× rata-rata hari aktif.</li>
<li>Daftar <b>menetap terhadap filter</b> dan <b>tersimpan otomatis</b> (followup.json) — aman walau aplikasi ditutup; baris yang tak ada lagi di data baru otomatis dipangkas.</li>
<li><b>💾 Ekspor Excel</b>: format rekap + kolom kosong PIC/KATEGORI/PENYEBAB utk diisi petugas (konvensi REKAP MENTAH) — hari mencurigakan ikut berwarna.</li>
<li><b>📥 Impor Hasil TL</b>: baca kembali file ekspor yang <b>sudah diisi petugas</b> (kolom <b>PIC / KATEGORI / PENYEBAB</b> di sheet FOLLOW UP) → baris yang cocok diberi status <b>Selesai</b> + PIC-nya tampil (kolom STATUS TL &amp; PIC di daftar). Kecocokan memakai kolom kunci + nilai hari 1–31 — <b>aman walau sheet di-sort / di-filter / urutan barisnya diubah di Excel</b>. Hasil tersimpan otomatis (followup_resolved.json); baris terisi yang belum ada di daftar saat ini <b>tetap disimpan</b> — statusnya aktif otomatis bila barisnya dicentang lagi nanti.</li>
</ul>
<h3>Filter (funnel di judul kolom tabel)</h3>
<ul>
<li>SEMUA kolom tabel punya ikon funnel di ujung kanan judulnya — klik = menu: <b>daftar nilai bercentang</b> (angka = jumlah baris), kotak cari, tombol <b>Urut Naik/Turun</b>, dan <b>☑ Pilih Semua</b> (lepas filter kolom itu).</li>
<li>Funnel berwarna <b>merah</b> = kolom itu sedang terfilter. Berlaku di tab Anomali, Hari Mencurigakan, Follow Up (filter tampilan saja — daftar tak berubah), dan Banding Periode (per halaman).</li>
<li>Di tab Anomali &amp; Hari: kolom NAMA RESTO / NAMA BARANG / JENIS / KETERANGAN / STATUS berbagi state yang sama antar kedua tab (dan KPI ikut terfilter); kolom lain = filter tampilan tabel itu saja.</li>
<li>Tombol <b>✕ Hapus Filter</b> (tab Anomali &amp; Hari) = lepas SEMUA filter sekaligus.</li>
</ul>
<h3>Tab lain</h3>
<ul>
<li><b>Banding Periode</b> — bulan berjalan vs <b>daftar file bulan lalu</b>
(1 file = 1 bulan, format REKAP MENTAH — kuantiti tanpa BOM). Nama bulan dibaca
otomatis dari nama file; daftar <b>diingat</b> antar sesi; dimuat di latar belakang.
Nama bulan bisa dikoreksi: <b>klik 2×</b> barisnya atau pilih baris lalu tekan
<b>Enter/F2</b>.
Banding per bulan atau vs <b>Tipikal</b> (median beberapa bulan): ringkasan,
cabang/item bergerak, item baru/hilang — semua murni kuantiti.</li>
<li><b>Tabel &amp; pop-up rincian</b> — tombol <b>⤢ Perbesar Tabel</b>
(ciyutkan daftar file) &amp; <b>⛶ Layar Penuh</b> (tabel tab aktif satu monitor; Esc
kembali). <b>Klik 2× baris</b> di semua tab banding = pop-up rantai rincian
<b>Total → resto → item → per hari</b> ("total naik — resto mana — item apa —
hari berapa").</li>
<li><b>Kolom perubahan di tab Anomali</b> — bila ada pembanding:
kolom <b>BULAN LALU</b>, <b>PERUBAHAN %</b> (+35,5% / BARU) &amp; kategori
<b>PERUBAHAN</b> (filter "Perubahan:") — memisahkan <b>lonjakan baru</b>
(kandidat salah input) dari <b>waste kronis</b> (tinggi tiap bulan).</li>
<li><b>Angka minus otomatis MERAH</b> di semua tabel; kolom
pembanding memakai <b>NAMA BULAN</b> (bukan kata "Pembanding"); tabel banding
menampilkan <b>JENIS</b> (SUSUT/TRIAL/WASTE) per baris cabang/item; tombol
<b>⤢ Perbesar Tabel</b> &amp; <b>⛶ Layar Penuh</b> kini juga ada di tab
<b>Anomali</b>; daftar file banding <b>auto-ciut</b> setelah dimuat (tabel
hasil langsung tinggi penuh).</li>
<li><b>Semua filter lewat funnel di judul kolom</b> — sidebar filter kiri &amp;
slicer chip dihapus: SEMUA kolom punya funnel, tabel memakai lebar &amp;
tinggi penuh.</li>
</ul>
<h3>💡 Bingung istilah?</h3>
<p><b>Hover (arahkan mouse &amp; diamkan)</b> di: judul kolom tabel, label metrik pop-up,
chip sinyal S1–S12, kartu KPI, dan kontrol filter — muncul penjelasan singkat
bahasa sehari-hari (mis. "% to BOM = waste dibanding penjualan").</p>
<p><b>Ekspor</b>: tombol <b>💾 Ekspor Excel</b> di toolbar (aktif setelah
pipeline menghasilkan data — sebelum itu tombol nonaktif) —
laporan lengkap termasuk sheet analisa (Waste per Hari, Money View, Data Quality).</p>
<p>Semua teks dirancang anti-terpotong: teks panjang otomatis berpindah
baris; tabel tanpa cap baris.</p>
"""


# Snapshot import-time (kompatibilitas import lama: test membaca
# ui.app._HELP_HTML; angka ambang dari config saat modul dimuat —
# sama seperti ctx aplikasi yang memuat config sekali di startup).
_HELP_HTML = _build_help_html(load_config())


def _adaptive_min_height(screen_h: int | None) -> int:
    """v2.13.15 (gel-6 D30) — tinggi-minimum jendela ADAPTIF LAYAR.

    Dulu literal 700px: di layar pendek (netbook 1024×600, VM dengan
    taskbar — available ±648) minimum MELEBIHI tinggi layar → jendela
    tak bisa dimuat penuh (titlebar di luar jangkauan, layout terpotong;
    audit D30 "jendela min 700px melebihi layar pendek"). Formula:
    max(560, min(700, screen_h − 80)) — layar biasa tetap 700, layar
    pendek turun sampai lantai 560 (layout masih layak: toolbar + bar
    kontrol + KPI + ≥ 3 baris tabel + status bar); None (screen tak
    diketahui) = 700 (default lama). Dikunci test_v21315 (formula) +
    test_v280 (dipakai MainWindow)."""
    if screen_h is None:
        return 700
    return max(560, min(700, screen_h - 80))


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
        # v2.13.15 (gel-6 D30): minimum TINGGI adaptif layar — helper
        # _adaptive_min_height (dulu literal 700px melebihi layar pendek;
        # lebar minimum 1024 tetap — tabel lebar by design).
        min_h = _adaptive_min_height(screen.height() if screen else None)
        if screen is not None:
            w = min(1500, max(1024, screen.width() - 100))
            h = min(900, max(min_h, screen.height() - 80))
            self.resize(w, h)
            self.move(max(0, (screen.width() - w) // 2),
                      max(0, (screen.height() - h) // 2))
        self.setMinimumSize(1024, min_h)

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
        # v2.17.0 P0-E: ToolButtonTextBesideIcon — ikon vektor + teks
        # (sebelumnya TextOnly + emoji 📊/💾/❓ = sup-emoji warna).
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # Judul app: ikon chart_bar + teks (bukan emoji 📊).
        title_host = QWidget()
        thl = QHBoxLayout(title_host)
        thl.setContentsMargins(8, 0, 8, 0)
        thl.setSpacing(6)
        title_icon = Icon("chart_bar", 18, QColor("#f1f5f9"))
        thl.addWidget(title_icon)
        title = QLabel(APP_TITLE)
        title.setStyleSheet("color:#f1f5f9; font-size:14px; font-weight:700; background:transparent;")
        thl.addWidget(title)
        bar.addWidget(title_host)
        sep = QWidget()
        sep.setFixedWidth(12)
        bar.addWidget(sep)

        # v2.17.0 P0-E: ikon vektor save (sebelumnya emoji 💾).
        act_export = QAction(make_qicon("save", 16, QColor("#f1f5f9")),
                             "Ekspor Excel", self)
        act_export.setToolTip(
            "Simpan laporan Excel (6 sheet inti + sheet analisa)\n"
            "Aktif setelah pipeline menghasilkan data (tab Pipeline).")
        act_export.triggered.connect(self._export_excel)
        # v2.13.14 (gel-5 D24): Ctrl+E = ekspor — padanan keyboard tombol
        # toolbar (tetap aktif walau toolbar disembunyikan; QKeySequence
        # literal aman — pola act_help F1 gel-1).
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        # v2.13.15 (gel-6 D16): tombol NONAKTIF sampai ada data — dulu
        # tampak siap-siap SEJAK first-run padahal ctx.df masih None:
        # klik = dialog "Belum ada data" (janji kosong; audit D16 "tombol
        # Export tampak siap padahal tanpa data"). Di-enable oleh
        # _on_data_ready saat dataset non-kosong (dan dikembalikan ke
        # keadaan-dengan-data pasca ekspor selesai/gagal).
        act_export.setEnabled(False)
        bar.addAction(act_export)
        self._act_export = act_export

        # v2.17.0 P0-E: ikon vektor help (sebelumnya emoji ❓).
        act_help = QAction(make_qicon("help", 16, QColor("#f1f5f9")),
                           "Bantuan", self)
        act_help.triggered.connect(self._show_help)
        # v2.13.10 (gel-1 D1): shortcut F1 — didokumentasikan di README,
        # banner .bat, dan Bantuan sendiri, tapi TIDAK pernah terpasang
        # (grep setShortcut|QKeySequence seluruh repo = 0 match; audit
        # D1: QTest keyClick F1 tidak membuka apa pun). Enum PySide6 =
        # QKeySequence.StandardKey.HelpContents — nested class, DENGAN
        # 's' (bukan konstanta modul QtGui.HelpContent).
        act_help.setShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents))
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
        # v2.17.0 (rombak P0 — urutan alur analisa): Pipeline (muat data)
        # di index 0 = entry point, Anomali (analisa utama) index 1,
        # drill-down Hari/Scorecard/Banding index 2-4, Follow Up (tindak
        # lanjut) terakhir index 5. Sebelumnya Pipeline di index 5 — user
        # harus tab ke akhir dulu baru bisa muat data (alur terbalik).
        self._views: list[tuple[str, QWidget]] = [
            ("Pipeline", PipelineView(self.ctx)),
            ("Anomali", AnomaliView(self.ctx)),
            ("Hari Mencurigakan", HariView(self.ctx)),
            # v2.13.1: tab Scorecard Cabang (urutan kunjungan audit +
            # kartu pendukung: top kerugian, pola hari kalender, hari
            # sistemik) — setelah Hari Mencurigakan, sebelum Banding.
            ("Scorecard Cabang", ScorecardView(self.ctx)),
            ("Banding Periode", PeriodeView(self.ctx)),
            ("Follow Up", FollowUpView(self.ctx)),
        ]
        for name, view in self._views:
            self._tabs.addTab(view, name)
        # v2.12.0: ref view Follow Up (badge jumlah baris di judul tab).
        # v2.17.0: Follow Up sekarang di index 5 (sebelumnya 1).
        self._fu_view = self._views[5][1]
        self._update_followup_badge()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        # v2.13.11 (gel-2 D4): first-run — currentChanged terpasang SETELAH
        # addTab, jadi tab 0 TIDAK PERNAH memicu on_shown otomatis. v2.17.0:
        # tab 0 kini Pipeline (entry point muat data) — picu SEKALI pasca-
        # wiring supaya PipelineView.on_shown() jalan sejak awal (tombol
        # Mulai/Olah siap, bukan layar kosong). Kontrak lazy-render tetap:
        # pindah tab → on_shown per-view.
        self._on_tab_changed(self._tabs.currentIndex())
        # Anti-terpotong: bila tab bar sempit, teks di-elide dengan '…'
        # (konvensi jelas) + tombol panah scroll — TIDAK pernah dipotong
        # mentah mid-character. 4 tab (v2.9.0) masih muat di jendela
        # normal; jendela sempit memakai tombol scroll.
        self._tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self._tabs.setUsesScrollButtons(True)
        self.setCentralWidget(self._tabs)
        # v2.13.14 (gel-5 D24) — SHORTCUT GLOBAL pindah tab Ctrl+1..Ctrl+6:
        # navigasi antar tab dulunya HANYA via mouse (audit D24: nol
        # shortcut global; pengguna keyboard harus klik tab bar).
        # QAction tanpa tombol fisik — addAction(window) memasang shortcut
        # aktif selama jendela fokus (konteks default WindowShortcut).
        # QKeySequence("Ctrl+N") literal: StandardKey tak punya padanan
        # angka (satu-satunya angka: StandardKey.Undo/Redo dsb. — aman).
        self._tab_actions: list[QAction] = []
        for i, (name, _view) in enumerate(self._views):
            act = QAction(f"Pindah ke tab {name}", self)
            act.setToolTip(f"Pindah ke tab {name} (Ctrl+{i + 1})")
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            # v2.13.14 (gel-5 D24-fix): koneksi ke BOUND METHOD self.
            # _on_tab_shortcut — BUKAN lambda yang menangkap self.
            # PySide6 memegang callable koneksi secara KUAT: lambda
            # dgn closure `self` = rantai kuat QAction(parent=window) →
            # sinyal → lambda → window yang TAK BISA dipecahkan gc
            # (siklus lintas C++/Python; window bocor selamanya —
            # terbukti empirik: window bertahan gc.collect(); teardown
            # conftest lalu memanggil close() → closeEvent melihat
            # _running → QMessageBox.question ASLI → full-suite hang
            # offscreen). Bound method = receiver LEMAH (PySide melacak
            # lemah objek penerima; koneksi mati sendiri saat window
            # hancur); index disimpan di property action + dibaca via
            # self.sender() — idiomatik Qt (pola QSignalMapper modern).
            act.setProperty("tab_index", i)
            act.triggered.connect(self._on_tab_shortcut)
            self.addAction(act)
            self._tab_actions.append(act)

    def _on_tab_shortcut(self, _checked: bool = False) -> None:
        """Slot Ctrl+1..Ctrl+6 — pindah tab sesuai action pengirim
        (index lewat property 'tab_index'; receiver lemah — D24-fix)."""
        act = self.sender()
        idx = act.property("tab_index") if act is not None else None
        if isinstance(idx, int) and 0 <= idx < self._tabs.count():
            self._tabs.setCurrentIndex(idx)

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
        # Permanent status: baris + anomali + waktu run.
        # v2.13.11 (gel-2 D3): DUA definisi "anomali" kini DILABELI — dulu
        # status bar "797 anomali" (= semua non-Normal) vs kartu Ringkasan
        # Run "399" (= prioritas+potensi saja) beda 398 tanpa pembeda.
        # Angka prioritas+potensi dihitung dari df dgn semantik SAMA dgn
        # pipeline.py build_summary (anomali_count = prioritas+potensi;
        # engine TIDAK diubah).
        total = len(df)
        n_non = n_pp = 0
        if "ANOMALY STATUS" in df.columns:
            status = df["ANOMALY STATUS"]
            n_non = int((status != "Normal").sum())
            n_pp = int(status.isin(
                ["Prioritas Tinggi", "Potensi Anomali"]).sum())
        run_t = self.ctx.last_run_time
        tstr = run_t.strftime("%H:%M:%S") if run_t else "—"
        self._lbl_perm.setText(
            f"{fmt_id(total)} baris • {fmt_id(n_non)} berstatus non-Normal"
            f" • {fmt_id(n_pp)} prioritas+potensi • run {tstr}")
        # v2.13.15 (gel-6 D16): enable HANYA bila dataset non-kosong —
        # dataset kosong (df.empty) tetap menonaktifkan (tak ada yang
        # bisa diekspor; dulu setEnabled(True) tak bersyarat).
        self._act_export.setEnabled(not df.empty)
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
                # v2.13.14 (gel-5 C16): traceback UTUH ke log — dulu hanya
                # pesan singkat status bar: baris/panggilan mana yang meledak
                # TIDAK PERNAH terekam (audit C16: "exception render tab
                # ditelan tanpa traceback") — mustahil didiagnosis dari
                # log. logging.exception → file log (pola _qt_excepthook);
                # ctx.log → panel log Pipeline + sheet Log Run ekspor.
                tb = traceback.format_exc()
                logging.getLogger("waste_anomaly.ui").exception(
                    "Render tab '%s' gagal", self._tabs.tabText(_index))
                self.ctx.log(f"⚠ Render tab gagal: {e}\n{tb}")
                self.ctx.set_status(f"⚠ Render tab gagal: {e}", "error")

    # ------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------
    def _pipeline_busy(self) -> bool:
        """v2.13.11 (gel-2 D2): apakah pipeline sedang berjalan? Iterasi
        _views nama 'Pipeline' cek _running. HistoryWorker (banding)
        sengaja TIDAK dicek — worker banding tidak mengganti ctx.df,
        export saat banding berjalan tetap sah."""
        for name, view in self._views:
            if name == "Pipeline" and getattr(view, "_running", False):
                return True
        return False

    def _export_excel(self) -> None:
        if self._exporting:
            return
        df = self.ctx.df
        if df is None or df.empty:
            QMessageBox.information(self, "Ekspor",
                                    "Belum ada data. Jalankan pipeline dulu.")
            return
        # v2.13.11 (gel-2 D2): export saat pipeline SEDANG berjalan → yang
        # diekspor = hasil run SEBELUMNYA — konfirmasi jujur sebelum dialog
        # file (default No, pola closeEvent; Enter salah = aman batal).
        # Dulu: tombol Export tampak siap & klik langsung menyimpan data
        # lama tanpa keterangan run mana (audit D2).
        if self._pipeline_busy():
            ans = QMessageBox.question(
                self, "Pipeline sedang berjalan",
                "Pipeline sedang berjalan — data yang diekspor adalah "
                "hasil run SEBELUMNYA. Lanjutkan?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                self.ctx.set_status(
                    "Export ditunda — pipeline masih berjalan", "running")
                return
        from PySide6.QtWidgets import QFileDialog
        initialdir = Path.home() / "Documents"
        if not initialdir.exists():
            initialdir = Path.home()
        suggested = f"Waste_Anomaly_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Laporan Excel", str(initialdir / suggested),
            "Excel files (*.xlsx);;All files (*.*)")
        if not path:
            return
        self._exporting = True
        self._act_export.setEnabled(False)
        self.ctx.set_status("Menyimpan laporan Excel…", "running")
        self.ctx.log(f"=== Ekspor Excel → {path} ===")
        self._export_worker = ExportWorker(
            df, path, dict(self.ctx.config), self.ctx.key_akhir,
            list(self.ctx.log_lines[-LOG_RUN_LINES:]), self)
        self._export_worker.set_log(self.ctx.log)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        # V26-L7: worker QThread selesai → deleteLater (aman post-finish;
        # guard re-entry pakai flag _exporting, bukan referensi worker).
        self._export_worker.finished.connect(self._export_worker.deleteLater)
        self._export_worker.start()

    def _on_export_done(self, result: dict) -> None:
        self._exporting = False
        # v2.13.15 (gel-6 D16): pulih ke keadaan-dengan-data (bukan True
        # buta — dataset bisa saja berganti selama ekspor jalan).
        self._act_export.setEnabled(
            self.ctx.df is not None and not self.ctx.df.empty)
        if result.get("success"):
            out = result.get("output_path", "")
            n_extra = result.get("extra_sheets_count", 0)
            self.ctx.set_status(f"✓ Laporan Excel tersimpan: {out}", "done")
            self.ctx.log(f"=== Ekspor selesai: {out} ===")
            QMessageBox.information(
                self, "Ekspor Selesai",
                f"Laporan Excel ({6 + n_extra} sheet) tersimpan:\n{out}")
        else:
            self._on_export_failed(result.get("error", "Unknown error"))

    def _on_export_failed(self, err: str) -> None:
        self._exporting = False
        # v2.13.15 (gel-6 D16): pulih ke keadaan-dengan-data (pola
        # _on_export_done).
        self._act_export.setEnabled(
            self.ctx.df is not None and not self.ctx.df.empty)
        self.ctx.set_status(f"⚠ Ekspor gagal: {err}", "error")
        self.ctx.log(f"!!! Ekspor gagal: {err}")
        QMessageBox.critical(self, "Ekspor Gagal", err)

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
            busy.append(("Ekspor Excel", self._export_worker))
        if busy:
            # v2.13.13 (gel-4 D28): tombol default = NO (pola D2 gel-2 /
            # konvensi repo "Enter salah = aman batal") — dulu default
            # Yes: menekan Enter saat dialog muncul = keluar paksa
            # padahal worker masih berjalan (audit D28).
            ans = QMessageBox.question(
                self, "Proses masih berjalan",
                "Pipeline/export/perbandingan masih berjalan. Tetap keluar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
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
