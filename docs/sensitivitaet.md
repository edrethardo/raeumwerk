# Sensitivitätsanalyse und Messreihenfolge für den ersten Kameratag (Kameratag P4)

Frage: Welche Messung am ersten Kameratag verändert die Entscheidung „Kette baut / baut nicht“ am stärksten, und welche
ist verzichtbar? Grundlage sind die Parameter aus P0 (C57-6-S im Raycast), P2 (Mechanik-Prior, neu hinsehen,
Zielverwechslung, Newton-Eckfälle), P3 (Isaac-Renders, Erkennung, Teller-Randdicke) und der Mast-Branch (vier Mastorte).

**Alles hier gilt für das geometrische Wahrnehmungsmodell mit wahrer Maske** (Raycast der Ensenso C57-6-S und der D405, Fehlermodell
`wahrnehmung/sensor.py`, Schätzer `wahrnehmung/schaetzer.py`, Erfolg nach `robustheit.erfolg_mechanisch`). Die Erkennung (P3) geht
nur als Wahrscheinlichkeit „Maske am Nennort gefunden“ ein, nicht als echte Maske. **Physik (Newton) ist nur an den sieben
Eckfällen aus P2 gerechnet, nicht im Raster.** Kein Zahlenwert hier ist eine Messung an der echten Anlage.

| Teil | Datei |
|---|---|
| Parameter, Zielgrößen, Mischung, Sobol-Schätzer | `wahrnehmung/sensitivitaet.py` |
| Modellauswertung (Design, Sweep, Verwechslung, Validierung) | `scripts/sensitivitaet_lauf.py` |
| Metamodell, Tornado, Sobol, Tabellen, Bilder | `scripts/sensitivitaet_auswerten.py` |
| Tests | `tests/test_sensitivitaet.py` |

## Parameter und Spannen

Plan = Ausgangspunkt der Sweeps. Jede Spanne hat eine Quelle oder ist als **Annahme** markiert.

| Parameter | Spanne | Plan | Quelle / Annahme |
|---|---|---|---|
| `dicke_mm` Tellerrand-Dicke (Randwulst) | 3–12 mm | 5 | Auftrag 3–6 mm, `config/finger.yaml` 5 mm; **12 mm = Szenenannahme ohne Quelle** (P3) |
| `gier_grad` Teller-Gier im Ständer (wahr, Betrag, Vorzeichen zufällig) | 0–8° | 1 | Prior ±1° (P2, Annahme); Newton: 3° ok, 7° Fehlgriff |
| `glas_lage_mm` Glaslage im Slot (Welt ±) | 0–10 mm | 5 | Prior ±5 mm (Annahme); P2 testet bis ±15 mm |
| `teller_lage_mm` Tellerlage x/y (Welt ±) | 0–15 mm | 5 | Prior ±5 mm (Annahme); zusätzlich zum Ticket, weil P2 hier die Schwachstelle fand |
| `kalib_versatz_mm` Station: Versatz | 0–30 mm | 5 | Ticket; P1/P2 rechnen σ 20 mm; **Plan 5 mm = „nach Kalibrierung“ (Annahme)** |
| `kalib_dreh_grad` Station: Drehung | 0–20° | 5 | Ticket; P1/P2 rechnen σ 15°; Plan 5° (Annahme); Glas (Zylinder) ignoriert die Drehung |
| `rausch_ens` Tiefenrauschen Station | 0,5–3 × (0,219 mm·z²) | 1 | Datenblatt C57-6-S, Spanne laut Ticket |
| `rausch_d405` Tiefenrauschen D405 | 0,5–3 × | 1 | Modell k = 0,02 1/m (Annahme, `sensor.py`); Spanne wie Station |
| `maske_versatz_px` Maske gegen Tiefe versetzt (σ) | 0–3 px | 0,7 | Modellannahme 0,7 px |
| `maske_kipp` Randpixel kippen (Wahrsch.) | 0–1 | 0,5 | Modellannahme 0,5 |
| `maske_bias_px` Maskenrand zu groß (+) / klein (−) | −3…+3 px | 0 | Annahme (Rasterpixel der Schätzung, Skala 2) |
| `mast` Mastort | 4 Klassen | Haupt | Mast-Branch: Haupt (0,55; 0,70; 1,25) 55°, höher (0,55; 0,70; 1,45) 60°, Bestand (0,55; 0,50; 1,35) 60°, einfacher Ausleger (0,55; 0,60; 1,30) 60°; Verdeckung aus dem Mast-Branch **nicht** im Modell |
| `erk_glas` Erkennungsrate Glas | 0–0,9 | 0,55 | P3 Baseline 55 % (Tag 86, Küche 66, dunkel 0), Mask R-CNN 31 % |
| `erk_teller` Erkennungsrate Teller | 0–0,9 | 0,45 | P3 Baseline 45 % (dunkel 31, Küche 54), Mask R-CNN 0 % klassenrichtig |
| `verwechslung` Zielverwechslung (Nachbarmaske, gegeben erkannt) | 0–0,2 | 0,05 | Ticket 0–20 %; P3 Nachbar/Verschmelzung 9 % (Glas), 16 % (Teller) |

