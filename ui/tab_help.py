"""Tab 10 Bantuan: instruksi pakai.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import APP_TITLE
from .shared import APP_VERSION
from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_TEXT_MAIN
from .shared import F_BODY
import tkinter as tk
from tkinter import ttk


class HelpTabMixin:
    """Tab 10 Bantuan: instruksi pakai."""

    def _build_help_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # L12: borderwidth dihapus
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c1.columnconfigure(0, weight=1)
        c1.rowconfigure(0, weight=1)

        txt = tk.Text(c1, wrap="word", relief="flat", bg=C_CARD, fg=C_TEXT_MAIN, font=F_BODY, padx=20, pady=16)
        sb = ttk.Scrollbar(c1, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        help_text = f"""{APP_TITLE} v{APP_VERSION}

=== CARA PAKAI ===

1. Siapkan workbook Excel `DATA_WASTE.xlsx` (struktur 53 kolom standar):
   Workflow: Query data → Olah di Excel → Save as DATA_WASTE.xlsx
   • DATA_WASTE (sheet utama) — data waste harian (kolom 1..31 + NAMA RESTO + NAMA BARANG + JENIS + KETERANGAN + SATUAN + dll)
   • BOM (opsional) — master Bill of Materials (Nomor #, Nama Barang, TOTAL BOM)
   • DATABASE_SATUAN (opsional) — master helper per kategori (NAMA ITEM + 11 kolom kategori)
   Sheet name auto-detect: DATA_WASTE / Sheet1 / REKAP_MENTAH / DATA / dll

2. Tab "Run Pipeline":
   • Browse... → pilih workbook Excel (DATA_WASTE.xlsx Anda)
   • Isi Key Akhir (1..31) — cutoff hari terakhir periode analisa
   • Klik "Mulai Pipeline" (hasil diproses IN-MEMORY, tidak menulis file).
     Selama run, tombol berubah menjadi "⏹ Batalkan Run" — pembatalan
     efektif antar stage / saat pipeline selesai (hasil dibuang).

3. Setelah selesai, tab "Dashboard" otomatis ter-isi:
   • KPI cards di atas (total, prioritas, potensi, waste, cabang)
   • 3 chart interaktif (klik bar untuk filter)
   • Drill-down table dengan sortable columns + status coloring

=== DRILL-DOWN (NEW v2.0) ===

Cara drill-down:
  1. Klik bar/slice di chart interaktif → auto-filter table + re-render chart lain
  2. Pilih dropdown Cabang/Status → filter langsung
  3. Ketik di Search box → filter free-text semua kolom
  4. Active filter chips muncul di atas table (klik chip ATAU × untuk remove)
  5. Double-click baris di table → drill-down ke cabang+item baris itu
  6. Klik header kolom table → sort naik/turun (indikator ▼/▲; kolom
     numerik sort angka, teks sort case-insensitive, NaN selalu di akhir)

Rentang hari (HARI MAX): centang "Aktifkan rentang hari" lalu atur 1–31.
Tanpa centang, semua hari ditampilkan (tidak ada filter).

Contoh workflow analisa:
  - Klik bar "Prioritas Tinggi" → lihat semua baris prioritas
  - Klik bar cabang "RESTO.PWKTAM" → fokus ke cabang itu
  - Klik bar top item "Bawang Putih" → lihat detail per-hari item itu
  - Search "Cancel Nota" → filter semua baris dengan keterangan itu

=== OUTPUT LAPORAN EXCEL — 6 SHEET (v2.4) ===

Pipeline berjalan IN-MEMORY (tidak otomatis menulis file Excel).
Untuk membuat laporan Excel 6 sheet:
  1. Buka tab "📋 Hasil" → klik "💾 Export Laporan Excel…"
  2. Pilih lokasi & nama file — default: Documents, nama disarankan
     Waste_Anomaly_Report_YYYYMMDD_HHMM.xlsx
  3. Sheet yang dihasilkan:
     • Detail             — semua baris (kolom mengikuti M code Final order)
     • Anomali Prioritas  — hanya Prioritas Tinggi + Potensi Anomali
     • Per Cabang         — ringkasan per NAMA RESTO
     • Top Items          — top 20 item by TOTAL waste
     • Pareto Alasan      — group by KETERANGAN + cumulative %
     • Log Run            — timestamp + parameter + log lines
  4. Kalau file sedang dibuka di Excel, akan muncul pesan untuk menutupnya
     dulu lalu ulangi.

Export CSV (tabel ter-filter) tersedia di tab Dashboard — "💾 Export CSV".

=== SHORTCUT KEYBOARD (v2.3.1) ===

• Enter di kolom workbook (tab Run Pipeline) → mulai run / batalkan run
• Enter di kotak Cari (tab Dashboard) → terapkan filter segera
  (tanpa menunggu debounce 300 ms)
• Ctrl+F → pindah ke tab Dashboard + fokus kotak Cari
• Ctrl+R → refresh semua chart (ditolak saat pipeline/export berjalan)
• Scroll wheel (mouse) → gulir tab panjang (Dashboard/Visualisasi/
  Konfigurasi); Treeview/Text menggulir sendiri

=== 12 SINYAL ANOMALI ===

S1  Spike vs AVG                 : MAX/AVG >= 3
S2  MAX vs AVG Aktif             : MAX/AVG_AKTIF >= 2.5 (>= 4 → skor 2)
S3  MAX vs Median Aktif          : MAX/MEDIAN >= 3 (skor 2)
S4  MAX Share                    : MAX/TOTAL >= 0.50 (1) / 0.70 (2)
S5  MAX vs Second Max            : MAX/SECOND_MAX >= 3
S6  MAX / BOM                    : MAX/TOTAL_BOM >= 0.25 (1) / 0.50 (2)
S7  TOTAL / BOM                  : TOTAL/TOTAL_BOM >= 0.50 (1) / 1.00 (2)
S8  Peer MAX                     : MAX/PeerMedMax >= 2 (1) / 3 (2)
S9  Peer TOTAL                   : TOTAL/PeerMedTot >= 3
S10 Single-day event             : Count=1 & (MaxBOM >= 0.10 atau MaxPeer >= 2)
S11 Last Day Share               : LastDay/TOTAL >= 0.70
S12 Scale Signal                 : heuristic rasio (8-12/80-120/800-1200/8000-12000)

Composite Score (max 19):
• >= 8  : Prioritas Tinggi
• >= 5  : Potensi Anomali
• >= 3  : Perlu Review
• else  : Normal

=== TROUBLESHOOTING ===

• "Tidak menemukan sheet untuk 'rekap_mentah'"
  → Pastikan workbook punya sheet DATA_WASTE / Sheet1 / REKAP_MENTAH.
     Atau edit waste_anomaly/config.json → input_sheets untuk tambah nama kandidat.

• "BOM sheet tidak ditemukan"
  → BOM join dilewati; TOTAL BOM jadi None dan sinyal BOM (S6/S7) tidak trigger.
     Tambahkan sheet BOM / MASTER BOM untuk mengaktifkan.

• Tab Dashboard kosong
  → Pastikan sudah run pipeline di tab "Run Pipeline" dulu.

=== KONTAK ===

Source: https://github.com/anandategarch/Waste
Pattern referensi: https://github.com/anandategarch/Inventory-Adjusment
"""
        txt.insert("1.0", help_text)
        txt.configure(state="disabled")



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
