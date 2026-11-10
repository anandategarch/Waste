"""test_v21313.py — regresi v2.13.13 (Gelombang 4 deep audit — PENUTUP:
PERF, FOKUS & POLISH). 24 test pengunci 14 klaster fix + 5 sweep P3:

[A5+A5b+C10] Mask/bukti/hist cache kini (weakref, hasil) dgn VALIDASI
          IDENTITAS ``entry[0]() is obj`` — dulu kunci id() tanpa
          strong-ref/validasi: id bisa dipakai ulang objek lain
          pasca-GC → tabrakan id mengembalikan mask baris STATE LAMA
          (audit A5/A5b; komentar "strong ref" palsu dihapus — C10).
[B8]×2    Label bulan kembar: _mlabel suffix " (2)" (label TAMPILAN —
          kanonik tak tersentuh) + combo 2 entri terbedakan + TIPICAL
          DEDUPE by label (2 file bulan sama = 1 bulan median — dulu
          double-count; audit B8).
[D7]×2    friendly_file_error: 5 pola EN mentah → Indonesia + Saran +
          teks asli dilampirkan (mapping di BATAS UI — pola _log_id
          gel-3); pola tak dikenal/kosong → APA ADANYA (jujur).
[A3]      Pop-up navigasi baris TAK mencuri fokus: WA_ShowWithout
          Activating + raise_ HANYA pop-up baru + activateWindow
          dihapus dari jalur navigasi (dulu 1× panah = navigasi tabel
          mati; audit A3).
[A4]      SELURUH sel kolom ✓ = area centang: klik tengah/kanan sel
          (dulu zona mati) kini toggle — TEPAT SATU sinyal (anti-dobel
          via state pra-super == state pasca-super; audit A4).
[A6]×2    UNION nilai state funnel ke menu: nilai terpilih yang
          disembunyikan filter lain ditawarkan "tersembunyi — lepas
          filter lain" (dulu dijatuhkan senyap = filter bolong) +
          _counts_has NaN-aware (None ≡ NaN, tak dobel "(kosong)").
[D5+D6]×2 Progres pipeline ke STATUS BAR JENDELA UTAMA saat run +
          pesan status TERAKHIR pasca-run = HASIL RUN ditulis SETELAH
          render (dulu ditimpa "✓ Menyaring… selesai (31 ms)" — user
          membaca pekerjaan filter sebagai hasil akhir); first-run
          TANPA dataset tak dibungkus busy (tanpa klaim (0 ms)).
[D22]     Gate cancel ANTAR-FILE fase LOAD (DATA_WASTE/BOM/DATABASE_
          SATUAN) — dulu tombol ⏹ tak berefek sampai Stage 1.
[B10]     SELURUH _refresh_result dibungkus busy_feedback (dulu hanya
          compare_quantity — render pertama 833 ms beku senyap).
[C8]×2    Memo drill Scorecard LRU-8 keyed (resto, data_version,
          history_version): klik-2 ×2 = hitung SEKALI + evict ke-9.
[D10]     PipelineWorker finished → deleteLater (dulu menumpuk per run).
[D29]     3 tombol (Mulai/Simpan/Pratinjau) dinonaktifkan selama compute
          pratinjau try/finally — exception pun memulihkan (dulu klik
          ganda = nested compute + freeze).
[D28]     Dialog keluar saat worker berjalan: tombol default = NO
          (Enter salah = aman batal — konvensi repo).
[C13]     narrow_hide: kolom PEMBANDING (ALASAN HARI, NILAI BULAN LALU)
          disembunyikan PALING AKHIR (dulu duluan — 1366px kehilangan
          bukti pembanding justru saat pembanding aktif).
[B14]     Baris log stage membawa persen kumulatif "(N%)" (dulu
          callback membuang pct dari log run).
[SWEEP]   C7 Enter = drill Scorecard (dulu hanya mouse) · B16 kolom File
          tooltip PATH penuh · B18 funnel halaman reset saat PEMBANDING
          berganti (dulu hanya dataset baru) · D25 QSS :focus tombol
          (navigasi keyboard kini terlihat).

Fixture pola v2139 (DetailPanel + _full_df) + v2135 (hari ber-bukti) +
v21312 (scorecard sintetis) + v21311 (PeriodeView worker-sungguhan).
NB: output terminal kadang mem-MANGLE sekuens "[m" (ANSI reset) —
verifikasi konten via compile/codepoint, bukan display.
Re-eksekusi WASTE-G4R: commit asli 80e1469 hilang pra-push bersama
environment reset — entry worklog WASTE-G4 = spesifikasi replikasi.
"""
from __future__ import annotations

import gc
import os
import re
import weakref
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"
FIXTURE = REPO / "DATA_WASTE.xlsx"
# v2.18.0: DATA_WASTE.xlsx dihapus dari repo (51d042f) — test ENGINE di
# file ini (cancel gate antar-file D22, persen kumulatif log B14, stub
# worker D10) TIDAK butuh data asli (hanya path yang ADA / workbook valid);
# fallback sample sintetis supaya kontrak TETAP teruji di CI (bukan skip
# hollow — pola anti audit-4 "golden test skip senyap").
WORKBOOK = FIXTURE if FIXTURE.exists() else REPO / "sample_workbook.xlsx"