Die drei Wahrscheinlichkeiten gehen analytisch ein (nicht gewürfelt): nicht erkannt → kein Griff; verwechselt → die Kette greift nie
erfolgreich, unbemerkt mit der gemessenen Rate (0 von 64 je Objekt und Kette, Wilson-Obergrenze 5,7 %; die Sobol-Rechnung mit der
Obergrenze liegt im Ergebnis-JSON).

## Zielgrößen

Je Versuch; Ketten **K** (heutige Prüfung, Abbruch bei Widerspruch), **A** („neu hinsehen“, D405-Pose zählt) und **B** (Mechanik-Prior).

* (a) Glas-Griff-Erfolg und (b) Teller-Griff-Erfolg: Kette greift **und** Griff liegt mechanisch im Fangbereich (Glas 9 mm, Teller Kerbe 7,66° und
  Greifpunkt ≤ 6 mm). Abbruch zählt als Nicht-Erfolg.
* (c) unbemerkter Fehlgriff: Kette greift, Griff nicht ok (Anteil der Versuche, nicht der Griffe).
* (d) brauchbare Aufnahme: Station-Schätzer nimmt an, D405-Schätzer nimmt an und die D405-Pose liegt ≤ 10 mm neben der Wahrheit
  (Kreuzprobe der Kette nicht eingerechnet).
* Variante „Physik-Gierlimit“ für den Teller: Erfolg nur bei Gierfehler ≤ 4° und Versatz ≤ 6 mm. **Die 4° sind eine Annahme** zwischen den zwei
  Newton-Punkten (Gierfehler 2° ok, ≈ 6° Fehlgriff, je 1 Seed); die geometrische Kerbengrenze 7,66° ist laut P2 zu optimistisch.

## Methode

* **Sweep** (816 Auswertungen): ein Parameter von Plan auf ein Gitter (68 Punkte einschließlich Plan), 6 Seeds je Punkt, Glas und Teller. Daraus Tornado (untere/obere Spannengrenze)
  und die Entscheidungsgrenzen. n = 6 je Punkt: Differenzen von 1–2 Läufen sind kein Beleg.
* **Design** (1024 Auswertungen = 512 Punkte × Glas/Teller): gestreutes Sobol-Design über die 12 Modellparameter, ein Seed je Punkt.
* **Metamodell** (Random Forest, 300 Bäume, `min_samples_leaf` 3; zum Vergleich Gradient Boosting) auf den 7 Ausgängen je Objekt; darauf **Sobol-Indizes**
  (Saltelli/Jansen, N = 2048 Grundpunkte, 15 Eingänge, also 34 816 Metamodell-Auswertungen je Zielgröße, 95-%-Bootstrap). Erkennung und Verwechslung werden analytisch aufgeschlagen.
* **Verwechslung** (128 Auswertungen): Nachbarmaske für beide Kameras; **Validierung** (128 Auswertungen): 16 frische Punkte × 4 Seeds.
* Keine Fehlerzeilen. Zeit: ≈ 4,3 s je Auswertung auf 4 Prozessen.

