# Konzept: beide Körbe, Körbe ausziehen, Kamerasicht (B57-4 und D405)

Stand: 29.10.2026. **Nur Konzept.** Es gibt keinen Produktcode und keine
Änderung an der Simulation. Die Zahlen stammen aus Überschlagsskripten außerhalb
des Repos. Sie nutzen `spuelmaschine/geometrie.py`, `spuelmaschine/erreichbarkeit.py`
und `rebel_model` unverändert. Nach der Freigabe baut die Ticket-Kette in §9.

## 0. Kurzfassung

- **Kann die B57-4 den Korb genau sehen?** Ja, aber nicht vom Mast neben dem
  Roboterfuß. Dort ist der Korb 0,66–1,15 m entfernt, also meist jenseits der
  0,8 m, die das Handbuch für die Farbvariante nennt. Innerhalb 0,8 m sind dann
  nur 0–21 % der Korbstreben sichtbar. Ein **Ausleger von 0,35 m Richtung
  Maschine** bringt die Kamera auf 0,57–0,94 m. Von dort sind 88 % der
  Glashalter-Slots und 100 % des Geschirrs sichtbar, das Raster beträgt
  0,35–0,58 mm/Pixel, und der simulierte Fehler der Korbpose liegt unter 1 mm.
  Gläser lassen sich aus RGB plus bekannter Glashöhe auf 4,6 mm (Mittel) bzw.
  4,9 mm (Maximum) genau lokalisieren, Teller aus der Tiefe auf 1,3/1,7 mm.
- **Die Tiefe auf Glas taugt nicht für die Glaslage:** Die Fehler liegen bei
  8–18 mm, im Nahbereich der D405 bei 4–29 mm. Glas wird über RGB, Glasmaß und
  Slot lokalisiert. Die Tiefe dient für Korb, Teller und Tassen.
- **Die D405 über dem Greifer** liefert bei **30° Neigung** die Feinlage vor dem
  Griff: Der Zielslot ist zu 89 % sichtbar, das Raster beträgt 0,43–0,62 mm/Pixel,
  und die Tellerlage ist auf 2,4 mm bestimmbar. Greifer und Finger verdecken aber
  29–65 % des Bildes. Beim Greifen selbst verdecken sie 89 % des Glases. Die
  Nahsicht taugt deshalb nur für die Vorposition.
- **Die Erreichbarkeit ist das größere Problem als die Kamera.** Von der Schiene
  bei x = 0,78 m reicht der Arm mit senkrechtem Greifer nur die rechte Korbhälfte
  (x ≥ 0,30 m). Beim Unterkorb gilt das zusätzlich nur ab 0,16 m vor der
  Maschinenfront. Ergebnisse für die Teller: 9/20 Griffpunkte bei 0,40 m Podest,
  3/20 bei 0,65 m. Die Unterkorbfront (Griffhöhe 0,27 m) erreicht der Arm nur
  bei 0,20 m Podest, also auf einer Höhe, auf der die Teller nicht gehen. Die Oberkorbfront lässt sich mit waagerechtem
  Griff über die 7. Achse 43 cm herausziehen.
- **Empfehlung:** B57 am Mast mit Ausleger, D405 über dem Greifer unter 30°.
  Reihenfolge Unterkorb vor Oberkorb. Korbauszug als Schubgelenk mit Reibung und
  Anschlag, gezogen von der 7. Achse. Vor dem Bau muss der Owner die
  Aufbaufrage entscheiden (§8, Frage 1).

## 1. Ausgangslage (Repo)

| Was | Wert | Stelle |
|---|---|---|
| Oberkorb | 525 × 475 mm, Boden 0,42 m, Wand 0,12 m, Auszug 0,45 m (Annahme) | `config/spuelmaschine.yaml:69-82` |
| Unterkorb | 525 × 515 × 140 mm, Boden 0,13 m, Auszug 0,45 m, ohne Inhalt | `config/spuelmaschine.yaml:84-90` |
| Korbauszug | nur als Beschreibung `korbgelenke` (prismatic, +y), in der Szene feste Pose | `spuelmaschine/geometrie.py:181-186`, `docs/spuelmaschine.md:73-75` |
| Schiene | senkrecht zur Front, Ursprung (0,78; 0,06; 0,65), Hub 1,0 m | `config/scene_spuelmaschine.yaml:23-29`, `config/robot.yaml:67` |
| Podest | 0,65 m wegen der Ablage (Griff von oben); mit Seitgriff und Konsole ~0,40 m | `docs/spuelmaschine.md:115-124`, `docs/ausraeumen.md:210-237` |
| Kamera | B57-4 Farbe am Mast auf dem Schlitten; D405 bisher ersetzt | `docs/hardware-auswahl.md:17-41`, `:171` |
| Gelenkmoment im Modell | 40 Nm je Gelenk (**Annahme**) | `config/robot.yaml:45` |
| Zugkraft 7. Achse | 300 N (**Annahme**) | `config/robot.yaml:75` |

## 2. Kameramodelle (Datenblattwerte)

| Größe | Ensenso B57-4 | RealSense D405 |
|---|---|---|
| Auflösung im Modell | 2024 × 2061 px (3D-Sichtfeld 621 × 633 mm bei 500 mm ÷ 0,307 mm Pixel) [K1] | 848 × 480 (Min-Z 70 mm); 1280 × 720 hat Min-Z 100 mm [K3] |
| Brennweite (px) | 1628,7 (aus 0,307 mm/px bei 500 mm) [K1] | fx 447, fy 433 aus 87° × 58° [K2] |
| Arbeitsbereich | 210–2000 mm laut Datenblatt [K1]; Farbvariante laut Handbuch bis 800 mm [K4] | 7–50 cm [K2] |
| Tiefenfehler | 0,383 mm bei 0,5 m, Datenblatttabelle ∝ d² (1,533 mm bei 1 m) [K1] | ±2 % bei 50 cm [K2], hier als 2σ und ∝ d² (σ 0,45 mm bei 15 cm) |
| mm pro Pixel | 0,614 mm je m Abstand [K1] | 2,24 mm je m Abstand (848 px) |
| Optikunschärfe | 0,55 px bei 400 mm, 1,03 bei 500, 1,59 bei 700, 1,76 bei 800 (Fokus 350 mm) [K1] | – |
| Masse, Anschluss | 1,10 kg, GigE/PoE++ [K1] | 60 g, 42 × 42 × 23 mm, USB-C, 1,55 W [K2] |

Die Lochkamera mit 1628,7 px gibt das Sichtfeld bei 0,5 m exakt wieder. Bei
0,8 m ist sie um 5 % zu breit (994 statt 949 mm), bei 0,3 m um 7 % zu schmal.
Die z-Werte des Datenblatts sind Geometriewerte und gelten nicht für reale
Oberflächen (`docs/hardware-auswahl.md:84-85`).

## 3. Methode der Sichtprüfung und der Messsimulation

**Szene.** Grundlage ist `geometrie.baue()` mit Tür offen in zwei Zuständen:
(a) Oberkorb 0,45 m ausgezogen, Unterkorb drin; (b) Unterkorb 0,45 m
ausgezogen, Oberkorb drin. Dazu kommen das Podest 0,65 m und folgender Inhalt:
- 4 Gläser (Ø 75 × 110 mm, kopfüber) in den Slots, je ±5 mm versetzt
- 8 Tassen (Ø 84 × 95 mm, kopfüber) links im Oberkorb
- 16 Teller (Ø 240 × 20 mm) stehend in zwei Spalten im Unterkorb, Teilung 5 cm,
  Normale entlang y

**Sichtbarkeit.** Zielpunkte liegen auf allen Korbstreben (Rand- und Wandstäbe),
auf den Glashalter-Streben („Slots“) und auf dem Geschirr: Glas- bzw.
Tassenboden oben, Tellerrand ±40° um den Scheitel. Von jedem Zielpunkt geht ein
Strahl zur Kamera, mit Schnitttest gegen alle Quader, Zylinder und Scheiben
außer dem eigenen Körper. Ein Punkt gilt als sichtbar, wenn er unverdeckt ist,
im Bild liegt und im Arbeitsbereich. Die Spalte „≤ 0,8 m“ verwendet die
Handbuchgrenze der Farbvariante.

**Bild und Sensor.** Je Pixel wird der nächste Treffer bestimmt, daraus RGB
(Lambert), die ideale Tiefe und darauf das Fehlermodell:

| Effekt | Modell | Grundlage |
|---|---|---|
| Rauschen | σ(d) wie §2 | [K1], [K2] |
| Bereich | außerhalb dmin…dmax kein Wert | [K1], [K2] |
| flacher Winkel | Normale > 60° (B57) bzw. > 70° (D405) zum Sehstrahl: kein Wert | Ensenso-Handbuch: Flächen > ~60° werden nicht rekonstruiert [K5]; D405 Annahme |
| Kanten | Tiefensprung > 2 cm im 3×3-Nachbarn: 50 % Ausfall | Annahme (Verdeckungsschatten Stereo/Projektor) |
| Glas | 50 % kein Wert, 35 % Tiefe des Hintergrunds, 15 % Reflex (±8 mm um die Glasfläche) | Typ II/Typ I nach [K6], [K7]; Anteile Annahme |
| Nässe | 5 % zufällige Ausfälle auf Geschirr, Korb, Tür | Annahme |
| Glanz | Normale < 10° zum Sehstrahl auf Geschirr/Edelstahl: Sättigung, kein Wert | Annahme |

**Messungen aus der Punktwolke.** Die Segmentierung je Pixel gilt als ideal. Das
ist eine optimistische Annahme. Gemessen werden:
- **Korbpose:** ICP Punkt-zu-Ebene, nur Translation, gegen die der Kamera
  zugewandten Strebenflächen des Korbmodells. Start 8/25/−6 mm neben der
  Wahrheit. Die Bodenplatte ist ausgenommen, denn sie ist im Modell eine Platte,
  in Wirklichkeit ein Gitter.
- **Glas (Tiefe):** Median der Glaspunkte ±8 mm um die bekannte Glasoberkante.
- **Glas (RGB + Modell):** Schwerpunkt der um 1 px erodierten Glasmaske, als
  Strahl geschnitten mit der Ebene der Glasmitte. Diese Höhe ist bekannt aus dem
  Korbboden plus dem halben Glasmaß.
- **Teller:** Ebene aus dem Median, Randkontur je 5 mm in x, Kreisanpassung mit
  bekanntem Radius.

Bilder zu jeder Pose: Perspektive mit Zielpunkten, RGB, Tiefe mit Lücken,
Punktwolke gegen die Wahrheit. Die Bilder liegen außerhalb des Repos und gehen
als Artefakt an den Owner.

## 4. Ergebnisse Kamerasicht

### 4.1 Posen

