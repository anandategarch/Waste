"""test_v2162_audit_fixes.py — tests untuk bug fix hasil deep audit v2.16.2.

Mengunci regression untuk bug kritis yg ditemukan audit:
  - A1: self-closing cell regex korupsi cell sebelah
  - A2: t="inlineStr"/"b" tidak ditolak
  - D-C1: _resolve_sheet hardcoded header_row=0 (shifted file break)
  - D-H1: promote path __SRC_ROW offset untested
  - D-H2: __SRC_ROW pipeline survival untested
  - write_day_edits basic + backup=False + verifikasi
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

REPO = Path(__file__).resolve().parent.parent


# ============================================================
# [A1] Self-closing cell regex — TIDAK korupsi cell sebelah
# ============================================================

class TestSelfClosingCellRegex:
    """v2.16.2 BUG A1: regex lama `[^>]*` menelan `/` di self-closing
    cell → match `</c>` cell SEBELAHNYA → korupsi cell lain.
    Fix: attrs pattern `[^>/]*` exclude `/`."""

    def test_self_closing_cell_ditangani_benar(self):
        """Edit cell self-closing → konversi ke sel lengkap dgn <v>,
        TIDAK menyentuh cell sebelah."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        # Row: I3=value, J3=self-closing(empty styled), K3=value
        row = ('<row r="3">'
               '<c r="I3"><v>100</v></c>'
               '<c r="J3" s="5"/>'
               '<c r="K3"><v>300</v></c>'
               '</row>')
        out, found, old = _replace_cell_v_xml(row, "J3", "250")
        assert found, "J3 harus ditemukan"
        assert old is None, "J3 self-closing tak punya old value"
        # J3 dikonversi ke sel lengkap dgn <v>250</v>
        assert '<c r="J3" s="5"><v>250</v></c>' in out
        # I3 dan K3 TIDAK berubah
        assert '<c r="I3"><v>100</v></c>' in out
        assert '<c r="K3"><v>300</v></c>' in out

    def test_self_closing_cell_tidak_match_cell_sebelah(self):
        """Sebelum fix: regex match `</c>` cell K3 → old=300 (K3's value),
        K3 ditimpa 250 (SALAH). Kini: J3 diupdate, K3 utuh."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        row = ('<row r="3">'
               '<c r="I3"><v>100</v></c>'
               '<c r="J3" s="5"/>'
               '<c r="K3"><v>300</v></c>'
               '</row>')
        out, found, old = _replace_cell_v_xml(row, "J3", "250")
        # K3 nilai 300 HARUS utuh (sebelum fix: jadi 250)
        assert '<c r="K3"><v>300</v></c>' in out, \
            "K3 tidak boleh tersentuh (bug lama: korupsi cell sebelah)"

    def test_cell_biasa_dengan_value_tetap_berfungsi(self):
        """Cell dgn <v> existing → ganti nilai, preserve atribut."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        xml = '<c r="I3" s="3"><v>1005</v></c>'
        out, found, old = _replace_cell_v_xml(xml, "I3", "9999")
        assert found and old == "1005"
        assert '<c r="I3" s="3"><v>9999</v></c>' in out

    def test_cell_dengan_formula_preserve_f(self):
        """Cell TOTAL dgn <f> formula → update <v>, PRESERVE <f>."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        xml = '<c r="AP3"><f t="shared" si="0"/><v>20610</v></c>'
        out, found, old = _replace_cell_v_xml(xml, "AP3", "29559")
        assert found and old == "20610"
        assert '<f t="shared" si="0"/>' in out, "<f> formula harus preserve"
        assert '<v>29559</v>' in out


# ============================================================
# [A2] t="inlineStr"/"b"/"e" rejection
# ============================================================

class TestNonNumericCellRejection:
    """v2.16.2 BUG A2: substring check 't="s"' lolos 't="inlineStr"' & 't="b"'.
    Fix: regex extract t= value, tolak jika bukan "n"."""

    @pytest.mark.parametrize("tval", ["s", "str", "inlineStr", "b", "e"])
    def test_non_numeric_t_ditolak(self, tval):
        from waste_anomaly.source_writer import _replace_cell_v_xml, SourceWriteError
        xml = f'<c r="I3" t="{tval}"><v>100</v></c>'
        with pytest.raises(SourceWriteError, match="non-numerik"):
            _replace_cell_v_xml(xml, "I3", "250")

    def test_t_numeric_diperbolehkan(self):
        """t="n" (numeric explicit) → allowed."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        xml = '<c r="I3" t="n"><v>100</v></c>'
        out, found, old = _replace_cell_v_xml(xml, "I3", "250")
        assert found and old == "100"

    def test_tidak_ada_attr_t_diperbolehkan(self):
        """Cell tanpa t= attr (default numeric) → allowed."""
        from waste_anomaly.source_writer import _replace_cell_v_xml
        xml = '<c r="I3"><v>100</v></c>'
        out, found, old = _replace_cell_v_xml(xml, "I3", "250")
        assert found and old == "100"


