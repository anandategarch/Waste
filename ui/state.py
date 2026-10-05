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

import pandas as pd
from PySide6.QtCore import QObject, Signal

from .shared import _apply_filters, _build_search_blob

# Label filter aktif → chip Indonesia (dari shared lama)
CHIP_LABELS = {
    "cabang": "Cabang", "status": "Status", "item": "Item", "search": "Cari",
    "jenis": "Jenis", "keterangan": "Keterangan", "hari": "Rentang Hari",
}


class AppContext(QObject):
    """State aplikasi tunggal + signal perubahan."""

    data_ready = Signal()
    history_ready = Signal()
    filters_changed = Signal()
    status = Signal(str, str)
    log_line = Signal(str)

    def __init__(self, config: dict, parent: QObject | None = None) -> None:
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
    # LOG / STATUS
    # ------------------------------------------------------------
    def log(self, msg: str) -> None:
        self.log_lines.append(str(msg))
        if len(self.log_lines) > 500:
            del self.log_lines[: len(self.log_lines) - 500]
        self.log_line.emit(str(msg))

    def set_status(self, text: str, kind: str = "running") -> None:
        self.status.emit(text, kind)