| Pose | Kamera (x; y; z) m | Blick |
|---|---|---|
| mast-gerade | 0,90; 0,30; 1,10 | 15° abwärts nach −x |
| mast-geneigt | 0,90; 0,30; 1,10 | auf Oberkorbmitte |
| mast-hoch (zweite Masthöhe) | 0,90; 0,30; 1,35 | auf Oberkorbmitte |
| schlitten-vorn / -hinten | 0,90; 0,10 bzw. 0,60; 1,10 | auf Oberkorbmitte |
| ausleger | 0,55; 0,35; 1,10 (Ausleger 0,35 m) | auf Oberkorbmitte |
| unterkorb-geneigt / -tief / ausleger-unterkorb | 0,90; 0,30; 1,10 / 0,90; 0,45; 0,85 / 0,55; 0,35; 1,10 | auf Unterkorbmitte |
| arm-greift | wie mast-geneigt, Arm in der Greifpose Slot 1 | |
| D405 ober-vor-30/45/60 | über dem Greifer, TCP 10 cm über der Greifpose von Glas 1 | 30/45/60° zur Werkzeugachse |
| D405 greifen-nah-45 | TCP in der Greifpose (Glas 10–23 cm entfernt) | 45° |
| D405 teller-vor-45 | TCP 10 cm über dem Tellerrand | 45° |

D405-Montage (Annahme): Kamera 2 cm über dem Flansch, Versatz quer zur
Schließrichtung `a = min(0,10; 0,16·tan θ)` m. Der Zentralstrahl trifft die
Werkzeugachse 6 cm unter dem TCP. Das Bild liegt mit 87° entlang der
Schließrichtung. Greiferkörper 150 × 50 × 50 mm und Finger 20 × 10 × 60 mm wie
`config/robot.yaml:79-95`.

### 4.2 Sichtbarkeit und Raster

Sichtbar in %, „≤ 0,8 m“ = mit Handbuchgrenze der Farbvariante. Geschirr = Gläser
und Tassen bzw. Teller; bei D405 nur das Zielobjekt mit Umgebung (12–15 cm).

| Pose | Streben % (≤ 0,8 m) | Slots % | Geschirr % (≤ 0,8 m) | Geschirr durch Finger/Arm verdeckt % | Abstand Geschirr m | mm/px am Geschirr |
|---|---|---|---|---|---|---|
| b57 mast-gerade | 44 (0,5) | 8 | 82 (5) | 0 | 0,71–1,05 | 0,44–0,64 |
| b57 mast-geneigt | 74 (21) | 53 | 100 (22) | 0 | 0,71–1,05 | 0,44–0,64 |
| b57 mast-hoch | 79 (0) | 75 | 100 (0) | 0 | 0,92–1,21 | 0,57–0,74 |
| b57 schlitten-vorn | 50 (16) | 38 | 99 (19) | 0 | 0,72–1,03 | 0,45–0,64 |
| b57 schlitten-hinten | 76 (14) | 34 | 100 (8) | 0 | 0,76–1,17 | 0,47–0,72 |
| **b57 ausleger** | **68 (53)** | **88** | **100 (94)** | 0 | **0,57–0,82** | **0,35–0,51** |
| b57 arm-greift | 57 (20) | 41 | 66 (11) | 16 | 0,71–1,05 | 0,44–0,64 |
| b57 unterkorb-geneigt | 42 (0) | – | 92 (0) | 0 | 0,84–1,13 | 0,52–0,69 |
| b57 unterkorb-tief | 9 (0) | – | 50 (0) | 0 | 0,64–1,03 | 0,40–0,63 |
| **b57 ausleger-unterkorb** | **58 (0)** | – | **100 (44)** | 0 | 0,73–0,93 | 0,45–0,57 |
| **d405 ober-vor-30** | 59 | **89** | 63 | 37 | 0,19–0,28 | 0,43–0,62 |
| d405 ober-vor-45 | 31 | 58 | 79 | 21 | 0,19–0,28 | 0,43–0,63 |
| d405 ober-vor-60 | 10 | 18 | 37 | 21 | 0,19–0,28 | 0,43–0,63 |
| d405 greifen-nah-45 | 14 | 47 | 11 | **89** | 0,11–0,23 | 0,25–0,52 |
| d405 teller-vor-45 | 0 | – | 73 | 6 | 0,21–0,30 | 0,47–0,67 |

Befunde:
- **Verdeckung durch das Podest.** Das Podest mit Schiene (0,65 m) verdeckt
  von jeder Mastpose die rechte Unterkante des Korbs. Bei der tiefen
  Unterkorbpose sind deshalb nur 9 % der Streben und 50 % der Teller sichtbar.
- **Oberkorb über Unterkorb.** Ist der Unterkorb ausgezogen, verdeckt der
  eingeschobene Oberkorb nur die hinteren ~4 cm. Die Tür liegt waagerecht unter
  dem Korb und verdeckt nichts.
- **Arm.** In der Greifpose belegt der Arm 46 % des Mastbildes und verdeckt 16 %
  des Geschirrs. Daraus folgt die Regel: erst schauen, dann greifen.
- **Abstand.** Alle Posen ohne Ausleger liegen überwiegend über 0,8 m. Mit der
  Grenze der Farbvariante wären sie unbrauchbar. Mit 2,0 m laut Datenblatt sind
  sie brauchbar, allerdings mit 1,0–2,2 mm z-Fehler und ≥ 1,7 px Unschärfe.
- **D405-Neigung.** 30° ist am besten: Der Greifer belegt 29 % des Bildes (45°:
  46 %, 60°: 65 %), der Zielslot ist zu 89 % sichtbar. Flacher geneigt schaut
  die Kamera über den Greifer hinweg auf den Korbgrund statt ins Ziel.

### 4.3 Simulierte Messung

Fehler gegen die Wahrheit in mm. Glas und Teller: Mittel / Maximum (gefundene /
alle), bei D405 nur das Zielobjekt. Gültig = Pixel mit Tiefe unter allen Pixeln,
die ein Objekt treffen.

| Pose | gültig % | Korbpose | Glas Tiefe | Glas RGB + Modell | Teller |
|---|---|---|---|---|---|
| b57 mast-gerade | 39 | 1,6 | 2,7 / 3,0 (2/4) | 57,6 / 58,2 (2/4) | – |
| b57 mast-geneigt | 63 | 2,7 | 5,1 / 10,5 (4/4) | 13,7 / 22,8 (4/4) | – |
| b57 mast-hoch | 64 | 6,3 | 6,2 / 9,5 | 6,5 / 11,2 | – |
| b57 schlitten-vorn | 63 | 2,4 | 5,6 / 9,9 | 12,3 / 24,4 | – |
| b57 schlitten-hinten | 68 | 25 (Auszug nicht beobachtbar) | 10,9 / 15,9 | 9,8 / 16,2 | – |
| **b57 ausleger** | 69 | **0,05** | 7,9 / 18,4 | **4,6 / 4,9** | – |
| b57 arm-greift | 58 | 2,6 | 11,7 / 28,4 (3/4) | 17,0 / 24,1 (3/4) | – |
| b57 unterkorb-geneigt | 70 | 2,5 | – | – | 1,9 / 2,6 (16/16) |
| b57 unterkorb-tief | 55 | 25 (Auszug nicht beobachtbar) | – | – | 1,8 / 2,2 (8/16) |
| **b57 ausleger-unterkorb** | 66 | 4,2 | – | – | **1,3 / 1,7 (16/16)** |
| **d405 ober-vor-30** | 79 | 18 (Ausschnitt) | **3,6** | 12,6 | – |
| d405 ober-vor-45 | 78 | 10,7 | 5,3 | 15,5 | – |
| d405 ober-vor-60 | 63 | 25 | 17,7 | 55,1 | – |
| d405 greifen-nah-45 | 74 | 1,5 | 29,0 | 6,6 | – |
| **d405 teller-vor-45** | 64 | 0,9 | – | – | **2,4** |

Lesart:
- **Korbpose.** Sie ist auf ≤ 3 mm bestimmbar, wenn Front- und Seitenstreben im
  Bild sind. Fehlt die Korbfront (schlitten-hinten, unterkorb-tief, D405), ist
  der Auszug entlang y nicht beobachtbar (25 mm = Startfehler). Den Auszug misst
  deshalb die B57 oder die Achse der Korbführung selbst (§6).
- **Glas.** Die Tiefe allein ergibt im Mittel 5–11 mm Fehler, im Maximum bis
  28 mm, verursacht durch Hintergrundtiefe durch das Nachbarglas. RGB + Glasmaß
  ergibt 4,6 / 4,9 mm, aber nur aus der Auslegerpose. Aus flachen Blickwinkeln
  verschiebt die Glaswand den Schwerpunkt um 10–58 mm. Der Variationslauf des
  Ausräumens verträgt ±5 mm (`docs/ausraeumen.md:175-196`). Die
  Auslegerpose erfüllt das knapp, alle anderen Posen nicht.
- **Teller.** Teller sind undurchsichtig und deshalb von allen Unterkorbposen auf
  ≤ 2,6 mm bestimmbar, sofern sie sichtbar sind.
- **D405.** Vor dem Griff ist die Glasoberkante aus der Tiefe auf 3,6 mm
  bestimmbar (30°). Das ist die einzige Kamera, die Glas in der Tiefe brauchbar
  sieht, weil der Glasboden unter steilem Blick als Fläche erscheint. Beim
  Greifen verdecken die Finger das Glas (89 %), die Tiefe fällt aus (29 mm).

### 4.4 Grenzen des Fehlermodells

- Die Segmentierung ist ideal. In Wirklichkeit kommen Fehlklassifikationen
  hinzu, vor allem Glas gegen Hintergrund.
- Die Glasanteile 50/35/15 % sind Annahmen. Die Literatur nennt die Typen, aber
  keine Raten für Ensenso oder D405 auf nassem Klarglas [K6], [K7]. Die
  Leihkamera-Analyse von Optonic soll diese Raten messen
  (`docs/hardware-auswahl.md:36-38`).
- Stereo- und Projektorgeometrie fehlen. Verdeckungsschatten sind nur als
  Kantenausfall modelliert, Mehrfachreflexe im Edelstahlbottich gar nicht.
- Die Gitterkörbe bestehen aus wenigen Stäben mit 6 mm Kantenlänge, echte
  Drähte sind rund und ~3–4 mm dick. Der Korbboden ist eine Platte.
- Das RGB-Bild ist eine Lambert-Schattierung aus numpy. Ein Isaac-RTX-Render
  der B57-Posen ist vorbereitet, aber nicht gelaufen (§10).

## 5. Inhalte und Greifstrategien

| Gut | Option A (Empfehlung) | Option B | Option C | Aufwand / Risiko |
|---|---|---|---|---|
| Teller (Unterkorb) | Griff von oben am Rand, Finger quer zur Tellerebene, 30 cm senkrecht heraus | Griff von vorn am Rand (Werkzeug waagerecht) | Teller kippen und dann greifen | A: mittel; Fingerdicke 10 mm passt in 5 cm Teilung nur bei 2 cm Tellerdicke. B: Kollision mit Nachbartellern |
| Gläser (Oberkorb) | wie heute: kopfüber von oben, Umgreifen über die Matte (`docs/ausraeumen.md:53-64`) | Seitgriff im Korb (scheidet aus: Wand 120 mm > Glas 110 mm) | – | gebaut, 10/10 |
| Tassen | kopfüber von oben am Fuß, Henkel egal; Umdrehen wie Glas | Henkelgriff | – | A klein; Henkellage aus RGB |
| Besteck | **zurückstellen**: Besteckkorb/-schublade bleibt dem Menschen | Besteckschublade ausziehen, Teile einzeln greifen | ganzen Besteckkorb heben | B: Teile 5–20 mm, Greifer 5–105 mm Hub, sehr viele Griffe. C: Korb ~1–2 kg, Lastkurve knapp |
| Schüsseln | später, kopfüber wie Tasse mit größerer Öffnung (Greifer max. 105 mm) | – | – | Durchmesser oft > 105 mm, dann nur Randgriff |
| Ablage | Teller: senkrecht in einen Tellerständer auf der Konsole; Gläser/Tassen: Matte → aufrecht | Stapel auf der Platte | – | Ständer erspart das Umdrehen der Teller |

