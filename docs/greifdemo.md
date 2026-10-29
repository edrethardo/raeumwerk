# Greifdemo: Glas greifen, anheben, versetzen, absetzen

Kleinster funktionierender Greifvorgang mit dem ReBeL-Modell aus
`docs/robotermodell.md` in Newton (MuJoCo-Warp-Löser). Start: `docs/START.md`.
Belegte Zahlen: `docs/STATUS.md`.

| Teil | Datei |
|---|---|
| Szene, Kontakt- und Greifparameter, Toleranzen | `config/scene.yaml` |
| Zustandsmaschine und IK-Wegpunkte | `greifen/plan.py` |
| Bewertung und Fehlergründe | `greifen/bewertung.py` |
| Newton-Lauf, Messung | `greifen/sim_newton.py` (über die Schnittstellen aus `raeumwerk/backends/`, `docs/architektur.md`) |
| Demo, JSON | `scripts/demo_greifen.py` |
| Runner (ein Befehl), Abnahmejob | `scripts/run_greifen.sh`, `scripts/job_greifen.sh` |
| Tests (ohne GPU und mit Backend) | `tests/test_greifen.py` |

## 1. Szene

Weltkoordinaten sind die der Schiene: Ursprung am Schienenanfang auf dem Boden,
+x entlang der Schiene, +z nach oben. Der Roboterfuß steht bei
x = 0,15 m + Achswert.

| Objekt | Form | Werte |
|---|---|---|
| Boden | Ebene | Reibung 0,5 |
| Tisch | Quader, statisch | x 0,20–1,20 m, y 0,22–0,62 m, Oberkante 0,16 m, Reibung 0,5 |
| Glas | Vollzylinder, frei | Ø 75 mm, Höhe 110 mm, 250 g (Dichte daraus, Modell: 0,2500 kg), Reibung 0,6 |
| Start / Ziel | Glasmitte | (0,55; 0,35) → (0,85; 0,33): 30 cm entlang der Schiene, 2 cm quer |

Die Tischhöhe folgt aus der Reichweite: Der Greifer greift senkrecht von oben,
Gelenk 5 darf höchstens 95° (Datenblatt). Mit dem 10-cm-Hub über einem höheren
Tisch würde Gelenk 5 an die Grenze laufen (IK-Raster in der Entwicklung: bei
y = 0,40 m war TCP-Höhe 0,40 m nicht mehr erreichbar). Glas als Zylinder ohne
Transparenz-Rendering; ein echtes Glas ist hohl (etwas größere Trägheit), für
Greifen und Abstellen unerheblich.

## 2. Kontakt und Reibung

- Alle Paare: weiche Kontakte mit ke = 2500, kd = 100. Newton rechnet das für
  MuJoCo in solref = (0,02 s; 1,0) um, das ist der MuJoCo-Standard.
- Reibwerte je Form: Finger 1,0 (Gummibelag), Glas 0,6, Tisch und Boden 0,5.
  Je Paar gilt der größere Wert (MuJoCo-Regel bei gleicher Priorität), also
  Finger-Glas 1,0 und Glas-Tisch 0,6. Drehreibung um die Normale 0,01 m.
- Löser: MuJoCo-Warp über Newton, Newton-Kollisionspipeline
  (`use_mujoco_contacts=False`), elliptischer Reibkegel, impratio 10,
  50 Iterationen, dt = 2 ms.
- Die Werte sind Tabellen-Größenordnungen, keine Messungen (`config/scene.yaml`,
  Quelle `reibung_tabelle`).

## 3. Greifer

- Öffnung 5–105 mm (Datenblatt), zwei prismatische Finger 20 × 10 × 60 mm
  (Quader, Annahme). Der TCP liegt auf halber Fingerlänge, 80 mm vor dem Flansch.
- Beide Finger haben einen eigenen PD-Antrieb mit demselben Ziel
  (ke = 2000 N/m, kd = 100 N s/m). In der URDF folgt der rechte Finger dem
  linken per Mimic; nur mit dieser weichen Kopplung lief der rechte Finger unter
  Last hinterher und schob das Glas um 2 mm zur Seite (gemessen), deshalb der
  zweite Antrieb.
