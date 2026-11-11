"""followup_table.py — mixin tabel ber-centang ✓ + funnel lokal (v2.13.8).

Konsolidasi 10 metode KEMBAR IDENTIK AnomaliView ⇄ HariView (v2.13.5
menyalin pola follow-up ke HariView kata-per-kata — audit gel-C
menemukan ±250 baris duplikat + 4 varian mask-funnel; kini SATU
implementasi). FollowUpView tidak ikut: tabelnya rekap (tanpa ✓-kolom
toggle in-place — perilaku berbeda, bukan kembar).

Kontrak atribut HOST (wajib disediakan view pemakai mixin):
  _ctx             AppContext (state + signal)
  _table           DataTable (model bertugas ✓/FP)
  _popup           DetailDialog (pop-up detail baris)
  _hfilters        dict funnel LOKAL kolom→list nilai
  _disp_cache      OrderedDict LRU display (weakref df → salinan ber-✓)
  _mask_cache      OrderedDict LRU mask isin
  _fps/_fps_src    memo sidik jari per objek df
  _DISP_LRU        konstanta kelas ukuran LRU display (Anomali 8, Hari 4)
  _refresh_table() metode render ulang tabel view

HF_COLS: mapping kolom tabel → key filter GLOBAL ctx (sumber tunggal —
dulunya didefinisikan view_anomali lalu diimpor view_hari; sama persis).
"""
from __future__ import annotations

import weakref

import pandas as pd

from .shared import fmt_id
from waste_anomaly.followup import CHECK_COL, FP_COL, fingerprint_series

# Kolom tabel → key filter GLOBAL (antar-tab sinkron via ctx.active_filters).
HF_COLS = {
    "NAMA RESTO": "cabang", "NAMA BARANG": "item", "JENIS": "jenis",
    "KETERANGAN": "keterangan", "ANOMALY STATUS": "status",
}


