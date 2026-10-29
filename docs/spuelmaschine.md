# Spülmaschine: parametrisches 60-cm-Modell und Erreichbarkeit

Standardmodell einer vollintegrierten 60-cm-Einbau-Spülmaschine unter einer
Arbeitsplatte, aus Datenblättern mehrerer Hersteller. Später wird es an die
echte Maschine angepasst (nur `config/spuelmaschine.yaml` ändern).
Belegte Zahlen: `docs/STATUS.md`.

| Teil | Datei |
|---|---|
| Maße mit Quellen | `config/spuelmaschine.yaml` |
| Schienenlage, Greif-, Raster- und Newton-Parameter | `config/scene_spuelmaschine.yaml` |
| Laden der YAML-Dateien, Quellenprüfung | `spuelmaschine/masse.py` |
| Geometrie-Generator (Kollisionskörper) | `spuelmaschine/geometrie.py` |
| Erreichbarkeit, Rastersuche, Tabelle | `spuelmaschine/erreichbarkeit.py` |
| Newton-Stabilitätstest | `spuelmaschine/stabilitaet.py` |
| Vorschau-Standbild (matplotlib, ohne GPU) | `scripts/vorschau_spuelmaschine.py` |
| Tests | `tests/test_spuelmaschine.py` |

## 1. Koordinaten

Küchensystem: Ursprung auf dem Boden an der linken Vorderkante der Nische,
+x nach rechts entlang der Front, +y aus der Nische in den Raum, +z nach oben.
Die Korpusfront liegt bei y = 0, die Nischenrückwand bei y = −0,55 m, die
Nische reicht von x = 0 bis 0,6 m. Die Schiene (7. Achse) wird mit Ursprung
und Gierwinkel in dieses System gesetzt (`schiene` in
`config/scene_spuelmaschine.yaml`).

## 2. Maße und Quellen

Jede Zahl steht in `config/spuelmaschine.yaml` als `{wert, src}`;
`test_every_value_has_source` prüft, dass jede Quelle genannt und benutzt ist.
Herstellerdaten sind nur als Zahlen übernommen, keine CAD-Dateien.

| Größe | Wert | Quelle |
|---|---|---|
| Nische B × H × T | 600 × 820 × 550 mm | Bosch SMV4HVX14E: 600 × 815–875 × 550; ASKO DW60 XL: 820–870 hoch, ≥ 550 tief; Miele G 6260 SCVi: 600 breit, ab 805 hoch |
| Gerät B × T | 598 × 550 mm | Bosch (Miele: 598 × 570) |
| Tür: Länge Scharnier → Oberkante | 600 mm | Bosch: Tiefe bei geöffneter Tür (90°) 1150 mm − Gerätetiefe 550 mm |
| Tür: Scharnierhöhe | 100 mm | ASKO: Sockel 60–140 mm (Mitte gewählt) |
| Tür: Dicke | 40 mm | Annahme (Innentür + 19-mm-Möbelfront) |
| Oberkorb B × T | 525 × 475 mm | BSH-Ersatzteil 00770441 (525 × 190 × 475 mm); 00774191: 520 × 510 × 160 mm |
| Oberkorb: lichte Höhe | 220 mm | Miele: Oberkorb „Mitte“ Teile bis 22 cm |
| Oberkorb: Boden über dem Fußboden | 420 mm | Annahme, abgeleitet: Unterkorbboden 130 mm + 29 cm lichte Höhe im Unterkorb (Miele, Oberkorb „Mitte“) |
| Oberkorb: Auszug | 450 mm | Annahme (Teleskopschienen, fast Vollauszug); kein Datenblattwert gefunden |
| Oberkorb: Wandhöhe | 120 mm | Annahme (Teile-Gesamthöhe 160–190 mm inkl. Rollen und Halter) |
| Unterkorb B × T × H | 525 × 515 × 140 mm | BSH-Ersatzteil 00775102 |
| Unterkorb: Boden | 130 mm | Annahme |
| Arbeitsplatte | 40 mm dick, 600 mm tief, Oberkante 860 mm | übliche Küchenmaße (Größenordnung) |
| Glas | Ø 75 × 110 mm, 250 g | Vorgabe wie `config/scene.yaml` |
| Glashalter | 2 Reihen × 2 Slots, Teilung 100 mm, Streben 35 mm hoch | Annahme |
| Ablagepunkte | (0,70/0,82; −0,03/−0,13) m auf der Platte rechts der Maschine | Annahme |

