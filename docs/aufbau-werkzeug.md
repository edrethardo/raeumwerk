# Erreichbarkeitswerkzeug `raeumwerk aufbau`

> **Vorgabe (Owner, 29.10.2026): Räumwerk macht nur den Oberkorb.** Der
> Unterkorb gehört nicht mehr zum Umfang. Die Beispiele `z-achse-frontal`,
> `stationaer` und `heute` rechnen den Unterkorb (Teller, Korbzug) nur noch,
> um die früheren Ergebnisse der Konzept-Spec §13 nachzuweisen; neue
> Varianten prüfen nur Oberkorb-Ziele.

Bewertet eine Aufbau-Variante des ReBeL an der Spülmaschine in wenigen
Minuten auf der CPU: Wohin kommt der Greifer kollisionsfrei, welche Körbe kann
der Arm ziehen, welche Gelenkmomente entstehen dabei?

```
raeumwerk aufbau beispiele/z-achse-frontal.yaml          # alle Kerne, Cache an, Bilder an
raeumwerk aufbau beispiele/auf-maschine.yaml --jobs 3 --out /tmp/c2
raeumwerk aufbau <aufbau.yaml> --gruppen zug slots       # nur diese Zielgruppen
raeumwerk aufbau <aufbau.yaml> --kein-cache --ohne-bilder
```

Ohne installiertes Paket: `python -m raeumwerk aufbau …` aus dem Repo
(braucht numpy, PyYAML, für die Bilder matplotlib).

Ausgabe im Ordner `aufbau-<Dateiname>/` (bzw. `--out`):

| Datei | Inhalt |
|---|---|
| `ergebnis.md` | Abdeckungstabelle je Zielgruppe, Abgleich mit der Referenz, Einzelziele mit Grund, Momente beim Korbzug |
| `ergebnis.json` | dasselbe maschinenlesbar, dazu Gelenkwinkel (`q`, `q_start`, `q_ende`) für Bilder und Simulation |
| `uebersicht.png` | Draufsicht und Seitenansicht mit dem Roboter in kritischen Posen |
| `pose-<gruppe>-<ziel>.png` | kritische Posen (Korbzug mit dem größten J2-Moment, je Gruppe ein erreichtes und ein gescheitertes Ziel) |

Die Bilder zeigen die Kollisionsquader (Prüfbilder), keine Renderings.

## Beispiele (`beispiele/`)

| Datei | Aufbau | Referenz |
|---|---|---|
| `z-achse-frontal.yaml` | ReBeL auf vertikaler Achse vor der Maschine | Konzept-Spec §13, Variante A |
| `auf-maschine.yaml` | C2: 7. Achse entlang der Arbeitsplatte, 105° geneigt | Konzept-Spec §14 |
| `stationaer.yaml` | fest ohne Achse, Fuß 0,35 m | Konzept-Spec §13, Variante B |
| `heute.yaml` | Schiene senkrecht zur Front, Podest 0,65 m | Konzept-Spec §13, Spalte heute |

Der Block `vergleich:` einer Beschreibung nennt die Referenzwerte; das Werkzeug
schreibt den Abgleich in den Bericht.

## Aufbau-Beschreibung (YAML)

```yaml
name: …
roboter:
  ursprung_xyz_m: [x, y, z]   # Ursprung des Links `rail` (Schienenanfang bzw. Schlittenplatte) im Küchensystem
  gier_grad: 0                # Drehung um z
  kipp_grad: 0                # Drehung um y (Roboter-x neigt nach unten)
  neigung_grad: 0             # Drehung um x (Roboter-z neigt zum Raum, +y)
  montage: stehend            # oder haengend (= kipp + 180°)
achse:
  richtung: x                 # x (liegende 7. Achse), y, z (vertikal) oder keine
  hub_m: 1.0
  schiene: standard           # standard = Schiene aus config/robot.yaml; platte = nur Schlittenplatte 0,25 × 0,25 m
  podest: false               # true: Podest unter der Schiene wie spuelmaschine.erreichbarkeit
greifer: {}                   # Überschreibungen von config/robot.yaml → greifer (z. B. koerper_breite_m)
masse: {}                     # Überschreibungen von config/spuelmaschine.yaml (Glashalter, Ablagepunkte, Tür …)
szene: {}                     # Überschreibungen von config/scene_spuelmaschine.yaml (Rand, Greifparameter …)
hindernisse:                  # zusätzliche Körper; "podest" = Halterung des Roboters
  - {name: podest, gruppe: saeule, lo: [x, y, z], hi: [x, y, z]}
  - {name: tisch_1, glas_mitte: [x, y, z]}       # Glas (Ablageziel und Hindernis)
erlaubt: ["base_link|podest"] # Berührungen, die keine Kollision sind (Link|Körper)
ik: {zufallsstarts_bei_fehlschlag: 12}
ziele:
  slots:  {oberkorb_auszug_m: 0.45, gier_grad: [0, 180]}
  teller: {korb: unterkorb, auszug_m: 0.45, x_m: […], tiefe_m: […], rand_ueber_boden_m: 0.26,
           greif_unter_rand_m: 0.01, vorposition_m: 0.10, aushub_m: 0.30, gier_grad: [90, 0],
           glashalter: true, last_kg: 0.35}
  zug:    {koerbe: [unterkorb, oberkorb], x_m: [0.50, 0.10], griffe: [waagerecht, oben],
           richtungen: [aus, ein], anfahrt_m: 0.08, szene_raster_m: 0.01}
  ablage: {platte: true, glaeser: [tisch_1], seitgriff: false, gier_grad: [0, 90, 180, 270]}
momente: {zugkraft_n: [20, 30]}
vergleich: {slots: 6, zug_oberkorb: true}
```

