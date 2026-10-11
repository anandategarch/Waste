"""theme.py — palet warna + QSS global untuk UI PySide6 (v2.6.0 rebuild).

Warna diambil dari tema lama (slate/white) supaya terasa familiar, dengan
penambahan token severity untuk pewarnaan baris tabel anomali.
"""
from __future__ import annotations

C_BG = "#f1f5f9"            # slate-100 — latar utama
C_CARD = "#ffffff"           # kartu
C_HEADER = "#0f172a"        # slate-900 — teks judul
C_BORDER = "#e2e8f0"         # border kartu
C_TEXT_MUTED = "#64748b"    # teks sekunder
C_ACCENT = "#0f766e"         # teal — tombol aksi utama
C_ACCENT_HOVER = "#115e59"

# v2.13.15 (gel-6 C21): teks TAB NON-AKTIF — dulu C_TEXT_MUTED (#64748b,
# slate-500) di atas latar tab #e2e8f0 = kontras 3,1:1 < WCAG AA 4,5:1
# (label tab terbaca kabur di layar kecil/low-vision). slate-600 #475569
# = kontras ±6,1:1 (≥ AA; dihitung fungsi luminance relatif di
# test_v21315). Konstanta bernama supaya perubahan kontras terlihat
# sebagai keputusan a11y, bukan warna ajaib.
C_TAB_IDLE_FG = "#475569"   # slate-600 — teks tab non-aktif (WCAG AA)

# Status colors (match charts.py + shared.py lama) — (fg, bg tint)
STATUS_COLORS: dict[str, tuple[str, str]] = {
    "Prioritas Tinggi": ("#dc2626", "#fef2f2"),
    "Potensi Anomali":  ("#ea580c", "#fff7ed"),
    "Perlu Review":     ("#b45309", "#fffbeb"),
    "Normal":           ("#16a34a", "#f0fdf4"),
}

SELECT_BG = "#ccfbf1"        # teal-100 — seleksi baris
SELECT_FG = "#134e4a"

# v2.12.5 — sumber tunggal font UI (dipakai QSS *{} + pengukuran judul
# kolom di DataTable._auto_columns): widget.font() TIDAK mewarisi font
# QSS (Windows: default 9pt vs QSS 13px → lantai header kurang ukur
# ~8% → "nama header terpotong" oleh funnel).
UI_FONT_FAMILY = '"Segoe UI", "Tahoma", "DejaVu Sans", sans-serif'
UI_FONT_PX = 13
UI_HEADER_WEIGHT = 600


# v2.13.13 (gel-4 D25): rule :focus TOMBOL ditambahkan di QSS bawah —
# tanpa itu, navigasi keyboard (Tab/Enter — jalur a11y) tak pernah
# menunjukkan tombol mana yang aktif (audit D25: hanya :hover yang ada;
# input QLineEdit dkk. sudah punya :focus sejak lama). Warna: aksen teal
# utk tombol biasa; #5eead4 (teal muda) utk accent (terbaca di atas
# latar teal gelap); merah utk danger.

QSS = f"""
* {{
    font-family: {UI_FONT_FAMILY};
    font-size: {UI_FONT_PX}px;
}}
QMainWindow {{ background: {C_BG}; }}
QFrame#card {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
}}
QFrame#kpiframe {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
}}
QLabel#cardTitle {{
    color: {C_HEADER};
    font-weight: 600;
    background: transparent;
    border: none;
}}
QLabel#hint {{ color: {C_TEXT_MUTED}; background: transparent; border: none; font-size: 12px; }}
QLabel#muted {{ color: {C_TEXT_MUTED}; background: transparent; border: none; }}

QPushButton {{
    background: #ffffff;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: #94a3b8; background: #f8fafc; }}
QPushButton:focus {{ border-color: {C_ACCENT}; }}
QPushButton:disabled {{ color: #94a3b8; background: #f1f5f9; }}

QPushButton#accent {{
    background: {C_ACCENT};
    color: #ffffff;
    border: 1px solid {C_ACCENT};
    font-weight: 600;
}}
QPushButton#accent:hover {{ background: {C_ACCENT_HOVER}; }}
QPushButton#accent:focus {{ border-color: #5eead4; }}
QPushButton#accent:disabled {{ background: #94a3b8; border-color: #94a3b8; color: #e2e8f0; }}

QPushButton#danger {{ background: #ffffff; color: #dc2626; border: 1px solid #fecaca; }}
QPushButton#danger:hover {{ background: #fef2f2; }}
QPushButton#danger:focus {{ border-color: #dc2626; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #ffffff;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {C_ACCENT}; }}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid {C_BORDER};
    selection-background-color: {SELECT_BG};
    selection-color: {SELECT_FG};
}}

QTableView {{
    background: #ffffff;
    border: 1px solid {C_BORDER};
    gridline-color: #f1f5f9;
    selection-background-color: {SELECT_BG};
    selection-color: {SELECT_FG};
    alternate-background-color: #fafcff;
}}
QHeaderView::section {{
    background: #f8fafc;
    color: {C_HEADER};
    border: none;
    border-right: 1px solid {C_BORDER};
    border-bottom: 1px solid {C_BORDER};
    padding: 6px 8px;
    font-weight: {UI_HEADER_WEIGHT};
}}
QTableView::item {{ padding: 3px 8px; }}

QTabWidget::pane {{ border: 1px solid {C_BORDER}; border-radius: 6px; background: {C_BG}; top: -1px; }}
QTabBar::tab {{
    background: #e2e8f0;
    color: {C_TAB_IDLE_FG};
    padding: 7px 10px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {C_CARD}; color: {C_HEADER}; font-weight: 600; }}

QProgressBar {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    background: #ffffff;
    text-align: center;
    min-height: 18px;
}}
QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 5px; }}

QPlainTextEdit#log {{
    background: #0b1220;
    color: #cbd5e1;
    font-family: "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
}}
QTextBrowser {{ background: #ffffff; border: 1px solid {C_BORDER}; border-radius: 6px; }}

QToolBar {{ background: {C_HEADER}; border: none; padding: 4px 8px; spacing: 8px; }}
QToolBar QToolButton {{
    background: transparent;
    color: #f1f5f9;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}}
QToolBar QToolButton:hover {{ background: #1e293b; }}
QToolBar QToolButton:pressed {{ background: #334155; }}
QToolBar::separator {{ background: #334155; width: 1px; margin: 6px 4px; }}

QStatusBar {{ background: {C_CARD}; border-top: 1px solid {C_BORDER}; color: {C_TEXT_MUTED}; }}
QSplitter::handle {{ background: {C_BORDER}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}
QScrollArea {{ border: none; background: transparent; }}

QGroupBox {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    margin-top: 12px;
    font-weight: 600;
    color: {C_HEADER};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: 0px;
    padding: 0 4px;
}}
"""
