"""test_v21314.py — regresi v2.13.14 (Gelombang 5: 14 SISA P3 kategori
SULIT/RISKY dari audit UI/UX 94 temuan — daftar sisa di worklog
WASTE-G4R/WASTE-G4; semua fix berbasis bukti empiris offscreen).

[B23]×2   Urutan bulan tak lagi rusak oleh nama file tak-terparse:
          month_sort_key sentinel (9999, 0) = TERAKHIR (dulu (0, 0) =
          PERTAMA — satu file "DATA.xlsx" menggeser semua bulan valid
          ke bawah combo) + pola nama file NUMERIK terparse
          (REKAP_2026_09 / REKAP_202609 / REKAP_09_2026 / tahun di depan
          nama bulan "REKAP 2025 SEPTEMBER").
[B11]     ⛶ Banding Periode kini SALINAN TABEL TAB AKTIF sungguhan:
          halaman Cabang/Item/Baru memakai frame _page_mask → kolom ✓
          follow-up IKUT (checkbox interaktif — centang di jendela penuh
          masuk Follow Up; dulu df mentah `res` → kolom ✓ massal hilang,
          kontradiksi docstring).
[B19]     Rename nama bulan file pembanding via KEYBOARD — Enter/F2 di
          baris terpilih memicu dialog rename yang sama dengan klik-2×
          (dulu hanya mouse double-click — pengguna keyboard tak punya
          jalur). F1 help seksi banding ikut menyebut.
[B22]     Drill dari ⛶ layar penuh berlanjut DI JENDELA PENUH itu —
          dialog sumber membawa rantainya sendiri (2× drill → jumlah
          dialog == 1; dulu tiap klik-2× dari ⛶ membuka dialog kecil
          terpisah menumpuk di atas jendela maximized).
[D24]×2   Shortcut global: Ctrl+1..Ctrl+6 pindah tab sesuai urutan +
          Ctrl+E ekspor (QAction setShortcut — pola act_help F1; dulu
          nol shortcut global: navigasi tab hanya via mouse). F1 help
          menyebut satu baris.
[C14]     ⛶ Scorecard kini pola PERSIS 2 tab lain: tabel index-0 stretch
          + showMaximized + raise_ + activateWindow + restore stretch
          (dulu insert-bawah-tombol tanpa raise — audit C14).
[D26]     _save_config mengecualikan kunci RUNTIME _config_load_error
          saat menulis config.json (dulu ikut ter-persist dari jalur
          fallback config korup; ctx.config tak termutasi).
[D27]     Run sukses TANPA modal "Pipeline Selesai" (status bar + kartu
          Ringkasan Run sudah menyampaikan; test v21313 yang mem-pin
          modal sukses ditulis ulang jujur); jalur GAGAL tetap modal
          critical ramah (friendly_file_error).
[A7]      set_dataset saat view terlihat = SATU render (bukan 2):
          pasangan data_ready→filters_changed dikonsumsi flag
          _skip_filters_once di AnomaliView + HariView; set_filter user
          tetap render normal.
[A16]     Fallback sig show_record (record tanpa __FP) memuat identitas
          baris: posisi + nilai hari 1-31 — 2 record beda tanpa __FP
          kini REBUILD pop-up (dulu 6 kolom kunci sama = sig sama →
          pop-up menampilkan record LAMA).
[A17]     full_box tak lagi YATIM saat n_full==0 — widget kolom-lengkap
          dibangun HANYA bila ada kolomnya (dulu QWidget tanpa parent
          dipegang ref sampai show_record berikutnya; tombol tak dibuat
          tapi box bocor).
[C16]     Exception render tab kini menulis TRACEBACK ke log
          (logging.exception + ctx.log — panel log + sheet Log Run;
          dulu cuma pesan singkat status bar: mustahil didiagnosis).
[C15]     Kolom BULAN LALU / NILAI BULAN LALU menyebut SUMBERNYA
          (Anomali = bulan pilihan combo; Hari = bulan terbaru termuat;
          alias headerData + tooltip dinamis — data tetap kanonik).
[C20]     Lookup nama cabang drill Scorecard di-STRIP di batas UI —
          nama ber-whitespace ekstra tetap match (dulu money_ranking
          RAW vs scorecard stripped → drill uang kosong senyap).

Fixture pola v21313 (worker-sungguhan _view_periode_files / _full_df /
_hari_df / _df_scorecard / _MBStub). NB: output terminal kadang
mem-MANGLE sekuens "[m" — verifikasi konten via compile/codepoint.
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

_FRAG = "Lonjakan vs rata-rata harian | Puncak harian vs BOM | Menumpuk di hari terakhir"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _full_df(n: int = 4, n_days: int = 31) -> pd.DataFrame:
    """Fixture lengkap (pola test_v21313/_v2139): kolom ringkasan + peer +
    pembanding + hari 1..n_days."""
    rows = []
    for i in range(n):
        vals = {str(d): 5.0 for d in range(1, n_days + 1)}
        vals["17"] = 8000.0
        rows.append({
            "NAMA RESTO": f"RESTO {i}", "NAMA BARANG": f"BARANG {i}",
            "JENIS": "WASTE", "KETERANGAN": "Kualitas Internal",
            "SOURCE DATA": "REKAP", "SATUAN": "GR",
            **vals,
            "TOTAL": 12470.0, "MAX": 8000.0, "HARI MAX": 17,
            "ANOMALY SCORE": 12, "ANOMALY STATUS": "Prioritas Tinggi",
            "ANOMALY REASONS": _FRAG,
            "% to BOM": 0.0134, "MAX SHARE": 0.64,
            "PEER COUNT": 9, "TOTAL / PEER MEDIAN": 2.44,
            "BULAN LALU": 9220.0, "PERUBAHAN %": 35.2,
            "RANGKING WASTE": "Top 2 TOTAL",
            "KATEGORI ANOMALI": "Lonjakan Ekstrem",
        })
    return pd.DataFrame(rows)


def _make_view(df: pd.DataFrame | None = None):
    """AnomaliView (+ dataset bila diberikan) — pola v2139/v21313."""
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    ctx = AppContext({})
    view = AnomaliView(ctx)
    if df is not None:
        ctx.set_dataset(df, {"key_akhir": 31})
        view._refresh_table()
    return view, ctx


def _hari_df() -> pd.DataFrame:
    """Dataset hari ber-bukti (pola test_v21313 — annotate_day_evidence)."""
    from waste_anomaly.day_focus import annotate_day_evidence
    rows = []
    for resto in ("A.OUTLET", "B.OUTLET", "C.OUTLET"):
        vals = {str(d): 5.0 if resto != "C.OUTLET" else 4.0
                for d in range(1, 31)}
        if resto == "A.OUTLET":
            vals["17"] = 70.0
        rows.append({
            "NAMA RESTO": resto, "NAMA BARANG": "ITEM UJI",
            "JENIS": "WASTE", "KETERANGAN": "Kualitas",
            "SOURCE DATA": "REKAP", "SATUAN": "GR",
            **vals,
            "TOTAL": float(sum(vals.values())),
            "ANOMALY STATUS": "Potensi Anomali",
            "ANOMALY SCORE": 9,
            "HARI MAX": 17.0 if resto == "A.OUTLET" else 1.0,
            "SCALE SIGNAL": "YES" if resto == "A.OUTLET" else "NO",
            "SINGLE DAY": "NO",
        })
    return annotate_day_evidence(pd.DataFrame(rows), 31, {"thresholds": {}})


def _df_ayam() -> pd.DataFrame:
    """Dataset bulan berjalan (pola v21311/v21313 — bahan banding A)."""
    def _row(status, total):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = 100.0
        return {
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
            "KETERANGAN": "Handling", "NAMA BARANG": "AYAM",
            "NAMA RESTO": "R1", "SATUAN": "PCS", "ANOMALY STATUS": status,
            **data, "TOTAL": float(total),
        }
    return pd.DataFrame([
        _row("Perlu Review", 100.0), _row("Prioritas Tinggi", 100.0)])


def _wb_month(tmp_path: Path, month: str) -> Path:
    """Workbook pembanding 1 bulan (pola v21311/v21313)."""
    data = {str(d): 0.0 for d in range(1, 32)}
    data["5"] = 80.0
    row = {
        "SOURCE DATA": "WASTE BAHAN DAN PACKAGING", "JENIS": "WASTE",
        "KETERANGAN": "Handling", "NAMA BARANG": "AYAM",
        "NAMA RESTO": "R1", "SATUAN": "PCS",
        **data, "TOTAL": float(sum(data.values())),
    }
    out = tmp_path / f"REKAP MENTAH {month} 2026.xlsx"
    pd.DataFrame([row]).to_excel(out, sheet_name="REKAP MENTAH", index=False)
    return out


def _wait_worker(view, app, timeout: float = 30.0) -> None:
    t0 = time.perf_counter()
    while view._running and time.perf_counter() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def _view_periode_files(tmp_path, monkeypatch, months):
    """PeriodeView + N file pembanding termuat (worker SUNGGUHAN) +
    dataset AYAM — pola v21311/v21313."""
    from waste_anomaly import period_history as ph
    from ui.state import AppContext
    from ui.view_periode import PeriodeView
    app = _qapp()
    store = tmp_path / "history_files.json"
    monkeypatch.setattr(ph, "history_store_path", lambda: store)
    entries = []
    for m in months:
        entries.append({"path": str(_wb_month(tmp_path, m)), "label": None})
    ph.save_history_entries(entries, store)
    ctx = AppContext({})
    ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
    view = PeriodeView(ctx)
    view.show()
    _wait_worker(view, app)
    view._refresh_result()
    app.processEvents()
    return view, ctx, app


class _MBStub:
    """Stub QMessageBox (pola repo: modal blocking dihindari offscreen)."""
    calls: list = []

    @staticmethod
    def information(*args, **kw):  # noqa: ARG004
        _MBStub.calls.append(("information", args))

    @staticmethod
    def critical(*args, **kw):  # noqa: ARG004
        _MBStub.calls.append(("critical", args))


# ============================================================
# [B23] Urutan bulan: sentinel TERAKHIR + pola nama file numerik
# ============================================================

class TestB23UrutanBulan:
    def test_unparseable_sort_terakhir(self):
        """B23: label tak-terparse sort TERAKHIR (sentinel (9999, 0)) —
        dulu (0, 0) = PERTAMA: satu file bernama aneh melompat ke atas
        combo & menggeser semua bulan valid ke bawah."""
        from waste_anomaly.period_history import month_sort_key
        assert month_sort_key("XJULI") == (9999, 0)
        assert month_sort_key("") == (9999, 0)
        assert month_sort_key("??") == (9999, 0)
        keys = ["Agustus 2026", "DATA", "Juli 2026", "Desember 2025"]
        assert sorted(keys, key=month_sort_key) == [
            "Desember 2025", "Juli 2026", "Agustus 2026", "DATA"], (
            "bulan valid tetap kronologis; label aneh paling belakang")

    def test_pola_nama_file_numerik_terparse(self):
        """B23: pola nama file umum terparse — REKAP_YYYY_MM,
        _YYYYMM, MM_YYYY, dan 'tahun menDEDAHI nama bulan' (dulu None →
        baris '(klik 2× utk beri nama)' + sort (0,0) menempatkan bulan
        valid bergeser). Validasi: bulan 1-12 + tahun wajar."""
        from waste_anomaly.period_history import (
            detect_month_label, month_sort_key)
        assert detect_month_label(
            "REKAP_2026_09.xlsx") == "September 2026"
        assert detect_month_label("REKAP_202609.xlsx") == "September 2026"
        assert detect_month_label("REKAP_09_2026.xlsx") == "September 2026"
        assert detect_month_label(
            "REKAP 2025 SEPTEMBER.xlsx") == "September 2025"
        # sort key ikut membaca label numerik (label user "2026-09")
        assert month_sort_key("2026-09") == (2026, 9)
        # validasi menolak run digit tak bermakna
        assert detect_month_label("REKAP 123.xlsx") is None
        assert detect_month_label("REKAP_2026_45.xlsx") is None
        assert month_sort_key("REKAP_2026_45") == (9999, 0)


# ============================================================
# [B11] ⛶ Banding = salinan tabel tab aktif (kolom ✓ ikut)
# ============================================================

class TestB11FullscreenKolomCentang:
    def test_fullscreen_banding_punya_kolom_centang(self, tmp_path,
                                                    monkeypatch):
        """B11: jendela ⛶ halaman Cabang (ber-✓) memakai frame tabel tab
        AKTIF — kolom ✓ follow-up IKUT & INTERAKTIF (centang di jendela
        penuh = masuk Follow Up; lepas dari mana pun = jendela penuh ikut
        jujur). Dulu df mentah `res` → kolom ✓ massal hilang."""
        from PySide6.QtCore import Qt
        from waste_anomaly.followup import CHECK_COL
        view, ctx, app = _view_periode_files(tmp_path, monkeypatch,
                                             ["JULI"])
        view._tabs.setCurrentIndex(2)  # halaman 'Cabang Mover'
        app.processEvents()
        view._on_fullscreen()
        app.processEvents()
        m = view._full._table.model()
        mdf = m.dataframe
        assert mdf is not None and CHECK_COL in mdf.columns, (
            "jendela ⛶ halaman cabang harus memuat kolom ✓ (B11)")
        assert "__FPS" in mdf.columns, "frame = _page_mask (ber-sidik jari)"
        # frame sama yang dirender tabel tab (baris identik)
        tab = view._tables["branch"].model().dataframe
        assert len(mdf) == len(tab)
        # checkbox benar-benar interaktif (flags model)
        col = mdf.columns.get_loc(CHECK_COL)
        idx = m.index(0, col)
        assert idx.flags() & Qt.ItemFlag.ItemIsUserCheckable, (
            "kolom ✓ di ⛶ harus bisa dicentang (bukan mati)")
        # centang dari jendela penuh → masuk Follow Up (routing check_cb)
        assert m.setData(idx, Qt.CheckState.Checked,
                         Qt.ItemDataRole.CheckStateRole)
        app.processEvents()
        assert len(ctx.followup_keys) == 1, (
            "✓ di jendela ⛶ harus masuk Follow Up (B11)")
        # tabel TAB ikut tercentang (state bersama)
        assert bool(tab.iloc[0][CHECK_COL])
        # lepas dari luar → jendela ⛶ ikut jujur (refresh in-place)
        ctx.remove_followup_many(list(ctx.followup_keys))
        app.processEvents()
        assert not bool(m.dataframe.iloc[0][CHECK_COL]), (
            "lepas ✓ dari mana pun → jendela ⛶ ikut kosong (B11)")


# ============================================================
# [B19] Rename nama bulan via keyboard (Enter/F2)
# ============================================================

class TestB19RenameKeyboard:
    def test_enter_f2_memicu_rename(self, tmp_path, monkeypatch):
        """B19: Enter/F2 di baris terpilih daftar file = rename (dialog
        QInputDialog sama dengan klik-2×; dulu rename cuma bisa lewat
        mouse double-click). Label tersimpan + ter-render."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        import ui.view_periode as vp
        view, _ctx, app = _view_periode_files(tmp_path, monkeypatch,
                                              ["JULI", "AGUSTUS"])
        calls: list = []

        class _InputDialogStub:
            @staticmethod
            def getText(parent, title, label, text=""):  # noqa: ARG004
                calls.append((title, text))
                return ("Nama Baru 2026", True)

        monkeypatch.setattr(vp, "QInputDialog", _InputDialogStub)
        # F2 di baris 0
        view._tbl_files.setCurrentCell(0, 0)
        app.processEvents()
        QTest.keyClick(view._tbl_files, Qt.Key.Key_F2)
        app.processEvents()
        assert len(calls) == 1, "F2 harus memicu dialog rename (B19)"
        assert view._entries[0]["label"] == "Nama Baru 2026"
        # Enter di baris 1 (pintu kedua)
        view._tbl_files.setCurrentCell(1, 0)
        app.processEvents()
        QTest.keyClick(view._tbl_files, Qt.Key.Key_Return)
        app.processEvents()
        assert len(calls) == 2, "Enter juga memicu rename (B19)"
        assert view._entries[1]["label"] == "Nama Baru 2026"
        assert view._tbl_files.item(0, 0).text() == "Nama Baru 2026"


