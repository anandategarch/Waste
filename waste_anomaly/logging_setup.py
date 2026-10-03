"""Logging framework — rotating file handler (F11 v2.4.0).

Sebelumnya: 16+ exception ditelan diam-diam (``except: pass``), error
produksi tidak meninggalkan jejak file apa pun (log hanya popup in-memory
+ 2 print stderr). Sekarang: logger terkonfigurasi menulis ke
``logs/waste_anomaly.log`` (rotating 1 MB × 3 backup) + hook exception
global Tkinter (``report_callback_exception``).

Cara pakai (ui/app.py startup):
    from waste_anomaly.logging_setup import setup_logging
    log_path = setup_logging()          # → logs/waste_anomaly.log
    ...
    install_tk_exception_hook(app)      # pasang hook ke root Tk
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
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

    # Matikan propagasi log library paling berisik ke file (matplotlib/openpyxl
    # DEBUG sangat verbose); kita tetap menangkap WARNING+ mereka.
    for noisy in ("matplotlib", "PIL", "openpyxl"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    setup_logging._log_path = log_path  # type: ignore[attr-defined]
    logging.getLogger(__name__).info(
        "Logging aktif → %s (rotating %d KB × %d)",
        log_path, LOG_MAX_BYTES // 1024, LOG_BACKUP_COUNT,
    )
    return log_path


def install_tk_exception_hook(root) -> None:
    """Pasang hook exception global untuk callback Tkinter (F11).

    Tanpa hook ini, exception di event handler Tk hanya tercetak ke stderr
    dan TIDAK masuk file log. Dengan hook: traceback lengkap ke file log +
    status bar app (bila tersedia) supaya user tahu sesuatu gagal.
    """
    log = logging.getLogger("waste_anomaly.ui")

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, tk_suppressed()):
            # TclError saat teardown window itu normal (widget sudah mati)
            return
        log.error(
            "Exception di callback Tk: %s: %s\n%s",
            exc_type.__name__, exc_value,
            "".join(traceback.format_tb(exc_tb)),
        )

    try:
        root.report_callback_exception = _hook
    except Exception:  # pragma: no cover — root bukan widget Tk biasa
        log.debug("Gagal memasang report_callback_exception", exc_info=True)


def tk_suppressed():
    """tk.TclError lazily — modul ini dipakai juga oleh non-UI (pipeline tests)."""
    try:
        import tkinter
        return tkinter.TclError
    except ImportError:  # pragma: no cover — environment tanpa tkinter
        class _NeverMatch(Exception):
            pass
        return _NeverMatch
