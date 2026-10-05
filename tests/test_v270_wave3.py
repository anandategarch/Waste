"""Test — regresi v2.7.0 gelombang 3 (fix views jelajah/waktu/uang/peer/
kualitas/pipeline + utils).

Mengunci fix audit v2.6.x (Task ID 2-c):
1. Validasi threshold _save_config: teks non-numerik / <= 0 / NaN ditolak
   SEBELUM file ditulis (regresi v2.6.0 — "0,5" koma Indonesia dulunya
   tersimpan sebagai string ke config.json).
2. _DEFAULT_CONFIG thresholds 20/20 key (Reset Default dulu 14/20).
3. Placeholder "Belum ada data" tampil sejak konstruksi view (pra-run pertama
   area view tidak lagi BLANK).
4. Hint Kualitas tidak lagi menyebut affordance "▶" era Treeview.
5. Duplikat chart statistik Jelajah dihapus (9 tersisa, tanpa pasangan
   interaktifnya).
6. Drill-down chart dijadwalkan via QTimer.singleShot (re-render tidak lagi
   sinkron di dalam handler event matplotlib).
7. Guard drill-down NaN-aware (NaN tidak lolos jadi filter).

KEAMANAN: semua test _save_config memonkeypatch APP_DIR ke tmp_path —
config.json repo TIDAK PERNAH ditulis; fixture autouse memverifikasi byte
config.json tidak berubah selama modul ini berjalan.

Headless: QT_QPA_PLATFORM=offscreen diset SEBELUM import PySide6.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Harus diset sebelum PySide6 di-import (dilakukan lazy di dalam test).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

import pytest


@pytest.fixture(autouse=True, scope="module")
def _repo_config_guard():
    """config.json repo tidak boleh tersentuh oleh test modul ini."""
    p = REPO / "waste_anomaly" / "config.json"
    before = p.read_bytes()
    yield
    assert p.read_bytes() == before, (
        "waste_anomaly/config.json berubah selama test — test WAJIB menulis "
        "ke tmp_path (monkeypatch APP_DIR), bukan ke repo!")


@pytest.fixture(autouse=True)
def _qapp_guard():
    """QApplication (offscreen) wajib ada SEBELUM widget apa pun dibuat."""
    _qapp()
    yield


def _qapp():
    """QApplication tunggal (offscreen) — dibuat sekali per proses pytest."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _make_ctx():
    """AppContext segaji dengan config asli (read-only)."""
    from ui.state import AppContext
    from waste_anomaly.utils import load_config
    return AppContext(load_config())


def _fake_messagebox(monkeypatch, target_module):
    """Ganti QMessageBox modul target dengan perekam (tanpa dialog nyata)."""
    calls: list[tuple[str, str]] = []

    class _MB:
        @staticmethod
        def critical(*args):
            calls.append(("critical", args[-1] if args else ""))

        @staticmethod
        def information(*args):
            calls.append(("information", args[-1] if len(args) > 1 else ""))

        @staticmethod
        def warning(*args):
            calls.append(("warning", args[-1] if args else ""))

    monkeypatch.setattr(target_module, "QMessageBox", _MB)
    return calls


def _make_pipeline_view(monkeypatch, tmp_path):
    """PipelineView offscreen dengan target simpan DIARAHKAN ke tmp_path."""
    import ui.view_pipeline as vpmod
    (tmp_path / "waste_anomaly").mkdir(exist_ok=True)
    monkeypatch.setattr(vpmod, "APP_DIR", tmp_path)
    view = vpmod.PipelineView(_make_ctx())
    return view, tmp_path / "waste_anomaly" / "config.json"


# ============================================================
# FIX 1 — validasi threshold _save_config
# ============================================================

