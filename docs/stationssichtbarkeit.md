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

**Stand dieses ersten Abschnitts (früheres Modell):** Geometrie ohne Verdeckung durch Stäbe, Kamerakörper und Arm, Teller nach
der **Rand-Zählung** (ohne Einfallswinkel-Prüfung der Fläche). Die Zahlen bleiben als Vergleichsstand stehen; die Mastposition
wird im Abschnitt „Mastposition mit Verdeckung …“ weiter unten mit Verdeckung und Einfallswinkel neu bestimmt
(Hauptposition (0,55; 0,70; 1,25) m, Neigung 55°).

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
| C57-6-S, Mast (0,55; 0,50; 1,35) *(früherer Standard; Rand-Zählung, altes Sichtfeld = Geometrie ohne Verdeckung)* | 0,97 / 0,20 / 99 % | 0,90 / 0,18 / 95 % | 1,13 / 0,28 / 100 % |

Der frühere Standard (0,55; 0,50; 1,35) ist nach der Neuberechnung mit Verdeckung und Einfallswinkel die „Alternative weiter hinten
(Bestand)“; **Standard ist jetzt die Hauptposition** (siehe unten). Die Teller-Sichtbarkeit von 95 % / 100 % dieser Zeile ist die
Rand-Zählung: mit der Flächen-Zählung sind an derselben Stelle bei 0,45 m Auszug 0/8 Oberkorb- und 0/6 Unterkorb-Teller nutzbar.

Am alten Mast liegt der Oberkorb mit 0,48–0,84 m unter der 0,75-m-Grenze des C57-6-S: er wird dort
nicht gemessen. Der Mast auf 1,35 m und 0,50 m nach vorn holt beide Körbe in 0,73–1,19 m.

## Alle Plätze (früherer Standard: C57-6-S, Mast (0,55; 0,50; 1,35); Rand-Zählung, ohne Verdeckung)

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
(Erreichbarkeit mit Kamerakörper); Tests `tests/test_verdeckung.py` (12) und `tests/test_mast_raster.py` (16: Nutzbarkeitsfenster, Einfallswinkel, Rand gegen Fläche). Das Mast-x bleibt 0,55 m.

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
  dazu ein Feinraster (y 0,65 / 0,70, z 1,175 … 1,275, 55° / 60°, 20 Orte). Die vier Endpositionen (Haupt, höher, Bestand, einfacher Ausleger) und die
  60°-Variante der Hauptposition sind auf Skala 2 nachgerechnet (gleiche Zählung wie Skala 4 an der Hauptposition).
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
| (0,60; 1,30) einfacher Ausleger | 7/14 / 67,5° | 0/14 / 77,7° | 5/14 |
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
| (0,60; 1,300; 60°) **Alternative einfacher Ausleger** (Skala 2; im Raster Skala 4 ebenfalls 0,549 / 1,000) | 0,549 | 1,000 | 16 / 8 / 1 | 16 / 1 / 0 |
| (0,50; 1,350; 60°) **Alternative weiter hinten (Bestand)** | 0,396 | 0,938 | 12 / 5 / 0 | 16 / 0 / 0 |

Gewählt: **y = 0,70 m ist in den besten Zeilen die Obergrenze des Bereichs** — das Raster läuft an den Rand; weiter nach vorn ist nur außerhalb des erlaubten Bereichs besser (siehe Winkeltabelle).
**Das Ranking Haupt > höher > einfacher Ausleger > Bestand gilt für die Flächen-Zählung.** In der Rand-Zählung sind Haupt, höher und einfacher Ausleger gleich (1,000), der Bestand liegt nahe (0,938);
die Rangliste ist dann kein Unterschied mehr der Teller, sondern nur noch Ausleger und Betriebsabstand (siehe „Fläche oder Rand“).
Die Hauptposition ist (0,70; 1,25) und nicht (0,70; 1,225) wegen der Reserve: dort liegen bei 0,45 m Auszug mehrere Plätze im Mittel unter 0,80 m.
Alle Zahlen: `mast_raster.py auswerten`; Rohzeilen je Platz im Artefaktordner des Laufs.

### Hauptposition und drei Alternativen (Skala 2, Plätze nutzbar)

