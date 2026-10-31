# Eigene 100-mm-Finger für den igus-Greifer 0-LCA-GRI-0100

Parametrische Finger als CAD (build123d, STEP/STL), Balkenrechnung je Werkstoff
und Greifsimulation in Newton im Aufbau „Arm auf der Spülmaschine“
(Szenario A1-S1, `beispiele/auf-maschine-korb-aus-finger100.yaml`).
Alle Parameter mit Quelle oder `annahme`: `config/finger.yaml`
(Finger) und `config/finger_a1.yaml` (Szenario). Zahlen: `docs/STATUS.md`.

| Teil | Datei |
|---|---|
| Parameter, abgeleitete Maße | `config/finger.yaml`, `finger/parameter.py` |
| CAD (build123d) → STEP/STL/JSON | `finger/cad.py`, `scripts/finger_cad.sh`, `cad/finger/` |
| Balkenrechnung | `finger/festigkeit.py` (`python -m finger.festigkeit --md`) |
| Kollisionsform für die Simulation | `finger/kollision.py` |
| Szene, Planung, Bewertung A1-S1 | `finger/a1.py` |
| Newton-Lauf mit Fingerkontur, Teller | `finger/sim.py` (auf `ausraeumen/sim_newton.py`) |
| Lauf, ein Befehl | `scripts/run_finger_a1.sh` (`scripts/demo_finger_a1.py`) |
| CAD-Prüfbilder | `finger/ansichten.py` |
| Tests | `tests/test_finger.py`, `tests/test_finger_a1.py`, `tests/test_finger_sim.py` |

## 1. Konstruktion

Fingersystem: Ursprung Mitte der Anschlussfläche, z zur Spitze, y in
Schließrichtung zum Greifgut, x quer. Innenbezugsebene y = 0 = Kanten der V-Kontur.

| Parameter | Wert | Quelle |
|---|---|---|
| Länge (Anschluss → Spitze) | 100 mm | Auftrag |
| Breite (quer) | 18 mm | Auftrag (15–20 mm) |
| Dicke in Schließrichtung | 14 mm an der Wurzel → 10 mm ab z 45 mm | Annahme: dünn, wo der Finger zwischen die Nachbargläser taucht (Spitze bis ~55 mm dahinter) |
| V-Kontur | Flanken 8° gegen die Bezugsebene, Nut 1,26 mm tief, z 40–100 mm | Annahme |
| Auflagen | TPU 85A oder Silikon 2 mm, je Flanke 7 mm breit, z 43–85 mm, in 1,5 mm tiefen Taschen (0,5 mm Überstand) | Auftrag (2 mm), Rest Annahme |
| Teller: Kerbe | z 87–95 mm, 2,5 mm tief, Grund r 1 mm | Annahme |
| Teller: Lippe | z 95–100 mm (V-Profil, Fase 1,5 mm) | Annahme |
| Anschluss | Platte 18 × 24 × 8 mm, 2 × M4 (Ø 4,5, Senkung Ø 8 × 4,5) im Abstand 14 mm entlang y | **ANNAHME**, Lochbild der Backe bei igus angefragt |
| Lage zur Backe | Bezugsebene 2,5 mm innen vor der Backenfläche | Annahme |
| Außenkanten | r 1 mm | Annahme |

**V-Kontur:** Ein Glas (Achse parallel zum Finger, Griff von oben) liegt
auf zwei Linien je Finger bei x = r·sin 8° (Ø 65 mm: 4,5 mm, Ø 85 mm: 5,9 mm),
immer auf den Auflagen (Test `test_v_kontur_beruehrt_glas_auf_beiden_auflagen`).
Die Zentrierkraft quer ist klein (tan 8° ≈ 0,14 der Greifkraft); der Nutzen
ist die Zwei-Linien-Auflage gegen Kippen um die Schließachse. Die harte
Lippe liegt im Nutgrund hinter den Auflagen, beim Glas berühren die weichen
Auflagen zuerst (`test_lippe_steht_hinter_den_auflagen`).

