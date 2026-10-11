"""test_v21315.py — regresi v2.13.15 (Gelombang 6 — GELOMBANG TERAKHIR:
13 sisa P3 dari audit UI/UX 94 temuan, perintah "kerjakan semua"; B21
di-skip jujur: desain eksplisit v2.12.2 startup-only — auto-collapse
dibatasi ke startup sejak gel-B, bukan bug).

[A15]     Indikator ambang skor LINTAS-TAB di tab Hari: spin "Anomali
          dengan skor ≥" (tab Anomali) menyaring ctx.anomali_df() yang
          JUGA jadi sumber tabel Hari — tabel diam-diam mengecil tanpa
          sebab terlihat. Label hitungan kini menyebut "⚠ Skor ≥ N
          aktif (diatur di tab Anomali)" + tooltip cara melepas.
[A18]     Dua "median cabang lain" beda definisi dalam SATU pop-up
          detail kini BERLABEL SCOPE: rasio ringkasan = "vs median
          cabang lain (sebulan)" (TOTAL / PEER MEDIAN — median TOTAL
          sebulan) vs daftar lengkap "PEER MEDIAN MAX — median cabang
          lain per hari (puncak)"; suffix nilai "(median sebulan N
          cabang)".
[B13]     _result_version DIHAPUS dari view_periode (dead state: ditulis
          tiap _refresh_result, tak pernah dibaca — pola bersih-bersih
          v2.13.8; kunci ketiadaan via source-contract).
[B24]     SKIP JUJUR + KUNCI: F1 Bantuan sudah menyebut rename manual
          entri banding (klik-2×/Enter/F2) sejak gel-5 B19 — test ini
          MENGUNCI dokumentasi itu tak terhapus (regresi doc).
[C6]      Funnel kartu 📅 Pola Hari Kalender & 🔗 Hari Sistemik
          Scorecard DI-AKTIFKAN (setup_header_filters — dulu plumbing
          _lfilters/_page_apply/_apply_local ADA tapi ikon funnel tak
          pernah terpasang: filter tak bisa dibuka + docstring modul
          menjanjikan "SEMUA kolom ber-funnel"); label kartu ikut
          menyatakan jumlah tampil + suffix tersaring pasca apply.
[C12]     Dataset tanpa kolom BUKTI HARI (tapi ber-HARI TERSANGKA) →
          pesan jujur "Dataset ini tanpa bukti hari (kolom … absen)"
          (dulu: bukti semua-False → 0 baris + "0 anomali lolos
          filter" MENYALAHKAN filter padahal kolomnya absen).
[C17]     Label info Follow Up SCOPE TERPISAH: funnel lokal aktif →
          "N dari M baris daftar tampil (funnel lokal — daftar & ekspor
          tak tersaring) · TOTAL tampil X · TOTAL daftar penuh Y"
          (dulu SATU kalimat mencampur n terfilter vs total tak
          terfilter: "0 baris · TOTAL 99").
[C19]     Drill rincian cabang Scorecard DITUTUP saat dataset berganti
          (data_ready) + cache drill dikosongkan — dulu dialog terbuka
          terus memajang angka dataset LAMA di atas tabel dataset baru
          (pola pop-up Anomali; drill Banding ditutup sejak gel-1).
[C21]     Kontras teks TAB NON-AKTIF ≥ WCAG AA 4,5:1 — dulu #64748b di
          atas #e2e8f0 = 3,1:1 (label tab kabur); kini C_TAB_IDLE_FG
          #475569 (slate-600) ≈ 6,1:1 — rasio DIHITUNG fungsi luminance
          relatif WCAG di test ini (bukan angka klaim).
[D11]     SATU konstanta ambang log run: ui.shared.LOG_RUN_LINES dipakai
          panel log (setMaximumBlockCount), memori ctx.log_lines (cap),
          dan sheet Log Run ekspor (slice) — dulu TIGA nilai beda
          (2000/500/200) tanpa nama.
[D16]×2   Tombol 💾 Ekspor Excel NONAKTIF sampai ada data (dulu tampak
          siap sejak first-run → klik = dialog "Belum ada data"); aktif
          pasca dataset non-kosong; dataset kosong tetap nonaktif.
[D21]     Header log run DIBERSIHKAN dari duplikasi: UI tidak lagi
          menulis "=== Mulai Pipeline ==="/"Workbook: …" SEBELUM engine
          (yang mencatat keduanya via _on_progress, terjemahan D18) +
          ekor "=== Selesai ===" dihapus (engine sudah mencatat "===
          Pipeline DONE ==="); baris Output engine jujur "—" saat tanpa
          output_path (dulu mencetak path placeholder "output/…" yang
          tak pernah ditulis).
[D30]     Tinggi-minimum jendela ADAPTIF layar: _adaptive_min_height =
          max(560, min(700, h−80)) — dulu literal 700px > layar pendek
          (netbook 600px / VM available 648px → jendela tak termuat
          penuh). test_v280 geometry pin ikut ditulis ulang jujur.

Fixture pola v21313/v2139/v2133/v21311 (hari ber-bukti, full df pop-up,
followup 2-baris, worker-stub). NB: output terminal kadang mem-mANGLE
sekuens "[" — verifikasi konten via compile/codepoint.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import QThread, Signal

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

_FRAG = "Lonjakan vs rata-rata harian | Puncak harian vs BOM | Menumpuk di hari terakhir"


def _qapp():
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


# ============================================================
# FIXTURES
# ============================================================

def _hari_df() -> pd.DataFrame:
    """Dataset hari ber-bukti (pola test_v21313 — Stage 15 sungguhan)."""
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
            **vals, "TOTAL": float(sum(vals.values())),
            "ANOMALY STATUS": "Potensi Anomali",
            "ANOMALY SCORE": 9,
            "HARI MAX": 17.0 if resto == "A.OUTLET" else 1.0,
            "SCALE SIGNAL": "YES" if resto == "A.OUTLET" else "NO",
            "SINGLE DAY": "NO",
        })
    return annotate_day_evidence(pd.DataFrame(rows), 31, {"thresholds": {}})


def _full_df() -> pd.DataFrame:
    """Fixture pop-up detail lengkap (pola test_v2139 + kolom PEER MEDIAN
    TOTAL/MAX + PEER MEDIAN (AKTIF) — dua median beda definisi, audit A18)."""
    rec = {
        "NAMA RESTO": "RESTO 0", "NAMA BARANG": "BARANG 0",
        "JENIS": "WASTE", "KETERANGAN": "Kualitas Internal",
        "SOURCE DATA": "REKAP", "SATUAN": "GR",
        **{str(d): 5.0 for d in range(1, 31)},
        "TOTAL": 12470.0, "MAX": 8000.0, "HARI MAX": 17,
        "ANOMALY SCORE": 12, "ANOMALY STATUS": "Prioritas Tinggi",
        "ANOMALY REASONS": _FRAG,
        "% to BOM": 0.0134, "MAX SHARE": 0.64,
        "PEER COUNT": 9, "TOTAL / PEER MEDIAN": 2.44,
        "PEER MEDIAN TOTAL": 5100.0, "PEER MEDIAN MAX": 2000.0,
        "MAX / PEER MEDIAN MAX": 4.0,
        "PEER MEDIAN (AKTIF)": 6000.0, "PEER AKTIF": 7,
        "BULAN LALU": 9220.0, "PERUBAHAN %": 35.2,
        "RANGKING WASTE": "Top 2 TOTAL",
        "KATEGORI ANOMALI": "Lonjakan Ekstrem",
    }
    return pd.DataFrame([rec])


def _panel(rec: pd.Series):
    from ui.state import AppContext
    from ui.view_anomali import DetailPanel
    panel = DetailPanel(AppContext({}))
    panel.show()
    panel.show_record(rec)
    return panel


def _df_fu() -> pd.DataFrame:
    """Fixture Follow Up 2-baris (pola test_v2133)."""
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


def _df_scorecard_sistemik(n_resto: int = 4,
                           spikes: tuple = (10, 20)) -> pd.DataFrame:
    """Dataset dengan HARI SISTEMIK ≥ 2 (semua resto naik serentak di hari
    spike → median harian 5, nilai 50 = 10×) + label bulan utk kartu
    kalender (workbook_path di summary)."""
    rows = []
    for i in range(n_resto):
        data = {str(d): 5.0 for d in range(1, 31)}
        for s in spikes:
            data[str(s)] = 50.0
        rows.append({
            "SOURCE DATA": "W", "JENIS": "WASTE", "KETERANGAN": "Handling",
            "NAMA BARANG": "MIE", "NAMA RESTO": f"R{i}", "SATUAN": "GR",
            "ANOMALY STATUS": "Perlu Review", "PROFIL": "Tiap Hari",
            **data, "TOTAL": float(sum(data.values())),
            "KELEBIHAN": 5.0, "PEER MEDIAN (AKTIF)": 50.0,
            "TOTAL BOM": 10_000.0,
        })
    return pd.DataFrame(rows)


def _view_scorecard(df: pd.DataFrame, summary: dict | None = None):
    from ui.state import AppContext
    from ui.view_scorecard import ScorecardView
    app = _qapp()
    ctx = AppContext({})
    ctx.set_dataset(df, summary or {"key_akhir": 31})
    view = ScorecardView(ctx)
    view.show()
    app.processEvents()
    view._refresh()
    app.processEvents()
    return view, ctx, app


# ============================================================
# [A15] Indikator skor lintas-tab di tab Hari
# ============================================================

class TestA15IndikatorSkorLintasTab:

    def test_indikator_skor_aktif_dan_hilang(self):
        """Skor ≥ aktif → label hitungan Hari menyebut ambang + asalnya
        (tab Anomali) + tooltip cara lepas; skor 0 → indikator + tooltip
        bersih (label kembali polos)."""
        from ui.state import AppContext
        from ui.view_hari import HariView
        app = _qapp()
        ctx = AppContext({})
        view = HariView(ctx)
        ctx.set_dataset(_hari_df(), {"key_akhir": 31})
        view._refresh_table()
        base = view._lbl_count.text()
        assert "Skor ≥" not in base, "premis: tanpa ambang tak ada indikator"
        # ambang N ≥ skor semua baris (9): tabel tetap berisi, indikator hadir
        ctx.set_score_min(9)
        view._refresh_table()
        txt = view._lbl_count.text()
        assert "· ⚠ Skor ≥ 9 aktif (diatur di tab Anomali)" in txt, txt
        assert txt.startswith(base), "bagian hitungan asli tak boleh berubah"
        assert "tab Anomali" in view._lbl_count.toolTip()
        assert "skor ≥ 9" in view._lbl_count.toolTip()
        # ambang di atas semua skor: 0 baris — pesan filter TETAP menyebut
        # penyebab skor (bukan hanya menyalahkan funnel).
        ctx.set_score_min(10)
        view._refresh_table()
        txt0 = view._lbl_count.text()
        assert txt0.startswith("0 anomali lolos filter"), txt0
        assert "Skor ≥ 10 aktif" in txt0, txt0
        # lepas → indikator & tooltip bersih
        ctx.set_score_min(0)
        view._refresh_table()
        assert view._lbl_count.text() == base
        assert view._lbl_count.toolTip() == ""
        view.close()
        view.deleteLater()


# ============================================================
# [A18] Label dua "median cabang lain" beda definisi
# ============================================================

class TestA18MedianScopeLabel:

    def test_label_median_sebulan_vs_per_hari(self):
        """Ringkasan "vs median cabang lain (sebulan)" + nilai "(median
        sebulan N cabang)"; daftar lengkap PEER MEDIAN TOTAL/MAX membawa
        sufiks scope yang BERBEDA (sebulan vs per hari)."""
        from PySide6.QtWidgets import QLabel
        panel = _panel(_full_df().iloc[0])
        texts = [l.text() for l in panel._content.findChildren(QLabel)]
        # ringkasan: rasio vs median TOTAL sebulan — label + nilai
        assert "vs median cabang lain (sebulan):" in texts
        assert "2,4× (median sebulan 9 cabang)" in texts
        # daftar lengkap: dua kolom median pembanding ber-sufiks scope beda
        assert ("PEER MEDIAN TOTAL — median cabang lain sebulan:"
                in texts), texts
        assert ("PEER MEDIAN MAX — median cabang lain per hari (puncak):"
                in texts), texts
        # label generik ambigu TAK boleh kembali
        assert "vs cabang lain (median):" not in texts


# ============================================================
# [B13] _result_version dead state dihapus
# ============================================================

class TestB13ResultVersionHapus:

    def test_kontrak_tak_ada(self):
        """Source-contract pola test_v2138 (dead-field dilarang kembali):
        "self._result_version" tak ada lagi di view_periode.py (komentar
        sejarah BOLEH menyebut nama tanpa prefix — pola state.py gel-C)
        + instance tak memiliki atributnya (dulu ditulis tiap
        _refresh_result tapi tak pernah dibaca)."""
        from ui.state import AppContext
        from ui.view_periode import PeriodeView
        src = (UI / "view_periode.py").read_text(encoding="utf-8")
        assert "self._result_version" not in src, (
            "dead state _result_version kembali (audit B13)")
        _qapp()
        view = PeriodeView(AppContext({}))
        assert not hasattr(view, "_result_version")
        view.close()
        view.deleteLater()


# ============================================================
# [B24] F1 help menyebut rename banding (SKIP jujur — kunci)
# ============================================================

class TestB24HelpRenameBanding:

    def test_help_menyebut_rename_manual(self):
        """SKIP JUJUR G6-4: fitur rename manual sudah didokumentasikan F1
        sejak gel-5 B19 ("klik 2× / Enter/F2") — fix G6 tak perlu menulis
        ulang; test ini MENGUNCI dokumen itu agar tak terhapus diam-diam
        (regresi doc, bukan fix baru)."""
        from ui.app import _HELP_HTML
        assert "Enter/F2" in _HELP_HTML, (
            "F1 tak lagi menyebut rename keyboard (gel-5 B19 hilang)")
        assert "klik 2×" in _HELP_HTML
        assert "koreksi" in _HELP_HTML


# ============================================================
# [C6] Funnel kartu kalender/sistemik Scorecard aktif
# ============================================================

class TestC6FunnelKartuSkor:

    def test_funnel_kartu_kalender_aktif(self):
        """Ikon funnel terpasang (plumbing hidup) + apply menyaring tabel
        + label kartu menyatakan jumlah tersaring (dulu tabel kartu TANPA
        funnel: menu tak bisa dibuka — audit C6)."""
        view, ctx, app = _view_scorecard(
            _df_scorecard_sistemik(),
            {"key_akhir": 31,
             "workbook_path": "/x/WASTE_SEPTEMBER_2026.xlsx"})
        try:
            assert view._weekday_table._hf_has("HARI"), (
                "funnel kartu kalender tak terpasang (C6)")
            assert view._weekday_table.model().rowCount() == 7  # Sen..Mgg
            # apply funnel via jalur apply_fn (kontrak menu → _on_page_filter)
            view._on_page_filter("weekday", "HARI", ["Senin"])
            app.processEvents()
            assert view._weekday_table.model().rowCount() == 1
            assert view._lfilters_state("weekday", "HARI") == ["Senin"]
            assert "tersaring: 1 dari 7 tampil" in view._lbl_weekday.text()
            # refresh penuh mempertahankan funnel (apply_local) + suffix
            view._refresh()
            app.processEvents()
            assert view._weekday_table.model().rowCount() == 1
            assert "tersaring: 1 dari 7 tampil" in view._lbl_weekday.text()
            # lepas → tabel & label pulih
            view._on_page_filter("weekday", "HARI", None)
            app.processEvents()
            assert view._weekday_table.model().rowCount() == 7
            assert "tersaring" not in view._lbl_weekday.text()
        finally:
            view.close()
            view.deleteLater()

    def test_funnel_kartu_sistemik_aktif(self):
        """Funnel kartu sistemik aktif + label kartu kini MENYATAKAN
        jumlah hari sistemik (dulu label kosong saat ada hari sistemik —
        efek funnel tak terbaca)."""
        view, ctx, app = _view_scorecard(
            _df_scorecard_sistemik())
        try:
            assert view._sistemik_table._hf_has("HARI"), (
                "funnel kartu sistemik tak terpasang (C6)")
            assert view._sistemik_table.model().rowCount() == 2  # hari 10,20
            assert "2 hari sistemik" in view._lbl_sistemik.text()
            view._on_page_filter("sistemik", "HARI", [10])
            app.processEvents()
            assert view._sistemik_table.model().rowCount() == 1
            assert "1 hari sistemik" in view._lbl_sistemik.text()
            assert "tersaring: 1 dari 2 tampil" in view._lbl_sistemik.text()
        finally:
            view.close()
            view.deleteLater()


# ============================================================
# [C12] Dataset tanpa kolom BUKTI HARI → pesan jujur
# ============================================================

class TestC12TanpaKolomBuktiHari:

    def test_pesan_jujur_bukan_menyalahkan_filter(self):
        """HARI TERSANGKA ada tapi BUKTI HARI absen → "Dataset ini tanpa
        bukti hari (kolom BUKTI HARI absen)…" — BUKAN "0 anomali lolos
        filter" (dulu salah menyalahkan filter; opsi 'Semua anomali' tak
        menolong)."""
        from ui.state import AppContext
        from ui.view_hari import HariView
        app = _qapp()
        df = _hari_df().drop(columns=["BUKTI HARI"])
        assert "HARI TERSANGKA" in df.columns  # premis: setengah-stage
        ctx = AppContext({})
        view = HariView(ctx)
        ctx.set_dataset(df, {"key_akhir": 31})
        view._refresh_table()
        txt = view._lbl_count.text()
        assert "tanpa bukti hari" in txt
        assert "BUKTI HARI absen" in txt
        assert "lolos filter" not in txt, "pesan masih menyalahkan filter"
        assert view._table.model().rowCount() == 0
        view.close()
        view.deleteLater()


# ============================================================
# [C17] Label info Follow Up — scope dipisah
# ============================================================

class TestC17LabelFollowupScope:

    def test_scope_terpisah_saat_funnel_lokal(self):
        """Funnel lokal aktif → predikat eksplisit "N dari M baris daftar
        tampil (funnel lokal…)" + DUA total dilabeli (tampil vs daftar
        penuh); tanpa funnel → kalimat tunggal seperti dulu (legacy utuh)."""
        from ui.state import AppContext
        from ui.view_followup import FollowUpView
        from waste_anomaly.followup import fingerprint_series
        app = _qapp()
        ctx = AppContext({})
        ctx.set_dataset(_df_fu(), {"key_akhir": 31})
        fps = fingerprint_series(_df_fu())
        ctx.add_followup_many([fps.iloc[0], fps.iloc[1]])
        view = FollowUpView(ctx)
        try:
            view.refresh()
            assert view._lbl_info.text() == "2 baris · TOTAL gabungan 45"
            # funnel lokal JENIS=WASTE → hanya AYAM tampil
            view._hfilters["JENIS"] = ["WASTE"]
            view.refresh()
            txt = view._lbl_info.text()
            assert "1 dari 2 baris daftar tampil" in txt, txt
            assert "funnel lokal" in txt
            assert "ekspor tak tersaring" in txt
            assert "TOTAL tampil 30" in txt, txt
            assert "TOTAL daftar penuh 45" in txt, txt
            # lepas → kembali kalimat tunggal (tak ada scope campur)
            view._hfilters.pop("JENIS")
            view.refresh()
            assert view._lbl_info.text() == "2 baris · TOTAL gabungan 45"
        finally:
            view.close()
            view.deleteLater()


# ============================================================
# [C19] Drill Scorecard ditutup saat re-run dataset
# ============================================================

class TestC19DrillScorecardBasi:

    def test_drill_ditutup_saat_data_ready(self):
        """Drill rincian cabang TERBUKA saat dataset berganti (data_ready)
        → dialog di-hide + cache drill dikosongkan — dulu angka dataset
        LAMA terus terpampang di atas tabel dataset baru (audit C19)."""
        view, ctx, app = _view_scorecard(_df_scorecard_sistemik())
        try:
            view._table.selectRow(0)
            rec = view._table.selected_record()
            assert rec is not None
            view._on_double(rec)
            app.processEvents()
            assert view._drill is not None and view._drill.isVisible()
            assert len(view._drill_cache) == 1
            # re-run pipeline → dataset baru → drill ditutup + cache bersih
            ctx.set_dataset(_df_scorecard_sistemik(n_resto=6),
                            {"key_akhir": 31})
            app.processEvents()
            assert not view._drill.isVisible(), (
                "drill basi masih terbuka di atas dataset baru (C19)")
            assert len(view._drill_cache) == 0
        finally:
            view.close()
            view.deleteLater()


# ============================================================
# [C21] Kontras tab non-aktif ≥ WCAG AA
# ============================================================

def _rel_lum(hex_color: str) -> float:
    """Luminance relatif WCAG 2.1 (rumus resmi — dipakai hitung rasio)."""
    h = hex_color.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(c1: str, c2: str) -> float:
    l1, l2 = sorted((_rel_lum(c1), _rel_lum(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


class TestC21KontrasTabNonAktif:

    def test_rasio_kontras_tab_nonaktif_aa(self):
        """Teks tab non-aktif vs latar tab (QSS QTabBar::tab) ≥ 4,5:1 —
        dihitung dari QSS + konstanta theme (bukan klaim statis; dulu
        #64748b/#e2e8f0 = 3,1:1 < WCAG AA)."""
        import ui.theme as theme
        m = re.search(r"QTabBar::tab\s*\{([^}]*)\}", theme.QSS)
        assert m, "rule QTabBar::tab tak ditemukan di QSS"
        body = m.group(1)
        fg = re.search(r"color:\s*(#[0-9a-fA-F]{6})", body)
        bg = re.search(r"background:\s*(#[0-9a-fA-F]{6})", body)
        assert fg and bg, "color/background tab tak terparse"
        ratio = _contrast(fg.group(1), bg.group(1))
        assert ratio >= 4.5, (
            f"kontras tab non-aktif {ratio:.2f}:1 < WCAG AA 4,5:1")
        # konstanta bernama = keputusan a11y yang terlihat (bukan warna ajaib)
        assert theme.C_TAB_IDLE_FG == fg.group(1)
        # latar sekitar (pane) juga harus lolos utk teks yang sama
        ratio2 = _contrast(fg.group(1), theme.C_BG)
        assert ratio2 >= 4.5


# ============================================================
# [D11] Satu konstanta ambang log run
# ============================================================

class TestD11SatuAmbangLog:

    def test_log_run_lines_dipakai_semua_penampang(self):
        """LOG_RUN_LINES = ambang TUNGGAL: cap ctx.log_lines, block-count
        panel log, slice sheet Log Run ekspor (dulu 500/2000/200 beda)."""
        from ui.shared import LOG_RUN_LINES
        assert LOG_RUN_LINES == 2000
        # memori ctx: trim tepat di konstanta
        from ui.state import AppContext
        _qapp()
        ctx = AppContext({})
        for i in range(LOG_RUN_LINES + 500):
            ctx.log(f"baris {i}")
        assert len(ctx.log_lines) == LOG_RUN_LINES
        assert ctx.log_lines[-1] == f"baris {LOG_RUN_LINES + 499}"
        # panel log: maximumBlockCount = konstanta yang sama
        from ui.state import AppContext as _AC
        from ui.view_pipeline import PipelineView
        view = PipelineView(_AC({}))
        try:
            assert view._log.maximumBlockCount() == LOG_RUN_LINES
        finally:
            view.close()
            view.deleteLater()
        # ekspor: slice memakai konstanta (bukan literal 200 lama)
        src_app = (UI / "app.py").read_text(encoding="utf-8")
        assert "[-LOG_RUN_LINES:]" in src_app
        assert "[-200:]" not in src_app
        # state.py: cap lama (literal 500) tak boleh kembali
        src_state = (UI / "state.py").read_text(encoding="utf-8")
        assert "> 500" not in src_state


# ============================================================
# [D16] Tombol Export nonaktif tanpa data
# ============================================================

class TestD16ExportTanpaData:

    def test_export_disabled_awal_dan_tooltip_jujur(self, tmp_path,
                                                     monkeypatch):
        """First-run (ctx.df None) → act_export NONAKTIF (dulu tampak siap
        → klik = dialog 'Belum ada data' — janji kosong) + tooltip
        menyebut syarat aktif."""
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        app.processEvents()
        try:
            assert not win._act_export.isEnabled()
            assert "Aktif setelah pipeline" in win._act_export.toolTip()
        finally:
            win.close()

    def test_enabled_pasca_dataset_dan_disabled_kosong(self, tmp_path,
                                                       monkeypatch):
        """Dataset non-kosong → aktif; dataset KOSONG → tetap nonaktif
        (tak ada yang bisa diekspor) — enable bersyarat, bukan True buta."""
        import ui.app as ap
        monkeypatch.setattr(ap, "followup_path",
                            lambda: tmp_path / "followup.json")
        app = _qapp()
        win = ap.MainWindow()
        app.processEvents()
        try:
            df = pd.DataFrame({
                "NAMA RESTO": ["R1"], "NAMA BARANG": ["I1"],
                "JENIS": ["WASTE"], "TOTAL": [10.0],
                "ANOMALY STATUS": ["Normal"],
            })
            win.ctx.set_dataset(df, {"key_akhir": 31})
            app.processEvents()
            assert win._act_export.isEnabled()
            win.ctx.set_dataset(pd.DataFrame(), {"key_akhir": 31})
            app.processEvents()
            assert not win._act_export.isEnabled()
        finally:
            win.close()


# ============================================================
# [D21] Header log run dedupe + baris Output jujur
# ============================================================

class _PWStub(QThread):
    """Stub PipelineWorker (pola v21311): sinyal kontrak + start no-op —
    progres dikendalikan test lewat _on_progress langsung."""

    progress = Signal(str, float)
    done = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, workbook, key_akhir, parent=None):  # noqa: ARG002
        super().__init__(parent)

    def start(self):  # noqa: D102 — test: jangan jalankan thread
        pass


