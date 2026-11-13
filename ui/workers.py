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
- FolderScanWorker  : v2.17.2 — scan folder file BJMHAS-style (.xlsx tanpa
                   kolom NAMA RESTO) → sintesis NAMA RESTO dari nama file →
                   gabung → temp .xlsx (siap di-feed PipelineWorker). Untuk
                   opsi "Proses dari Folder" (permintaan user: folder
                   DEVIASI WEEKLY berisi file bjmhas-style).

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
from waste_anomaly.rekap_import import (
    RekapImportError,
    convert_rekap_mentah,
    load_rekap_folder,
)
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


def _build_grouped_layout_df(
    df: pd.DataFrame, key_akhir: int, log
) -> pd.DataFrame | None:
    """v2.19.2 — bangun DataFrame grup utk sheet 'Anomali Grup'.

    Memakai ui.grouping.group_anomali_display (agregasi per KETERANGAN×
    NAMA BARANG×NAMA RESTO — sama dgn tampilan tab Anomali; v2.21.0 kunci
    pertama JENIS → KETERANGAN, permintaan user "grouping pakai keterangan
    terus nama barang"). Mencakup SEMUA baris (bukan hanya anomali) —
    sesuai sampel SAMPEL TAMPILAN BARU.xlsx yg menampilkan seluruh
    item×cabang. has_baseline=False (kolom BULAN LALU diisi bila df sudah
    ber-annotate change_vs_history; selain itu kosong).
    """
    if df is None or df.empty:
        return None
    if not all(k in df.columns for k in
               ("KETERANGAN", "NAMA BARANG", "NAMA RESTO")):
        return None
    from .grouping import group_anomali_display
    fps = fingerprint_series(df)
    cfg = load_config()
    grouped = group_anomali_display(
        df, fps, cfg, key_akhir=key_akhir, has_baseline=False)
    if grouped is None or grouped.empty:
        return None
    log(f"[export] sheet 'Anomali Grup': {len(grouped)} grup item×cabang")
    return grouped


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
        # v2.19.2 — bangun DataFrame grup (layout SAMPEL TAMPILAN BARU) utk
        # sheet 'Anomali Grup'. Best-effort: bila grouping gagal, export
        # tetap jalan tanpa sheet ini (sheet opsional).
        grouped_df = None
        try:
            grouped_df = _build_grouped_layout_df(
                self._df, self._key_akhir, self._log_cb)
        except Exception as e:  # noqa: BLE001 — sheet opsional best-effort
            self._log_cb(f"⚠ Sheet 'Anomali Grup' dilewati: {e}")
        try:
            result = export_to_excel(
                self._df, self._path, self._config, self._key_akhir,
                self._log_lines, extra_sheets=extra,
                grouped_layout_df=grouped_df,
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
                 day_edits: dict, parent=None,
                 src_rows: list[int] | None = None) -> None:
        super().__init__(parent)
        self._source = str(source_path)
        self._day_edits = dict(day_edits)
        # v2.19.2 — dukungan grup MULTI-anggota: bila src_rows (list) akan
        # tulis koreksi yg SAMA ke SEMUA baris Excel anggota grup. src_row
        # tunggal (jalur lama v2.16.0) tetap dipakai bila src_rows=None.
        if src_rows:
            self._src_rows = [int(r) for r in src_rows]
        else:
            self._src_rows = [int(src_row)]

    def run(self) -> None:
        try:
            from waste_anomaly.source_writer import (
                SourceWriteError, write_day_edits)
            results: list[dict] = []
            # Tulis tiap baris anggota grup. Backup dilewati (permintaan user
            # v2.16.1). Bila satu baris gagal — hentikan & lempar (anti
            # sebagian-tulis: file bisa konsisten atau gagal total).
            for r in self._src_rows:
                res = write_day_edits(
                    self._source, r, self._day_edits,
                    logger=None, backup=False)
                results.append(res)
            # Agregat hasil: emit result baris PERTAMA + ringkasan multi-row
            # (cells_written = total seluruh baris; src_rows = semua; total_new
            # = total baris pertama — utk sinkron ctx.df per-anggota di view).
            agg = dict(results[0])
            agg["cells_written"] = sum(r.get("cells_written", 0) for r in results)
            agg["src_rows"] = self._src_rows
            agg["results"] = results
            agg["multi"] = len(self._src_rows) > 1
            self.done.emit(agg)
        except SourceWriteError as e:
            # v2.16.2: sertakan traceback supaya root cause (chained
            # OSError/openpyxl) tak hilang dari log. Sebelumnya: "" (kosong).
            self.failed.emit(str(e), traceback.format_exc())
        except Exception as e:  # noqa: BLE001 — error ke UI, bukan crash thread
            self.failed.emit(f"{type(e).__name__}: {e}",
                             traceback.format_exc())


