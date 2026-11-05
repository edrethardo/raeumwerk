# Stationskamera Ensenso C57-6-S: Sichtbarkeit und Tiefenrauschen je Platz

Eingang für die Mastposition, die Prior-Kette und die Messvorhersagen. Erzeugt mit
`scripts/kamera_stationen.py` (Strahlschnitt, kein Fehlermodell; Glas als Silhouette).

## Modell

| Größe | Wert | Herkunft |
|---|---|---|
| Sensor | 2472 × 2064 px | `config/kameras.yaml`, `c57_6_s` (Art. 1009348) |
| Brennweite | f = 2591 px (x), 2381 px (y) | aus dem Arbeitsvolumen 954 × 867 mm bei 1 m: `f = Pixel · 1 m / Kantenlänge` |
| Betriebsabstand | 0,75–1,50 m, in Kamerarahmen-z | Datenblatt; Punkte außerhalb gelten als **nicht gemessen** |
| Tiefenrauschen | σ = 0,219 mm · z² (z in m) | Datenblatt 0,123 / 0,219 / 0,46 mm bei 0,75 / 1,0 / 1,45 m |
| Altes Modell (wählbar) | B57: f = 1628,7 px, 2024 × 2061 px, 0,21–2,0 m, σ = 1,533 mm · z² | `wahrnehmung.strahlen.ENSENSO_ALT`, Parameter `b57_alt` |

Mast (0,55; 0,50; 1,35) m, Blick auf die Korbmitte (0,30; 0,17) m, 60° unter der Waagerechten
(Blickpunkthöhe 0,63 m). Der Mensch zieht je einen Korb 0,45 m aus. Zielpunkte je Objekt: Glas Öffnung,
Boden und Mantel (25 Punkte), Teller Rand und beide Flächen (21 Punkte). „Sichtbar“ = Punkt frei (kein
anderer Körper im Strahl), im Bild und im Betriebsabstand.

## Vergleich der Gruppen (Mittel über die Plätze)

| Konfiguration | Gläser Oberkorb (16) z m / σ mm / sichtbar | Teller Oberkorb (8) | Teller Unterkorb (6) |
|---|---|---|---|
| altes Sichtfeld: B57, Mast 1,10 m | 0,71 / 0,78 / 99 % | 0,65 / 0,65 / 100 % | 0,89 / 1,22 / 100 % |
| C57-6-S, alter Mast 1,10 m | 0,71 / 0,11 / **16 %** | 0,65 / 0,09 / **0 %** | 0,89 / 0,17 / 90 % |
| B57, neuer Mast (0,55; 0,50; 1,35) | 0,97 / 1,43 / 99 % | 0,90 / 1,24 / 100 % | 1,13 / 1,97 / 100 % |
| **C57-6-S, neuer Mast (Standard)** | **0,97 / 0,20 / 99 %** | **0,90 / 0,18 / 95 %** | **1,13 / 0,28 / 100 %** |

Am alten Mast liegt der Oberkorb mit 0,48–0,84 m unter der 0,75-m-Grenze des C57-6-S: er wird dort
nicht gemessen. Der Mast auf 1,35 m und 0,50 m nach vorn holt beide Körbe in 0,73–1,19 m.

## Alle Plätze (Standard: C57-6-S, Mast 1,35 m)