Quellen (öffentlich, nur Zahlen übernommen):
- Bosch Produktdatenblatt „Serie 4, Vollintegrierter Geschirrspüler, 60 cm
  SMV4HVX14E“, media3.bosch-home.com (specsheet de-DE).
- Miele Gebrauchsanweisung Geschirrspüler G 6260 SCVi / G 6265 SCVi
  (Kapitel Oberkorb, Technische Daten).
- ASKO Montageinformation Geschirrspüler 60 cm (Planungsunterlage eines
  Küchenhändlers, fors.ch).
- Bosch/Siemens-Originalkörbe 00770441, 00774191, 00775102 (Maßangaben des
  Ersatzteilhändlers fiyo).

## 3. Geometrie

`geometrie.baue()` erzeugt 75 statische Körper, alle als Quader:
Korpus (Seiten, Rückwand, Bottichdecke, Bodenwanne), Tür (waagerecht offen,
um die Scharnierachse gedreht), Ober- und Unterkorb (Bodenplatte, vier
Randstäbe, senkrechte Stäbe im Abstand 10 cm als Gitter-Ersatz),
Glashalter-Streben, Arbeitsplatte, je ein Nachbarschrank links und rechts.
Die Gläser sind stehende Zylinder; kopfüber heißt Rand unten auf dem
Korbboden (für einen Vollzylinder ändert die Drehung die Kollision nicht).

Korbauszug: Schiebeweg entlang +y (`auszug` 0 … `auszug_max_m`), in der
Szene als feste, ausgezogene Pose; `Szene.korbgelenke` beschreibt das
Schubgelenk für eine spätere Simulation mit beweglichem Korb.

Tests (`test_keine_ueberschneidungen`, `test_slots_vier_glaeser_kopfueber_im_korb`):
zwischen Teilen verschiedener Gruppen höchstens Berührung; jedes Glas steht
auf dem Korbboden, hat zu allem anderen ≥ 5 mm Luft und zu den Nachbargläsern
≥ 2 cm, an jedem Slot Streben auf allen vier Seiten.

## 4. Erreichbarkeit

**Griff:** Greifer senkrecht von oben, Finger schließen quer zur Glasreihe
(x), TCP 88 mm über dem Glasrand (Greiferkörper 8 mm über dem Glasboden,
Fingerspitzen 23 mm über den Streben). Je Slot wird der Weg Vorposition
(10 cm über dem Griff) → Greifpose → Aushub (15 cm, Glasrand 3 cm über der
Korbwand) in 1-cm-Schritten geprüft, je Ablagepunkt Vorposition (5 cm, Glas
getragen) → Absetzen.

**Prüfung je Wegpunkt:** vorhandene IK (`Chain.ik`, 7. Achse + 6 Armgelenke,
Lage und Orientierung, warm gestartet), IK-Fehler < 1 mm, Gelenksprung je
Schritt ≤ 10° (durchgehender Griff), Selbstkollision mit den Quaderpaaren aus
`rebel_model.collision`, Roboterquader und getragenes Glas gegen jeden
Szenenkörper (Quader-Trennachsentest bzw. Kreisabstand für Gläser) mit 5 mm
Sicherheitsrand; alle anderen Gläser in Korb und Ablage stehen als
Hindernisse (konservativ). Die Finger dürfen nur das gegriffene Glas
berühren. Podest und Schiene dürfen Tür und Schränke nicht berühren.