_FRAG = "Lonjakan vs rata-rata harian | Puncak harian vs BOM | Menumpuk di hari terakhir"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _full_df(n: int = 4, n_days: int = 31) -> pd.DataFrame:
    """Fixture lengkap (pola test_v2139): kolom ringkasan + peer +
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
    """AnomaliView (+ dataset bila diberikan) — pola test_v2139."""
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
    """Dataset hari ber-bukti (pola test_v2135 _hari_df — kolom BUKTI
    HASIL Stage 15 hasil annotate_day_evidence)."""
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


def _make_hari():
    _qapp()
    from ui.state import AppContext
    from ui.view_hari import HariView
    ctx = AppContext({})
    view = HariView(ctx)
    ctx.set_dataset(_hari_df(), {"key_akhir": 31})
    view._refresh_table()
    return view, ctx


def _df_ayam() -> pd.DataFrame:
    """Dataset bulan berjalan (pola test_v21311 — bahan banding A)."""
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
    """Workbook pembanding 1 bulan (pola test_v21311 _view_periode_files)."""
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


def _view_periode_files(tmp_path, monkeypatch, months):
    """PeriodeView + N file pembanding termuat (worker SUNGGUHAN) +
    dataset AYAM — pola test_v21311."""
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


def _wait_worker(view, app, timeout: float = 30.0) -> None:
    import time
    t0 = time.perf_counter()
    while view._running and time.perf_counter() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def _df_scorecard(n_resto: int = 4) -> pd.DataFrame:
    """Dataset sintetis Scorecard (pola test_v21312 — item SAMA di ≥ 3
    resto supaya money_ranking (peer ≥ 3) terisi)."""
    rows = []
    for i in range(n_resto):
        data = {str(d): 0.0 for d in range(1, 32)}
        data["5"] = 10.0
        rows.append({
            "SOURCE DATA": "WASTE BAHAN DAN PACKAGING",
            "JENIS": "WASTE", "KETERANGAN": "Handling",
            "NAMA BARANG": "MIE", "NAMA RESTO": f"R{i}",
            "SATUAN": "GR", "ANOMALY STATUS": "Perlu Review",
            "PROFIL": "Tiap Hari",
            **data, "TOTAL": float(100 + 10 * i),
            "KELEBIHAN": 5.0, "PEER MEDIAN (AKTIF)": 50.0,
            "TOTAL BOM": 10_000.0,
        })
    return pd.DataFrame(rows)


def _view_scorecard(df: pd.DataFrame):
    from ui.state import AppContext
    from ui.view_scorecard import ScorecardView
    app = _qapp()
    ctx = AppContext({})
    ctx.set_dataset(df, {"key_akhir": 31})
    view = ScorecardView(ctx)
    view.show()
    app.processEvents()
    view._refresh()
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
# [A5+C10] Mask cache — weakref + validasi identitas (anti id-reuse)
# ============================================================

class TestA5MaskCache:
    def test_mask_cache_validasi_identitas_weakref(self):
        """A5+C10: entri _mask_cache kini (weakref, hasil) dgn validasi
        ``entry[0]() is disp`` — entri basi (weakref ke objek LAIN /
        referent sudah mati) DITOLAK dan dihitung ulang; dulu kunci id()
        tanpa validasi → tabrakan id pasca-GC mengembalikan mask STATE
        LAMA (data salah, jarang tapi nyata)."""
        view, _ctx = _make_view()
        view._hfilters = {"KETERANGAN": ["Kualitas Internal"]}
        disp = _full_df(4)
        out1 = view._mask_local(disp)
        assert len(out1) == 4
        sig = tuple(sorted((c, tuple(v))
                           for c, v in view._hfilters.items()))
        key = (id(disp), sig)
        assert key in view._mask_cache, "entri memo harus terpasang"
        entry = view._mask_cache[key]
        assert isinstance(entry[0], weakref.ref), (
            "entri harus (weakref, hasil) — bukan hasil mentah (A5)")
        assert entry[0]() is disp and entry[1] is out1

        # (1) POISON: weakref hidup tapi menunjuk objek LAIN + hasil basi
        other = pd.DataFrame({"X": [1]})
        stale = disp.iloc[:0].copy()
        view._mask_cache[key] = (weakref.ref(other), stale)
        out2 = view._mask_local(disp)
        assert out2 is not stale, (
            "tabrakan id/id-objek-lain harus DITOLAK (validasi identitas)")
        assert len(out2) == 4, "hasil hitung ulang harus benar"

        # (2) POISON: referent mati pasca-GC (id bisa dipakai ulang)
        tmp = pd.DataFrame({"A": [1]})
        wr_dead = weakref.ref(tmp)
        del tmp
        gc.collect()
        assert wr_dead() is None
        view._mask_cache[key] = (wr_dead, stale)
        out3 = view._mask_local(disp)
        assert out3 is not stale and len(out3) == 4
        # entri segar terpasang kembali dgn weakref ke disp
        assert view._mask_cache[key][0]() is disp


# ============================================================
# [A5b] HariView bukti/hist cache — weakref + identitas
# ============================================================

class TestA5bBuktiHistCache:
    def test_bukti_dan_hist_cache_weakref_identitas(self):
        """A5b: _bukti_cache/_hist_cache view_hari kini weakref + validasi
        identitas (komentar lama 'strong ref ke df dasar' TIDAK jujur —
        cache hanya memegang df HASIL → id bisa dipakai ulang pasca-GC →
        masker basi). Entri dgn weakref ke objek lain → dibangun ulang."""
        view, ctx = _make_hari()
        app = _qapp()
        base = ctx.anomali_df()
        cache = view._bukti_cache
        assert cache is not None, "render ber-bukti harus mengisi memo"
        assert isinstance(cache[0], weakref.ref)
        assert cache[0]() is base
        # POISON bukti: weakref ke objek lain + hasil basi
        other = pd.DataFrame({"A": [1]})
        view._bukti_cache = (weakref.ref(other), cache[1], cache[2])
        view._refresh_table()
        app.processEvents()
        rebuilt = view._bukti_cache
        assert rebuilt[0]() is ctx.anomali_df(), (
            "memo bukti basi harus dibangun ulang (identitas ditolak)")
        # HIST cache: jalur _with_history — entri basi → hitung ulang
        df_show = rebuilt[2]
        out1 = view._with_history(df_show)
        hc = view._hist_cache
        assert hc is not None and isinstance(hc[0], weakref.ref)
        view._hist_cache = (weakref.ref(other), hc[1], hc[2], hc[3])
        out2 = view._with_history(df_show)
        assert view._hist_cache[0]() is df_show, (
            "memo hist basi harus dibangun ulang (identitas ditolak)")
        assert list(out1.columns) == list(out2.columns)


# ============================================================
# [B8] Bulan kembar — label tampilan unik + Tipikal dedupe
# ============================================================

class TestB8BulanKembar:
    def test_mlabel_suffix_dan_label_kanonik_utuh(self):
        """B8: _mlabel memberi suffix ' (2)', ' (3)' utk bulan kembar —
        kunci 'disp' TAMPILAN saja; label KANONIK tak tersentuh (yang
        dipersist ke history_files.json tetap tanpa suffix; identitas
        file = path). Label kosong → '?' jujur."""
        from ui.view_periode import _mlabel
        used: set = set()
        assert _mlabel({"label": "AGUSTUS 2026"}, used) == "AGUSTUS 2026"
        assert _mlabel({"label": "AGUSTUS 2026"}, used) == \
            "AGUSTUS 2026 (2)"
        assert _mlabel({"label": "AGUSTUS 2026"}, used) == \
            "AGUSTUS 2026 (3)"
        # bulan lain tak terganggu suffix
        used2: set = set()
        assert _mlabel({"label": "JULI 2026"}, used2) == "JULI 2026"
        # label kosong/None → '?' (jujur, bukan crash)
        assert _mlabel({"label": ""}, set()) == "?"
        assert _mlabel({}, set()) == "?"
        # label kanonik TIDAK termutasi (dict yang sama utuh)
        m = {"label": "JULI 2026", "path": "/x.xlsx"}
        _mlabel(m, set())
        assert m == {"label": "JULI 2026", "path": "/x.xlsx"}

    def test_combo_dua_entri_dan_tipikal_dedupe(self, monkeypatch):
        """B8 (wiring): 2 file label bulan SAMA → combo 2 baris TERBEDA
        ('AGUSTUS 2026' + 'AGUSTUS 2026 (2)') + TIPICAL dihitung dari
        bulan UNIK (2 file bulan sama = 1 bulan — dulu double-count
        median; < 2 bulan unik → tipikal TIDAK dihitung)."""
        import ui.view_periode as vp
        from ui.state import AppContext
        app = _qapp()
        view = vp.PeriodeView(AppContext({}))
        p = ["/h/a1.xlsx", "/h/a2.xlsx", "/h/j.xlsx"]
        view._entries = [
            {"path": p[0], "label": "AGUSTUS 2026"},
            {"path": p[1], "label": "AGUSTUS 2026"},
            {"path": p[2], "label": "JULI 2026"},
        ]
        view._loaded = {
            p[0]: {"label": "AGUSTUS 2026", "item_count": 10},
            p[1]: {"label": "AGUSTUS 2026", "item_count": 20},
            p[2]: {"label": "JULI 2026", "item_count": 30},
        }
        months = view._combo_months()
        # urut kronologis lama→baru: JULI dulu, lalu 2 AGUSTUS ber-suffix
        assert [m["disp"] for m in months] == \
            ["JULI 2026", "AGUSTUS 2026", "AGUSTUS 2026 (2)"]
        # label kanonik tetap TANPA suffix (identitas data tak berubah)
        assert all("(2)" not in str(m.get("label")) for m in months)
        # combo menampilkan label unik — bukan 2 baris identik
        view._rebuild_combo(months)
        texts = [view._cb_b.itemText(i)
                 for i in range(view._cb_b.count())]
        assert texts.count("AGUSTUS 2026") == 1
        assert "AGUSTUS 2026 (2)" in texts
        # kolom pembanding (judul kolom) ikut label tampilan unik
        assert view._col_header_b(months[2]) == "AGUSTUS 2026 (2)"
        # TIPICAL dedupe: typical_months menerima bulan UNIK by label
        calls: list = []

        def spy_typical(ms):
            calls.append([str(m.get("label")) for m in ms])
            return None
        monkeypatch.setattr(vp, "typical_months", spy_typical)
        view._finalize()
        app.processEvents()
        assert calls == [["JULI 2026", "AGUSTUS 2026"]], (
            "tipikal harus dihitung dari bulan UNIK (2 AGUSTUS = 1 bulan)")
        # kasus kembar murni (2 file, 1 label unik) → tipikal tak dihitung
        view._entries = view._entries[:2]
        view._loaded = {p[0]: view._loaded[p[0]], p[1]: view._loaded[p[1]]}
        calls.clear()
        view._finalize()
        app.processEvents()
        assert calls == [], (
            "1 bulan unik = tak cukup utk tipikal (dulu double-count)")


# ============================================================
# [D7] friendly_file_error — pesan file korup ramah di batas UI
# ============================================================

class TestD7FriendlyFileError:
    def test_lima_pola_diterjemahkan(self):
        """D7: 5 pola EN mentah (openpyxl/pandas/Python) → Indonesia +
        SARAN + teks asli dilampirkan di ekor (bisa dicocokkan dgn log
        yang menulis versi mentah — kontrak: worker TIDAK diubah)."""
        from ui.shared import _FILE_ERR_PATTERNS, friendly_file_error
        assert len(_FILE_ERR_PATTERNS) == 5, (
            "kontrak 5 pola (zip / no-such-file / permission / format / "
            "xls-lama)")
        cases = [
            ("File is not a zip file", "bukan workbook Excel"),
            ("[Errno 2] No such file or directory: 'rekap.xlsx'",
             "tidak ditemukan"),
            ("[Errno 13] Permission denied: 'rekap.xlsx'",
             "tidak bisa dibaca"),
            ("Excel file format cannot be determined; you must specify "
             "an engine manually", "tidak dikenali"),
            ("Excel 5.0 sheet does not support the old .xls flavor",
             "tidak didukung"),
        ]
        for raw, frag in cases:
            out = friendly_file_error(raw)
            assert frag in out, (raw, out)
            assert "Saran:" in out, (raw, out)
            assert raw in out, "teks asli harus dilampirkan (jujur)"
        # suggestion actionable utk pola paling umum (zip rusak)
        out = friendly_file_error("File is not a zip file")
        assert "simpan ulang" in out.lower()

    def test_pola_tak_dikenal_dan_kosong_apa_adanya(self):
        """D7 (jujur): pola tak dikenal → teks asli APA ADANYA (bukan
        tebakan); input kosong/None → string kosong (bukan crash)."""
        from ui.shared import friendly_file_error
        assert friendly_file_error("Kafka cluster is down") == \
            "Kafka cluster is down"
        assert friendly_file_error("") == ""
        assert friendly_file_error(None) == ""
        # case-insensitive fragment match (pesan EN kapital acak)
        out = friendly_file_error("FILE IS NOT A ZIP FILE")
        assert "bukan workbook Excel" in out


# ============================================================
# [A3] Pop-up detail tidak mencuri fokus tabel
# ============================================================

class TestA3FokusPopup:
    def test_popup_navigasi_tidak_mencuri_fokus(self, monkeypatch):
        """A3: DetailDialog memasang WA_ShowWithoutActivating; show_record
        jalur navigasi (pop-up SUDAH tampak) TIDAK memanggil raise_ lagi
        dan TIDAK PERNAH activateWindow (dulu: tiap ganti baris fokus
        lompat ke pop-up → 1× panah = navigasi tabel mati). Pop-up BARU
        tetap raise_ (terlihat) TANPA mengambil fokus."""
        from PySide6.QtCore import Qt
        from ui.state import AppContext
        from ui.view_anomali import DetailDialog
        app = _qapp()
        dlg = DetailDialog(AppContext({}), None)
        assert dlg.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating), (
            "WA_ShowWithoutActivating harus terpasang (audit A3)")
        rec_calls: list = []
        monkeypatch.setattr(DetailDialog, "raise_",
                            lambda self: rec_calls.append("raise"))
        monkeypatch.setattr(DetailDialog, "activateWindow",
                            lambda self: rec_calls.append("activate"))
        df = _full_df(2)
        dlg.show_record(df.iloc[0])   # pop-up BARU
        app.processEvents()
        assert dlg.isVisible()
        assert rec_calls == ["raise"], (
            "pop-up baru raise_ SEKALI — tanpa activateWindow")
        dlg.show_record(df.iloc[1])   # navigasi baris (pop-up tampak)
        app.processEvents()
        assert rec_calls == ["raise"], (
            "navigasi baris tak boleh raise_ ulang (pop-up sudah terlihat)")
        assert "activate" not in rec_calls, (
            "activateWindow tak boleh dipanggil jalur navigasi (A3)")
        # konten berganti jujur (bukan early-return idempoten)
        assert "RESTO 1" in dlg._panel._title.text()
        # klik baris SAMA saat tampak → idempoten (tak rebuild — kontrak
        # v2.13.5 tetap utuh di bawah fix A3)
        before = rec_calls[:]
        dlg.show_record(df.iloc[1])
        assert rec_calls == before


# ============================================================
# [A4] Seluruh sel kolom ✓ = area centang
# ============================================================

class TestA4ZonaCentang:
    def test_seluruh_sel_centang_toggle_tepat_sekali(self):
        """A4: klik TENGAH dan KANAN sel ✓ (dulu zona mati — delegate Qt
        hanya toggle indikator x 4-16 dari sel 36px) kini men-toggle;
        TEPAT SATU sinyal check_toggled per klik (anti-dobel: state
        pra-super == state pasca-super → toggle manual; beda → delegate
        sudah men-toggle, jangan dobel). Klik indikator (x 10) juga
        tepat satu — semua jalur satu toggle."""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from waste_anomaly.followup import CHECK_COL
        view, ctx = _make_view(_full_df(3))
        app = _qapp()
        view.resize(1200, 700)
        view.show()
        app.processEvents()
        view._popup.hide()
        app.processEvents()
        m = view._table.model()
        assert str(m.dataframe.columns[0]) == CHECK_COL
        view._table.setColumnWidth(0, 44)  # zona indikator 4-16 pasti kiri
        sig: list = []
        m.check_toggled.connect(lambda r, c: sig.append((r, c)))

        def _click(row: int, x_off: int) -> None:
            idx = m.index(row, 0)
            rect = view._table.visualRect(idx)
            pt = QPointF(rect.left() + x_off, rect.center().y())
            g = QPointF(view._table.mapToGlobal(pt.toPoint()))
            for typ, btns in [(QEvent.Type.MouseButtonPress,
                               Qt.MouseButton.LeftButton),
                              (QEvent.Type.MouseButtonRelease,
                               Qt.MouseButton.NoButton)]:
                app.sendEvent(view._table.viewport(), QMouseEvent(
                    typ, pt, g, Qt.MouseButton.LeftButton, btns,
                    Qt.KeyboardModifier.NoModifier))
            app.processEvents()

        for row, x_off, label in [(0, 22, "tengah"), (1, 38, "kanan"),
                                  (2, 10, "indikator")]:
            before = m.data(m.index(row, 0), Qt.ItemDataRole.CheckStateRole)
            _click(row, x_off)
            after = m.data(m.index(row, 0), Qt.ItemDataRole.CheckStateRole)
            assert after != before, (
                f"klik {label} sel ✓ harus men-toggle (zona mati — A4)")
            fp = str(m.record(row)["__FP"])
            assert (fp in ctx.followup_set()) == (
                after == Qt.CheckState.Checked)
        # tepat 3 toggle utk 3 klik (anti-dobel — jalur mana pun)
        assert len(sig) == 3, sig
        # pop-up detail ditekan selama klik sel ✓ (kontrak v2.13.5 utuh)
        assert not view._popup.isVisible()


# ============================================================
# [A6] Union nilai state funnel + _counts_has NaN-aware
# ============================================================

class TestA6UnionFunnel:
    def test_counts_has_nan_aware(self):
        """A6: _counts_has — keanggotaan NaN-aware: None ≡ NaN kunci
        counts (dan sebaliknya); dua objek NaN BERBEDA tetap menyatu
        (hash NaN id-based — ``v in counts`` polos bisa meleset);
        nilai biasa / tak ada → False jujur."""
        from ui.widgets import _counts_has
        nan = float("nan")
        counts = {nan: 3, 1.0: 5}
        assert _counts_has(counts, None)
        assert _counts_has(counts, nan)
        assert _counts_has(counts, float("nan"))
        assert _counts_has(counts, 1.0)
        assert not _counts_has(counts, 2.0)
        assert not _counts_has(counts, "nan")
        counts_none = {None: 2}
        assert _counts_has(counts_none, nan)
        assert _counts_has(counts_none, None)
        assert not _counts_has({1.0: 1}, None)
        assert not _counts_has({}, None)

    def test_union_nilai_state_tersembunyi(self):
        """A6 (wiring): nilai milik STATE funnel yang tak tampak di df
        (disembunyikan filter lain) DITAWARKAN dgn penanda jujur
        '(tersembunyi — lepas filter lain)' — dulu dijatuhkan senyap →
        apply membuat filter 'bolong'. None di state menyatu dgn kunci
        NaN counts (tak dobel entri '(kosong)')."""
        import numpy as np
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        df = pd.DataFrame({"KETERANGAN": ["a", "b", "a"]})
        t.set_dataframe(df)
        t.setup_header_filters(
            None, lambda c, k, vals: None,
            lambda col: ["zzz-tersembunyi"],
            all_cols=True, skip=())
        hdr = t.horizontalHeader()
        hdr._open_menu(0)
        menu = hdr._menu
        assert menu is not None
        assert menu._counts.get("zzz-tersembunyi") == 0, (
            "nilai state hilang dari counts harus ditambahkan (union)")
        texts = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        assert any("zzz-tersembunyi" in t and "tersembunyi" in t
                   and "lepas filter lain" in t for t in texts), texts
        # nilai tersembunyi ikut tercentang (bagian filter aktif)
        assert menu._checked.get("zzz-tersembunyi") is True
        # varian NaN: state None + counts NaN → TAK dobel '(kosong)'
        t2 = DataTable()
        t2.set_dataframe(pd.DataFrame({
            "TOTAL": [np.nan, 1.0, 5.0], "KETERANGAN": ["a", "b", "c"]}))
        t2.setup_header_filters(
            None, lambda c, k, vals: None, lambda col: [None],
            all_cols=True, skip=())
        hdr2 = t2.horizontalHeader()
        hdr2._open_menu(0)
        menu2 = hdr2._menu
        n_kosong = sum(1 for i in range(menu2._lw.count())
                       if menu2._lw.item(i).text().startswith("(kosong)"))
        assert n_kosong == 1, (
            "None state harus menyatu dgn kunci NaN counts (tak dobel)")
        assert len(menu2._counts) == 3, (
            "None state menyatu dgn kunci NaN — tak ada entri ke-4")


# ============================================================
# [D5+D6] Progres ke status bar utama + pesan akhir hasil-run
# ============================================================

class TestD5D6StatusRun:
    def test_progres_status_bar_dan_pesan_akhir_setelah_render(
            self, monkeypatch):
        """D5+D6: tiap baris stage saat run menulis status bar JENDELA
        UTAMA ('⏳ …' running — pindah tab tak lagi kehilangan progres);
        pesan TERAKHIR pasca-run = HASIL RUN (2 angka berlabel) ditulis
        SETELAH set_dataset/render — bukan '✓ Menyaring… selesai (N ms)'
        dari busy render (dulu user membaca pekerjaan FILTER sebagai
        hasil akhir)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        ctx = AppContext({})
        view = vp.PipelineView(ctx)
        captured: list = []
        ctx.status.connect(lambda t, k: captured.append((t, k)))
        ctx.data_ready.connect(lambda: captured.append(("MARKER", "")))
        _MBStub.calls = []
        monkeypatch.setattr(vp, "QMessageBox", _MBStub)
        # D5: progres stage → status bar utama (label Indonesia via _log_id)
        view._on_progress("Stage 3 — Reason summary ...", 30)
        app.processEvents()
        assert captured[-1] == ("⏳ Tahap 3 — ringkasan alasan ...",
                                "running"), captured[-1]
        assert view._progress.value() == 30
        # D6: pesan akhir SETELAH render (marker set_dataset mendahului)
        df = _full_df(2)
        summary = {"success": True, "df": df, "total_rows": 2,
                   "prioritas_count": 1, "potensi_count": 1,
                   "anomali_count": 2, "review_count": 0,
                   "workbook_path": "rekap.xlsx"}
        view._on_done(summary)
        app.processEvents()
        texts = [t for t, _k in captured]
        i_marker = texts.index("MARKER")
        i_final = next(i for i, t in enumerate(texts)
                       if t.startswith("✓ Pipeline selesai"))
        assert i_final > i_marker, (
            "pesan akhir harus ditulis SETELAH set_dataset/render (D6)")
        assert captured[i_final] == (
            "✓ Pipeline selesai — 2 baris • 2 anomali (prioritas+potensi)",
            "done")
        assert captured[-1][1] == "done", (
            "pesan TERAKHIR pasca-run = hasil run, bukan busy render")
        assert not any("Menyaring" in t for t in texts), (
            "klaim 'Menyaring… selesai' tak boleh jadi pesan akhir (D6)")
        # v2.13.14 (gel-5 D27) — DITULIS ULANG JUJUR: assertion lama
        # mem-PIN modal "Pipeline Selesai" (QMessageBox.information) yang
        # muncul TIAP run sukses. Audit D27: status bar jendela utama +
        # kartu Ringkasan Run sudah menyampaikan hasil — modal sukses
        # dihapus (jalur GAGAL tetap modal critical); run sukses kini
        # TANPA dialog apa pun.
        assert not any(c[0] == "information" for c in _MBStub.calls), (
            "run sukses tak boleh lagi memunculkan modal (D27)")

    def test_first_run_tanpa_klaim_menyaring(self):
        """D6 (first-run): render TANPA dataset TIDAK dibungkus
        busy_feedback — dulu klaim '✓ Menyaring & menampilkan data
        selesai (0 ms)' / '✓ Menganalisa hari tersangka selesai (0 ms)'
        padahal tak ada data (klaim kosong); label arah tetap ter-render
        (kontrak D4 gel-2 utuh)."""
        from ui.state import AppContext
        from ui.view_anomali import AnomaliView
        from ui.view_hari import HariView
        app = _qapp()
        for cls, frag in [(AnomaliView, "Menyaring & menampilkan data"),
                          (HariView, "Menganalisa hari tersangka")]:
            ctx = AppContext({})
            view = cls(ctx)
            captured: list = []
            ctx.status.connect(lambda t, k: captured.append(t))
            view._refresh_table()
            app.processEvents()
            assert not any(frag in t for t in captured), (
                f"first-run {cls.__name__} tak boleh klaim '{frag}'")
            assert "Belum ada data" in view._lbl_count.text()
            assert view._lbl_count.text().endswith("jalankan.")