| Platz | Korb | z Mitte m | z min–max m | σ mm | frei+Bild % | im Bereich % | sichtbar % |
|---|---|---|---|---|---|---|---|
| glas_1 | oberkorb | 0.851 | 0.79–0.87 | 0.16 | 100 | 100 | 100 |
| glas_2 | oberkorb | 0.891 | 0.83–0.91 | 0.17 | 100 | 100 | 100 |
| glas_3 | oberkorb | 0.930 | 0.87–0.95 | 0.19 | 100 | 100 | 100 |
| glas_4 | oberkorb | 0.970 | 0.91–0.99 | 0.21 | 96 | 100 | 96 |
| glas_5 | oberkorb | 0.887 | 0.82–0.91 | 0.17 | 100 | 100 | 100 |
| glas_6 | oberkorb | 0.927 | 0.86–0.94 | 0.19 | 100 | 100 | 100 |
| glas_7 | oberkorb | 0.967 | 0.90–0.98 | 0.20 | 100 | 100 | 100 |
| glas_8 | oberkorb | 1.006 | 0.94–1.02 | 0.22 | 96 | 100 | 96 |
| glas_9 | oberkorb | 0.923 | 0.86–0.94 | 0.19 | 100 | 100 | 100 |
| glas_10 | oberkorb | 0.963 | 0.90–0.98 | 0.20 | 100 | 100 | 100 |
| glas_11 | oberkorb | 1.003 | 0.94–1.02 | 0.22 | 100 | 100 | 100 |
| glas_12 | oberkorb | 1.043 | 0.98–1.06 | 0.24 | 96 | 100 | 96 |
| glas_13 | oberkorb | 0.959 | 0.90–0.98 | 0.20 | 100 | 100 | 100 |
| glas_14 | oberkorb | 0.999 | 0.94–1.02 | 0.22 | 100 | 100 | 100 |
| glas_15 | oberkorb | 1.039 | 0.97–1.06 | 0.24 | 100 | 100 | 100 |
| glas_16 | oberkorb | 1.079 | 1.01–1.10 | 0.26 | 100 | 100 | 100 |
| oberteller_0_1 (vorderster) | oberkorb | 0.908 | 0.82–0.89 | 0.18 | 100 | 100 | 100 |
| oberteller_0_2 | oberkorb | 0.932 | 0.84–0.92 | 0.19 | 100 | 100 | 100 |
| oberteller_0_3 | oberkorb | 0.955 | 0.87–0.94 | 0.20 | 100 | 100 | 100 |
| oberteller_0_4 | oberkorb | 0.979 | 0.89–0.97 | 0.21 | 100 | 100 | 100 |
| oberteller_1_1 | oberkorb | 0.817 | 0.73–0.80 | 0.15 | 100 | **57** | **57** |
| oberteller_1_2 | oberkorb | 0.841 | 0.75–0.83 | 0.15 | 100 | 100 | 100 |
| oberteller_1_3 | oberkorb | 0.865 | 0.78–0.85 | 0.16 | 100 | 100 | 100 |
| oberteller_1_4 | oberkorb | 0.889 | 0.80–0.88 | 0.17 | 100 | 100 | 100 |
| unterteller_0_1 | unterkorb | 1.155 | 1.07–1.14 | 0.29 | 100 | 100 | 100 |
| unterteller_0_2 | unterkorb | 1.179 | 1.09–1.17 | 0.30 | 100 | 100 | 100 |
| unterteller_0_3 | unterkorb | 1.203 | 1.11–1.19 | 0.32 | 100 | 100 | 100 |
| unterteller_1_1 | unterkorb | 1.064 | 0.98–1.05 | 0.25 | 100 | 100 | 100 |
| unterteller_1_2 | unterkorb | 1.088 | 1.00–1.07 | 0.26 | 100 | 100 | 100 |
| unterteller_1_3 | unterkorb | 1.112 | 1.02–1.10 | 0.27 | 100 | 100 | 100 |

Glas 1–16 = Reihen x 0,48 / 0,36 / 0,24 / 0,12 m (je 4 Plätze, von vorn nach hinten); Platz 5 ist
Reihe x 0,36 m, vorderster Platz. Teller `oberteller_<Reihe>_<Tiefe>`: Reihe 0 = x 0,15 m, Reihe 1 =
x 0,45 m (nächste am Mast). Der Oberkorb trägt entweder die Gläser oder die Teller (zwei Szenen, wie im
Aufbau ohne Überstand).

## Lesehinweise

- Der Tiefenbereich der Zielpunkte an einem Platz ist 0,05–0,10 m breit; `z min–max` zeigt, wo die
  Bereichsgrenze (0,75 m) schneidet: `oberteller_1_1` liegt mit 0,73 m teilweise unter der Grenze.
- σ im Betriebsbereich: 0,15 mm (z 0,82 m) bis 0,32 mm (z 1,20 m) je nach Platz –
  kleiner als jede andere Fehlerquelle der Kette (Kalibrierung 1,5 mm, Maskenrand).
- Das ist reine Geometrie. Nicht enthalten: Arm im Bild, Zwischenstellungen des Auszugs, nasses Glas,
  Reflexe (siehe `docs/griff-verrauscht.md`, Vereinfachungen).

## Mastposition mit Verdeckung, Auszugszuständen und Einfallswinkel (Kameratag P1)

Rechnung: `wahrnehmung/verdeckung.py` (Strahlschnitt je Pixel), `scripts/mast_raster.py` (Raster, Auswertung,
Vorhersagezeilen, Arm in Greifpose), `scripts/mast_teller_winkel.py` (Einfallswinkel), `scripts/mast_gegenprobe.py`
(Erreichbarkeit mit Kamerakörper); Tests `tests/test_verdeckung.py` (12). Das Mast-x bleibt 0,55 m.