### Metamodell-Güte

R² auf dem 20-%-Hold-out (409 Trainings-, 103 Testpunkte je Objekt). Die Ausgänge sind 0/1 mit einem Seed; die **Rauschgrenze** (größtmögliches R²
bei binären Einzelseeds, aus den Vorhersagen geschätzt) steht daneben.

| Objekt | Ziel | R² Hold-out RF | GBM | 5-fach-CV RF | Rauschgrenze | R² Validierung (Mittel über 4 Seeds) |
|---|---|---:|---:|---:|---:|---:|
| Glas | Erfolg K | 0,44 | 0,45 | 0,52 | 0,59 | 0,68 |
| Glas | Erfolg A / B / brauchbar | −0,16 / −0,09 / −0,16 | | | < 0 | −0,14 / 0,08 / −0,15 |
| Glas | unbemerkt K/A/B | 0 % im ganzen Design, keine Varianz | | | | |
| Teller | Erfolg K / A / B | 0,61 / 0,55 / 0,46 | 0,26 / 0,36 / 0,39 | 0,53 / 0,47 / 0,47 | 0,65 / 0,60 / 0,50 | −1,17 / 0,07 / 0,78 |
| Teller | unbemerkt A / B | 0,25 / 0,24 | 0,26 / −0,09 | 0,32 / 0,21 | 0,34 / 0,05 | 0,37 / 0,29 |
| Teller | brauchbar | 0,58 | 0,56 | 0,61 | 0,60 | 0,47 |
| Teller (Physik-Gier) | Erfolg K / A / B | 0,21 / 0,39 / 0,45 | −0,04 / 0,15 / 0,41 | 0,27 / 0,23 / 0,46 | 0,54 / 0,47 / 0,42 | 0,94 / 0,82 / 0,85 |
| Teller (Physik-Gier) | unbemerkt K / A / B | – / 0,36 / 0,55 | – / 0,34 / 0,50 | 0,17 / 0,39 / 0,45 | – / 0,44 / 0,47 | −0,12 / −0,10 / 0,62 |

Lesart: **Der Random Forest erreicht beim Teller und bei Glas-K etwa die Rauschgrenze, mehr als R² ≈ 0,5–0,6 ist mit einem Seed je Punkt nicht zu holen.**
Für Glas A/B/brauchbar ist R² ≤ 0, weil diese Ausgänge nahezu konstant sind (Design-Mittel 97 %, 93 %, 97 %): da gibt es nichts zu erklären, die Sobol-Indizes
dieser Ausgänge sind klein und rauschbehaftet. Die Validierungs-R² mit nur 16 Punkten schwanken stark (−1,17 … 0,94) und sind kein Gütesiegel; die MAE liegt
je Ziel bei 0,002–0,12 (Anteil, siehe Ergebnisdateien). **Die Sobol-Rangfolge ist deshalb als Größenordnung zu lesen:** der Spearman-Rang zwischen RF und GBM liegt
bei 0,65–0,93 (K: 0,67–0,87, A: 0,65–0,93, B: 0,74–0,87). Ränge innerhalb der „Null“-Gruppe (ST < 0,03) sind nicht unterscheidbar.

## Ergebnis

### Mittlere Anteile im ganzen Design (gleichverteilt über alle Spannen, wahre Maske, Erkennung ausgeklammert)

| Objekt | Erfolg K | Erfolg A | Erfolg B | unbemerkt K | A | B | brauchbar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Glas | 17,2 % | 97,1 % | 93,4 % | 0,0 % | 0,0 % | 0,0 % | 97,3 % |
| Teller (geometrisch) | 4,1 % | 7,8 % | 32,4 % | 1,0 % | 8,6 % | 9,0 % | 14,8 % |
| Teller (Physik-Gierlimit 4°) | 2,7 % | 5,1 % | 16,8 % | 2,3 % | 11,3 % | 24,6 % | 14,8 % |

