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

v2.12.3:
- Kolom TOTAL BULAN LALU + PERUBAHAN % muncul bila pembanding dimuat
  (change_vs_history — match resto×item×jenis×keterangan; PERUBAHAN %
  negatif otomatis merah; judul alias 'TOTAL BULAN LALU', kanonik tetap).
- Funnel filter di header tabel = filter LOKAL tampilan (shortlist,
  ✓ dan ekspor tak tersentuh) + tombol sort di menu funnel.

v2.12.4:
- Funnel di SEMUA kolom (termasuk hari 1-31 — permintaan user
  "harusnya semua kolom punya filter"); masih filter lokal tampilan.
- Hint '💡 🔴 merah = hari tersangka...' DIHAPUS (permintaan user:
  kalimat penjelas dihapus dari UI — keterangan warna pindah ke
  tooltip judul kartu).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
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
    import_followup_workbook,
    suspicious_days,
)
from waste_anomaly.period_history import change_vs_history

from .shared import fmt_id
from .state import AppContext
from .view_anomali import DetailDialog
from .widgets import Card, DataTable, WLabel, busy_feedback

# v2.12.4: funnel di header = SEMUA kolom (termasuk hari 1–31) — filter
# LOKAL tampilan (BUKAN ctx: shortlist menetap by design — hanya
# menyaring yang tampil; daftar ✓ & ekspor tak tersentuh).
_HF_SKIP = (CHECK_COL, FP_COL)


