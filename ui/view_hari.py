"""view_hari.py — view 'Hari Mencurigakan' (v2.9.0).

Tab ke-4 (disetujui user setelah pembuktian read-only v2.8.3: 74% anomali
bisa dilokalisasi ke hari tertentu). Menjawab pertanyaan user:
"misal ada potensi salah angka kamu bisa deteksi gak dia potensi salah
nya di tanggal berapa dari 1-31?"

Data: kolom bukti-hari hasil Stage 15 (waste_anomaly/day_focus.py) —
HARI TERSANGKA, NILAI HARI TERSANGKA, TIPIKAL CABANG LAIN,
RASIO VS CABANG LAIN, SHARE HARI TERSANGKA, ALASAN HARI.

UI:
- 3 KPI ringkas: anomali tampil · ada bukti hari · rasio terbesar
- Combo: hanya baris dengan bukti hari (default) / semua anomali
- Tabel terurut RASIO VS CABANG LAIN (terbesar duluan) — hover judul
  kolom = penjelasan istilah (COLUMN_TOOLTIPS); klik baris = pop-up
  detail 12 sinyal + peta hari 1-31.
- v2.13.5: kolom ✓ follow-up (pola tab Anomali) + tombol '☑ Centang
  yang tampil' — baris hari-mencurigakan langsung masuk daftar Follow
  Up tanpa pindah tab; tombol follow-up juga ada di pop-up detail.
- v2.13.5 (permintaan user): klik-2× baris TAK LAGI memasang filter —
  keluhan "klik 1× pop-up kadang tidak muncul dan malah ketrigger
  klik 2× yang langsung filter" (klik-2× → set_filter → render →
  pop-up di-hide). Fokus cabang/item kini hanya lewat tombol eksplisit
  pop-up detail. Pop-up juga muncul ulang saat baris SAMA diklik
  lagi (sinyal clicked + guard idempoten DetailDialog).

Istilah sengaja awam (permintaan user): "tipikal cabang lain", "berapa
kali lipat", "porsi dari total bulanan" — bukan jargon statistik.
"""
from __future__ import annotations

import weakref
from collections import OrderedDict

import pandas as pd
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .shared import baseline_label, fmt_id
from .state import AppContext
from .followup_table import FollowupTableMixin
from .models import COLUMN_TOOLTIPS
from .view_anomali import DetailDialog, _HF_COLS
from .widgets import Card, DataTable, KpiCard, WLabel, busy_feedback
from waste_anomaly.period_history import (
    day_evidence_vs_history,
    month_sort_key,
)
from waste_anomaly.followup import CHECK_COL, FP_COL

# Kolom tabel hari-mencurigakan (ramping — detail lengkap di pop-up).
# v2.10.0: 3 kolom bukti vs bulan lalu HANYA muncul bila data pembanding
# dimuat (filter `c in df.columns` di bawah) — tanpa pembanding, tabel
# tampil persis seperti v2.9.0.
TABLE_COLS = [
    "ANOMALY SCORE", "NAMA RESTO", "NAMA BARANG", "JENIS", "KETERANGAN",
    "HARI TERSANGKA", "NILAI HARI TERSANGKA", "TIPIKAL CABANG LAIN",
    "RASIO VS CABANG LAIN", "SHARE HARI TERSANGKA",
    "NILAI BULAN LALU", "RASIO VS BULAN LALU", "TIPIKAL BEBERAPA BULAN",
    "ALASAN HARI",
]

# v2.12.4: hint '💡 Bukti hari = ...' DIHAPUS (permintaan user: kalimat
# penjelas panjang dihapus dari UI). Penjelasan istilah tetap tersedia di
# tooltip judul kolom (COLUMN_TOOLTIPS) + Bantuan.


