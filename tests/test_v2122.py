"""test_v2122.py — regresi v2.12.2 (UI/UX fix batch).

Cakupan (semua fitur sesi ini):
[A] WLabel heightForWidth — bug sizeHint "persegi" (112px padahal 28px)
    dicuri dari tinggi tabel SEMUA tab; flag dipulihkan + layout hidup.
[B] SlicerBar kompak — label INLINE dengan chip (gaya Excel): tinggi
    baris dimensi ~1 baris (bukan 2), tabel anomali dapat ruang kembali.
[C] Minus merah GLOBAL — level model (PandasTableModel ForegroundRole):
    angka < 0 merah di semua tabel; 0/plus/teks/bool tidak.
[D] remove_followup_many — bulk lepas ✓: satu broadcast, satu persist,
    no-op tanpa broadcast.
[E] compare_quantity + JENIS — tabel mover cabang/item/baru/hilang
    berkolom JENIS (agg_jenis); bulan tanpa agg_jenis = perilaku lama
    PERSIS (regresi golden v2.10.0).
[F] PeriodeView v2.12.2 — header kolom 'Pembanding' → NAMA BULAN
    (render-layer; frame mentah kontrak tetap 'Pembanding'), ✓ follow-up
    di halaman cabang/item (tambah/lepas massal + sinkron in-place +
    baris tanpa pasangan anomali = revert centangan), auto-ciut kartu
    daftar file hanya di jalur muat-otomatis.
[G] AnomaliView ⤢/⛶ — ciutkan KPI+kontrol; layar penuh reparent tabel
    ASLI (interaksi tetap hidup) + pemulihan posisi layout saat ditutup.
[H] fmt_run_label — jargon 'key_akhir' → 'hari data'.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtCore import Qt

REPO = Path(__file__).resolve().parent.parent

_DAY_COLS = [str(d) for d in range(1, 32)]


def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


# ============================================================
# [A] WLabel heightForWidth
# ============================================================

class TestWLabelHFW:
    def test_flag_hfw_aktif(self):
        from PySide6.QtWidgets import QLabel
        from ui.widgets import WLabel
        app = _qapp()
        lb = WLabel("x" * 300)
        assert lb.hasHeightForWidth()
        assert lb.sizePolicy().hasHeightForWidth()
        # QLabel plain dengan wordWrap punya flag yang SAMA (paritas
        # perilaku layout — dulu WLabel kalah karena flag terhapus).
        plain = QLabel("y" * 300)
        plain.setWordWrap(True)
        assert plain.sizePolicy().hasHeightForWidth()

    def test_layout_memberi_tinggi_jujur_bukan_sizehint_persegi(self):
        """Regresi inti: di VBox lebar 900px, label 2-baris HARUS diberi
        ~heightForWidth (28px) — BUKAN sizeHint persegi (112px) yang
        mencuri 84px tinggi tabel di semua tab."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.widgets import WLabel
        app = _qapp()
        txt = ("💡 Klik baris = detail pop-up · klik 2× = fokus cabang+item · "
               "klik header = sort · centang ✓ = kumpulkan baris ke tab "
               "Follow Up · kolom BULAN LALU/PERUBAHAN muncul bila ada file "
               "pembanding (tab Banding Periode)")
        host = QWidget()
        lay = QVBoxLayout(host)
        lb = WLabel(txt)
        lay.addWidget(lb)
        stretch = QWidget()  # penanda agar label tak ditarik layout
        lay.addWidget(stretch, 1)
        host.resize(900, 400)
        host.show()
        app.processEvents()
        need = lb.heightForWidth(lb.width())
        # tinggi aktual ≤ kebutuhan nyata + toleransi 6px (bukan 4× lipat)
        assert lb.height() <= need + 6, (
            f"hint {lb.height()}px > kebutuhan {need}px (sizeHint persegi "
            "kembali dicari layout — flag hfw mati)")
        assert lb.height() < lb.sizeHint().height() - 30

    def test_tinggi_berubah_mengikuti_lebar(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from ui.widgets import WLabel
        app = _qapp()
        txt = "kata " * 40
        host = QWidget()
        lay = QVBoxLayout(host)
        lb = WLabel(txt)
        lay.addWidget(lb)
        lay.addStretch(1)  # label hanya dapat tinggi kebutuhannya
        host.resize(700, 400)
        host.show()
        app.processEvents()
        h_lebar = lb.height()
        host.resize(200, 400)
        app.processEvents()
        h_sempit = lb.height()
        assert h_sempit > h_lebar  # menyempit → baris bertambah → lebih tinggi


# ============================================================
# [B] SlicerBar kompak (label inline)
# ============================================================

class TestSlicerKompak:
    def _bar(self):
        from ui.state import AppContext
        from ui.widgets import SlicerBar
        app = _qapp()
        ctx = AppContext({})
        bar = SlicerBar(ctx)
        bar.set_dim_values("jenis", ["WASTE", "SUSUT", "TRIAL"])
        bar.set_dim_values("keterangan", ["Handling", "Cancel Nota"])
        bar.set_dim_values("status", ["Prioritas Tinggi", "Normal"])
        return bar

    def _hosted(self):
        """Bar di dalam VBox + stretch (konfigurasi persis kartu tabel
        tab Anomali) — layout memberi tinggi = kebutuhan nyata.
        Return (bar, host): host WAJIB dipegang (parent Python-only —
        tanpa referensi, C++ object terhapus & bar yatim)."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        app = _qapp()
        bar = self._bar()
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.addWidget(bar)
        lay.addStretch(1)
        host.resize(800, 400)
        host.show()
        app.processEvents()
        return bar, host

    def test_label_sebaris_dengan_chip(self):
        app = _qapp()
        bar, _host = self._hosted()
        from PySide6.QtWidgets import QLabel
        row, _flow = bar._rows["jenis"]
        chip = bar._chips["jenis"]["WASTE"]
        labels = [c for c in row.findChildren(QLabel)]
        assert labels, "label dimensi tak ketemu"
        assert abs(labels[0].y() - chip.y()) <= 2, (
            f"label y={labels[0].y()} vs chip y={chip.y()} — label masih "
            "makan baris sendiri")

    def test_tinggi_kompak(self):
        """3 dimensi × 1 baris + baris aksi ≈ ≤115px (dulu 137-148px)."""
        app = _qapp()
        bar, _host = self._hosted()
        assert bar.height() <= 115, f"slicer {bar.height()}px — masih boros"
        for key in ("jenis", "keterangan", "status"):
            row, _ = bar._rows[key]
            assert row.height() <= 30, (
                f"baris {key} {row.height()}px — label masih makan baris "
                "sendiri?")


# ============================================================
# [C] Minus merah global (model)
# ============================================================

class TestMinusMerah:
    def _model(self, df):
        from ui.models import PandasTableModel
        app = _qapp()
        return PandasTableModel(df)

    def test_negatif_merah_positif_tidak(self):
        df = pd.DataFrame({"Selisih": [-5.0, 3.0, -2.5, 0.0],
                           "Perubahan %": [-12.0, 28.5, 0.0, -0.5]})
        m = self._model(df)
        reds = [m.data(m.index(r, 0), Qt.ItemDataRole.ForegroundRole) for r in range(4)]
        for i in (0, 2):
            assert reds[i] is not None, f"baris {i} (-) harus merah"
        assert reds[1] is None  # 3.0 positif → warna default
        assert reds[3] is None  # 0.0 nol → bukan minus
        # nilai persen negatif juga merah (sumbernya float < 0)
        p = [m.data(m.index(r, 1), Qt.ItemDataRole.ForegroundRole) for r in range(4)]
        assert p[0] is not None and p[3] is not None
        assert p[2] is None  # 0.0

    def test_numpy_int_negatif_merah(self):
        import numpy as np
        df = pd.DataFrame({"Delta": np.array([-7, 7], dtype="int64")})
        m = self._model(df)
        assert m.data(m.index(0, 0), Qt.ItemDataRole.ForegroundRole) is not None
        assert m.data(m.index(1, 0), Qt.ItemDataRole.ForegroundRole) is None

    def test_teks_bool_nan_tidak_merah(self):
        df = pd.DataFrame({
            "Teks": ["BARU", "-item hilang"],
            "✓": [False, True],
            "X": [float("nan"), 1.0],
        })
        m = self._model(df)
        assert m.data(m.index(0, 0), Qt.ItemDataRole.ForegroundRole) is None
        assert m.data(m.index(1, 0), Qt.ItemDataRole.ForegroundRole) is None  # teks '-'
        assert m.data(m.index(0, 1), Qt.ItemDataRole.ForegroundRole) is None  # bool False
        assert m.data(m.index(0, 2), Qt.ItemDataRole.ForegroundRole) is None  # NaN

    def test_penanda_hari_menang_prioritas(self):
        """Sel hari tersangka merah tetap merah walau nilainya negatif /
        bukan — prioritas penanda follow-up > aturan minus."""
        from ui.models import PandasTableModel
        app = _qapp()
        from waste_anomaly.followup import CHECK_COL, FP_COL
        df = pd.DataFrame({
            CHECK_COL: [True],
            FP_COL: ["fp1"],
            "4": [-9.0],  # hari tersangka bernilai negatif
        })
        m = self._model(df)
        m.set_row_key_column(FP_COL)
        m.set_highlights({("fp1", "4")}, set())
        got = m.data(m.index(0, 2), Qt.ItemDataRole.ForegroundRole)
        assert got is not None  # merah (baik dari penanda maupun minus)


# ============================================================
# [D] remove_followup_many (bulk lepas)
# ============================================================

class TestRemoveFollowupMany:
    def _ctx(self):
        from ui.state import AppContext
        _qapp()
        return AppContext({})

    def test_bulk_hapus_satu_broadcast(self):
        ctx = self._ctx()
        ctx.add_followup_many(["a", "b", "c"])
        hits = []
        ctx.followup_changed.connect(lambda: hits.append(1))
        n = ctx.remove_followup_many(["a", "c"])
        assert n == 2
        assert ctx.followup_keys == ["b"]
        assert len(hits) == 1  # SATU broadcast

    def test_noop_tanpa_broadcast(self):
        ctx = self._ctx()
        ctx.add_followup_many(["a"])
        hits = []
        ctx.followup_changed.connect(lambda: hits.append(1))
        assert ctx.remove_followup_many(["zzz"]) == 0
        assert ctx.remove_followup_many([]) == 0
        assert hits == []
        assert ctx.followup_keys == ["a"]

    def test_duplikat_batch_dedup(self):
        ctx = self._ctx()
        ctx.add_followup_many(["a", "b"])
        n = ctx.remove_followup_many(["a", "a", "b", "b"])
        assert n == 2
        assert ctx.followup_keys == []


# ============================================================
# [E] compare_quantity + JENIS
# ============================================================

def _month_jenis(label: str, ka: int, rows: list) -> dict:
    """rows = [(jenis, resto, barang, total)] — lengkap dgn agg_jenis."""
    days = {str(d): 0.0 for d in range(1, 32)}
    agg = pd.DataFrame([
        {"NAMA RESTO": r, "NAMA BARANG": i, "TOTAL": t, "HARI AKTIF": 3,
         **days} for _j, r, i, t in rows])
    jt = pd.DataFrame({"JENIS": [j for j, *_ in rows],
                       "TOTAL": [t for *_x, t in rows]})
    aj = pd.DataFrame([
        {"NAMA RESTO": r, "NAMA BARANG": i, "JENIS": j, "TOTAL": t}
        for j, r, i, t in rows])
    return {"label": label, "agg": agg, "jenis_totals": jt,
            "key_akhir": ka, "agg_jenis": aj}


class TestCompareQuantityJenis:
    def test_items_berkolom_jenis_dan_nilai_split(self):
        from waste_anomaly.period_history import compare_quantity
        a = _month_jenis("Bulan Ini", 31, [
            ("WASTE", "R1", "X", 100.0), ("TRIAL", "R1", "X", 20.0)])
        b = _month_jenis("Juli 2026", 31, [("WASTE", "R1", "X", 80.0)])
        res = compare_quantity(a, b)
        items = res["items"]
        assert "JENIS" in items.columns
        rx = items[items["NAMA BARANG"] == "X"].set_index("JENIS")
        assert rx.loc["WASTE", "Bulan Ini"] == 100.0
        assert rx.loc["WASTE", "Pembanding"] == 80.0
        assert rx.loc["WASTE", "Selisih"] == 20.0
        assert rx.loc["TRIAL", "Bulan Ini"] == 20.0
        assert rx.loc["TRIAL", "Pembanding"] == 0.0  # TRIAL baru

    def test_branch_dan_baru_hilang_per_jenis(self):
        from waste_anomaly.period_history import compare_quantity
        a = _month_jenis("A", 31, [
            ("WASTE", "R1", "X", 100.0), ("WASTE", "R2", "Y", 30.0)])
        b = _month_jenis("B", 31, [
            ("WASTE", "R1", "X", 80.0), ("SUSUT", "R2", "Z", 10.0)])
        res = compare_quantity(a, b)
        branch = res["branch"]
        assert "JENIS" in branch.columns
        br = branch.set_index(["JENIS", "NAMA RESTO"])
        assert br.loc[("WASTE", "R1"), "Selisih"] == 20.0
        assert br.loc[("WASTE", "R2"), "Pembanding"] == 0.0
        assert br.loc[("SUSUT", "R2"), "Bulan Ini"] == 0.0
        # baru: WASTE R2 Y (pembanding 0); hilang: SUSUT R2 Z (bulan ini 0)
        assert set(map(tuple, res["new_items"][
            ["JENIS", "NAMA RESTO", "NAMA BARANG"]].to_numpy())) == {
            ("WASTE", "R2", "Y")}
        assert set(map(tuple, res["gone_items"][
            ["JENIS", "NAMA RESTO", "NAMA BARANG"]].to_numpy())) == {
            ("SUSUT", "R2", "Z")}

    def test_tanpa_agg_jenis_perilaku_lama(self):
        """Regresi golden: bulan tanpa agg_jenis (fixture v2.10.0) →
        struktur LAMA persis (tanpa kolom JENIS)."""
        from waste_anomaly.period_history import compare_quantity

        def _old(label, ka, rows):  # fixture _month v2.10.0 (tanpa agg_jenis)
            days = {str(d): 0.0 for d in range(1, 32)}
            agg = pd.DataFrame([
                {"NAMA RESTO": r, "NAMA BARANG": i, "TOTAL": t,
                 "HARI AKTIF": 3, **days} for r, i, t in rows])
            jt = pd.DataFrame({"JENIS": ["WASTE"],
                               "TOTAL": [sum(t for *_x, t in rows)]})
            return {"label": label, "agg": agg, "jenis_totals": jt,
                    "key_akhir": ka}

        a = _old("A", 31, [("R1", "X", 100.0), ("R1", "Y", 50.0)])
        b = _old("B", 31, [("R1", "X", 80.0), ("R2", "Z", 10.0)])
        res = compare_quantity(a, b)
        for key in ("branch", "items", "new_items", "gone_items"):
            assert "JENIS" not in res[key].columns, (
                f"{key} tak boleh berubah utk bulan tanpa agg_jenis")
        items = res["items"]
        rx = items[items["NAMA BARANG"] == "X"].set_index("NAMA RESTO")
        assert rx.loc["R1", "Selisih"] == 20.0

    def test_satu_sisi_agg_jenis_cukup(self):
        """A punya agg_jenis, B tidak (dan sebaliknya) → JENIS tetap
        tampil (sisi kosong = 0)."""
        from waste_anomaly.period_history import compare_quantity
        a = _month_jenis("A", 31, [("WASTE", "R1", "X", 100.0)])

        def _old(label, ka, rows):
            days = {str(d): 0.0 for d in range(1, 32)}
            agg = pd.DataFrame([
                {"NAMA RESTO": r, "NAMA BARANG": i, "TOTAL": t,
                 "HARI AKTIF": 3, **days} for r, i, t in rows])
            return {"label": label, "agg": agg,
                    "jenis_totals": pd.DataFrame(columns=["JENIS", "TOTAL"]),
                    "key_akhir": ka}

        b = _old("B", 31, [("R1", "X", 80.0)])
        res = compare_quantity(a, b)
        assert "JENIS" in res["items"].columns
        row = res["items"].iloc[0]
        # sisi tanpa agg_jenis = tak ada rincian per-jenis → 0 (kasus ini
        # tak pernah terjadi di data nyata — A/B/Tipikal selalu membawa
        # agg_jenis; kontrak: JENIS tetap tampil, sisi kosong = 0).
        assert row["JENIS"] == "WASTE"
        assert row["Bulan Ini"] == 100.0
        assert row["Pembanding"] == 0.0
        assert row["Selisih"] == 100.0


# ============================================================
# [F] PeriodeView v2.12.2 — nama bulan + ✓ + auto-ciut
# ============================================================

def _wb_bulan(tmp_path: Path, name: str = "REKAP MENTAH JULI 2026.xlsx",
              trial: bool = False) -> Path:
    """Workbook bulan sintetis (pola test_v2100) — opsional +baris TRIAL."""
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): float(base) for d in range(1, 32)}
        data["24"] = float(day24)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": "MIE (V.20)",
            "NAMA RESTO": "1042.KWGGAL", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 100, 2.0)
    _row("WASTE", "Cancel Nota", 94, 0.0)
    if trial:
        _row("TRIAL", "Over Stock", 10, 0.0)
    out = tmp_path / name
    pd.DataFrame(rows).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _df_a() -> pd.DataFrame:
    """Dataset bulan berjalan (A) — 3 baris: WASTE×2 + TRIAL×1."""
    rows = []

    def _row(jenis, ket, day24, base):
        data = {str(d): float(base) for d in range(1, 32)}
        data["24"] = float(day24)
        rows.append({
            "SOURCE DATA": "WASTE BAHAN dan PACKAGING", "JENIS": jenis,
            "KETERANGAN": ket, "NAMA BARANG": "MIE (V.20)",
            "NAMA RESTO": "1042.KWGGAL", "SATUAN": "PCS",
            **data, "TOTAL": float(sum(data.values())),
        })

    _row("WASTE", "Handling", 150.0, 2.0)
    _row("WASTE", "Cancel Nota", 94.0, 0.0)
    _row("TRIAL", "Over Stock", 10.0, 0.0)
    return pd.DataFrame(rows)


def _make_view(tmp_path, monkeypatch, entries):
    from waste_anomaly import period_history as ph
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    app = _qapp()
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    ph.save_history_entries(entries, store)
    ctx = AppContext({})
    view = PeriodeView(ctx)
    return view, ctx


def _wait(view, app, timeout_s: float = 30.0) -> None:
    t0 = time.perf_counter()
    while view._running:
        app.processEvents()
        time.sleep(0.01)
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("worker pembanding tidak selesai")


def _armed_view(tmp_path, monkeypatch, trial_in_b: bool = False):
    """View + dataset A + 1 file pembanding termuat + render hasil."""
    from waste_anomaly.period_history import load_history_file
    view, ctx = _make_view(
        tmp_path, monkeypatch,
        [{"path": str(_wb_bulan(tmp_path, trial=trial_in_b)),
          "label": None}])
    app = _qapp()
    _wait(view, app)
    ctx.set_dataset(_df_a(), {"key_akhir": 31})
    app.processEvents()
    view._refresh_result()
    app.processEvents()
    return view, ctx, app


class TestPeriodeHeaderNamaBulan:
    def test_header_kolom_pakai_nama_bulan(self, tmp_path, monkeypatch):
        from waste_anomaly.followup import CHECK_COL
        view, _ctx, app = _armed_view(tmp_path, monkeypatch)
        m = view._tables["summary"].model()
        cols = [str(m.headerData(i, Qt.Orientation.Horizontal)) for i in range(m.columnCount())]
        # 'Pembanding' DIGANTI nama bulan; 'Bulan Ini' tetap.
        assert "Pembanding" not in cols
        assert "Juli 2026" in cols
        assert "Bulan Ini" in cols
        # halaman FU juga ter-rename (items)
        mi = view._tables["items"].model()
        icols = [str(mi.headerData(i, Qt.Orientation.Horizontal))
                 for i in range(mi.columnCount())]
        assert "Juli 2026" in icols and CHECK_COL in icols

    def test_frame_mentah_kontrak_tetap_pembanding(self, tmp_path, monkeypatch):
        """Golden guard: res/_res (bahan drill + layar penuh) TETAP
        berkolom 'Pembanding' — rename hanya di salinan render."""
        view, _ctx, _app = _armed_view(tmp_path, monkeypatch)
        assert "Pembanding" in view._res["summary"].columns
        assert "Pembanding" in view._res["items"].columns

    def test_tipikal_label_median(self, tmp_path, monkeypatch):
        from ui.view_periode import PeriodeView
        # _col_header_b: dict tipikal (months_count) → label median.
        view, _ctx = _make_view(tmp_path, monkeypatch, [])
        assert view._col_header_b(
            {"months_count": 3}) == "Tipikal — median 3 bulan"
        assert view._col_header_b({"label": "Juli 2026"}) == "Juli 2026"
        assert view._col_header_b(None) == "Pembanding"

    def test_kolom_jenis_tampil(self, tmp_path, monkeypatch):
        view, _ctx, _app = _armed_view(tmp_path, monkeypatch)
        mi = view._tables["items"].model()
        icols = [str(mi.headerData(i, Qt.Orientation.Horizontal))
                 for i in range(mi.columnCount())]
        assert "JENIS" in icols


class TestPeriodeCheckFollowup:
    def test_centang_item_menambah_baris_anomali(self, tmp_path, monkeypatch):
        from waste_anomaly.followup import CHECK_COL
        view, ctx, app = _armed_view(tmp_path, monkeypatch)
        mi = view._tables["items"].model()
        # baris WASTE (2 baris anomali A) vs TRIAL (1 baris — bila B
        # tanpa TRIAL, TRIAL = item baru, tetap punya pasangan anomali).
        rows = {str(mi.record(r).get("JENIS")): r for r in range(mi.rowCount())}
        r_waste = rows["WASTE"]
        # flip programatik = klik user (setData → sinyal → handler)
        assert mi.setData(mi.index(r_waste, 0), True, Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        assert len(ctx.followup_keys) == 2  # 2 baris WASTE A
        # ✓ di tabel ikut konsisten (in-place, tanpa reset)
        assert bool(mi.dataframe.iloc[r_waste][CHECK_COL])
        # uncheck → keluar semua sekaligus (satu broadcast)
        assert mi.setData(mi.index(r_waste, 0), False, Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        assert ctx.followup_keys == []

    def test_centang_cabang_massal_dan_sinkron_antartabel(self,
                                                          tmp_path,
                                                          monkeypatch):
        from waste_anomaly.followup import CHECK_COL
        view, ctx, app = _armed_view(tmp_path, monkeypatch)
        mb = view._tables["branch"].model()
        assert mb.rowCount() >= 2  # WASTE + TRIAL @ resto itu
        r = 0
        rec = mb.record(r)
        jenis = str(rec.get("JENIS"))
        assert mb.setData(mb.index(r, 0), True, Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        n_expect = 2 if jenis == "WASTE" else 1
        assert len(ctx.followup_keys) == n_expect
        # sinkron in-place: tabel items (baris jenis sama) ikut tercentang
        mi = view._tables["items"].model()
        for r2 in range(mi.rowCount()):
            rec2 = mi.record(r2)
            want = str(rec2.get("JENIS")) == jenis
            assert bool(rec2[CHECK_COL]) == want, (
                f"✓ items baris {r2} ({rec2.get('JENIS')}) tak sinkron")

    def test_baris_tanpa_pasangan_revert_centangan(self, tmp_path, monkeypatch):
        """Item HANYA di bulan pembanding (tak ada di A) → klik ✓ tak
        mengubah state; centangan visual dikembalikan False."""
        from waste_anomaly.followup import CHECK_COL
        # B diberi item ekstra: restoran itu tak ada di A → fps kosong.
        wb = _wb_bulan(tmp_path)
        df_b = pd.read_excel(wb)
        extra = dict(df_b.iloc[0])
        extra["NAMA BARANG"] = "EKSTRA (LAMA)"
        df_b = pd.concat([df_b, pd.DataFrame([extra])], ignore_index=True)
        df_b.to_excel(wb, sheet_name="REKAP MENTAH", index=False)
        view, ctx = _make_view(tmp_path, monkeypatch,
                               [{"path": str(wb), "label": None}])
        app = _qapp()
        _wait(view, app)
        ctx.set_dataset(_df_a(), {"key_akhir": 31})
        app.processEvents()
        view._refresh_result()
        app.processEvents()
        mi = view._tables["items"].model()
        target = None
        for r in range(mi.rowCount()):
            if str(mi.record(r).get("NAMA BARANG")) == "EKSTRA (LAMA)":
                target = r
                break
        assert target is not None, "baris item-hanya-di-B tak ketemu"
        before = list(ctx.followup_keys)
        assert mi.setData(mi.index(target, 0), True, Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        assert ctx.followup_keys == before  # state tak berubah
        assert not bool(mi.dataframe.iloc[target][CHECK_COL])  # revert

    def test_gone_items_tanpa_kolom_centang(self, tmp_path, monkeypatch):
        view, _ctx, _app = _armed_view(tmp_path, monkeypatch)
        from waste_anomaly.followup import CHECK_COL
        mg = view._tables["gone_items"].model()
        assert CHECK_COL not in mg.dataframe.columns
        ms = view._tables["summary"].model()
        assert CHECK_COL not in ms.dataframe.columns


class TestAutoCiutDaftarFile:
    def test_muat_otomatis_ciut(self, tmp_path, monkeypatch):
        view, _ctx = _make_view(
            tmp_path, monkeypatch,
            [{"path": str(_wb_bulan(tmp_path)), "label": None}])
        app = _qapp()
        _wait(view, app)
        app.processEvents()
        assert view._card_files.isHidden(), (
            "kartu daftar file harus auto-ciut setelah muat otomatis")
        assert "Tampilkan Daftar File" in view._btn_expand.text()

    def test_muat_manual_tidak_ciut(self, tmp_path, monkeypatch):
        """User menambah / memuat ulang → daftar tetap terlihat (tidak
        dikejut ciut sendiri saat sedang mengelola file)."""
        view, _ctx = _make_view(
            tmp_path, monkeypatch,
            [{"path": str(_wb_bulan(tmp_path)), "label": None}])
        app = _qapp()
        _wait(view, app)
        app.processEvents()
        # user buka kembali daftar → lalu muat ulang (manual)
        view._on_expand()
        app.processEvents()
        assert not view._card_files.isHidden()
        view._on_reload()
        _wait(view, app)
        app.processEvents()
        assert not view._card_files.isHidden(), (
            "muat ulang manual tidak boleh menyembunyikan daftar file")


# ============================================================
# [G] AnomaliView ⤢ / ⛶
# ============================================================

class TestAnomaliMelebarkan:
    def _view(self):
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        app = _qapp()
        ctx = AppContext({})
        view = AnomaliView(ctx)
        return ctx, view, app

    def _data(self, ctx, view, app):
        view.show()
        ctx.set_dataset(_df_a(), {"key_akhir": 31})
        view.refresh()
        app.processEvents()
        return view._table.model()

    def test_toggle_perbesar_kpi_kontrol(self):
        ctx, view, app = self._view()
        m = self._data(ctx, view, app)
        assert not view._kpi.isHidden()
        view._on_expand()
        app.processEvents()
        assert view._kpi.isHidden() and view._ctrl.isHidden()
        assert "Tampilkan" in view._btn_expand.text()
        view._on_expand()
        app.processEvents()
        assert not view._kpi.isHidden() and not view._ctrl.isHidden()
        assert "Perbesar" in view._btn_expand.text()

    def test_layar_penuh_reparent_dan_pulihkan(self):
        ctx, view, app = self._view()
        m = self._data(ctx, view, app)
        n_rows = m.rowCount()
        card = view._table.parent()
        idx_before = view._tcl.indexOf(view._table)
        view._on_fullscreen()
        app.processEvents()
        dlg = view._fs_dlg
        assert dlg is not None and dlg.isVisible()
        assert view._table.parent() is dlg  # reparent ke jendela penuh
        # interaksi tetap hidup: model & data sama
        assert view._table.model() is m and m.rowCount() == n_rows
        dlg.close()
        app.processEvents()
        # pemulihan: parent kembali kartu + posisi layout asli
        assert view._table.parent() is card
        assert view._tcl.indexOf(view._table) == idx_before
        assert view._fs_dlg is not None  # dialog dipakai ulang, tak dibuang

    def test_layar_penuh_idempoten_ganda(self):
        """Tutup dua kali (Esc + close) → tabel tak teracak urutannya."""
        ctx, view, app = self._view()
        m = self._data(ctx, view, app)
        idx_before = view._tcl.indexOf(view._table)
        view._on_fullscreen()
        app.processEvents()
        view._restore_table_from_fs()
        view._restore_table_from_fs()  # no-op kedua
        app.processEvents()
        assert view._tcl.indexOf(view._table) == idx_before

    def test_layar_penuh_kosong_guard(self):
        ctx, view, app = self._view()
        view.show()
        app.processEvents()
        # tanpa data → jendela TIDAK dibuka (guard status, bukan crash)
        view._on_fullscreen()
        app.processEvents()
        assert view._fs_dlg is None


# ============================================================
# [H] fmt_run_label — jargon hilang
# ============================================================

class TestFmtRunLabel:
    def test_tanpa_jargon_key_akhir(self):
        from ui.view_periode import fmt_run_label
        s = fmt_run_label({"total_rows": 25901}, 31)
        assert "key_akhir" not in s
        assert "31 hari data" in s
        assert "25.901" in s
        assert fmt_run_label(None, 31) == "(run terakhir)"
