# Ausräumen: 4 Gläser kopfüber aus dem Oberkorb, umdrehen, aufrecht abstellen

Der ReBeL auf der 7. Achse (Podest 0,65 m, Schiene senkrecht zur Front,
`docs/spuelmaschine.md` §4) holt vier kopfüber stehende Gläser aus dem
ausgezogenen Oberkorb, dreht sie um und stellt sie aufrecht auf die
Arbeitsplatte. Newton 1.6.1 (MuJoCo-Warp), CPU = GPU. Start: `docs/START.md` §8,
belegte Zahlen: `docs/STATUS.md`.

| Teil | Datei |
|---|---|
| Ablauf, Zwischenablage, Griffe, Bewertung, Negativtest | `config/ausraeumen.yaml` |
| Szene (Maschine, Gläser je Versuch), Kollision gedrehter Gläser | `ausraeumen/geometrie.py` |
| Ablaufplanung (IK, Wege, Zwischenpunkte) | `ausraeumen/plan.py` |
| Newton-Lauf, Messung | `ausraeumen/sim_newton.py` |
| Bewertung je Glas, Gesamtbericht | `ausraeumen/bewertung.py` |
| Versuch von Plan bis Bewertung, Backend für `raeumwerk run` | `ausraeumen/ablauf.py`, `raeumwerk/simulator.py` |
| Befund Podesthöhe mit Seitgriff | `ausraeumen/befund.py` |
| Demo/Negativtest (JSON), Runner | `scripts/demo_ausraeumen.py`, `scripts/run_ausraeumen.sh` |
| Variationslauf | `experimente/ausraeumen_variation.yaml` |
| Video | `scripts/render_ausraeumen.py` |
| Tests | `tests/test_ausraeumen.py` |

## 1. Grenzen vorweg

- Die Glaslage ist der Planung genau bekannt (keine Kamera). Die Variation
  zeigt die Robustheit des Ablaufs gegen andere Lagen, nicht gegen eine
  falsch geschätzte Lage.
- Korb als feste, ausgezogene Pose; Gitter als wenige Stäbe, Glashalter als
  Streben, Gläser als Vollzylinder (`docs/spuelmaschine.md` §3, §7).
- Kontakte weich (ke 2500, kd 100 wie die Greifdemo); Reibwerte und
  Greifkraft sind Annahmen.
- Kollisionsvermeidung über Zwischenpunkte, kein vollständiger
  Bewegungsplaner.

## 2. Befund: Umdrehen mit dem Griff von oben geht nicht

Im Korb ist nur der Griff von oben möglich (`docs/spuelmaschine.md` §4).
Ein Seitgriff im Korb scheidet aus: die Korbwand ist 120 mm hoch, das Glas
110 mm; der waagerechte Greifer (Körper ±25 mm um die Griffhöhe 55 mm über
dem Korbboden) müsste durch die Wand.

Mit einem starren Griff von oben lässt sich das Glas aber nicht aufrecht
abstellen, und das liegt nicht an J5/J6: Dreht man Greifer und Glas um 180°
um eine waagerechte Achse, zeigt der Greifer danach nach oben, und sein Körper
liegt unter dem Glasboden. Beim Abstellen auf die Platte säße der TCP
22 mm über der Platte (Glashöhe 110 mm − 88 mm Griff), die Fingerwurzel 8 mm
und der Flansch 58 mm unter der Plattenoberkante
(`test_umdrehen_mit_griff_von_oben_stellt_greifer_in_die_platte`). Allgemein:
Soll der Greifer vor und nach dem Umdrehen über bzw. neben dem Glas bleiben,
muss die Anfahrrichtung waagerecht sein (eine 180°-Drehung um eine waagerechte
Achse kehrt die senkrechte Komponente der Anfahrrichtung um).

