"""models.py — QAbstractTableModel di atas pandas DataFrame (v2.6.0).

Pengganti ttk.Treeview + _populate_tree (cap 500 baris + _format_cell float
mentah). Keunggulan model/view Qt:
- TANPA cap baris: 25.901 baris di-render virtualized (semua anomali terlihat)
- Sort numeric-aware di DataFrame sumber (NaN di akhir) — klik header
- Pewarnaan baris per severity (BackgroundRole)
- Tooltip sel = teks penuh (kolom panjang tidak pernah 'hilang')
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont

from waste_anomaly.utils import load_config

from .grouping import LASTMONTH_COMBINED_COL
from .shared import fmt_id
from .theme import STATUS_COLORS

# Nama logger mengikuti konvensi app ("waste_anomaly.ui" — lihat
# logging_setup.py dan app.py::_qt_excepthook).
_LOG = logging.getLogger("waste_anomaly.ui")

_NUM_COLS = {"ANOMALY SCORE", "TOTAL", "MAX", "AVG", "HARI MAX", "RANK",
             "Rank", "PEER COUNT", "PEER MEDIAN TOTAL", "PEER MEDIAN MAX",
             "TOTAL / PEER MEDIAN", "MAX / PEER MEDIAN MAX", "MAX / BOM",
             "TOTAL / BOM", "MAX SHARE", "LAST DAY SHARE", "TopTotal",
             "Total_Waste", "Max_Waste", "Persentase", "Cumulative",
             "Jumlah_Barang", "Total_A", "Total_B", "Delta", "Delta %",
             "Waste per Hari", "Hari Aktif",
             "% to BOM", "Rill % to BOM",
             # v2.9.0: kolom bukti hari (tab Hari Mencurigakan)
             "HARI TERSANGKA", "NILAI HARI TERSANGKA", "TIPIKAL CABANG LAIN",
             "N CABANG PEMBANDING", "RASIO VS CABANG LAIN",
             "SHARE HARI TERSANGKA", "Count Hari",
             # v2.10.0: bukti vs bulan lalu + tabel banding periode
             "NILAI BULAN LALU", "TIPIKAL BEBERAPA BULAN", "HARI AKTIF",
             "Total Waste", "Waste per Hari", "Perubahan %",
             # v2.10.2: kolom perubahan tabel Anomali + drill hari
             "BULAN LALU", "PERUBAHAN %", "HARI", "Selisih",
             # v2.19.0: kolom tampilan grup tab Anomali (sampel user —
             # nilai numerik: total bulan lalu & selisih absolut)
             LASTMONTH_COMBINED_COL, "Selisih Bulan Lalu"}

# Kolom rasio (nilai 0..1) yang ditampilkan sebagai PERSEN — v2.8.1.
# '% to BOM' = waste dibanding penjualan kuantiti (BOM = qty terjual);
# nilai non-numerik seperti penanda 'Cek' (tak ada data penjualan)
# diteruskan apa adanya. MAX / BOM, TOTAL / BOM, MAX SHARE, LAST DAY
# SHARE ikut format persen supaya konsisten & terbaca (dulu '0,00').
PCT_COLS = frozenset({
    "% to BOM", "Rill % to BOM", "MAX / BOM", "TOTAL / BOM",
    "MAX SHARE", "LAST DAY SHARE",
    # v2.9.0: porsi hari tersangka dari total bulanan
    "SHARE HARI TERSANGKA",
})

# Kolom rasio "berapa kali lipat" (v2.9.0) — ditampilkan '404×' / '8,5×',
# BUKAN persen dan BUKAN angka mentah (0,0008 tidak terbaca manusia).
# v2.10.0: + RASIO VS BULAN LALU (bukti tanggal-sama bulan sebelumnya).
RATIO_X_COLS = frozenset({"RASIO VS CABANG LAIN", "RASIO VS BULAN LALU"})

# v2.10.2 — kolom DELTA persen bertanda (skala 0-100, konvensi _delta_pct
# period_compare): '+35,5%' / '-12,0%' / '0%'; NaN → 'BARU' (tanpa
# riwayat); None → '' (sengaja kosong, mis. metrik 'Hari Data').
# Dipakai semua tabel banding ('Perubahan %', 'Delta %') + tabel Anomali
# ('PERUBAHAN %') — sebelumnya fmt_cell menampilkan '35,5' polos tanpa
# tanda/persen (permintaan user v2.10.2: persen perubahan jelas terbaca).
DELTA_PCT_COLS = frozenset({"Perubahan %", "PERUBAHAN %", "Delta %"})

# v2.19.0 — kolom GABUNGAN sampel user: nilai sel = total bulan lalu
# (NUMERIK — sort klik-header/SortControl tetap benar), teks tampilan
# "1.969,1 (-30%)" digabung dari companion kolom 'PERUBAHAN %'.
LASTMONTH_DELTA_COL = "PERUBAHAN %"


def fmt_lastmonth_combined(value, delta_pct, ndigits: int = 1) -> str:
    """Format kolom 'TOTAL BULAN LALU & % Selisih' (v2.19.0 — sampel user
    'SAMPEL TAMPILAN BARU.xlsx': '1.969,1 (-30%)').

    value      = total bulan lalu (numerik; NaN/None → '' — grup BARU).
    delta_pct  = PERUBAHAN % skala 0-100 (NaN → tanpa kurung persen).
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    base = fmt_id(f, ndigits)
    if delta_pct is None or delta_pct is pd.NA:
        return base
    try:
        d = float(delta_pct)
    except (TypeError, ValueError):
        return base
    if d != d:  # NaN = tanpa riwayat → tampil angka polos
        return base
    if d == 0:
        return f"{base} (0%)"
    sign = "+" if d > 0 else "-"
    return f"{base} ({sign}{abs(d):.0f}%)"

# ============================================================
# v2.12.0 — FOLLOW UP: konstanta bersama model (kolom ✓ + kunci baris)
# ============================================================
# Nama kolom TIDAK dipakai model langsung (dipasang via setter supaya
# tetap generik) — nilai di sini dipakai view Anomali & Follow Up +
# waste_anomaly.followup (FP_COL/CHECK_COL — sumber tunggal).

# Warna penanda hari mencurigakan di sel tabel (konsisten peta hari
# pop-up detail: merah #fee2e2/#dc2626; amber = amber-100).
_HL_RED_BG = QColor("#fee2e2")
_HL_RED_FG = QColor("#dc2626")
_HL_AMBER_BG = QColor("#fef3c7")

# v2.12.2 — angka MINUS merah GLOBAL (semua tabel: Anomali/Hari/Banding/
# Follow Up/pop-up drill — permintaan user "jika minus kasih warna merah,
# berlaku global"). Aturan level MODEL → satu tempat, semua view.
# Cek murah (isinstance + banding < 0) di jalur ForegroundRole paint —
# hanya sel TERLIHAT yang dipanggil → tak ada dampak perf (diukur jalur
# klik v2.12.1 tetap 14-130 ms). String bertanda minus yang diformat
# dari angka (mis. '-12,0%') otomatis ikut: sumber nilainya float < 0.
_NEG_FG = QColor("#dc2626")

