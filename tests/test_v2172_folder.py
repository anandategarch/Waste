"""test_v2172_folder.py — fitur v2.17.2: Proses dari Folder (file BJMHAS-style).

Permintaan user: "ada opsi untuk proses file langsung dari folder
C:\\KERJA\\...\\1. DEVIASI WEEKLY nah itu isi nya file bjmhas itu dan
ambil sheet rekap mentah. Struktur nya hampir sama dengan file rekap
mentah. jadi ada 2 opsi proses pipeline yaitu: Proses dari folder atau
pilih sendiri (format REKAP MENTAH_..._TEGAR)."

File BJMHAS = sheet REKAP MENTAH TANPA kolom NAMA RESTO (resto identity =
nama file). File TEGAR = punya kolom NAMA RESTO.

Implementasi:
- waste_anomaly/rekap_import.py: find_rekap_sheet_lenient (deteksi sheet
  tanpa NAMA RESTO wajib — JENIS + NAMA BARANG + ≥3 hari) + load_rekap_folder
  (scan folder, baca sheet, sintesis NAMA RESTO dari filename bila absen,
  gabung, tulis temp .xlsx).
- ui/workers.py: FolderScanWorker (QThread — done/failed).
- ui/view_pipeline.py: tombol "Proses dari Folder…" + folder picker +
  wiring worker → _start pipeline pada temp.

[F172-1] _detect_header_row_lenient: deteksi header tanpa NAMA RESTO
         (JENIS + NAMA BARANG + ≥3 hari); None bila tak ada.
[F172-2] find_rekap_sheet_lenient: file BJMHAS (tanpa NAMA RESTO) →
         ("REKAP MENTAH", 0); file tanpa sheet rekap → raise.
[F172-3] load_rekap_folder: folder 2 file BJMHAS-style → gabung, NAMA
         RESTO disintesis dari filename (2 file di "synthesized"), temp
         file punya NAMA RESTO → find_rekap_sheet STRICT deteksi.
[F172-4] load_rekap_folder: folder CAMPURAN (BJMHAS + TEGAR) → keduanya
         diproses; hanya BJMHAS di "synthesized"; TEGAR keep-own.
[F172-5] load_rekap_folder: folder kosong / tanpa rekap → raise
         RekapImportError (bukan diam).
[F172-6] load_rekap_folder: file non-rekap di-skip (bukan crash) +
         dicatat di "skipped".
[F172-7] FolderScanWorker: QThread subclass; done emits dict; failed
         emits (str, str) bila folder tak ada.
[F172-8] UI: PipelineView punya _btn_folder "Proses dari Folder…" +
         tooltip menyebut BJMHAS + handler _on_import_folder/_on_folder_done/
         _on_folder_failed/_cleanup_folder_temp.
[F172-9] ikon "folder" terdaftar di icons registry (bukan null pixmap).
[F172-10] pipeline pada temp file folder-flow menghasilkan dataset dgn
          NAMA RESTO terisi (sintesis) + TOTAL BOM hidup (bila baris BOM).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent

# Header 2 ambang: E9/F63/F7/F82/F401 — fatal & unused imports.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qapp():
    """QApplication offscreen tunggal per proses (pola test_ui_structure)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# FIXTURES — file BJMHAS-style (TANPA NAMA RESTO) + TEGAR-style (DENGAN)
# ============================================================

_BASE_COLS = ["KATEGORI", "SOURCE DATA", "JENIS", "STATUS", "NAMA BARANG",
              "KETERANGAN", "PENYEBAB TERJADINYA WASTE", "SATUAN"]
_DAYS = [str(d) for d in range(1, 32)]


def _bjmhas_rows(stem: str, n_waste: int = 3) -> pd.DataFrame:
    """File BJMHAS-style: TANPA kolom NAMA RESTO (resto = filename)."""
    rows = []
    for i in range(n_waste):
        row = {c: "" for c in _BASE_COLS}
        row.update({
            "KATEGORI": "COM DEVIASI - RESTO",
            "SOURCE DATA": "WASTE BAHAN",
            "JENIS": "WASTE",
            "STATUS": "DEVIASI",
            "NAMA BARANG": f"{stem} ITEM {i}",
            "KETERANGAN": "Handling",
            "PENYEBAB TERJADINYA WASTE": "x",
            "SATUAN": "GR",
        })
        for d in _DAYS:
            row[d] = 10 * (i + 1) if d == "17" else 0  # hari 17 = tersangka
        rows.append(row)
    # Baris BOM (TOTAL BOM hidup lewat inject_bom_from_raw_rows)
    bom = {c: "" for c in _BASE_COLS}
    bom.update({"JENIS": "BOM", "NAMA BARANG": f"{stem} ITEM 0",
                "SATUAN": "GR"})
    for d in _DAYS:
        bom[d] = 100
    rows.append(bom)
    cols = _BASE_COLS + _DAYS + ["TOTAL", "DATA NEW ITEM", "selisih"]
    df = pd.DataFrame(rows, columns=cols)
    df["TOTAL"] = df[_DAYS].sum(axis=1)
    return df


