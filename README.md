# Räumwerk

Ein Open-Source-Framework, mit dem ein Roboter eine Spülmaschine selbstständig ein- und ausräumt. Ziel des ersten Meilensteins ist ein simulierter igus ReBeL (6 DOF) mit siebter Linearachse und Parallelgreifer, der ein Glas greift und an anderer Stelle wieder abstellt.

- Umgebung und Smoke-Test: `docs/umgebung.md`
- Robotermodell: `docs/robotermodell.md`
- Greifdemo starten (frischer Klon, ein Befehl): `docs/START.md`; Details: `docs/greifdemo.md`
- Was nachgewiesen ist und was experimentell: `docs/STATUS.md`

## Drittquellen

- Die Maße und Grenzen des ReBeL stammen aus dem öffentlichen igus-Datenblatt. Das Datenblatt selbst liegt nicht im Repo, `scripts/fetch_assets.sh` lädt es herunter und prüft die Prüfsumme.
- Die Achsrichtungen und einzelne Zahlenwerte sind aus CommonplaceRobotics/iRC_ROS übernommen (Apache-2.0). Dateien aus diesem Projekt sind nicht enthalten.