# ============================================================
# [D22] Gate cancel antar-file fase LOAD
# ============================================================

class TestD22CancelGate:
    def test_cancel_gate_antar_file_load(self):
        """D22: cancel_check kini dicek ANTAR-FILE fase LOAD (DATA_WASTE/
        BOM/DATABASE_SATUAN) — dulu fase LOAD tanpa gate: tombol ⏹ tak
        berefek sampai Stage 1 (terasa lama di file besar). Cancel
        dinyatakan SETELAH file pertama termuat → gate kedua (BOM)
        menghentikan run dgn pesan jujur 'saat memuat file'."""
        from waste_anomaly.pipeline import run_pipeline
        calls = {"n": 0}

        def cancel_check() -> bool:
            calls["n"] += 1
            return calls["n"] > 1  # lolos gate DATA_WASTE, berhenti di BOM
        result = run_pipeline(workbook_path=str(WORKBOOK), key_akhir=31,
                              cancel_check=cancel_check)
        assert result["success"] is False
        assert result.get("cancelled") is True
        assert "saat memuat file (BOM)" in result["error"], result["error"]
        # gate hidup SETELAH file termuat (bukan pra-load) — log membuktikan
        assert "Loading DATA_WASTE" in result["log"]
        assert "Loading BOM" in result["log"]
        assert "Stage 1" not in result["log"], (
            "cancel antar-file harus mencegah stage pertama berjalan")