Die niedrigen Teller-Zahlen kommen großenteils aus der Spanne der Randdicke (mehr als die Hälfte der Spanne liegt über 7 mm, dort gibt es keine Station-Pose) und aus den
großen Kalibrierfehlern; sie sagen nichts über den erwarteten Betrieb. **Unbemerkte Fehlgriffe entstehen nur beim Teller und nur in A/B**, die weniger abbrechen.

### Tornado (Plan-Punkt, ein Parameter auf seine Spannengrenzen, Kette K, inklusive Erkennung mit Plan-Raten)

Plan-Basis K: (a) Glas 26 %, (b) Teller 36 %, (c) unbemerkt 0 %, (d) brauchbar 48 %. Auszug (untere / obere Spannengrenze, %):

| Parameter | a Glas | b Teller | c unbemerkt | d brauchbar |
|---|---|---|---|---|
| Erkennung Teller 0 → 0,9 | 26 / 26 | **0 / 71** | 0 / 0 | 26 / 69 |
| Kalibrier-Versatz 0 → 30 mm | **52 / 0** | **43 / 0** | 0 / 0 | 48 / 48 |
| Kalibrier-Drehung 0 → 20° | 26 / 26 | 28 / 0 | 0 / 0 | 48 / 26 |
| Erkennung Glas 0 → 0,9 | **0 / 43** | 36 / 36 | 0 / 0 | 21 / 64 |
| Tellerrand-Dicke 3 → 12 mm | 26 / 26 | **36 / 0** | 0 / 0 | 48 / 26 |
| D405-Rauschen 0,5 → 3 × | 26 / 26 | 36 / 0 | 0 / 4 | 48 / 48 |
| Maske kippen 0 → 1 | 44 / 35 | 36 / 21 | 0 / 0 | 48 / 48 |
| Tellergier 0 → 8° | 26 / 26 | 21 / 28 | 0 / 0 | 48 / 40 |
| Mast, Station-Rauschen, Maskenbias, Tellerlage, Glaslage | je ≤ 18 Prozentpunkte, ohne klare Richtung | | | |

Kette B (Basis a 52 %, b 43 %, c 0 %, d 48 %): Glas hängt nur an der Erkennung (0 / 86 %), Teller an Erkennung (0 / 86 %) und Dicke (43 / 0 %), Gier 43 / 28 %
und Tellerlage 43 / 28 % (unbemerkt 0 / 7 %); alle übrigen Parameter bewegen B um höchstens 9 Prozentpunkte (Tornado-Bilder und Vollständigkeit: Ergebnisdateien).
Die Prozentzahlen des Tornados enthalten die Plan-Erkennungsraten (0,55 / 0,45) und sind deshalb viel kleiner als die „sauberen“ Zahlen im Sweep.
Die Glas-K-Werte schwanken mit den Seeds (2–5 von 6) und folgen aus dem bekannten Kreuzproben-Fehlalarm bei 5 mm Versatz.

### Gemeinsame Rangfolge (Sobol-Gesamtindex ST, Metamodell, 15 Parameter, geometrisches Maß)

ST je Ziel (95-%-Bootstrap auf ST in den Ergebnisdateien; Mittel = Mittel der vier Ziele a, b, c, d):

**Kette K (heutige Prüfung)**

| Rang | Parameter | a Glas | b Teller | c unbemerkt | d brauchbar | Mittel |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Kalibrier-Versatz | 0,91 | 0,60 | 0,57 | 0,02 | 0,53 |
| 2 | Kalibrier-Drehung | 0,00 | 0,63 | 0,72 | 0,20 | 0,39 |
| 3 | Tellerrand-Dicke | 0,00 | 0,53 | 0,62 | 0,16 | 0,33 |
| 4 | Erkennung Glas | 0,31 | 0,00 | 0,00 | 0,75 | 0,26 |
| 5 | Erkennung Teller | 0,00 | 0,32 | 0,34 | 0,09 | 0,19 |
| 6 | D405-Rauschen | 0,00 | 0,17 | 0,29 | 0,00 | 0,12 |
| 7 | Tellerlage | 0,00 | 0,06 | 0,35 | 0,00 | 0,10 |
| 8–15 | Verwechslung 0,01; Maskenbias, Tellergier, Station-Rauschen, Glaslage, Maske-Versatz, Maske-Kippen, Mast | ≤ 0,01 | | | | ≤ 0,01 |