# ============================================================
# [B22] Drill dari ⛶ berlanjut di jendela itu (dialog reusable)
# ============================================================

class TestB22DrillDariFullscreen:
    def test_dua_drill_dari_fullscreen_satu_dialog(self, tmp_path,
                                                   monkeypatch):
        """B22: 2× drill dari jendela ⛶ → jumlah dialog yang TERLIHAT ==
        1 (rantai berlanjut di jendela penuh itu, tetap maximized; dulu
        tiap klik-2× dari ⛶ membuka dialog kecil terpisah menumpuk di
        atas jendela maximized)."""
        from ui.view_periode import BandTableDialog
        view, _ctx, app = _view_periode_files(tmp_path, monkeypatch,
                                              ["JULI"])
        view._tabs.setCurrentIndex(3)  # halaman 'Item Mover'
        app.processEvents()
        view._on_fullscreen()
        app.processEvents()
        assert view._full.isVisible()
        # drill #1: klik-2× baris di jendela penuh (level 'tab')
        m = view._full._table.model()
        rec = m.record(0)
        assert rec is not None
        view._full._on_double(rec)
        app.processEvents()
        vis = [d for d in view.findChildren(BandTableDialog)
               if d.isVisible()]
        assert len(vis) == 1 and vis[0] is view._full, (
            "drill dari ⛶ harus berlanjut di jendela ⛶ (B22)")
        assert not view._drill.isVisible(), (
            "dialog kecil tak boleh ikut terbuka (B22)")
        # halaman Item Mover → klik-2× langsung level HARI (_open_day)
        assert view._full._level == "day"
        # drill #2: level resto (dari jendela penuh — dispatch eksplisit)
        view._drill_dispatch("resto", {"jenis": None},
                             rec, source=view._full)
        app.processEvents()
        vis = [d for d in view.findChildren(BandTableDialog)
               if d.isVisible()]
        assert len(vis) == 1, "2× drill → tetap 1 dialog (B22)"
        assert view._full._level == "item"
        assert view._full._max_mode, "jendela ⛶ tetap maximized (B22)"
        assert "Item" in view._full._lbl_title.text()


