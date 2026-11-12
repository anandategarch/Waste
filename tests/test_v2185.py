"""test_v2185.py — v2.18.5: 4 permintaan user (UX Banding + pembersihan).

[U1] RESTO INTERSECTION — "misal bulan ini ada resto CKRBOS tetapi bulan
     kemarin gak ada, maka gak perlu muncul di banding periode karna
     belum ada pembandingnya. Begitu juga misal bulan kemarin ada bulan
     ini gak ada gak perlu ditampilkan."
     compare_quantity menyaring resto SATU-SISI dari SEMUA tabel banding
     (Cabang/Item/Baru/Hilang) — join resto = intersection, bukan outer.
     Ringkasan sebulan TETAP angka penuh. Jumlah disembunyikan dilaporkan
     via resto_only_a/resto_only_b → pesan status tab Banding.
[U2] SORT "KEBALIK" — "tombol sort urut naik seperti nya kebalik ya?
     aku tekan sort naik malah mulai dari nlai terkecil."
     Urut Naik = nilai TERBESAR dulu (naik = yang besar naik ke atas),
     Urut Turun = terkecil dulu — tombol funnel + SortControl konsisten.
[U3] PILIH 1 DATA — "di tombol filter bisa ditampilkan hanya pilih
     misal aku pengen pilih 1 data itu aja dibanding harus uncek satu
     per satu." Klik-ganda nilai = hanya nilai itu; tombol ◉ Hanya Ini =
     centang hanya hasil pencarian.
[U4] SCORECARD DIHAPUS — "scorecard cabang hapus aja dan dead code nya."
     Tab + ui/view_scorecard.py + waste_anomaly/insights.py + alias
     PEER_KEYS dibuang; 6 → 5 tab.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# Helper — entri bulan sintetis (bentuk _month_dict, pola v2.18.4)
# ============================================================

def _month(label: str, rows: list[dict]) -> dict:
    _alias = {"JENIS": "jenis", "KETERANGAN": "ket"}

    def _frame(keys):
        recs = []
        for r in rows:
            rec = {"NAMA RESTO": r["resto"], "NAMA BARANG": r["barang"],
                   "TOTAL": r["total"]}
            for k in keys:
                src = _alias.get(k, k)
                if src in r:
                    rec[k] = r[src]
            recs.append(rec)
        return pd.DataFrame(recs)

    agg = _frame(["NAMA RESTO", "NAMA BARANG"])
    for d in range(1, 21):
        agg[str(d)] = [r.get("hari", {}).get(str(d), 0.0) for r in rows]
    jenis_tot: dict = {}
    for r in rows:
        jenis_tot[r.get("jenis", "WASTE")] = (
            jenis_tot.get(r.get("jenis", "WASTE"), 0.0) + r["total"])
    return {
        "label": label, "key_akhir": 20, "agg": agg,
        "jenis_totals": pd.DataFrame(
            [{"JENIS": j, "TOTAL": t} for j, t in jenis_tot.items()]),
        "agg_jenis": _frame(["NAMA RESTO", "NAMA BARANG", "JENIS"]),
        "agg_detail": _frame(
            ["NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN"]),
        "resto_count": len({r["resto"] for r in rows}),
        "item_count": len({r["barang"] for r in rows}),
        "rows_kept": len(rows), "rows_raw": len(rows), "error": None,
    }


def _row(resto, barang, total, hari=None, jenis="WASTE", ket="Internal"):
    return {"resto": resto, "barang": barang, "jenis": jenis, "ket": ket,
            "total": float(total),
            "hari": {str(d): float(v) for d, v in (hari or {}).items()}}


_A = [  # bulan berjalan: R1 & R2 punya pembanding; CKRBOS BARU (A-only)
    _row("R1", "AYAM", 100, {5: 100}),
    _row("R1", "MIE BARU", 30, {7: 30}),      # item baru di resto COMMON
    _row("R2", "AYAM", 50, {5: 50}),
    _row("CKRBOS", "AYAM", 70, {5: 70}),      # resto A-only → disembunyikan
]
_B = [  # pembanding: R1 & R2; OLDRESTO sudah tutup (B-only)
    _row("R1", "AYAM", 80, {5: 80}),
    _row("R2", "AYAM", 50, {5: 50}),
    _row("R2", "MIE HILANG", 10, {3: 10}),    # item hilang di resto COMMON
    _row("OLDRESTO", "AYAM", 99, {5: 99}),    # resto B-only → disembunyikan
]


# ============================================================
# [U1] RESTO INTERSECTION — compare_quantity
# ============================================================

class TestRestoIntersection:
    def test_resto_satu_sisi_disembunyikan_semua_tabel(self):
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", _A),
                               _month("Juli 2026", _B))
        # Cabang: HANYA resto yang ada di kedua bulan
        assert set(res["branch"]["NAMA RESTO"]) == {"R1", "R2"}
        # Item mover: baris CKRBOS/OLDRESTO tak tampil
        assert set(res["items"]["NAMA RESTO"]) <= {"R1", "R2"}
        # BARU/HILANG: item-level di resto common tetap sah…
        assert list(res["new_items"]["NAMA BARANG"]) == ["MIE BARU"]
        assert list(res["gone_items"]["NAMA BARANG"]) == ["MIE HILANG"]
        # …tapi resto satu-sisi TIDAK (dulu CKRBAS/OLDRESTO masok semua)
        assert "CKRBOS" not in set(res["new_items"]["NAMA RESTO"])
        assert "OLDRESTO" not in set(res["gone_items"]["NAMA RESTO"])
        # jumlah disembunyikan dilaporkan jujur
        assert res["resto_only_a"] == 1 and res["resto_only_b"] == 1
        assert res["resto_overlap"] == 2

    def test_ringkasan_tetap_angka_bulan_penuh(self):
        """Total Waste / Cabang Aktif = metrik SEBULAN penuh — BUKAN
        disaring intersection (CKRBOS tetap dihitung bulan ini)."""
        from waste_anomaly.period_history import compare_quantity
        res = compare_quantity(_month("Bulan Ini", _A),
                               _month("Juli 2026", _B))
        s = res["summary"].set_index("Metrik")
        assert s.loc["Total Waste", "Bulan Ini"] == 250.0   # 100+30+50+70
        assert s.loc["Total Waste", "Pembanding"] == 239.0  # 80+50+10+99
        assert int(s.loc["Cabang Aktif", "Bulan Ini"]) == 3
        assert int(s.loc["Cabang Aktif", "Pembanding"]) == 3

    def test_semua_resto_common_perilaku_lama_persis(self):
        """Tanpa resto satu-sisi → hasil sama dgn kontrak v2.18.4
        (intersection tak mengubah apa pun bila kedua sisi utuh)."""
        from waste_anomaly.period_history import compare_quantity
        a = [_row("R1", "AYAM", 100, {5: 100}), _row("R2", "AYAM", 50, {5: 50})]
        b = [_row("R1", "AYAM", 80, {5: 80}), _row("R2", "AYAM", 60, {5: 60})]
        res = compare_quantity(_month("Bulan Ini", a), _month("Juli 2026", b))
        assert set(res["branch"]["NAMA RESTO"]) == {"R1", "R2"}
        assert res["resto_only_a"] == 0 and res["resto_only_b"] == 0
        assert len(res["new_items"]) == 0 and len(res["gone_items"]) == 0


# ============================================================
# [U1-UI] pesan status tab Banding menyebut jumlah tersembunyi
# ============================================================

class TestPesanBandingPeriode:
    def test_label_menyebut_cabang_disembunyikan(self):
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        app = _qapp()
        ctx = AppContext({})
        # bulan berjalan (A) — kolom hari utk aggregate_current
        rows = []
        for r in _A:
            data = {str(d): 0.0 for d in range(1, 21)}
            data.update(r["hari"])
            rows.append({"NAMA RESTO": r["resto"], "NAMA BARANG": r["barang"],
                         "JENIS": r["jenis"], "KETERANGAN": r["ket"],
                         "SATUAN": "GR", **data,
                         "TOTAL": float(sum(data.values()))})
        ctx.set_dataset(pd.DataFrame(rows), {"key_akhir": 20})
        view = PeriodeView(ctx)
        view._entries = [{"path": "b.xlsx", "label": "Juli 2026"}]
        view._loaded = {"b.xlsx": _month("Juli 2026", _B)}
        view._combo_version = -1  # paksa rebuild combo
        view._refresh_result()
        app.processEvents()
        txt = view._lbl_compare.text()
        assert "2 cabang tanpa pembanding disembunyikan" in txt
        assert "1 hanya di bulan ini, 1 hanya di pembanding" in txt
        # tabel cabang benar-benar tersaring (bukan cuma pesan)
        branch = view._tables["branch"].model().dataframe
        assert set(branch["NAMA RESTO"]) == {"R1", "R2"}
        view.close()
        view.deleteLater()


# ============================================================
# [U2] SORT — Naik = BESAR dulu (funnel menu + SortControl)
# ============================================================

class TestSortNaikBesarDulu:
    def _table(self):
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        t.set_dataframe(pd.DataFrame({
            "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL"],
            "TOTAL": [10.0, 20.0, 5.0, 1.0],
        }))
        t.resize(500, 200)
        t.show()
        app.processEvents()
        return t

    def _menu(self, t):
        t.setup_header_filters({"TOTAL": "total"}, lambda *a: None,
                               lambda c: None)
        hdr = t.horizontalHeader()
        app = _qapp()
        hdr._open_menu(1)  # kolom TOTAL (numerik)
        app.processEvents()
        return hdr._menu, app

    def _btn(self, menu, needle):
        from PySide6.QtWidgets import QPushButton
        return next(b for b in menu.findChildren(QPushButton)
                    if needle in b.text())

    def test_tombol_urut_naik_besar_dulu(self):
        """v2.18.5: tekan 'Urut Naik' → nilai TERBESAR di baris pertama
        (dulu terkecil — user: 'kebalik')."""
        t = self._table()
        menu, app = self._menu(t)
        assert "besar dulu" in self._btn(menu, "Urut Naik").text()
        self._btn(menu, "Urut Naik").click()
        app.processEvents()
        assert float(t.model().record(0)["TOTAL"]) == 20.0
        assert float(t.model().record(3)["TOTAL"]) == 1.0
        t.close()

    def test_tombol_urut_turun_kecil_dulu(self):
        t = self._table()
        menu, app = self._menu(t)
        self._btn(menu, "Urut Turun").click()
        app.processEvents()
        assert float(t.model().record(0)["TOTAL"]) == 1.0
        assert float(t.model().record(3)["TOTAL"]) == 20.0
        t.close()

    def test_sortcontrol_naik_default_besar_dulu(self):
        """SortControl (toolbar Anomali + dialog banding): default =
        Naik (besar dulu); toggle → Turun (kecil dulu)."""
        from ui.widgets import DataTable, SortControl
        app = _qapp()
        t = DataTable()
        t.set_dataframe(pd.DataFrame({"TOTAL": [10.0, 20.0, 5.0, 1.0]}))
        t.resize(400, 200)
        sc = SortControl(t)
        assert "Naik" in sc._dir.text() and "besar dulu" in sc._dir.text()
        sc.refresh_columns()
        sc._cb.setCurrentIndex(sc._cb.findData("TOTAL"))
        app.processEvents()
        assert float(t.model().record(0)["TOTAL"]) == 20.0  # Naik = besar
        sc._dir.click()
        app.processEvents()
        assert "Turun" in sc._dir.text() and "kecil dulu" in sc._dir.text()
        assert float(t.model().record(0)["TOTAL"]) == 1.0   # Turun = kecil
        t.close()


# ============================================================
# [U3] FILTER — pilih 1 nilai tanpa uncek satu per satu
# ============================================================

class TestFilterPilihSatu:
    def _menu(self):
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        t.set_dataframe(pd.DataFrame({
            "JENIS": ["WASTE", "WASTE", "SUSUT", "TRIAL"],
        }))
        t.resize(400, 200)
        t.show()
        calls = []
        t.setup_header_filters(
            {"JENIS": "jenis"},
            lambda col, key, vals: calls.append((col, key, vals)),
            lambda col: None)
        hdr = t.horizontalHeader()
        hdr._open_menu(0)
        app.processEvents()
        return t, hdr._menu, calls, app

    def _item(self, menu, needle):
        return next(menu._lw.item(i) for i in range(menu._lw.count())
                    if needle in menu._lw.item(i).text())

    def test_klik_ganda_nilai_hanya_nilai_itu(self):
        """Klik-ganda 'SUSUT' → HANYA SUSUT tercentang (semua nilai lain
        dilepas) + apply langsung — pengganti uncek satu per satu."""
        from PySide6.QtCore import Qt
        t, menu, calls, app = self._menu()
        menu._on_double_item(self._item(menu, "SUSUT"))
        app.processEvents()
        assert calls[-1] == ("JENIS", "jenis", ["SUSUT"])
        assert menu._checked == {"WASTE": False, "SUSUT": True,
                                 "TRIAL": False}
        # tambah 1 nilai lain dgn klik biasa tetap bisa (menu terbuka)
        it = self._item(menu, "TRIAL")
        it.setCheckState(Qt.CheckState.Checked)
        menu._apply_now()
        assert sorted(calls[-1][2]) == ["SUSUT", "TRIAL"]
        t.close()

    def test_hanya_ini_tombol_hasil_cari(self):
        """Ketik 'su' → tombol ◉ Hanya Ini aktif → centang HANYA nilai
        yang cocok pencarian; tanpa kata kunci tombol mati."""
        t, menu, calls, app = self._menu()
        assert not menu._b_only.isEnabled()  # tanpa kata kunci
        menu._ed.setText("su")               # cocok: SUSUT saja
        app.processEvents()
        assert menu._b_only.isEnabled()
        menu._only_search()
        app.processEvents()
        assert calls[-1] == ("JENIS", "jenis", ["SUSUT"])
        t.close()

    def test_hanya_ini_cari_kosong_tak_apply_senyap(self):
        """0 nilai cocok → JANGAN melepas seluruh filter senyap."""
        t, menu, calls, app = self._menu()
        menu._ed.setText("zzz")
        app.processEvents()
        menu._only_search()
        assert calls == []  # tak pernah apply
        t.close()

    def test_pilih_semua_kembali_setelah_hanya_ini(self):
        t, menu, calls, app = self._menu()
        menu._on_double_item(self._item(menu, "SUSUT"))
        menu._pick_all()
        app.processEvents()
        assert calls[-1] == ("JENIS", "jenis", None)
        t.close()


# ============================================================
# [U4] SCORECARD + DEAD CODE DIHAPUS
# ============================================================

class TestScorecardDihapus:
    def test_modul_dan_view_terhapus(self):
        import importlib.util
        assert importlib.util.find_spec("waste_anomaly.insights") is None
        assert not (REPO / "ui" / "view_scorecard.py").exists()

    def test_app_tanpa_scorecard_view(self):
        import ui.app as ap
        assert not hasattr(ap, "ScorecardView")

    def test_alias_peer_keys_dead_code_dibuang(self):
        import waste_anomaly.profile as pr
        assert not hasattr(pr, "PEER_KEYS")  # konsumen terakhir = insights

    def test_mainwindow_enam_tab(self):
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        assert win._tabs.count() == 6
        assert "Scorecard" not in " ".join(
            win._tabs.tabText(i) for i in range(6))
        win.close()


# ============================================================
# VERSI — pin triple (pola test_v2139)
# ============================================================

class TestVersi:
    def test_versi_pin(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        assert APP_VERSION == __version__ == \
            load_config().get("version") == "2.18.7"
