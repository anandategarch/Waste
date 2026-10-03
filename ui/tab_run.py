"""Tab 8 Run Pipeline: lifecycle worker + cancel + queue UI.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
from pathlib import Path
from datetime import datetime
from tkinter import filedialog
from tkinter import messagebox
import pandas as pd
import queue
from waste_anomaly.pipeline import run_pipeline
import threading
import tkinter as tk
import traceback
from tkinter import ttk


class RunTabMixin:
    """Tab 8 Run Pipeline: lifecycle worker + cancel + queue UI."""

    def _build_run_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # L12: borderwidth dihapus (semua kartu di bawah sama)
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Input Workbook", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm = ttk.Frame(c1)
        frm.pack(fill="x", padx=16, pady=(0, 12))
        self.var_workbook = tk.StringVar()
        self._ent_workbook = ttk.Entry(frm, textvariable=self.var_workbook)
        self._ent_workbook.pack(side="left", fill="x", expand=True, padx=(0, 8))
        # L11: Enter di kolom workbook → mulai/batalkan run langsung
        self._ent_workbook.bind("<Return>", self._run_from_entry)
        ttk.Button(frm, text="Browse…", command=self._browse_workbook).pack(side="left", padx=4)
        ttk.Button(frm, text="Buka Folder Sample", command=self._open_data_folder).pack(side="left", padx=4)

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c2, text="Parameter", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        frm2 = ttk.Frame(c2)
        frm2.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(frm2, text="Key Akhir (1-31):").pack(side="left", padx=(0, 8))
        # H4: StringVar + validate digits — IntVar.get() TclError kalau kosong;
        # guard config default_key_akhir non-int → fallback 31.
        try:
            _ka_default = int(self.config.get("default_key_akhir", 31))
        except (TypeError, ValueError):
            _ka_default = 31
        if not (1 <= _ka_default <= 31):
            _ka_default = 31
        self.var_key_akhir = tk.StringVar(value=str(_ka_default))
        _vcmd_ka = self.register(self._digits_only)
        ttk.Spinbox(frm2, from_=1, to=31, textvariable=self.var_key_akhir, width=6,
                    validate="key", validatecommand=(_vcmd_ka, "%P")).pack(side="left", padx=4)
        tk.Label(frm2, text="(hanya hari 1..N dianalisa)", font=F_HINT, foreground=C_TEXT_MUTED).pack(side="left", padx=8)
        # H6: baris Output Excel DIHAPUS — pipeline in-memory; laporan dibuat
        # on-demand via "💾 Export Laporan Excel" di tab Hasil.

        c3 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c3.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        c3.columnconfigure(0, weight=1)
        c3.rowconfigure(3, weight=1)
        tk.Label(c3, text="Kontrol", font=F_CARD, fg=C_HEADER, bg=C_CARD).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        frm3 = ttk.Frame(c3)
        frm3.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        # M21: tombol dua-mode — "▶ Mulai Pipeline" ↔ "⏹ Batalkan Run"
        # (command _on_run_button memutuskan berdasar _pipeline_running).
        self.btn_run = ttk.Button(frm3, text="▶ Mulai Pipeline", style="Accent.TButton", command=self._on_run_button)
        self.btn_run.pack(side="left", padx=4)
        self.btn_log = ttk.Button(frm3, text="Log Proses", command=self._show_log_popup)
        self.btn_log.pack(side="left", padx=4)
        # H6: tombol "Buka Folder Output" / "Buka Downloads" dihapus — tidak ada
        # lagi file output otomatis (pipeline in-memory); CSV/Excel export memilih
        # lokasi sendiri lewat file dialog saat export.
        self.progress = ttk.Progressbar(c3, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        self.lbl_status = tk.Label(c3, text="Siap. Pilih workbook dan klik Mulai Pipeline.", bg=C_CARD, fg=C_TEXT_MUTED, font=F_BODY, anchor="w")
        self.lbl_status.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 12))


    def _browse_workbook(self):
        path = filedialog.askopenfilename(
            title="Pilih Workbook Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if path:
            self.var_workbook.set(path)


    def _on_run_button(self):
        if self._pipeline_running:
            self._cancel_pipeline()
        else:
            self._start_pipeline()


    def _run_from_entry(self, _event=None):
        """L11: Enter di kolom workbook → aksi tombol Run (mulai/batalkan)."""
        self._on_run_button()
        return "break"


    def _cancel_pipeline(self):
        """F9 (v2.4.0): set flag cancel — pipeline mengeceknya di GATE ANTAR
        STAGE (via cancel_check) dan berhenti di titik tersebut. CPU berhenti
        bekerja (dulu: hasil dihitung sampai tuntas ~15+ detik lalu dibuang)."""
        if not self._pipeline_running:
            return
        self._pipeline_cancel.set()
        self.btn_run.configure(state="disabled")
        self._set_status("⏹ Membatalkan run… (berhenti di gate stage berikutnya)", "running")
        self.log("=== Permintaan batal diterima — pipeline berhenti di gate antar-stage ===")


    def _set_run_button(self, mode: str):
        """M21: teks/state tombol run. mode "cancel" = sedang berjalan;
        "start" = idle (normal + label mulai)."""
        if not hasattr(self, "btn_run"):
            return
        if mode == "cancel":
            self.btn_run.configure(text="⏹ Batalkan Run")
        else:
            self.btn_run.configure(text="▶ Mulai Pipeline", state="normal")


    def _finish_run_state(self):
        """C1+M21: pulihkan state run (flag, tombol) — dipanggil di SEMUA jalur
        keluar (done/error/cancel) supaya tombol tidak pernah macet."""
        self._pipeline_running = False
        self._pipeline_cancel.clear()
        self._set_run_button("start")


    def _start_pipeline(self):
        if self._pipeline_running:
            return  # C1: guard double-run (normalnya tombol sudah ke mode cancel)
        wb_path = self.var_workbook.get().strip()
        if not wb_path or not Path(wb_path).exists():
            messagebox.showerror("Input Error", "Workbook belum dipilih atau tidak ditemukan.")
            return
        # H4: parse aman — StringVar + validate digits
        ka = self._safe_int(self.var_key_akhir, -1)
        if not (1 <= ka <= 31):
            messagebox.showerror("Input Error", "Key Akhir harus angka antara 1 dan 31.")
            return

        self._pipeline_running = True
        self._pipeline_cancel.clear()
        # M21: tombol TETAP aktif — berubah jadi "⏹ Batalkan Run" (dulu di-disable,
        # sekarang bisa membatalkan). _finish_run_state memulihkan di semua jalur.
        self._set_run_button("cancel")
        self.progress["value"] = 0
        self._set_status("Memulai…", "running")

        self._show_log_popup()
        if self.log_popup:
            self.log_popup.clear()
        # H6: log lewat self.log() — masuk buffer juga (dipakai sheet Log Run)
        self._log_lines.clear()
        self.log("=== Mulai Pipeline ===")
        self.log(f"Workbook: {wb_path} • Key Akhir: {ka} (in-memory)")

        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(wb_path, ka),
            daemon=True,
        )
        self.worker_thread.start()


    def _worker_run(self, wb_path: str, key_akhir: int):
        """Thread pekerja — pipeline in-memory (output_path param legacy, tidak
        perlu di-pass). Semua hasil/error dikirim balik lewat ui_queue.

        F9 (v2.4.0): cancel_check kini di-pass KE pipeline — pembatalan
        efektif ANTAR STAGE (pipeline raise PipelineCancelledError dan
        kembali dengan summary cancelled=True). Dulu flag hanya dicek
        SETELAH run_pipeline() selesai — hasil dihitung sampai tuntas lalu
        dibuang (pembatalan palsu — CPU tetap bekerja penuh)."""
        try:
            summary = run_pipeline(
                workbook_path=wb_path,
                key_akhir=key_akhir,
                progress_callback=lambda msg, pct: self.ui_queue.put(("log", msg, pct)),
                cancel_check=self._pipeline_cancel.is_set,
            )
            if summary.get("cancelled"):
                # Pipeline berhenti di gate antar-stage — pesan ramah + log utuh.
                self.ui_queue.put(("error", summary.get("error", "Run dibatalkan pengguna"), None))
                return
            if self._pipeline_cancel.is_set():
                # Race tipis: cancel datang setelah pipeline DONE tapi sebelum
                # queue diproses — perlakukan sama (hasil dibuang).
                self.ui_queue.put(("error", "Run dibatalkan pengguna", None))
                return
            self.ui_queue.put(("done", summary, None))
        except Exception as e:
            # Sertakan traceback lengkap di queue — ditampilkan di log popup,
            # messagebox hanya pesan singkat (fix worker error detail).
            self.ui_queue.put(("error", str(e), traceback.format_exc()))


    def _drain_queue(self):
        # Reschedule FIRST (fix C1) — polling loop tidak boleh mati oleh
        # exception apa pun, kalau tidak UI freeze + Run button macet disabled.
        self.after(100, self._drain_queue)
        while True:
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._process_queue_item(item)
            except Exception as e:  # noqa: BLE001 — loop must survive anything
                self._set_status(f"⚠ {e}")
                self.log(f"⚠ Error memproses event UI: {e}")


    def _process_queue_item(self, item):
        """Dispatch satu item dari ui_queue (dipisah dari _drain_queue, fix C1)."""
        tag = item[0] if item else None
        if tag == "log":
            _, msg, pct = item
            # C2/H6: lewat self.log() — buffer internal + popup bila hidup
            self.log(msg)
            if pct is not None:
                self.progress["value"] = float(pct)
            self._set_status(msg, "running")
        elif tag == "done":
            _, summary, _ = item
            # C1: pulihkan state tombol/flag SEBELUM render — exception saat
            # render hasil tidak boleh membuat Run button macet disabled.
            self._finish_run_state()
            try:
                self._on_pipeline_done(summary)
            except Exception as e:  # noqa: BLE001 — render hasil best-effort
                self._set_status(f"⚠ Render hasil gagal: {e}", "error")
                self.log(f"⚠ Gagal render hasil pipeline: {e}")
        elif tag == "error":
            _, err, tb = (item + (None,))[:3] if len(item) < 3 else item
            self._finish_run_state()
            self._on_pipeline_error(err, tb)
        elif tag == "export_done":
            _, result, _ = item
            self._on_export_done(result)


    def _on_pipeline_done(self, summary: dict):
        self._finish_run_state()  # C1+M21: flag + tombol pulih di jalur mana pun
        if not summary.get("success"):
            self._on_pipeline_error(summary.get("error", "Unknown error"))
            return
        self.progress["value"] = 100
        # In-memory DataFrame (NO Excel file output)
        df = summary.get("df")
        self.last_summary = summary
        self._last_run_time = datetime.now()
        # Simpan key_akhir ASLI run ini (dipakai quadrant scatter + export Excel)
        try:
            self._last_key_akhir = int(summary.get("key_akhir", 31))
        except (TypeError, ValueError):
            self._last_key_akhir = 31
        rows = summary.get("total_rows", 0)
        self._set_status(f"✓ Pipeline selesai — {rows} baris", "done")
        self.log("=== Selesai ===")  # L6: "DONE" → "Selesai"
        self.log(f"Total baris: {rows}")
        self.log(f"Anomali prioritas: {summary.get('prioritas_count', 0)}")
        self.log("Data siap in-memory — export Excel via tab Hasil")
        # Surface config_load_error (tidak ditelan pipeline)
        cfg_err = summary.get("config_load_error")
        if cfg_err:
            self.log(f"⚠ Config load error: {cfg_err} — threshold memakai default")

        # Build preview_dfs dari DataFrame summary (no Excel read).
        # L17: fallback sheet kosong kini memakai kolom ASLI yang diharapkan
        # (dulu df.iloc[0:0] — kolom Detail bocor ke sheet lain → header salah
        # di tab Hasil; sekarang placeholder kolom + baris "(kosong)").
        if df is not None and not df.empty:
            self._pipeline_df = df  # H6: df utk tombol Export Laporan Excel
            self._preview_dfs["Detail"] = df
            # Build derived sheets in-memory
            self._preview_dfs["Anomali Prioritas"] = df[df["ANOMALY STATUS"].isin(
                ["Prioritas Tinggi", "Potensi Anomali"]
            )].sort_values("ANOMALY SCORE", ascending=False) if "ANOMALY STATUS" in df.columns else df.head(0)
            # Per Cabang summary (in-memory) — L17: builder dibungkus try/except
            # supaya kolom pendukung yang hilang (NAMA BARANG/TOTAL/dll.) tidak
            # melempar KeyError; sheet tetap dibuat dengan kolom yang diharapkan.
            _PC_COLS = ["Cabang", "Jumlah_Barang", "Total_Waste", "Max_Waste_Harian",
                        "Anomali_Prioritas", "Anomali_Potensi", "Anomali_Review"]
            if "NAMA RESTO" in df.columns:
                try:
                    self._preview_dfs["Per Cabang"] = (
                        df.groupby("NAMA RESTO", dropna=False).agg(
                            Jumlah_Barang=("NAMA BARANG", "size"),
                            Total_Waste=("TOTAL", "sum"),
                            Max_Waste_Harian=("MAX", "max"),
                            Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                            Anomali_Potensi=("ANOMALY STATUS", lambda x: int((x == "Potensi Anomali").sum())),
                            Anomali_Review=("ANOMALY STATUS", lambda x: int((x == "Perlu Review").sum())),
                        ).reset_index().rename(columns={"NAMA RESTO": "Cabang"})
                        .sort_values("Anomali_Prioritas", ascending=False)
                    )
                except Exception as e:  # kolom pendukung hilang → fallback kosong
                    self.log(f"⚠ Gagal membangun sheet 'Per Cabang': {e}")
                    self._preview_dfs["Per Cabang"] = pd.DataFrame(columns=_PC_COLS)
            else:
                self._preview_dfs["Per Cabang"] = pd.DataFrame(columns=_PC_COLS)
            # Top Items
            _TI_COLS = ["Rank", "NAMA BARANG", "JENIS", "Total_Waste", "Max_Waste",
                        "Cabang_Terpengaruh", "Anomali_Prioritas"]
            if "NAMA BARANG" in df.columns:
                try:
                    self._preview_dfs["Top Items"] = (
                        df.groupby(["NAMA BARANG", "JENIS"], dropna=False).agg(
                            Total_Waste=("TOTAL", "sum"),
                            Max_Waste=("MAX", "max"),
                            Cabang_Terpengaruh=("NAMA RESTO", "nunique"),
                            Anomali_Prioritas=("ANOMALY STATUS", lambda x: int((x == "Prioritas Tinggi").sum())),
                        ).reset_index().sort_values("Total_Waste", ascending=False).head(20)
                    )
                    self._preview_dfs["Top Items"].insert(0, "Rank", range(1, len(self._preview_dfs["Top Items"]) + 1))
                except Exception as e:  # NAMA RESTO/ANOMALY STATUS hilang → fallback
                    self.log(f"⚠ Gagal membangun sheet 'Top Items': {e}")
                    self._preview_dfs["Top Items"] = pd.DataFrame(columns=_TI_COLS)
            else:
                self._preview_dfs["Top Items"] = pd.DataFrame(columns=_TI_COLS)
            # Pareto
            _PA_COLS = ["KETERANGAN", "Total_Waste", "Jumlah_Barang",
                        "Persentase", "Cumulative"]
            if "KETERANGAN" in df.columns:
                try:
                    pareto_df = (
                        df.groupby("KETERANGAN", dropna=False).agg(
                            Total_Waste=("TOTAL", "sum"),
                            Jumlah_Barang=("NAMA BARANG", "size"),
                        ).reset_index().sort_values("Total_Waste", ascending=False)
                    )
                    grand = pareto_df["Total_Waste"].sum()
                    if grand and grand > 0:
                        pareto_df["Persentase"] = (pareto_df["Total_Waste"] / grand) * 100
                        pareto_df["Cumulative"] = pareto_df["Persentase"].cumsum()
                    else:
                        pareto_df["Persentase"] = 0
                        pareto_df["Cumulative"] = 0
                    self._preview_dfs["Pareto Alasan"] = pareto_df
                except Exception as e:
                    self.log(f"⚠ Gagal membangun sheet 'Pareto Alasan': {e}")
                    self._preview_dfs["Pareto Alasan"] = pd.DataFrame(columns=_PA_COLS)
            else:
                self._preview_dfs["Pareto Alasan"] = pd.DataFrame(columns=_PA_COLS)

        # Ringkasan (murah, tekstual) — render langsung
        self._update_summary_tab(summary)
        # KPI cards (murah) — render langsung
        if df is not None and not df.empty:
            self._update_kpi_cards(df, summary)
            # Reset filter TANPA render (H5) — render ditangani lazy per-tab
            self._reset_filters_state()

        # H2: lazy per-tab render — tandai SEMUA tab dirty, render HANYA tab
        # yang sedang dipilih. Tab lain render saat pertama kali dikunjungi
        # (dulu: ~18 figure di-render sinkron sekaligus → UI nge-freek lama).
        self._mark_all_tabs_dirty()
        self._tab_render_dirty["ringkasan"] = False  # sudah dirender di atas
        cur = self._current_tab_key()
        if cur and cur != "ringkasan":
            err = self._render_tab(cur)
            self._tab_render_dirty[cur] = False
            if err:
                self.log(f"⚠ Render tab '{cur}' gagal: {err}")

        messagebox.showinfo(
            "Pipeline Selesai",
            f"Pipeline selesai!\n\n"
            f"Total baris diproses: {summary.get('total_rows', 0)}\n"
            f"Anomali prioritas: {summary.get('prioritas_count', 0)}\n"
            f"Potensi anomali: {summary.get('potensi_count', 0)}\n"
            f"Perlu review: {summary.get('review_count', 0)}\n\n"
            f"Data siap ditampilkan in-memory (tanpa export Excel).\n"  # L6
            f"Buka tab 'Dashboard' untuk analisa drill-down.",
        )


    def _on_pipeline_error(self, err: str, tb: str | None = None):
        """C1: selalu pulihkan Run button; traceback lengkap ke log popup saja.
        M21: error pembatalan user ditampilkan sebagai info, bukan error."""
        self._finish_run_state()
        cancelled = (err == "Run dibatalkan pengguna")
        if cancelled:
            self._set_status("⏹ Run dibatalkan pengguna", "error")
        else:
            self._set_status(f"ERROR: {err}", "error")
        self.log(f"!!! ERROR: {err}")
        if tb:
            self.log(tb)  # detail traceback di popup log — bukan messagebox
        if cancelled:
            self.log("=== Run dibatalkan — hasil tidak dirender ===")
            messagebox.showinfo("Run Dibatalkan", "Run dibatalkan oleh pengguna — hasil tidak dirender.")
        else:
            messagebox.showerror("Pipeline Error", err)



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
