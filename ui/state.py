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

from .shared import _apply_filters, _build_search_blob
from waste_anomaly.followup import (
    fingerprint_series,
    load_followup_keys,
    save_followup_keys,
    select_followup_rows,
)
from waste_anomaly.period_history import month_sort_key

# Label filter aktif → chip Indonesia (dari shared lama)
CHIP_LABELS = {
    "cabang": "Cabang", "status": "Status", "item": "Item", "search": "Cari",
    "jenis": "Jenis", "keterangan": "Keterangan", "hari": "Rentang Hari",
}


class AppContext(QObject):
    """State aplikasi tunggal + signal perubahan."""

    data_ready = Signal()
    history_ready = Signal()
    baseline_changed = Signal()  # v2.10.2: pilihan pembanding combo berubah
    filters_changed = Signal()
    followup_changed = Signal()  # v2.12.0: daftar follow-up baris berubah
    status = Signal(str, str)
    log_line = Signal(str)

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

        # Drill-down state (bentuk IDENTIK v2.5.1 — dikonsumsi _apply_filters)
        self.active_filters: dict[str, str | list[str] | None] = {
            "cabang": None, "item": None, "jenis": [],
            "keterangan": None, "status": None,
        }
        self.day_min: int | None = None
        self.day_max: int | None = None
        self.search = ""
        # v2.6.0: ambang skor minimum (khusus tabel anomali — fitur hunting)
        self.score_min = 0
        # v2.7.0 (perf, audit Task ID 1): memo hasil filtered_df — dulu
        # _apply_filters dijalankan 2× per refresh (anomali_df + KPI view)
        # atas df 25.901×53. Divalidasi oleh set_filter/set_search/
        # set_day_range/set_score_min/reset_filters/set_dataset. Pemanggil
        # hanya membaca (mask/slice kolom = copy) — kontrak aman tanpa copy
        # ekstra per hit.
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
        # v2.9.0 (perf): blob pencarian (semua kolom digabung per baris,
        # sudah lower-case) — dibangun SEKALI per dataset, dipakai
        # _apply_filters utk jalur cepat search (dari 1,5 dtk per kata
        # → ~0,1 dtk; lihat shared._build_search_blob).
        self._search_blob: pd.Series | None = None
        self._search_blob_version: int = -1
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
        # v2.10.2 (perf): LRU hasil change_vs_history per (df, baseline) —
        # df objek sama + baseline sama → salinan berkolom sama dipakai
        # ulang antar-refresh (cache fit DataTable tetap kena, kontrak
        # 'konsumen hanya membaca' tetap aman: enrich selalu di salinan).
        self._change_cache: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
        # v2.12.0: daftar follow-up (sidik jari baris, urutan centang).
        # Persisten bila _followup_path dipasang; memo fingerprint per
        # data_version (dibangun malas — 25.9k baris ≈ 0,1-0,2 dtk sekali
        # per dataset, pola _search_blob).
        self._followup_path = (
            None if followup_path is None else Path(str(followup_path)))
        self.followup_keys: list[str] = (
            load_followup_keys(self._followup_path)
            if self._followup_path is not None else [])
        self._fp_series: pd.Series | None = None
        self._fp_version: int = -1

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
        # v2.9.0 (perf): blob pencarian dibangun PipelineWorker di thread
        # background (1,2 dtk di luar UI); bila ada dan index cocok →
        # pakai, kalau tidak (jalur test/set_dataset manual) → dibangun
        # malas saat pencarian pertama (lihat filtered_df).
        blob = summary.get("search_blob")
        if isinstance(blob, pd.Series) and blob.index.equals(df.index):
            self._search_blob = blob
            self._search_blob_version = self.data_version
        else:
            self._search_blob = None
        self.reset_filters()  # juga meng-invalidasi memo filtered_df
        self.data_ready.emit()
        # v2.7.0 (V26-H2): siarkan reset filter SEKALI SETELAH data_ready —
        # views pendengar filters_changed (Anomali/Banding Periode) menandai dirty
        # secara konsisten. Urutan setelah data_ready dipilih karena pada
        # alur tipikal re-run user ada di tab Pipeline (view tidak terlihat
        # → kedua handler hanya menandai dirty, TANPA render ganda); bila
        # kebetulan terlihat, handler filters_changed hanya partial refresh
        # (bukan refresh penuh ganda).
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

    def banding_baseline_effective(self) -> dict | None:
        """Baseline utk kolom perubahan view Anomali (v2.10.2).

        Prioritas: pilihan combo Banding Periode (bila user sudah membuka
        tab itu) → Tipikal (≥ 2 bulan) → bulan pembanding TERBARU → None."""
        if self.banding_baseline is not None:
            return self.banding_baseline
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
        """df hasil filter lengkap (search + dropdown + rentang hari).

        v2.7.0: hasil di-memo — dipakai ulang sampai filter/data berubah
        (lihat invalidasi di setter + invalidate_filter_cache).
        v2.9.0: pencarian memakai blob gabungan per-baris yang dibangun
        sekali per dataset (cache data_version) — lihat _build_search_blob.
        """
        if self.df is None:
            return None
        if not self._filter_cache_valid:
            search = (self.search or "").strip()
            blob = None
            if search:
                if (self._search_blob is None
                        or self._search_blob_version != self.data_version):
                    self._search_blob = _build_search_blob(self.df)
                    self._search_blob_version = self.data_version
                blob = self._search_blob
            self._filtered_cache = _apply_filters(
                self.df, self.active_filters,
                day_min=self.day_min, day_max=self.day_max,
                search=self.search,
                search_blob=blob,
            )
            self._filter_cache_valid = True
        return self._filtered_cache

    def invalidate_filter_cache(self) -> None:
        """Batalkan memo filtered_df — WAJIB dipanggil bila filter state
        dimutasi langsung (bypass setter), mis. pemulihan profil filter.
        (LRU anomali tak perlu dibatalkan: kunci = tanda tangan filter yang
        dibaca ULANG saat query — hasil selalu konsisten dgn state.)"""
        self._filter_cache_valid = False

    def _filter_signature(self) -> tuple:
        """Kunci state filter utk LRU anomali (v2.9.0)."""
        af = tuple(sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in self.active_filters.items()))
        return (self.data_version, self.search, af,
                self.day_min, self.day_max, self.score_min)

    def anomali_df(self) -> pd.DataFrame | None:
        """df terfilter, hanya baris ANOMALY STATUS ≠ Normal, skor ≥ min.

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
        if "ANOMALY STATUS" in df.columns:
            df = df[df["ANOMALY STATUS"] != "Normal"]
        if self.score_min > 0 and "ANOMALY SCORE" in df.columns:
            df = df[pd.to_numeric(df["ANOMALY SCORE"], errors="coerce")
                    .fillna(0) >= self.score_min]
        self._anomali_cache[key] = df
        while len(self._anomali_cache) > 8:
            self._anomali_cache.popitem(last=False)
        return df

    def set_filter(self, key: str, value) -> None:
        """Set satu filter (drill-down atau dropdown) lalu broadcast."""
        self.active_filters[key] = value
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_filters_multi(self, values: dict) -> None:
        """Set BEBERAPA filter sekaligus + broadcast SEKALI (v2.11.0 slicer).

        Klik beruntun chip slicer dikoalesce timer di SlicerBar; metode ini
        memastikan beberapa dimensi berganti bersamaan hanya memicu SATU
        filters_changed (satu render) — pola coalesce _batch_filters V26-L4
        diangkat ke state. Kunci tak dikenal diabaikan."""
        for k, v in values.items():
            if k in self.active_filters:
                self.active_filters[k] = v
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_day_range(self, day_min: int | None, day_max: int | None) -> None:
        self.day_min = day_min
        self.day_max = day_max
        self._filter_cache_valid = False
        self.filters_changed.emit()

    def set_search(self, text: str) -> None:
        self.search = text
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
        self.day_min = None
        self.day_max = None
        self.search = ""
        self.score_min = 0
        self._filter_cache_valid = False

    def filter_summary(self) -> str:
        """Deskripsi filter aktif (utk chip / status bar)."""
        parts: list[str] = []
        for key, val in self.active_filters.items():
            if val is None or (isinstance(val, list) and not val):
                continue
            label = CHIP_LABELS.get(key, key.title())
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val[:3]) + ("…" if len(val) > 3 else "")
            parts.append(f"{label}: {val}")
        if self.day_min is not None and self.day_max is not None:
            parts.append(f"{CHIP_LABELS['hari']}: {self.day_min}–{self.day_max}")
        if (self.search or "").strip():
            parts.append(f'{CHIP_LABELS["search"]}: "{self.search.strip()}"')
        return " • ".join(parts)

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
        """Centang BANYAK baris sekaligus — SATU broadcast (pola
        set_filters_multi: satu render, bukan satu per baris).

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
        if len(self.log_lines) > 500:
            del self.log_lines[: len(self.log_lines) - 500]
        self.log_line.emit(str(msg))

    def set_status(self, text: str, kind: str = "running") -> None:
        self.status.emit(text, kind)
