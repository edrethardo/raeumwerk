"""Glas-Greifdemo: Szene, Ablaufplanung und Bewertung (ohne Simulator).

* ``szene``     liest ``config/scene.yaml``
* ``plan``      Zustandsmaschine Vorposition -> ... -> Rueckzug, IK je Wegpunkt
* ``bewertung`` Erfolg/Fehlergruende eines Versuchs aus den Messwerten

Der Simulator-Teil (Newton) steht in ``scripts/demo_greifen.py``.
"""
