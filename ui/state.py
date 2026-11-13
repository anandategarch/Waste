"""state.py — AppContext: satu sumber state + signal Qt (v2.6.0).

Pengganti state tersebar di god-object Tkinter lama (active_filters,
day_min/max, _preview_dfs, last_summary, ...). Views membaca state via
ctx, bereaksi lewat signal:

- data_ready()      → dataset baru dari pipeline (df + summary)
- history_ready()   → data pembanding bulan-bulan lalu selesai dimuat (v2.10.0)
- filters_changed() → filter/drill-down berubah
- status(text, kind)→ pesan status bar ("running"|"done"|"error")
- log_line(str)     → satu baris log

v2.8.1: _build_derived_sheets + ctx.sheets DIHAPUS — satu-satunya
konsumen adalah view Jelajah (dihapus total); export Excel membangun
sheet analisanya sendiri (ui/workers.py::_extra_sheets).
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, Signal

from .shared import LOG_RUN_LINES, _apply_filters
from waste_anomaly.followup import (
    fingerprint_series,
    load_followup_keys,
    save_followup_keys,
    select_followup_rows,
)
from waste_anomaly.period_history import month_sort_key


class AppContext(QObject):
    """State aplikasi tunggal + signal perubahan."""

    data_ready = Signal()
    history_ready = Signal()
    baseline_changed = Signal()  # v2.10.2: pilihan pembanding combo berubah
    filters_changed = Signal()
    followup_changed = Signal()  # v2.12.0: daftar follow-up baris berubah
    status = Signal(str, str)
    log_line = Signal(str)
    # v2.19.5 — staging koreksi (tab Update nilai): kumpulin dulu, proses
    # batch nanti. update_staged dipancar HANYA saat add_update (MainWindow
    # dengar → pindah ke tab Update nilai). updates_changed dipancar saat
    # ANY change (add/remove/clear/status) — UpdateView dengar → refresh
    # tabel; MainWindow dengar → update badge jumlah pending.
    update_staged = Signal()
    updates_changed = Signal()

    def __init__(self, config: dict, parent: QObject | None = None,
                 followup_path=None) -> None:
        """``followup_path`` (v2.12.0): jalur followup.json — None = tanpa
        persistensi disk (mode test). Dipasang saat konstruksi supaya
        centangan termuat SEBELUM view dibangun (badge tab akurat)."""
        super().__init__(parent)
        self.config = config
        self.df: pd.DataFrame | None = None
        self.summary: dict | None = None
        self.key_akhir: int = 31
        self.last_run_time: datetime | None = None
        self.log_lines: list[str] = []
        # v2.7.0: versi dataset — bertambah tiap set_dataset; dipakai view
        # (mis. Banding Periode) utk tahu hasil lama dibuat dari dataset lama.
        self.data_version = 0
        # v2.19.5 — staging koreksi: list dict pending tulis ke file Excel
        # sumber. Diproses batch via tab Update nilai (BatchUpdateWorker).
        self.pending_updates: list[dict] = []

        # Drill-down state (bentuk IDENTIK v2.5.1 — dikonsumsi _apply_filters)
        # v2.13.8 (gel-C): search/day_min/day_max DIHAPUS — kotak cari &
        # rentang hari dihapus dari UI sejak v2.12.4; field-field itu mati
        # di produksi (audit D11) dan hanya hidup via test lama.
        self.active_filters: dict[str, str | list[str] | None] = {
            "cabang": None, "item": None, "jenis": [],
            "keterangan": None, "status": None,
        }
        # v2.6.0: ambang skor minimum (khusus tabel anomali — fitur hunting)
        self.score_min = 0
        # v2.7.0 (perf, audit Task ID 1): memo hasil filtered_df — dulu
        # _apply_filters dijalankan 2× per refresh (anomali_df + KPI view)
        # atas df 25.901×53. Divalidasi oleh set_filter/set_score_min/
        # reset_filters/set_dataset. Pemanggil hanya membaca (mask/slice
        # kolom = copy) — kontrak aman tanpa copy ekstra per hit.
        self._filtered_cache: pd.DataFrame | None = None
        self._filter_cache_valid = False
        # v2.9.0 (perf): LRU anomali_df() BERDASARKAN TANDA TANGAN FILTER —
        # bukan satu slot memo: unfilter/drill bolak-balik kembali ke state
        # filter yang SAMA → objek df yang PERSIS sama dikembalikan →
        # DataTable mengenali df identik (id sama) dan memasang ulang hasil
        # pengukuran lebar/tinggi tanpa hitung ulang (diukur v2.8.3:
        # 220-460 ms per render). Satu slot memo (iterasi-1 v2.9.0) gagal
        # karena tiap invalidasi membuat objek BARU — cache fit tak pernah
        # kena. Tanda tangan mencakup data_version (dataset baru ≠ state lama).
        self._anomali_cache: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
        # v2.10.0: data pembanding periode (multi-file bulan lalu, kuantiti
        # tanpa BOM) — diisi view Banding Periode via HistoryWorker (thread
        # background). history_version naik tiap set_history → view Hari
        # Mencurigakan mem-memo bukti "bulan lalu" per versi (cache fit
        # DataTable tetap kena antar-refresh dengan state sama).
        self.history_months: list[dict] = []
        self.history_typical: dict | None = None
        self.history_version: int = 0
        # v2.10.2: pilihan pembanding combo 'Banding Periode' (objek bulan /
        # tipikal) — DIBAGIKAN ke view Anomali supaya kolom BULAN LALU /
        # PERUBAHAN menghitung vs bulan yang sama dengan tab banding.
        # None = combo belum dirender → view Anomali pakai aturan default
        # (banding_baseline_effective).
        self.banding_baseline: dict | None = None
        # v2.12.0: daftar follow-up (sidik jari baris, urutan centang).
        # Persisten bila _followup_path dipasang; memo fingerprint per
        # data_version (dibangun malas — 25.9k baris ≈ 0,1-0,2 dtk sekali
        # per dataset).
        self._followup_path = (
            None if followup_path is None else Path(str(followup_path)))
        self.followup_keys: list[str] = (
            load_followup_keys(self._followup_path)
            if self._followup_path is not None else [])
        self._fp_series: pd.Series | None = None
        self._fp_version: int = -1
        # v2.18.7: fitur "Impor Hasil TL" (followup_resolved.json +
        # apply_followup_resolved) DIHAPUS atas permintaan user
        # ("import ITL itu hapus aja belum kepakai") — penggantinya:
        # impor file ekspor → auto-centang (read_followup_export_fps +
        # add_followup_many), tanpa state tambahan.

    # ------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------
    def set_dataset(self, df: pd.DataFrame, summary: dict) -> None:
        """Dataset baru dari pipeline: simpan + reset filter + broadcast."""
        self.df = df
        self.summary = summary
        try:
            self.key_akhir = int(summary.get("key_akhir", 31))
        except (TypeError, ValueError):
            self.key_akhir = 31
        self.last_run_time = datetime.now()
        self.data_version += 1
        # v2.9.0: LRU anomali berisi df dari dataset LAMA — data_version
        # baru membuat tanda tangan tak cocok, tapi entri tetap memakan
        # memori → kosongkan eksplisit.
        self._anomali_cache.clear()
        # v2.12.1 (perf): sidik jari follow-up dibangun PipelineWorker di
        # thread background — di sini cuma diambil; bila tak ada (jalur
        # test / set_dataset manual) → bangun malas di fingerprints()
        # seperti sebelumnya.
        fps = summary.get("followup_fps")
        if isinstance(fps, pd.Series) and fps.index.equals(df.index):
            self._fp_series = fps
            self._fp_version = self.data_version
        else:
            self._fp_series = None
        self.reset_filters()  # juga meng-invalidasi memo filtered_df
        self.data_ready.emit()
        # v2.7.0 (V26-H2): siarkan reset filter SEKALI SETELAH data_ready —
        # views pendengar filters_changed (Anomali/Hari) menandai dirty
        # secara konsisten. Urutan setelah data_ready dipilih karena pada
        # alur tipikal re-run user ada di tab Pipeline (view tidak terlihat
        # → kedua handler hanya menandai dirty, TANPA render ganda); bila
        # kebetulan terlihat, pasangan emit ini kini DIKONSUMSI SEKALI oleh
        # flag _skip_filters_once di view (v2.13.14 gel-5 A7) — dulu
        # _on_filters_changed menjalankan render PENUH kedua yang identik
        # (docstring lama menjanjikan 'partial refresh' — tidak jujur;
        # audit A7). set_filter/drill user tetap render normal (flag hanya
        # dikonsumsi oleh emit pasangan set_dataset).
        self.filters_changed.emit()

    # ------------------------------------------------------------
    # HISTORY PEMBANDING (v2.10.0)
    # ------------------------------------------------------------
    def set_history(self, months: list[dict],
                    typical: dict | None = None) -> None:
        """Simpan hasil HistoryWorker (daftar bulan + tipikal gabungan)
        lalu broadcast history_ready. Entri ber-"error" tetap disimpan
        (view menandainya merah) tapi dikecualikan dari history_months_ok."""
        self.history_months = list(months or [])
        self.history_typical = typical
        self.history_version += 1
        self.history_ready.emit()

    def history_months_ok(self) -> list[dict]:
        """Bulan pembanding yang berhasil dimuat (tanpa error, agg ada)."""
        return [m for m in self.history_months
                if m and not m.get("error") and m.get("agg") is not None]

    def set_banding_baseline(self, b: dict | None) -> None:
        """Simpan pilihan pembanding combo Banding Periode (v2.10.2).

        Emit baseline_changed HANYA bila objek berganti (identitas —
        _refresh_result memanggil ini tiap render; dict combo stabil
        sehingga tidak spam signal)."""
        if b is not self.banding_baseline:
            self.banding_baseline = b
            self.baseline_changed.emit()

    def _baseline_alive(self, b) -> bool:
        """v2.13.10 (gel-1 B2/B5) — apakah baseline masih HIDUP di data
        pembanding saat ini (validasi umur, lapis-2 anti baseline-hantu).

        Aturan IDENTITAS (bukan dict-equality penuh — nilai 'agg' berupa
        DataFrame: bool(DataFrame) = truth-ambiguous ValueError, crash!):
        - objek Tipikal SAAT INI (identitas objek — set_history baru
          membuat objek Tipikal baru → objek lama dianggap usang);
        - bulan file: 'path' masih ada di daftar bulan OK saat ini
          (file dihapus dari daftar pembanding → baseline mati);
        - dict suntetis TANPA 'path' (fixture test v2.12.3/v2.10.2 yang
          menyuntik baseline langsung) → dipercaya apa adanya.
        Bentuk tak dikenal → hidup (jangan mematikan begitu saja)."""
        if not isinstance(b, dict):
            return True
        if b is self.history_typical:
            return True
        if "path" not in b:
            return True  # fixture suntetis — kompatibilitas 31+ test lama
        for m in self.history_months_ok():
            if isinstance(m, dict) and m.get("path") == b.get("path"):
                return True
        return False

    def banding_baseline_effective(self) -> dict | None:
        """Baseline utk kolom perubahan view Anomali (v2.10.2).

        Prioritas: pilihan combo Banding Periode (bila user sudah membuka
        tab itu) → Tipikal (≥ 2 bulan) → bulan pembanding TERBARU → None.
        v2.13.10 (gel-1 B2/B5): baseline yang sudah MATI (bulan filenya
        dihapus dari daftar pembanding / objek Tipikal usang pasca
        set_history baru — mis. saat view banding tersembunyi, hanya
        menandai dirty) diabaikan → jatuh ke fallback. Dulu baseline
        hantu terus dipakai: tab Anomali menghitung BULAN LALU vs bulan
        yang tak ada lagi (audit B2/B5)."""
        b = self.banding_baseline
        if b is not None and self._baseline_alive(b):
            return b
        months = self.history_months_ok()
        if not months:
            return None
        if self.history_typical is not None:
            return self.history_typical
        return max(months, key=lambda m: month_sort_key(m.get("label")))

    # ------------------------------------------------------------
    # FILTER
    # ------------------------------------------------------------
    def filtered_df(self) -> pd.DataFrame | None:
        """df hasil filter funnel (cabang/item/jenis/keterangan/status).

        v2.7.0: hasil di-memo — dipakai ulang sampai filter/data berubah
        (lihat invalidasi di setter). v2.13.8: jalur search/rentang-hari
        dihapus bersama fiturnya (audit D11)."""
        if self.df is None:
            return None
        if not self._filter_cache_valid:
            self._filtered_cache = _apply_filters(
                self.df, self.active_filters)
            self._filter_cache_valid = True
        return self._filtered_cache

    def _filter_signature(self) -> tuple:
        """Kunci state filter utk LRU anomali (v2.9.0)."""
        af = tuple(sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in self.active_filters.items()))
        return (self.data_version, af, self.score_min)

    def anomali_df(self) -> pd.DataFrame | None:
        """df terfilter utk tab Anomali. v2.19.8 — TAMPILKAN SEMUA BARIS
        (termasuk Normal) supaya user bisa cek seluruh data, bukan hanya
        anomali. Filter skor ≥ min tetap jalan (spinner "Skor ≥", default
        0 = semua). Filter keterangan/status (funnel) tetap lokal grup.

        v2.9.0: LRU per tanda tangan filter (≤ 8 entri, objek sama dipakai
        ulang antar-refresh/antar-view Anomali & Hari Mencurigakan) —
        kembali ke state filter lama = kembali objek lama → cache fit
        DataTable tetap valid. Konsumen hanya membaca (sort model bekerja
        pada salinannya sendiri) — kontrak aman tanpa copy defensif.
        """
        df = self.filtered_df()
        if df is None:
            return None
        key = self._filter_signature()
        cached = self._anomali_cache.get(key)
        if cached is not None:
            self._anomali_cache.move_to_end(key)
            return cached
        # v2.19.8 — Normal TIDAK lagi dibuang (permintaan user: "tampilkan
        # semua data jangan hanya yg perlu review atau anomali aja tapi
        # semua data"). Filter skor ≥ min tetap jalan.
        if self.score_min > 0 and "ANOMALY SCORE" in df.columns:
            df = df[pd.to_numeric(df["ANOMALY SCORE"], errors="coerce")
                    .fillna(0) >= self.score_min]
        self._anomali_cache[key] = df
        while len(self._anomali_cache) > 8:
            self._anomali_cache.popitem(last=False)
        return df

    def set_filter(self, key: str, value) -> None:
        """Set satu filter (drill-down atau funnel) lalu broadcast."""
        self.active_filters[key] = value
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_score_min(self, score: int) -> None:
        self.score_min = score
        self._filter_cache_valid = False  # tak dipakai _apply_filters, tetap aman
        self.filters_changed.emit()

    def reset_filters(self) -> None:
        """Reset total ke nilai default (tanpa broadcast — pemanggil yang
        memutuskan; set_dataset sudah diikuti data_ready)."""
        for k in self.active_filters:
            self.active_filters[k] = [] if k == "jenis" else None
        self.score_min = 0
        self._filter_cache_valid = False

    # ------------------------------------------------------------
    # FOLLOW UP (v2.12.0)
    # ------------------------------------------------------------
    def followup_set(self) -> set[str]:
        """Set sidik jari tercentang (lookup O(1))."""
        return set(self.followup_keys)

    def toggle_followup(self, fp: str, checked: bool) -> bool:
        """Tambah/hapus SATU baris (centang/lepas) + broadcast + simpan.

        Return True bila state benar-benar berubah (klik ulang nilai
        sama = no-op tanpa broadcast — anti render sia-sia)."""
        fset = self.followup_set()
        if checked == (fp in fset):
            return False
        if checked:
            self.followup_keys.append(fp)
        else:
            self.followup_keys = [k for k in self.followup_keys if k != fp]
        self._persist_followup()
        self.followup_changed.emit()
        return True

    def add_followup_many(self, fps) -> int:
        """Centang BANYAK baris sekaligus — SATU broadcast (satu render,
        bukan satu per baris).

        Return jumlah baris BENAR-BENAR baru — duplikat DI DALAM batch
        maupun yang sudah ada di daftar dihitung 0 (batch 'tombol centang
        semua' berisi kembar identik — dedup wajib, else key ganda
        menumpuk di followup.json)."""
        seen = self.followup_set()
        added: list[str] = []
        for fp in fps:
            s = str(fp)
            if s and s != "nan" and s not in seen:
                seen.add(s)
                added.append(s)
        if not added:
            return 0
        self.followup_keys.extend(added)
        self._persist_followup()
        self.followup_changed.emit()
        return len(added)

    def remove_followup_many(self, fps) -> int:
        """Lepas centang BANYAK baris sekaligus — SATU broadcast + SATU
        persist (pola add_followup_many; v2.12.2: lepas ✓ di tabel Banding
        Periode = keluarkan SEMUA baris anomali terkait sekaligus — tanpa
        ini tiap baris menulis followup.json + broadcast N kali).

        Return jumlah baris benar-benar dikeluarkan (0 = tak ada yang
        cocok / daftar sudah bersih — no-op tanpa broadcast sia-sia)."""
        drop: set = set()
        for fp in fps:
            s = str(fp)
            if s and s != "nan":
                drop.add(s)
        if not drop:
            return 0
        keep = [k for k in self.followup_keys if k not in drop]
        removed = len(self.followup_keys) - len(keep)
        if removed == 0:
            return 0
        self.followup_keys = keep
        self._persist_followup()
        self.followup_changed.emit()
        return removed

    def clear_followup(self) -> int:
        """Kosongkan seluruh daftar + broadcast. Return jumlah dihapus."""
        n = len(self.followup_keys)
        if n == 0:
            return 0
        self.followup_keys = []
        self._persist_followup()
        self.followup_changed.emit()
        return n

    def _persist_followup(self) -> None:
        if self._followup_path is None:
            return
        if not save_followup_keys(self.followup_keys, self._followup_path):
            self.set_status("⚠ Gagal menyimpan daftar follow-up (disk?)",
                            "error")

    def fingerprints(self) -> pd.Series | None:
        """Sidik jari per baris dataset PENUH (memo per data_version)."""
        if self.df is None:
            return None
        if self._fp_series is None or self._fp_version != self.data_version:
            self._fp_series = fingerprint_series(self.df)
            self._fp_version = self.data_version
        return self._fp_series

    def followup_df(self) -> pd.DataFrame | None:
        """Baris follow-up dari dataset PENUH (bukan terfilter — shortlist
        menetap terhadap filter/slicer) + kolom __FP + dedup kembar.

        None = belum ada dataset; df kosong = tidak ada centangan."""
        if self.df is None:
            return None
        if not self.followup_keys:
            return self.df.iloc[:0].copy()
        fps = self.fingerprints()
        if fps is None:
            return None
        return select_followup_rows(self.df, fps, self.followup_keys)

    def prune_followup(self) -> int:
        """Buang key yang barisnya tak ada lagi di dataset (dipanggil
        MainWindow pasca data_ready — pipeline baru/file berganti).

        Return jumlah dihapus (0 = semua centangan masih valid)."""
        if not self.followup_keys or self.df is None:
            return 0
        fps = self.fingerprints()
        valid: set = set(fps) if fps is not None else set()
        keep = [k for k in self.followup_keys if k in valid]
        dropped = len(self.followup_keys) - len(keep)
        if dropped:
            self.followup_keys = keep
            self._persist_followup()
            self.followup_changed.emit()
        return dropped

    # ------------------------------------------------------------
    # LOG / STATUS
    # ------------------------------------------------------------
    def log(self, msg: str) -> None:
        self.log_lines.append(str(msg))
        # v2.13.15 (gel-6 D11): SATU konstanta ambang lintas penampang log
        # run (panel / memori / ekspor) — dulu angka 500 lokal di sini vs
        # 2000 panel vs 200 ekspor (audit D11: tiga ambang beda).
        if len(self.log_lines) > LOG_RUN_LINES:
            del self.log_lines[: len(self.log_lines) - LOG_RUN_LINES]
        self.log_line.emit(str(msg))

    def set_status(self, text: str, kind: str = "running") -> None:
        self.status.emit(text, kind)

    # ------------------------------------------------------------
    # v2.19.5 — PENDING UPDATES (staging koreksi, tab Update nilai)
    # ------------------------------------------------------------
    def add_update(self, entry: dict) -> int:
        """Tambah satu entry koreksi pending ke antrian staging.

        entry dict kontrak (dipasang DetailPanel._on_stage_edits):
          source    : str path file Excel sumber (REKAP MENTAH).
          src_rows  : list[int] nomor baris fisik sheet (anggota grup).
          day_edits : dict[str, float] hari→nilai-baru.
          day_orig  : dict[str, float] hari→nilai-lama (utk tampilan).
          label     : str ringkas (mis. "Handling · AYAM · R1" —
                      keterangan·barang·resto sejak v2.21.1).
          jenis/barang/resto : str komponen label.
          keterangan : str alasan grup (v2.21.1 — kolom 'Keterangan'
                      tab Update nilai; fallback = nilai JENIS utk
                      baris ber-keterangan kosong).
          added_at  : str timestamp.

        Return index entry di pending_updates (utk highlight baris baru).
        Pancar update_staged (MainWindow → pindah tab Update nilai) +
        updates_changed (UpdateView refresh + badge).
        """
        entry.setdefault("status", "pending")
        entry.setdefault("error", None)
        entry.setdefault("result", None)
        entry.setdefault("added_at",
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.pending_updates.append(entry)
        idx = len(self.pending_updates) - 1
        self.update_staged.emit()
        self.updates_changed.emit()
        return idx

    def remove_update(self, idx: int) -> bool:
        """Buang entry staging ber-index. Return True bila dibuang."""
        if 0 <= idx < len(self.pending_updates):
            del self.pending_updates[idx]
            self.updates_changed.emit()
            return True
        return False

    def clear_updates(self) -> int:
        """Kosongkan SELURUH staging (pending + hasil). Return jumlah
        dibuang. Dipakai tombol 'Kosongkan semua' di tab Update nilai."""
        n = len(self.pending_updates)
        self.pending_updates.clear()
        if n:
            self.updates_changed.emit()
        return n

    def clear_processed_updates(self) -> int:
        """Buang HANYA entry yg status-nya 'done' (tersimpan). Entry
        'failed' + 'pending' tetap (utk retry). Dipakai pasca proses
        batch supaya user bisa lihat yg gagal tanpa clutter yg sukses.
        Return jumlah dibuang."""
        before = len(self.pending_updates)
        self.pending_updates = [e for e in self.pending_updates
                                if e.get("status") != "done"]
        removed = before - len(self.pending_updates)
        if removed:
            self.updates_changed.emit()
        return removed

    def mark_update_status(self, idx: int, status: str,
                           error: str | None = None,
                           result: dict | None = None) -> None:
        """Update status entry staging (dipanggil BatchUpdateWorker via
        UpdateView: 'done' / 'failed'). Pancar updates_changed."""
        if 0 <= idx < len(self.pending_updates):
            e = self.pending_updates[idx]
            e["status"] = status
            e["error"] = error
            e["result"] = result
            self.updates_changed.emit()

    def pending_count(self) -> int:
        """Jumlah entry staging (semua status)."""
        return len(self.pending_updates)

    def pending_unprocessed_count(self) -> int:
        """Jumlah entry staging BELUM tersimpan (pending + failed — siap
        diproses/diulang). Dipakai badge tab + enabled-state tombol Proses.
        Entry 'done' tak dihitung (sudah sukses — menunggu dibersihkan)."""
        return sum(1 for e in self.pending_updates
                   if e.get("status") != "done")