- **Greifkraft begrenzt:** Das Schließziel liegt 10 mm innerhalb der
  Glasoberfläche, also 2000 N/m × 0,01 m = 20 N je Finger. Die Antriebsgrenze
  aus `config/robot.yaml` ist 50 N. Zum Halten reichen schon
  2 × 1,0 × 20 N = 40 N Reibkraft gegen 2,45 N Gewicht.
- Gemessen beim Greifen: Öffnung 71,3 mm bei 75 mm Glas, die Finger stecken je
  1,9 mm im Glas. Das ist die Nachgiebigkeit der weichen Kontakte; Grenze in der
  Bewertung 3 mm. Das Glas wird nicht weggeschleudert: höchste
  Glasgeschwindigkeit 0,18 m/s, das ist die geplante Fahrgeschwindigkeit.
- Schwerkraftkompensation der Armglieder (`mujoco:gravcomp`), wie sie die
  Robotersteuerung auch macht. Ohne sie wären die Folgefehler größer.

## 4. Ablauf (Zustandsmaschine)

Der Greifer zeigt senkrecht nach unten, die Finger schließen entlang der
Schiene. Die 7. Achse folgt der x-Lage des TCP: Der Fuß steht über dem Glas, die
sechs Armgelenke lösen per IK den Rest (`rebel_model.kinematics`, gedämpfte
kleinste Quadrate, fester Seed). Gerade TCP-Wege werden in Wegpunkte von
höchstens 1 cm zerlegt. Jede Phase hat ein ruckarmes Zeitprofil. Die Dauer folgt
aus 60 % der Datenblattgeschwindigkeiten (Arm 45°/s, Achse 0,3 m/s, Greifer
0,05 m/s). Die Antriebe fahren das Positionsziel mit Geschwindigkeitsvorsteuerung.

| Phase | Was | Zeit im Demo-Lauf (s) |
|---|---|---|
| start | Ruhepose, Greifer offen | 0,00–0,30 |
| vorposition | TCP 10 cm über den Greifpunkt | 0,30–1,20 |
| anfahrt | senkrecht hinab auf 88 mm über dem Tisch | 1,20–2,53 |
| greifen | Finger schließen, 0,4 s halten | 2,53–4,49 |
| anheben | 10 cm senkrecht hoch | 4,49–5,82 |
| verfahren | 30 cm über die 7. Achse, 2 cm quer mit dem Arm | 5,82–8,94 |
| absetzen | hinab bis 2 mm über die Greifhöhe | 8,94–10,25 |
| loesen | Finger öffnen, 0,4 s halten | 10,25–12,21 |
| rueckzug | 10 cm senkrecht hoch | 12,21–13,54 |
| nachlauf | 1 s Ruhe, dann bewerten | 13,54–14,54 |

Vor dem Lauf prüft die Planung jeden Wegpunkt auf Gelenkgrenzen, Selbstkollision
(Quadertest aus `rebel_model.collision`) und Abstand zum Tisch.

## 5. Bewertung je Versuch

Gemessen wird alle 10 ms: Glaslage und -geschwindigkeit, Kontakte Roboter↔Tisch
und Finger↔Glas (Separation wie Newtons `contact_surface_separation`), Folgefehler
der Gelenke. Am Ende entscheidet `greifen/bewertung.py`:

| Grund | Bedingung für „bestanden“ |
|---|---|
| `planung_fehlgeschlagen` | IK, Grenzen, Selbstkollision und Tischabstand im Plan in Ordnung |
| `simulation_instabil` | keine NaN-Werte |
| `nicht_gegriffen` | Glasmitte beim Anheben/Verfahren ≥ 8 cm über dem Start |
| `gefallen` | zwischen Ende „anheben“ und Beginn „absetzen“ nie unter 8 cm Hub; am Ende Glasmitte ±5 mm auf Standhöhe |
| `gekippt` | Kippung am Ende < 10° |
| `nicht_am_ziel` | Abstand der Glasmitte zum Ziel in x/y ≤ 1 cm |
| `kollision_arm_tisch` | Roboter dringt nie mehr als 0,1 mm in den Tisch ein |
| `durchdringung` | Finger dringen ≤ 3 mm ins Glas ein |
| `weggeschossen` | Glas nie schneller als 1 m/s |

