"""
source_writer.py — Tulis balik koreksi nilai HARI (1-31) langsung ke file
Excel sumber REKAP MENTAH (v2.16.0 — fitur "edit dari pop-up").

MASALAH yang diselesaikan:
Sebelumnya pop-up DetailDialog 100% read-only — user lihat detail anomali
tapi tidak bisa mengoreksi nilai waste yang salah. Koreksi harus dilakukan
manual di Excel lalu re-run pipeline. User minta: "bisa gak aku langsung
revisi nilai dari program ketika pop up?" + "disimpan langsung ke file
rekap mentahnya" + "jangan ada silent error, semua transparan dan akurat".

Modul ini JUJUR & TRANSPARAN (anti silent-error):
  - BACKUP otomatis sebelum tulis (timestamped .bak.xlsx) — file asli
    TIDAK PERNAH ditimpa tanpa cadangan.
  - Setiap koreksi di-log eksplisit (file + konsol): siapa, baris Excel
    berapa, kolom hari berapa, nilai lama → nilai baru.
  - Validasi ketat: src_row integer ≥2 (header=row 1), day 1-31, nilai
    numerik ≥0. Input invalid → raise SourceWriteError (bukan ditelan).
  - Verifikasi post-write: baca ulang sel yang ditulis, bandingkan nilai
    yang dikembalikan engine vs nilai yang diminta — mismatch = raise
    (tulisan gagal diam-diam).
  - File terkunci (dibuka di Excel) → error jelas, bukan crash.
  - TOTAL (kolom 42) dihitung ulang = sum hari 1-31 supaya file tetap
    konsisten (TOTAL ≠ sum hari = korupsi data senyap).

Kontrak:
  SRC_ROW_COL = "__SRC_ROW" — kolom tersembunyi di df, nilai = nomor baris
  fisik di sheet sumber (1-based; baris 1 = header, data mulai baris 2).
  Dipasang oleh rekap_import.ensure_rekap_header() (injection point tunggal
  — row-accounting terjadi di sana). Disurvive pipeline stages (kolom
  biasa, tidak di-drop). Tidak ditampilkan (bukan anggota TABLE_COLS /
  DETAIL_COLS).

API utama:
  write_day_edits(source_path, src_row, day_edits, logger=None)
    → {"ok": True, "cells_written": int, "total_updated": bool,
       "backup": str, "sheet": str, "changes": [...]}
    → raise SourceWriteError bila gagal (pesan ramah, ada konteks).

  make_backup(source_path) → Path backup (dipakai write_day_edits; juga
    bisa dipanggil manual sebelum operasi berbahaya).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .loader import find_sheet, list_sheets, _read_excel_fast, _normalize_columns
from .rekap_import import _DAY_SET, RekapImportError, SRC_ROW_COL
from .utils import load_config

_LOG = logging.getLogger("waste_anomaly.source_writer")

# Kolom hari valid "1".."31" (string — kanonik df setelah _normalize_columns).
DAY_COLUMNS: tuple[str, ...] = tuple(str(d) for d in range(1, 32))


class SourceWriteError(Exception):
    """Gagal menulis koreksi ke file sumber. Pesan ramah-user + konteks."""


def _log(logger: Callable[[str], None] | None, msg: str) -> None:
    """Kirim ke callback logger pipeline-style DAN ke modul logging."""
    _LOG.info(msg)
    if logger is not None:
        try:
            logger(msg)
        except Exception:  # noqa: BLE001 — logger gagal tidak boleh crash write
            _LOG.warning("logger callback gagal (pesan: %s)", msg,
                         exc_info=True)


def make_backup(source_path: str | os.PathLike,
                logger: Callable[[str], None] | None = None) -> Path:
    """Salin file sumber ke backup timestamped di folder yang sama.

    Format: <name>.bak-YYYYMMDD-HHMMSS.xlsx (bukan .bak.xlsx polos —
    supaya backup berulang tidak menimpa cadangan sebelumnya; user bisa
    mengaudit riwayat koreksi). Raise SourceWriteError bila gagal (disk
    penuh / file terkunci / path tak ada) — TIDAK diam.
    """
    src = Path(source_path)
    if not src.exists():
        raise SourceWriteError(
            f"File sumber tidak ditemukan: {src}")
    if not src.is_file():
        raise SourceWriteError(
            f"Path sumber bukan file: {src}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = src.with_name(f"{src.stem}.bak-{stamp}{src.suffix}")
    try:
        shutil.copy2(src, bak)
    except OSError as exc:
        raise SourceWriteError(
            f"Gagal membuat backup '{bak}': {exc}") from exc
    _log(logger, f"[source_writer] backup dibuat: {bak.name}")
    return bak


def _resolve_sheet(path: Path, config: dict | None = None
                   ) -> tuple[str, int]:
    """Resolve nama sheet rekap di workbook sumber + baris header (0-based).

    Mirror find_rekap_sheet — dipakai pipeline fase LOAD. Return (sheet,
    header_row). Header_row selalu 0 untuk file standar (header baris-1
    Excel → 0-based row 0). Bila tidak ketemu → SourceWriteError jelas.
    """
    sheets = list_sheets(path)
    if not sheets:
        raise SourceWriteError(
            f"Workbook sumber tidak punya sheet terbaca: {path.name}")
    config = config if config is not None else load_config()
    candidates = list(config.get("input_sheets", {}).get("rekap_mentah", []))
    for extra in ("REKAP MENTAH", "rekap mentah"):
        if extra not in candidates:
            candidates.append(extra)
    name = None
    try:
        name = find_sheet(candidates, sheets)
    except ValueError:
        name = None
    if name is None:
        # Fallback: scan sheet pertama yang punya schema rekap
        for sn in sheets:
            try:
                df0 = _read_excel_fast(path, sheet_name=sn,
                                       header=0, nrows=6)
            except Exception as exc:  # noqa: BLE001 — log + lanjut sheet lain
                _LOG.warning("sheet %r gagal dibaca saat resolve: %s",
                             sn, exc)
                continue
            if df0 is None or df0.empty:
                continue
            df0 = _normalize_columns(df0)
            cols = [str(c).strip().upper() for c in df0.columns]
            if all(rc in cols for rc in ("NAMA RESTO", "JENIS", "NAMA BARANG")) \
                    and sum(1 for c in cols if c in _DAY_SET) >= 3:
                name = sn
                break
    if name is None:
        raise SourceWriteError(
            f"Tidak ada sheet rekap di '{path.name}' (cari: "
            f"{', '.join(candidates[:3])}…). Sheet tersedia: "
            f"{', '.join(sheets[:5])}")
    return name, 0


def _find_day_columns(ws, header_row: int = 1
                      ) -> dict[str, int]:
    """Map nama hari "1".."31" → nomor kolom Excel (1-based) di sheet.

    Baca header row (default baris 1) — cari sel berisi integer/teks hari
    1..31. Layout standar = col 9..39, tapi fungsi ini JUJUR membaca header
    sesungguhnya supaya robust terhadap layout non-standar (kolom
    ditambah/dihapus user). Hari yang tak ada di header → tidak di-map
    (koreksi hari itu akan ditolak eksplisit).
    """
    mapping: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=col).value
        if v is None:
            continue
        # Normalisasi: float integral (1.0) → "1"; selain itu str().strip()
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        s = str(v).strip()
        if s in DAY_COLUMNS:
            mapping[s] = col
    return mapping


def _find_total_column(ws, header_row: int = 1) -> int | None:
    """Cari kolom TOTAL di header row. Return nomor kolom atau None."""
    for col in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=col).value
        if v is None:
            continue
        s = str(v).strip().upper()
        if s == "TOTAL":
            return col
    return None


# ============================================================
# v2.16.0 — XML writer (memory-efficient, surgical)
# ============================================================
# File .xlsx = ZIP berisi XML. Sheet data di xl/worksheets/sheetN.xml.
# openpyxl load_workbook(read_only=False) memuat SEMUA sel ke objek Python
# (~450MB untuk file 54rb×42kolom) → OOM di mesin terbatas. Writer XML ini
# membaca HANYA sheet XML target sbg string (~67MB), replace <v> nilai sel
# spesifik via regex (well-formed xlsx → pola konsisten), lalu tulis ZIP
# baru dgn semua entry disalin tak berubah kecuali sheet XML yg dimodifikasi.
#
# Sel hari (I3, U3, dst.) = numerik murni: <c r="I3"><v>1005</v></c>.
# Sel TOTAL (AP3) = shared formula + cached value:
#   <c r="AP3"><f t="shared" si="0"/><v>20610</v></c>
# Writer UPDATE <v> cached value saja; <f> formula dibiarkan utuh supaya
# Excel recompute saat dibuka (nilai = sum hari baru = sama dgn <v> baru).
#
# Anti silent-error:
#   - Sel tipe string (t="s"/"str") → RAISE (sel hari seharusnya numerik).
#   - Sel tak ditemukan di XML → RAISE (jangan skip diam-diam).
#   - Verifikasi post-write baca ulang via openpyxl read_only.

_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _resolve_sheet_xml_path(zip_reader: zipfile.ZipFile,
                            sheet_name: str) -> str:
    """Map nama sheet → path file XML sheet di dalam ZIP xlsx.

    Baca xl/workbook.xml (daftar sheet + r:id) lalu xl/_rels/workbook.xml.rels
    (map r:id → target file). Return path absolut dlm ZIP mis.
    'xl/worksheets/sheet1.xml'. Raise SourceWriteError bila tak ketemu.
    """
    try:
        wb_xml = zip_reader.read("xl/workbook.xml")
    except KeyError as exc:
        raise SourceWriteError(
            f"Workbook rusak — 'xl/workbook.xml' tak ada di ZIP: {exc}"
        ) from exc
    try:
        root = ET.fromstring(wb_xml)
    except ET.ParseError as exc:
        raise SourceWriteError(
            f"xl/workbook.xml XML rusak (ParseError): {exc}") from exc
    sheets_el = root.find(f"{{{_XLSX_MAIN_NS}}}sheets")
    if sheets_el is None:
        raise SourceWriteError(
            "workbook.xml tak punya elemen <sheets> — file bukan xlsx valid")
    r_id = None
    for s in sheets_el.findall(f"{{{_XLSX_MAIN_NS}}}sheet"):
        if s.get("name") == sheet_name:
            r_id = s.get(f"{{{_XLSX_REL_NS}}}id")
            break
    if r_id is None:
        raise SourceWriteError(
            f"Sheet {sheet_name!r} tak ditemukan di workbook.xml")
    try:
        rels_xml = zip_reader.read("xl/_rels/workbook.xml.rels")
    except KeyError as exc:
        raise SourceWriteError(
            f"workbook.xml.rels tak ada di ZIP: {exc}") from exc
    try:
        rels_root = ET.fromstring(rels_xml)
    except ET.ParseError as exc:
        raise SourceWriteError(
            f"workbook.xml.rels XML rusak (ParseError): {exc}") from exc
    target = None
    for rel in rels_root:
        if rel.get("Id") == r_id:
            target = rel.get("Target")
            break
    if target is None:
        raise SourceWriteError(
            f"Relationship {r_id} (sheet {sheet_name!r}) tak ada di rels")
    # Target dari rels bisa: "worksheets/sheet1.xml" (relatif ke xl/),
    # "/xl/worksheets/sheet1.xml" (absolut dgn leading slash), atau
    # "xl/worksheets/sheet1.xml" (sudah absolut tanpa leading slash).
    # Normalisasi: hilangkan leading slash, pastikan prefix "xl/".
    target = target.lstrip("/")
    if not target.startswith("xl/"):
        target = f"xl/{target}"
    # Hilangkan duplikasi "xl/xl/" bila terjadi (edge case rels aneh)
    target = target.replace("xl/xl/", "xl/", 1) if target.startswith("xl/xl/") else target
    return target


def _replace_cell_v_xml(xml_str: str, cell_ref: str,
                        new_value_str: str) -> tuple[str, bool, str | None]:
    """Ganti nilai <v> di dalam <c r="cell_ref" ...>...</c>.

    Return (xml_str_baru, found: bool, old_value_str | None).
    Kasus yg ditangani:
      - Sel dgn <v>: ganti nilai, PRESERVE <f> formula (TOTAL shared formula).
      - Sel tanpa <v> (hanya <f> atau kosong): tambah <v>.
      - Sel self-closing (<c r="X" .../>): konversi ke sel lengkap dgn <v>.
      - Sel tipe string (t="s"/"str"): RAISE (sel hari seharusnya numerik).
      - Sel tak ditemukan: found=False (caller putuskan: raise vs skip).
    """
    # Cari sel lengkap: <c r="REF" ...> ... </c>
    cell_pat = re.compile(
        r'<c r="' + re.escape(cell_ref) + r'"([^>]*)>(.*?)</c>',
        re.DOTALL)
    m = cell_pat.search(xml_str)
    old_val: str | None = None
    if m:
        attrs = m.group(1)
        inner = m.group(2)
        # Tolak sel string (shared/inline) — sel hari harus numerik
        if 't="s"' in attrs or 't="str"' in attrs or 't="e"' in attrs:
            raise SourceWriteError(
                f"Sel {cell_ref} bertipe string/error "
                f"(atribut {attrs.strip()}) — tidak bisa tulis nilai "
                f"numerik. Sel hari seharusnya numerik; periksa file Excel "
                f"sumber (mungkin header hari terbaca sebagai teks).")
        # Cari <v>...</v> di inner
        v_pat = re.compile(r'<v>([^<]*)</v>')
        v_m = v_pat.search(inner)
        if v_m:
            old_val = v_m.group(1)
            new_inner = (inner[:v_m.start()] + f'<v>{new_value_str}</v>'
                         + inner[v_m.end():])
        else:
            # Tidak ada <v> — tambahkan (preserve <f> bila ada)
            new_inner = inner + f'<v>{new_value_str}</v>'
        new_cell = f'<c r="{cell_ref}"{attrs}>{new_inner}</c>'
        return xml_str[:m.start()] + new_cell + xml_str[m.end():], True, old_val
    # Coba self-closing: <c r="REF" .../>
    sc_pat = re.compile(r'<c r="' + re.escape(cell_ref) + r'"([^>]*)/>')
    sc = sc_pat.search(xml_str)
    if sc:
        attrs = sc.group(1)
        if 't="s"' in attrs or 't="str"' in attrs or 't="e"' in attrs:
            raise SourceWriteError(
                f"Sel {cell_ref} (self-closing) bertipe string/error "
                f"— tidak bisa tulis numerik.")
        attrs_clean = re.sub(r'\s+t="[^"]*"', '', attrs)
        new_cell = f'<c r="{cell_ref}"{attrs_clean}><v>{new_value_str}</v></c>'
        return xml_str[:sc.start()] + new_cell + xml_str[sc.end():], True, None
    return xml_str, False, None


def _write_zip_replaced_sheet(source_path: Path,
                              sheet_xml_path: str,
                              new_sheet_xml: str,
                              tmp_out: Path) -> None:
    """Tulis ZIP baru = salin semua entry xlsx, GANTI sheet XML target.

    Semua entry (styles, sharedStrings, sheet lain, pivotTable, theme,
    [Content_Types], rels) disalin APA ADANYA — hanya sheet XML target
    diganti. Kompresi per-entry dipertahankan (ZipInfo.compress_type).
    Raise SourceWriteError bila gagal (disk penuh / I/O error).
    """
    try:
        with zipfile.ZipFile(source_path, "r") as zin:
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED,
                                 allowZip64=True) as zout:
                for item in zin.infolist():
                    if item.filename == sheet_xml_path:
                        zout.writestr(
                            item, new_sheet_xml.encode("utf-8"))
                    else:
                        data = zin.read(item.filename)
                        zout.writestr(item, data)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SourceWriteError(
            f"Gagal menulis ZIP baru '{tmp_out.name}': {exc}") from exc


def write_day_edits(
    source_path: str | os.PathLike,
    src_row: int,
    day_edits: dict[str, float | int | None],
    logger: Callable[[str], None] | None = None,
    config: dict | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Tulis koreksi nilai hari 1-31 ke baris `src_row` sheet rekap sumber.

    Parameter:
      source_path  : path file Excel sumber (REKAP MENTAH / DATA_WASTE).
      src_row      : nomor baris FISIK sheet (1-based; ≥2 — baris 1 header).
      day_edits    : {nama_hari_str: nilai_baru} — mis. {"13": 0.0, "14": 1250}.
                     Hari tak ada di dict TIDAK diubah. Nilai None = hapus
                     (sel kosong). Nilai harus numerik ≥0.
      logger       : callback pipeline-style (opsional).
      config       : config dict (opsional; default load_config()).
      backup       : v2.16.1 — bila False, LEWATI pembuatan backup (user yakin
                     perubahan, minta cepat). Default True (aman). Bila False,
                     field "backup" di return = "" dan pesan error tak referensi
                     backup (tidak ada cadangan utk pulih).

    Return dict:
      ok=True, sheet, src_row, cells_written, total_updated (bool),
      total_new (float|None), backup (path str or ""), changes (list[dict]),
      prev_total (float|None).

    Raise SourceWriteError bila:
      - src_row < 2 (baris header / invalid)
      - day_edits kosong / berisi hari invalid / nilai non-numerik / negatif
      - file tidak ada / terkunci (dibuka Excel)
      - hari di day_edits tak ada di header sheet
      - verifikasi post-write mismatch (tulis 'X' tapi baca 'Y')

    Backup otomatis dibuat SEBELUM tulis (make_backup) bila backup=True.
    """
    src = Path(source_path)
    # ---- VALIDASI INPUT (sebelum sentuh file) ----
    if not src.exists():
        raise SourceWriteError(f"File sumber tidak ditemukan: {src}")
    try:
        src_row_i = int(src_row)
    except (TypeError, ValueError) as exc:
        raise SourceWriteError(
            f"src_row harus integer, dapat {src_row!r}") from exc
    if src_row_i < 2:
        raise SourceWriteError(
            f"src_row harus ≥2 (baris 1 = header); dapat {src_row_i}")
    if not day_edits:
        raise SourceWriteError("day_edits kosong — tidak ada koreksi untuk ditulis")
    # Validasi setiap entry
    cleaned: dict[str, float | None] = {}
    for day, val in day_edits.items():
        day_s = str(day).strip()
        if day_s not in DAY_COLUMNS:
            raise SourceWriteError(
                f"Hari {day!r} invalid — harus salah satu dari "
                f"{', '.join(DAY_COLUMNS)}")
        if val is None or (isinstance(val, float) and val != val):
            cleaned[day_s] = None  # NaN/None → hapus sel
        else:
            try:
                num = float(val)
            except (TypeError, ValueError) as exc:
                raise SourceWriteError(
                    f"Nilai hari {day_s} bukan numerik: {val!r}") from exc
            if num != num:  # NaN check post-conversion
                raise SourceWriteError(
                    f"Nilai hari {day_s} adalah NaN — tolak")
            if num < 0:
                raise SourceWriteError(
                    f"Nilai hari {day_s} negatif ({num}) — tolak "
                    f"(waste tidak boleh < 0)")
            if num > 1e9:
                raise SourceWriteError(
                    f"Nilai hari {day_s} absurd ({num}) — tolak "
                    f"(batas wajar 1e9)")
            cleaned[day_s] = num
    _log(logger, f"[source_writer] mulai tulis {len(cleaned)} koreksi hari "
                 f"ke baris {src_row_i} file '{src.name}'"
                 + ("" if backup else " (TANPA backup — user yakin perubahan)"))

    # ---- BACKUP (sebelum sentuh file) — opsional v2.16.1 ----
    backup_path: Path | None = None
    if backup:
        backup_path = make_backup(src, logger=logger)
    else:
        _log(logger, "[source_writer] backup DILEWATI (backup=False)")
    # Pesan seragam utk error messages: path atau fallback bila tak ada.
    bak_msg = (str(backup_path) if backup_path is not None
               else "(backup dilewati — TIDAK ada cadangan)")

    # ---- RESOLVE SHEET ----
    sheet_name, header_row_0 = _resolve_sheet(src, config=config)
    header_row_1 = header_row_0 + 1  # 1-based untuk openpyxl
    _log(logger, f"[source_writer] sheet target: '{sheet_name}' "
                 f"(header baris {header_row_1})")

    # ---- BACA HEADER + OLD VALUES (openpyxl read_only — memory-efficient) ----
    # v2.16.0: TIDAK memakai openpyxl write mode (OOM di file 54rb×42kolom).
    # Baca header & old values via read_only (streaming), lalu tulis via XML
    # (surgical, hanya sentuh sel target).
    try:
        wb_ro = load_workbook(src, read_only=True, data_only=True)
    except Exception as exc:
        raise SourceWriteError(
            f"Gagal membuka workbook '{src.name}' (read_only): {exc}") from exc
    day_col_map: dict[str, int] = {}
    total_col: int | None = None
    old_day_vals: dict[str, float | None] = {}
    prev_total: float | None = None
    all_day_vals_for_total: dict[str, float] = {}  # semua hari utk sum TOTAL
    try:
        if sheet_name not in wb_ro.sheetnames:
            raise SourceWriteError(
                f"Sheet '{sheet_name}' tidak ada di workbook. "
                f"Tersedia: {', '.join(wb_ro.sheetnames[:5])}")
        ws = wb_ro[sheet_name]
        # read_only: max_row mungkin tak akurat sampai iter. Ambil header
        # via iter_rows baris 1 + baris src_row.
        header_row = ws.iter_rows(min_row=header_row_1, max_row=header_row_1,
                                  values_only=True)
        try:
            header_vals = next(header_row)
        except StopIteration:
            raise SourceWriteError(
                f"Sheet '{sheet_name}' kosong — tak ada baris header")
        # Map hari + total dari header
        for ci, hv in enumerate(header_vals, start=1):
            if hv is None:
                continue
            if isinstance(hv, float) and hv.is_integer():
                hv = int(hv)
            s = str(hv).strip()
            if s in DAY_COLUMNS:
                day_col_map[s] = ci
            elif s.upper() == "TOTAL" and total_col is None:
                total_col = ci
        _log(logger, f"[source_writer] header map: {len(day_col_map)} kolom "
                     f"hari ditemukan, TOTAL "
                     f"{'kolom '+str(total_col) if total_col else 'TIDAK ADA'}")
        # Baca baris src_row utk old values (hari + TOTAL + semua hari utk sum)
        target_row_iter = ws.iter_rows(min_row=src_row_i, max_row=src_row_i,
                                       values_only=True)
        try:
            target_vals = next(target_row_iter)
        except StopIteration:
            raise SourceWriteError(
                f"src_row {src_row_i} tak ada di sheet (baris kosong/melebihi "
                f"max_row).")
        # Ekstrak old values
        for day_s, xl_col in day_col_map.items():
            if xl_col - 1 < len(target_vals):
                v = target_vals[xl_col - 1]
                if v is None:
                    old_day_vals[day_s] = None
                    all_day_vals_for_total[day_s] = 0.0
                elif isinstance(v, (int, float)) and not (
                        isinstance(v, float) and v != v):
                    old_day_vals[day_s] = float(v)
                    all_day_vals_for_total[day_s] = float(v)
                else:
                    old_day_vals[day_s] = None
                    all_day_vals_for_total[day_s] = 0.0
            else:
                old_day_vals[day_s] = None
                all_day_vals_for_total[day_s] = 0.0
        if total_col is not None and total_col - 1 < len(target_vals):
            tv = target_vals[total_col - 1]
            if isinstance(tv, (int, float)) and not (
                    isinstance(tv, float) and tv != tv):
                prev_total = float(tv)
    finally:
        wb_ro.close()

    # Validasi: semua hari di day_edits harus ada di header
    for day_s in cleaned:
        if day_s not in day_col_map:
            raise SourceWriteError(
                f"Hari {day_s} tidak ada di header sheet '{sheet_name}' "
                f"(baris {header_row_1}). Kolom hari yang tersedia: "
                f"{', '.join(sorted(day_col_map, key=int))}")

    # Hitung TOTAL baru = sum semua hari (old + edits)
    for day_s, new_val in cleaned.items():
        if new_val is None:
            all_day_vals_for_total[day_s] = 0.0
        else:
            all_day_vals_for_total[day_s] = float(new_val)
    day_sum = sum(all_day_vals_for_total.values())
    total_new: float | None = (float(day_sum) if total_col is not None else None)

    # ---- TULIS VIA XML (surgical, memory-efficient) ----
    # 1. Resolve sheet XML path di ZIP
    try:
        with zipfile.ZipFile(src, "r") as zf:
            sheet_xml_path = _resolve_sheet_xml_path(zf, sheet_name)
            sheet_xml_bytes = zf.read(sheet_xml_path)
    except SourceWriteError:
        raise
    except Exception as exc:
        raise SourceWriteError(
            f"Gagal membaca ZIP xlsx '{src.name}': {exc}") from exc
    _log(logger, f"[source_writer] sheet XML path: {sheet_xml_path} "
                 f"({len(sheet_xml_bytes):,} bytes)")
    sheet_xml = sheet_xml_bytes.decode("utf-8", errors="replace")

    # 2. Replace setiap sel hari
    changes: list[dict[str, Any]] = []
    cells_written = 0
    for day_s, new_val in cleaned.items():
        xl_col = day_col_map[day_s]
        cell_ref = f"{get_column_letter(xl_col)}{src_row_i}"
        # Format nilai utk XML: numerik (int jika bulat, else float repr)
        if new_val is None:
            # Hapus nilai: tulis 0 (sel hari waste tidak boleh kosong utk
            # konsistensi TOTAL sum; None diperlakukan 0)
            val_str = "0"
            display_new = 0.0
        else:
            if float(new_val).is_integer():
                val_str = str(int(new_val))
            else:
                val_str = repr(float(new_val))
            display_new = float(new_val)
        old_norm = old_day_vals.get(day_s)
        sheet_xml, found, _old_str = _replace_cell_v_xml(
            sheet_xml, cell_ref, val_str)
        if not found:
            raise SourceWriteError(
                f"Sel {cell_ref} (hari {day_s}) tidak ditemukan di sheet XML. "
                f"Baris mungkin tak punya sel itu (data sparse). Backup: "
                f"{bak_msg}. Koreksi dibatalkan — file TIDAK berubah.")
        cells_written += 1
        changes.append({
            "day": day_s,
            "xl_col": xl_col,
            "xl_col_letter": get_column_letter(xl_col),
            "cell_ref": cell_ref,
            "old": old_norm,
            "new": display_new,
        })
        _log(logger, f"  hari {day_s} (sel {cell_ref}): "
                     f"{old_norm!r} → {display_new!r}")

    # 3. Update TOTAL (sum hari 1-31) — preserve <f> formula
    total_updated = False
    if total_col is not None:
        total_ref = f"{get_column_letter(total_col)}{src_row_i}"
        if float(day_sum).is_integer():
            total_str = str(int(day_sum))
        else:
            total_str = repr(float(day_sum))
        sheet_xml, found_t, _ = _replace_cell_v_xml(
            sheet_xml, total_ref, total_str)
        if not found_t:
            _log(logger, f"[source_writer] WARNING: sel TOTAL {total_ref} "
                         f"tak ditemukan di XML — TOTAL tidak diupdate "
                         f"(file tetap disimpan dgn koreksi hari).")
        else:
            total_updated = True
            _log(logger, f"  TOTAL (sel {total_ref}): "
                         f"{prev_total!r} → {total_new!r}")

    # 4. Tulis ZIP baru (semua entry disalin, sheet XML diganti)
    tmp_out = src.with_suffix(src.suffix + ".tmp_write")
    try:
        _write_zip_replaced_sheet(src, sheet_xml_path, sheet_xml, tmp_out)
    except SourceWriteError:
        # Bersihkan tmp
        try:
            tmp_out.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    # Ganti file asli dgn tmp (atomic di Unix)
    try:
        shutil.move(str(tmp_out), str(src))
    except OSError as exc:
        raise SourceWriteError(
            f"Gagal mengganti file asli dgn hasil tulis: {exc}. "
            f"File hasil ada di {tmp_out}; asli MUNGKIN masih utuh. "
            f"Backup: {bak_msg}.") from exc
    _log(logger, f"[source_writer] SIMPAN OK (via XML) — {cells_written} sel "
                 f"hari + TOTAL {'diupdate' if total_updated else 'tidak ada'}")

    # ---- VERIFIKASI POST-WRITE (openpyxl read_only — baca ulang) ----
    try:
        wb_verify = load_workbook(src, read_only=True, data_only=True)
    except Exception as exc:
        raise SourceWriteError(
            f"Gagal membuka ulang file utk verifikasi: {exc}. "
            f"File MUNGKIN korup — backup: {bak_msg}.") from exc
    try:
        ws_v = wb_verify[sheet_name]
        vrow = ws_v.iter_rows(min_row=src_row_i, max_row=src_row_i,
                              values_only=True)
        try:
            v_vals = next(vrow)
        except StopIteration:
            raise SourceWriteError(
                f"VERIFIKASI GAGAL: baris {src_row_i} tak terbaca ulang. "
                f"Backup: {bak_msg}.")
        for ch in changes:
            xl_col = ch["xl_col"]
            got = v_vals[xl_col - 1] if xl_col - 1 < len(v_vals) else None
            want = ch["new"]
            if want is None:
                ok = (got is None or got == 0)
            elif isinstance(got, (int, float)):
                ok = abs(float(got) - float(want)) < 1e-9
            else:
                ok = False
            if not ok:
                raise SourceWriteError(
                    f"VERIFIKASI GAGAL hari {ch['day']} (sel {ch['cell_ref']}): "
                    f"tulis {want!r} tapi baca-ulang {got!r}. File MUNGKIN "
                    f"korup — backup: {bak_msg}. JANGAN pakai file ini.")
        if total_updated and total_col is not None:
            got_t = (v_vals[total_col - 1]
                     if total_col - 1 < len(v_vals) else None)
            if isinstance(got_t, (int, float)):
                if abs(float(got_t) - float(total_new)) > 1e-9:
                    raise SourceWriteError(
                        f"VERIFIKASI TOTAL GAGAL: tulis {total_new!r} tapi "
                        f"baca-ulang {got_t!r}. Backup: {bak_msg}.")
            else:
                raise SourceWriteError(
                    f"VERIFIKASI TOTAL GAGAL: baca-ulang non-numerik "
                    f"{got_t!r}. Backup: {bak_msg}.")
    finally:
        wb_verify.close()
    _log(logger, f"[source_writer] verifikasi post-write OK — semua sel "
                 f"terbaca ulang dgn nilai benar")

    return {
        "ok": True,
        "sheet": sheet_name,
        "src_row": src_row_i,
        "cells_written": cells_written,
        "total_updated": total_updated,
        "total_new": total_new,
        "prev_total": prev_total,
        "backup": str(backup_path) if backup_path is not None else "",
        "changes": changes,
    }