| | **Haupt** | Alternative höher | Alternative weiter hinten (Bestand) | Alternative einfacher Ausleger |
|---|---|---|---|---|
| Kameraort (x; y; z) m | 0,55; 0,70; 1,25 | 0,55; 0,70; 1,45 | 0,55; 0,50; 1,35 | 0,55; 0,60; 1,30 |
| Neigung / Blickpunkt (m) | 55° / (0,30; 0,17; 0,41) | 60° / (0,30; 0,17; 0,44) | 60° / (0,30; 0,17; 0,63) | 60° / (0,30; 0,17; 0,44) |
| Gläser Oberkorb (16), Auszug 0,225 / 0,45 | 16 / 16 | 16 / 16 | 12 / 16 | 16 / 16 |
| Teller Oberkorb (8), Fläche, 0,225 / 0,45 | 8 / 5 | 8 / 2 | 5 / 0 | 8 / 1 |
| Teller Unterkorb (6), Fläche, 0,225 / 0,45 | 5 / 0 | 1 / 0 | 0 / 0 | 1 / 0 |
| Teller mit Rand, Ober / Unter, 0,225 | 8 / 6 | 8 / 6 | 8 / 6 | 8 / 6 |
| Teller mit Rand, Ober / Unter, 0,45 | 8 / 6 | 8 / 6 | 7 / 6 | 8 / 6 |
| Punktzahl Fläche / mit Rand | 0,743 / 1,000 | 0,569 / 1,000 | 0,396 / 0,938 | 0,549 / 1,000 |
| Sichtbare Fläche Gläser (Mittel), 0,225 / 0,45 | 74 % / 87 % | 80 % / 91 % | 82 % / 97 % | 81 % / 93 % |
| Platz-z Oberkorb bei 0,45 m (Mitte min–max) | 0,80–1,06 m | 0,98–1,21 m | 0,80–1,05 m | 0,80–1,04 m |
| Platz-z Unterkorb bei 0,45 m | 1,03–1,16 m | 1,23–1,34 m | 1,04–1,19 m | 1,05–1,18 m |
| σ (0,219 mm · z²) Oberkorb / Unterkorb | 0,14–0,25 / 0,23–0,29 mm | 0,21–0,32 / 0,33–0,39 mm | 0,14–0,24 / 0,24–0,31 mm | 0,14–0,24 / 0,24–0,30 mm |
| Körbe vollständig im Bild (Ecken der Korbhülle), 0,225 / 0,45 | 8/8 / 7/8 (Unterkante Unterkorb am Rand) | 8/8 / 8/8 | 7/8 / 6/8 | 7/8 / 7/8 |
| Unterschied zur Haupt | — | +0,20 m höher: weiter weg, Gläser gleich gut, Teller schlechter | 0,20 m weiter hinten, 0,10 m höher: Teller kaum nutzbar, Gläser bei 0,225 m 12/16 | 0,10 m weniger Ausleger, 0,05 m höher, 60°: Gläser gleich; Fläche: Oberkorb-Teller bei 0,45 m 1/8 statt 5/8, Unterkorb 1/6 statt 5/6 bei 0,225 m |
| Erreichbarkeit mit Kamerakörper + Säule | 8/16, 8/8, 4/4 | 8/16, 8/8, 4/4 | 8/16, 8/8, 4/4 | 8/16, 8/8, 4/4 |

Der Unterschied zur Haupt in einer Größe: *höher* ändert den Betriebsabstand (Unterkorb bis 1,34 m, σ steigt um ~40 %) bei gleichen Gläsern;
*weiter hinten* ist der frühere Stand und zeigt, was die Verdeckung und der Winkel gegenüber der reinen Geometrie ausmachen;
*einfacher Ausleger* behält Abstand und σ der Haupt (Betriebsabstand praktisch gleich) und verliert nur Tellerfläche, also genau die Größe, die an der Randwulst hängt (nächster Abschnitt).
Gläser: an der Hauptposition sind bei 0,225 und 0,45 m alle 16 nutzbar; bei Auszug 0 (Korb drin) nur 10/16 (es fehlen g1, g4, g8, g12, g13, g16); am einfachen Ausleger bei Auszug 0 nur 8/16 (g3, g4, g7, g8, g11, g12, g15, g16).
Erreichbarkeit der einfachen Position: dieselben Plätze wie ohne Kamera (Gläser 2, 3, 5, 6, 7, 10, 11, 14).

### Fläche oder Rand: wovon das Ranking abhängt

| Zählung | Haupt | höher | einfacher Ausleger | Bestand |
|---|---|---|---|---|
| Punktzahl **Fläche** | **0,743** | 0,569 | 0,549 | 0,396 |
| Punktzahl **mit Rand** | **1,000** | **1,000** | **1,000** | 0,938 |

* **Die Reihenfolge Haupt > höher > Bestand hängt an der Zählung „Fläche“.** Mit „Rand“ sind Haupt und höher gleich (1,000), der Bestand liegt mit 0,938 nahe, und der einfache Ausleger
  ist ebenfalls 1,000: er hat gleich viele Gläser und Teller nutzbar wie die Haupt, mit 0,10 m weniger Ausleger.