**Kette B (Mechanik-Prior)**

| Rang | Parameter | a Glas | b Teller | c unbemerkt | d brauchbar | Mittel |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Erkennung Glas | 0,95 | 0,00 | 0,00 | 0,75 | 0,42 |
| 2 | Tellerrand-Dicke | 0,00 | 0,76 | 0,59 | 0,16 | 0,38 |
| 3 | Erkennung Teller | 0,00 | 0,40 | 0,28 | 0,09 | 0,19 |
| 4 | Kalibrier-Drehung | 0,00 | 0,04 | 0,22 | 0,20 | 0,12 |
| 5 | Tellerlage | 0,00 | 0,06 | 0,37 | 0,00 | 0,11 |
| 6 | Kalibrier-Versatz | 0,01 | 0,01 | 0,07 | 0,02 | 0,03 |
| 7–15 | Maskenbias 0,02 u. a. | ≤ 0,03 | | | | ≤ 0,02 |

Mit dem **Physik-Gierlimit 4°** ändert sich beim Teller-Erfolg: Kette B: Tellergier steigt auf ST 0,55 (b) bzw. 0,33 (c), Mittel 0,22, Rang 3 hinter Erkennung Glas (0,43) und
Dicke (0,38); Kette K: Kalibrier-Drehung 0,90 (b) und Versatz bleiben vorn (Mittel 0,47 / 0,49), Tellergier nur 0,02. Im geometrischen Maß ist die Gier wirkungslos (ST ≤ 0,01), weil
die Kerbengrenze 7,66° weit weg liegt; **ob die Gier zählt, hängt damit an einer Annahme, die nur Newton klärt, nicht der Kameratag.**

**Bedingte Rangfolge** (Metamodell, Spannen eingeengt, als „nach der Messung“ gelesen):
nach Tellerrand ≤ 6 mm bleiben Kalibrierung (K) bzw. Erkennung (B) vorn; nach Tellerrand ≤ 6 mm **und** Kalibrierung klein (Versatz ≤ 5 mm, Drehung ≤ 5°) bleiben nur noch
Erkennung Teller (ST-Mittel 0,37 K / 0,43 B), Erkennung Glas (0,32 / 0,37), D405-Rauschen (0,19 K) und Tellerlage (0,15 / 0,18; für B der größte Treiber des unbemerkten Fehlgriffs, ST 0,60);
Kalibrier-Versatz fällt auf 0,07 / 0,00. Bei großer Kalibrierabweichung (10–30 mm, 10–20°) ist die Kette K ohnehin tot (siehe Grenzen) und B hängt nur an der Erkennung (0,48 / 0,33).

### Entscheidungsgrenzen (aus dem Sweep, „sauber“ = wahre Maske, übrige Parameter am Plan-Punkt, 6 Seeds je Wert)

