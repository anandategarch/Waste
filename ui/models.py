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
             "% to BOM", "Rill % to BOM",
             # v2.9.0: kolom bukti hari (tab Hari Mencurigakan)
             "HARI TERSANGKA", "NILAI HARI TERSANGKA", "TIPIKAL CABANG LAIN",
             "N CABANG PEMBANDING", "RASIO VS CABANG LAIN",
             "SHARE HARI TERSANGKA", "Count Hari",
             # v2.10.0: bukti vs bulan lalu + tabel banding periode
             "NILAI BULAN LALU", "TIPIKAL BEBERAPA BULAN", "HARI AKTIF",
             "Total Waste", "Waste per Hari", "Perubahan %"}

# Kolom rasio (nilai 0..1) yang ditampilkan sebagai PERSEN — v2.8.1.
# '% to BOM' = waste dibanding penjualan kuantiti (BOM = qty terjual);
# nilai non-numerik seperti penanda 'Cek' (tak ada data penjualan)
# diteruskan apa adanya. MAX / BOM, TOTAL / BOM, MAX SHARE, LAST DAY
# SHARE ikut format persen supaya konsisten & terbaca (dulu '0,00').
PCT_COLS = frozenset({
    "% to BOM", "Rill % to BOM", "MAX / BOM", "TOTAL / BOM",
    "MAX SHARE", "LAST DAY SHARE",
    # v2.9.0: porsi hari tersangka dari total bulanan
    "SHARE HARI TERSANGKA",
})

# Kolom rasio "berapa kali lipat" (v2.9.0) — ditampilkan '404×' / '8,5×',
# BUKAN persen dan BUKAN angka mentah (0,0008 tidak terbaca manusia).
# v2.10.0: + RASIO VS BULAN LALU (bukti tanggal-sama bulan sebelumnya).
RATIO_X_COLS = frozenset({"RASIO VS CABANG LAIN", "RASIO VS BULAN LALU"})