# v2.20.0 — HEATMAP sel (permintaan user: "kolom % to bom diberi warna
# semacam heat map ... diabsolutekan dulu ... tampilkan nilai asli"):
# background sel diwarna dari |nilai| (nilai campur +/-), ramp
# hijau-pucat → kuning → oranye → merah; TEKS tetap nilai asli apa
# adanya (DisplayRole tak tersentuh). Semua stop sengaja MUDA supaya
# teks hitam default tetap kontras (tanpa ForegroundRole khusus).
# Skala = p99 |nilai| kolom (robust — satu outlier ekstrem tak
# memucatkan seluruh kolom; nilai ≥ p99 → merah penuh).
#
# v2.20.1 (permintaan user: "warna heat map lebih sensitif lagi dong
# biar benar-benar beda di kolom Persen to bom") — DUA perubahan supaya
# selaras perbedaan kecil jelas terlihat (dulu nilai 2% vs 10% vs 30%
# sama-sama hijau pucat sebab ramp baru mulai menguning di t=0,35):
#   1. GAMMA curve (pangkat < 1) diterapkan pada t SEBELUM interpolasi:
#      t_eff = t ** _HEAT_GAMMA. Pangkat 0,5 (√t) MENDORONG nilai
#      kecil/menengah ke rentang warna hangat — 2%→hijau-kuning, 10%→
#      kuning, 25%→kuning-emas, 50%→oranye, 100%→merah (dulu semua
#      hijau pucat). Endpoint tak tergeser: t=0→0, t=1→1 (gamma tak
#      mengubah ujung — kontrak _heat_color(0/1) utuh).
#   2. RAMP 5 stop (dulu 4) — rentang warna lebih halus & merata:
#      hijau-pucat → kuning pucat → kuning emas → oranye → merah.
# Skala p99 tetap (robust); gamma + ramp finer = sensitivitas naik
# TANPA memucatkan kolom oleh 1 outlier.
_HEAT_GAMMA = 0.5  # √t — dorong nilai kecil ke rentang warna hangat
_HEAT_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (214, 236, 216)),   # hijau pucat — |nilai| ≈ 0
    (0.25, (253, 235, 170)),   # kuning pucat — nilai kecil mulai nyata
    (0.50, (253, 200, 110)),   # kuning emas — menengah
    (0.75, (250, 160, 95)),    # oranye — menengah-tinggi
    (1.00, (238, 112, 99)),    # merah — |nilai| ≥ p99 kolom
)


def _heat_color(t: float) -> QColor:
    """Warna heatmap untuk intensitas t ∈ [0,1].

    t di-clamp ke [0,1], lalu diterapkan GAMMA (t ** _HEAT_GAMMA) supaya
    nilai kecil/menengah memakai rentang warna hangat lebih banyak
    (v2.20.1 — sensitivitas naik), lalu interpolasi linear antar stop
    _HEAT_STOPS. Endpoint tetap: _heat_color(0)=hijau, _heat_color(1)=
    merah (gamma tak menggeser ujung — 0**γ=0, 1**γ=1)."""
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    t = t ** _HEAT_GAMMA
    for (t0, c0), (t1, c1) in zip(_HEAT_STOPS, _HEAT_STOPS[1:]):
        if t <= t1:
            f = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return QColor(*(int(round(a + (b - a) * f))
                            for a, b in zip(c0, c1)))
    return QColor(*_HEAT_STOPS[-1][1])

# ============================================================
# v2.9.0 — KAMUS ISTILAH (tooltip judul kolom, semua tabel & detail)
# ============================================================
# Permintaan user: "buatkan tool tip biar aku mudah mencerna. Semua
# istilah ya bukan hanya S-1". Hover judul kolom tabel / label metrik
# pop-up detail → penjelasan Bahasa Indonesia awam. Satu sumber untuk
# semua view (Anomali, Hari Mencurigakan, Banding Periode).
#
# v2.13.12 (gel-3 C18): angka ambang kini dibaca dari config AKTIF via
# build_column_tooltips(config) — dulu hardcode di teks ("≥ 8", "≥ 50%",
# "≥ 5×") padahal nilai TH_* / STATUS_* user-editable lewat kartu
# Threshold tab Pipeline (audit C18: tooltip bohong diam-diam begitu
# user mengubah config). COLUMN_TOOLTIPS tetap ada sebagai snapshot
# import-time load_config() — kompatibilitas import lama (test/fixture
# memakai nama modul); view tabel memasang kamus runtime dari
# ctx.config lewat PandasTableModel.set_tooltip_map (gel-3 C3+C9;
# v2.18.5: konsumen kini tabel Anomali & Hari — Scorecard dihapus).


def _th(config: dict | None, key: str, default: float) -> float:
    """v2.13.12 (gel-3 C18): ambil angka ambang dari config dengan
    FALLBACK default engine bila nilai korup (None/string tak terurai/
    NaN) — default = nilai bawaan signals.py/pipeline, bukan teks lama
    yang menempel."""
    try:
        raw = (config or {}).get("thresholds", {}).get(key, default)
        if raw is None:
            return float(default)
        val = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if val != val:  # NaN
        return float(default)
    return val


def _fmt_th(val: float) -> str:
    """Format angka ambang utk teks tooltip: int polos ('8'), float
    koma-ID ('2,5') — konvensi fmt_id (IN-L1)."""
    f = float(val)
    if f == int(f):
        return fmt_id(int(f), 0)
    return fmt_id(f, 1)


