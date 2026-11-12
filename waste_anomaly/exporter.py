"""
exporter.py — penulis output Excel multi-sheet dengan formatting.

Sheet:
  1. Detail            — semua baris, kolom mengikuti Final order M code
  2. Anomali Prioritas — hanya Prioritas Tinggi + Potensi Anomali
  3. Per Cabang        — ringkasan per NAMA RESTO
  4. Top Items         — top 20 NAMA BARANG by TOTAL
  5. Pareto Alasan     — group by KETERANGAN, sum TOTAL, cumulative %
  6. Log Run           — timestamp, parameter, summary stats
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

try:  # fast-path styling (lihat _shared_body_style) — API internal openpyxl,
    # stabil sejak 2.6, di-guard dengan fallback descriptor per-cell.
    from openpyxl.cell import Cell as _Cell
    from openpyxl.styles.cell_style import StyleArray as _StyleArray
except Exception:  # pragma: no cover
    _Cell = None
    _StyleArray = None


# ============================================================
# STYLE CONSTANTS — object dibuat SEKALI di module level dan di-share ke
# semua cell (L15: alokasi Alignment/Font per-cell pada loop ~26k x ~50 kolom
# = ~1.3M objek adalah hotspot penulisan Detail sheet).
# ============================================================

HEADER_FILL = PatternFill(start_color="172033", end_color="172033", fill_type="solid")
HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
TITLE_FONT = Font(name="Segoe UI", size=14, bold=True, color="172033")
BODY_FONT = Font(name="Segoe UI", size=10, color="1F2937")
BODY_ALIGN = Alignment(vertical="top", wrap_text=False)
MONO_FONT = Font(name="Consolas", size=10, color="1F2937")
EMPTY_NOTE_FONT = Font(name="Segoe UI", size=10, italic=True, color="6B7280")

STATUS_FILLS = {
    "Prioritas Tinggi": PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid"),
    "Potensi Anomali": PatternFill(start_color="EA580C", end_color="EA580C", fill_type="solid"),
    "Perlu Review": PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid"),
    "Normal": PatternFill(start_color="16A34A", end_color="16A34A", fill_type="solid"),
}
STATUS_FONT = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
STATUS_ALIGN = Alignment(horizontal="center", vertical="center")

# Kolom Persentase/Cumulative (sheet "Pareto Alasan") ditampilkan dengan format
# "%". Nilainya sudah skala 0-100, jadi pakai suffix literal — BUKAN format
# Excel '0%' yang mengalikan 100 saat display.
PCT_FORMAT_COLUMNS = ("Persentase", "Cumulative")
PCT_NUMBER_FORMAT = '0.0"%"'

THIN_BORDER = Border(
    left=Side(style="thin", color="E5E7EB"),
    right=Side(style="thin", color="E5E7EB"),
    top=Side(style="thin", color="E5E7EB"),
    bottom=Side(style="thin", color="E5E7EB"),
)

# ============================================================
# STREAMING MODE (F10 v2.4.0) — anti OOM untuk data besar
# ============================================================
# Audit terukur: openpyxl mode normal memakan ±947 MB pada 30k baris × 46
# kolom, 1.56 GB pada 50k, dan proses di-OOM-KILL pada 100k (exit 137).
# Mode streaming (write_only=True) menulis baris demi baris ke disk — memori
# konstan berapa pun ukurannya.
#
# Trade-off yang disengaja & terdokumentasi: body cell pada mode streaming
# TIDAK diberi border/font grid (hanya header, kolom status berwarna, format
# persentase, freeze, auto-filter, lebar kolom). Data ≤ threshold tetap pakai
# mode normal dengan formatting penuh — dataset user saat ini 25.9k baris.
STREAMING_THRESHOLD_DEFAULT = 35_000


# ============================================================
# GROUPED LAYOUT SHEET — SAMPEL TAMPILAN BARU (v2.19.2)
# ============================================================
# Sheet tambahan "Anomali Grup" mengikuti sampel user: SATU BARIS per
# pasangan (JENIS × NAMA BARANG × NAMA RESTO), urut menurut (JENIS, NAMA
# BARANG, NAMA RESTO), dgn BARIS KOSONG pemisah antar grup (JENIS, NAMA
# BARANG). 11 kolom persis sampel:
#   JENIS · NAMA BARANG · NAMA RESTO · SOURCE DATA GABUNGAN · [TOTAL] ·
#   [% to BOM] · TOTAL BULAN LALU & % Selisih · Selisih Bulan Lalu ·
#   PERUBAHAN · ANOMALY STATUS · PROFIL
#
# DataFrame grup dibangun pemanggil (ui/workers.py via ui.grouping
# .group_anomali_display) lalu diteruskan ke export_to_excel lewat param
# ``grouped_layout_df``. Engine tetap Qt-free (grouping pure-pandas; ui
# memanggil & meneruskan hasilnya). Kolom internal (__SRC_ROW/__FPS/
# __SRC_ROWS) dibuang sebelum tulis.

# Nama kolom grup (string biasa — engine tak impor ui.grouping; pemanggil
# membangun df dgn nama ini). Didefinisikan di awal supaya _GROUPED_COLS
# di bawah tak dependensi impor silang.
SRC_GAB_COL_NAME = "SOURCE DATA GABUNGAN"
LASTMONTH_COMBINED_COL_NAME = "TOTAL BULAN LALU & % Selisih"
SELISIH_COL_NAME = "Selisih Bulan Lalu"

_GROUPED_COLS = [
    "JENIS", "NAMA BARANG", "NAMA RESTO", SRC_GAB_COL_NAME,
    "TOTAL", "% to BOM",
    LASTMONTH_COMBINED_COL_NAME, SELISIH_COL_NAME, "PERUBAHAN",
    "ANOMALY STATUS", "PROFIL",
]
_GROUPED_ALIASES = {"TOTAL": "[TOTAL]", "% to BOM": "[% to BOM]"}
# Format angka: TOTAL/Selisih pakai pemisah ribuan; % to BOM skala 0-1 → 0%.
_GROUPED_NUMFMT_INT = '#,##0;;"-"'
_GROUPED_NUMFMT_PCT = '0%'


def _fmt_id_num(value, decimals: int = 0) -> str:
    """Format angka gaya Indonesia: ribuan '.', desimal ','.

    Replika minimal ui/shared.py:fmt_id (engine tak boleh impor ui).
    None/NaN → ''.
    """
    if value is None:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    s = f"{f:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_combined_lastmonth(value, delta_pct) -> str:
    """Format kolom 'TOTAL BULAN LALU & % Selisih' — sampel: '1.969,1 (-30%)'.

    Replika ui/models.py:fmt_lastmonth_combined (engine tak boleh impor ui).
    value      = total bulan lalu (numerik; NaN/None → '' — grup BARU).
    delta_pct  = PERUBAHAN % skala 0-100 (NaN → tanpa kurung persen).
    """
    import math
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:
        return ""
    base = _fmt_id_num(f, 1)
    if delta_pct is None:
        return base
    try:
        d = float(delta_pct)
    except (TypeError, ValueError):
        return base
    if d != d:
        return base
    if d == 0:
        return f"{base} (0%)"
    sign = "+" if d > 0 else "-"
    return f"{base} ({sign}{abs(d):.0f}%)"



# ============================================================
# MAIN ENTRY
# ============================================================

def export_to_excel(
    df: pd.DataFrame,
    output_path: str | os.PathLike,
    config: dict,
    key_akhir: int,
    log_lines: list[str],
    extra_sheets: dict[str, pd.DataFrame] | None = None,
    grouped_layout_df: pd.DataFrame | None = None,
) -> dict:
    """Tulis multi-sheet xlsx. Return summary dict.

    Return contract (v2.3.1):
      - sukses: ``{"success": True, "output_path": <str>, ...statistik}``
      - gagal  : ``{"success": False, "error": <pesan ramah>, "output_path": <str>}``
        Contoh: file output terkunci (sedang dibuka di Excel, khas Windows) →
        "File output sedang dibuka di Excel — tutup dulu lalu ulangi".
    Akses kolom opsional (ANOMALY STATUS, ANOMALY SCORE, NAMA RESTO, dst.)
    di-guard — sheet terkait di-skip/dikosongkan secara graceful (H8-c).

    v2.5.0: ``extra_sheets`` (opsional) = dict nama sheet → DataFrame;
    ditulis SETELAH 'Pareto Alasan' dan SEBELUM 'Log Run' (dipakai UI untuk
    sheet analisa baru: Waste per Hari, Alasan x Hari, Money View, Data
    Quality). Sheet kosong/None di-skip; nama didedupe otomatis.
    v2.19.2: ``grouped_layout_df`` (opsional) = DataFrame grup hasil
    group_anomali_display; ditulis sbg sheet 'Anomali Grup' SETELAH
    'Anomali Prioritas' & SEBELUM 'Per Cabang'. Layout SAMPEL TAMPILAN
    BARU: grup per NAMA BARANG + baris kosong pemisah (lihat
    _write_grouped_layout_sheet). None/kosong → di-skip graceful.
    """
    output_path = Path(output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {
            "success": False,
            "error": f"Tidak bisa membuat folder output '{output_path.parent}' — cek permission",
            "output_path": str(output_path),
        }

    # v2.18.0 audit (F-3): kolom internal __SRC_ROW (mapping baris fisik
    # utk edit pop-up, dipasang ensure_rekap_header) TIDAK boleh bocor ke
    # laporan Excel — pengguna melihat kolom teknis yang tak diminta di
    # sheet Detail/Anomali. Drop dari df utama & tiap extra sheet (kolom
    # internal tetap utuh di df in-memory pemanggil — ini salinan view).
    # v2.19.2 — __FPS & __SRC_ROWS (kolom internal grouping) juga dibuang.
    from .rekap_import import SRC_ROW_COL
    _INTERNAL_DROP = [SRC_ROW_COL, "__FPS", "__SRC_ROWS"]
    drop_main = [c for c in _INTERNAL_DROP if c in df.columns]
    if drop_main:
        df = df.drop(columns=drop_main)
    if extra_sheets:
        extra_sheets = {
            name: (ex_df.drop(columns=[c for c in _INTERNAL_DROP
                                       if getattr(ex_df, "columns", None)
                                       is not None and c in ex_df.columns])
                   if ex_df is not None and getattr(ex_df, "columns", None)
                   is not None else ex_df)
            for name, ex_df in extra_sheets.items()
        }
    # v2.19.2 — grouped_layout_df: buang kolom internal sebelum tulis.
    if (grouped_layout_df is not None
            and getattr(grouped_layout_df, "columns", None) is not None):
        g_drop = [c for c in _INTERNAL_DROP if c in grouped_layout_df.columns]
        if g_drop:
            grouped_layout_df = grouped_layout_df.drop(columns=g_drop)

    # F10 (v2.4.0): pilih mode — normal (formatting penuh) vs streaming
    # (memori konstan untuk data besar). Threshold bisa di-override via
    # config["output"]["streaming_threshold"].
    try:
        threshold = int(config.get("output", {}).get(
            "streaming_threshold", STREAMING_THRESHOLD_DEFAULT))
    except (TypeError, ValueError):
        threshold = STREAMING_THRESHOLD_DEFAULT
    use_streaming = len(df) > max(0, threshold)

    try:
        if use_streaming:
            wb = Workbook(write_only=True)  # tidak ada default sheet
            _write = _write_sheet_streaming
        else:
            wb = Workbook()
            wb.remove(wb.active)  # hapus default sheet
            _write = _write_sheet

        sheet_cfg = config.get("output", {})
        status_col = "ANOMALY STATUS"
        has_status = status_col in df.columns

        # ---- 1. Detail ----
        detail_name = sheet_cfg.get("detail_sheet", "Detail")
        _write(wb, detail_name, df, freeze="A2", status_col=status_col if has_status else None)

        # ---- 2. Anomali Prioritas ---- (H8-c: guard kolom status/score)
        anomali_name = sheet_cfg.get("anomali_sheet", "Anomali Prioritas")
        if has_status:
            df_anomali = df[df[status_col].isin(["Prioritas Tinggi", "Potensi Anomali"])]
            if not df_anomali.empty and "ANOMALY SCORE" in df_anomali.columns:
                df_anomali = df_anomali.sort_values("ANOMALY SCORE", ascending=False)
        else:
            df_anomali = df.iloc[0:0]
        _write(wb, anomali_name, df_anomali, freeze="A2", status_col=status_col if has_status else None)

        # ---- 2b. Anomali Grup (layout SAMPEL TAMPILAN BARU v2.19.2) ----
        # Satu baris per (JENIS×NAMA BARANG×NAMA RESTO), urut, baris KOSONG
        # pemisah antar grup (JENIS, NAMA BARANG). Dipakai utk tampilan ringkas
        # per item seperti sampel user. Di-skip bila grouped_layout_df tak
        # diberikan / kosong / streaming mode (mode streaming tak mendukung
        # formatter per-cell — fitur ini ditunda di data ekstrem).
        if (not use_streaming and grouped_layout_df is not None
                and not grouped_layout_df.empty):
            grouped_name = sheet_cfg.get("grouped_sheet", "Anomali Grup")
            try:
                _write_grouped_layout_sheet(
                    wb, grouped_name, grouped_layout_df,
                    status_col=status_col if has_status else None)
            except Exception:  # noqa: BLE001 — sheet opsional best-effort
                pass

        # ---- 3. Per Cabang ----
        per_cabang_name = sheet_cfg.get("per_cabang_sheet", "Per Cabang")
        df_cabang = _build_per_cabang(df)
        _write(wb, per_cabang_name, df_cabang, freeze="A2")

        # ---- 4. Top Items ----
        top_items_name = sheet_cfg.get("top_items_sheet", "Top Items")
        df_top = _build_top_items(df)
        _write(wb, top_items_name, df_top, freeze="A2")

        # ---- 5. Pareto Alasan ----
        pareto_name = sheet_cfg.get("pareto_sheet", "Pareto Alasan")
        df_pareto = _build_pareto(df)
        _write(wb, pareto_name, df_pareto, freeze="A2")

        # ---- 5b. Extra sheets analisa (v2.5.0) ----
        # Urutan insert: setelah ringkasan turunan, sebelum Log Run. Nama
        # sheet didedupe oleh _write (via _dedupe_sheet_name) sehingga tidak
        # bentrok bila user memakai nama yang sudah ada.
        n_extra = 0
        for sheet_name, extra_df in (extra_sheets or {}).items():
            if extra_df is None or getattr(extra_df, "empty", False):
                continue
            _write(wb, str(sheet_name), extra_df, freeze="A2")
            n_extra += 1

        # ---- 6. Log Run ----
        log_name = sheet_cfg.get("log_sheet", "Log Run")
        df_log = _build_log(df, key_akhir, log_lines)
        _write(wb, log_name, df_log, freeze="A2")

        # Save — H8: file yang sedang dibuka di Excel terkunci (PermissionError di
        # Windows); kembalikan pesan ramah, jangan biarkan traceback ke caller.
        # F10: MemoryError pada data ekstrem → pesan actionable (mode streaming
        # sudah meminimalkan risiko ini, guard terakhir tetap disediakan).
        try:
            wb.save(output_path)
        except PermissionError:
            return {
                "success": False,
                "error": "File output sedang dibuka di Excel — tutup dulu lalu ulangi",
                "output_path": str(output_path),
            }
        except MemoryError:
            return {
                "success": False,
                "error": ("Memori tidak cukup saat menulis Excel. Tutup aplikasi lain "
                          "lalu ulangi, atau pecah data menjadi beberapa bagian."),
                "output_path": str(output_path),
            }
    except MemoryError:
        return {
            "success": False,
            "error": ("Memori tidak cukup saat menyiapkan laporan. Tutup aplikasi lain "
                      "lalu ulangi, atau pecah data menjadi beberapa bagian."),
            "output_path": str(output_path),
        }

    # Build summary return (H8-c: hitungan status hanya bila kolomnya ada)
    total_rows = len(df)
    anomali_count = len(df_anomali)
    if has_status:
        prioritas_count = int((df[status_col] == "Prioritas Tinggi").sum())
        potensi_count = int((df[status_col] == "Potensi Anomali").sum())
        review_count = int((df[status_col] == "Perlu Review").sum())
        normal_count = int((df[status_col] == "Normal").sum())
    else:
        prioritas_count = potensi_count = review_count = normal_count = 0

    # Streaming flag masuk summary supaya UI/log bisa menampilkan mode yang dipakai
    return {
        "success": True,
        "output_path": str(output_path),
        "streaming": use_streaming,
        "total_rows": total_rows,
        "anomali_count": anomali_count,
        "prioritas_count": prioritas_count,
        "potensi_count": potensi_count,
        "review_count": review_count,
        "normal_count": normal_count,
        "cabang_count": int(df["NAMA RESTO"].nunique()) if "NAMA RESTO" in df.columns else 0,
        "item_count": int(df["NAMA BARANG"].nunique()) if "NAMA BARANG" in df.columns else 0,
        "extra_sheets_count": n_extra,
    }


# ============================================================
# SHEET WRITER — STREAMING MODE (F10 v2.4.0)
# ============================================================

def _dedupe_sheet_name(sheet_name: str, existing: list[str]) -> str:
    """Truncate 31 char + dedupe — dipakai kedua mode writer."""
    sheet_name = sheet_name[:31]
    if sheet_name not in existing:
        return sheet_name
    base = sheet_name[:27]  # sisakan ruang suffix " (n)" (27 + 4 = 31)
    i = 2
    while f"{base} ({i})" in existing:
        i += 1
    return f"{base} ({i})"


def _write_sheet_streaming(
    wb: Workbook,
    sheet_name: str,
    df: pd.DataFrame,
    freeze: str | None = "A2",
    status_col: str | None = None,
):
    """Tulis DataFrame ke sheet write-only — memori KONSTAN (F10 v2.4.0).

    Sheet dibuat dengan workbook write_only=True: baris diserialisasi ke disk
    saat di-append, tidak ditahan di RAM (mode normal: ~950 MB pada 30k baris;
    mode ini: puluhan MB berapa pun jumlah barisnya).

    Yang TETAP dipertahankan: header styled, kolom status berwarna, format
    persentase, freeze panes, auto-filter, lebar kolom, tinggi header.
    Yang disederhanakan (trade-off terdokumentasi): body cell tanpa grid
    border/font per-cell — data ≤ threshold tetap pakai _write_sheet penuh.
    """
    sheet_name = _dedupe_sheet_name(sheet_name, wb.sheetnames)
    ws = wb.create_sheet(title=sheet_name)

    if df.empty:
        cell = WriteOnlyCell(ws, value=f"(Tidak ada data untuk sheet '{sheet_name}')")
        cell.font = EMPTY_NOTE_FONT
        ws.append([cell])
        return

    cols = list(df.columns)
    if status_col is not None and status_col not in cols:
        status_col = None
    status_idx = cols.index(status_col) if status_col is not None else None
    pct_idx_set = {i for i, c in enumerate(cols) if c in PCT_FORMAT_COLUMNS}

    # --- Dimensi harus di-set SEBELUM baris (kontrak write-only openpyxl) ---
    for c_idx, col_name in enumerate(cols, start=1):
        max_len = len(str(col_name))
        sample = df[col_name].dropna().astype(str).head(100).tolist()
        if sample:
            sample_max = max(len(s) for s in sample)
            max_len = max(max_len, min(sample_max, 60))
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max_len + 2, 40)
    ws.row_dimensions[1].height = 28
    if freeze:
        ws.freeze_panes = freeze

    # --- Header (styled, hanya len(cols) cell) ---
    header_cells = []
    for c in cols:
        hc = WriteOnlyCell(ws, value=str(c))
        # M-1: header dari workbook user juga bisa berawalan '='
        if _is_dangerous_text(hc.value):
            hc.data_type = "s"
        hc.fill = HEADER_FILL
        hc.font = HEADER_FONT
        hc.alignment = HEADER_ALIGN
        hc.border = THIN_BORDER
        header_cells.append(hc)
    ws.append(header_cells)

    # --- Body: nilai plain (append cepat); hanya status & pct yang di-style ---
    col_values = [_column_cell_values(df[c]) for c in cols]
    for row in zip(*col_values):
        if status_idx is not None:
            v = row[status_idx]
            fill = STATUS_FILLS.get(v) if isinstance(v, str) else None
        else:
            fill = None
        cells = []
        for i, v in enumerate(row):
            if fill is not None and i == status_idx:
                sc = WriteOnlyCell(ws, value=v)
                sc.fill = fill
                sc.font = STATUS_FONT
                sc.alignment = STATUS_ALIGN
                cells.append(sc)
            elif i in pct_idx_set:
                pc = WriteOnlyCell(ws, value=v)
                pc.number_format = PCT_NUMBER_FORMAT
                cells.append(pc)
            elif _is_dangerous_text(v):  # M-1: anti formula injection
                cells.append(_force_text_cell(ws, v))
            else:
                cells.append(v)  # nilai plain — tercepat, tetap ter-format angka default
        ws.append(cells)

    # Auto filter (row count diketahui: len(df) + header)
    last_col = get_column_letter(len(cols))
    ws.auto_filter.ref = f"A1:{last_col}{len(df) + 1}"


# ============================================================
# SHEET WRITER (LOW LEVEL)
# ============================================================

def _shared_body_style(ws):
    """Bangun StyleArray untuk style body via satu reference cell (detached).

    Assignment descriptor per-cell (font/border/alignment) untuk sheet Detail
    25.9k baris x 94 kolom memakan ~100 detik (Serialisable.__eq__ dipanggil
    per assignment). Copy StyleArray per cell ~1 µs → kira-kira 30x lebih
    cepat. Return None bila fast path tidak tersedia — caller fallback ke
    descriptor path biasa (output akhirnya identik).
    """
    if _Cell is None or _StyleArray is None:
        return None
    try:
        ref = _Cell(ws, row=1, column=1)  # detached — tidak masuk ke sheet
        ref.font = BODY_FONT
        ref.border = THIN_BORDER
        ref.alignment = BODY_ALIGN
        return _StyleArray(ref._style)
    except Exception:
        return None


def _to_cell_value(val):
    """NaN/NA -> None; numpy scalar -> python scalar; list/dict -> str.

    Setara logika konversi lama yang dulunya dijalankan per-cell di dalam
    loop body (plus guard np.bool_ yang dulu lolos apa adanya).
    """
    if val is None or val is pd.NA:
        return None
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val) if not np.isnan(val) else None
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (list, dict)):
        return str(val)
    return val


# v2.18.0 audit (M-1) — ANTI FORMULA INJECTION: openpyxl menginferensi
# data_type='f' (formula hidup) utk string berawalan '=' (dan Excel
# mengevaluasi '+', '-', '@', TAB/CR juga). Sumber = workbook user
# (nama barang/keterangan bisa ber-teks apa pun) → laporan & file serah
# terima FOLLOW UP bisa memuat formula hidup yang mengubah tampilan/
# memicu peringatan DDE saat dibuka. Perlindungan: paksa data_type='s'
# (STRING) — nilai round-trip PERSIS (tanpa prefiks apostrof yang
# mengubah data), Excel tidak mengevaluasi apa pun.
_FORMULA_TEXT_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _is_dangerous_text(val) -> bool:
    """String berawalan prefix formula Excel? (lihat _FORMULA_TEXT_PREFIXES)."""
    return isinstance(val, str) and val[:1] in _FORMULA_TEXT_PREFIXES


def _force_text_cell(ws, val):
    """WriteOnlyCell dgn data_type='s' — teks dipaksa STRING (mode
    streaming; nilai berbahaya TIDAK dievaluasi Excel sebagai formula)."""
    c = WriteOnlyCell(ws, value=val)
    c.data_type = "s"
    return c


def _force_text_row(ws, row: list) -> None:
    """Mode normal: append lalu paksa data_type='s' utk sel teks berbahaya
    (baris baru saja di-append — ws[ws.max_row])."""
    if any(_is_dangerous_text(v) for v in row):
        for cell in ws[ws.max_row]:
            if _is_dangerous_text(cell.value):
                cell.data_type = "s"


def _column_cell_values(series: pd.Series) -> list:
    """Konversi satu kolom DataFrame -> list python scalar siap openpyxl.

    Kolom float/integer dikonversi vectorized (NaN/NA -> None); kolom lain
    (object/datetime/bool) per-elemen via _to_cell_value. Jalan sekali per
    kolom, bukan sekali per cell.
    """
    dtype = series.dtype
    if pd.api.types.is_float_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
        return series.astype(object).where(series.notna(), None).tolist()
    return [_to_cell_value(v) for v in series.tolist()]


def _write_grouped_layout_sheet(
    wb: Workbook,
    sheet_name: str,
    df: pd.DataFrame,
    status_col: str | None = "ANOMALY STATUS",
):
    """Tulis sheet 'Anomali Grup' — layout SAMPEL TAMPILAN BARU (v2.19.2).

    Satu baris per (JENIS × NAMA BARANG × NAMA RESTO), urut menurut
    (JENIS, NAMA BARANG, NAMA RESTO), dgn BARIS KOSONG pemisah antar grup
    (JENIS, NAMA BARANG). 11 kolom sampel; [TOTAL]/Selisih dgn pemisah
    ribuan, [% to BOM] format persen, 'TOTAL BULAN LALU & % Selisih' sebagai
    teks 'nilai (±X%)' gaya Indonesia (replika fmt_lastmonth_combined).
    ANOMALY STATUS diberi warna status (sama sheet Anomali Prioritas).

    ``df`` = DataFrame grup hasil group_anomali_display (pemanggil membangun).
    Kolom internal (__SRC_ROW/__FPS/__SRC_ROWS) dibuang pemanggil sebelum
    memanggil (lihat export_to_excel). Bila kolom sampel tak ada di df,
    di-skip graceful (hanya kolom yg ada yg ditulis).
    """
    sheet_name = _dedupe_sheet_name(sheet_name, wb.sheetnames)
    ws = wb.create_sheet(title=sheet_name)

    if df is None or df.empty:
        ws["A1"] = f"(Tidak ada data untuk sheet '{sheet_name}')"
        ws["A1"].font = EMPTY_NOTE_FONT
        return

    # v2.19.2 — SELALU tulis 11 header sampel (meski kolom tak ada di df —
    # mis. tanpa baseline, kolom BULAN LALU/Selisih/PERUBAHAN tak dihasilkan
    # grouping → header tampil dgn sel kosong, persis struktur sampel user).
    # Mapping nama kolom sampel → nama kolom df (None = tak ada → sel kosong).
    cols_map: list[tuple[str, str | None]] = []
    for c in _GROUPED_COLS:
        cols_map.append((c, c if c in df.columns else None))
    headers = [_GROUPED_ALIASES.get(c, c) for c, _ in cols_map]
    # Indeks kolom sampel (posisi di header) utk number format + status color.
    status_idx = next((i for i, (c, _) in enumerate(cols_map)
                       if c == status_col), None) if status_col else None
    total_idx = next((i for i, (c, _) in enumerate(cols_map) if c == "TOTAL"), None)
    pct_idx = next((i for i, (c, _) in enumerate(cols_map) if c == "% to BOM"), None)
    selisih_idx = next((i for i, (c, _) in enumerate(cols_map)
                        if c == SELISIH_COL_NAME), None)
    combined_df_col = LASTMONTH_COMBINED_COL_NAME  # nama di df (bila ada)
    delta_col = "PERUBAHAN %"

    # Sort by (JENIS, NAMA BARANG, NAMA RESTO) — stable mergesort.
    sort_keys = [k for k in ("JENIS", "NAMA BARANG", "NAMA RESTO")
                 if k in df.columns]
    sdf = (df.sort_values(sort_keys, na_position="last", kind="mergesort")
           if sort_keys else df)

    # ---- Header (styled) ----
    ws.append(headers)
    for cell in ws[1]:
        if _is_dangerous_text(cell.value):
            cell.data_type = "s"
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 28

    # ---- Body: baris demi baris, sisipkan baris KOSONG antar grup ----
    n_body = 0
    first_row = True  # grup pertama tak dapat pemisah di depannya
    prev_key = None
    # Pre-compute per-column python lists utk akses cepat (iterrows lambat
    # pada 25k baris; pakai dict-of-lists). Kolom tak ada di df → list None.
    col_data: dict[str, list] = {}
    for c, src_col in cols_map:
        if src_col is not None and src_col in sdf.columns:
            col_data[src_col] = sdf[src_col].tolist()
    delta_series = (sdf[delta_col].tolist() if delta_col in sdf.columns
                    else [None] * len(sdf))
    jenis_series = (sdf["JENIS"].tolist() if "JENIS" in sdf.columns
                    else [None] * len(sdf))
    barang_series = (sdf["NAMA BARANG"].tolist() if "NAMA BARANG" in sdf.columns
                     else [None] * len(sdf))
    for i in range(len(sdf)):
        cur_key = (jenis_series[i], barang_series[i])
        if not first_row and cur_key != prev_key:
            # Baris KOSONG pemisah antar grup (JENIS, NAMA BARANG).
            ws.append([None] * len(headers))
            n_body += 1
        first_row = False
        prev_key = cur_key
        row_cells = []
        for c, src_col in cols_map:
            if src_col is None or src_col not in col_data:
                v = None
            else:
                v = col_data[src_col][i]
                if c == combined_df_col:
                    v = _fmt_combined_lastmonth(v, delta_series[i])
                else:
                    v = _to_cell_value(v)
            row_cells.append(v)
        ws.append(row_cells)
        _force_text_row(ws, row_cells)
        n_body += 1

    # ---- Styling body (style objects shared) + number formats + status ----
    body_style = _shared_body_style(ws)
    for row_cells in ws.iter_rows(min_row=2, max_row=n_body + 1):
        if body_style is not None:
            for cell in row_cells:
                cell._style = _StyleArray(body_style)
        else:  # pragma: no cover — fallback kompatibilitas
            for cell in row_cells:
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
                cell.alignment = BODY_ALIGN
        # Number formats (hanya sel numerik — sel teks/'Cek' tak terformat).
        if total_idx is not None:
            v = row_cells[total_idx].value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row_cells[total_idx].number_format = _GROUPED_NUMFMT_INT
        if selisih_idx is not None:
            v = row_cells[selisih_idx].value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row_cells[selisih_idx].number_format = _GROUPED_NUMFMT_INT
        if pct_idx is not None:
            v = row_cells[pct_idx].value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row_cells[pct_idx].number_format = _GROUPED_NUMFMT_PCT
        # Status coloring (ANOMALY STATUS).
        if status_idx is not None:
            v = row_cells[status_idx].value
            fill = STATUS_FILLS.get(v) if isinstance(v, str) else None
            if fill is not None:
                row_cells[status_idx].fill = fill
                row_cells[status_idx].font = STATUS_FONT
                row_cells[status_idx].alignment = STATUS_ALIGN

    # ---- Auto-width (sample 100 baris non-null per kolom df sumber) ----
    for c_idx, (c, src_col) in enumerate(cols_map, start=1):
        max_len = len(str(_GROUPED_ALIASES.get(c, c)))
        if src_col is not None and src_col in sdf.columns:
            sample = sdf[src_col].dropna().astype(str).head(100).tolist()
            if sample:
                sample_max = max(len(s) for s in sample)
                max_len = max(max_len, min(sample_max, 60))
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max_len + 2, 40)

    # Freeze + auto-filter (mencakup header + seluruh body termasuk pemisah;
    # saat filter aktif, baris pemisah kosong tak match → tersembunyi otomatis).
    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last_col}{n_body + 1}"


def _write_sheet(
    wb: Workbook,
    sheet_name: str,
    df: pd.DataFrame,
    freeze: str | None = "A2",
    status_col: str | None = None,
):
    """Tulis DataFrame ke sheet baru dengan header stylized + auto-width.

    Optimasi (L15): nilai ditulis bulk dengan ``ws.append()`` (bukan
    ``ws.cell()`` cell-by-cell yang ~110 detik untuk Detail sheet 25.9k baris),
    style objects di-share dari module level, dan konversi scalar dilakukan
    per-kolom. Conditional status coloring tetap HANYA pada kolom status —
    sama dengan perilaku lama, bukan satu baris penuh.
    """
    # Truncate ke 31 char (limit sheet Excel) + dedupe via helper bersama
    sheet_name = _dedupe_sheet_name(sheet_name, wb.sheetnames)

    ws = wb.create_sheet(title=sheet_name)

    if df.empty:
        ws["A1"] = f"(Tidak ada data untuk sheet '{sheet_name}')"
        ws["A1"].font = EMPTY_NOTE_FONT
        return

    cols = list(df.columns)
    # H8-c: kolom status tidak ada -> skip coloring secara graceful
    if status_col is not None and status_col not in cols:
        status_col = None
    status_idx = cols.index(status_col) if status_col is not None else None
    pct_col_idx = [i for i, c in enumerate(cols) if c in PCT_FORMAT_COLUMNS]

    # ---- Header: bulk append lalu style (hanya ~len(cols) cell) ----
    ws.append([str(c) for c in cols])
    for cell in ws[1]:
        # M-1: header dari workbook user juga bisa berawalan '='
        if _is_dangerous_text(cell.value):
            cell.data_type = "s"
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER

    # ---- Body: konversi per-kolom sekali, lalu append per baris ----
    col_values = [_column_cell_values(df[c]) for c in cols]
    n_rows = len(df)
    for row in zip(*col_values):
        ws.append(row)
        # M-1: anti formula injection — string berbahaya dipaksa STRING
        _force_text_row(ws, row)

    # ---- Styling body (style objects shared, tidak ada alokasi per-cell) ----
    # Fast path: style-array body dibangun sekali lalu di-copy per cell;
    # fallback: assignment descriptor per-cell (hasil file identik).
    status_vals = col_values[status_idx] if status_idx is not None else None
    body_style = _shared_body_style(ws)
    for row_cells in ws.iter_rows(min_row=2, max_row=n_rows + 1):
        if body_style is not None:
            for cell in row_cells:
                cell._style = _StyleArray(body_style)
        else:  # pragma: no cover — fallback kompatibilitas openpyxl lama
            for cell in row_cells:
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
                cell.alignment = BODY_ALIGN
        if pct_col_idx:
            for i in pct_col_idx:
                row_cells[i].number_format = PCT_NUMBER_FORMAT
        if status_vals is not None:
            v = status_vals[row_cells[0].row - 2]
            fill = STATUS_FILLS.get(v) if isinstance(v, str) else None
            if fill is not None:
                cell = row_cells[status_idx]
                cell.fill = fill
                cell.font = STATUS_FONT
                cell.alignment = STATUS_ALIGN

    # Auto-width (approximate; cap at 40)
    for c_idx, col_name in enumerate(cols, start=1):
        max_len = len(str(col_name))
        # Sample 100 rows max untuk efisiensi — drop NaN agar tidak menambah lebar palsu
        sample = df[col_name].dropna().astype(str).head(100).tolist()
        if sample:
            sample_max = max(len(s) for s in sample)
            max_len = max(max_len, min(sample_max, 60))
        width = min(max_len + 2, 40)
        ws.column_dimensions[get_column_letter(c_idx)].width = width

    # Header row height + freeze
    ws.row_dimensions[1].height = 28
    if freeze:
        ws.freeze_panes = freeze

    # Auto filter pada header
    last_col = get_column_letter(len(cols))
    ws.auto_filter.ref = f"A1:{last_col}{len(df) + 1}"


# ============================================================
# SHEET BUILDERS (ringkasan turunan)
# ============================================================

def _build_per_cabang(df: pd.DataFrame) -> pd.DataFrame:
    """Ringkasan per NAMA RESTO.

    H8-c: kolom opsional (TOTAL/MAX/ANOMALY STATUS/NAMA BARANG) di-skip
    bila tidak ada — graceful degradation, bukan KeyError.
    """
    if "NAMA RESTO" not in df.columns:
        return pd.DataFrame()
    size_col = "NAMA BARANG" if "NAMA BARANG" in df.columns else "NAMA RESTO"
    aggs = {"Total_Barang": (size_col, "size")}  # size counts ALL rows (count only non-null)
    if "TOTAL" in df.columns:
        aggs["Total_Waste"] = ("TOTAL", "sum")
    if "MAX" in df.columns:
        aggs["Max_Waste_Single"] = ("MAX", "max")
    if "ANOMALY STATUS" in df.columns:
        aggs["Anomali_Prioritas"] = ("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum()))
        aggs["Anomali_Potensi"] = ("ANOMALY STATUS", lambda x: int((x == "Potensi Anomali").sum()))
        aggs["Anomali_Review"] = ("ANOMALY STATUS", lambda x: int((x == "Perlu Review").sum()))
    out = df.groupby("NAMA RESTO", dropna=False).agg(**aggs).reset_index()
    out = out.rename(columns={
        k: v for k, v in {
            "NAMA RESTO": "Cabang",
            "Total_Barang": "Jumlah Baris",
            "Total_Waste": "Total Waste (qty)",
            "Max_Waste_Single": "Max Waste Harian",
        }.items() if k in out.columns
    })
    if "Anomali_Prioritas" in out.columns:
        out = out.sort_values("Anomali_Prioritas", ascending=False)
    return out


def _build_top_items(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Top N item by TOTAL. H8-c: kolom opsional di-skip bila tidak ada."""
    if "NAMA BARANG" not in df.columns or "TOTAL" not in df.columns:
        return pd.DataFrame()
    group_cols = ["NAMA BARANG"] + (["JENIS"] if "JENIS" in df.columns else [])
    aggs = {"Total_Waste": ("TOTAL", "sum")}
    if "MAX" in df.columns:
        aggs["Max_Waste"] = ("MAX", "max")
    if "NAMA RESTO" in df.columns:
        aggs["Cabang_Terpengaruh"] = ("NAMA RESTO", "nunique")
    if "ANOMALY STATUS" in df.columns:
        aggs["Anomali_Prioritas"] = ("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum()))
    g = (
        df.groupby(group_cols, dropna=False)
        .agg(**aggs)
        .reset_index()
        .sort_values("Total_Waste", ascending=False)
        .head(top_n)
    )
    g.insert(0, "Rank", range(1, len(g) + 1))
    return g


def _build_pareto(df: pd.DataFrame) -> pd.DataFrame:
    """Pareto alasan (KETERANGAN) — sum TOTAL, cumulative %."""
    if "KETERANGAN" not in df.columns or "TOTAL" not in df.columns:
        return pd.DataFrame()
    size_col = "NAMA BARANG" if "NAMA BARANG" in df.columns else "KETERANGAN"
    g = (
        df.groupby("KETERANGAN", dropna=False)
        .agg(Total_Waste=("TOTAL", "sum"), Jumlah_Barang=(size_col, "size"))  # size counts all rows
        .reset_index()
        .sort_values("Total_Waste", ascending=False)
    )
    grand_total = g["Total_Waste"].sum()
    if grand_total and grand_total > 0:
        g["Persentase"] = (g["Total_Waste"] / grand_total) * 100  # display as 0-100
        g["Cumulative"] = g["Persentase"].cumsum()
    else:
        g["Persentase"] = 0
        g["Cumulative"] = 0
    return g


def _build_log(df: pd.DataFrame, key_akhir: int, log_lines: list[str]) -> pd.DataFrame:
    """Sheet Log Run — ringkasan + timestamp + log lines."""
    rows = []
    rows.append(("Waktu Run", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    rows.append(("Key Akhir", str(key_akhir)))
    rows.append(("Total Baris Diproses", str(len(df))))
    rows.append(("Cabang Unik", str(df["NAMA RESTO"].nunique()) if "NAMA RESTO" in df.columns else "0"))
    rows.append(("Item Unik", str(df["NAMA BARANG"].nunique()) if "NAMA BARANG" in df.columns else "0"))
    if "ANOMALY STATUS" in df.columns:
        rows.append(("— Status —", ""))
        for status in ["Prioritas Tinggi", "Potensi Anomali", "Perlu Review", "Normal"]:
            cnt = int((df["ANOMALY STATUS"] == status).sum())
            rows.append((f"  {status}", str(cnt)))
    rows.append(("", ""))
    rows.append(("=== LOG PIPELINE ===", ""))
    for line in log_lines:
        rows.append(("", line))
    return pd.DataFrame(rows, columns=["Key", "Value"])
