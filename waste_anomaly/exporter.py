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
# MAIN ENTRY
# ============================================================

def export_to_excel(
    df: pd.DataFrame,
    output_path: str | os.PathLike,
    config: dict,
    key_akhir: int,
    log_lines: list[str],
    extra_sheets: dict[str, pd.DataFrame] | None = None,
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
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER

    # ---- Body: konversi per-kolom sekali, lalu append per baris ----
    col_values = [_column_cell_values(df[c]) for c in cols]
    n_rows = len(df)
    for row in zip(*col_values):
        ws.append(row)

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
