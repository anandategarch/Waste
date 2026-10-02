"""
ui_app.py — Tkinter multi-tab UI untuk Waste Anomaly Detection.

Versi: 1.0.0

Tab:
  1. Run Pipeline  — pilih workbook + Key Akhir + Run + log
  2. Hasil         — preview tabel hasil (Detail + Anomali Prioritas)
  3. Ringkasan     — summary per cabang, top items, pareto
  4. Konfigurasi   — threshold editor (load/save config.json)
  5. Bantuan       — instruksi pakai

Entry point: python ui_app.py  (atau jalankan MULAI.bat)
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Pastikan module lokal ke-import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.utils import load_config, CONFIG_PATH

APP_VERSION = "1.0.0"
APP_TITLE = "Waste Anomaly Detection"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = APP_DIR / "output" / "Waste_Anomaly_Report.xlsx"

# ============================================================
# STYLE
# ============================================================
FONT_NAME = "Segoe UI"
MONO_NAME = "Consolas"
F_APP_TITLE = (FONT_NAME, 16, "bold")
F_CARD = (FONT_NAME, 11, "bold")
F_BODY = (FONT_NAME, 10)
F_HINT = (FONT_NAME, 9)
F_LOG = (MONO_NAME, 10)

C_BG = "#eef2f7"
C_CARD = "#ffffff"
C_HEADER = "#172033"
C_FOOTER = "#e2e8f0"
C_TERM_BG = "#0b1220"
C_TERM_FG = "#d1d5db"


# ============================================================
# POPUP LOG WINDOW (pola proven dari Inventory-Adjusment)
# ============================================================

class SimpleLogPopup(tk.Toplevel):
    def __init__(self, parent, title="Log Proses"):
        super().__init__(parent)
        self.title(title)
        self.geometry("800x500")
        self.minsize(600, 300)
        self._build()

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        self.text = tk.Text(
            frm, wrap="word", state="disabled",
            bg=C_TERM_BG, fg=C_TERM_FG, font=F_LOG,
            padx=10, pady=10, relief="flat",
            insertbackground=C_TERM_FG,
        )
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        # Footer
        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(frm_btn, text="Bersihkan", command=self.clear).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Salin Log", command=self.copy_log).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Tutup", command=self.withdraw).pack(side="right", padx=4)

    def append(self, msg: str):
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def copy_log(self):
        content = self.text.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            messagebox.showinfo("Salin Log", "Log telah disalin ke clipboard.", parent=self)


# ============================================================
# MAIN APP
# ============================================================

class WasteAnomalyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=C_BG)

        self.config = load_config()
        self.ui_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.log_popup: SimpleLogPopup | None = None
        self.last_output_path: str | None = None
        self.last_summary: dict | None = None

        self._build_styles()
        self._build_header()
        self._build_tabs()
        self._build_footer()
        self.after(100, self._drain_queue)

    # --------------------------------------------------------
    # STYLES
    # --------------------------------------------------------
    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=C_BG)
        style.configure("Card.TFrame", background=C_CARD)
        style.configure("TLabel", background=C_BG, font=F_BODY, foreground="#1F2937")
        style.configure("Card.TLabel", background=C_CARD, font=F_BODY, foreground="#1F2937")
        style.configure("CardTitle.TLabel", background=C_CARD, font=F_CARD, foreground=C_HEADER)
        style.configure("Hint.TLabel", background=C_BG, font=F_HINT, foreground="#6B7280")
        style.configure("TButton", font=F_BODY, padding=6)
        style.configure("Accent.TButton", font=(FONT_NAME, 10, "bold"), padding=8)
        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=F_BODY)
        style.map("TNotebook.Tab",
                  background=[("selected", C_CARD)],
                  foreground=[("selected", C_HEADER)])
        style.configure("TEntry", fieldbackground=C_CARD, padding=4)
        style.configure("TCombobox", padding=4)

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------
    def _build_header(self):
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", side="top")
        hdr.configure(style="TFrame")
        # Inner card
        inner = tk.Frame(hdr, bg=C_HEADER, height=56)
        inner.pack(fill="x")
        lbl = tk.Label(
            inner, text=f"  {APP_TITLE}",
            font=F_APP_TITLE, fg="white", bg=C_HEADER,
        )
        lbl.pack(side="left", padx=16, pady=10)
        sub = tk.Label(
            inner,
            text=f"v{APP_VERSION}  •  Replika Python dari Power Query M code  •  Key Akhir default: {self.config.get('default_key_akhir', 31)}",
            font=F_HINT, fg="#94a3b8", bg=C_HEADER,
        )
        sub.pack(side="left", padx=8)

    # --------------------------------------------------------
    # TABS
    # --------------------------------------------------------
    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Tab 1: Run Pipeline
        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="1. Run Pipeline")
        self._build_run_tab(tab1)

        # Tab 2: Hasil
        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="2. Hasil")
        self._build_result_tab(tab2)

        # Tab 3: Ringkasan
        tab3 = ttk.Frame(nb)
        nb.add(tab3, text="3. Ringkasan")
        self._build_summary_tab(tab3)

        # Tab 4: Konfigurasi
        tab4 = ttk.Frame(nb)
        nb.add(tab4, text="4. Konfigurasi")
        self._build_config_tab(tab4)

        # Tab 5: Bantuan
        tab5 = ttk.Frame(nb)
        nb.add(tab5, text="5. Bantuan")
        self._build_help_tab(tab5)

    # --------------------------------------------------------
    # TAB 1: RUN PIPELINE
    # --------------------------------------------------------
    def _build_run_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # Card 1: Input
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Input Workbook", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_workbook = tk.StringVar()
        ent = ttk.Entry(frm, textvariable=self.var_workbook)
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frm, text="Browse…", command=self._browse_workbook).pack(side="left", padx=4)
        ttk.Button(frm, text="Buka Folder Sample", command=self._open_data_folder).pack(side="left", padx=4)

        # Card 2: Parameters
        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c2.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c2, text="Parameter", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm2 = ttk.Frame(c2)
        frm2.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frm2, text="Key Akhir (1-31):").pack(side="left", padx=(0, 8))
        self.var_key_akhir = tk.IntVar(value=self.config.get("default_key_akhir", 31))
        sp = ttk.Spinbox(frm2, from_=1, to=31, textvariable=self.var_key_akhir, width=6)
        sp.pack(side="left", padx=4)
        tk.Label(frm2, text="(hanya hari 1..N dianalisa)", font=F_HINT, foreground="#6B7280").pack(side="left", padx=8)

        tk.Label(frm2, text="Output:").pack(side="left", padx=(20, 8))
        self.var_output = tk.StringVar(value=str(DEFAULT_OUTPUT))
        ent2 = ttk.Entry(frm2, textvariable=self.var_output, width=50)
        ent2.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(frm2, text="Browse…", command=self._browse_output).pack(side="left")

        # Card 3: Controls + progress
        c3 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c3.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(3, weight=1)

        tk.Label(c3, text="Kontrol", font=F_CARD, fg=C_HEADER, bg=C_CARD).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        frm3 = ttk.Frame(c3)
        frm3.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        self.btn_run = ttk.Button(frm3, text="▶ Mulai Pipeline", style="Accent.TButton", command=self._start_pipeline)
        self.btn_run.pack(side="left", padx=4)
        self.btn_log = ttk.Button(frm3, text="Log Proses", command=self._show_log_popup)
        self.btn_log.pack(side="left", padx=4)
        self.btn_open_out = ttk.Button(frm3, text="Buka Output", command=self._open_output)
        self.btn_open_out.pack(side="left", padx=4)
        self.btn_open_out_dir = ttk.Button(frm3, text="Buka Folder Output", command=self._open_output_folder)
        self.btn_open_out_dir.pack(side="left", padx=4)

        self.progress = ttk.Progressbar(c3, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="ew", padx=16, pady=8)

        self.lbl_status = tk.Label(c3, text="Idle. Pilih workbook dan klik Mulai Pipeline.", bg=C_CARD, fg="#475569", font=F_BODY, anchor="w")
        self.lbl_status.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 12))

    # --------------------------------------------------------
    # TAB 2: HASIL (Treeview)
    # --------------------------------------------------------
    def _build_result_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Card: controls
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Preview Hasil", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_result_sheet = tk.StringVar(value="Detail")
        ttk.Radiobutton(frm, text="Detail", variable=self.var_result_sheet, value="Detail", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Anomali Prioritas", variable=self.var_result_sheet, value="Anomali", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Per Cabang", variable=self.var_result_sheet, value="Cabang", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Top Items", variable=self.var_result_sheet, value="Top", command=self._refresh_preview).pack(side="left", padx=4)
        ttk.Radiobutton(frm, text="Pareto", variable=self.var_result_sheet, value="Pareto", command=self._refresh_preview).pack(side="left", padx=4)

        # Card: treeview
        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(c2, show="headings")
        sb_y = ttk.Scrollbar(c2, orient="vertical", command=self.tree.yview)
        sb_x = ttk.Scrollbar(c2, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        self._preview_dfs: dict[str, "pd.DataFrame"] = {}

    # --------------------------------------------------------
    # TAB 3: RINGKASAN
    # --------------------------------------------------------
    def _build_summary_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Ringkasan Run Terakhir", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        self.lbl_summary = tk.Label(c1, text="(belum ada run)", bg=C_CARD, fg="#475569", font=F_BODY, anchor="w", justify="left")
        self.lbl_summary.pack(fill="x", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)
        self.tree_summary = ttk.Treeview(c2, show="tree headings")
        self.tree_summary.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    # --------------------------------------------------------
    # TAB 4: KONFIGURASI
    # --------------------------------------------------------
    def _build_config_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Threshold & Konfigurasi", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text=f"Di-load dari: {CONFIG_PATH}", font=F_HINT, fg="#6B7280", bg=C_CARD).pack(anchor="w", padx=16)
        tk.Label(c1, text="Edit nilai threshold di bawah, lalu klik Simpan untuk apply ke config.json.", font=F_HINT, fg="#6B7280", bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        # Scrollable threshold form
        canvas = tk.Canvas(c2, bg=C_CARD, highlightthickness=0)
        sb = ttk.Scrollbar(c2, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=C_CARD)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._config_vars: dict[str, tk.Entry] = {}
        thresholds = self.config.get("thresholds", {})
        for i, (key, val) in enumerate(sorted(thresholds.items())):
            tk.Label(inner, text=key, bg=C_CARD, font=F_BODY, width=24, anchor="w").grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            var = tk.StringVar(value=str(val))
            ent = ttk.Entry(inner, textvariable=var, width=12)
            ent.grid(row=i, column=1, padx=4, pady=2, sticky="w")
            self._config_vars[key] = var

        # Save buttons
        btn_frame = tk.Frame(inner, bg=C_CARD)
        btn_frame.grid(row=len(thresholds) + 1, column=0, columnspan=2, padx=12, pady=12, sticky="w")
        ttk.Button(btn_frame, text="Simpan config.json", command=self._save_config).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Reset Default", command=self._reset_config).pack(side="left", padx=4)

    # --------------------------------------------------------
    # TAB 5: BANTUAN
    # --------------------------------------------------------
    def _build_help_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", borderwidth=1, highlightbackground="#e2e8f0", highlightthickness=1)
        c1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        c1.columnconfigure(0, weight=1)
        c1.rowconfigure(0, weight=1)

        txt = tk.Text(c1, wrap="word", relief="flat", bg=C_CARD, fg="#1F2937", font=F_BODY, padx=20, pady=16)
        sb = ttk.Scrollbar(c1, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        help_text = f"""{APP_TITLE} v{APP_VERSION}