**Rastersuche** (`python -m spuelmaschine.erreichbarkeit --raster`): 176
Lagen, Schiene senkrecht zur Front (x = 0,74–1,00 m, Anfang y = 0,06 m) und
parallel zur Front hinter der offenen Tür (y = 0,75–0,95 m), Podesthöhe
0–0,8 m. Gewählt wird die Lage mit den meisten erfolgreichen Nachbarlagen
(± 5 cm), dann das niedrigste Podest, dann die kleinste J5-Auslenkung.

| Ergebnis | Lagen |
|---|---|
| parallel zur Front: Ablage außerhalb der Reichweite | 99 / 99 |
| senkrecht, Podest ≤ 0,45 m: Ablage außerhalb der Reichweite | 28 / 28 |
| senkrecht, Podest 0,5–0,6 m: Ablage ohne IK-Lösung (J5 ≤ 95°) | 20 / 21 |
| senkrecht, Podest ≥ 0,65 m: Slot 4 außer Reichweite (Schiene zu weit rechts oder Podest zu hoch) | 20 / 28 |
| senkrecht, Podest ≥ 0,65 m: Ablage ohne IK-Lösung (x = 0,82 m bzw. 1,0 m) | 5 / 28 |
| **erreichbar** | **3**: (0,74; 0,65), (0,78; 0,65), (0,74; 0,70) (x; Podesthöhe) |

**Befund:** Mit der Schiene auf dem Boden erreicht der ReBeL weder den
ausgezogenen Oberkorb (Griff von oben mit 15 cm Aushub: 92–163 mm außer
Reichweite) noch die Ablage auf der Arbeitsplatte (0,86 m). Die Slots allein
gehen ab etwa 0,3–0,4 m Podest (Stichprobe x = 0,74/0,78 m: 0,3 m 4/4 bzw.
2/4, 0,4 m 4/4). Die Ablage ist der Engpass: Beim Griff von oben muss das
Handgelenk über dem Glas liegen, und wegen J5 ≤ 95° darf der Unterarm
höchstens 5° ansteigen. Nötig ist ein **Podest von 0,65 m** unter der
Schiene, die **senkrecht zur Front** neben der offenen Tür steht. Parallel
zur Front muss die Schiene hinter der offenen Tür (0,6 m) bleiben; von dort
ist die Arbeitsplatte zu weit weg.
`config/robot.yaml` bleibt unverändert (Schiene 1,0 m Hub reicht; die
Ablagepunkte 3 und 4 nutzen das Schienenende bei Achswert 0).

**Gewählte Lage** (`config/scene_spuelmaschine.yaml`): Schiene senkrecht zur
Front, Ursprung (0,78; 0,06; 0,65) m, Gierwinkel 90°.

| Ziel | erreichbar | Wegpunkte | IK-Fehler max. | Gelenksprung max. | Achse 7 | J5 max. | Kollisionen |
|---|---|---|---|---|---|---|---|
| Slot 1 | ja | 26 | 0,0030 mm | 2,1° | 0,251–0,314 m | 37,8° | keine |
| Slot 2 | ja | 26 | 0,0030 mm | 2,1° | 0,151–0,214 m | 37,8° | keine |
| Slot 3 | ja | 26 | 0,0089 mm | 4,5° | 0,135–0,244 m | 53,8° | keine |
| Slot 4 | ja | 26 | 0,0089 mm | 4,5° | 0,035–0,144 m | 53,8° | keine |
| Ablage 1 | ja | 6 | 0,0051 mm | 1,8° | 0,087–0,103 m | 88,1° | keine |
| Ablage 2 | ja | 6 | 0,0034 mm | 1,8° | 0,092–0,108 m | 88,1° | keine |
| Ablage 3 | ja | 6 | 0,0012 mm | 1,7° | 0,000–0,017 m | 88,6° | keine |
| Ablage 4 | ja | 6 | 0,0004 mm | 1,8° | 0,000–0,017 m | 88,3° | keine |

