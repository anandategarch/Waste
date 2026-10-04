"""workers.py — pekerja background (QThread) v2.6.0.

Pipeline/export/compare-period tetap berjalan di thread terpisah (UI tidak
freeze) — pola worker+queue Tkinter lama diganti QThread + Signal:
- PipelineWorker: run_pipeline + progress + cancel antar-stage (F9)
- ExportWorker: export_to_excel + extra_sheets (P1/P2/P6)
- PeriodWorker: run_pipeline periode B + compare_periods (P9)
"""
from __future__ import annotations

import traceback
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QThread, Signal

from waste_anomaly.exporter import export_to_excel
from waste_anomaly.loader import load_rekap_mentah
from waste_anomaly.period_compare import auto_key_akhir, compare_periods
from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.utils import load_config


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


class PeriodWorker(QThread):
    """P9: jalankan pipeline untuk workbook B (key_akhir otomatis) lalu
    bandingkan periode A (dataset aktif) vs B.

    v2.7.0 (regresi v2.6.0 vs v2.5.1 tab_period.py): key_akhir B dideteksi
    dari sheet mentah SEBELUM run_pipeline. Dulu key_akhir=None → pipeline
    memakai default 31 → bila workbook B hanya berisi data s.d. hari 20,
    sinyal S11 (LAST DAY SHARE) dihitung vs hari 31 yang kosong → S11
    tidak pernah terpicu untuk periode B. Plus cancel_check (V26-L5).
    """

    done = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, df_a: pd.DataFrame, workbook_b: str,
                 key_akhir_a: int, config: dict | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._df_a = df_a
        self._workbook_b = workbook_b
        self._ka_a = key_akhir_a
        # Config utk loader mentah (sheet/named-range resolution) — default
        # load_config() sama seperti jalur run_pipeline tanpa config_path.
        self._config = config if config is not None else load_config()
        self._cancel = False

    def cancel(self) -> None:
        """V26-L5: batalkan — efektif di gate antar-stage pipeline B."""
        self._cancel = True

    def _detect_key_akhir_b(self) -> int:
        """Hari aktif terbesar workbook B dari sheet mentah (via
        load_rekap_mentah + auto_key_akhir — fungsi yang sama dipakai
        run_pipeline utk membaca sheet). Fallback 31 bila gagal/kosong."""
        try:
            raw_b = load_rekap_mentah(self._workbook_b, self._config)
            ka_b = auto_key_akhir(raw_b)
        except Exception:  # noqa: BLE001 — defensif: pipeline tetap jalan
            ka_b = 31
        try:
            ka_b = int(ka_b)
        except (TypeError, ValueError):
            ka_b = 31
        return ka_b if 1 <= ka_b <= 31 else 31

    def run(self) -> None:
        try:
            ka_b = self._detect_key_akhir_b()
            if self._cancel:
                self.failed.emit("Perbandingan dibatalkan pengguna", "")
                return
            summary_b = run_pipeline(
                workbook_path=self._workbook_b,
                key_akhir=ka_b,
                progress_callback=lambda msg, pct: None,
                cancel_check=lambda: self._cancel,
            )
            if summary_b.get("cancelled") or self._cancel:
                self.failed.emit("Perbandingan dibatalkan pengguna", "")
                return
            if not summary_b.get("success"):
                self.failed.emit(
                    summary_b.get("error", "Pipeline periode B gagal"), "")
                return
            df_b = summary_b["df"]
            # ka_b hasil deteksi mentah dipakai BAIK utk pipeline B maupun
            # normalisasi perbandingan (compare_periods) — konsisten.
            result = compare_periods(
                self._df_a, df_b,
                key_akhir_a=self._ka_a, key_akhir_b=ka_b,
            )
            result = dict(result)
            result["key_akhir_b"] = ka_b
            result["workbook_b"] = str(Path(self._workbook_b).name)
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e), traceback.format_exc())
