"""Raeumwerk: Experimente headless starten, auswerten, Sim/Hardware trennen.

* ``raeumwerk.cli``        ``raeumwerk run|report|next`` (``python -m raeumwerk``)
* ``raeumwerk.experiment`` Experimentdatei laden, Parameterraum, Versuchsliste
* ``raeumwerk.lauf``       Run-Verzeichnis, Manifest, Checkpoints, Stuecke
* ``raeumwerk.auswertung`` Bericht und naechster Parametervorschlag
* ``raeumwerk.backends``   Schnittstellen Roboter/Greifer/Kamera, Sim und Hardware-Stub

Architektur: docs/architektur.md.
"""
__version__ = "0.1.0"
