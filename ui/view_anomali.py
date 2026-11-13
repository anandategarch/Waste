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

v2.18.7 (3 permintaan user):
- "kasih kolom tambahan itu jenis nya waste, susut atau trial" —
  kolom JENIS kini SELALU tampil (keluar dari narrow_hide; pola tab
  Hari Mencurigakan v2.12.3). "kolom anomali score hapus aja" —
  ANOMALY SCORE keluar dari TABLE_COLS (skor tetap menjadi dasar
  RANKING tabel + filter "Skor ≥" + tampil di pop-up detail).
- "aku bisa pilih tampilkan yang sudah masuk follow up atau tampilkan
  semua" — combo "Tampilkan:" (Semua / ✓ Sudah masuk Follow Up):
  filter LOKAL view (pola combo Kategori PERUBAHAN — KPI & tab lain
  tak tersentuh). Saat aktif, lepas centang ✓ = baris langsung
  hilang dari tabel (hook mixin _followup_filter_active →
  _on_followup_changed me-render ulang, bukan segarkan ✓ in-place).

v2.20.0 (3 permintaan user):
- "kolom % to bom bisa gak diberi warna semacam heat map ... absolute
  dulu ... tampilkan nilai asli" — heatmap background '% to BOM' dari
  |nilai| (skala p99 kolom, ramp hijau→kuning→oranye→merah; teks tetap
  nilai asli bertanda — model.set_heat_column).
- "tambahkan cuman analisa rangking waste ya" (kode Power Query user
  'TambahRangkingFast') — kolom baru RANGKING WASTE paling kanan tabel
  (kanan PROFIL; PROFIL dirapatkan _WIDTH_CAPS): label grup Top 3 Total
  & Top 3 % BOM per item lintas cabang (ui/grouping.py 6b + sumber label
  tunggal waste_anomaly.signals.ranking_waste_label).
- "tambah fitur juga aku bisa hide dan unhide kolom di tab anomali" —
  tombol '⇔ Kolom': menu centangan per kolom + 'Tampilkan semua kolom'
  (jalur visible_cols — persisten lintas auto-fit; data tetap di model).