| Parameter | Kette baut | Kette baut nicht | Beleg (Erfolg K / A / B, %) |
|---|---|---|---|
| Tellerrand-Dicke | ≤ 5 mm: Teller-Pose aus der Station | **≥ 8 mm: keine Station-Pose** (alle Ketten 0 %); 6–7 mm Grenzbereich | Teller 3–5 mm: 83 / 100 / 100; 6 mm: 67 / 100 / 100; 7 mm: 33 / 83 / 100; 8–12 mm: 0 / 0 / 0. Im Design haben 0 von 227 Tellerpunkten mit Dicke > 8 mm eine Station- und D405-Pose |
| Kalibrier-Versatz | K trägt bis ≈ 2,5 mm (Glas 100, Teller 100) | K ab ≥ 7,5–10 mm 0 % (Glas ab 10, Teller ab 7,5); bei 5 mm Glas 50 % (Fehlalarm) | Glas K: 100/100/50/17/0 % bei 0/2,5/5/7,5/10 mm; Teller K: 100/100/83/0/0; A: Glas überall 100, Teller 100 bis 15 mm, 83 bei 20, 33 bei 30 mm (dort **unbemerkt 67 %**); B: überall 100 |
| Kalibrier-Drehung (Teller) | K und A bis 5° | K und A **0 % ab 10°** | B 100 % bis 20° |
| D405-Rauschen (Teller) | 1 ×: K 83, A 100, B 100 | **2 ×: K 33 (unbemerkt 17), A 50 (unbemerkt 50); 3 ×: K 0, A 0 (unbemerkt 100)** | B bleibt 100 % |
| Tellerlage x/y | B ≤ 10 mm: 100 | B bei ±15 mm: 67 %, **unbemerkt 33 %** | K und A 83 / 100 |
| Tellergier (Physik-Limit 4°, Annahme) | B 100 % bis 3° | B 33 % bei 4–5°, 0 % ab 6° | geometrisch: kein Effekt bis 8° |
| Erkennung Glas | Erfolg (A/B) = Erkennungsrate × (1 − Verwechslung) × sauberer Anteil (97–100 % im Plan-Bereich); linear, keine Schwelle | – | Baseline Tag 86 % (P3) liefert ≈ 80 % Erfolg, Küche 66 % und dunkel 0 % nicht |

Messung **wertlos** (kein Einfluss im Modell, ST ≤ 0,03 bei K und B, auch in den Sweeps ohne klare Wirkung): Mastort, Tiefenrauschen der Station,
Maske (Versatz, Kippen, Bias im Bereich ±3 px), Glaslage 0–10 mm (A und B fangen sie ab; K schwankt mit Kalibrierfehlalarmen), Zielverwechslung (ST ≤ 0,02:
sie kostet im Modell linear Griffe, aber keine unbemerkten Fehlgriffe).

### Empfohlene Messreihenfolge für den ersten Kameratag (Top 5)

Aufwand = Annahme (Minuten am Kameratag), keine Messung. Einfluss = Sobol-Mittel K/B aus der Tabelle oben.

| Nr. | Messung | Aufwand | Hilfsmittel | Einfluss (ST K / B) | Entscheidet über |
|---:|---|---:|---|---|---|
| 1 | **Randdicke der echten Dessertteller** + eine Ensenso-Aufnahme der Tellerreihe in Mastpose | 20 min | Messschieber, 3 Teller, Pose-Schätzer | 0,33 / 0,38 (b: 0,53 / 0,76) | Teller aus der Station: ≤ 6 mm ja, ≥ 8 mm nein |
| 2 | **Kalibrierung Station**: Versatz und Drehung (ein Durchgang) | 45 min | Kalibriertafel, TCP auf 3–5 Referenzpunkte | 0,53 + 0,39 / 0,03 + 0,12 | K reicht (Versatz ≤ 2,5 mm, Drehung ≤ 5°) oder A/B nötig (> 5 mm / > 10°) |
| 3 | **Erkennungsrate bei den Lichtlagen** (Glas, Teller; Nachbartreffer mitzählen) | 75 min | 20+ Aufnahmen bei Tag/Küche/dunkel, Handlabel, Erkennungslauf | 0,26 + 0,19 / 0,42 + 0,19 | Glas bei Tageslicht ≈ 80 % Erfolg möglich (Erkennung × ~0,95), Küche/dunkel nicht; Teller: P3 gibt für die Baseline-Maske 3 % Pose-Ausbeute |
| 4 | **Tellerlage und -gier im Ständer** | 35 min | Messschieber/Lehre, Winkelmesser an 6 Tellern | 0,10 / 0,11 (unbemerkt B 0,37); Gier nur im Physik-Maß 0,02 / 0,22 | B-Annahmen (±5 mm, ±1°): Lage > 10 mm und Gier > 3° kippen B |
| 5 | **D405-Rauschen am Teller** (und Hand-Auge-Kalibrierung) | 15 min | ebene Platte, 2 Abstände, je 5 Aufnahmen | 0,12 / 0,01 | Faktor ≥ 2: K bricht, **A unbemerkt gefährlich** |

