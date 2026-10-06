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
  detail 12 sinyal + peta hari 1-31; klik 2× = fokus cabang+item.

Istilah sengaja awam (permintaan user): "tipikal cabang lain", "berapa
kali lipat", "porsi dari total bulanan" — bukan jargon statistik.
"""
from __future__ import annotations

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

from .shared import fmt_id
from .state import AppContext
from .view_anomali import DetailDialog, _HF_COLS
from .widgets import Card, DataTable, KpiCard, WLabel, busy_feedback
from waste_anomaly.period_history import day_evidence_vs_history
from waste_anomaly.followup import FP_COL

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


class HariView(QWidget):
    """View 'Hari Mencurigakan': tabel bukti hari per anomali ter-filter."""

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
            "untuk kembali). Sort / pop-up detail / klik 2× tetap\n"
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
        # v2.12.3: funnel filter + opsi sort di header tabel (satu state
        # ctx dgn tab Anomali). v2.12.4: SEMUA kolom ber-funnel — kolom
        # mapping global, lainnya filter LOKAL (pola AnomaliView).
        self._table.setup_header_filters(
            _HF_COLS, self._on_header_filter, self._hf_state,
            all_cols=True, skip=(FP_COL,))
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        self._table.double_clicked.connect(self._on_double)
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
        # (hit) + memo teks model tetap hidup. Strong ref ke df dasar = id
        # tak bisa dipakai ulang selama cache hidup (kunci id() aman).
        self._bukti_cache: tuple[int, int, pd.DataFrame] | None = None
        # v2.10.0: memo df + bukti bulan-lalu — kunci (id df, len, versi
        # history); objek SAMA dipakai ulang antar-refresh → cache fit
        # DataTable tetap kena (pola _bukti_cache).
        self._hist_cache: tuple[int, int, int, pd.DataFrame] | None = None
        # v2.12.4: funnel LOKAL kolom non-ctx (SEMUA kolom ber-funnel) —
        # pola AnomaliView: hanya menyaring TAMPILAN tabel ini.
        self._hfilters: dict[str, list] = {}
        self._mask_cache: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()

        # Reaksi state — pola lazy H2 (sama dengan AnomaliView).
        self._dirty = True
        self._batch_filters = False
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)
        # v2.10.0: pembanding bulan lalu selesai dimuat → render ulang
        # (kolom bukti bulan lalu muncul) bila terlihat, else tandai dirty.
        ctx.history_ready.connect(self._on_history_ready)

    # ------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------
    def _on_data_ready(self) -> None:
        # v2.12.4: dataset baru → nilai funnel lokal bisa jadi tak ada —
        # reset (pola AnomaliView).
        self._hfilters.clear()
        self._mask_cache.clear()
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def _on_filters_changed(self) -> None:
        if self._batch_filters:
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
        (pola v2.8.3 anti-freeze: cursor sibuk + status ⏳/✓ + durasi)."""
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
            if (cached is not None and cached[0] == id(df)
                    and cached[1] == len(df)):
                df_show = cached[2]
            else:
                df_show = df[bukti]
                self._bukti_cache = (id(df), len(df), df_show)
        else:
            df_show = df
        n_bukti_all = int(bukti.sum())
        # v2.10.0: bukti tambahan vs bulan lalu (tanggal sama) — hanya bila
        # pembanding dimuat; memo objek per (id, len, versi history).
        months = self._ctx.history_months_ok()
        if months:
            df_show = self._with_history(df_show)
        cols = [c for c in TABLE_COLS if c in df_show.columns]
        # v2.12.3: JENIS keluar dari narrow_hide (permintaan user "tambahkan
        # kolom jenis" — dulu disembunyikan responsif di layar sempit
        # 1366px; kini selalu tampil — SUSUT/TRIAL/WASTE terlihat langsung).
        # v2.12.4: funnel LOKAL kolom non-ctx — mask isin di atas df_show
        # (memo per state — pola AnomaliView._mask_local).
        shown = self._mask_local(df_show)
        self._table.set_dataframe(
            shown, sort_desc="RASIO VS CABANG LAIN",
            narrow_hide=["KETERANGAN", "NILAI BULAN LALU",
                         "TIPIKAL BEBERAPA BULAN", "ALASAN HARI"],
            visible_cols=cols)
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
        if (cached is not None and cached[0] == id(df_show)
                and cached[1] == len(df_show) and cached[2] == ver):
            return cached[3]
        out = day_evidence_vs_history(
            df_show, months=self._ctx.history_months_ok(),
            typical=self._ctx.history_typical, config=self._ctx.config)
        self._hist_cache = (id(df_show), len(df_show), ver, out)
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
    # INTERAKSI
    # ------------------------------------------------------------
    def _on_selection(self) -> None:
        rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    def _on_double(self, rec: pd.Series) -> None:
        """Klik 2×: fokus cabang+item (pola drill-down AnomaliView + guard
        coalesce V26-L4 — dua filter, satu render)."""
        self._batch_filters = True
        try:
            if rec.get("NAMA RESTO") is not None:
                self._ctx.set_filter("cabang", rec.get("NAMA RESTO"))
            if rec.get("NAMA BARANG") is not None:
                self._ctx.set_filter("item", rec.get("NAMA BARANG"))
        finally:
            self._batch_filters = False
        self._refresh_table()

    def _on_header_filter(self, col: str, key: str, values) -> None:
        """v2.12.3 — menu funnel header → state ctx (sinkron dgn tab
        Anomali — satu sumber active_filters).
        v2.12.4 — kolom NON-mapping: filter LOKAL tampilan view ini
        (pola AnomaliView)."""
        if col in _HF_COLS:
            self._ctx.set_filter(key, values)  # global — antar-tab sinkron
            return
        if values:
            self._hfilters[col] = list(values)
        else:
            self._hfilters.pop(col, None)
        self._refresh_table()

    def _hf_state(self, col: str):
        """v2.12.3 — status funnel kolom utk MELUKIS (aktif = terisi).
        v2.12.4 — kolom lokal: baca _hfilters view."""
        key = _HF_COLS.get(col)
        if key is not None:
            v = self._ctx.active_filters.get(key)
            if isinstance(v, list):
                return v or None
            if isinstance(v, str) and v:
                return [v]
            return None
        v = self._hfilters.get(col)
        return list(v) if v else None

    def _mask_local(self, df_show: pd.DataFrame) -> pd.DataFrame:
        """v2.12.4 — mask isin per kolom funnel LOKAL (memo LRU per state,
        pola AnomaliView._mask_local — objek stabil → cache fit kena)."""
        if not self._hfilters:
            return df_show
        sig = tuple(sorted((c, tuple(v)) for c, v in self._hfilters.items()))
        key = (id(df_show), sig)
        out = self._mask_cache.get(key)
        if out is None:
            m = pd.Series(True, index=df_show.index)
            for col, vals in self._hfilters.items():
                if col in df_show.columns and vals:
                    m &= df_show[col].isin(vals)
            out = df_show[m]
            self._mask_cache[key] = out
            while len(self._mask_cache) > 4:
                self._mask_cache.popitem(last=False)
        else:
            self._mask_cache.move_to_end(key)
        return out

    def _on_clear_filters(self) -> None:
        """v2.12.4 — tombol '✕ Hapus Filter': lepas SEMUA filter aktif
        (funnel global ctx + funnel lokal view) — pengganti tombol sidebar
        yang dihapus (pola AnomaliView)."""
        self._hfilters.clear()
        had_global = bool(self._ctx.active_filters and any(
            v for v in self._ctx.active_filters.values())) \
            or self._ctx.day_min is not None or bool((self._ctx.search or "").strip())
        if had_global:
            self._ctx.reset_filters()
            self._ctx.filters_changed.emit()
        else:
            self._refresh_table()
        self._ctx.set_status("✓ Semua filter dihapus", "done")

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
        reparent + pulihkan index layout (pola AnomaliView v2.12.2)."""
        if self._table.model().rowCount() == 0:
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
