"""Test — fix wave 4 v2.7.0 (release sweep: manifest dua-arah, lantai
header tabel, fmt_id None, Pareto string-TOTAL, konsistensi versi).

Mengunci temuan audit V26 gelombang akhir:
- V26-M18: manifest metode paket ui/ kini DUA-ARAH — definisi aktual
  (AST, top-level per modul) harus SAMA PERSIS dengan manifest (0 hilang,
  0 lebih). Menambah def baru tanpa update manifest → test GAGAL.
- V26-M17: jaminan anti-terpotong DataTable tingkah-laku: (a) lantai lebar
  kolom tampak ≥ horizontalAdvance(header)+26 (formula _auto_columns);
  (b) narrow_hide menyembunyikan kolom di viewport sempit + memunculkannya
  kembali saat melebar; (c) setColumnWidth manual (guard _in_fit mati)
  menjadwalkan refit debounce. (Tabel >3000 baris wrap-mati + ElideRight
  sudah dikunci tests/test_v270_wave2.py::TestV270BigTableWrap.)
- V26-L2 : fmt_id(None) → '' (dulu 'None' bocor ke label).
- Pareto Alasan: TOTAL string di-koersi numerik (konsisten dgn 'Per
  Cabang'/'Top Items' wave-1) — jumlah baris tak lagi tersambung jadi teks.
- V26-M13: versi 2.7.0 tunggal di 3 situs (shared.py, __init__.py,
  config.json).

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6
(pola tests/test_ui_structure.py).
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

from ui.shared import fmt_id

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "ui_methods_manifest.txt"

EXPECTED_MODULES = [
    "__init__.py", "shared.py", "theme.py", "state.py", "models.py",
    "workers.py", "widgets.py", "app.py",
    "view_anomali.py", "view_followup.py", "view_hari.py",
    "view_periode.py", "view_pipeline.py", "followup_table.py",
]


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


def _top_level_defs(path: Path) -> set[str]:
    """Nama kelas + fungsi top-level sebuah modul (via AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _current_defs() -> set[str]:
    """Definisi top-level aktual seluruh modul ui/ (format manifest)."""
    current: set[str] = set()
    for mod in EXPECTED_MODULES:
        if mod == "__init__.py":
            continue
        for name in _top_level_defs(UI / mod):
            current.add(f"{mod}::{name}")
    return current


# ============================================================
# V26-M18 — MANIFEST DUA-ARAH
# ============================================================

class TestManifestDuaArah:
    """test_ui_structure.py hanya memeriksa manifest ⊆ kode (def hilang).
    Arah SEBALIKNYA kini dikunci: kode ⊆ manifest — def BARU tanpa update
    manifest (atau sisa def yang sudah dihapus) gagal test ini."""

    def test_def_aktual_sama_persis_dengan_manifest(self):
        manifest = set(MANIFEST.read_text(encoding="utf-8").strip().splitlines())
        current = _current_defs()
        missing = manifest - current
        extra = current - manifest
        assert not missing and not extra, (
            f"manifest ≠ kode — HILANG (manifest tanpa def): {sorted(missing)}; "
            f"LEBIH (def tanpa manifest): {sorted(extra)}. "
            "Update tests/fixtures/ui_methods_manifest.txt.")

    def test_def_baru_tanpa_manifest_terdeteksi(self):
        """Simulasi regresi: def baru muncul di kode tanpa update manifest →
        diff dua-arah HARUS melaporkannya (yaitu test di atas akan gagal)."""
        manifest = set(MANIFEST.read_text(encoding="utf-8").strip().splitlines())
        tampered = _current_defs() | {"view_pipeline.py::def_baru_tanpa_manifest"}
        extra = tampered - manifest
        assert extra == {"view_pipeline.py::def_baru_tanpa_manifest"}, extra

    def test_manifest_tanpa_duplikat(self):
        lines = MANIFEST.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == len(set(lines)), "manifest punya entri duplikat"


# ============================================================
# V26-M17 — ANTI-TERPOTONG TINGKAH-LAKU (offscreen)
# ============================================================

class TestLantaiHeader:
    """Kolom TAMPAK tidak pernah menyusut di bawah lantai teks header —
    formula _auto_columns: floor = min(max(84, advance(header)+26), 420)."""

    def test_lebar_kolom_tampak_ge_lantai_header(self):
        from PySide6.QtCore import Qt
        _qapp()
        from ui.widgets import DataTable
        df = pd.DataFrame({
            "ANOMALY SCORE": [17, 5],
            "NAMA RESTO": ["RESTO.PWKTAM", "RESTO.KWGGAL"],
            "NAMA BARANG": ["Bawang Putih", "Tepung"],
            "KETERANGAN": ["Cancel Nota", "Handling"],
            "TOTAL": [290.0, 327.0],
        })
        t = DataTable()
        t.resize(700, 300)  # menyekit: kolom tertekan ke lantai
        t.set_dataframe(df)
        fm = t.fontMetrics()
        for c in range(t.model().columnCount()):
            if t.isColumnHidden(c):
                continue
            name = str(t.model().headerData(c, Qt.Horizontal))
            floor = min(max(84, fm.horizontalAdvance(name) + 26), 420)
            assert t.columnWidth(c) >= floor, (
                f"kolom '{name}' lebar {t.columnWidth(c)} < lantai {floor}")

    def test_lantai_header_juga_di_viewport_sangat_sempit(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        _qapp()
        app = QApplication.instance()
        from ui.widgets import DataTable
        df = pd.DataFrame({
            "ANOMALY SCORE": [17],
            "ANOMALY STATUS": ["Prioritas Tinggi"],
            "NAMA RESTO": ["RESTO.PWKTAM"],
            "NAMA BARANG": ["Bawang Putih"],
        })
        t = DataTable()
        t.set_dataframe(df)
        t.resize(320, 200)
        app.processEvents()
        t._auto_columns()
        fm = t.fontMetrics()
        for c in range(t.model().columnCount()):
            if t.isColumnHidden(c):
                continue
            name = str(t.model().headerData(c, Qt.Horizontal))
            floor = min(max(84, fm.horizontalAdvance(name) + 26), 420)
            assert t.columnWidth(c) >= floor, name


class TestNarrowHidePulih:
    """narrow_hide murni (tanpa visible_cols): kolom boleh-disebunyikan
    hilang di viewport sempit DAN muncul kembali saat melebar."""

    def test_jenis_tersembunyi_saat_sempit_muncul_saat_lebar(self):
        from PySide6.QtWidgets import QApplication
        _qapp()
        app = QApplication.instance()
        from ui.widgets import DataTable
        df = pd.DataFrame({
            "A": ["x"],
            "JENIS": ["WASTE"],
            "B": ["y"],
            "C": ["z"],
            "D": ["w"],
        })
        t = DataTable()
        t.set_dataframe(df, narrow_hide=["JENIS"])
        t.resize(210, 200)  # Σ lantai 5 kolom > avail → JENIS disembunyikan
        app.processEvents()
        t._auto_columns()
        j = list(df.columns).index("JENIS")
        assert t.isColumnHidden(j), "JENIS seharusnya disembunyikan saat sempit"
        # melebar → semua lantai muat → JENIS kembali tampil
        t.resize(900, 400)
        app.processEvents()
        t._auto_columns()
        assert not t.isColumnHidden(j), "JENIS seharusnya tampil lagi saat lebar"


class TestRefitTerjadwal:
    """setColumnWidth manual (guard _in_fit mati) → debounce refit aktif.
    (Komplemen test_v270_wave2::test_resize_kolom_manual_memicu_refit_
    terjadwal yang memakai header.resizeSection — jalur sinyal sama.)"""

    def test_setcolumnwidth_memicu_timer_refit(self):
        _qapp()
        from ui.widgets import DataTable
        t = DataTable()
        t.set_dataframe(pd.DataFrame({
            "A": ["teks yang sangat panjang sekali ini " * 2] * 3,
            "B": ["x"] * 3,
        }))
        t.resize(900, 400)
        t._auto_columns()
        assert not t._refit_timer.isActive()  # lebar auto-fit tak menjadwal
        assert not t._in_fit                  # guard mati (bukan auto-fit)
        # v2.9.0: jendela tenang 300ms pasca-fit menelan resize deferred
        # Qt internal — tirukan drag user SETELAH jendela itu lewat.
        import time
        t._fit_ts = time.monotonic() - 1.0
        t.setColumnWidth(0, 60)               # resize manual ala user
        assert t._refit_timer.isActive()


# ============================================================
# V26-L2 — fmt_id(None)
# ============================================================

class TestFmtIdNone:
    def test_none_menghasilkan_string_kosong(self):
        assert fmt_id(None) == ""
        assert fmt_id(None, 2) == ""

    def test_perilaku_lain_tak_berubah(self):
        assert fmt_id(25901) == "25.901"
        assert fmt_id(9333117.5, 1) == "9.333.117,5"
        assert fmt_id(float("nan")) == ""
        assert fmt_id("bukan angka") == "bukan angka"


# ============================================================
# Pareto Alasan — TOTAL string di-koersi numerik (v2.7.0)
# ============================================================
# DIHAPUS v2.8.1: _build_derived_sheets dihapus dari ui/state.py —
# satu-satunya konsumen view Jelajah (dihapus total); koersi numerik
# TOTAL/MAX yang sejenis tetap terkunci di workers._extra_sheets path
# (tests/test_priority.py / test_data_quality.py / test_temporal.py).


# ============================================================
# V26-M13 — versi tunggal di 3 situs
# ============================================================

class TestVersiSync:
    def test_versi_sama_di_tiga_situs(self):
        """v2.10.0: versi disinkronkan di ui/shared.py, __init__.py, dan
        config.json (ganti nama kelas dari TestVersi270 — angka versi
        berubah tiap rilis, lock-nya cukup 'ketiga situs SAMA')."""
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        cfg = json.loads(
            (REPO / "waste_anomaly" / "config.json").read_text(encoding="utf-8"))
        assert APP_VERSION == __version__ == cfg.get("version") == "2.17.0"
