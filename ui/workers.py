"""workers.py — pekerja background (QThread) v2.10.0.

Pipeline/export/history-pembanding tetap berjalan di thread terpisah (UI
tidak freeze) — pola QThread + Signal:
- PipelineWorker : run_pipeline + progress + cancel antar-stage (F9)
- ExportWorker   : export_to_excel + extra_sheets (P1/P2/P6)
- HistoryWorker  : muat N workbook pembanding (kuantiti) + tipikal (v2.10.0
                   menggantikan PeriodWorker — banding kini multi-file,
                   kuantiti tanpa BOM, via waste_anomaly/period_history)
- RekapImportWorker : olah REKAP MENTAH mentah → workbook DATA_WASTE standar
                   (v2.14.0 — menggantikan olahan manual Excel user;
                   jalur waste_anomaly/rekap_import)

v2.15.0 — SEKALI JALAN: tombol 🧮 UI kini menjalankan pipeline LANGSUNG
pada file mentah (rekap_import dipanggil pipeline.py di fase LOAD —
ensure_rekap_header + normalize_rekap_values + inject_bom_from_raw_rows),
TANPA file olahan antara (permintaan user: "aku mau sekali proses aja dan
gak perlu export hasil olahan proses rekap mentah nya"). RekapImportWorker
TETAP tersedia sebagai API berdiri-sendiri (ekspor file olahan untuk
arsip/pemakaian programatik — teruji test_v2140; UI tidak lagi
memanggilnya).
"""
from __future__ import annotations

import traceback
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QThread, Signal

from waste_anomaly.exporter import export_to_excel
from waste_anomaly.period_history import load_history_file
from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.rekap_import import RekapImportError, convert_rekap_mentah
from waste_anomaly.utils import load_config

from waste_anomaly.followup import fingerprint_series


def _extra_sheets(df: pd.DataFrame, key_akhir: int, log) -> dict:
    """Sheet analisa tambahan untuk laporan Excel (logika v2.5.0 port).

    P1: 'Waste per Hari' + 'Alasan x Hari'; P2: 'Money View'; P6: 'Data Quality'.
    Best-effort — modul gagal → sheet di-skip (tercatat di log).
    """
    sheets: dict = {}
    try:
        from waste_anomaly import temporal as wa_temporal
        per_day = wa_temporal.waste_per_day(df, key_akhir=key_akhir)
        if not per_day.empty:
            sheets["Waste per Hari"] = per_day
        reason_day = wa_temporal.reason_by_day(df, key_akhir=key_akhir)
        if not reason_day.empty:
            sheets["Alasan x Hari"] = reason_day
    except Exception as e:  # noqa: BLE001 — sheet opsional best-effort
        log(f"⚠ Sheet temporal untuk export dilewati: {e}")
    try:
        from waste_anomaly import priority as wa_priority
        mv = wa_priority.money_view(df, top_n=100)
        if not mv.empty:
            sheets["Money View"] = mv
    except Exception as e:  # noqa: BLE001
        log(f"⚠ Sheet money view untuk export dilewati: {e}")
    try:
        from waste_anomaly import data_quality as wa_dq
        checks = wa_dq.run_checks(df, key_akhir=key_akhir)
        if checks:
            sheets["Data Quality"] = pd.DataFrame([
                {
                    "Severity": r.severity, "Kode": r.code, "Judul": r.title,
                    "Jumlah": r.count, "Detail": r.detail,
                    "Contoh": " | ".join(r.sample),
                }
                for r in checks
            ])
    except Exception as e:  # noqa: BLE001
        log(f"⚠ Sheet data quality untuk export dilewati: {e}")
    return sheets


