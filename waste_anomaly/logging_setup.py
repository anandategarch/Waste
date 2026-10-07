"""Logging framework — rotating file handler (F11 v2.4.0).

Sebelumnya: 16+ exception ditelan diam-diam (``except: pass``), error
produksi tidak meninggalkan jejak file apa pun (log hanya popup in-memory
+ 2 print stderr). Sekarang: logger terkonfigurasi menulis ke
``logs/waste_anomaly.log`` (rotating 1 MB × 3 backup); exception global
UI ditangani ``sys.excepthook`` di ui/app.py (_qt_excepthook).

Cara pakai (ui/app.py startup):
    from waste_anomaly.logging_setup import setup_logging
    log_path = setup_logging()          # → logs/waste_anomaly.log

v2.13.8 (gel-C deep audit): install_tk_exception_hook + tk_suppressed
DIHAPUS — sisa era Tkinter (UI PySide6 sejak v2.6.0, hook Tk tak pernah
dipanggil lagi; contoh pemakaian lama di docstring ini juga menyesatkan).
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_MAX_BYTES = 1 * 1024 * 1024   # 1 MB per file
LOG_BACKUP_COUNT = 3              # waste_anomaly.log.1/.2/.3

_configured = False


def setup_logging(
    log_dir: str | Path | None = None,
    level: int = logging.INFO,
) -> Path | None:
    """Konfigurasi root logger dengan RotatingFileHandler (idempotent).

    Args:
        log_dir: folder log. Default: folder exe saat frozen (v2.4.1 — dulu
            cwd, yang bisa berupa System32 kalau shortcut punya "Start in"
            berbeda), lalu ``<cwd>/logs``, lalu ``~/.waste_anomaly/logs``.
            Kalau semua gagal (read-only), → None (console-only).
        level: level file handler (default INFO).

    Returns:
        Path file log, atau None bila logging ke file tidak tersedia.
    """
    global _configured
    if _configured:
        return getattr(setup_logging, "_log_path", None)

    candidates = []
    if log_dir is not None:
        candidates.append(Path(log_dir))
    else:
        # v2.4.1: exe mode — log BERDAMPINGAN exe (bukan cwd yang bisa aneh
        # / bukan _MEIPASS temp yang terhapus saat exit).
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve().parent / "logs")
        candidates.append(Path.cwd() / "logs")
    candidates.append(Path.home() / ".waste_anomaly" / "logs")

    log_dir_path: Path | None = None
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            log_dir_path = cand
            break
        except OSError:
            continue

    if log_dir_path is None:
        # Tidak ada lokasi writable — console-only, jangan ganggu aplikasi.
        logging.basicConfig(level=level, format=LOG_FORMAT)
        return None

    log_path = log_dir_path / "waste_anomaly.log"
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # Cegah handler ganda bila setup dipanggil ulang
    for existing in list(root.handlers):
        if isinstance(existing, logging.handlers.RotatingFileHandler):
            root.removeHandler(existing)
    root.addHandler(handler)

    # Matikan propagasi log library paling berisik ke file (PIL/openpyxl
    # DEBUG sangat verbose); kita tetap menangkap WARNING+ mereka.
    # v2.8.2: "matplotlib" dibuang — dependensi sudah dihapus sejak v2.8.1.
    for noisy in ("PIL", "openpyxl"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    setup_logging._log_path = log_path  # type: ignore[attr-defined]
    logging.getLogger(__name__).info(
        "Logging aktif → %s (rotating %d KB × %d)",
        log_path, LOG_MAX_BYTES // 1024, LOG_BACKUP_COUNT,
    )
    return log_path
