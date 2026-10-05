"""state.py — AppContext: satu sumber state + signal Qt (v2.6.0).

Pengganti state tersebar di god-object Tkinter lama (active_filters,
day_min/max, _preview_dfs, last_summary, ...). Views membaca state via
ctx, bereaksi lewat signal:

- data_ready()      → dataset baru dari pipeline (df + summary)
- filters_changed() → filter/drill-down berubah
- status(text, kind)→ pesan status bar ("running"|"done"|"error")
- log_line(str)     → satu baris log

v2.8.1: _build_derived_sheets + ctx.sheets DIHAPUS — satu-satunya
konsumen adalah view Jelajah (dihapus total); export Excel membangun
sheet analisanya sendiri (ui/workers.py::_extra_sheets).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from PySide6.QtCore import QObject, Signal

from .shared import _apply_filters

# Label filter aktif → chip Indonesia (dari shared lama)
CHIP_LABELS = {
    "cabang": "Cabang", "status": "Status", "item": "Item", "search": "Cari",
    "jenis": "Jenis", "keterangan": "Keterangan", "hari": "Rentang Hari",
}


class AppContext(QObject):
    """State aplikasi tunggal + signal perubahan."""

    data_ready = Signal()
    filters_changed = Signal()
    status = Signal(str, str)
    log_line = Signal(str)

    def __init__(self, config: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.df: pd.DataFrame | None = None
        self.summary: dict | None = None
        self.key_akhir: int = 31
        self.last_run_time: datetime | None = None
        self.log_lines: list[str] = []
        # v2.7.0: versi dataset — bertambah tiap set_dataset; dipakai view
        # (mis. Banding Periode) utk tahu hasil lama dibuat dari dataset lama.
        self.data_version = 0

        # Drill-down state (bentuk IDENTIK v2.5.1 — dikonsumsi _apply_filters)
        self.active_filters: dict[str, str | list[str] | None] = {
            "cabang": None, "item": None, "jenis": [],
            "keterangan": None, "status": None,
        }
        self.day_min: int | None = None
        self.day_max: int | None = None
        self.search = ""
        # v2.6.0: ambang skor minimum (khusus tabel anomali — fitur hunting)
        self.score_min = 0
        # v2.7.0 (perf, audit Task ID 1): memo hasil filtered_df — dulu
        # _apply_filters dijalankan 2× per refresh (anomali_df + KPI view)
        # atas df 25.901×53. Divalidasi oleh set_filter/set_search/
        # set_day_range/set_score_min/reset_filters/set_dataset. Pemanggil
        # hanya membaca (mask/slice kolom = copy) — kontrak aman tanpa copy
        # ekstra per hit.
        self._filtered_cache: pd.DataFrame | None = None
        self._filter_cache_valid = False

    # ------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------
    def set_dataset(self, df: pd.DataFrame, summary: dict) -> None:
        """Dataset baru dari pipeline: simpan + reset filter + broadcast."""
        self.df = df
        self.summary = summary
        try:
            self.key_akhir = int(summary.get("key_akhir", 31))
        except (TypeError, ValueError):
            self.key_akhir = 31
        self.last_run_time = datetime.now()
        self.data_version += 1
        self.reset_filters()  # juga meng-invalidasi memo filtered_df
        self.data_ready.emit()
        # v2.7.0 (V26-H2): siarkan reset filter SEKALI SETELAH data_ready —
        # views pendengar filters_changed (Anomali/Banding Periode) menandai dirty
        # secara konsisten. Urutan setelah data_ready dipilih karena pada
        # alur tipikal re-run user ada di tab Pipeline (view tidak terlihat
        # → kedua handler hanya menandai dirty, TANPA render ganda); bila
        # kebetulan terlihat, handler filters_changed hanya partial refresh
        # (bukan refresh penuh ganda).
        self.filters_changed.emit()

    # ------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------
    def filtered_df(self) -> pd.DataFrame | None:
        """df hasil filter lengkap (search + dropdown + rentang hari).

        v2.7.0: hasil di-memo — dipakai ulang sampai filter/data berubah
        (lihat invalidasi di setter + invalidate_filter_cache).
        """
        if self.df is None:
            return None
        if not self._filter_cache_valid:
            self._filtered_cache = _apply_filters(
                self.df, self.active_filters,
                day_min=self.day_min, day_max=self.day_max,
                search=self.search,
            )
            self._filter_cache_valid = True
        return self._filtered_cache

    def invalidate_filter_cache(self) -> None:
        """Batalkan memo filtered_df — WAJIB dipanggil bila filter state
        dimutasi langsung (bypass setter), mis. pemulihan profil filter."""
        self._filter_cache_valid = False

    def anomali_df(self) -> pd.DataFrame | None:
        """df terfilter, hanya baris ANOMALY STATUS ≠ Normal, skor ≥ min."""
        df = self.filtered_df()
        if df is None:
            return None
        if "ANOMALY STATUS" in df.columns:
            df = df[df["ANOMALY STATUS"] != "Normal"]
        if self.score_min > 0 and "ANOMALY SCORE" in df.columns:
            df = df[pd.to_numeric(df["ANOMALY SCORE"], errors="coerce")
                    .fillna(0) >= self.score_min]
        return df

    def set_filter(self, key: str, value) -> None:
        """Set satu filter (drill-down atau dropdown) lalu broadcast."""
        self.active_filters[key] = value
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_day_range(self, day_min: int | None, day_max: int | None) -> None:
        self.day_min = day_min
        self.day_max = day_max
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_search(self, text: str) -> None:
        self.search = text
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_score_min(self, score: int) -> None:
        self.score_min = score
        self._filter_cache_valid = False  # tak dipakai _apply_filters, tetap aman
        self.filters_changed.emit()

    def reset_filters(self) -> None:
        """Reset total ke nilai default (tanpa broadcast — pemanggil yang
        memutuskan; set_dataset sudah diikuti data_ready)."""
        for k in self.active_filters:
            self.active_filters[k] = [] if k == "jenis" else None
        self.day_min = None
        self.day_max = None
        self.search = ""
        self.score_min = 0
        self._filter_cache_valid = False

    def filter_summary(self) -> str:
        """Deskripsi filter aktif (utk chip / status bar)."""
        parts: list[str] = []
        for key, val in self.active_filters.items():
            if val is None or (isinstance(val, list) and not val):
                continue
            label = CHIP_LABELS.get(key, key.title())
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val[:3]) + ("…" if len(val) > 3 else "")
            parts.append(f"{label}: {val}")
        if self.day_min is not None and self.day_max is not None:
            parts.append(f"{CHIP_LABELS['hari']}: {self.day_min}–{self.day_max}")
        if (self.search or "").strip():
            parts.append(f'{CHIP_LABELS["search"]}: "{self.search.strip()}"')
        return " • ".join(parts)

    # ------------------------------------------------------------
    # LOG / STATUS
    # ------------------------------------------------------------
    def log(self, msg: str) -> None:
        self.log_lines.append(str(msg))
        if len(self.log_lines) > 500:
            del self.log_lines[: len(self.log_lines) - 500]
        self.log_line.emit(str(msg))

    def set_status(self, text: str, kind: str = "running") -> None:
        self.status.emit(text, kind)