class TestD21LogRunDedupe:

    def test_awal_run_tanpa_header_ganda(self, monkeypatch):
        """UI tidak lagi menulis header+identitas ganda pra-worker
        (dulu '=== Mulai Pipeline ===' + 'Workbook: …' UI SEBELUM baris
        engine terjemahannya); header run = SATU baris engine; ekor
        '=== Selesai ===' dihapus (engine sudah mencatat DONE)."""
        import ui.view_pipeline as vp
        from ui.state import AppContext
        app = _qapp()
        ctx = AppContext({})
        view = vp.PipelineView(ctx)
        monkeypatch.setattr(
            view, "current_workbook",
            lambda: str(REPO / "sample_workbook.xlsx"))
        monkeypatch.setattr(vp, "PipelineWorker", _PWStub)
        try:
            view._start()
            app.processEvents()
            lines = list(ctx.log_lines)
            assert not any("=== Mulai Pipeline ===" in l for l in lines)
            assert not any(l.startswith("Workbook:") for l in lines), (
                "baris Workbook UI ganda (engine sudah mencatatnya)")
            assert any("stage dianalisa in-memory" in l for l in lines)
            # engine mencatat header (diterjemahkan di batas UI, D18)
            view._on_progress("=== Waste Anomaly Pipeline START ===", 0.0)
            view._on_progress("Workbook: sample_workbook.xlsx", 1.0)
            hdr = [l for l in ctx.log_lines if l.startswith("===")]
            assert hdr == ["=== Pipeline waste dimulai ==="], hdr
            # selesai: TANPA '=== Selesai ===' UI (engine DONE via progress)
            view._on_progress("=== Pipeline DONE ===", 100.0)
            view._on_done({"success": True, "total_rows": 30,
                           "prioritas_count": 2})
            assert not any("=== Selesai ===" in l for l in ctx.log_lines)
            hdr = [l for l in ctx.log_lines if l.startswith("===")]
            assert hdr == ["=== Pipeline waste dimulai ===",
                           "=== Pipeline selesai ==="], hdr
        finally:
            view.close()
            view.deleteLater()

    def test_output_line_jujur_tanpa_path_palsu(self):
        """Engine tanpa output_path (jalur UI) → 'Output: —' (dulu path
        placeholder 'output/Waste_Anomaly_Report.xlsx' yang tak pernah
        ditulis — user mencari file yang tak ada)."""
        from waste_anomaly.pipeline import run_pipeline
        sample = REPO / "sample_workbook.xlsx"
        if not sample.exists():
            import pytest
            pytest.skip("sample_workbook.xlsx tidak ada")
        s = run_pipeline(str(sample), key_akhir=31)
        assert s["success"]
        log = s.get("log", "")
        assert "Output: — (in-memory result" in log
        assert "Output: output" not in log
        assert "Output: /" not in log and "Output: C:" not in log


# ============================================================
# [D30] Tinggi-minimum jendela adaptif
# ============================================================

class TestD30MinimumAdaptif:

    def test_formula_adaptif(self):
        """_adaptive_min_height: layar tinggi → 700 (tak memaksa raksasa),
        layar pendek → turun (netbook 600 → 560 lantai; VM 648 → 568),
        None → 700 (default lama). MainWindow memakai formula (test_v280
        mem-pin jendela nyata — ini unit formula)."""
        from ui.app import _adaptive_min_height as f
        assert f(None) == 700
        assert f(1200) == 700
        assert f(800) == 700
        assert f(728) == 648
        assert f(648) == 568
        assert f(600) == 560      # lantai 560 (netbook)
        assert f(400) == 560      # tak turun lebih jauh dari lantai