**Abhilfe (gebaut): Umgreifen über eine kleine Zwischenablage.** Das Glas wird
mit dem Griff von oben kopfüber auf einer 10 × 10 cm großen Matte auf der
Arbeitsplatte abgestellt, dort mit waagerechtem Greifer seitlich auf Höhe der
Glasmitte neu gegriffen, 4 cm angehoben und **nur mit Gelenk 6 um 180°**
gedreht: Gelenk 6 dreht um die Greiferachse, die waagerecht liegt, das Glas
steht danach aufrecht. Es gibt zwei Matten, links (x 0,58 m) und rechts
(x 0,98 m) der Ablagepunkte (y −0,03 m), je Ablagepunkt die auf derselben
Seite des Roboterfußes (Schiene bei x 0,78 m): Ein gerader Weg von der linken
Matte zu den rechten Ablagepunkten führt das Handgelenk dicht vor dem Fuß
vorbei, dort riss die IK ab (Gelenk 3 an seiner Grenze, Gelenksprung 15°).
Die Matten liegen auf Plattenhöhe, weil der Griff von oben höher nicht mehr
erreichbar ist (J5 ≤ 95°). Grenzen beim Umdrehen siehe §6.

## 3. Ablauf und Planung

Je Glas (`ablauf.zuordnung`: Slot → Ablagepunkt; hintere Ablagereihe zuerst,
damit der Seitgriff über die noch freien vorderen Punkte zurückfährt):

| Phase | Was |
|---|---|
| anfahrt_korb, runter_korb | Gelenkfahrt über den Slot, senkrecht hinab (TCP 88 mm über dem Glasrand) |
| greifen_korb, aushub | Finger schließen, 15 cm senkrecht hoch (Glasrand 3 cm über der Korbwand) |
| zur_zwischenablage, absetzen_zw, loesen_zw, hoch_zw | Gelenkfahrt, kopfüber auf die Matte (2 mm Luft), loslassen, 5 cm hoch |
| anfahrt_seite, zu_seite, greifen_seite | Greifer waagerecht 10 cm vor das Glas, waagerecht heran (Glasmitte 15 mm vor dem TCP), schließen |
| anheben, umdrehen | 4 cm hoch, Gelenk 6 um 180° (30 % der Datenblattgeschwindigkeit) |
| zur_ablage, absetzen, loesen, rueckzug | gerader Weg 3 cm über den Ablagepunkt (Drehung nur um die Senkrechte), senkrecht absetzen (2 mm Luft), loslassen, 10 cm waagerecht zurück |

Gerade TCP-Wege: 1-cm-Wegpunkte, warm gestartete IK (7. Achse + 6 Gelenke,
Lage und Orientierung, < 1 mm), Gelenksprung je Wegpunkt ≤ 10°.
Gelenkfahrten werden in 2°-Schritten geprüft. Jeder Prüfpunkt: Gelenkgrenzen,
Selbstkollision, Roboterquader gegen Szene (5 mm Rand) und gegen ruhende
Gläser (bei Gelenkfahrten 2 cm, sonst 5 mm; die Finger dürfen nur beim
geraden Heranfahren das zu greifende Glas berühren), getragenes Glas gegen
Szene (2 mm) und gegen den Greifer; ein getragenes Glas darf sich bei
Gelenkfahrten höchstens 20° neigen. Gedrehte Gläser prüft
`ausraeumen.geometrie.ueberlappung` mit der exakten Stützfunktion des
Zylinders (Trennachsentest; meldet im Zweifel eine Kollision zu viel). Findet
eine Gelenkfahrt keinen freien Weg, kommen Zwischenpunkte 8 bzw. 16 cm über
Start und Ziel und die Ruhepose als Zwischenpunkt dran. Nach dem Umdrehen
fährt der TCP auf geradem Weg zur Ablage und dreht dabei nur um die
Senkrechte. Ohne Neigungsgrenze hatte die Gelenkfahrt dorthin
(J1 146°, J3 174°) den Greifer um seine Anfahrachse gedreht; das Glas
rutschte 11 mm in der Hand, die Finger drangen 3,4 mm ein (Demo-Lauf vor der
Änderung: 2/4). Die IK-Lösungen werden je Stelle gemerkt (gleiche Haltung für
jedes Glas; die Variation startet mit den Lösungen des Nennplans).