**Teller:** Der Teller wird oben am Rand gegriffen, die Spitze 10 mm unter
der Tellerkante. Der Randwulst (Annahme 5 mm, Auftrag 3–6 mm) liegt in der
Kerbe, die Lippen klemmen die Fahne darunter (Annahme 3 mm). Beim ganz
geschlossenen Greifer (5 mm Backenabstand) berühren sich die Lippen, die
Fahne wird also auch bei 3 mm noch geklemmt; über die Lippen kommt der
Wulst nicht (Formschluss gegen Herausrutschen nach unten). Quelle für
Randmaße: keine gefunden, Bereich aus dem Auftrag.

**Öffnung:** Backen 5–105 mm (igus) → Bezugsebenen 0–100 mm, Auflagen
99 mm offen: ein 85-mm-Glas hat 7 mm Luft je Seite.

CAD: `scripts/finger_cad.sh` (build123d 0.13.0 über uvx, nur Wheels, keine
Systempakete; CadQuery wäre ebenfalls über Wheels gegangen, build123d hat
die knappere algebraische API und denselben OCCT-Kern). Ausgabe
`cad/finger/finger_100.step` (131 kB), `finger_100.stl` (69 kB),
`auflage.stl`, `finger_100.json`: Volumen 18 865 mm³ (Näherung aus den
Parametern 18 950 mm³, Abweichung 0,5 %), alle Merkmale angewandt, Körper
gültig. Eigene Konstruktion, darf veröffentlicht werden.

## 2. Werkstoff, Masse, Festigkeit

Kragbalken, eingespannt unter der Anschlussplatte, Netto-Rechteckquerschnitt
(Nut und Tasche konservativ über die ganze Breite abgezogen), Formzahl 2,0
im Kerbgrund und 1,5 am Übergang zur Platte. Lastfälle je Finger:
`glas_griff` (Greifkraft am Griffpunkt 30 mm hinter der Spitze + halbes
Glasgewicht × 2 quer, Seitgriff) und `teller_lippe` (Greifkraft an der Lippe
+ Tellermoment um die Schließachse 0,35 kg · g · 95 mm · 2 / 2 + halbes
Tellergewicht × 2 längs). Zulässig = Festigkeit × Abminderung (0,7 für
Kunststoff: Feuchte, Wärme bis ~60 °C, Alterung).

| Werkstoff | Masse je Finger | Lastfall | F je Finger | σ max (Ort) | Sicherheit | Durchbiegung Spitze |
|---|---|---|---|---|---|---|
| PA12, Lasersintern (PA 2200) | 17,6 g | glas_griff | 10 N | 1,88 MPa (z 8 mm, Anschlussplatte) | 15,6 | 0,45 mm |
| PA12, Lasersintern (PA 2200) | 17,6 g | teller_lippe | 10 N | 4,20 MPa (z 45 mm, Auflagetasche) | 7,0 | 1,05 mm |
| PA12, Lasersintern (PA 2200) | 17,6 g | glas_griff | 20 N | 3,46 MPa | 8,5 | 0,91 mm |
| PA12, Lasersintern (PA 2200) | 17,6 g | teller_lippe | 20 N | 7,55 MPa | 3,9 | 2,10 mm |
| PETG, FDM (Prusament) | 24,1 g | teller_lippe | 10 / 20 N | 4,20 / 7,55 MPa | 3,0 / **1,7** | 1,16 / 2,31 mm |
| Aluminium EN AW-6082 T6, gefräst | 51,2 g | teller_lippe | 10 / 20 N | 4,20 / 7,55 MPa | 59,5 / 33,1 | 0,03 / 0,05 mm |

Vollständige Tabelle: `python -m finger.festigkeit --md`. Masse aus dem
CAD-Volumen × Dichte (Tabelle oben: Näherung aus den Parametern, 17,6 g;
CAD 17,5 g).

