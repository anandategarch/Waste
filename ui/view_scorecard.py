"""view_scorecard.py — view 'Scorecard Cabang' (v2.13.1).

Menjawab pertanyaan audit level manajemen (riset R1): "kunjungi cabang
mana dulu, bawa bukti apa, berapa yang bisa dihemat?" — satu halaman
per cabang + kartu pendukung. Semua bahan dari waste_anomaly/insights.py
(vektor, dihitung sekali per data/pembanding lalu di-memo).

UI (istilah awam — permintaan user):
- KPI: POTENSI HEMAT (Σ kelebihan vs tipikal) · INTENSITAS TIPIKAL
  (median waste/BOM) · CABANG #1 · HARI SISTEMIK.
- Tabel utama: Scorecard per cabang (RANK = urutan kunjungan audit;
  klik-2× = rincian cabang: top kerugian + item tak input + profil
  alasan). ⤢ Perbesar Tabel + ⛶ Layar Penuh (pola tab lain).
- Kartu "Top Kerugian vs Tipikal" (money_ranking — ranking uang,
  SATUAN tampil jujur).
- Kartu "Pola Hari Kalender" (Senin..Minggu asli dari label bulan file
  — fix proxy mod-7) + kartu "Hari Sistemik" (hari naik serentak di
  banyak cabang = masalah bersama; 0 = semua lonjakan lokal).

Semua tabel pakai DataTable biasa (≤ 25 baris — render milidetik,
aman anti-lambat) + funnel di judul kolom (SEMUA kolom — filter lokal
tampilan, pola v2.12.4).
"""
from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QFrame,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.data_quality import run_checks
from waste_anomaly.insights import (
    branch_trend,
    coverage_report,
    money_ranking,
    resto_intensity,
    scorecard,
    systemic_days,
    weekday_real,
)
from waste_anomaly.period_history import detect_month_label
from waste_anomaly.priority import reason_share

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, DataTable, KpiCard, WLabel, busy_feedback

# Kolom tabel utama = SCORECARD_COLS (insights) — urutan PERSIS.
# (v2.13.8 gel-C: konstanta SC_COLS lokal DIHAPUS — tak pernah dirujuk;
# insights.SCORECARD_COLS adalah satu sumber kebenaran.)