class TestSaveConfigValidasi:
    def test_tolak_teks_non_numerik(self, monkeypatch, tmp_path):
        """"0,5" (koma Indonesia) / "abc" → dialog error + TIDAK menulis file
        (dulu disimpan sebagai string — regresi v2.6.0)."""
        import ui.view_pipeline as vpmod
        view, target = _make_pipeline_view(monkeypatch, tmp_path)
        calls = _fake_messagebox(monkeypatch, vpmod)
        for bad in ("0,5", "abc", "", "lima"):
            key = sorted(view._config_vars)[0]
            view._config_vars[key].setText(bad)
            view._save_config()
            assert not target.exists(), f"file ditulis padahal input {bad!r} invalid"
            assert calls and calls[-1][0] == "critical"
            assert "tidak valid" in calls[-1][1]
        assert len(calls) == 4

    def test_tolak_nol_negatif_dan_nan(self, monkeypatch, tmp_path):
        """"-1" / "0" / "nan" → dialog error 'harus > 0' / 'tidak valid'."""
        import ui.view_pipeline as vpmod
        view, target = _make_pipeline_view(monkeypatch, tmp_path)
        calls = _fake_messagebox(monkeypatch, vpmod)
        key = sorted(view._config_vars)[0]
        view._config_vars[key].setText("-1")
        view._save_config()
        assert not target.exists()
        assert calls[-1][0] == "critical" and "harus > 0" in calls[-1][1]
        view._config_vars[key].setText("0")
        view._save_config()
        assert not target.exists() and "harus > 0" in calls[-1][1]
        # "nan" lolos float() tapi int(nan) raise ValueError → ditolak
        view._config_vars[key].setText("nan")
        view._save_config()
        assert not target.exists()
        assert "tidak valid" in calls[-1][1]

    def test_simpan_valid_roundtrip_numerik(self, monkeypatch, tmp_path):
        """Input valid → JSON berisi angka (int utk bilangan bulat, float utk
        desimal) — bukan string."""
        import ui.view_pipeline as vpmod
        view, target = _make_pipeline_view(monkeypatch, tmp_path)
        calls = _fake_messagebox(monkeypatch, vpmod)
        key = sorted(view._config_vars)[0]
        view._config_vars[key].setText("5")           # → int 5
        view._config_vars["TH_MAX_AVG_AKTIF"].setText("2.5")  # → float 2.5
        view._save_config()
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        th = data["thresholds"]
        assert th[key] == 5 and isinstance(th[key], int)
        assert th["TH_MAX_AVG_AKTIF"] == 2.5 and isinstance(th["TH_MAX_AVG_AKTIF"], float)
        # seluruh nilai numerik — tidak ada string lolos
        assert all(isinstance(v, (int, float)) for v in th.values())
        assert calls and calls[-1][0] == "information"


# ============================================================
# FIX 2 — _DEFAULT_CONFIG 20/20 key
# ============================================================

class TestDefaultConfig:
    def test_thresholds_default_20_key(self):
        from waste_anomaly.utils import _DEFAULT_CONFIG
        assert len(_DEFAULT_CONFIG["thresholds"]) == 20

    def test_default_menutup_semua_key_config_json(self):
        """Setiap key di config.json bawaan wajib punya default (Reset
        Default 20/20 — dulu 6 key tidak pernah ter-reset)."""
        from waste_anomaly.utils import _DEFAULT_CONFIG
        cfg = json.loads((REPO / "waste_anomaly" / "config.json")
                         .read_text(encoding="utf-8"))
        missing = set(cfg["thresholds"]) - set(_DEFAULT_CONFIG["thresholds"])
        assert missing == set()

    def test_nilai_default_identik_config_json(self):
        """Nilai default disalin persis dari config.json (bukan tebakan)."""
        from waste_anomaly.utils import _DEFAULT_CONFIG
        cfg = json.loads((REPO / "waste_anomaly" / "config.json")
                         .read_text(encoding="utf-8"))
        for k, v in cfg["thresholds"].items():
            assert _DEFAULT_CONFIG["thresholds"][k] == v, f"beda nilai utk {k}"


# ============================================================
# FIX 3 — placeholder pra-run pertama
# ============================================================