"""
from __future__ import annotations

import weakref
from collections import OrderedDict
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
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
from waste_anomaly.rekap_import import SRC_ROW_COL
from waste_anomaly.signals import SIGNAL_PARTS
# v2.16.2: SourceWriteError & write_day_edits tidak lagi di-import di sini
# (SaveEditsWorker import sendiri secara lazy di run(); UI tak panggil langsung).
from .workers import SaveEditsWorker

from .followup_table import (
    FPS_LIST_COL,
    FollowupTableMixin,
    HF_COLS as _HF_COLS,
)
from .grouping import (
    FPS_COL as _GRP_FPS_COL,
    GROUP_KEYS,
    LASTMONTH_COMBINED_COL,
    SEP_COL,
    SEP_KEYS,
    SELISIH_COL,
    SRC_GAB_COL,
    SRC_ROWS_COL as _GRP_SRC_ROWS_COL,
    group_anomali_display,
    insert_group_separators,
)
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
from .shared import _apply_filters, baseline_label, fmt_id
from .state import AppContext
from .widgets import (
    Card,
    DataTable,
    KpiStrip,
    SortControl,
    StatusChip,
    WLabel,
    busy_feedback,
    status_chip_for,
)

# Kolom tabel anomali — LAYOUT SAMPEL USER v2.19.0 ("SAMPEL TAMPILAN
# BARU.xlsx"): SATU BARIS per (JENIS × NAMA BARANG × NAMA RESTO) — semua
# alasan/KETERANGAN & SOURCE DATA digabung (kolom SOURCE DATA GABUNGAN),
# urutan 11 kolom persis sampel:
#   KETERANGAN · NAMA BARANG · NAMA RESTO · SOURCE DATA GABUNGAN · [TOTAL] ·
#   [% to BOM] · TOTAL BULAN LALU & % Selisih · Selisih Bulan Lalu ·
#   PERUBAHAN · ANOMALY STATUS · PROFIL
# v2.20.1 (permintaan user: "kolom jenis diganti jadi kolom KETERANGAN
# AJA") — kolom pertama BUKAN lagi JENIS (WASTE/SUSUT/TRIAL) melainkan
# KETERANGAN (alasan pencatatan: Alat/Mesin, Cancel Nota, Handling,
# Kualitas, Kualitas Eksternal, Kualitas Internal, Over Stock, SUSUT,
# TRIAL). SUSUT/TRIAL muncul di KETERANGAN via fallback (grouping.py:
# KETERANGAN kosong → JENIS) sebab catatan SUSUT/TRIAL tak punya
# sub-alasan — jenisnya itulah keterangannya. JENIS tetap di df model
# (kunci grup + sort + funnel global 'jenis' di tab Hari) — hanya
# disembunyikan dari tabel Anomali (visible_cols = TABLE_COLS).
# [TOTAL]/[% to BOM] = ALIAS judul (nama kanonik df tetap TOTAL/% to BOM
# — kontrak test_v280 index+1 utuh). 'TOTAL BULAN LALU & % Selisih' =
# kolom NUMERIK berisi total bulan lalu; teks sel "1.969,1 (-30%)"
# digabung formatter model (fmt_lastmonth_combined) dari companion
# PERUBAHAN % — sort numerik tetap benar. Kolom banding muncul hanya bila
# pembanding bulan lalu tersedia (pola v2.10.2 — kolom ditambahkan
# ADDITIF oleh change_vs_history + agregasi grup).
# v2.6.1→v2.18.7 riwayat: 10→7 kolom, +"% to BOM", skor dihapus dari
# tabel (tetap dasar ranking/sort/filter), JENIS selalu tampil.
TABLE_COLS = [
    "KETERANGAN", "NAMA BARANG", "NAMA RESTO", SRC_GAB_COL,
    "TOTAL", "% to BOM",
    LASTMONTH_COMBINED_COL, SELISIH_COL, "PERUBAHAN",
    "ANOMALY STATUS", "PROFIL",
    # v2.20.0 — RANGKING WASTE paling kanan (permintaan user: kolom baru
    # "disebelah kanan sendiri aja atau kanan nya profil"; PROFIL dirapatkan
    # via _WIDTH_CAPS supaya muat). Nilai = label grup dari kode Power
    # Query user 'TambahRangkingFast' (Top 3 Total & Top 3 % BOM per item
    # lintas cabang — ui/grouping.py section 6b).
    "RANGKING WASTE",
]
# v2.20.0 — batas lebar kolom tampilan (PROFIL dirapatkan — permintaan
# user "kolom profil rapatkan aja"): nilai PROFIL pendek ('Tiap Hari',
# 'Kadang', 'Sekali Ini', '— Baru') tak butuh kolom lebar; ruangnya
# diserahkan ke RANGKING WASTE di kanannya.
_WIDTH_CAPS = {"PROFIL": 150}
# Alias judul tampilan sampel user ([TOTAL] / [% to BOM]) — dipasang di
# _refresh_table_impl via model.set_header_map (data/sort/record tetap
# nama kanonik; alias WAJIB ikut visible_cols supaya kolom tak tersembunyi
# — set_dataframe mencocokkan nama JUDUL, lihat view_followup v2.12.3).
_TABLE_ALIASES = {"TOTAL": "[TOTAL]", "% to BOM": "[% to BOM]"}
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


class _NoWheelFilter(QObject):
    """v2.16.1 — blok event wheel di QDoubleSpinBox (permintaan user:
    "jangan pakai scroll dong buat ubah kuantiti nya khawatiri tidak
    sengaja scroll pakai ketik manual aja atau klik atas bawah").

    Event wheel DICONSUME (return True) → spinbox tak berubah saat scroll.
    User tetap bisa: ketik angka manual, klik panah atas/bawah spinbox.
    Filter dipasang per-spinbox via installEventFilter.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True  # consume — abaikan scroll
        return False


# v2.17.3 — deteksi workbook = file sementara folder-flow (rekap_folder_*).
# Edit nilai HANYA utk file asli (mode "Pilih REKAP MENTAH" / format TEGAR).
# File folder-flow = temp gabungan — edit akan tulis ke temp (bukan asli),
# jadi tombol Simpan di-DISABLE + pesan jujur arahkan ke mode Pilih File.
_FOLDER_TEMP_PREFIX = "rekap_folder_"


def _workbook_is_folder_temp(src_path: str | None) -> bool:
    """True bila workbook_path = file sementara folder-flow (rekap_folder_*).

    load_rekap_folder menulis temp dgn tempfile.mkstemp(prefix=
    "rekap_folder_") → nama file selalu diawali "rekap_folder_". Deteksi
    nama file = cara andal (tanpa thread flag lewat ctx/summary).
    """
    if not src_path:
        return False
    return Path(src_path).name.startswith(_FOLDER_TEMP_PREFIX)


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
    v2.16.0: peta hari kini EDITABLE (QDoubleSpinBox). Signal day_edited
    dipancarkan setelah koreksi tersimpan ke file Excel — view pemilik
    (AnomaliView) mendengarkan & me-refresh model tabel utk baris ini.
    """

    # v2.16.0: (src_row, day_edits, total_new) — dipancar SETELAH tulis
    # Excel sukses + ctx.df diupdate. View pemilik update model df +
    # emit dataChanged utk re-render sel baris ini.
    day_edited = Signal(int, dict, object)

    # Prompt default — dipakai __init__ DAN clear() (V26-L12)
    # v2.13.9: teks mengikuti desain ringkas (ringkasan + sinyal terpicu
    # + peta hari; kolom lengkap di balik tombol).
    # v2.13.12 (gel-3 A13): frasa era panel-inline "menampilkan detailnya
    # di sini" dibuang (panel poped-out sejak v2.8.1 — "di sini" menipu:
    # detailnya bukan di panel ini melainkan di pop-up) → deskripsi jujur
    # isi pop-up + footer aksi yang selalu terlihat (gel-1 V1).
    _PROMPT = ("Klik-ganda baris di tabel (atau tekan Enter) untuk membuka "
               "pop-up detail: ringkasan angka kunci, sinyal terpicu, peta "
               "nilai per hari, dan tombol tindak lanjut (drill fokus + "
               "masuk Follow Up) di footer yang selalu terlihat.")

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        # v2.13.5: tombol follow-up di pop-up (sinkron dgn state ctx —
        # toggle dari mana pun memperbarui teksnya tanpa rebuild).
        self._fu_btn: QPushButton | None = None
        self._cur_fp: str | None = None
        self._cur_fps: list[str] | None = None  # v2.19.0: plural (grup)
        # v2.13.9: wadah + tombol kolom-lengkap (diisi show_record).
        self._full_box: QWidget | None = None
        self._more_btn: QPushButton | None = None
        # v2.13.12 (gel-3 A11): jumlah kolom lengkap DISIMPAN supaya teks
        # tombol mempertahankan '(N)' sepanjang siklus buka/tutup (dulu
        # angka hilang setelah siklus pertama — toggle kedua menulis teks
        # tanpa angka, user tak tahu lagi berapa kolom yang disembunyikan).
        self._n_full: int = 0
        # v2.16.0 — fitur "edit dari pop-up": spinbox editable hari 1-31.
        # self._day_edits = {nama_hari_str: QDoubleSpinBox}; self._day_orig
        # = nilai asli record (utk bandingin "apa berubah?" saat simpan).
        # self._cur_src_row = __SRC_ROW record saat ini (None = tak ada →
        # tombol Simpan di-disable dengan pesan jujur).
        self._day_edits: dict[str, QDoubleSpinBox] = {}
        self._day_orig: dict[str, float] = {}
        self._cur_src_row: int | None = None
        # v2.19.2 — daftar semua baris Excel anggota grup (utk tulis-balik
        # multi-anggota). [] = tak ada mapping; [n] = grup 1-anggota / baris
        # tunggal; [n, m, ...] = grup multi-anggota (tulis ke SEMUA).
        self._cur_src_rows: list[int] = []
        self._save_btn: QPushButton | None = None
        # v2.16.1 — no-wheel filter (blok scroll di spinbox) + save worker
        # (background thread supaya UI tak "Not Responding" saat tulis Excel).
        self._no_wheel = _NoWheelFilter(self)
        self._save_worker: SaveEditsWorker | None = None
        self._pending_edits: dict[str, float] | None = None  # utk done handler
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
        self._cur_fps = None
        self._full_box = None
        self._more_btn = None
        # v2.16.0: reset state editable hari (spinbox widget dihapus bersama
        # konten lama di bawah; ref dict dikosongkan supaya handler Simpan
        # tidak menyentuh spinbox mayat).
        self._day_edits = {}
        self._day_orig = {}
        self._cur_src_row = None
        self._cur_src_rows = []
        self._save_btn = None
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
        self._cur_fps = None
        self._full_box = None   # v2.13.9: ref wadah kolom lengkap
        self._more_btn = None   # v2.13.9: ref tombol pembuka kolom lengkap
        # v2.16.0: reset state editable hari (spinbox lama dibuang bersama
        # konten; dict dikosongkan — handler Simpan tak sentuh mayat).
        self._day_edits = {}
        self._day_orig = {}
        self._cur_src_row = None
        self._cur_src_rows = []
        self._save_btn = None
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

        # v2.17.0 rombak P0: urutan SINYAL-DULU — "Sinyal terpicu" (chip
        # merah, inti investigasi) ditampilkan SEBELUM "Ringkasan" (angka
        # konteks). Sebelumnya Ringkasan duluan → user baca 7 angka konteks
        # sebelum tahu SINYAL APA yang menyala. Popup anomali = jawaban
        # "kenapa baris ini muncul" → sinyal wajib terbaca pertama.

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
            except Exception as exc:  # v2.16.0: log, bukan diam jadi 0.0
                # Sebelumnya: nilai non-numerik DIAM-DIAM jadi 0.0 → sinyal
                # nampak "tidak terpicu" padahal data aneh (menyesatkan).
                # Kini: nilai tetap 0.0 utk display (jangan crash pop-up),
                # TAPI di-log supaya investigasi bisa telusuri.
                import logging
                logging.getLogger("waste_anomaly.ui").warning(
                    "Nilai sinyal %r non-numerik (%r) → dianggap 0 utk "
                    "display. %s", col, val, exc)
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
        # v2.16.0: peta hari kini EDITABLE — QDoubleSpinBox per hari (bukan
        # QLabel read-only). User ubah nilai → klik "Simpan koreksi" di
        # footer → tulis balik ke file Excel sumber (source_writer).
        # v2.19.2 — PULIHKAN jalur edit v2.16.0 yg ter-regresi v2.19.0:
        # grouping selalu membentuk __FPS tuple (bahkan 1 anggota) sehingga
        # `is_group` selalu True → edit DISABLED total di tab Anomali.
        # Sekarang dipakai __SRC_ROWS (tuple nomor baris Excel anggota):
        #   • 1 anggota  → editable (jalur v2.16.0 pulih)
        #   • >1 anggota → editable; koreksi ditulis ke SEMUA anggota grup
        #     (konfirmasi daftar baris diberikan sebelum tulis). Nilai yg
        #     tampil = JUMLAH anggota; ubah salah satu hari = tulis nilai
        #     BARU yg sama ke tiap anggota (bukan distribusi — pilihan
        #     sengaja: user mengoreksi satu nilai spesifik, semua alasan
        #     grup menerima koreksi itu).
        src_rows: list[int] = []
        sr_val = rec.get(_GRP_SRC_ROWS_COL)
        if isinstance(sr_val, tuple):
            for v in sr_val:
                try:
                    src_rows.append(int(v))
                except (TypeError, ValueError):
                    pass
        # Fallback bila __SRC_ROWS tak ada (dataset pra-v2.19.2 / fixture):
        # pakai __SRC_ROW tunggal dari record (jalur lama).
        if not src_rows:
            src_row_val = rec.get(SRC_ROW_COL)
            if src_row_val is not None and not (
                    isinstance(src_row_val, float) and src_row_val != src_row_val):
                try:
                    src_rows = [int(src_row_val)]
                except (TypeError, ValueError):
                    src_rows = []
        self._cur_src_rows = src_rows
        self._cur_src_row = src_rows[0] if len(src_rows) == 1 else None
        # v2.19.5 — simpan record aktif utk label staging (jenis/barang/resto)
        # di _on_stage_edits (tab Update nilai).
        self._cur_rec = rec
        is_multi = len(src_rows) > 1
        if is_multi:
            lay.addWidget(self._section(
                f"Nilai per hari ({day_rng}) — GABUNGAN {len(src_rows)} baris "
                f"alasan grup ini (jumlah per hari). EDITABLE: ubah angka → "
                f"“Simpan koreksi” menulis nilai ke SEMUA {len(src_rows)} "
                f"baris Excel anggota; sel merah = hari tersangka"))
            lay.addWidget(self._editable_day_map(rec, day_names))
        else:
            lay.addWidget(self._section(
                f"Nilai per hari ({day_rng}) — EDITABLE: ubah angka lalu klik "
                "“Simpan koreksi” di bawah (tulis ke file Excel sumber); "
                "sel merah = hari tersangka"))
            lay.addWidget(self._editable_day_map(rec, day_names))

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
        # v2.19.0 — sidik jari PLURAL: record grup membawa __FPS (semua
        # anggota); tombol follow-up grup = masukkan/keluarkan SEMUA
        # anggota sekaligus. Record baris tunggal: satu fp (v2.12.0).
        # v2.19.2 — is_group = >1 anggota (bukan sekadar punya __FPS tuple,
        # yg selalu True pasca-grouping). Follow-up plural hanya bila grup
        # benar-benar multi-anggota.
        fps = self._row_fingerprints(rec)
        if fps:
            self._cur_fps = fps
            in_list = any(f in self._ctx.followup_set() for f in fps)
            is_group = len(fps) > 1
            self._fu_btn = QPushButton(self._fu_btn_text(in_list, is_group))
            self._fu_btn.setToolTip(
                ("Tambahkan / keluarkan SEMUA baris gabungan ini (grup "
                 "item×cabang) dari daftar Follow Up — tab Follow Up "
                 "menampilkan tiap barisnya.\nSama seperti mencentang "
                 "kolom ✓ di tabel."
                 if is_group else
                 "Tambahkan / keluarkan baris ini dari daftar Follow Up\n"
                 "(tab Follow Up — format rekap siap serah terima petugas).\n"
                 "Sama seperti mencentang kolom ✓ di tabel."))
            self._fu_btn.clicked.connect(self._on_fu_toggle)
            alay.addWidget(self._fu_btn)

        # v2.16.0 — tombol SIMPAN KOREKSI hari 1-31 ke file Excel sumber.
        # Hanya aktif bila record punya __SRC_ROW (dipasang pipeline v2.16
        # via ensure_rekap_header). Tanpa itu, tulis-balik tidak tahu baris
        # Excel mana yang dituju → tombol di-disabled + pesan jujur.
        # v2.19.2 — PULIHKAN edit grup: __SRC_ROWS (tuple anggota) dipakai,
        # grup 1-anggota editable seperti biasa, grup multi-anggota editable
        # dgn tulis ke SEMUA anggota (konfirmasi daftar baris diberikan).
        src_path = self._ctx.summary.get("workbook_path") if self._ctx.summary else None
        save = QPushButton("➡ Pindah ke tab Update nilai")
        save.setStyleSheet(
            "QPushButton { background:#0f766e; color:white; "
            "font-weight:700; border:none; padding:8px 14px; "
            "border-radius:5px; }"
            "QPushButton:hover { background:#115e59; }"
            "QPushButton:disabled { background:#cbd5e1; color:#94a3b8; }")
        # v2.17.3 — edit DISABLED utk file folder-flow (temp gabungan).
        # Edit nilai HANYA utk file asli (mode Pilih REKAP MENTAH / TEGAR).
        is_temp = _workbook_is_folder_temp(src_path)
        src_rows = getattr(self, "_cur_src_rows", []) or []
        if is_temp:
            save.setEnabled(False)
            save.setToolTip(
                "Nonaktif — file ini adalah file SEMENTERARA hasil gabungan "
                "folder (mode Proses dari Folder).\n"
                "Edit nilai akan tersimpan ke file sementara INI, BUKAN file "
                "asli di folder (file asli utuh — tapi edit tidak permanen).\n\n"
                "Untuk edit nilai permanen ke file asli:\n"
                "  1. Tutup pop-up ini.\n"
                "  2. Tab Pipeline → 🧮 Pilih REKAP MENTAH (format REKAP "
                "MENTAH_..._TEGAR dgn kolom NAMA RESTO).\n"
                "  3. Pilih file asli → Mulai Pipeline → edit via pop-up.")
        elif src_rows and src_path:
            save.setEnabled(True)
            if len(src_rows) == 1:
                save.setToolTip(
                    f"Tampung koreksi hari yg diubah ke daftar staging\n"
                    f"(tab Update nilai — BELUM ditulis ke file Excel):\n"
                    f"  File: {src_path}\n"
                    f"  baris Excel #{src_rows[0]} (sheet REKAP MENTAH)\n\n"
                    f"Setelah ditampung, tab pindah otomatis ke Update nilai.\n"
                    f"Kumpulkan koreksi lain, lalu klik 'Proses semua' di\n"
                    f"tab Update nilai utk tulis sekaligus ke file Excel\n"
                    f"(langsung timpa, tanpa backup — TOTAL dihitung ulang).")
            else:
                rows_txt = ", ".join(f"#{r}" for r in src_rows)
                save.setToolTip(
                    f"Tampung koreksi hari yg diubah ke daftar staging\n"
                    f"(tab Update nilai — BELUM ditulis ke file Excel):\n"
                    f"  File: {src_path}\n"
                    f"  baris Excel: {rows_txt} ({len(src_rows)} anggota grup)\n"
                    f"Nilai baru ditulis SAMA ke tiap anggota saat diproses.\n\n"
                    f"Setelah ditampung, tab pindah otomatis ke Update nilai.\n"
                    f"Klik 'Proses semua' di sana utk tulis sekaligus.")
        else:
            save.setEnabled(False)
            why = ("__SRC_ROW tidak ada di record"
                   if not src_rows
                   else "workbook_path tidak ada di summary")
            save.setToolTip(
                f"Nonaktif — {why}.\n"
                "Jalankan ulang pipeline (tab Pipeline → 🧮 Pilih REKAP "
                "Mentah → Mulai) supaya mapping baris Excel terpasang.")
        save.clicked.connect(self._on_stage_edits)
        self._save_btn = save
        alay.addWidget(save)

        btns = QWidget()
        bl = QHBoxLayout(btns)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        if rec.get("NAMA RESTO") is not None:
            b = QPushButton("🏬 Fokus cabang ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA RESTO"):
                              self._ctx.set_filter("cabang", v))
            bl.addWidget(b)
        if (rec.get("NAMA BARANG") is not None):
            b = QPushButton("📦 Fokus item ini")
            b.clicked.connect(lambda _=False, v=rec.get("NAMA BARANG"):
                              self._ctx.set_filter("item", v))
            bl.addWidget(b)
        # v2.19.0: 'Fokus alasan' disembunyikan utk record GRUP —
        # KETERANGAN grup = JOIN banyak alasan ("A | B"), nilainya tak
        # pernah cocok dgn filter keterangan baris-detail.
        if (not is_group and rec.get("KETERANGAN") is not None
                and str(rec.get("KETERANGAN")) not in ("", "nan")):
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

    def _row_fingerprints(self, rec: pd.Series) -> list[str]:
        """v2.19.0 — sidik jari PLURAL utk follow-up pop-up.

        Record GRUP (tampilan item×cabang) membawa __FPS (tuple sidik
        jari semua anggota) → kembalikan semuanya. Record baris tunggal
        → satu sidik jari via _row_fingerprint (fallback lama)."""
        v = rec.get(_GRP_FPS_COL)
        if isinstance(v, tuple) and len(v):
            return [str(x) for x in v if str(x) not in ("", "nan", "None")]
        fp = self._row_fingerprint(rec)
        return [fp] if fp else []

    def _fu_btn_text(self, in_list: bool, is_group: bool = False) -> str:
        if is_group:
            return ("☑ Masuk Follow Up (semua baris grup ini)" if not in_list
                    else "✅ Semua baris grup di Follow Up — klik utk "
                         "keluarkan")
        return ("☑ Masuk Follow Up" if not in_list
                else "✅ Sudah di Follow Up — klik utk keluarkan")

    def _on_fu_toggle(self) -> None:
        """Klik tombol → toggle state ctx (broadcast → badge tab + tabel
        kolom ✓ semua view + tombol ini sendiri via _on_fu_state_changed).
        v2.19.0: record grup = toggle SEMUA anggota (satu broadcast —
        pola add/remove_followup_many)."""
        fps = getattr(self, "_cur_fps", None)
        if not fps:
            return
        fset = self._ctx.followup_set()
        if len(fps) == 1:
            self._ctx.toggle_followup(fps[0], fps[0] not in fset)
        elif any(f not in fset for f in fps):
            self._ctx.add_followup_many(fps)
        else:
            self._ctx.remove_followup_many(fps)
        n = len(self._ctx.followup_keys)
        self._ctx.set_status(
            f"✓ Daftar follow-up kini {fmt_id(n)} baris (dari pop-up "
            "detail)", "done")

    def _on_fu_state_changed(self) -> None:
        """followup_changed (toggle/bulk dari mana pun) → perbarui teks
        tombol pop-up IN-PLACE bila pop-up sedang menampilkan baris.
        v2.19.0: plural — grup di Follow Up bila ADA anggota tercentang."""
        fps = getattr(self, "_cur_fps", None)
        if self._fu_btn is not None and fps:
            try:
                is_group = len(fps) > 1
                self._fu_btn.setText(
                    self._fu_btn_text(
                        any(f in self._ctx.followup_set() for f in fps),
                        is_group))
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

    # ------------------------------------------------------------
    # v2.16.0 — EDITABLE DAY MAP + SAVE HANDLER (fitur "edit dari pop-up")
    # ------------------------------------------------------------

    def _editable_day_map(self, rec: pd.Series,
                          day_names: list[str]) -> QWidget:
        """Grid 31 sel EDITABLE (v2.16.0) — QDoubleSpinBox per hari.

        Beda dgn _day_map (read-only QLabel): setiap sel = spinbox numerik
        yg user bisa ubah langsung di pop-up. Nilai diambil dari record
        (0 bila NaN/kosong). Hari tersangka disorot merah (visual only —
        masih bisa diedit). Simpan lewat tombol "💾 Simpan koreksi" footer.

        Anti silent-error:
          - Nilai NaN/kosong → 0.0 eksplisit (bukan diam-diam string kosong
            yg gagal parse nanti).
          - Range 0..1e9 (tolak absurd).
          - Original value disimpan di self._day_orig utk banding "apa
            berubah?" — simpan hanya yg CHANGED (bukan rewrite semua).
        """
        host = QWidget()
        gl = QGridLayout(host)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(3)
        # Hari tersangka (visual highlight — tidak mempengaruhi editability)
        tersangka = None
        for src in ("HARI TERSANGKA", "HARI MAX"):
            v = rec.get(src)
            try:
                if v is not None and not pd.isna(v):
                    tersangka = int(float(v))
                    break
            except (TypeError, ValueError):
                pass
        self._day_edits = {}
        self._day_orig = {}
        for i, name in enumerate(day_names):
            hari = int(name)
            raw = rec.get(name)
            v = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
            val = 0.0 if (v != v or v is None) else float(v)  # NaN → 0
            # Sel: label tanggal kecil + spinbox
            cell_host = QWidget()
            cl = QVBoxLayout(cell_host)
            cl.setContentsMargins(1, 1, 1, 1)
            cl.setSpacing(0)
            lbl = QLabel(str(hari), cell_host)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:#94a3b8; font-size:9px; "
                              "font-weight:600; background:transparent;")
            cl.addWidget(lbl)
            sp = QDoubleSpinBox(cell_host)
            sp.setRange(0.0, 1e9)
            sp.setDecimals(2)
            sp.setSingleStep(1.0)
            sp.setValue(val)
            sp.setCorrectionMode(
                sp.CorrectionMode.CorrectToPreviousValue)
            sp.setGroupSeparatorShown(True)
            sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sp.setMinimumWidth(74)
            sp.setMinimumHeight(24)
            # v2.16.1 — blok scroll wheel (permintaan user: ketik/klik aja,
            # jangan scroll — khawatir tidak sengaja ubah nilai).
            sp.installEventFilter(self._no_wheel)
            sp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            if hari == tersangka:
                sp.setStyleSheet(
                    "QDoubleSpinBox { background:#fee2e2; color:#dc2626; "
                    "font-weight:700; border:1px solid #fca5a5; "
                    "border-radius:4px; }")
                sp.setToolTip(f"Hari {hari} — TERSANGKA. Nilai asli: "
                              f"{fmt_cell(val)}. Ubah lalu Simpan.")
            elif val > 0:
                sp.setStyleSheet(
                    "QDoubleSpinBox { background:#f1f5f9; color:#334155; "
                    "border:1px solid #cbd5e1; border-radius:4px; }")
                sp.setToolTip(f"Hari {hari}. Nilai asli: {fmt_cell(val)}.")
            else:
                sp.setStyleSheet(
                    "QDoubleSpinBox { background:transparent; color:#94a3b8; "
                    "border:1px solid #e2e8f0; border-radius:4px; }")
                sp.setToolTip(f"Hari {hari} — kosong (0).")
            cl.addWidget(sp)
            self._day_edits[name] = sp
            self._day_orig[name] = val
            gl.addWidget(cell_host, i // 8, i % 8)
        return host

    @staticmethod
    def _find_df_label_by_src_row(df: pd.DataFrame,
                                  src_row: int) -> object | None:
        """Cari index label di df yg punya __SRC_ROW == src_row.

        Return label (utk df.at[label, col]) atau None bila tak ketemu /
        df tidak punya kolom __SRC_ROW. Transparan — tidak raise (caller
        yg putuskan: skip dengan pesan vs raise).
        """
        if df is None or df.empty or SRC_ROW_COL not in df.columns:
            return None
        col = df[SRC_ROW_COL]
        if not pd.api.types.is_numeric_dtype(col):
            return None
        mask = col == src_row
        if not mask.any():
            return None
        # Seharusnya persis 1 match. Bila duplikat (anomali), ambil
        # pertama + LOG supaya tidak senyap.
        idx = df.index[mask]
        if len(idx) > 1:
            import logging
            logging.getLogger("waste_anomaly.ui").warning(
                "__SRC_ROW=%d match %d baris di df (seharusnya 1) — "
                "ambil pertama. Duplikasi __SRC_ROW menandakan bug di "
                "ensure_rekap_header.", src_row, len(idx))
        return idx[0]

    def _on_stage_edits(self) -> None:
        """v2.19.5 — Handler klik "➡ Pindah ke tab Update nilai".

        Kumpulkan hari yg diubah → tampung ke ctx.pending_updates (staging)
        → MainWindow pindah tab ke "Update nilai" (signal ctx.update_staged).
        TIDAK menulis ke file Excel di sini — user klik "Proses semua" di
        tab Update nilai utk tulis batch (permintaan user: "kumpulin dulu
        terus baru proses dari pada proses satu per satu").

        Menggantikan _on_save_edits (v2.16.0 — simpan-satu-per-satu ke
        Excel via SaveEditsWorker). SaveEditsWorker tetap tersedia sbg API
        (BatchUpdateWorker memakai write_day_edits langsung).
        """
        if self._save_btn is None:
            return  # tombol mayat — jangan sentuh
        # v2.17.3 — guard: edit DISABLED utk file folder-flow (temp).
        src_path = (self._ctx.summary.get("workbook_path")
                    if self._ctx.summary else None)
        if _workbook_is_folder_temp(src_path):
            QMessageBox.information(
                self, "Edit tidak tersedia",
                "File ini adalah file SEMENTERARA hasil gabungan folder "
                "(mode Proses dari Folder).\n\n"
                "Edit nilai tidak tersedia karena akan tersimpan ke file "
                "sementara INI, BUKAN file asli di folder (file asli utuh, "
                "tapi edit tidak permanen).\n\n"
                "Untuk edit nilai permanen ke file asli:\n"
                "  Tab Pipeline → 🧮 Pilih REKAP MENTAH → pilih file format "
                "REKAP MENTAH_..._TEGAR (dgn kolom NAMA RESTO) → edit via "
                "pop-up.")
            return
        # 1. Kumpulkan perubahan
        if not self._day_edits:
            QMessageBox.information(
                self, "Tidak ada hari untuk diedit",
                "Pop-up belum memuat grid hari. Klik baris tabel lain "
                "untuk membuka detail.")
            return
        # v2.19.2 — src_rows (list, dukungan grup multi-anggota). Fallback
        # ke _cur_src_row tunggal utk jalur lama (dataset pra-v2.19.2).
        src_rows = list(getattr(self, "_cur_src_rows", []) or [])
        if not src_rows and self._cur_src_row is not None:
            src_rows = [int(self._cur_src_row)]
        if not src_rows:
            QMessageBox.warning(
                self, "Tidak bisa menampung koreksi",
                "Record ini tidak punya mapping baris Excel (__SRC_ROW / "
                "__SRC_ROWS).\n"
                "Jalankan ulang pipeline (tab Pipeline → 🧮 Pilih REKAP "
                "Mentah → Mulai) supaya mapping terpasang.\n\n"
                "Kemungkinan sebab: record dari dataset lama yang dimuat "
                "sebelum fitur edit pop-up aktif.")
            return
        if not src_path:
            QMessageBox.warning(
                self, "Tidak bisa menampung koreksi",
                "Path file Excel sumber tidak ada di summary context.\n"
                "Jalankan ulang pipeline dari tab Pipeline.")
            return
        day_edits: dict[str, float] = {}
        day_orig: dict[str, float] = {}
        for name, sp in self._day_edits.items():
            try:
                new_val = float(sp.value())
            except (TypeError, ValueError):
                QMessageBox.critical(
                    self, "Nilai tidak valid",
                    f"Nilai hari {name} bukan angka yang valid. Perbaiki "
                    f"lalu coba lagi.")
                return
            orig = self._day_orig.get(name, 0.0)
            if abs(new_val - orig) > 1e-9:  # hanya yg berubah
                day_edits[name] = new_val
                day_orig[name] = float(orig)
        if not day_edits:
            QMessageBox.information(
                self, "Tidak ada perubahan",
                "Tidak ada nilai hari yang berubah dari nilai asli.\n"
                "Ubah minimal satu hari di grid atas lalu klik tombol "
                "Pindah ke tab Update nilai.")
            return
        # 2. Bangun entry staging + label dari record aktif.
        rec = getattr(self, "_cur_rec", None)

        def _s(name: str) -> str:
            v = rec.get(name) if rec is not None else None
            if v is None:
                return ""
            if isinstance(v, float) and v != v:  # NaN
                return ""
            return str(v).strip()

        jenis = _s("JENIS")
        barang = _s("NAMA BARANG")
        resto = _s("NAMA RESTO")
        label = " · ".join(p for p in (jenis, barang, resto) if p)
        rows_txt = ", ".join(f"#{r}" for r in src_rows)
        changes_txt = "\n".join(
            f"  Hari {d}: {fmt_cell(day_orig.get(d, 0.0))} → "
            f"{fmt_color_styled_write_day_value(day_edits[d])}"
            for d in sorted(day_edits, key=int))
        from pathlib import Path
        # 3. Konfirmasi tampung (BELUM tulis Excel — aman dibatalkan).
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setWindowTitle("Tampung koreksi ke Update nilai")
        confirm.setText(
            f"Tampung {len(day_edits)} koreksi hari ke daftar staging?\n\n"
            f"  File: {Path(src_path).name}\n"
            f"  Baris Excel: {rows_txt}\n"
            f"  Item: {label}\n\n"
            f"Perubahan:\n{changes_txt}\n\n"
            f"Koreksi BELUM ditulis ke file Excel — ditampung dulu di\n"
            f"tab Update nilai. Kumpulkan koreksi lain, lalu klik\n"
            f"'Proses semua' di tab Update nilai utk menulis sekaligus.")
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirm.setDefaultButton(QMessageBox.StandardButton.Yes)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            self._ctx.set_status("Tampung koreksi dibatalkan user.", "info")
            return
        confirm.deleteLater()
        # 4. Tampung ke ctx.pending_updates → pancar update_staged
        # (MainWindow pindah tab) + updates_changed (UpdateView refresh).
        entry = {
            "source": str(src_path),
            "src_rows": list(src_rows),
            "day_edits": dict(day_edits),
            "day_orig": dict(day_orig),
            "label": label,
            "jenis": jenis,
            "barang": barang,
            "resto": resto,
        }
        idx = self._ctx.add_update(entry)
        n_total = self._ctx.pending_count()
        self._ctx.set_status(
            f"Koreksi ditampung ke tab Update nilai (#{idx + 1} — total "
            f"{n_total}). Klik 'Proses semua' di tab Update nilai utk "
            f"tulis ke file Excel.", "info")
        self._ctx.log(
            f"[edit-pop-up] STAGE: {len(day_edits)} hari ke {rows_txt} "
            f"({label}) — total staging {n_total}.")

    def _on_save_done(self, result: dict) -> None:
        """Worker selesai SUKSES — update df + emit signal + dialog hasil.

        Dipanggil di UI thread (signal Qt cross-thread). result = dict dari
        write_day_edits (ok/sheet/src_row/cells_written/total_new/...).
        v2.19.2 — result["src_rows"] (list) utk grup multi-anggota: ctx.df
        disinkron utk SEMUA anggota + day_edited dipancar per-anggota.
        """
        if self._save_worker is not None:
            self._save_worker.deleteLater()
            self._save_worker = None
        src_row = result.get("src_row")
        # v2.19.2 — daftar semua baris anggota grup (multi) atau [src_row].
        result_rows = list(result.get("src_rows") or ([src_row] if src_row else []))
        day_edits = self._pending_edits or {}
        self._pending_edits = None
        n_written = result.get("cells_written", 0)
        total_new = result.get("total_new")
        # total per-anggota (utk sinkron ctx.df akurat — tiap anggota punya
        # TOTAL sendiri = sum hari setelah koreksi).
        per_row_results = result.get("results") or [result]
        src_path = (self._ctx.summary.get("workbook_path")
                    if self._ctx.summary else "")
        from pathlib import Path
        # Re-enable tombol + spinbox
        self._reset_save_ui()
        # Update ctx.df utk SEMUA baris anggota grup (v2.19.2)
        ctx_df = self._ctx.df
        synced: list[int] = []
        skipped_sync: list[int] = []
        if ctx_df is not None and SRC_ROW_COL in ctx_df.columns:
            for r, pres in zip(result_rows, per_row_results):
                lbl = self._find_df_label_by_src_row(ctx_df, r)
                if lbl is None:
                    skipped_sync.append(r)
                    continue
                for day, val in day_edits.items():
                    if day in ctx_df.columns:
                        ctx_df.at[lbl, day] = val
                t_new = pres.get("total_new")
                if t_new is not None and "TOTAL" in ctx_df.columns:
                    ctx_df.at[lbl, "TOTAL"] = t_new
                synced.append(r)
        elif result_rows:
            skipped_sync = list(result_rows)
        for r in skipped_sync:
            self._ctx.log(
                f"[edit-pop-up] WARNING: baris __SRC_ROW={r} tak ketemu di "
                f"ctx.df — update tabel dilewati. File Excel SUDAH tersimpan; "
                f"re-run pipeline utk sinkron.")
        # Pancar signal per-anggota — view pemilik update model df +
        # emit dataChanged (memberi tahu tiap baris berubah).
        for r, pres in zip(result_rows, per_row_results):
            self.day_edited.emit(r, dict(day_edits), pres.get("total_new"))
        # Update spinbox "original" HANYA bila pop-up masih tampilkan record
        # yg sama (user tak klik baris lain saat worker jalan). Bila record
        # berganti, spinbox sekarang = record baru — jangan sentuh style-nya.
        cur_rows = getattr(self, "_cur_src_rows", None) or (
            [self._cur_src_row] if self._cur_src_row is not None else [])
        same_record = bool(cur_rows) and set(cur_rows) == set(result_rows)
        if same_record:
            for day, val in day_edits.items():
                self._day_orig[day] = float(val)
                sp = self._day_edits.get(day)
                if sp is not None:
                    try:
                        sp.setStyleSheet(
                            "QDoubleSpinBox { background:#dcfce7; color:#166534; "
                            "border:1px solid #86efac; border-radius:4px; "
                            "font-weight:600; }")
                    except RuntimeError:
                        pass
        # Status + log transparan
        is_multi = result.get("multi", False)
        rows_lbl = (f"{len(result_rows)} baris grup "
                    f"({', '.join(f'#{r}' for r in result_rows)})"
                    if is_multi else f"baris #{src_row}")
        self._ctx.log(
            f"[edit-pop-up] SIMPAN OK: {n_written} sel hari ditulis ke "
            f"'{Path(src_path).name}' {rows_lbl}. "
            f"TOTAL: {result.get('prev_total')!r} → {total_new!r}.")
        self._ctx.set_status(
            f"Tersimpan: {n_written} hari ke {rows_lbl} "
            f"({Path(src_path).name}). TOTAL={fmt_cell(total_new)}. "
            f"Skor anomali/AVG/MAX STALE — re-run pipeline utk update.",
            "done")
        # v2.16.2: dialog sukses HANYA bila panel masih visible.
        if self.isVisible():
            QMessageBox.information(
                self, "Koreksi Tersimpan",
                f"Berhasil menulis {n_written} koreksi hari ke file Excel:\n"
                f"  {Path(src_path).name}\n"
                f"  {rows_lbl} (sheet '{result.get('sheet', '?')}')\n\n"
                f"TOTAL diperbarui: {fmt_cell(result.get('prev_total'))} → "
                f"{fmt_cell(total_new)}\n\n"
                f"PERHATIAN: Skor anomali, AVG, MAX, dan metrik turunan di "
                f"tabel masih pakai nilai LAMA (dihitung pipeline sebelum "
                f"koreksi).\n"
                f"Untuk recompute penuh: jalankan ulang pipeline (tab Pipeline "
                f"→ Mulai).")

    def _on_save_failed(self, msg: str, tb: str) -> None:
        """Worker GAGAL — dialog error eksplisit + log. JANGAN sentuh df."""
        if self._save_worker is not None:
            self._save_worker.deleteLater()
            self._save_worker = None
        self._pending_edits = None
        self._reset_save_ui()
        self._ctx.log(f"[edit-pop-up] GAGAL simpan: {msg}")
        if tb:
            self._ctx.log(f"[edit-pop-up] traceback:\n{tb}")
        self._ctx.set_status(f"Gagal simpan koreksi: {msg}", "error")
        QMessageBox.critical(
            self, "GAGAL Simpan Koreksi",
            f"Penulisan ke file Excel GAGAL:\n\n{msg}\n\n"
            + (f"Detail teknis:\n{tb}\n\n" if tb else "")
            + f"File sumber TIDAK berubah. Lihat log utk detail.")

    def _reset_save_ui(self) -> None:
        """Re-enable tombol Simpan + spinbox setelah worker selesai."""
        if self._save_btn is not None:
            try:
                # v2.17.3 — tetap disabled bila workbook = folder temp.
                src_path = (self._ctx.summary.get("workbook_path")
                            if self._ctx.summary else None)
                if _workbook_is_folder_temp(src_path):
                    self._save_btn.setEnabled(False)
                else:
                    self._save_btn.setEnabled(self._cur_src_row is not None)
                self._save_btn.setText("💾 Simpan koreksi hari ke file Excel")
            except RuntimeError:
                pass
        for sp in self._day_edits.values():
            try:
                sp.setEnabled(True)
            except RuntimeError:
                pass


def fmt_color_styled_write_day_value(v: float) -> str:
    """Helper kecil: format nilai utk dialog konfirmasi (str, 2 desimal)."""
    try:
        f = float(v)
        if f.is_integer():
            return str(int(f))
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v)


class DetailDialog(QDialog):
    """Pop-up detail baris anomali (v2.8.1) — pengganti panel inline.

    Non-modal: tabel tetap bisa diklik / di-sort / di-scroll saat pop-up
    terbuka. Satu instance dipakai ulang — setiap klik-ganda baris (atau
    Enter) memperbarui isi pop-up yang sama (bukan menumpuk jendela
    baru). Tutup lewat X kapan saja; klik-ganda baris lain membukanya
    kembali. Saat pop-up TERBUKA, klik-1×/panah cukup mengganti isinya.

    v2.18.6 (permintaan user: "klik sekali aja pop up langsung muncul…
    kadang bikin klik yang gak sengaja ketriger"): pop-up HANYA terbuka
    lewat klik-ganda / Enter — klik 1× saat pop-up tertutup tak lagi
    memicu apa pun (dulu v2.8.1: klik 1× langsung buka pop-up).
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
        Jalur niat-eksplisit (drill banding / ⛶ layar penuh) tidak
        tersentuh — mereka tetap mengaktifkan."""
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
        # v2.18.7 (permintaan user: "aku bisa pilih tampilkan yang sudah
        # masuk follow up atau tampilkan semua") — combo Tampilkan: filter
        # LOKAL view (pola combo Kategori PERUBAHAN): hanya menyaring
        # tabel ini; KPI, daftar Follow Up & ekspor tak tersentuh.
        lbl_fu = WLabel("Tampilkan:", ctrl)
        lbl_fu.setToolTip(
            "Saring tabel anomali menurut status follow-up:\n"
            "• Semua = tampilkan semua anomali (bawaan);\n"
            "• ✓ Sudah masuk Follow Up = hanya baris yang sudah\n"
            "  terkumpul di daftar Follow Up (tercentang ✓).\n"
            "Filter tampilan tabel ini saja — KPI, daftar Follow Up\n"
            "dan ekspor tidak terpengaruh.")
        cl.addWidget(lbl_fu)
        self._cb_followup = QComboBox(ctrl)
        self._cb_followup.addItem("Semua", None)
        self._cb_followup.addItem("✓ Sudah masuk Follow Up", "fu")
        self._cb_followup.setToolTip(lbl_fu.toolTip())
        self._cb_followup.currentIndexChanged.connect(
            lambda _i: self._on_fu_filter())
        cl.addWidget(self._cb_followup)
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
        # v2.20.0 (permintaan user: "tambah fitur juga aku bisa hide dan
        # unhide kolom di tab anomali") — tombol menu kolom: centang =
        # tampil, lepas centang = sembunyikan (data tetap ada di model —
        # hanya setColumnHidden; record pop-up detail tetap lengkap).
        self._btn_cols = QPushButton("⇔ Kolom", ctrl)
        self._btn_cols.setToolTip(
            "Sembunyikan / tampilkan kolom tabel Anomali:\n"
            "• lepas centang = kolom disembunyikan (data tetap ada —\n"
            "  pop-up detail & ekspor tidak terpengaruh);\n"
            "• 'Tampilkan semua kolom' mengembalikan semuanya.\n"
            "Berguna utk fokus kolom tertentu di layar sempit.")
        self._btn_cols.clicked.connect(self._on_column_menu)
        cl.addWidget(self._btn_cols)
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
            "maupun tampilan), ambang skor, dan combo Tampilkan:/Perubahan: "
            "— kembali ke tampilan anomali penuh.")
        self._btn_clear.clicked.connect(self._on_clear_filters)
        cl.addWidget(self._btn_clear)
        lay.addWidget(ctrl)
        self._ctrl = ctrl  # v2.12.2: toggle ⤢ (KPI + bar kontrol)

        # v2.16.1 — SortControl di bar kontrol (dibuat setelah self._table
        # ada, lalu disisipkan ke layout ctrl). Kolom di-refresh tiap render.
        # (self._table dibuat di bawah — SortControl dibuat setelahnya.)
        self._sort: SortControl | None = None

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
        # v2.20.0 — heatmap kolom '% to BOM' (permintaan user: "diberi warna
        # semacam heat map ... diabsolutekan dulu ... tampilkan nilai asli"):
        # background sel dari |nilai| (campur +/-), teks tetap nilai asli.
        # Skala dihitung ulang otomatis tiap set_dataframe (p99 |nilai|).
        self._table.model().set_heat_column("% to BOM")
        # v2.12.3: funnel filter + opsi sort di header tabel.
        # v2.12.4: SEMUA kolom ber-funnel (skip kolom ✓ + identitas __FP);
        # kolom mapping = state global ctx, lainnya = filter lokal view.
        # v2.19.0: + skip __FPS (daftar sidik jari anggota grup — kolom
        # internal tampilan grup, bukan nilai yang layak difilter).
        # v2.19.3: + skip __SEP (penanda baris pemisah layout sampel).
        self._table.setup_header_filters(
            _HF_COLS, self._on_header_filter, self._hf_state,
            all_cols=True,
            skip=(CHECK_COL, FP_COL, SRC_ROW_COL, FPS_LIST_COL, SEP_COL))
        self._table.selectionModel().currentRowChanged.connect(
            lambda *_: self._on_selection())
        # v2.13.5: sinyal QTableView.clicked memicu di SETIAP klik — termasuk
        # klik baris yang SAMA (currentRowChanged diam saat index tak
        # berubah). Tanpa ini: tutup pop-up (X) → klik baris sama → pop-up
        # TIDAK muncul lagi (keluhan user "klik 1× pop-up kadang tidak
        # muncul"). Guard idempoten DetailDialog membuat pemanggilan ganda
        # (currentRowChanged + clicked utk satu klik) tetap membangun sekali.
        # v2.18.6 (permintaan user: "klik sekali aja pop up langsung muncul
        # … kadang bikin klik yang gak sengaja ketriger"): klik 1× kini
        # hanya MEfollow pop-up yang SUDAH terbuka (guard isVisible di
        # _on_selection) — membuka pop-up = KLIK-GANDA / Enter
        # (_open_popup_row). v2.13.5: klik-2× → filter DIHAPUS (permintaan
        # user) — double_clicked kini berlangganan _open_popup_row.
        self._table.row_clicked.connect(lambda *_: self._on_selection())
        self._table.double_clicked.connect(self._open_popup_row)
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
        # v2.16.0: dengarkan signal koreksi hari dari pop-up — update model
        # df + emit dataChanged supaya tabel re-render sel baris ini.
        self._popup._panel.day_edited.connect(self._on_day_edited)

        # v2.16.1 — SortControl (tombol sort eksplisit di bar kontrol).
        # Dibuat setelah self._table ada; disisipkan ke ctrl layout.
        self._sort = SortControl(self._table, self._ctrl)
        self._ctrl.layout().insertWidget(self._ctrl.layout().count() - 1,
                                         self._sort)

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
        # v2.20.0 — kolom TABEL yang disembunyikan user (tombol '⇔ Kolom'):
        # nama kanonik TABLE_COLS; visible_cols di _refresh_table_impl
        # mengurangi keduanya (kanonik + alias). Data TETAP di model df —
        # hanya setColumnHidden (pop-up detail/ekspor tak tersentuh).
        self._hidden_cols: set[str] = set()
        # v2.12.4: memo hasil mask per (objek display, state filter) —
        # objek mask stabil per state → cache fit DataTable tetap kena
        # (pola _disp_cache LRU; A→B→A memakai ulang objek A).
        # v2.13.13 (gel-4 A5): entri = (weakref, hasil) dgn validasi
        # identitas (lihat followup_table._mask_local — anti tabrakan id
        # pasca-GC, audit A5).
        self._mask_cache: OrderedDict[tuple, tuple] = OrderedDict()
        # v2.19.3: memo df tampilan GRUP+PEMISAH (layout sampel) — objek
        # STABIL per objek shown (pola _disp_cache LRU-8 + weakref) supaya
        # cache fit DataTable tetap kena antar-refresh (kontrak perf
        # v2.9.0/test_v2120 'display memo objek stabil').
        self._sep_cache: OrderedDict[int, tuple] = OrderedDict()
        # v2.19.1 (audit bug C): memo 1-slot df sumber anomali tanpa
        # filter baris keterangan/status (jalur rebuild lintas-tab).
        self._src_cache: tuple | None = None
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
        # v2.19.1 (audit bug C): memo df sumber ikut basi bersama dataset.
        self._src_cache = None
        # v2.19.3: memo pemisah grup ikut basi bersama dataset.
        self._sep_cache.clear()
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

    def _on_fu_filter(self) -> None:
        """v2.18.7 — combo "Tampilkan:" (Semua / ✓ Sudah masuk Follow Up)
        → saring tabel (lokal view, tanpa state — pola _on_change_filter)."""
        self._refresh_table()

    # ------------------------------------------------------------
    # v2.20.0 — sembunyi/tampil kolom tabel (tombol '⇔ Kolom')
    # ------------------------------------------------------------
    def _on_column_menu(self) -> None:
        """Buka menu kolom (dibangun _build_column_menu) di bawah tombol."""
        menu = self._build_column_menu()
        btn = self._btn_cols
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))
        # v2.18.0 audit (UI-6): menu parented tak pernah dihapus otomatis
        # (per klik) — pensiunkan pasca exec (pola funnel/_on_context_menu).
        menu.deleteLater()

    def _build_column_menu(self) -> QMenu:
        """Menu kolom: centang = tampil, lepas = sembunyikan.

        Daftar = TABLE_COLS yang ada di dataset (kolom banding opsional
        tak tampil bila pembanding belum ada). Dibangun TERPISAH dari
        eksekusi supaya testable tanpa loop event modal (_on_column_menu
        memanggil ini lalu exec). Klik aksi menutup menu (perilaku
        bawaan QMenu) → refresh tabel lewat sinyal toggled."""
        mdf = self._table.model().dataframe
        cols = [c for c in TABLE_COLS if c in mdf.columns]
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for name in cols:
            title = _TABLE_ALIASES.get(name, name)
            act = QAction(title, menu)
            act.setCheckable(True)
            act.setChecked(name not in self._hidden_cols)
            tip = COLUMN_TOOLTIPS.get(name)
            if tip:
                act.setToolTip(tip)
            act.toggled.connect(
                lambda on, n=name: self._set_column_hidden(n, not on))
            menu.addAction(act)
        menu.addSeparator()
        act_all = QAction("Tampilkan semua kolom", menu)
        act_all.setToolTip("Kembalikan SEMUA kolom tabel yang sempat "
                           "disembunyikan.")
        act_all.triggered.connect(lambda: self._show_all_columns())
        menu.addAction(act_all)
        return menu

    def _set_column_hidden(self, name: str, hidden: bool) -> None:
        """Sembunyikan/tampilkan SATU kolom (nama kanonik TABLE_COLS).

        Jalur mekanis: nama dibuang dari visible_cols pada render
        berikutnya → DataTable._auto_columns menyembunyikan + TIDAK
        mengukur lebar kolom itu (persisten lintas re-fit, beda dari
        setColumnHidden manual yang ditimpa ulang tiap auto-fit)."""
        if hidden:
            self._hidden_cols.add(name)
        else:
            self._hidden_cols.discard(name)
        if self._ctx.df is not None:
            self._refresh_table()

    def _show_all_columns(self) -> None:
        """Kembalikan semua kolom tabel yang disembunyikan."""
        if self._hidden_cols:
            self._hidden_cols.clear()
            if self._ctx.df is not None:
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
        (pola _cb_mode HariView.refresh).
        v2.18.7: combo "Tampilkan:" (follow-up) ikut direset — dua combo
        filter lokal kini diperlakukan SAMA (tooltip Hapus Filter menjanjikan
        SEMUA; dataset baru tak mewarisi pilihan run lama)."""
        self._cb_change.blockSignals(True)
        self._cb_change.setCurrentIndex(0)
        self._cb_change.blockSignals(False)
        self._cb_followup.blockSignals(True)
        self._cb_followup.setCurrentIndex(0)
        self._cb_followup.blockSignals(False)

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

    def _followup_filter_active(self) -> bool:
        """v2.18.7 — override hook mixin (pola _reset_view_controls):
        combo "Tampilkan:" = ✓ Sudah masuk Follow Up → keanggotaan
        follow-up = hasil filter tabel → _on_followup_changed mixin
        me-render ulang (lepas centang ✓ = baris LANGSUNG hilang),
        bukan sekadar menyegarkan kolom ✓ in-place."""
        return self._cb_followup.currentData() == "fu"

    # ------------------------------------------------------------
    # v2.19.0 — TAMPILAN GRUP per (JENIS × NAMA BARANG × NAMA RESTO)
    # (sampel user "SAMPEL TAMPILAN BARU.xlsx"). Override mixin baris-
    # tunggal: ✓ grup = SEMUA sidik jari anggota sekaligus.
    # ------------------------------------------------------------
    def _key_akhir(self) -> int:
        """Hari terakhir periode run (penyebut AVG grup; fallback 31)."""
        try:
            return int((self._ctx.summary or {}).get("key_akhir", 31))
        except (TypeError, ValueError):
            return 31

    # v2.19.1 (audit bug B+C) — kolom TURUNAN grup yang TIDAK boleh
    # difilter di level baris: nilai KETERANGAN grup = JOIN alasan anggota
    # ('Handling | Cancel Nota' — tak pernah cocok dgn nilai baris tunggal
    # → tabel 0 baris), ANOMALY STATUS grup = paling parah (worst-of-group
    # → filter baris memangkas TOTAL grup diam-diam: grup 2-anggota
    # 100+40 tampil TOTAL 40). Keduanya difilter LEVEL GRUP: isin pada
    # df grup SETELAH agregasi (pola combo 'Perubahan:' v2.19.0).
    # Kunci grup (NAMA RESTO/NAMA BARANG/JENIS) tetap GLOBAL level-baris —
    # isin kunci ≡ isin grup, TOTAL utuh, sinkron antar-tab tetap hidup.
    _GRP_FILTER_COLS = frozenset({"KETERANGAN", "ANOMALY STATUS"})
    _GRP_FILTER_KEYS = frozenset({"keterangan", "status"})

    def _on_header_filter(self, col: str, key: str, values) -> None:
        """Override mixin — funnel KETERANGAN/ANOMALY STATUS = LOKAL grup.

        Funnel di tab ini menawarkan nilai KOLOM TAMPILAN (join/worst
        grup — menu dibaca dari df model), jadi filternya harus isin pada
        df grup, BUKAN set_filter global level-baris (nilai join tak
        pernah match baris → 0 baris; status memangkas TOTAL).
        Interaksi funnel kolom ini = AMBIL ALIH dim dari filter global
        (anti-loop: tanpa ini, membersihkan lokal membuat filter global
        — dipasang dari tab Hari — muncul kembali; baris yang barusan
        di-uncheck tetap tampil)."""
        if col in self._GRP_FILTER_COLS or key in self._GRP_FILTER_KEYS:
            vals = [v for v in (values or [])]
            if vals:
                self._hfilters[col] = vals
            else:
                self._hfilters.pop(col, None)
            gv = self._ctx.active_filters.get(key)
            if gv:
                # Lepas dim global (broadcast → render view ini + tab
                # lain; TANPA render ganda — jalur lokal tak refresh lagi).
                self._ctx.set_filter(key, None)
                return
            self._refresh_table()
            return
        FollowupTableMixin._on_header_filter(self, col, key, values)

    def _hf_state(self, col: str):
        """Override mixin — status funnel KETERANGAN/ANOMALY STATUS.

        Aktif (terisi merah) bila filter LOKAL grup aktif, ATAU filter
        GLOBAL dim itu aktif (dipasang dari tab Hari — data grup ikut
        tersaring level grup oleh _anomali_source_df + _grp_global_mask).
        Utk kasus global, nilai yg dikembalikan = nilai grup yg SEDANG
        TAMPIL (cache per-render _grp_paint_vals) supaya menu funnel
        membuka dgn centangan yg benar (nilai join — bukan nilai baris
        global yg tak pernah match)."""
        if col in self._GRP_FILTER_COLS:
            v = self._hfilters.get(col)
            if v:
                return list(v)
            key = _HF_COLS.get(col)
            gv = self._ctx.active_filters.get(key) if key else None
            if isinstance(gv, list) and gv or (isinstance(gv, str) and gv):
                paint = getattr(self, "_grp_paint_vals", None) or {}
                return list(paint.get(col) or [])
            return None
        return FollowupTableMixin._hf_state(self, col)

    def _grp_global_mask(self, shown: pd.DataFrame, col: str):
        """Mask level-grup utk filter GLOBAL dim kolom turunan (v2.19.1).

        Filter global keterangan/status dipasang dari tab HARI (level
        baris di sana). Di view grup, penerapannya:
        - KETERANGAN  : keanggotaan alasan dalam JOIN grup — grup yang
          MELIBATKAN alasan terpilih tampil (TOTAL utuh; isin nilai
          tunggal pada join tak pernah match → 0 baris).
        - ANOMALY STATUS: worst-of-group (nilai yg TAMPIL di kolom) in
          vals — konsisten dgn kolom tampilan.
        Return None bila dim tak difilter global (funnel lokal sudah
        di-apply _mask_local di atas — isin nilai grup persis)."""
        v = self._hfilters.get(col)
        if v:
            return None  # lokal aktif — global diambil alih (anti-loop)
        key = _HF_COLS.get(col)
        gv = self._ctx.active_filters.get(key) if key else None
        if isinstance(gv, list) and gv:
            vals = gv
        elif isinstance(gv, str) and gv:
            vals = [gv]
        else:
            return None
        if col == "KETERANGAN":
            vs = {str(x) for x in vals}
            parts = shown[col].astype(str).str.split(r"\s*\|\s*")
            return parts.map(lambda ps: any(p in vs for p in ps))
        return shown[col].isin(vals)

    def _anomali_source_df(self) -> pd.DataFrame | None:
        """v2.19.1 (audit bug C lintas-tab) — df anomali TANPA filter
        baris-level keterangan/status.

        Filter global kedua dim itu (dipasang dari funnel tab Hari /
        drill pop-up baris) diterapkan LEVEL GRUP di view ini (lihat
        _refresh_table_impl) supaya TOTAL grup tak terpangkas diam-diam.
        Tanpa filter itu aktif → ctx.anomali_df() apa adanya (memoized,
        objek stabil → cache fit/enrich tetap kena). Memo 1-slot utk
        jalur rebuild (df baru per panggilan tanpa memo akan terus
        me-miss cache enrich change_vs_history)."""
        ctx = self._ctx
        af = ctx.active_filters or {}
        if not any(af.get(k) for k in self._GRP_FILTER_KEYS):
            self._src_cache = None
            return ctx.anomali_df()
        if ctx.df is None:
            return None
        sig = (id(ctx.df), ctx.data_version, ctx.score_min,
               tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                            for k, v in af.items()
                            if k not in self._GRP_FILTER_KEYS)))
        cached = self._src_cache
        if cached is not None and cached[0] == sig and cached[1] is not None:
            return cached[1]
        safe = {k: v for k, v in af.items()
                if k not in self._GRP_FILTER_KEYS}
        base = _apply_filters(ctx.df, safe) if safe else ctx.df
        # v2.19.8 — baris Normal TIDAK lagi dibuang (permintaan user:
        # "tampilkan semua data"). Ambang skor (spinner "Skor ≥") tetap
        # jalan — TANPA filter keterangan/status (lokal grup via funnel).
        if ctx.score_min > 0 and "ANOMALY SCORE" in base.columns:
            base = base[pd.to_numeric(base["ANOMALY SCORE"], errors="coerce")
                        .fillna(0) >= ctx.score_min]
        self._src_cache = (sig, base)
        return base

    def _display_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Override mixin — df tampilan = AGRAGASI GRUP per item×cabang.

        Memo LRU per objek df (pola mixin — objek stabil → cache fit
        DataTable kena antar-state); ✓ grup disegarkan tiap pemakaian.
        Bila df TAK punya kunci grup (fixture minimal), fallback jalur
        mixin baris-tunggal supaya tabel tetap tampil (defensif)."""
        if df is None or df.empty or not all(
                k in df.columns for k in ("JENIS", "NAMA BARANG",
                                          "NAMA RESTO")):
            return FollowupTableMixin._display_df(self, df)
        key = id(df)
        entry = self._disp_cache.get(key)
        if entry is not None and entry[0]() is df and entry[1] is not None:
            self._disp_cache.move_to_end(key)
            disp = entry[1]
            self._refresh_check_col(disp)
            return disp
        baseline = self._ctx.banding_baseline_effective()
        fps = self._fps_for(df)
        disp = group_anomali_display(
            df, fps, self._ctx.config,
            key_akhir=self._key_akhir(),
            has_baseline=baseline is not None)
        disp.insert(0, CHECK_COL, False)
        self._refresh_check_col(disp)
        self._disp_cache[key] = (weakref.ref(df), disp)
        while len(self._disp_cache) > self._DISP_LRU:
            self._disp_cache.popitem(last=False)
        return disp

    def _separated_df(self, shown: pd.DataFrame) -> pd.DataFrame:
        """v2.19.3 — df tampilan GRUP urut-sampel + BARIS PEMISAH kosong.

        Urut (JENIS, NAMA BARANG, NAMA RESTO) lalu sisip pemisah antar
        grup (JENIS, NAMA BARANG) — layout SAMPEL TAMPILAN BARU.xlsx di
        TABEL tab Anomali (permintaan user: "insert blank line after each
        item label"). Memo LRU per objek shown (pola _display_df) — objek
        df ber-pemisah STABIL antar-refresh → cache fit DataTable tetap
        kena (kontrak perf v2.9.0). Defensif: grouping/tanpa kunci grup /
        error → shown apa adanya (tabel tetap jalan tanpa spasi).
        """
        try:
            if (shown is None or shown.empty
                    or not all(k in shown.columns for k in GROUP_KEYS)):
                return shown
            key = id(shown)
            entry = self._sep_cache.get(key)
            if (entry is not None and entry[0]() is shown
                    and entry[1] is not None):
                self._sep_cache.move_to_end(key)
                return entry[1]
            disp = shown.sort_values(
                GROUP_KEYS, na_position="last", kind="mergesort")
            disp = insert_group_separators(disp)
            self._sep_cache[key] = (weakref.ref(shown), disp)
            while len(self._sep_cache) > self._DISP_LRU:
                self._sep_cache.popitem(last=False)
            return disp
        except Exception:  # noqa: BLE001 — layout spasi opsional, defensif
            return shown

    def _refresh_check_col(self, d: pd.DataFrame) -> None:
        """Override hook mixin — ✓ GRUP = ADA anggota yang tercentang."""
        if (CHECK_COL in d.columns and _GRP_FPS_COL in d.columns):
            fset = self._ctx.followup_set()
            d[CHECK_COL] = [
                any(str(f) in fset for f in fps)
                if isinstance(fps, tuple) else False
                for fps in d[_GRP_FPS_COL]]
        elif CHECK_COL in d.columns and FP_COL in d.columns:
            d[CHECK_COL] = d[FP_COL].isin(self._ctx.followup_set())

    def _on_check_toggled(self, row: int, checked: bool) -> None:
        """Override mixin — klik ✓ GRUP = masukkan/keluarkan SEMUA baris
        anggota grup (satu broadcast, pola add/remove_followup_many)."""
        rec = self._table.model().record(row)
        fps = rec.get(_GRP_FPS_COL) if rec is not None else None
        if not isinstance(fps, tuple) or not fps:
            return FollowupTableMixin._on_check_toggled(self, row, checked)
        members = [str(f) for f in fps if str(f) not in ("", "nan")]
        if checked:
            self._ctx.add_followup_many(members)
        else:
            self._ctx.remove_followup_many(members)
        n = len(self._ctx.followup_keys)
        self._ctx.set_status(
            (f"✓ {fmt_id(len(members))} baris grup masuk Follow Up"
             if checked else
             f"✓ {fmt_id(len(members))} baris grup dikeluarkan")
            + f" — total {fmt_id(n)} baris", "done")

    def _on_check_all(self) -> None:
        """Override mixin — '☑ Centang yang tampil': semua baris ANGGOTA
        semua grup yang tampil masuk follow-up (SATU broadcast)."""
        mdf = self._table.model().dataframe
        if (mdf is None or len(mdf) == 0
                or _GRP_FPS_COL not in mdf.columns):
            return FollowupTableMixin._on_check_all(self)
        all_fps: list[str] = []
        seen: set[str] = set()
        for fps in mdf[_GRP_FPS_COL]:
            if isinstance(fps, tuple):
                for f in fps:
                    s = str(f)
                    if s and s != "nan" and s not in seen:
                        seen.add(s)
                        all_fps.append(s)
        if not all_fps:
            self._ctx.set_status("Tidak ada baris yang tampil — longgarkan "
                                 "filter dulu.", "error")
            return
        added = self._ctx.add_followup_many(all_fps)
        total = len(self._ctx.followup_keys)
        if added:
            self._ctx.set_status(
                f"✓ {fmt_id(added)} baris masuk Follow Up — total "
                f"{fmt_id(total)}", "done")
        else:
            self._ctx.set_status(
                f"Semua baris yang tampil sudah tercentang (total "
                f"{fmt_id(total)})", "done")

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
        # v2.19.1 (audit bug C): df sumber TANPA filter baris keterangan/
        # status — kedua dim itu kolom TURUNAN grup (join alasan /
        # worst-of-group), filternya diterapkan LEVEL GRUP setelah
        # agregasi supaya TOTAL grup tak terpangkas diam-diam.
        df = self._anomali_source_df()
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
        # v2.19.0: filter kini LEVEL GRUP (dijalankan SETELAH agregasi —
        # lihat bawah); dulu level baris sebelum grouping, yang membuat
        # TOTAL grup terpangkas diam-diah saat kategori aktif.
        cat = self._cb_change.currentData() if self._cb_change.isEnabled() \
            else None
        self._cb_change.setEnabled(baseline is not None)
        # v2.13.14 (gel-5 C15) → v2.19.0: tooltip kolom banding menyebut
        # SUMBER pembandingnya (bulan pilihan combo Banding Periode /
        # Tipikal) — dulu label polos di SEMUA tab padahal "bulan lalu"
        # beda sumber antar tab. Alias judul sampel user ([TOTAL]/[% to
        # BOM]) dipasang bersamaan; kolom gabungan TOTAL BULAN LALU & %
        # Selisih menerima tooltip sumber pembanding (judulnya tetap nama
        # sampel — data/sort/record nama kanonik).
        lbl_b = baseline_label(baseline)
        aliases = dict(_TABLE_ALIASES)
        tips: dict[str, str] = {}
        if lbl_b:
            tips[LASTMONTH_COMBINED_COL] = (
                COLUMN_TOOLTIPS.get(LASTMONTH_COMBINED_COL, "")
                + f"\nSumber saat ini: {lbl_b} (mengikuti combo tab "
                "'Banding Periode')")
        self._table.model().set_header_map(aliases or None)
        self._table.model().set_tooltip_map(tips or None)
        # v2.7.0 (V26-C1): model memegang df PENUH (bukan irisan TABLE_COLS
        # lagi) — kolom non-tabel disembunyikan via visible_cols. Record
        # terpilih / double-klik tetap membawa SEMUA kolom (12 sinyal,
        # ANOMALY REASONS, peer, MAX, ...) ke pop-up detail + drill-down.
        # v2.19.0: df tampilan = AGRAGASI GRUP per (JENIS×NAMA BARANG×NAMA
        # RESTO) — sampel user "SAMPEL TAMPILAN BARU.xlsx" (lihat
        # _display_df override + ui/grouping.py).
        # v2.12.0: objek display di-memo per objek df → cache fit DataTable
        # tetap kena (kontrak 'konsumen hanya membaca' utk objek LRU/enriched
        # tetap utuh — grup dibangun dari salinan).
        disp = self._display_df(df)
        # v2.12.4: funnel LOKAL kolom non-ctx — mask isin di atas display
        # (memo per state; ✓ disegarkan tiap pemakaian). 'Perubahan:' combo
        # dulu di sini — v2.19.0 dipindah SETELAH agregasi grup (lihat
        # bawah) supaya TOTAL grup tak terpangkas.
        shown = self._mask_local(disp)
        # v2.19.0 — filter kategori PERUBAHAN di level GRUP: kategori
        # dihitung dari TOTAL grup vs bulan lalu grup (bukan memangkas
        # anggota grup — TOTAL yang tampil selalu utuh).
        if cat and "PERUBAHAN" in shown.columns:
            sel = shown[shown["PERUBAHAN"] == cat]
            shown = sel.copy() if len(sel) else sel
        # v2.19.1 (audit bug B+C) — filter KETERANGAN/ANOMALY STATUS di
        # LEVEL GRUP. Funnel LOKAL kolom ini sudah di-apply _mask_local
        # di atas (isin nilai grup persis — nilai menu = nilai kolom).
        # Filter GLOBAL dim itu (dipasang dari tab Hari; df sumber sudah
        # dibangun tanpa keduanya oleh _anomali_source_df) diterapkan di
        # sini: KETERANGAN = keanggotaan alasan dalam join, STATUS =
        # worst-of-group — TOTAL grup tak perpangkas.
        grp_paint: dict[str, list] = {}
        for gcol in sorted(self._GRP_FILTER_COLS):
            if gcol not in shown.columns:
                continue
            mask = self._grp_global_mask(shown, gcol)
            if mask is not None:
                sel = shown[mask]
                shown = sel.copy() if len(sel) else sel
            # cache lukisan funnel: nilai kolom yg TAMPIL pasca-filter
            # (menu membuka dgn centangan benar saat global aktif).
            try:
                grp_paint[gcol] = [str(v) for v in pd.unique(shown[gcol])]
            except Exception:  # noqa: BLE001 — nilai eksotis: skip cache
                pass
        self._grp_paint_vals = grp_paint
        # v2.18.7 — combo "Tampilkan:" ✓ Sudah masuk Follow Up: hanya
        # baris ber-✓ (filter LOKAL view — KPI/daftar Follow Up tak
        # tersentuh). .copy() eksplisit: hasil slice membawa _is_copy —
        # mixin _on_followup_changed menulis kolom ✓ pada df model.
        fu_only = self._cb_followup.currentData() == "fu"
        if fu_only and CHECK_COL in shown.columns:
            sel = shown[shown[CHECK_COL].astype(bool)]
            shown = sel.copy() if len(sel) else sel
        # v2.19.1 (audit bug A): visible_cols dihitung dari df GRUP FINAL
        # (shown) — dulu dari df BARIS awal, yang tak pernah punya kolom
        # khusus grup (SOURCE DATA GABUNGAN, TOTAL BULAN LALU & % Selisih,
        # Selisih Bulan Lalu) → kolom2 inti redesain TERSEMBUNYI selamanya.
        # Alias judul WAJIB ikut (set_dataframe mencocokkan nama JUDUL/
        # alias — pola view_followup v2.12.3) tanpa merusak SortControl
        # (entri non-kanonik dibuang sejak v2.19.0).
        # v2.20.0: kolom yang disembunyikan user (tombol '⇔ Kolom') dibuang
        # dari daftar — mekanisme visible_cols dipakai (bukan setColumnHidden
        # manual) supaya status sembunyi PERSISTEN lintas auto-fit tabel.
        visible = ([CHECK_COL]
                   + [c for c in TABLE_COLS
                      if c in shown.columns and c not in self._hidden_cols]
                   + [_TABLE_ALIASES[c] for c in TABLE_COLS
                      if c in shown.columns and c in _TABLE_ALIASES
                      and c not in self._hidden_cols])
        # v2.19.3 — TABEL layout SAMPEL TAMPILAN BARU (permintaan user:
        # "tampilan di tab anomali kok gak ada spasi nya ... insert blank
        # line after each item label dari kolom jenis dan nama barang"):
        # urut per GRUP ITEM (JENIS, NAMA BARANG, NAMA RESTO) — bukan skor
        # turun (dulu) — + BARIS KOSONG pemisah antar grup (JENIS, NAMA
        # BARANG). Sort by skor/angka lain tetap tersedia via SortControl /
        # klik judul (model.sort separator-aware: sort kolom non-grup =
        # tabel polos ter-ranked; sort kolom grup = pemisah disisip ulang;
        # "(urut default)" mengembalikan layout grup+spasi).
        # MEMO LRU per objek shown (pola _disp_cache) — objek df ber-pemisah
        # STABIL antar-refresh supaya cache fit DataTable tetap kena
        # (kontrak perf v2.9.0; insert membangun df baru tiap kali tanpa memo).
        disp = self._separated_df(shown)
        self._table.set_dataframe(disp, sort_desc=None,
                                  narrow_hide=[SRC_GAB_COL, "PERUBAHAN"],
                                  visible_cols=visible,
                                  width_caps=_WIDTH_CAPS)
        # Aktifkan render separator (baris kosong) di model — SETELAH
        # set_dataframe (setter tak memicu render ulang; data()/flags()
        # membaca kolom __SEP per baris).
        self._table.model().set_separator_column(
            SEP_COL, group_keys=SEP_KEYS)
        # v2.16.1 — refresh pilihan kolom SortControl sesuai dataset baru
        if self._sort is not None:
            self._sort.refresh_columns()
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if len(shown) == 0:
            # v2.18.7: pesan 0-baris dibedakan per penyebab — filter
            # follow-up aktif tapi belum ada centangan vs filter/skor
            # umum (pola D6/D24: pesan kontekstual, bukan generik).
            if fu_only:
                self._lbl_count.setText(
                    "0 anomali lolos filter — belum ada baris yang masuk "
                    "Follow Up (centang ✓ dulu, atau ganti Tampilkan: ke "
                    "Semua).")
            else:
                self._lbl_count.setText("0 anomali lolos filter — longgarkan "
                                        "filter atau ambang skor.")
        else:
            self._lbl_count.setText(
                f"{fmt_id(len(shown))} grup item×cabang tampil (dari "
                f"{fmt_id(full)} baris data)")
        self._refresh_kpi()

    def _refresh_kpi(self) -> None:
        filtered = self._ctx.filtered_df()
        full = len(self._ctx.df) if self._ctx.df is not None else 0
        if filtered is not None:
            self._kpi.update_from(filtered, full)

    # ------------------------------------------------------------
    # v2.16.0 — handler signal koreksi hari dari pop-up detail
    # ------------------------------------------------------------
    def _on_day_edited(self, src_row: int, day_edits: dict,
                       total_new: object) -> None:
        """Koreksi hari tersimpan ke Excel + ctx.df diupdate oleh pop-up.

        Tugas view: update MODEL df (display copy) utk baris ini + emit
        dataChanged supaya tabel re-render sel hari + TOTAL yg berubah.

        Transparan: bila baris tak ketemu di model df (terfilter keluar
        / di-reparent ke jendela layar penuh), LOG + jangan crash — data
        ctx.df sudah benar, re-render berikutnya akan ambil nilai baru.
        Metrik turunan (AVG/MAX/skor anomali) TETAP STALE sampai re-run
        pipeline — itu kontrak yg sudah diumumkan ke user di dialog sukses.
        """
        model = None
        try:
            model = self._table.model() if self._table is not None else None
        except RuntimeError:
            model = None
        if model is None:
            self._ctx.log(
                f"[edit-pop-up] model tabel tak tersedia — skip re-render "
                f"sel. ctx.df sudah diupdate; nilai baru tampak setelah "
                f"refresh tabel berikutnya.")
            return
        mdf = model.dataframe
        if mdf is None or mdf.empty:
            self._ctx.log(
                f"[edit-pop-up] model df kosong — skip re-render sel. "
                f"Refresh tabel berikutnya ambil nilai baru.")
            return
        # v2.19.2 — tampilan GRUP: model df punya __SRC_ROWS (tuple anggota),
        # BUKAN __SRC_ROW tunggal. Cari baris grup yg anggotanya memuat
        # src_row, lalu recomput JUMLAH hari grup dari ctx.df (sum semua
        # anggota — bukan pakai nilai tunggal). Total grup = sum hari grup.
        ctx_df = self._ctx.df
        if (_GRP_SRC_ROWS_COL in mdf.columns
                and ctx_df is not None and SRC_ROW_COL in ctx_df.columns):
            grp_label = None
            for lbl, rows in mdf[_GRP_SRC_ROWS_COL].items():
                if isinstance(rows, tuple) and src_row in rows:
                    grp_label = lbl
                    break
            if grp_label is None:
                self._ctx.log(
                    f"[edit-pop-up] baris __SRC_ROW={src_row} tak tampak di "
                    f"tabel grup (terfilter keluar) — skip re-render. ctx.df "
                    f"sudah diupdate.")
                return
            # Recomput sum hari grup dari ctx.df (anggota via __SRC_ROWS).
            member_rows = list(mdf.at[grp_label, _GRP_SRC_ROWS_COL])
            src_col = ctx_df[SRC_ROW_COL]
            member_mask = src_col.isin(member_rows)
            members = ctx_df[member_mask]
            for day in day_edits:
                if day in mdf.columns and day in members.columns:
                    new_sum = pd.to_numeric(
                        members[day], errors="coerce").fillna(0.0).sum()
                    mdf.at[grp_label, day] = float(new_sum)
                    try:
                        model.notify_column_changed(day)
                    except Exception as exc:  # noqa: BLE001
                        self._ctx.log(
                            f"[edit-pop-up] WARNING: notify_column_changed "
                            f"hari {day} gagal ({exc}).")
            if "TOTAL" in mdf.columns:
                day_cols = [c for c in (str(i) for i in range(1, 32))
                            if c in members.columns]
                new_total = (pd.to_numeric(members[day_cols], errors="coerce")
                             .fillna(0.0).sum().sum() if day_cols
                             else pd.to_numeric(
                                 members.get("TOTAL", pd.Series([0])),
                                 errors="coerce").fillna(0.0).sum())
                mdf.at[grp_label, "TOTAL"] = float(new_total)
                try:
                    model.notify_column_changed("TOTAL")
                except Exception as exc:  # noqa: BLE001
                    self._ctx.log(
                        f"[edit-pop-up] WARNING: notify_column_changed TOTAL "
                        f"gagal ({exc}).")
            return
        # Jalur lama (baris tunggal — tab Hari / Follow Up / fixture tanpa
        # grouping): cari baris via __SRC_ROW langsung.
        if SRC_ROW_COL not in mdf.columns:
            self._ctx.log(
                f"[edit-pop-up] model df tak punya {SRC_ROW_COL}/{_GRP_SRC_ROWS_COL} "
                f"— skip re-render sel. Refresh tabel berikutnya ambil nilai baru.")
            return
        col = mdf[SRC_ROW_COL]
        if not pd.api.types.is_numeric_dtype(col):
            return
        mask = col == src_row
        if not mask.any():
            self._ctx.log(
                f"[edit-pop-up] baris __SRC_ROW={src_row} tak tampak di "
                f"tabel (terfilter keluar) — skip re-render sel. ctx.df "
                f"sudah diupdate.")
            return
        label = mdf.index[mask][0]
        # v2.16.2 FIX: pakai model.notify_column_changed(name) BUKAN manual
        # mdf.at + dataChanged.emit. Sebelumnya: _texts cache model TIDAK
        # di-invalidasi → sel tabel tampilkan nilai LAMA pasca-save.
        # notify_column_changed sync _arr + clear _texts + emit dataChanged
        # utk seluruh kolom (API benar, lihat models.py:531).
        for day, val in day_edits.items():
            if day in mdf.columns:
                mdf.at[label, day] = val
                try:
                    model.notify_column_changed(day)
                except Exception as exc:  # noqa: BLE001 — log, jangan crash
                    self._ctx.log(
                        f"[edit-pop-up] WARNING: notify_column_changed hari "
                        f"{day} gagal ({exc}) — tabel mungkin perlu manual "
                        f"refresh.")
        if total_new is not None and "TOTAL" in mdf.columns:
            mdf.at[label, "TOTAL"] = total_new
            try:
                model.notify_column_changed("TOTAL")
            except Exception as exc:  # noqa: BLE001 — log, jangan crash
                self._ctx.log(
                    f"[edit-pop-up] WARNING: notify_column_changed TOTAL "
                    f"gagal ({exc}) — tabel mungkin perlu manual refresh.")

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