class FollowUpView(QWidget):
    """View 'Follow Up': tabel rekap baris tercentang + ekspor."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        # v2.12.3: filter LOKAL tampilan per kolom {kolom: nilai terpilih}
        # — shortlist menetap; hanya tampilan yang tersaring. (Didefinisikan
        # SEBELUM pembuatan tabel — dipakai sbg state_fn funnel header.)
        self._hfilters: dict[str, list] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        card = Card(self)
        card.setMinimumHeight(240)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        title = WLabel("Daftar Follow Up — baris tercentang (✓) di tab "
                       "Anomali & Banding Periode", card)
        title.setObjectName("cardTitle")
        title.setToolTip(
            "Kumpulan baris anomali yang Anda centang (kolom ✓) di tab "
            "Anomali, ATAU baris tabel banding (tab Banding Periode — "
            "halaman Cabang/Item: satu centang = baris ANOMALI resto/item "
            "itu masuk — baris Normal tidak ikut, jadi umumnya tepat 1 "
            "baris per item per resto).\nDaftar ini TIDAK terpengaruh "
            "filter — baris yang sudah dikumpulkan menetap.\nHari "
            "mencurigakan diberi warna: merah = hari tersangka (puncak); "
            "amber = nilai ≥ 2× rata-rata hari aktif.\nKolom TOTAL "
            "BULAN LALU + PERUBAHAN % muncul bila file pembanding dimuat "
            "di tab Banding Periode.\nTertutup aplikasi pun aman: daftar "
            "tersimpan otomatis (followup.json).")
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
        # v2.13.3 (⑯): re-import sheet hasil TL terisi → status Selesai.
        self._btn_import = QPushButton("📥 Impor Hasil TL", ctrl)
        self._btn_import.setToolTip(
            "Baca kembali file ekspor yang SUDAH DIISI petugas\n"
            "(kolom PIC / KATEGORI / PENYEBAB di sheet 'FOLLOW UP') →\n"
            "baris yang cocok diberi status 'Selesai' + PIC-nya tampil.\n"
            "Kecocokan = nilai baris (kolom kunci + hari 1-31) — aman\n"
            "walau sheet di-sort/di-filter di Excel. Tersimpan di\n"
            "followup_resolved.json.")
        self._btn_import.clicked.connect(self._on_import)
        rl.addWidget(self._btn_import)
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
        # v2.12.3: funnel filter LOKAL tampilan + opsi sort di header.
        # v2.12.4: SEMUA kolom ber-funnel (skip ✓ + __FP).
        self._table.setup_header_filters(
            None, self._on_header_filter, self._hfilters.get,
            all_cols=True, skip=_HF_SKIP)
        # Klik baris = pop-up detail (komponen sama dgn tab Anomali).
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        cl.addWidget(self._table, 1)

        lay.addWidget(card, 1)

        # Pop-up detail — instance dipakai ulang (pola tab Anomali).
        self._popup = DetailDialog(ctx, self)

        # State ekspor (df baris + penanda warna) dari refresh terakhir.
        self._rows: pd.DataFrame | None = None
        self._red: dict[str, int] = {}
        self._amber: set[tuple[str, str]] = set()
        self._disp: pd.DataFrame | None = None
        self._visible: list[str] | None = None

        # Lazy render (pola H2): view tak terlihat → dirty; render saat
        # tab dibuka. Tidak terhubung ke filters_changed (by design).
        self._dirty = True
        ctx.data_ready.connect(self._on_data_ready)
        ctx.followup_changed.connect(self._on_followup_changed)
        # v2.12.3: pembanding (bulan lalu) siap / combo berganti → kolom
        # TOTAL BULAN LALU + PERUBAHAN % muncul / dihitung ulang (pola
        # view_hari._on_history_ready).
        ctx.history_ready.connect(self._on_history_ready)
        ctx.baseline_changed.connect(self._on_history_ready)

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

    def _on_history_ready(self) -> None:
        """v2.12.3: pembanding siap / berganti → kolom bulan lalu muncul."""
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
                            "(atau tombol ☑ Centang yang tampil / centang "
                            "✓ di tab Banding Periode).")
            return
        with busy_feedback(self._ctx.set_status, "Menyusun daftar follow-up"):
            self._rows = rows
            self._red, self._amber = suspicious_days(rows, rows[FP_COL])
            # v2.12.3 — TOTAL BULAN LALU + PERUBAHAN % (permintaan user:
            # "tampilkan juga total bulan lalu"): enrich vs baseline
            # pembanding bila tersedia (pola view_anomali v2.10.2 —
            # change_vs_history additive, merge vektor ~ms utk ratusan
            # baris). Tanpa pembanding: tabel identik dulu (kolom absen).
            baseline = self._ctx.banding_baseline_effective()
            if baseline is not None:
                disp = change_vs_history(rows, baseline, self._ctx.config)
            else:
                disp = rows.copy()
            # URUTAN KOLOM = format rekap PERSIS permintaan user (TOTAL·
            # [TOTAL BULAN LALU·PERUBAHAN % bila ada]·AVG·MAX·SOURCE
            # DATA·JENIS·KETERANGAN·NAMA BARANG·NAMA RESTO·SATUAN·1..31)
            # — urutan df sumber bisa lain (TOTAL belakang).
            # Kolom sisanya (skor, sinyal, peer…) ikut di belakang utk
            # pop-up detail (pola V26-C1: model pegang baris PENUH).
            base_cols = [c for c in FOLLOWUP_COLS if c in disp.columns]
            if "BULAN LALU" in disp.columns:
                base_cols = (
                    ["TOTAL", "BULAN LALU", "PERUBAHAN %"]
                    + [c for c in base_cols
                       if c not in ("TOTAL", "BULAN LALU", "PERUBAHAN %")])
            # v2.13.3 (⑯): status tindak lanjut hasil re-import — kolom
            # pertama supaya terlihat tanpa scroll horizontal.
            resolved = self._ctx.followup_resolved
            if resolved:
                fp_vals = disp[FP_COL].astype(str) if FP_COL in disp.columns \
                    else pd.Series([""] * len(disp), index=disp.index)
                disp = disp.copy()
                disp["STATUS TL"] = [
                    "Selesai" if fp in resolved else "—"
                    for fp in fp_vals]
                disp["PIC"] = [
                    str(resolved.get(fp, {}).get("PIC", "") or "—")
                    if fp in resolved else "—"
                    for fp in fp_vals]
                base_cols = ["STATUS TL", "PIC"] + base_cols
            ordered = base_cols + day_cols(disp)
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
            # v2.12.3: judul kolom 'BULAN LALU' tampil sbg 'TOTAL BULAN
            # LALU' (nama kanonik tetap — kontrak konsumen/test utuh;
            # alias di headerData, pola tab Banding v2.12.2).
            alias_map = ({"BULAN LALU": "TOTAL BULAN LALU"}
                         if "BULAN LALU" in disp.columns else None)
            self._table.model().set_header_map(alias_map)
            visible = ([CHECK_COL] + base_cols + day_cols(disp))
            if alias_map:
                # set_dataframe membandingkan nama JUDUL (alias!) dgn
                # visible_cols → alias kolom ter-rename WAJIB ikut masuk
                # daftar, kalau tidak kolomnya disembunyikan.
                visible = visible + [alias_map[c] for c in base_cols
                                     if c in alias_map]
            # Tanpa sort_desc (urutan dataset — deterministik) & tanpa
            # narrow_hide: format rekap = sheet lebar + scrollbar
            # horizontal (konvensi anti-terpotong: scroll ≠ terpotong).
            self._table.set_dataframe(disp, visible_cols=visible)
            # v2.12.3: simpan bahan render + terapkan filter lokal
            # (mask murah — tanpa hitung ulang suspicious_days).
            self._disp = disp
            self._visible = list(visible)
            shown = self._apply_hfilter(disp)
            if shown is not disp:
                self._table.set_dataframe(shown, visible_cols=visible)
            self._table.setup_header_filters(
                None, self._on_header_filter, self._hfilters.get,
                all_cols=True, skip=_HF_SKIP)
            n = len(shown)
            total = (pd.to_numeric(rows.get("TOTAL"), errors="coerce")
                     .fillna(0).sum() if "TOTAL" in rows.columns else 0)
            label_b = str(baseline.get("label") or "") if baseline else ""
            # v2.13.3: hitungan penyelesaian tindak lanjut (⑯)
            n_done = sum(
                1 for fp in rows[FP_COL].astype(str)
                if fp in self._ctx.followup_resolved) \
                if FP_COL in rows.columns else 0
            done_part = (f" · selesai {fmt_id(n_done)}/{fmt_id(n)}"
                         if self._ctx.followup_resolved else "")
            self._lbl_info.setText(
                f"{fmt_id(n)} baris · TOTAL gabungan {fmt_id(total)}"
                + done_part
                + (f" · pembanding: {label_b}" if label_b else ""))
            self._btn_export.setEnabled(True)
            self._btn_clear.setEnabled(True)

    def _set_empty(self, message: str) -> None:
        self._rows = None
        self._disp = None
        self._red, self._amber = {}, set()
        self._table.set_dataframe(None)
        self._lbl_info.setText(message)
        self._btn_export.setEnabled(False)
        self._btn_clear.setEnabled(False)

    # ------------------------------------------------------------
    # v2.12.3 — FILTER LOKAL TAMPILAN (funnel header)
    # ------------------------------------------------------------
    def _on_header_filter(self, col: str, key: str, values) -> None:
        """Menu funnel header → saring TAMPILAN saja (daftar follow-up
        & ekspor tak tersentuh — shortlist menetap by design)."""
        if values:
            self._hfilters[col] = list(values)
        else:
            self._hfilters.pop(col, None)
        if self._disp is not None and self._visible is not None:
            shown = self._apply_hfilter(self._disp)
            self._table.set_dataframe(shown, visible_cols=self._visible)
        n = len(self._hfilters)
        self._ctx.set_status(
            f"⧩ Filter tampilan ({n} kolom) diterapkan — daftar follow-up "
            "tidak berubah", "done")

    def _apply_hfilter(self, disp: pd.DataFrame) -> pd.DataFrame:
        """Mask isin per kolom terpilih (murah — ratusan baris)."""
        if not self._hfilters:
            return disp
        m = pd.Series(True, index=disp.index)
        for col, vals in self._hfilters.items():
            if col in disp.columns and vals:
                m &= disp[col].isin(vals)
        out = disp[m]
        return out if len(out) else disp.iloc[:0]

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
                     f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")  # noqa: DTZ005
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

    def _on_import(self) -> None:
        """⑯ v2.13.3: baca file ekspor yang sudah diisi petugas →
        baris cocok diberi status 'Selesai' (persist + refresh in-place)."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Hasil Tindak Lanjut (sheet FOLLOW UP terisi)",
            str(Path.home() / "Documents"),
            "Excel files (*.xlsx *.xlsm);;All files (*.*)")
        if not path:
            return
        with busy_feedback(self._ctx.set_status,
                           "Membaca hasil tindak lanjut"):
            res = import_followup_workbook(path, self._ctx.config)
        if res.get("error"):
            self._ctx.set_status(f"⚠ Impor TL gagal: {res['error']}",
                                 "error")
            QMessageBox.critical(self, "Impor Hasil TL",
                                 str(res["error"]))
            return
        resolved = res.get("resolved") or {}
        n_rows = int(res.get("n_rows", 0))
        n_filled = int(res.get("n_filled", 0))
        # berapa yang cocok dgn daftar saat ini (info jujur — baris di
        # file yang TIDAK ada di daftar tetap disimpan (data berguna bila
        # barisnya dicentang lagi nanti), tapi dilaporkan terpisah).
        in_list = sum(1 for fp in resolved
                      if fp in self._ctx.followup_set())
        changed = self._ctx.apply_followup_resolved(resolved)
        self._ctx.log(
            f"=== Impor Hasil TL ← {res.get('file')} — {n_filled} baris "
            f"terisi, {in_list} cocok dgn daftar, {changed} status baru ===")
        msg = (f"File: {res.get('file')}\n"
               f"{fmt_id(n_rows)} baris dibaca · {fmt_id(n_filled)} baris "
               f"terisi petugas.\n"
               f"{fmt_id(in_list)} cocok dengan daftar follow-up saat ini · "
               f"{fmt_id(changed)} status diperbarui.")
        if in_list < n_filled:
            msg += ("\n\nCatatan: baris terisi yang belum ada di daftar "
                    "sekarang tetap disimpan — statusnya aktif otomatis "
                    "bila barisnya dicentang lagi.")
        self._ctx.set_status(
            f"✓ Impor hasil TL: {n_filled} terisi, {in_list} cocok", "done")
        QMessageBox.information(self, "Impor Hasil TL", msg)