### Was gerechnet wird

* **Szenen** je Kameraort: Oberkorb mit 16 Gläsern, Oberkorb mit 8 Tellern, Unterkorb mit 6 Tellern, jeweils der
  betrachtete Korb 0 / 0,225 / 0,45 m ausgezogen, der andere drin (9 Zustände). Hindernisse: Korbstäbe und
  Glashalter, Rahmen, Tür, Arbeitsplatte, Nachbargläser und Nachbarteller, Kamerakörper (Hüllquader
  0,29 × 0,10 × 0,10 m, Katalog 290 × 58 × 100 mm, Kantenzuordnung nicht geklärt, konservativ), Mastsäule (0,95; 0,0) mit
  Ausleger, Arm in der Ruhepose (kleinstes Schweremoment bei 5 cm Abstand zum Bedienraum: J2 −164°, hinter der Plattenkante, 6 cm Abstand).
* **Sichtbarkeit** = Anteil der Pixel eines Objekts, in denen es der erste Treffer ist (nicht der Mittelpunkt).
* **Brauchbar** nach den Mindestbedingungen von `schaetzer.py`, umgerechnet auf die Schätzerauflösung (Skala 2):
  Glas ≥ 30 echte Konturpixel und ≥ 50 % davon am Glasmantel (Verdeckungskanten zählen nicht); Teller ≥ 60 Tiefenpunkte
  im Betriebsabstand **und** Einfallswinkel < 60° **und** Konturbogen ≥ 40°.
* **Nutzbar** = brauchbar und Mittenabstand z ∈ [0,80; 1,45] m (5 cm Reserve zum Betriebsabstand 0,75–1,50 m).
  Beim Teller gibt es zwei Zählungen: **Fläche** (nur Pixel mit Normale ≈ Tellerachse; die Hauptgröße) und **mit Rand**
  (zusätzlich der schmale Tellerrand von 5 mm, dessen Normale radial liegt).
* Raster y ∈ {0,30 … 0,70} (5), z ∈ {1,15 … 1,60} (7, Schritt 0,075), Neigung {50°, 60°, 70°}: 105 Orte × 9 Zustände auf Skala 4,
  dazu ein Feinraster (y 0,65 / 0,70, z 1,175 … 1,275, 55° / 60°, 20 Orte). Die drei Endpositionen sind auf Skala 2 nachgerechnet
  (gleiche Zählung wie Skala 4 an der Hauptposition).
* Punktzahl = Mittel über Auszug 0,225 und 0,45 m von (Gläser nutzbar/16 + Oberkorb-Teller/8 + Unterkorb-Teller/6)/3. Auszug 0 geht nicht ein
  (Oberkorb drin, Sicht durch die Maschinenöffnung; nur zur Information).

### Einfallswinkel der Teller: gibt es einen erlaubten Mastort, der alle Teller unter 60° sieht? Nein.

Die Teller stehen hochkant in der Reihe (Normale entlang y). Der Winkel zum Sehstrahl hängt **nur vom Kameraort** ab,
`cos w = |y_Kamera − y_Teller| / Abstand`; die Neigung der Kamera ändert ihn nicht (sie bestimmt nur den Bildausschnitt).
Winkel zum Tellermittelpunkt, 14 Teller (8 Oberkorb, 6 Unterkorb), Mast x 0,55 m:

| Ort (y; z) | Auszug 0,225 m: Teller unter 60° / größter Winkel | Auszug 0,45 m: Teller unter 60° / größter Winkel | unter 70° bei 0,45 m |
|---|---|---|---|
| (0,70; 1,15) bester Ort im erlaubten Bereich | 13/14 / 60,3° | 5/14 / 70,8° | 13/14 |
| (0,70; 1,25) Hauptposition | 11/14 / 62,4° | 3/14 / 72,4° | 12/14 |
| (0,70; 1,45) | 7/14 / 66,0° | 0/14 / 74,8° | 9/14 |
| (0,50; 1,35) Bestand | 3/14 / 72,6° | 0/14 / 82,8° | 2/14 |

* Im erlaubten Bereich (y 0,30–0,70, z 1,15–1,60) liegen **nie alle 14** bei beiden Auszügen unter 60°. Mast x 0,30 statt 0,55 hilft kaum (14/14 bei 0,225 m, 6/14 bei 0,45 m).
* Alle 14 unter 60° bei beiden Auszügen gibt es erst bei y ≥ 0,4 + 0,5·z (Raster 0,05 m): z 0,80 → y ≥ 0,80; z 1,00 → y ≥ 0,90;
  z 1,20 → y ≥ 1,00; z 1,60 → y ≥ 1,20. Das liegt mindestens 0,25 m vor dem erlaubten Bereich (Kamera in Brusthöhe vor dem Bedienraum).