class TestPlaceholderPraRun:
    def _assert_placeholder(self, view):
        from PySide6.QtWidgets import QLabel
        hits = [l for l in view.findChildren(QLabel)
                if "Belum ada data" in l.text()]
        assert hits, ("tidak ada label 'Belum ada data' di widget tree — "
                      "area view BLANK sebelum run pertama (V26-M6)")
        return hits

    def test_view_chart_punya_placeholder(self):
        """Jelajah/Waktu menampilkan placeholder sejak konstruksi (tanpa
        perlu refresh/on_shown). v2.8.0: Uang/Peer/Kualitas dihapus total
        keluar dari cakupan test ini."""
        _qapp()
        from ui.view_jelajah import JelajahView
        from ui.view_waktu import WaktuView
        for cls in (JelajahView, WaktuView):
            view = cls(_make_ctx())
            self._assert_placeholder(view)

    def test_placeholder_kartu_terpasang_di_layout(self):
        """Kartu placeholder benar-benar ber-parent (dalam grid) — bukan
        ChartCard yatim parent=None yang tak terlihat."""
        _qapp()
        from ui.view_waktu import WaktuView
        view = WaktuView(_make_ctx())
        for card in (view._c_per_day, view._c_weekday, view._c_heatmap):
            assert card.parent() is not None, "ChartCard belum ditempatkan"
        assert view._chart_grid.count() == 3


# ============================================================
# FIX 4 — hint Kualitas (tanpa affordance Treeview)
# ============================================================
# v2.8.0: TestHintKualitas DIHAPUS — view_kualitas.py dihapus total
# (8 → 5 tab). Interaksi 'sort header + kolom Detail/Contoh' yang
# dulu diuji di sini tidak lagi punya subjek.


# ============================================================
# FIX 5 — dedupe chart statistik Jelajah
# ============================================================

class TestDedupeChartJelajah:
    def test_tanpa_duplikat_pasangan_interaktif(self):
        """3 builder statis duplikat (status pie / waste per cabang / top
        items) dihapus — pasangan interaktifnya tetap ada di grid atas."""
        from ui.view_jelajah import _STAT_CHARTS
        keys = [k for _t, k in _STAT_CHARTS]
        assert len(keys) == 9
        for gone in ("status_pie", "waste_cabang", "top_items"):
            assert gone not in keys, f"chart statis duplikat {gone} masih ada"
        titles = [t for t, _k in _STAT_CHARTS]
        assert len(titles) == len(set(titles))

    def test_chart_interaktif_tetap_ada(self):
        """Drill-down interaktif (status/cabang/item) tidak ikut terhapus."""
        _qapp()
        from ui.view_jelajah import JelajahView
        view = JelajahView(_make_ctx())
        assert view._c_status is not None and view._c_cabang is not None
        assert view._c_items is not None


# ============================================================
# FIX 6 + 7 — drill-down deferred & guard NaN
# ============================================================

