"""
Waste Anomaly Detection — Python/pandas replica dari Power Query M code.

Versi: 2.13.14
Author: anandategarch
Lisensi: MIT

Penggunaan dasar (tanpa UI):
    from waste_anomaly.pipeline import run_pipeline

    summary = run_pipeline(
        workbook_path="data/rekap.xlsx",
        key_akhir=31,
    )
    df = summary["df"]  # hasil in-memory — export via exporter.export_to_excel

Untuk UI (PySide6), jalankan:  python ui_app.py
"""

__version__ = "2.13.14"
__all__ = ["pipeline", "loader", "stages", "signals", "exporter", "utils",
           "temporal", "priority", "data_quality", "period_compare",
           "period_history"]