Winkelfehler überall ≤ 0,0003°. Erzeugt mit
`python -m spuelmaschine.erreichbarkeit` (ohne GPU, ~2 s);
`test_gewaehlte_lage_erreicht_alles_kollisionsfrei` prüft dieselbe Tabelle.
Gegenproben: `test_kollision_mit_hindernis_wird_erkannt` (Quader im Anfahrweg),
`test_befund_schiene_am_boden_reicht_nicht`, `test_podest_neben_der_tuer_wird_abgelehnt`.

Der Machbarkeitsbereich ist schmal (3 von 176 Lagen, J5 bis 88,6°): Ablage
etwas weiter hinten, Arbeitsplatte höher oder ein anderer Greifer
(längerer TCP) kippen das Ergebnis. Das Folgeticket mit Wegeplanung sollte
die Lage deshalb mit dem echten Aufbau erneut prüfen.

## 5. Newton-Stabilität

`python -m spuelmaschine.stabilitaet --device cpu` baut die statische Szene
(75 Quader + Bodenebene) und 4 freie Gläser (Vollzylinder, 0,25 kg) in Newton
1.6.1 (MuJoCo-Warp 3.12.0, Newton-Kollisionspipeline, dt 2 ms, Kontakt
ke 2500 / kd 100 wie die Greifdemo), lässt 0,2 s einschwingen und misst 2,0 s.

| Glas | Drift im Messfenster | Einsinken unter die Ruhelage | Kippung max. |
|---|---|---|---|
| 1–4 | 0,0031–0,0047 mm | 0,121 mm | 0,097° |

Bestanden: Drift < 1 mm, Einsinken < 5 mm, keine NaN. CPU-Lauf 43 s
Wandzeit. Gegenprobe ohne Korbboden (`--ohne oberkorb_boden`): alle Gläser
fallen 337 mm, Exit 1. Beides als pytest:
`RAEUMWERK_RUN_NEWTON=1 RAEUMWERK_NEWTON_PYTHON=<Python mit Newton> pytest -q tests/test_spuelmaschine.py -k newton`.
Das Python liefert z. B.

```bash
uvx -p 3.12 --with newton==1.6.1 --with warp-lang==1.17.0 --with mujoco==3.12.0 \
    --with mujoco-warp==3.12.0 --with numpy --with pyyaml --with pytest \
    python -c 'import sys; print(sys.executable)'
```

Auf einem geteilten GPU-Rechner gilt auch für diesen CPU-Lauf die
GPU-Warteschlange (`docs/START.md`).

## 6. Vorschau

```bash
python scripts/vorschau_spuelmaschine.py --out spuelmaschine.png [--slot 1]
```

Schrägansicht aus dem Raum und Draufsicht: Korpus, offene Tür, ausgezogener
Oberkorb mit Glashaltern und Gläsern, Arbeitsplatte mit Ablage, Podest,
Schiene und der ReBeL (Kollisionsquader) in der Greifpose eines Slots. Der
Video-Renderer bleibt unberührt.

## 7. Grenzen

- Nur Posen und senkrechte Wege sind geprüft, nicht der Transport vom Korb
  zur Ablage (Wegeplanung und Umdrehen: `docs/ausraeumen.md`).
- Korb als feste Pose; der Schiebeweg ist nur beschrieben, nicht in Newton
  simuliert.
- Gitterkörbe als wenige Stäbe und Platte, Gläser als Vollzylinder.
- Oberkorbhöhe, Auszug, Wandhöhe und Glashalter sind Annahmen; an der
  echten Maschine nachmessen.
- Die IK-Suche probiert je Ziel 10 Startposen; eine Lage mit „IK ohne
  Lösung“ kann in Grenzfällen doch lösbar sein (der Reichweitenvorfilter ist
  dagegen exakt für den senkrechten Greifer).