**Reihenfolge: Unterkorb zuerst** (Empfehlung). Beim Herausziehen des Oberkorbs
tropft Restwasser von den kopfüber stehenden Gläsern und Tassen in den
Unterkorb. Das ist eine verbreitete Haushaltsregel. Eine Herstellerquelle dafür
wurde nicht gesucht, und die Regel ist nicht gemessen. Gegenoption Oberkorb zuerst: Der Arm erreicht den Oberkorb
leichter, weil er höher liegt. Bei eingeschobenem Oberkorb ist der Unterkorb von
oben frei, die Sicht wird dadurch nicht schlechter (§4.2).

Ablauf: Tür offen (Mensch oder Türöffner, nicht Teil dieses Konzepts) →
Unterkorb greifen, ausziehen → Teller entnehmen → Unterkorb einschieben →
Oberkorb ausziehen → Gläser/Tassen → einschieben.

## 6. Korbmodell und Ausziehen

### 6.1 Korbmodell

| Option | Inhalt | Aufwand | Risiko |
|---|---|---|---|
| **A (Empfehlung)** | Schubgelenk je Korb (wie `korbgelenke`), Reibung als Gelenkdämpfung + Coulomb, Anschläge 0 und 0,45 m, Korb als wenige Quader wie heute | klein | Teller in Zinken: viele Kontakte, Newton-Stabilität (§7) |
| B | A + Zinkenreihen als Quader (Tellerhalter), Gitterboden als Stabraster | mittel | 3–5× mehr Kontaktpaare |
| C | Draht-Mesh aus Hersteller-CAD | groß | keine freie CAD-Quelle gefunden; Laufzeit |

**Zugkraft.** Belastbare Herstellerwerte fehlen. Eine Ratgeberseite unklarer
Herkunft nennt ≤ 2,5–3 lbf (11–13 N) für einen leichtgängigen Korb [K8]. Ein
Überschlag mit Rollwiderstand 0,02–0,05 bei 10 kg (16 Teller à 0,55 kg plus
Korb) ergibt 2–5 N rollend. Losbrechen und Anschlag liegen etwa beim Doppelten.
**Auslegung: 30 N Spitze.** Den echten Wert misst der Owner mit einer
Kofferwaage an der eigenen Maschine (§8, Frage 3).
**Rackmatic.** Bosch verstellt den Oberkorb in 3 Stufen um bis zu 5 cm, auch
beladen [K9]. Im Modell genügt ein Parameter `oberkorb.boden_hoehe_m`
(0,42 ± 0,025 m), Simulation mit mittlerer Stufe.

### 6.2 Ausziehen durch den Roboter

| Option | Griff | Antrieb | Befund (IK-Überschlag) |
|---|---|---|---|
| **A (Empfehlung)** | waagerechter Zangengriff an der Frontstrebe, Werkzeug zeigt in die Maschine | **7. Achse** zieht, Arm hält die Pose | Oberkorb: bei 0,40 und 0,65 m über 43 cm kinematisch machbar, Achse 7 0 → 0,43 m. Einziger Konflikt: Der 60-mm-Finger trifft das vorderste Glas, ein kürzerer Eingriff (≤ 2 cm hinter der Strebe) ist nötig. Unterkorb: keine IK bei 0,40 und 0,65 m; bei 0,20 m am rechten Frontteil (x 0,50) machbar, Achse 7 0,28 → 0,72 m |
| B | Griff von oben, Finger um die Strebe | 7. Achse | Oberkorb: Kollision von Unterarm und Hand mit Arbeitsplatte und Bottichdecke; Unterkorb außer Reichweite (53–197 mm) |
| C | Hakenfinger (Zusatzteil) | Arm allein | Gelenkmomente zu hoch (s. u.) |

**Momente bei 20 N Zug** (`tau = Jᵀ F` aus der IK-Pose, Option A):
- J1 5,6–9,6 Nm, entsprechend dem seitlichen Hebel 0,28–0,48 m zur Schiene.
- Oberkorb: J2–J6 ≤ 0,6 Nm, weil die Kraftlinie durch das Handgelenk läuft.
- Unterkorb (0,20 m Podest): J2 3,9 Nm und J3 3,5 Nm.
- Beim Griff von oben (B) kommen J4/J5 auf 2,7–3,0 Nm.

Dagegen steht die Datenlage zu den Getrieben (igus-Seiten widersprechen sich):
- Baugröße 80: Nennmoment 2 Nm, Maximum 2,5–3 Nm [K10]
- Baugröße 105: Nennmoment 10–15 Nm, Maximum 12,5–20 Nm [K10]

Welche Gelenke welche Baugröße haben, steht nicht im Datenblatt. Annahme:
J1–J3 Baugröße 105, J4–J6 Baugröße 80. Schwerkraft allein belastet J2 schon mit
8,6–13,7 Nm (grob, Massen aus `config/robot.yaml:47-56`). Folgerungen:
**ziehen nur über die 7. Achse mit waagerechtem Griff**, und das Modellmoment
40 Nm (`config/robot.yaml:45`) ist zu hoch und muss auf die igus-Werte (§9, T1).

### 6.3 Podest für beide Körbe (IK-Überschlag)

Schiene senkrecht zur Front bei x = 0,78 m, senkrechter Greifer, 1-cm-Wege,
Kollision mit Szene und Selbstkollision wie `spuelmaschine/erreichbarkeit.py`.
Teller: 20 Griffpunkte (x 0,10–0,50 × 4 Tiefen), Vorposition 10 cm, Aushub 30 cm.

| Podest | Oberkorb-Slots (4) | Ablage Platte | Unterkorb-Teller (20) | Unterkorbfront ziehen | Oberkorbfront ziehen |
|---|---|---|---|---|---|
| 0,65 m | 4/4 | ja (von oben) | **3/20** (nur x 0,50) | nein | ja (Finger kürzen) |
| 0,40 m | 4/4 | nur mit Seitgriff + Konsole | **9/20** (x ≥ 0,30, ab 0,16 m vor der Front) | nein | ja (Finger kürzen) |
| 0,20 m | nicht gerechnet (0,30 m: 2/4) | nein | **0/20** (x ≥ 0,40: 30-cm-Aushub reißt ab; x ≤ 0,30 außer Reichweite) | **ja** (x 0,50, waagerecht) | ja (Finger kürzen) |
| 0,00 m | – | nein | 0/20 (außer Reichweite) | – | – |

Slots 0,30–0,65 m aus `docs/ausraeumen.md:215-219`. Gegenprobe Schiene parallel
zur Front hinter der offenen Tür (y = 0,80 m): Teller 5/20 bei 0,40 m und 0/20
bei 0,20 m, Slots 2/4 bzw. 0/4. Das ist nicht besser.

**Befund.**
- Die **Breite** begrenzt stärker als die Höhe. Griffpunkte mit x ≤ 0,20 m
  liegen bei jeder Podesthöhe 66–271 mm außerhalb der Reichweite. Der Grund:
  Von x = 0,78 m sind es 0,58–0,68 m seitlich, Oberarm plus Unterarm messen nur
  0,534 m.
- Die **hintere Tellerreihe** (0,04 m vor der Front) scheitert an Arbeitsplatte
  und Bottichdecke.
- **Eine Podesthöhe für beide Körbe gibt es nicht.**
  - Teller entnehmen geht am besten bei 0,40 m (9/20). Bei 0,20 m reißt der
    30-cm-Aushub ab (0/20).
  - Die Unterkorbfront lässt sich nur bei 0,20 m ziehen.
  - Die Ablage auf der Platte braucht 0,65 m (Griff von oben) bzw. 0,40 m mit
    Seitgriff und Konsole.
  - 0,40 m mit Konsole bedient deshalb den Oberkorb ganz und vom Unterkorb die
    rechte vordere Hälfte. Den Unterkorb muss dann jemand anderes herausziehen.
- **Lösungsoptionen** (Frage 1):
  - (a) Teller nur in der rechten Hälfte einräumen (Owner-Regel)
  - (b) zweite Schiene bzw. längere Schiene über die Tür ist nicht möglich,
    weil die Tür im Weg ist
  - (c) Hubachse unter der Schiene (0,2–0,65 m)
  - (d) der Mensch zieht den Unterkorb heraus, der Roboter räumt die rechte Hälfte

## 7. Simulation

- **Newton mit vielen Kontakten.** 16 Teller in Zinken plus 4–12 Gläser/Tassen
  ergeben rund 10× mehr Kontaktpaare als heute (4 Gläser, CPU 43 s für 2,2 s
  Simzeit, `docs/spuelmaschine.md:153-167`). Vorschlag: zuerst
  Stabilitätstest je Korb (Teller als Box-Zylinder, ke/kd wie die Greifdemo),
  Abnahme Drift < 1 mm und kein Teller kippt > 2°.
- **Laufzeit.** CPU-Läufe des Ausräumens dauern 45–84 min je Versuch
  (`docs/ausraeumen.md:150-182`), mit Tellern ein Vielfaches. Variationsläufe
  deshalb über die GPU-Warteschlange (Newton auf der GPU = gleiche Ergebnisse).
- **Isaac RTX.** Beide Körbe als statische Quader und Scheiben über
  `isaac_render.auftrag` (Formen `glas`, `scheibe` vorhanden). Kameraproben
  laufen über `scripts/isaac_render.py --kamera`, ein Bild je Kamerapose, mit
  Brennweite 28,97 mm (B57) bzw. 18,97 mm (D405) bei 36 mm Apertur.
- **Sensorsimulation** als eigenes Modul. Inhalt: Lochkamera, Fehlermodell aus
  §3, Messungen aus §4.3; numpy, ohne GPU, testbar.

## 8. Fragen an den Owner (Empfehlung zuerst)

1. **Wie erreicht der Roboter die linke Korbhälfte und die Unterkorbfront?**
   (a) Hubachse unter der Schiene, 0,2–0,65 m (*Empfehlung*: deckt die
   Unterkorbfront, die Teller und die Ablage mit einer Schiene ab). Kosten offen.
   (b) Podest 0,40 m mit Konsole, Teller nur rechts einräumen, der Mensch zieht
   den Unterkorb. (c) Nur Oberkorb automatisch, Unterkorb bleibt manuell.
2. **Kamera-Aufbau:** (a) B57 am Mast mit 0,35-m-Ausleger plus D405 über dem
   Greifer unter 30° (*Empfehlung*: Überblick und Feinlage, Glas über
   RGB + D405). (b) Nur B57 mit Ausleger: Glaslage 4,6/4,9 mm, ohne Reserve.
   (c) Nur D405: kein Überblick, kein Korbauszug, eine Vorposition je Objekt.
   Dazu die Variantenfrage: B57 in Farbe (Handbuch: bis 0,8 m) oder mono BL
   (bis 2 m, kein RGB) beim Hersteller klären.
