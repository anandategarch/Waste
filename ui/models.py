"""models.py — QAbstractTableModel di atas pandas DataFrame (v2.6.0).

Pengganti ttk.Treeview + _populate_tree (cap 500 baris + _format_cell float
mentah). Keunggulan model/view Qt:
- TANPA cap baris: 25.901 baris di-render virtualized (semua anomali terlihat)
- Sort numeric-aware di DataFrame sumber (NaN di akhir) — klik header
- Pewarnaan baris per severity (BackgroundRole)
- Tooltip sel = teks penuh (kolom panjang tidak pernah 'hilang')
"""
from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from .shared import fmt_id
from .theme import STATUS_COLORS

_NUM_COLS = {"ANOMALY SCORE", "TOTAL", "MAX", "AVG", "HARI MAX", "RANK",
             "Rank", "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
             "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX", "MAX / BOM",
             "TOTAL / BOM", "MAX SHARE", "LAST DAY SHARE", "TopTotal",
             "Total_Waste", "Max_Waste", "Persentase", "Cumulative",
             "Jumlah_Barang", "Total_A", "Total_B", "Delta", "Delta %",
             "Waste per Hari", "Hari Aktif"}


def fmt_cell(value, ndigits: int = 2) -> str:
    """Format sel untuk tampilan — konvensi Indonesia (IN-L1).

    Angka float dengan pecahan → fmt_id(x, ndigits); integer → fmt_id(x, 0);
    NaN/None → ''; teks → str apa adanya.
    """
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return fmt_id(value, 0)
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return fmt_id(value, 0)
        return fmt_id(value, ndigits)
    return str(value)


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
            return fmt_cell(value, self._ndigits)
        if role == Qt.ToolTipRole:
            text = fmt_cell(value, self._ndigits)
            return text if len(str(text)) > 18 else None
        if role == Qt.TextAlignmentRole:
            if col_name in _NUM_COLS or isinstance(value, (int, float)):
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
            return