def build_column_tooltips(config: dict | None = None) -> dict[str, str]:
    """Kamus tooltip judul kolom dgn angka ambang dari ``config``.

    v2.13.12 (gel-3 C18): satu pabrik untuk kamus global (snapshot
    import-time) DAN kamus per-view runtime (view tabel memakai
    ctx.config aktif). Entri tanpa angka ambang = teks tetap (verbatim
    dari v2.9.0). Kunci kamus TIDAK berubah (dikunci
    test_v290/test_v2100/test_v2102)."""
    # Ambang dari config AKTIF (fallback default engine bila korup).
    pr = _fmt_th(_th(config, "STATUS_PRIORITAS", 8))
    po = _fmt_th(_th(config, "STATUS_POTENSI", 5))
    rv = _fmt_th(_th(config, "STATUS_REVIEW", 3))
    spike = _fmt_th(_th(config, "TH_SPIKE", 3))
    avg_aktif = _fmt_th(_th(config, "TH_MAX_AVG_AKTIF", 2.5))
    med = _fmt_th(_th(config, "TH_MAX_MEDIAN", 3))
    second = _fmt_th(_th(config, "TH_MAX_SECOND", 3))
    share = _fmt_th(_th(config, "TH_MAX_SHARE_WARN", 0.5) * 100)
    last_share = _fmt_th(_th(config, "TH_LAST_SHARE", 0.7) * 100)
    bom_warn = _fmt_th(_th(config, "TH_MAX_BOM_WARN", 0.25) * 100)
    total_bom = _fmt_th(_th(config, "TH_TOTAL_BOM_WARN", 0.5) * 100)
    peer_high = _fmt_th(_th(config, "TH_PEER_HIGH", 3))
    peer_warn = _fmt_th(_th(config, "TH_PEER_WARN", 2))
    hari_peer = _fmt_th(_th(config, "TH_HARI_PEER_RATIO", 5.0))
    hari_hist = _fmt_th(_th(config, "TH_HARI_HIST_RATIO", 3.0))
    chg_high = _fmt_th(_th(config, "TH_CHANGE_HIGH", 50.0))
    chg_stable = _fmt_th(_th(config, "TH_CHANGE_STABLE", 20.0))
    chg_min = _fmt_th(_th(config, "TH_CHANGE_MIN_ABS", 10.0))
    profil_min = int(_th(config, "PROFIL_DAILY_MIN", 20))
    return {
    # --- identitas ---
    "NAMA RESTO": "Kode & nama cabang/outlet yang mencatat data ini.",
    "NAMA BARANG": "Nama item barang.",
    "JENIS": "Jenis catatan: SUSUT, TRIAL, atau WASTE.",
    "KETERANGAN": ("Alasan pencatatan: Alat/Mesin, Cancel Nota, Handling, "
                   "Kualitas, Kualitas Eksternal, Kualitas Internal, Over "
                   "Stock — atau SUSUT/TRIAL bila catatan itu tak punya "
                   "sub-alasan (jenisnya itulah keterangannya)."),
    "SATUAN": "Satuan item (PCS, KG, LTR, ...).",
    "SOURCE DATA": "Asal baris data (sheet sumber).",
    "Status2": "Kosong = tidak ada nilai sama sekali; Isi = ada nilainya.",
    # --- skor & status ---
    "ANOMALY SCORE": "Total poin dari 12 pemeriksaan (maks 19).\nMakin tinggi = makin layak diperiksa duluan.",
    "ANOMALY STATUS": f"Kategori skor:\nPrioritas Tinggi (≥ {pr}) · Potensi Anomali (≥ {po}) · Perlu Review (≥ {rv}) · Normal.",
    "ANOMALY REASONS": "Daftar pemeriksaan yang terpicu (dipisah '|').\nHover chip di pop-up detail untuk arti tiap sinyal.",
    "KATEGORI ANOMALI": "Lonjakan Ekstrem / Dominasi Non-Handling / Normal.",
    "RANGKING WASTE": "Peringkat item ini di antara cabang (Top 1-3 — total dan/atau % BOM).",
    # --- statistik harian ---
    "TOTAL": "Jumlah waste sebulan (hari 1-31 dijumlahkan).",
    "MAX": "Nilai waste terbesar dalam SATU hari.",
    "AVG": "Rata-rata per hari (TOTAL ÷ jumlah hari periode).",
    "AVG AKTIF": "Rata-rata hanya dari hari yang ADA wastenya (> 0) —\nhari kosong tidak menarik rata-rata turun.",
    "MEDIAN AKTIF": "Nilai tengah dari hari yang ada wastenya —\ntahan terhadap 1 hari ekstrem (lebih adil dari rata-rata).",
    "SECOND MAX": "Nilai terbesar KEDUA.",
    "HARI MAX": "Tanggal (1-31) nilai terbesar terjadi.",
    "Count Hari": "Banyaknya hari dengan waste > 0.",
    "NILAI HARI TERAKHIR": "Nilai waste di hari terakhir periode.",
    # --- rasio harian ---
    "MAX / AVG": f"Berapa kali lipat nilai terbesar vs rata-rata (≥ {spike}× = lonjakan).",
    "MAX / AVG AKTIF": f"Nilai terbesar vs rata-rata hari aktif (≥ {avg_aktif}× = mencurigakan).",
    "MAX / MEDIAN AKTIF": f"Nilai terbesar vs nilai tengah (≥ {med}× = mencurigakan).",
    "MAX / SECOND MAX": f"Nilai terbesar vs terbesar kedua (≥ {second}× = puncak menjulang sendirian).",
    "MAX SHARE": f"Porsi nilai terbesar dari TOTAL sebulan (≥ {share}% = waste terpusat di 1 hari).",
    "LAST DAY SHARE": f"Porsi hari TERAKHIR dari total (≥ {last_share}% = menumpuk di akhir bulan — cek input).",
    "SINGLE DAY": "YES = waste hanya terjadi 1 hari sebulan.",
    "SCALE SIGNAL": "YES = nilai ~10×/100×/1000× nilai tengah sendiri —\npola khas salah ketik digit tambahan (7 → 70 → 700).",
    # --- BOM (penjualan) ---
    "TOTAL BOM": "Qty PENJUALAN item sebulan (pembanding — bukan waste).\nBOM = penjualan kuantiti.",
    "% to BOM": "Waste vs penjualan. 5% = waste 5 dari 100 terjual.\n'Cek' = tidak ada data penjualan.",
    "Rill % to BOM": "Sama seperti % to BOM (versi tanpa penanda 'Cek').",
    "MAX / BOM": f"Nilai terbesar SEHARI vs penjualan SEBULAN (≥ {bom_warn}% = tinggi).",
    "TOTAL / BOM": f"Total waste sebulan vs penjualan (≥ {total_bom}% = tinggi).",
    # --- peer (cabang lain) ---
    "PEER COUNT": "Banyak cabang lain yang juga mencatat item ini (pembanding).",
    "PEER MEDIAN TOTAL": "Nilai tengah TOTAL item ini di cabang lain.",
    "PEER MEDIAN MAX": "Nilai tengah puncak-harian item ini di cabang lain.",
    "TOTAL / PEER MEDIAN": f"Total kita vs nilai tengah cabang lain (≥ {peer_high}× = jauh di atas).",
    "MAX / PEER MEDIAN MAX": f"Puncak kita vs nilai tengah puncak cabang lain (≥ {peer_warn}× = jauh di atas).",
    # --- hari tersangka (v2.9.0) ---
    "HARI TERSANGKA": "Tanggal (1-31) angka mencurigakan berada —\nhari dengan nilai terbesar baris ini.",
    "NILAI HARI TERSANGKA": "Nilai waste pada hari tersangka.",
    "TIPIKAL CABANG LAIN": "Nilai tengah item SAMA di hari SAMA pada cabang lain —\nangka wajarnya hari itu.",
    "N CABANG PEMBANDING": "Banyak cabang lain yang jadi pembanding di hari itu.",
    "RASIO VS CABANG LAIN": f"Berapa kali lipat nilai kita vs cabang lain di hari yang sama.\n≥ {hari_peer}× = mencurigakan.",
    "SHARE HARI TERSANGKA": f"Porsi hari tersangka dari total bulanan (≥ {share}% = terpusat).",
    "BUKTI HARI": "YES = ada ≥ 1 bukti kuat hari itu mencurigakan.\nLihat ALASAN HARI untuk rinciannya.",
    "ALASAN HARI": "Ringkasan bukti hari tersangka dalam satu kalimat.",
    # --- bukti vs bulan lalu (v2.10.0) ---
    "NILAI BULAN LALU": "Nilai item yang sama di cabang yang sama pada\nTANGGAL yang sama, bulan pembanding sebelumnya\n(jumlah semua alasan) — kebiasaan bulan lalu.",
    "RASIO VS BULAN LALU": f"Berapa kali lipat nilai hari tersangka vs\ntanggal yang sama bulan lalu. ≥ {hari_hist}× = jauh di atas\nkebiasaan bulan sebelumnya.",
    "TIPIKAL BEBERAPA BULAN": "Nilai tengah tanggal yang sama dari ≥ 2\nbulan pembanding (butuh beberapa file bulan lalu).",
    # --- profil & kelebihan (v2.13.0) ---
    "PROFIL": (f"Pola waktu waste baris ini:\nTiap Hari = hampir setiap hari ada waste (masalah proses/kronis) ·\n"
               f"Kadang = 2-{max(profil_min - 1, 2)} hari sebulan · Sekali Ini = 1 hari saja (kejadian\n"
               "tunggal — kandidat salah input).\n'— Baru' = pasangan cabang×item tidak ada/nol di bulan pembanding."),
    "KELEBIHAN": "TOTAL sebulan dikurangi tipikal (nilai tengah) cabang lain\npada item yang sama (hanya cabang yang memang punya waste).\nPlus = lebih boros dari tipikal; minus = lebih hemat.\nKosong = pembanding kurang (< 3 cabang lain ber-waste).",
    "PEER MEDIAN (AKTIF)": "Nilai tengah TOTAL item ini di cabang lain yang\nmemang punya waste — baris cabang nol tidak ikut (tidak menarik\ntipikal turun).",
    "PEER AKTIF": "Banyak cabang lain yang punya waste pada item yang sama\n(dipakai menghitung KELEBIHAN).",
    # --- banding periode ---
    "Hari Data": "Banyak hari berdata pada periode itu.",
    "Hari Aktif": "Banyak hari dengan waste > 0.",
    "Total_A": "Total periode A (run sekarang).",
    "Total_B": "Total periode B (pembanding).",
    "Delta": "Selisih (B − A).",
    "Delta %": "Perubahan relatif vs A.",
    # --- banding periode v2.10.0 (kuantiti multi-file) ---
    "Bulan Ini": "Nilai bulan berjalan (hasil run pipeline saat ini).",
    "Pembanding": "Nilai bulan pembanding yang dipilih (bulan lalu / tipikal).\nKosong = item tidak ada di bulan pembanding.",
    "Selisih": "Bulan ini dikurangi pembanding.\nMinus = turun, plus = naik.",
    "Perubahan %": "Naik/turun relatif vs pembanding (mis. +28% = 1,28×).\n'BARU' = pembandingnya 0/tidak ada (item baru).",
    "Metrik": "Nama ukuran yang dibandingkan.",
    # --- v2.10.2: kolom perubahan tabel Anomali + drill-down hari ---
    "BULAN LALU": ("Total baris yang PERSIS sama (cabang+item+jenis+keterangan) "
                   "di bulan pembanding — bulan yang dipilih combo tab "
                   "'Banding Periode'.\nPencocokan nama abaikan besar/kecil "
                   "huruf & spasi.\nKosong = belum ada di bulan lalu (BARU)."),
    "PERUBAHAN %": ("(TOTAL − BULAN LALU) ÷ BULAN LALU × 100.\n"
                    "'BARU' = tidak ada riwayat bulan lalu."),
    "PERUBAHAN": (f"(Kategori perubahan vs bulan lalu — memisahkan LONJAKAN BARU "
                  f"(Naik Tinggi: kandidat salah input / kejadian baru) dari "
                  f"WASTE KRONIS (Stabil: sudah tinggi tiap bulan — masalah "
                  f"proses, bukan salah ketik).\nAmbang aktif: Naik Tinggi ≥ {chg_high}%"
                  f" · Stabil ≤ {chg_stable}% · minimum {chg_min} satuan agar "
                  "bermakna (anti derau).\nBisa diatur di config.json "
                  "(TH_CHANGE_HIGH / STABLE / MIN_ABS)."),
    "HARI": ("Tanggal 1-31 (pop-up rincian per hari).\n"
             "Selisih = bulan ini − pembanding tanggal sama."),
    # --- v2.19.0: tampilan grup tab Anomali (sampel user) ---
    "SOURCE DATA GABUNGAN": ("Semua asal data baris gabungan ini (satu baris "
                             "per item×cabang — semua alasan/KETERANGAN "
                             "digabung; klik-ganda utk rincian per baris di "
                             "pop-up detail)."),
    LASTMONTH_COMBINED_COL: ("Total bulan lalu + persen selisih vs bulan ini "
                             "dalam satu sel — '1.969,1 (-30%)' = bulan lalu "
                             "1.969,1 dan bulan ini turun 30%.\nKosong = "
                             "grup belum ada di bulan pembanding (BARU).\n"
                             "Sumber pembanding mengikuti combo tab 'Banding "
                             "Periode'."),
    "Selisih Bulan Lalu": ("TOTAL bulan ini dikurangi total bulan lalu "
                           "(grup item×cabang yang sama).\nPlus = naik, "
                           "minus = turun."),
    }


