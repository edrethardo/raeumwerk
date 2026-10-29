# Architektur

Wie Räumwerk-Experimente headless laufen und wie Simulation und spätere echte
Hardware getrennt sind. Was davon belegt ist: `docs/STATUS.md`. Start:
`docs/START.md`.

## 1. Überblick

```
experimente/<name>.yaml ──► raeumwerk run ──► Simulator je Versuch ──► Run-Verzeichnis
   (Szene, Roboter,           (raeumwerk.lauf)   (raeumwerk.simulator)    manifest.json
    Parameterraum, N)              │                    │                 versuche/versuch-NNN.json
                                   │            greifen.plan (IK, Ablauf) messwerte.csv
                                   │                    │                       │
                                   │      Schnittstellen raeumwerk.backends     ▼
                                   │      RobotBackend / GripperBackend /  raeumwerk report
                                   │      CameraBackend                    raeumwerk next
                                   │        ├─ sim: Newton (greifen.sim_newton)   │
                                   │        └─ hardware: Stub, bewegt nichts      ▼
                                   │                                     vorschlag.yaml ──► nächster run
scripts/submit_gpu.sh ─────────────┘
  (externe GPU-Warteschlange oder GPU-Lock, Stücke ≤ 30 min, eigene Unit je Stück)
```

Steuerung nur über Kommandozeile, Dateien und die GPU-Warteschlange. Es gibt
**keine Netzwerkschnittstelle**: kein Dienst, kein Port, keine Remote-API. Ein
Agent oder Auftragssystem startet `scripts/submit_gpu.sh`, wartet auf den
Exit-Code und liest `manifest.json` bzw. `bericht.json`.

| Teil | Datei | braucht |
|---|---|---|
| Kommandozeile `raeumwerk run/report/next` | `raeumwerk/cli.py`, `scripts/raeumwerk` | – |
| Experimentdatei, Parameterraum, Versuchsliste, Konfig-Hash | `raeumwerk/experiment.py` | pyyaml (nur `run`) |
| Run-Verzeichnis, Manifest, Checkpoints, Stücke | `raeumwerk/lauf.py` | – |
| Versuch ausführen (Newton bzw. Testdouble) | `raeumwerk/simulator.py` | Newton/Warp/numpy |
| Bericht und Parametervorschlag | `raeumwerk/auswertung.py` | nur Standardbibliothek |
| Schnittstellen, Sim-Implementierung, Hardware-Stub | `raeumwerk/backends/` | – |
| Newton-Versuchslauf (Modell, Regelschleife, Messung) | `greifen/sim_newton.py` | Newton/Warp/numpy |
| Planung, Bewertung, Szene | `greifen/plan.py`, `greifen/bewertung.py`, `greifen/szene.py` | numpy, pyyaml |
| Job einreichen (Warteschlange/Lock) | `scripts/submit_gpu.sh` | ssh, rsync |
| Job auf dem GPU-Rechner (Log, Exit-Code) | `scripts/gpu_job.sh` | systemd (user) |

## 2. Experimentdatei

Beispiel `experimente/beispiel.yaml`: Name, `backend` (`newton` oder
`attrappe`), Szene und Roboter (Pfade im Repo), Anzahl `versuche`, `seed` der
Stichprobe und der Parameterraum. Jeder Parameter ist fest (`0.2` oder
`{fest: 0.2}`), gleichverteilt (`{bereich: [a, b]}`) oder eine Auswahl
(`{werte: [...]}`). Nicht genannte Parameter behalten den Wert aus
`config/scene.yaml`.

| Parameter | Wirkung | erlaubt |
|---|---|---|
| `glas_x_m`, `glas_y_m` | Startlage des Glases | auf dem Tisch |
| `greif_versatz_x_m`, `greif_versatz_y_m`, `greif_versatz_z_m` | Greifpunkt neben/über der Glasmitte | ±10 cm bzw. −3…+5 cm |
| `reibung_finger`, `reibung_glas`, `reibung_tisch` | Reibwerte (je Paar gilt der größere) | 0…2 |
| `greifkraft_n` | Greifkraft je Finger | 0,5…50 N (Antriebsgrenze) |

