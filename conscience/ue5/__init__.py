"""
conscience.ue5 — the ONLY place that knows UE5's coordinate system.

UE5 is left-handed, Z-up, centimetres; canonical space is right-handed, Z-up,
metres. `adapter.py` is the single boundary that converts between them (the §17.5
proof); `bridge.py` (Task B5) speaks UE5 Remote Control HTTP on top of it.
"""
