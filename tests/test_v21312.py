"""test_v21312.py — regresi v2.13.12 (Gelombang 3 deep audit:
BANTUAN & TEKS JUJUR). 26 test pengunci 9 klaster fix:

[D8]      Bantuan memuat seksi "Tab Pipeline (tempat semua dimulai)"
          — tab paling operasional dulunya tak terdokumentasi.
[D9]      Fitur 📥 Impor Hasil TL terdokumentasi (seksi Follow Up).
[D19]×2   10 token versi dibersihkan dari Bantuan (fitur-deskriptif)
          + frasa "Ekspor" konsisten. (1 pin lama v2135 "TIDAK lagi
          memfilter" ditulis ulang jujur di file asalnya.)
[D15]×2   PIPELINE_STAGES (18) satu sumber kebenaran + hint/placeholder
          view_pipeline dinamis (dulu hardcode "14 stage").
[D18]×2   _log_id prefix-match + WIRING _on_progress → label status +
          panel log + ctx.log_lines (sheet Log Run) Indonesia.
[C3]×2    set_tooltip_map menimpa global (kontrak model) + wiring
          Scorecard: "HARI TERSANGKA" = JUMLAH baris ber-bukti (bukan
          tanggal), "HARI" weekday = Senin–Minggu, sistemik = tanggal.
[C9]      10/13 kolom tabel utama Scorecard kini berkamus (dulu polos).
[C18]×3   build_column_tooltips(config): override ikut (tooltip+help),
          nilai korup → fallback default engine, Scorecard runtime
          ctx.config (bukan snapshot import-time).
[B9]×2    Menu funnel nilai TERFORMAT (formatter sel tabel) + None/NaN
          ditawarkan "(kosong)" (dropna=False) + UserRole MENTAH utk
          isin (round-trip); varian float-NaN.
[A8]      Funnel 0-baris: menu TETAP terbuka dgn catatan (dulu
          dead-end senyap) + catatan hasil-cari-kosong.
[A9]×2    Tombol ⛶ 3 view membedakan 0-baris-KARENA-FILTER vs
          belum-ada-data (kontrol positif ke Pipeline).
[A11]     Tombol "▸ Tampilkan semua kolom data (N)" mempertahankan
          "(N)" sepanjang siklus buka/tutup.
[A12]     Sel peta hari & tooltip format SAMA (nilai tooltip ⊆ teks
          sel — dulu "7" vs "7,5").
[A13]     _PROMPT pop-up jujur (frasa era panel-inline hilang).
[A14]     Judul seksi peta hari DINAMIS dari kolom hari aktual
          (key_akhir=30 → "1–30", dulu selalu "1–31").
[D13]×2   Ringkasan Run: angka fmt_id + timestamp "12 Jan 2026 18:07"
          + nilai eksotis jujur.
[B17/D14/D17] Pin sumber: fmt_id menggantikan format koma-EN di drill
          banding / tooltip status file / dialog Pratinjau; i18n
          Telusuri / Input Belum Valid / Ekspor.

Fixture pola v2139 (DetailPanel + _full_df) + pola v2136 (view + header
filter) + pola v21311 (df scorecard sintetis).
Re-eksekusi WASTE-G3R: commit asli 8f50b33 hilang pra-push bersama
environment reset — entry worklog WASTE-G3 = spesifikasi replikasi.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
UI = REPO / "ui"

_FRAG = "Lonjakan vs rata-rata harian | Puncak harian vs BOM | Menumpuk di hari terakhir"


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _full_df(n: int = 4, n_days: int = 31) -> pd.DataFrame:
    """Fixture lengkap (pola test_v2139): kolom ringkasan + peer +
    pembanding + hari 1..n_days (n_days=30 utk A14 rentang dinamis)."""
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


def _rec_desimal() -> pd.Series:
    """Record dgn nilai hari BERPECAHAN (7,5) — bukti A12: dulu sel
    membulatkan '8' (fmt_cell(v,0)) tapi tooltip '7,5' (fmt_cell(v,1))."""
    df = _full_df(1)
    df.loc[0, "3"] = 7.5
    return df.iloc[0]


def _panel(rec: pd.Series):
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import DetailPanel
    panel = DetailPanel(AppContext({}))
    panel.show()
    panel.show_record(rec)
    return panel


def _make_view(df: pd.DataFrame | None = None):
    _qapp()
    from ui.state import AppContext
    from ui.view_anomali import AnomaliView
    ctx = AppContext({})
    view = AnomaliView(ctx)
    if df is not None:
        ctx.set_dataset(df, {"key_akhir": 31})
        view._refresh_table()
    return view, ctx


class TestBantuanPipeline:
    def test_seksi_tab_pipeline_lengkap(self):
        """D8: Bantuan memuat seksi 'Tab Pipeline (tempat semua dimulai)'
        dgn alur lengkap — Telusuri/Key Akhir/Threshold+Pratinjau+Simpan/
        Reset/Mulai↔Batalkan/progres+log/Ringkasan Run/Enter (dulu: tab
        paling operasional TAK TERDOKUMENTASIKAN sama sekali)."""
        from ui.app import _HELP_HTML
        assert "Tab Pipeline (tempat semua dimulai)" in _HELP_HTML
        for frasa in ("Telusuri", "Pakai Sample", "Key Akhir (1–31)",
                      "Threshold", "Pratinjau Ambang",
                      "Simpan config.json", "Reset Default",
                      "▶ Mulai Pipeline", "⏹ Batalkan Run",
                      "progres", "log proses", "Ringkasan Run", "Enter"):
            assert frasa in _HELP_HTML, f"Bantuan tanpa '{frasa}' (D8)"
        # Berlaku run BERIKUTNYA — kontrak Simpan config jujur
        assert "BERIKUTNYA" in _HELP_HTML
        assert "gerbang antar-stage" in _HELP_HTML


class TestBantuanImporFileEkspor:
    def test_impor_file_ekspor_terdokumentasi(self):
        """D9 (diperbarui v2.18.7): fitur 📥 Impor File Ekspor —
        pengganti "Impor Hasil TL" yang DIHAPUS atas permintaan user
        ("import ITL itu hapus aja belum kepakai"). Bantuan kini
        mendokumentasikan: memulihkan daftar dari file ekspor, format
        sama persis, otomatis di-centang kembali."""
        from ui.app import _HELP_HTML
        assert "Impor File Ekspor" in _HELP_HTML
        # efek: baris otomatis di-centang kembali
        assert "otomatis di-centang kembali" in _HELP_HTML
        # format sama persis + aman walau di-sort/di-filter di Excel
        assert "format sama persis" in _HELP_HTML
        assert "di-sort" in _HELP_HTML and "di-filter" in _HELP_HTML
        # jejak fitur LAMA (Impor Hasil TL) bersih total
        assert "Impor Hasil TL" not in _HELP_HTML
        assert "followup_resolved.json" not in _HELP_HTML
        assert "STATUS TL" not in _HELP_HTML


class TestBantuanTanpaTokenVersi:
    def test_help_bersih_dari_token_versi(self):
        """D19: 10 token versi (v2.9.0..v2.13.9) dibersihkan — Bantuan =
        panduan CARA PAKAI, bukan changelog mini (user tak peduli versi
        mana menambah apa; angka versi membingungkan & cepat basi)."""
        from ui.app import _HELP_HTML
        tokens = re.findall(r"v2\.\d+\.\d+", _HELP_HTML)
        assert not tokens, f"Bantuan masih memuat token versi: {tokens}"

    def test_help_fitur_deskriptif_dan_ekspor(self):
        """D19+D17: token versi diganti frasa fitur-deskriptif; tombol
        Export kini '💾 Ekspor Excel' di seluruh teks bantuan (i18n)."""
        from ui.app import _HELP_HTML
        for frasa in ("pop-up detail ringkas", "Angka minus otomatis MERAH",
                      "Semua filter lewat funnel di judul kolom",
                      "bisa digulir", "💾 Ekspor Excel", "Ekspor</b>"):
            assert frasa in _HELP_HTML, f"Bantuan tanpa '{frasa}' (D19)"
        assert "💾 Export Excel" not in _HELP_HTML


# ============================================================
# [D15] PIPELINE_STAGES — satu sumber kebenaran jumlah stage
# ============================================================

class TestPipelineStages:
    def test_18_stage_urutan_eksekusi(self):
        """D15: PIPELINE_STAGES = 18 stage (stage_01..14 + 12.5/12.6 +
        annotate_day_evidence + annotate_profile) — urutan EKSEKUSI;
        PIPELINE_N_STAGES = len() (dulu UI hardcode '14 stage' yang
        basi sejak v2.9.0 menambah Stage 15)."""
        from waste_anomaly.pipeline import (
            PIPELINE_N_STAGES,
            PIPELINE_STAGES,
        )
        assert PIPELINE_N_STAGES == 18, PIPELINE_N_STAGES
        assert len(PIPELINE_STAGES) == PIPELINE_N_STAGES
        assert PIPELINE_STAGES[0] == "Stage 1 — Source & cleanup"
        assert PIPELINE_STAGES[7] == "Stage 8 — Merge"
        assert "Stage 12.5 — Waste Fingerprint + Sistematik Flag" \
            in PIPELINE_STAGES
        assert "Stage 12.6 — Quadrant Classification" in PIPELINE_STAGES
        assert PIPELINE_STAGES[-2] == "Stage 15 — Bukti hari tersangka"
        assert PIPELINE_STAGES[-1] == "Stage 15b — Profil baris + kelebihan"

    def test_hint_dan_placeholder_dinamis(self):
        """D15: hint Parameter + placeholder log memakai angka DINAMIS
        dari PIPELINE_N_STAGES ('18 stage') — sumber berubah → UI ikut
        tanpa edit manual (dulu hardcode '14 stage')."""
        from ui.state import AppContext
        from ui.view_pipeline import PipelineView
        app = _qapp()
        view = PipelineView(AppContext({}))
        hint = view._page.findChildren(type(view._lbl_status))
        texts = [w.text() for w in hint]
        assert any("18 stage" in t for t in texts), texts
        assert "18 stage" in view._log.placeholderText()
        src = (UI / "view_pipeline.py").read_text(encoding="utf-8")
        # literal UI hardcode LAMA hilang (docstring sejarah tak dihitung)
        assert "14 stage pipeline dijalankan" not in src
        assert "Log proses (14 stage)" not in src
        assert "PIPELINE_N_STAGES} stage " in src, (
            "hint harus dibangun dari PIPELINE_N_STAGES (D15)")


# ============================================================
# [D18] Terjemahan log stage DI BATAS UI
# ============================================================

class TestLogId:
    def test_prefix_match_dan_passthrough(self):
        """D18: _log_id menerjemahkan awalan baris log EN engine
        (prefix-match — sisa baris dinamis diteruskan); baris tak
        dikenal lolos APA ADANYA; baris yang memang sudah Indonesia
        (stage 11/15/15b) tidak diubah; 'Stage 1' tak menabrak
        'Stage 12.5'/'Stage 15b' (kunci = label penuh)."""
        from ui.view_pipeline import _log_id
        assert _log_id(
            "Stage 2 — Per-row daily statistics ..."
        ) == "Tahap 2 — statistik harian per baris ..."
        assert _log_id(
            "Stage 12.5 — Waste Fingerprint + Sistematik Flag ..."
        ) == "Tahap 12.5 — fingerprint waste + penanda sistemik ..."
        assert _log_id("Loading BOM ...") == "Memuat BOM ..."
        assert _log_id("=== Pipeline DONE ===") == "=== Pipeline selesai ==="
        # stage yang SUDAH Indonesia — tak di-map, tetap apa adanya
        assert _log_id(
            "Stage 11 — 12 sinyal anomali ..."
        ) == "Stage 11 — 12 sinyal anomali ..."
        assert _log_id(
            "Stage 15b — Profil baris + kelebihan ..."
        ) == "Stage 15b — Profil baris + kelebihan ..."
        # baris EN baru yang tak di-map → jujur apa adanya
        assert _log_id("Some future line") == "Some future line"
        # prefix-match: angka dinamis di ekor tetap utuh
        out = _log_id("[loader] BOM loaded: 54 rows")
        assert out == "[loader] BOM termuat: 54 rows"

    def test_wiring_on_progress_log_indonesia(self):
        """D18 (WIRING): _on_progress menerjemahkan SATU KALI di batas
        UI → label status + panel log + ctx.log_lines (yang ikut
        diekspor ke sheet Log Run) semuanya Indonesia; baris ENGINE
        (pipeline._log) tetap menulis EN (diterjemahkan hanya di UI)."""
        from ui.state import AppContext
        from ui.view_pipeline import PipelineView
        app = _qapp()
        ctx = AppContext({})
        view = PipelineView(ctx)
        before = len(ctx.log_lines)
        view._on_progress("Stage 3 — Reason summary ...", 30)
        app.processEvents()
        assert ctx.log_lines[-1] == \
            "Tahap 3 — ringkasan alasan ...", ctx.log_lines[-1]
        assert view._lbl_status.text() == "Tahap 3 — ringkasan alasan ..."
        assert "Tahap 3 — ringkasan alasan" in view._log.toPlainText()
        assert len(ctx.log_lines) == before + 1  # sekali saja (bukan 2×)
        assert view._progress.value() == 30


# ============================================================
# [C3/C9/C18] Kamus tooltip per-view + angka ambang dari config
# ============================================================

class TestTooltipPerView:
    def test_set_tooltip_map_menimpa_global(self):
        """C3 (kontrak model): set_tooltip_map = kamus PER-VIEW yang
        MENIMPA kamus global — hanya ToolTipRole header; kolom tanpa
        entri per-view jatuh ke kamus global; kontrak lain (alias
        judul set_header_map) tak tersentuh."""
        from PySide6.QtCore import Qt
        from ui.models import COLUMN_TOOLTIPS, PandasTableModel
        df = pd.DataFrame({"HARI": ["Senin"], "BULAN LALU": [1.0]})
        m = PandasTableModel(df)
        # tanpa peta per-view → kamus global (tanggal 1-31)
        tip_global = m.headerData(0, Qt.Horizontal, Qt.ToolTipRole)
        assert "Tanggal" in str(tip_global)
        m.set_tooltip_map({"HARI": "Hari KALENDER (Senin–Minggu)."})
        tip_view = m.headerData(0, Qt.Horizontal, Qt.ToolTipRole)
        assert "Senin" in str(tip_view) and str(tip_view) != str(tip_global)
        # kolom lain tetap kamus global
        assert m.headerData(1, Qt.Horizontal, Qt.ToolTipRole) \
            == COLUMN_TOOLTIPS["BULAN LALU"]
        # alias judul tak tersentuh oleh peta tooltip
        m.set_header_map({"HARI": "DOW"})
        assert m.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "DOW"
        assert "Senin" in str(
            m.headerData(0, Qt.Horizontal, Qt.ToolTipRole))
        # None/{} = kembali ke kamus global
        m.set_tooltip_map(None)
        assert m.headerData(0, Qt.Horizontal, Qt.ToolTipRole) == tip_global


class TestAngkaAmbangDariConfig:
    def test_config_override_tooltip_dan_help_ikut(self):
        """C18: build_column_tooltips(config) + _build_help_html(config)
        — angka ambang mengikuti config yang DIBERIKAN (user mengubah
        threshold → tooltip/help ikut; dulu hardcode '≥ 8'/'≥ 50%'
        bohong diam-diam)."""
        from ui.app import _build_help_html
        from ui.models import build_column_tooltips
        cfg = {"thresholds": {"STATUS_PRIORITAS": 12,
                              "TH_HARI_PEER_RATIO": 7.5,
                              "TH_MAX_SHARE_WARN": 0.65}}
        tips = build_column_tooltips(cfg)
        assert "≥ 12" in tips["ANOMALY STATUS"]
        assert "≥ 7,5×" in tips["RASIO VS CABANG LAIN"]
        assert "≥ 65%" in tips["MAX SHARE"]
        help_html = _build_help_html(cfg)
        assert "≥ 65% waste sebulan" in help_html
        # default (tanpa override) tetap angka engine
        assert "≥ 50% waste sebulan" in _build_help_html()

    def test_config_korup_fallback_default_engine(self):
        """C18: nilai korup (string tak terurai / None / NaN) →
        FALLBACK default engine (bukan teks lama menempel / crash)."""
        from ui.models import build_column_tooltips
        cfg = {"thresholds": {
            "STATUS_PRIORITAS": "korup", "TH_SPIKE": None,
            "TH_MAX_SHARE_WARN": float("nan"),
            "STATUS_POTENSI": 6,  # valid → dipakai
        }}
        tips = build_column_tooltips(cfg)
        assert "≥ 8" in tips["ANOMALY STATUS"]       # default 8
        assert "≥ 3×" in tips["MAX / AVG"]           # default 3
        assert "≥ 50%" in tips["MAX SHARE"]          # default 0.5
        assert "≥ 6" in tips["ANOMALY STATUS"]       # valid ikut
        # None seluruhnya (bukan dict thresholds)
        assert "≥ 8" in build_column_tooltips(None)["ANOMALY STATUS"]


# ============================================================
# [B9] Menu funnel — nilai TERFORMAT + "(kosong)" + UserRole mentah
# ============================================================

class TestMenuFunnelTerformat:
    def _menu(self, df: pd.DataFrame, col: str):
        from ui.widgets import DataTable
        app = _qapp()
        t = DataTable()
        t.set_dataframe(df)
        applied = []
        t.setup_header_filters(
            None, lambda c, k, vals: applied.append((c, k, vals)),
            None, all_cols=True, skip=())
        hdr = t.horizontalHeader()
        logical = list(df.columns).index(col)
        hdr._open_menu(logical)
        assert hdr._menu is not None, "menu funnel tak terbuka"
        return hdr._menu, applied

    def test_nilai_terformat_userrole_mentah_none_ditawarkan(self):
        """B9: nilai menu = nilai TERFORMAT (formatter sel tabel kolom
        itu — '+28,6%' utk Delta %, bukan float mentah '28.571' di
        samping sel tabel yang terformat); None DITAWARKAN sbg
        '(kosong)' (dropna=False — dulu dibuang senyap); UserRole =
        nilai MENTAH utk isin (round-trip)."""
        df = pd.DataFrame({
            "Perubahan %": [28.571, -12.0],
            "KETERANGAN": ["a", "b"],
        })
        menu, _applied = self._menu(df, "Perubahan %")
        texts = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        joined = " | ".join(texts)
        assert "+28,6%" in joined, texts
        assert "-12,0%" in joined, texts
        assert "28.571" not in joined, (
            "nilai float mentah masih bocor ke menu (audit B9)")
        # UserRole = nilai MENTAH (round-trip isin)
        vals = [menu._lw.item(i).data(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt
            .ItemDataRole.UserRole) for i in range(menu._lw.count())]
        assert 28.571 in vals and -12.0 in vals, vals

    def test_nan_ditawarkan_dan_isin_roundtrip(self):
        """B9 (varian float-NaN): kolom numerik dgn NaN → '(kosong)'
        DITAWARKAN (value_counts(dropna=False)); UserRole NaN mentah;
        memilih HANYA nilai kosong → list [nan] → isin cocok baris NaN
        (round-trip — baris kosong bisa difilter eksplisit). NB: kolom
        Delta % sengaja TIDAK dipakai — formatter selnya memetakan NaN
        ke 'BARU' (konvensi perubahan), menu mengikuti formatter itu
        (nilai menu ≡ nilai sel — inti B9)."""
        df = pd.DataFrame({
            "TOTAL": [np.nan, 1.0, 5.0],
            "KETERANGAN": ["a", "b", "c"],
        })
        menu, applied = self._menu(df, "TOTAL")
        texts = [menu._lw.item(i).text()
                 for i in range(menu._lw.count())]
        assert any("(kosong)" in t for t in texts), texts
        # hanya NaN tercentang → apply([nan])
        menu._checked = {v: bool(v != v) for v in menu._counts}
        menu._apply_now()
        col, _key, vals = applied[-1]
        assert col == "TOTAL"
        assert vals is not None and len(vals) == 1, vals
        nan_val = vals[0]
        assert isinstance(nan_val, float) and nan_val != nan_val, (
            "UserRole harus NaN MENTAH (bukan string '(kosong)')")
        mask = pd.Series([np.nan, 1.0]).isin([nan_val])
        assert bool(mask.iloc[0]) and not bool(mask.iloc[1]), (
            "round-trip isin gagal — nilai kosong tak bisa difilter")


# ============================================================
# [A8] Funnel 0-baris — bukan dead-end
# ============================================================

class TestFunnelNolBaris:
    def test_menu_tetap_terbuka_berpesan(self):
        """A8: kolom dgn 0 nilai lolos (semua baris tersaring filter
        lain) → menu TETAP dibuka dgn catatan arahan (dulu: klik funnel
        tanpa umpan balik = dead-end senyap); hasil cari 0 → catatan
        coba kata kunci lain (bukan daftar kosong hening)."""
        from ui.widgets import DataTable
        app = _qapp()
        df = pd.DataFrame({"KETERANGAN": ["a"], "PERUBAHAN": ["x"]})
        t = DataTable()
        # tabel 0-baris (kolom utuh) = semua nilai tersaring filter lain
        t.set_dataframe(df.iloc[:0])
        t.setup_header_filters(None, lambda *a: None, None,
                               all_cols=True, skip=())
        hdr = t.horizontalHeader()
        hdr._open_menu(0)
        assert hdr._menu is not None, (
            "menu harus tetap terbuka saat 0 nilai (audit A8)")
        texts = [hdr._menu._lw.item(i).text()
                 for i in range(hdr._menu._lw.count())]
        assert any("0 baris cocok" in t2 for t2 in texts), texts
        assert any("lepas filter" in t2 for t2 in texts), texts
        # hasil cari kosong (counts NON-kosong) → catatan coba kata lain
        t2w = DataTable()
        t2w.set_dataframe(df)
        t2w.setup_header_filters(None, lambda *a: None, None,
                                 all_cols=True, skip=())
        hdr2 = t2w.horizontalHeader()
        hdr2._open_menu(0)
        hdr2._menu._populate("zzz-tak-ada")
        texts2 = [hdr2._menu._lw.item(i).text()
                  for i in range(hdr2._menu._lw.count())]
        assert any("0 nilai cocok" in t2 for t2 in texts2), texts2


# ============================================================
# [A9] Tombol ⛶ — 0-baris-karena-filter ≠ belum-ada-data
# ============================================================

class TestFullscreenNolBaris:
    def test_nol_baris_karena_filter_menyebut_filter(self):
        """A9: dataset ADA tapi tabel 0 baris (funnel/ambang skor
        menyaring semua) → pesan ⛶ menyebut FILTER + cara melepasnya
        (dulu satu pesan 'belum ada data' utk dua situasi beda —
        menyesatkan: datanya ada!)."""
        view, ctx = _make_view(_full_df())
        app = _qapp()
        captured: list[str] = []
        ctx.status.connect(lambda t, _k: captured.append(t))
        # simulasikan semua baris tersaring: tabel dikosongkan TANPA
        # melepas dataset (persis keadaan funnel menyaring semua).
        view._table.set_dataframe(view._table.model().dataframe.iloc[:0])
        assert view._table.model().rowCount() == 0
        assert ctx.df is not None and not ctx.df.empty
        view._on_fullscreen()
        assert captured and "filter" in captured[-1].lower(), captured
        app.processEvents()

    def test_tanpa_dataset_arahan_pipeline(self):
        """A9 (kontrol positif): TANPA dataset → arahan ke Pipeline
        tetap (bukan pesan filter yang salah arah)."""
        view, ctx = _make_view(None)
        assert ctx.df is None
        assert view._table.model().rowCount() == 0
        captured: list[str] = []
        ctx.status.connect(lambda t, _k: captured.append(t))
        view._on_fullscreen()
        assert captured
        status = captured[-1]
        assert "Belum ada data" in status and "Pipeline" in status, status


# ============================================================
# [A11] Tombol kolom lengkap — "(N)" bertahan sepanjang siklus
# ============================================================

class TestTombolKolomLengkap:
    def test_angka_n_utuh_pasca_siklus(self):
        """A11: '▸ Tampilkan semua kolom data (N)' mempertahankan (N)
        sepanjang siklus buka/tutup (dulu angka hilang pasca siklus
        pertama — toggle kedua menulis teks tanpa angka)."""
        panel = _panel(_full_df(1).iloc[0])
        btn = panel._more_btn
        assert btn is not None
        n = panel._n_full
        assert n > 0 and f"({n})" in btn.text(), btn.text()
        panel._toggle_full()  # buka
        assert "Sembunyikan" in btn.text() and f"({n})" in btn.text(), (
            "angka hilang saat DIBUKA (audit A11)")
        panel._toggle_full()  # tutup
        assert "Tampilkan semua kolom data" in btn.text()
        assert f"({n})" in btn.text(), (
            "angka hilang saat DITUTUP kembali (audit A11)")
        panel._toggle_full()  # buka lagi — siklus kedua
        assert f"({n})" in btn.text()


# ============================================================
# [A12] Peta hari — sel & tooltip format sama
# ============================================================

class TestPetaHariDesimal:
    def test_nilai_tooltip_subset_teks_sel(self):
        """A12: sel peta hari & tooltip MEMAKAI format sama (fmt_cell
        default 2-desimal) — nilai di tooltip sesuai nilai sel (dulu sel
        read-only membulatkan '8' (fmt_cell(v,0)) vs tooltip '7,5'
        (fmt_cell(v,1)) — dua angka beda utk data sama di dua tempat
        bersebelahan). v2.16.0: peta hari kini EDITABLE (QDoubleSpinBox) —
        nilai spinbox = nilai asli (presisi penuh, decimals=2), tooltip
        'Nilai asli: X' konsisten dgn nilai spinbox."""
        from PySide6.QtWidgets import QDoubleSpinBox
        panel = _panel(_rec_desimal())
        cells = [c for c in panel._content.findChildren(QDoubleSpinBox)
                 if c.toolTip().startswith("Hari ")]
        assert cells, "sel peta hari tak ditemukan"
        # Hari 3 = 7,5 — spinbox value HARUS 7.5 (presisi penuh, BUKAN
        # membulatkan ke 8 seperti _day_map read-only dulu — bug A12).
        day3 = [c for c in cells if "Hari 3" in c.toolTip()]
        assert day3, "sel hari 3 tak ditemukan"
        assert abs(day3[0].value() - 7.5) < 0.01, day3[0].value()
        # Tooltip menyebut 'Nilai asli: 7,50' (fmt_cell 2-desimal) —
        # konsisten dgn nilai spinbox (7.5 ≈ 7,50).
        assert "7,50" in day3[0].toolTip(), day3[0].toolTip()
        # Semua sel: nilai spinbox non-negatif (range 0..1e9, anti absurd).
        for c in cells:
            assert 0.0 <= c.value() <= 1e9, c.value()


# ============================================================
# [A13] _PROMPT pop-up jujur
# ============================================================

class TestPromptPopUp:
    def test_prompt_tanpa_frasa_era_panel_inline(self):
        """A13: _PROMPT tak lagi berkata 'menampilkan detailnya DI SINI'
        (era panel-inline — panel sudah jadi POP-UP sejak v2.8.1);
        mendeskripsikan isi pop-up + footer aksi yang selalu terlihat."""
        from ui.view_anomali import DetailPanel
        prompt = DetailPanel._PROMPT
        assert "di sini" not in prompt.lower(), prompt
        assert "pop-up" in prompt.lower(), prompt
        for isi in ("ringkasan", "sinyal", "peta"):
            assert isi in prompt.lower(), prompt
        assert "Follow Up" in prompt  # footer aksi disebut


# ============================================================
# [A14] Judul seksi peta hari dinamis
# ============================================================

class TestPetaHariRentangDinamis:
    def test_rentang_dari_kolom_hari_aktual(self):
        """A14: judul seksi peta hari dari rentang kolom hari yang
        BENAR-BENAR ada di record (n_days=30 → '1–30'; dulu SELALU
        '1–31' — judul mendiskripsikan kolom yang tak ada)."""
        from PySide6.QtWidgets import QLabel
        rec = _full_df(1, n_days=30).iloc[0]
        day_cols = [c for c in rec.index if c.isdigit()]
        assert day_cols and day_cols[-1] == "30", "premis: hari 1..30"
        panel = _panel(rec)
        titles = [l.text() for l in panel._content.findChildren(QLabel)
                  if l.text().startswith("Nilai per hari")]
        assert titles, "judul seksi peta hari tak ditemukan"
        assert "Nilai per hari (1–30)" in titles[0], titles[0]
        assert "(1–31)" not in titles[0], titles[0]


# ============================================================
# [D13] Ringkasan Run — fmt_id + timestamp Indonesia
# ============================================================

class TestRingkasanRun:
    def test_angka_fmt_id_dan_waktu_id(self):
        """D13: angka Ringkasan Run fmt_id ('25.901', bukan '25,901'
        koma-EN) + timestamp '12 Jan 2026 18:07' (dulu ISO mentah
        '2026-01-12T18:07:33')."""
        from ui.state import AppContext
        from ui.view_pipeline import PipelineView
        app = _qapp()
        view = PipelineView(AppContext({}))
        view._render_summary({
            "total_rows": 25901, "anomali_count": 399,
            "prioritas_count": 41, "potensi_count": 358,
            "review_count": 398, "normal_count": 25104,
            "cabang_count": 58, "item_count": 933,
            "key_akhir": 31,
            "timestamp": "2026-01-12T18:07:33.123456",
        })
        plain = view._summary.toPlainText()
        assert "25.901" in plain, plain
        assert "25,901" not in plain, "koma-EN masih bocor (D13)"
        assert "12 Jan 2026 18:07" in plain, plain
        assert "2026-01-12T" not in plain, plain

    def test_fmt_ts_id_nilai_eksotis_jujur(self):
        """D13: nilai eksotis (teks aneh / kosong / None) → str apa
        adanya / '—' — jujur, bukan crash & bukan tebakan."""
        from ui.view_pipeline import _fmt_ts_id
        assert _fmt_ts_id("bukan-tanggal") == "bukan-tanggal"
        assert _fmt_ts_id("") == "—"
        assert _fmt_ts_id(None) == "—"
        assert _fmt_ts_id("2026-07-09T05:03:00") == "9 Jul 2026 05:03"


# ============================================================
# [B17/D14/D17] Pin sumber — fmt_id & i18n
# ============================================================

class TestPinSumber:
    def test_fmt_id_dan_i18n_menggantikan_koma_en_dan_en(self):
        """B17+D14: format koma-EN (':,') DIGANTI fmt_id di subjudul
        drill hari + tooltip status file banding + dialog Pratinjau.
        D17: 'Browse…' → 'Telusuri…', 'Input Error' → 'Input Belum
        Valid', 'Export' user-facing → 'Ekspor' (nama file output
        tetap EN)."""
        src_vp = (UI / "view_periode.py").read_text(encoding="utf-8")
        assert "tot_a:,.0f" not in src_vp, "subjudul drill masih koma-EN"
        assert "fmt_id(tot_a)" in src_vp
        assert "rows_kept', 0):," not in src_vp, (
            "tooltip status file masih koma-EN")
        src_vpl = (UI / "view_pipeline.py").read_text(encoding="utf-8")
        assert "{before[s]:>7,}" not in src_vpl, (
            "dialog pratinjau masih koma-EN")
        assert "{after[s]:>7,}" not in src_vpl
        assert "fmt_id(before[s])" in src_vpl
        assert 'QPushButton("Browse' not in src_vpl, "Browse masih ada"
        assert 'QPushButton("Telusuri' in src_vpl
        assert 'critical(self, "Input Error"' not in src_vpl
        assert 'critical(self, "Input Belum Valid"' in src_vpl
        src_app = (UI / "app.py").read_text(encoding="utf-8")
        # v2.17.0 rombak P0-E: tombol Ekspor kini pakai ikon vektor
        # (make_qicon("save")) + teks "Ekspor Excel" (tanpa emoji 💾).
        assert 'make_qicon("save"' in src_app
        assert '"Ekspor Excel"' in src_app
        assert '"Export Selesai"' not in src_app
        assert '"Ekspor Selesai"' in src_app
        src_fu = (UI / "view_followup.py").read_text(encoding="utf-8")
        assert '"Export Selesai"' not in src_fu
        assert '"Ekspor Selesai"' in src_fu
        assert '"Export Gagal"' not in src_fu
        # nama file output TETAP EN (kontrak file)
        assert "Waste_FollowUp_" in src_fu
        assert "Waste_Anomaly_Report.xlsx" in (
            REPO / "waste_anomaly" / "config.json").read_text(
                encoding="utf-8")


# ============================================================
# CATATAN VERSI: pin 2.13.12 dilakukan di situs test LAMA (pola
# G1R/G2R — test_v2136 ×6 baris + test_v2102 + test_v2139 +
# test_v270_wave4 — test_v21311 tak memegang assert versi), TIDAK di
# file ini, supaya jumlah test baru tepat 26 (973 + 26 = 999 —
# kontrak worklog WASTE-G3).
# ============================================================