class BatchUpdateWorker(QThread):
    """v2.19.5 — proses SEMUA koreksi staging ke file Excel (batch).

    Menggantikan jalur SaveEditsWorker satu-per-satu (user: "bisa gak
    misal update nilai nya ke file rekap mentah dikumpulin dulu terus
    baru proses dari pada proses satu per satu?"). Tab Update nilai
    menampung staging; tombol 'Proses semua' menjalankan worker ini.

    Input: list entry staging (sama dgn ctx.pending_updates — dipakai
    APA ADANYA; index entry == index ctx.pending_updates supaya
    mark_update_status(idx) tepat). Entry ber-status 'done' di-skip
    (idempoten — klik Proses ulang tak tulis ulang yg sukses).

    Per entry: loop src_rows (anggota grup) → write_day_edits per row
    (backup=False, langsung timpa file asli — permintaan user v2.19.4).
    Bila satu row gagal → entry FAILED (anti sebagian-tulis: tulis ke
    anggota grup harus konsisten atau gagal total — pola SaveEditsWorker).
    Entry gagal TETAP di staging (status='failed') utk retry setelah
    user tutup Excel; batch lanjut entry berikutnya (jangan hentikan
    seluruh batch karena 1 file terkunci).

    Signals:
      progress(idx, ok, msg) — per entry (idx = index ctx.pending_updates).
      done(n_ok, n_fail)     — ringkasan akhir.
    """

    progress = Signal(int, bool, str)
    done = Signal(int, int)

    def __init__(self, entries: list[dict], parent=None) -> None:
        super().__init__(parent)
        # Snapshot list (referensi dict sama dgn ctx — mutasi status
        # via mark_update_status dilihat UpdateView secara langsung).
        self._entries = list(entries)
        self._cancel = False

    def cancel(self) -> None:
        """Batalkan ANTAR-entry (pola FolderScanWorker — efektif setelah
        entry saat ini selesai; write_day_edits sendiri tak bisa cancel
        tengah-jalan). Dipakai closeEvent supaya close saat batch berjalan
        tak menghancurkan QThread hidup."""
        self._cancel = True

    def run(self) -> None:
        from waste_anomaly.source_writer import (
            SourceWriteError, write_day_edits)
        n_ok = 0
        n_fail = 0
        for i, entry in enumerate(self._entries):
            if self._cancel:
                break
            # Skip entry sudah sukses (idempoten — Proses ulang tak tulis
            # ulang entry 'done').
            if entry.get("status") == "done":
                continue
            source = entry.get("source")
            src_rows = entry.get("src_rows") or []
            day_edits = entry.get("day_edits") or {}
            if not source or not src_rows or not day_edits:
                n_fail += 1
                self.progress.emit(
                    i, False, "Entry tidak lengkap (source/src_rows/day_edits).")
                continue
            try:
                # Tulis tiap baris anggota grup (pola SaveEditsWorker).
                # Bila satu row gagal → entry FAILED (anti sebagian-tulis).
                for r in src_rows:
                    write_day_edits(source, int(r), day_edits,
                                    logger=None, backup=False)
                n_ok += 1
                rows_txt = ", ".join(f"#{r}" for r in src_rows)
                self.progress.emit(
                    i, True,
                    f"{len(day_edits)} hari × {len(src_rows)} baris "
                    f"({rows_txt}) tersimpan.")
            except SourceWriteError as e:
                n_fail += 1
                self.progress.emit(i, False, str(e))
            except Exception as e:  # noqa: BLE001 — error ke UI, bukan crash
                n_fail += 1
                self.progress.emit(i, False, f"{type(e).__name__}: {e}")
        self.done.emit(n_ok, n_fail)


class FolderScanWorker(QThread):
    """v2.17.2 — scan folder file .xlsx → gabung → temp .xlsx (background).

    Untuk opsi "Proses dari Folder" (permintaan user: folder DEVIASI WEEKLY
    berisi file bjmhas-style). Memanggil waste_anomaly.rekap_import
    .load_rekap_folder — scan .xlsx, deteksi sheet REKAP MENTAH (lenient —
    tanpa NAMA RESTO wajib), sintesis NAMA RESTO dari nama file bila kolom
    absen, gabung semua, tulis temp .xlsx.

    done → dict hasil load_rekap_folder (temp_path, files, rows_total,
    rows_per_file, synthesized, skipped). UI mengisi kolom workbook dgn
    temp_path lalu "Mulai Pipeline" (PipelineWorker) memprosesnya.
    failed → (pesan singkat, traceback). RekapImportError sudah ramah
    (pesan siap tampil); traceback kosong untuk kasus itu.

    Anti silent-error: file tanpa sheet REKAP MENTAH dicatat di
    result["skipped"] (bukan diam-dalam dibuang). NAMA RESTO disintesis
    dicatat di result["synthesized"] (transparan).
    """

    done = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, folder_path: str, config: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._folder = str(folder_path)
        self._config = config if config is not None else load_config()
        self._cancel = False

    def cancel(self) -> None:
        """v2.18.0 audit (UI-2): batalkan scan — efektif ANTAR-FILE
        (pola HistoryWorker; dipakai closeEvent supaya close saat scan
        berjalan tidak menghancurkan QThread hidup → qFatal)."""
        self._cancel = True

    def run(self) -> None:
        try:
            result = load_rekap_folder(
                self._folder, self._config, logger=None,
                cancel_check=lambda: self._cancel)
            self.done.emit(result)
        except RekapImportError as e:
            self.failed.emit(str(e), "")
        except Exception as e:  # noqa: BLE001 — error ke UI, bukan crash thread
            self.failed.emit(f"{type(e).__name__}: {e}",
                             traceback.format_exc())