* **Welche Zählung gilt, entscheidet die Randwulst-Dicke der echten Teller.** Zweig P3 (`docs/kameratag-p3.md`, Strahlschnitt, Bestandsposition, 131 Teller-Posen): mit 5 mm Randdicke gelingt die Teller-Pose
  in 96/131 Fällen, mit 12 mm in 0/131. Die Tellerfläche allein liefert bei 61–80° kaum Tiefe, der Rand trägt. Das spricht dafür, dass bei 5 mm eher die Rand-Zählung zutrifft, bei 12 mm weder Fläche noch Rand
  eine Teller-Pose liefern; gerechnet ist 12 mm nur an der Bestandsposition, nicht an den anderen Orten. Die 5 mm sind eine Annahme aus der Finger-Dokumentation (Auftrag 3–6 mm), die 12 mm eine Annahme der Szenen:
  **die echte Dicke ist eine Kameratag-Messgröße** und nicht entschieden.
* Die Zahlen sind nicht gleichwertig: 96/131 sind Posen aus dem Schätzer, die Punktzahl „Rand“ zählt Plätze, die die Mindestbedingungen erfüllen. Die Richtung stimmt überein, die Höhe nicht übertragbar.
* **Empfehlung: zwei Montagen bzw. Messreihen am Kameratag, nicht eine:** (1) Hauptposition (0,55; 0,70; 1,25), 55°; (2) einfacher Ausleger (0,55; 0,60; 1,30), 60°. Je Position dieselbe Reihe:
  Randdicke der echten Teller (Messschieber), Ensenso-Aufnahme je Teller bei 0,225 und 0,45 m Auszug, Tiefenpunkte auf Fläche gegen Rand getrennt auswerten, Pose gegen den bekannten Platz.
  **Entscheidungsregel:** trägt der Rand (Teller-Posen aus dem Rand gelingen an der einfachen Position bei beiden Auszügen), gilt der einfache Ausleger (gleiche Gläser, gleiche Rand-Punktzahl, 0,10 m weniger Ausleger);
  trägt er nicht, bleibt die Haupt (Fläche 0,743 gegen 0,549) — und selbst sie bringt den Unterkorb bei 0,45 m nur über den Rand (0/6 Fläche).

### 55° oder 60° an der Hauptposition

Der Reviewer fand im Raster (Skala 4) für (0,70; 1,25) bei 60° dieselben Zahlen wie bei 55° und alle Ecken des Unterkorbs im Bild. Auf Skala 2 nachgerechnet:

| Größe | 55° (Blickpunkt z 0,41) | 60° (Blickpunkt z 0,235) |
|---|---|---|
| Punktzahl Fläche / mit Rand | 0,743 / 1,000 | 0,743 / 1,000 |
| Gläser / Ober-Teller / Unter-Teller (Fläche), 0,225 m | 16 / 8 / 5 | 16 / 8 / 5 |
| dasselbe bei 0,45 m | 16 / 5 / 0 | 16 / 5 / 0 |
| Gläser sichtbar (Mittel) 0,225 / 0,45 m | 74 % / 87 % | 72 % / 87 % |
| Plätze vollständig im Bild, 0,225 m: Gläser / Ober-Teller / Unter-Teller | 16/16, 8/8, 6/6 | 14/16, 7/8, 6/6 |
| Plätze vollständig im Bild, 0,45 m: Gläser / Ober-Teller / Unter-Teller | 16/16, 8/8, 6/6 | 16/16, 8/8, 6/6 |
| Korbhülle: Ecken im Bild Oberkorb 0,225 m / Unterkorb 0,45 m | 8/8 / 7/8 | 7/8 / 8/8 |
| Auszug 0 (nicht gewertet): Gläser nutzbar / Ober-Teller / Korbhülle Oberkorb | 10/16 / 8/8 / 7/8 | 13/16 / 5/8 / 5/8 |

* Das Reviewer-Argument stimmt für den **Unterkorb** (60°: alle Ecken im Bild bei 0,45 m, 55°: 7/8, die Unterkante liegt am Bildrand; alle sechs Unterkorb-Teller sind aber auch bei 55° vollständig im Bild).
  Es kippt für den **Oberkorb** bei 0,225 m: bei 60° liegen zwei Gläser und ein Oberkorb-Teller nicht mehr vollständig im Bild und eine Ecke der Hülle fehlt.
* Die gewerteten Zahlen (Punktzahl, nutzbare Plätze) sind gleich, z und σ bis auf etwa 0,02 m bzw. 0,01 mm. Der Unterschied liegt nur in der Bildlage: 55° hält bei Auszug 0,225 m alle Plätze ganz im Bild, 60° die Hülle des Unterkorbs bei 0,45 m;
  bei Auszug 0 (Korb drin, nicht gewertet) hat 60° 3 Gläser mehr, 55° 3 Oberkorb-Teller mehr.