Replika Python dari Power Query M code waste anomaly detection.

=== CARA PAKAI ===

1. Siapkan workbook Excel berisi 3 sheet/named-range:
   • REKAP_MENTAH   — data waste harian (kolom 1..31 + NAMA RESTO + NAMA BARANG + JENIS + KETERANGAN + SATUAN + dll)
   • BOM            — master Bill of Materials (Nomor #, Nama Barang, TOTAL BOM)
   • DATABASE_SATUAN — master helper value per kategori (NAMA ITEM + 11 kolom kategori)

2. Tab "1. Run Pipeline":
   • Browse... → pilih workbook Excel
   • Isi Key Akhir (1..31) — cutoff hari terakhir periode analisa
   • (Optional) ganti path output Excel
   • Klik "Mulai Pipeline"

3. Log muncul di popup "Log Proses" (otomatis terbuka saat mulai).

4. Setelah selesai:
   • Output Excel multi-sheet tersimpan di path Output
   • Tab "2. Hasil" → preview tabel per sheet
   • Tab "3. Ringkasan" → ringkasan statistik

5. Tab "4. Konfigurasi" → edit threshold (TH_SPIKE, TH_PEER_HIGH, dll).
   Klik "Simpan config.json" untuk apply perubahan.

=== OUTPUT EXCEL — 6 SHEET ===

• Detail             — semua baris (kolom mengikuti M code Final order)
• Anomali Prioritas  — hanya baris Prioritas Tinggi + Potensi Anomali
• Per Cabang         — ringkasan per NAMA RESTO
• Top Items          — top 20 item by TOTAL waste
• Pareto Alasan      — group by KETERANGAN + cumulative %
• Log Run            — timestamp + parameter + summary stats + log lines

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

Composite Score (max 18):
• >= 8  : Prioritas Tinggi
• >= 5  : Potensi Anomali
• >= 3  : Perlu Review
• else  : Normal

=== TROUBLESHOOTING ===

• "Tidak menemukan sheet untuk 'rekap_mentah'"
  → Pastikan workbook punya sheet bernama REKAP_MENTAH / Rekap Mentah / REKAP.
     Atau edit waste_anomaly/config.json → input_sheets untuk tambah nama kandidat.

• "BOM sheet tidak ditemukan"
  → BOM join dilewati; TOTAL BOM jadi None dan sinyal BOM (S6/S7) tidak trigger.
     Tambahkan sheet BOM / MASTER BOM untuk mengaktifkan.

• "DATABASE_SATUAN tidak ditemukan"
  → STATUS menjadi "Cek" untuk semua baris.
     Tambahkan sheet DATABASE_SATUAN untuk mengaktifkan.

=== KONTAK / UPDATE ===

Source: https://github.com/anandategarch/Waste
Pattern referensi: https://github.com/anandategarch/Inventory-Adjusment
"""
        txt.insert("1.0", help_text)
        txt.configure(state="disabled")

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------
    def _build_footer(self):
        ftr = tk.Frame(self, bg=C_FOOTER, height=28)
        ftr.pack(fill="x", side="bottom")
        self.lbl_footer = tk.Label(
            ftr, text=f"Ready  •  v{APP_VERSION}  •  {datetime.now().strftime('%Y-%m-%d')}",
            bg=C_FOOTER, fg="#475569", font=F_HINT,
        )
        self.lbl_footer.pack(side="left", padx=12, pady=4)

    # --------------------------------------------------------
    # ACTIONS — Run Pipeline
    # --------------------------------------------------------
    def _browse_workbook(self):
        path = filedialog.askopenfilename(
            title="Pilih Workbook Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if path:
            self.var_workbook.set(path)
            # Auto-set output path kalau kosong
            if not self.var_output.get():
                self.var_output.set(str(DEFAULT_OUTPUT))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Pilih Output Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if path:
            self.var_output.set(path)

    def _open_data_folder(self):
        data_dir = APP_DIR / "data"
        data_dir.mkdir(exist_ok=True)
        self._open_path_in_explorer(data_dir)

    def _open_output_folder(self):
        out_dir = Path(self.var_output.get()).parent if self.var_output.get() else APP_DIR / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._open_path_in_explorer(out_dir)

    def _open_output(self):
        if not self.last_output_path:
            messagebox.showinfo("Output", "Belum ada output. Jalankan pipeline dulu.")
            return
        self._open_path_in_explorer(Path(self.last_output_path))

    @staticmethod
    def _open_path_in_explorer(path: Path):
        path = Path(path)
        try:
            if sys.platform.startswith("win"):
                if path.is_dir():
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    os.startfile(str(path.parent))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}" 2>/dev/null &')
        except Exception:
            pass

    def _show_log_popup(self):
        if self.log_popup is None:
            self.log_popup = SimpleLogPopup(self)
        self.log_popup.deiconify()
        self.log_popup.lift()
        self.log_popup.focus_force()

    def _start_pipeline(self):
        wb_path = self.var_workbook.get().strip()
        if not wb_path or not Path(wb_path).exists():
            messagebox.showerror("Input Error", "Workbook belum dipilih atau tidak ditemukan.")
            return
        try:
            ka = int(self.var_key_akhir.get())
            if not (1 <= ka <= 31):
                raise ValueError("Key Akhir harus antara 1 dan 31.")
        except Exception:
            messagebox.showerror("Input Error", "Key Akhir harus angka antara 1 dan 31.")
            return
        out_path = self.var_output.get().strip()
        if not out_path:
            messagebox.showerror("Input Error", "Output path belum diisi.")
            return

        # Disable run button
        self.btn_run.configure(state="disabled")
        self.progress["value"] = 0
        self._set_status("Starting...", "running")

        # Buka log popup
        self._show_log_popup()
        if self.log_popup:
            self.log_popup.clear()
            self.log_popup.append("=== Mulai Pipeline ===")

        # Run in background thread
        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(wb_path, ka, out_path),
            daemon=True,
        )
        self.worker_thread.start()

    def _worker_run(self, wb_path: str, key_akhir: int, out_path: str):
        try:
            summary = run_pipeline(
                workbook_path=wb_path,
                key_akhir=key_akhir,
                output_path=out_path,
                progress_callback=lambda msg, pct: self.ui_queue.put(("log", msg, pct)),
            )
            self.ui_queue.put(("done", summary, None))
        except Exception as e:
            self.ui_queue.put(("error", str(e), None))

    def _drain_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                tag = item[0]
                if tag == "log":
                    _, msg, pct = item
                    if self.log_popup:
                        self.log_popup.append(msg)
                    if pct is not None:
                        self.progress["value"] = float(pct)
                    self._set_status(msg, "running")
                elif tag == "done":
                    _, summary, _ = item
                    self._on_pipeline_done(summary)
                elif tag == "error":
                    _, err, _ = item
                    self._on_pipeline_error(err)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _on_pipeline_done(self, summary: dict):
        self.btn_run.configure(state="normal")
        if not summary.get("success"):
            self._on_pipeline_error(summary.get("error", "Unknown error"))
            return
        self.progress["value"] = 100
        self.last_output_path = summary.get("output_path")
        self.last_summary = summary
        self._set_status(
            f"Done. {summary.get('total_rows', 0)} baris, "
            f"{summary.get('anomali_count', 0)} anomali prioritas, "
            f"output: {self.last_output_path}", "done"
        )
        if self.log_popup:
            self.log_popup.append(f"=== DONE ===")
            self.log_popup.append(f"Total baris: {summary.get('total_rows', 0)}")
            self.log_popup.append(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
            self.log_popup.append(f"Output: {self.last_output_path}")
        # Load preview
        self._load_preview_data(self.last_output_path)
        self._update_summary_tab(summary)
        messagebox.showinfo(
            "Pipeline Selesai",
            f"Pipeline selesai!\n\n"
            f"Total baris diproses: {summary.get('total_rows', 0)}\n"
            f"Anomali prioritas: {summary.get('prioritas_count', 0)}\n"
            f"Potensi anomali: {summary.get('potensi_count', 0)}\n"
            f"Perlu review: {summary.get('review_count', 0)}\n\n"
            f"Output: {self.last_output_path}",
        )

    def _on_pipeline_error(self, err: str):
        self.btn_run.configure(state="normal")
        self._set_status(f"ERROR: {err}", "error")
        if self.log_popup:
            self.log_popup.append(f"!!! ERROR: {err}")
        messagebox.showerror("Pipeline Error", err)

    def _set_status(self, msg: str, kind: str = "running"):
        colors = {"running": "#0369a1", "done": "#16a34a", "error": "#dc2626"}
        self.lbl_status.configure(fg=colors.get(kind, "#475569"))
        self.lbl_status.configure(text=msg)
        self.lbl_footer.configure(text=f"{msg[:80]}  •  v{APP_VERSION}")

    # --------------------------------------------------------
    # PREVIEW (TAB 2)
    # --------------------------------------------------------
    def _load_preview_data(self, xlsx_path: str):
        try:
            import pandas as pd
            sheets = ["Detail", "Anomali Prioritas", "Per Cabang", "Top Items", "Pareto Alasan"]
            self._preview_dfs = {}
            xls = pd.ExcelFile(xlsx_path)
            for s in sheets:
                if s in xls.sheet_names:
                    self._preview_dfs[s] = pd.read_excel(xls, sheet_name=s)
            self._refresh_preview()
        except Exception as e:
            messagebox.showwarning("Preview", f"Gagal load preview: {e}")

    def _refresh_preview(self):
        sheet_map = {
            "Detail": "Detail",
            "Anomali": "Anomali Prioritas",
            "Cabang": "Per Cabang",
            "Top": "Top Items",
            "Pareto": "Pareto Alasan",
        }
        sheet = sheet_map.get(self.var_result_sheet.get(), "Detail")
        df = self._preview_dfs.get(sheet)
        # Clear tree
        self.tree.delete(*self.tree.get_children())
        if df is None or df.empty:
            self.tree["columns"] = ["info"]
            self.tree.heading("info", text="info")
            self.tree.insert("", "end", values=["(tidak ada data — jalankan pipeline dulu)"])
            return
        cols = list(df.columns)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=str(c))
            self.tree.column(c, width=120, stretch=False)
        # Insert rows (limit 500 untuk performa)
        for row in df.head(500).itertuples(index=False, name=None):
            vals = []
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 4))
                else:
                    vals.append(v)
            self.tree.insert("", "end", values=vals)

    # --------------------------------------------------------
    # SUMMARY (TAB 3)
    # --------------------------------------------------------
    def _update_summary_tab(self, summary: dict):
        # Update label
        msg = (
            f"Waktu Run     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total Baris   : {summary.get('total_rows', 0)}\n"
            f"Cabang Unik   : {summary.get('cabang_count', 0)}\n"
            f"Item Unik     : {summary.get('item_count', 0)}\n"
            f"Anomali       : {summary.get('prioritas_count', 0)} prioritas • "
            f"{summary.get('potensi_count', 0)} potensi • "
            f"{summary.get('review_count', 0)} review • "
            f"{summary.get('normal_count', 0)} normal\n"
            f"Output        : {summary.get('output_path', '-')}"
        )
        self.lbl_summary.configure(text=msg)
        # Update tree dengan tabel ringkasan per cabang
        df = self._preview_dfs.get("Per Cabang")
        self.tree_summary.delete(*self.tree_summary.get_children())
        if df is None or df.empty:
            return
        cols = list(df.columns)
        self.tree_summary["columns"] = cols
        for c in cols:
            self.tree_summary.heading(c, text=str(c))
            self.tree_summary.column(c, width=140, stretch=False)
        for row in df.itertuples(index=False, name=None):
            vals = []
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    vals.append("")
                elif isinstance(v, float):
                    vals.append(round(v, 4))
                else:
                    vals.append(v)
            self.tree_summary.insert("", "end", values=vals)

    # --------------------------------------------------------
    # CONFIG (TAB 4)
    # --------------------------------------------------------
    def _save_config(self):
        try:
            new_th = {}
            for k, var in self._config_vars.items():
                raw = var.get().strip()
                # Try int dulu, lalu float
                try:
                    new_th[k] = int(raw)
                except ValueError:
                    try:
                        new_th[k] = float(raw)
                    except ValueError:
                        messagebox.showerror("Config Error", f"Nilai untuk {k} tidak valid: {raw}")
                        return
            self.config["thresholds"] = new_th
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Config", f"Disimpan ke {CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Config Error", str(e))

    def _reset_config(self):
        default_cfg = {
            "thresholds": {
                "TH_SPIKE": 3, "TH_MAX_AVG_AKTIF": 2.5, "TH_MAX_MEDIAN": 3,
                "TH_MAX_SECOND": 3, "TH_MAX_SHARE_WARN": 0.50,
                "TH_MAX_SHARE_HIGH": 0.70, "TH_MAX_BOM_WARN": 0.25,
                "TH_MAX_BOM_HIGH": 0.50, "TH_TOTAL_BOM_WARN": 0.50,
                "TH_TOTAL_BOM_HIGH": 1.00, "TH_PEER_MIN": 3,
                "TH_PEER_WARN": 2, "TH_PEER_HIGH": 3, "TH_LAST_SHARE": 0.70,
            }
        }
        for k, var in self._config_vars.items():
            if k in default_cfg["thresholds"]:
                var.set(str(default_cfg["thresholds"][k]))


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    app = WasteAnomalyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
