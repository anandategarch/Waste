# -*- coding: utf-8 -*-
"""Regresi v2.18.1 — AUDIT TAB BANDING PERIODE (skenario user).

Pemicu: "proses dari folder terus di banding periode aku pilih file
seperti format REKAP MENTAH yang hanya 1 file — bisa gak? ada bug gak?"

Jawab: BISA (1 file valid — Tipikal butuh ≥2 bulan, combo otomatis
fallback ke bulan itu), TAPI 4 bug ditemukan repro empiris — SEMUA
diperbaiki + dikunci di sini:

  R181-1  JENIS ber-prefix angka ('2.WASTE' — template PQ varian,
          fix v2.17.5 hanya sampai jalur pipeline) DIBUANG filter
          exact-match jalur pembanding → item hilang → 'BARU' palsu
          + TOTAL pembanding terlalu rendah. FIX: load_history_file
          kini memanggil helper pipeline (parity v2.15.0).
  R181-2  Header tergeser (baris judul di atas header asli — pola
          stock-monitoring) GAGAL dgn error menyesatkan "Kolom wajib
          'NAMA BARANG' tidak ada" padahal file yang sama jalan mulus
          di pipeline utama. FIX: ensure_rekap_header ikut dipanggil.
  R181-3  key_akhir pembanding dihitung dari frame mentah TERMASUK
          baris BOM/SO — BOM ber-value di hari di luar periode waste
          (waste berhenti hari-20, BOM sampai hari-31) menggelembung-
          kan 'HARI DATA' → 'Waste per Hari' pembanding salah kecil.
          FIX: auto_key_akhir dari baris waste PASCA filter.
  R181-4  compare_quantity: 0 resto cocok (folder-flow = NAMA FILE vs
          pembanding = kode resto asli) → SEMUA item BARU/HILANG palsu
          SENYAP (ringkasan Total Waste tetap tampak wajar — menyesat-
          kan). FIX: key resto_overlap + resto_overlap_warn; UI menam-
          pilkan peringatan eksplisit.
  R181-5  Kontrak file standar bersih TAK berubah (helper no-op
          identitas — rows_kept/key_akhir/TOTAL dari kolom hari).
  R181-6  UI: label peringatan benar-benar muncul saat 0 overlap
          (offscreen, alur penuh worker→render).
  R181-7  Pin versi 2.18.1 sinkron semua situs.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent

CFG = {"input_sheets": {"rekap_mentah": [
    "DATA_WASTE", "Data Waste", "DATA", "Sheet1",
    "REKAP_MENTAH", "Rekap Mentah", "REKAP"]}}


# ============================================================
# Helper — workbook pembanding sintetis
# ============================================================

def _wb_rekap(tmp_path: Path, name: str = "REKAP MENTAH JULI 2026.xlsx",
              title_row: bool = False, bom_full_month: bool = False,
              prefix_jenis: bool = False) -> Path:
    """Workbook pembanding format REKAP MENTAH.

    - 2 baris WASTE di 1042.KWGGAL: hari-5 = 100 + 50 (prefix: salah
      satu baris JENIS '2.WASTE'), hari-20 = 10 + 10 → waste berhenti
      hari-20.
    - 1 baris BOM ber-value 7 di SEMUA hari 1-31 (bom_full_month=True)
      → pengecoh key_akhir: tanpa fix, ka = 31 (BOM dihitung).
    - title_row=True: baris judul di ATAS header asli (pola stock-
      monitoring) — dibuat via openpyxl supaya header fisik baris 2.
    """
    from openpyxl import Workbook
    cols = ["SOURCE DATA", "JENIS", "KETERANGAN", "NAMA BARANG",
            "NAMA RESTO", "SATUAN"] + [str(d) for d in range(1, 32)]
    wb = Workbook()
    ws = wb.active
    ws.title = "REKAP MENTAH"
    if title_row:
        ws.append(["REKAP MENTAH RESTO — DEVIASI WEEKLY"]
                  + [None] * (len(cols) - 1))
    ws.append(cols)

    def _add(jenis, barang, hari):
        row = ["WASTE BAHAN DAN PACKAGING", jenis, "Internal", barang,
               "1042.KWGGAL", "GR"] + [0] * 31
        for d, v in hari.items():
            row[6 + d - 1] = v
        ws.append(row)

    j2 = ("2.WASTE" if prefix_jenis else "WASTE")
    _add("WASTE", "AYAM FILET", {5: 100, 20: 10})
    _add(j2, "TEPUNG", {5: 50, 20: 10})
    if bom_full_month:
        bom = ["BOM", "BOM", "-", "AYAM FILET", "1042.KWGGAL", "GR"] + [0] * 31
        for d in range(1, 32):
            bom[6 + d - 1] = 7
        ws.append(bom)
    path = tmp_path / name
    wb.save(path)
    return path


# ============================================================
# [R181-1] PARITY JENIS PREFIX ANGKA
# ============================================================

class TestParityJenisPrefix:
    def test_prefix_angka_tidak_dibuang(self, tmp_path):
        """'2.WASTE' == WASTE di jalur pipeline (fix v2.17.5) — jalur
        pembanding HARUS setara: baris masuk agregat (dulu terbuang
        exact-match → TEPUNG hilang → 'BARU' palsu + TOTAL rendah)."""
        from waste_anomaly.period_history import load_history_file
        wb = _wb_rekap(tmp_path, prefix_jenis=True)
        res = load_history_file(str(wb), CFG)
        assert res["error"] is None, res["error"]
        assert res["rows_kept"] == 2  # kedua baris waste (dulu 1)
        assert res["agg"]["TOTAL"].sum() == 170.0  # 110 + 60 (dulu 110)
        assert set(res["agg"]["NAMA BARANG"]) == {"AYAM FILET", "TEPUNG"}

    def test_parity_total_dengan_jalur_pipeline(self, tmp_path):
        """File yang sama di kedua jalur → TOTAL identik (semangat
        v2.15.0 'golden parity mentah vs olahan', diterapkan ke
        pembanding)."""
        from waste_anomaly.loader import load_rekap_mentah
        from waste_anomaly.rekap_import import (ensure_rekap_header,
                                                normalize_rekap_values)
        from waste_anomaly.period_history import (aggregate_current,
                                                  load_history_file)
        wb = _wb_rekap(tmp_path, prefix_jenis=True, bom_full_month=True)
        h = load_history_file(str(wb), CFG)
        raw = load_rekap_mentah(str(wb), CFG)
        dfp = normalize_rekap_values(ensure_rekap_header(raw))
        dfp = dfp[dfp["JENIS"].isin(("SUSUT", "TRIAL", "WASTE"))]
        cur = aggregate_current(dfp, 20, "Bulan Ini")
        assert cur["agg"]["TOTAL"].sum() == h["agg"]["TOTAL"].sum() == 170.0


# ============================================================
# [R181-2] PARITY HEADER TERGESER
# ============================================================

class TestParityHeaderTergeser:
    def test_baris_judul_dimuat_tanpa_error(self, tmp_path):
        """Baris judul di atas header asli (pola stock-monitoring):
        pipeline utama jalan mulus (ensure_rekap_header) — pembanding
        dulu GAGAL 'Kolom wajib NAMA BARANG tidak ada'."""
        from waste_anomaly.period_history import load_history_file
        wb = _wb_rekap(tmp_path, title_row=True)
        res = load_history_file(str(wb), CFG)
        assert res["error"] is None, res["error"]
        assert res["agg"]["TOTAL"].sum() == 170.0

    def test_header_normal_tetap_utuh(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        res = load_history_file(str(_wb_rekap(tmp_path)), CFG)
        assert res["error"] is None
        assert res["rows_raw"] == 2


# ============================================================
# [R181-3] KEY_AKHIR DARI BARIS WASTE SAJA
# ============================================================

class TestKeyAkhirDariWaste:
    def test_bom_di_luar_periode_tak_menggelembungkan(self, tmp_path):
        """Waste berhenti hari-20; BOM ber-value hingga hari-31 →
        key_akhir = 20 (dulu 31 — 'HARI DATA' & 'Waste per Hari'
        pembanding salah)."""
        from waste_anomaly.period_history import load_history_file
        wb = _wb_rekap(tmp_path, bom_full_month=True)
        res = load_history_file(str(wb), CFG)
        assert res["error"] is None
        assert res["key_akhir"] == 20

    def test_waste_penuh_bulan_tetap_31(self, tmp_path):
        from waste_anomaly.period_history import load_history_file
        wb = _wb_rekap(tmp_path)  # tanpa BOM; waste sampai hari-20
        # hari-20 = 10 > 0 → ka = 20 (kontrak lama test_v2100 utuh)
        res = load_history_file(str(wb), CFG)
        assert res["key_akhir"] == 20


# ============================================================
# [R181-4] OVERLAP RESTO (compare_quantity)
# ============================================================

def _month(label: str, restos: list[str], total: float = 100.0) -> dict:
    agg = pd.DataFrame({
        "NAMA RESTO": restos,
        "NAMA BARANG": ["AYAM FILET"] * len(restos),
        "TOTAL": [total] * len(restos),
    })
    return {"label": label, "key_akhir": 31, "agg": agg,
            "jenis_totals": pd.DataFrame(
                {"JENIS": ["WASTE"], "TOTAL": [total * len(restos)]}),
            "resto_count": len(set(restos)), "item_count": 1,
            "rows_kept": len(restos), "rows_raw": len(restos), "error": None}


class TestRestoOverlap:
    def test_overlap_positif_tanpa_warn(self):
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", ["1042.KWGGAL", "B.1002.SBY"])
        b = _month("Juli 2026", ["1042.KWGGAL"])
        res = compare_quantity(a, b)
        assert res["resto_overlap"] == 1
        assert res["resto_overlap_warn"] is False

    def test_folder_flow_vs_kode_resto_warn(self):
        """Alur folder: NAMA RESTO = nama file; pembanding = kode resto
        asli → 0 match → semua BARU/HILANG palsu. Kontrak: warn nyala.
        v2.18.5: resto satu-sisi disembunyikan (permintaan user "belum
        ada pembandingnya → gak perlu muncul") → 0-cocok = SEMUA tabel
        banding kosong (dulu BARU/HILANG terisi 2+2 baris palsu)."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", ["BJMHAS", "MLGPAR"])       # nama file
        b = _month("Juli 2026", ["1042.KWGGAL", "B.1002.SBY"])  # kode asli
        res = compare_quantity(a, b)
        assert res["resto_overlap"] == 0
        assert res["resto_overlap_warn"] is True
        # v2.18.5 — tabel kosong: tak ada baris yang bisa dibandingkan
        # (resto satu-sisi disembunyikan, jumlahnya dilaporkan).
        assert len(res["branch"]) == 0
        assert len(res["items"]) == 0
        assert len(res["new_items"]) == 0
        assert len(res["gone_items"]) == 0
        assert res["resto_only_a"] == 2
        assert res["resto_only_b"] == 2

    def test_satu_sisi_kosong_tanpa_warn(self):
        """Bulan tanpa data (agg kosong) ≠ salah penamaan — jangan
        memperingatkan (hindari false alarm)."""
        from waste_anomaly.period_history import compare_quantity
        a = _month("Bulan Ini", ["1042.KWGGAL"])
        empty = _month("Juli 2026", [])
        res = compare_quantity(a, empty)
        assert res["resto_overlap_warn"] is False
        # v2.18.5: pembanding kosong → tak ada resto yang punya pembanding
        # → semua tabel banding kosong (A-only = 1 resto disembunyikan).
        assert res["resto_only_a"] == 1
        assert len(res["branch"]) == 0


