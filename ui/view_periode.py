"""view_periode.py — view 'Banding Periode' multi-file (v2.10.0).

Desain disetujui user (worklog Task 9 + jawaban 5 pertanyaan):
- Pembanding = DAFTAR workbook (1 file = 1 bulan, template standar
  "REKAP MENTAH" — kuantiti tanpa BOM). Nama bulan dibaca OTOMATIS dari
  nama file ("...AGUSTUS 2026..." → "Agustus 2026"), bisa dikoreksi
  manual (klik 2× baris).
- Dua-duanya: banding vs 1 bulan pilihan + "Tipikal" (median gabungan
  ≥ 2 bulan) — combo di kartu hasil.
- Daftar file DIINGAT antar sesi (history_files.json, atomic — pola
  filters.py); dimuat ulang otomatis di background saat aplikasi dibuka.
- Muat di HistoryWorker (QThread + progress + cancel) — UI tidak beku
  (standar anti-lambat). File gagal → baris merah + pesan, file lain jalan.
- Perbandingan MURNI KUANTITI (compare_quantity): Total Waste, Waste per
  Hari (menormalkan beda 30/31 hari), cabang/item mover, item baru/hilang.

Istilah awam + tooltip di semua kontrol (kebijakan v2.9.0).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.period_history import (
    aggregate_current,
    compare_quantity,
    detect_month_label,
    load_history_entries,
    month_sort_key,
    save_history_entries,
    typical_months,
)

from .shared import fmt_id
from .state import AppContext
from .widgets import Card, DataTable, WLabel, busy_feedback
from .workers import HistoryWorker

_PAGES = [
    ("summary", "📊 Ringkasan"),
    ("per_jenis", "🧾 Per Jenis"),
    ("branch", "🏬 Cabang Mover"),
    ("items", "📦 Item Mover"),
    ("new_items", "🆕 Item Baru"),
    ("gone_items", "📉 Item Hilang"),
]

# key dict hasil compare_quantity → (df, label) — kontrak TERKUNCI test
# wave1 (V26-H3): nilai HARUS kunci dict hasil (compare_periods lama maupun
# compare_quantity v2.10.0 memakai nama kunci yang sama).
_RESULT_KEYS = {
    "summary": "summary",
    "per_jenis": "per_jenis",
    "branch": "branch",
    "items": "items",
    "new_items": "new_items",
    "gone_items": "gone_items",
}

# Penanda userData combo: pilihan tipikal gabungan vs index bulan.
_TYPICAL_KEY = "__tipikal__"


class PeriodeView(QWidget):
    """View 'Banding Periode': bulan berjalan vs daftar bulan pembanding."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: HistoryWorker | None = None
        self._running = False
        # Kontrak lazy-render + stale-result (pola lama dipertahankan).
        self._dirty = True
        self._has_result = False
        self._result_version: tuple[int, int] | None = None
        # Daftar file (persisten): [{"path":…, "label":…|None}]
        self._entries: list[dict] = []
        # Cache hasil muat per path (hanya entri SUKSES — entri error
        # di-retry otomatis pada pemuatan berikutnya). Key = path,
        # divalidasi dgn (mtime, size) — file diganti → dimuat ulang.
        self._loaded: dict[str, dict] = {}
        self._loaded_sig: dict[str, tuple] = {}
        self._last_results: dict[str, dict] = {}
        # Memo agregat bulan berjalan (A) — per data_version + key_akhir.
        self._a_cache: tuple[int, int, dict] | None = None
        # Versi history saat combo terakhir diisi ulang — combo selalu
        # disinkronkan di _refresh_result (satu tempat, tanpa render ganda:
        # _finalize hanya set_history; sinyal → _refresh_result → rebuild).
        self._combo_version: int = -1

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        lay.addWidget(self._build_card_files())
        lay.addWidget(self._build_card_result(), 1)

        ctx.data_ready.connect(self._on_data_ready)
        ctx.history_ready.connect(self._on_history_ready)

        # Muat daftar tersimpan → auto-load background (user: "ya boleh
        # diingat"). Konstruktor berjalan saat app dibuka; worker QThread
        # tidak memblokir UI startup.
        self._entries = load_history_entries()
        self._render_file_list()
        if self._entries:
            self._start_worker()

    # ------------------------------------------------------------
    # BANGUN UI
    # ------------------------------------------------------------
    def _build_card_files(self) -> Card:
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("🔀 Banding Periode — bulan berjalan vs bulan-bulan sebelumnya", card)
        ttl.setObjectName("cardTitle")
        cl.addWidget(ttl)
        hint = WLabel(
            "💡 Tambahkan file rekap bulan lalu (1 file = 1 bulan, format REKAP MENTAH "
            "— cukup kolom nama barang, resto, satuan & hari 1-31, tanpa angka BOM). "
            "Nama bulan dibaca otomatis dari nama file; klik 2× baris untuk mengoreksi. "
            "Semua file dimuat di latar belakang — aplikasi tetap responsif.", card)
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)

        row = QWidget(card)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self._tbl_files = QTableWidget(0, 3, row)
        self._tbl_files.setHorizontalHeaderLabels(["Bulan", "File", "Status"])
        self._tbl_files.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_files.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_files.verticalHeader().setVisible(False)
        self._tbl_files.setAlternatingRowColors(True)
        head = self._tbl_files.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl_files.setMinimumHeight(120)
        self._tbl_files.setToolTip(
            "Daftar file pembanding (diingat antar sesi).\n"
            "Klik 2× kolom Bulan untuk memberi/koreksi nama bulan.")
        self._tbl_files.doubleClicked.connect(self._on_double)
        rl.addWidget(self._tbl_files, 1)

        btns = QWidget(row)
        bl = QVBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        self._btn_add = QPushButton("＋ Tambah File…", btns)
        self._btn_add.setToolTip(
            "Pilih satu atau beberapa workbook bulan lalu "
            "(bisa multi-pilih sekaligus).")
        self._btn_add.clicked.connect(self._on_add)
        bl.addWidget(self._btn_add)
        self._btn_del = QPushButton("🗑 Hapus Pilihan", btns)
        self._btn_del.setToolTip("Hapus file terpilih dari daftar pembanding\n"
                                 "(file aslinya tidak dihapus).")
        self._btn_del.clicked.connect(self._on_delete)
        bl.addWidget(self._btn_del)
        self._btn_run = QPushButton("🔄 Muat Ulang", btns)
        self._btn_run.setToolTip("Baca ulang SEMUA file pembanding dari disk\n"
                                 "(mis. setelah file diperbarui).")
        self._btn_run.clicked.connect(self._on_reload)
        bl.addWidget(self._btn_run)
        bl.addStretch(1)
        rl.addWidget(btns)
        cl.addWidget(row, 1)

        self._lbl_a = WLabel("Bulan berjalan: (belum ada run)", card)
        self._lbl_a.setStyleSheet("font-weight:600;")
        cl.addWidget(self._lbl_a)
        self._lbl_status = WLabel("Siap — belum ada file pembanding.", card)
        self._lbl_status.setObjectName("hint")
        self._lbl_status.setWordWrap(True)
        cl.addWidget(self._lbl_status)
        return card

    def _build_card_result(self) -> Card:
        card = Card(self)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)
        ttl = WLabel("📈 Hasil Banding (kuantiti — tanpa angka BOM)", card)
        ttl.setObjectName("cardTitle")
        cl.addWidget(ttl)

        ctrl = QWidget(card)
        ctl = QHBoxLayout(ctrl)
        ctl.setContentsMargins(8, 0, 8, 0)
        ctl.setSpacing(10)
        lbl = WLabel("Banding dengan:", ctrl)
        ctl.addWidget(lbl)
        self._cb_b = QComboBox(ctrl)
        self._cb_b.setToolTip(
            "Pilih pembanding:\n"
            "• 'Tipikal' = nilai tengah gabungan beberapa bulan lalu "
            "(butuh ≥ 2 bulan) — untuk deteksi perubahan;\n"
            "• satu bulan tertentu — untuk melihat bulan itu apa adanya.")
        self._cb_b.setMinimumWidth(220)
        self._cb_b.currentIndexChanged.connect(
            lambda _i: self._on_combo_changed())
        ctl.addWidget(self._cb_b)
        self._lbl_compare = WLabel("", ctrl)
        self._lbl_compare.setObjectName("hint")
        ctl.addWidget(self._lbl_compare, 1)
        cl.addWidget(ctrl)

        self._tabs = QTabWidget(card)
        self._tables: dict[str, DataTable] = {}
        for key, title in _PAGES:
            table = DataTable()
            self._tables[key] = table
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(12, 10, 12, 10)
            pl.setSpacing(6)
            pl.addWidget(table, 1)
            self._tabs.addTab(page, title)
        cl.addWidget(self._tabs, 1)
        return card

    # ------------------------------------------------------------
    # KONTRAK LAZY-RENDER
    # ------------------------------------------------------------
    def refresh(self) -> None:
        """Kontrak lazy-render: perbarui label A + render ulang bila basi."""
        self._on_data_ready()

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data/history berubah."""
        if self._dirty or not self._has_result:
            self._refresh_result()

    def _on_data_ready(self) -> None:
        self._lbl_a.setText(
            "Bulan berjalan: " + fmt_run_label(
                self._ctx.summary, self._ctx.key_akhir))
        if self.isVisible():
            self._refresh_result()
        else:
            self._dirty = True

    def _on_history_ready(self) -> None:
        self._render_file_list()
        if self.isVisible():
            self._refresh_result()
        else:
            self._dirty = True

    def _on_combo_changed(self) -> None:
        if self.isVisible():
            self._refresh_result()

    # ------------------------------------------------------------
    # DAFTAR FILE
    # ------------------------------------------------------------
    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Pilih Workbook Pembanding (bisa beberapa)",
            str(Path.home() / "Documents"),
            "Excel files (*.xlsx *.xlsm);;All files (*.*)")
        if not paths:
            return
        added = 0
        for p in paths:
            known = {e["path"] for e in self._entries}
            if p in known:
                continue
            self._entries.append(
                {"path": p, "label": detect_month_label(p)})
            added += 1
        if added:
            save_history_entries(self._entries)
            self._render_file_list()
            self._start_worker()

    def _on_delete(self) -> None:
        rows = sorted({i.row() for i in self._tbl_files.selectedIndexes()},
                      reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(self._entries):
                p = self._entries[r]["path"]
                self._entries.pop(r)
                self._loaded.pop(p, None)
                self._loaded_sig.pop(p, None)
                self._last_results.pop(p, None)
        save_history_entries(self._entries)
        self._render_file_list()
        self._finalize()  # render ulang dgn sisa bulan (tanpa worker bila semua termuat)

    def _on_reload(self) -> None:
        if self._running:
            self._cancel()
            return
        self._loaded.clear()
        self._loaded_sig.clear()
        self._start_worker()

    def _on_double(self, index) -> None:
        """Klik 2× baris: koreksi nama bulan (persisten)."""
        r = index.row()
        if not (0 <= r < len(self._entries)):
            return
        ent = self._entries[r]
        cur = ent.get("label") or ""
        auto = detect_month_label(ent["path"]) or ""
        text, ok = QInputDialog.getText(
            self, "Nama Bulan Pembanding",
            "Nama bulan file ini (mis. 'Agustus 2026'):",
            text=cur or auto)
        if not ok:
            return
        text = text.strip()
        if text and text != cur:
            ent["label"] = text
            save_history_entries(self._entries)
            self._render_file_list()
            self._finalize()

    def _render_file_list(self) -> None:
        """Sinkronkan tabel daftar dgn self._entries + status termuat."""
        self._tbl_files.setRowCount(len(self._entries))
        for r, ent in enumerate(self._entries):
            label = ent.get("label") or detect_month_label(ent["path"]) \
                or "(klik 2× utk beri nama)"
            it_l = QTableWidgetItem(str(label))
            it_l.setToolTip(
                "Klik 2× untuk mengoreksi nama bulan ini.\n"
                "Nama dipakai untuk urutan & pilihan pembanding.")
            self._tbl_files.setItem(r, 0, it_l)
            self._tbl_files.setItem(r, 1, QTableWidgetItem(
                Path(ent["path"]).name))
            res = self._last_results.get(ent["path"])
            if res is None:
                status = "⏳ belum dimuat" if not self._running else "⏳ memuat…"
                it_s = QTableWidgetItem(status)
            elif res.get("error"):
                it_s = QTableWidgetItem(f"✗ {res['error']}")
                it_s.setForeground(QColor("#dc2626"))
                it_s.setToolTip(str(res["error"]))
            else:
                n_item = fmt_id(res.get("item_count", 0))
                ka = res.get("key_akhir", "?")
                it_s = QTableWidgetItem(f"✓ {n_item} item • {ka} hari")
                it_s.setToolTip(
                    f"Berhasil dimuat: {res.get('rows_kept', 0):,} baris "
                    f"waste disaring → {res.get('item_count', 0):,} "
                    f"kombinasi cabang × item.")
            self._tbl_files.setItem(r, 2, it_s)

    # ------------------------------------------------------------
    # WORKER
    # ------------------------------------------------------------
    def _file_sig(self, path: str) -> tuple | None:
        try:
            st = Path(path).stat()
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _start_worker(self) -> None:
        """Muat file yang belum termuat (cache mtime/size) di background."""
        if self._running:
            return
        todo: list[dict] = []
        for ent in self._entries:
            p = ent["path"]
            sig = self._file_sig(p)
            cached = self._loaded.get(p)
            if (cached is not None and sig is not None
                    and self._loaded_sig.get(p) == sig):
                continue  # termuat & file tak berubah → pakai ulang
            todo.append(ent)
        if not todo:
            self._finalize()
            return
        self._running = True
        self._btn_run.setText("⏹ Batalkan")
        self._btn_run.setObjectName("danger")
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._btn_add.setEnabled(False)
        self._btn_del.setEnabled(False)
        n = len(todo)
        self._lbl_status.setText(
            f"⏳ Memuat {n} file pembanding di latar belakang…")
        self._ctx.set_status(
            f"Banding periode: memuat {n} file pembanding…", "running")
        self._render_file_list()
        self._worker = HistoryWorker(todo, dict(self._ctx.config), self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _cancel(self) -> None:
        if not self._running or self._worker is None:
            return
        self._worker.cancel()
        self._btn_run.setEnabled(False)
        self._ctx.set_status("⏹ Membatalkan pemuatan pembanding…", "running")

    def _finish(self) -> None:
        self._running = False
        self._worker = None
        self._btn_run.setText("🔄 Muat Ulang")
        self._btn_run.setObjectName("accent")
        self._btn_run.setEnabled(True)
        self._btn_run.style().unpolish(self._btn_run)
        self._btn_run.style().polish(self._btn_run)
        self._btn_add.setEnabled(True)
        self._btn_del.setEnabled(True)

    def _on_progress(self, msg: str, pct: float) -> None:
        self._lbl_status.setText(f"⏳ {msg}")

    def _on_done(self, months: list) -> None:
        self._finish()
        for m in months or []:
            p = m.get("path")
            if not p:
                continue
            self._last_results[p] = m
            if not m.get("error"):
                sig = self._file_sig(p)
                if sig is not None:
                    self._loaded[p] = m
                    self._loaded_sig[p] = sig
                else:  # file menghilang setelah termuat — jangan cache
                    self._loaded.pop(p, None)
                    self._loaded_sig.pop(p, None)
        ok = [m for m in self._last_results.values()
              if not m.get("error")]
        err = [m for m in self._last_results.values() if m.get("error")]
        parts = [f"✓ {len(ok)} bulan pembanding aktif"]
        if err:
            parts.append(f"⚠ {len(err)} file gagal (lihat kolom Status)")
        self._lbl_status.setText(" — ".join(parts) + ".")
        self._ctx.set_status("✓ Pembanding periode siap", "done")
        self._finalize()

    def _on_failed(self, err: str, tb: str) -> None:
        self._finish()
        cancelled = "dibatalkan" in err.lower()
        if cancelled:
            self._lbl_status.setText("⏹ Pemuatan pembanding dibatalkan.")
            self._ctx.set_status("⏹ Pemuatan pembanding dibatalkan", "error")
            return
        self._lbl_status.setText(f"⚠ Gagal: {err}")
        self._ctx.set_status(f"⚠ Pembanding gagal: {err}", "error")
        if tb:
            self._ctx.log(f"⚠ HistoryWorker traceback: {tb}")
        QMessageBox.critical(self, "Banding Periode", err)

    # ------------------------------------------------------------
    # HASIL BANDING
    # ------------------------------------------------------------
    def _agg_a(self) -> dict | None:
        """Agregat bulan berjalan (A) — memo per data_version + key_akhir."""
        if self._ctx.df is None:
            return None
        key = (self._ctx.data_version, self._ctx.key_akhir)
        if self._a_cache is not None and self._a_cache[:2] == key:
            return self._a_cache[2]
        a = aggregate_current(self._ctx.df, self._ctx.key_akhir)
        if a is not None:
            self._a_cache = (key[0], key[1], a)
        return a

    def _combo_months(self) -> list[dict]:
        """Bulan valid utk combo — urut kronologis (lama → baru)."""
        months = []
        for ent in self._entries:
            m = self._loaded.get(ent["path"]) \
                or self._last_results.get(ent["path"])
            if m and not m.get("error"):
                m = dict(m)
                m["label"] = ent.get("label") or m.get("label") or "?"
                months.append(m)
        months.sort(key=lambda m: month_sort_key(m.get("label")))
        return months

    def _rebuild_combo(self, months: list[dict]) -> None:
        """Isi ulang combo (Tipikal + bulan kronologis) tanpa trigger render
        (setCurrentIndex di dalam blok sinyal — klik user tetap memicu
        render lewat _on_combo_changed)."""
        self._combo_version = self._ctx.history_version
        self._cb_b.blockSignals(True)
        self._cb_b.clear()
        typ = self._ctx.history_typical
        if typ is not None:
            n = typ.get("months_count", 0)
            self._cb_b.addItem(f"📊 Tipikal — median {n} bulan", _TYPICAL_KEY)
        for m in months:
            self._cb_b.addItem(str(m.get("label") or "?"), m)
        if self._cb_b.count() == 0:
            self._cb_b.blockSignals(False)
            return
        # Default: Tipikal (deteksi perubahan) bila ada, else bulan TERBARU.
        idx = 0
        if typ is None and months:
            idx = self._cb_b.count() - 1  # bulan terakhir = terbaru
        self._cb_b.setCurrentIndex(idx)
        self._cb_b.blockSignals(False)

    def _finalize(self) -> None:
        """Susun hasil final (bulan termuat + tipikal) → set_history.

        TIDAK membangun combo di sini: set_history menaikkan versi & memancar
        history_ready → _refresh_result mendeteksi versi beda → combo diisi
        ulang LALU render — satu jalur, urutan selalu benar (label hasil edit
        pun ikut tersinkron)."""
        months = self._combo_months()
        typical = None
        if len(months) >= 2:
            with busy_feedback(self._ctx.set_status,
                               "Menghitung tipikal bulan lalu"):
                typical = typical_months(months)
        self._ctx.set_history(months, typical)

    def _refresh_result(self) -> None:
        """Render hasil banding A vs pilihan combo (titik tunggal).

        Combo disinkronkan LEBIH DULU (sebelum cek data A) supaya daftar
        bulan + Tipikal terlihat seketika walau pipeline belum dijalankan —
        tabel menunggu A, combo tidak."""
        self._dirty = False
        months = self._combo_months()
        if self._combo_version != self._ctx.history_version:
            self._rebuild_combo(months)
        a = self._agg_a()
        if a is None:
            self._clear_tables(
                "Jalankan pipeline dulu (tab Pipeline) — banding butuh data "
                "bulan berjalan.")
            return
        if not months:
            self._clear_tables(
                "Belum ada file pembanding — tambahkan file bulan lalu di atas "
                "(1 file = 1 bulan).")
            return
        data = self._cb_b.currentData()
        if data == _TYPICAL_KEY:
            b = self._ctx.history_typical
        elif isinstance(data, dict):
            b = data
        else:
            b = None
        if b is None:
            b = months[-1]  # fallback: bulan terbaru
        with busy_feedback(self._ctx.set_status,
                           f"Banding {a.get('label')} vs {b.get('label')}"):
            res = compare_quantity(a, b, top_n=100)
        self._has_result = True
        self._result_version = (self._ctx.data_version,
                                self._ctx.history_version)
        for key, df_key in _RESULT_KEYS.items():
            df = res.get(df_key)
            self._tables[key].set_dataframe(
                df if isinstance(df, pd.DataFrame) else None)
        ka_a = res.get("key_akhir_a")
        ka_b = res.get("key_akhir_b")
        self._lbl_compare.setText(
            f"✓ Bulan berjalan ({ka_a} hari) vs {res.get('label_b')} "
            f"({ka_b} hari) — 'Waste per Hari' menormalkan beda panjang bulan.")

    def _clear_tables(self, msg: str) -> None:
        for table in self._tables.values():
            table.set_dataframe(None)
        self._lbl_compare.setText(msg)
        self._has_result = False


def fmt_run_label(summary: dict | None, key_akhir: int) -> str:
    label = "(run terakhir)"
    if summary:
        rows = summary.get("total_rows", 0)
        label = f"{fmt_id(rows)} baris • key_akhir {key_akhir}"
    return label