# ============================================================
# [D24] Shortcut global Ctrl+1..6 + Ctrl+E
# ============================================================

class TestD24ShortcutGlobal:
    def test_ctrl_3_pindah_tab_index_2(self):
        """D24: QTest Ctrl+3 → tab index 2 (Hari Mencurigakan — urutan
        _views); dulu nol shortcut global: pindah tab hanya via mouse.
        v2.17.0 rombak: urutan tab diganti (Pipeline 0, Anomali 1, Hari 2,
        ...Follow Up terakhir). v2.18.5: Scorecard dihapus (6 → 5 tab) —
        Hari tetap index 2; Ctrl+5 kini → Follow Up (index 4)."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        win.show()
        app.processEvents()
        assert win._tabs.currentIndex() == 0, "first-run = Pipeline (idx 0)"
        QTest.keyClick(win, Qt.Key.Key_3,
                       Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert win._tabs.currentIndex() == 2, (
            "Ctrl+3 harus pindah ke tab index 2 (D24)")
        QTest.keyClick(win, Qt.Key.Key_1,
                       Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert win._tabs.currentIndex() == 0, "Ctrl+1 → tab Pipeline (idx 0)"
        QTest.keyClick(win, Qt.Key.Key_5,
                       Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert win._tabs.currentIndex() == 4, "Ctrl+5 → tab Follow Up (idx 4)"

    def test_shortcut_terpasang_semua_action(self):
        """D24: 6 action tab (Ctrl+1..Ctrl+6; v2.19.5 +tab Update nilai)
        + action ekspor (Ctrl+E) semuanya ber-shortcut (shortcuts()
        non-kosong & urut benar)."""
        from PySide6.QtGui import QKeySequence
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        assert len(win._tab_actions) == 6, "enam tab = enam shortcut"
        for i, act in enumerate(win._tab_actions):
            sc = act.shortcuts()
            assert len(sc) == 1, f"tab {i + 1}: tepat satu shortcut"
            assert sc[0].matches(
                QKeySequence(f"Ctrl+{i + 1}")) == \
                QKeySequence.SequenceMatch.ExactMatch
        assert win._act_export.shortcuts()[0].toString() == "Ctrl+E"

    def test_tab_action_tak_membocorkan_window(self):
        """D24-fix (regresi kebocoran): koneksi sinyal QAction tab HARUS
        bound method (receiver lemah) — BUKAN lambda yang menangkap self.
        PySide6 memegang callable koneksi KUAT: lambda closure `self` =
        rantai QAction(parent=win)→sinyal→lambda→win yang tak bisa
        dipecahkan gc (siklus lintas C++/Python). Dulu (gel-5 iterasi-1)
        window bertahan gc.collect() → teardown conftest memanggil
        close() → closeEvent melihat _running → QMessageBox.question
        ASLI → modal menunggu klik abadi di offscreen → full-suite HANG
        (diagnosis: py-spy → closeEvent dari _dispose_orphan_widgets)."""
        import gc
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        # jendela "sedang berjalan" — kondisi yang membuat closeEvent
        # bertanya (modal) bila window bocor sampai teardown.
        for _n, v in win._views:
            if getattr(v, "_btn_run", None) is not None:
                v._running = True
                v._worker = object()
        n_alive = sum(1 for w in app.topLevelWidgets()
                      if isinstance(w, MainWindow))
        assert n_alive == 1
        del win
        gc.collect()
        n_leaked = sum(1 for w in app.topLevelWidgets()
                       if isinstance(w, MainWindow))
        assert n_leaked == 0, (
            "MainWindow bocor lewat koneksi sinyal tab-action "
            "(lambda menangkap self?) — window harus mati saat refcount "
            "turun + gc (D24-fix)")


class TestD26ConfigLoadError:
    def test_saved_config_tak_memuat_kunci_runtime(self, monkeypatch,
                                                   tmp_path):
        """D26: _save_config mengecualikan _config_load_error (kunci
        RUNTIME jalur fallback config korup) — file hasil simpan bersih;
        ctx.config TAK termutasi (pesan error tetap hidup di sesi)."""
        import ui.view_pipeline as vpmod
        from ui.state import AppContext
        _qapp()
        (tmp_path / "waste_anomaly").mkdir(exist_ok=True)
        monkeypatch.setattr(vpmod, "APP_DIR", tmp_path)
        ctx = AppContext({"thresholds": {"TH_SPIKE": 3},
                          "_config_load_error": "JSONDecodeError: x"})
        view = vpmod.PipelineView(ctx)
        _MBStub.calls = []
        monkeypatch.setattr(vpmod, "QMessageBox", _MBStub)
        view._save_config()
        target = tmp_path / "waste_anomaly" / "config.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert "_config_load_error" not in data, (
            "kunci runtime tak boleh ter-persist (D26)")
        assert data["thresholds"]["TH_SPIKE"] == 3
        # ctx.config tak termutasi — kunci runtime tetap utk sesi ini
        assert ctx.config.get("_config_load_error") == "JSONDecodeError: x"


# ============================================================
# [D27] Modal sukses dihapus — jalur gagal tetap modal
# ============================================================

class TestD27ModalPipeline:
    def test_run_gagal_tetap_modal_critical(self, monkeypatch):
        """D27: run sukses TANPA modal (dibuktikan test_v21313 D5+D6 yang
        ditulis ulang); jalur GAGAL TETAP modal critical + pesan ramah
        friendly_file_error (error butuh atensi + saran)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        ctx = AppContext({})
        view = vp.PipelineView(ctx)
        _MBStub.calls = []
        monkeypatch.setattr(vp, "QMessageBox", _MBStub)
        view._on_failed("File is not a zip file", "")
        app.processEvents()
        kinds = [c[0] for c in _MBStub.calls]
        assert "critical" in kinds, "run gagal tetap modal (D27)"
        # pesan diterjemahkan friendly_file_error (kontrak D7 gel-4)
        text = " ".join(str(a) for c in _MBStub.calls for a in c[1])
        assert "File bukan workbook Excel" in text
        assert "Teks asli" in text