# ============================================================
# [B10] Render banding dibungkus busy_feedback penuh
# ============================================================

class TestB10BusyBanding:
    def test_refresh_result_dibungkus_busy_penuh(self):
        """B10: SELURUH _refresh_result dibungkus busy_feedback (dulu
        hanya compare_quantity — render pertama tab banding 833 ms
        offscreen BEKU senyap tanpa cursor sibuk). First-run TANPA
        dataset tak dibungkus (tanpa klaim 'selesai (0 ms)' — D6-kelas)."""
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        app = _qapp()
        # first-run: df None → impl tanpa busy (tanpa klaim kosong)
        ctx0 = AppContext({})
        view0 = PeriodeView(ctx0)
        captured0: list = []
        ctx0.status.connect(lambda t, k: captured0.append(t))
        view0._refresh_result()
        app.processEvents()
        assert not any("hasil banding" in t for t in captured0)
        # berdata: badan penuh dibungkus (label lapisan luar menutup)
        ctx = AppContext({})
        ctx.set_dataset(_df_ayam(), {"key_akhir": 31})
        view = PeriodeView(ctx)
        captured: list = []
        ctx.status.connect(lambda t, k: captured.append(t))
        view._refresh_result()
        app.processEvents()
        assert any(t.startswith("⏳ Menampilkan hasil banding")
                   for t in captured), captured
        assert any(t.startswith("✓ Menampilkan hasil banding selesai")
                   for t in captured), captured
        i_open = next(i for i, t in enumerate(captured)
                      if t.startswith("⏳ Menampilkan hasil banding"))
        i_close = next(i for i, t in enumerate(captured)
                       if t.startswith("✓ Menampilkan hasil banding"))
        assert i_open < i_close