3. **Zugkraft messen und Besteck:** (a) Du misst die Zugkraft beider Körbe mit
   einer Kofferwaage (beladen, Start und Lauf). Besteck bleibt manuell
   (*Empfehlung*). (b) Wir rechnen mit 30 N und lassen Besteck offen. (c) Die
   Besteckschublade kommt als eigenes Ticket dazu.

## 9. Vorgeschlagene Ticket-Kette

| # | Titel | nach | parallel zu | Abnahme |
|---|---|---|---|---|
| T1 | Robotermodell: Gelenkmomente aus igus-Getriebedaten, D405 und Halter am Greifer, Nutzlastkurve je Wegpunkt | – | T2, T3 | Tests: Momentgrenze je Gelenk, Lastkurve mit Greifer + D405 + Teller (1,17 kg → r_max 483 mm); Erreichbarkeitstabelle unverändert grün |
| T2 | Korbmodell: Schubgelenk mit Reibung und Anschlag für beide Körbe, Unterkorb mit Zinken und 16 Tellern, Rackmatic-Parameter | – | T1, T3 | Newton-Stabilität beide Körbe (Drift < 1 mm), Auszug unter 30 N läuft bis zum Anschlag, Negativtest ohne Reibung |
| T3 | Sensorsimulation B57/D405: Lochkamera, Fehlermodell, Messungen (Korbpose, Glas, Teller) | – | T1, T2 | Tabelle §4.3 reproduziert (± 10 %), Test: Glas ohne Tiefe → RGB-Weg, Korbfront außerhalb → Auszug „nicht beobachtbar“ |
| T4 | Aufbauentscheidung umsetzen (Frage 1): Hubachse oder Podest 0,40 + Konsole; Erreichbarkeit beider Körbe | T1, Owner-Antwort | – | IK-Tabelle beide Körbe: alle Slots, ≥ 80 % der Tellergriffe, Korbfronten ziehen |
| T5 | Korb ausziehen und einschieben durch die 7. Achse (waagerechter Griff), Unter- dann Oberkorb | T2, T4 | – | Newton: beide Körbe 0 → 0,45 → 0 m, Kraft ≤ 30 N, kein Kontakt Arm ↔ Szene > 0,1 mm, Video |
| T6 | Teller aus dem Unterkorb in einen Ständer | T5, T3 | T7 | Demo + Variation 10 Versuche, Tellerlage aus der simulierten B57-Messung |
| T7 | Gläser mit Kamera statt bekannter Lage (B57 Überblick, D405 Feinlage) | T3, T5 | T6 | Variation 10 Versuche mit Lage aus der Messsimulation, Zielfehler ≤ 10 mm |
| T8 | Gesamtablauf beide Körbe + Isaac-RTX-Video | T6, T7 | – | ein Lauf Tür offen → beide Körbe leer, Video aus Isaac Sim |

## 10. Gewichtsbilanz mit D405

Lastkurve 2 kg bis 400 mm, linear auf 1 kg bei 500 mm
(`docs/hardware-auswahl.md:267-299`):

| Posten | Glas | Teller |
|---|---|---|
| Greifer inkl. Finger (Annahme) | 0,50 | 0,50 |
| D405 [K2] | 0,06 | 0,06 |
| Halter + Kabelanteil (Annahme) | 0,06 | 0,06 |
| Gut | 0,25 | 0,55 (Speiseteller, Annahme) |
| **Summe kg** | **0,87** | **1,17** |
| r_max | 500 mm (Kurvenende) | 483 mm |

Slot 3/4 liegt bei 451/502 mm (`docs/hardware-auswahl.md:276-280`). Mit Glas
passt das waagerecht, räumlich ist es 2 mm zu weit. Mit Teller passt es nur,
solange der Griff ≤ 483 mm vom Fuß liegt. Die Teller rechts vorne, also die
erreichbaren Griffpunkte, liegen nach §6.3 nahe am Fuß. Das prüft T1 je
Wegpunkt.

**D405 im System.**
- **Hand-Auge-Kalibrierung „moving“**: die Kamera bewegt sich mit dem
  Flansch [K11]. Sie ist von der B57-Kalibrierung („fixed“) getrennt.
- Gemeinsamer Bezug ist das Kalibriermuster im Korb bzw. der Roboterfuß.
- **USB-C am Handgelenk.** Das Kabel läuft durch J4–J6, die ±179° drehen
  (`config/robot.yaml:41-43`). Nötig sind eine Kabelschleife und ein aktives
  USB-3-Kabel bzw. ein USB-über-Ethernet-Wandler zum Jetson.
- **Glas und Nässe.** Die D405 hat keinen Projektor. Auf Klarglas fehlt Tiefe
  wie bei der B57 [K6], [K7]. Der Vorteil ist der steile Blick auf den Glasboden
  aus 20–30 cm. Tropfen auf der Optik sind ein Risiko, deshalb Abdeckung und
  Blick schräg nach unten (30°).

## 11. Verworfen

- Kamera am Mast ohne Ausleger als einzige Quelle: Der Korb liegt 0,7–1,2 m
  entfernt, die Glaslage hat 10–58 mm Fehler.
- D405 zwischen den Fingern: ersetzt durch die Owner-Vorgabe „über dem Greifer“.
- D405-Neigung 60°: Der Greifer belegt 65 % des Bildes.
- Korb mit dem Arm allein ziehen: Gelenkmomente der Baugröße 80 schon bei
  20 N ausgeschöpft.
- Schiene parallel zur Front hinter der Tür: Sie erreicht weniger als die
  senkrechte Schiene.

## 12. Quellen (abgerufen 29.10.2026)

- [K1] IDS-Datenblatt Ensenso B57-4 (B57-5C-4/28|4/28|350-75/7), Stand 25.09.2024, Tabelle z-Genauigkeit, Pixelgröße, Sichtfeld, Unschärfe: https://www.tvcnet.1stvision.com/cameras/IDS/Ensenso/dataman/Ensenso-B-series-datasheet.pdf
- [K2] Intel RealSense D405, Spezifikation: https://www.intel.com/content/www/us/en/products/sku/229218/intel-realsense-depth-camera-d405/specifications.html ; Produktseite (60 g, ±2 % bei 50 cm, 1280 × 720): https://www.realsenseai.com/products/stereo-depth-camera-d405
- [K3] Min-Z der D405 je Auflösung (Intel-Tabelle, wiedergegeben im DigiKey-Forum): https://forum.digikey.com/t/the-intel-realsense-depth-camera-d405/50822
- [K4] Ensenso-Handbuch, Hardware/Namensschema (Farbvariante bis 800 mm), wie `docs/hardware-auswahl.md` [Q6]: https://manual.ensenso.com/latest/hardware/index.html
- [K5] Ensenso-Handbuch, Camera Setup Considerations: https://manual.ensenso.com/latest/guides/camera-setup-considerations.html
- [K6] Sajjan et al., ClearGrasp (ICRA 2020): https://arxiv.org/abs/1910.02550
- [K7] Robotic Perception of Transparent Objects: A Review: https://arxiv.org/abs/2304.00157
- [K8] Ratgeberseite zum Korbwechsel (≤ 2,5–3 lbf), Herkunft unklar, nur Größenordnung: https://commgearpro.com/food-service-equipment/how-do-you-replace-a-universal-dishwasher-lower-rack
- [K9] Bosch, RackMatic 3 Stufen bis 5 cm: https://media3.bosch-home.com/Documents/specsheet/en-XN/SMS43D08ME.pdf
- [K10] igus ReBeL-Getriebe Baugröße 80/105: https://www.igus.eu/automation/robot-types/cobot/rebel-gearbox-construction-kit ; https://www.igus.ca/info/rebel-gearbox-system ; RBTX 105: https://rbtx.com/en-US/components/accessories/rebel-fully-integrated-shaft-gearbox-size-105
- [K11] Ensenso-Handbuch, Hand-Eye Calibration: https://manual.ensenso.com/latest/guides/multi-camera-setups-and-calibrations/handeyecalibration.html

## 13. Machbarkeit: ReBeL frontal vor der Maschine (Z-Achse bzw. stationär)

Stand: 29.10.2026. **Nur Machbarkeitsprüfung, kein Produktcode.** Frage des
Owners: Der ReBeL steht frontal vor der offenen Maschine, zieht die Körbe selbst
heraus, schiebt sie wieder ein und entlädt von vorn wie ein Mensch. Geprüft sind
zwei Aufbauten: **A „Z-Achse frontal“** (ReBeL auf einer vertikalen
Linearachse) und **B „stationär“** (ReBeL fest montiert, ohne Achse, Fuß
zwischen den Körben). Verglichen wird mit dem heutigen Aufbau (Schiene
senkrecht zur Front bei x = 0,78 m, Podest). Die Rechnungen stammen aus
Überschlagsskripten außerhalb des Repos. Sie nutzen `rebel_model` und
`spuelmaschine/erreichbarkeit.py` unverändert und ersetzen nur die 7. Achse
(Achse entlang z bzw. gesperrt).

### 13.1 Kurzfassung

- **A (Z-Achse frontal) geht, mit Einschränkungen.** Der Roboter zieht beide
  Körbe über 0,45 m heraus und schiebt sie wieder ein. Er erreicht die Teller
  links und rechts gleich gut (15/20, heute 9/20, links 0/8). Die Glasplätze
  der linken Korbhälfte sind erstmals erreichbar (6/16 statt 3/16). Die
  Momente aus dem Zug liegen unter dem igus-Nennmoment. Die Ablage auf der
  Arbeitsplatte liegt außer Reichweite (0/4). Er legt deshalb auf einem Tisch
  bzw. Tablett neben sich ab (4/4).
- **Das Zugfenster ist schmal.** Nur mit dem Fuß 0,55–0,60 m vor der Front
  schafft der Arm den ganzen Auszug. Bei 0,50 m stößt der Fuß an den
  ausgezogenen Korb, ab 0,65 m reißt der Weg ab bzw. trifft der Fuß die Tür.
  Gegriffen wird die Frontstrebe 0,20 m seitlich vom Fuß (x 0,50 bzw. 0,10),
  nicht mittig. Beim Unterkorb fährt die Z-Achse während des Zugs mit
  (0,13 → 0,31 m).
- **B (stationär) geht nicht.**
  - Keine Fußhöhe zieht beide Körbe ganz. Bei 0,35 m fehlt dem Oberkorb der
    letzte Zentimeter (0,44 m). Bei 0,375 m fehlt dem Unterkorb der erste
    Zentimeter ab „ganz eingeschoben“.
  - Mit dieser Fußhöhe erreicht der Arm nur 2–4 der 16 Glasplätze und
    0–7 der 20 Teller. Erst bei 0,40 m sind es 6/16 und 10/20, dann fehlen
    beim Unterkorb aber 4–5 cm. Ohne Z-Achse fehlt der Hub für den
    Telleraushub.
  - Der Fuß steht im Schwenkbereich der Tür. Die Maschine lässt sich mit
    montiertem Roboter nicht schließen.
  - Gekippte Montage bringt nichts: 45° voll gerechnet ergibt Slots 2/16,
    Teller 1/20 und keinen Korbzug. 90° scheitert schon im Vorfilter
    (Ablage 1/8).