Die Versuchsliste ist deterministisch (`random.Random(seed)`) und steht im
Manifest, damit ein fortgesetzter Lauf dieselben Versuche fährt. Jeder Versuch
läuft in einer frisch aufgebauten Simulation (parallele Welten sind in Newton
1.6.1 mit diesem Modell fehlerhaft, `docs/greifdemo.md` §7).

## 3. Run-Verzeichnis und Manifest

`raeumwerk run <experiment.yaml> --run-dir <name>` schreibt nach
`$RAEUMWERK_EXPERIMENT_RUNS/<name>/` (Standard
`$RAEUMWERK_HOME/runs/experimente`; ein Pfad mit `/` wird unverändert genommen):

| Datei | Inhalt |
|---|---|
| `manifest.json` | siehe unten |
| `experiment.yaml` | Kopie der Experimentdatei |
| `versuche/versuch-NNN.json` | Ergebnis und Messwerte eines Versuchs, zugleich der Checkpoint (atomar geschrieben) |
| `messwerte.csv` | eine Zeile je Versuch: Erfolg, Gründe, Zielfehler, Kippung, Hub, Durchdringungen, Glasgeschwindigkeit, Wandzeit, Parameter |
| `bericht.json`, `bericht.md` | von `raeumwerk report` |
| `vorschlag.yaml` | von `raeumwerk next` |

Felder in `manifest.json`:

| Feld | Bedeutung |
|---|---|
| `schema` | `raeumwerk-run/1` |
| `run`, `name`, `erstellt`, `letzte_aenderung` | Name des Run-Verzeichnisses, des Experiments, Zeitstempel (UTC) |
| `experiment_datei` | Pfad relativ zum Repo (nie ein Rechnerpfad) |
| `git` | `sha`, `dirty` (Arbeitsstand weicht vom Commit ab), `quelle` (`git` oder Datei `REVISION` einer Kopie ohne `.git`) |
| `git_spaeter` | nur wenn ein späteres Stück auf einem anderen Stand lief |
| `konfig_hash` | sha256 über das geparste Experiment und die Bytes von Szene und Roboter |
| `dateien_sha256` | sha256 von Experiment-, Szenen- und Roboterdatei |
| `experiment`, `backend`, `seed`, `parameter_standard` | aufgelöste Experimentdatei, Werte der Szene für alle Parameter |
| `versuche_geplant`, `versuche_plan` | Anzahl und Parameter jedes Versuchs |
| `versionen` | Newton, Warp, MuJoCo, MuJoCo-Warp, numpy, Python, raeumwerk, Plattform |
| `device` | z. B. `cuda:0` oder `cpu` |
| `status` | `laeuft`, `unvollstaendig`, `fertig`, `abgebrochen`, `fehler` |
| `versuche_fertig`, `erfolge` | Zähler |
| `stuecke` | je Aufruf: Nummer, Start, Ende, Budget, gefahrene Versuche, Wandzeit, Grund für das Ende |

**Fortsetzen und Stücke.** Derselbe Aufruf mit demselben `--run-dir` fährt nur
die Versuche, deren `versuch-NNN.json` fehlt. Ein anderer Konfig-Hash im selben
Verzeichnis wird abgelehnt (Exit 2). `--max-minuten` (≤ 30, Standard
`stueck.max_minuten`) begrenzt ein Stück: Vor jedem Versuch wird mit dem
längsten bisherigen Versuch geschätzt, ob er noch passt; mindestens ein
Versuch je Stück.

Exit-Codes von `run`: 0 fertig, 1 Fehler, 2 Aufruf/Konfiguration, 3 Stück zu
Ende (weiter), 143 abgebrochen (SIGTERM: fertige Versuche bleiben, der
laufende geht verloren).