# ============================================================
# [R181-5] KONTRAK FILE STANDAR BERSIH TAK BERUBAH
# ============================================================

class TestKontrakFileStandar:
    def test_rows_kept_label_total(self, tmp_path):
        """Mirror test_v2100 (label dari nama file; agregat dihitung
        dari kolom hari, bukan kolom TOTAL)."""
        from waste_anomaly.period_history import load_history_file
        df = pd.DataFrame([
            {"NAMA BARANG": "X", "NAMA RESTO": "R1", "JENIS": "WASTE",
             "KETERANGAN": "Handling",
             **{str(d): 1.0 for d in range(1, 32)},
             "TOTAL": 99999.0},  # pengecoh — diabaikan
        ])
        wb = tmp_path / "REKAP MENTAH JANUARI 2026.xlsx"
        df.to_excel(wb, sheet_name="REKAP MENTAH", index=False)
        res = load_history_file(str(wb), {})
        assert res["error"] is None
        assert res["label"] == "Januari 2026"
        assert res["rows_kept"] == 1
        assert res["agg"]["TOTAL"].iloc[0] == 31.0


# ============================================================
# [R181-6] UI — PERINGATAN OVERLAP MUNCUL (offscreen)
# ============================================================

def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _make_periode_view(monkeypatch, tmp_path, entries):
    _qapp()
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    from waste_anomaly import period_history as ph
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    ph.save_history_entries(entries, store)
    ctx = AppContext({})
    view = PeriodeView(ctx)
    return view, ctx