JSON je Versuch (`versuch-NN.json`) mit allen Kriterien, Werten und Grenzen,
dazu `zusammenfassung.json` mit Erfolgsquote und Häufigkeit der Gründe.

## 6. Messwerte (Abnahmelauf, RTX 3090)

Lauf `runs/greifen/20261029T043004Z/` unter `RAEUMWERK_HOME` auf dem
GPU-Rechner (Stand 41d1075), Newton 1.6.1, Warp 1.17.0, MuJoCo-Warp 3.12.0,
`scripts/job_greifen.sh` über die GPU-Warteschlange, 12 min 35 s für alles.

| Lauf | Ergebnis |
|---|---|
| Demo (fester Seed) | Erfolg. Endlage (0,8502; 0,3291) bei Ziel (0,85; 0,33): **0,88 mm** Fehler; Kippung am Ende **0,10°**, höchstens 2,17° unterwegs; Hub 99,9 mm; Tisch nie berührt; **14,54 s** Ablauf (Simzeit), 28,6 s Wandzeit |
| Variation, 20 Versuche, Start ±2 cm (Seed 4711) | **20/20 Erfolg**; Zielfehler 0,85–0,90 mm (Mittel 0,87 mm); Kippung am Ende ≤ 0,103°, unterwegs ≤ 2,18°; Fingerdurchdringung ≤ 1,88 mm; Glas ≤ 0,18 m/s; je Versuch 14,1–15,0 s Simzeit, 28–30 s Wandzeit |
| Negativtest (Greifpunkt 6 cm neben der Glasmitte) | als Fehlversuch erkannt: `nicht_gegriffen` (Hub −0,1 mm) und `nicht_am_ziel` (300,7 mm); Glas blieb stehen (Kippung 0,10°) |
| Backend-pytest im selben Job | `tests/test_greifen.py`: 33 passed (inkl. Demo- und Negativlauf) |
| CPU (Weg A, frischer Klon) | gleiches Ergebnis wie GPU: 0,88 mm, Kippung 0,10°; 124 s Wandzeit |

Folgefehler der Antriebe während der Fahrt (Maximum über alle Läufe): Achse 7
3,6 mm, Gelenke 2/3/5 bis 0,81°, die übrigen < 0,01°. Am Phasenende sind sie
abgebaut.

## 7. Grenzen und Annahmen

- Die Glaslage ist der Planung genau bekannt (keine Kamera, kein
  Wahrnehmungsfehler). Die Variation zeigt deshalb Reichweite und Greifen über
  ±2 cm, nicht die Robustheit gegen eine falsch geschätzte Glaslage. Der
  Zielfehler von etwa 0,9 mm ist fast ganz systematisch (y-Richtung).
- Reibwerte, Kontaktsteifigkeit, Fingermaße und Greifkraft sind Annahmen
  (`src: annahme` bzw. Tabellenwerte), am echten Greifer nachzumessen.
- Kollisionsgeometrie nur aus Quadern (Roboter) und einem Zylinder (Glas).
- **Ein Versuch, eine Simulation.** Mehrere Versuche als parallele Welten in
  einer Newton-Simulation wurden ausprobiert und verworfen: Ab Welt 1 liefen die
  Gelenke schon im ersten Schritt weg (über die Grenzen, das Glas fiel durch
  den Tisch), Welt 0 war korrekt. Das Verhalten war gleich mit Newton- und
  MuJoCo-Kontakten, mit und ohne Mimic-Kopplung, mit `begin_world` und
  `add_world`. Ein kleines Modell aus Glas und Roboter ohne Ablauf lief in
  beiden Welten richtig; die Ursache ist nicht gefunden. Nacheinander kosten
  20 Versuche etwa 10 min auf der GPU.
- Bilder/Video: nicht umgesetzt (siehe `docs/START.md` §6).