* **Optionen**, wenn Tellerflächen Tiefe liefern sollen: (a) Kamera an einem Stativ, 0,8–1,0 m hoch und ≥ 0,8–0,9 m vor der Front (am Kameratag möglich, am Roboter nicht; der Betriebsabstand 0,75 m zu den vordersten Tellern ist dort nicht geprüft und wird knapp); (b) Kamera verfahrbar (y/z), nicht nur schwenkbar, weil Schwenken den Winkel nicht ändert;
  (c) Teller um ≥ 12–15° zur Kamera geneigt im Ständer (Abschätzung: Winkel 72° → 60°); (d) Teller nur bei halbem Auszug (0,225 m) erfassen: an der Hauptposition 8/8 Oberkorb- und 5/6 Unterkorb-Teller nutzbar;
  (e) Tellerlage aus dem Mechanik-Prior statt aus der Pose und die Kamera nur prüfen lassen (Anwesenheit, Gier); (f) die Grenze 60° am Kameratag messen
  (Teller um die Hochachse drehen, 40° … 80°, Tiefenausfall und σ über dem Winkel) — sie ist eine Annahme, nicht gemessen.
* **Widerspruch zur früheren Zeile „Teller 16/16“** (`docs/griff-verrauscht.md`, vorderster Oberkorb-Teller): an der damaligen Stelle (0,55; 0,50; 1,35) liegt dieser Teller (Mitte 0,15; 0,33; 0,515) im Median bei 79° zum Sehstrahl; nur 14 % seiner Pixel liegen unter 60°.
  Die Mindestbedingungen sind trotzdem erfüllt (1661 Punkte auf Skala 2, Konturbogen 103°). Die 14 % passen zum schmalen Tellerrand (5 mm, Normale radial; seine Fläche ist etwa so groß); einzeln nachgewiesen ist das nicht.
  Die Flächenzählung stützt es: an der Bestandsposition sind bei 0,45 m Auszug 0/8 Oberkorb-Teller mit Fläche nutzbar, aber 7/8 „mit Rand“. Die „16/16“ jener Tabelle sind also vom Rand getragen.
  Zu den 0/131 Tellern der gerenderten Szenen passt das (Fläche unter 70–80°); warum der Rand dort nicht reicht, ist hier nicht untersucht (Vermutung: Nachbarn und Tellerstäbe verdecken ihn, die Ebenenanpassung braucht Fläche).
  „Mit Rand“ ist deshalb die **obere Schranke**, „Fläche“ die vorsichtige Zählung.

### Raster: Rangliste

| Ort (y; z; Neigung) | Punktzahl (Fläche) | mit Rand | Gläser / Ober-Teller / Unter-Teller nutzbar bei 0,225 m | bei 0,45 m |
|---|---|---|---|---|
| (0,70; 1,250; 55°) **Hauptposition** | 0,743 | 1,000 | 16 / 8 / 5 | 16 / 5 / 0 |
| (0,70; 1,225; 55°) | 0,740 | 0,948 | 16 / 8 / 6 | 15 / 4 / 0 (Reserve bei 0,45 m nicht eingehalten: Teller 6/8, Gläser 15/16) |
| (0,70; 1,150; 50°) | 0,688 | 0,854 | 16 / 8 / 6 | 12 / 3 / 0 (Reserve verletzt: nächster Teller 0,71 m) |
| (0,70; 1,450; 60°) **Alternative höher** | 0,569 | 1,000 | 16 / 8 / 1 | 16 / 2 / 0 |
| (0,50; 1,350; 60°) **Alternative weiter hinten (Bestand)** | 0,396 | 0,938 | 12 / 5 / 0 | 16 / 0 / 0 |

Gewählt: **y = 0,70 m ist in den besten Zeilen die Obergrenze des Bereichs** — das Raster läuft an den Rand; weiter nach vorn ist nur außerhalb des erlaubten Bereichs besser (siehe Winkeltabelle).
Die Hauptposition ist (0,70; 1,25) und nicht (0,70; 1,225) wegen der Reserve: dort liegen bei 0,45 m Auszug mehrere Plätze im Mittel unter 0,80 m.
Alle Zahlen: `mast_raster.py auswerten`; Rohzeilen je Platz im Artefaktordner des Laufs.