def _tegar_rows(resto: str, n_waste: int = 2) -> pd.DataFrame:
    """File TEGAR-style: DENGAN kolom NAMA RESTO (multi-resto)."""
    df = _bjmhas_rows(resto, n_waste)
    df["NAMA RESTO"] = resto
    return df


def _write_xlsx(df: pd.DataFrame, path: Path, sheet: str = "REKAP MENTAH"):
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet, index=False)


# ============================================================
# [F172-1] _detect_header_row_lenient
# ============================================================
class TestDetectHeaderLenient:
    def test_deteksi_tanpa_nama_resto(self):
        from waste_anomaly.rekap_import import _detect_header_row_lenient
        # peek raw (header=None) — baris 0 = NAMA KOLOM (header BJMHAS-style,
        # tanpa NAMA RESTO). _detect_header_row_lenient baca nilai sel.
        cols = list(_bjmhas_rows("X").columns)
        peek = pd.DataFrame([cols])
        hr = _detect_header_row_lenient(peek)
        assert hr == 0, "header baris 0 harus terdeteksi tanpa NAMA RESTO"

    def test_none_bila_tak_ada_jenis_nama_barang(self):
        from waste_anomaly.rekap_import import _detect_header_row_lenient
        peek = pd.DataFrame([["a", "b", "c", "1", "2", "3"]])
        assert _detect_header_row_lenient(peek) is None

    def test_none_bila_kurang_dari_3_hari(self):
        from waste_anomaly.rekap_import import _detect_header_row_lenient
        peek = pd.DataFrame([["WASTE", "ITEM", "GR", "1", "2"]])  # hanya 2 hari
        assert _detect_header_row_lenient(peek) is None


# ============================================================
# [F172-2] find_rekap_sheet_lenient
# ============================================================
class TestFindRekapSheetLenient:
    def test_bjmhas_tanpa_nama_resto(self, tmp_path):
        from waste_anomaly.rekap_import import find_rekap_sheet_lenient
        fp = tmp_path / "BJMHAS.xlsx"
        _write_xlsx(_bjmhas_rows("BJMHAS"), fp)
        name, off = find_rekap_sheet_lenient(fp)
        assert name == "REKAP MENTAH"
        assert off == 0

    def test_tanpa_sheet_rekap_raise(self, tmp_path):
        from waste_anomaly.rekap_import import (
            RekapImportError, find_rekap_sheet_lenient)
        fp = tmp_path / "nosheet.xlsx"
        with pd.ExcelWriter(fp, engine="openpyxl") as w:
            pd.DataFrame({"A": [1, 2]}).to_excel(w, sheet_name="OTHER", index=False)
        with pytest.raises(RekapImportError):
            find_rekap_sheet_lenient(fp)