# ============================================================
# [C8] Memo drill Scorecard LRU-8
# ============================================================

class TestC8MemoDrill:
    def test_drill_memo_hit_satu_hitungan(self, monkeypatch):
        """C8: drill rincian cabang di-MEMO keyed (resto, data_version,
        history_version) — klik-2 ×2 resto sama = hitung SEKALI (dulu
        bolak-balik cabang menghitung ulang PENUH 102-164 ms tiap kali);
        busy 'Menghitung rincian' hanya di jalur MISS."""
        from contextlib import contextmanager
        import ui.view_scorecard as vs
        view, ctx, app = _view_scorecard(_df_scorecard())
        rec = view._table.model().record(0)
        resto = str(rec.get("NAMA RESTO"))
        busy_labels: list = []
        orig = vs.busy_feedback

        @contextmanager
        def spy_busy(status_cb=None, label="Memproses"):
            busy_labels.append(label)
            with orig(status_cb, label):
                yield
        monkeypatch.setattr(vs, "busy_feedback", spy_busy)
        view._on_double(rec)
        app.processEvents()
        assert view._drill is not None and view._drill.isVisible()
        assert len(view._drill_cache) == 1
        misses = [l for l in busy_labels if "Menghitung rincian" in l]
        assert len(misses) == 1
        # hit ke-2 (objek sama) → tanpa hitung, tanpa busy miss
        view._on_double(rec)
        app.processEvents()
        misses2 = [l for l in busy_labels if "Menghitung rincian" in l]
        assert len(misses2) == 1, "cache hit tak boleh menghitung ulang"
        assert len(view._drill_cache) == 1
        assert resto in view._drill_title.text()

    def test_drill_memo_lru8_evict(self, monkeypatch):
        """C8 (LRU-8): memo menampung maksimal 8 kombinasi — drill ke-9
        mengeluarkan yang paling lama tak dipakai (LRU), kunci = (resto,
        data_version, history_version) — data baru = kunci baru = hitung
        ulang jujur."""
        from contextlib import contextmanager
        import ui.view_scorecard as vs
        view, ctx, app = _view_scorecard(_df_scorecard(n_resto=10))
        orig = vs.busy_feedback

        @contextmanager
        def silent_busy(status_cb=None, label="Memproses"):
            with orig(status_cb, label):
                yield
        monkeypatch.setattr(vs, "busy_feedback", silent_busy)
        for r in range(9):
            rec = view._table.model().record(r)
            view._on_double(rec)
            app.processEvents()
        keys = list(view._drill_cache.keys())
        assert len(view._drill_cache) == 8, (
            "LRU-8: drill ke-9 harus mengeluarkan entri tertua")
        restos = [k[0] for k in keys]
        assert "R0" not in restos, (
            "entri paling lama (R0, drill pertama) harus ter-evict")
        assert "R8" in restos and "R1" in restos