**Gewählt: PA12, lasergesintert (PA 2200).** Mindestsicherheit 3,9 bei
20 N (Grenze 2 erst bei ~39 N je Finger), Masse 17,5 g je Finger (statt der
bisher angenommenen 83 g). Keine Lagenhaftungs-Schwäche wie beim FDM-PETG
(dort 1,7 bei 20 N an der Lippe, durchgefallen; außerdem
Wärmeformbeständigkeit nur 68 °C bei frisch gespültem Geschirr).
Aluminium 6082 hält mit großem Abstand und biegt sich kaum (0,05 mm),
wiegt aber 51 g je Finger und braucht Auflagen auch an der Lippe; es bleibt
die Wahl, falls die Durchbiegung von PA12 (bis 2,1 mm an der Spitze bei
20 N) beim Tellergriff stört. Lebensmitteleignung von PA 2200 beim
Hersteller bestätigen lassen (offen).

## 3. Simulation im Aufbau A1-S1

Newton 1.6.1 (MuJoCo-Warp 3.12.0, eigene Kollisionspipeline, dt 2 ms),
Finger als CAD-nahe Quader (`finger/kollision.py`), jedes Objekt einzeln
geplant und simuliert, bereits abgeräumte Objekte stehen am Ziel
(`--erledigt`). Grenzen wie beim Ausräumen: Zielfehler ≤ 10 mm, Kippung
< 10°, Fingerdurchdringung ≤ 3 mm, Nachbarn ≤ 5 mm. Läufe auf der CPU
und auf einer Laptop-GPU (`--device cuda`): gleicher Plan, Glas 3 bei 10 N
CPU 3,06 mm / 4,32 mm, GPU 3,07 mm / 4,15 mm (Durchdringung / Zielfehler),
GPU ~8× schneller (313 s statt 2 510 s Wandzeit).

**Gläser: 1 von 8.** Greifkraft in der Simulation 7 N je Finger
(10 N: Glas 3 mit 3,06 mm knapp über der Grenze, Phase Anheben im Seitgriff).

| Glas (Platz) | Ergebnis | Zahlen / Grund |
|---|---|---|
| 3 (5) | **Erfolg** | Zielfehler 4,45 mm, Kippung am Ende 0,10° (Start 180°), Aushub 150 mm, Wanderung in der Hand 1,7 mm, Finger 2,86 mm, Nachbarn 0,03 mm |
| 4 (6) | Fehlversuch, `durchdringung` | geplant und physikalisch am Ziel (Zielfehler 8,6 mm, Kippung 0,10°), aber Fingerdurchdringung im Seitgriff beim Anheben 3,57 / 3,33 / 3,07 mm bei 10 / 7 / 5 N – kaum kraftabhängig, Grund ist die Neigung des Glases in der Hand |
| 1, 2 (1, 2) | nicht planbar | Ablage auf der hinteren Brettreihe (Sockel 5 cm): nach dem Abstellen reißt der IK-Weg des waagerechten Seitgriffs zum Umdrehen bei allen 12 Gierwinkeln ab (Handgelenk neben dem Fuß) |
| 5, 6 (9, 10) | nicht planbar | Gelenkfahrt Korb → linkes Brett neigt das getragene Glas 30–32° (Grenze 30°); Ausweichhübe treffen Podest/Platte, über die Zwischenposen reißt die IK ab |
| 7, 8 (13, 14) | nicht planbar | Gelenkfahrt führt Finger und Glas durch die Arbeitsplatte; alle Ausweichwege kollidieren oder reißen ab |

Die Gründe für 1, 2, 5–8 liegen im Aufbau (Fuß auf der Maschine,
Ablage neben dem Fuß), nicht an den Fingern; weiteres Iterieren an den
Ablagepunkten wurde abgebrochen.

**Variation Glas 3:** 5 Läufe (Seeds 11–15; Glas ±5 mm / ±3°, Korbauszug
0 … −1 cm, der Korb steht am Anschlag): **5/5 Erfolg**, Zielfehler
4,47–4,77 mm, Finger 2,86–2,88 mm, Kippung 0,10°, Hand ≤ 1,8 mm.