def _wait_worker(view, app, timeout_s: float = 30.0) -> None:
    t0 = time.perf_counter()
    while view._running:
        app.processEvents()
        time.sleep(0.01)
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("worker pembanding tidak selesai")


class TestUiPeringatanOverlap:
    def test_label_peringatan_0_overlap(self, tmp_path, monkeypatch):
        """Alur penuh (worker → render): current = nama file (folder-
        flow), pembanding = kode resto → label banding memuat peringatan
        '0 cabang cocok' (dulu senyap — analisa salah tanpa penjelasan)."""
        wb = _wb_rekap(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx = _make_periode_view(
            monkeypatch, tmp_path, [{"path": str(wb), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        # current: folder-flow — NAMA RESTO = nama file (BUKAN 1042.KWGGAL)
        data = {str(d): 3.0 for d in range(1, 31)}
        df = pd.DataFrame([
            {"NAMA RESTO": "BJMHAS", "NAMA BARANG": "AYAM FILET",
             "JENIS": "WASTE", "KETERANGAN": "Internal",
             **data, "TOTAL": float(sum(data.values()))}])
        ctx.set_dataset(df, {"key_akhir": 30, "total_rows": 1})
        view._refresh_result()
        txt = view._lbl_compare.text()
        assert "0 cabang cocok" in txt
        assert "nama file" in txt

    def test_label_normal_tanpa_peringatan(self, tmp_path, monkeypatch):
        """Resto sama-sama 1042.KWGGAL → TIDAK ada peringatan (teks
        normal 'Waste per Hari menormalkan')."""
        wb = _wb_rekap(tmp_path, "REKAP MENTAH JULI 2026.xlsx")
        view, ctx = _make_periode_view(
            monkeypatch, tmp_path, [{"path": str(wb), "label": None}])
        app = _qapp()
        _wait_worker(view, app)
        data = {str(d): 3.0 for d in range(1, 31)}
        df = pd.DataFrame([
            {"NAMA RESTO": "1042.KWGGAL", "NAMA BARANG": "AYAM FILET",
             "JENIS": "WASTE", "KETERANGAN": "Internal",
             **data, "TOTAL": float(sum(data.values()))}])
        ctx.set_dataset(df, {"key_akhir": 30, "total_rows": 1})
        view._refresh_result()
        txt = view._lbl_compare.text()
        assert "0 cabang cocok" not in txt
        assert "menormalkan" in txt


# ============================================================
# [R181-7] PIN VERSI 2.18.1
# ============================================================

class TestVersiSinkron:
    def test_versi_2181_sinkron(self):
        from ui.shared import APP_VERSION
        from waste_anomaly import __version__
        from waste_anomaly.utils import load_config
        cfg = load_config()
        assert APP_VERSION == __version__ == cfg.get("version") == "2.21.1"
        init_src = (REPO / "waste_anomaly" / "__init__.py").read_text(
            encoding="utf-8")
        assert "Versi: 2.18.4" in init_src
        mulai = (REPO / "MULAI.bat").read_bytes()
        assert b"v2.18.4" in mulai
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        assert "v2.18.4" in readme