# ============================================================
# [D10] PipelineWorker finished → deleteLater
# ============================================================

class TestD10DeleteLater:
    def test_worker_finished_delete_later(self, monkeypatch, tmp_path):
        """D10: worker pipeline terhubung finished→deleteLater — tiap
        run membuat QThread baru; tanpa ini objek worker menumpuk seumur
        aplikasi (pola ExportWorker/HistoryWorker). Stub worker
        (QThread nyata) selesai → objek Qt benar-benar dihancurkan
        (sinyal destroyed)."""
        from PySide6.QtCore import QCoreApplication, QEvent, QThread
        from PySide6.QtCore import Signal
        import ui.view_pipeline as vp
        app = _qapp()

        class _StubWorker(QThread):
            # kontrak sinyal PipelineWorker (stub tak memancarkan apa pun)
            progress = Signal(str, float)
            done = Signal(dict)
            failed = Signal(str, str)

            def __init__(self, wb, ka, parent=None):
                super().__init__(parent)

            def run(self):
                return
        monkeypatch.setattr(vp, "PipelineWorker", _StubWorker)
        from ui.state import AppContext
        view = vp.PipelineView(AppContext({}))
        view._ent_workbook.setText(str(WORKBOOK))  # path ada (stubs tak baca; v2.18.0 fallback sample)
        view._start()
        w = view._worker
        assert w is not None and isinstance(w, _StubWorker)
        destroyed: list = []
        w.destroyed.connect(lambda *a: destroyed.append(1))
        assert w.wait(3000), "stub worker harus selesai cepat"
        app.processEvents()  # antre finished → deleteLater
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        assert destroyed == [1], (
            "worker harus terhapus pasca finished (deleteLater — D10)")


