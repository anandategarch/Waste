"""view_update.py — v2.19.5 — tab "Update nilai" (staging koreksi batch).

Permintaan user: "bisa gak misal update nilai nya ke file rekap mentah
dikumpulin dulu terus baru proses dari pada proses satu per satu? Jadi
tombol simpan koreksi hari ke file excel diganti aja Pindah ke tab Update
nilai. Di tab update nilai itu buat tampung sementara nilai nilai yang
aku simpan dan akan diproses nanti nya."

ALUR BARU (gantikan simpan-satu-per-satu v2.16.0):
  1. User edit nilai hari di pop-up detail (tab Anomali) → klik
     "➡ Pindah ke tab Update nilai" (BUKAN "💾 Simpan koreksi" lagi).
  2. Koreksi ditampung ke ctx.pending_updates (list staging) + tab
     otomatis pindah ke "Update nilai" (signal ctx.update_staged).
  3. Tab Update nilai menampilkan tabel staging: file sumber, item,
     resto, baris Excel, hari (lama→baru), status, waktu ditambah.
  4. User review: hapus baris terpilih / kosongkan semua.
  5. Klik "💾 Proses semua ke file Excel" → BatchUpdateWorker tulis
     SEMUA staging ke file Excel sumber (loop per entry, backup=False,
     langsung timpa — permintaan user v2.19.4 "jangan buat back up").
  6. Hasil: entry 'done' (✓ tersimpan) / 'failed' (✗ alasan). Entry
     gagal TETAP di staging utk retry setelah user tutup Excel; entry
     sukses bisa dibersihkan (tombol "Buang yg sudah tersimpan").

Tabel = QTableWidget (bukan DataTable) — list staging kecil + dinamis
(status berubah tiap proses); QTableWidget lebih ringan utk mutasi
baris ad-hoc daripada model pandas.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .state import AppContext
from .widgets import Card, WLabel, busy_feedback
from .workers import BatchUpdateWorker

# Kolom tabel staging (urutan = tampil).
_COLS = (
    "#", "File sumber", "Item", "Resto", "Baris Excel",
    "Hari (lama → baru)", "Status", "Ditambahkan",
)


def _fmt_day_edits(day_edits: dict, day_orig: dict) -> str:
    """Format kolom 'Hari (lama → baru)': '5: 100 → 55; 13: 0 → 200'."""
    if not day_edits:
        return ""
    parts = []
    for day in sorted(day_edits, key=lambda d: int(d) if str(d).isdigit() else 0):
        new = day_edits[day]
        old = day_orig.get(day, 0.0)
        parts.append(f"{day}: {_fmt_num(old)} → {_fmt_num(new)}")
    return "; ".join(parts)


def _fmt_num(v) -> str:
    """Format angka: int bulat tanpa desimal, else 2 desimal."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v) if v is not None else ""
    if f.is_integer():
        return str(int(f))
    return f"{f:.2f}"


