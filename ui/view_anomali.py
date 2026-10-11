"""view_anomali.py — view utama (default): perburuan anomali (v2.6.0).

Landing pertama aplikasi: tabel anomali TER-RANKING (skor turun) + KPI
terfilter. Semua teks word-wrap; tabel tanpa cap baris; kolom auto-width
+ wrap.

v2.8.1: panel detail inline DIGANTI pop-up — klik baris tabel membuka
jendela pop-up non-modal berisi 12 sinyal + peer + uang + tombol
drill-down. Tabel kini memenuhi SELURUH tinggi view (tanpa splitter).
Kolom "% to BOM" (waste dibanding penjualan kuantiti) ditambahkan ke
tabel per-ranking; kolom rasio ditampilkan sebagai persen.

v2.13.5 (permintaan user "hilangkan yang klik 2x"): klik-2× baris TIDAK
LAGI memasang filter cabang+item — perilaku itu justru sumber keluhan
"klik 1× pop-up kadang tidak muncul dan malah ketrigger klik 2× yang
langsung filter" (klik-2× → set_filter → render ulang → pop-up di-hide
di awal _refresh_table_impl). Jalur drill fokus kini HANYA tombol
eksplisit di pop-up detail (niat user jelas, tak pernah tak disengaja).
Pop-up kini juga muncul ulang saat baris YANG SAMA diklik lagi (tutup
pop-up → klik baris sama dulu: currentRowChanged tak memicu — sinyal
QTableView.clicked kini ikut dihubungkan + guard idempoten di
DetailDialog.show_record supaya klik-baris-berganti tidak membangun
ulang panel dua kali).

v2.13.9 (permintaan user "pop up hanya tampilkan yang penting-penting
aja, jangan semua — aku jadi bingung"): DetailPanel didesain ulang —
RINGKASAN (±7 angka kunci berlabel awam) + chip sinyal TERPICU SAJA +
alasan + peta hari + tombol tindak lanjut; daftar ±25 kolom lengkap
kini di balik tombol "▸ Tampilkan semua kolom data" (default sembunyi,
per-baris). Guard funnel v2.12.5 diperluas ke TEKAN TUNGGAL replay
(mousePressEvent — lihat widgets.py: bug "klik filter muncul pop-up").

v2.13.10 (gel-1 deep audit): footer AKSI STICKY di DetailPanel —
tombol tindak lanjut/drill/pembuka kolom lengkap pindah DI LUAR
QScrollArea (audit V1: CTA dulunya di bawah lipatan gulir pop-up);
hook _reset_view_controls + reset combo kategori PERUBAHAN di
_on_clear_filters/refresh (audit A1/A2 — "Hapus SEMUA filter" kini
benar-benar SEMUA, dataset baru tak mewarisi kategori run lama).
"""
from __future__ import annotations

import weakref
from collections import OrderedDict

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from waste_anomaly.followup import (
    CHECK_COL,
    FP_COL,
    fingerprint_series,
)
from waste_anomaly.period_history import CHANGE_CATEGORIES, change_vs_history
from waste_anomaly.profile import annotate_profile_vs_history
from waste_anomaly.signals import SIGNAL_PARTS

from .followup_table import FollowupTableMixin, HF_COLS as _HF_COLS
from .models import (
    COLUMN_TOOLTIPS,
    DELTA_PCT_COLS,
    PCT_COLS,
    RATIO_X_COLS,
    fmt_cell,
    fmt_delta_pct,
    fmt_pct,
    fmt_ratio_x,
)
from .shared import baseline_label, fmt_id
from .state import AppContext
from .widgets import (
    Card,
    DataTable,
    KpiStrip,
    StatusChip,
    WLabel,
    busy_feedback,
    status_chip_for,
)

# Kolom tabel anomali — ramping (detail lengkap ada di pop-up detail).
# v2.6.1: 10 → 7 kolom (MAX / HARI MAX / RANGKING WASTE duplikatif).
# v2.8.1: 7 → 8 — "% to BOM" (waste vs penjualan kuantiti) ditambahkan
# setelah TOTAL sesuai permintaan user: rasio per-ranking terlihat langsung
# di tabel. Nilai 'Cek' = item tanpa data penjualan (tak bisa dihitung).
TABLE_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "PROFIL", "NAMA RESTO",
    "NAMA BARANG", "JENIS", "KETERANGAN", "TOTAL", "% to BOM",
    # v2.10.2: muncul hanya bila pembanding bulan lalu tersedia (kolom
    # ditambahkan ADDITIF oleh change_vs_history — tanpa pembanding tabel
    # identik v2.10.1, pola view Hari Mencurigakan).
    "BULAN LALU", "PERUBAHAN %", "PERUBAHAN",
]

# v2.12.3: funnel filter di header tabel (permintaan user "daripada aku
# harus pakai slicer"). Kolom → kunci filter ctx — STATE TETAP SATU di
# ctx.active_filters.
# v2.12.4: funnel di SEMUA kolom (permintaan user "harusnya semua kolom
# punya filter"): 5 kolom mapping tetap GLOBAL (sinkron antar tab Anomali/
# Hari + KPI ikut terfilter); kolom lain = filter LOKAL tampilan view ini
# (mask isin per kolom — KPI/daftar Follow Up tak tersentuh).
# v2.13.8 (gel-C): _HF_COLS kini tinggal di followup_table.HF_COLS (satu
# sumber — dulu modul ini + view_hari mengimpor kembali; isi SAMA persis).


# 12 sinyal — label ringkas utk chip + fragmen teks ANOMALY REASONS
# (sumber tunggal fragmen: SIGNAL_PARTS di waste_anomaly/signals.py).
# v2.7.0 (lanjutan V26-C1): kolom _s1.._s12 DI-DROP pipeline sebelum df
# sampai UI, jadi status terpicu chip dibaca dari fragmen di teks
# ANOMALY REASONS; nilai _s* hanya fallback bila kolom ada (fixture
# test sintetis) — sebelum fix ini 12 chip SELALU abu-abu di data riil.
# v2.9.0 (permintaan user "permudah istilah"): label tanpa jargon;
# penjelasan lengkap tiap sinyal ada di _CHIP_TIPS (tooltip chip).
_CHIP_LABELS = {
    "_s1": "S1 · Lonjakan vs rata-rata",
    "_s2": "S2 · Lonjakan vs hari aktif",
    "_s3": "S3 · Lonjakan vs nilai tengah",
    "_s4": "S4 · Terpusat di satu hari",
    "_s5": "S5 · Jauh di atas hari kedua",
    "_s6": "S6 · Puncak vs BOM",
    "_s7": "S7 · Total vs BOM",
    "_s8": "S8 · Puncak vs cabang lain",
    "_s9": "S9 · Total vs cabang lain",
    "_s10": "S10 · Waste hanya 1 hari",
    "_s11": "S11 · Menumpuk di hari terakhir",
    "_s12": "S12 · Pola 10× (salah ketik?)",
}

# v2.9.0 — tooltip chip sinyal: penjelasan Bahasa awam + angka threshold
# + apa yang biasanya diperiksa. Hover chip = langsung paham.
_CHIP_TIPS = {
    "_s1": ("Nilai waste di satu hari ≥ 3× rata-rata harian item yang sama.\n"
             "Sering karena salah ketik angka (mis. 7 → 70) — cek tanggal "
             "di HARI TERSANGKA."),
    "_s2": ("Nilai terbesar ≥ 2,5× rata-rata HARI YANG ADA WASTENYA saja.\n"
             "Lebih adil dari S1: hari kosong tidak menarik rata-rata turun."),
    "_s3": ("Nilai terbesar ≥ 3× nilai tengah (median) hari aktif.\n"
             "Nilai tengah tahan terhadap 1 hari ekstrem — lonjakan besar "
             "di sini lebih kuat mencurigakan."),
    "_s4": ("≥ 50% waste sebulan terjadi di SATU hari (≥ 70% = skor penuh).\n"
             "Waste terpusat satu tanggal — cek apa kejadian nyata."),
    "_s5": ("Nilai terbesar ≥ 3× nilai terbesar kedua.\n"
             "Puncaknya menjulang sendirian — bukan pola harian biasa."),
    "_s6": ("Nilai terbesar SEHARI ≥ 25% penjualan SEMBULAN (≥ 50% = skor penuh).\n"
             "BOM = qty penjualan (bukan waste)."),
    "_s7": ("Total waste sebulan ≥ 50% penjualan (≥ 100% = skor penuh).\n"
             "BOM = qty penjualan (bukan waste)."),
    "_s8": ("Nilai terbesar ≥ 2× nilai tengah cabang lain, item sama "
             "(≥ 3× = skor penuh). Butuh ≥ 3 cabang pembanding."),
    "_s9": ("Total sebulan ≥ 3× nilai tengah total cabang lain (item sama).\n"
             "Butuh ≥ 3 cabang pembanding."),
    "_s10": ("Waste baris ini hanya terjadi 1 hari sebulan + nilainya besar\n"
              "(≥ 10% penjualan atau ≥ 2× cabang lain)."),
    "_s11": ("≥ 70% waste sebulan menumpuk di HARI TERAKHIR periode.\n"
              "Pola tumpukan akhir bulan — cek input hari terakhir."),
    "_s12": ("Nilai ≈ 10× / 100× / 1000× nilai tengah sendiri — pola khas "
              "salah ketik digit tambahan (7 → 70 → 700).\n"
              "Tab Hari Mencurigakan menunjukkan tanggalnya."),
}
SIGNALS: list[tuple[str, str, str]] = [
    (col, _CHIP_LABELS[col], frag) for col, frag in SIGNAL_PARTS
]

