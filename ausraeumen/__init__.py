"""Ausraeumen: Glaeser kopfueber aus dem Oberkorb, umdrehen, aufrecht abstellen.

* ``konfig``     laedt ``config/ausraeumen.yaml`` (+ Maschine und Schienenlage)
* ``geometrie``  Kollisionspruefung mit beweglichen Glaesern (auch gedreht)
* ``plan``       Ablaufplanung: Griff von oben, Zwischenablage, Seitgriff, Umdrehen
* ``bewertung``  Bewertung je Glas und Gesamtbericht
* ``sim_newton`` Newton-Lauf (braucht Newton/Warp)

Erklaerung: ``docs/ausraeumen.md``.
"""