## Was geprüft wird

Die Verfahren sind dieselben wie in `spuelmaschine/erreichbarkeit.py` und den
bisherigen Machbarkeitsprüfungen:

- **slots / ablage:** Vorposition → senkrecht hinab → Aushub mit getragenem
  Glas (Ablage: nur hinab). Wegpunkte im 1-cm-Abstand, IK-Fehler < 1 mm,
  Gelenksprung ≤ 10° je Wegpunkt, Selbstkollision und 5 mm Rand zur Szene.
  Das gegriffene Glas wird für die Finger **ausgeblendet**, nie aus der Szene
  entfernt.
- **teller:** Rand von oben greifen, Vorposition und Aushub senkrecht.
- **zug:** Korbfront greifen (waagerecht in die Maschine oder von oben),
  Anfahrt, dann den Korb ausziehen (`aus`) bzw. vom ausgezogenen Korb aus
  einschieben (`ein`). Die Kollisionsszene fährt im **1-cm-Raster** mit
  (`szene_raster_m`); Finger und Greifer dürfen die gegriffene Korbfront
  berühren. Ein Korb gilt als ziehbar, wenn einer der Wege gelingt.
- **seitgriff:** Ablage eines aufrechten Glases von vorn (10 cm waagerecht,
  2 cm absenken), hintere Reihe zuerst; in der Szene stehen nur die schon
  abgestellten Gläser.
- **Vorfilter Reichweite:** Ein Ziel mit senkrechtem Greifer scheidet ohne IK
  aus, wenn das Handgelenk für jede Achsstellung weiter als die Armlänge
  (Gelenk 2 → 5) **oder näher als die Mindestreichweite** (~0,19 m, Gelenk 3
  am Anschlag 140°) an Gelenk 2 liegt.

## Momente

`tau = Jᵀ F` mit der Zugkraft entlang der Werkzeugachse (20 und 30 N), dazu
das Eigengewicht der Glieder (Masse im Link-Ursprung, wie in den
Machbarkeitsprüfungen). Je Gelenk das Maximum über den Zugweg; Urteil gegen die
igus-Grenzen aus `config/robot.yaml` (J1–J3 Nenn 10 / Max 12,5 Nm, J4–J6 Nenn
2 / Max 2,5 Nm, jeweils der untere Wert): „geht“ (alle ≤ Nenn), „knapp“
(≤ Max) oder „geht nicht“. Zusätzlich steht da, ob der Zug allein unter dem
Nennmoment bleibt.

## Warum es schnell ist

| Maßnahme | Wirkung |
|---|---|
| `rebel_model.schnell`: FK, Jacobi und IK für viele Gelenkvektoren auf einmal (numpy-Batch), Drehungen um Koordinatenachsen als Spaltenmischung | IK gleich der Einzel-IK (`Chain.ik`) bis auf 1e-13 rad, ~8× schneller je Ziel |
| Startposen stückweise: erst die erste allein, dann der Rest als Batch | meist reicht die erste; scheitern alle, kosten die übrigen nur einen Batch |
| Warmstart entlang der Wege, Zufallsstarts nur bei Fehlschlag | kein Neustart mitten im Weg, wenn das Ergebnis ohnehin feststeht (ein Neustart springt > 10°) |
| vektorisierter AABB-Vorfilter der Kollision | Quadertest nur für nahe Paare |
| Prozesse über alle Ziele (`--jobs`, Standard alle Kerne) | Zug, Slots, Teller, Ablage parallel |
| Cache je Ziel (`~/.cache/raeumwerk/aufbau`) | Schlüssel = SHA-256 aus Aufbau (ohne Name/Beschreibung), Ziel, `config/*.yaml` und Quellcode; jede Änderung an Szene, Roboter oder Code rechnet neu |

## Grenzen

- Ergebnisse, die nur von einem Zufallsstart erreicht werden, schwanken mit dem
  Seed. Seeds sind fest je Ziel (reproduzierbar), aber andere als in den alten
  Skripten, die einen Zufallsstrom über alle Ziele teilten.
- Kein Weg zwischen den Zielen (Korb → Ablage), keine Dynamik, keine
  Durchbiegung; Eigengewicht mit geschätzter Massenaufteilung.
- Kameraperspektiven (`kamera`-Posen) sind noch nicht eingebaut; dafür gibt es
  das Kamerawerkzeug der Konzept-Spec (§3).