# Metrik konteks yang ditampilkan di detail pop-up (bila kolomnya ada)
DETAIL_COLS = [
    "ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO", "NAMA BARANG",
    "JENIS", "KETERANGAN", "SOURCE DATA", "TOTAL", "MAX", "AVG",
    "HARI MAX", "SATUAN", "TOTAL BOM", "% to BOM", "PEER COUNT",
    "PEER MEDIAN TOTAL", "PEER MEDIAN MAX", "TOTAL / PEER MEDIAN",
    "MAX / PEER MEDIAN MAX", "MAX / BOM", "TOTAL / BOM", "MAX SHARE",
    # v2.10.2: bukti perubahan vs bulan lalu (tampil bila pembanding ada)
    "BULAN LALU", "PERUBAHAN %", "PERUBAHAN",
    "LAST DAY SHARE", "KATEGORI ANOMALI", "RANGKING WASTE",
    # v2.13.0: profil pola waktu + kelebihan vs tipikal cabang lain
    "PROFIL", "KELEBIHAN", "PEER MEDIAN (AKTIF)", "PEER AKTIF",
]

# Baris (label, kolom sumber, formatter, kolom tooltip) RINGKASAN pop-up
# v2.13.9 — permintaan user: "data pada bagian pop up hanya tampilkan yang
# penting penting aja jangan semua ditampilkan aku jadi bingung". Pop-up
# lama menampilkan ±25 baris metrik SEKALIGUS — kini hanya ±7 angka kunci
# yang menjawab pertanyaan investigasi (apa/siapa/kapan/seberapa besar/
# dibanding siapa), label Bahasa awam; sisanya di balik tombol
# "Tampilkan semua kolom data".
_SUMMARY_SPECS: list[tuple[str, tuple[str, ...], object]] = [
    ("Jenis & alasan catatan", ("JENIS", "KETERANGAN"), "_join"),
    ("Total waste sebulan", ("TOTAL",), "_num0"),
    ("Puncak sehari", ("MAX",), "_peak"),
    ("vs penjualan (BOM)", ("% to BOM",), "_pct"),
    # v2.13.15 (gel-6 A18): label SPESIFIK "(sebulan)" — pop-up ini
    # memuat DUA median pembanding beda definisi: rasio ini dihitung vs
    # PEER MEDIAN TOTAL (median TOTAL sebulan cabang lain) sementara
    # daftar lengkap menampilkan PEER MEDIAN MAX (median puncak PER
    # HARI cabang lain); label generik "vs cabang lain (median)"
    # membuat keduanya dibaca sebagai angka sama (audit A18).
    ("vs median cabang lain (sebulan)", ("TOTAL / PEER MEDIAN",), "_ratio"),
    ("vs bulan lalu", ("PERUBAHAN %",), "_delta"),
    ("Peringkat waste cabang", ("RANGKING WASTE",), "_raw"),
]


def _rec_val(rec: pd.Series, col: str):
    """Nilai kolom baris; None bila hilang/NaN (pd.isna None-safe)."""
    v = rec.get(col)
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass  # nilai eksotis — biarkan formatter mengurus
    return v


def _summary_rows(rec: pd.Series) -> list[tuple[str, str, str]]:
    """Bangun baris ringkasan penting: (label, nilai, tooltip gabungan).

    Baris dengan nilai kosong DILEWATI — pop-up tetap ramping di data
    tanpa pembanding (Hari tab / fixture sintetis)."""
    out: list[tuple[str, str, str]] = []

    def tip(cols: tuple[str, ...]) -> str:
        return "\n\n".join(COLUMN_TOOLTIPS[c] for c in cols
                           if c in COLUMN_TOOLTIPS)

    for label, cols, how in _SUMMARY_SPECS:
        shown = ""
        if how == "_join":
            parts = [str(_rec_val(rec, c)).strip()
                     for c in cols if _rec_val(rec, c) is not None]
            parts = [p for p in parts if p and p not in ("nan", "None")]
            shown = " · ".join(parts)
        elif how == "_num0":
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_cell(v, 0)
                sat = _rec_val(rec, "SATUAN")
                if sat is not None and str(sat).strip():
                    shown += f" {str(sat).strip()}"
        elif how == "_peak":
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_cell(v, 0)
                for src in ("HARI TERSANGKA", "HARI MAX"):
                    h = _rec_val(rec, src)
                    if h is not None:
                        try:
                            shown += f" di tanggal {int(float(h))}"
                            break
                        except (TypeError, ValueError):
                            pass
        elif how == "_pct":
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_pct(v)
        elif how == "_ratio":
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_ratio_x(v)
                n = _rec_val(rec, "PEER COUNT")
                if n is not None:
                    try:
                        shown += (f" (median sebulan "
                                  f"{fmt_id(int(float(n)))} cabang)")
                    except (TypeError, ValueError):
                        pass
        elif how == "_delta":
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_delta_pct(v)
                old = _rec_val(rec, "BULAN LALU")
                if old is not None and fmt_cell(old, 0):
                    shown += f" — bulan lalu {fmt_cell(old, 0)}"
        else:  # _raw
            v = _rec_val(rec, cols[0])
            if v is not None:
                shown = fmt_cell(v)
        if shown:
            out.append((label, shown, tip(cols)))
    return out