# ============================================================
# [D29] Disable 3 tombol selama compute pratinjau (try/finally)
# ============================================================

class TestD29DisableTombol:
    def test_tiga_tombol_disable_selama_compute_dan_pulih(self, monkeypatch):
        """D29: tombol Mulai/Simpan/Pratinjau NONAKTIF selama compute
        pratinjau sinkron (dulu tetap aktif → klik ganda = nested
        compute + freeze bertumpuk); pulih di finally — exception
        compute pun tak mengunci UI permanen."""
        import pytest
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        ctx = AppContext({})
        ctx.set_dataset(_full_df(2), {"key_akhir": 31})
        view = vp.PipelineView(ctx)
        buttons = (view._btn_run, view._btn_save, view._btn_preview)
        assert all(b.isEnabled() for b in buttons)
        _MBStub.calls = []
        monkeypatch.setattr(vp, "QMessageBox", _MBStub)
        seen: dict = {}

        def fake_cs(df, ka, cfg, params=None):
            seen["disabled"] = [not b.isEnabled() for b in buttons]
            return pd.DataFrame({"ANOMALY STATUS": ["Normal"] * 2})
        monkeypatch.setattr("waste_anomaly.signals.compute_signals",
                            fake_cs)
        view._preview_thresholds()
        app.processEvents()
        assert all(seen["disabled"]), (
            "3 tombol harus nonaktif SELAMA compute pratinjau (D29)")
        assert all(b.isEnabled() for b in buttons), (
            "tombol pulih pasca compute")
        # exception compute → finally tetap memulihkan
        def boom(*a, **k):
            raise RuntimeError("boom-compute")
        monkeypatch.setattr("waste_anomaly.signals.compute_signals", boom)
        with pytest.raises(RuntimeError):
            view._preview_thresholds()
        assert all(b.isEnabled() for b in buttons), (
            "try/finally: exception pun memulihkan tombol (D29)")


# ============================================================
# [D28] Dialog keluar default No
# ============================================================

class TestD28DefaultNo:
    def test_close_event_default_no(self, tmp_path, monkeypatch):
        """D28: dialog 'Proses masih berjalan. Tetap keluar?' tombol
        DEFAULT = No (pola D2 gel-2 — Enter salah = aman batal); dulu
        default Yes: Enter saat dialog muncul = keluar paksa padahal
        worker masih berjalan."""
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        for _name, v in win._views:
            if getattr(v, "_btn_run", None) is not None:  # view Pipeline
                v._running = True
                v._worker = object()  # dummy — tak pernah ditunggu (No)
        captured: dict = {}

        def fake_question(parent, title, text, *args):
            captured["title"] = title
            captured["args"] = args
            return QMessageBox.StandardButton.No
        monkeypatch.setattr(ap.QMessageBox, "question",
                            staticmethod(fake_question))
        ev = QCloseEvent()
        win.closeEvent(ev)
        assert captured["title"] == "Proses masih berjalan"
        assert captured["args"], "question memakai tombol eksplisit"
        assert captured["args"][-1] == QMessageBox.StandardButton.No, (
            "tombol default harus NO (Enter salah = aman batal — D28)")
        assert not ev.isAccepted(), "jawaban No → keluar ditolak"
        # v2.13.14 (D24-fix, higienis test): pulihkan flag _running/_worker
        # SEBELUM teardown — dulu window bocor (lambda D24 menangkap self)
        # bertahan sampai _dispose_orphan_widgets conftest → close() →
        # closeEvent melihat _running → QMessageBox.question ASLI (monkeypatch
        # sudah dibuka) → modal exec() MENUNGGU KLIK yang tak pernah datang
        # di offscreen → full suite HANG. Kini lambda diganti bound method
        # (receiver lemah) window mati saat refcount turun; reset ini =
        # pertahanan kedua bila kelak ada kebocoran lain.
        for _name, v in win._views:
            if getattr(v, "_btn_run", None) is not None:
                v._running = False
                v._worker = None
        win.close()


# ============================================================
# [C13] narrow_hide — kolom pembanding paling akhir
# ============================================================

class TestC13NarrowHide:
    def test_narrow_hide_pembanding_paling_akhir(self, monkeypatch):
        """C13: lantai header tak muat → kolom disembunyikan SESUAI
        URUTAN narrow_hide — kolom PEMBANDING (ALASAN HARI, NILAI BULAN
        LALU) kini PALING AKHIR (dulu duluan: layar 1366px kehilangan
        bukti pembanding justru saat pembanding AKTIF). Kolom
        non-pembanding (KETERANGAN, TIPIKAL) mundur duluan."""
        import ui.widgets as uw
        captured: dict = {}
        orig = uw.DataTable.set_dataframe

        def spy(self, df, **kw):
            if "narrow_hide" in kw:
                captured["narrow_hide"] = list(kw["narrow_hide"])
            return orig(self, df, **kw)
        monkeypatch.setattr(uw.DataTable, "set_dataframe", spy)
        view, _ctx = _make_hari()
        nh = captured["narrow_hide"]
        assert nh == ["KETERANGAN", "TIPIKAL BEBERAPA BULAN",
                      "NILAI BULAN LALU", "ALASAN HARI"], nh
        # pembanding = dua EKOR terakhir (mundur paling belakang)
        assert set(nh[-2:]) == {"NILAI BULAN LALU", "ALASAN HARI"}
        assert nh.index("KETERANGAN") < nh.index("NILAI BULAN LALU")