class PipelineWorker(QThread):
    """Jalankan pipeline penuh di background thread.

    F9: cancel_check antar-stage — tombol Batal efektif (worker set event;
    pipeline berhenti di gate berikutnya dan mengembalikan cancelled=True).
    """

    progress = Signal(str, float)
    done = Signal(dict)
    failed = Signal(str, str)  # (pesan singkat, traceback)

    def __init__(self, workbook: str, key_akhir: int, parent=None) -> None:
        super().__init__(parent)
        self._workbook = workbook
        self._key_akhir = key_akhir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: C901 — kontrak worker lama
        try:
            summary = run_pipeline(
                workbook_path=self._workbook,
                key_akhir=self._key_akhir,
                progress_callback=lambda msg, pct: self.progress.emit(str(msg), float(pct)),
                cancel_check=lambda: self._cancel,
            )
            # v2.13.7 (perf-audit B): blob pencarian TIDAK lagi dibangun di
            # worker — kotak cari dihapus dari UI sejak v2.12.4, hasilnya
            # tak pernah terpakai di produksi (terbuang ±1,2 dtk per run
            # di data asli 25.901 baris). State tetap menyediakan jalur
            # pembangunan malas utk pengujian semantik filter (set_search).
            if summary.get("success") and summary.get("df") is not None:
                # v2.12.1 (perf): sidik jari follow-up dataset penuh
                # dibangun DI THREAD WORKER (~0,3 dtk data asli 25.901
                # baris) — sebelumnya dibangun malas di thread UI saat
                # pertama dibutuhkan (prune data_ready / buka tab Follow
                # Up / centang pertama) = beku sesaat pasca-pipeline.
                self.progress.emit("Menyiapkan data follow-up ...", 99)
                summary["followup_fps"] = fingerprint_series(
                    summary["df"])
        except Exception as e:  # noqa: BLE001 — semua error ke UI, bukan crash thread
            self.failed.emit(str(e), traceback.format_exc())
            return
        if summary.get("cancelled") or self._cancel:
            self.failed.emit("Run dibatalkan pengguna", "")
            return
        self.done.emit(summary)


class ExportWorker(QThread):
    """Tulis laporan Excel (6 sheet inti + extra) dari df in-memory (H6)."""

    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, df: pd.DataFrame, path: str, config: dict,
                 key_akhir: int, log_lines: list[str], parent=None) -> None:
        super().__init__(parent)
        self._df = df
        self._path = path
        self._config = config
        self._key_akhir = key_akhir
        self._log_lines = log_lines
        self._log_cb = lambda msg: None

    def set_log(self, log_cb) -> None:
        self._log_cb = log_cb

    def run(self) -> None:
        extra = _extra_sheets(self._df, self._key_akhir, self._log_cb)
        try:
            result = export_to_excel(
                self._df, self._path, self._config, self._key_akhir,
                self._log_lines, extra_sheets=extra,
            )
        except Exception as e:  # defensive — kontrak exporter dict
            self.failed.emit(str(e))
            return
        if isinstance(result, dict):
            result.setdefault("extra_sheets_count", 0)
            self.done.emit(result)
        else:
            self.failed.emit(str(result))


