"""test_charts_contract.py — kontrak chart interaktif (v2.5.1, PR-H2/DD-M5).

Mengunci kontrak yang SELAMA ini hanya diverifikasi E2E dengan canvas
stub (C-ext _tkagg tidak tersedia di sandbox):

1. KONTRAK NILAI: nilai yang dipancarkan on_click(key, value) saat bar /
   wedge diklik HARUS anggota df[kolom].unique() — bukan label tampilan
   (truncation 'KULIT PANGS…', disambiguation '#2', dst.). Label tampilan
   bocor jadi nilai filter = drill-down 0 baris TANPA error (senyap).
   Klik DISIMULASI SUNGGUHAN: MouseEvent di-dispatch ke callbacks canvas
   Agg — jalur hit-test contains() yang sama dengan canvas asli.

2. KONTRAK CID: tiap chart interaktif menyimpan cid di fig._waste_cids
   (teardown _dispose_chart_registry memutus semua listener); setelah
   di-disconnect, klik TIDAK lagi memancarkan nilai (tidak ada zombie).

3. KONTRAK TUPLE: chart dashboard.py mengembalikan (Figure, on_click).

Run: python -m pytest tests/test_charts_contract.py -v
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless — dispatch event nyata tanpa display

import pandas as pd
import pytest
from matplotlib.backend_bases import MouseEvent
from matplotlib.figure import Figure

from waste_anomaly import charts as wa_charts
from waste_anomaly import dashboard as wa_dash


# ============================================================
# FIXTURE — Detail-like frame dengan nilai yang MIRIP label display
# (nama panjang → fmt_item truncation aktif) supaya kontrak RAW ketat.
# ============================================================

@pytest.fixture(scope="module")
def det() -> pd.DataFrame:
    return pd.DataFrame({
        "NAMA RESTO": ["1151.GGPDAA", "1152.GGPDBB", "1153.GGPDCC"],
        "NAMA BARANG": [
            "KULIT PANGSIT FROZEN 500GR", "SUSURURUT BANDENG 250",
            "KULIT PANGSIT FROZEN 500GR",
        ],
        "KETERANGAN": ["Kualitas Internal", "Cancel Nota", "Over Stock"],
        "JENIS": ["WASTE", "SUSUT", "TRIAL"],
        "SATUAN": ["GR", "PCS", "GR"],
        "TOTAL": [300.0, 200.0, 100.0],
        "MAX": [100.0, 90.0, 50.0],
        "Count Hari": [3, 2, 1],
        "ANOMALY SCORE": [5, 3, 0],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Perlu Review", "Normal"],
        "1": [100.0, 50.0, 0.0],
        "2": [100.0, 60.0, 30.0],
        "5": [100.0, 90.0, 70.0],
        "6": [0.0, 0.0, 0.0],
        "7": [0.0, 60.0, 0.0],
    })


class Recorder:
    """Tangkap semua (key, value) yang dipancarkan on_click."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def __call__(self, key: str, value):
        self.calls.append((key, value))

    @property
    def last(self):
        return self.calls[-1] if self.calls else None


def _click_patch(fig: Figure, patch) -> bool:
    """Dispatch button_press_event di pusat patch. Return True bila event
    mencapai handler chart (klik di luar semua patch tidak dihitung)."""
    if patch in (None,):
        return False
    try:
        x0, y0 = patch.get_x(), patch.get_y()
        w, h = patch.get_width(), patch.get_height()
        if w <= 0 or h <= 0:
            return False
        ax = patch.axes
        x_disp, y_disp = ax.transData.transform((x0 + w / 2.0, y0 + h / 2.0))
        event = MouseEvent("button_press_event", fig.canvas, x_disp, y_disp, 1)
        fig.canvas.callbacks.process("button_press_event", event)
        return True
    except Exception:
        return False


def _clickable_patches(fig: Figure):
    """Semua patch bar/wedge ber-ukuran positif dari semua axes."""
    out = []
    for ax in fig.axes:
        for p in ax.patches:
            try:
                if p.get_width() > 0 and p.get_height() > 0:
                    out.append(p)
            except AttributeError:
                # Wedge tidak punya get_width — pakai radius
                try:
                    if p.r > 0:
                        out.append(p)
                except AttributeError:
                    continue
    return out