Zeitprofil: ruckarm (wie die Greifdemo), Gelenke höchstens 60 % der
Datenblattgeschwindigkeit, dazu je Wegstück TCP ≤ 0,1 m/s und ≤ 0,1 m/s².
Ohne die TCP-Grenze regte der 4-cm-Hub in 0,5 s die Finger zu Schwingungen
an, das Glas kippte im Griff um 9°.

## 4. Greifer und Kontakt

Finger wie `config/robot.yaml` (20 × 10 × 60 mm), eigener PD-Antrieb je
Finger. Greifkraft **10 N je Finger** (Greifdemo: 20 N), Halten
2 × 1,0 × 10 N = 20 N gegen 2,45 N Gewicht. Im Seitgriff kippt das Glas beim
Umdrehen etwas im Griff, die Fingerkante drückt dann tiefer ins weiche
Kontaktmodell. Gemessen an Glas 1 (Fingerdurchdringung, Grenze 3 mm):

| Greifkraft | Umdrehen | Finger | Durchdringung | Zielfehler |
|---|---|---|---|---|
| 20 N | 60 % | 20 mm | 4,72 mm | 4,1 mm |
| 20 N | 100 % | 20 mm | 6,52 mm | 3,5 mm |
| 40 N | 100 % | 20 mm | 8,85 mm | 3,9 mm |
| 10 N | 60 % | 20 mm | 3,49 mm | 4,3 mm |
| 6 N | 60 % | 20 mm | 3,03 mm | 4,0 mm |
| 8 N | 30 % | 20 mm | 2,09 mm | 5,3 mm |
| **10 N** | **30 %** | **20 mm** | **2,34 mm** | **3,8 mm** |
| 20 N | 60 % | 50 mm | 5,56 mm | 9,7 mm (Glas wandert 13 mm in der Hand) |

Gewählt: 10 N, Umdrehen mit 30 % (13,5°/s, etwa 25 s je Glas).

## 5. Bewertung je Glas

Gemessen alle 10 ms: Lage und Drehung jedes Glases, TCP-Lage, tiefste
Durchdringung Roboter ↔ Korb/Glashalter, Tür, Arbeitsplatte, Zwischenablage
und Finger ↔ Glas, jeweils dem Glas zugeordnet, das gerade bearbeitet wird.
`ausraeumen/bewertung.py`:

| Grund | bestanden, wenn |
|---|---|
| `planung_fehlgeschlagen` | Plan gefunden |
| `simulation_instabil` | keine NaN |
| `nicht_aus_dem_korb` | Glas am Ende des Aushubs ≥ 8 cm über dem Slot |
| `gefallen` | Abstand Glas ↔ TCP ändert sich in der Hand ≤ 2 cm, am Ende ±5 mm auf Plattenhöhe |
| `gekippt` | Glasachse am Ende < 10° gegen die Senkrechte (Start kopfüber = 180°) |
| `nicht_am_ziel` | Glasmitte ≤ 1 cm neben dem Ablagepunkt |
| `kontakt_korb`, `kontakt_tuer`, `kontakt_arbeitsplatte` | Roboter dringt nie > 0,1 mm ein |
| `nachbar_verschoben` | kein anderes Glas wandert im Zeitfenster dieses Glases > 5 mm |
| `durchdringung` | Finger ≤ 3 mm im Glas |
| `weggeschossen` | Glas ≤ 1 m/s |

Gesamtbericht: `versuch-00.json` mit `bewertung.glaeser[]` (Gründe,
Kriterien mit Werten und Grenzen, Plan-Infos) und `bewertung.erfolge`.

## 6. Messwerte

Abnahmelauf auf der CPU (Newton 1.6.1, Warp 1.17.0, MuJoCo-Warp 3.12.0, Stand
`beb4671`), `scripts/run_ausraeumen.sh --cpu demo`, fester Seed. Ablauf
376 s Simzeit (Planung 227 s, Simulation 78 min Wandzeit neben anderen
Läufen), 77 statische Formen + 4 Gläser.