### Hauptposition und zwei Alternativen (Skala 2, Plätze nutzbar)

| | **Haupt** | Alternative höher | Alternative weiter hinten (Bestand) |
|---|---|---|---|
| Kameraort (x; y; z) m | 0,55; 0,70; 1,25 | 0,55; 0,70; 1,45 | 0,55; 0,50; 1,35 |
| Neigung / Blickpunkt (m) | 55° / (0,30; 0,17; 0,41) | 60° / (0,30; 0,17; 0,44) | 60° / (0,30; 0,17; 0,63) |
| Gläser Oberkorb (16), Auszug 0,225 / 0,45 | 16 / 16 | 16 / 16 | 12 / 16 |
| Teller Oberkorb (8), Fläche, 0,225 / 0,45 | 8 / 5 | 8 / 2 | 5 / 0 |
| Teller Unterkorb (6), Fläche, 0,225 / 0,45 | 5 / 0 | 1 / 0 | 0 / 0 |
| Teller mit Rand, Ober / Unter, 0,45 | 8 / 6 | 8 / 6 | 7 / 6 |
| Sichtbare Fläche Gläser (Mittel), 0,225 / 0,45 | 74 % / 87 % | 80 % / 91 % | 82 % / 97 % |
| Platz-z Oberkorb bei 0,45 m (Mitte min–max) | 0,80–1,06 m | 0,98–1,21 m | 0,80–1,05 m |
| Platz-z Unterkorb bei 0,45 m | 1,03–1,16 m | 1,23–1,34 m | 1,04–1,19 m |
| σ (0,219 mm · z²) Oberkorb / Unterkorb | 0,14–0,25 / 0,23–0,29 mm | 0,21–0,32 / 0,33–0,39 mm | 0,14–0,24 / 0,24–0,31 mm |
| Körbe vollständig im Bild (Ecken der Korbhülle), 0,225 / 0,45 | 8/8 / 7/8 (Unterkante Unterkorb am Rand) | 8/8 / 8/8 | 7/8 / 6/8 |
| Unterschied zur Haupt | — | +0,20 m höher: weiter weg, Gläser gleich gut, Teller schlechter | 0,20 m weiter hinten, 0,10 m höher: Teller kaum nutzbar, Gläser bei 0,225 m 12/16 |
| Erreichbarkeit mit Kamerakörper + Säule | 8/16, 8/8, 4/4 | 8/16, 8/8, 4/4 | 8/16, 8/8, 4/4 |

Der Unterschied zur Haupt in einer Größe: *höher* ändert den Betriebsabstand (Unterkorb bis 1,34 m, σ steigt um ~40 %) bei gleichen Gläsern;
*weiter hinten* ist der frühere Stand und zeigt, was die Verdeckung und der Winkel gegenüber der reinen Geometrie ausmachen.
Gläser: an der Hauptposition sind bei 0,225 und 0,45 m alle 16 nutzbar; bei Auszug 0 (Korb drin) nur 10/16 (es fehlen g1, g4, g8, g12, g13, g16).

**Montagehinweis (Hauptposition):** Mastsäule bei (0,95; 0,0) auf der Platte (Oberseite 0,86 m); optisches Zentrum der Kamera 0,39 m über der Plattenoberseite, bei x 0,55 (0,40 m von der Säule), y 0,70;
Ausleger L-förmig: 0,70 m in y von der Säule bis zur Kamera und 0,40 m in x, 7–11 cm über dem Kameraort; Blickachse 55° unter der Waagerechten auf (0,30; 0,17; 0,41).
Die Kamera steht damit 0,65 m vor der Plattenvorderkante (y 0,05) und liegt im angenommenen Bedienraum des Menschen (x −0,05…0,65, y ≥ 0,10): ein langer, stoßgefährdeter Ausleger. Die Alternative „weiter hinten“ hat 0,20 m weniger davon.

### Arm in Greifpose als Hindernis

An den acht erreichbaren Glasplätzen (Greifposen aus dem Aufbau ohne Überstand) gehen der Ensenso-Sicht auf die *anderen* Gläser pro Greifpose 0–4 von 15 nutzbaren Plätzen verloren
(Mittel 2,4 an der Hauptposition, 1,8 höher, 1,9 hinten; am häufigsten g12, g8, g16, g4 an der Hauptposition). Bei den acht Tellergreifposen verliert die Hauptposition keinen Platz, die höhere einen (oberteller_0_4).
Daraus folgt: **während eines Griffs im Oberkorb ist die Ensenso-Sicht auf Nachbargläser nicht verlässlich; die Messung gehört vor den Griff (Arm in Ruhe).** Der Weg von der Ruhepose zum Ziel ist nicht als Hindernis gerechnet, nur Ruhe und Greifpose.