## 4. Auswertung

`raeumwerk report <run>`: Erfolge und Quote, Kollisionen (Arm/Tisch, Finger zu
tief im Glas, je mit Höchstwert), Fehlergründe mit Anzahl, jeder Fehlversuch
mit Parametern, für jeden variierten Parameter die Spanne der Erfolge und der
Fehlversuche. Schreibt `bericht.json` und `bericht.md`.

`raeumwerk next <run>`: neue Experimentdatei aus einfachen Regeln, kein
Training (Reihenfolge in `raeumwerk/auswertung.py`):

1. Bereich mit ≥ 2 Erfolgen → auf kleinsten bis größten Erfolgswert einengen.
2. Bereich mit genau 1 Erfolg → halbe Breite um ihn.
3. Ohne Erfolg nach dem häufigsten Grund, für den es eine Regel gibt
   (`nicht_am_ziel` ist meist nur Folge): `nicht_gegriffen` → Greifpunktversatz
   zur Mitte halbieren; `gefallen` → untere Grenze von Greifkraft/Reibung auf
   die Mitte; `kollision_arm_tisch` → 5 mm höher greifen; `durchdringung` →
   obere Grenze der Greifkraft auf die Mitte; `planung_fehlgeschlagen` →
   Glaslage zum Szenenwert halbieren.
4. Auswahl-Parameter: nur Werte mit Erfolg behalten.
5. Sonst Zufallssuche im gleichen Raum.

Immer Seed + 1, Name mit Folgenummer (`-n1`, `-n2`, …), `abgeleitet_von` und
eine `begruendung` je Regel. Der Vorschlag ist selbst eine gültige
Experimentdatei.

## 5. GPU-Rechner: `scripts/submit_gpu.sh`

Läuft auf dem steuernden Rechner. Jedes Stück wird ein eigener Job mit eigenem
Namen `raeumwerk-<schritt>-<UTC-Zeit>-s<n>` und läuft auf dem GPU-Rechner als
`systemd-run --user --collect --wait --unit=<name> -p RuntimeMaxSec=<t·60>`.
Die Laufzeitgrenze (`-t`, höchstens 30 min) beendet die ganze Unit mit allen
Kindprozessen; `scripts/gpu_job.sh` schreibt Log und Exit-Code nach
`$REMOTE_JOBS/<name>.{log,rc}`.

| Weg | gewählt, wenn | Ablauf |
|---|---|---|
| externe GPU-Warteschlange | `GPU_SUBMIT_CMD` gesetzt | `$GPU_SUBMIT_CMD <name> $GPU_SUBMIT_ARGS -- '<Befehl>'`; die Warteschlange hält den GPU-Lock nur während des Jobs; das Skript wartet per ssh auf `<name>.rc` |
| GPU-Lock (Fallback) | sonst `GPU_LOCK` | `acquire` ohne Warten alle `POLL_S` s (höchstens `WAIT_MAX_S`), ssh mit dem Befehl, `release` per trap |

Mit `--weiter-rc 3` reicht das Skript nach einem Stück mit Exit 3 das nächste
ein. Dazwischen ist die Karte frei: Beim Lock-Weg nach `GAP_S` Sekunden Pause,
bei der Warteschlange wird das nächste Stück erst nach dem Ende des vorigen
eingereicht, wartende fremde Jobs kommen zuerst dran.

**Abbruch** (SIGTERM/SIGINT an `submit_gpu.sh`): eigenen Eintrag in der
Warteschlange zurückziehen (`GPU_CANCEL_CMD <name>`, falls gesetzt), eigene
Unit stoppen (`systemctl --user stop <name>`, beendet alle Prozesse des Jobs),
ssh beenden, Lock freigeben; Exit 143. Fremde Jobs und Locks werden nie
angefasst. Belegt mit Fake-Lock, Fake-Warteschlange und Fake-ssh in
`tests/test_submit_gpu.py`.

