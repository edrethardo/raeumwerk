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
