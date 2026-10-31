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
| Newton-Lauf (Kurz- und Vollablauf), Reihe, Wahrnehmung allein, Auswertung | `scripts/griff_lauf.py`, `scripts/griff_serie.sh`, `scripts/griff_wahrnehmung.py`, `scripts/griff_auswertung.py` |
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

**Startwert ohne Wahrheit.** Alles, was die Schätzer vorab wissen, kommt aus der **Nennlage laut
Belegungsplan** (`griffpose.schaetzen(..., nennlage)`): Welt ohne Lageabweichung, verschoben um den
von der Ensenso gemessenen Korbauszug. Daraus kommen Suchstart und Suchfenster (Glas: Platzmitte;
Teller: Kreis-Suchfenster 30 mm um die Nennmitte), Bildausschnitt (ROI), erwartete Tellernormale,
Bodenhöhe (Glas) und Modellmaße. Die wahre Lage geht nur in die Szene ein, die die Kameras sehen,
und in die Fehlerangaben. Nachweis: `test_griffpose_glas_liest_die_wahrheit_nicht` und
`test_griffpose_teller_liest_die_wahrheit_nicht` verschieben nur die Wahrheit (Glas 5 mm, Teller
35 mm + 3°) bei gleicher Szene: Pose, Normalenprüfung und ausgewertete Pixel bleiben bitgleich.
`test_griffpose_glas_folgt_der_szene` verschiebt die Szene: die Schätzung folgt. Mutationen, die
den alten Startwert (`wahr[:2]`, `c0 = wahr`, Normale aus der wahren Drehung, ROI um die Wahrheit)
zurückbringen, machen diese Tests rot. Einzige Stelle mit Wahrheit im Schätzpfad bleibt das
Sensormodell der Korbpose (wahrer Auszug + Rauschen σ 1,5 mm, als Messung modelliert).

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
| Tiefenrauschen entlang des Strahls | σ = k·z², Ensenso k = 1,533·10⁻³ 1/m (0,38 mm bei 0,5 m), D405 k = 0,02 1/m (±2 % bei 0,5 m als 2σ) | Datenblätter; `test_tiefenrauschen_sigma_wie_datenblatt` |
| Glas, je gültigem Glaspixel | 50 % kein Wert, 35 % Durchblick (Tiefe des Hintergrunds), 15 % Reflex (Glasfläche ± 8 mm) | Annahme nach Literatur zu transparenten Objekten (Kamerastudie) |
| Nässe / Glanz | 5 % zufällige Ausfälle auf nassen Flächen; Ausfall, wenn Normale < 10° zum Sehstrahl (Teller, Glas) | Annahme |
| Kanten / flache Winkel | Sprung > 2 cm: jeder zweite Pixel fällt aus; kein Wert über 60° (Ensenso) / 70° (D405) | Annahme |
| Farbmaske | Randpixel kippen mit 50 % (±1 px), dazu ganze Maske um N(0; 0,7 px) je Achse versetzt (Registrierung) | Annahme; `test_maskenversatz_verschiebt_ganze_maske` |
| Kalibrierung je Aufnahme | Ensenso 1,5 mm / 0,05°, D405 (Hand-Auge) 1,0 mm / 0,2° | Annahme |

### Ergebnis Wahrnehmung allein (20 Seeds, Fehler gegen die Wahrheit)

Reproduzieren: `scripts/griff_wahrnehmung.py --alle AUSGABE`, dann `scripts/griff_auswertung.py
AUSGABE` (CPU, ~5 s je Objekt).

| Objekt | angenommen | Ensenso Mittel / Max | D405 = Griffpose Mittel / Max |
|---|---|---|---|
| Glas | 19/20 (Seed 20: Ensenso 5,5 mm daneben, Abstand zur D405 6,9 mm > 6 mm → Abbruch; die D405-Pose wäre 1,7 mm gut gewesen) | 1,9 / 5,5 mm | 1,3 / 3,4 mm |
| Teller | 20/20 | 3,0 / 5,8 mm | 3,2 / 5,3 mm |