class HariView(FollowupTableMixin, QWidget):
    """View 'Hari Mencurigakan'.

    v2.13.8 (gel-C): 10 metode kembar ✓-follow-up/funnel diwariskan
    dari FollowupTableMixin (konsolidasi dgn AnomaliView — dulu
    salinan ±250 baris); _DISP_LRU khusus view ini = 4."""

    _DISP_LRU = 4

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # KPI ringkas (3 kartu)
        kpi_row = QWidget(self)
        kl = QHBoxLayout(kpi_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(8)
        self._kpi_tampil = KpiCard("ANOMALI TAMPIL", "#0f172a",
                                   tooltip="Banyak baris anomali yang lolos "
                                           "filter & pilihan tampil.")
        self._kpi_bukti = KpiCard("ADA BUKTI HARI", "#dc2626",
                                  tooltip="Anomali yang bisa dilokalisasi ke "
                                          "tanggal tertentu (rasio ≥ 5× cabang "
                                          "lain, atau ≥ 50% waste sebulan di "
                                          "satu hari, atau pola 10× salah "
                                          "ketik, atau waste cuma 1 hari).")
        self._kpi_rasio = KpiCard("RASIO TERBESAR", "#ea580c",
                                  tooltip="Berapa kali lipat nilai hari "
                                          "tersangka vs cabang lain di hari "
                                          "yang sama (baris teratas saat "
                                          "diurut berdasarkan rasio).")
        for card in (self._kpi_tampil, self._kpi_bukti, self._kpi_rasio):
            kl.addWidget(card)
        kl.addStretch(1)
        lay.addWidget(kpi_row)
        self._kpi_row = kpi_row  # v2.12.3: toggle ⤢ (ciutkan KPI)

        # Kartu tabel
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        # v2.12.3: judul + tombol melebarkan SATU baris (pola tab Anomali
        # — permintaan user "bisa diperbesar kaya tab lain").
        head = QWidget(card)
        hcl = QHBoxLayout(head)
        hcl.setContentsMargins(0, 0, 0, 0)
        hcl.setSpacing(8)
        title = WLabel("📅 Hari Mencurigakan — potensi salah angka per tanggal (1–31)", head)
        title.setObjectName("cardTitle")
        hcl.addWidget(title)
        hcl.addStretch(1)
        self._btn_expand = QPushButton("⤢ Perbesar Tabel", head)
        self._btn_expand.setToolTip(
            "Sembunyikan KPI, judul & bar kontrol supaya tabel memakai "
            "seluruh tinggi tampilan (funnel header tetap hidup — filter "
            "tetap aktif). Klik lagi untuk mengembalikan.")
        self._btn_expand.clicked.connect(self._on_expand)
        hcl.addWidget(self._btn_expand)
        self._btn_full = QPushButton("⛶ Layar Penuh", head)
        self._btn_full.setToolTip(
            "Buka tabel ini di jendela LAYAR PENUH (tekan Esc atau Tutup\n"
            "untuk kembali). Sort / pop-up detail / centang ✓ tetap\n"
            "berfungsi penuh di jendela itu.")
        self._btn_full.clicked.connect(self._on_fullscreen)
        hcl.addWidget(self._btn_full)
        cl.addWidget(head)
        self._head_row = head  # v2.12.3: toggle ⤢ (ciutkan judul+hint)

        # Bar kontrol: combo tampilkan + hapus filter
        ctrl = QWidget(card)
        ctl = QHBoxLayout(ctrl)
        ctl.setContentsMargins(8, 0, 8, 0)
        ctl.setSpacing(10)
        lbl = WLabel("Tampilkan:", ctrl)
        ctl.addWidget(lbl)
        self._cb_mode = QComboBox(ctrl)
        self._cb_mode.addItem("Ada bukti hari (disarankan)")
        self._cb_mode.addItem("Semua anomali")
        self._cb_mode.setToolTip(
            "Default: hanya anomali yang punya bukti hari (lebih fokus).\n"
            "'Semua anomali' = tampilkan juga yang belum bisa dilokalisasi\n"
            "(kolom bukti kosong).")
        self._cb_mode.currentIndexChanged.connect(
            lambda _i: self._on_mode_changed())
        ctl.addWidget(self._cb_mode)
        # v2.12.4 — pengganti tombol '✕ Hapus Semua Filter' sidebar: lepas
        # SEMUA filter (funnel global + lokal) sekaligus (pola AnomaliView).
        self._btn_fu_all = QPushButton("☑ Centang yang tampil", ctrl)
        self._btn_fu_all.setToolTip(
            "Centang SEMUA baris hari-mencurigakan yang sedang tampil "
            "(hasil filter saat ini) sekaligus ke daftar Follow Up.\n"
            "Cocok dipakai setelah funnel kolom menyempitkan daftar: "
            "saring → centang massal → tinjau di tab Follow Up.\n"
            "(v2.13.5 — pola tab Anomali, kini juga di tab ini.)")
        self._btn_fu_all.clicked.connect(self._on_check_all)
        ctl.addWidget(self._btn_fu_all)
        self._btn_clear = QPushButton("✕ Hapus Filter", ctrl)
        self._btn_clear.setToolTip(
            "Hapus SEMUA filter yang sedang aktif — funnel kolom (global "
            "maupun tampilan) — kembali ke tampilan penuh.")
        self._btn_clear.clicked.connect(self._on_clear_filters)
        ctl.addWidget(self._btn_clear)
        self._lbl_count = WLabel("", ctrl)
        self._lbl_count.setObjectName("hint")
        ctl.addWidget(self._lbl_count, 1)
        cl.addWidget(ctrl)
        self._ctrl = ctrl  # v2.12.3: toggle ⤢ (ciutkan bar kontrol)

        self._table = DataTable(card)
        self._table.setMinimumHeight(200)
        # v2.13.5 — kolom centang ✓ follow-up in-place (pola AnomaliView:
        # klik sel = flip bool + sinyal check_toggled → state ctx TANPA
        # render ulang; dataChanged satu sel — cache fit tak tersentuh).
        self._table.model().set_check_column(CHECK_COL)
        self._table.model().set_row_key_column(FP_COL)
        self._table.model().check_toggled.connect(self._on_check_toggled)
        # v2.12.3: funnel filter + opsi sort di header tabel (satu state
        # ctx dgn tab Anomali). v2.12.4: SEMUA kolom ber-funnel — kolom
        # mapping global, lainnya filter LOKAL (pola AnomaliView).
        # v2.13.5: kolom ✓ juga di-skip (pola AnomaliView).
        self._table.setup_header_filters(
            _HF_COLS, self._on_header_filter, self._hf_state,
            all_cols=True, skip=(CHECK_COL, FP_COL))
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        # v2.13.5: klik baris SAMA saat pop-up sempat ditutup harus
        # membuka pop-up lagi — currentRowChanged diam saat index tak
        # berubah (keluhan user "pop-up kadang tidak muncul"); sinyal
        # clicked memicu di SETIAP klik. Guard idempoten DetailDialog
        # mencegah rebuild ganda (currentRowChanged + clicked).
        self._table.row_clicked.connect(lambda *_: self._on_selection())
        cl.addWidget(self._table, 1)
        self._tcl = cl  # v2.12.3: reparent ⛶ (pulihkan index layout tabel)
        lay.addWidget(card, 1)

        # Pop-up detail — satu instance dipakai ulang (pola AnomaliView).
        self._popup = DetailDialog(ctx, self)
        # v2.12.3 — jendela layar penuh tabel (dibuat malas, dipakai ulang):
        # WIDGET TABEL ASLI di-reparent sementara (pola AnomaliView v2.12.2)
        # → interaksi sort/pop-up/klik-2× tetap hidup; Esc → pulihkan posisi.
        self._fs_dlg: QDialog | None = None
        self._fs_idx: int = 2  # v2.12.4: head(0)+ctrl(1)+tabel(2) — slicer/hint dihapus
        # v2.9.0 (perf): memo irisan bukti-hari — kombinasi (df dasar, mode)
        # yang sama mengembalikan objek SAMA → cache fit LRU DataTable
        # (hit) + memo teks model tetap hidup.
        # v2.13.13 (gel-4 A5b+C10): weakref + validasi identitas — dulu
        # kunci id() dgn komentar "strong ref ke df dasar" yang TIDAK
        # jujur (cache hanya memegang df HASIL, bukan df dasar → id bisa
        # dipakai ulang objek lain pasca-GC → masker basi — audit A5b;
        # komentar palsu dilaporkan audit C10). Pola _disp_cache: entri
        # (weakref, len, hasil), validasi ``cached[0]() is df``.
        self._bukti_cache: tuple[weakref.ref, int, pd.DataFrame] | None = None
        # v2.10.0: memo df + bukti bulan-lalu — kunci (id df, len, versi
        # history); objek SAMA dipakai ulang antar-refresh → cache fit
        # DataTable tetap kena (pola _bukti_cache; weakref+identitas
        # sejak v2.13.13 — alasan sama di atas).
        self._hist_cache: tuple[weakref.ref, int, int, pd.DataFrame] | None = None
        # v2.12.4: funnel LOKAL kolom non-ctx (SEMUA kolom ber-funnel) —
        # pola AnomaliView: hanya menyaring TAMPILAN tabel ini.
        self._hfilters: dict[str, list] = {}
        # v2.13.13 (gel-4 A5): entri mask = (weakref, hasil) dgn
        # validasi identitas (lihat followup_table._mask_local).
        self._mask_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
        # v2.13.5: df tampilan = salinan + ✓/__FP (pola AnomaliView) —
        # LRU-4 + weakref ke df sumber supaya objek display STABIL per
        # objek df → cache fit DataTable tetap kena antar-refresh; nilai
        # ✓ selalu disegarkan dari state saat dipakai.
        self._disp_cache: "OrderedDict[int, tuple]" = OrderedDict()
        self._fps_src: pd.DataFrame | None = None
        self._fps: pd.Series | None = None

        # Reaksi state — pola lazy H2 (sama dengan AnomaliView).
        self._dirty = True
        # v2.13.14 (gel-5 A7): flag anti render-ganda set_dataset — pola
        # AnomaliView (data_ready + filters_changed berpasangan dari
        # state.set_dataset; render data_ready sudah final).
        self._skip_filters_once = False
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)
        # v2.10.0: pembanding bulan lalu selesai dimuat → render ulang
        # (kolom bukti bulan lalu muncul) bila terlihat, else tandai dirty.
        ctx.history_ready.connect(self._on_history_ready)
        # v2.13.5: centangan follow-up berubah (toggle/bulk dari mana pun,
        # termasuk tombol di pop-up detail) → segarkan kolom ✓ IN-PLACE
        # (pola AnomaliView._on_followup_changed — bukan render ulang).
        ctx.followup_changed.connect(self._on_followup_changed)

    # ------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------
    def _on_data_ready(self) -> None:
        # v2.12.4: dataset baru → nilai funnel lokal bisa jadi tak ada —
        # reset (pola AnomaliView).
        self._hfilters.clear()
        self._mask_cache.clear()
        # v2.13.5: memo display/fingerprint berasal dataset lama — lepas
        # instan (pola AnomaliView; kunci id() df lama tak bisa kena lagi).
        self._disp_cache.clear()
        self._fps_src, self._fps = None, None
        if self.isVisible():
            self.refresh()
            # A7 (gel-5): render di atas sudah final utk dataset baru —
            # pasangan filters_changed dari set_dataset tak perlu render.
            self._skip_filters_once = True
        else:
            self._dirty = True

    def _on_filters_changed(self) -> None:
        if self._skip_filters_once:
            # A7 (gel-5): konsumsi flag — emit pasangan set_dataset.
            self._skip_filters_once = False
            return
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_mode_changed(self) -> None:
        if self.isVisible():
            self._refresh_table()

    def _on_history_ready(self) -> None:
        """v2.10.0: data pembanding (bulan lalu) siap → tampilkan bukti
        tanggal-sama bulan lalu (kolom NILAI/RASIO/TIPIKAL BULAN LALU)."""
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data baru / filter basi."""
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        """Dataset baru: KPI + tabel (filter sudah direset oleh state)."""
        self._dirty = False
        self._cb_mode.blockSignals(True)
        self._cb_mode.setCurrentIndex(0)
        self._cb_mode.blockSignals(False)
        self._refresh_table()

    def _refresh_table(self) -> None:
        """v2.9.0 — titik tunggal render tabel, dibungkus busy_feedback
        (pola v2.8.3 anti-freeze: cursor sibuk + status ⏳/✓ + durasi).
        v2.13.13 (gel-4 D6): first-run TANPA dataset TIDAK dibungkus —
        busy_feedback akan mengklaim "✓ Menganalisa hari tersangka
        selesai (0 ms)" padahal tak ada data yang dianalisa (residual
        D6 gel-2; pesan sukses-menampilkan-menyaring = klaim kosong).
        Render BERDATA tetap dibungkus utuh (kerja nyata 75-460 ms)."""
        if self._ctx.df is None:
            self._refresh_table_impl()
            return
        with busy_feedback(self._ctx.set_status, "Menganalisa hari tersangka"):
            self._refresh_table_impl()

    def _refresh_table_impl(self) -> None:
        self._table.clearSelection()
        self._popup.hide()
        self._popup._panel.clear()
        df = self._ctx.anomali_df()
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_count.setText(
                "Belum ada data — buka tab Pipeline, pilih workbook, jalankan.")
            return
        if "HARI TERSANGKA" not in df.columns:
            # Dataset tanpa kolom bukti hari (fixture sintetis / pipeline lama)
            self._table.set_dataframe(None)
            self._lbl_count.setText(
                "Dataset ini tidak punya kolom bukti hari — jalankan ulang "
                "pipeline (v2.9.0+).")
            self._update_kpi(None, 0, None)
            return
        bukti = (df["BUKTI HARI"].astype(str) == "YES") \
            if "BUKTI HARI" in df.columns else pd.Series(False, index=df.index)
        if self._cb_mode.currentIndex() == 0:
            cached = self._bukti_cache
            if (cached is not None and cached[0]() is df
                    and cached[1] == len(df)):
                df_show = cached[2]
            else:
                df_show = df[bukti]
                self._bukti_cache = (weakref.ref(df), len(df), df_show)
        else:
            df_show = df
        n_bukti_all = int(bukti.sum())
        # v2.10.0: bukti tambahan vs bulan lalu (tanggal sama) — hanya bila
        # pembanding dimuat; memo objek per (id, len, versi history).
        months = self._ctx.history_months_ok()
        # v2.13.14 (gel-5 C15): judul kolom NILAI BULAN LALU + tooltip
        # menyebut SUMBER — di tab Hari sumbernya = bulan pembanding
        # TERBARU yang termuat (BEDA dgn tab Anomali yang mengikuti combo
        # Banding Periode; dulu kedua tab memakai nama kolom sama tanpa
        # label bulan — audit C15). Alias headerData saja: data/sort/
        # record tetap nama kanonik (pola view_periode 'Pembanding').
        lbl_b = None
        if months:
            newest = max(months,
                         key=lambda m: month_sort_key(m.get("label")))
            lbl_b = baseline_label(newest)
        if lbl_b:
            self._table.model().set_header_map(
                {"NILAI BULAN LALU": f"NILAI BULAN LALU ({lbl_b})"})
            self._table.model().set_tooltip_map({
                "NILAI BULAN LALU":
                    COLUMN_TOOLTIPS.get("NILAI BULAN LALU", "")
                    + f"\nSumber saat ini: {lbl_b} (bulan pembanding "
                    "TERBARU yang termuat — beda dgn tab Anomali yang "
                    "mengikuti pilihan combo Banding Periode)"})
        else:
            self._table.model().set_header_map(None)
            self._table.model().set_tooltip_map(None)
        if months:
            df_show = self._with_history(df_show)
        cols = [c for c in TABLE_COLS if c in df_show.columns]
        # v2.13.5: df tampilan = salinan + ✓ + __FP (pola AnomaliView —
        # kontrak 'konsumen hanya membaca': objek memo tak dimutasi;
        # mutasi centang hanya menyentuh salinan view ini).
        disp = self._display_df(df_show)
        # v2.12.3: JENIS keluar dari narrow_hide (permintaan user "tambahkan
        # kolom jenis" — dulu disembunyikan responsif di layar sempit
        # 1366px; kini selalu tampil — SUSUT/TRIAL/WASTE terlihat langsung).
        # v2.12.4: funnel LOKAL kolom non-ctx — mask isin di atas display
        # (memo per state — pola AnomaliView._mask_local).
        shown = self._mask_local(disp)
        self._table.set_dataframe(
            shown, sort_desc="RASIO VS CABANG LAIN",
            # v2.13.13 (gel-4 C13): kolom PEMBANDING (ALASAN HARI, NILAI
            # BULAN LALU) disembunyikan PALING AKHIR — narrow_hide
            # menyembunyikan SESUAI URUTAN saat lantai header tak muat
            # (dulu keduanya duluan: layar 1366px justru kehilangan bukti
            # pembanding di saat pembanding AKTIF — audit C13). Kolom
            # non-pembanding (KETERANGAN, TIPIKAL BEBERAPA BULAN) lebih
            # dulu mundur; detail penuh tetap di pop-up.
            narrow_hide=["KETERANGAN", "TIPIKAL BEBERAPA BULAN",
                         "NILAI BULAN LALU", "ALASAN HARI"],
            visible_cols=[CHECK_COL] + cols)
        n_tampil = len(shown)
        if n_tampil == 0:
            self._lbl_count.setText(
                "0 anomali lolos filter — longgarkan filter / coba "
                "'Semua anomali'.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(n_tampil)} baris tampil • {fmt_id(n_bukti_all)} "
                f"dari {fmt_id(len(df))} anomali punya bukti hari")
        # Rasio terbesar utk KPI (dari shown — konsisten dgn tabel)
        rasio = None
        if "RASIO VS CABANG LAIN" in shown.columns:
            r = pd.to_numeric(shown["RASIO VS CABANG LAIN"],
                              errors="coerce").max()
            if r == r:
                rasio = float(r)
        self._update_kpi(n_tampil, n_bukti_all, rasio)

    def _with_history(self, df_show: pd.DataFrame) -> pd.DataFrame:
        """Tambah kolom bukti bulan-lalu (memo — pola _bukti_cache).

        day_evidence_vs_history vektor (merge) ~ms-level untuk ribuan
        baris; hasilnya di-memo supaya objek df SAMA dipakai ulang
        antar-refresh → cache fit DataTable tidak invalidasi ulang."""
        ver = self._ctx.history_version
        cached = self._hist_cache
        if (cached is not None and cached[0]() is df_show
                and cached[1] == len(df_show) and cached[2] == ver):
            return cached[3]
        out = day_evidence_vs_history(
            df_show, months=self._ctx.history_months_ok(),
            typical=self._ctx.history_typical, config=self._ctx.config)
        self._hist_cache = (weakref.ref(df_show), len(df_show), ver, out)
        return out

    def _update_kpi(self, n_tampil: int, n_bukti: int, rasio) -> None:
        self._kpi_tampil.set_value(fmt_id(n_tampil or 0))
        self._kpi_bukti.set_value(fmt_id(n_bukti or 0))
        if rasio is None:
            self._kpi_rasio.set_value("—")
            self._kpi_rasio.set_context("belum ada pembanding hari")
        else:
            self._kpi_rasio.set_value(
                f"{rasio:,.0f}×".replace(",", "."))
            self._kpi_rasio.set_context("vs cabang lain, hari sama")

    # ------------------------------------------------------------
    # v2.13.8 (gel-C): 10 metode ✓-follow-up + funnel (dulu seksi
    # INTERAKSI s/d _on_clear_filters) DIWARISKAN dari FollowupTableMixin
    # — konsolidasi kembar AnomaliView ⇄ HariView (±250 baris → 1 sumber).
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    # v2.12.3 — MELEBARKAN TABEL (pola tab Anomali v2.12.2)
    # ------------------------------------------------------------
    def _on_expand(self) -> None:
        """Ciutkan/kembalikan KPI + judul + bar kontrol (pola
        AnomaliView._on_expand — isHidden() agar toggle benar walau view
        induk di-balik tab lain). Funnel header tetap hidup."""
        collapsed = self._kpi_row.isHidden()
        show = collapsed
        self._kpi_row.setVisible(show)
        self._head_row.setVisible(show)
        self._ctrl.setVisible(show)
        self._btn_expand.setText(
            "⤢ Perbesar Tabel" if show else "⤡ Tampilkan KPI & Filter")
        self._ctx.set_status(
            "⤡ KPI disembunyikan — tabel diperbesar" if not show
            else "⤢ KPI & filter ditampilkan kembali", "done")

    def _on_fullscreen(self) -> None:
        """Pop-out TABEL ASLI ke jendela maximized (Esc = kembali) —
        reparent + pulihkan index layout (pola AnomaliView v2.12.2).
        v2.13.12 (gel-3 A9): tabel 0 baris DIBEDAKAN — 0-baris-karena-
        filter (dataset ADA tapi funnel menyaring semua) → pesan
        menyebut filter + cara melepas; tanpa dataset → arahan Pipeline
        tetap (kontrol positif)."""
        if self._table.model().rowCount() == 0:
            df = self._ctx.df
            if df is not None and not df.empty:
                self._ctx.set_status(
                    "Tabel 0 baris — filter sedang menyaring semua baris; "
                    "lepas filter dulu (tombol ✕ Hapus Filter / ikon "
                    "funnel di judul kolom), lalu perbesar tabel.", "done")
            else:
                self._ctx.set_status(
                    "Belum ada data utk dibesarkan — jalankan pipeline dulu "
                    "(tab Pipeline)", "done")
            return
        if self._fs_dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(
                "Tabel Hari Mencurigakan — Layar Penuh (Esc = kembali)")
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
            # rejected = Esc (default QDialog) DAN tombol Tutup X — satu
            # jalur pemulihan (pola AnomaliView).
            dlg.rejected.connect(self._restore_table_from_fs)
            self._fs_dlg = dlg
        idx = self._tcl.indexOf(self._table)
        self._fs_idx = idx if idx >= 0 else 2
        self._tcl.removeWidget(self._table)
        # insert DI ATAS baris tombol (hint dihapus v2.12.4)
        self._fs_dlg.layout().insertWidget(0, self._table, 1)
        self._fs_dlg.showMaximized()
        self._fs_dlg.raise_()
        self._fs_dlg.activateWindow()
        self._ctx.set_status("⛶ Tabel hari mencurigakan dibuka layar penuh "
                             "— Esc utk kembali", "done")

    def _restore_table_from_fs(self) -> None:
        """Kembalikan tabel ke kartu pada index layout asli (idempoten —
        guard parent, pola AnomaliView v2.12.2)."""
        if (self._fs_dlg is None
                or self._table.parent() is not self._fs_dlg):
            return
        self._fs_dlg.layout().removeWidget(self._table)
        self._tcl.insertWidget(self._fs_idx, self._table, 1)
        self._ctx.set_status("⤡ Tabel kembali ke tab Hari Mencurigakan",
                             "done")
