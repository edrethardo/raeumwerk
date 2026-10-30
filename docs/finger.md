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
| Tests | `tests/test_finger.py`, `tests/test_finger_a1.py` |

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

PLATZHALTER_FESTIGKEIT

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

PLATZHALTER_SIM

## 4. Momente mit der CAD-Masse

PLATZHALTER_MOMENTE

## 5. Annahmen, die igus bestätigen muss

- Lochbild und Lage der Backen (Anschlussplatte 2 × M4, 14 mm, Bezugsebene
  2,5 mm vor der Backenfläche).
- Greifkraft (gerechnet und simuliert 10 N je Finger, Festigkeit bis 20 N).
- Zulässige Fingerlänge, -masse und Kippmoment an der Backe (100 mm,
  17,5 g; Tellermoment an der Spitze bis ~0,33 Nm je Finger).
- Körpermaße (Annahme 150 × 50 × 50 mm) und Masse des Greifers (0,40 kg).

## 6. Bilder

Prüfbilder (matplotlib aus der STL bzw. den Kollisionsquadern, kein
Rendering), außerhalb des Repos.
