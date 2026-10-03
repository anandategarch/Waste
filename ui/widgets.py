"""Widget UI reusable: popup log, KPI card, filter chip.

Dipakai mixin-mixin tab via komposisi (ui/app.py)."""
from __future__ import annotations

from .shared import C_BORDER
from .shared import C_TERM_BG
from .shared import C_TEXT_MUTED
from .shared import FONT_NAME
from .shared import F_HINT
from .shared import F_KPI_LABEL
from .shared import F_KPI_NUM
from .shared import F_LOG
from .shared import _LOGGER
from datetime import datetime
import tkinter as tk
from tkinter import ttk


class SimpleLogPopup(tk.Toplevel):
    def __init__(self, parent, title="Log Proses"):
        super().__init__(parent)
        self.title(title)
        self.geometry("800x500")
        self.minsize(600, 300)
        # C2: tombol X hanya menyembunyikan popup (semantics sama dengan tombol
        # "Tutup") — reference di app tetap valid, tidak jadi stale lalu TclError.
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        try:
            self.transient(parent)  # M20: ikuti parent — tanpa focus_force()
        except Exception:
            _LOGGER.debug("Suppressed: Exception", exc_info=True)
        self._build()

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        self.text = tk.Text(
            frm, wrap="word", state="disabled",
            bg=C_TERM_BG, fg="#d1d5db", font=F_LOG,
            padx=10, pady=10, relief="flat",
        )
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(frm_btn, text="Bersihkan", command=self.clear).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Salin Log", command=self.copy_log).pack(side="right", padx=4)
        ttk.Button(frm_btn, text="Tutup", command=self.withdraw).pack(side="right", padx=4)

    def append(self, msg: str):
        if not self.winfo_exists():  # C2: popup mungkin sudah di-destroy
            return
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        if not self.winfo_exists():  # C2
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def copy_log(self):
        content = self.text.get("1.0", "end").strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)


class KPICard(tk.Frame):
    """KPI card dengan angka besar + label + warna tema."""

    def __init__(self, parent, label: str, value: str = "0", color: str = "#0f172a", bg: str = "#ffffff"):
        super().__init__(parent, bg=bg, relief="flat",
                         highlightbackground=C_BORDER, highlightthickness=1)
        self._label_var = tk.StringVar(value=label)
        self._value_var = tk.StringVar(value=value)
        self._color = color

        # Padding
        self.columnconfigure(0, weight=1)
        # Label
        lbl = tk.Label(self, textvariable=self._label_var, font=F_KPI_LABEL,
                       fg=C_TEXT_MUTED, bg=bg, anchor="w")
        lbl.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        # Value — L13: wraplength supaya angka panjang wrap ke 2 baris, bukan
        # kepotong (KPI card sempit di layar kecil).
        self.val_lbl = tk.Label(self, textvariable=self._value_var, font=F_KPI_NUM,
                                fg=color, bg=bg, anchor="w", wraplength=120)
        self.val_lbl.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

    def set_value(self, value: str):
        self._value_var.set(value)


class FilterChip(tk.Frame):
    """Chip filter aktif — M7: SELURUH chip clickable (klik di mana pun =
    remove, sama dengan klik ×), cursor hand2 + bg berubah saat hover.
    Glyph × tetap ada sebagai affordance visual."""

    _BG = "#fef3c7"        # amber-100
    _BG_HOVER = "#fde68a"  # amber-200
    _BORDER = "#fcd34d"    # amber-300
    _FG = "#92400e"        # amber-800

    def __init__(self, parent, label: str, on_remove):
        super().__init__(parent, bg=self._BG, relief="flat", cursor="hand2",
                         highlightbackground=self._BORDER, highlightthickness=1)
        self._on_remove_cb = on_remove
        self._lbl = tk.Label(self, text=label, font=F_HINT, fg=self._FG,
                             bg=self._BG, cursor="hand2")
        self._lbl.pack(side="left", padx=(6, 2), pady=2)
        self._x = tk.Label(self, text="×", font=(FONT_NAME, 10, "bold"),
                           fg=self._FG, bg=self._BG, cursor="hand2")
        self._x.pack(side="left", padx=(0, 6))
        # M7: hit area = seluruh chip (frame + kedua label), bukan cuma ×
        for w in (self, self._lbl, self._x):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, _event):
        try:
            self._on_remove_cb()
        except tk.TclError:
            _LOGGER.debug("Suppressed: chip sudah di-destroy oleh handler remove-nya", exc_info=True)
        return "break"

    def _on_leave(self, _event):
        # Pointer mungkin hanya pindah frame → label anak (memicu Leave frame
        # + Enter label) — matikan hover hanya bila pointer benar-benar keluar.
        try:
            x, y = self.winfo_pointerxy()
            node = self.winfo_containing(x, y)
            while node is not None:
                if node is self:
                    return  # masih di dalam chip
                node = getattr(node, "master", None)
        except tk.TclError:
            _LOGGER.debug("Suppressed: tk.TclError", exc_info=True)
        self._set_hover(False)

    def _set_hover(self, hovered: bool):
        bg = self._BG_HOVER if hovered else self._BG
        for w in (self, self._lbl, self._x):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                _LOGGER.debug("Suppressed: widget mungkin sudah di-destroy", exc_info=True)

# Registry font (v2.4.0): _init_fonts me-rebind F_*/FONT_NAME/MONO_NAME di
# namespace modul INI saat startup — pengganti pola `global` satu-file lama.
import sys as _sys  # noqa: E402
from . import shared as _shared  # noqa: E402
_shared.register_font_consumer(_sys.modules[__name__])