# ============================================================
# v2.9.0 — KAMUS ISTILAH (tooltip judul kolom, semua tabel & detail)
# ============================================================
# Permintaan user: "buatkan tool tip biar aku mudah mencerna. Semua
# istilah ya bukan hanya S-1". Hover judul kolom tabel / label metrik
# pop-up detail → penjelasan Bahasa Indonesia awam. Satu sumber untuk
# semua view (Anomali, Hari Mencurigakan, Banding Periode).
COLUMN_TOOLTIPS = {
    # --- identitas ---
    "NAMA RESTO": "Kode & nama cabang/outlet yang mencatat data ini.",
    "NAMA BARANG": "Nama item barang.",
    "JENIS": "Jenis catatan: SUSUT, TRIAL, atau WASTE.",
    "KETERANGAN": "Alasan pencatatan (mis. Alat/Mesin, Cancel Nota, Over Stock).",
    "SATUAN": "Satuan item (PCS, KG, LTR, ...).",
    "SOURCE DATA": "Asal baris data (sheet sumber).",
    "Status2": "Kosong = tidak ada nilai sama sekali; Isi = ada nilainya.",
    # --- skor & status ---
    "ANOMALY SCORE": "Total poin dari 12 pemeriksaan (maks 19).\nMakin tinggi = makin layak diperiksa duluan.",
    "ANOMALY STATUS": "Kategori skor:\nPrioritas Tinggi (≥ 8) · Potensi Anomali (≥ 5) · Perlu Review (≥ 3) · Normal.",
    "ANOMALY REASONS": "Daftar pemeriksaan yang terpicu (dipisah '|').\nHover chip di pop-up detail untuk arti tiap sinyal.",
    "KATEGORI ANOMALI": "Lonjakan Ekstrem / Dominasi Non-Handling / Normal.",
    "RANGKING WASTE": "Peringkat item ini di antara cabang (Top 1-3 — total dan/atau % BOM).",
    # --- statistik harian ---
    "TOTAL": "Jumlah waste sebulan (hari 1-31 dijumlahkan).",
    "MAX": "Nilai waste terbesar dalam SATU hari.",
    "AVG": "Rata-rata per hari (TOTAL ÷ jumlah hari periode).",
    "AVG AKTIF": "Rata-rata hanya dari hari yang ADA wastenya (> 0) —\nhari kosong tidak menarik rata-rata turun.",
    "MEDIAN AKTIF": "Nilai tengah dari hari yang ada wastenya —\ntahan terhadap 1 hari ekstrem (lebih adil dari rata-rata).",
    "SECOND MAX": "Nilai terbesar KEDUA.",
    "HARI MAX": "Tanggal (1-31) nilai terbesar terjadi.",
    "Count Hari": "Banyaknya hari dengan waste > 0.",
    "NILAI HARI TERAKHIR": "Nilai waste di hari terakhir periode.",
    # --- rasio harian ---
    "MAX / AVG": "Berapa kali lipat nilai terbesar vs rata-rata (≥ 3× = lonjakan).",
    "MAX / AVG AKTIF": "Nilai terbesar vs rata-rata hari aktif (≥ 2,5× = mencurigakan).",
    "MAX / MEDIAN AKTIF": "Nilai terbesar vs nilai tengah (≥ 3× = mencurigakan).",
    "MAX / SECOND MAX": "Nilai terbesar vs terbesar kedua (≥ 3× = puncak menjulang sendirian).",
    "MAX SHARE": "Porsi nilai terbesar dari TOTAL sebulan (≥ 50% = waste terpusat di 1 hari).",
    "LAST DAY SHARE": "Porsi hari TERAKHIR dari total (≥ 70% = menumpuk di akhir bulan — cek input).",
    "SINGLE DAY": "YES = waste hanya terjadi 1 hari sebulan.",
    "SCALE SIGNAL": "YES = nilai ~10×/100×/1000× nilai tengah sendiri —\npola khas salah ketik digit tambahan (7 → 70 → 700).",
    # --- BOM (penjualan) ---
    "TOTAL BOM": "Qty PENJUALAN item sebulan (pembanding — bukan waste).\nBOM = penjualan kuantiti.",
    "% to BOM": "Waste vs penjualan. 5% = waste 5 dari 100 terjual.\n'Cek' = tidak ada data penjualan.",
    "Rill % to BOM": "Sama seperti % to BOM (versi tanpa penanda 'Cek').",
    "MAX / BOM": "Nilai terbesar SEHARI vs penjualan SEBULAN (≥ 25% = tinggi).",
    "TOTAL / BOM": "Total waste sebulan vs penjualan (≥ 50% = tinggi).",
    # --- peer (cabang lain) ---
    "PEER COUNT": "Banyak cabang lain yang juga mencatat item ini (pembanding).",
    "PEER MEDIAN TOTAL": "Nilai tengah TOTAL item ini di cabang lain.",
    "PEER MEDIAN MAX": "Nilai tengah puncak-harian item ini di cabang lain.",
    "TOTAL / PEER MEDIAN": "Total kita vs nilai tengah cabang lain (≥ 3× = jauh di atas).",
    "MAX / PEER MEDIAN MAX": "Puncak kita vs nilai tengah puncak cabang lain (≥ 2× = jauh di atas).",
    # --- hari tersangka (v2.9.0) ---
    "HARI TERSANGKA": "Tanggal (1-31) angka mencurigakan berada —\nhari dengan nilai terbesar baris ini.",
    "NILAI HARI TERSANGKA": "Nilai waste pada hari tersangka.",
    "TIPIKAL CABANG LAIN": "Nilai tengah item SAMA di hari SAMA pada cabang lain —\nangka wajarnya hari itu.",
    "N CABANG PEMBANDING": "Banyak cabang lain yang jadi pembanding di hari itu.",
    "RASIO VS CABANG LAIN": "Berapa kali lipat nilai kita vs cabang lain di hari yang sama.\n≥ 5× = mencurigakan.",
    "SHARE HARI TERSANGKA": "Porsi hari tersangka dari total bulanan (≥ 50% = terpusat).",
    "BUKTI HARI": "YES = ada ≥ 1 bukti kuat hari itu mencurigakan.\nLihat ALASAN HARI untuk rinciannya.",
    "ALASAN HARI": "Ringkasan bukti hari tersangka dalam satu kalimat.",
    # --- bukti vs bulan lalu (v2.10.0) ---
    "NILAI BULAN LALU": "Nilai item yang sama di cabang yang sama pada\nTANGGAL yang sama, bulan pembanding sebelumnya\n(jumlah semua alasan) — kebiasaan bulan lalu.",
    "RASIO VS BULAN LALU": "Berapa kali lipat nilai hari tersangka vs\ntanggal yang sama bulan lalu. ≥ 3× = jauh di atas\nkebiasaan bulan sebelumnya.",
    "TIPIKAL BEBERAPA BULAN": "Nilai tengah tanggal yang sama dari ≥ 2\nbulan pembanding (butuh beberapa file bulan lalu).",
    # --- banding periode ---
    "Hari Data": "Banyak hari berdata pada periode itu.",
    "Hari Aktif": "Banyak hari dengan waste > 0.",
    "Total_A": "Total periode A (run sekarang).",
    "Total_B": "Total periode B (pembanding).",
    "Delta": "Selisih (B − A).",
    "Delta %": "Perubahan relatif vs A.",
    # --- banding periode v2.10.0 (kuantiti multi-file) ---
    "Bulan Ini": "Nilai bulan berjalan (hasil run pipeline saat ini).",
    "Pembanding": "Nilai bulan pembanding yang dipilih (bulan lalu / tipikal).\nKosong = item tidak ada di bulan pembanding.",
    "Selisih": "Bulan ini dikurangi pembanding.\nMinus = turun, plus = naik.",
    "Perubahan %": "Naik/turun relatif vs pembanding (mis. +28% = 1,28×).\nKosong = pembandingnya 0/tidak ada.",
    "Metrik": "Nama ukuran yang dibandingkan.",
}


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


