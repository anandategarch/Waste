"""view_followup.py — tab "Follow Up" (v2.12.0).

Daftar baris anomali yang di-CENTANG (kolom ✓) di tab Anomali —
shortlist investigasi, ditampilkan dalam format rekap PERSIS permintaan
user: ``TOTAL · AVG · MAX · SOURCE DATA · JENIS · KETERANGAN · NAMA
BARANG · NAMA RESTO · SATUAN · hari 1..31`` (nilai apa adanya dari
barisnya — tanpa agregasi baru, skor anomali tak diubah).

Perilaku:
- TIDAK ikut filter/slicer global (shortlist menetap — baris yang sudah
  dikumpulkan tak ikut hilang saat user menyaring). Ikut data_ready
  (dataset baru → baris di-refresh; key yang tak ada lagi dipangkas
  oleh MainWindow → ctx.prune_followup).
- Lepas centang ✓ = keluarkan dari daftar (baris hilang dari tabel).
- Hari mencurigakan diberi WARNA: merah = hari tersangka (HARI
  TERSANGKA/HARI MAX — konsisten peta hari pop-up detail); amber =
  nilai ≥ 2× rata-rata hari aktif (lonjakan sekunder).
- Klik baris = pop-up detail (komponen yang sama dgn tab Anomali —
  12 sinyal, peta hari, peer).
- Ekspor Excel: format rekap + 3 kolom serah terima kosong (PIC/
  KATEGORI/PENYEBAB — konvensi REKAP MENTAH), hari mencurigakan ikut
  diberi fill merah/amber.
- Kosongkan: hapus seluruh daftar (dengan konfirmasi).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.followup import (
    CHECK_COL,
    FOLLOWUP_COLS,
    FP_COL,
    day_cols,
    export_followup_xlsx,
    suspicious_days,
)

from .shared import fmt_id
from .state import AppContext
from .view_anomali import DetailDialog
from .widgets import Card, DataTable, WLabel, busy_feedback


class FollowUpView(QWidget):
    """View 'Follow Up': tabel rekap baris tercentang + ekspor."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        card = Card(self)
        card.setMinimumHeight(240)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        title = WLabel("Daftar Follow Up — baris tercentang (✓) di tab Anomali", card)
        title.setObjectName("cardTitle")
        title.setToolTip(
            "Kumpulan baris anomali yang Anda centang (kolom ✓) di tab "
            "Anomali.\nDaftar ini TIDAK terpengaruh filter/slicer — baris "
            "yang sudah dikumpulkan menetap.\nTertutup aplikasi pun aman: "
            "daftar tersimpan otomatis (followup.json).")
        cl.addWidget(title)

        # Bar kontrol: info jumlah + total + tombol ekspor & kosongkan.
        ctrl = QWidget(card)
        rl = QHBoxLayout(ctrl)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        self._lbl_info = WLabel("", ctrl)
        self._lbl_info.setObjectName("hint")
        rl.addWidget(self._lbl_info, 1)
        self._btn_export = QPushButton("💾 Ekspor Excel", ctrl)
        self._btn_export.setToolTip(
            "Simpan daftar follow-up sebagai workbook Excel (.xlsx):\n"
            "kolom format rekap (TOTAL…SATUAN + hari 1-31) + kolom kosong\n"
            "PIC / KATEGORI / PENYEBAB utk diisi petugas (konvensi REKAP\n"
            "MENTAH). Hari mencurigakan diberi warna merah/amber.")
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        rl.addWidget(self._btn_export)
        self._btn_clear = QPushButton("✕ Kosongkan", ctrl)
        self._btn_clear.setToolTip("Hapus SEMUA baris dari daftar follow-up\n"
                                   "(centangan di tab Anomali ikut lepas).")
        self._btn_clear.clicked.connect(self._on_clear)
        self._btn_clear.setEnabled(False)
        rl.addWidget(self._btn_clear)
        cl.addWidget(ctrl)

        self._table = DataTable(card)
        self._table.setMinimumHeight(200)
        # Kolom ✓ aktif di sini juga — lepas centang = keluarkan baris.
        self._table.model().set_check_column(CHECK_COL)
        self._table.model().set_row_key_column(FP_COL)
        self._table.model().check_toggled.connect(self._on_check_toggled)
        # Klik baris = pop-up detail (komponen sama dgn tab Anomali).
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        cl.addWidget(self._table, 1)

        hint = WLabel(
            "💡 🔴 merah = hari tersangka (puncak) · 🟠 amber = ≥ 2× rata-rata hari aktif · "
            "klik baris = detail · lepas centang ✓ = keluarkan dari daftar · sort klik header",
            card)
        hint.setObjectName("hint")
        cl.addWidget(hint)
        lay.addWidget(card, 1)

        # Pop-up detail — instance dipakai ulang (pola tab Anomali).
        self._popup = DetailDialog(ctx, self)

        # State ekspor (df baris + penanda warna) dari refresh terakhir.
        self._rows: pd.DataFrame | None = None
        self._red: dict[str, int] = {}
        self._amber: set[tuple[str, str]] = set()

        # Lazy render (pola H2): view tak terlihat → dirty; render saat
        # tab dibuka. Tidak terhubung ke filters_changed (by design).
        self._dirty = True
        ctx.data_ready.connect(self._on_data_ready)
        ctx.followup_changed.connect(self._on_followup_changed)

    # ------------------------------------------------------------
    # REAKSI STATE
    # ------------------------------------------------------------
    def _on_data_ready(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def _on_followup_changed(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data/state basi."""
        if self._dirty:
            self.refresh()

    # ------------------------------------------------------------
    # RENDER
    # ------------------------------------------------------------
    def refresh(self) -> None:
        self._dirty = False
        # V26-L12 / v2.10.3 (pola _refresh_table_impl Anomali): daftar
        # berubah → record terpilih + pop-up detail bisa basi (baris yang
        # ditampilkan pop-up mungkin sudah keluar dari daftar) — tutup +
        # kosongkan SEBELUM render ulang.
        self._table.clearSelection()
        self._popup.hide()
        self._popup._panel.clear()
        rows = self._ctx.followup_df()
        if rows is None:
            self._set_empty("Belum ada data — jalankan pipeline dulu "
                            "(tab Pipeline → Mulai Pipeline).")
            return
        if rows.empty:
            self._set_empty("Belum ada baris tercentang — buka tab Anomali, "
                            "centang kolom ✓ pada baris mencurigakan "
                            "(atau tombol ☑ Centang yang tampil).")
            return
        with busy_feedback(self._ctx.set_status, "Menyusun daftar follow-up"):
            self._rows = rows
            self._red, self._amber = suspicious_days(rows, rows[FP_COL])
            disp = rows.copy()
            # URUTAN KOLOM = format rekap PERSIS permintaan user (TOTAL·AVG·
            # MAX·SOURCE DATA·JENIS·KETERANGAN·NAMA BARANG·NAMA RESTO·
            # SATUAN·1..31) — urutan df sumber bisa lain (TOTAL belakang).
            # Kolom sisanya (skor, sinyal, peer…) ikut di belakang utk
            # pop-up detail (pola V26-C1: model pegang baris PENUH).
            ordered = ([c for c in FOLLOWUP_COLS if c in disp.columns]
                       + day_cols(disp))
            rest = [c for c in disp.columns
                    if c not in ordered and c != FP_COL]
            disp = disp[ordered + rest + ([FP_COL] if FP_COL in disp.columns else [])]
            # Semua baris di sini tercentang by definition (baris = hasil
            # seleksi key tercentang) — kolom ✓ semua True (posisi 0).
            disp.insert(0, CHECK_COL, [True] * len(disp))
            # red dari suspicious_days berbentuk {fp: hari} → konversi ke
            # himpunan (fp, kolom-hari) utk model (penanda level sel).
            red_hits = {(fp, str(day)) for fp, day in self._red.items()}
            self._table.model().set_highlights(red_hits, self._amber)
            visible = ([CHECK_COL]
                       + [c for c in FOLLOWUP_COLS if c in disp.columns]
                       + day_cols(disp))
            # Tanpa sort_desc (urutan dataset — deterministik) & tanpa
            # narrow_hide: format rekap = sheet lebar + scrollbar
            # horizontal (konvensi anti-terpotong: scroll ≠ terpotong).
            self._table.set_dataframe(disp, visible_cols=visible)
            n = len(disp)
            total = (pd.to_numeric(rows.get("TOTAL"), errors="coerce")
                     .fillna(0).sum() if "TOTAL" in rows.columns else 0)
            self._lbl_info.setText(
                f"{fmt_id(n)} baris · TOTAL gabungan {fmt_id(total)}")
            self._btn_export.setEnabled(True)
            self._btn_clear.setEnabled(True)

    def _set_empty(self, message: str) -> None:
        self._rows = None
        self._red, self._amber = {}, set()
        self._table.set_dataframe(None)
        self._lbl_info.setText(message)
        self._btn_export.setEnabled(False)
        self._btn_clear.setEnabled(False)

    # ------------------------------------------------------------
    # INTERAKSI
    # ------------------------------------------------------------
    def _on_check_toggled(self, row: int, checked: bool) -> None:
        """Lepas centang ✓ di tabel ini → keluarkan baris dari daftar."""
        rec = self._table.model().record(row)
        fp = rec.get(FP_COL) if rec is not None else None
        if fp is None or str(fp) == "nan":
            return
        self._ctx.toggle_followup(str(fp), checked)
        self._ctx.set_status(
            ("✓ Baris tetap di Follow Up" if checked
             else "✓ Baris dikeluarkan dari Follow Up"), "done")

    def _on_selection(self) -> None:
        rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    def _on_clear(self) -> None:
        n = len(self._ctx.followup_keys)
        if n == 0:
            return
        ans = QMessageBox.question(
            self, "Kosongkan Follow Up",
            f"Keluarkan SEMUA {fmt_id(n)} baris dari daftar follow-up?\n"
            "(Centangan ✓ di tab Anomali ikut lepas — tidak bisa dibatalkan.)")
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._ctx.clear_followup()
        self._ctx.set_status(f"✓ Daftar follow-up dikosongkan ({fmt_id(n)} baris)",
                             "done")

    def _on_export(self) -> None:
        if self._rows is None or self._rows.empty:
            QMessageBox.information(self, "Export",
                                    "Daftar follow-up masih kosong.")
            return
        from PySide6.QtWidgets import QFileDialog
        suggested = (f"Waste_FollowUp_"
                     f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Daftar Follow Up", suggested,
            "Excel files (*.xlsx);;All files (*.*)")
        if not path:
            return
        try:
            with busy_feedback(self._ctx.set_status,
                               "Menyimpan daftar follow-up"):
                out = export_followup_xlsx(self._rows, path,
                                           self._red, self._amber)
            self._ctx.log(f"=== Export Follow Up → {out} ===")
            self._ctx.set_status(f"✓ Daftar follow-up tersimpan: {out}", "done")
            QMessageBox.information(
                self, "Export Selesai",
                f"Daftar follow-up ({len(self._rows)} baris) tersimpan:\n{out}")
        except Exception as e:  # noqa: BLE001 — gagal tulis disk dsb.
            self._ctx.log(f"!!! Export follow-up gagal: {e}")
            self._ctx.set_status(f"⚠ Export follow-up gagal: {e}", "error")
            QMessageBox.critical(self, "Export Gagal", str(e))
