"""state.py — AppContext: satu sumber state + signal Qt (v2.6.0).

Pengganti state tersebar di god-object Tkinter lama (active_filters,
day_min/max, _preview_dfs, last_summary, ...). Views membaca state via
ctx, bereaksi lewat signal:

- data_ready()      → dataset baru dari pipeline (df + summary + sheet turunan)
- filters_changed() → filter/drill-down berubah
- status(text, kind)→ pesan status bar ("running"|"done"|"error")
- log_line(str)     → satu baris log
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


def _build_derived_sheets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Sheet turunan in-memory — logika IDENTIK tab_run.py v2.5.1.

    Dipakai view Jelajah (combo sheet) + export Excel (sheet inti).
    """
    sheets: dict[str, pd.DataFrame] = {"Detail": df}
    if "ANOMALY STATUS" in df.columns:
        sheets["Anomali Prioritas"] = df[df["ANOMALY STATUS"].isin(
            ["Prioritas Tinggi", "Potensi Anomali"]
        )].sort_values("ANOMALY SCORE", ascending=False)
    else:
        sheets["Anomali Prioritas"] = df.head(0)

    _pc_cols = ["Cabang", "Jumlah_Barang", "Total_Waste", "Max_Waste_Harian",
                "Anomali_Prioritas", "Anomali_Potensi", "Anomali_Review"]
    if "NAMA RESTO" in df.columns:
        try:
            sheets["Per Cabang"] = (
                df.groupby("NAMA RESTO", dropna=False).agg(
                    Jumlah_Barang=("NAMA BARANG", "size"),
                    Total_Waste=("TOTAL", "sum"),
                    Max_Waste_Harian=("MAX", "max"),
                    Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                    Anomali_Potensi=("ANOMALY STATUS", lambda x: int((x == "Potensi Anomali").sum())),
                    Anomali_Review=("ANOMALY STATUS", lambda x: int((x == "Perlu Review").sum())),
                ).reset_index().rename(columns={"NAMA RESTO": "Cabang"})
                .sort_values("Anomali_Prioritas", ascending=False)
            )
        except Exception:  # kolom pendukung hilang → fallback kosong
            sheets["Per Cabang"] = pd.DataFrame(columns=_pc_cols)
    else:
        sheets["Per Cabang"] = pd.DataFrame(columns=_pc_cols)

    _ti_cols = ["Rank", "NAMA BARANG", "JENIS", "Total_Waste", "Max_Waste",
                "Cabang_Terpengaruh", "Anomali_Prioritas"]
    if "NAMA BARANG" in df.columns:
        try:
            top = (
                df.groupby(["NAMA BARANG", "JENIS"], dropna=False).agg(
                    Total_Waste=("TOTAL", "sum"),
                    Max_Waste=("MAX", "max"),
                    Cabang_Terpengaruh=("NAMA RESTO", "nunique"),
                    Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                ).reset_index().sort_values("Total_Waste", ascending=False).head(20)
            )
            top.insert(0, "Rank", range(1, len(top) + 1))
            sheets["Top Items"] = top
        except Exception:
            sheets["Top Items"] = pd.DataFrame(columns=_ti_cols)
    else:
        sheets["Top Items"] = pd.DataFrame(columns=_ti_cols)

    _pa_cols = ["KETERANGAN", "Total_Waste", "Jumlah_Barang",
                "Persentase", "Cumulative"]
    if "KETERANGAN" in df.columns:
        try:
            pareto = (
                df.groupby("KETERANGAN", dropna=False).agg(
                    Total_Waste=("TOTAL", "sum"),
                    Jumlah_Barang=("NAMA BARANG", "size"),
                ).reset_index().sort_values("Total_Waste", ascending=False)
            )
            grand = pareto["Total_Waste"].sum()
            if grand and grand > 0:
                pareto["Persentase"] = (pareto["Total_Waste"] / grand) * 100
                pareto["Cumulative"] = pareto["Persentase"].cumsum()
            else:
                pareto["Persentase"] = 0
                pareto["Cumulative"] = 0
            sheets["Pareto Alasan"] = pareto
        except Exception:
            sheets["Pareto Alasan"] = pd.DataFrame(columns=_pa_cols)
    else:
        sheets["Pareto Alasan"] = pd.DataFrame(columns=_pa_cols)
    return sheets


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
        self.sheets: dict[str, pd.DataFrame] = {}
        self.key_akhir: int = 31
        self.last_run_time: datetime | None = None
        self.log_lines: list[str] = []

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

    # ------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------
    def set_dataset(self, df: pd.DataFrame, summary: dict) -> None:
        """Dataset baru dari pipeline: simpan + reset filter + broadcast."""
        self.df = df
        self.summary = summary
        self.sheets = _build_derived_sheets(df)
        try:
            self.key_akhir = int(summary.get("key_akhir", 31))
        except (TypeError, ValueError):
            self.key_akhir = 31
        self.last_run_time = datetime.now()
        self.reset_filters()
        self.data_ready.emit()

    # ------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------
    def filtered_df(self) -> pd.DataFrame | None:
        """df hasil filter lengkap (search + dropdown + rentang hari)."""
        if self.df is None:
            return None
        return _apply_filters(
            self.df, self.active_filters,
            day_min=self.day_min, day_max=self.day_max,
            search=self.search,
        )

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
        self.filters_changed.emit()

    def set_day_range(self, day_min: int | None, day_max: int | None) -> None:
        self.day_min = day_min
        self.day_max = day_max
        self.filters_changed.emit()

    def set_search(self, text: str) -> None:
        self.search = text
        self.filters_changed.emit()

    def set_score_min(self, score: int) -> None:
        self.score_min = score
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