# ============================================================
# [D-C1] Shifted-header file — write_day_edits works
# ============================================================

def _build_shifted_rekap(fp: Path) -> None:
    """Build file dgn title row 1, blank row 2, header row 3, data row 4+."""
    wb = Workbook()
    ws = wb.active
    ws.title = "REKAP MENTAH"
    ws.append(["REKAP WASTE BULANAN — JUDUL"])  # row 1 title
    ws.append([None])  # row 2 blank
    hdr = (["KATEGORI", "SOURCE DATA", "JENIS", "STATUS", "NAMA BARANG",
            "KETERANGAN", "PENYEBAB TERJADINYA WASTE", "SATUAN"]
           + list(range(1, 32))
           + ["NAMA RESTO", "PIC", "TOTAL"])
    ws.append(hdr)  # row 3 header
    ws.append(["c", "w", "WASTE", "d", "I A", "O", "IA", "GR"]
              + [100, 200, 300] + [0] * 28
              + ["R", "P", 600])  # row 4 data
    wb.save(fp)


class TestShiftedHeaderWrite:
    """v2.16.2 BUG D-C1: _resolve_sheet hardcoded header_row=0 →
    shifted-header file gagal (header di row 3, bukan row 1).
    Fix: pakai find_rekap_sheet yg detect header row sesungguhnya."""

    def test_write_ke_shifted_header_file(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "shifted.xlsx"
        _build_shifted_rekap(fp)
        # Edit Excel row 4 (data row): day 1 = 100 → 777
        result = write_day_edits(fp, src_row=4, day_edits={"1": 777.0},
                                 backup=False)
        assert result["ok"]
        assert result["cells_written"] == 1
        assert result["total_new"] == 1277.0  # 600 - 100 + 777
        # Verify
        wb = load_workbook(fp, read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        r4 = next(ws.iter_rows(min_row=4, max_row=4, values_only=True))
        assert r4[8] == 777, f"day1 should be 777, got {r4[8]}"
        assert r4[41] == 1277, f"TOTAL should be 1277, got {r4[41]}"
        wb.close()

    def test_title_row_tidak_tertulis(self, tmp_path):
        """Title row (row 1) TIDAK boleh berubah."""
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "shifted.xlsx"
        _build_shifted_rekap(fp)
        write_day_edits(fp, src_row=4, day_edits={"1": 777.0}, backup=False)
        wb = load_workbook(fp, read_only=True, data_only=True)
        ws = wb["REKAP MENTAH"]
        r1 = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        assert r1[0] == "REKAP WASTE BULANAN — JUDUL", "title row rusak"
        wb.close()


# ============================================================
# [D-H1] Promote path __SRC_ROW offset
# ============================================================

class TestSrcRowPromoteOffset:
    """v2.16.2 BUG D-H1: promote path __SRC_ROW offset untested.
    Offset = hr+2 (hr = grid row header ditemukan)."""

    def test_promote_offset_benar(self, tmp_path):
        """Shifted file: title r1, blank r2, header r3, data r4+ →
        __SRC_ROW = [4, 5, ...] (data Excel mulai row 4)."""
        from waste_anomaly.loader import _read_excel_fast
        from waste_anomaly.rekap_import import ensure_rekap_header, SRC_ROW_COL
        fp = tmp_path / "shifted.xlsx"
        _build_shifted_rekap(fp)
        df = _read_excel_fast(fp, sheet_name="REKAP MENTAH", header=0)
        out = ensure_rekap_header(df)
        assert SRC_ROW_COL in out.columns
        # 1 data row → __SRC_ROW = [4] (Excel row 4)
        assert list(out[SRC_ROW_COL]) == [4], \
            f"promote offset salah: dapat {list(out[SRC_ROW_COL])}, expect [4]"


# ============================================================
# [D-H2] __SRC_ROW survival through pipeline
# ============================================================

class TestSrcRowPipelineSurvival:
    """v2.16.2 BUG D-H2: __SRC_ROW survival through pipeline untested."""

    def test_src_row_survive_pipeline(self, tmp_path):
        """run_pipeline → s['df'] HARUS punya __SRC_ROW."""
        from waste_anomaly.pipeline import run_pipeline
        from waste_anomaly.rekap_import import SRC_ROW_COL
        fp = tmp_path / "shifted.xlsx"
        _build_shifted_rekap(fp)
        s = run_pipeline(str(fp), key_akhir=31)
        assert s["success"], s.get("error", "")
        df = s["df"]
        assert SRC_ROW_COL in df.columns, \
            f"__SRC_ROW hilang dari pipeline output. cols: {list(df.columns[:15])}"
        # Semua nilai __SRC_ROW ≥ 2 (contract source_writer)
        assert (df[SRC_ROW_COL] >= 2).all(), \
            "__SRC_ROW harus ≥2 (baris 1 = header)"
        # Tidak ada NaN
        assert not df[SRC_ROW_COL].isna().any(), "__SRC_ROW tidak boleh NaN"


# ============================================================
# write_day_edits — basic + backup=False + verifikasi
# ============================================================

def _build_normal_rekap(fp: Path, n_rows: int = 3) -> None:
    """Build file normal: header row 1, data row 2+."""
    wb = Workbook()
    ws = wb.active
    ws.title = "REKAP MENTAH"
    hdr = (["KATEGORI", "SOURCE DATA", "JENIS", "STATUS", "NAMA BARANG",
            "KETERANGAN", "PENYEBAB TERJADINYA WASTE", "SATUAN"]
           + list(range(1, 32))
           + ["NAMA RESTO", "PIC", "TOTAL"])
    ws.append(hdr)
    for i in range(n_rows):
        ws.append(["c", "w", "WASTE", "d", f"I{i}", "O", "IA", "GR"]
                  + [100 * (i + 1), 200, 300] + [0] * 28
                  + ["R", "P", 600 * (i + 1)])
    wb.save(fp)


class TestWriteDayEditsBasic:
    """Test dasar write_day_edits — normal + error cases."""

    def test_write_normal_file(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        result = write_day_edits(fp, src_row=2, day_edits={"1": 999.0},
                                 backup=False)
        assert result["ok"]
        assert result["cells_written"] == 1
        assert result["total_new"] == 1499.0  # 600 - 100 + 999
        wb = load_workbook(fp, read_only=True, data_only=True)
        r2 = next(wb["REKAP MENTAH"].iter_rows(min_row=2, max_row=2,
                                               values_only=True))
        assert r2[8] == 999
        assert r2[41] == 1499
        wb.close()

    def test_backup_false_tidak_buat_backup(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        write_day_edits(fp, src_row=2, day_edits={"1": 999.0}, backup=False)
        baks = list(tmp_path.glob("*.bak-*"))
        assert len(baks) == 0, "backup=False tidak boleh buat backup"

    def test_backup_true_buat_backup(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        result = write_day_edits(fp, src_row=2, day_edits={"1": 999.0},
                                 backup=True)
        baks = list(tmp_path.glob("*.bak-*"))
        assert len(baks) == 1, "backup=True harus buat 1 backup"
        assert result["backup"] != ""

    def test_src_row_header_ditolak(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits, SourceWriteError
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        with pytest.raises(SourceWriteError, match="≥2"):
            write_day_edits(fp, src_row=1, day_edits={"1": 5.0})

    def test_nilai_negatif_ditolak(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits, SourceWriteError
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        with pytest.raises(SourceWriteError, match="negatif"):
            write_day_edits(fp, src_row=2, day_edits={"1": -5.0})

    def test_hari_invalid_ditolak(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits, SourceWriteError
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        with pytest.raises(SourceWriteError, match="invalid"):
            write_day_edits(fp, src_row=2, day_edits={"99": 5.0})

    def test_edits_kosong_ditolak(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits, SourceWriteError
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        with pytest.raises(SourceWriteError, match="kosong"):
            write_day_edits(fp, src_row=2, day_edits={})

    def test_multi_edit_dan_total_recompute(self, tmp_path):
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp)
        # Edit day 1 (100→500) + day 13 (0→200)
        result = write_day_edits(fp, src_row=2,
                                 day_edits={"1": 500.0, "13": 200.0},
                                 backup=False)
        assert result["cells_written"] == 2
        # TOTAL = 600 - 100 - 0 + 500 + 200 = 1200
        assert result["total_new"] == 1200.0
        wb = load_workbook(fp, read_only=True, data_only=True)
        r2 = next(wb["REKAP MENTAH"].iter_rows(min_row=2, max_row=2,
                                               values_only=True))
        assert r2[8] == 500  # day 1
        assert r2[20] == 200  # day 13
        assert r2[41] == 1200  # TOTAL
        wb.close()

    def test_baris_lain_tidak_tertulis(self, tmp_path):
        """Edit row 2 → row 3 HARUS utuh."""
        from waste_anomaly.source_writer import write_day_edits
        fp = tmp_path / "normal.xlsx"
        _build_normal_rekap(fp, n_rows=3)
        write_day_edits(fp, src_row=2, day_edits={"1": 999.0}, backup=False)
        wb = load_workbook(fp, read_only=True, data_only=True)
        r3 = next(wb["REKAP MENTAH"].iter_rows(min_row=3, max_row=3,
                                               values_only=True))
        assert r3[8] == 200, "row 3 day1 harus utuh (200)"
        assert r3[41] == 1200, "row 3 TOTAL harus utuh (1200)"
        wb.close()