- **Grenzen, die kein Aufbau löst:** Die hinterste Tellerreihe und die
  hinterste Glasreihe (0,04 bzw. 0,02 m vor der Front bei 0,45 m Auszug)
  liegen unter der Plattenkante. Die äußeren Glasreihen (12 cm von der
  Korbwand) scheitern am 150 mm breiten Greiferkörper.
- **Empfehlung:** A ist dem heutigen Aufbau bei den Zielen überlegen (Teller
  links, Korbzug beider Körbe mit kleinem Moment). Der Preis dafür:
  Ablage auf einem Tablett statt auf der Platte, Roboter und Säule stehen vor
  der Maschine (Parkhöhe nötig), und die vertikale Achse braucht Bremse und
  synchrone Ansteuerung. Beides ist bei igus nicht als Produkt belegt (§13.6).
  B verwerfen. Vor einem Umbau die igus-Frage klären (§13.8).

### 13.2 Modell und Ziele

| Größe | A: Z-Achse frontal | B: stationär | heute |
|---|---|---|---|
| Fuß (x; y) m | 0,30; 0,60 (Maschinenmitte, Türende) | 0,30; 0,55 | Schiene ab (0,78; 0,06), senkrecht zur Front |
| Höhe | Achse 0–1,0 m gerechnet (Fußunterkante 0,02–1,02 m) | Fuß 0,25–0,45 m gerastert, gewählt 0,35 m | Podest 0,40 bzw. 0,65 m |
| Ausrichtung | Gesicht zur Maschine | dito; gekippt 45°/90° geprüft | Schiene 1,0 m Hub |
| Halterung (Hindernis) | Säule 0,10 × 0,20 m hinter dem Fuß, Schlittenplatte 0,25 × 0,25 m | Konsole von der linken Schrankfront (Balken 0,10 m breit in Fußhöhe) | Podest |
| Ablage neben dem Roboter | Tisch 0,28 × 0,28 m rechts, Höhe 0,86 m (Variante 0,60 m) | Tablett 0,28 × 0,28 m hinter dem Fuß, in Fußhöhe | – |

Raster (Vorfilter Reichweite, dann volle Prüfung):
- A: Fußabstand zur Front 0,50–1,00 m, seitlich x −0,10…0,70 m (0 bis
  ±0,40 m Versatz zur Maschinenmitte). Gier spielt bei senkrechter Achse nur
  für die Säulenlage eine Rolle (J1 dreht ±179°).
- B: Fußabstand 0,50–1,00 m, x wie A, Fuß 0,25–0,45 m, Kippung 0/45/90°.
- Volle IK mit Kollision nur für die besten Lagen, für den Korbzug zusätzlich
  das Raster 0,55–0,75 m.

Ziele, gleich für alle Aufbauten:
- **Glasplätze:** 16 im ausgezogenen Oberkorb, 4 Reihen (x 0,12 / 0,24 /
  0,36 / 0,48 m, Teilung 0,12 m wie heute) mal 4 Tiefen (0,09–0,39 m hinter
  der Korbfront). Die Gläser stehen in allen Plätzen und gelten als
  Hindernis.
- **Teller:** 20 Griffe wie in §6.3 (x 0,10–0,50 × 4 Tiefen), Vorposition
  10 cm, Aushub 30 cm. „Links“ bedeutet x ≤ 0,20 m, „rechts“ x ≥ 0,40 m.
- **Korbzug:** waagerechter Zangengriff an der oberen Frontstrebe, Werkzeug
  zeigt in die Maschine. 8 cm Anfahrt, dann 0,45 m Zug in 1-cm-Schritten. Der
  Korb fährt in der Kollisionsprüfung mit (Szene je 1 cm). Einschieben ist
  derselbe Weg rückwärts. Geprüft ist der Weg in beiden Richtungen; gilt
  einer, ist der Hub zusammenhängend machbar.
- **Ablage:** 4 Punkte auf der Arbeitsplatte (wie heute) und 4 Punkte auf
  Tisch bzw. Tablett.
- **Kollisionen:** 5 mm Rand gegen Tür, Korbgitter, eingeschobenen zweiten
  Korb, Korpus, Platte, Halterung, Ablage und Selbstkollision. IK-Fehler
  < 1 mm, Gelenksprung ≤ 10° je Wegpunkt.

### 13.3 Abdeckung der Ziele

| Zielgruppe | heute (Podest 0,40 / 0,65 m) | **A: Z-Achse frontal** | B: stationär (Fuß 0,35 m; 0,40 m) |
|---|---|---|---|
| Glasplätze Oberkorb (16) | 3/16 / 3/16 (links 0/8, rechts 3/8) | **6/16 (links 3/8, rechts 3/8)** | 2/16; 6/16 bei 0,40 m |
| davon innere Reihen x 0,24/0,36 (8) | 3/8 | **6/8** | 2/8; 6/8 |
| Teller Unterkorb (20) | 9/20 / 3/20 (links 0/8) [§6.3] | **15/20 (links 6/8, rechts 6/8)** | 0/20 (30-cm-Aushub reißt oben ab); 10/20 bei 0,40 m |
| Unterkorb ziehen 0,45 m und einschieben | nur bei Podest 0,20 m [§6.2] | **ja** (Griff x 0,50) | ja bei 0,35 m; ab 0,375 m nur 0,44 m (die ersten 1–5 cm ab „eingeschoben“ fehlen) |
| Oberkorb ziehen 0,45 m und einschieben | ja, die 7. Achse zieht [§6.2] | **ja** (Griff x 0,50 und x 0,10) | bei 0,35 m nur 0,44 m; ja ab 0,375 m |
| Ablage Arbeitsplatte (4) | 4/4 bei 0,65 m; 0/4 bei 0,40 m | **0/4** (212–362 mm zu weit) | 0/4 (394–514 mm zu weit) |
| Ablage neben dem Roboter (4) | – | **4/4** (Tisch 0,86 m; ebenso bei 0,60 m) | 4/4 (Tablett in Fußhöhe) |

Lesart:
- **Ausfälle bei A:**
  - Die hinterste Tellerreihe (y 0,04 m, 26–61 mm außer Reichweite) und die
    hinterste Glasreihe (y 0,02 m) liegen unter der Plattenkante (y 0,05 m).
    Sie scheitern bei jedem Aufbau.
  - Die äußeren Glasreihen x 0,12 und 0,48 m scheitern am Greiferkörper
    (150 mm in Schließrichtung) an der Korbwand. Quer gedreht trifft er die
    Nachbargläser (Teilung 0,10 m). Das ist eine Grenze des Greifers, nicht
    des Aufbaus.
  - Erreichbar sind damit alle Plätze, die mit diesem Greifer überhaupt gehen.
- **Lage der Z-Achse:**
  - Bei 0,50 m vor der Front erreicht der Arm geometrisch alles (Vorfilter:
    16/16 Slots, 20/20 Teller). Der Korbzug scheitert dort aber, weil Fuß und
    Schlitten den ausgezogenen Korb bzw. die Tür treffen.
  - Ab 0,65 m reißt der Zugweg ab (Arm ganz eingefaltet) oder der Fuß trifft
    beim Unterkorb die Tür.
  - Mittig gegriffen (x 0,30) gelang der Zug bei 0,50 m und bei 0,65–0,75 m
    nicht. Bei 0,55 und 0,60 m ist dieser Fall nicht zu Ende gerechnet. Am
    Ende stünde das Handgelenk (y 0,64 m) über dem eigenen Fuß.
  - 0,60 m ist der beste Kompromiss.
- **B nach Höhe:**
  - 0,35 m: Unterkorb ja, Oberkorb 0,44 m, Slots 2/16, Teller 0/20 (der
    30-cm-Aushub reißt 2–7 cm vor dem Ende ab).
  - 0,375 m: Oberkorb ja, Unterkorb ab 1 cm Auszug, Slots 4/16, Teller 7/20.
  - 0,40 m: Oberkorb ja, Unterkorb ab 5 cm, Slots 6/16, Teller 10/20.
  - 0,45 m: Oberkorb ja, Unterkorb ab 13 cm.
  - Die Abrisse liegen alle am Anfang: Der Griff am ganz eingeschobenen Korb
    gelingt nicht durchgehend.
  - Gekippt 45° (Fuß 0,45 m, y 0,60 m): Slots 2/16, Teller 1/20, kein Korbzug.
  - Bei 0,30–0,35 m trafen eine seitliche Ablage und die Konsole den Unterarm
    beim Unterkorbzug. Das Tablett steht deshalb hinter dem Fuß.

### 13.4 Momente beim Korbzug (igus-Grenzen)

Die Momente sind `tau = Jᵀ F` über den ganzen Zugweg gerechnet, das Maximum je
Gelenk. Die Kraft wirkt waagerecht entlang der Werkzeugachse.

Grenzen [K10]:
- J1–J3 Baugröße 105: Nennmoment 10–15 Nm, Maximum 12,5–20 Nm.
- J4–J6 Baugröße 80: Nennmoment 2 Nm, Maximum 2,5–3 Nm.
- Annahme wie §6.2: J1–J3 Baugröße 105, J4–J6 Baugröße 80.

Die Pressemitteilung zum Marktstart nennt abweichend 25 Nm (105) bzw. 3 Nm
(80) bei 6 U/min [K12].

| Zug | Aufbau | J1 | J2 | J3 | J4–J6 | Urteil (Zug allein ≤ Nennmoment) |
|---|---|---|---|---|---|---|
| 20 N | A Unterkorb / Oberkorb | 4,0 / 4,0 | 3,7 / 1,0 | 4,5 / 2,7 | 0,0 | **geht** |
| 30 N | A Unterkorb / Oberkorb | 6,0 / 6,0 | 5,6 / 1,5 | 6,7 / 4,0 | 0,0 | **geht** |
| 20 N | B Unterkorb (0,35 m) / Oberkorb (0,40 m) | 4,0 / 4,0 | 5,9 / 2,0 | 4,5 / 4,2 | 0,0 | geht |
| 30 N | B Unterkorb / Oberkorb | 6,0 / 6,0 | 8,8 / 3,1 | 6,7 / 6,2 | 0,0 | geht |
| 20 N | heute, Oberkorb (7. Achse zieht) [§6.2] | 5,6–9,6 | ≤ 0,6 | ≤ 0,6 | ≤ 0,6 | geht |

Befunde:
- **Das Handgelenk bleibt frei.** Die Zugkraft läuft entlang der
  Werkzeugachse durch J5. J4–J6 tragen 0 Nm.
- **Griff von oben scheidet aus.** Mit senkrechtem Greifer läge J5 0,21 m
  über der Strebe. Das ergäbe 20 N × 0,21 m ≈ 4,1 Nm, bei 30 N 6,2 Nm, über
  dem Maximum der Baugröße 80. Bei A und B lag die eingeschobene Korbfront
  für den Griff von oben zudem meist außer Reichweite (9–259 mm).
