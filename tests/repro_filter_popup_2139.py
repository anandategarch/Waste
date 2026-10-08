"""Repro empiris: bug user 'klik filter muncul pop up' (v2.13.8).

Skenario (jalur riil Qt, terdokumentasi di widgets.py v2.12.5):
  1. User klik ikon funnel di header kolom → _HeaderFilterMenu terbuka
     (menu menutupi sebagian baris tabel).
  2. User memberi filter (live-apply) lalu menutup menu — BUKAN lewat
     tombol 'Selesai' melainkan KLIK DI LUAR MENU (kebiasaan umum).
     Qt: menu tertutup + klik itu DI-REPLAY ke tabel sebagai tekan#1.
  3. Tekanan#1 jatuh di BARIS TABEL → currentRowChanged → _on_selection
     → DetailDialog.show_record → POP-UP MUNCUL TANPA NIAT USER.
Guard v2.12.5 hanya menelan klik-GANDA artefak (tekan#2 sintesis) —
tekan#1 replay JALUR TUNGGAL tidak tersentuh → inilah sisa bug yang
dilaporkan user ("masih ada bug pada klik filter muncul pop up").

Simulasi offscreen: buka menu riil → tutup (aboutToHide terpicu,
_note_hf_menu_hidden mencatat waktu) → QTest.mouseClick baris tabel
segera setelahnya = replika tekan#1 replay. Cek popup visible?
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _anomali_df(n: int = 8) -> pd.DataFrame:
    data = {
        "NAMA RESTO": [f"RESTO {i}" for i in range(n)],
        "NAMA BARANG": [f"BARANG {i}" for i in range(n)],
        "JENIS": ["BAHAN"] * n,
        "KETERANGAN": ["alasan A"] * n,
        "SOURCE DATA": ["S1"] * n,
        "SATUAN": ["GR"] * n,
        "TOTAL": [float(1000 * (i + 1)) for i in range(n)],
        "ANOMALY SCORE": [9 - i for i in range(n)],
        "ANOMALY STATUS": ["Prioritas Tinggi", "Potensi Anomali",
                           "Perlu Review", "Perlu Review"] * 2,
        "ANOMALY REASONS": ["S1 spike; S6 max/BOM"] * n,
    }
    return pd.DataFrame(data)


def main() -> None:
    app = _qapp()
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from ui.state import AppContext
    from ui.view_anomali import AnomaliView

    ctx = AppContext({})
    view = AnomaliView(ctx)
    ctx.set_dataset(_anomali_df(), {"key_akhir": 31})
    view._refresh_table()
    view.resize(1200, 700)
    view.show()
    app.processEvents()

    hdr = view._table.horizontalHeader()
    assert isinstance(hdr, __import__("ui.widgets", fromlist=["FilterHeader"]).FilterHeader), \
        "header harus FilterHeader"

    # --- 1. Buka menu funnel kolom 'NAMA RESTO' (via jalur riil _open_menu)
    logical = list(view._table.model().dataframe.columns).index("NAMA RESTO")
    hdr._open_menu(logical)
    menu = hdr._menu
    assert menu is not None and menu.isVisible(), "menu harus terbuka"
    print("[1] menu funnel terbuka  :", menu.isVisible())

    # --- 2. Tutup menu SEBAGAIMANA klik-di-luar → aboutToHide terpicu
    #         (inilah momen _note_hf_menu_hidden mencatat waktu+rect)
    menu.hide()
    app.processEvents()
    print("[2] menu tertutup, guard terekam (ts, rect):",
          view._table._hf_hide[0] > 0, view._table._hf_hide[1] is not None)

    # --- 3. Replika tekan#1 REPLAY: klik tunggal pada baris tabel SEGERA
    #         setelah menu tertutup (dalam jendela guard 0.6 dtk).
    #         Pilih BARIS-2 (baris lain dari seleksi saat ini) — persis
    #         seperti klik penutup menu yang jatuh di baris tabel.
    view._table.setCurrentIndex(view._table.model().index(0, 1))
    app.processEvents()
    # seleksi awal membuka pop-up (fitur) — tutup dulu utk premis bersih
    view._popup.hide()
    app.processEvents()
    assert not view._popup.isVisible(), "premis: popup tertutup dulu"

    row_y = view._table.visualRect(view._table.model().index(2, 1)).center()
    QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(row_y.x(), row_y.y()))
    app.processEvents()

    leaked = view._popup.isVisible()
    print("[3] klik tunggal pasca-tutup-menu → popup VISIBLE:",
          leaked, "<== BUG MASIH ADA" if leaked else "(bersih)")

    # --- Kontrol: klik baris NORMAL (tanpa riwayat menu baru-baru ini)
    #     — jendela guard lewat dulu (sleep 0.8 dtk) → popup HARUS terbuka.
    view._table.setCurrentIndex(view._table.model().index(1, 1))
    app.processEvents()
    view._popup.hide()
    app.processEvents()
    QTest.qWait(800)
    row_y = view._table.visualRect(view._table.model().index(3, 1)).center()
    QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(row_y.x(), row_y.y()))
    app.processEvents()
    print("[4] kontrol: klik normal (guard lewat) → popup VISIBLE:",
          view._popup.isVisible(), "(harus True — fitur inti utuh)")

    print()
    print("KESIMPULAN: bug klik-filter→popup",
          "TERKONFIRMASI (tekan#1 replay lolos guard)" if leaked
          else "tidak terkonfirmasi")


if __name__ == "__main__":
    main()
