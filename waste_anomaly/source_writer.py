"""
source_writer.py — Tulis balik koreksi nilai HARI (1-31) langsung ke file
Excel sumber REKAP MENTAH (v2.16.0 — fitur "edit dari pop-up").

MASALAH yang diselesaikan:
Sebelumnya pop-up DetailDialog 100% read-only — user lihat detail anomali
tapi tidak bisa mengoreksi nilai waste yang salah. Koreksi harus dilakukan
manual di Excel lalu re-run pipeline. User minta: "bisa gak aku langsung
revisi nilai dari program ketika pop up?" + "disimpan langsung ke file
rekap mentahnya" + "jangan ada silent error, semua transparan dan akurat".
v2.19.4: "kalau ubah nilai langsung timpa file nya jangan buat back up" →
jalur UI default backup=False (langsung timpa file asli — user yakin
perubahan, tidak mau .bak berpuluh-puluh). backup=True tetap tersedia utk
operasi lain yang minta cadangan.

Modul ini JUJUR & TRANSPARAN (anti silent-error):
  - TIMPA LANGSUNG file asli (permintaan user v2.19.4) — tanpa backup di
    jalur UI default. Aman via rantai: tulis ke tmp → os.replace ATOMIK
    (file utuh ATAU tmp utuh, tak pernah setengah). Total gagal menimpa
    → file HASIL koreksi diselamatkan sbg <nama>_KOREKSI.xlsx (siap dibuka
    Excel) + raise ramah — file asli TETAP utuh (atomik).
  - Setiap koreksi di-log eksplisit (file + konsol): siapa, baris Excel
    berapa, kolom hari berapa, nilai lama → nilai baru.
  - Validasi ketat: src_row integer ≥2 (header=row 1), day 1-31, nilai
    numerik ≥0. Input invalid → raise SourceWriteError (bukan ditelan).
  - Verifikasi post-write: baca ulang sel yang ditulis, bandingkan nilai
    yang dikembalikan engine vs nilai yang diminta — mismatch = raise
    (tulisan gagal diam-diam).
  - File terkunci (dibuka di Excel / read-only attr / AV scan) → error
    jelas, bukan crash. v2.19.4: pre-check bersihkan atribut read-only
    Windows dulu + retry backoff panjang (~9 dtk utk AV scan file 9MB) +
    fallback in-place (replace diblokir, tulis boleh).
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
  write_day_edits(source_path, src_row, day_edits, logger=None,
                  backup=False)
    → {"ok": True, "cells_written": int, "total_updated": bool,
       "backup": str, "sheet": str, "changes": [...]}
    → raise SourceWriteError bila gagal (pesan ramah, ada konteks).

  make_backup(source_path) → Path backup (opsional; dipakai hanya bila
    backup=True — bisa dipanggil manual sebelum operasi berbahaya).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .rekap_import import SRC_ROW_COL
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


def _assert_writable(src: Path,
                     logger: Callable[[str], None] | None = None) -> None:
    """v2.19.3 — PRE-CHECK kunci tulis SEBELUM kerja berat dimulai.

    Laporan user (WinError 5 saat "Simpan koreksi"): file rekap terbuka
    di Excel mengunci file → os.replace gagal SETELAH seluruh kerja tulis
    selesai — jelek: tmp file tercecer, user baru tahu di akhir, koreksi
    "hilang". Uji kunci di muka: buat handle tulis SEBENTAR (os.open
    O_RDWR + tutup). File yang:
      - dibuka di Excel (sharing violation menolak tulis),
      - ber-atribut read-only,
      - sedang di-sinkron OneDrive / discan antivirus
    → PermissionError → raise pesan ramah LANGSUNG (sebelum backup/
    tmp/verifikasi jalan; tidak ada file tercecer).

    v2.19.4 — bersihkan atribut READ-ONLY Windows DULU (sebab umum
    WinError 5 yang BUKAN kunci Excel: file download/internet/salin CD
    punya flag read-only → os.open O_RDWR ditolak padahal Excel TIDAK
    membukanya). _clear_readonly hapus flag → os.open retry.

    Kegagalan OSError lain (platform eksotis) → diabaikan diam-diam:
    jalur os.replace asli tetap jadi sumber kebenaran terakhir.
    """
    # v2.19.4 — read-only attr Windows dibersihkan otomatis (no-op POSIX).
    _clear_readonly(src, logger=logger)
    try:
        fd = os.open(str(src), os.O_RDWR | getattr(os, "O_BINARY", 0))
    except PermissionError as exc:
        _log(logger, f"[source_writer] PRE-CHECK: file terkunci: {exc}")
        raise SourceWriteError(
            f"File '{src.name}' sedang TERKUNI — tidak bisa ditulis.\n"
            "Kemungkinan: (1) masih DIBUKA di Excel — paling sering; "
            "(2) sedang disinkronkan OneDrive / discan antivirus.\n"
            "Solusi: TUTUP dulu file-nya (Excel: File → Close, atau keluar "
            "Excel), lalu klik \"Simpan koreksi\" ulang.\n"
            "(File asli TIDAK tersentuh — pengecekan ini jalan sebelum "
            "penulisan.)") from exc
    except OSError:
        return
    else:
        os.close(fd)


# v2.19.4 — RETRY backoff panjang utk os.replace. File besar (9MB) +
# Windows Defender real-time scan bisa pegang handle detik-detikan saat
# tmp baru ditulis → 4×0,4 dtk (v2.19.3) tak cukup. 8 jeda naik
# (0,3→2,0 dtk) = ~9 dtk jendela total; kunci PERMANEN (Excel terbuka)
# tak akan lepas → fallback in-place / rescue (lihat bawah).
_REPLACE_RETRY_DELAYS: tuple[float, ...] = (
    0.3, 0.5, 0.7, 1.0, 1.0, 1.5, 2.0, 2.0,
)


def _file_is_readonly(src: Path) -> bool:
    """v2.19.4 — deteksi atribut READ-ONLY Windows (sebab umum WinError 5
    yang BUKAN kunci Excel — file download/internet/salin CD punya flag
    read-only). POSIX: st_fileattributes tak ada → False (chmod-perm
    ditangani jalur OSError biasa)."""
    try:
        st = os.stat(str(src))
    except OSError:
        return False
    attrs = getattr(st, "st_fileattributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1))


def _clear_readonly(src: Path,
                    logger: Callable[[str], None] | None = None) -> bool:
    """v2.19.4 — bersihkan atribut READ-ONLY Windows (PermissionError di
    os.open utk file ber-flag read-only). Return True bila dibersihkan.
    POSIX no-op (st_fileattributes tak ada)."""
    if not _file_is_readonly(src):
        return False
    try:
        os.chmod(str(src), stat.S_IWRITE | stat.S_IREAD)
    except OSError as exc:
        _log(logger, f"[source_writer] read-only terdeteksi tapi chmod "
                     f"gagal: {exc}")
        return False
    _log(logger, "[source_writer] atribut READ-ONLY dihapus otomatis "
                 "(file download/salin punya flag read-only).")
    return True


def _overwrite_in_place(tmp_out: Path, src: Path,
                        logger: Callable[[str], None] | None = None) -> None:
    """v2.19.4 — FALLBACK saat os.replace diblokir tapi tulis-file
    diizinkan: buka file asli mode 'r+b', stream-salin isi tmp ke
    dalamnya, truncate sisa, flush + fsync. Lalu hapus tmp.

    NON-atomik (vs os.replace) — crash/listrik di tengah salin = file
    asli rusak. Tapi replace sudah gagal; ini jalur terakhir sebelum
    menyerah. fsync + truncate meminimalkan jendela kerentanan.

    Raise OSError bila open-tulis ditolak (file terkunci Excel —
    penanganan rescue di pemanggil).
    """
    chunk = 1024 * 1024  # 1 MB — buffer besar utk file 9MB (1 pass)
    with open(src, "r+b") as dst_f, open(tmp_out, "rb") as src_f:
        shutil.copyfileobj(src_f, dst_f, chunk)
        dst_f.truncate()
        dst_f.flush()
        os.fsync(dst_f.fileno())
    try:
        tmp_out.unlink(missing_ok=True)
    except OSError as exc:
        _log(logger, f"[source_writer] tmp sisa (unlink gagal, abaikan): "
                     f"{exc}")
    _log(logger, "[source_writer] FALLBACK in-place sukses (replace "
                 "diblokir tapi tulis langsung berhasil — file asli "
                 "ditimpa penuh + fsync).")


def _rescue_result_file(tmp_out: Path, src: Path,
                        logger: Callable[[str], None] | None = None) -> Path:
    """v2.19.4 — TOTAL gagal menimpa: file hasil (berisi koreksi) diberi
    nama ramah <stem>_KOREKSI.xlsx di folder sama (siap dibuka Excel —
    beda dgn .tmp_write.PID tak dikenal Windows). Bila rename pun
    diblokir, tmp dipertahankan apa adanya (path dikembalikan).

    Return: path file hasil koreksi (rescue kalau rename ok, tmp kalau
    tidak) — ditampilkan ke user utk pemulihan manual.
    """
    rescue = src.with_name(f"{src.stem}_KOREKSI{src.suffix}")
    if rescue == src:
        # suffix kosong / nama aneh — jangan tabrak file asli.
        return tmp_out
    try:
        os.replace(tmp_out, rescue)
        return rescue
    except OSError as exc:
        _log(logger, f"[source_writer] rescue-rename ke {rescue.name} "
                     f"gagal ({exc}) — tmp dipertahankan: {tmp_out.name}")
        return tmp_out


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
    # v2.18.0 audit (L-9): dua backup dalam sedetik sama saling menimpa
    # (copy2 menimpa diam-diam) — suffix penghitung bila nama sudah ada.
    if bak.exists():
        i = 1
        while bak.exists():
            bak = src.with_name(f"{src.stem}.bak-{stamp}-{i}{src.suffix}")
            i += 1
    try:
        shutil.copy2(src, bak)
    except OSError as exc:
        raise SourceWriteError(
            f"Gagal membuat backup '{bak}': {exc}") from exc
    _log(logger, f"[source_writer] backup dibuat: {bak.name}")
    return bak


def _resolve_sheet(path: Path, config: dict | None = None,
                   logger: Callable[[str], None] | None = None
                   ) -> tuple[str, int]:
    """Resolve nama sheet rekap di workbook sumber + baris header (0-based).

    v2.16.2 BUG FIX: sebelumnya hardcoded `return name, 0` (header_row=0
    selalu) → SHIFTED-HEADER file (title row 1, header row 3, data row 4+)
    diproses dgn header_row=0 → writer baca Excel row 1 (title) sbg header
    → 0 kolom hari ditemukan → SourceWriteError menyesatkan.
    Fix: panggil find_rekap_sheet (rekap_import) yg memakai _detect_header_row
    utk scan ≤6 baris pertama + temukan header SESUNGGUHNYA. Return header_row
    0-based yg benar.
    """
    from .rekap_import import find_rekap_sheet, RekapImportError
    config = config if config is not None else load_config()
    try:
        name, header_row_0 = find_rekap_sheet(path, config, logger=logger)
    except RekapImportError as exc:
        raise SourceWriteError(
            f"Tidak bisa resolve sheet rekap di '{path.name}': {exc}"
        ) from exc
    return name, header_row_0


# v2.16.2: _find_day_columns & _find_total_column DIHAPUS (dead code —
# write_day_edits baca header inline via iter_rows, bukan helper ini).


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
    # v2.16.2: normalisasi lengkap — handle leading slash, ../ , duplikasi.
    import posixpath
    target = target.lstrip("/")
    if not target.startswith("xl/"):
        target = f"xl/{target}"
    # posixpath.normpath resolve ../ dan ./ (ZIP flat namespace tak resolve)
    target = posixpath.normpath(target)
    # Pastikan masih di bawah xl/ (normpath bisa naik ke atas)
    if not target.startswith("xl/"):
        target = f"xl/{target.split('/')[-1]}"
    return target


def _replace_cell_v_xml(xml_str: str, cell_ref: str,
                        new_value_str: str) -> tuple[str, bool, str | None]:
    """Ganti nilai <v> di dalam <c r="cell_ref" ...>...</c>.

    Return (xml_str_baru, found: bool, old_value_str | None).
    Kasus yg ditangani:
      - Sel dgn <v>: ganti nilai, PRESERVE <f> formula (TOTAL shared formula).
      - Sel tanpa <v> (hanya <f> atau kosong): tambah <v>.
      - Sel self-closing (<c r="X" .../>): konversi ke sel lengkap dgn <v>.
      - Sel tipe string (t="s"/"str"/"inlineStr"/"b"/"e"): RAISE.
      - Sel tak ditemukan: found=False (caller putuskan: raise vs skip).

    v2.16.2 BUG FIX: regex lama `[^>]*` menelan `/` di self-closing cell
    (`<c r="I3" s="5"/>`) → match `</c>` cell SEBELAHNYA → korupsi cell lain.
    Fix: attrs pattern `[^>/]*` exclude `/` → self-closing tak match full-cell
    pattern, jatuh ke self-closing handler di bawah.
    """
    # Cari sel lengkap: <c r="REF" attrs> inner </c>
    # attrs = [^>/]* (exclude / supaya self-closing tak match di sini)
    cell_pat = re.compile(
        r'<c r="' + re.escape(cell_ref) + r'"([^>/]*?)>(.*?)</c>',
        re.DOTALL)
    m = cell_pat.search(xml_str)
    old_val: str | None = None
    if m:
        attrs = m.group(1)
        inner = m.group(2)
        # v2.16.2: tolak SEMUA tipe non-numerik (s/str/inlineStr/b/e).
        # Sebelumnya: substring check 't="s"' lolos 't="inlineStr"' & 't="b"'.
        # Kini: regex extract t= value, tolak jika bukan "n" (numeric).
        t_match = re.search(r'\st="([^"]*)"', attrs)
        if t_match and t_match.group(1) != "n":
            raise SourceWriteError(
                f"Sel {cell_ref} bertipe non-numerik (t=\"{t_match.group(1)}\") "
                f"— tidak bisa tulis nilai numerik. Sel hari seharusnya "
                f"numerik; periksa file Excel sumber.")
        # Cari <v>...</v> di inner.
        # v2.18.0 audit (M-2): pola lama r'<v>[^<]*</v>' TIDAK match
        # bentuk self-closing '<v/>' (sel kosong bergaya dari tool lain
        # — openpyxl menulis '<c r=.. s=../>' tapi pustaka lain bisa
        # '<c r=..><v/></c>') → <v> baru DITAMBAHKAN setelahnya → dua
        # anak <v> = XML invalid → file sumber KORUP sebelum verifikasi
        # jalan. Pola baru meng-cover dua-duanya dan MENGGANTI.
        v_pat = re.compile(r'<v(?:/>|>[^<]*</v>)')
        v_m = v_pat.search(inner)
        if v_m:
            old_val = None if v_m.group(0) == "<v/>" else v_m.group(0)[3:-4]
            new_inner = (inner[:v_m.start()] + f'<v>{new_value_str}</v>'
                         + inner[v_m.end():])
        else:
            # Tidak ada <v> — tambahkan (preserve <f> bila ada)
            new_inner = inner + f'<v>{new_value_str}</v>'
        new_cell = f'<c r="{cell_ref}"{attrs}>{new_inner}</c>'
        return xml_str[:m.start()] + new_cell + xml_str[m.end():], True, old_val
    # Coba self-closing: <c r="REF" attrs/>
    sc_pat = re.compile(r'<c r="' + re.escape(cell_ref) + r'"([^>]*)/>')
    sc = sc_pat.search(xml_str)
    if sc:
        attrs = sc.group(1)
        t_match = re.search(r'\st="([^"]*)"', attrs)
        if t_match and t_match.group(1) != "n":
            raise SourceWriteError(
                f"Sel {cell_ref} (self-closing) bertipe non-numerik "
                f"(t=\"{t_match.group(1)}\") — tidak bisa tulis numerik.")
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
    backup: bool = False,
) -> dict[str, Any]:
    """Tulis koreksi nilai hari 1-31 ke baris `src_row` sheet rekap sumber.

    Parameter:
      source_path  : path file Excel sumber (REKAP MENTAH / DATA_WASTE).
      src_row      : nomor baris FISIK sheet (1-based; ≥2 — baris 1 header).
      day_edits    : {nama_hari_str: nilai_baru} — mis. {"13": 0.0, "14": 1250}.
                     Hari tak ada di dict TIDAK diubah. Nilai None/NaN
                     ditulis sebagai 0 (bukan sel kosong — konsistensi
                     TOTAL = sum hari; audit v2.18.0 L-7: docstring lama
                     salah menjanjikan "hapus sel"). Nilai harus numerik ≥0.
      logger       : callback pipeline-style (opsional).
      config       : config dict (opsional; default load_config()).
      backup       : v2.16.1 — bila False (default sejak v2.19.4, permintaan
                     user "kalau ubah nilai langsung timpa file nya jangan
                     buat back up"), LEWATI pembuatan backup. True hanya bila
                     pemanggil eksplisit minta cadangan. Bila False, field
                     "backup" di return = "" dan pesan error tak referensi
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
    # v2.19.3 — pre-check kunci tulis (Excel terbuka / read-only / sync):
    # gagal cepat dgn pesan jelas SEBELUM kerja tulis jalan (anti tmp
    # file tercecer + koreksi "hilang" — laporan user WinError 5).
    _assert_writable(src, logger=logger)
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
    sheet_name, header_row_0 = _resolve_sheet(src, config=config, logger=logger)
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
        # Map hari + total dari header.
        # v2.18.0 audit (L-5): duplikat header hari ("1" & "1.1") —
        # dulu assignment terus menimpa (LAST wins) padahal pipeline
        # membaca kemunculan PERTAMA (pandas mangling keep-first) →
        # koreksi ditulis ke kolom salah & "hilang" saat re-run.
        # Kini: kemunculan PERTAMA yang dipakai (konsisten pipeline).
        for ci, hv in enumerate(header_vals, start=1):
            if hv is None:
                continue
            if isinstance(hv, float) and hv.is_integer():
                hv = int(hv)
            s = str(hv).strip()
            if s in DAY_COLUMNS and s not in day_col_map:
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
    # v2.18.0 audit: strict decode — errors="replace" menulis U+FFFD
    # kembali ke file (korupsi senyap) utk arsip berkarakter invalid;
    # kini gagal JUJUR sebelum file tersentuh.
    try:
        sheet_xml = sheet_xml_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceWriteError(
            f"Sheet XML sumber bukan UTF-8 valid ({exc}) — tolak menulis "
            f"supaya file tidak rusak. Backup: {bak_msg}.") from exc

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
    # v2.16.2: tmp file name unik per-PID supaya tak race jika 2 thread
    # tulis file sama bersamaan (mitigated UI guard, tapi defense-in-depth).
    tmp_out = src.with_suffix(f".tmp_write.{os.getpid()}")
    try:
        _write_zip_replaced_sheet(src, sheet_xml_path, sheet_xml, tmp_out)
    except SourceWriteError:
        # Bersihkan tmp
        try:
            tmp_out.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    # Ganti file asli dgn tmp — ATOMIK di Windows (MoveFileExW
    # REPLACE_EXISTING); crash/listrik penuh di tengah = file utuh ATAU
    # tmp utuh, tak pernah setengah (anti hancur data senyap).
    # v2.19.3 — RETRY utk kunci transien (AV scan / OneDrive / Excel
    # baru ditutup). v2.19.4 — backoff LEBIH PANJANG (file 9MB + AV
    # Defender bisa pegang handle detik-detikan) + FALLBACK in-place
    # (replace diblokir tapi tulis boleh: ACL deny-delete / atribut
    # aneh) + rescue <nama>_KOREKSI.xlsx bila TOTAL gagal (file hasil
    # tetap terbuka Excel — beda dgn .tmp_write.PID tak dikenal Windows).
    attempts = len(_REPLACE_RETRY_DELAYS) + 1
    last_perm: PermissionError | None = None
    for attempt in range(attempts):
        try:
            os.replace(tmp_out, src)
            last_perm = None
            break
        except PermissionError as exc:
            last_perm = exc
            _log(logger, f"[source_writer] replace gagal (kunci transien?) "
                         f"— percobaan {attempt + 1}/{attempts}: {exc}")
            if attempt < len(_REPLACE_RETRY_DELAYS):
                time.sleep(_REPLACE_RETRY_DELAYS[attempt])
    if last_perm is not None:
        # v2.19.4 — FALLBACK: timpa file asli IN-PLACE (buka r+b + salin
        # tmp + truncate + fsync). Berguna saat os.replace diblokir tapi
        # open-tulis diizinkan (ACL deny-delete; beberapa state AV).
        try:
            _overwrite_in_place(tmp_out, src, logger=logger)
            last_perm = None
        except OSError as ip_exc:
            _log(logger, f"[source_writer] fallback in-place gagal: {ip_exc}")
            recovery = _rescue_result_file(tmp_out, src, logger=logger)
            is_rescue = ("_KOREKSI" in recovery.name
                         and recovery.suffix == src.suffix)
            raise SourceWriteError(
                f"Gagal menimpa file asli dgn hasil tulis: {last_perm}\n"
                f"Umumnya: file '{src.name}' sedang DIBUKA di Excel/program "
                f"lain (mengunci file). TUTUP dulu (Excel: File → Close / "
                f"keluar Excel), lalu klik \"Simpan koreksi\" ulang.\n"
                f"File HASIL (sudah berisi koreksi) aman tersimpan di:\n"
                f"  {recovery}\n"
                + ("— sudah diberi nama _KOREKSI.xlsx: bisa langsung dibuka "
                   "di Excel, atau rename menggantikan file asli setelah "
                   "Excel ditutup.\n" if is_rescue else
                   "— bisa ditukar manual (rename) bila perlu.\n")
                + f"File asli TIDAK berubah. Backup: {bak_msg}."
            ) from ip_exc
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