**Ergebnis: 4/4 Gläser aufrecht am Ziel.**

| Glas → Ablage | Zielfehler | Kippung Ende (Start) | Aushub | Fingerdurchdringung | Glas in der Hand gewandert | Kontakt Arm ↔ Korb/Tür/Platte | andere Gläser verschoben |
|---|---|---|---|---|---|---|---|
| 1 → 3 | 3,58 mm | 0,10° (180°) | 150 mm | 2,34 mm (umdrehen) | 1,0 mm | keiner | ≤ 0,03 mm |
| 2 → 4 | 3,40 mm | 0,10° (180°) | 150 mm | 2,42 mm (zur_ablage) | 1,9 mm | keiner | ≤ 0,05 mm |
| 3 → 1 | 5,48 mm | 0,10° (180°) | 149 mm | 2,54 mm (zur_ablage) | 1,4 mm | keiner | ≤ 0,05 mm |
| 4 → 2 | 3,89 mm | 0,10° (180°) | 149 mm | 2,78 mm (zur_ablage) | 2,4 mm | keiner | ≤ 0,04 mm |

Grenzen: Zielfehler ≤ 10 mm, Kippung < 10°, Durchdringung ≤ 3 mm, Kontakt
≤ 0,1 mm (gemessen: keine Durchdringung), Nachbarn ≤ 5 mm. Glas am Ende
0,9149 m (Soll 0,915 m), höchstens 0,21 m/s. Umdrehen: Gelenk 6 von 34° auf
−146° (Gläser 1, 3) bzw. von −34° auf 146° (Gläser 2, 4), Grenze ±179°;
Gelenk 5 dabei 42–43°, Grenze ±95°. Zur rechten Matte dreht Gelenk 1 um bis
zu 272° (18 s), das kopfüber getragene Glas bleibt dabei aufrecht (≤ 20°).

Vor der Neigungsgrenze und den zwei Matten (Stand `405f505`, eine Matte):
Demo 2/4, Gläser 2 und 4 mit 3,35/3,45 mm Fingerdurchdringung in der Fahrt
zur Ablage (Glas 11/8,8 mm in der Hand gewandert).

## 7. Variation

`experimente/ausraeumen_variation.yaml`, 10 Versuche auf der CPU (Stand
`beb4671`), in 5 Teilen parallel mit `raeumwerk run --teil K/5`; jeder Versuch
rund 84 min Wandzeit. Je Versuch werden Lage jedes Glases im Slot (±5 mm in x
und y), Drehung um die Senkrechte (±3°) und der Korbauszug (±1 cm) gewürfelt;
gemessen wurden Glasversatz höchstens 4,9 mm, Drehung −2,8 … +3,0°,
Korbauszug −8,8 … +7,9 mm.

**Ergebnis: 10 von 10 Versuchen mit allen vier Gläsern am Ziel**, also je Glas
10/10 Erfolge (Quote 1,00), keine Fehlversuche, keine Fehlgründe.

| Größe | Wert | Grenze |
|---|---|---|
| Zielfehler der Erfolge | höchstens 7,37 mm, Mittel über alle 40 Gläser 3,03 mm (Mittel der Versuchsmaxima 6,04 mm) | 10 mm |
| Fingerdurchdringung | höchstens 2,92 mm | 3 mm |
| Kontakt Arm ↔ Tisch | 0 mm | 0,1 mm |

Über alle 40 Gläser liegt der Zielfehler im Mittel bei 3,0 mm und damit etwas unter dem Demo-Bereich (3,4–5,5 mm).
Das schlechteste Glas liegt mindestens 2,6 mm unter der Grenze. Die Fingerdurchdringung hat nur 0,08 mm
Reserve. Ihre 3-mm-Grenze ist eine Modellgrenze der weichen Kontakte, keine gemessene Materialgrenze. Zehn Versuche ohne Fehlschlag belegen keine Quote nahe 1: die obere
95-%-Grenze der Fehlerquote liegt bei dieser Stichprobe bei etwa 26 %.

