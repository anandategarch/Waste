"""ui/ — paket UI Waste Anomaly Detection (dipecah dari ui_app.py, v2.4.0).

Struktur:
    shared.py        — konstanta + registry font + helper murni
    widgets.py       — SimpleLogPopup, KPICard, FilterChip
    base.py          — infrastruktur app (styling, tab scaffolding, queue log)
    tab_*.py         — 10 modul tab (dashboard, compare, quadrant, rate,
                       result, viz, summary, run, config, help)
    app.py           — komposisi WasteAnomalyApp + main()

Pintu masuk tetap ui_app.py (MULAI.bat tidak berubah).
"""
