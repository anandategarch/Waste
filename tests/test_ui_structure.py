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
    "view_anomali.py", "view_followup.py", "view_hari.py",
    "view_periode.py", "view_pipeline.py", "followup_table.py",
]

# File mixin Tkinter lama — TIDAK BOLEH kembali (rebuild = penggantian total)
OLD_MIXIN_FILES = [
    "base.py", "tab_dashboard.py", "tab_temporal.py", "tab_money.py",
    "tab_compare.py", "tab_quadrant.py", "tab_rate.py", "tab_result.py",
    "tab_viz.py", "tab_quality.py", "tab_period.py", "tab_summary.py",
    "tab_run.py", "tab_config.py", "tab_help.py",
]

# View data wajib punya kontrak lazy-render (refresh + on_shown)
# v2.8.0: view_uang / view_peer / view_kualitas dihapus total (8 → 5 tab)
# v2.8.1: view_jelajah / view_waktu dihapus total (5 → 3 tab)
# v2.9.0: view_hari DITAMBAHKAN (tab Hari Mencurigakan — 3 → 4 tab)
# v2.12.0: view_followup DITAMBAHKAN (tab Follow Up — 4 → 5 tab)
DATA_VIEWS = {
    "view_anomali.py": "AnomaliView",
    "view_followup.py": "FollowUpView",
    "view_hari.py": "HariView",
    "view_periode.py": "PeriodeView",
}

# v2.9.0: 3 → 4 tab (+ Hari Mencurigakan); v2.12.0: 4 → 5 (+ Follow Up);
# v2.17.0 rombak P0: urutan alur analisa — Pipeline index 0 (entry point
# muat data), Anomali index 1, drill Hari/Banding index 2-3, Follow Up
# (tindak lanjut) terakhir. v2.18.5: Scorecard Cabang DIHAPUS (6 → 5).
VIEW_TAB_TITLES = [
    "Pipeline", "Anomali", "Hari Mencurigakan",
    "Banding Periode", "Follow Up",
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
        from ui.workers import ExportWorker, HistoryWorker, PipelineWorker
        for cls in (PipelineWorker, ExportWorker, HistoryWorker):
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
        # 5 judul (v2.18.5: Scorecard Cabang dihapus), tidak ada duplikat
        assert len(VIEW_TAB_TITLES) == len(set(VIEW_TAB_TITLES)) == 5

    def test_window_dibangun_offscreen(self):
        """MainWindow + 5 view ter-instantiate tanpa display (smoke).

        Judul dibandingkan tanpa badge '(N)' — bila followup.json ada
        isinya (app pernah dijalankan di repo), tab Follow Up tampil
        'Follow Up (N)' yang tetap sah. v2.18.5: tab Scorecard Cabang
        dihapus (6 → 5)."""
        import sys
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.app import MainWindow
        win = MainWindow()
        assert win._tabs.count() == 5
        for i in range(5):
            assert win._tabs.tabText(i).split(" (")[0] == VIEW_TAB_TITLES[i]
        win.close()


class TestWidgets:
    def test_widget_classes_ada(self):
        from ui.widgets import (  # noqa: F401
            Card, DataTable, KpiCard, KpiStrip, StatusChip, WLabel,
            status_chip_for,
        )

    def test_infra_chart_dihapus_dari_widgets(self):
        """v2.8.1: MplCanvas/ChartCard/place_charts_responsive hanya dipakai
        view Jelajah & Waktu (dihapus total) — widget chart ikut bersih +
        import matplotlib hilang dari jalur start-up UI."""
        import ui.widgets as w
        for name in ("MplCanvas", "ChartCard", "place_charts_responsive"):
            assert not hasattr(w, name), (
                f"widgets.{name} masih ada — infrastruktur chart mati")
        src = (REPO / "ui" / "widgets.py").read_text(encoding="utf-8")
        assert "from matplotlib" not in src, (
            "widgets.py masih mengimpor matplotlib (chart infra sudah mati)")
        assert "import matplotlib" not in src, (
            "widgets.py masih mengimpor matplotlib (chart infra sudah mati)")


class TestSetupBatContract:
    """v2.8.2 — kontrak SETUP.bat ↔ requirements.txt.

    Akar bug v2.8.1: matplotlib dihapus dari requirements.txt, tetapi
    langkah [5/5] Verifikasi SETUP.bat masih `import matplotlib` →
    setup "gagal" padahal instalasi sukses (error user nyata di
    Windows). Kontrak ini mengunci baris verifikasi agar selalu
    sinkron dengan requirements.txt.
    """

    def _verification_line(self) -> str:
        setup = (REPO / "SETUP.bat").read_text(encoding="utf-8")
        # Baris verifikasi final [5/5] = satu-satunya -c import yang
        # mencetak penanda 'OK:' (baris -c "import sys..." di langkah
        # lain tidak dihitung).
        lines = [l for l in setup.splitlines()
                 if '" -c "import ' in l and "print('OK:" in l]
        assert len(lines) == 1, (
            "SETUP.bat harus punya tepat 1 baris verifikasi -c import")
        return lines[0]

    def test_verifikasi_import_sesuai_requirements(self):
        """Modul yang diimpor baris verifikasi = paket di requirements.txt."""
        ver = self._verification_line()
        mods = ver.split("import ", 1)[1].split(";", 1)[0]
        imported = {m.strip() for m in mods.split(",")}
        # calamine: nama modul ≠ nama distribusi
        dist_map = {"python_calamine": "python-calamine"}
        imported_dist = {dist_map.get(m, m.lower()) for m in imported}
        req = set()
        for line in (REPO / "requirements.txt").read_text(
                encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split(">")[0].split("<")[0].split("=")[0].split("!")[0]
            req.add(name.strip().lower())
        assert imported_dist == req, (
            f"verifikasi SETUP.bat ({sorted(imported_dist)}) != "
            f"requirements.txt ({sorted(req)}) — dependensi berubah tanpa "
            "menyamakan langkah verifikasi installer (bug v2.8.1)")

    def test_tanpa_referensi_paket_terhapus(self):
        """SETUP.bat/MULAI.bat tidak menyebut paket yang sudah dihapus."""
        for name in ("SETUP.bat", "MULAI.bat"):
            src = (REPO / name).read_text(encoding="utf-8").lower()
            for dead in ("matplotlib", "seaborn", "tkinter"):
                assert dead not in src, (
                    f"{name} masih menyebut '{dead}' — paket sudah dihapus "
                    "dari dependensi (jangan biarkan referensi basi)")
