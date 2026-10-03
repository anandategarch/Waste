"""
Waste Anomaly Detection — Python/pandas replica dari Power Query M code.

Versi: 1.0.0
Author: anandategarch
Lisensi: MIT

Penggunaan dasar (tanpa UI):
    from waste_anomaly.pipeline import run_pipeline
    run_pipeline(
        workbook_path="data/rekap.xlsx",
        key_akhir=31,
        output_path="output/Waste_Anomaly_Report.xlsx",
    )

Untuk UI Tkinter, jalankan:  python ui_app.py
"""

__version__ = "2.5.0"
__all__ = ["pipeline", "loader", "stages", "signals", "exporter", "utils",
           "temporal", "priority", "data_quality", "period_compare"]