# ============================================================
# [A7] set_dataset saat view terlihat = SATU render
# ============================================================

class TestA7RenderSekali:
    def test_set_dataset_render_count_satu(self, monkeypatch):
        """A7: set_dataset saat view TERLIHAT → _refresh_table TEPAT
        SEKALI (dulu 2×: data_ready render penuh lalu filters_changed
        render penuh identik — docstring state.py lama menjanjikan
        'partial refresh', tidak jujur). set_filter user tetap render."""
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        app = _qapp()
        for cls in (AnomaliView, HariView):
            ctx = AppContext({})
            view = cls(ctx)
            view.show()
            app.processEvents()
            calls: list = []
            orig = view._refresh_table

            def wrap(*a, _o=orig, _c=calls):
                _c.append(1)
                return _o(*a)

            monkeypatch.setattr(view, "_refresh_table", wrap)
            ctx.set_dataset(_full_df(2), {"key_akhir": 31})
            app.processEvents()
            assert len(calls) == 1, (
                f"{cls.__name__}: set_dataset = 1 render (A7; dulu 2)")
            # filter user SETELAHNYA tetap render normal (flag habis)
            ctx.set_filter("cabang", "RESTO 0")
            app.processEvents()
            assert len(calls) == 2, (
                f"{cls.__name__}: set_filter user tetap render (A7)")