## 6. Simulation und Hardware

Der Ablauf (`greifen.plan`) erzeugt eine Soll-Trajektorie. Ausgeführt wird sie
nur über drei Schnittstellen (`raeumwerk/backends/basis.py`):

| Schnittstelle | Methoden | Simulation (`backends/sim.py`) | Hardware (`backends/hardware.py`) |
|---|---|---|---|
| `RobotBackend` | `gelenknamen`, `gelenke`, `setze_soll(q, qd)`, `halt` | schreibt PD-Sollwerte der 6 Gelenke und der 7. Achse in den Newton-Lauf | Stub: verweigert jede Bewegung |
| `GripperBackend` | `oeffnung`, `setze_soll(finger_q, finger_qd)` | beide Finger mit eigenem Antrieb, gleiches Ziel | Stub: verweigert jede Bewegung |
| `CameraBackend` | `objektlage(name)`, `bild` | ideale Wahrnehmung: wahre Lage aus dem Modell, keine Bilder | Stub: nicht angebunden |

Die Regelschleife in `greifen/sim_newton.py` setzt Sollwerte nur über
`SimRobot`/`SimGripper` und liest die Endlage des Glases über `SimCamera`.

**Hardware-Stub.** Kein Treiber, keine Verbindung, kein Port. `setze_soll`
wirft immer `BewegungVerweigert`: ohne Freigabe mit „keine Freigabe“, mit
Freigabe mit „Hardware-Stub ohne Treiber“. Die Freigabe ist eine Konfiguration
mit `hardware.bewegung_freigegeben: true` (genau der Wahrheitswert, kein „ja“
oder `1`) und einem nicht leeren `hardware.freigabe_durch`; fehlende,
unlesbare oder unvollständige Dateien gelten als „keine Freigabe“. `halt()`
ist immer erlaubt. Ein späterer Treiber muss dieselbe Prüfung vor jeder
Bewegung behalten.

## 7. Phase 5: geplante Bausteine (nicht umgesetzt)

Nichts aus diesem Abschnitt ist gebaut oder getestet. Die Liste ordnet nur ein,
wo die Teile an die Schnittstellen oben andocken.

| Baustein | Plan | Andockpunkt |
|---|---|---|
| Spülmaschine | Szene mit Korb, Geschirrteilen und Tür statt Tisch und Glas; Ablauf je Teil (greifen, aus dem Korb heben, ablegen) | neue Szene unter `config/`, Planer je Objektart, Parameter im Experiment |
| RealSense D405 Eye-in-Hand | Tiefenkamera am Greifer; Hand-Auge-Kalibrierung; Objektlage aus Tiefenbild statt aus dem Modell | `CameraBackend` (Hardware); in der Simulation zuerst ein gerendertes Kamerabild für denselben Code |
| Jetson AGX Orin | Rechner am Roboter für Wahrnehmung und Ablauf; die Simulation bleibt auf dem GPU-Rechner | gleiche CLI und Run-Verzeichnisse, Steuerung weiter ohne eigene Netzwerkschnittstelle |
| echter ReBeL | Treiber für Arm, 7. Achse und Greifer über die Schnittstelle der Robotersteuerung (Protokoll noch zu prüfen) | `RobotBackend`/`GripperBackend` (Hardware) ersetzen den Stub |
| Sicherheitsprüfungen | vor jeder Bewegung: Freigabe, Arbeitsraum- und Geschwindigkeitsgrenzen, Kollisionsprüfung des Plans (wie in der Planung), derselbe Plan vorher als Trockenlauf in der Simulation, reduzierte Geschwindigkeit beim ersten Lauf, Not-Halt der Robotersteuerung bleibt die oberste Instanz | Prüfschicht zwischen Ablauf und Hardware-Backend; Freigabe wie im Stub |