Reihenfolge begründet: 1 und 2 sind billig und tragen die größten Teller-Indizes (ST b: Dicke 0,53 K / 0,76 B, Kalibrierung 0,60–0,63 bei K); danach bleibt die Erkennung
(größter Treiber für Glas, ST a 0,31–0,95), danach die Prior-Annahmen. Nach 1 und 2 sinkt der Einfluss aller übrigen Parameter (bedingte Rangfolge). **Mast-Umbau (≈ 120 min)
zählt im Modell nichts**; er gehört nicht in den ersten Tag, solange keine Verdeckung durch Arm und Kamerakörper aus dem Mast-Branch dafür spricht.

## Grenzen (nicht schönreden)

* **Modell, nicht Anlage.** Geometrie und angenommene Fehlermodelle; wahre Maske, außer dass die Erkennungsrate als Wahrscheinlichkeit eingeht. Physik nur an den P2-Eckfällen.
* **Die Maskenstörung dieses Modells ist harmlos gegen echte Erkennungsmasken.** P3 misst mit der Baseline-Maske beim Teller (5 mm) 4 von 131 (3 %) Posen gegenüber 96 von 131 mit wahrer Maske; die hier
  variierte Störung (±3 px, Kippen, Versatz) erklärt das nicht und hat deshalb ST ≈ 0. Die wahre Wirkung der Maskenqualität beim Teller ist also **im Modell unterschätzt**; die P3-Erkennungsraten sind der bessere Weg.
  Das Plan-Teller-Erkennungsniveau 0,45 überschätzt die Ausbeute der Baseline.
* **Mast:** ST ≈ 0 im Modell (im Plan-Punkt und im Design). Der Mast-Branch rechnet Verdeckung durch Arm, Kamerakörper und Mastsäule sowie Einfallswinkel der Tellerfläche; beides geht hier nicht ein (der Teller trägt hier über den Randwulst).
* **Kalibrierfehler als fester Betrag mit zufälliger Richtung** (Versatz) bzw. fester Gier-Richtung (Teller-Drehung um die Hochachse), nicht Gauß; Drehung bleibt für das Glas wirkungslos.
* **Spannen sind Annahmen und bestimmen die Indizes**: Sobol-Indizes hängen von der gewählten Spanne ab (die obere Hälfte der Dickenspanne erzeugt allein einen großen Teil der Teller-Varianz). Die bedingten Rangfolgen zeigen das.
* **Plan-Punkt:** Kalibrierung 5 mm / 5° und die Plan-Erkennungsraten sind Annahmen; der Tornado ist darauf zentriert.
* **Stichprobe klein:** 6 Seeds je Sweep-Punkt, 1 Seed je Design-Punkt, 16 Validierungspunkte; Metamodell-R² 0,2–0,6 (Rauschgrenze 0,4–0,65). Ränge unter ST 0,03 sind nicht unterscheidbar.
* **Unbemerkte Fehlgriffe** sind selten im Plan-Punkt (0–2 von 6 in einzelnen Sweep-Punkten) und treten im Design nur beim Teller und nur bei A/B auf; die Sobol-Werte für (c) beziehen sich auf seltene Ereignisse und sind die unsicherste der vier Zielgrößen.
* **Aufwand und „leicht messbar“** sind Annahmen des Autors, nicht gemessen.

## Reproduktion

```
scripts/sensitivitaet_lauf.py --out <ordner> --teil sweep --seeds 6
scripts/sensitivitaet_lauf.py --out <ordner> --teil design --n 512
scripts/sensitivitaet_lauf.py --out <ordner> --teil conf   --n 64        # Nachbarmaske
scripts/sensitivitaet_lauf.py --out <ordner> --teil val    --n 16 --seeds 4
scripts/sensitivitaet_auswerten.py <ordner> --out <auswertung> --sobol-n 2048   # Tabellen, Bilder, ergebnis.json
```
Optional `kappung.json` im Rohdatenordner deckelt `n`/`seeds`/`max_index` je Teil. Die Läufe sind fortsetzbar (eine Zeile je Auswertung).
Rohdaten (JSON-Zeilen, Tabellen, Bilder) liegen nicht im Repo.
