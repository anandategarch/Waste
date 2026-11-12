"""view_pipeline.py — view 'Pipeline': jalankan analisa + log + ringkasan
+ editor threshold config (gabungan tab Run + Ringkasan + Config lama).

Worker = QThread (ui tidak freeze); tombol dua-mode Mulai↔Batalkan (F9);
log selalu terlihat (popup log lama dihapus — tidak ada tombol ganda).

v2.15.0: tombol 🧮 "Olah & Jalankan REKAP MENTAH…" SEKALI JALAN — pilih
file mentah → pipeline LANGSUNG dijalankan padanya (header tergeser
diperbaiki + nilai identity dinormalisasi + TOTAL BOM diinjeksi dari baris
JENIS=BOM oleh rekap_import, dipanggil pipeline di fase LOAD); TANPA file
olahan antara & tanpa klik Mulai Pipeline kedua kali — hasil identik jalur
2-langkah v2.14.0 (golden file asli: 25.722 baris · 25.028 ber-BOM · 62
prioritas) tapi jauh lebih cepat (satu baca file, ±6 dtk vs ±32 dtk).

v2.14.0: tombol 🧮 "Olah REKAP MENTAH…" (2-langkah: worker RekapImportWorker
mengolah → ekspor DATA_WASTE <bulan>.xlsx → kolom workbook terisi → user
klik Mulai Pipeline) — jalur ekspor itu kini hanya API
(convert_rekap_mentah / RekapImportWorker tetap tersedia & teruji,
UI tidak lagi memakainya — permintaan user: "aku mau sekali proses aja
dan gak perlu export hasil olahan proses rekap mentah nya").

v2.13.12 (gel-3): D15 — jumlah stage dinamis dari pipeline.PIPELINE_N_STAGES
(dulu hardcode "14 stage"); D17 — "Browse…" → "Telusuri…", "Input Error" →
"Input Belum Valid"; D18 — label stage EN engine diterjemahkan di BATAS UI
(_log_id di _on_progress; engine tetap EN); D13 — angka Ringkasan Run fmt_id
+ timestamp "12 Jan 2026 18:07"; D14 — dialog Pratinjau Ambang fmt_id.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .shared import APP_DIR, LOG_RUN_LINES, fmt_id, friendly_file_error
from .state import AppContext
from .icons import make_qicon
from .widgets import Card, WLabel, busy_feedback
from .workers import PipelineWorker, FolderScanWorker
from waste_anomaly.pipeline import PIPELINE_N_STAGES

_SUMMARY_LABELS = {
    "total_rows": "Total baris",
    # v2.13.11 (gel-2 D3): dua definisi anomali dilabeli — angka ini =
    # prioritas + potensi (semantik build_summary pipeline.py), BUKAN
    # semua baris non-Normal yang ditampilkan status bar. Dulu kartu
    # "399" vs status bar "797" tanpa pembeda (audit D3).
    "anomali_count": "Total anomali (prioritas+potensi)",
    "prioritas_count": "Prioritas tinggi",
    "potensi_count": "Potensi anomali",
    "review_count": "Perlu review",
    "normal_count": "Normal",
    "cabang_count": "Jumlah cabang",
    "item_count": "Jumlah item",
    "key_akhir": "Key akhir (hari)",
    "timestamp": "Waktu run",
}


# ============================================================
# v2.13.12 (gel-3 D18) — TERJEMAHAN LOG STAGE di BATAS UI
# ============================================================
# Engine (pipeline.py/loader.py) tetap menulis log EN (nama stage &
# istilah teknis internal) — penerjemahan dilakukan SAAT baris sampai
# ke UI (_on_progress): label status + panel log + ctx.log_lines yang
# ikut diekspor ke sheet "Log Run" semuanya Bahasa Indonesia. Baris
# stage 11/15/15b memang sudah Indonesia sejak awal — tak perlu di-map.
# Prefix-match: kunci = awalan baris log PERSIS engine, sisa baris
# (angka dinamis) ditempel setelah terjemahan. Baris EN baru yang tak
# di-map lolos apa adanya (drift kecil, dikunci test_v21312).
_LOG_ID_MAP: dict[str, str] = {
    "=== Waste Anomaly Pipeline START ===": "=== Pipeline waste dimulai ===",
    "Loading DATA_WASTE": "Memuat DATA_WASTE",
    "Loading BOM": "Memuat BOM",
    "Loading DATABASE_SATUAN": "Memuat DATABASE_SATUAN",
    "[loader] DATA_WASTE loaded: ": "[loader] DATA_WASTE termuat: ",
    "[loader] BOM loaded: ": "[loader] BOM termuat: ",
    "[loader] DATABASE_SATUAN loaded: ": "[loader] DATABASE_SATUAN termuat: ",
    "Stage 1 — Source & cleanup": "Tahap 1 — sumber & pembersihan",
    "Stage 2 — Per-row daily statistics": "Tahap 2 — statistik harian per baris",
    "Stage 3 — Reason summary": "Tahap 3 — ringkasan alasan",
    "Stage 4 — Group totals": "Tahap 4 — total per grup",
    "Stage 5 — BOM join": "Tahap 5 — penggabungan BOM",
    "Stage 6 — Peer summary": "Tahap 6 — ringkasan peer (cabang lain)",
    "Stage 7 — Top 3 summary": "Tahap 7 — ringkasan Top 3",
    "Stage 8 — Merge": "Tahap 8 — penggabungan",
    "Stage 9 — DATABASE_SATUAN join": "Tahap 9 — penggabungan DATABASE_SATUAN",
    "Stage 10 — Helper / STATUS / % to BOM":
        "Tahap 10 — helper / STATUS / % to BOM",
    "Stage 12.5 — Waste Fingerprint + Sistematik Flag":
        "Tahap 12.5 — fingerprint waste + penanda sistemik",
    "Stage 12.6 — Quadrant Classification": "Tahap 12.6 — klasifikasi kuadran",
    "Stage 13 — Cleanup temporary": "Tahap 13 — pembersihan kolom sementara",
    "Stage 14 — Final column order": "Tahap 14 — urutan kolom final",
    "Build summary statistics": "Menyusun statistik ringkasan",
    "=== Pipeline DONE ===": "=== Pipeline selesai ===",
}


def _log_id(msg: str) -> str:
    """v2.13.12 (gel-3 D18): terjemahkan AWALAN baris log engine (EN)
    ke Indonesia — prefix-match atas _LOG_ID_MAP, sisanya (angka,
    path, nama sheet) diteruskan. Baris tak dikenal → apa adanya
    (jujur, bukan tebakan)."""
    for prefix, indo in _LOG_ID_MAP.items():
        if msg.startswith(prefix):
            return indo + msg[len(prefix):]
    return msg


# ============================================================
# v2.13.12 (gel-3 D13) — timestamp ringkasan gaya Indonesia
# ============================================================
_BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _fmt_ts_id(value) -> str:
    """v2.13.12 (gel-3 D13): timestamp ISO engine ('2026-01-12T18:07:33')
    → '12 Jan 2026 18:07' (Bulan Indonesia). Nilai eksotis (teks/tanggal
    aneh) → str apa adanya — jujur, bukan error."""
    s = str(value or "").strip()
    if not s:
        return "—"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return s
    return (f"{dt.day} {_BULAN_ID[dt.month - 1]} {dt.year} "
            f"{dt.hour:02d}:{dt.minute:02d}")


class PipelineView(QWidget):
    """Kontrol pipeline: input, parameter, run/cancel, progress, log, ringkasan."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: PipelineWorker | None = None
        self._running = False
        # v2.17.2 — folder flow (scan+combine BJMHAS-style files → temp).
        self._folder_worker: FolderScanWorker | None = None
        self._folder_temp: str | None = None  # temp path utk cleanup
        # v2.15.0 — tombol 🧮 kini SEKALI JALAN (dialog → _start; pipeline
        # sendiri memanggil rekap_import di fase LOAD): tidak ada lagi
        # worker olah terpisah / file antara (jalur RekapImportWorker
        # 2-langkah v2.14.0 kini hanya API di ui/workers.py).

        # v2.13.6 (audit R2): tinggi-min 4 kartu = 716px (terukur) >
        # ruang halaman tab ±582px di 1366×768 → tombol Simpan/Reset/
        # Pratinjau di kartu Threshold terpotong. Bungkus QScrollArea:
        # kartu 1-3 tetap muat & terlihat, kartu Threshold digulir.
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        self._page = page
        scroll.setWidget(page)
        lay.addWidget(scroll)
        # NB: nama 'page_lay' — jangan 'pl' (var 'pl' dipakai QHBoxLayout
        # prow di card 2 kode lama; tabrakan nama = layout siklik → hang).
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(8)

        # ===== Card 1: Input workbook =====
        c1 = Card(self)
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(12, 10, 12, 10)
        l1.setSpacing(6)
        t = WLabel("Input Workbook", c1)
        t.setObjectName("cardTitle")
        l1.addWidget(t)
        row = QWidget(c1)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self._ent_workbook = QLineEdit(row)
        self._ent_workbook.setPlaceholderText("Pilih file Excel rekap (mis. DATA_WASTE.xlsx)")
        self._ent_workbook.returnPressed.connect(self._on_run_button)
        rl.addWidget(self._ent_workbook, 1)
        b_browse = QPushButton("Telusuri…", row)
        b_browse.clicked.connect(self._browse)
        rl.addWidget(b_browse)
        # v2.15.0 — SEKALI JALAN: pilih file REKAP MENTAH mentah →
        # pipeline LANGSUNG dijalankan padanya (rekap_import dipanggil
        # pipeline di fase LOAD: perbaiki header tergeser + normalisasi
        # nilai identity + injeksi TOTAL BOM dari baris JENIS==BOM).
        # Tanpa file olahan antara — menggantikan 2-langkah v2.14.0
        # (olah → ekspor → klik Mulai Pipeline) atas permintaan user.
        # v2.19.2 — label diperjelas "Pilih REKAP MENTAH" (permintaan user:
        # tombol "pilih rekap mentah" terasa hilang padahal fungsinya sama —
        # label lama "Olah & Jalankan REKAP MENTAH" tak dikenali). Tombol ini
        # = satu-satunya jalur memuat file REKAP MENTAH mentah + menjalankan
        # pipeline sekaligus; tooltip menjelaskan olahan+pipeline sekali jalan.
        b_import = QPushButton("🧮 Pilih REKAP MENTAH…", row)
        b_import.setToolTip(
            "Pilih file REKAP MENTAH mentah (mis. \"REKAP MENTAH_01-31 "
            "AGUSTUS 2026_TEGAR.xlsx\" — boleh masih berisi SEMUA jenis "
            "BOM/SO/stok & header tergeser) — olahan + pipeline berjalan "
            "SEKALI JALAN tanpa file antara: TOTAL BOM diambil dari baris "
            "BOM, saringan & statistik dihitung pipeline. Menggantikan "
            "olah manual Excel + proses 2-klik. Inilah tombol utama utk "
            "memuat rekap mentah & mengaktifkan edit kuantiti di tab Anomali.")
        b_import.clicked.connect(self._on_import_rekap)
        rl.addWidget(b_import)
        self._btn_import = b_import
        # v2.17.2 — Proses dari Folder (file BJMHAS-style: tanpa kolom
        # NAMA RESTO → disintesis dari nama file; folder DEVIASI WEEKLY).
        b_folder = QPushButton(make_qicon("folder", 16), "Proses dari Folder…", row)
        b_folder.setToolTip(
            "Pilih FOLDER berisi file .xlsx (format BJMHAS — sheet REKAP "
            "MENTAH tanpa kolom NAMA RESTO; resto diambil dari NAMA FILE). "
            "Semua file .xlsx di folder dipindai, sheet REKAP MENTAH "
            "diekstrak, NAMA RESTO disintesis dari nama file (bila kolom "
            "absen), lalu DIGABUNG jadi satu dataset. Hasil gabungan = "
            "file sementara — edit nilai via pop-up menyimpan ke file "
            "sementara INI, bukan file asli di folder (untuk edit file "
            "asli, gunakan tombol 🧮 Pilih REKAP MENTAH dengan format "
            "REKAP MENTAH_..._TEGAR).")
        b_folder.clicked.connect(self._on_import_folder)
        rl.addWidget(b_folder)
        self._btn_folder = b_folder
        b_sample = QPushButton("Pakai Sample", row)
        b_sample.setToolTip("Isi kolom dengan DATA_WASTE.xlsx dari folder repo")
        b_sample.clicked.connect(self._use_sample)
        rl.addWidget(b_sample)
        l1.addWidget(row)
        page_lay.addWidget(c1)

        # ===== Card 2: Parameter + Kontrol =====
        c2 = Card(self)
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(12, 10, 12, 10)
        l2.setSpacing(6)
        t2 = WLabel("Parameter & Kontrol", c2)
        t2.setObjectName("cardTitle")
        l2.addWidget(t2)
        prow = QWidget(c2)
        pl = QHBoxLayout(prow)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)
        pl.addWidget(WLabel("Key Akhir (1–31):", prow))
        try:
            ka_default = int(self._ctx.config.get("default_key_akhir", 31))
        except (TypeError, ValueError):
            ka_default = 31
        if not (1 <= ka_default <= 31):
            ka_default = 31
        self._spin_ka = QSpinBox(prow)
        self._spin_ka.setRange(1, 31)
        self._spin_ka.setValue(ka_default)
        pl.addWidget(self._spin_ka)
        hint = WLabel(
            f"(hanya hari 1..N dianalisa — {PIPELINE_N_STAGES} stage "
            "pipeline dijalankan in-memory)", prow)
        hint.setObjectName("hint")
        pl.addWidget(hint, 1)
        l2.addWidget(prow)

        self._btn_run = QPushButton("▶ Mulai Pipeline", c2)
        self._btn_run.setObjectName("accent")
        self._btn_run.clicked.connect(self._on_run_button)
        l2.addWidget(self._btn_run)
        self._progress = QProgressBar(c2)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        l2.addWidget(self._progress)
        self._lbl_status = WLabel("Siap. Pilih workbook lalu klik Mulai Pipeline.", c2)
        self._lbl_status.setObjectName("hint")
        l2.addWidget(self._lbl_status)
        page_lay.addWidget(c2)

        # ===== Card 3: Ringkasan + Log (splitter vertikal) =====
        c3 = Card(self)
        l3 = QVBoxLayout(c3)
        l3.setContentsMargins(12, 10, 12, 10)
        l3.setSpacing(6)
        t3 = WLabel("Ringkasan Run & Log Proses", c3)
        t3.setObjectName("cardTitle")
        l3.addWidget(t3)
        self._summary = QTextBrowser(c3)
        self._summary.setOpenExternalLinks(False)
        self._summary.setMaximumHeight(150)
        self._summary.setPlaceholderText("Ringkasan run akan tampil di sini setelah pipeline selesai.")
        l3.addWidget(self._summary)
        self._log = QPlainTextEdit(c3)
        self._log.setObjectName("log")
        self._log.setReadOnly(True)
        # v2.13.15 (gel-6 D11): ambang blok panel log = LOG_RUN_LINES —
        # dulu angka literal 2000 lokal vs 500 memori ctx vs 200 ekspor
        # (audit D11: tiga ambang beda); kini SATU konstanta bersama.
        self._log.setMaximumBlockCount(LOG_RUN_LINES)
        self._log.setPlaceholderText(
            f"Log proses ({PIPELINE_N_STAGES} stage) tampil di sini saat "
            "pipeline berjalan…")
        l3.addWidget(self._log, 1)
        # v2.17.0 rombak P0: c3 (Ringkasan/Log) addWidget DITUNDA —
        # ditambahkan SETELAH c4 (Threshold) di bawah. Alur baru: Input →
        # Parameter → Threshold Config → Run & Log Results (config sebelum
        # hasil, bukan sebaliknya).

        # ===== Card 4: Threshold & Konfigurasi =====
        c4 = Card(self)
        l4 = QVBoxLayout(c4)
        l4.setContentsMargins(12, 10, 12, 10)
        l4.setSpacing(6)
        t4 = WLabel("Threshold & Konfigurasi (config.json)", c4)
        t4.setObjectName("cardTitle")
        l4.addWidget(t4)
        h4 = WLabel("Edit nilai threshold lalu Simpan — berlaku mulai run BERIKUTNYA.", c4)
        h4.setObjectName("hint")
        l4.addWidget(h4)
        scroll = QScrollArea(c4)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form_host = QWidget(inner)
        fl = QFormLayout(form_host)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.setSpacing(4)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._config_vars: dict[str, QLineEdit] = {}
        for key, val in sorted(self._ctx.config.get("thresholds", {}).items()):
            ent = QLineEdit(str(val))
            ent.setMaximumWidth(140)
            lbl = QLabel(f"{key}:", form_host)
            lbl.setToolTip(key)
            fl.addRow(lbl, ent)
            self._config_vars[key] = ent
        btns = QWidget(inner)
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(4, 8, 4, 4)
        bl.setSpacing(8)
        b_save = QPushButton("Simpan config.json", btns)
        b_save.setObjectName("accent")
        b_save.clicked.connect(self._save_config)
        bl.addWidget(b_save)
        b_reset = QPushButton("Reset Default", btns)
        b_reset.clicked.connect(self._reset_config)
        bl.addWidget(b_reset)
        # v2.13.3 (⑮): pratinjau distribusi status dengan nilai form
        # SEKARANG — tanpa simpan (jawab "kalau aku ubah X, berapa
        # perubahannya?" sebelum commit).
        b_preview = QPushButton("👀 Pratinjau Ambang", btns)
        b_preview.setToolTip(
            "Hitung ulang 12 sinyal + status MEMAKAI NILAI FORM saat ini\n"
            "(belum disimpan) pada dataset terakhir — tampilkan jumlah\n"
            "baris per status SEBELUM → SESUDAH. Berjalan sekali per klik\n"
            "(sibuk ± 1 dtk di data besar) — bukan live per ketikan.")
        b_preview.clicked.connect(self._preview_thresholds)
        bl.addWidget(b_preview)
        # v2.13.13 (gel-4 D29): tombol disimpan sebagai ATRIBUT —
        # _preview_thresholds menonaktifkan 3 tombol (Mulai/Simpan/
        # Pratinjau) selama compute pratinjau berjalan (dulu lokal var:
        # klik ganda saat compute 0,3-0,5 dtk = nested compute + UI
        # freeze — audit D29).
        self._btn_save = b_save
        self._btn_preview = b_preview
        self._btn_reset = b_reset
        bl.addStretch(1)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.addWidget(form_host)
        inner_lay.addWidget(btns)
        inner_lay.addStretch(1)
        scroll.setWidget(inner)
        l4.addWidget(scroll, 1)
        page_lay.addWidget(c4, 1)
        # v2.17.0 rombak P0: c3 (Ringkasan/Log) ditambahkan SETELAH c4
        # (Threshold) — alur config-sebelum-hasil. Sebelumnya c4 di akhir
        # (setelah hasil) → user harus scroll ke bawah utk atur threshold
        # padahal itu wajib SEBELUM menjalankan pipeline.
        page_lay.addWidget(c3, 1)

        # Log line dari ctx → panel log (worker progress juga lewat sini)
        ctx.log_line.connect(self._append_log)
        # v2.17.0 rombak P0: setelah reorder — index 2 = c4 Threshold
        # (stretch 2, form konfig), index 3 = c3 Ringkasan/Log (stretch 3,
        # ruang log tumbuh lebih besar). Sebelumnya index 2=c3, 3=c4.
        page_lay.setStretch(2, 2)
        page_lay.setStretch(3, 3)

    # ------------------------------------------------------------
    # INPUT
    # ------------------------------------------------------------
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih Workbook Excel", str(APP_DIR),
            "Excel files (*.xlsx *.xlsm *.xls);;All files (*.*)")
        if path:
            self._ent_workbook.setText(path)

    def _use_sample(self) -> None:
        sample = APP_DIR / "DATA_WASTE.xlsx"
        if sample.exists():
            self._ent_workbook.setText(str(sample))
        else:
            QMessageBox.information(
                self, "Sample", "DATA_WASTE.xlsx tidak ditemukan di folder aplikasi.")

    def current_workbook(self) -> str:
        return self._ent_workbook.text().strip()

    # ------------------------------------------------------------
    # v2.15.0 — OLAH & JALANKAN REKAP MENTAH SEKALI JALAN
    # (menggantikan olahan manual Excel + 2-langkah v2.14.0)
    # ------------------------------------------------------------
    def _on_import_rekap(self) -> None:
        """Pilih file REKAP MENTAH mentah → MULAI PIPELINE SEKARANG.

        v2.14.0 (2-langkah): worker mengolah → ekspor "DATA_WASTE <bulan>
        .xlsx" → kolom workbook terisi → user klik Mulai Pipeline.
        v2.15.0 (SEKALI JALAN — permintaan user "aku mau sekali proses aja
        dan gak perlu export hasil olahan proses rekap mentah nya"):
        kolom workbook diisi path MENTAH lalu _start() dipanggil LANGSUNG
        — pipeline memanggil rekap_import di fase LOAD (ensure_rekap_header
        + normalize_rekap_values + inject_bom_from_raw_rows) sehingga file
        mentah dianalisa lengkap (BOM hidup) TANPA file antara. Seluruh
        mesin run lama dipakai apa adanya: worker QThread + progres per
        stage + tombol ⏹ Batalkan + ringkasan + render tab lain. Batal/
        error/gagal memakai jalur _on_failed yang sama (D7
        friendly_file_error + traceback utuh ke log panel).
        """
        if self._running:
            QMessageBox.information(
                self, "Pipeline Sedang Berjalan",
                "Tunggu pipeline selesai (atau batalkan) sebelum memproses "
                "file REKAP MENTAH baru.")
            return
        # Folder awal dialog: folder workbook aktif (kalau ada) — file
        # rekap mentah user biasanya satu folder dengan data bulanan.
        start_dir = str(APP_DIR)
        cur = self.current_workbook()
        if cur:
            cur_dir = str(Path(cur).parent)
            if Path(cur_dir).is_dir():
                start_dir = cur_dir
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File REKAP MENTAH (mentah)", start_dir,
            "Excel files (*.xlsx *.xlsm);;All files (*.*)")
        if not path:
            return
        # Kolom workbook = file MENTAH (tidak ada file antara yang
        # diekspor); _start membaca nilai ini lalu menjalankan worker.
        self._ent_workbook.setText(path)
        self._ctx.log(
            f"=== Olah & jalankan REKAP MENTAH sekali proses: "
            f"{Path(path).name} ===")
        self._start()

    # ------------------------------------------------------------
    # v2.17.2 — FOLDER FLOW (scan BJMHAS-style files → temp → pipeline)
    # ------------------------------------------------------------
    def _on_import_folder(self) -> None:
        """Pilih FOLDER → scan .xlsx → gabung → temp → MULAI PIPELINE.

        Untuk file format BJMHAS (folder DEVIASI WEEKLY): tiap file .xlsx
        punya sheet REKAP MENTAH TANPA kolom NAMA RESTO (resto = nama file).
        FolderScanWorker memindai, sintesis NAMA RESTO dari filename,
        gabung semua jadi temp .xlsx, lalu _start() menjalankan pipeline
        pada temp (PipelineWorker). Edit nilai via pop-up menyimpan ke
        temp file INI (bukan file asli — file asli di folder utuh).
        """
        if self._running:
            QMessageBox.information(
                self, "Pipeline Sedang Berjalan",
                "Tunggu pipeline selesai (atau batalkan) sebelum memproses "
                "folder baru.")
            return
        if self._folder_worker is not None:
            QMessageBox.information(
                self, "Scan Folder Sedang Berjalan",
                "Tunggu scan folder selesai sebelum memilih folder lain.")
            return
        # v2.17.3 — default folder dari config (permintaan user: "secara
        # default pkai alamat C:\KERJA\1. RESTO\9.NEW QUERY\1. DEVIASI
        # WEEKLY"; bisa diganti — edit config.json key
        # "default_deviasi_folder"). Fallback: folder workbook aktif / APP_DIR.
        # v2.18.0 audit (UI-7): PRESEDEN DIBALIK — dulu folder workbook aktif
        # SELALU menang setelah run pertama (kolom workbook terisi temp path
        # %TEMP% folder-flow → dialog terbuka di %TEMP%, bukan folder config
        # yang diminta user). Config default valid menang; workbook dir hanya
        # fallback bila config tak di-set/tak ada.
        start_dir = str(APP_DIR)
        default_folder = self._ctx.config.get("default_deviasi_folder", "")
        if default_folder and Path(default_folder).is_dir():
            start_dir = default_folder
        else:
            cur = self.current_workbook()
            if cur:
                cur_dir = str(Path(cur).parent)
                if Path(cur_dir).is_dir():
                    start_dir = cur_dir
        folder = QFileDialog.getExistingDirectory(
            self, "Pilih Folder berisi file .xlsx (REKAP MENTAH)",
            start_dir)
        if not folder:
            return
        # Bersihkan temp folder-flow sebelumnya (bila ada).
        self._cleanup_folder_temp()
        # Mulai worker scan folder (background — baca N file .xlsx bisa
        # beberapa detik; UI tetap responsif).
        self._folder_worker = FolderScanWorker(folder, self._ctx.config, self)
        self._folder_worker.done.connect(self._on_folder_done)
        self._folder_worker.failed.connect(self._on_folder_failed)
        self._folder_worker.finished.connect(
            self._folder_worker.deleteLater)
        # Disable tombol + kolom workbook selama scan (v2.17.4 — FIX bug
        # "Workbook belum dipilih" saat user klik Mulai Pipeline / tekan
        # Enter di kolom workbook SEBELUM scan selesai. Scan butuh beberapa
        # detik (20 file ~9-13s calamine); workbook belum terisi temp path
        # → _start() melihat workbook kosong → error menyesatkan. Pipeline
        # jalan OTOMATIS setelah scan selesai (_on_folder_done → _start).
        self._btn_import.setEnabled(False)
        self._btn_folder.setEnabled(False)
        self._btn_run.setEnabled(False)
        self._ent_workbook.setEnabled(False)
        self._btn_run.setText("⏳ Memindai folder…")
        self._ctx.set_status(
            f"⏳ Memindai folder {Path(folder).name}… (tunggu — pipeline "
            f"jalan otomatis setelah selesai)", "running")
        self._ctx.log(f"=== Proses dari Folder: {folder} ===")
        self._folder_worker.start()

    def _on_folder_done(self, result: dict) -> None:
        """Scan folder selesai → isi workbook dgn temp_path → MULAI PIPELINE."""
        self._folder_worker = None
        # Re-enable tombol + kolom workbook (di-disable saat scan).
        self._btn_import.setEnabled(True)
        self._btn_folder.setEnabled(True)
        self._ent_workbook.setEnabled(True)
        self._btn_run.setEnabled(True)  # _start akan set text→Batalkan
        temp = result.get("temp_path", "")
        if not temp:
            # v2.18.0 audit (UI-8): early return dulu membiarkan teks tombol
            # "⏳ Memindai folder…" selamanya — pulihkan label + aksen dulu.
            self._btn_run.setText("▶ Mulai Pipeline")
            self._btn_run.setObjectName("accent")
            self._btn_run.style().unpolish(self._btn_run)
            self._btn_run.style().polish(self._btn_run)
            self._ctx.set_status("⚠ Scan folder: temp file tidak dibuat.", "error")
            return
        self._folder_temp = temp  # simpan utk cleanup nanti
        files = result.get("files", [])
        synth = result.get("synthesized", [])
        skipped = result.get("skipped", [])
        rows_total = result.get("rows_total", 0)
        engine = result.get("engine", "?")
        elapsed = result.get("elapsed_s", 0.0)
        # v2.18.2 — info sheet per file (nama sheet terpilih + skor) &
        # daftar file low-confidence (sheet meragukan — anti silent-error).
        sheets_info = result.get("sheets", {})
        low_conf = set(result.get("low_confidence", []))
        # Log transparan (anti silent-error) — engine + waktu + per-file.
        self._ctx.log(
            f"✓ Folder dipindai: {len(files)} file, {fmt_id(rows_total)} "
            f"baris gabungan ({elapsed}s, engine={engine}).")
        for fn in files:
            tag = " (NAMA RESTO dari nama file)" if fn in synth else ""
            n = result.get("rows_per_file", {}).get(fn, 0)
            info = sheets_info.get(fn) or {}
            sheet = info.get("sheet")
            sheet_tag = f" · sheet {sheet!r}" if sheet else ""
            self._ctx.log(f"  • {fn}: {fmt_id(n)} baris{sheet_tag}{tag}")
            if fn in low_conf:
                self._ctx.log(
                    f"    ⚠ {fn}: sheet terpilih tampaknya BUKAN rekap "
                    f"mentah penuh (skor {info.get('score', '?')} — tanpa "
                    f"kolom SOURCE DATA / JENIS tak kanonik). Periksa "
                    f"isi file.")
        for fn, reason in skipped:
            self._ctx.log(f"  ✕ {fn} dilewati: {reason}")
        # v2.18.3 — transparansi isi-ulang kolom TOTAL (anti silent-error).
        total_filled = result.get("total_filled", 0)
        if total_filled:
            self._ctx.log(
                f"  ℹ Kolom TOTAL: {fmt_id(total_filled)} sel kosong "
                "diisi jumlah kolom hari (sel TOTAL blank di file sumber).")
        self._ctx.log(
            f"  File gabungan (sementara): {Path(temp).name}")
        if synth:
            self._ctx.log(
                "  ⚠ Edit nilai via pop-up menyimpan ke file sementara INI, "
                "BUKAN file asli di folder.")
        # Isi kolom workbook dgn temp path → _start pipeline.
        self._ent_workbook.setText(temp)
        self._ctx.set_status(
            f"✓ {len(files)} file digabung ({fmt_id(rows_total)} baris) — "
            "menjalankan pipeline…", "done")
        self._start()

    def _on_folder_failed(self, msg: str, tb: str) -> None:
        """Scan folder gagal → pulihkan UI + tampilkan error ramah."""
        self._folder_worker = None
        # Re-enable tombol + kolom workbook + restore _btn_run text.
        self._btn_import.setEnabled(True)
        self._btn_folder.setEnabled(True)
        self._ent_workbook.setEnabled(True)
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶ Mulai Pipeline")
        self._btn_run.setObjectName("accent")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._ctx.log(f"!!! Scan folder gagal: {msg}\n{tb}")
        # v2.18.0 audit (HIGH): friendly_file_error HANYA menerima 1 arg &
        # return string — pemanggilan 4-arg lama raise TypeError DI DALAM
        # slot → dialog tak muncul & status error tak terpasang (gagal
        # senyap). Kini: pesan ramah → dialog critical + status.
        QMessageBox.critical(
            self, "Scan Folder Gagal", friendly_file_error(msg))
        self._ctx.set_status(f"⚠ Scan folder gagal: {msg}", "error")

    def _cleanup_folder_temp(self) -> None:
        """Hapus temp file folder-flow sebelumnya (bila ada)."""
        if self._folder_temp:
            try:
                from os import unlink
                unlink(self._folder_temp)
            except OSError:
                pass  # best-effort — tak perlu crash
            self._folder_temp = None

    # ------------------------------------------------------------
    # RUN / CANCEL
    # ------------------------------------------------------------
    def _on_run_button(self) -> None:
        if self._running:
            self._cancel()
        else:
            self._start()

    def _start(self) -> None:
        if self._running:
            return
        # v2.17.4 — guard: bila scan folder sedang jalan, JANGAN mulai
        # pipeline (workbook belum terisi temp path). Pipeline jalan
        # OTOMATIS via _on_folder_done setelah scan selesai.
        if self._folder_worker is not None:
            QMessageBox.information(
                self, "Scan Folder Sedang Berjalan",
                "Folder sedang dipindai — tunggu sebentar.\n"
                "Pipeline akan jalan OTOMATIS setelah scan selesai "
                "(tidak perlu klik Mulai Pipeline).")
            return
        wb = self.current_workbook()
        if not wb or not Path(wb).exists():
            # v2.13.12 (gel-3 D17): "Input Error" → "Input Belum Valid"
            # (label dialog = status JUDUL, bukan tuduhan error sistem —
            # workbook memang belum dipilih).
            QMessageBox.critical(self, "Input Belum Valid",
                                 "Workbook belum dipilih atau tidak ditemukan.")
            return
        ka = self._spin_ka.value()
        self._running = True
        self._btn_run.setText("⏹ Batalkan Run")
        self._btn_run.setObjectName("danger")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._progress.setValue(0)
        self._ctx.set_status("Memulai pipeline…", "running")
        # v2.13.15 (gel-6 D21) — DEDUPE HEADER LOG RUN: dulu baris ini
        # "=== Mulai Pipeline ===" + "Workbook: … • Key Akhir: …" ditulis
        # UI SEBELUM worker jalan, lalu engine mencatat DUPLIKATNYA via
        # _on_progress ("=== Pipeline waste dimulai ===", "Workbook: …",
        # "Key Akhir: …") — awal run menampilkan header+info ganda.
        # Kini header & identitas run DATANG dari engine (diterjemahkan
        # di batas UI, pola D18); UI hanya menambah baris yang TIDAK
        # dikeluarkan engine (jumlah stage).
        self._ctx.log(
            f"{PIPELINE_N_STAGES} stage dianalisa in-memory — progres "
            "per stage di bawah")

        self._worker = PipelineWorker(wb, ka, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        # v2.13.13 (gel-4 D10): worker selesai → deleteLater — tiap run
        # membuat QThread baru; tanpa ini objek worker menumpuk seumur
        # aplikasi (pola ExportWorker app.py / HistoryWorker view_periode;
        # _finish_run sudah melepas ref view, deleteLater meng-amankan
        # objek Qt sendiri pasca-sinyal selesai).
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _cancel(self) -> None:
        if not self._running or self._worker is None:
            return
        self._worker.cancel()
        self._btn_run.setEnabled(False)
        self._ctx.set_status("⏹ Membatalkan run… (berhenti di gate stage berikutnya)", "running")
        self._ctx.log("=== Permintaan batal diterima — pipeline berhenti di gate antar-stage ===")

    def _finish_run(self) -> None:
        self._running = False
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶ Mulai Pipeline")
        self._btn_run.setObjectName("accent")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._worker = None

    def _on_progress(self, msg: str, pct: float) -> None:
        # v2.13.12 (gel-3 D18): terjemahan di BATAS UI — baris log EN
        # engine diterjemahkan SEKALI di sini sehingga label status +
        # panel log + ctx.log_lines (yang ikut diekspor ke sheet Log Run)
        # semuanya Indonesia; engine & nama stage internal tetap EN.
        line = _log_id(msg)
        self._ctx.log(line)
        self._progress.setValue(int(pct))
        self._lbl_status.setText(line)
        # v2.13.13 (gel-4 D5): progres ikut STATUS BAR JENDELA UTAMA —
        # pindah tab saat run dulunya = TANPA indikator progres di
        # jendela utama (progress bar hanya hidup di dalam tab Pipeline;
        # audit D5). Baris stage engine kini membawa "(N%)" (gel-4 B14)
        # → pesan status bar jujur menyertakan persen kumulatif.
        # (Bergetar per baris stage = by design — progres hidup.)
        self._ctx.set_status(f"⏳ {line}", "running")

    def _on_done(self, summary: dict) -> None:
        self._finish_run()
        if not summary.get("success"):
            self._on_failed(summary.get("error", "Unknown error"), "")
            return
        self._progress.setValue(100)
        df = summary.get("df")
        rows = summary.get("total_rows", 0)
        # v2.13.13 (gel-4 D6): pesan "selesai" TIDAK lagi ditulis di sini
        # (pra-render) — dulu ditimpa pesan busy render pasca-set_dataset
        # ("✓ Menyaring & menampilkan data selesai (N ms)") sehingga user
        # membaca pekerjaan filter sebagai hasil akhir; kini ditulis
        # SEKALI, SETELAH render (lihat bawah).
        # v2.13.15 (gel-6 D21): baris "=== Selesai ===" DIHAPUS — header
        # penutup SUDAH dicatat engine ("=== Pipeline DONE ===" → diter-
        # jemahkan "=== Pipeline selesai ===" via _on_progress); menulis
        # kedua = ekor log ber-header ganda (pasangan dedupe header awal).
        self._ctx.log(f"Total baris: {rows}")
        self._ctx.log(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
        cfg_err = summary.get("config_load_error")
        if cfg_err:
            self._ctx.log(f"⚠ Config load error: {cfg_err} — threshold memakai default")
        self._lbl_status.setText(
            f"✓ Selesai — {fmt_id(rows)} baris • {fmt_id(summary.get('prioritas_count', 0))} prioritas")
        # Ringkasan run
        self._render_summary(summary)
        if df is not None and not df.empty:
            self._ctx.set_dataset(df, summary)
        # v2.13.13 (gel-4 D6): pesan status TERAKHIR pasca-run = HASIL
        # RUN (2 angka), ditulis SETELAH set_dataset — seluruh render
        # view (busy_feedback "⏳/✓ Menyaring…") selesai dulu. Dulu pesan
        # "✓ Pipeline selesai" ditulis SEBELUM render lalu ditimpa pesan
        # busy render ("✓ Menyaring & menampilkan data selesai (31 ms)")
        # → user membaca pekerjaan FILTER sebagai hasil akhir (audit D6).
        self._ctx.set_status(
            f"✓ Pipeline selesai — {fmt_id(rows)} baris • "
            f"{fmt_id(summary.get('anomali_count', 0))} anomali "
            "(prioritas+potensi)", "done")
        # v2.13.14 (gel-5 D27): modal "Pipeline Selesai" DIHAPUS dari
        # jalur sukses — status bar jendela utama (pesan hasil run 2
        # angka, gel-4 D6) + kartu "Ringkasan Run" (fmt_id, gel-3 D13)
        # + tab follow-up badge sudah menyampaikan hasilnya; modal tiap
        # run memaksa user menutup dialog SEBELUM bisa melihat data
        # (audit D27: "modal 'Pipeline Selesai' tiap run"). Jalur GAGAL
        # TETAP modal (QMessageBox.critical di _on_failed — error butuh
        # atensi eksplisit + saran perbaikan). Tombol tab kini juga
        # terjangkau Ctrl+1 (gel-5 D24).

    def _on_failed(self, err: str, tb: str) -> None:
        self._finish_run()
        # v2.13.11 (gel-2 D23): progress + label direset JUJUR pasca
        # cancel/gagal — dulu sisa % terakhir menempel selamanya (bar 40%
        # + pesan stage terakhir padahal run sudah tidak berjalan).
        self._progress.setValue(0)
        cancelled = (err == "Run dibatalkan pengguna")
        if cancelled:
            self._lbl_status.setText(
                "⏹ Dibatalkan — tidak ada hasil; progres direset.")
            self._ctx.set_status("⏹ Run dibatalkan pengguna", "error")
            self._ctx.log("=== Run dibatalkan — hasil tidak dirender ===")
            QMessageBox.information(self, "Run Dibatalkan",
                                    "Run dibatalkan — hasil tidak dirender.")
        else:
            self._lbl_status.setText(f"⚠ Gagal: {err}")
            self._ctx.set_status(f"ERROR: {err}", "error")
            self._ctx.log(f"!!! ERROR: {err}")
            if tb:
                self._ctx.log(tb)
            # v2.13.13 (gel-4 D7): error file korup diterjemahkan DI
            # BATAS UI (friendly_file_error — 5 pola EN → Indonesia +
            # saran; worker tetap emit raw, label/log di atas tetap
            # menulis error ASLI supaya bisa dicocokkan dgn traceback).
            QMessageBox.critical(
                self, "Pipeline Error", friendly_file_error(err))

    def _render_summary(self, summary: dict) -> None:
        """v2.13.12 (gel-3 D13): angka fmt_id (pemisah ribuan '.' koma
        desimal ',' — konvensi app) + timestamp '12 Jan 2026 18:07'
        (_fmt_ts_id; dulu ISO mentah '2026-01-12T18:07:33.123456')."""
        rows = ["<table cellspacing='6'>"]
        for key, label in _SUMMARY_LABELS.items():
            val = summary.get(key)
            if val is None:
                continue
            if key == "timestamp":
                shown = _fmt_ts_id(val)
            elif isinstance(val, bool):
                shown = str(val)
            elif isinstance(val, (int, float)):
                shown = fmt_id(val)
            else:
                shown = str(val)
            rows.append(f"<tr><td style='color:#64748b;'>{label}</td>"
                        f"<td style='font-weight:600;'>{shown}</td></tr>")
        rows.append("</table>")
        self._summary.setHtml("".join(rows))

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    # ------------------------------------------------------------
    # CONFIG
    # ------------------------------------------------------------
    def _save_config(self) -> None:
        """Simpan config.json — atomic (tmp + replace) + VALIDASI nilai.

        Regresi v2.6.0 (audit Task 1): teks non-numerik ("0,5" koma Indonesia,
        "abc") dulunya disimpan sebagai STRING ke config.json → run berikutnya
        membaca threshold string (perilaku sinyal berubah senyap). Validasi
        v2.5.1 (tab_config.py) dipulihkan: wajib int/float DAN > 0 — salah
        satu gagal → dialog error + BATAL simpan (file tidak tersentuh).
        """
        target = APP_DIR / "waste_anomaly" / "config.json"
        if not target.parent.exists():  # frozen exe: sidecar di samping exe
            target = APP_DIR / "config.json"
        try:
            # v2.18.0 audit (UI-5): TRANSAKSIONAL — dulu ctx.config termutasi
            # SEBELUM tulis disk; write gagal (file locked editor/permission/
            # disk penuh) → sesi jalan dgn threshold BARU yang tak pernah
            # tersimpan, padahal run berikutnya load_config() baca file LAMA
            # → tab saling kontradiksi senyap. Kini: stage ke salinan, commit
            # ctx.config HANYA setelah replace() sukses.
            staged = {k: (v.copy() if isinstance(v, (dict, list)) else v)
                      for k, v in self._ctx.config.items()}
            staged.setdefault("thresholds", {})
            for key, ent in self._config_vars.items():
                text = ent.text().strip()
                try:
                    val = float(text)
                    val = int(val) if val == int(val) else val
                except ValueError:
                    QMessageBox.critical(self, "Config Error",
                                         f"Nilai untuk {key} tidak valid: {text}")
                    return
                # F2 v2.3.2: validasi rentang — nilai <= 0 mengubah perilaku
                # sinyal diam-diam. (NaN juga tertangkap di sini: NaN bukan
                # int/float valid — int(nan) raise ValueError di atas.)
                if val <= 0:
                    QMessageBox.critical(self, "Config Error",
                                         f"Nilai {key} harus > 0 (dapat: {text})")
                    return
                staged["thresholds"][key] = val
            tmp_path = target.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                # v2.13.14 (gel-5 D26): kunci RUNTIME dikecualikan saat
                # menulis — load_config() menaruh "_config_load_error" di
                # dict config saat config.json korup (jalur fallback
                # default; v2.3.1 H5). Dulu json.dump menulis kunci itu
                # ke disk → config "diperbaiki" user malah membawa error
                # lama permanen + key aneh di file yang user edit manual
                # (audit D26). Salinan difilter — staged tak termutasi
                # (pesan error tetap hidup di sesi ini utk _on_done).
                out_cfg = {k: v for k, v in staged.items()
                           if k != "_config_load_error"}
                json.dump(out_cfg, f, ensure_ascii=False, indent=2)
            tmp_path.replace(target)  # F2: atomic save
            # Commit in-memory SETELAH file sukses tersimpan.
            self._ctx.config.clear()
            self._ctx.config.update(staged)
            self._ctx.set_status(f"✓ config.json tersimpan: {target}", "done")
            self._ctx.log(f"=== Threshold disimpan → {target} (berlaku mulai run berikutnya) ===")
            QMessageBox.information(self, "Config", f"config.json tersimpan:\n{target}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Config Error", f"Gagal menyimpan config:\n{e}")

    def _reset_config(self) -> None:
        """Reset form threshold ke default (20/20 key — belum disimpan).

        Sumber default: _DEFAULT_CONFIG di waste_anomaly/utils.py — kini
        berisi SELURUH 20 key (v2.7.0, dulu 14 → 6 key v2.3.1 tidak pernah
        ter-reset: STATUS_*, S2_SCORE2_MIN, S10_BOM_MIN, QUADRANT_THRESHOLD).
        """
        from waste_anomaly.utils import _DEFAULT_CONFIG
        defaults = _DEFAULT_CONFIG.get("thresholds", {})
        for key, ent in self._config_vars.items():
            if key in defaults:
                ent.setText(str(defaults[key]))
        self._ctx.set_status("Form threshold dikembalikan ke default (belum disimpan)", "running")

    def _preview_thresholds(self) -> None:
        """⑮ v2.13.3: pratinjau distribusi ANOMALY STATUS memakai nilai
        form saat ini (validasi seperti _save_config — tanpa menulis).

        compute_signals murni vektor (± 0,3-0,5 dtk data asli 25,9 ribu
        baris; laptop user 2-4× — sekali per klik, busy feedback).
        """
        df = self._ctx.df
        if df is None or df.empty:
            QMessageBox.information(
                self, "Pratinjau Ambang",
                "Belum ada dataset — jalankan pipeline dulu.")
            return
        params: dict = {}
        for key, ent in self._config_vars.items():
            text = ent.text().strip()
            try:
                val = float(text)
                val = int(val) if val == int(val) else val
            except ValueError:
                QMessageBox.critical(
                    self, "Config Error",
                    f"Nilai untuk {key} tidak valid: {text}")
                return
            if val <= 0:
                QMessageBox.critical(
                    self, "Config Error",
                    f"Nilai {key} harus > 0 (dapat: {text})")
                return
            params[key] = val
        from waste_anomaly.signals import compute_signals
        # v2.13.13 (gel-4 D29): 3 tombol (Mulai/Simpan/Pratinjau)
        # dinonaktifkan SELAMA compute pratinjau (0,3-0,5 dtk data besar)
        # — dulu tetap aktif: klik ganda Pratinjau / klik Mulai saat
        # compute = nested compute sinkron + freeze bertumpuk (audit
        # D29). try/finally: exception compute apa pun tetap memulihkan
        # tombol (tidak ada UI terkunci permanen).
        busy = (self._btn_run, self._btn_save, self._btn_preview)
        for b in busy:
            b.setEnabled(False)
        try:
            with busy_feedback(self._ctx.set_status,
                               "Menghitung pratinjau ambang"):
                out = compute_signals(df, self._ctx.key_akhir,
                                      self._ctx.config, params=params)
        finally:
            for b in busy:
                b.setEnabled(True)
        order = ["Prioritas Tinggi", "Potensi Anomali",
                 "Perlu Review", "Normal"]
        def _counts(series):
            vc = series.value_counts()
            return {s: int(vc.get(s, 0)) for s in order}
        before = _counts(df["ANOMALY STATUS"]) \
            if "ANOMALY STATUS" in df.columns else {s: 0 for s in order}
        after = _counts(out["ANOMALY STATUS"])
        lines = []
        # v2.13.12 (gel-3 D14): angka pemisah ribuan gaya Indonesia
        # (fmt_id — dulu '{:>7,}' koma-EN '25,901' di UI Indonesia).
        for s in order:
            d = after[s] - before[s]
            sign = f"+{fmt_id(d)}" if d > 0 else fmt_id(d)
            arrow = "→" if d == 0 else ("↑" if d > 0 else "↓")
            lines.append(f"{s:<18} {fmt_id(before[s]):>7}  →  "
                         f"{fmt_id(after[s]):>7}  ({sign}) {arrow}")
        n_anom_a = sum(after[s] for s in order[:3])
        n_anom_b = sum(before[s] for s in order[:3])
        self._ctx.log("=== Pratinjau ambang (BELUM disimpan) ===\n"
                      + "\n".join(lines))
        self._ctx.set_status("👀 Pratinjau ambang selesai (lihat dialog)",
                             "done")
        QMessageBox.information(
            self, "Pratinjau Ambang (belum disimpan)",
            "Distribusi status dengan nilai form SAAT INI:\n\n"
            + "\n".join(lines)
            + f"\n\nAnomali total: {fmt_id(n_anom_b)} → {fmt_id(n_anom_a)}\n"
            "Simpan config.json bila hasilnya sesuai (berlaku mulai run "
            "berikutnya).")