# ============================================================
# [A16] Fallback sig show_record memuat identitas baris
# ============================================================

class TestA16SigFallback:
    def test_dua_record_beda_tanpa_fp_membangun_ulang(self):
        """A16: 2 record BEDA tanpa __FP yang sama di kolom kunci (beda
        hari) → show_record ke-2 MEMBANGUN ULANG pop-up (dulu sig 6
        kolom kunci identik → guard salah anggap sama → pop-up record
        LAMA)."""
        from ui.state import AppContext
        from ui.view_anomali import DetailDialog
        app = _qapp()
        ctx = AppContext({})
        dlg = DetailDialog(ctx)
        base = {
            "NAMA RESTO": "R1", "NAMA BARANG": "B1", "JENIS": "WASTE",
            "KETERANGAN": "Handling", "SOURCE DATA": "REKAP",
            "ANOMALY SCORE": 10, "ANOMALY STATUS": "Prioritas Tinggi",
            "ANOMALY REASONS": _FRAG, "TOTAL": 100.0, "SATUAN": "GR",
        }
        r1 = dict(base, **{"5": 100.0, "6": 0.0})
        r2 = dict(base, **{"5": 0.0, "6": 100.0})
        df = pd.DataFrame([r1, r2])
        rec1, rec2 = df.iloc[0], df.iloc[1]
        assert "__FP" not in rec1.index
        # sig berbeda → guard tak menyamakan
        assert dlg._record_sig(rec1) != dlg._record_sig(rec2), (
            "record beda (hari beda) harus sig beda (A16)")
        calls: list = []
        orig = dlg._panel.show_record

        def wrap(rec, _o=orig, _c=calls):
            _c.append(1)
            return _o(rec)

        dlg._panel.show_record = wrap
        dlg.show_record(rec1)
        app.processEvents()
        assert len(calls) == 1 and dlg.isVisible()
        dlg.show_record(rec2)
        app.processEvents()
        assert len(calls) == 2, (
            "record beda tanpa __FP harus rebuild pop-up (A16; dulu 1)")