# Snapshot import-time (kompatibilitas import lama; kontrak test lama
# `COLUMN_TOOLTIPS.get(col)` tetap terpenuhi — angka dari config saat
# modul pertama kali dimuat, sama seperti ctx aplikasi startup).
COLUMN_TOOLTIPS: dict[str, str] = build_column_tooltips(load_config())


def fmt_cell(value, ndigits: int = 2) -> str:
    """Format sel untuk tampilan — konvensi Indonesia (IN-L1).

    Angka float dengan pecahan → fmt_id(x, ndigits); integer → fmt_id(x, 0);
    NaN/None/pd.NA/NaT → ''; teks → str apa adanya.

    v2.7.0 (V26-M1/L2): integer/float numpy (np.int64, np.float32, ...) kini
    terformat seperti int/float python (np.int64 sebelumnya lolos ke str()
    tanpa pemisah ribuan + rata kiri). pd.NA/NaT dicek DULU —
    ``pd.NA != pd.NA`` menghasilkan pd.NA (truthy-ambiguous), bukan False.
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return fmt_id(int(value), 0)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if f == int(f) and abs(f) < 1e15:
            return fmt_id(f, 0)
        return fmt_id(f, ndigits)
    return str(value)


def fmt_ratio_x(value, ndigits: int = 1) -> str:
    """Format rasio "berapa kali lipat" gaya Indonesia (v2.9.0).

    Contoh: fmt_ratio_x(404.0) → '404×'; fmt_ratio_x(8.5) → '8,5×'.
    NaN/None → '' (konvensi sama dengan fmt_cell/fmt_pct).
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    if f >= 10:
        return f"{f:,.0f}".replace(",", ".") + "×"
    return f"{f:,.{ndigits}f}".replace(".", ",") + "×"