class UpdateView(QWidget):
    """Tab 'Update nilai' — tampung sementara koreksi + proses batch."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: BatchUpdateWorker | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        card = Card(self)
        card.setMinimumHeight(240)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        title = WLabel(
            "Update nilai — kumpulkan koreksi, proses sekaligus", card)
        title.setObjectName("cardTitle")
        title.setToolTip(
            "Alur baru (v2.19.5):\n"
            "  1. Edit nilai hari di pop-up detail (tab Anomali).\n"
            "  2. Klik '➡ Pindah ke tab Update nilai' — koreksi ditampung\n"
            "     di tabel ini (BELUM ditulis ke file Excel).\n"
            "  3. Kumpulkan beberapa koreksi (item/hari berbeda).\n"
            "  4. Klik '💾 Proses semua ke file Excel' — tulis SEMUA\n"
            "     koreksi ke file REKAP MENTAH sumber (langsung timpa,\n"
            "     tanpa backup — sesuai permintaan Anda).\n"
            "  5. Entry gagal (file dibuka Excel?) tetap di daftar utk\n"
            "     diulang setelah Anda tutup Excel lalu klik Proses lagi.\n\n"
            "Tips: tutup file Excel sumber sebelum klik Proses supaya tak\n"
            "kena WinError 5 (akses ditolak).")
        cl.addWidget(title)
        desc = WLabel(
            "Koreksi yang Anda kumpulkan di tab Anomali tertampung di sini. "
            "Saat sudah siap, klik “Proses semua ke file Excel” — semua "
            "koreksi ditulis sekaligus ke file REKAP MENTAH sumber.", card)
        desc.setObjectName("hint")
        desc.setWordWrap(True)
        cl.addWidget(desc)

        # Bar kontrol: info jumlah + tombol.
        ctrl = QWidget(card)
        rl = QHBoxLayout(ctrl)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        self._lbl_info = WLabel("", ctrl)
        self._lbl_info.setObjectName("hint")
        rl.addWidget(self._lbl_info, 1)
        self._btn_remove = QPushButton("🗑 Hapus terpilih", ctrl)
        self._btn_remove.setToolTip(
            "Buang baris terpilih dari daftar staging (BELUM ditulis ke "
            "file Excel — aman dibatalkan selama belum diproses).")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        rl.addWidget(self._btn_remove)
        self._btn_clear_done = QPushButton("↺ Buang yg sudah tersimpan", ctrl)
        self._btn_clear_done.setToolTip(
            "Bersihkan entry ber-status ✓ Tersimpan. Entry ✗ Gagal tetap "
            "(utk diulang).")
        self._btn_clear_done.clicked.connect(self._on_clear_done)
        rl.addWidget(self._btn_clear_done)
        self._btn_clear_all = QPushButton("🗑 Kosongkan semua", ctrl)
        self._btn_clear_all.setToolTip(
            "Buang SELURUH daftar staging (pending + hasil). Konfirmasi "
            "diberikan — tindakan tak bisa dibatalkan.")
        self._btn_clear_all.clicked.connect(self._on_clear_all)
        rl.addWidget(self._btn_clear_all)
        self._btn_process = QPushButton("💾 Proses semua ke file Excel", ctrl)
        self._btn_process.setStyleSheet(
            "QPushButton { background:#dc2626; color:white; font-weight:700; "
            "border:none; padding:8px 14px; border-radius:5px; }"
            "QPushButton:hover { background:#b91c1c; }"
            "QPushButton:disabled { background:#cbd5e1; color:#94a3b8; }")
        self._btn_process.setToolTip(
            "Tulis SEMUA koreksi staging ke file Excel sumber (REKAP "
            "MENTAH) sekaligus.\nLangsung timpa file asli — tanpa backup "
            "(permintaan Anda).\nTutup file di Excel dulu supaya tak "
            "kena WinError 5 (akses ditolak).")
        self._btn_process.clicked.connect(self._on_process)
        rl.addWidget(self._btn_process)
        cl.addWidget(ctrl)

        # Tabel staging.
        self._table = QTableWidget(0, len(_COLS), card)
        self._table.setHorizontalHeaderLabels(list(_COLS))
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.ResizeToContents)  # #
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Stretch)           # File
        hdr.setSectionResizeMode(2, hdr.ResizeMode.ResizeToContents)  # Item
        hdr.setSectionResizeMode(3, hdr.ResizeMode.ResizeToContents)  # Resto
        hdr.setSectionResizeMode(4, hdr.ResizeMode.ResizeToContents)  # Baris
        hdr.setSectionResizeMode(5, hdr.ResizeMode.Stretch)           # Hari
        hdr.setSectionResizeMode(6, hdr.ResizeMode.ResizeToContents)  # Status
        hdr.setSectionResizeMode(7, hdr.ResizeMode.ResizeToContents)  # Ditambahkan
        cl.addWidget(self._table, 1)

        lay.addWidget(card)

        # Wire signal ctx — refresh saat staging berubah.
        self._ctx.updates_changed.connect(self.refresh)
        # Initial render (kosong saat startup).
        self.refresh()

    # ------------------------------------------------------------
    # Kontrak lazy-render (test_ui_structure DATA_VIEWS)
    # ------------------------------------------------------------
    def refresh(self) -> None:
        """Re-render tabel dari ctx.pending_updates + update info/badge."""
        entries = self._ctx.pending_updates
        self._table.setRowCount(0)
        for i, e in enumerate(entries):
            self._table.insertRow(i)
            self._set_cell(i, 0, str(i + 1))
            self._set_cell(i, 1, Path(e.get("source", "")).name)
            self._set_cell(
                i, 2,
                f"{e.get('jenis', '')} · {e.get('barang', '')}".strip(" ·"))
            self._set_cell(i, 3, str(e.get("resto", "") or ""))
            rows = e.get("src_rows") or []
            self._set_cell(
                i, 4,
                ", ".join(f"#{r}" for r in rows) if rows else "—")
            self._set_cell(
                i, 5,
                _fmt_day_edits(e.get("day_edits") or {}, e.get("day_orig") or {}))
            status = e.get("status", "pending")
            status_txt, color = _status_render(status, e.get("error"))
            self._set_cell(i, 6, status_txt, color)
            self._set_cell(i, 7, str(e.get("added_at", "")))
        # Info label: jumlah pending/done/failed.
        n_total = len(entries)
        n_done = sum(1 for e in entries if e.get("status") == "done")
        n_fail = sum(1 for e in entries if e.get("status") == "failed")
        n_pending = n_total - n_done - n_fail
        self._lbl_info.setText(
            f"Total {n_total} koreksi — pending {n_pending} · "
            f"✓ tersimpan {n_done} · ✗ gagal {n_fail}")
        # Enabled-state tombol.
        has_rows = n_total > 0
        has_pending = n_pending > 0 or n_fail > 0
        self._btn_remove.setEnabled(has_rows and self._worker is None)
        self._btn_clear_done.setEnabled(n_done > 0 and self._worker is None)
        self._btn_clear_all.setEnabled(has_rows and self._worker is None)
        self._btn_process.setEnabled(has_pending and self._worker is None)

    def on_shown(self) -> None:
        """Dipanggil MainWindow saat tab dibuka — refresh staging (mungkin
        baru ditambah dari tab Anomali)."""
        self.refresh()

    # ------------------------------------------------------------
    # Helper tabel
    # ------------------------------------------------------------
    def _set_cell(self, row: int, col: int, text: str,
                  color: QColor | None = None) -> None:
        item = QTableWidgetItem(text)
        if color is not None:
            item.setForeground(color)
        self._table.setItem(row, col, item)

    def _selected_entry_idx(self) -> int | None:
        """Index ctx.pending_updates dari baris terpilih (atau None)."""
        row = self._table.currentRow()
        if row < 0 or row >= self._table.rowCount():
            return None
        # Kolom # berisi idx+1 (label 1-based); kembali ke 0-based.
        item = self._table.item(row, 0)
        if item is None:
            return None
        try:
            return int(item.text()) - 1
        except ValueError:
            return None

    # ------------------------------------------------------------
    # Aksi tombol
    # ------------------------------------------------------------
    def _on_remove_selected(self) -> None:
        idx = self._selected_entry_idx()
        if idx is None:
            QMessageBox.information(
                self, "Tidak ada baris",
                "Pilih baris di tabel dulu, lalu klik 'Hapus terpilih'.")
            return
        e = self._ctx.pending_updates[idx]
        confirm = QMessageBox.question(
            self, "Hapus baris staging",
            f"Hapus koreksi ini dari daftar?\n"
            f"  Item: {e.get('barang', '')} · {e.get('resto', '')}\n"
            f"  Hari: {_fmt_day_edits(e.get('day_edits') or {}, e.get('day_orig') or {})}\n\n"
            f"(Belum ditulis ke file Excel — aman dibatalkan.)")
        if confirm == QMessageBox.StandardButton.Yes:
            self._ctx.remove_update(idx)

    def _on_clear_done(self) -> None:
        n = self._ctx.clear_processed_updates()
        if n:
            self._ctx.set_status(
                f"{n} koreksi tersimpan dibersihkan dari daftar.", "done")

    def _on_clear_all(self) -> None:
        if not self._ctx.pending_updates:
            return
        confirm = QMessageBox.question(
            self, "Kosongkan seluruh daftar",
            f"Buang SEMUA {len(self._ctx.pending_updates)} koreksi dari "
            f"daftar staging?\n\n"
            f"Entry ✓ Tersimpan: file Excel SUDAH ditulis (tak terpengaruh).\n"
            f"Entry pending/✗ Gagal: koreksi HILANG dari daftar (belum "
            f"ditulis ke Excel) — harus diinput ulang via tab Anomali.\n\n"
            f"Tindakan tak bisa dibatalkan.")
        if confirm == QMessageBox.StandardButton.Yes:
            n = self._ctx.clear_updates()
            self._ctx.set_status(f"{n} koreksi dibuang dari daftar.", "info")

    def _on_process(self) -> None:
        """Start BatchUpdateWorker — tulis semua staging ke file Excel."""
        if self._worker is not None:
            QMessageBox.information(
                self, "Proses sedang berjalan",
                "Proses batch sebelumnya masih berjalan di background.\n"
                "Tunggu sebentar lalu coba lagi.")
            return
        entries = self._ctx.pending_updates
        n_pending = self._ctx.pending_unprocessed_count()
        n_fail = sum(1 for e in entries if e.get("status") == "failed")
        n_to_process = n_pending + n_fail
        if n_to_process == 0:
            QMessageBox.information(
                self, "Tidak ada yang diproses",
                "Tidak ada koreksi pending/failed untuk diproses.")
            return
        # Konfirmasi: daftar file yg akan ditulis + jumlah koreksi.
        files = sorted({Path(e["source"]).name
                        for e in entries if e.get("status") != "done"})
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setWindowTitle("Konfirmasi Proses Batch")
        confirm.setText(
            f"Akan menulis {n_to_process} koreksi ke file Excel sumber:\n\n"
            f"  File: {', '.join(files)}\n"
            f"  Total entry: {len(entries)} (pending {n_pending} + "
            f"retry failed {n_fail})\n\n"
            f"Langsung timpa file asli — tanpa backup.\n"
            f"TOTAL per baris dihitung ulang = sum hari 1-31.\n\n"
            f"PENTING: tutup file Excel sumber dulu bila terbuka (anti "
            f"WinError 5). Lanjutkan?")
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            self._ctx.set_status("Proses batch dibatalkan user.", "info")
            return
        confirm.deleteLater()
        # Start worker.
        self._worker = BatchUpdateWorker(entries, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._worker.deleteLater)
        # Disable tombol selama proses.
        self._btn_process.setEnabled(False)
        self._btn_process.setText("⏳ Memproses…")
        self._btn_remove.setEnabled(False)
        self._btn_clear_done.setEnabled(False)
        self._btn_clear_all.setEnabled(False)
        self._ctx.set_status(
            f"Memproses {n_to_process} koreksi ke file Excel (background)…",
            "running")
        self._ctx.log(f"[update-nilai] mulai proses batch: {n_to_process} "
                      f"koreksi ke {len(files)} file")
        self._worker.start()

    @busy_feedback
    def _on_progress(self, idx: int, ok: bool, msg: str) -> None:
        """Worker selesai satu entry — update status + log."""
        status = "done" if ok else "failed"
        self._ctx.mark_update_status(idx, status, error=None if ok else msg)
        e = self._ctx.pending_updates[idx]
        mark = "✓" if ok else "✗"
        self._ctx.log(
            f"[update-nilai] {mark} entry #{idx + 1} "
            f"({e.get('barang', '')} · {e.get('resto', '')}): {msg}")
        # refresh() dipicu updates_changed dari mark_update_status — tabel
        # otomatis update status baris.

    def _on_done(self, n_ok: int, n_fail: int) -> None:
        """Worker selesai seluruh batch — ringkasan + reset UI."""
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._btn_process.setText("💾 Proses semua ke file Excel")
        self._btn_process.setEnabled(self._ctx.pending_unprocessed_count() > 0
                                     or any(e.get("status") == "failed"
                                            for e in self._ctx.pending_updates))
        self._btn_remove.setEnabled(len(self._ctx.pending_updates) > 0)
        self._btn_clear_done.setEnabled(
            any(e.get("status") == "done" for e in self._ctx.pending_updates))
        self._btn_clear_all.setEnabled(len(self._ctx.pending_updates) > 0)
        # Ringkasan dialog.
        total = n_ok + n_fail
        if n_fail == 0:
            self._ctx.set_status(
                f"Selesai: {n_ok} koreksi tersimpan ke file Excel. "
                f"Re-run pipeline utk refresh tabel.", "done")
            QMessageBox.information(
                self, "Proses selesai",
                f"✓ {n_ok} koreksi tersimpan ke file Excel.\n\n"
                f"Re-run pipeline (tab Pipeline → Mulai) supaya tabel "
                f"Anomali/Hari memuat nilai baru.")
        else:
            self._ctx.set_status(
                f"Selesai: {n_ok} tersimpan, {n_fail} gagal (lihat daftar).",
                "error" if n_ok == 0 else "running")
            QMessageBox.warning(
                self, "Proses selesai (parsial)",
                f"✓ {n_ok} koreksi tersimpan ke file Excel.\n"
                f"✗ {n_fail} koreksi GAGAL — lihat kolom Status di tabel.\n\n"
                f"Umumnya gagal karena file Excel sumber sedang DIBUKA di "
                f"Excel (mengunci file). TUTUP file-nya, lalu klik "
                f"'💾 Proses semua' lagi utk mengulang entry gagal "
                f"(entry yg sudah ✓ tersimpan tak akan ditulis ulang).")
        self._ctx.log(
            f"[update-nilai] SELESAI: {n_ok} ok, {n_fail} gagal dari "
            f"{total} entry.")
        self.refresh()


def _status_render(status: str, error: str | None) -> tuple[str, QColor]:
    """Render kolom Status: teks + warna fg."""
    if status == "done":
        return "✓ Tersimpan", QColor("#16a34a")
    if status == "failed":
        # Teks error dipotong (tooltip kolom? — tampilkan ringkas).
        err = (error or "").split("\n")[0][:60]
        return f"✗ Gagal — {err}", QColor("#dc2626")
    return "⏳ Pending", QColor("#475569")
