"""view_pipeline.py — view 'Pipeline': jalankan analisa + log + ringkasan
+ editor threshold config (gabungan tab Run + Ringkasan + Config lama).

Worker = QThread (ui tidak freeze); tombol dua-mode Mulai↔Batalkan (F9);
log selalu terlihat (popup log lama dihapus — tidak ada tombol ganda).

v2.14.0: tombol 🧮 "Olah REKAP MENTAH…" — pilih file mentah → diolah
background (RekapImportWorker) jadi workbook DATA_WASTE standar (saring
JENIS WASTE/SUSUT/TRIAL + TOTAL BOM dari baris JENIS==BOM + kolom
hitungan semantika stage_02/05; menggantikan olahan manual Excel user);
kolom workbook terisi otomatis + log ringkasan + petunjuk Mulai Pipeline.

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
from .widgets import Card, WLabel, busy_feedback
from .workers import PipelineWorker, RekapImportWorker
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
        # v2.14.0 — worker olah REKAP MENTAH (satu aktif; referensi dipegang
        # supaya tidak GC saat thread jalan — pola _worker pipeline).
        self._import_worker: RekapImportWorker | None = None

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
        # v2.14.0 — olah REKAP MENTAH mentah jadi DATA_WASTE standar
        # (menggantikan olahan manual Excel user: saring JENIS WASTE/
        # SUSUT/TRIAL + ekstrak TOTAL BOM baris JENIS==BOM + kolom
        # hitungan stage_02/05 — jalur waste_anomaly/rekap_import).
        b_import = QPushButton("🧮 Olah REKAP MENTAH…", row)
        b_import.setToolTip(
            "Pilih file REKAP MENTAH mentah (mis. \"REKAP MENTAH_01-31 "
            "AGUSTUS 2026_TEGAR.xlsx\") — diolah otomatis jadi workbook "
            "DATA_WASTE standar (saring WASTE/SUSUT/TRIAL + TOTAL BOM dari "
            "baris BOM) lalu siap Mulai Pipeline. Menggantikan olahan "
            "manual di Excel.")
        b_import.clicked.connect(self._on_import_rekap)
        rl.addWidget(b_import)
        self._btn_import = b_import
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
        page_lay.addWidget(c3, 1)

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

        # Log line dari ctx → panel log (worker progress juga lewat sini)
        ctx.log_line.connect(self._append_log)
        # Set split: ringkasan/log card mendapat ruang lebih besar
        page_lay.setStretch(2, 3)
        page_lay.setStretch(3, 2)

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
    # v2.14.0 — OLAH REKAP MENTAH (menggantikan olahan manual Excel)
    # ------------------------------------------------------------
    def _on_import_rekap(self) -> None:
        """Pilih file REKAP MENTAH mentah → olah di background thread.

        Dulu: user filter JENIS + formula + Power Query manual di Excel
        supaya jadi struktur 53 kolom. Kini: satu tombol — worker
        (RekapImportWorker) menjalankan convert_rekap_mentah (baca ±54
        ribu baris + tulis ±25 ribu baris = ±10-15 dtk — UI tetap hidup,
        pola QThread PipelineWorker/HistoryWorker; D29: tombol Mulai +
        tombol ini dinonaktifkan selama proses supaya klik-ganda tidak
        membuat worker ganda)."""
        if self._running:
            QMessageBox.information(
                self, "Pipeline Sedang Berjalan",
                "Tunggu pipeline selesai (atau batalkan) sebelum mengolah "
                "file REKAP MENTAH baru.")
            return
        if self._import_worker is not None and self._import_worker.isRunning():
            return  # sudah berjalan — klik ganda di-swallow senyap
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
        self._btn_import.setEnabled(False)
        self._btn_run.setEnabled(False)
        self._ctx.set_status(
            f"⏳ Mengolah REKAP MENTAH: {Path(path).name} …", "running")
        self._ctx.log(f"=== Olah REKAP MENTAH: {Path(path).name} ===")
        self._lbl_status.setText("⏳ Mengolah REKAP MENTAH di background…")
        self._import_worker = RekapImportWorker(
            path, config=self._ctx.config, parent=self)
        self._import_worker.done.connect(self._on_import_done)
        self._import_worker.failed.connect(self._on_import_failed)
        # D10 (gel-4): worker selesai → deleteLater — objek QThread tidak
        # menumpuk seumur aplikasi (pola PipelineWorker/ExportWorker).
        self._import_worker.finished.connect(self._import_worker.deleteLater)
        self._import_worker.start()

    def _on_import_done(self, result: dict) -> None:
        """Olahan selesai → isi kolom workbook + log ringkasan + petunjuk
        langkah berikutnya (Mulai Pipeline)."""
        self._btn_import.setEnabled(True)
        self._btn_run.setEnabled(True)
        self._ent_workbook.setText(result.get("out_path", ""))
        jenis = ", ".join(
            f"{k} {fmt_id(v)}"
            for k, v in sorted(result.get("jenis_counts", {}).items()))
        lines = [
            f"✓ REKAP MENTAH terolah → {Path(result.get('out_path', '')).name}",
            f"  {fmt_id(result.get('rows_raw', 0))} baris mentah → "
            f"{fmt_id(result.get('rows_kept', 0))} baris data "
            f"({jenis})",
            f"  {fmt_id(result.get('resto_count', 0))} cabang · "
            f"{fmt_id(result.get('item_count', 0))} item · "
            f"{fmt_id(result.get('day_count', 0))} kolom hari",
            f"  BOM: {fmt_id(result.get('bom_pairs', 0))} pasangan "
            f"(resto, barang) — {fmt_id(result.get('bom_matched', 0))} baris "
            f"data ber-TOTAL BOM (sinyal S6/S7 aktif)",
            "  Kolom workbook terisi otomatis — klik ▶ Mulai Pipeline.",
        ]
        for ln in lines:
            self._ctx.log(ln)
        self._lbl_status.setText(
            f"✓ Terolah: {fmt_id(result.get('rows_kept', 0))} baris — "
            "siap Mulai Pipeline")
        self._ctx.set_status(
            f"✓ REKAP MENTAH terolah: {fmt_id(result.get('rows_kept', 0))} "
            f"baris • {fmt_id(result.get('bom_pairs', 0))} pasangan BOM",
            "ok")
        QMessageBox.information(
            self, "REKAP MENTAH Terolah",
            "File mentah berhasil diolah jadi workbook DATA_WASTE standar:\n"
            f"\n{result.get('out_path', '')}"
            f"\n\nBaris mentah: {fmt_id(result.get('rows_raw', 0))}"
            f"\nBaris data (WASTE/SUSUT/TRIAL): {fmt_id(result.get('rows_kept', 0))}"
            f"\nJenis: {jenis}"
            f"\nCabang: {fmt_id(result.get('resto_count', 0))} · "
            f"Item: {fmt_id(result.get('item_count', 0))}"
            f"\nTOTAL BOM: {fmt_id(result.get('bom_pairs', 0))} pasangan "
            f"({fmt_id(result.get('bom_matched', 0))} baris ber-BOM)"
            "\n\nKolom workbook sudah terisi — tinggal klik "
            "▶ Mulai Pipeline.")

    def _on_import_failed(self, err: str, tb: str) -> None:
        """Olahan gagal → tombol dipulihkan + pesan ramah (pola D7:
        RekapImportError sudah ramah; error lain diterjemahkan di batas
        UI via friendly_file_error, traceback utuh ke log panel)."""
        self._btn_import.setEnabled(True)
        self._btn_run.setEnabled(True)
        self._lbl_status.setText("⚠ Olah REKAP MENTAH gagal")
        self._ctx.set_status(f"ERROR: {err}", "error")
        self._ctx.log(f"!!! Olah REKAP MENTAH gagal: {err}")
        if tb:
            self._ctx.log(tb)
        QMessageBox.critical(
            self, "Olah REKAP MENTAH Gagal", friendly_file_error(err))

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
                self._ctx.config.setdefault("thresholds", {})[key] = val
            tmp_path = target.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                # v2.13.14 (gel-5 D26): kunci RUNTIME dikecualikan saat
                # menulis — load_config() menaruh "_config_load_error" di
                # dict config saat config.json korup (jalur fallback
                # default; v2.3.1 H5). Dulu json.dump menulis kunci itu
                # ke disk → config "diperbaiki" user malah membawa error
                # lama permanen + key aneh di file yang user edit manual
                # (audit D26). Salinan difilter — ctx.config tak termutasi
                # (pesan error tetap hidup di sesi ini utk _on_done).
                out_cfg = {k: v for k, v in self._ctx.config.items()
                           if k != "_config_load_error"}
                json.dump(out_cfg, f, ensure_ascii=False, indent=2)
            tmp_path.replace(target)  # F2: atomic save
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