def fmt_pct(value, ndigits: int = 2) -> str:
    """Format rasio 0..1 sebagai persen gaya Indonesia (v2.8.1).

    Contoh: fmt_pct(0.01335) → '1,34%'; fmt_pct(0.000914) → '0,09%'.
    Penanda non-numerik ('Cek' = tak ada data penjualan/BOM) diteruskan
    apa adanya; NaN/None → '' (konvensi sama dengan fmt_cell).
    """
    if (value is None or value is pd.NA or value is pd.NaT
            or (isinstance(value, (float, np.floating))
                and math.isnan(float(value)))):
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return ""
    s = f"{f * 100:,.{ndigits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + "%"


def fmt_delta_pct(value, ndigits: int = 1) -> str:
    """Format DELTA persen BERTANDA, skala 0-100 (v2.10.2).

    Konvensi _delta_pct (period_compare): (new−old)÷old×100.
    Contoh: 35.5 → '+35,5%'; -12.0 → '-12,0%'; 0 → '0%'.
    NaN → 'BARU' (pembanding 0/tak ada — item baru); None/pd.NA → ''
    (kosong SENGAJA, mis. kolom Perubahan % metrik 'Hari Data');
    teks non-numerik diteruskan apa adanya.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN = tanpa riwayat pembanding
        return "BARU"
    s = f"{abs(f):,.{ndigits}f}".replace(",", "X").replace(".", ",").replace(
        "X", ".")
    if f > 0:
        return "+" + s + "%"
    if f < 0:
        return "-" + s + "%"
    return "0%"


class PandasTableModel(QAbstractTableModel):
    """Model tabel generik untuk DataFrame (sort + severity tint + tooltip).

    v2.12.0 — tiga mekanisme opsional (opt-in, default MATI — perilaku
    view lain tak berubah):
    - ``set_check_column(name)``: kolom bool menjadi centang in-place
      (flags ItemIsUserCheckable + CheckStateRole + setData flip →
      sinyal ``check_toggled(row, checked)``). Toggle = 1 sel repaint
      (dataChanged index tunggal) — BUKAN render ulang tabel.
    - ``set_row_key_column(name)`` + ``set_highlights(red, amber)``:
      penanda warna sel per (kunci-baris, kolom) — STABIL melewati sort
      (kunci ikut travel di kolomnya, bukan posisi baris).
    - ``notify_column_changed(name)``: dataChanged satu kolom penuh —
      sinkronisasi nilai ✓ in-place pasca perubahan state eksternal
      (bulk/toggle dari tab lain) TANPA reset model (cache fit DataTable
      tetap kena).
    """

    check_toggled = Signal(int, bool)

    def __init__(self, df: pd.DataFrame | None = None, parent=None) -> None:
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._ndigits = 2
        # v2.9.0 (perf): cache teks DisplayRole per (row, col) — fmt_cell/
        # fmt_pct dibangun SEKALI lalu dipakai ulang oleh auto-fit kolom,
        # pengukuran tinggi baris, dan paint (diukur: 30-40% waktu render
        # tabel habis di pemformatan string yang sama berulang-ulang).
        # Di-invalidasi set_dataframe & sort (baris berganti isi).
        self._texts: dict[tuple[int, int], str] = {}
        # v2.12.1 (perf): snapshot numpy 2D (dtype object) dari _df —
        # data()/_row_tint/_row_key membaca sel via arr[r, c] (~0,1 µs)
        # BUKAN pandas iat (~24 µs/sel: _get_value → _ixs → boxing).
        # Diukur profil data asli: pengukuran fit tabel Follow Up
        # 797×41 memanggil data() 42.927× = 1,7 dtk habis di iat;
        # snapshot dibangun sekali (~2-4 ms per set_dataframe/sort) dan
        # disinkronkan saat nilai dimutasi in-place (notify_column_changed
        # / setData ✓). Fallback iat bila snapshot gagal dibangun.
        self._arr: np.ndarray | None = None
        self._status_idx: int | None = None
        # v2.19.0: posisi kolom companion formatter gabungan (malas).
        self._companion_idx: dict[str, int] = {}
        self._rebuild_snapshot()
        # v2.12.0: konfigurasi follow-up (opt-in).
        self._check_col: str | None = None
        self._fp_col: str | None = None
        self._fp_idx: int | None = None
        self._hl_red: set[tuple[str, str]] = set()
        self._hl_amber: set[tuple[str, str]] = set()
        self._hl_cols: set[str] = set()
        # v2.12.2: alias JUDUL kolom (tampilan) — data/sort/record tetap
        # nama KANONIK (dipakai tab Banding: 'Pembanding' → nama bulan;
        # kontrak test lama `dataframe['Pembanding']` tak tersentuh).
        self._header_map: dict[str, str] = {}
        # v2.13.12 (gel-3 C3+C9): kamus tooltip PER-VIEW menimpa kamus
        # global (kolom 'HARI' = tanggal di kartu sistemik vs tanggal
        # 1-31 di tabel Anomali — satu nama, banyak makna per tabel).
        # Hanya ToolTipRole header yang membaca ini; kontrak lain
        # (set_header_map alias judul, data, sort) tak tersentuh.
        self._tooltip_map: dict[str, str] = {}
        # v2.19.3 — baris PEMISAH grup (layout SAMPEL TAMPILAN BARU di tab
        # Anomali): kolom __SEP=True → baris kosong visual. Opt-in via
        # set_separator_column; data()/flags()/record()/sort() separator-aware.
        self._sep_col: str | None = None
        # v2.21.0 — default kunci pemisah ikut grouping SEP_KEYS baru
        # (KETERANGAN, NAMA BARANG); pemanggil eksplisit (view Anomali)
        # mem-pass SEP_KEYS — default ini murni nilai awal konsisten.
        self._sep_group_keys: tuple[str, ...] = ("KETERANGAN", "NAMA BARANG")
        # v2.20.0 — heatmap kolom (opt-in, default MATI — view lain tak
        # terdampak): background sel dari |nilai|, skala p99 kolom.
        self._heat_col: str | None = None
        self._heat_scale: float = 0.0

    def _rebuild_snapshot(self) -> None:
        """Bangun ulang snapshot numpy dari _df (setelah set/reset/sort)."""
        try:
            self._arr = (self._df.to_numpy(dtype=object)
                         if self._df is not None and self._df.shape[1] > 0
                         else None)
            self._cols = list(self._df.columns)
        except Exception:  # noqa: BLE001 — df eksotis → fallback iat
            self._arr = None
            self._cols = list(self._df.columns) if self._df is not None else []

    def _cell_value(self, row: int, col: int):
        """Nilai mentah sel dari SNAPSHOT numpy (bulk path — v2.12.1).

        Hanya untuk jalur pengukuran massal (text_at); data() Qt tetap
        membaca pandas iat supaya mutasi df langsung tetap terlihat."""
        if self._arr is not None and self._arr.ndim == 2:
            try:
                return self._arr[row, col]
            except IndexError:
                return None
        try:
            return self._df.iat[row, col]
        except Exception:  # noqa: BLE001 — di luar bentuk
            return None

    def text_at(self, row: int, col: int) -> str:
        """Teks DisplayRole satu sel — JALUR BULK pengukuran (v2.12.1).

        Dipakai DataTable._auto_columns/_refit_rows: profil data asli
        membuktikan 42.927 panggilan data() (797×41 + sampel lebar) = 1,7 dtk
        habis di pandas iat per sel; snapshot numpy + cache _texts memotong
        ~20×. Jalur Qt data() TIDAK diganti (paint hanya menyentuh sel
        terlihat ~ratusan — iat di sana murah dan tetap hidup terhadap
        mutasi langsung). Kolom centang → teks kosong (konsisten data())."""
        if not (0 <= col < len(self._cols)) or not (0 <= row < len(self._df)):
            return ""
        if self._check_col is not None and self._cols[col] == self._check_col:
            return ""
        return self._cell_text(row, col, self._cols[col],
                               self._cell_value(row, col))

    # ------------------------------------------------------------
    # API
    # ------------------------------------------------------------
    def set_dataframe(self, df: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self._texts = {}
        self._fp_idx = None  # v2.12.0: posisi kolom kunci bisa bergeser
        self._status_idx = None  # v2.12.1
        self._companion_idx = {}  # v2.19.0: posisi companion ikut bergeser
        self._rebuild_snapshot()
        self.endResetModel()
        self._recompute_heat_scale()  # v2.20.0: nilai kolom berganti

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._df

    def record(self, row: int) -> pd.Series | None:
        """Baris penuh (pd.Series) pada posisi tampilan saat ini.

        v2.19.3 — baris PEMISAH grup → None (bukan data; caller memperlakukan
        None = tak ada baris → pop-up/klik/follow-up no-op)."""
        if self._sep_row(row):
            return None
        if 0 <= row < len(self._df):
            return self._df.iloc[row]
        return None

    # ------------------------------------------------------------
    # v2.12.0 — konfigurasi follow-up (opt-in)
    # ------------------------------------------------------------
    def set_check_column(self, name: str | None) -> None:
        """Pasang kolom centang (bool). None = matikan."""
        self._check_col = name

    def set_row_key_column(self, name: str | None) -> None:
        """Pasang kolom kunci baris (mis. '__FP') — dasar penanda sel."""
        self._fp_col = name
        self._fp_idx = None

    # ------------------------------------------------------------
    # v2.19.3 — baris pemisah grup (layout SAMPEL TAMPILAN BARU)
    # ------------------------------------------------------------
    def set_separator_column(
        self, name: str | None,
        group_keys: tuple[str, ...] = ("KETERANGAN", "NAMA BARANG"),
    ) -> None:
        """Pasang kolom penanda baris pemisah grup (mis. '__SEP').

        Baris dgn nilai bool True di kolom tsb = baris KOSONG pemisah
        antar grup item (layout sampel user): render kosong, tak
        selectable, record()=None, tak masuk funnel. ``group_keys`` =
        kolom identitas grup — dipakai sort() utk menyisip ulang pemisah
        saat user sort by kolom grup (pemisah hanya bermakna bila baris
        grup bertetangga). None = matikan (default — view lain tak
        terdampak).
        """
        self._sep_col = name
        self._sep_group_keys = tuple(group_keys)

    def _sep_row(self, row: int) -> bool:
        """Baris `row` = baris pemisah grup? (guard murah — snapshot numpy)"""
        if (self._sep_col is None or row < 0 or row >= len(self._df)
                or self._sep_col not in self._df.columns):
            return False
        try:
            c = self._df.columns.get_loc(self._sep_col)
            v = (self._arr[row, c] if self._arr is not None
                 and self._arr.shape == self._df.shape
                 else self._df.iat[row, c])
        except Exception:  # noqa: BLE001 — bentuk eksotis: bukan pemisah
            return False
        return isinstance(v, bool) and v

    def set_highlights(self, red: set[tuple[str, str]],
                       amber: set[tuple[str, str]]) -> None:
        """Penanda warna sel per (kunci-baris, nama-kolom).

        red = (bg merah + font merah tebal); amber = bg amber. Kunci
        berbasis nilai (bukan posisi) → tetap benar setelah sort."""
        self._hl_red = set(red or set())
        self._hl_amber = set(amber or set())
        self._hl_cols = ({c for _k, c in self._hl_red}
                         | {c for _k, c in self._hl_amber})

    def set_header_map(self, mapping: dict[str, str] | None) -> None:
        """Alias judul kolom TAMPILAN (v2.12.2 — permintaan user: kata
        'Pembanding' diganti NAMA BULAN di tabel banding).

        Hanya headerData(DisplayRole) yang memakai alias — data sel,
        sort, record, dan ``dataframe`` tetap nama kanonik (kontrak
        konsumen/test tak berubah). None/{} = matikan."""
        self._header_map = dict(mapping or {})

    def set_tooltip_map(self, mapping: dict[str, str] | None) -> None:
        """Kamus tooltip judul kolom PER-VIEW menimpa kamus global
        (v2.13.12 gel-3 C3+C9 — audit: kolom "HARI" bisa berarti
        tanggal 1-31 di tabel Anomali atau tanggal serentak di kartu
        sistemik — satu nama, banyak makna per tabel).

        Hanya ToolTipRole headerData yang membaca peta ini (dicari lebih
        dulu sebelum COLUMN_TOOLTIPS global); kontrak lain — alias judul
        (set_header_map), data sel, sort, record — tak tersentuh.
        None/{} = kembali ke kamus global."""
        self._tooltip_map = dict(mapping or {})

    def set_heat_column(self, name: str | None) -> None:
        """v2.20.0 — pasang kolom HEATMAP background (None = matikan).

        Background sel kolom ``name`` diwarna dari |nilai|
        (nilai campur +/- — permintaan user: "diabsolutekan dulu")
        dengan skala p99 |nilai| kolom; TEKS sel TETAP nilai asli
        (DisplayRole/ForegroundRole tak tersentuh — minus tetap merah
        global). Non-numerik (mis. 'Cek') → tanpa warna. Menimpa tint
        baris status utk kolom ini saja. Opt-in: hanya tab Anomali
        ('% to BOM') yang memasang; tabel lain tak terdampak."""
        self._heat_col = name
        self._recompute_heat_scale()

    def _recompute_heat_scale(self) -> None:
        """Skala heatmap = p99 |nilai numerik| kolom heat (v2.20.0).

        p99 (bukan max): satu outlier ekstrem (mis. % to BOM 77× karena
        BOM kecil) tak memucatkan seluruh kolom — 99% nilai tetap
        memakai rentang warna penuh. Kolom kosong/non-numerik → 0
        (heatmap mati otomatis)."""
        self._heat_scale = 0.0
        if (self._heat_col is None or self._df is None
                or self._heat_col not in self._df.columns):
            return
        try:
            s = pd.to_numeric(self._df[self._heat_col],
                              errors="coerce").dropna().abs()
            if len(s):
                self._heat_scale = float(s.quantile(0.99))
        except Exception:  # noqa: BLE001 — kolom eksotis → heatmap mati
            self._heat_scale = 0.0

    def notify_column_changed(self, name: str) -> None:
        """dataChanged SATU kolom penuh (nilai berubah in-place).

        v2.12.1: kolom di snapshot numpy disinkronkan dari df (view memutasi
        ``m.dataframe[name] = ...`` lalu memanggil ini — tanpa sinkronisasi
        snapshot memegang nilai LAMA) + teks sel kolom itu dibatalkan."""
        if name in self._df.columns and len(self._df) > 0:
            col = self._df.columns.get_loc(name)
            if self._arr is not None and self._arr.shape == self._df.shape:
                try:
                    self._arr[:, col] = self._df[name].to_numpy()
                except Exception:  # noqa: BLE001
                    self._rebuild_snapshot()
            elif self._arr is not None:
                self._rebuild_snapshot()
            self._texts = {k: v for k, v in self._texts.items()
                           if k[1] != col}
            self.dataChanged.emit(self.index(0, col),
                                  self.index(len(self._df) - 1, col))

    def _row_key(self, row: int) -> str | None:
        """Nilai kolom kunci baris (posisi dicari malas + diverifikasi)."""
        if self._fp_col is None or not (0 <= row < len(self._df)):
            return None
        if (self._fp_idx is None
                or self._fp_idx >= len(self._df.columns)
                or self._df.columns[self._fp_idx] != self._fp_col):
            try:
                self._fp_idx = self._df.columns.get_loc(self._fp_col)
            except KeyError:
                return None
        try:
            return str(self._df.iat[row, self._fp_idx])
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------
    # Qt model contract
    # ------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._df.columns):
                name = str(self._df.columns[section])
                if role == Qt.DisplayRole:
                    # v2.12.2: alias tampilan (mis. 'Pembanding' → 'Juli
                    # 2026') — data tetap kanonik.
                    return self._header_map.get(name, name)
                if role == Qt.ToolTipRole:
                    # v2.9.0: kamus istilah — hover judul kolom menjelaskan
                    # artinya Bahasa awam (permintaan user: tooltip SEMUA
                    # istilah, bukan cuma S-1). Kolom tanpa kamus → nama.
                    # v2.13.12 (gel-3 C3+C9): kamus PER-VIEW menimpa global
                    # (kolom sama beda makna antar tabel — 'HARI' kalender
                    # vs sistemik vs tanggal Anomali).
                    tip = self._tooltip_map.get(name)
                    if tip is None:
                        tip = COLUMN_TOOLTIPS.get(name, name)
                    return tip
        if role == Qt.FontRole and orientation == Qt.Horizontal:
            f = QFont()
            f.setBold(True)
            return f
        return None

    def _cell_text(self, row: int, col: int, col_name: str, value) -> str:
        """Teks tampilan satu sel — memo per (row, col) (v2.9.0 perf)."""
        key = (row, col)
        text = self._texts.get(key)
        if text is None:
            if col_name == LASTMONTH_COMBINED_COL:
                # v2.19.0 — kolom gabungan sampel user: nilai numerik =
                # total bulan lalu, teks = '1.969,1 (-30%)' dari companion
                # PERUBAHAN % baris yang sama (sort tetap numerik).
                text = fmt_lastmonth_combined(
                    value, self._companion_value(row, LASTMONTH_DELTA_COL))
            elif col_name in PCT_COLS:
                text = fmt_pct(value)
            elif col_name in DELTA_PCT_COLS:
                text = fmt_delta_pct(value)
            elif col_name in RATIO_X_COLS:
                text = fmt_ratio_x(value)
            else:
                text = fmt_cell(value, self._ndigits)
            self._texts[key] = text
        return text

    def _companion_value(self, row: int, col_name: str):
        """Nilai kolom pendamping pada baris tampilan row (v2.19.0).

        Dipakai formatter kolom gabungan TOTAL BULAN LALU & % Selisih —
        membaca PERUBAHAN % baris yang sama. Posisi kolom dicari malas
        + diverifikasi (pola _status_idx); kolom absen → None."""
        if col_name not in self._df.columns or not (0 <= row < len(self._df)):
            return None
        idx = self._companion_idx.get(col_name)
        if (idx is None or idx >= len(self._df.columns)
                or self._df.columns[idx] != col_name):
            try:
                idx = self._df.columns.get_loc(col_name)
            except KeyError:
                return None
            self._companion_idx[col_name] = idx
        try:
            return self._df.iat[row, idx]
        except Exception:  # noqa: BLE001 — di luar bentuk
            return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if (not index.isValid() or not (0 <= index.row() < len(self._df))
                or not (0 <= index.column() < len(self._df.columns))):
            return None
        row, col = index.row(), index.column()
        col_name = self._df.columns[col]
        # v2.19.3 — baris PEMISAH grup (layout sampel user): baris kosong
        # murni visual — DisplayRole "", tanpa centang/tooltip/warna/judul
        # alignment (semua role lain None → default paint polos).
        if self._sep_row(row):
            if role in (Qt.DisplayRole, Qt.EditRole):
                return ""
            return None
        try:
            value = self._df.iat[row, col]  # live-view (mutasi df terlihat)
        except Exception:  # noqa: BLE001
            return None

        # v2.12.0 — kolom centang: CheckState dari nilai bool; teks kosong
        # (bukan 'True'/'False'); tooltip menjelaskan aksi.
        if col_name == self._check_col and self._check_col is not None:
            if role == Qt.CheckStateRole:
                return (Qt.CheckState.Checked if bool(value)
                        else Qt.CheckState.Unchecked)
            if role in (Qt.DisplayRole, Qt.EditRole):
                return ""
            if role == Qt.ToolTipRole:
                return ("Centang = masukkan baris ini ke daftar Follow Up "
                        "(tab Follow Up). Lepas centang = keluarkan.")
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None

        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._cell_text(row, col, col_name, value)
        if role == Qt.ToolTipRole:
            text = self._cell_text(row, col, col_name, value)
            return text if len(str(text)) > 18 else None
        if role == Qt.TextAlignmentRole:
            # V26-M1: numpy int/float juga rata kanan (np.int64 dulunya
            # lolos ke rata kiri karena bukan subclass int/float python).
            if col_name in _NUM_COLS or isinstance(
                    value, (int, float, np.integer, np.floating)):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.BackgroundRole:
            # v2.12.0 — penanda hari mencurigakan (kunci-baris, kolom):
            # merah (tersangka) > amber (lonjakan) > tint baris status.
            if self._hl_cols and col_name in self._hl_cols:
                fp = self._row_key(row)
                if fp is not None:
                    if (fp, col_name) in self._hl_red:
                        return _HL_RED_BG
                    if (fp, col_name) in self._hl_amber:
                        return _HL_AMBER_BG
            # v2.20.0 — heatmap kolom (mis. '% to BOM' tab Anomali):
            # background dari |nilai| (campur +/- → absolut dulu —
            # permintaan user), skala p99 kolom, menimpa tint baris
            # status utk KOLOM INI saja. Teks tetap nilai asli.
            if (self._heat_col is not None and col_name == self._heat_col
                    and self._heat_scale > 0
                    and isinstance(value, (int, float, np.integer,
                                           np.floating))
                    and not isinstance(value, bool)):
                t = abs(float(value)) / self._heat_scale
                return _heat_color(min(t, 1.0))
            return self._row_tint(row)
        if role == Qt.ForegroundRole:
            # Prioritas 1 — penanda hari mencurigakan (merah + tebal).
            if self._hl_cols and col_name in self._hl_cols:
                fp = self._row_key(row)
                if fp is not None and (fp, col_name) in self._hl_red:
                    return _HL_RED_FG
            # v2.12.2 — prioritas 2: angka NEGATIF merah global (semua
            # tabel): Selisih/Perubahan % negatif di tab Banding, BULAN
            # LALU/PERUBAH turun di tab Anomali, dst. bool dikecualikan
            # (kolom ✓ — False == 0 tapi bukan "minus").
            if (isinstance(value, (int, float, np.integer, np.floating))
                    and not isinstance(value, bool) and value < 0):
                return _NEG_FG
            return None
        if role == Qt.FontRole:
            if col_name == "ANOMALY SCORE":
                f = QFont()
                f.setBold(True)
                return f
            # v2.12.0 — sel hari tersangka: tebal (konsisten peta hari).
            if (self._hl_cols and col_name in self._hl_cols
                    and self._fp_col is not None):
                fp = self._row_key(row)
                if fp is not None and (fp, col_name) in self._hl_red:
                    f = QFont()
                    f.setBold(True)
                    return f
            return None
        return None

    # ------------------------------------------------------------
    # v2.12.0 — centang in-place (delegate klik → CheckStateRole)
    # ------------------------------------------------------------
    def flags(self, index: QModelIndex):
        # v2.19.3 — baris PEMISAH grup: ENABLED saja (tak selectable /
        # checkable) — klik, Enter, klik-ganda tak memicu pop-up detail;
        # fokus keyboard boleh lewat (currentRowChanged di-guard record()).
        if index.isValid() and self._sep_row(index.row()):
            return Qt.ItemFlag.ItemIsEnabled
        base = super().flags(index)
        if (self._check_col is not None and index.isValid()
                and 0 <= index.column() < len(self._df.columns)
                and self._df.columns[index.column()] == self._check_col):
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:  # noqa: N802 — Qt API
        """Toggle centang kolom ✓ (klik mouse — jalur delegate editorEvent,
        bekerja meski tabel read-only/NoEditTriggers).

        Flip nilai bool → dataChanged SATU sel (bukan reset model →
        cache fit/ukuran DataTable tak tersentuh) → sinyal
        check_toggled(row, checked) utk view mengubah state ctx."""
        if (role != Qt.CheckStateRole or self._check_col is None
                or not index.isValid()
                or not (0 <= index.row() < len(self._df))):
            return False
        col_name = self._df.columns[index.column()] \
            if index.column() < len(self._df.columns) else ""
        if col_name != self._check_col:
            return False
        if isinstance(value, bool):
            checked = value
        elif isinstance(value, Qt.CheckState):
            checked = value == Qt.CheckState.Checked
        else:
            # int (2 = Qt.Checked dari delegate versi Qt lama / QVariant).
            # Catatan: int(Qt.CheckState.Checked) TypeError di PySide6 —
            # enum CheckState tak punya __int__ (beda dari ItemDataRole).
            try:
                checked = int(value) == 2
            except (TypeError, ValueError):
                return False
        try:
            self._df.iat[index.row(), index.column()] = bool(checked)
        except Exception:  # noqa: BLE001 — df aneh (readonly view dsb.)
            return False
        if self._arr is not None and self._arr.shape == self._df.shape:
            try:
                self._arr[index.row(), index.column()] = bool(checked)
            except IndexError:
                pass
        self.dataChanged.emit(index, index)
        self.check_toggled.emit(index.row(), bool(checked))
        return True

    def _row_tint(self, row: int) -> QColor | None:
        """Tint baris sesuai ANOMALY STATUS (bila kolom ada)."""
        if "ANOMALY STATUS" in self._df.columns:
            if (self._status_idx is None
                    or self._status_idx >= len(self._df.columns)
                    or self._df.columns[self._status_idx] != "ANOMALY STATUS"):
                self._status_idx = self._df.columns.get_loc("ANOMALY STATUS")
            try:
                status = str(self._df.iat[row, self._status_idx])
            except Exception:  # noqa: BLE001
                return None
            tint = STATUS_COLORS.get(status, (None, None))[1]
            if tint:
                return QColor(tint)
        return None

    # ------------------------------------------------------------
    # SORT — numeric-aware pada df sumber (semantik _sort_df_for_treeview)
    # ------------------------------------------------------------
    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        if column < 0 or column >= len(self._df.columns):
            return
        name = self._df.columns[column]
        ascending = order == Qt.AscendingOrder
        # v2.19.3 — separator-aware: baris pemisah BUKAN data (NaN di semua
        # kolom sort — na_position="last" akan menumpuk mereka di ekor).
        # Buang pemisah → sort data murni → sisip ulang pemisah antar grup
        # HANYA bila kolom sort = kunci grup (pemisah cuma bermakna bila
        # baris grup bertetangga). Sort kolom lain (skor/TOTAL) → pemisah
        # DIBUANG (tabel jadi ter-ranked polos — layout sampel tak relevan).
        base_df = self._df
        sep_mode = (self._sep_col is not None
                    and self._sep_col in self._df.columns)
        if sep_mode:
            try:
                sep_mask = base_df[self._sep_col].map(
                    lambda v: isinstance(v, bool) and v)
                if bool(sep_mask.any()):
                    base_df = base_df[~sep_mask]
            except Exception:  # noqa: BLE001 — anggap tak ada pemisah
                sep_mode = False
        try:
            col = base_df[name]
            numeric = pd.to_numeric(col, errors="coerce")
            if numeric.notna().sum() > 0:
                key = numeric
            else:
                key = col.astype(str).str.lower()
            sorted_df = base_df.assign(_k=key).sort_values(
                "_k", ascending=ascending, na_position="last"
            ).drop(columns="_k")
            if sep_mode and name in self._sep_group_keys:
                # mergesort stable → baris dgn nilai kunci sama tetap
                # bertetangga sesuai urutan grup sebelumnya → pemisah
                # antar grup tetap benar posisinya.
                try:
                    from .grouping import insert_group_separators
                    sorted_df = insert_group_separators(
                        sorted_df, keys=self._sep_group_keys)
                except Exception:  # noqa: BLE001 — pemisah opsional
                    pass
            # v2.19.8 (audit-2 B-9): begin/endResetModel harus try/finally —
            # exception di assign/_rebuild_snapshot antara keduanya
            # meninggalkan model MID-RESET (view terkunci abadi).
            self.beginResetModel()
            try:
                self._df = sorted_df
                self._texts = {}  # urutan baris berganti → cache teks basi
                self._rebuild_snapshot()  # v2.12.1: urutan baris berganti
            finally:
                self.endResetModel()
        except Exception:
            # V26-L3: sort gagal (dtype aneh dsb.) — jangan senyap total,
            # tinggalkan jejak debug utk logs/waste_anomaly.log.
            _LOG.debug("sort kolom '%s' gagal — tabel dibiarkan tak tersort",
                       name, exc_info=True)
            return
