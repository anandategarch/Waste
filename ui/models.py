"""models.py — QAbstractTableModel di atas pandas DataFrame (v2.6.0).

Pengganti ttk.Treeview + _populate_tree (cap 500 baris + _format_cell float
mentah). Keunggulan model/view Qt:
- TANPA cap baris: 25.901 baris di-render virtualized (semua anomali terlihat)
- Sort numeric-aware di DataFrame sumber (NaN di akhir) — klik header
- Pewarnaan baris per severity (BackgroundRole)
- Tooltip sel = teks penuh (kolom panjang tidak pernah 'hilang')
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from .shared import fmt_id
from .theme import STATUS_COLORS

# Nama logger mengikuti konvensi app ("waste_anomaly.ui" — lihat
# logging_setup.py dan app.py::_qt_excepthook).
_LOG = logging.getLogger("waste_anomaly.ui")

_NUM_COLS = {"ANOMALY SCORE", "TOTAL", "MAX", "AVG", "HARI MAX", "RANK",
             "Rank", "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
             "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX", "MAX / BOM",
             "TOTAL / BOM", "MAX SHARE", "LAST DAY SHARE", "TopTotal",
             "Total_Waste", "Max_Waste", "Persentase", "Cumulative",
             "Jumlah_Barang", "Total_A", "Total_B", "Delta", "Delta %",
             "Waste per Hari", "Hari Aktif",
             "% to BOM", "Rill % to BOM"}

# Kolom rasio (nilai 0..1) yang ditampilkan sebagai PERSEN — v2.8.1.
# '% to BOM' = waste dibanding penjualan kuantiti (BOM = qty terjual);
# nilai non-numerik seperti penanda 'Cek' (tak ada data penjualan)
# diteruskan apa adanya. MAX / BOM, TOTAL / BOM, MAX SHARE, LAST DAY
# SHARE ikut format persen supaya konsisten & terbaca (dulu '0,00').
PCT_COLS = frozenset({
    "% to BOM", "Rill % to BOM", "MAX / BOM", "TOTAL / BOM",
    "MAX SHARE", "LAST DAY SHARE",
})


def fmt_cell(value, ndigits: int = 2) -> str:
    """Format sel untuk tampilan — konvensi Indonesia (IN-L1).

    Angka float dengan pecahan → fmt_id(x, ndigits); integer → fmt_id(x, 0);
    NaN/None/pd.NA/NaT → ''; teks → str apa adanya.

    v2.7.0 (V26-M1/L2): integer/float numpy (np.int64, np.float32, ...) kini
    terformat seperti int/float python (np.int64 sebelumnya lolos ke str()
    tanpa pemisah ribuan + rata kiri). pd.NA/NaT dicek DULU —
    ``pd.NA != pd.NA`` menghasilkan pd.NA (truthy-ambiguous), bukan False.
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return fmt_id(int(value), 0)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if f == int(f) and abs(f) < 1e15:
            return fmt_id(f, 0)
        return fmt_id(f, ndigits)
    return str(value)


def fmt_pct(value, ndigits: int = 2) -> str:
    """Format rasio 0..1 sebagai persen gaya Indonesia (v2.8.1).

    Contoh: fmt_pct(0.01335) → '1,34%'; fmt_pct(0.000914) → '0,09%'.
    Penanda non-numerik ('Cek' = tak ada data penjualan/BOM) diteruskan
    apa adanya; NaN/None → '' (konvensi sama dengan fmt_cell).
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    s = f"{f * 100:,.{ndigits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + "%"


class PandasTableModel(QAbstractTableModel):
    """Model tabel generik untuk DataFrame (sort + severity tint + tooltip)."""

    def __init__(self, df: pd.DataFrame | None = None, parent=None) -> None:
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._ndigits = 2

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------
    def set_dataframe(self, df: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._df

    def record(self, row: int) -> pd.Series | None:
        """Baris penuh (pd.Series) pada posisi tampilan saat ini."""
        if 0 <= row < len(self._df):
            return self._df.iloc[row]
        return None

    # ------------------------------------------------------------
    # Qt model contract
    # ------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._df.columns):
                name = str(self._df.columns[section])
                if role == Qt.DisplayRole:
                    return name
                if role == Qt.ToolTipRole:
                    return name  # header sempit → nama kolom penuh di tooltip
        if role == Qt.FontRole and orientation == Qt.Horizontal:
            f = QFont()
            f.setBold(True)
            return f
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._df)):
            return None
        row, col = index.row(), index.column()
        col_name = self._df.columns[col]
        value = self._df.iat[row, col]

        if role in (Qt.DisplayRole, Qt.EditRole):
            if col_name in PCT_COLS:
                return fmt_pct(value)
            return fmt_cell(value, self._ndigits)
        if role == Qt.ToolTipRole:
            text = (fmt_pct(value) if col_name in PCT_COLS
                    else fmt_cell(value, self._ndigits))
            return text if len(str(text)) > 18 else None
        if role == Qt.TextAlignmentRole:
            # V26-M1: numpy int/float juga rata kanan (np.int64 dulunya
            # lolos ke rata kiri karena bukan subclass int/float python).
            if col_name in _NUM_COLS or isinstance(
                    value, (int, float, np.integer, np.floating)):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole:
            return self._row_tint(row)
        if role == Qt.FontRole and col_name == "ANOMALY SCORE":
            f = QFont()
            f.setBold(True)
            return f
        return None

    def _row_tint(self, row: int) -> QColor | None:
        """Tint baris sesuai ANOMALY STATUS (bila kolom ada)."""
        if "ANOMALY STATUS" in self._df.columns:
            status = str(self._df.iat[row, self._df.columns.get_loc("ANOMALY STATUS")])
            tint = STATUS_COLORS.get(status, (None, None))[1]
            if tint:
                return QColor(tint)
        return None

    # ------------------------------------------------------------
    # SORT — numeric-aware pada df sumber (semantik _sort_df_for_treeview)
    # ------------------------------------------------------------
    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        if column < 0 or column >= len(self._df.columns):
            return
        name = self._df.columns[column]
        ascending = order == Qt.AscendingOrder
        try:
            col = self._df[name]
            numeric = pd.to_numeric(col, errors="coerce")
            if numeric.notna().sum() > 0:
                key = numeric
            else:
                key = col.astype(str).str.lower()
            self.beginResetModel()
            self._df = self._df.assign(_k=key).sort_values(
                "_k", ascending=ascending, na_position="last"
            ).drop(columns="_k")
            self.endResetModel()
        except Exception:
            # V26-L3: sort gagal (dtype aneh dsb.) — jangan senyap total,
            # tinggalkan jejak debug utk logs/waste_anomaly.log.
            _LOG.debug("sort kolom '%s' gagal — tabel dibiarkan tak tersort",
                       name, exc_info=True)
            return