# ============================================================
# [B14] Persen kumulatif di log stage
# ============================================================

class TestB14PersenLog:
    def test_log_stage_membawa_persen(self):
        """B14: baris log stage kini membawa persen kumulatif '(N%)' —
        dulu callback (msg, pct) MEMBUANG pct dari log run (log tak
        menunjukkan progres; sheet Log Run pun tak bernilai persen)."""
        from waste_anomaly.pipeline import run_pipeline
        lines: list = []
        state = {"cancel": False}

        def on_progress(msg, pct):
            lines.append(msg)
            if msg.startswith("Stage 1"):
                state["cancel"] = True
        result = run_pipeline(workbook_path=str(WORKBOOK), key_akhir=31,
                              progress_callback=on_progress,
                              cancel_check=lambda: state["cancel"])
        assert result["success"] is False and result.get("cancelled")
        stage_lines = [l for l in lines if l.startswith("Stage ")]
        assert stage_lines, "log stage harus terisi"
        assert all(re.search(r"\(\d+%\)$", l) for l in stage_lines), (
            "SETIAP baris stage harus ber-ekor '(N%)' (audit B14)")
        assert any(l.startswith("Stage 1 — Source & cleanup ...")
                   for l in stage_lines)


# ============================================================
# [SWEEP C7] Enter = drill Scorecard
# ============================================================

class TestSweepC7EnterDrill:
    def test_enter_drill_scorecard(self):
        """C7: Enter/Return di baris terpilih tabel Scorecard = DRILL
        rincian cabang — padanan keyboard utk klik-2 mouse (dulu hanya
        mouse: pengguna keyboard-only tak punya jalur sama sekali)."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        view, _ctx, app = _view_scorecard(_df_scorecard())
        view._table.setCurrentIndex(view._table.model().index(0, 1))
        app.processEvents()
        view._table.setCurrentIndex(view._table.model().index(0, 1))
        app.processEvents()
        rec = view._table.selected_record()
        expected = str(rec.get("NAMA RESTO"))
        QTest.keyClick(view._table, Qt.Key.Key_Return)
        app.processEvents()
        assert view._drill is not None and view._drill.isVisible(), (
            "Enter harus membuka drill rincian cabang (a11y C7)")
        assert expected in view._drill_title.text()
        # kontrak: klik-2× mouse tetap jalur utama (eventFilter tak
        # mengganggu) — pop-up tertutup, dbl-click terhubung
        assert view._drill.isVisible()


# ============================================================
# [SWEEP B16+B18] Tooltip path file + funnel reset saat pembanding
# berganti (worker sungguhan — pola v21311)
# ============================================================

class TestSweepB16B18Periode:
    def test_tooltip_path_dan_funnel_reset_pembanding(self, tmp_path,
                                                      monkeypatch):
        """B16: kolom File menampilkan NAMA file tapi tooltip = PATH
        PENUH (dulu tak ada cara melihat lokasi file — 2 file beda
        folder bernama sama tak terbedakan).
        B18: PEMBANDING berganti (combo) → funnel halaman di-RESET
        (nilai funnel bulan lama bisa tak ada di bulan baru → tabel 0
        baris senyap; dulu hanya dataset baru yang me-reset); pembanding
        SAMA dirender ulang → funnel DIPERTAHANKAN."""
        view, ctx, app = _view_periode_files(tmp_path, monkeypatch,
                                             ["JULI", "AGUSTUS"])
        # B16 — tooltip path penuh di kolom File
        n = view._tbl_files.rowCount()
        assert n == 2
        tips = {str(view._tbl_files.item(r, 1).toolTip())
                for r in range(n)}
        paths = {str(e["path"]) for e in view._entries}
        assert tips == paths, "tooltip kolom File harus PATH PENUH (B16)"
        for r in range(n):
            assert view._tbl_files.item(r, 1).text().endswith(".xlsx")
            assert "/" not in view._tbl_files.item(r, 1).text()
        # B18 — pembanding berganti → funnel halaman reset
        assert view._pf_b_key_cache is not None
        view._pfilters["items"]["NAMA RESTO"] = ["R1"]
        view._cb_b.setCurrentIndex(view._cb_b.count() - 1)  # bulan terakhir
        app.processEvents()
        view._refresh_result()
        app.processEvents()
        assert view._pfilters["items"] == {}, (
            "pembanding berganti → funnel halaman harus reset (B18)")
        # pembanding SAMA dirender ulang → funnel dipertahankan
        view._pfilters["items"]["NAMA RESTO"] = ["R1"]
        view._refresh_result()
        app.processEvents()
        assert view._pfilters["items"] == {"NAMA RESTO": ["R1"]}, (
            "render ulang pembanding sama tak boleh membuang funnel")


# ============================================================
# [SWEEP D25] QSS :focus tombol — navigasi keyboard terlihat
# ============================================================

class TestSweepD25QssFocus:
    def test_qss_fokus_tombol_dan_pin_versi(self):
        """D25: rule :focus QSS utk tombol biasa/accent/danger — dulu
        hanya :hover (navigasi keyboard Tab/Enter tak pernah menunjukkan
        tombol aktif; a11y). + pin versi file test ke-5 (v2.13.13)."""
        from ui.theme import QSS
        assert "QPushButton:focus {" in QSS
        assert "QPushButton#accent:focus {" in QSS
        assert "QPushButton#danger:focus {" in QSS
        # keyboard-visible: rule fokus tombol LEBIH BANYAK dari era lama
        assert QSS.count(":focus") >= 4
        from ui.shared import APP_VERSION
        assert APP_VERSION == "2.18.3"  # pin versi file test ke-5 (gel-4; dinaikkan v2.15.0)
