"""test_v2133.py — v2.13.3 (sisa): ⑯ re-import hasil tindak lanjut.

- import_followup_workbook: round-trip file ekspor terisi → resolved
  {fp: info}; baris kosong di-skip; kolom kunci hilang → error jujur;
  file/sheet salah → error (tidak raise).
- load/save_resolved: atomic + file korup di-backup .bad.
- AppContext.apply_followup_resolved: merge + persist + SATU broadcast;
  no-op tanpa broadcast.
- FollowUpView: kolom STATUS TL + PIC muncul bila ada resolusi; label
  "selesai X/Y".
- ⑧ branch_trend / TREN scorecard DIHAPUS v2.18.5 bersama tab Scorecard
  Cabang & waste_anomaly/insights.py (permintaan user).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


REPO = Path(__file__).resolve().parent.parent


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# [C] RE-IMPORT WORKBOOK (⑯)
# ============================================================

def _tl_workbook(tmp: Path, filled: bool = True) -> Path:
    df = pd.DataFrame({
        "SOURCE DATA": ["W", "W"],
        "JENIS": ["WASTE", "WASTE"],
        "KETERANGAN": ["Handling", "Handling"],
        "NAMA BARANG": ["MIE", "TEH"],
        "NAMA RESTO": ["R1", "R2"],
        "SATUAN": ["GR", "GR"],
        "TOTAL": [100.0, 10.0], "AVG": [3.0, 0.3], "MAX": [50.0, 8.0],
        "1": [50.0, 0.0], "2": [50.0, 0.0], "3": [0.0, 10.0],
        "PIC": ["Tegar", None] if filled else [None, None],
        "KATEGORI": ["Proses", None] if filled else [None, None],
        "PENYEBAB TERJADINYA WASTE": (
            ["salah timbang", None] if filled else [None, None]),
    })
    path = tmp / "hasil_tl.xlsx"
    df.to_excel(path, sheet_name="FOLLOW UP", index=False)
    return path


class TestImportWorkbook:
    def test_round_trip_terisi(self):
        from waste_anomaly.followup import (fingerprint_series,
                                            import_followup_workbook)
        with tempfile.TemporaryDirectory() as td:
            p = _tl_workbook(Path(td))
            res = import_followup_workbook(str(p))
            assert not res.get("error")
            assert res["n_rows"] == 2 and res["n_filled"] == 1
            fp_map = res["resolved"]
            assert len(fp_map) == 1
            fp = next(iter(fp_map))
            assert fp_map[fp]["PIC"] == "Tegar"
            assert fp_map[fp]["KATEGORI"] == "Proses"
            # fp harus cocok dgn fungsi asli (kolom ✓ tak ada di file —
            # tiruan tanpa kolom ✓; fingerprint identik)
            local = pd.read_excel(p, sheet_name="FOLLOW UP")
            local = local.rename(
                columns={c: str(c) for c in local.columns})
            assert str(fingerprint_series(local).iloc[0]) == fp

    def test_semua_kosong_tak_terisi(self):
        from waste_anomaly.followup import import_followup_workbook
        with tempfile.TemporaryDirectory() as td:
            p = _tl_workbook(Path(td), filled=False)
            res = import_followup_workbook(str(p))
            assert not res.get("error")
            assert res["n_filled"] == 0 and res["resolved"] == {}

    def test_file_tak_ada_error(self):
        from waste_anomaly.followup import import_followup_workbook
        res = import_followup_workbook("/tmp/tidak_ada_12345.xlsx")
        assert res.get("error")

    def test_kolom_kunci_hilang_error(self):
        from waste_anomaly.followup import import_followup_workbook
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "salah.xlsx"
            pd.DataFrame({"TOTAL": [1.0]}).to_excel(p, index=False,
                                                    sheet_name="FOLLOW UP")
            res = import_followup_workbook(str(p))
            assert res.get("error")

    def test_sheet_lain_error_jujur(self):
        from waste_anomaly.followup import import_followup_workbook
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nosheet.xlsx"
            pd.DataFrame({"A": [1]}).to_excel(p, index=False,
                                              sheet_name="Sheet1")
            res = import_followup_workbook(str(p))
            assert res.get("error")


# ============================================================
# [D] PERSISTENSI RESOLVED (atomic + korup)
# ============================================================

class TestResolvedPersist:
    def test_save_load_round_trip(self):
        from waste_anomaly.followup import load_resolved, save_resolved
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "resolved.json"
            data = {"abc": {"PIC": "T", "ts": "2026-10-01T00:00:00"}}
            assert save_resolved(data, p)
            assert load_resolved(p) == data

    def test_korup_dibackup(self):
        from waste_anomaly.followup import load_resolved
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "resolved.json"
            p.write_text("{bukan json", encoding="utf-8")
            assert load_resolved(p) == {}
            assert p.with_suffix(".json.bad").exists()

    def test_absen_kosong(self):
        from waste_anomaly.followup import load_resolved
        with tempfile.TemporaryDirectory() as td:
            assert load_resolved(Path(td) / "takada.json") == {}


# ============================================================
# [E] AppContext.apply_followup_resolved
# ============================================================

class TestApplyResolved:
    def _ctx(self, path=None):
        _qapp()
        from ui.state import AppContext
        return AppContext({}, followup_path=path)

    def test_merge_broadcast_persist(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "f.json"
            ctx = self._ctx(str(base))
            n = {"emit": 0}
            ctx.followup_changed.connect(
                lambda: n.__setitem__("emit", n["emit"] + 1))
            info = {"PIC": "Tegar", "ts": "2026-10-01"}
            assert ctx.apply_followup_resolved({"fp1": info}) == 1
            assert n["emit"] == 1
            # no-op: dict sama persis → tanpa broadcast
            assert ctx.apply_followup_resolved({"fp1": info}) == 0
            assert n["emit"] == 1
            # persist ke followup_resolved.json samping f.json
            saved = json.loads(
                (base.with_name("followup_resolved.json"))
                .read_text(encoding="utf-8"))
            assert saved["rows"]["fp1"]["PIC"] == "Tegar"
            # reload → masih ada
            ctx2 = self._ctx(str(base))
            assert ctx2.followup_resolved.get("fp1", {}).get("PIC") == "Tegar"

    def test_tanpa_path_tak_persist_tapi_broadcast(self):
        ctx = self._ctx()
        n = {"emit": 0}
        ctx.followup_changed.connect(
            lambda: n.__setitem__("emit", n["emit"] + 1))
        assert ctx.apply_followup_resolved({"x": {"PIC": "A"}}) == 1
        assert n["emit"] == 1
        assert ctx.followup_resolved["x"]["PIC"] == "A"


# ============================================================
# [F] FollowUpView — kolom STATUS TL + label selesai X/Y
# ============================================================

def _df_fu() -> pd.DataFrame:
    return pd.DataFrame({
        "SOURCE DATA": ["W1", "W2"],
        "JENIS": ["WASTE", "SUSUT"],
        "KETERANGAN": ["Cancel Nota", "Alat/Mesin"],
        "NAMA BARANG": ["AYAM", "BEBEK"],
        "NAMA RESTO": ["R1", "R2"],
        "SATUAN": ["PCS", "KG"],
        "TOTAL": [30.0, 15.0],
        "AVG": [1.0, 0.5], "MAX": [20.0, 15.0],
        "AVG AKTIF": [10.0, 7.5],
        "HARI TERSANGKA": [pd.NA, 4],
        "HARI MAX": [2, 4],
        "1": [10, 0], "2": [20, 0], "4": [0, 15],
    })


class TestFollowupViewStatusTL:
    def test_kolom_status_tl_pic(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_followup import FollowUpView
        from waste_anomaly.followup import fingerprint_series
        with tempfile.TemporaryDirectory() as td:
            ctx = AppContext({}, followup_path=str(Path(td) / "f.json"))
            ctx.set_dataset(_df_fu(), {"key_akhir": 31})
            fps = fingerprint_series(_df_fu())
            ctx.add_followup_many([fps.iloc[0], fps.iloc[1]])
            ctx.apply_followup_resolved({
                str(fps.iloc[0]): {"PIC": "Tegar", "KATEGORI": "Proses"}})
            view = FollowUpView(ctx)
            view.refresh()
            cols = list(view._table.model().dataframe.columns)
            assert "STATUS TL" in cols and "PIC" in cols
            df = view._table.model().dataframe
            row0 = df[df["NAMA BARANG"] == "AYAM"].iloc[0]
            row1 = df[df["NAMA BARANG"] == "BEBEK"].iloc[0]
            assert row0["STATUS TL"] == "Selesai"
            assert row0["PIC"] == "Tegar"
            assert row1["STATUS TL"] == "—"
            assert "selesai 1/2" in view._lbl_info.text()
            view.close()
            view.deleteLater()

    def test_tanpa_resolved_tak_ada_kolom(self):
        _qapp()
        from ui.state import AppContext
        from ui.view_followup import FollowUpView
        from waste_anomaly.followup import fingerprint_series
        ctx = AppContext({})
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0]])
        view = FollowUpView(ctx)
        view.refresh()
        cols = list(view._table.model().dataframe.columns)
        assert "STATUS TL" not in cols
        view.close()
        view.deleteLater()