# ============================================================
# [A17] full_box tak yatim saat n_full == 0
# ============================================================

class TestA17FullBoxKosong:
    def test_tanpa_kolom_tambahan_tak_ada_box_dan_tombol(self):
        """A17: record tanpa kolom tambahan (hanya identitas + hari) →
        TIDAK ada full_box yatim (ref None), TIDAK ada tombol pembuka,
        _n_full == 0 (dulu QWidget dibuat tanpa parent lalu dibuang)."""
        from ui.state import AppContext
        from ui.view_anomali import DetailPanel
        app = _qapp()
        ctx = AppContext({})
        panel = DetailPanel(ctx)
        rec = pd.Series({
            "NAMA RESTO": "R1", "NAMA BARANG": "B1",
            "ANOMALY SCORE": 10, "ANOMALY STATUS": "Perlu Review",
            "ANOMALY REASONS": _FRAG, "5": 100.0,
        })
        # hanya kolom SKIP + hari (hari bukan DETAIL_COLS) → n_full == 0
        panel.show_record(rec)
        app.processEvents()
        assert panel._n_full == 0
        assert panel._full_box is None, (
            "tanpa kolom tambahan → tak ada box yatim (A17)")
        assert panel._more_btn is None, "tak ada tombol pembuka (A17)"
        # kontrol positif: record lengkap → tombol dibuat dgn '(N)'
        panel.show_record(_full_df(1).iloc[0])
        app.processEvents()
        assert panel._more_btn is not None and panel._n_full > 0
        assert f"({panel._n_full})" in panel._more_btn.text()


