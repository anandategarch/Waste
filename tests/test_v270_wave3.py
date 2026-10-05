"""Test — regresi v2.7.0 gelombang 3 (fix views pipeline + utils).

Mengunci fix audit v2.6.x (Task ID 2-c) yang MASIH relevan di v2.8.1:
1. Validasi threshold _save_config: teks non-numerik / <= 0 / NaN ditolak
   SEBELUM file ditulis (regresi v2.6.0 — "0,5" koma Indonesia dulunya
   tersimpan sebagai string ke config.json).
2. _DEFAULT_CONFIG thresholds 20/20 key (Reset Default dulu 14/20).

v2.8.0: test hint Kualitas dihapus (view_kualitas.py dihapus total).
v2.8.1: test placeholder Jelajah/Waktu, dedupe chart statistik, drill-down
chart interaktif, refresh non-modal Waktu, note stat-chart — semuanya
dihapus: view_jelajah.py + view_waktu.py dihapus total (5 → 3 tab)
bersama modul charts/dashboard/chart_helpers.

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
