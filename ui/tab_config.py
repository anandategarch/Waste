"""Tab 9 Konfigurasi: editor threshold.

Mixin untuk WasteAnomalyApp (komposisi di ui/app.py)."""
from __future__ import annotations

from waste_anomaly.utils import CONFIG_PATH
from .shared import C_BORDER
from .shared import C_CARD
from .shared import C_HEADER
from .shared import C_TEXT_MUTED
from .shared import F_BODY
from .shared import F_CARD
from .shared import F_HINT
import json
from tkinter import messagebox
import os
import tkinter as tk
from tkinter import ttk


class ConfigTabMixin:
    """Tab 9 Konfigurasi: editor threshold."""

    def _build_config_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # L12: borderwidth dihapus
        c1 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(c1, text="Threshold & Konfigurasi", font=F_CARD, fg=C_HEADER, bg=C_CARD).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Label(c1, text=f"Di-load dari: {CONFIG_PATH}", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16)
        tk.Label(c1, text="Edit nilai threshold di bawah, lalu klik Simpan untuk apply ke config.json.", font=F_HINT, fg=C_TEXT_MUTED, bg=C_CARD).pack(anchor="w", padx=16, pady=(0, 12))

        c2 = tk.Frame(parent, bg=C_CARD, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        c2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=1)

        canvas = tk.Canvas(c2, bg=C_CARD, highlightthickness=0)
        sb = ttk.Scrollbar(c2, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=C_CARD)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        _cfg_window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        # M12: width-sync — input threshold ikut lebar canvas; C3: wheel via
        # global dispatcher (sebelumnya canvas ini TIDAK bisa di-scroll sama sekali).
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(_cfg_window_id, width=e.width))
        canvas._waste_scroll = True  # type: ignore[attr-defined]

        # L3: type hint diperbaiki — isinya StringVar, bukan tk.Entry
        self._config_vars: dict[str, tk.StringVar] = {}
        thresholds = self.config.get("thresholds", {})
        for i, (key, val) in enumerate(sorted(thresholds.items())):
            tk.Label(inner, text=key, bg=C_CARD, font=F_BODY, width=24, anchor="w").grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            var = tk.StringVar(value=str(val))
            ttk.Entry(inner, textvariable=var, width=12).grid(row=i, column=1, padx=4, pady=2, sticky="w")
            self._config_vars[key] = var

        btn_frame = tk.Frame(inner, bg=C_CARD)
        btn_frame.grid(row=len(thresholds) + 1, column=0, columnspan=2, padx=12, pady=12, sticky="w")
        ttk.Button(btn_frame, text="Simpan config.json", command=self._save_config).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Reset Default", command=self._reset_config).pack(side="left", padx=4)


    def _save_config(self):
        """Simpan config.json — ATOMIC (tmp + os.replace, pola filters.py) +
        validasi rentang: threshold numerik negatif/0 ditolak (mengubah
        perilaku sinyal diam-diam)."""
        try:
            new_th = {}
            for k, var in self._config_vars.items():
                raw = var.get().strip()
                try:
                    new_th[k] = int(raw)
                except ValueError:
                    try:
                        new_th[k] = float(raw)
                    except ValueError:
                        messagebox.showerror("Config Error", f"Nilai untuk {k} tidak valid: {raw}")
                        return
                # F2 v2.3.2: validasi rentang — mencegah nilai invalid tersimpan
                if isinstance(new_th[k], (int, float)) and new_th[k] <= 0:
                    messagebox.showerror("Config Error", f"Nilai {k} harus > 0 (dapat: {raw})")
                    return
            self.config["thresholds"] = new_th
            # F2 v2.3.2: atomic save — crash/kill mid-write tidak lagi mengorupsi
            # config.json (sebelumnya open("w") + json.dump langsung).
            tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, CONFIG_PATH)
            messagebox.showinfo("Config", f"Disimpan ke {CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Config Error", str(e))


    def _reset_config(self):
        # F3 v2.3.2: kini 20/20 key (sebelumnya 14 — 6 key baru v2.3.1 tidak
        # pernah di-reset: STATUS_*, S2_SCORE2_MIN, S10_BOM_MIN, QUADRANT_THRESHOLD)
        default_cfg = {
            "thresholds": {
                "TH_SPIKE": 3, "TH_MAX_AVG_AKTIF": 2.5, "TH_MAX_MEDIAN": 3,
                "TH_MAX_SECOND": 3, "TH_MAX_SHARE_WARN": 0.50,
                "TH_MAX_SHARE_HIGH": 0.70, "TH_MAX_BOM_WARN": 0.25,
                "TH_MAX_BOM_HIGH": 0.50, "TH_TOTAL_BOM_WARN": 0.50,
                "TH_TOTAL_BOM_HIGH": 1.00, "TH_PEER_MIN": 3,
                "TH_PEER_WARN": 2, "TH_PEER_HIGH": 3, "TH_LAST_SHARE": 0.70,
                "STATUS_PRIORITAS": 8, "STATUS_POTENSI": 5, "STATUS_REVIEW": 3,
                "S2_SCORE2_MIN": 4, "S10_BOM_MIN": 0.10, "QUADRANT_THRESHOLD": 0.50,
            }
        }
        for k, var in self._config_vars.items():
            if k in default_cfg["thresholds"]:
                var.set(str(default_cfg["thresholds"][k]))



# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
