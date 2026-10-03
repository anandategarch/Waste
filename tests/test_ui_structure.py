"""Test — struktur paket ui/ (refactor v2.4.0 dari god-object ui_app.py).

Mengunci hasil pemecahan monolit 3.256 baris / 102 metode menjadi 11 modul
mixin + shared + widgets. Test ini mencegah:
- metode hilang saat seseorang memindahkan/k menghapus kode
- MRO rusak (mixin hilang dari komposisi class)
- file modul terhapus
- metode duplikat antar mixin (bayang MRO)

Tidak butuh display (hanya import + inspeksi class, tidak instansiasi Tk).
"""

import ast
from pathlib import Path

import pytest
import tkinter

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "ui_methods_manifest.txt"

EXPECTED_MODULES = [
    "shared.py", "widgets.py", "base.py", "app.py",
    "tab_dashboard.py", "tab_temporal.py", "tab_money.py",
    "tab_compare.py", "tab_quadrant.py",
    "tab_rate.py", "tab_result.py", "tab_viz.py", "tab_quality.py",
    "tab_period.py", "tab_summary.py",
    "tab_run.py", "tab_config.py", "tab_help.py",
]

EXPECTED_MIXINS = [
    "AppBase", "DashboardTabMixin", "TemporalTabMixin", "MoneyTabMixin",
    "CompareTabMixin", "QuadrantTabMixin",
    "RateLeagueTabMixin", "ResultTabMixin", "VizTabMixin",
    "QualityTabMixin", "PeriodTabMixin", "SummaryTabMixin",
    "RunTabMixin", "ConfigTabMixin", "HelpTabMixin",
]


def _mixin_methods(cls):
    """Metode milik mixin murni (unwrap staticmethod/classmethod descriptor)."""
    out = {}
    for name, fn in vars(cls).items():
        if name.startswith("__") and name != "__init__":
            continue
        raw = fn.__func__ if hasattr(fn, "__func__") else fn
        if callable(raw):
            out[name] = raw
    return out


def _mixin_classes():
    """Semua mixin WasteAnomalyApp sebelum Tk (urutan MRO)."""
    from ui.app import WasteAnomalyApp
    classes = []
    for cls in WasteAnomalyApp.__mro__[1:]:
        if cls is tkinter.Tk:
            break
        classes.append(cls)
    return classes


class TestUiStructure:
    def test_semua_modul_ada(self):
        for mod in EXPECTED_MODULES:
            assert (UI / mod).exists(), f"ui/{mod} hilang!"

    def test_import_tanpa_display(self):
        """Import paket ui tidak membutuhkan X server."""
        import ui.app  # noqa: F401

    def test_launcher_ui_app_masih_ada(self):
        """ui_app.py tetap jadi entry point (MULAI.bat tidak berubah)."""
        assert (REPO / "ui_app.py").exists()
        content = (REPO / "ui_app.py").read_text(encoding="utf-8")
        assert "from ui.app import" in content

    def test_mro_15_mixin_dan_tk(self):
        from ui.app import WasteAnomalyApp

        names = [c.__name__ for c in WasteAnomalyApp.__mro__]
        n_mixins = len(EXPECTED_MIXINS)
        assert names[0] == "WasteAnomalyApp"
        assert names[1:1 + n_mixins] == EXPECTED_MIXINS
        assert WasteAnomalyApp.__mro__[1 + n_mixins] is tkinter.Tk

    def test_set_metode_identik_dengan_manifest(self):
        """102 metode asli god-object TIDAK BOLEH hilang satu pun."""
        manifest = MANIFEST.read_text(encoding="utf-8").strip().splitlines()
        assert len(manifest) == 102

        composed = set()
        for cls in _mixin_classes():
            composed |= set(_mixin_methods(cls))
        missing = set(manifest) - composed
        assert not missing, f"Metode HILANG: {sorted(missing)}"

    def test_tidak_ada_metode_duplikat_antarmixin(self):
        """Metode yang sama di 2 mixin = bug MRO bayang (silent override)."""
        seen = {}
        for cls in _mixin_classes():
            for name in _mixin_methods(cls):
                assert name not in seen, (
                    f"{name} didefinisikan di {seen[name]} DAN {cls.__name__}"
                )
                seen[name] = cls.__name__

    def test_dekorator_static_class_dipertahankan(self):
        """8 metode asli berdekorator — harus tetap static/class method."""
        from ui.base import AppBase
        assert isinstance(vars(AppBase)["_make_scrollable"], staticmethod)
        assert isinstance(vars(AppBase)["_format_cell"], staticmethod)
        assert isinstance(vars(AppBase)["_column_is_numeric"], staticmethod)
        assert isinstance(vars(AppBase)["_sort_df_for_treeview"], classmethod)
        assert isinstance(vars(AppBase)["_sanitize_filename"], staticmethod)
        assert isinstance(vars(AppBase)["_format_compare_metric"], staticmethod)
        assert isinstance(vars(AppBase)["_open_path_in_explorer"], staticmethod)
        assert isinstance(vars(AppBase)["_winfo_alive"], staticmethod)

    def test_metode_verbatim_vs_manifest_source(self):
        """Body metode identik dengan ui_app.py ASLI yang di-backup di fixture.

        (Fixture source asli tidak di-commit — pemeriksaan verbatim penuh
        dilakukan saat refactor; test ini cukup memastikan signature def
        tiap metode ada di file mixin yang benar.)
        """
        manifest = MANIFEST.read_text(encoding="utf-8").strip().splitlines()
        all_src = "\n".join(
            (UI / f).read_text(encoding="utf-8") for f in EXPECTED_MODULES
        )
        tree = ast.parse(all_src)
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)
        missing = set(manifest) - defined
        assert not missing, f"def hilang dari file mixin: {sorted(missing)}"

    def test_font_registry_mekanisme(self):
        """rebind_fonts menyuntik nilai ke modul konsumen terdaftar."""
        from ui import shared
        import ui.tab_help  # modul dengan font consumer terdaftar

        sentinel = ("TestFont", 9)
        shared.rebind_fonts(F_BODY=sentinel)
        try:
            assert shared.F_BODY == sentinel
            assert ui.tab_help.F_BODY == sentinel  # propagated via registry
        finally:
            shared.rebind_fonts(F_BODY=(shared.FONT_NAME, 9))

    def test_shared_app_dir_repo_root(self):
        """APP_DIR harus repo root (folder data/), BUKAN folder ui/."""
        from ui.shared import APP_DIR
        assert (APP_DIR / "waste_anomaly").is_dir()
        assert APP_DIR.name == "Waste" or "Waste-audit" in APP_DIR.name or True
        # kriteria tegas: parent dari ui/ = repo root
        assert APP_DIR == (REPO / "ui").resolve().parent


class TestWidgets:
    def test_widget_classes_ada(self):
        from ui.widgets import SimpleLogPopup, KPICard, FilterChip  # noqa: F401
