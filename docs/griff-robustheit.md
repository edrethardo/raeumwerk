# Griffrobustheit bei einem Posefehler der Station (σ 15° / 2 cm)

Was passiert, wenn die *geschätzte* Objektpose streut, so wie es nach Kalibrierung,
Nachjustage und bei transparentem, nassem Geschirr der realistische Fall ist – und welche
Heilungsstrategien den Griff trotzdem sitzen lassen. Baut auf `docs/griff-verrauscht.md`
auf (dort der Fall *kleiner* Fehler); Aufbau, Objekte und Sensorik sind dieselben.

| Teil | Datei |
|---|---|
| Fehlermodell, Kalibrierfehler | `wahrnehmung/sensor.py` |
| Drift der Schätzung, Fusion, mechanische Grenzen | `wahrnehmung/robustheit.py` |
| Ablauf Ensenso → D405 → Prüfung (`posedrift`) | `wahrnehmung/griffpose.py` |
| Raster S0…S6, Wahrnehmung allein | `scripts/griff_robustheit.py` |
| Newton-Lauf, Strategie S0/S1 | `scripts/griff_lauf.py` (`--posedrift`, `--strategie`) |
| Tests | `tests/test_robustheit.py` |

## Fehlermodell

Der Fehler wird auf die **Station (Ensenso)** gelegt — die Pose, die die Grobpose liefert —,
nicht auf die Wahrheit: simuliert wird weiter in der wahren Welt
(`griffpose.schaetzen(..., posedrift=)`). Die D405 am Handgelenk sieht das Ziel in ihrer
(dann falschen) Vorposition **unabhängig neu**; genau das ist der Hebel. Ein Betrag von
0 mm / 0° ist bitgleich zum Lauf ohne Drift (`test_griffpose_posedrift_null_aendert_nichts`).

- **Raster:** Drehung {0; 5; 15}°, Versatz {0; 5; 20} mm, je 16 Seeds, Glas (Platz 5) und
  vorderster Dessertteller. Fester Betrag, zufällige Richtung (`drift_fest`); der Versatz
  liegt waagerecht (die Kalibrierung wirkt vor allem seitlich), beim Teller dreht der Fehler
  um die Hochachse (die wirksame Drehlage ist die Gier).
- **Zusätzlich σ-Variante:** Betrag/Drehung ~ N(0; 2 cm bzw. 15°), einmal frei, einmal hart
  begrenzt auf |Δp| ≤ 2 cm und |ΔR| ≤ 30°.