def fmt_ratio_x(value, ndigits: int = 1) -> str:
    """Format rasio "berapa kali lipat" gaya Indonesia (v2.9.0).

    Contoh: fmt_ratio_x(404.0) → '404×'; fmt_ratio_x(8.5) → '8,5×'.
    NaN/None → '' (konvensi sama dengan fmt_cell/fmt_pct).
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
    if f >= 10:
        return f"{f:,.0f}".replace(",", ".") + "×"
    return f"{f:,.{ndigits}f}".replace(".", ",") + "×"


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
        # v2.9.0 (perf): cache teks DisplayRole per (row, col) — fmt_cell/
        # fmt_pct dibangun SEKALI lalu dipakai ulang oleh auto-fit kolom,
        # pengukuran tinggi baris, dan paint (diukur: 30-40% waktu render
        # tabel habis di pemformatan string yang sama berulang-ulang).
        # Di-invalidasi set_dataframe & sort (baris berganti isi).
        self._texts: dict[tuple[int, int], str] = {}

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------
    def set_dataframe(self, df: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self._texts = {}
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
                    # v2.9.0: kamus istilah — hover judul kolom menjelaskan
                    # artinya Bahasa awam (permintaan user: tooltip SEMUA
                    # istilah, bukan cuma S-1). Kolom tanpa kamus → nama.
                    return COLUMN_TOOLTIPS.get(name, name)
        if role == Qt.FontRole and orientation == Qt.Horizontal:
            f = QFont()
            f.setBold(True)
            return f
        return None

    def _cell_text(self, row: int, col: int, col_name: str, value) -> str:
        """Teks tampilan satu sel — memo per (row, col) (v2.9.0 perf)."""
        key = (row, col)
        text = self._texts.get(key)
        if text is None:
            if col_name in PCT_COLS:
                text = fmt_pct(value)
            elif col_name in RATIO_X_COLS:
                text = fmt_ratio_x(value)
            else:
                text = fmt_cell(value, self._ndigits)
            self._texts[key] = text
        return text

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._df)):
            return None
        row, col = index.row(), index.column()
        col_name = self._df.columns[col]
        value = self._df.iat[row, col]

        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._cell_text(row, col, col_name, value)
        if role == Qt.ToolTipRole:
            text = self._cell_text(row, col, col_name, value)
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
            self._texts = {}  # urutan baris berganti → cache teks basi
            self.endResetModel()
        except Exception:
            # V26-L3: sort gagal (dtype aneh dsb.) — jangan senyap total,
            # tinggalkan jejak debug utk logs/waste_anomaly.log.
            _LOG.debug("sort kolom '%s' gagal — tabel dibiarkan tak tersort",
                       name, exc_info=True)
            return
