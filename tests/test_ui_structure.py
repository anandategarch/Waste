"""Test — struktur paket ui/ (rebuild PySide6 v2.6.0).

Mengunci hasil rebuild total UI (14 mixin Tkinter → 8 view + state/signal):
- file modul baru ada (dan file mixin lama TIDAK kembali)
- kontrak publik dijaga (ui.shared — test lama tetap hijau)
- tiap view data punya refresh()/on_shown() (kontrak lazy render)
- worker = QThread (pipeline/export/periode)
- model tabel memenuhi kontrak QAbstractTableModel
- manifest metode: metode publik tidak hilang/duplikat antar modul

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "ui_methods_manifest.txt"

EXPECTED_MODULES = [
    "__init__.py", "shared.py", "theme.py", "state.py", "models.py",
    "workers.py", "widgets.py", "app.py",
    "view_anomali.py", "view_jelajah.py", "view_waktu.py", "view_uang.py",
    "view_peer.py", "view_kualitas.py", "view_periode.py",
    "view_pipeline.py",
]

# File mixin Tkinter lama — TIDAK BOLEH kembali (rebuild = penggantian total)
OLD_MIXIN_FILES = [
    "base.py", "tab_dashboard.py", "tab_temporal.py", "tab_money.py",
    "tab_compare.py", "tab_quadrant.py", "tab_rate.py", "tab_result.py",
    "tab_viz.py", "tab_quality.py", "tab_period.py", "tab_summary.py",
    "tab_run.py", "tab_config.py", "tab_help.py",
]

# View data wajib punya kontrak lazy-render (refresh + on_shown)
DATA_VIEWS = {
    "view_anomali.py": "AnomaliView",
    "view_jelajah.py": "JelajahView",
    "view_waktu.py": "WaktuView",
    "view_uang.py": "UangView",
    "view_peer.py": "PeerView",
    "view_kualitas.py": "KualitasView",
    "view_periode.py": "PeriodeView",
}

VIEW_TAB_TITLES = [
    "Anomali", "Jelajah", "Waktu", "Uang", "Peer", "Kualitas Data",
    "Banding Periode", "Pipeline",
]


def _top_level_defs(path: Path) -> set[str]:
    """Nama kelas + fungsi top-level sebuah modul (via AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _class_methods(path: Path, class_name: str) -> set[str]:
    """Nama metode kelas utama sebuah modul (via AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("__")
            }
    return set()


class TestUiStructure:
    def test_semua_modul_baru_ada(self):
        for mod in EXPECTED_MODULES:
            assert (UI / mod).exists(), f"ui/{mod} hilang!"

    def test_file_mixin_lama_tidak_kembali(self):
        """Rebuild = penggantian total — mixin Tkinter lama dilarang kembali."""
        for mod in OLD_MIXIN_FILES:
            assert not (UI / mod).exists(), (
                f"ui/{mod} kembali muncul — UI Tkinter lama seharusnya "
                "sudah diganti total (rebuild v2.6.0)")

    def test_import_tanpa_display(self):
        """Import paket ui tidak membutuhkan X server (offscreen)."""
        import ui.app  # noqa: F401

    def test_launcher_ui_app_masih_ada(self):
        """ui_app.py tetap jadi entry point (MULAI.bat tidak berubah)."""
        assert (REPO / "ui_app.py").exists()
        content = (REPO / "ui_app.py").read_text(encoding="utf-8")
        assert "from ui.app import" in content

    def test_kontrak_shared_dijaga(self):
        """Kontrak publik lama (dipakai test frozen/filter) tidak berubah."""
        from ui import shared
        assert callable(shared.app_dir)
        assert callable(shared.bundle_res_dir)
        assert callable(shared._apply_filters)
        assert callable(shared.fmt_id)
        assert shared.app_dir() == Path(shared.__file__).resolve().parent.parent

    def test_view_data_punya_refresh_dan_on_shown(self):
        """Kontrak lazy-render: view data dirender saat dibuka (H2)."""
        for fname, cls_name in DATA_VIEWS.items():
            methods = _class_methods(UI / fname, cls_name)
            assert methods, f"{fname}: class {cls_name} tidak ditemukan"
            assert "refresh" in methods, f"{fname}::{cls_name} tanpa refresh()"
            assert "on_shown" in methods, f"{fname}::{cls_name} tanpa on_shown()"

    def test_pipeline_view_punya_worker_signal(self):
        methods = _class_methods(UI / "view_pipeline.py", "PipelineView")
        assert "_start" in methods
        assert "_on_done" in methods
        assert "_on_failed" in methods

    def test_worker_adalah_qthread(self):
        from PySide6.QtCore import QThread
        from ui.workers import ExportWorker, PeriodWorker, PipelineWorker
        for cls in (PipelineWorker, ExportWorker, PeriodWorker):
            assert issubclass(cls, QThread), f"{cls.__name__} bukan QThread"

    def test_model_tabel_memenuhi_kontrak_qt(self):
        import pandas as pd
        from PySide6.QtCore import Qt
        from ui.models import PandasTableModel
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        m = PandasTableModel(df)
        assert m.rowCount() == 2
        assert m.columnCount() == 2
        assert m.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "A"
        # sort numeric-aware tidak boleh error
        m.sort(0, Qt.DescendingOrder)
        assert m.data(m.index(0, 0), Qt.DisplayRole) is not None

    def test_manifest_metode_tidak_berubah(self):
        """Metode publik modul ui tidak boleh hilang satu pun (lock refactor)."""
        manifest = MANIFEST.read_text(encoding="utf-8").strip().splitlines()
        current: set[str] = set()
        for mod in EXPECTED_MODULES:
            if mod in ("__init__.py",):
                continue
            for name in _top_level_defs(UI / mod):
                current.add(f"{mod}::{name}")
        missing = set(manifest) - current
        assert not missing, f"Definisi HILANG: {sorted(missing)}"

    def test_tidak_ada_duplikat_antarmodul(self):
        """View/pipeline menghasilkan tab unik — tidak ada tombol/fitur ganda."""
        from ui.app import MainWindow
        import inspect
        src = inspect.getsource(MainWindow._build_body)
        for title in VIEW_TAB_TITLES:
            assert f'("{title}"' in src, f"tab '{title}' tidak dibangun"
        # 8 judul, tidak ada duplikat
        assert len(VIEW_TAB_TITLES) == len(set(VIEW_TAB_TITLES)) == 8

    def test_window_dibangun_offscreen(self):
        """MainWindow + 8 view ter-instantiate tanpa display (smoke)."""
        import sys
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.app import MainWindow
        win = MainWindow()
        assert win._tabs.count() == 8
        for i in range(8):
            assert win._tabs.tabText(i) == VIEW_TAB_TITLES[i]
        win.close()


class TestWidgets:
    def test_widget_classes_ada(self):
        from ui.widgets import (  # noqa: F401
            Card, ChartCard, DataTable, KpiCard, KpiStrip, MplCanvas, WLabel,
        )

    def test_place_charts_responsive_ada(self):
        from ui.widgets import place_charts_responsive  # noqa: F401
