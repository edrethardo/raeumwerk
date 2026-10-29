"""Parametrisiertes Simulationsmodell igus ReBeL 6 DOF + 7. Achse + Parallelgreifer.

* ``config``: liest ``config/robot.yaml``
* ``urdf_gen``: erzeugt die URDF (``python -m rebel_model.urdf_gen``)
* ``kinematics``: FK/IK aus der URDF (numpy)
* ``collision``: Selbstkollision auf den Kollisionsquadern (numpy)
"""