class DetailPanel(Card):
    """Panel detail satu baris anomali: identitas + sinyal + drill-down.

    v2.8.1: panel ini tinggal DI DALAM DetailDialog (pop-up) — bukan lagi
    bagian splitter di bawah tabel.
    v2.13.9: isi RINGKAS (permintaan user): ringkasan angka kunci →
    sinyal terpicu saja → alasan → peta hari → tindak lanjut → tombol
    pembuka daftar kolom lengkap (default tersembunyi).
    v2.13.10 (gel-1 V1): susunan dua zona — KONTEN GULIR (ringkasan →
    sinyal → alasan → peta hari → kolom lengkap) + FOOTER AKSI STICKY
    di luar QScrollArea (judul seksi tindak lanjut + ☑ Masuk Follow Up
    + drill fokus + pembuka kolom lengkap) — CTA utama selalu terlihat
    tanpa menggulir.
    """

    # Prompt default — dipakai __init__ DAN clear() (V26-L12)
    # v2.13.9: teks mengikuti desain ringkas (ringkasan + sinyal terpicu
    # + peta hari; kolom lengkap di balik tombol).
    # v2.13.12 (gel-3 A13): frasa era panel-inline "menampilkan detailnya
    # di sini" dibuang (panel poped-out sejak v2.8.1 — "di sini" menipu:
    # detailnya bukan di panel ini melainkan di pop-up) → deskripsi jujur
    # isi pop-up + footer aksi yang selalu terlihat (gel-1 V1).
    _PROMPT = ("Klik baris di tabel untuk membuka pop-up detail: ringkasan "
               "angka kunci, sinyal terpicu, peta nilai per hari, dan "
               "tombol tindak lanjut (drill fokus + masuk Follow Up) di "
               "footer yang selalu terlihat.")

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        # v2.13.5: tombol follow-up di pop-up (sinkron dgn state ctx —
        # toggle dari mana pun memperbarui teksnya tanpa rebuild).
        self._fu_btn: QPushButton | None = None
        self._cur_fp: str | None = None
        # v2.13.9: wadah + tombol kolom-lengkap (diisi show_record).
        self._full_box: QWidget | None = None
        self._more_btn: QPushButton | None = None
        # v2.13.12 (gel-3 A11): jumlah kolom lengkap DISIMPAN supaya teks
        # tombol mempertahankan '(N)' sepanjang siklus buka/tutup (dulu
        # angka hilang setelah siklus pertama — toggle kedua menulis teks
        # tanpa angka, user tak tahu lagi berapa kolom yang disembunyikan).
        self._n_full: int = 0
        ctx.followup_changed.connect(self._on_fu_state_changed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._title = WLabel(self._PROMPT, self)
        self._title.setObjectName("cardTitle")
        lay.addWidget(self._title)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self._scroll, 1)
        self._content = QWidget()
        self._scroll.setWidget(self._content)

        # v2.13.10 (gel-1 V1): footer AKSI STICKY — DI LUAR QScrollArea.
        # Audit V1 (geometri terukur): tombol "☑ Masuk Follow Up"
        # (y≈623) & pembuka kolom lengkap (y≈698) dulunya anak KONTEN
        # GULIR di bawah lipatan viewport pop-up (578px) — CTA utama tak
        # terlihat sampai user menggulir melewati peta hari (VLM: "tidak
        # ada tombol aksi terlihat"). Footer menampung: judul seksi +
        # tombol follow-up + baris drill fokus + pembuka kolom lengkap;
        # yang tetap digulir: ringkasan → sinyal → alasan → peta hari →
        # kolom lengkap (dibuka → ensureWidgetVisible menggulir otomatis).
        # Dibangun ulang per show_record (teardown di clear()/show_record
        # — ref mayat direset lebih dulu, pola v2.13.5).
        self._actions = QWidget(self)
        self._actions_lay = QVBoxLayout(self._actions)
        self._actions_lay.setContentsMargins(4, 0, 4, 0)
        self._actions_lay.setSpacing(6)
        lay.addWidget(self._actions)

    def clear(self) -> None:
        """Kosongkan panel (V26-L12): df terfilter berubah → record yang
        sedang ditampilkan bisa jadi sudah tidak lolos filter — jangan
        biarkan panel menampilkan data basi (pola teardown show_record).
        v2.13.5: ref tombol follow-up + fp ikut direset (widgetnya
        sudah deleteLater — jangan biarkan handler menyentuh mayat).
        v2.13.9: ref wadah/tombol kolom-lengkap ikut direset (mayat).
        v2.13.10 (gel-1 V1): footer AKSI ikut dikosongkan (pola teardown
        _content — widget mayat tak tersisa)."""
        self._fu_btn = None
        self._cur_fp = None
        self._full_box = None
        self._more_btn = None
        self._title.setText(self._PROMPT)
        old = self._content.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._teardown_actions()

    def _teardown_actions(self) -> None:
        """v2.13.10 (gel-1 V1) — buang semua widget footer AKSI (dipanggil
        clear() + awal show_record; ref _fu_btn/_more_btn sudah direset
        PEMANGGIL sebelum panggilan ini — handler tak menyentuh mayat)."""
        alay = self._actions.layout()
        if alay is not None:
            while alay.count():
                item = alay.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def show_record(self, rec: pd.Series) -> None:
        """Render ulang konten detail dari record baris terpilih.

        v2.13.9 — desain "hanya yang penting" (permintaan user: pop-up
        lama menampilkan SEMUA kolom sekaligus — membingungkan). Susunan
        KONTEN GULIR: chip status + skor → RINGKASAN (±7 angka kunci) →
        sinyal TERPICU saja (chip merah; jumlah di judul seksi) → alasan
        → peta hari 1-31 → kolom lengkap (±25 baris metrik tersembunyi,
        di balik tombol).
        v2.13.10 (gel-1 V1) — baris TINDAK LANJUT + drill fokus + pembuka
        kolom lengkap pindah ke footer AKSI STICKY di luar area gulir
        (CTA utama selalu terlihat tanpa menggulir — audit V1)."""
        # v2.13.5: reset ref tombol follow-up (konten lama dibuang —
        # tombol lama dideleteLater; nilai baru dipasang di bawah).
        self._fu_btn = None
        self._cur_fp = None
        self._full_box = None   # v2.13.9: ref wadah kolom lengkap
        self._more_btn = None   # v2.13.9: ref tombol pembuka kolom lengkap
        # Buang konten lama
        old = self._content.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        else:
            from PySide6.QtWidgets import QVBoxLayout as _VL
            old = _VL(self._content)
        # v2.13.10 (gel-1 V1): footer aksi ikut dibangun ulang — widget
        # footer lama dideleteLater (ref direset di atas, mayat tak
        # tersentuh handler).
        self._teardown_actions()

        lay = old
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)
        alay = self._actions_lay   # footer STICKY (di luar scroll)

        cabang = fmt_cell(rec.get("NAMA RESTO"))
        item_name = fmt_cell(rec.get("NAMA BARANG"))
        status = fmt_cell(rec.get("ANOMALY STATUS"))
        skor = fmt_cell(rec.get("ANOMALY SCORE"))
        self._title.setText(f"Anomali — Skor {skor} — {cabang} — {item_name}")

        # Baris identitas: chip status + skor
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        hl.addWidget(status_chip_for(status))
        skor_lbl = QLabel(f"Skor {skor} dari 19", head)
        skor_lbl.setStyleSheet("font-weight:700;")
        hl.addWidget(skor_lbl)
        hl.addStretch(1)
        lay.addWidget(head)

        # v2.13.9 — RINGKASAN PENTING (permintaan user "yang penting-penting
        # aja"): ±7 angka kunci berlabel Bahasa awam, nilai kosong dilewati.
        # Tooltip label/nilai = kamus istilah kolom sumbernya.
        sum_rows = _summary_rows(rec)
        if sum_rows:
            lay.addWidget(self._section("Ringkasan"))
            sum_w = QWidget()
            sfl = QFormLayout(sum_w)
            sfl.setContentsMargins(0, 0, 0, 0)
            sfl.setSpacing(4)
            sfl.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for label, shown, tip in sum_rows:
                key = QLabel(f"{label}:", sum_w)
                key.setStyleSheet("color:#64748b;")
                if tip:
                    key.setToolTip(tip)
                val_lbl = WLabel(shown, sum_w)
                val_lbl.setStyleSheet("font-weight:600;")
                if tip:
                    val_lbl.setToolTip(tip)
                sfl.addRow(key, val_lbl)
            lay.addWidget(sum_w)

        # Sinyal TERPICU SAJA (v2.13.9 — dulu grid 12 chip: 7-11 di
        # antaranya abu-abu "tidak terpicu" = kebisingan visual; yang
        # penting investigasi = chip MERAH. Jumlah total tetap disebut
        # di judul seksi; nilai _s* / fragmen ANOMALY REASONS baca
        # seperti v2.7.0 — lihat komentar SIGNALS di atas).
        reasons_raw = rec.get("ANOMALY REASONS")
        reasons_text = "" if reasons_raw is None else str(reasons_raw)
        if reasons_text in ("nan", "None", "<NA>"):
            reasons_text = ""
        trig: list[tuple[str, str]] = []
        for col, label, fragment in SIGNALS:
            val = rec.get(col, 0)
            try:
                val = float(pd.to_numeric(pd.Series([val])).iloc[0])
            except Exception:
                val = 0.0
            triggered = (val > 0) or (fragment in reasons_text)
            if triggered:
                text = (f"{label} ✓ ({fmt_id(val, 0)})" if val > 0
                        else f"{label} ✓")
                trig.append((col, text))
        lay.addWidget(self._section(
            f"Sinyal terpicu ({len(trig)} dari {len(SIGNALS)})"))
        if trig:
            grid = QWidget()
            gl = QGridLayout(grid)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.setSpacing(6)
            for i, (col, text) in enumerate(trig):
                chip = StatusChip(text, "#dc2626", "#fef2f2")
                # v2.9.0: hover chip = penjelasan sinyal Bahasa awam
                # (permintaan user: tooltip SEMUA istilah, bukan hanya S-1).
                tip = _CHIP_TIPS.get(col, "")
                if tip:
                    chip.setToolTip(tip)
                gl.addWidget(chip, i // 3, i % 3)
            lay.addWidget(grid)
        else:
            note = WLabel("Tidak ada sinyal terpicu pada baris ini.",
                          self._content)
            note.setObjectName("muted")
            lay.addWidget(note)

        # Alasan (teks lengkap ANOMALY REASONS)
        reasons = fmt_cell(rec.get("ANOMALY REASONS"))
        if reasons:
            lay.addWidget(self._section("Alasan terdeteksi"))
            lay.addWidget(WLabel(reasons))

        # Metrik konteks LENGKAP (v2.13.9: kini di balik tombol — dulu
        # QFormLayout ±25 baris tampil SELALU, sumber "aku jadi bingung").
        # Dibangun utuh seperti v2.8.1 (format persen/rasio/teks sama),
        # lalu disembunyikan; tombol toggle ada di footer AKSI (v2.13.10).
        # v2.13.14 (gel-5 A17): widget DIBANGUN HANYA bila ada kolomnya —
        # dulu full_box + label seksi dibuat duluan lalu tak ditambahkan
        # ke layout mana pun saat n_full==0 → QWidget TANPA PARENT
        # ("yatim") dipegang self._full_box sampai show_record berikutnya
        # (audit A17: box kosong + potensi window liar bila ter-show).
        _FULL_SKIP = ("ANOMALY SCORE", "ANOMALY STATUS", "NAMA RESTO",
                      "NAMA BARANG", "ANOMALY REASONS")
        # v2.13.15 (gel-6 A18): sufiks scope kolom median pembanding di
        # daftar lengkap — "PEER MEDIAN MAX" (median puncak PER HARI
        # cabang lain) vs "PEER MEDIAN TOTAL" (median TOTAL SEBULAN)
        # tampil bersebelahan dgn nama mirip; tanpa pembeda dua baris
        # dibaca sebagai angka sama sekadar beda nama (audit A18: dua
        # "median cabang lain" beda definisi dalam satu pop-up).
        _FULL_SCOPE: dict[str, str] = {
            "PEER MEDIAN TOTAL": " — median cabang lain sebulan",
            "PEER MEDIAN MAX": " — median cabang lain per hari (puncak)",
            "PEER MEDIAN (AKTIF)": " — median cabang lain sebulan "
            "(hanya cabang yang punya waste)",
        }
        full_cols = [col for col in DETAIL_COLS
                     if col not in _FULL_SKIP and col in rec.index]
        n_full = len(full_cols)
        full_box: QWidget | None = None
        if n_full:
            full_box = QWidget()
            fbl = QVBoxLayout(full_box)
            fbl.setContentsMargins(0, 0, 0, 0)
            fbl.setSpacing(4)
            fbl.addWidget(self._section("Konteks & pembanding — semua kolom"))
            metrics = QWidget()
            fl = QFormLayout(metrics)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(4)
            fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for col in full_cols:
                key = QLabel(
                    f"{col}{_FULL_SCOPE.get(col, '')}:", metrics)
                key.setStyleSheet("color:#64748b;")
                # v2.9.0: label metrik + nilai dapat tooltip kamus istilah
                tip = COLUMN_TOOLTIPS.get(col)
                if tip:
                    key.setToolTip(tip)
                # v2.8.1: kolom rasio (BOM/SHARE) tampil sebagai persen —
                # '0,00080' mentah tak terbaca manusia.
                val = rec.get(col)
                shown = (fmt_pct(val) if col in PCT_COLS
                         else fmt_delta_pct(val) if col in DELTA_PCT_COLS
                         else fmt_ratio_x(val) if col in RATIO_X_COLS
                         else fmt_cell(val))
                val_lbl = WLabel(shown, metrics)
                val_lbl.setStyleSheet("font-weight:600;")
                if tip:
                    val_lbl.setToolTip(tip)
                fl.addRow(key, val_lbl)
            fbl.addWidget(metrics)
            full_box.setVisible(False)
            self._full_box = full_box
        else:
            # A17: tanpa kolom tambahan → TIDAK ada tombol, TIDAK ada box
            # (ref None = _toggle_full no-op guard lama tetap benar).
            self._full_box = None
        # v2.13.12 (gel-3 A11): simpan jumlah kolom lengkap utk siklus
        # toggle berikutnya (teks tombol mempertahankan '(N)').
        self._n_full = n_full

        # Peta hari 1-31 (v2.9.0): nilai waste per hari dalam mini-grid —
        # hari tersangka disorot merah. "Grafik batang" tanpa matplotlib:
        # 31 sel kecil (8 per baris) menunjukkan di tanggal mana angka
        # besar itu duduk — jawaban visual utk "potensi salah angka di
        # tanggal berapa".
        # v2.12.3 (redesain permintaan user): dulu sel berisi '13:1.245'
        # (tanggal:nilai) — PEMBUANGKAN makna: user membaca '13:…' sebagai
        # bagian nilai ("kira 13 itu nilainya"). Kini DUA BARIS: tanggal
        # kecil redup di atas + nilai TEBAL di bawah — tanggal & nilai tak
        # mungkin tertukar lagi.
        # v2.13.12 (gel-3 A14): rentang judul DINAMIS dari kolom hari yang
        # benar-benar ada di record (key_akhir=30 → '1–30'; dulu SELALU
        # '1–31' — judul mendiskripsikan kolom yang tak ada).
        day_names = [c for c in (str(i) for i in range(1, 32))
                     if c in rec.index]
        day_rng = (f"{int(day_names[0])}–{int(day_names[-1])}"
                   if day_names else "1–31")
        lay.addWidget(self._section(
            f"Nilai per hari ({day_rng}) — angka kecil = TANGGAL, angka "
            "besar = NILAI; sel merah = hari tersangka"))
        lay.addWidget(self._day_map(rec))

        # v2.13.10 (gel-1 V1): kolom lengkap = item KONTEN GULIR TERAKHIR
        # (setelah peta hari — data mentah opsional, tak menghalangi CTA).
        # Dibuka → ensureWidgetVisible otomatis menggulir ke daftarnya.
        if n_full:
            lay.addWidget(full_box)
        lay.addStretch(1)

        # ----------------------------------------------------------
        # v2.13.10 (gel-1 V1): FOOTER AKSI STICKY — tindak lanjut + drill
        # fokus + pembuka kolom lengkap DI LUAR QScrollArea (niat
        # eksplisit — satu-satunya jalur fokus sejak v2.13.5; klik-2×
        # baris tak lagi memfilter). Dulu baris ini anak KONTEN GULIR di
        # bawah lipatan viewport pop-up (y≈623-698 vs viewport 578px —
        # CTA tak terlihat tanpa menggulir; audit V1).
        # ----------------------------------------------------------
        alay.addWidget(self._section("Tindak lanjut & drill-down dari baris ini"))
        fp = self._row_fingerprint(rec)
        if fp is not None:
            self._cur_fp = str(fp)
            in_list = self._cur_fp in self._ctx.followup_set()
            self._fu_btn = QPushButton(self._fu_btn_text(in_list))
            self._fu_btn.setToolTip(
                "Tambahkan / keluarkan baris ini dari daftar Follow Up\n"
                "(tab Follow Up — format rekap siap serah terima petugas).\n"
                "Sama seperti mencentang kolom ✓ di tabel.")
            self._fu_btn.clicked.connect(self._on_fu_toggle)
            alay.addWidget(self._fu_btn)
        btns = QWidget()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        if rec.get("NAMA RESTO") is not None:
            b = QPushButton("🏬 Fokus cabang ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA RESTO"):
                              self._ctx.set_filter("cabang", v))
            bl.addWidget(b)
        if rec.get("NAMA BARANG") is not None:
            b = QPushButton("📦 Fokus item ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA BARANG"):
                              self._ctx.set_filter("item", v))
            bl.addWidget(b)
        if rec.get("KETERANGAN") is not None and str(rec.get("KETERANGAN")) not in ("", "nan"):
            b = QPushButton("🏷 Fokus alasan ini")
            b.clicked.connect(lambda _=False, v=str(rec.get("KETERANGAN")).strip():
                              self._ctx.set_filter("keterangan", v))
            bl.addWidget(b)
        bl.addStretch(1)
        alay.addWidget(btns)

        # v2.13.9 — tombol pembuka kolom lengkap (v2.13.10: ikut footer
        # sticky — aksi tetap terlihat tanpa gulir; data mentah = opsional).
        # Kolom lengkap = semua DETAIL_COLS baris ini.
        if n_full:
            more = QPushButton(
                f"▸ Tampilkan semua kolom data ({n_full})", self._actions)
            more.setToolTip(
                "Buka / tutup daftar lengkap semua kolom data baris ini.\n"
                "Dulu daftar ini selalu tampil (±25 baris) — kini "
                "tersembunyi supaya pop-up hanya menampilkan yang penting.")
            more.setStyleSheet(
                "QPushButton { text-align:left; color:#64748b; "
                "border:none; background:transparent; padding:2px 0; "
                "font-weight:400; }"
                "QPushButton:hover { color:#0f172a; }")
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.clicked.connect(self._toggle_full)
            self._more_btn = more
            alay.addWidget(more)

    def _toggle_full(self) -> None:
        """v2.13.9 — buka/tutup daftar kolom lengkap (teks tombol ikut).
        Baris baru (show_record) selalu mulai TERSEMBUNYI — pop-up "hanya
        yang penting" adalah keadaan default.
        v2.13.10 (gel-1 V1): tombol kini di footer sticky — daftar
        lengkap membuka DI AREA GULIR (bagian bawah konten, setelah peta
        hari); ensureWidgetVisible menggulir otomatis supaya daftar
        langsung terlihat begitu dibuka.
        v2.13.12 (gel-3 A11): '(N)' dipertahankan sepanjang siklus —
        jumlahnya dari self._n_full (dulu angka hilang pasca siklus
        pertama: teks toggle ditulis ulang tanpa angka)."""
        box = self._full_box
        if box is None:
            return
        show = box.isHidden()
        box.setVisible(show)
        if self._more_btn is not None:
            suffix = f" ({self._n_full})" if self._n_full else ""
            self._more_btn.setText(
                ("▾ Sembunyikan daftar kolom lengkap" if show
                 else "▸ Tampilkan semua kolom data") + suffix)
            try:
                self._more_btn.setToolTip(
                    "Klik utk menyembunyikan kembali daftar kolom lengkap."
                    if show else
                    "Buka / tutup daftar lengkap semua kolom data baris ini.")
            except RuntimeError:
                pass
        if show:
            # auto-gulir ke daftar yang baru dibuka (tombol di footer —
            # daftarnya sendiri jauh di bawah lipatan konten).
            try:
                self._scroll.ensureWidgetVisible(box)
            except RuntimeError:
                pass

    # ------------------------------------------------------------
    # v2.13.5 — tombol follow-up di pop-up (satu klik dari investigasi
    # ke daftar tindak lanjut; sinkron dua arah dgn kolom ✓ tabel)
    # ------------------------------------------------------------
    def _row_fingerprint(self, rec: pd.Series) -> str | None:
        """Sidik jari baris utk identitas follow-up.

        Utama: kolom __FP tersembunyi di record (tabel Anomali/Hari/
        Follow Up memasangnya di df tampilan — murah, tinggal baca).
        Fallback: hitung ulang utk 1 baris (record dari fixture tanpa
        __FP; ~ms — md5 satu baris). None hanya bila hash gagal."""
        v = rec.get(FP_COL)
        if v is not None and str(v) not in ("", "nan", "None"):
            return str(v)
        try:
            one = rec.to_frame().T
            fp = fingerprint_series(one)
            if len(fp):
                out = fp.iloc[0]
                if out:
                    return str(out)
        except Exception:  # noqa: BLE001, S110 — record eksotis (test fixture): fallback None memang perilaku yang diinginkan
            pass
        return None

    def _fu_btn_text(self, in_list: bool) -> str:
        return ("☑ Masuk Follow Up" if not in_list
                else "✅ Sudah di Follow Up — klik utk keluarkan")

    def _on_fu_toggle(self) -> None:
        """Klik tombol → toggle state ctx (broadcast → badge tab + tabel
        kolom ✓ semua view + tombol ini sendiri via _on_fu_state_changed)."""
        if self._cur_fp is None:
            return
        self._ctx.toggle_followup(
            self._cur_fp, self._cur_fp not in self._ctx.followup_set())
        n = len(self._ctx.followup_keys)
        self._ctx.set_status(
            f"✓ Daftar follow-up kini {fmt_id(n)} baris (dari pop-up "
            "detail)", "done")

    def _on_fu_state_changed(self) -> None:
        """followup_changed (toggle/bulk dari mana pun) → perbarui teks
        tombol pop-up IN-PLACE bila pop-up sedang menampilkan baris."""
        if self._fu_btn is not None and self._cur_fp is not None:
            try:
                self._fu_btn.setText(
                    self._fu_btn_text(self._cur_fp
                                      in self._ctx.followup_set()))
            except RuntimeError:  # widget sudah dihancurkan Qt (clear)
                self._fu_btn = None

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#0f172a; font-weight:700; border:none; background:transparent;")
        return lbl

    def _day_map(self, rec: pd.Series) -> QWidget:
        """Mini-grid 31 sel (v2.12.3 — redesain): tanggal kecil redup di
        baris atas + NILAI tebal di baris bawah (dulu 'hari:nilai' satu
        baris — membingungkan, '13' dikira bagian nilai). Hari kosong =
        tanggal redup saja. Sel merah = hari tersangka (HARI TERSANGKA /
        HARI MAX). Tooltip sel = 'Hari N: nilai X'."""
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(3)
        day_cols = [c for c in (str(i) for i in range(1, 32))
                    if c in rec.index]
        tersangka = None
        for src in ("HARI TERSANGKA", "HARI MAX"):
            v = rec.get(src)
            try:
                if v is not None and not pd.isna(v):
                    tersangka = int(float(v))
                    break
            except (TypeError, ValueError):
                pass
        for i, name in enumerate(day_cols):
            hari = int(name)
            v = pd.to_numeric(pd.Series([rec.get(name)]),
                              errors="coerce").iloc[0]
            has_val = v == v and v and v > 0
            if has_val:
                # tanggal kecil redup + nilai tebal (rich text — warna nilai
                # mengikuti stylesheet QLabel: merah utk tersangka, gelap
                # utk hari biasa).
                # v2.13.12 (gel-3 A12): nilai sel & tooltip MEMAKAI format
                # sama — fmt_cell default 2-desimal (dulu sel fmt_cell(v,0)
                # '7' vs tooltip fmt_cell(v,1) '7,5' — dua angka beda utk
                # data yang sama di dua tempat bersebelahan).
                text = (f'<span style="color:#94a3b8; font-size:9px;">'
                        f"{hari}</span><br><b>{fmt_cell(v)}</b>")
            else:
                text = (f'<span style="color:#cbd5e1; font-size:9px;">'
                        f"{hari}</span>")
            cell = QLabel(text)
            cell.setTextFormat(Qt.TextFormat.RichText)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setMinimumWidth(74)
            cell.setMinimumHeight(40)
            if hari == tersangka:
                cell.setStyleSheet(
                    "background:#fee2e2; color:#dc2626; font-weight:700; "
                    "border-radius:4px;")
            elif has_val:
                cell.setStyleSheet(
                    "background:#f1f5f9; color:#334155; "
                    "border-radius:4px;")
            else:
                cell.setStyleSheet(
                    "color:#cbd5e1; background:transparent;")
            tip_val = fmt_cell(v) if has_val else "kosong"
            cell.setToolTip(f"Hari {hari}: {tip_val}")
            gl.addWidget(cell, i // 8, i % 8)
        return host


class DetailDialog(QDialog):
    """Pop-up detail baris anomali (v2.8.1) — pengganti panel inline.

    Non-modal: tabel tetap bisa diklik / di-sort / di-scroll saat pop-up
    terbuka. Satu instance dipakai ulang — setiap klik baris memperbarui
    isi pop-up yang sama (bukan menumpuk jendela baru). Tutup lewat X
    kapan saja; klik baris lain membukanya kembali.

    v2.13.5: klik baris YANG SAMA (pop-up sempat ditutup X / refresh)
    membuka pop-up kembali — dulu currentRowChanged tak memicu karena
    index tak berubah. Guard idempoten: show_record dipanggil dua kali
    berturut untuk record sama (klik = currentRowChanged + clicked)
    cukup membangun SEKALI.

    v2.13.9: isi panel RINGKAS (lihat DetailPanel) — kolom lengkap
    di balik tombol "▸ Tampilkan semua kolom data".
    v2.13.10 (gel-1 V1): tombol aksi di footer sticky panel (selalu
    terlihat tanpa menggulir).
    """

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # v2.13.9: judul jujur — isi kini ringkas (bukan lagi 12 chip +
        # ±25 baris metrik sekaligus).
        self.setWindowTitle("Detail Anomali — Ringkasan Baris")
        self.setModal(False)
        self.resize(920, 640)
        self._shown_sig: tuple | None = None
        # v2.13.13 (gel-4 A3): pop-up navigasi baris TAK mencuri fokus —
        # dulu activateWindow() tiap ganti baris memindahkan fokus dari
        # tabel: 1× panah keyboard = navigasi tabel MATI (fokus lompat ke
        # pop-up; audit A3). WA_ShowWithoutActivating membuat show() tanpa
        # aktivasi; drill/⛶ (niat eksplisit user) TETAP activateWindow
        # (pemanggilan mereka di luar kelas ini tidak berubah).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self._panel = DetailPanel(ctx, self)
        lay.addWidget(self._panel)

    def _record_sig(self, rec: pd.Series) -> tuple:
        """Identitas record utk guard idempoten (fp utama, identitas
        kunci sbg cadangan — membedakan klik-baris-sama dari klik-berganti).

        v2.13.14 (gel-5 A16): jalur FALLBACK (record tanpa __FP — fixture
        sintetis / jalur test) kini memuat IDENTITAS BARIS: posisi baris
        (rec.name) + nilai hari 1-31 — dulu sig hanya 6 kolom kunci: dua
        record BEDA yang kebetulan sama di 6 kolom itu (mis. item sama,
        hari beda) dianggap SAMA → show_record ke-2 di-skip SENYAP,
        pop-up menampilkan record LAMA (audit A16: guard idempoten salah
        anggap record beda = sama). Jalur __FP tetap persis seperti lama
        (fp = md5 baris penuh — identitas sudah unik; menambah posisi
        justru memicu rebuild sia-sia saat sort menggeser baris)."""
        fp = rec.get(FP_COL)
        if fp is not None:
            return (
                str(fp),
                str(rec.get("NAMA RESTO")), str(rec.get("NAMA BARANG")),
                str(rec.get("JENIS")), str(rec.get("KETERANGAN")),
                str(rec.get("SOURCE DATA")), str(rec.get("TOTAL")),
            )
        days = tuple(
            str(rec.get(c))
            for c in (str(i) for i in range(1, 32)) if c in rec.index)
        return (
            None, rec.name if rec.name is not None else -1,
            str(rec.get("NAMA RESTO")), str(rec.get("NAMA BARANG")),
            str(rec.get("JENIS")), str(rec.get("KETERANGAN")),
            str(rec.get("SOURCE DATA")), str(rec.get("TOTAL")),
            days,
        )

    def show_record(self, rec: pd.Series) -> None:
        """Tampilkan record di panel + munculkan pop-up di depan.

        Idempoten (v2.13.5): record SAMA & pop-up masih tampak → tidak
        dibangun ulang (klik tunggal memicu currentRowChanged + clicked;
        klik ulang baris saat pop-up terbuka tak boleh mengedipkan
        rebuild ~70 widget).

        v2.13.13 (gel-4 A3): show() TANPA aktivasi jendela (WA dipasang
        di __init__) dan raise_() HANYA saat pop-up BARU muncul —
        navigasi baris (panah/klik) saat pop-up sudah terbuka cukup
        mengganti kontennya; activateWindow() dihapus dari jalur ini
        (fokus tabel tetap milik tabel — navigasi keyboard hidup).
        Jalur niat-eksplisit (drill banding / ⛶ layar penuh / pop-up
        Scorecard) tidak tersentuh — mereka tetap mengaktifkan."""
        sig = self._record_sig(rec)
        if self.isVisible() and sig == self._shown_sig:
            return
        self._shown_sig = sig
        self._panel.show_record(rec)
        was_visible = self.isVisible()
        self.show()
        if not was_visible:
            # pop-up BARU → pastikan terlihat di atas jendela lain
            # (TANPA mengambil fokus dari tabel pemanggil).
            self.raise_()


class AnomaliView(FollowupTableMixin, QWidget):
    """View 'Anomali': KPI + tabel ranking (penuh) + pop-up detail.

    v2.13.8 (gel-C): 10 metode kembar ✓-follow-up/funnel diwariskan dari
    FollowupTableMixin (konsolidasi dgn HariView — dulu salinan ±250
    baris); _DISP_LRU khusus view ini = 8."""

    _DISP_LRU = 8

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # KPI strip (nilai mengikuti filter — DD-M3)
        self._kpi = KpiStrip(self)
        lay.addWidget(self._kpi)

        # Bar kontrol: ambang skor + jumlah anomali + filter perubahan
        ctrl = QWidget(self)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(8, 0, 8, 0)
        cl.setSpacing(10)
        lbl = WLabel("Anomali dengan skor ≥", ctrl)
        cl.addWidget(lbl)
        self._spin_score = QSpinBox(ctrl)
        self._spin_score.setRange(0, 19)
        self._spin_score.setValue(0)
        self._spin_score.setToolTip(
            "Sembunyikan anomali ber-skor rendah (0 = tampilkan semua).\n"
            "Skor komposit maksimum = 19 (S1..S12).")
        self._spin_score.valueChanged.connect(self._on_score_changed)
        cl.addWidget(self._spin_score)
        # v2.10.2 — filter kuadran perubahan vs bulan lalu (permintaan user:
        # "analisa dengan perubahan yang tinggi atau rendah"). Filter LOKAL
        # view (bukan state) — kolom PERUBAHAN hanya ada setelah enrich.
        lbl_chg = WLabel("Perubahan:", ctrl)
        lbl_chg.setToolTip(
            "Saring anomali menurut perubahan totalnya vs bulan lalu:\n"
            "• Naik Tinggi = lonjakan baru (kandidat salah input / "
            "kejadian baru);\n"
            "• Stabil = waste kronis (sudah tinggi tiap bulan — masalah "
            "proses, bukan salah ketik);\n"
            "• Baru = belum ada riwayat bulan lalu.\n"
            "Butuh file pembanding di tab 'Banding Periode'.")
        cl.addWidget(lbl_chg)
        self._cb_change = QComboBox(ctrl)
        self._cb_change.addItem("Semua", None)
        for cat in CHANGE_CATEGORIES:
            icon = {"Baru": "🆕", "Naik Tinggi": "🔺", "Naik Sedang": "↗",
                    "Stabil": "➡️", "Turun": "↘", "Turun Tinggi": "🔻"}.get(
                        cat, "")
            self._cb_change.addItem(f"{icon} {cat}", cat)
        self._cb_change.setToolTip(lbl_chg.toolTip())
        self._cb_change.setEnabled(False)  # aktif begitu pembanding ada
        self._cb_change.currentIndexChanged.connect(
            lambda _i: self._on_change_filter())
        cl.addWidget(self._cb_change)
        self._lbl_count = WLabel("", ctrl)
        self._lbl_count.setObjectName("hint")
        cl.addWidget(self._lbl_count, 1)
        # v2.12.0 — aksi follow-up massal: centang SEMUA baris yang sedang
        # tampil (setelah funnel kolom menyempitkan — mis. 43 SUSUT)
        # sekaligus ke daftar Follow Up.
        self._btn_fu_all = QPushButton("☑ Centang yang tampil", ctrl)
        self._btn_fu_all.setToolTip(
            "Centang SEMUA baris anomali yang sedang tampil (hasil filter "
            "saat ini) sekaligus ke daftar Follow Up.\n"
            "Cocok dipakai setelah funnel kolom menyempitkan daftar: "
            "saring → centang massal → tinjau di tab Follow Up.")
        self._btn_fu_all.clicked.connect(self._on_check_all)
        cl.addWidget(self._btn_fu_all)
        # v2.12.4 — pengganti tombol '✕ Hapus Semua Filter' sidebar (kini
        # dihapus): lepas SEMUA filter (funnel global + lokal) sekaligus.
        self._btn_clear = QPushButton("✕ Hapus Filter", ctrl)
        self._btn_clear.setToolTip(
            "Hapus SEMUA filter yang sedang aktif — funnel kolom (global "
            "maupun tampilan) dan ambang skor — kembali ke tampilan "
            "anomali penuh.")
        self._btn_clear.clicked.connect(self._on_clear_filters)
        cl.addWidget(self._btn_clear)
        lay.addWidget(ctrl)
        self._ctrl = ctrl  # v2.12.2: toggle ⤢ (KPI + bar kontrol)

        # Kartu tabel — memenuhi SELURUH sisa tinggi view (v2.8.1: tanpa
        # splitter/panel inline; detail hadir sebagai pop-up saat baris
        # diklik).
        table_card = Card(self)
        table_card.setMinimumHeight(240)
        tcl = QVBoxLayout(table_card)
        tcl.setContentsMargins(12, 10, 12, 10)
        tcl.setSpacing(6)
        # v2.8.0: judul satu baris (dulu wrap 2-3 baris — makan ±100px);
        # v2.12.2: judul + tombol melebarkan tabel SATU baris (pola tombol
        # kartu hasil tab Banding Periode — permintaan user "tabel anomali
        # bisa diperbesar seperti di tab banding periode").
        head = QWidget(table_card)
        hcl = QHBoxLayout(head)
        hcl.setContentsMargins(0, 0, 0, 0)
        hcl.setSpacing(8)
        title = WLabel("Tabel Anomali Ter-ranking", head)
        title.setObjectName("cardTitle")
        hcl.addWidget(title)
        hcl.addStretch(1)
        self._btn_expand = QPushButton("⤢ Perbesar Tabel", head)
        self._btn_expand.setToolTip(
            "Sembunyikan KPI & bar kontrol supaya tabel memakai seluruh\n"
            "tinggi tampilan (funnel header tetap hidup — filter tetap\n"
            "aktif). Klik lagi untuk mengembalikan.")
        self._btn_expand.clicked.connect(self._on_expand)
        hcl.addWidget(self._btn_expand)
        self._btn_full = QPushButton("⛶ Layar Penuh", head)
        self._btn_full.setToolTip(
            "Buka tabel ini di jendela LAYAR PENUH (tekan Esc atau Tutup\n"
            "untuk kembali). Centang ✓ / sort / pop-up detail tetap\n"
            "berfungsi penuh di jendela itu.")
        self._btn_full.clicked.connect(self._on_fullscreen)
        hcl.addWidget(self._btn_full)
        tcl.addWidget(head)
        self._tcl = tcl  # v2.12.2: reparent ⛶ (pulihkan index layout tabel)
        self._table = DataTable(table_card)
        self._table.setMinimumHeight(200)
        # v2.12.0 — kolom centang follow-up (✓) in-place: klik sel = flip
        # bool + sinyal check_toggled → state ctx (TANPA render ulang:
        # dataChanged satu sel, cache fit DataTable tak tersentuh).
        self._table.model().set_check_column(CHECK_COL)
        self._table.model().set_row_key_column(FP_COL)
        self._table.model().check_toggled.connect(self._on_check_toggled)
        # v2.12.3: funnel filter + opsi sort di header tabel.
        # v2.12.4: SEMUA kolom ber-funnel (skip kolom ✓ + identitas __FP);
        # kolom mapping = state global ctx, lainnya = filter lokal view.
        self._table.setup_header_filters(
            _HF_COLS, self._on_header_filter, self._hf_state,
            all_cols=True, skip=(CHECK_COL, FP_COL))
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        # v2.13.5: sinyal QTableView.clicked memicu di SETIAP klik — termasuk
        # klik baris yang SAMA (currentRowChanged diam saat index tak
        # berubah). Tanpa ini: tutup pop-up (X) → klik baris sama → pop-up
        # TIDAK muncul lagi (keluhan user "klik 1× pop-up kadang tidak
        # muncul"). Guard idempoten DetailDialog membuat pemanggilan ganda
        # (currentRowChanged + clicked utk satu klik) tetap membangun sekali.
        # v2.13.5: klik-2× → filter DIHAPUS (permintaan user) — sinyal
        # double_clicked tabel ini TIDAK lagi punya subscriber.
        self._table.row_clicked.connect(lambda *_: self._on_selection())
        tcl.addWidget(self._table, 1)
        lay.addWidget(table_card, 1)

        # v2.12.2 — jendela layar penuh tabel (dibuat malas, dipakai ulang):
        # WIDGET TABEL ASLI di-reparent sementara → interaksi ✓/sort/
        # pop-up detail tetap 100% hidup (bukan salinan). Esc/Tutup →
        # dikembalikan ke kartu pada POSISI LAYOUT ASLI (index dicatat).
        self._fs_dlg: QDialog | None = None
        self._fs_idx: int = 1  # v2.12.4: head(0) + tabel(1) — slicer/hint dihapus
        # Pop-up detail (v2.8.1) — satu instance dipakai ulang.
        self._popup = DetailDialog(ctx, self)

        # Reaksi state — pola lazy H2: view tak terlihat → tandai dirty,
        # render saat dibuka (on_shown). View default biasanya terlihat saat
        # pipeline selesai → render langsung.
        self._dirty = True
        # v2.13.14 (gel-5 A7): set_dataset memancarkan data_ready LALU
        # filters_changed BERPASANGAN (state.py) — render penuh di
        # _on_data_ready sudah memakai state filter yang di-reset;
        # filters_changed yang menyusul = render penuh KEDUA yang identik
        # (dulu full-render ×2 tiap run saat view terlihat — audit A7:
        # docstring state.py menjanjikan 'partial refresh', kenyataannya
        # _refresh_table penuh dua kali). Flag konsumsi-sekali: skip
        # TEPAT pasangan emit itu; set_filter/drill user (filters_changed
        # yang TIDAK didahului data_ready) tetap render normal.
        self._skip_filters_once = False
        # v2.10.2: versi cache enrich (df + baseline + data/history) —
        # kombinasi sama → salinan berkolom sama dipakai ulang.
        # v2.12.1: satu slot → LRU weakref (bolak-balik antar state filter
        # dulu selalu miss → change_vs_history dihitung ulang tiap toggle).
        self._change_cache: OrderedDict[tuple, tuple] = OrderedDict()
        # v2.12.0: memo display (df + ✓/__FP) & memo fingerprint — objek
        # STABIL per objek df supaya cache fit DataTable tetap kena;
        # nilai ✓ disegarkan tiap pemakaian (state bisa berubah).
        # v2.12.1: SATU SLOT → LRU-8 per objek df (weakref — pola cache fit
        # DataTable). Diukur profil data asli: toggle slicer bolak-balik
        # antar 2 state filter → memo satu slot SELALU miss → fingerprint
        # md5 + salinan df + objek display BARU → kunci cache fit (id objek)
        # tak pernah cocok lagi → jalur 'balik baseline' yang dulu ~30 ms
        # (v2.9.0) membesar ~350 ms. LRU mengembalikan objek display PERSIS
        # sama per state → cache fit kena seperti sebelum v2.12.0.
        self._disp_cache: OrderedDict[int, tuple] = OrderedDict()
        self._fps_src: pd.DataFrame | None = None
        self._fps: pd.Series | None = None
        # v2.12.4: funnel LOKAL kolom non-ctx (SEMUA kolom ber-funnel;
        # kolom mapping tetap global). {kolom: nilai terpilih} — hanya
        # menyaring TAMPILAN tabel ini (KPI + Follow Up tak tersentuh).
        self._hfilters: dict[str, list] = {}
        # v2.12.4: memo hasil mask per (objek display, state filter) —
        # objek mask stabil per state → cache fit DataTable tetap kena
        # (pola _disp_cache LRU; A→B→A memakai ulang objek A).
        # v2.13.13 (gel-4 A5): entri = (weakref, hasil) dgn validasi
        # identitas (lihat followup_table._mask_local — anti tabrakan id
        # pasca-GC, audit A5).
        self._mask_cache: OrderedDict[tuple, tuple] = OrderedDict()
        ctx.data_ready.connect(self._on_data_ready)
        ctx.filters_changed.connect(self._on_filters_changed)
        # v2.10.2: pembanding siap / pilihan combo berganti → kolom
        # BULAN LALU-PERUBAHAN muncul / dihitung ulang.
        ctx.history_ready.connect(self._on_history_ready)
        ctx.baseline_changed.connect(self._on_baseline_changed)
        # v2.12.0: daftar follow-up berubah (toggle di mana pun / bulk /
        # prune) → segarkan kolom ✓ in-place (bukan render ulang).
        ctx.followup_changed.connect(self._on_followup_changed)

    def _on_data_ready(self) -> None:
        # v2.12.1: memo display/fingerprint/enrich berasal dataset LAMA —
        # kosongkan (weakref objek tua mati sendiri, tapi salinan display
        # yang dipegang kuat dilepas instan supaya memori tak menumpuk).
        self._disp_cache.clear()
        self._fps_src, self._fps = None, None
        self._change_cache.clear()
        # v2.12.4: dataset baru → nilai funnel lokal bisa jadi tak ada lagi
        # di data baru — reset (state global sudah direset set_dataset).
        self._hfilters.clear()
        self._mask_cache.clear()
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

    def _on_history_ready(self) -> None:
        """Pembanding selesai dimuat → kolom perubahan bisa dihitung."""
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_baseline_changed(self) -> None:
        """Combo 'Banding dengan:' berganti → hitung ulang vs bulan itu."""
        if self.isVisible():
            self._refresh_table()
        else:
            self._dirty = True

    def _on_change_filter(self) -> None:
        """Combo kategori perubahan → saring tabel (lokal, tanpa state).

        Tanpa guard isVisible: combo hanya bisa diklik saat view terlihat,
        dan pemanggilan programatik (test / refresh eksternal) tetap bekerja.
        (Pola _on_score_changed — aksi kontrol = refresh langsung.)"""
        self._refresh_table()

    def _reset_view_controls(self) -> None:
        """v2.13.10 (gel-1 A1+A2) — override hook mixin: reset combo
        'Kategori PERUBAHAN' ke 'Semua' (index 0).

        Combo itu filter LOKAL view yang di-apply ulang di
        _refresh_table_impl lewat currentData() — tanpa reset ini:
        (A1) tombol '✕ Hapus Filter' menjanjikan 'SEMUA' tapi kategori
        tetap aktif; (A2) dataset baru mewarisi kategori run lama.
        blockSignals: index berganti memicu currentIndexChanged →
        _on_change_filter → render — pemanggil (_on_clear_filters /
        refresh) sudah me-render SETELAH ini; tanpa blok = render ganda
        (pola _cb_mode HariView.refresh)."""
        self._cb_change.blockSignals(True)
        self._cb_change.setCurrentIndex(0)
        self._cb_change.blockSignals(False)

    def on_shown(self) -> None:
        """Kontrak lazy-render: view dibuka setelah data baru / filter basi."""
        if self._dirty:
            self.refresh()

    # ------------------------------------------------------------
    def refresh(self) -> None:
        """Dataset baru: KPI + tabel (filter sudah direset oleh state)."""
        self._dirty = False
        self._spin_score.blockSignals(True)
        self._spin_score.setValue(0)
        self._ctx.score_min = 0
        self._spin_score.blockSignals(False)
        # v2.13.10 (gel-1 A2): combo 'Kategori PERUBAHAN' ikut direset —
        # kategori dataset lama bisa tak ada lagi di data baru (tabel
        # diam-diah hanya menampilkan subset). Pola _cb_mode HariView
        # — dulu asimetri antar view kembar (HariView reset, ini tidak).
        self._reset_view_controls()
        self._refresh_kpi()
        self._refresh_table()

    def _on_score_changed(self, value: int) -> None:
        self._ctx.set_score_min(value)

    def _refresh_table(self) -> None:
        """v2.8.3 — titik tunggal SEMUA jalur render tabel (filter/search/
        rentang hari/Hapus Filter/drill-down/dataset baru) dibungkus
        busy_feedback: cursor sibuk + pesan status "⏳ …" dipasang SEBELUM
        kerja berat sinkron (auto-fit kolom + ukur tinggi baris per sel;
        diukur data asli: 75–460 ms sandbox = 1–2+ dtk di laptop user) —
        proses terlihat 'masih jalan', bukan beku senyap. Selesai → durasi
        dilaporkan ke status bar.
        v2.13.13 (gel-4 D6): first-run TANPA dataset TIDAK dibungkus —
        busy_feedback akan mengklaim "✓ Menyaring & menampilkan data
        selesai (0 ms)" padahal tak ada data yang disaring (residual D6
        gel-2 — user membaca pekerjaan filter sebagai hasil akhir).
        Render BERDATA tetap dibungkus utuh (kerja nyata)."""
        if self._ctx.df is None:
            self._refresh_table_impl()
            return
        with busy_feedback(self._ctx.set_status, "Menyaring & menampilkan data"):
            self._refresh_table_impl()

    def _refresh_table_impl(self) -> None:
        # v2.7.0 (V26-L12): dataset/filter berubah → seleksi + detail lama
        # bisa basi (record terpilih mungkin sudah tak lolos filter) —
        # kosongkan keduanya (model reset mengosongkan seleksi).
        # v2.8.1: panel detail kini di pop-up → tutup + kosongkan.
        self._table.clearSelection()
        self._popup.hide()
        self._popup._panel.clear()
        # Sinkron spin ambang skor (reset eksternal, mis. tombol Hapus Filter)
        if self._spin_score.value() != self._ctx.score_min:
            self._spin_score.blockSignals(True)
            self._spin_score.setValue(self._ctx.score_min)
            self._spin_score.blockSignals(False)
        df = self._ctx.anomali_df()
        if df is None:
            self._table.set_dataframe(None)
            self._lbl_count.setText("Belum ada data — buka tab Pipeline, pilih workbook, jalankan.")
            return
        # v2.10.2 — kolom perubahan vs bulan lalu (permintaan user: "persen
        # perubahan ke anomali sebagai analisa perubahan tinggi/rendah").
        # Enrich di SALINAN (kontrak 'konsumen hanya membaca' — mem-memo per
        # (df, baseline, versi) supaya refresh dgn state sama mengembalikan
        # objek sama → cache fit DataTable tetap kena).
        baseline = self._ctx.banding_baseline_effective()
        if baseline is not None and not df.empty:
            key = (id(df), self._ctx.data_version, self._ctx.history_version,
                   id(baseline))
            cached = self._change_cache.get(key)
            if cached is not None and cached[0]() is df:
                self._change_cache.move_to_end(key)
                df = cached[1]
            else:
                src = df  # weakref menunjuk SUMBER (df ter-reassign di bawah)
                with busy_feedback(
                        self._ctx.set_status,
                        "Menghitung perubahan vs bulan lalu"):
                    df = change_vs_history(df, baseline, self._ctx.config)
                    # v2.13.0: PROFIL "+ Baru" (pasangan tidak ada/nol di
                    # bulan pembanding) — dibaca dari kolom BULAN LALU yang
                    # baru dihitung; idempoten, vektor, murah.
                    df = annotate_profile_vs_history(df)
                self._change_cache[key] = (weakref.ref(src), df)
                while len(self._change_cache) > 4:
                    self._change_cache.popitem(last=False)
        # Filter kategori perubahan (LOKAL view — bukan state): hanya
        # menyaring tampilan, KPI/label lain tidak terpengaruh.
        cat = self._cb_change.currentData() if self._cb_change.isEnabled() \
            else None
        self._cb_change.setEnabled(baseline is not None)
        if cat and "PERUBAHAN" in df.columns:
            df = df[df["PERUBAHAN"] == cat]
        # v2.13.14 (gel-5 C15): judul kolom BULAN LALU + tooltip menyebut
        # SUMBER pembandingnya (bulan pilihan combo Banding Periode /
        # Tipikal) — dulu label polos di SEMUA tab padahal "bulan lalu"
        # beda sumber antar tab (Anomali = combo; Hari = bulan terbaru
        # termuat) — dua angka tak terbandingkan tanpa konteks (audit
        # C15). Alias headerData saja (pola 'Pembanding' → nama bulan di
        # view_periode): data/sort/record tetap nama kanonik.
        lbl_b = baseline_label(baseline)
        if lbl_b:
            self._table.model().set_header_map(
                {"BULAN LALU": f"BULAN LALU ({lbl_b})"})
            self._table.model().set_tooltip_map({
                "BULAN LALU": COLUMN_TOOLTIPS.get("BULAN LALU", "")
                + f"\nSumber saat ini: {lbl_b} (mengikuti combo tab "
                "'Banding Periode')"})
        else:
            self._table.model().set_header_map(None)
            self._table.model().set_tooltip_map(None)
        cols = [c for c in TABLE_COLS if c in df.columns]
        # v2.7.0 (V26-C1): model memegang df PENUH (bukan irisan TABLE_COLS
        # lagi) — kolom non-tabel disembunyikan via visible_cols. Record
        # terpilih / double-klik tetap membawa SEMUA kolom (12 sinyal,
        # ANOMALY REASONS, peer, MAX, ...) ke pop-up detail + drill-down.
        # v2.8.1: 8 kolom + sidebar membuat lantai header melebihi viewport
        # laptop (1024) — JENIS & KETERANGAN masuk narrow_hide (disembunyikan
        # responsif saat sempit, muncul lagi saat melebar; alasan tetap ada
        # di pop-up detail) supaya kolom inti + % to BOM tetap muat TANPA
        # scrollbar horizontal.
        # v2.10.2: kolom perubahan ikut narrow_hide — 11 kolom di laptop
        # sempit; kolom PERUBAHAN % tetap prioritas tampak.
        # v2.12.0: df tampilan = SALINAN + ✓ + __FP (kontrak 'konsumen
        # hanya membaca' utk objek LRU/enriched tetap utuh; objek display
        # di-memo per objek df → cache fit DataTable tetap kena).
        disp = self._display_df(df)
        # v2.12.4: funnel LOKAL kolom non-ctx — mask isin di atas display
        # (memo per state; ✓ disegarkan tiap pemakaian). 'Perubahan:' combo
        # sudah di-apply di atas (df), funnel lokal di bawah (disp).
        shown = self._mask_local(disp)
        self._table.set_dataframe(shown, sort_desc="ANOMALY SCORE",
                                  narrow_hide=["JENIS", "KETERANGAN",
                                               "BULAN LALU", "PERUBAHAN"],
                                  visible_cols=[CHECK_COL] + cols)
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if len(shown) == 0:
            self._lbl_count.setText("0 anomali lolos filter — longgarkan filter atau ambang skor.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(len(shown))} anomali tampil (dari {fmt_id(full)} baris data)")
        self._refresh_kpi()

    def _refresh_kpi(self) -> None:
        filtered = self._ctx.filtered_df()
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if filtered is not None:
            self._kpi.update_from(filtered, full)

    # ------------------------------------------------------------
    # v2.13.8 (gel-C): 10 metode ✓-follow-up + funnel (dulu §v2.12.0
    # s/d _on_selection) DIWARISKAN dari FollowupTableMixin —
    # konsolidasi kembar AnomaliView ⇄ HariView (±250 baris → 1 sumber).
    # ------------------------------------------------------------


    # ------------------------------------------------------------
    # v2.12.2 — MELEBARKAN TABEL (pola tab Banding Periode)
    # ------------------------------------------------------------
    def _on_expand(self) -> None:
        """Ciutkan/kembalikan KPI + bar kontrol (tabel makan tinggi penuh).

        isHidden() (bukan isVisible()) — toggle benar walau view induk
        sedang tak tampak (di-balik tab lain) — pola _on_expand PeriodeView.
        Funnel header tetap hidup: filter tetap aktif saat diperbesar."""
        collapsed = self._kpi.isHidden()
        show = collapsed
        self._kpi.setVisible(show)
        self._ctrl.setVisible(show)
        self._btn_expand.setText(
            "⤢ Perbesar Tabel" if show else "⤡ Tampilkan KPI & Filter")
        self._ctx.set_status(
            "⤡ KPI disembunyikan — tabel diperbesar" if not show
            else "⤢ KPI & filter ditampilkan kembali", "done")

    def _on_fullscreen(self) -> None:
        """Pop-out TABEL ASLI ke jendela maximized (Esc = kembali).

        Reparent widget tabel (bukan salinan render) → centang ✓, sort,
        seleksi→pop-up detail — semua tetap hidup dan IKUT TERBARUI saat
        filter berganti (model sama, sinyal sama). Posisi layout asli
        dicatat utk dipulihkan utuh saat ditutup.
        v2.13.12 (gel-3 A9): tabel 0 baris kini DIBEDAKAN — 0-baris-
        KARENA-FILTER (dataset ADA tapi funnel/skor menyaring semua)
        → pesan menyebut filter + cara melepasnya; tanpa dataset →
        arahan ke Pipeline tetap (kontrol positif; dulu kedua-duanya
        satu pesan 'belum ada data' — menyesatkan saat datanya ADA)."""
        if self._table.model().rowCount() == 0:
            df = self._ctx.df
            if df is not None and not df.empty:
                self._ctx.set_status(
                    "Tabel 0 baris — filter/ambang skor sedang menyaring "
                    "semua baris; lepas filter dulu (tombol ✕ Hapus Filter "
                    "/ naikkan ambang skor), lalu perbesar tabel.", "done")
            else:
                self._ctx.set_status(
                    "Belum ada data utk dibesarkan — jalankan pipeline dulu "
                    "(tab Pipeline)", "done")
            return
        if self._fs_dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(
                "Tabel Anomali — Layar Penuh (Esc = kembali)")
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
            # rejected = Esc (default QDialog) DAN tombol Tutup X (close-
            # Event default QDialog → reject) — satu jalur pemulihan.
            dlg.rejected.connect(self._restore_table_from_fs)
            self._fs_dlg = dlg
        idx = self._tcl.indexOf(self._table)
        self._fs_idx = idx if idx >= 0 else 1
        self._tcl.removeWidget(self._table)
        # insert DI BAWAH baris tombol (hint dihapus v2.12.4)
        self._fs_dlg.layout().insertWidget(0, self._table, 1)
        self._fs_dlg.showMaximized()
        self._fs_dlg.raise_()
        self._fs_dlg.activateWindow()
        self._ctx.set_status("⛶ Tabel anomali dibuka layar penuh — Esc "
                             "utk kembali", "done")

    def _restore_table_from_fs(self) -> None:
        """Kembalikan tabel ke kartu pada index layout asli (idempoten —
        guard parent supaya pemanggilan ganda tak mengacak urutan)."""
        if (self._fs_dlg is None
                or self._table.parent() is not self._fs_dlg):
            return
        self._fs_dlg.layout().removeWidget(self._table)
        self._tcl.insertWidget(self._fs_idx, self._table, 1)
        self._ctx.set_status("⤡ Tabel kembali ke tab Anomali", "done")

    # v2.13.5: _on_double (klik-2× → filter cabang+item) DIHAPUS atas
    # permintaan user — perilaku itu membuat pop-up detail "kadang tidak
    # muncul" (klik-2× → set_filter → render → _popup.hide() di awal
    # _refresh_table_impl; klik#1-nya malah menjadikan klik tunggal yang
    # seolah tidak membuka apa-apa). Jalur fokus drill kini HANYA tombol
    # eksplisit di pop-up detail ("🏬 Fokus cabang ini" dst. — niat user
    # jelas, tak pernah terpicu tak sengaja). Guard _batch_filters ikut
    # hilang bersama satu-satunya pemakainya.