# ============================================================
# [C16] Exception render tab → traceback ke log
# ============================================================

class TestC16ExceptionRenderKeLog:
    def test_render_raise_tercatat_di_log(self, monkeypatch, caplog):
        """C16: on_shown raise saat ganti tab → traceback UTUH ke log
        file (logging.exception logger waste_anomaly.ui) + panel log
        pipeline (ctx.log — ikut diekspor ke sheet Log Run); status bar
        tetap jujur (pesan singkat). Dulu hanya status bar: mustahil
        didiagnosis dari log."""
        from ui.app import MainWindow
        app = _qapp()
        win = MainWindow()
        win.show()
        app.processEvents()

        def boom():
            raise ValueError("ledakan-render-uji")

        hari_view = win._views[2][1]
        monkeypatch.setattr(hari_view, "on_shown", boom)
        with caplog.at_level(logging.ERROR, logger="waste_anomaly.ui"):
            win._tabs.setCurrentIndex(2)
            app.processEvents()
        recs = [r for r in caplog.records
                if "Render tab" in r.getMessage()]
        assert recs, "logging.exception harus merekam (C16)"
        err = recs[0]
        assert err.exc_info is not None, (
            "logging.exception membawa exc_info (traceback; C16)")
        tb_txt = "".join(traceback.format_exception(*err.exc_info))
        assert "ValueError" in tb_txt and "ledakan-render-uji" in tb_txt, (
            "traceback exception ikut terekam (C16)")
        joined = "\n".join(win.ctx.log_lines)
        assert "Render tab gagal" in joined, "ctx.log merekam (C16)"
        assert "ledakan-render-uji" in joined, (
            "pesan exception utuh di panel log (C16)")
        assert "Traceback" in joined, "traceback utuh di panel log (C16)"


