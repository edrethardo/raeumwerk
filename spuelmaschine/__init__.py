"""Parametrische 60-cm-Spuelmaschine mit Koerben, Glashaltern und Ablage.

- ``masse``: laedt ``config/spuelmaschine.yaml`` (jede Zahl mit Quelle/Annahme)
- ``geometrie``: erzeugt einfache Kollisionskoerper (Quader, Zylinder)
- ``erreichbarkeit``: Rastersuche der Schienenlage mit der vorhandenen IK
- ``stabilitaet``: Newton-Lauf, Glaeser liegen ruhig im Korb (braucht Newton)

Erklaerung: docs/spuelmaschine.md.
"""
