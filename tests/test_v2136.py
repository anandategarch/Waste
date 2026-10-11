"""test_v2136.py — regresi Gelombang A deep-audit v2.13.6.

Sumber: audit menyeluruh UI/UX/kode/dead-code/engine (R2, laporan
audit-A-ui.md). Gelombang A = perbaikan UX nyata yang user langsung
rasakan, tanpa menyentuh jalur data:

- [K] LAYOUT: tab Scorecard (konten ±1.270px) & tab Pipeline (±716px)
  TIDAK muat di ruang halaman tab ±582px (1366×768, terukur offscreen)
  → kedua view dibungkus QScrollArea (widgetResizable, NoFrame) —
  view boleh diciutkan, konten tetap utuh & terjangkau lewat gulir
  (audit R1/R2). Kartu bawah Scorecard (Tren/Sistemik/DQ) dan kartu
  Threshold Pipeline tak lagi terpotong permanen.
- [U] TEKS JUJUR: label kartu DQ tak lagi menyuruh "klik 2× sel
  PENJELASAN" (tabel DQ tidak punya handler klik-2× — instruksi mati,
  audit U1) → kini "arahkan kursor"; Bantuan (F1) kini memuat seksi
  Tab Scorecard Cabang (audit U2); docstring app/ui_app "6 tab".
- [B] BANNER .BAT: MULAI.bat/SETUP.bat disegarkan ke v2.13.6 — banner
  lama masih v2.12.5 + mengiklankan "3 view" + "Sidebar filter …
  Ctrl+Shift+F" (sidebar dihapus v2.12.4 — banner menipu, audit C).
  CRLF dijaga (kontrak .gitattributes).
- [V] VERSI: 2.13.6 di semua situs (termasuk .bat yang dulu tertinggal).

Catatan: perubahan perilaku TIDAK ada — murni layout-wrapping + teks;
semua atribut view (tabel/KPI/tombol) tetap pada tempatnya (tes [K3]).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def _make_ctx():
    from ui.state import AppContext
    return AppContext({})


# ============================================================
# [K] LAYOUT — QScrollArea bungkus view panjang (audit R1 + R2)
# ============================================================

class TestScrollScorecard:
    def test_view_dibungkus_scroll(self):
        _qapp()
        from PySide6.QtWidgets import QFrame, QScrollArea
        from ui.view_scorecard import ScorecardView
        view = ScorecardView(_make_ctx())
        scrolls = view.findChildren(QScrollArea)
        assert scrolls, "ScorecardView harus dibungkus QScrollArea (R1)"
        s = scrolls[0]
        assert s.widgetResizable(), "widgetResizable supaya lebar ikut viewport"
        assert s.frameShape() == QFrame.Shape.NoFrame, "tanpa bingkai ganda"
        view.close()
        view.deleteLater()

    def test_view_bisa_diciutkan_tapi_konten_utuh(self):
        """Kontrak inti R1: view tak lagi MEMAKSA tinggi 1.270px —
        ruang tab 582px di 1366×768 kini cukup + gulir; konten halaman
        tetap menuntut tinggi penuhnya (tak ada kartu yang dibuang)."""
        _qapp()
        from ui.view_scorecard import ScorecardView
        view = ScorecardView(_make_ctx())
        vm = view.minimumSizeHint().height()
        pm = view._page.minimumSizeHint().height()
        assert vm <= 640, f"view masih memaksa tinggi {vm}px (dulu 1270)"
        assert pm >= 1000, f"konten halaman menyusut tak wajar: {pm}px"
        view.close()
        view.deleteLater()

    def test_semua_kartu_tetap_anak_halaman(self):
        """Tak ada widget hilang saat dibungkus — tabel/KPI/kartu tren
        tetap cucu halaman scroll (⤢/⛶ & reparent tabel tak terdampak)."""
        _qapp()
        from ui.view_scorecard import ScorecardView
        view = ScorecardView(_make_ctx())
        page = view._page
        for w in (view._kpi_row, view._main_card, view._row2, view._row3,
                  view._table, view._money_table, view._weekday_table,
                  view._dq_table, view._sistemik_table, view._trend_table):
            assert page.isAncestorOf(w), (
                f"{w.objectName() or type(w).__name__} tak lagi di halaman")
        view.close()
        view.deleteLater()


class TestScrollPipeline:
    def test_view_dibungkus_scroll(self):
        _qapp()
        from PySide6.QtWidgets import QFrame, QScrollArea
        from ui.view_pipeline import PipelineView
        view = PipelineView(_make_ctx())
        scrolls = view.findChildren(QScrollArea)
        assert scrolls, "PipelineView harus dibungkus QScrollArea (R2)"
        s = scrolls[0]
        assert s.widgetResizable()
        assert s.frameShape() == QFrame.Shape.NoFrame
        view.close()
        view.deleteLater()

    def test_view_bisa_diciutkan_tapi_konten_utuh(self):
        """Kontrak R2: tinggi-min 716px tak lagi dipaksakan — tombol
        Simpan/Reset/Pratinjau di kartu Threshold terjangkau via gulir."""
        _qapp()
        from ui.view_pipeline import PipelineView
        view = PipelineView(_make_ctx())
        vm = view.minimumSizeHint().height()
        pm = view._page.minimumSizeHint().height()
        assert vm <= 640, f"view masih memaksa tinggi {vm}px (dulu 716)"
        assert pm >= 600, f"konten halaman menyusut tak wajar: {pm}px"
        view.close()
        view.deleteLater()

    def test_kontrol_utama_tetap_anak_halaman(self):
        _qapp()
        from ui.view_pipeline import PipelineView
        ctx = _make_ctx()
        ctx.config = {"thresholds": {"TH_SPIKE": 3}}  # form threshold terisi
        view = PipelineView(ctx)
        page = view._page
        for w in (view._ent_workbook, view._btn_run, view._progress,
                  view._summary, view._log, view._spin_ka):
            assert page.isAncestorOf(w), (
                f"{type(w).__name__} tak lagi di halaman")
        # editor threshold (kartu 4) ada di halaman yang sama → tergulir
        assert view._config_vars, "form threshold kosong (config kosong?)"
        assert all(page.isAncestorOf(e) for e in view._config_vars.values())
        view.close()
        view.deleteLater()


# ============================================================
# [U] TEKS JUJUR (audit U1 + U2 + docstring basi)
# ============================================================

class TestTeksJujur:
    def test_label_dq_tak_lagi_menyuruh_klik_2x(self):
        """U1: tabel DQ tidak punya handler double_clicked — instruksi
        lama 'klik 2× sel PENJELASAN' mati (klik tak berbuat apa-apa)."""
        src = (UI / "view_scorecard.py").read_text(encoding="utf-8")
        assert "klik 2× sel PENJELASAN" not in src
        assert "arahkan kursor ke sel PENJELASAN" in src

    def test_bantuan_memuat_seksi_scorecard(self):
        """U2: 1 dari 6 tab tak terdokumentasi di Bantuan (F1)."""
        from ui.app import _HELP_HTML
        assert "Tab Scorecard Cabang" in _HELP_HTML
        assert "POTENSI HEMAT" in _HELP_HTML
        assert "digulir" in _HELP_HTML  # info layar kecil v2.13.6

    def test_docstring_modul_bebas_angka_basi(self):
        """Docstring/deskripsi struktur harus bilang 6 tab. (Komentar
        SEJARAH 'v2.8.0: 8 → 5 view' di app.py sah — bukan klaim kini.)"""
        import ast

        def _docstring(path: Path) -> str:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return ast.get_docstring(tree) or ""

        assert "6 tab" in _docstring(UI / "app.py")
        assert "5 view" not in _docstring(UI / "app.py")
        assert "6 tab" in _docstring(REPO / "ui_app.py")
        assert "3 view" not in _docstring(REPO / "ui_app.py")


# ============================================================
# [B] BANNER .BAT disegarkan (audit C — banner menipu sejak v2.13.0)
# ============================================================

class TestBannerBat:
    def test_mulai_bat_versi_dan_6_tab(self):
        b = (REPO / "MULAI.bat").read_bytes().decode("utf-8")
        assert "v2.13.15" in b
        assert "6 tab" in b
        assert "Scorecard" in b, "banner harus menyebut tab baru"

    def test_mulai_bat_tanpa_iklan_fitur_terhapus(self):
        b = (REPO / "MULAI.bat").read_bytes().decode("utf-8")
        assert "Ctrl+Shift+F" not in b, "sidebar dihapus v2.12.4"
        assert "Sidebar" not in b
        assert "3 view" not in b

    def test_setup_bat_versi_baru(self):
        b = (REPO / "SETUP.bat").read_bytes().decode("utf-8")
        assert "v2.13.15" in b
        assert "v2.12.5" not in b

    def test_crlf_utuh(self):
        """Kontrak .gitattributes (*.bat eol=crlf) tak boleh rusak."""
        for f in ("MULAI.bat", "SETUP.bat"):
            b = (REPO / f).read_bytes()
            n_lf = b.count(b"\n")
            n_crlf = b.count(b"\r\n")
            assert n_lf == n_crlf, f"{f}: ada baris LF tanpa CR"


# ============================================================
# [V] VERSI — semua situs 2.13.6 (termasuk .bat yang pernah
#     tertinggal 7 versi minor — audit konsistensi)
# ============================================================

class TestVersi:
    def test_app_version(self):
        from ui.shared import APP_VERSION
        assert APP_VERSION == "2.13.15"

    def test_engine_version_sinkron(self):
        from waste_anomaly import __version__
        cfg = json.loads(
            (REPO / "waste_anomaly" / "config.json").read_text(
                encoding="utf-8"))
        assert __version__ == "2.13.15"
        assert cfg.get("version") == "2.13.15"

    def test_docstring_init_tidak_basi(self):
        src = (REPO / "waste_anomaly" / "__init__.py").read_text(
            encoding="utf-8")
        assert "Versi: 2.13.15" in src