- **J1** trägt 4 bzw. 6 Nm, weil der Griff 0,20 m seitlich vom Fuß liegt.
- **Eigengewicht.** Das Modell belastet J2 schon ohne Zug mit
  13,3–14,9 Nm (Gliedmassen geschätzt, `config/robot.yaml:47-56`).
  - Mit Zug kommt J2 bei A auf 18,4 Nm (20 N) bzw. 20,2 Nm (30 N), bei B
    auf 19,2 bzw. 22,1 Nm.
  - Das liegt am oberen Ende bzw. über dem igus-Maximum von 12,5–20 Nm.
  - Der ReBeL trägt laut Datenblatt aber 2 kg am Arm. Die
    Massenaufteilung ist eine Annahme.
  - Urteil: Der Zug allein geht. Die Summe mit Eigengewicht ist bei 30 N
    knapp und muss am Gerät gemessen werden (§13.8).
- **Last der Z-Achse:** 85 N statisch (Arm, Greifer, Schlitten), dazu
  vertikale Anteile des Zugs ≈ 0.

### 13.5 Nötiger Hub

Fußunterkante je Aufgabe (aus den IK-Lösungen, A bei y 0,60 m):

| Aufgabe | Fuß m |
|---|---|
| Unterkorb ziehen | 0,13–0,31 (fährt während des Zugs mit) |
| Oberkorb ziehen | 0,17–0,28 |
| Teller greifen und 30 cm ausheben | 0,28 → 0,60 (fährt beim Aushub mit) |
| Glasplätze | 0,41–0,58 |
| Ablage Tisch 0,86 m | 0,85–0,91 |
| Ablage Tisch 0,60 m | 0,59–0,65 |
| Parken über dem Tür-Schwenkbereich (Fußkante außerhalb Radius 0,64 m) | ≥ 0,65 |

- **Nötiger Hub:** 0,13–0,91 m, also **0,78 m** mit Ablage auf
  Arbeitshöhe. Mit Tablett auf 0,60 m sind es 0,13–0,65 m, also **0,52 m**.
- Die igus-Achse gibt es mit 500 mm Hub oder mehr (§13.6). Die
  500-mm-Variante reicht knapp nicht, die 1000-mm-Variante ja.

### 13.6 Platz, Kosten, Sicherheit

| Größe | heute | A: Z-Achse frontal | B: stationär |
|---|---|---|---|
| Platz in der Küche | Podest 1,36 × 0,26 m rechts neben der Tür, 0,65 m hoch; Front der Maschine bleibt frei | Säule + Schlitten ≈ 0,30 × 0,45 m direkt vor der Maschine (y 0,48–0,86 m), Säule ~1,6 m hoch; Tisch 0,28 × 0,28 m daneben | Konsole quer vor der Maschine in 0,35 m Höhe; Tablett 0,28 × 0,28 m dahinter |
| Tür schließen mit Roboter | geht (Roboter seitlich) | geht, wenn der Roboter auf ≥ 0,65 m parkt | **geht nicht**: Fuß bei y 0,46–0,64 m, z 0,35 m liegt im Schwenkbereich |
| Mensch an der Maschine | frei | Säule steht im Stehplatz vor der Maschine | Konsole und Roboter im Weg |
| Achse | ReBeL-Bundle mit ZLW-20200 (Hub 1000 mm), iRC, synchron: 10.499,07 € inkl. Roboter, Achsanteil ≈ 5.529 € gegen ReBeL allein 4.970 € [Q17][Q18] | **Preis für eine vertikale igus-Achse mit iRC-Anbindung nicht gefunden.** Dasselbe ZLW-Bundle senkrecht montiert kostete 10.499,07 € (1000 mm) bzw. 10.369,23 € (500 mm) [Q17]. Ob igus den senkrechten Einbau mit Haltebremse freigibt, ist nicht belegt (Datenblatt: Werte „in horizontaler Einbaulage“ [K13]). Hubsäule „AI Lift“ auf RBTX: 2.340,00 € netto (500 mm), Hub 500–1000 mm, Modbus TCP, 80 mm/s, ±1 mm, eingefahren Hub/2 + 283 mm [K14] | keine Achse; Konsole Eigenbau, Preis offen |
| Bewertung der Hubsäule | – | nicht synchron mit dem Arm (Modbus, nicht iRC). Eingefahren 0,53 m (500 mm Hub): Fuß 0,13 m nur mit Winkel nach unten. Der Teller-Aushub (0,3 m Z-Fahrt) müsste dann der Arm allein leisten. Nicht gerechnet | – |
| Sicherheit | wie bisher (§ Hardware) | Vertikale Last 85 N fällt bei Stromausfall ohne Bremse. Quetschstellen Schlitten ↔ Tür/Korb. Roboter arbeitet im Stehplatz | Roboter in Kniehöhe im Schwenkbereich der Tür, Quetschgefahr beim Schließen |

### 13.7 Kamera

Ausgewertet mit dem Kamerawerkzeug aus §3. Der Arm steht in der Greifpose
(Glasplatz links, x 0,24 m) bzw. beim Teller links. Säule und Tisch sind
Hindernisse.

| B57-Lage (A) | Oberkorb: Slots % | Geschirr % (≤ 0,8 m) | Unterkorb: Geschirr % (≤ 0,8 m) | Abstand m |
|---|---|---|---|---|
| fest oben vor der Säule (0,30; 0,70; 1,35) | 59 | 75 (0) | 67 (0) | 0,9–1,5 |
| fest über dem Roboter (0,30; 0,55; 1,20) | 61 | 82 (48) | 70 (0) | 0,7–1,3 |
| fest seitlich rechts (0,60; 0,65; 1,15) | 40 | 65 (28) | 79 (0) | 0,7–1,4 |
| auf dem Z-Schlitten, 0,80 m über dem Fuß | 54 | 59 (8) | 90 (0) | 0,8–1,4 |
| **Ausleger von der Säule (0,55; 0,35; 1,10)** | **88** | **81 (75)** | **99 (44)** | 0,56–0,94 |

- **Beste Lage:** die B57 fest an einem Ausleger von der Säule, dieselbe
  Kamerapose wie in §4.
  - Simulierte Messung (Oberkorb): Korbpose 0,06 mm, Gläser über RGB plus
    Glasmaß 0,4–4,9 mm.
  - Simulierte Messung (Unterkorb): Korbpose 4,2 mm, Teller 0,9–1,7 mm.
  - Der frontale Arm verdeckt in der Greifpose 19 % des Geschirrs (§4: 0 %
    ohne Arm). Die Regel „erst schauen, dann greifen“ bleibt.
- **Ausleger und Arm.** Der Ausleger liegt in 1,10 m Höhe über dem Arbeitsraum.
  Bei Ablage auf 0,86 m reicht der Arm bis ~1,3 m und kann ihn treffen. Das
  ist nicht geprüft. Mit Tablett auf 0,60 m bleibt der Arm darunter.
- **Mitfahrende B57.** Auf dem Z-Schlitten fährt sie mit, ist aber 0,8–1,4 m
  entfernt, außerhalb der 0,8 m der Farbvariante.
- **D405** über dem Greifer unter 30°, Vorposition 10 cm über Glas 1, Arm
  frontal: Zielslot 90 % sichtbar, Zielglas 63 % in 0,19–0,28 m. Tiefe am
  Zielglas 3,6 mm, Greifer im Bild 29 %. Das deckt sich mit §4.3, die
  Nahsicht hängt nicht vom Aufbau ab.

### 13.8 Empfehlung und offene Punkte

1. **A weiter verfolgen, B verwerfen.**
   - A erreicht die Teller links und rechts.
   - A zieht beide Körbe mit dem Arm, das Handgelenk bleibt dabei ohne
     Moment.
   - Ablage auf einem Tablett neben dem Roboter auf etwa 0,60 m. Das spart
     Hub (0,52 statt 0,78 m) und hält den Arm unter dem Kameraausleger.
2. **Vor dem Bau bei igus klären:**
   - Darf die ZLW-20200 (bzw. eine andere iRC-taugliche Achse) senkrecht mit
     ~10 kg Last betrieben werden?
   - Gibt es dafür Haltebremse und Preis?
   - Ohne synchrone Achse sind der Unterkorbzug (Z fährt 0,18 m mit) und der
     Telleraushub (0,3 m) neu zu rechnen.
3. **Messen am Gerät:**
   - J2-Moment im Eigengewicht (die Summe mit 30 N Zug liegt am Maximum).
   - Zugkraft der Körbe (Frage 3 in §8).
4. **Nicht gerechnet:**
   - Dynamik.
   - Durchbiegung der Säule unter 20–30 N Zug in 0,3–0,6 m Höhe.
   - Weg Korb → Ablage mit getragenem Teller.
   - Kollision Arm ↔ Kameraausleger.
   - Rackmatic-Stufen (±2,5 cm Oberkorb).

Bilder (Übersicht A und B, Posen Unterkorb ziehen, Oberkorb ziehen, Teller
links hinten, Ablage, kritischste Pose B, Kameraperspektiven B57 und D405)
liegen außerhalb des Repos und gehen als Artefakt an den Owner.

### 13.9 Verworfen

- **Mittiger Griff an der Korbfront (x 0,30)** bei frontalem Fuß: Am Ende des
  Zugs stünde das Handgelenk über dem eigenen Fuß. Bei 0,65–0,70 m reißt der
  Weg nach 0,33–0,36 m ab.
- **Griff von oben für den Zug:** J5-Moment 4,1 Nm bei 20 N, über dem
  Maximum der Baugröße 80. Der Korb ist eingeschoben außer Reichweite.
- **Z-Achse bei 0,50 m vor der Front:** Fuß trifft den ausgezogenen Korb
  bzw. die Tür.
- **Z-Achse ab 0,70 m:** Zugweg reißt ab, die Slots fallen auf 8/16
  (Vorfilter).
- **Stationär gekippt (45°/90°):** keine Lage mit Korbzug, Slots 2/16, Teller
  1/20.
- **Stationär mit seitlichem Tablett** in Fußhöhe: Unterarm trifft es beim
  Unterkorbzug.
- **Hubsäule ohne Synchronisation** als einzige Lösung: Nicht gerechnet. Ihre
  Mindesthöhe von 0,53 m liegt über der Fußhöhe von 0,13 m, die der
  Unterkorbzug braucht.

### 13.10 Quellen zu §13 (abgerufen 29.10.2026)

- [K12] igus-Pressemitteilung zum ReBeL, 16.03.2022 (Getriebe 80/105: 3 bzw. 25 Nm bei 6 U/min): https://presse.igus.de/der-rebel-der-automatisierung-smarter-igus-cobot-fuer-4-970-euro/
- [K13] igus drylin ZLW, technische Daten (Werte „in horizontaler Einbaulage“): https://igus.eu/drive-technology/linear-axes-with-toothed-belts/technical-data
- [K14] RBTX, Cobot-Hubsäule AI Lift (RBTX-BUS-0001, 2.340,00 € netto, 500 mm): https://rbtx.de/de-DE/components/profiles-more/cobot-lifting-column-ai-lift-500 ; Datenblatt Baumeister & Schack: https://a.storyblok.com/f/298593/x/ad1cc75250/13_ai-lift-baumeister-rev06.pdf
- [Q17], [Q18] wie `docs/hardware-auswahl.md`.

