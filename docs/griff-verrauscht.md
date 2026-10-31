# Griff Glas + Teller aus verrauschter Wahrnehmung (Ensenso + D405)

Aufbau: Roboter auf der Spülmaschine ohne Überstand (`beispiele/auf-maschine-ohne-ueberstand.yaml`,
Fuß (0,35; −0,05; 0,86)), Oberkorb fest ausgezogen und gemischt belegt: 8 Gläser kopfüber auf den
Plätzen 1–8 (rechte Korbhälfte), 6 Dessertteller Ø 19 cm hochkant in der Tellerreihe x 0,15
(Teilung 6 cm, Stäbe mit 1 mm Luft, Rollsperren). Gegriffen wird ein Glas (Platz 5) und ein Teller
(vorderster). Die Griffpose kommt aus der simulierten Sensorik, nicht aus der Wahrheit: geplant wird
in der Welt, die die Wahrnehmung liefert, simuliert (Newton 1.6.1) in der wahren Welt.

| Teil | Datei |
|---|---|
| Kameramodelle, Strahlschnitt | `wahrnehmung/strahlen.py` |
| Fehlermodell (Rauschen, Glas, Nässe, Maske, Kalibrierung) | `wahrnehmung/sensor.py` |
| Schätzer Glas (Zylinder auf der Silhouette, Modellwahl), Teller (Ebene + Kreis) | `wahrnehmung/schaetzer.py` |
| Ablauf Ensenso → D405 → Prüfung → Griffpose oder Abbruch | `wahrnehmung/griffpose.py` |
| Tellergriff-Varianten (Parameter + Kollisionsform) | `finger/tellergriff/varianten.yaml`, `finger/tellergriff/varianten.py` |
| Tests | `tests/test_wahrnehmung.py` |

## Wahrnehmung

1. **Ensenso** (fest am Mast mit Ausleger, (0,55; 0,40; 1,10), Blick auf die Korbmitte; halbe
   Auflösung) nimmt den Korb auf. Das Ziel kommt als Instanzmaske aus der Farbsegmentierung.
   Grobpose: Glas aus der Silhouette, Teller aus Ebene + Kreis (siehe unten). Die Korbpose
   (Auszug) kommt aus der Ensenso mit σ 1,5 mm.
2. **D405** am Greifer (60 mm seitlich der Werkzeugachse, 13 cm über dem TCP, 20° zur Achse
   geneigt), Greifer 10 cm über der Grobpose: Feinpose mit demselben Schätzer, Greifer und Finger
   verdecken einen Teil des Bilds.
3. **Prüfung**, sonst Abbruch ohne Griff: jeder Schätzer für sich (Modell-Passwert, freier Radius
   ±4 mm, Kontur-Inlier ≥ 50 %; Teller: Ebenen-Inlier ≥ 60 %, Normale ≤ 8°, Kreis-RMS ≤ 2 mm,
   Bogen ≥ 40°), Ensenso und D405 stimmen überein (Glas ≤ 6 mm, Teller ≤ 8 mm), und die Pose liegt
   höchstens 15 mm neben dem Platz laut Belegungsplan (Teilung 6 cm bzw. Glasplätze).

**Glas:** Die Tiefe des transparenten Glases ist unbrauchbar, die Kontur im Farbbild nicht. Jeder
Randstrahl der Maske streift den Glaszylinder: sein kleinster waagerechter Abstand zur Glasachse im
Höhenbereich des Glases (Halterhöhe aus dem Korbmodell + Modellhöhe) ist der Radius. Gauss-Newton
auf die Achse mit robusten Gewichten (Verdeckungskanten der Nachbarn fallen heraus). Modellwahl
(Glas Ø 75 / Ø 65, Becher Ø 84) über den Restfehler der Konturinlier, den Inlier-Anteil und den
Anteil der Innenstrahlen, die das Modell treffen.

**Teller:** Keramik, Tiefe gut. RANSAC-Ebene auf den Maskenpunkten (Normale = Lage der Reihe), in
der Ebene die obere Kontur (höchster Punkt je 4-mm-Streifen) und ein Kreis mit Modellradius
(Ø 190 / 215 / 260 mm). Die D405 sieht den Teller von oben nur als Randstreifen (Bogen); ihre
Feinpose korrigiert die Lage im Teller, die Normale kommt aus der Ensenso.

### Rauschannahmen

| Größe | Wert | Herkunft |
|---|---|---|
| Tiefenrauschen entlang des Strahls | σ = k·z², Ensenso k = 1,533·10⁻³ 1/m (0,38 mm bei 0,5 m), D405 k = 0,02 1/m (±2 % bei 0,5 m als 2σ) | Datenblätter |
| Glas, je gültigem Glaspixel | 50 % kein Wert, 35 % Durchblick (Tiefe des Hintergrunds), 15 % Reflex (Glasfläche ± 8 mm) | Annahme nach Literatur zu transparenten Objekten (Kamerastudie) |
| Nässe / Glanz | 5 % zufällige Ausfälle auf nassen Flächen; Ausfall, wenn Normale < 10° zum Sehstrahl (Teller, Glas) | Annahme |
| Kanten / flache Winkel | Sprung > 2 cm: jeder zweite Pixel fällt aus; kein Wert über 60° (Ensenso) / 70° (D405) | Annahme |
| Farbmaske | Randpixel kippen mit 50 % (±1 px), dazu ganze Maske um N(0; 0,7 px) je Achse versetzt (Registrierung) | Annahme |
| Kalibrierung je Aufnahme | Ensenso 1,5 mm / 0,05°, D405 (Hand-Auge) 1,0 mm / 0,2° | Annahme |

