"""Test — logging framework (logging_setup.py, F11 v2.4.0).

Logger rotating-file harus: aktif & idempotent, menulis exception dari
hook Tk, dan tidak crash di environment tanpa lokasi writable.
"""

import logging
from pathlib import Path

from waste_anomaly.logging_setup import setup_logging


class TestSetupLogging:
    def test_file_log_terbuat_dan_terisi(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path)
        assert log_path is not None
        assert log_path.exists()
        # Tulis pesan → muncul di file
        logging.getLogger("test.waste").warning("pesan-uji-123")
        for h in logging.getLogger().handlers:
            h.flush()
        content = log_path.read_text(encoding="utf-8")
        assert "pesan-uji-123" in content
        assert "WARNING" in content

    def test_format_terstruktur(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path)
        logging.getLogger("test.waste").error("err-uji")
        for h in logging.getLogger().handlers:
            h.flush()
        content = log_path.read_text(encoding="utf-8")
        # Format: timestamp [LEVEL] name: message
        assert " [ERROR] test.waste: err-uji" in content

    def test_rotating_handler_dipakai(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        handlers = logging.getLogger().handlers
        rotating = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 1 * 1024 * 1024
        assert rotating[0].backupCount == 3

    def test_idempotent_tidak_doouble_handler(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        setup_logging(log_dir=tmp_path)  # panggil ulang — tidak menambah handler
        handlers = logging.getLogger().handlers
        rotating = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1

    def test_library_berisik_dibatasi(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        assert logging.getLogger("matplotlib").level == logging.WARNING