## 14. Machbarkeit: ReBeL auf der Arbeitsplatte über der Maschine (Variante C)

Stand: 29.10.2026. **Nur Machbarkeitsprüfung, kein Produktcode.** Frage des
Owners: Der Roboter steht auf der Arbeitsplatte über der Einbau-Spülmaschine
(Plattenoberkante 0,86 m, Vorderkante y = 0,05 m). Kann er dann den Oberkorb
mit Gläsern und Tellern leeren? Geprüft sind zwei Untervarianten:
**C1** (fest an der Vorderkante) und **C2** (auf der vorhandenen horizontalen
7. Achse entlang der Platte, Schiene in x). Gerechnet wurde mit denselben
Überschlagsskripten wie in §13, außerhalb des Repos. `rebel_model` und
`spuelmaschine/erreichbarkeit.py` blieben unverändert. Neu sind die Lage
(Fuß an der Kante, Neigung), die Halterung als Hindernis und die
Oberkorb-Teller.

### 14.1 Kurzfassung

- **Er leert den Oberkorb nicht vollständig.**
  - Steht der ReBeL aufrecht auf der Platte, reicht er an die Ablage auf der
    Platte. Den eingeschobenen Oberkorb kann er aber nicht ziehen: Der
    Frontgriff liegt 0,32 m unter der Platte und hinter der Kante.
  - Zieht der Arm geneigt über die Kante (C2, Roboterachse 105–135° aus der
    Senkrechten zum Raum hin), geht der Korbzug über 0,45 m. Dann erreicht er
    aber nur **2/16 Glasplätze**, **3/8 Teller** (nur die rechte Korbhälfte)
    und auf der Platte nur **1/4 Ablagepunkte** (Seitgriff, vordere Reihe).
- **C1 (fest) geht nicht.** Ohne die 8 cm Bauhöhe von Schiene und Schlitten
  fehlen beim Zug 2–5 cm (0,40–0,43 m statt 0,45 m). Gläser und Teller
  ergaben in der geneigten Lage 0 von 8 bzw. 0 von 5 geprüften Zielen.
- **Momente:** Der Zug geht. Mit Eigengewicht liegt J2 bei 10,0 Nm (20 N)
  bzw. 12,4 Nm (30 N), bei der Z-Achse waren es 18,4 bzw. 20,2 Nm.
  - Der geneigte Arm entlastet J2 (Eigengewicht 5–6 Nm statt 13–15 Nm).
  - Dafür liegt die J1-Achse fast waagerecht und trägt **10–15 Nm**
    Eigengewicht, auch in Ruhe.
- **Kamera:** Hinter oder über dem Roboter sieht die B57 den Oberkorb nicht:
  0 % bzw. 1–12 %. Der Roboter steht zwischen Kamera und Korb. Brauchbar
  bleibt nur ein Ausleger vor der Maschine (20–39 %), also wieder im
  Stehplatz.
- **Tür und Platz:** Die Tür schwenkt frei (0–90°, Halter, Fuß und Schiene
  frei, Parkpose gefunden). Vor der Maschine bleibt der Boden frei. Dafür
  belegt der Roboter die Arbeitsplatte und arbeitet in Kopfhöhe von Kindern.
- **Empfehlung:** Variante C nicht weiter verfolgen. Die Z-Achse frontal
  (§13) bleibt die bessere Lösung für den Oberkorb. C2 ist nur dann
  interessant, wenn ein zweiter Greifpunkt bzw. die Korbtiefe die
  Glasabdeckung ändert (§14.8).

### 14.2 Modell, Raster und Ziele

| Größe | C1: fest | C2: 7. Achse entlang der Platte |
|---|---|---|
| Fuß | Fußmitte x 0,15 / 0,30 / 0,45 m | Schiene x −0,40…0,90 m, Fuß fährt x −0,25…0,75 m (ZLW 1000 mm Hub) |
| Fußabstand zur Vorderkante d | −0,10…+0,15 m (+ = über die Kante) | dito, Schienenmitte |
| Neigung t der Roboterachse zum Raum | 0° stehend, 45°, 90° (Winkel), 135°, 180° hängend; nachgerechnet 105° und 120° | dito |
| Halterung (Hindernis) | Platte 0,25 × 0,25 m; überstehend Konsole unter dem Fuß, geneigt Keil bzw. Winkel, hängend Ausleger auf der Platte | dito über die Schienenlänge |
| Ablage | 4 Gläser auf der Platte rechts neben dem Fuß (x +0,30/+0,42 m, y −0,03/−0,15 m) | 4 Gläser hinter dem Schienenende (x 1,00/1,10 m, y −0,03/−0,15 m) |

- **Gierwinkel:** spielt bei J1 ±179° keine Rolle und wurde nicht variiert.
- **Vorfilter:** Reichweite aller Ziele, 120 Lagen (C1 90, C2 30), dazu
  Lagekonflikte von Fuß, Schiene und Halter.
- **Volle IK mit Kollisionsprüfung:**
  - Korbzug: stehend, 90°, 105°, 120°, 135° und hängend.
  - Alle Ziele: für die beste Lage je Variante, C2 bei 105°/d 0 und C1 bei
    105°/d 0/x 0,30.
- **Ausgeschieden im Vorfilter:**
  - Hängend (180°) bei d ≤ +0,10 m: Fuß trifft die Platte bzw. die
    Bottichdecke.
  - 45° bei d ≤ +0,05 m: Keil trifft die Bottichdecke.

Ziele (nur Oberkorb, 0,45 m ausgezogen, Regeln wie §13.2: 5 mm Rand,
IK-Fehler < 1 mm, Sprung ≤ 10° je 1-cm-Wegpunkt, Korbzug mit Szene je 1 cm):
- **Korbzug:** Zangengriff waagerecht an der oberen Frontstrebe (x 0,30,
  0,15 bzw. 0,45 m), 8 cm Anfahrt, 0,45 m Zug. Das Einschieben ist derselbe
  Weg rückwärts. Zusätzlich geprüft: Griff von oben.
- **Glasplätze:** 16 wie §13 (4 Reihen x 0,12–0,48 m × 4 Tiefen).
- **Teller im Oberkorb:** 8 Dessertteller, Annahme Ø 19 cm (Maßgedeck
  EN 50242 [K15]). Sie stehen hochkant in Stachelreihen, die Fläche zur
  Front, in zwei Reihen bei x 0,15 und 0,45 m, je 4 Tiefen 0,07–0,25 m
  hinter der Korbfront. Oberkörbe nehmen Teller bis Ø 22–27 cm auf, je nach
  Korbstufe [K16]; 19 cm liegt sicher darunter.
  - Griff von oben am Tellerrand, 2 cm tief, Finger schließen entlang y.
  - 10 cm Anfahrt, 15 cm Aushub (Tellerunterkante 3 cm über der Korbwand).
  - Die Teller sind wie in §6.3 nicht als Hindernis modelliert. Gläser
    stehen in diesem Lastfall nicht im Korb.
- **Ablage:** Griff von oben wie §13. Zusätzlich der Seitgriff am aufrechten
  Glas (TCP in Glasmitte, waagerecht von vorn, wie `config/ausraeumen.yaml`).

### 14.3 Abdeckung der Ziele

| Zielgruppe | heute (Podest 0,40 / 0,65 m) | Z-Achse frontal (§13) | C1 fest (stehend; geneigt 105°) | **C2 7. Achse (geneigt 105°, d 0)** |
|---|---|---|---|---|
| Oberkorb ziehen 0,45 m und einschieben | ja (7. Achse zieht) | ja | **nein**: stehend außer Reichweite; geneigt nur 0,40–0,43 m | **ja** (auch bei 120°/d +0,05 und 135°/d +0,15) |
| Glasplätze Oberkorb (16) | 3/16 | 6/16 | stehend 2/13 (Lauf vorzeitig beendet); geneigt 0/8 geprüft | **2/16** (x 0,24 und 0,36, vorderste Tiefe) |
| Teller Oberkorb (8) | nicht gerechnet | nicht gerechnet | geneigt 0/5 geprüft | **3/8** (rechts 3/4, links 0/4) |
| Ablage auf der Platte (4, Griff von oben) | 4/4 bei 0,65 m | 0/4 (Tisch 4/4) | stehend 4/4 (Vorfilter); geneigt 0/4 (90–163 mm zu weit) | 0/4 (97–179 mm zu weit) |
| Ablage auf der Platte (4, Seitgriff) | – | – | nicht gerechnet | 1/4 (vorn außen) |
| Tür schließen mit montiertem Roboter | geht | Parkhöhe ≥ 0,65 m nötig | geht (Lage frei) | **geht** (Halter, Fuß und Schiene frei im Schwenk 0–90°, Parkpose Arm über der linken Platte) |

Lesart:
- **Stehend fehlt der Korbzug.** Die eingeschobene Frontstrebe liegt bei
  y −0,04 m, z 0,54 m. Beim waagerechten Griff stünde das Handgelenk
  0,6 m von J2 entfernt, der Arm reicht 0,53 m. Von oben gegriffen fehlen
  6 mm, und J5 bekäme den Hebel aus §13.4 (4,1 Nm bei 20 N).
- **Stehend 90° (Winkel):** Der Zugweg reißt bei 48–50 von 54 Wegpunkten
  ab (0,40–0,42 m).
- **Hängend vor der Kante (180°, d +0,15 m)** findet keine IK für den
  Griffbeginn. Die Strebe liegt nur 0,07 m vom eigenen J2 entfernt, der Arm
  faltet aber nicht enger als ~0,19 m (J3 ≤ 140°).
- **Erst die Neigung um 105–135° bringt den Zug.** Dann liegt J2 vor der
  Kante auf etwa 0,86 m Höhe. C1 fehlen dabei 2–5 cm, weil Schiene und
  Schlitten bei C2 den Fuß um 8 cm von der Platte abheben. Ein C1-Winkel mit
  8 cm Distanz entspräche geometrisch C2 (nicht gerechnet).
- **Gläser:** Die äußeren Reihen x 0,12 und 0,48 m scheitern wie in §13 am
  150 mm breiten Greiferkörper.
  - In den inneren Reihen trifft der geneigte Unterarm ab der zweiten Tiefe
    die Plattenkante, die Bottichdecke oder die eigene Halterung.
  - Die hinterste Reihe (y 0,02 m) liegt unter der Platte, siehe
    `pose-glas-links-hinten.png`.
- **Teller:** Erreichbar ist nur die rechte Reihe, die hinterste davon
  stößt an den eigenen Fuß. Die linke Reihe (x 0,15 m) findet keine IK.
  Der Fuß fährt auf der Schiene mit. Die Ursache ist nicht untersucht.
- **Ablage:**
  - Die geneigte Basis reicht nicht bis auf die Plattenoberfläche: Die Hand
    müsste beim Griff von oben 0,2 m über dem Glas stehen.
  - Der Seitgriff erreicht die vordere Reihe. Bei 0,12 m Teilung trifft der
    Greiferkörper das Nachbarglas, nötig sind ≥ 0,16 m.
  - In der hinteren Reihe (y −0,15 m) streift der Unterarm die Platte.