# ============================================================
# [F172-3..6] load_rekap_folder
# ============================================================
class TestLoadRekapFolder:
    def test_folder_2_bjmhas_sintesis_nama_resto(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder, find_rekap_sheet
        from waste_anomaly.utils import load_config
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")
        _write_xlsx(_bjmhas_rows("BDGUKU"), tmp_path / "BDGUKU.xlsx")
        res = load_rekap_folder(tmp_path, load_config())
        assert sorted(res["files"]) == ["BDGUKU.xlsx", "BJMHAS.xlsx"]
        assert sorted(res["synthesized"]) == ["BDGUKU.xlsx", "BJMHAS.xlsx"]
        assert res["rows_total"] > 0
        assert res["skipped"] == []
        # Temp file punya NAMA RESTO → find_rekap_sheet STRICT deteksi.
        name, off = find_rekap_sheet(res["temp_path"], load_config())
        assert name == "REKAP MENTAH"
        # Baca temp: NAMA RESTO terisi (BJMHAS + BDGUKU).
        df = pd.read_excel(res["temp_path"], sheet_name="REKAP MENTAH", dtype=object)
        restos = set(df["NAMA RESTO"].dropna().unique())
        assert "BJMHAS" in restos and "BDGUKU" in restos
        os.unlink(res["temp_path"])

    def test_folder_engine_dan_elapsed_dilog(self, tmp_path):
        """v2.17.3 — result punya 'engine' (calamine/openpyxl) + 'elapsed_s'."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")
        res = load_rekap_folder(tmp_path, load_config())
        assert res["engine"] in ("calamine", "openpyxl")
        assert isinstance(res["elapsed_s"], float)
        assert res["elapsed_s"] >= 0.0
        os.unlink(res["temp_path"])

    def test_folder_20_file_paralel_cepat(self, tmp_path):
        """v2.17.3 — 20 file diproses paralel (ThreadPoolExecutor max 4).
        Semua diproses, NAMA RESTO disintesis per-file, gabungan utuh."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        restos = [f"R{i:02d}" for i in range(20)]
        for r in restos:
            _write_xlsx(_bjmhas_rows(r), tmp_path / f"{r}.xlsx")
        res = load_rekap_folder(tmp_path, load_config())
        assert len(res["files"]) == 20
        assert sorted(res["synthesized"]) == sorted(f"{r}.xlsx" for r in restos)
        assert res["rows_total"] > 0
        # Engine dilog + elapsed masuk akal (< 30s utk 20 file kecil).
        assert res["elapsed_s"] < 30.0
        os.unlink(res["temp_path"])

    def test_config_default_deviasi_folder_ada(self):
        """v2.17.3 — config.json punya key default_deviasi_folder."""
        from waste_anomaly.utils import load_config
        cfg = load_config()
        assert "default_deviasi_folder" in cfg
        val = cfg["default_deviasi_folder"]
        assert isinstance(val, str) and val
        # Path user: C:\KERJA\1. RESTO\9.NEW QUERY\1. DEVIASI WEEKLY
        assert "DEVIASI WEEKLY" in val

    def test_folder_campuran_bjmhas_dan_tegar(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")  # no RESTO
        _write_xlsx(_tegar_rows("1216.XYZ"), tmp_path / "TEGAR.xlsx")  # has RESTO
        res = load_rekap_folder(tmp_path, load_config())
        assert "BJMHAS.xlsx" in res["synthesized"]
        assert "TEGAR.xlsx" not in res["synthesized"]  # TEGAR keep-own RESTO
        assert res["rows_total"] > 0
        os.unlink(res["temp_path"])

    def test_folder_kosong_raise(self, tmp_path):
        from waste_anomaly.rekap_import import (
            RekapImportError, load_rekap_folder)
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(RekapImportError, match="Tidak ada file"):
            load_rekap_folder(empty)

    def test_folder_tanpa_rekap_raise_dgn_skipped(self, tmp_path):
        from waste_anomaly.rekap_import import (
            RekapImportError, load_rekap_folder)
        from waste_anomaly.utils import load_config
        fp = tmp_path / "norekap.xlsx"
        with pd.ExcelWriter(fp, engine="openpyxl") as w:
            pd.DataFrame({"A": [1]}).to_excel(w, sheet_name="X", index=False)
        with pytest.raises(RekapImportError, match="Tidak ada file"):
            load_rekap_folder(tmp_path, load_config())

    def test_folder_non_rekap_diskip_bukan_crash(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        # 1 file BJMHAS (valid) + 1 file non-rekap (skip).
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")
        with pd.ExcelWriter(tmp_path / "junk.xlsx", engine="openpyxl") as w:
            pd.DataFrame({"A": [1]}).to_excel(w, sheet_name="JUNK", index=False)
        res = load_rekap_folder(tmp_path, load_config())
        assert res["files"] == ["BJMHAS.xlsx"]
        assert any(n == "junk.xlsx" for n, _ in res["skipped"])
        os.unlink(res["temp_path"])

    def test_folder_tidak_ada_raise(self):
        from waste_anomaly.rekap_import import (
            RekapImportError, load_rekap_folder)
        with pytest.raises(RekapImportError, match="Folder tidak ditemukan"):
            load_rekap_folder("/path/yang/tidak/ada/12345")


# ============================================================
# [F172-7] FolderScanWorker
# ============================================================
class TestFolderScanWorker:
    def test_qthread_subclass_dgn_sinyal(self):
        from PySide6.QtCore import QThread
        from ui.workers import FolderScanWorker
        _qapp()
        assert issubclass(FolderScanWorker, QThread)
        w = FolderScanWorker("/tmp")
        # Signal ada (class-level).
        assert hasattr(FolderScanWorker, "done")
        assert hasattr(FolderScanWorker, "failed")
        w.deleteLater()

    def test_done_emits_dict(self, tmp_path, monkeypatch):
        """Worker jalan di thread — drain processEvents sampai done."""
        from ui.workers import FolderScanWorker
        import time
        app = _qapp()
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")
        w = FolderScanWorker(str(tmp_path))
        results: list[dict] = []
        failures: list[tuple] = []
        w.done.connect(lambda r: results.append(r))
        w.failed.connect(lambda m, tb: failures.append((m, tb)))
        w.start()
        # Drain event loop sampai signal tiba (bukan isRunning — thread
        # bisa selesai sangat cepat sebelum cek pertama).
        t0 = time.monotonic()
        while not results and not failures and time.monotonic() - t0 < 30:
            app.processEvents()
            time.sleep(0.05)
        w.wait(5000)
        assert not failures, f"worker failed: {failures}"
        assert len(results) == 1
        r = results[0]
        assert r["files"] == ["BJMHAS.xlsx"]
        assert "BJMHAS.xlsx" in r["synthesized"]
        assert "temp_path" in r
        os.unlink(r["temp_path"])

    def test_failed_emits_bila_folder_tidak_ada(self):
        from ui.workers import FolderScanWorker
        import time
        app = _qapp()
        w = FolderScanWorker("/path/tidak/ada/xyz/999")
        failures: list[tuple] = []
        w.failed.connect(lambda m, tb: failures.append((m, tb)))
        w.start()
        t0 = time.monotonic()
        while not failures and time.monotonic() - t0 < 10:
            app.processEvents()
            time.sleep(0.05)
        w.wait(5000)
        assert failures, "failed signal harus ter-emit utk folder tak ada"


# ============================================================
# [F172-8] UI — tombol folder + handler
# ============================================================
class TestUIFolderButton:
    def _win(self):
        from ui.app import MainWindow
        _qapp()
        return MainWindow()

    def test_tombol_folder_ada_dgn_teks_dan_ikon(self):
        win = self._win()
        try:
            pv = win._views[0][1]  # PipelineView = tab 0 (v2.17.0 reorder)
            assert hasattr(pv, "_btn_folder")
            assert "Proses dari Folder" in pv._btn_folder.text()
            assert not pv._btn_folder.icon().isNull(), "ikon folder harus terpasang"
        finally:
            win.close()

    def test_tooltip_menyebut_bjmhas_dan_sintesis(self):
        win = self._win()
        try:
            pv = win._views[0][1]
            tip = pv._btn_folder.toolTip()
            assert "BJMHAS" in tip
            assert "NAMA RESTO" in tip
            assert "sementara" in tip.lower() or "temp" in tip.lower()
        finally:
            win.close()

    def test_handler_wired(self):
        win = self._win()
        try:
            pv = win._views[0][1]
            for m in ("_on_import_folder", "_on_folder_done",
                      "_on_folder_failed", "_cleanup_folder_temp"):
                assert callable(getattr(pv, m)), f"{m} harus ada & callable"
            assert pv._folder_worker is None  # awal bersih
            assert pv._folder_temp is None
        finally:
            win.close()

    def test_start_guard_saat_scan_jalan(self, monkeypatch):
        """v2.17.4 — _start() HARUS di-guard bila folder scan sedang jalan
        (tidak error 'workbook belum dipilih'). Bug: user klik Mulai
        Pipeline / Enter di workbook field SEBELUM scan selesai → workbook
        kosong → error menyesatkan."""
        from PySide6.QtWidgets import QMessageBox
        # Suppress dialog (guard pakai QMessageBox.information).
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
        monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
        win = self._win()
        try:
            pv = win._views[0][1]
            # Simulasi: folder scan sedang jalan (worker != None) +
            # workbook field KOSONG (temp belum terisi).
            pv._folder_worker = object()  # mock worker running
            pv._ent_workbook.setText("")  # workbook kosong
            # _start() HARUS return early (guard), TIDAK raise / error.
            pv._start()
            # Tidak ada exception = pass. Workbook tetap kosong (pipeline
            # belum jalan — menunggu scan selesai).
            assert pv._ent_workbook.text() == ""
            assert not pv._running  # pipeline belum jalan
        finally:
            # v2.18.0: closeEvent kini MELACAK _folder_worker (audit UI-2 —
            # dulu close saat scan = qFatal). Mock object() tanpa wait() akan
            # menabrak dialog "proses masih berjalan" + AttributeError di
            # wait — reset dulu (skenario: scan selesai) sebelum close.
            pv._folder_worker = None
            win.close()


# ============================================================
# [F172-9] ikon folder di registry
# ============================================================
class TestFolderIcon:
    def test_folder_icon_terdaftar_dan_render(self):
        from ui.icons import icon_pixmap, has_icon, icon_names
        assert has_icon("folder")
        assert "folder" in icon_names()
        pm = icon_pixmap("folder", 24)
        assert not pm.isNull(), "pixmap folder harus ter-render"


# ============================================================
# [F172-11] v2.17.3 — edit DISABLED utk file folder-temp
# (permintaan user: "revisi file hanya tersedia jika aku pilih file
# sendiri bukan dari folder")
# ============================================================
class TestEditDisabledForFolderTemp:
    def test_detect_folder_temp_by_name(self):
        from ui.view_anomali import _workbook_is_folder_temp
        assert _workbook_is_folder_temp("/tmp/rekap_folder_abc123.xlsx") is True
        assert _workbook_is_folder_temp("C:/x/rekap_folder_XYZ.xlsx") is True
        # File asli (mode Pilih File Sendiri) → False.
        assert _workbook_is_folder_temp(
            "C:/data/REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx") is False
        assert _workbook_is_folder_temp("BJMHAS.xlsx") is False
        # None / kosong → False.
        assert _workbook_is_folder_temp(None) is False
        assert _workbook_is_folder_temp("") is False

    def test_save_button_disabled_saat_folder_temp(self, tmp_path):
        """Pop-up detail: save button DISABLED bila workbook = folder temp."""
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel, _FOLDER_TEMP_PREFIX
        import pandas
        _qapp()
        # ctx dgn summary workbook_path = folder temp.
        ctx = AppContext({})
        ctx.summary = {"workbook_path": f"/tmp/{_FOLDER_TEMP_PREFIX}xyz.xlsx"}
        # Record minimal dgn __SRC_ROW (supaya kondisi lain True, isolasi
        # efek folder-temp).
        rec = pandas.Series({"NAMA RESTO": "X", "NAMA BARANG": "Y",
                             "__SRC_ROW": 5, "ANOMALY STATUS": "Normal",
                             "ANOMALY SCORE": 0})
        panel = DetailPanel(ctx)
        panel.show_record(rec)
        # Tombol Simpan harus DISABLED (folder temp) meski __SRC_ROW ada.
        assert panel._save_btn is not None
        assert panel._save_btn.isEnabled() is False
        tip = panel._save_btn.toolTip()
        assert "SEMENTERARA" in tip or "sementara" in tip.lower()

    def test_save_button_enabled_untuk_file_asli(self, tmp_path):
        """Pop-up detail: save button ENABLED bila workbook = file asli
        (mode Pilih File Sendiri) + __SRC_ROW ada."""
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        import pandas
        _qapp()
        ctx = AppContext({})
        ctx.summary = {"workbook_path": str(tmp_path / "REKAP MENTAH_TEGAR.xlsx")}
        rec = pandas.Series({"NAMA RESTO": "X", "NAMA BARANG": "Y",
                             "__SRC_ROW": 5, "ANOMALY STATUS": "Normal",
                             "ANOMALY SCORE": 0})
        panel = DetailPanel(ctx)
        panel.show_record(rec)
        assert panel._save_btn is not None
        assert panel._save_btn.isEnabled() is True


# ============================================================
# [F172-10] pipeline pada temp folder-flow → dataset dgn NAMA RESTO
# ============================================================
class TestPipelineOnFolderTemp:
    def test_pipeline_temp_hasilkan_dataset_nama_resto(self, tmp_path):
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        from waste_anomaly.pipeline import run_pipeline
        _write_xlsx(_bjmhas_rows("BJMHAS"), tmp_path / "BJMHAS.xlsx")
        _write_xlsx(_bjmhas_rows("BDGUKU"), tmp_path / "BDGUKU.xlsx")
        res = load_rekap_folder(tmp_path, load_config())
        out = run_pipeline(res["temp_path"], key_akhir=31)["df"]
        # NAMA RESTO terisi (sintesis dari filename) + stage_01 filter W/S/T.
        restos = set(out["NAMA RESTO"].dropna().unique())
        assert "BJMHAS" in restos
        assert "BDGUKU" in restos
        # TOTAL BOM hidup (baris BOM di fixture → inject_bom_from_raw_rows).
        assert out["TOTAL BOM"].notna().any()
        os.unlink(res["temp_path"])


# ============================================================
# [F172-12] v2.17.5 — JENIS prefix angka distrip ('2.WASTE'→'WASTE')
# (bug 17/20 resto: file dgn JENIS ber-prefix angka dibuang Stage 1)
# ============================================================
class TestJenisPrefixStrip:
    def test_normalize_strip_prefix_angka(self):
        """normalize_rekap_values: '2.WASTE'→'WASTE', '3.SUSUT'→'SUSUT',
        '4.TRIAL'→'TRIAL'. Tanpa strip, '2.WASTE' dianggap non-WASTE →
        dibuang Stage 1 → resto hilang dari analisa."""
        from waste_anomaly.rekap_import import normalize_rekap_values, _KEEP_JENIS
        import pandas as pd
        df = pd.DataFrame({
            "JENIS": ["2.WASTE", "3.SUSUT", "4.TRIAL", "1.DEVIASI",
                      "WASTE", "waste ", "5.LOSS SURPLUS", "BOM"],
            "SATUAN": ["GR"] * 8,
        })
        out = normalize_rekap_values(df)
        jenis = list(out["JENIS"])
        # Prefix distrip → canonical.
        assert jenis[0] == "WASTE", f"2.WASTE→WASTE, got {jenis[0]}"
        assert jenis[1] == "SUSUT", f"3.SUSUT→SUSUT, got {jenis[1]}"
        assert jenis[2] == "TRIAL", f"4.TRIAL→TRIAL, got {jenis[2]}"
        # Non-W/S/T prefix distrip tapi tetap non-canonical (dibuang Stage 1).
        assert jenis[3] == "DEVIASI"
        assert jenis[6] == "LOSS SURPLUS"
        # Canonical tetap utuh.
        assert jenis[4] == "WASTE"
        assert jenis[5] == "WASTE"  # 'waste ' → strip+upper
        # 5 baris W/S/T canonical (lolos Stage 1): sebelumnya hanya 2.
        n_keep = sum(1 for v in jenis if v in _KEEP_JENIS)
        assert n_keep == 5, f"5 W/S/T canonical, got {n_keep}"

    def test_folder_dgn_jenis_prefix_20_resto_masuk(self, tmp_path):
        """Simulasi bug user: 3 file ber-prefix JENIS ('2.WASTE') + 17 file
        canonical. Sebelum fix: 3 resto hilang (17 masuk). Setelah fix:
        20 resto masuk (prefix distrip → WASTE → lolos Stage 1)."""
        from waste_anomaly.rekap_import import load_rekap_folder
        from waste_anomaly.utils import load_config
        from waste_anomaly.pipeline import run_pipeline
        # 17 file canonical (JENIS='WASTE') + 3 file ber-prefix ('2.WASTE')
        for i in range(17):
            _write_xlsx(_bjmhas_rows(f"CANON{i:02d}"), tmp_path / f"CANON{i:02d}.xlsx")
        for i in range(3):
            df_pre = _bjmhas_rows(f"PRE{i}")
            # Override JENIS: 'WASTE' → '2.WASTE' (prefix angka)
            df_pre.loc[df_pre["JENIS"] == "WASTE", "JENIS"] = "2.WASTE"
            df_pre.loc[df_pre["JENIS"] == "SUSUT", "JENIS"] = "3.SUSUT"
            df_pre.loc[df_pre["JENIS"] == "TRIAL", "JENIS"] = "4.TRIAL"
            _write_xlsx(df_pre, tmp_path / f"PRE{i}.xlsx")
        res = load_rekap_folder(tmp_path, load_config())
        assert len(res["files"]) == 20
        out = run_pipeline(res["temp_path"], key_akhir=31)["df"]
        restos = set(out["NAMA RESTO"].dropna().unique())
        # SEMUA 20 resto masuk (termasuk 3 ber-prefix — JENIS distrip).
        assert len(restos) == 20, f"20 resto harus masuk, got {len(restos)}"
        for i in range(3):
            assert f"PRE{i}" in restos, f"PRE{i} harus masuk (JENIS prefix distrip)"
        os.unlink(res["temp_path"])
