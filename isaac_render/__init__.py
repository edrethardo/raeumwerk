"""Isaac-Sim-RTX-Rendering der Raeumwerk-Szenen (Replay von Newton-Aufzeichnungen).

Zwei Teile:

* ``auftrag``/``geometrie`` (nur numpy, pyyaml): bauen aus einer Aufzeichnung
  (``greifen/aufzeichnung.py``) bzw. aus der statischen Spuelmaschinen-Szene
  einen Renderauftrag (npz): Posen je Bild, statische Koerper mit Material,
  Kamera. Testbar ohne Isaac Sim.
* ``scripts/isaac_render.py`` (Python des Isaac-Sim-venv): baut daraus die
  USD-Szene (Roboter ueber den URDF-Importer bzw. urdf-usd-converter),
  setzt die Posen Bild fuer Bild (Physik aus) und rendert headless mit RTX
  ueber den Replicator-RGB-Annotator.
"""