### Erreichbarkeits-Gegenprobe

`raeumwerk aufbau` mit Kamerakörper, Säule und Ausleger als Hindernisse: für alle drei Positionen **Gläser 8/16, Teller 8/8, Ablage 4/4**, dieselben Plätze wie ohne Kamera (2, 3, 5, 6, 7, 10, 11, 14).
Positivkontrolle, damit die Probe nicht blind ist: eine Kamera bei (0,40; 0,20; 1,00) im Arbeitsraum des Arms senkt die Abdeckung auf Gläser 0/16, Teller 0/8 (Kollisionen von J2…J4 mit Kamera und Ausleger).

### Vorhersagezeilen (Hauptposition; Katalog Zeilen 2–4)

* **Abstände (Zeile 2), ±2 cm:** Kamera → Mitte Plattenvorderkante 0,80 m; → Mitte Oberkorb-Front am Boden (0,45 m aus) 0,91 m; → Mitte Unterkorb-Front am Boden (0,45 m aus) 1,18 m
  (Kamerarahmen-z 0,72 / 0,89 / 1,11 m). Plätze bei 0,45 m Auszug: Oberkorb z 0,80–1,06 m, Unterkorb 1,03–1,16 m. Das weicht von der Zeile des Entwurfs („Oberkorb 0,82–0,98 / Unterkorb 1,02–1,20 m“) ab und ersetzt sie für die Hauptposition.
  Höhere Alternative: 0,91 / 1,10 / 1,37 m; Bestand: 0,71 / 0,97 / 1,25 m.
* **Bildausschnitt (Zeile 3):** Sichtfeld 954 × 867 mm bei 1 m; an der mittleren Platzebene des Oberkorbs bei 0,45 m Auszug rund 830–890 × 750–810 mm, Unterkorb rund 1050 × 950 mm. Der Oberkorb belegt bei 0,45 m Auszug 14–92 % der Bildbreite
  und 15–87 % der Bildhöhe, der Unterkorb 20–85 % und 33–100 % (Unterkante am Bildrand; 7 von 8 Ecken der Korbhülle im Bild).
* **Sichtbarkeit je Platz (Zeile 4):** Gläser Oberkorb 16/16 nutzbar bei 0,225 und 0,45 m (sichtbare Fläche 74 % / 87 %, g4 als hinterster Platz der Reihe x 0,48 am schwächsten: 57 % / 68 %); Oberkorb-Teller (Fläche) 8/8 bei 0,225 m, 5/8 bei 0,45 m
  (nicht nutzbar: die drei vordersten, 63–67° Einfallswinkel); Unterkorb-Teller 5/6 bei 0,225 m, 0/6 bei 0,45 m (65–72°). Je Platz mit Abstand und Einfallswinkel im Rohdatenordner des Laufs.

### Was idealisiert bleibt

* Stäbe, Glashalter und Rahmen sind Quader bzw. Zylinder in Nennmaßen; Tellerstäbe fehlen in der Oberkorb-Tellerszene; Korbverformung und Wackeln nicht.
* Glas ist eine Silhouette (Vollzylinder), keine Brechung, keine Reflexe, keine Nässe; Teller sind glatte flache Zylinder (5 mm Rand), kein Dekor, keine Muldenform.
* Die Winkelgrenze 60° und die Mindestbedingungen sind die Annahmen der Schätzer, nicht gemessen. Das Tiefen-Fehlermodell (Ausfälle, Durchblick) ist **nicht** im Raster; die Zahlen sind geometrische obere Schranken.
* Kamerahülle konservativ als achsparalleler Quader; Säule/Ausleger als Balken; der Bedienraum (x −0,05…0,65, y ≥ 0,10, z 0…2,0) ist eine Annahme.
* Der Oberkorb enthält in der Unterkorbszene keine Gegenstände, der Unterkorb in den Oberkorbszenen ebenso; mit Inhalt wäre die Sicht auf den Unterkorb eher schlechter.
* Greifposen nur im Oberkorb (der Aufbau enthält keine Unterkorb-Ziele); die Ruhepose ist die Stellung mit kleinstem Schweremoment (Suche), nicht die gewählte Parkpose des Betriebs.