# ============================================================
# [C15] Kolom BULAN LALU menyebut sumbernya (bulan aktif)
# ============================================================

class TestC15LabelBulanLalu:
    def test_header_memuat_nama_bulan_aktif(self):
        """C15: judul kolom + tooltip BULAN LALU (Anomali — sumber combo
        Banding Periode) dan NILAI BULAN LALU (Hari — sumber bulan
        TERBARU termuat) memuat NAMA BULAN — dulu label polos di kedua
        tab padahal 'bulan lalu' beda sumber (tak terbandingkan).
        v2.19.0 — tampilan GRUP: kolom 'BULAN LALU' diganti 'TOTAL
        BULAN LALU & % Selisih' (nilai gabungan); nama bulan aktif
        kini termuat di TOOLTIP kolom baru (bukan judul kolom)."""
        from PySide6.QtCore import Qt
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.grouping import LASTMONTH_COMBINED_COL
        app = _qapp()
        ctx = AppContext({})
        view = AnomaliView(ctx)
        ctx.set_dataset(_full_df(2), {"key_akhir": 31})
        ctx.set_banding_baseline({"label": "Juli 2026"})
        view._refresh_table()
        app.processEvents()
        m = view._table.model()
        mdf = m.dataframe
        # v2.19.0: kolom gabungan 'TOTAL BULAN LALU & % Selisih' (bukan
        # 'BULAN LALU' lagi — tetap di df tapi tersembunyi, bukan kolom
        # tampilan sampel user).
        assert LASTMONTH_COMBINED_COL in mdf.columns
        col = mdf.columns.get_loc(LASTMONTH_COMBINED_COL)
        # TOOLTIP memuat nama bulan aktif (C15 — sumber combo Banding).
        tip = m.headerData(col, Qt.Orientation.Horizontal,
                           Qt.ItemDataRole.ToolTipRole)
        assert "Juli 2026" in tip and "Sumber saat ini" in tip, (
            f"tooltip kolom harus menyebut bulan aktif (C15): {tip!r}")
        # baseline hilang → tooltip kembali polos (tanpa 'Sumber saat ini')
        ctx.set_banding_baseline(None)
        view._refresh_table()
        app.processEvents()
        tip2 = view._table.model().headerData(
            col, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert "Sumber saat ini" not in tip2, (
            "tanpa baseline → tooltip polos (C15)")

    def test_hari_nilai_bulan_lalu_memuat_bulan_terbaru(self):
        """C15 (tab Hari): sumber NILAI BULAN LALU = bulan pembanding
        TERBARU yang termuat — judul kolom kini menyebutnya (beda sumber
        dgn tab Anomali; dulu nama sama tanpa konteks)."""
        from PySide6.QtCore import Qt
        from ui.state import AppContext
        from ui.view_hari import HariView
        app = _qapp()
        ctx = AppContext({})
        view = HariView(ctx)
        ctx.set_dataset(_hari_df(), {"key_akhir": 31})
        months = [
            {"label": "Juni 2026", "agg": pd.DataFrame(
                {"NAMA RESTO": ["A.OUTLET"], "NAMA BARANG": ["ITEM UJI"],
                 "TOTAL": [10.0]})},
            {"label": "Juli 2026", "agg": pd.DataFrame(
                {"NAMA RESTO": ["A.OUTLET"], "NAMA BARANG": ["ITEM UJI"],
                 "TOTAL": [12.0]})},
        ]
        ctx.set_history(months, None)
        view._refresh_table()
        app.processEvents()
        m = view._table.model()
        mdf = m.dataframe
        assert "NILAI BULAN LALU" in mdf.columns
        col = mdf.columns.get_loc("NILAI BULAN LALU")
        hdr = m.headerData(col, Qt.Orientation.Horizontal,
                           Qt.ItemDataRole.DisplayRole)
        assert "Juli 2026" in hdr, (
            f"tab Hari: bulan TERBARU termuat (bukan Juni) — {hdr!r}")


# ============================================================