### 14.4 Momente beim Korbzug mit Eigengewicht

Gerechnet ist `tau = Jᵀ F` über den ganzen Zugweg, Maximum je Gelenk. Dazu
kommt das Eigengewicht: Gliedmassen aus `config/robot.yaml` im
Link-Ursprung, Greifer 0,5 kg. Die Summe ist konservativ als |Zug| +
|Schwerkraft| je Wegpunkt gebildet. Grenzen [K10]: J1–J3 Nennmoment
10–15 Nm, Maximum 12,5–20 Nm. J4–J6 Nennmoment 2 Nm, Maximum 2,5–3 Nm.
Geurteilt wird gegen die unteren Werte.

| Lage | Zug | J1 | J2 | J3 | J4 / J5 | davon Eigengewicht J2 | Urteil |
|---|---|---|---|---|---|---|---|
| C2 105°, d 0 | 20 N | 7,2 | 13,1 | 9,4 | 0,8 / 1,1 | 5,7 | knapp (J2 über Nenn, unter Max) |
| | 30 N | 7,8 | 16,8 | 11,7 | 0,8 / 1,1 | 5,7 | geht nicht (J2 über 12,5) |
| **C2 120°, d +0,05** | 20 N | 4,6 | **10,0** | 9,3 | 1,1 / 0,7 | 5,3 | **geht** (J2 am Nennmoment) |
| | 30 N | 5,5 | 12,4 | 11,7 | 1,1 / 0,7 | 5,3 | knapp |
| C2 135°, d +0,15 | 20 N | 13,5 | 14,9 | 8,4 | 1,2 / 0,5 | 10,1 | geht nicht (J1, J2) |
| Z-Achse frontal (§13.4) | 20 / 30 N | 4,0 | 18,4 / 20,2 | 4,5 / 6,7 | 0 | 13,3–14,9 | knapp bis über Max |

- **Hängt der Arm nach unten, ist das für J2 günstiger.** Das Eigengewicht an
  J2 fällt von 13–15 Nm (Z-Achse) auf 5–6 Nm. Die Summe mit 20 N Zug fällt
  von 18,4 auf 10,0 Nm (120°). Ohne Eigengewicht trägt J2 aus dem Zug
  allein 5–8 Nm (20 N) bzw. 8–12 Nm (30 N).
- **Der Preis ist J1.** Bei 105–135° liegt die J1-Achse fast waagerecht. Das
  Eigengewicht des Arms dreht dann an J1:
  - in den Greifposen für Glas und Teller (0,25 bzw. 0,35 kg Last)
    10–15 Nm,
  - in der Parkpose 11 Nm.
  - Das liegt dauernd über dem Nennmoment von 10 Nm. Ob das J1-Getriebe das
    im Dauerbetrieb hält, muss am Gerät gemessen werden.
- **Das Handgelenk bleibt frei.** Die Zugkraft läuft wie in §13 entlang der
  Werkzeugachse. J4 und J5 tragen nur Eigengewicht (≤ 1,2 Nm).
- **Ergebnis:** Das Ziehen geht bei 20 N in der 120°-Lage. Bei 30 N ist es
  knapp. Mit 105° geht es bei 30 N nicht.

### 14.5 Kamera

Gerechnet mit dem Kamerawerkzeug aus §3, Oberkorb 0,45 m ausgezogen, die 8
Teller ergänzt. Der Arm steht in der Tellergreifpose (C2, 105°). Roboter und
Halter sind Hindernisse.

| B57-Lage | Streben % | Slots % | Geschirr % | Teller % | Abstand m |
|---|---|---|---|---|---|
| Wandhalter hinter dem Roboter (0,30; −0,50; 1,45) | 0 | 0 | 0 | 0 | 1,0–1,4 |
| Wandhalter tief (0,30; −0,45; 1,20) | 0 | 0 | 0 | 0 | 0,8–1,2 |
| Ausleger über der Kante (0,30; 0,05; 1,30) | 3 | 1 | 7 | 12 | 0,7–1,0 |
| Ausleger rechts über der Kante (0,75; 0,05; 1,20) | 5 | 0 | 0 | 0 | 0,7–1,1 |
| Ausleger vor der Maschine wie §4 (0,55; 0,35; 1,10) | 52 | 20 | 32 | 39 | 0,5–0,9 |

- **Befund:** Der Korb liegt unter der Plattenkante, der Roboter mit
  Halterung steht genau dazwischen. Von hinten bzw. oben verdecken Platte,
  Fuß und Unterarm fast alles.
  - Die Messsimulation über der Kante ergab einen Korbposen-Fehler von
    26 mm (§4: 0,06 mm).
  - Nur der Ausleger vor der Maschine sieht genug. Auch dort verdeckt der
    Arm in der Greifpose die Hälfte (§4 ohne Arm: 88 % der Slots).
- **D405** über dem Greifer unter 30°: Die Nahsicht hängt nicht vom Aufbau ab
  (§13.7: Zielglas 3,6 mm). In diesem Lauf überdeckten die ergänzten Teller
  das Zielglas der Konzeptszene. Die D405-Werte dieses Laufs sind deshalb
  nicht verwertbar.

### 14.6 Vergleich der Aufbauten

| Größe | heute | Z-Achse frontal | C1 fest auf der Platte | C2 7. Achse auf der Platte |
|---|---|---|---|---|
| Abdeckung Oberkorb (Zug / Gläser / Teller / Ablage Platte) | ja / 3/16 / – / 4/4 | ja / 6/16 / – / 0/4 (Tisch 4/4) | nein / ≤ 2/16 / 0 / 4/4 nur stehend | ja / 2/16 / 3/8 / 1/4 |
| Unterkorb | 9/20 Teller | 15/20 Teller, Zug ja | nicht erreichbar (0,6 m unter der Platte, nicht gerechnet) | dito |
| Platzbedarf | Podest 1,36 × 0,26 m rechts neben der Tür | Säule + Schlitten ≈ 0,30 × 0,45 m vor der Maschine | Fuß + Keil ≈ 0,25 × 0,30 m auf der Platte, Boden frei | Schiene 1,3 × 0,2 m entlang der Plattenkante + Keil, Boden frei, Arbeitsplatte über der Maschine belegt |
| Stehplatz vor der Maschine | frei | belegt | **frei** | **frei** |
| Kosten | ReBeL + ZLW-Bundle 10.499,07 € [Q17] | Bundle senkrecht 10.369–10.499 € (Freigabe offen) bzw. Hubsäule 2.340 € netto [K14] | ReBeL 4.970 € [Q18] + Keil/Winkel Eigenbau | ZLW-Bundle 10.499,07 € [Q17], waagerecht (die Einbaulage der Datenblattwerte [K13]) |
| Sicherheit | Roboter seitlich, Kniehöhe bis Brust | Säule im Stehplatz, vertikale Last ohne Bremse | Arm in 0,8–1,3 m Höhe an der Plattenkante, **Kopfhöhe von Kindern**, im Arbeitsplatz des Menschen | wie C1, dazu fährt die Achse 1 m entlang der Platte (Quetschstelle Schlitten ↔ Gegenstände auf der Platte) |
| J2 mit Eigengewicht beim Zug (20 N) | ≤ 0,6 Nm (Achse zieht) | 18,4 Nm | – | 10,0 Nm; dafür J1 10–15 Nm Dauerlast |

### 14.7 Empfehlung

1. **Variante C nicht weiter verfolgen.**
   - Auf der Platte erreicht der ReBeL entweder die Ablage (stehend) oder
     den Korbzug (geneigt), nie beides.
   - Geneigt schafft er nur 2 der 16 Glasplätze und die rechte
     Tellerreihe, das ist schlechter als die Z-Achse (6/16).
   - Die Kamera müsste trotzdem vor die Maschine.
   - Der Arm arbeitet in Kopfhöhe von Kindern und an der Arbeitsplatte.
2. **Was C2 gut macht:**
   - Die Achse liegt waagerecht in der freigegebenen Einbaulage.
   - Der Stehplatz und der Türschwenk bleiben frei.
   - J2 trägt beim Zug nur gut die Hälfte des Moments der Z-Achse.
   - Wer diese Vorteile will, muss vorher das J1-Dauermoment (10–15 Nm bei
     geneigter Achse) am Gerät messen.
3. **Die Z-Achse frontal (§13) bleibt die Empfehlung für den Oberkorb.**

### 14.8 Nicht gerechnet / offen

- **Nicht gerechnet:** Dynamik, Weg Korb → Ablage mit getragenem Teller,
  Umgreifen des kopfüber stehenden Glases, Teller als Hindernis für die
  Finger (Stachelteilung), Rackmatic-Stufen.
- **Abgebrochene Läufe:**
  - Gläser stehend (C1): 13 von 16 geprüft.
  - Gläser und Teller geneigt (C1): 8 bzw. 5 geprüft.
  - Grund: Diese Lagen ziehen den Korb nicht. Die Lauf-Zahlen sind
    Untergrenzen.
- **C1 mit 8 cm Distanz unter dem Fuß** sollte C2 geometrisch gleichen.
  Nicht gerechnet.
- **Seitgriff-Ablage** mit 0,16 m Teilung und Ablage näher an der Kante
  (y ≥ −0,05 m) könnte 2/4 ergeben. Nicht gerechnet.

### 14.9 Verworfen

- **Hängend vor der Kante (180°):**
  - bei d ≤ +0,10 m Lagekonflikt mit Platte bzw. Bottichdecke;
  - bei +0,15 m Griff zu nah an J2 (keine IK);
  - Ablage auf der Platte unerreichbar (0/4 im Vorfilter).
- **Stehend auf der Platte (0°):** kein Korbzug (waagerecht 0,6 m zu weit,
  von oben 6 mm und J5-Moment).
- **Winkel 90° (Arm waagerecht zum Raum):** Zugweg reißt bei 0,40–0,42 m ab.
- **Geneigt 135°, d +0,15 m:** Zug geht, aber J1 13,5 und J2 14,9 Nm bei
  20 N.
- **B57 an der Wand hinter dem Roboter:** 0 % Sicht auf den Oberkorb.

Bilder (Übersicht C2, Korbzug, Glas links hinten, Teller, Ablage,
Perspektiven B57 über der Kante und D405) liegen außerhalb des Repos und
gehen als Artefakt an den Owner.

### 14.10 Quellen zu §14 (abgerufen 29.10.2026)

- [K15] EN 50242, Maßgedeck (Dessertteller Ø 19 cm, Untertasse Ø 14 cm), Zusammenfassung: https://de.wikipedia.org/wiki/EN_50242
- [K16] Bosch, Gebrauchsanleitung Geschirrspüler (Oberkorb Stufe 1/2/3: Teller max. Ø 22/24/27 cm): https://media3.bosch-home.com/Documents/9000611003_A.pdf ; BSH-Datenblatt DF480101 (maximale Tellergrößen Ober-/Unterkorb 27/25, 24,5/27,5 bzw. 22/31 cm): https://media3.bsh-group.com/Documents/specsheet/de-DE/DF480101.pdf
- [K10], [K13], [K14], [Q17], [Q18] wie §13 bzw. `docs/hardware-auswahl.md`.