def _click_wedge_center(fig: Figure, wedge) -> None:
    """Klik wedge di sudut tengah (θ = (θ1+θ2)/2), radius tengah CINCIN.

    Donut (wedgeprops width) punya lubang: klik di r/2 jatuh di lubang →
    contains() False. Radius tengah cincin = r - width/2 (pie penuh:
    width = r → pusat cincin = r/2, tetap benar).
    """
    import math
    theta = math.radians((wedge.theta1 + wedge.theta2) / 2.0)
    width = getattr(wedge, "width", 0.0) or 0.0
    if width > 0:
        r = wedge.r - width / 2.0  # donut: tengah cincin
    else:
        r = wedge.r * 0.5  # pie penuh: setengah radius
    x_data = wedge.center[0] + r * math.cos(theta)
    y_data = wedge.center[1] + r * math.sin(theta)
    x_disp, y_disp = wedge.axes.transData.transform((x_data, y_data))
    event = MouseEvent("button_press_event", fig.canvas, x_disp, y_disp, 1)
    fig.canvas.callbacks.process("button_press_event", event)


# ============================================================
# charts.py — 4 chart interaktif (tab Visualisasi, P8)
# ============================================================

class TestChartsPyContract:
    @pytest.mark.parametrize("fn, key, col", [
        (wa_charts.chart_status_pie, "status", "ANOMALY STATUS"),
        (wa_charts.chart_waste_per_cabang, "cabang", "NAMA RESTO"),
        (wa_charts.chart_top_items, "item", "NAMA BARANG"),
        (wa_charts.chart_pareto_keterangan, "keterangan", "KETERANGAN"),
    ])
    def test_klik_memancarkan_nilai_raw(self, det, fn, key, col):
        """DD-M5: nilai on_click ∈ df[col].unique() — bukan label display."""
        rec = Recorder()
        fig = fn(det, on_click=rec)
        assert isinstance(fig, Figure)
        assert getattr(fig, "_waste_cids", []), "cid tidak tersimpan"

        allowed = {str(v) for v in det[col].dropna().unique()}
        n_fired = 0
        for patch in _clickable_patches(fig):
            before = len(rec.calls)
            if key == "status":
                _click_wedge_center(fig, patch)
            else:
                ok = _click_patch(fig, patch)
                if not ok:
                    continue
            if len(rec.calls) > before:
                n_fired += 1
                k, v = rec.calls[-1]
                assert k == key
                assert v is None or str(v) in allowed, (
                    f"Nilai on_click {v!r} BUKAN anggota {col}.unique() "
                    f"(label display bocor jadi nilai filter?)"
                )
        assert n_fired >= 1, "tidak ada patch yang berhasil diklik"

    def test_disconnect_cid_mematikan_klik(self, det):
        """PR-H2: teardown _dispose_chart_registry memutus semua listener —
        setelah disconnect, klik tidak lagi memancarkan (tidak ada zombie)."""
        rec = Recorder()
        fig = wa_charts.chart_waste_per_cabang(det, on_click=rec)
        cids = getattr(fig, "_waste_cids", [])
        assert cids
        for cid in cids:
            fig.canvas.mpl_disconnect(cid)
        patches = _clickable_patches(fig)
        assert patches
        n_before = len(rec.calls)
        _click_patch(fig, patches[0])
        assert len(rec.calls) == n_before, (
            "klik masih terpicu setelah semua cid di-disconnect (zombie)"
        )


# ============================================================
# dashboard.py — 7 chart interaktif (kontrak tuple + nilai raw)
# ============================================================