### Ergebnis Wahrnehmung allein (20 Seeds, Fehler gegen die Wahrheit)

| Objekt | angenommen | Ensenso Mittel / Max | D405 = Griffpose Mittel / Max |
|---|---|---|---|
| Glas | 20/20 | 2,0 / 4,1 mm | 1,5 / 2,3 mm |
| Teller | 19/20 (1 × Ensenso 13,4 mm daneben, als Widerspruch abgelehnt) | 3,3 / 13,4 mm | 2,8 / 5,3 mm |

### Negativtests (je 5 Seeds): alle abgelehnt

| Fehler | Glas | Teller | Grund |
|---|---|---|---|
| zwei Objekte in einer Maske (Fehlsegmentierung) | 0/5 angenommen | 0/5 | Glas: Kontur-Inlier, Modell passt nicht; Teller: Ebenen-Inlier |
| Grobpose 15 mm daneben (Kalibrierfehler) | 0/5 | 0/5 | Ensenso ↔ D405 widersprechen sich |
| Nachbar statt Ziel segmentiert | 0/5 | 0/5 | Glas: Kontur passt nicht; Teller: 62–68 mm neben dem Platz laut Belegungsplan |

Ohne die Platzprüfung wurde der Nachbarteller angenommen (Ensenso und D405 sehen denselben
falschen Teller übereinstimmend); die Prüfung gegen den Belegungsplan ist deshalb Pflicht.

## Tellergriff

Der bisherige 18-mm-Randgriff lässt den Teller in seiner Ebene um den einen Griffpunkt pendeln
(docs/finger.md). Kurzläufe: Start in der Vorposition, runter, greifen, Aushub 20 cm, erste
Querfahrt zum Ständer (dort fiel der Teller bisher), 1 s halten; Teller frei, Gläser statisch.

| Variante | Ergebnis (Griffpose aus der Wahrheit) |
|---|---|
| (a) Gabel: zwei 10-mm-Zinken mit Kerbe/Lippe, Abstand 50 mm, äußere Zinken um den Bogenstich (3,35 mm) länger | **fällt**: Aushub fast erreicht, Absturz am Übergang Aushub → Querfahrt, Finger 7,1 mm im Kontakt (Lippen rutschen über den Wulst) |
| (b) breite Backe 60 mm, flache Kontur (2°), 10 N | **hält**: Aushub 200 mm, Querfahrt, Hand 4,3 mm, Kippung 1,9°, Finger 2,8 mm |
| (b') wie (b), Sollkraft 6 N (~10 N am Wulst) | hält (Seed 2: Finger 2,4 mm statt 3,1 mm bei 10 N) |
| (d) 18-mm-Finger, 20 N, halbe Geschwindigkeit | **fällt** wie (a): Absturz am Ende des Aushubs, Finger 6,1 mm |
| (c) Kippen/Anlehnen vor dem Herausziehen | nicht gerechnet: ändert nichts am Drehen in der Tellerebene um einen Griffpunkt |

Warum (b) hält: die gerade Backe liegt seitlich auf dem gekrümmten Wulst auf (Bogenstich 4,9 mm
bei ±30 mm), der Teller hat zwei weit auseinanderliegende Auflagen und kann nicht mehr um einen
Punkt pendeln. Weil die Backe am 5-mm-Wulst statt an der 3-mm-Fahne schließt, ist die Kraft über die
Fingersteifigkeit höher (10 N Soll → ~17 N); deshalb (b') mit 6 N Soll.

## Robustheit (Griffpose aus der Wahrnehmung)

Je Lauf: Lageabweichung im Korb (Glas ±5 mm / ±3°, Korb 0…−1 cm; Teller x ±5 mm, Reihe y ±5 mm,
Gier ±1°, mehr lassen die Stäbe nicht zu) und Rauschseed. Erfolg: Aushub ≥ 80 mm, Wanderung in der
Hand ≤ 20 mm, Kippung in der Hand < 10°, Nachbarn ≤ 5 mm, Finger ≤ 3 mm, kein Kontakt Arm ↔ Korb.

| Objekt | Erfolg | Pose-Fehler | Kippung in der Hand | Hand | Nachbarn | Finger |
|---|---|---|---|---|---|---|
| Glas (Kurzlauf bis Aushub 150 mm) | **10/10** | 0,4–2,3 mm | 0,7–1,2° | ≤ 0,9 mm | ≤ 0,2 mm | 1,2–2,1 mm |
| Teller, breite Backe 10 N | **7/11**, 1 Abbruch der Wahrnehmung, 3 × `durchdringung` 3,1–3,2 mm | 1,4–5,3 mm | 1,5–2,3° | ≤ 5,0 mm | ≤ 3,4 mm | 2,5–3,2 mm |

Alle Teller-Fehlschläge halten den Teller (Aushub 200 mm, Querfahrt, Hand ≤ 5 mm); sie liegen nur
über der Grenze der Fingerdurchdringung (Kraft am Wulst ~17 N, siehe (b')).

## Vereinfachungen

- Kurzläufe: Glas bis zum Aushub, Teller bis nach der ersten Querfahrt; Umgreifen/Ablage des Glases
  ist im Volllauf mit Wahrheits-Pose gezeigt (docs/finger.md, 5/5), Tellerständer nicht gerechnet.
- Im Glaslauf stehen die Teller statisch, im Tellerlauf die Gläser (als Quader) — die jeweils
  andere Korbhälfte, Abstand > 7 cm.
- Wahrnehmung einmal vor dem Griff (Ensenso) und einmal in der Vorposition (D405); kein
  Nachführen während des Absenkens. Primitive statt Meshes im Strahlschnitt.
- Instanzsegmentierung ideal bis auf Randrauschen, Versatz und die Negativtests.