class TestDrillDown:
    def test_klik_chart_dieksekusi_deferred(self):
        """Handler mpl hanya menjadwalkan (singleShot 0) — filter belum
        berubah SESAAT setelah klik, berubah setelah event loop berputar
        (re-render tidak lagi sinkron di dalam handler event matplotlib)."""
        app = _qapp()
        from ui.view_jelajah import JelajahView
        ctx = _make_ctx()
        view = JelajahView(ctx)
        view._on_chart_click("cabang", "CAB X")
        assert ctx.active_filters["cabang"] is None, (
            "filter berubah sinkron di dalam handler — harus deferred")
        app.processEvents()
        assert ctx.active_filters["cabang"] == "CAB X"

    def test_klik_ulang_melepas_filter(self):
        """Klik nilai yang sama → lepas (perilaku klik-ganda-untuk-lepas
        tetap bekerja lewat jalur deferred)."""
        app = _qapp()
        from ui.view_jelajah import JelajahView
        ctx = _make_ctx()
        view = JelajahView(ctx)
        view._on_chart_click("cabang", "CAB X")
        app.processEvents()
        assert ctx.active_filters["cabang"] == "CAB X"
        view._on_chart_click("cabang", "CAB X")
        app.processEvents()
        assert ctx.active_filters["cabang"] is None

    def test_drill_nan_ditolak_tanpa_exception(self):
        """NaN/None → tidak set filter, tidak raise, status bar memberi tahu
        (dulu NaN lolos guard ``is not None`` → tabel kosong senyap)."""
        app = _qapp()
        from ui.view_jelajah import JelajahView
        ctx = _make_ctx()
        status: list[tuple[str, str]] = []
        ctx.status.connect(lambda t, k: status.append((t, k)))
        view = JelajahView(ctx)
        before = dict(ctx.active_filters)
        # jalur langsung (eksekusi pekerjaan deferred)
        view._do_chart_click("cabang", float("nan"))
        assert ctx.active_filters["cabang"] is None
        # jalur handler + event loop
        view._on_chart_click("cabang", float("nan"))
        app.processEvents()
        view._on_chart_click("cabang", None)
        app.processEvents()
        assert ctx.active_filters == before, "filter tidak boleh berubah"
        assert any("drill-down" in t for t, _k in status), (
            "harus ada pesan status 'tidak bisa drill-down'")

    def test_double_click_tabel_nan_ditolak(self):
        """Double-click baris dengan sel NaN: kolom NaN di-skip (bukan jadi
        filter), kolom valid tetap dipakai."""
        _qapp()
        import pandas as pd
        from ui.view_jelajah import JelajahView
        ctx = _make_ctx()
        view = JelajahView(ctx)
        rec = pd.Series({"NAMA RESTO": float("nan"), "NAMA BARANG": "Item A"})
        view._on_double(rec)
        assert ctx.active_filters["cabang"] is None
        assert ctx.active_filters["item"] == "Item A"

    def test_guard_drill_value_ok(self):
        """Unit helper guard: None/NaN False; teks/angka True; list aman."""
        from ui.view_jelajah import _drill_value_ok
        assert _drill_value_ok(None) is False
        assert _drill_value_ok(float("nan")) is False
        assert _drill_value_ok("CAB X") is True
        assert _drill_value_ok(3) is True
        assert _drill_value_ok(["a", "b"]) is True  # list tak dinilai isna


# ============================================================
# FIX 8 — jalur refresh/on_shown tidak lagi modal (waktu)
# ============================================================

class TestRefreshNonBlocking:
    def test_error_tabel_waktu_non_modal(self):
        """Gagal membangun tabel saat refresh (dipicu on_shown) → status bar,
        BUKAN QMessageBox.warning bertumpuk (grep sumber: tidak ada pemanggil
        QMessageBox di modul waktu lagi). v2.8.0: modul uang dihapus total
        keluar dari cakupan test ini."""
        _qapp()
        import ui.view_waktu as vw
        for mod in (vw,):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            assert "QMessageBox.warning" not in src, (
                f"{mod.__name__}: refresh path masih memakai dialog modal")
            assert "set_status" in src, (
                f"{mod.__name__}: harus memberi pesan non-blocking via status")


# ============================================================
# FIX 9 — note tidak lagi mengklaim "ikut filter aktif"
# ============================================================

class TestNoteStale:
    def test_note_stat_chart_jujur(self):
        """Note chart statistik menyatakan perilaku sebenarnya (tidak otomatis
        ikut filter — perlu tombol Segarkan), bukan klaim basi."""
        src = (REPO / "ui" / "view_jelajah.py").read_text(encoding="utf-8")
        assert "(ikut filter aktif)" not in src
        assert "Segarkan" in src

    def test_docstring_tanpa_era_v250(self):
        """Referensi era '(P1/P2 v2.5.0)' di docstring view diganti wording
        v2.6+ (audit L14). v2.8.0: view_uang dihapus total."""
        for fname in ("view_waktu.py",):
            src = (REPO / "ui" / fname).read_text(encoding="utf-8")
            assert "v2.5.0" not in src, f"{fname}: docstring masih era v2.5.0"