- **σ je Kamera** für die Fusion aus der eigenen Messung (`docs/griff-verrauscht.md`,
  Tabelle „Wahrnehmung allein", Mittel): Ensenso 2,0 mm (Glas) / 3,0 mm (Teller),
  D405 1,3 mm / 3,2 mm.

Reproduzieren (CPU, ohne Newton, ~4 s je Schätzung): `scripts/griff_robustheit.py --seeds 16
--out ORDNER` (schreibt `robustheit-glas.json`, `robustheit-teller.json`). Die Auswertung
unten entsteht aus diesen JSONs.

## Ergebnis Wahrnehmung (16 Seeds je Zelle)

**Glas.** Drehung ändert nichts (0°, 5°, 15° sind zeilengleich): das Glas ist ein Zylinder,
der Griff liest nur x, y. Der Versatz wirkt voll.

| Fehler | S0 mm (blind) | S1 mm | S2 mm | S0 Griff | S1 Kette | S2 Kette | S3 erkannt |
|---|---|---|---|---|---|---|---|
| 0 mm | 1,6 / 2,8 | 1,2 / 2,0 | 0,9 / 1,4 | 16/16 | 16/16 | 16/16 | 0/16 |
| 5 mm | 5,3 / 7,7 | 1,5 / 2,3 | 1,7 / 2,7 | 16/16 | 9/16 | 9/16 | 7/16 |
| 20 mm | 20,2 / 22,7 | 1,6 / 3,8 | 6,5 / 8,5 | 0/16 | 0/16 | 0/16 | 16/16 |
| σ 15°/2 cm, frei | 20,2 / 22,7 | 1,6 / 3,8 | 6,5 / 8,5 | 0/16 | 0/16 | 0/16 | 16/16 |
| σ 15°/2 cm, hart | 15,8 / 22,6 | 1,0 / 2,1 | 4,6 / 5,7 | 0/16 | 0/16 | 0/16 | 16/16 |

„S1 mm" = Restfehler der Griffpose gegen die Wahrheit (Mittel / Max), **unabhängig vom
Drift** (0 mm und 20 mm ergeben denselben Wert): die D405 **heilt 2 cm und 15° vollständig**,
Restfehler 1,2–1,6 mm, Max 3,8 mm — weit innerhalb des mechanischen Fangbereichs (9 mm).
„Kette" zählt nur, wenn zusätzlich die Prüfung nicht abbricht: bei 20 mm bricht die
Kreuzprobe Ensenso ↔ D405 (Toleranz 6 mm) **jedes Mal** ab, obwohl die D405-Pose 2 mm gut ist.

**Teller.** Die Drehung zählt (Gier); ab 15° verwirft die D405 die Schätzung (Normale weicht
ab) → die ganze Kette bricht ab.

| Fehler | S0 mm | S1 mm | S2 mm | S1 Gier | S0 Griff | S1 Kette | S2 Kette | S3 erkannt |
|---|---|---|---|---|---|---|---|---|
| 0° / 0 mm | 3,0 / 5,8 | 3,3 / 5,3 | 2,5 / 4,7 | 0,1 | 16/16 | 16/16 | 16/16 | 0/16 |
| 0° / 5 mm | 6,9 / 9,3 | 3,0 / 4,7 | 4,7 / 6,3 | 0,1 | 6/16 | 15/16 | 14/16 | 1/16 |
| 0° / 20 mm | 21,5 / 24,3 | 6,9 / 10,6 | 13,9 / 17,6 | 0,1 | 0/16 | 0/16 | 0/16 | 16/16 |
| 5° / 0 mm | 3,0 / 5,8 | 3,3 / 5,2 | 2,5 / 4,6 | **5,1** | 16/16 | 16/16 | 16/16 | 0/16 |
| 5° / 5 mm | 6,9 / 9,3 | 3,0 / 4,7 | 4,7 / 6,4 | **5,1** | 6/16 | 15/16 | 14/16 | 1/16 |
| 5° / 20 mm | 21,5 / 24,3 | 7,0 / 10,8 | 14,0 / 17,6 | **5,1** | 0/16 | 0/16 | 0/16 | 16/16 |
| 15° / beliebig | 3,0–21,5 | – | – | – | 0/16 | 0/16 | 0/16 | 16/16 |

Beim Teller heilt die D405 die **Lage**, nicht die **Drehlage**: die Gier bleibt der
Stationsfehler (bei 5° Drift 5,1° statt ~0°), weil die D405 nur einen dünnen Randbogen sieht.
Ab 15° Gier liegt der Fehler über der Kerbengrenze von **7,7°** (S4, aus der Fingergeometrie
`asin(8 mm/2 / 60 mm/2)`) — und die D405 verwirft die Schätzung ganz.

## Ergebnis Newton (Kurzläufe, CPU, 8 Kerne)

Je Lauf ein Objekt, Kurzlauf bis Aushub (Glas) bzw. erste Querfahrt zum Ständer (Teller),
Griffpose aus der gestörten Wahrnehmung. Laufzeit Kurzlauf Glas ~327 s, Teller ~566 s.
Reproduzieren: `scripts/griff_lauf.py --art glas|teller --seed 1 --wahrnehmung
[--posedrift T_MM,R_GRAD --strategie s0|s1] --device cpu --out ORDNER`.

| Lauf | Wahrnehmung | Ergebnis | Aushub | Hand | Finger | Gründe |
|---|---|---|---|---|---|---|
| Glas S1, kein Drift | ok, 0,6 mm | **Erfolg** | 149 mm | 0,7 mm | 1,2 mm | – |
| Glas S0, 20 mm/15° | Widerspruch, „blind" 18,5 mm | **Planfehler** | – | – | – | „Griff im Korb nicht planbar", kein Griff |
| Glas S1, 20 mm/15° | Widerspruch, **D405 2,4 mm** | **Abbruch** | – | – | – | sicherer Abbruch, kein Griff |
| Teller S1, kein Drift | ok, 4,0 mm | **Erfolg** | 200 mm | 4,2 mm | 2,2 mm | – |
| Teller S0, 10 mm/10° | „blind" 13,7 mm | **Fehlgriff** | **0,7 mm** | **467 mm** | 4,6 mm | nicht_aus_dem_korb, gefallen_oder_gerutscht, durchdringung |
| Teller S1, 10 mm/10° | Normale weicht ab | **Abbruch** | – | – | – | sicherer Abbruch, kein Griff |

Die Kurzläufe bestätigen die Wahrnehmungstabelle: **blind (S0)** ist der Teller bei 14 mm
nicht gegriffen und fällt zu Boden (Aushub 0,7 mm, Hand wandert 467 mm, Finger 4,6 mm über
der 3-mm-Grenze) — der Glass-Griff ist bei 20 mm nicht einmal planbar. **Mit der
Nahekorrektur (S1)** ist die D405-Pose gut (2,4 mm), die Kette greift aber nicht, weil die
Prüfung abbricht: „sicher, aber ohne Griff".

## Die Strategien

- **S0 blind (nur Station):** trägt bis ~5 mm (Glas) bzw. ~5 mm (Teller); ab ~9 mm (Glas,
  halbe Fingerbreite) bzw. ~6 mm (Teller, Greifpunkt) mechanisch außerhalb. Bei 2 cm/15°
  **fällt der Griff aus** (0/16 bzw. 0/16) — physikalisch bestätigt.
- **S1 Nahekorrektur (D405):** **heilt die Lage vollständig** (Glas 1,2–1,6 mm bei jedem
  Drift; Teller 3 mm), die **Drehlage des Tellers nicht** (Gier bleibt der Stationsfehler).
- **S2 Fusion (Ensenso ⊕ D405, invers-varianz-gewichtet):** verschlechtert den Restfehler
  gegenüber S1 (Glas 3,0 statt 1,4 mm, Teller 7,0 statt 4,4 mm), weil der Stationsfehler ein
  *systematischer* Bias ist: die Fusion zieht die gute D405-Pose zur falschen Station zurück.
  Gegen **Rauschen** senkt sie σ (2,0 mm ⊕ 1,3 mm → 1,09 mm), gegen einen Bias nicht.
- **S3 Kreuzprobe/Misstrauensregel:** **erkennt den Fehler zuverlässig** — kein Fehlalarm bei
  0 mm (0/16), 100 % bei 2 cm und bei 15° Gier. Nur die heute gewählte Reaktion *Abbruch*
  wirft den geheilten Griff weg. „Neu hinsehen" statt „abbruch" nutzt dieselbe Information.
- **S4 Greifer als Toleranz:** mechanisch geschluckt werden Glas **≤ 9 mm** (halbe
  Fingerbreite 18 mm, V-Kontur) und Teller **≤ 7,7° Gier** (Kerbengrenze, 60-mm-Backe) bzw.
  ≤ ~6 mm Greifpunktversatz (Annahme). Ein 2-cm-Versatz liegt darüber, eine 5-mm-Drehung des
  Tellers nicht.
- **S5 Nachfassen:** der Zweitversuch setzt S1 voraus und gelingt im geprüften Seed ebenso
  (Glas/Teller wie S1); er kostet einen zusätzlichen Anlauf (lösen, neu ansehen, erneut
  anfahren ≈ das Griffsegment der Bahn, beim Glas ~10 s simuliert).
- **S6 Prüfen statt vertrauen:** die Greifweite beim Schließen erkennt einen Fehlgriff —
  im Modell genau dann, wenn der Fehler die mechanische Grenze (S4) übersteigt: **100 %
  Treffer** auf allen S0-Fehlgriffen (48/48 Glas, 100/100 Teller), ohne Fehlalarm bei
  kleinem Fehler. Nach der Ablage bleibt die Prüfung offen (kein Sensor am Ständer).

## Taktzeit

Die D405-Aufnahme sitzt in der Vorposition, die die Bahn ohnehin anfährt — S1 kostet keine
zusätzliche Bewegung (nur eine Punktwolke, ~3–10/s). S3 „neu hinsehen" kostet eine zweite
Stationsaufnahme plus kleines Umpositionieren. S5 kostet einen vollen zweiten Anlauf
(lösen + anfahren + greifen), beim Glas ~10 s simuliert, beim Teller ~15 s (Transport abort).
Der Newton-Kurzlauf selbst braucht auf der CPU (8 Kerne) ~5,5 min (Glas) / ~9,5 min (Teller) Wandzeit
— das ist Rechen-, nicht Taktzeit.

## Empfehlung

**Kette: S0 + S1 + S3(neu hinsehen, nicht abbruch) + S6, mit S4 als Freigabegrenze und S5 als
Rückfall.** Konkret:

1. Grobpose von der Station (S0), D405 in der Vorposition schätzt neu (**S1**) — sie trägt
   2 cm und 15° für das Glas, Restfehler ~1,5 mm.
2. Weicht die D405 über der Schwelle von der Station ab (**S3**), **nicht abbrechen**: die
   Station erneut aufnehmen (zweite Ansicht/Achsstellung) und bei weiterem Widerspruch die
   **D405-Pose** nehmen, solange sie die mechanischen Grenzen (S4) und der Plan tragen.
   Für das Glas hebt das die heute 0/16 auf das Niveau der D405 (16/16).
3. **Teller:** die Gier muss von der Station kommen; 15° sind mit der heutigen Prüfung nicht
   heilbar — nötig ist eine **zweite Stationsansicht** (S3) oder eine bessere Kalibrierung,
   damit die Gier unter der Kerbengrenze **7,7°** bleibt. Bis ~5° genügt S1+Platzprüfung.
4. **S6** (Greifweite, Ablageprüfung) als Wächter: er erkennt jeden Fehlgriff, den der Griff
   blind genommen hätte, und löst **S5** aus.

**σ 15°/2 cm sind also nicht blind zu heilen.** Mit der D405 (S1) ist der **Glas**-Griff
heilbar, wenn die Prüfung statt Abbruch „neu hinsehen" macht; beim **Teller** ist die *Lage*
heilbar, die *Drehlage* nicht — dafür ist eine zweite Stationsansicht oder eine genauere
Kalibrierung nötig. Ohne jede Heilung fällt der Griff ab ~6–9 mm aus.

## Grenzen / offen

- Der mechanische Erfolg ist ein **geometrisches Modell** (Fangbereich = halbe Fingerbreite,
  Kerbengrenze je Objekt), keine Physik; es ist an den bekannten Newton-Fällen (kleiner
  Fehler 10/10 bzw. 12/12) verankert. Die **Physik ist nur für die 15°/2-cm-Eckfälle
  stichprobenartig** gerechnet (je ein Seed Glas und Teller), nicht über das ganze Raster.
- Der **Teller-Newton-Lauf bei 20 mm** ist nicht planbar (IK-Weg), nicht „nur schwer": das
  ist als Fehlerbild „Griff nicht planbar" berichtet, nicht als Griff-Fehlschlag.
- σ je Kamera ist der Mittelwert der eigenen Wahrnehmungsreihe (kein Datenblatt); die Fusion
  nimmt eine Achse als so unsicher wie die andere an.
- Der Stations-Raycast läuft weiter mit dem B57-Modell (`wahrnehmung/strahlen.py`); die
  σ-Gewichte der Fusion sind nicht davon abhängig, das Sichtfeld schon.