class FollowupTableMixin:
    """Perilaku tabel ✓-follow-up + funnel lokal — dipakai Anomali &
    Hari Mencurigakan (v2.13.8; metode dipindah VERBATIM dari kedua view)."""

    # Ukuran LRU display df — di-override view (Anomali 8, Hari 4).
    _DISP_LRU = 8

    # ------------------------------------------------------------
    # INTERAKSI BARIS
    # ------------------------------------------------------------
    def _on_selection(self) -> None:
        """Klik 1×/navigasi baris → ikuti pop-up HANYA bila sudah TERBUKA
        (v2.18.6 — permintaan user: "klik sekali aja pop up langsung
        muncul… kadang bikin klik yang gak sengaja ketriger munculin
        pop up"). Pop-up kini dibuka lewat KLIK-GANDA / Enter
        (_open_popup_row); klik 1× saat pop-up tertutup = tanpa efek.
        v2.13.5: tekanan di sel ✓ → pop-up TIDAK dibuka (aksi centang
        murni — flag window mousePressEvent, lihat suppress_row_popup)."""
        if self._table.suppress_row_popup():
            return
        if not self._popup.isVisible():
            return  # pop-up tertutup → klik 1× tak sengaja: no-op
        rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    def _open_popup_row(self, rec=None) -> None:
        """KLIK-GANDA baris (sinyal double_clicked) / Enter → buka pop-up
        detail (v2.18.6). rec = record dari sinyal (fallback: baris
        terpilih). Ini SATU-SATUNYA jalur membuka pop-up — klik 1× tak
        lagi memicu apa pun (permintaan user; dulu v2.8.1-v2.18.5:
        klik 1× langsung buka pop-up)."""
        if self._table.suppress_row_popup():
            return
        if rec is None:
            rec = self._table.selected_record()
        if rec is not None:
            self._popup.show_record(rec)

    # ------------------------------------------------------------
    # FOLLOW UP: display ✓/__FP + toggle + sinkron in-place
    # ------------------------------------------------------------
    def _fps_for(self, df: pd.DataFrame) -> pd.Series:
        """Sidik jari baris (memo per objek df — nilai tak pernah berubah
        utk df yang sama; pola memo objek cache fit).

        v2.12.1: bila memo dataset PENUH tersedia (dibangun PipelineWorker
        di thread background), sidik jari subset = reindex O(len) (~2 ms)
        BUKAN md5 ulang (~40-100 ms per state). Memo penuh TIDAK dipicu
        dari sini (bangun malas 25.901 baris di thread UI = beku) —
        fallback md5 lokal bila belum ada."""
        if self._fps_src is not df or self._fps is None:
            full = None
            c = self._ctx
            if (getattr(c, "_fp_series", None) is not None
                    and c._fp_version == c.data_version
                    and c._fp_series.index.is_unique
                    and df.index.is_unique
                    and df.index.isin(c._fp_series.index).all()):
                full = c._fp_series
            if full is not None:
                self._fps = full.reindex(df.index)
            else:
                self._fps = fingerprint_series(df)
            self._fps_src = df
        return self._fps

    def _display_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Salinan df + kolom ✓ (bool) + __FP — OBJEK STABIL per objek df
        (LRU + weakref, v2.12.1) supaya cache fit DataTable tetap kena
        ANTAR-STATE (toggle funnel A→B→A: objek display A dipakai ulang,
        bukan salinan baru tiap kali); nilai ✓ SELALU disegarkan dari
        state saat dipakai.

        Kontrak 'konsumen hanya membaca' utk objek LRU anomali / enriched
        tetap utuh: mutasi centang hanya menyentuh salinan view ini."""
        key = id(df)
        entry = self._disp_cache.get(key)
        if entry is not None and entry[0]() is df and entry[1] is not None:
            self._disp_cache.move_to_end(key)
            disp = entry[1]
            disp[CHECK_COL] = disp[FP_COL].isin(
                self._ctx.followup_set())
            return disp
        fps = self._fps_for(df)
        disp = df.copy()
        disp[FP_COL] = fps
        disp.insert(0, CHECK_COL, fps.isin(self._ctx.followup_set()))
        self._disp_cache[key] = (weakref.ref(df), disp)
        while len(self._disp_cache) > self._DISP_LRU:
            self._disp_cache.popitem(last=False)
        return disp

    def _on_check_toggled(self, row: int, checked: bool) -> None:
        """Klik sel ✓ → state ctx (broadcast → badge tab + tab Follow Up)."""
        rec = self._table.model().record(row)
        fp = rec.get(FP_COL) if rec is not None else None
        if fp is None or str(fp) == "nan":
            return
        self._ctx.toggle_followup(str(fp), checked)
        n = len(self._ctx.followup_keys)
        self._ctx.set_status(
            ("✓ Masuk Follow Up" if checked else "✓ Dikeluarkan dari Follow Up")
            + f" — total {fmt_id(n)} baris", "done")

    def _on_followup_changed(self) -> None:
        """State follow-up berubah (toggle di mana pun/bulk/prune) —
        segarkan kolom ✓ model IN-PLACE (dataChanged satu kolom) —
        BUKAN render ulang (cache fit + ukuran baris tak tersentuh).
        v2.18.7: hook ``_followup_filter_active()`` — view yang punya
        filter tampilan berbasis keanggotaan follow-up (combo
        "Tampilkan: ✓ Sudah masuk Follow Up" di AnomaliView) tak bisa
        sekadar menyegarkan ✓: keanggotaan = hasil filter → lepas
        centang harus LANGSUNG menghilangkan barisnya → render ulang
        penuh (pola lazy H2 bila view tersembunyi)."""
        if self._followup_filter_active():
            if self.isVisible():
                self._refresh_table()
            else:
                self._dirty = True
            return
        m = self._table.model()
        mdf = m.dataframe
        if (mdf is not None and len(mdf) > 0
                and CHECK_COL in mdf.columns and FP_COL in mdf.columns):
            mdf[CHECK_COL] = mdf[FP_COL].isin(self._ctx.followup_set())
            m.notify_column_changed(CHECK_COL)

    def _followup_filter_active(self) -> bool:
        """v2.18.7 hook — True bila view ini punya filter TAMPILAN yang
        bergantung pada keanggotaan follow-up (→ _on_followup_changed
        memilih render ulang, bukan segarkan ✓ in-place).

        Default False; AnomaliView meng-override (combo "Tampilkan:" =
        ✓ Sudah masuk Follow Up). Pola hook _reset_view_controls —
        view kembar tak menyalin metode mixin (kontrak test_v2138)."""
        return False

    def _on_check_all(self) -> None:
        """Tombol '☑ Centang yang tampil' — semua baris model saat ini
        (hasil filter/funnel) masuk follow-up, SATU broadcast."""
        mdf = self._table.model().dataframe
        if mdf is None or len(mdf) == 0 or FP_COL not in mdf.columns:
            self._ctx.set_status("Tidak ada baris yang tampil — longgarkan "
                                 "filter dulu.", "error")
            return
        fps = [str(v) for v in mdf[FP_COL].tolist()]
        added = self._ctx.add_followup_many(fps)
        total = len(self._ctx.followup_keys)
        if added:
            self._ctx.set_status(
                f"✓ {fmt_id(added)} baris masuk Follow Up — total {fmt_id(total)}",
                "done")
        else:
            self._ctx.set_status(
                f"Semua baris yang tampil sudah tercentang (total {fmt_id(total)})",
                "done")

    # ------------------------------------------------------------
    # FUNNEL: global (HF_COLS) + lokal tampilan
    # ------------------------------------------------------------
    def _on_header_filter(self, col: str, key: str, values) -> None:
        """v2.12.3 — menu funnel header → state ctx (satu sumber
        kebenaran active_filters).
        v2.12.4 — kolom NON-mapping (SEMUA kolom lain punya funnel kini):
        filter LOKAL tampilan view ini (mask isin — state ctx tak
        tersentuh, KPI & Follow Up tak berubah)."""
        if col in HF_COLS:
            self._ctx.set_filter(key, values)  # global — antar-tab sinkron
            return
        if values:
            self._hfilters[col] = list(values)
        else:
            self._hfilters.pop(col, None)
        self._refresh_table()

    def _hf_state(self, col: str):
        """v2.12.3 — status funnel kolom utk MELUKIS (aktif = terisi).
        List kosong = tanpa filter (semantik _apply_filters).
        v2.12.4 — kolom lokal: baca _hfilters view."""
        key = HF_COLS.get(col)
        if key is not None:
            v = self._ctx.active_filters.get(key)
            if isinstance(v, list):
                return v or None
            if isinstance(v, str) and v:
                return [v]
            return None
        v = self._hfilters.get(col)
        return list(v) if v else None

    def _mask_local(self, disp: pd.DataFrame) -> pd.DataFrame:
        """v2.12.4 — mask isin per kolom funnel LOKAL di atas display df.

        Memo LRU per (id objek display, tanda tangan filter) supaya objek
        hasil STABIL per state → cache fit DataTable tetap kena (pola
        _disp_cache). Kolom ✓ disegarkan tiap pemakaian (state follow-up
        bisa berganti saat objek ini tak sedang jadi model).

        v2.13.13 (gel-4 A5+C10): entri kini (weakref, hasil) dgn
        VALIDASI IDENTITAS ``entry[0]() is disp`` — dulu kunci id()
        TANPA strong-ref/validasi: id bisa DIPAKAI ULANG objek lain
        pasca-GC → tabrakan id mengembalikan mask baris STATE LAMA
        (data salah, jarang tapi nyata — audit A5; komentar lama
        "strong ref" yang menutupi celah ini dihapus jujur — audit
        C10). Pola = _disp_cache/_change_cache (weakref + identity)."""
        if not self._hfilters:
            return disp
        sig = tuple(sorted((c, tuple(v)) for c, v in self._hfilters.items()))
        key = (id(disp), sig)
        entry = self._mask_cache.get(key)
        if (entry is not None and entry[0]() is disp
                and entry[1] is not None):
            self._mask_cache.move_to_end(key)
            out = entry[1]
        else:
            m = pd.Series(True, index=disp.index)
            for col, vals in self._hfilters.items():
                if col in disp.columns and vals:
                    m &= disp[col].isin(vals)
            # .copy() eksplisit — hasil slice dgn _is_copy terpasang;
            # assignment kolom ✓ di bawah memicu SettingWithCopyWarning
            # palsu (objek ini memang salinan baru milik memo).
            out = disp[m].copy()
            self._mask_cache[key] = (weakref.ref(disp), out)
            while len(self._mask_cache) > 4:
                self._mask_cache.popitem(last=False)
        if CHECK_COL in out.columns and FP_COL in out.columns:
            out[CHECK_COL] = out[FP_COL].isin(self._ctx.followup_set())
        return out

    def _on_clear_filters(self) -> None:
        """v2.12.4 — tombol '✕ Hapus Filter': lepas SEMUA filter aktif
        (funnel global ctx + funnel lokal view + ambang skor) — pengganti
        tombol 'Hapus Semua Filter' sidebar yang dihapus.
        v2.13.8 (gel-C): klausa day_min/search dihapus — field sudah tak
        ada (fitur mati sejak v2.12.4; audit D11).
        v2.13.10 (gel-1 A1): kontrol filter MILIK VIEW (combo 'Kategori
        PERUBAHAN' AnomaliView — re-apply via currentData() di
        _refresh_table_impl) ikut direset PRA-render lewat hook
        _reset_view_controls() — dulu tooltip menjanjikan 'Hapus SEMUA
        filter' tapi combo tetap aktif → tabel diam-diah hanya menampilkan
        satu kategori (tooltip menipu; audit A1)."""
        self._hfilters.clear()
        # PRA-render: reset kontrol view dulu — nilai combo baru terbaca
        # benar oleh _refresh_table_impl di bawah (blockSignals di override
        # mencegah currentIndexChanged memicu render ganda).
        self._reset_view_controls()
        had_global = bool(self._ctx.active_filters and any(
            v for v in self._ctx.active_filters.values())) \
            or self._ctx.score_min > 0
        if had_global:
            self._ctx.reset_filters()   # score_min ikut 0 — spin disinkronkan render
            self._ctx.filters_changed.emit()
        else:
            self._refresh_table()
        self._ctx.set_status("✓ Semua filter dihapus", "done")

    def _reset_view_controls(self) -> None:
        """v2.13.10 (gel-1 A1) — reset kontrol filter MILIK VIEW (bukan
        funnel global/lokal); dipanggil _on_clear_filters PRA-render.

        Default NO-OP: mixin dipakai AnomaliView & HariView — hanya
        AnomaliView punya kontrol filter ekstra (combo 'Kategori
        PERUBAHAN', filter LOKAL view yang di-apply ulang di
        _refresh_table_impl). HariView tak terdampak: _cb_mode-nya bukan
        filter (mode tampilan bukti-hari — reset-nya di refresh()).
        View pemakai mixin yang menambah kontrol filter cukup override
        hook ini (pola _cb_mode view_hari)."""
        return None
