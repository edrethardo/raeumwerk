"""Simulierte Wahrnehmung fuer den Griff im Oberkorb: Ensenso (fest am Mast) fuer die Grobpose,
D405 am Greifer fuer die Feinpose, mit Rauschen und Glasfehlern; Schaetzer fuer Glas und Teller.

    strahlen   Primitive (Quader, Zylinder), Strahlschnitt, Kameramodelle
    sensor     Fehlermodell (Rauschen ~ d^2, Ausfall, Glas: fehlt / Durchblick / Reflex, Naesse, Kanten)
    schaetzer  Zylinderfit auf der Silhouette (Glas), Ebenen- und Kreisfit (Teller), Plausibilitaet
    griffpose  Szene -> Aufnahmen -> geschaetzte Griffpose (oder Abbruch mit Grund)
"""