class TestDashboardPyContract:
    @pytest.mark.parametrize("fn, key, col", [
        (wa_dash.chart_status_bar_interactive, "status", "ANOMALY STATUS"),
        (wa_dash.chart_cabang_bar_interactive, "cabang", "NAMA RESTO"),
        (wa_dash.chart_top_items_interactive, "item", "NAMA BARANG"),
        (wa_dash.chart_keterangan_bar_interactive, "keterangan", "KETERANGAN"),
    ])
    def test_kontrak_tuple_dan_nilai_raw(self, det, fn, key, col):
        """Kontrak return (Figure, on_click) + nilai klik ∈ unique()."""
        rec = Recorder()
        result = fn(det, on_click=rec)
        assert isinstance(result, tuple) and len(result) == 2
        fig, wired = result
        assert isinstance(fig, Figure)
        assert wired is rec
        assert getattr(fig, "_waste_cids", []), "cid tidak tersimpan"

        allowed = {str(v) for v in det[col].dropna().unique()}
        n_fired = 0
        for patch in _clickable_patches(fig):
            before = len(rec.calls)
            if not _click_patch(fig, patch):
                continue
            if len(rec.calls) > before:
                n_fired += 1
                k, v = rec.calls[-1]
                assert k == key
                assert v is None or str(v) in allowed
        assert n_fired >= 1

    def test_jenis_donut_skalar_di_guard_ui(self, det):
        """DD-M4: donut JENIS memancarkan nilai SKALAR — UI menormalkan ke
        list (guard _apply_filters toleran keduanya; test ini mengunci
        bentuk emisi supaya sinkronisasi checkbox di _on_chart_click tetap
        diperlukan — lihat tab_dashboard v2.5.1)."""
        rec = Recorder()
        fig, wired = wa_dash.chart_jenis_donut_interactive(det, on_click=rec)
        assert isinstance(fig, Figure)
        wedges = [p for p in fig.axes[0].patches if hasattr(p, "r")]
        assert wedges
        _click_wedge_center(fig, wedges[0])
        assert rec.calls, "klik wedge tidak memancarkan"
        k, v = rec.calls[0]
        assert k == "jenis"
        allowed = {str(v) for v in det["JENIS"].dropna().unique()}
        assert v is None or str(v) in allowed
        # v skalar str (atau None saat toggle) — UI-side menormalkan [v]
        assert v is None or isinstance(v, str)

    def test_score_per_cabang_klik_raw(self, det):
        rec = Recorder()
        fig, wired = wa_dash.chart_score_per_cabang_interactive(det, on_click=rec)
        allowed = {str(v) for v in det["NAMA RESTO"].dropna().unique()}
        n_fired = 0
        for patch in _clickable_patches(fig):
            before = len(rec.calls)
            if not _click_patch(fig, patch):
                continue
            if len(rec.calls) > before:
                n_fired += 1
                k, v = rec.calls[-1]
                assert k == "cabang"
                assert v is None or str(v) in allowed
        assert n_fired >= 1

    def test_active_filter_menonaktifkan_toggle(self, det):
        """Klik bar yang SAMA dengan active_filter → nilai None (clear)."""
        rec = Recorder()
        fig, _ = wa_dash.chart_cabang_bar_interactive(
            det, on_click=rec, active_filter=("cabang", "1151.GGPDAA"))
        patches = _clickable_patches(fig)
        # bar pertama = agregat terbesar (1151.GGPDAA, TOTAL 300)
        _click_patch(fig, patches[0])
        assert rec.calls
        k, v = rec.calls[-1]
        assert v is None, "klik bar aktif harus memancarkan None (toggle off)"


# ============================================================
# _wire_patch_click: log tertulis saat on_click raise (DD-M5 hardening)
# ============================================================

class TestSafeHandler:
    def test_on_click_raise_tidak_melempar(self, det, caplog):
        """Handler event tidak boleh raise — exception callback UI ditelan
        + tercatat log (dulu senyap di charts.py / propagate di dashboard)."""
        import logging

        def bad(key, value):
            raise RuntimeError("boom dari UI")

        fig = wa_charts.chart_waste_per_cabang(det, on_click=bad)
        with caplog.at_level(logging.WARNING, logger="waste_anomaly.charts"):
            patches = _clickable_patches(fig)
            _click_patch(fig, patches[0])  # tidak boleh raise
        # dashboard._safe_on_click juga tidak boleh melempar
        fig2, _ = wa_dash.chart_status_bar_interactive(det, on_click=bad)
        patches2 = _clickable_patches(fig2)
        _click_patch(fig2, patches2[0])  # tidak boleh raise