Mit dem früheren Startwert aus der Wahrheit waren es Glas 20/20 (Ensenso 2,0 / 4,1 mm, Griffpose
1,5 / 2,3 mm) und Teller 19/20 (Ensenso 3,3 / 13,4 mm, Griffpose 2,8 / 5,3 mm). Ohne Wahrheit wird
die Glas-Grobpose etwas schlechter (Max 4,1 → 5,5 mm), ein Glas fällt als Widerspruch heraus (sicherer
Abbruch, kein Fehlgriff); beim Teller ändert sich der Fehler der Griffpose im Mittel um 0,4 mm.

### Negativtests (je 5 Seeds): alle abgelehnt

| Fehler | Glas | Teller | Grund |
|---|---|---|---|
| zwei Objekte in einer Maske (Fehlsegmentierung) | 0/5 angenommen | 0/5 | Glas: Kontur-Inlier, Modell passt nicht; Teller: Ebenen-Inlier |
| Grobpose 15 mm daneben (Kalibrierfehler) | 0/5 | 0/5 | Ensenso ↔ D405 widersprechen sich (Abstand Glas 15,3 / 16,2 mm, Teller 15,6 / 17,1 mm); Teller-Toleranz zusätzlich `test_griffpose_teller_widerspruch_ensenso_d405` |
| Nachbar statt Ziel segmentiert | 0/5 | 0/5 | Glas: Kontur passt nicht; Teller: 61–65 mm neben dem Platz laut Belegungsplan |

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
| (b') wie (b), Sollkraft 6 N (~10 N am Wulst), `breit_6n` | hält, siehe Robustheit; Standard in `scripts/griff_lauf.py` |
| (d) 18-mm-Finger, 20 N, halbe Geschwindigkeit | **fällt** wie (a): Absturz am Ende des Aushubs, Finger 6,1 mm |
| (c) Kippen/Anlehnen vor dem Herausziehen | nicht gerechnet: ändert nichts am Drehen in der Tellerebene um einen Griffpunkt |

Warum (b) hält: die gerade Backe liegt seitlich auf dem gekrümmten Wulst auf (Bogenstich 4,9 mm
bei ±30 mm), der Teller hat zwei weit auseinanderliegende Auflagen und kann nicht mehr um einen
Punkt pendeln. Weil die Backe am 5-mm-Wulst statt an der 3-mm-Fahne schließt, ist die Kraft über die
Fingersteifigkeit höher (10 N Soll → ~17 N, Fingerdurchdringung 3,1–3,2 mm); deshalb (b') mit 6 N
Soll. Die Grenze der Fingerdurchdringung bleibt bei 3 mm.

## Robustheit (Griffpose aus der Wahrnehmung)

Je Lauf: Lageabweichung im Korb (Glas ±5 mm / ±3°, Korb 0…−1 cm; Teller x ±5 mm, Reihe y ±5 mm,
Gier ±1°, mehr lassen die Stäbe nicht zu) und Rauschseed. Reproduzieren: Liste mit Zeilen
`<name> --art glas|teller --seed S --wahrnehmung [--voll] --device cuda` an
`scripts/griff_serie.sh AUSGABE LISTE`, dann `scripts/griff_auswertung.py AUSGABE` (eine Tabelle je
Reihe). Laufzeit auf einer Laptop-GPU (12 GB): Kurzlauf ~65 s, Vollablauf Teller ~3 min, Glas ~5 min.

**Kurzlauf** — Erfolg: Aushub ≥ 80 mm, Wanderung in der Hand ≤ 20 mm, Kippung in der Hand < 10°,
Nachbarn ≤ 5 mm, Finger ≤ 3 mm, kein Kontakt Arm ↔ Korb.

| Objekt | Erfolg | Pose-Fehler | Kippung in der Hand | Hand | Nachbarn | Finger |
|---|---|---|---|---|---|---|
| Glas (bis Aushub 150 mm), Seeds 1–10 | **10/10** | 0,4–1,6 mm | 0,8–1,2° | 0,7–0,9 mm | 0,2 mm | 1,2–1,6 mm |
| Teller `breit_6n` (bis nach der ersten Querfahrt), Seeds 1–12 | **12/12** | 2,0–5,3 mm | 2,0–3,1° | 4,2–5,5 mm | 3,3–3,4 mm | 2,2–2,5 mm |
| zum Vergleich: Teller `breit` 10 N, früherer Startwert, 11 Seeds | 7/11 | 1,4–5,3 mm | 1,5–2,3° | ≤ 5,0 mm | ≤ 3,4 mm | 2,5–3,2 mm (3 × über 3 mm) |

Die Nachbarteller wandern in jedem Lauf gleich weit (3,2–3,4 mm, auch mit Wahrheits-Pose),
unabhängig vom Seed.

**Voller Ablauf** — Glas: Griff → Aushub → Zwischenablage → Umgreifen von der Seite → Umdrehen →
Ablage (125,5 s simuliert); Teller: Griff → Aushub → Transport (22 s) → Absetzen im Ständer (58,6 s).
Kriterien wie `ausraeumen.bewertung`: Zielfehler ≤ 10 mm, Kippung am Ende < 10°, Hand ≤ 20 mm,
Standhöhe ± 5 mm, Nachbarn ≤ 5 mm, Finger ≤ 3 mm, Kontakte, Objekt ≤ 1 m/s. Teller-Kippung =
Neigung der Tellerebene gegen die Senkrechte (`griff_lauf.teller_lage_grad`); `finger.a1.bewerte_teller`
misst die Körperachse und zählt so die Drehung des Tellers in seiner Ebene mit, beim Kapselring-Teller
schon zu Beginn 7,5° (halbes Segment). Mit dem alten Maß stünden Teller 1, 3 und 9 bei 8,4°, Teller 5
bei 23,1° (`gekippt`); an der Quote ändert das nichts.

| Objekt | Erfolg | Zielfehler | Kippung am Ende | Hand | Nachbarn | Finger |
|---|---|---|---|---|---|---|
| Glas, Seeds 1–5 | **5/5** | 5,5–7,0 mm | 0,1° | 2,0–2,6 mm | ≤ 0,1 mm | 2,8 mm |
| Teller `breit_6n`, Seeds 1–10 | **2/10** | 8,7 / 9,9 mm (die zwei Erfolge) | 3,8° | 6,8–7,0 mm | 3,2–3,3 mm | 2,2–2,3 mm |

Teller-Fehlschläge (alle mit Aushub 200 mm und gehaltenem Teller bis in die Querfahrt):

| Ursache | Seeds | Befund |
|---|---|---|
| fällt im Transport | 2, 6 | Teller dreht sich in der Hand in seiner Ebene um den Griffpunkt und fällt zu Boden (Phase `zur_ablage`; im ersten Lauf von Seed 2 ab 37,2 s, kurz vor dem Ständer beim Abbremsen) |
| wird beim Einsetzen in den Ständer herausgeschlagen | 7, 8, 10 | Absetzen (38,6–40,4 s): Teller stößt an den Ständerhalter, kippt auf 71–74° und liegt auf dem Ständer; Seed 10 hatte sich im Transport schon 12° in der Ebene gedreht |
| steht im Ständer, Zielfehler knapp über 10 mm | 3, 4 | 11,0 / 10,1 mm, davon ~6 mm quer (Teller lehnt 3,4–3,8° im Spiel des Halters) und 8,5–9,4 mm längs der Reihe (Griffpunkt + 7 mm Wanderung in der Hand) |
| Zielfehler 17 mm + Finger 4,2 mm | 5 | beim Absetzen drückt der Ständer den Teller in die Backe, er dreht sich 15° in der Ebene |

Auch die zwei Erfolge liegen mit 8,7 / 9,9 mm knapp unter der Zielgrenze. Der Tellergriff hält im
Korb und in der ersten Querfahrt (12/12), aber nicht zuverlässig über Transport und Ablage: der
Teller wandert 7 mm in der Hand und kann um den Griffpunkt drehen; das Einsetzen in den Ständer ist
nicht nachgeführt (keine Messung des Tellers in der Hand, kein Ausrichten am Ständer).

## Vereinfachungen

- Im Glaslauf stehen die Teller statisch, im Tellerlauf die Gläser (als Quader) — die jeweils
  andere Korbhälfte, Abstand > 7 cm.
- Wahrnehmung einmal vor dem Griff (Ensenso) und einmal in der Vorposition (D405); kein
  Nachführen während des Absenkens und keine Messung des Objekts in der Hand vor der Ablage.
  Primitive statt Meshes im Strahlschnitt.
- Instanzsegmentierung ideal bis auf Randrauschen, Versatz und die Negativtests.
- Newton auf der GPU ist nicht bitgleich wiederholbar: derselbe Seed liefert leicht andere Zahlen
  (Teller Seed 2 fiel in zwei Läufen, mit verschiedener Endlage).