class ScorecardView(QWidget):
    """View 'Scorecard Cabang': urutan kunjungan audit + kartu pendukung."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        # v2.13.6 (audit R1): konten scorecard ±1.270px tinggi-min — tak
        # mungkin dipadatkan ke ruang halaman tab (±582px di 1366×768;
        # terukur offscreen). Bungkus QScrollArea supaya kartu bawah
        # (Tren Bulanan / Hari Sistemik / Kualitas Data) tetap TERJANGKAU
        # lewat gulir di layar kecil. ⤢/⛶ & reparent tabel tak terdampak
        # (tabel tetap anak kartu di halaman ini); tabel ≤ 200 baris punya
        # scrollbar sendiri — gulir roda di atas tabel tetap milik tabel.
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        self._page = page
        scroll.setWidget(page)
        lay.addWidget(scroll)
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(8)

        # ---- KPI row (4 kartu) ---------------------------------------
        kpi_row = QWidget(self)
        kl = QHBoxLayout(kpi_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(8)
        self._kpi_hemat = KpiCard(
            "POTENSI HEMAT", "#dc2626",
            tooltip="Perkiraan waste yang bisa dihilangkan bila semua "
                    "cabang bermain di intensitas TIPIKAL (median) — "
                    "Σ (intensitas cabang − tipikal) × BOM cabang, hanya "
                    "yang di atas tipikal. Satuan campuran (GR/PCS) — "
                    "tiap baris dibandingkan BOM satuannya sendiri.")
        self._kpi_intens = KpiCard(
            "INTENSITAS TIPIKAL", "#0f172a",
            tooltip="Median waste ÷ penjualan (BOM) antar cabang, dalam "
                    "persen. Intensitas cabang di atas angka ini = "
                    "kandidat perbaikan proses.")
        self._kpi_top = KpiCard(
            "CABANG #1", "#ea580c",
            tooltip="Cabang dengan potensi hemat terbesar (kolom KELEBIHAN "
                    "tabel utama) — kandidat kunjungan audit pertama.")
        self._kpi_sistemik = KpiCard(
            "HARI SISTEMIK", "#7c3aed",
            tooltip="Hari yang waste-nya naik di BANYAK cabang sekaligus "
                    "(≥ 3 cabang atau 15% cabang, ≥ 2× median hariannya "
                    "sendiri) — penanda masalah BERSAMA (pengiriman / hari "
                    "besar / sistem POS), bukan kecurigaan satu cabang. "
                    "0 = semua lonjakan lokal.")
        for card in (self._kpi_hemat, self._kpi_intens, self._kpi_top,
                     self._kpi_sistemik):
            kl.addWidget(card)
        kl.addStretch(1)
        page_lay.addWidget(kpi_row)
        self._kpi_row = kpi_row

        # ---- Kartu utama: tabel scorecard -----------------------------
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        head = QWidget(card)
        hcl = QHBoxLayout(head)
        hcl.setContentsMargins(0, 0, 0, 0)
        hcl.setSpacing(8)
        title = WLabel(
            "🏢 Scorecard Cabang — urutan kunjungan audit (klik 2× = "
            "rincian cabang)", head)
        title.setObjectName("cardTitle")
        hcl.addWidget(title)
        hcl.addStretch(1)
        self._btn_expand = QPushButton("⤢ Perbesar Tabel", head)
        self._btn_expand.setToolTip(
            "Sembunyikan KPI & kartu pendukung supaya tabel memakai "
            "seluruh tinggi tampilan. Klik lagi untuk mengembalikan.")
        self._btn_expand.clicked.connect(self._on_expand)
        hcl.addWidget(self._btn_expand)
        self._btn_full = QPushButton("⛶ Layar Penuh", head)
        self._btn_full.setToolTip(
            "Buka tabel ini di jendela layar penuh (Esc = kembali).\n"
            "Sort / funnel / klik-2× tetap berfungsi penuh.")
        self._btn_full.clicked.connect(self._on_fullscreen)
        hcl.addWidget(self._btn_full)
        cl.addWidget(head)
        self._head_row = head

        self._lbl_count = WLabel(
            "Jalankan pipeline dulu (tab Pipeline) — scorecard menunggu "
            "data bulan berjalan.", card)
        self._lbl_count.setObjectName("hint")
        cl.addWidget(self._lbl_count)

        self._table = DataTable(card)
        self._table.setMinimumHeight(220)
        self._table.setup_header_filters(
            {}, self._page_apply("scorecard"), self._page_state("scorecard"),
            all_cols=True, skip=())
        self._table.double_clicked.connect(self._on_double)
        cl.addWidget(self._table, 1)
        self._tcl = cl
        page_lay.addWidget(card, 3)
        self._main_card = card

        # ---- Baris kartu pendukung: kerugian + hari -------------------
        row2 = QWidget(self)
        rl = QHBoxLayout(row2)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        money = Card(row2)
        ml = QVBoxLayout(money)
        ml.setContentsMargins(12, 10, 12, 10)
        ml.setSpacing(6)
        mt = WLabel("💰 Top Kerugian vs Tipikal — per baris (ranking uang)",
                    money)
        mt.setObjectName("cardTitle")
        mt.setToolTip(
            "Baris teratas berdasar KELEBIHAN (TOTAL − tipikal/median "
            "cabang lain, hanya cabang yang memang ber-waste; peer < 3 = "
            "tak dihitung). SATUAN tampil — campuran GR/PCS jujur "
            "(funnel SATUAN bisa memilah).")
        ml.addWidget(mt)
        self._lbl_money = WLabel("", money)
        self._lbl_money.setObjectName("hint")
        ml.addWidget(self._lbl_money)
        self._money_table = DataTable(money)
        self._money_table.setMinimumHeight(140)
        self._money_table.setup_header_filters(
            {}, self._page_apply("money"), self._page_state("money"),
            all_cols=True, skip=())
        ml.addWidget(self._money_table, 1)
        rl.addWidget(money, 3)
        self._money_card = money

        side = QWidget(row2)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)

        wcard = Card(side)
        wl = QVBoxLayout(wcard)
        wl.setContentsMargins(12, 10, 12, 10)
        wl.setSpacing(6)
        wt = WLabel("📅 Pola Hari Kalender (Senin–Minggu)", wcard)
        wt.setObjectName("cardTitle")
        wt.setToolTip(
            "Total waste per HARI KALENDER asli — dibaca dari nama bulan "
            "file (mis. 'SEPTEMBER_2026'). Mengganti proxy hari%7 yang "
            "tak sebanding antar bulan (1 Agustus 2026 = Sabtu, "
            "1 September 2026 = Selasa).")
        wl.addWidget(wt)
        self._lbl_weekday = WLabel("", wcard)
        self._lbl_weekday.setObjectName("hint")
        wl.addWidget(self._lbl_weekday)
        self._weekday_table = DataTable(wcard)
        self._weekday_table.setMinimumHeight(120)
        wl.addWidget(self._weekday_table, 1)
        sl.addWidget(wcard, 1)

        dqcard = Card(side)
        dql = QVBoxLayout(dqcard)
        dql.setContentsMargins(12, 10, 12, 10)
        dql.setSpacing(6)
        dqt = WLabel("🧪 Kualitas Data — pemeriksaan otomatis", dqcard)
        dqt.setObjectName("cardTitle")
        dqt.setToolTip(
            "Hasil pemeriksaan data quality (dulu hanya di export/Excel).\n"
            "warning = patut dibersihkan (satuan kembar, kapitalisasi beda);\n"
            "info = konteks normal (baris placeholder, Benford).")
        dql.addWidget(dqt)
        self._lbl_dq = WLabel("", dqcard)
        self._lbl_dq.setObjectName("hint")
        dql.addWidget(self._lbl_dq)
        self._dq_table = DataTable(dqcard)
        self._dq_table.setMinimumHeight(80)
        self._dq_table.setup_header_filters(
            {}, self._page_apply("dq"), self._page_state("dq"),
            all_cols=True, skip=())
        dql.addWidget(self._dq_table, 1)
        sl.addWidget(dqcard, 1)

        scard = Card(side)
        scl = QVBoxLayout(scard)
        scl.setContentsMargins(12, 10, 12, 10)
        scl.setSpacing(6)
        st = WLabel("🔗 Hari Sistemik — naik serentak di banyak cabang",
                    scard)
        st.setObjectName("cardTitle")
        st.setToolTip(
            "Hari dengan ≥ 3 cabang (atau 15%) mengalami waste ≥ 2× "
            "median hariannya sendiri → kemungkinan masalah BERSAMA "
            "(pengiriman / hari besar / POS), bukan kecurigaan satu "
            "cabang. Hari tersangka yang bertepatan hari sistemik perlu "
            "ditafsir ulang.")
        scl.addWidget(st)
        self._lbl_sistemik = WLabel("", scard)
        self._lbl_sistemik.setObjectName("hint")
        scl.addWidget(self._lbl_sistemik)
        self._sistemik_table = DataTable(scard)
        self._sistemik_table.setMinimumHeight(80)
        scl.addWidget(self._sistemik_table, 1)
        sl.addWidget(scard, 1)
        rl.addWidget(side, 2)
        page_lay.addWidget(row2, 2)
        self._row2 = row2

        # v2.13.3 (⑧): kartu tren multi-bulan (butuh ≥ 2 pembanding —
        # tanpa itu pesan jujur; ⤢ menyembunyikan kartu ini juga).
        tcard = Card(self)
        tl2 = QVBoxLayout(tcard)
        tl2.setContentsMargins(12, 10, 12, 10)
        tl2.setSpacing(6)
        tt = WLabel("📈 Tren Bulanan per Cabang — butuh ≥ 2 bulan pembanding",
                    tcard)
        tt.setObjectName("cardTitle")
        tt.setToolTip(
            "Total waste per cabang tiap bulan pembanding + bulan "
            "berjalan + TREN (vs pembanding terbaru):\n"
            "↗ Naik / ↘ Turun (batas ±10%), → Stabil, Baru, Pulih.\n"
            "Menambah file bulan lalu di tab Banding Periode otomatis "
            "mengisi kartu ini.")
        tl2.addWidget(tt)
        self._lbl_trend = WLabel("", tcard)
        self._lbl_trend.setObjectName("hint")
        tl2.addWidget(self._lbl_trend)
        self._trend_table = DataTable(tcard)
        self._trend_table.setMinimumHeight(90)
        self._trend_table.setup_header_filters(
            {}, self._page_apply("trend"), self._page_state("trend"),
            all_cols=True, skip=())
        tl2.addWidget(self._trend_table, 1)
        page_lay.addWidget(tcard, 2)
        self._row3 = tcard

        # Pop-up rincian cabang — satu instance dipakai ulang.
        self._drill: QDialog | None = None
        # Jendela layar penuh tabel utama (reparent, pola view_hari).
        self._fs_dlg: QDialog | None = None
        self._fs_idx: int = 2

        # Memo hasil analisa — kunci (data_version, history_version):
        # objek sama dipakai ulang antar-refresh → cache fit DataTable
        # kena (pola view lain). Dihitung di thread UI dengan
        # busy_feedback (terukur data asli: ±150-250 ms — aman).
        self._memo_ver: tuple[int, int] | None = None
        self._memo: dict = {}
        # funnel LOKAL per tabel tampilan (pola v2.12.4).
        self._lfilters: dict[str, dict[str, list]] = {
            "scorecard": {}, "money": {}, "weekday": {}, "sistemik": {},
            "dq": {}, "trend": {},
        }

        # Reaksi state — lazy (hitung hanya saat tab terlihat; data baru
        # / pembanding baru menandai dirty). app.py memanggil on_shown()
        # saat tab dibuka (pola view lain).
        self._dirty = True
        ctx.data_ready.connect(self._on_data_ready)
        ctx.history_ready.connect(self._on_history_ready)

    # ------------------------------------------------------------
    # RENDER (memo tunggal — anti-lambat)
    # ------------------------------------------------------------

    def _on_data_ready(self) -> None:
        self._dirty = True
        self._memo_ver = None
        if self.isVisible():
            self._refresh()

    def _on_history_ready(self) -> None:
        self._dirty = True
        self._memo_ver = None
        if self.isVisible():
            self._refresh()

    def on_shown(self) -> None:
        if self._dirty:
            self._refresh()

    def _refresh(self) -> None:
        """Hitung (sekali per data/pembanding) + render semua tabel."""
        self._dirty = False
        df = self._ctx.df
        if df is None or df.empty:
            self._lbl_count.setText(
                "Jalankan pipeline dulu (tab Pipeline) — scorecard "
                "menunggu data bulan berjalan.")
            self._table.set_dataframe(None)
            self._money_table.set_dataframe(None)
            self._weekday_table.set_dataframe(None)
            self._sistemik_table.set_dataframe(None)
            return

        ver = (self._ctx.data_version, self._ctx.history_version)
        if self._memo_ver != ver:
            with busy_feedback(self._ctx.set_status,
                               "Menghitung scorecard cabang"):
                months = self._ctx.history_months
                sc = scorecard(df, months, self._ctx.key_akhir,
                               self._ctx.config)
                inten = resto_intensity(df)
                money = money_ranking(df, top_n=200)
                label = detect_month_label(
                    self._ctx.summary.get("workbook_path", "")
                    if isinstance(self._ctx.summary, dict) else "")
                wk = weekday_real(df, label, self._ctx.key_akhir)
                sysd = systemic_days(df, self._ctx.key_akhir)
                checks = run_checks(df, key_akhir=self._ctx.key_akhir)
                dq = pd.DataFrame([
                    {"SEVERITY": r.severity, "KODE": r.code,
                     "TEMUAN": r.title, "JUMLAH": r.count,
                     "PENJELASAN": r.detail}
                    for r in checks
                ]) if checks else pd.DataFrame(
                    columns=["SEVERITY", "KODE", "TEMUAN", "JUMLAH",
                             "PENJELASAN"])
                trend = branch_trend(df, months)
                self._memo = {
                    "scorecard": sc, "intensity": inten, "money": money,
                    "weekday": wk, "sistemik": sysd, "label": label,
                    "dq": dq, "trend": trend,
                }
            self._memo_ver = ver

        m = self._memo
        sc = self._apply_local("scorecard", m["scorecard"])
        self._table.set_dataframe(sc, sort_desc="KELEBIHAN")

        money = self._apply_local("money", m["money"])
        self._money_table.set_dataframe(money, sort_desc="KELEBIHAN")
        self._lbl_money.setText(
            f"{len(money)} baris ber-kelebihan (dari baris aktif yang "
            f"punya ≥ 3 pembanding) — urut kelebihan terbesar.")

        wk = self._apply_local("weekday", m["weekday"])
        self._weekday_table.set_dataframe(wk)
        label = m.get("label") or ""
        if wk is None or wk.empty:
            self._lbl_weekday.setText(
                "Nama bulan file tidak terbaca — pola hari kalender butuh "
                "bulan+tahun di nama file (mis. WASTE_SEPTEMBER_2026).")
        else:
            self._lbl_weekday.setText(
                f"Bulan berjalan: {label} — hari dengan rata-rata waste "
                "terbesar otomatis terlihat (klik judul utk sort).")

        sysd = self._apply_local("sistemik", m["sistemik"])
        self._sistemik_table.set_dataframe(sysd)
        if sysd is None or sysd.empty:
            self._lbl_sistemik.setText(
                "0 hari sistemik bulan ini — semua lonjakan bersifat "
                "lokal per cabang (itu sendiri informasi: tidak ada "
                "kejadian bersama).")

        dq = self._apply_local("dq", m.get("dq"))
        self._dq_table.set_dataframe(dq)
        if dq is None or dq.empty:
            self._lbl_dq.setText("Semua pemeriksaan bersih.")
        else:
            n_warn = int((dq["SEVERITY"] == "warning").sum()) \
                if "SEVERITY" in dq.columns else 0
            self._lbl_dq.setText(
                f"{len(dq)} temuan ({n_warn} warning) — hover judul "
                "kolom utk istilah; arahkan kursor ke sel PENJELASAN utk "
                "baca lengkap (tooltip).")

        # v2.13.3 (⑧): kartu tren multi-bulan (≥ 2 pembanding).
        trend = self._apply_local("trend", m.get("trend"))
        self._trend_table.set_dataframe(trend)
        if trend is None or trend.empty:
            self._lbl_trend.setText(
                "Belum cukup bulan pembanding — tambahkan ≥ 2 file bulan "
                "lalu di tab Banding Periode (kartu terisi otomatis). "
                "Kolom TREN tabel utama sudah aktif dengan 1 bulan.")
        else:
            self._lbl_trend.setText(
                f"{len(trend)} cabang · urut 'Bulan Ini' terbesar — "
                "bandingkan per bulan (klik judul = sort).")

        # KPI
        inten = m["intensity"]
        if inten is not None and not inten.empty:
            hemat = float(pd.to_numeric(
                inten["KELEBIHAN"], errors="coerce").fillna(0).sum())
            med = inten["TIPIKAL CABANG %"].dropna()
            med_v = float(med.iloc[0]) if len(med) else float("nan")
            self._kpi_hemat.set_value(fmt_id(hemat))
            self._kpi_hemat.set_context(
                "satuan campuran GR/PCS — baca per cabang")
            self._kpi_intens.set_value(
                f"{med_v:.3f}".replace(".", ",") + "%"
                if pd.notna(med_v) else "—")
            self._kpi_intens.set_context("median waste ÷ BOM semua cabang")
            top = inten.iloc[0]
            self._kpi_top.set_value(str(top["NAMA RESTO"]))
            self._kpi_top.set_context(
                f"hemat ± {fmt_id(top['KELEBIHAN'])} · intensitas "
                + (f"{top['INTENSITAS %']:.3f}".replace(".", ",") + "%"
                   if pd.notna(top["INTENSITAS %"]) else "Cek"))
        n_sys = 0 if sysd is None else len(sysd)
        self._kpi_sistemik.set_value(str(n_sys))
        self._kpi_sistemik.set_context(
            "hari naik serentak (≥ 3 cabang)" if n_sys
            else "semua lonjakan lokal")
        self._lbl_count.setText(
            f"{len(sc)} cabang — urut KELEBIHAN (potensi hemat) "
            "terbesar; klik 2× baris = rincian cabang.")

    # ------------------------------------------------------------
    # FUNNEL LOKAL (pola v2.12.4 — tampilan saja)
    # ------------------------------------------------------------

    def _page_apply(self, page: str):
        """Closure apply_fn funnel utk tabel halaman `page` (menu memanggil
        callable langsung — pemilahan tabel lewat closure, bukan sender)."""
        return lambda col, key, values: self._on_page_filter(
            page, col, values)

    def _page_state(self, page: str):
        return lambda col: self._lfilters_state(page, col)

    def _on_page_filter(self, page: str, col: str, values) -> None:
        """Menu funnel header tabel halaman `page` → saring TAMPILAN tabel
        itu saja (bahan memo tersimpan — tanpa hitung ulang)."""
        f = self._lfilters.setdefault(page, {})
        if values:
            f[col] = list(values)
        else:
            f.pop(col, None)
        src = self._memo.get(page)
        table = {"scorecard": self._table, "money": self._money_table,
                 "weekday": self._weekday_table,
                 "sistemik": self._sistemik_table,
                 "dq": self._dq_table,
                 "trend": self._trend_table}[page]
        if isinstance(src, pd.DataFrame) and not src.empty:
            table.set_dataframe(self._apply_local(page, src))
        self._ctx.set_status(
            "⧩ Filter tampilan diterapkan di kartu ini — angka analisa "
            "tak berubah", "done")

    def _lfilters_state(self, page: str, col: str):
        v = self._lfilters.get(page, {}).get(col)
        return list(v) if v else None

    def _apply_local(self, page: str, df: pd.DataFrame):
        f = self._lfilters.get(page) or {}
        if not isinstance(df, pd.DataFrame) or df.empty or not f:
            return df
        m = pd.Series(True, index=df.index)
        for col, vals in f.items():
            if col in df.columns and vals:
                m &= df[col].isin(vals)
        return df[m]

    # ------------------------------------------------------------
    # RINCIAN CABANG (pop-up — klik 2×)
    # ------------------------------------------------------------

    def _on_double(self, rec: pd.Series) -> None:
        resto = str(rec.get("NAMA RESTO") or "").strip()
        if not resto or self._ctx.df is None:
            return
        df = self._ctx.df
        dlg = self._drill
        if dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Rincian Cabang — klik 2× baris scorecard")
            dlg.resize(860, 560)
            dl = QVBoxLayout(dlg)
            dl.setContentsMargins(10, 8, 10, 8)
            dl.setSpacing(6)
            self._drill_title = WLabel("", dlg)
            self._drill_title.setObjectName("cardTitle")
            dl.addWidget(self._drill_title)
            btn = QPushButton("⤡ Tutup (Esc)", dlg)
            btn.clicked.connect(dlg.close)
            brow = QWidget(dlg)
            brl = QHBoxLayout(brow)
            brl.setContentsMargins(0, 0, 0, 0)
            brl.addStretch(1)
            brl.addWidget(btn)
            dl.addWidget(brow)
            self._drill_money = DataTable(dlg)
            self._drill_money.setMinimumHeight(180)
            dl.addWidget(self._drill_money, 3)
            self._drill_share = DataTable(dlg)
            self._drill_share.setMinimumHeight(120)
            dl.addWidget(self._drill_share, 2)
            self._drill_missing = WLabel("", dlg)
            self._drill_missing.setObjectName("hint")
            self._drill_missing.setWordWrap(True)
            dl.addWidget(self._drill_missing)
            self._drill = dlg
        self._drill_title.setText(
            f"🏬 {resto} — top kerugian vs tipikal & profil alasan "
            "(klik judul = sort)")
        with busy_feedback(self._ctx.set_status,
                           f"Menghitung rincian {resto}"):
            money = money_ranking(df, top_n=10_000)
            if not money.empty:
                money = money[money["NAMA RESTO"].astype(str) == resto]
            self._drill_money.set_dataframe(
                money.head(15), sort_desc="KELEBIHAN")
            share = reason_share(df, resto)
            if share is not None and not share.empty:
                share_df = pd.DataFrame({
                    "ALASAN": share.index.to_numpy(),
                    "SHARE %": share.to_numpy(),
                })
            else:
                share_df = pd.DataFrame(
                    columns=["ALASAN", "SHARE %"])
            self._drill_share.set_dataframe(share_df)
            cov = coverage_report(df, self._ctx.history_months)
            if not cov.empty:
                c = cov[cov["NAMA RESTO"].astype(str) == resto]
                if not c.empty:
                    n = int(c.iloc[0]["ITEM UMUM TAK INPUT"])
                    verdict = str(c.iloc[0]["STATUS INPUT"])
                    contoh = str(c.iloc[0]["CONTOH ITEM"])
                    self._drill_missing.setText(
                        f"Input: {verdict} — {n} item umum tak dilaporkan"
                        + (f" (contoh: {contoh})" if contoh else "") + ".")
                else:
                    self._drill_missing.setText("Input: —")
            else:
                self._drill_missing.setText("")
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ------------------------------------------------------------
    # ⤢ / ⛶ (pola view_hari — reparent tabel ASLI)
    # ------------------------------------------------------------

    def _on_expand(self) -> None:
        collapsed = self._kpi_row.isHidden()
        show = collapsed
        self._kpi_row.setVisible(show)
        self._row2.setVisible(show)
        self._row3.setVisible(show)
        self._btn_expand.setText(
            "⤢ Perbesar Tabel" if show else "⤡ Tampilkan KPI & Kartu")
        self._ctx.set_status(
            "⤡ KPI & kartu disembunyikan — tabel diperbesar" if not show
            else "⤢ KPI & kartu ditampilkan kembali", "done")

    def _on_fullscreen(self) -> None:
        if self._table.model().rowCount() == 0:
            self._ctx.set_status(
                "Belum ada data utk dibesarkan — jalankan pipeline dulu "
                "(tab Pipeline)", "done")
            return
        if self._fs_dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(
                "Scorecard Cabang — Layar Penuh (Esc = kembali)")
            dlay = QVBoxLayout(dlg)
            dlay.setContentsMargins(10, 8, 10, 8)
            dlay.setSpacing(6)
            btn = QPushButton("⤡ Kembali ke Tab (Esc)", dlg)
            btn.clicked.connect(dlg.close)
            brow = QWidget(dlg)
            brl = QHBoxLayout(brow)
            brl.setContentsMargins(0, 0, 0, 0)
            brl.addStretch(1)
            brl.addWidget(btn)
            dlay.addWidget(brow)
            dlg.rejected.connect(self._restore_table_from_fs)
            self._fs_dlg = dlg
        idx = self._tcl.indexOf(self._table)
        self._fs_idx = idx if idx >= 0 else 2
        self._tcl.removeWidget(self._table)
        self._fs_dlg.layout().insertWidget(1, self._table)
        self._fs_dlg.show()
        self._fs_dlg.showMaximized()
        self._ctx.set_status("⛶ Scorecard dibesarkan — Esc = kembali",
                             "done")

    def _restore_table_from_fs(self) -> None:
        if self._fs_dlg is not None and self._table.parent() is self._fs_dlg:
            self._fs_dlg.layout().removeWidget(self._table)
            self._tcl.insertWidget(self._fs_idx, self._table)
        self._ctx.set_status("⤡ Kembali ke tab scorecard", "done")
