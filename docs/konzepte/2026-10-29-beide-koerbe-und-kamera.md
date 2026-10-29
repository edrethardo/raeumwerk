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