* **Entscheidung: 55° bleibt, weil es bei den gewerteten Auszügen mehr Plätze vollständig im Bild hält (zwei Gläser und ein Teller mehr bei 0,225 m); es ist ein schwacher Vorsprung, keine Überlegenheit.**
  60° ist gleichwertig in allen gewerteten Kennzahlen und würde bei 0,45 m den Unterkorb sauberer ins Bild bringen. Die Neigung ist am Kameratag ohne Umbau verstellbar; sie braucht keine eigene Messreihe,
  nur eine Aufnahme je Neigung in der Hauptposition, um Bildlage gegen Rechnung zu prüfen.

**Montagehinweis (Hauptposition):** Mastsäule bei (0,95; 0,0) auf der Platte (Oberseite 0,86 m); optisches Zentrum der Kamera 0,39 m über der Plattenoberseite, bei x 0,55 (0,40 m von der Säule), y 0,70;
Ausleger L-förmig: 0,70 m in y von der Säule bis zur Kamera und 0,40 m in x, 7–11 cm über dem Kameraort; Blickachse 55° unter der Waagerechten auf (0,30; 0,17; 0,41).
Die Kamera steht damit 0,65 m vor der Plattenvorderkante (y 0,05) und liegt im angenommenen Bedienraum des Menschen (x −0,05…0,65, y ≥ 0,10): ein langer, stoßgefährdeter Ausleger. Die Alternative „weiter hinten“ hat 0,20 m weniger davon.
**Montagehinweis (einfacher Ausleger):** gleiche Säule; Kamera bei (0,55; 0,60; 1,30), also 0,44 m über der Plattenoberseite und 0,55 m vor der Plattenvorderkante; Ausleger 0,60 m in y und 0,40 m in x; Blickachse 60° auf (0,30; 0,17; 0,44).
Das ist 0,10 m weniger Ausleger als an der Hauptposition (die „weiter hinten“-Alternative spart 0,20 m); die Kamera liegt ebenfalls im Bedienraum.

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

**Vorhersagezeilen, Alternative einfacher Ausleger** (0,55; 0,60; 1,30), 60°: Abstände ±2 cm: Kamera → Mitte Plattenvorderkante 0,75 m, → Mitte Oberkorb-Front am Boden (0,45 m aus) 0,93 m, → Mitte Unterkorb-Front am Boden 1,21 m
(Kamerarahmen-z 0,68 / 0,91 / 1,15 m; der Plattenrand liegt mit 0,68 m unter der Betriebsgrenze 0,75 m, ist aber kein Platz). Plätze bei 0,45 m: Oberkorb z 0,80–1,04 m, Unterkorb 1,05–1,18 m.
Sichtfeld an der mittleren Platzebene bei 0,45 m: Oberkorb rund 830–880 × 760–800 mm, Unterkorb rund 1060 × 970 mm; der Oberkorb belegt 12–92 % der Bildbreite und 13–92 % der Bildhöhe, der Unterkorb 19–85 % und 31–100 %.
Gläser Oberkorb 16/16 nutzbar bei 0,225 und 0,45 m (sichtbare Fläche 81 % / 93 %, g4 am schwächsten: 64 % / 77 %); Oberkorb-Teller (Fläche) 8/8 bei 0,225 m, 1/8 bei 0,45 m (nutzbar nur `oberteller_1_4`; die anderen 63–73°);
Unterkorb-Teller 1/6 bei 0,225 m, 0/6 bei 0,45 m (71–78°). Mit Rand: Oberkorb 8/8 und 8/8, Unterkorb 6/6 und 6/6. Rohzeilen je Platz: `vorhersage_v2.md` im Artefaktordner.

### Was idealisiert bleibt

* Stäbe, Glashalter und Rahmen sind Quader bzw. Zylinder in Nennmaßen; Tellerstäbe fehlen in der Oberkorb-Tellerszene; Korbverformung und Wackeln nicht.
* Glas ist eine Silhouette (Vollzylinder), keine Brechung, keine Reflexe, keine Nässe; Teller sind glatte flache Zylinder (5 mm Rand), kein Dekor, keine Muldenform.
* Die Winkelgrenze 60° und die Mindestbedingungen sind die Annahmen der Schätzer, nicht gemessen. Das Tiefen-Fehlermodell (Ausfälle, Durchblick) ist **nicht** im Raster; die Zahlen sind geometrische obere Schranken.
* Kamerahülle konservativ als achsparalleler Quader; Säule/Ausleger als Balken; der Bedienraum (x −0,05…0,65, y ≥ 0,10, z 0…2,0) ist eine Annahme.
* Der Oberkorb enthält in der Unterkorbszene keine Gegenstände, der Unterkorb in den Oberkorbszenen ebenso; mit Inhalt wäre die Sicht auf den Unterkorb eher schlechter.
* Greifposen nur im Oberkorb (der Aufbau enthält keine Unterkorb-Ziele); die Ruhepose ist die Stellung mit kleinstem Schweremoment (Suche), nicht die gewählte Parkpose des Betriebs.
