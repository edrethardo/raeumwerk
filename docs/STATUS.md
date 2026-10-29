# Status Räumwerk

Stand: 2026-10-29. „nachgewiesen“ steht nur da, wo ein Test oder Log es zeigt.
Laufpfade sind relativ zu `RAEUMWERK_RUNS` bzw. `RAEUMWERK_HOME` auf dem
jeweiligen Rechner (siehe `docs/umgebung.md`).

| Funktion | Status | Beleg (Testname, Logpfad, Zahl) |
|---|---|---|
| Bestandsaufnahme `scripts/check_env.sh` (Hauptrechner) | nachgewiesen | Ausgabe in `docs/umgebung.md` §1; kein Rechnername/IP in der Ausgabe |
| Installation Isaac Lab 3.0.0 + Newton 1.6.1 (pip/uv, ohne Isaac Sim) | nachgewiesen | `logs/install-isaaclab.log`, venv 7,4 GB |
| Installation Isaac Sim 6.2.0.0 (pip/uv) | nachgewiesen | `logs/install-isaacsim.log`, `logs/fetch-wheels.log`, venv 22–23 GB |
| Smoke Newton headless, Hauptrechner | nachgewiesen, 3/3 ok | `newton-20261029T0152{22,28,34}Z.json`: 5,6–5,8 s, RAM 491 MiB, VRAM 318 MiB, Endhöhe 0,04999 m |
| Smoke Isaac Sim (PhysX) headless, Hauptrechner | nachgewiesen, 3/3 ok | `isaacsim-20261029T015240Z.json` (107,8 s, RAM 11 154 MiB, Erststart), `…015428Z.json` (9,0 s, 5 836 MiB), `…015437Z.json` (8,3 s, 5 852 MiB); VRAM 1,6–1,8 GiB; Endhöhe 0,05000 m |
| Kein Listener außerhalb localhost während der Läufe | nachgewiesen | `ss-newton-20261029T015222Z.txt`, `ss-isaacsim-20261029T015240Z.txt`; im JSON `listeners_non_local_new_during_run: []` |
| `/` hat nach der Installation ≥ 35 GB frei | nachgewiesen | beides nach der Installation gemessen: `df -BG /` zeigt 45G (GiB, binär, auf ganze GiB aufgerundet); JSON `root_free_gb_after`: 47,3 (GB, dezimal) = 44,1 GiB. Der Unterschied ist Einheit und Rundung, kein Messfehler |
| `tests/test_smoke.py` ohne Backend sauber übersprungen | nachgewiesen | `uvx -p 3.10 pytest -q tests` und `uvx -p 3.14 pytest -q tests`: je 19 passed, 2 skipped (die 2 echten Backendtests) |
| `scripts/remote_smoke.sh`: ungültiges Backend → Exit 2, Lock-Wartefrist → Exit 4, Lock-Freigabe per trap | nachgewiesen | `test_remote_smoke_rejects_invalid_backend`, `test_remote_smoke_gives_up_after_wait_max`, `test_remote_smoke_runs_ssh_and_releases_lock` (Fake-Lock, Fake-ssh) |
| `tests/test_smoke.py` mit Backend (`RAEUMWERK_RUN_GPU_SMOKE=1`) | experimentell | Code vorhanden, unter GPU-Lock noch nicht über pytest ausgeführt (die Smokes liefen über `run_smoke_local.sh`) |
| Isaac Sim auf dem zweiten Rechner (Laptop, 12 GB VRAM, 31 GB RAM) | blockiert/läuft | Erster Lauf endete mit Exit 10: die Installation überschritt die 2-h-Frist (langsamer Download). Ein zweiter Lauf mit längerer Frist läuft; Ergebnis steht aus (`docs/umgebung.md` §5) |
| Isaac Sim unter Last (paralleler fremder GPU-Job, 16 GB RAM) | experimentell | nicht gemessen: die Läufe hatten die Karte und den RAM exklusiv; Erststart-Spitze 11,2 GB RAM lässt neben einem parallelen Job kaum Platz |
| Isaac Lab Tasks/Training mit Newton | experimentell | nur `import isaaclab` + direkte Newton-API im Smoke, kein Isaac-Lab-Task gestartet |
| Agent Skills / MCP | bewertet, nicht eingesetzt | `docs/bewertung-agent-tools.md` |
| ReBeL-Modell (6 DOF + 7. Achse + Parallelgreifer) aus `config/robot.yaml`, Quellen/Lizenzen | nachgewiesen | `docs/robotermodell.md`; `test_config_every_value_has_source`, `test_urdf_structure` |
| Referenzunterlagen per `scripts/fetch_assets.sh` mit sha256 (nicht im Repo) | nachgewiesen | 4/4 Dateien ok auf beiden Rechnern; `test_cpr_numbers_in_fetched_asset` grün mit `RAEUMWERK_ASSETS` |
| Kinematiktests ohne GPU | nachgewiesen | `uvx -p 3.10 … pytest -q tests`: 44 passed, 3 skipped; FK 6 Datenblattposen < 1 µm; IK-Rundlauf 60 Posen max. 0,0099 mm / 0,001°, mit 7. Achse 50 Punkte < 1 mm; Hülle 660 mm; FK gegen iRC_ROS max. 14,7 mm (andere Längen, erklärt) |
| Selbstkollision erkannt (CPU-Quadertest) | nachgewiesen | `test_self_collision_detected` (2 Posen innerhalb der Grenzen), `test_self_collision_free_poses` (6 Posen ohne Treffer) |
| Newton: Modell laden, Massen (8,2 kg + 1,5 kg Nutzlast), Grenzen, Mimic | nachgewiesen | `runs/rebel/20261029T025400Z/rebel.json` (RTX 3090, Newton 1.6.1, warp 1.17.0, MuJoCo-Warp 3.12.0): Grenzenfehler 0, 1 Mimic-Constraint |
| Newton: FK gleich der numpy-FK | nachgewiesen | gleicher Lauf: 55 Posen, max. 0,34 µm |
| Newton: alle 7 Achsen + Greifer gefahren, Ziel mit Toleranz erreicht | nachgewiesen | gleicher Lauf, 16 Ziele: Drehgelenke max. 0,18° (J2 unter Last), Achse 7 max. 0,0001 mm, Finger < 0,001 mm, gespiegelter Finger 0,38 mm hinter dem Ziel (< 1 mm); 78 s Simzeit in 246 s Wandzeit, dt 2 ms |
| Newton: Selbstkollision an, selbstschneidende Pose erkannt | nachgewiesen | gleicher Lauf: 4 freie Posen ohne Durchdringung, 2 Schnittposen mit 3 bzw. 11 Paaren (bis 81 mm tief), deckungsgleich mit dem CPU-Test |
| Kein neuer Listener außerhalb localhost während des Newton-Laufs | nachgewiesen | `runs/rebel/20261029T025400Z/ss-ltnp.txt`: nur die schon vorher offenen Ports 22 und 8000 (fremde Dienste) |
| Modellwerte Momentgrenze 40 Nm, Massenaufteilung, Greifer-/Schienenmaße | experimentell | Annahmen in `config/robot.yaml`, am echten Gerät nachzumessen |