**Negativtest:** Glas 3 im zu engen Halter (verklemmt) wird erkannt:
`nicht_aus_dem_korb` (Aushub 0 mm), dazu `nicht_am_ziel`, `gefallen`
(bei 10 N und 7 N).

**Teller: 0 von 6.** Griff oben am Rand, Wulst in der Kerbe, Lippen unter
dem Wulst; Ablage hochkant im Ständer.

- Startfehler behoben: Teller im Ständer (schon abgeräumt) starteten
  quer zu ihren Stäben, die Simulation flog auseinander (Teller 4–6,
  Nachbarn bis 1,3 m). Jetzt Startlage = Planungslage
  (`finger.sim.teller_koerper_rot`, `tests/test_finger_sim.py`).
- Teller 1, 3 mm Luft im Halter: Teller lehnt 3,9° an den Stäben, der
  absenkende Finger streift die Oberkante, der Teller dreht sich 7,6° in
  seiner Ebene und rutscht beim Aushub aus dem Griff (10 N und 20 N).
- Mit 1 mm Luft (Annahme jetzt): Aushub 192 mm erreicht, dann pendelt der
  Teller in der Hand um die Tellernormale (2° → 22°) und fällt beim Beginn
  der Querfahrt (Teller 1 und 4 gleich). Fingerdurchdringung 6,9–7,5 mm:
  der 1-mm-Formschluss des Wulstes (5 mm Wulst, 3 mm Fahne) ist kleiner als
  die Nachgiebigkeit der weichen Kontakte.
- Folgerung: Ein 18 mm breiter Randgriff hält den Teller nicht gegen
  Drehen in seiner Ebene. Nötig wäre eine Zwei-Punkt-Auflage am Rand
  (breitere Spitze oder Gabel, z. B. 40–60 mm Abstand der Auflagen) –
  zwischen Tellern mit 6 cm Teilung schwer unterzubringen – oder ein
  anderer Griff. Nicht mehr gerechnet.

## 4. Momente mit der CAD-Masse

`raeumwerk aufbau` mit `beispiele/auf-maschine-korb-aus-finger100.yaml`
(Finger 17,5 g statt 83 g): J2 höchstens **14,81 Nm** an den Glasplätzen
und **14,84 Nm** an den Tellern. Gerechnet ist jede Gliedmasse im Schwerpunkt
(seit 31.10.2026; Gliedermassen geschätzt, Schwerpunkte = Quadermitte, Annahme).
Mit der Masse im Gliedursprung waren es 12,52 / 12,58 Nm, mit 83-g-Fingern
13,0 / 13,06 Nm. Das liegt über der igus-Nenngröße 10 Nm und über dem Maximum
12,5 Nm (`config/robot.yaml`); die leichteren Finger allein lösen das
J2-Problem nicht.

## 5. Annahmen, die igus bestätigen muss

- Lochbild und Lage der Backen (Anschlussplatte 2 × M4, 14 mm, Bezugsebene
  2,5 mm vor der Backenfläche).
- Greifkraft (simuliert 7 N je Finger bei Gläsern, 10–20 N bei Tellern,
  Festigkeit gerechnet bis 20 N) und ob der Greifer sie geregelt hält.
- Zulässige Fingerlänge, -masse und Kippmoment an der Backe (100 mm,
  17,5 g; Tellermoment an der Spitze bis ~0,33 Nm je Finger).
- Körpermaße (Annahme 150 × 50 × 50 mm) und Masse des Greifers (0,40 kg).
- Zulässiges J2-Moment im Dauerbetrieb (gerechnet bis 14,84 Nm, siehe §4).

Weitere eigene Annahmen (nicht igus): Auflagen TPU 85A/Silikon und deren
Reibwert, Tellerrand (Wulst 5 mm, Fahne 3 mm), Halterluft 1 mm,
Lebensmitteleignung PA 2200 (Hersteller).

## 6. Bilder

Prüfbilder (matplotlib aus der STL bzw. den Kollisionsquadern, kein
Rendering) und eine schematische Vorschau des gelungenen Glaslaufs
(matplotlib, kein Isaac-Render), außerhalb des Repos.