## 8. Negativtest

`scripts/run_ausraeumen.sh --cpu negativ`: Glas 1 steht in einem zu schmalen
Halter, zwei Klemmbacken (40 × 10 × 80 mm, Reibwert 1,5) drücken vorn und
hinten je 3 mm ins Glas; die Planung weiß davon nichts und plant wie in der
Demo. Ergebnis (gleicher Stand): Glas 1 **Fehlversuch** mit
`nicht_aus_dem_korb` (Aushub 0 mm, Grenze 80 mm), dazu `gefallen`
(Abstand zum TCP 615 mm: nicht in der Hand), `gekippt` (179,9°, steht weiter
kopfüber) und `nicht_am_ziel` (515 mm). Der Arm berührt dabei weder Korb noch
Klemmbacken (0 mm). Die Gläser 2–4 laufen danach normal: 3/3 Erfolg
(Zielfehler 1,9 / 6,1 / 3,4 mm). Exit 0 heißt: Klemmglas erkannt.

## 9. Befund: seitlicher Griff und Podesthöhe

Nur Kinematik (`python -m ausraeumen.befund`, IK + Kollision gegen die
statische Szene, Teilwege einzeln, kein Newton):

| Podest | Slots (oben) | Matte (oben, Platte) | Seitgriff an der Matte | Ablage (seitlich) |
|---|---|---|---|---|
| 0,30 m | 2/4 | nein | ja | 3/4 |
| 0,40 / 0,50 / 0,60 m | 4/4 | nein | ja | 4/4 |
| 0,65 m | 4/4 | ja | ja | 4/4 |

Mit dem Seitgriff ist die Ablage auf der Platte schon ab 0,40 m erreichbar
(der Griff von oben brauchte dort 0,65 m, `docs/spuelmaschine.md` §4). Der
Engpass wandert zum Abstellen auf der Zwischenablage, das mit dem Griff von
oben geschieht. Liegt die Zwischenablage tiefer, als Konsole neben dem
Podest (x 1,00 m, y 0,30 m, Oberkante 0,45 bzw. 0,55 m), sind alle Teilwege
bei 0,40 und 0,50 m Podest erreichbar:

```bash
python -m ausraeumen.befund --hoehen 0.30 0.40 0.50 0.60 0.65
python -m ausraeumen.befund --hoehen 0.40 0.50 --set "zwischenablage.matten_xy_m=[[1.00, 0.30]]" \
    --set "zwischenablage.oberkante_m=0.45" --set "zwischenablage.dicke_m=0.02"
```

**Bewertung:** Ein Podest von etwa 0,40 m wäre mit einer Konsole als
Zwischenablage möglich; geprüft sind nur Posen und gerade Teilwege, nicht die
Gelenkfahrten dazwischen und nicht die Physik. Die Demo läuft auf der
gewählten Lage (0,65 m) mit den Matten auf der Platte.

## 10. Video

`scripts/run_ausraeumen.sh --cpu demo --aufzeichnen …npz` und
`scripts/render_ausraeumen.py` (Mesh-Optik mit `RAEUMWERK_ASSETS`, sonst
Quader): Abnahmelauf als 50,0 s, 1280×720, 30 Bilder/s, H.264 High,
yuv420p, `moov` vor `mdat` (faststart), 1,7 MB, 8,35-fach schneller als die
Simzeit, 275 s Renderzeit in 4 Prozessen. Oben die Phase je Glas
(„Glas 2/4 · Umdrehen“), am Ende 5 s Ergebnis (4/4, Zielfehler, Kippung). Die
Szene wird einmal gezeichnet, Arm und Gläser darüber; aus dieser Kamera liegt
der Arm vor bzw. über der Szene, die Gläser im Korb werden aber über die
vorderen Korbstäbe gezeichnet. Videos und Aufzeichnungen kommen nicht ins
Repo.
