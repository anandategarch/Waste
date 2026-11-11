"""test_v2138.py — regresi Gelombang C deep-audit v2.13.8 (bersih-bersih).

Sumber: audit menyeluruh dead-code (laporan audit-B-engine.md §2 +
audit-A-ui.md §1). Gelombang C = PENGHAPUSAN mati-total + konsolidasi —
bukan perubahan perilaku (semua perilaku hidup tetap dikunci test lama).

- [M] MIXIN: 10 metode kembar AnomaliView ⇄ HariView (±250 baris ×2)
  kini SATU sumber ui/followup_table.py (FollowupTableMixin) — kunci:
  resolusi metode ke mixin, _DISP_LRU per-view (8/4), HF_COLS tunggal.
- [D] DEAD CODE ENGINE: utils 17 fungsi mati, modul filters.py (yatim
  sejak sidebar v2.12.4), install_tk_exception_hook/tk_suppressed (era
  Tkinter) — semua DILARANG kembali.
- [S] DEAD CODE STATE/FITUR MATI: set_search/set_day_range/
  set_filters_multi/invalidate_filter_cache/filter_summary/CHIP_LABELS +
  _build_search_blob + mesin search/hari-range — kotak cari & rentang
  hari dihapus dari UI sejak v2.12.4 (audit D11).
- [V] DEAD CODE UI: PipelineView.set_workbook, ScorecardView.SC_COLS,
  ui/__init__ lazy-export.
- [F] FIX E5: mutasi ✓ view_periode kini lewat notify_column_changed
  (sinkron snapshot numpy — dulu dataChanged manual mem-bypass).

Konvensi repo: test yang mengunci API dihapus ditulis ulang jadi
KUNCI KETIADAAN (pola test_v270_wave2 §"sidebar dihapus").
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _src(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


# ============================================================
# [M] KONSOLIDASI KEMBAR — satu sumber FollowupTableMixin
# ============================================================

class TestMixinKonsolidasi:
    def test_kedua_view_mewarisi_mixin(self):
        _qapp()
        from ui.followup_table import FollowupTableMixin
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        assert issubclass(AnomaliView, FollowupTableMixin)
        assert issubclass(HariView, FollowupTableMixin)
        # v2.19.0 — AnomaliView MEN-OVERRIDE beberapa metode mixin utk
        # tampilan GRUP per item×cabang (sampel user). Override: _display_df,
        # _refresh_check_col, _on_check_toggled, _on_check_all. Metode LAIN
        # tetap di-share via mixin (HariView sepenuhnya pakai mixin).
        shared = ("_mask_local", "_on_followup_changed",
                  "_on_header_filter", "_hf_state", "_on_clear_filters",
                  "_fps_for", "_on_selection")
        for m in shared:
            assert getattr(AnomaliView, m) is getattr(FollowupTableMixin, m)
            assert getattr(HariView, m) is getattr(FollowupTableMixin, m)
        # Override AnomaliView (grup) — bukan mixin lagi.
        for m in ("_display_df", "_on_check_toggled", "_on_check_all",
                  "_refresh_check_col"):
            assert getattr(AnomaliView, m) is not getattr(
                FollowupTableMixin, m), f"{m} harus di-override AnomaliView"
            assert getattr(HariView, m) is getattr(
                FollowupTableMixin, m), f"{m} tetap di-share utk HariView"

    def test_lru_per_view(self):
        _qapp()
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        assert AnomaliView._DISP_LRU == 8
        assert HariView._DISP_LRU == 4

    def test_hf_cols_satu_sumber(self):
        import ui.followup_table as ft
        from ui.view_anomali import _HF_COLS
        assert _HF_COLS is ft.HF_COLS, ("_HF_COLS view_anomali harus alias "
                                        "followup_table.HF_COLS")
        from ui.view_hari import _HF_COLS as hari_cols
        assert hari_cols is ft.HF_COLS

    def test_duplikasi_hilang(self):
        """Metode kembar TIDAK lagi didefinisikan di kedua file view.
        v2.19.0 — AnomaliView MEN-OVERRIDE beberapa metode utk tampilan
        GRUP (sampel user); override ini BUKAN duplikasi mati, melainkan
        perilaku grup yg berbeda dari mixin baris-tunggal."""
        # HariView tak boleh mendefinisikan ulang metode mixin (pure consumer).
        tree = ast.parse(_src("ui/view_hari.py"))
        hari_names = {n.name for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef)
                      for n in [node]}
        for m in ("_fps_for", "_display_df", "_mask_local",
                  "_on_check_all", "_hf_state"):
            assert m not in hari_names, f"{m} masih didefinisikan di view_hari.py"
        # AnomaliView boleh override _display_df, _on_check_all, dll utk grup
        # (bukan duplikasi mati — semantik berbeda).
        tree_a = ast.parse(_src("ui/view_anomali.py"))
        anomali_names = {n.name for node in ast.walk(tree_a)
                         if isinstance(node, ast.FunctionDef)
                         for n in [node]}
        # metode PURE-MIXIN (tak boleh di-override) tetap tak didefinisikan
        for m in ("_fps_for", "_mask_local", "_hf_state"):
            assert m not in anomali_names, (
                f"{m} masih didefinisikan di view_anomali.py "
                "(harus di-share via mixin)")


# ============================================================
# [D] DEAD CODE ENGINE — dilarang kembali
# ============================================================

class TestDeadCodeEngine:
    def test_utils_tanpa_fungsi_mati(self):
        tree = ast.parse(_src("waste_anomaly/utils.py"))
        names = {node.name for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
        dead = {"to_number", "to_text", "safe_sum", "safe_max", "safe_min",
                "safe_mean", "safe_median", "safe_count",
                "safe_count_active", "safe_div", "position_of",
                "second_max", "now_iso", "round_safe", "pct",
                "coerce_day_columns_numeric", "fillna_numeric"}
        assert not (names & dead), f"fungsi mati kembali: {names & dead}"
        # yang HIDUP tetap ada
        assert {"load_config", "clamp", "day_columns", "norm_text"} <= names

    def test_modul_filters_hilang(self):
        assert not (REPO / "waste_anomaly" / "filters.py").exists()
        # tak ada import filters tersisa
        for f in ("waste_anomaly/__init__.py", "ui/workers.py", "ui/app.py"):
            assert "filters" not in _src(f), f"{f} masih mengimpor filters"

    def test_tk_hooks_hilang(self):
        tree = ast.parse(_src("waste_anomaly/logging_setup.py"))
        names = {node.name for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "install_tk_exception_hook" not in names
        assert "tk_suppressed" not in names
        assert "setup_logging" in names


# ============================================================
# [S] FITUR MATI (search / rentang hari) — dilarang kembali
# ============================================================

class TestFiturMatiHilang:
    def test_state_tanpa_api_mati(self):
        src = _src("ui/state.py")
        for sym in ("def set_search", "def set_day_range",
                    "def set_filters_multi", "def invalidate_filter_cache",
                    "def filter_summary", "CHIP_LABELS",
                    "self.search", "self.day_min", "self.day_max",
                    "_search_blob"):
            assert sym not in src, f"{sym} kembali di state.py"

    def test_shared_tanpa_mesin_cari(self):
        src = _src("ui/shared.py")
        assert "def _build_search_blob" not in src
        assert "search_blob: pd.Series" not in src  # param signature
        assert "day_min: int | None = None" not in src
        assert "search: str = " not in src

    def test_apply_filters_kontrak_baru(self):
        from ui.shared import _apply_filters
        import pandas as pd
        df = pd.DataFrame({"NAMA RESTO": ["R1", "R2"], "JENIS": ["WASTE"] * 2})
        # fast path: tanpa filter → objek sama
        assert _apply_filters(df, {}) is df
        # filter hidup tetap bekerja
        out = _apply_filters(df, {"cabang": "R1"})
        assert len(out) == 1

    def test_lengkap_semula_funnel_5_dimensi(self):
        """Semantik funnel yang HIDUP tak tersentuh: 5 dimensi global."""
        import pandas as pd
        from ui.shared import _apply_filters
        df = pd.DataFrame({
            "NAMA RESTO": ["R1", "R2"], "NAMA BARANG": ["A", "B"],
            "JENIS": ["WASTE", "SUSUT"],
            "KETERANGAN": ["Cancel Nota", "Internal"],
            "ANOMALY STATUS": ["Normal", "Prioritas Tinggi"],
        })
        assert len(_apply_filters(df, {"jenis": ["WASTE", "SUSUT"]})) == 2
        assert len(_apply_filters(df, {"status": "Prioritas Tinggi"})) == 1
        assert len(_apply_filters(df, {"keterangan": "Cancel Nota"})) == 1
        assert len(_apply_filters(df, {"keterangan": " Cancel   Nota "})) == 1  # DQ-M1
        assert len(_apply_filters(df, {"item": "A"})) == 1


# ============================================================
# [V] DEAD CODE UI — dilarang kembali
# ============================================================

class TestDeadCodeUI:
    def test_pipeline_tanpa_set_workbook(self):
        src = _src("ui/view_pipeline.py")
        assert "def set_workbook" not in src
        assert "def current_workbook" in src  # yang hidup tetap

    def test_scorecard_dan_insights_terhapus_total(self):
        """v2.18.5: tab Scorecard Cabang dihapus permintaan user — file
        view_scorecard.py & waste_anomaly/insights.py TIDAK boleh kembali
        (dead code dibuang bersama fiturnya)."""
        assert not (REPO / "ui" / "view_scorecard.py").exists()
        assert not (REPO / "waste_anomaly" / "insights.py").exists()

    def test_ui_init_tanpa_lazy_export(self):
        src = _src("ui/__init__.py")
        assert "def __getattr__" not in src
        assert "__all__ = " not in src


# ============================================================
# [F] FIX E5 — sinkron snapshot notify_column_changed
# ============================================================

class TestFixSnapshotPeriode:
    def test_mutasi_check_lewat_notify(self):
        src = _src("ui/view_periode.py")
        assert "m.notify_column_changed(CHECK_COL)" in src
        assert "m.dataChanged.emit(idx, idx)" not in src


# ============================================================
# [K] MANIFEST — modul baru terdaftar (manifest dua-arah jujur)
# ============================================================

class TestManifestFollowupTable:
    def test_modul_terdaftar(self):
        manifest = (REPO / "tests" / "fixtures" /
                    "ui_methods_manifest.txt").read_text(encoding="utf-8")
        assert "followup_table.py::FollowupTableMixin" in manifest
        for f in ("tests/test_ui_structure.py", "tests/test_v270_wave4.py"):
            assert '"followup_table.py"' in _src(f), (
                f"{f}: EXPECTED_MODULES harus memuat followup_table.py")