class HistoryWorker(QThread):
    """v2.10.0: muat N workbook pembanding (kuantiti) di background.

    Menggantikan PeriodWorker (pipeline penuh per file B, 7,5 dtk/file):
    jalur ringan load_history_file (load + saringan JENIS + agregat hari,
    ±2-3 dtk/file) sesuai kebutuhan user — "hanya bandingkan tanpa angka
    BOM / secara kuantiti". Cancel dicek ANTAR file (efektif ≤ 1 file
    setelah tombol ditekan); file gagal → entri ber-"error" (merah di
    daftar), file lain tetap diproses. Tipikal gabungan dihitung VIEW
    (_finalize) atas set bulan gabungan penuh (cache + baru) — worker
    tidak menghitungnya supaya tidak ada dua jalur kebenaran.
    """

    progress = Signal(str, float)
    done = Signal(list)   # daftar entri bulan (bisa berisi entri error)
    failed = Signal(str, str)

    def __init__(self, entries: list[dict], config: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        # entries: [{"path": str, "label": str | None (override manual)}]
        self._entries = list(entries or [])
        self._config = config if config is not None else load_config()
        self._cancel = False

    def cancel(self) -> None:
        """Batalkan — efektif di gate antar-file."""
        self._cancel = True

    def run(self) -> None:
        try:
            months: list[dict] = []
            total = max(1, len(self._entries))
            for i, ent in enumerate(self._entries):
                if self._cancel:
                    self.failed.emit(
                        "Pemuatan pembanding dibatalkan pengguna", "")
                    return
                path = str(ent.get("path", ""))
                name = Path(path).name if path else "(tanpa nama)"
                self.progress.emit(
                    f"Memuat pembanding {name} … ({i + 1}/{total})",
                    100.0 * i / total)
                entry = load_history_file(path, self._config)
                manual = ent.get("label")
                if manual:
                    entry["label"] = str(manual)
                    entry["label_source"] = "manual"
                months.append(entry)
            self.done.emit(months)
        except Exception as e:  # noqa: BLE001 — semua error ke UI, bukan crash thread
            self.failed.emit(str(e), traceback.format_exc())


class RekapImportWorker(QThread):
    """v2.14.0: olah REKAP MENTAH mentah → workbook DATA_WASTE standar.

    Dulu user harus mengolah manual di Excel (filter JENIS + formula +
    Power Query) supaya jadi struktur 53 kolom — kini satu panggilan
    API. Berjalan di background (pembacaan ±54 ribu baris + tulis
    ±25 ribu baris = ±10-15 dtk — UI tidak boleh freeze); pola sinyal
    mengikuti PipelineWorker/HistoryWorker (done/failed + deleteLater
    D10 di sisi view). Config dilewatkan pemanggil (dict sudah termuat —
    tidak baca-ulang file dari dalam thread).

    v2.15.0 — API BERDIRI-SENDIRI: tombol 🧮 UI kini SEKALI JALAN
    (pipeline memanggil rekap_import di fase LOAD — tanpa file antara),
    jadi worker ini TIDAK lagi dipakai jalur utama UI; tetap tersedia
    untuk ekspor file olahan programatik (teruji test_v2140).

    done → dict ringkasan (lihat convert_rekap_mentah): out_path,
    rows_raw/rows_kept, jenis_counts, bom_pairs/bom_matched, dll.
    failed → (pesan singkat, traceback). RekapImportError sudah ramah
    (pesan siap tampil); traceback kosong untuk kasus itu.
    """

    done = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, source: str,
                 out_path: str | None = None,
                 config: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._source = str(source)
        self._out_path = out_path
        self._config = config if config is not None else load_config()

    def run(self) -> None:
        try:
            result = convert_rekap_mentah(
                self._source, out_path=self._out_path,
                config=self._config)
            self.done.emit(result)
        except RekapImportError as e:
            # Pesan sudah user-friendly (daftar masalah + saran) —
            # traceback kosong: tidak ada yang perlu dicocokkan.
            self.failed.emit(str(e), "")
        except Exception as e:  # noqa: BLE001 — error ke UI, bukan crash thread
            self.failed.emit(f"{type(e).__name__}: {e}",
                             traceback.format_exc())


class SaveEditsWorker(QThread):
    """v2.16.1 — tulis koreksi hari ke file Excel di background thread.

    MASALAH: write_day_edits di UI thread membekukan aplikasi ~2 detik
    (file 10MB) → "Not Responding". User: "percepat proses revisi
    kuantiti nya? yang sekarang masih lama dan not responding."

    SOLUSI: jalankan write_day_edits di QThread terpisah. UI tetap responsif
    (status "Menyimpan…" + tombol di-disable selagi worker jalan). Signal
    done/failed dikirim ke UI thread utk update df + dialog hasil.

    backup=False default (permintaan user: "Gak perlu ada back up file aja
    biar cepat dan aku sudah aku yakin dengan perubahan nku"). Verifikasi
    post-write TETAP jalan (anti silent-error — tulis yg salah = raise).
    """

    done = Signal(dict)
    failed = Signal(str, str)  # (pesan singkat, traceback)

    def __init__(self, source_path: str, src_row: int,
                 day_edits: dict, parent=None) -> None:
        super().__init__(parent)
        self._source = str(source_path)
        self._src_row = int(src_row)
        self._day_edits = dict(day_edits)

    def run(self) -> None:
        try:
            from waste_anomaly.source_writer import (
                SourceWriteError, write_day_edits)
            result = write_day_edits(
                self._source, self._src_row, self._day_edits,
                logger=None, backup=False)
            self.done.emit(result)
        except SourceWriteError as e:
            # v2.16.2: sertakan traceback supaya root cause (chained
            # OSError/openpyxl) tak hilang dari log. Sebelumnya: "" (kosong).
            self.failed.emit(str(e), traceback.format_exc())
        except Exception as e:  # noqa: BLE001 — error ke UI, bukan crash thread
            self.failed.emit(f"{type(e).__name__}: {e}",
                             traceback.format_exc())
