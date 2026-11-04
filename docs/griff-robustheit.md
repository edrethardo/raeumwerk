# Griffrobustheit bei Posefehler der Station (Raster bis 15° / 20 mm, Gauss σ 15° / 2 cm)

Was passiert, wenn die *geschätzte* Objektpose streut, so wie es nach Kalibrierung,
Nachjustage und bei transparentem, nassem Geschirr der realistische Fall ist – und welche
Heilungsstrategien den Griff trotzdem sitzen lassen. Baut auf `docs/griff-verrauscht.md`
auf (dort der Fall *kleiner* Fehler); Aufbau, Objekte und Sensorik sind dieselben.

**Stand und Gültigkeit:** gerechnet ist die *Wahrnehmung* (Raster und Gauss) mit dem alten
B57-Sichtfeld des Raycasts (siehe „Grenzen"); die Newton-Läufe sind **Einzelfälle**. S5 und S6
sind **nicht gerechnet**, nur Entwurf. Die Ergebnisse sind nach der Umstellung auf das
C57-6-S-Sichtfeld neu zu rechnen.

| Teil | Datei |
|---|---|
| Fehlermodell, Kalibrierfehler | `wahrnehmung/sensor.py` |
| Drift der Schätzung, Fusion, mechanische Grenzen | `wahrnehmung/robustheit.py` |
| Ablauf Ensenso → D405 → Prüfung (`posedrift`) | `wahrnehmung/griffpose.py` |
| Raster und Gauss-σ, S0…S3 (Wahrnehmung allein) | `scripts/griff_robustheit.py` |
| Auswertung zu Tabellen | `scripts/griff_robustheit_auswerten.py` |
| Newton-Lauf, Strategie S0/S1 | `scripts/griff_lauf.py` (`--posedrift`, `--strategie`) |
| Tests | `tests/test_robustheit.py` |

## Fehlermodell

Der Fehler wird auf die **Station (Ensenso)** gelegt — die Pose, die die Grobpose liefert —,
nicht auf die Wahrheit: simuliert wird weiter in der wahren Welt
(`griffpose.schaetzen(..., posedrift=)`). Die D405 am Handgelenk sieht das Ziel in ihrer
(dann falschen) Vorposition **unabhängig neu**; genau das ist der Hebel. Ein Betrag von
0 mm / 0° ist bitgleich zum Lauf ohne Drift (`test_griffpose_posedrift_null_aendert_nichts`
für das Glas, `test_griffpose_teller_posedrift_null_aendert_nichts` für den Teller inklusive
Gier-Neuberechnung).

- **Raster:** Drehung {0; 5; 15}°, Versatz {0; 5; 20} mm, je 16 Seeds, Glas (Platz 5) und
  vorderster Dessertteller. Fester Betrag, zufällige Richtung (`drift_fest`); der Versatz
  liegt waagerecht (die Kalibrierung wirkt vor allem seitlich), beim Teller dreht der Fehler
  um die Hochachse (die wirksame Drehlage ist die Gier).
- **Gauss-σ-Varianten** (`robustheit.drift`, 16 Seeds): Versatz 3D, je Achse N(0; 2 cm); Drehwinkel
  N(0; 15°) um eine zufällige Achse. **σ frei**: ohne Kappung. **σ hart**: dieselbe Ziehung
  (gleicher Seed), gekappt auf |Δp| ≤ 2 cm und |ΔR| ≤ 30°. Gezogen (16 Seeds): frei Versatz
  Mittel 28,1 mm / Max 52,5 mm, Drehung Mittel 12,1° / Max 34,4°; hart 18,8 / 20,0 mm und
  11,8° / 30,0°. Weil Achse und Versatz im Raum liegen, wirkt beim Glas nur die Projektion auf x, y
  (Drehung irrelevant), beim Teller kippt die Drehung die Normale meist, statt nur die Gier zu ändern
  (Gier-Mittel nach S1 nur 1,1–1,4°).
- **σ je Kamera** für die Fusion aus der eigenen Messung (`docs/griff-verrauscht.md`,
  Tabelle „Wahrnehmung allein", Mittel): Ensenso 2,0 mm (Glas) / 3,0 mm (Teller),
  D405 1,3 mm / 3,2 mm.

Reproduzieren (CPU, ohne Newton, ~4–9 s je Schätzung): `scripts/griff_robustheit.py --seeds 16
--out ORDNER` (schreibt `robustheit-glas-alle.json`, `robustheit-teller-alle.json`; `--nur fest|sigma`
teilt das Raster), Tabellen mit `scripts/griff_robustheit_auswerten.py ORDNER`.

## Ergebnis Wahrnehmung (16 Seeds je Zelle)

Spalten: „Mm" sind Restfehler gegen die Wahrheit (Mittel / Max, nur Seeds mit Wert). „ok" =
mechanisch im Fangbereich (S4). „Kette" = ok **und** S3 schlägt nicht an **und** D405 nicht
verworfen — also dass die heutige Kette (Abbruch bei Widerspruch) wirklich greift. „S3 schlägt an"
zählt nur die Kreuzprobe Ensenso ↔ D405 (Toleranz 6 mm Glas / 8 mm Teller); „D405 verworfen"
(D405 nimmt die Schätzung nicht an) ist getrennt gezählt. „Fehlalarm" = S3 schlägt an, obwohl der
blinde Griff S0 mechanisch noch greift.

**Glas.** Drehung ändert nichts (0°, 5°, 15° sind zeilengleich): das Glas ist ein Zylinder,
der Griff liest nur x, y. Der Versatz wirkt voll.

| Fehler | S0 mm (blind) | S1 mm | S2 mm | S0 ok | S1 ok | S2 ok | S1 Kette | S2 Kette | S3 schlägt an | davon Fehlalarm | S0-Fehlgriffe erkannt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 mm | 1,6 / 2,8 | 1,2 / 2,0 | 0,9 / 1,4 | 16 | 16 | 16 | 16 | 16 | 0 | 0 | – |
| 5 mm | 5,3 / 7,7 | 1,5 / 2,3 | 1,7 / 2,7 | 16 | 16 | 16 | **9** | 9 | 7 | **7** | – |
| 20 mm | 20,2 / 22,7 | 1,6 / 3,8 | 6,5 / 8,5 | 0 | 16 | 16 | 0 | 0 | 16 | 0 | 16/16 |
| σ 15°/2 cm, **frei** | 23,7 / 51,4 | 1,3 / 2,4 | 6,4 / 9,8 | 0 | 14 | 12 | 0 | 0 | 14 | 0 | 16/16 |
| σ 15°/2 cm, **hart** | 15,8 / 22,6 | 1,0 / 2,1 | 4,6 / 5,7 | 0 | 16 | 16 | 0 | 0 | 16 | 0 | 16/16 |

(Bei σ frei verwirft die D405 zwei Seeds, die in „S3 schlägt an" nicht stehen; die 16/16 „erkannt"
zählen sie mit. S1 ok 14 statt 16 sind genau diese zwei.)

**S1 heilt das Glas bis 2 cm Versatz:** Restfehler 1,2 / 1,5 / 1,6 mm im Mittel (0 / 5 / 20 mm),
Max 2,0 / 2,3 / 3,8 mm, also bei den Rasterfällen und σ hart immer im mechanischen Fangbereich
(Grenze 9 mm). Der Restfehler **wächst mit dem Drift leicht** (Mittel 1,2 → 1,6 mm), er ist nicht
driftunabhängig. Bei σ frei (Versatz bis 52 mm) bleibt S1 im Mittel bei 1,3 mm, aber 2/16 Seeds
verwirft die D405 (Ursache nicht untersucht).
„Kette" bricht trotzdem fast überall ab: bei 20 mm schlägt die Kreuzprobe **jedes Mal** an,
obwohl die D405-Pose 2 mm gut ist.

**S3 hat Fehlalarme.** Bei 5 mm Versatz greift der blinde Griff S0 in 16/16, die Kreuzprobe
schlägt aber in 7/16 an (Toleranz 6 mm bei 5,3 mm mittlerem S0-Fehler, Streuung beider Kameras) →
mit „Abbruch" sinkt die Kette S1/S2 auf 9/16. „Kein Fehlalarm" gilt nur bei 0 mm.

**Teller.** Die Drehung zählt (Gier); bei 15° Gier verwirft die D405 die Schätzung (Normale
weicht ab) → die ganze Kette bricht ab.

| Fehler | S0 mm | S1 mm | S2 mm | S1 Gier ° | S0 ok | S1 ok | S2 ok | D405 verworfen | S1 Kette | S2 Kette | S3 schlägt an | davon Fehlalarm | S0-Fehlgriffe erkannt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0° / 0 mm | 3,0 / 5,8 | 3,3 / 5,3 | 2,5 / 4,7 | 0,1 | 16 | 16 | 16 | 0 | 16 | 16 | 0 | 0 | – |
| 0° / 5 mm | 6,9 / 9,3 | 3,0 / 4,7 | 4,7 / 6,3 | 0,1 | **6** | 16 | 15 | 0 | 15 | 14 | 1 | 0 | **1/10** |
| 0° / 20 mm | 21,5 / 24,3 | 6,9 / 10,6 | 13,9 / 17,6 | 0,1 | 0 | **6** | 0 | 0 | 0 | 0 | 16 | 0 | 16/16 |
| 5° / 0 mm | 3,0 / 5,8 | 3,3 / 5,2 | 2,5 / 4,6 | **5,1** | 16 | 16 | 16 | 0 | 16 | 16 | 0 | 0 | – |
| 5° / 5 mm | 6,9 / 9,3 | 3,0 / 4,7 | 4,7 / 6,4 | **5,1** | 6 | 16 | 15 | 0 | 15 | 14 | 1 | 0 | 1/10 |
| 5° / 20 mm | 21,5 / 24,3 | 7,0 / 10,8 | 14,0 / 17,6 | **5,1** | 0 | **5** | 0 | 0 | 0 | 0 | 16 | 0 | 16/16 |
| 15° / 0 mm | 3,0 / 5,8 | – | – | – | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 16/16 (nur verworfen) |
| 15° / 5 mm | 6,9 / 9,3 | – | – | – | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 16/16 (nur verworfen) |
| 15° / 20 mm | 21,5 / 24,3 | – | – | – | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 16/16 (nur verworfen) |
| σ 15°/2 cm, **frei** | 29,5 / 55,2 | 9,9 / 22,7 | 20,1 / 39,0 | 1,4 | 0 | 3 | 0 | 8 | 0 | 0 | 8 | 0 | 16/16 |
| σ 15°/2 cm, **hart** | 20,1 / 23,2 | 6,2 / 10,2 | 12,4 / 16,5 | 1,1 | 0 | 5 | 0 | 7 | 0 | 0 | 9 | 0 | 16/16 |

(„S1 ok" beim Teller: Gier ≤ 7,66° **und** Greifpunktversatz ≤ 6 mm. S1-Gier-Mittel nur über die
Seeds mit D405-Wert.)

**S1 beim Teller:** bis 5 mm Versatz Restfehler 3,0–3,3 mm (Max 5,3 mm), alle Seeds im Greifpunktlimit.
**Bei 2 cm heilt S1 den Teller nicht:** Mittel 6,9 mm (0°) bzw. 7,0 mm (5°), Max 10,6 / 10,8 mm,
nur 6/16 (0°) bzw. 5/16 (5°) im Greifpunktlimit 6 mm. Unter Gauss-σ nimmt die D405 bei 7–8 von 16
Seeds die Schätzung nicht an, 3 (frei) bzw. 5 (hart) von 16 sind im Limit. Die D405 sieht nur einen
dünnen Randbogen; die *Drehlage* (Gier) kommt von der Station und bleibt deren Fehler (bei 5° Drift
5,1°). Ab 15° Gier liegt der Fehler über der Kerbengrenze von **7,66°** (S4) — und die D405 verwirft
die Schätzung ganz.

**S3 beim Teller:** bei 5 mm erkennt die Kreuzprobe nur **1 von 10** blinden Fehlgriffen (Toleranz 8 mm
über dem 6,9 mm mittleren Fehler). In den 15°-Zeilen steht „erkannt" 16/16 **nur**, weil jede
verworfene D405-Schätzung als erkannt zählt, nicht weil die Kreuzprobe etwas sieht.

## Ergebnis Newton (Einzelfälle, CPU, 8 Kerne)

Je Lauf ein Objekt, Kurzlauf bis Aushub (Glas) bzw. erste Querfahrt zum Ständer (Teller),
Griffpose aus der gestörten Wahrnehmung. Laufzeit Kurzlauf Glas ~327 s, Teller ~566 s.
Reproduzieren: `scripts/griff_lauf.py --art glas|teller --seed 1 --wahrnehmung
[--posedrift T_MM,R_GRAD --strategie s0|s1] --device cpu --out ORDNER`.

| Lauf | Wahrnehmung | Ergebnis | Aushub | Hand | Finger | Gründe |
|---|---|---|---|---|---|---|
| Glas S1, kein Drift (Smoke-Lauf, `smoke.log`) | ok, 0,6 mm | Erfolg | 149 mm | 0,7 mm | 1,2 mm | – |
| Glas S0, 20 mm/15° | Widerspruch, „blind" 18,5 mm | **Planfehler, kein Greifversuch** | – | – | – | „Griff im Korb nicht planbar" |
| Glas S1, 20 mm/15° | Widerspruch, D405 2,4 mm | Abbruch | – | – | – | sicherer Abbruch, kein Griff |
| Teller S1, kein Drift | ok, 4,0 mm | Erfolg | 200 mm | 4,2 mm | 2,2 mm | – |
| Teller S0, 10 mm/10° | „blind" Wahrnehmung 13,7 mm | **Fehlgriff** | 0,7 mm | 467 mm | 4,6 mm | nicht_aus_dem_korb, gefallen_oder_gerutscht, durchdringung |
| Teller S1, 10 mm/10° | Normale weicht ab (`normale_weicht_ab`) | Abbruch | – | – | – | sicherer Abbruch, kein Griff |

Was die Läufe belegen und was nicht:

- Teller S0 bei 10 mm/10° ist ein **gerechneter Fehlgriff** (der Teller fällt, Finger 4,6 mm über der
  3-mm-Grenze). Der „14 mm"-Wert ist die **Wahrnehmung** (13,7 mm), nicht der Griffversatz.
- Teller S1 bricht schon bei **10°** ab (`normale_weicht_ab`), nicht erst ab 15°.
- Glas S0 bei 20 mm/15° endet als **Planfehler ohne Greifversuch**; das ist keine physikalische
  Bestätigung eines Fehlgriffs, nur dass der Fall nicht planbar ist. Eine Physik-Bestätigung der
  Raster-Eckfälle (Teller 20 mm/15°, Glas Greifversuch) gibt es nicht; Läufe sind je ein Seed.
- Die Glas-Zeile „kein Drift, 149 mm" stammt aus dem Smoke-Lauf (`smoke.log`), nicht aus einer
  eigenen Newton-Reihe.

## Die Strategien

- **S0 blind (nur Station):** Glas 16/16 bei 0 und 5 mm, 0/16 bei 20 mm (Grenze 9 mm, halbe
  Fingerbreite). Teller 16/16 ohne Drift (S0-Fehler dort 3,0 mm), nur **6/16 bei 5 mm** Versatz
  (Greifpunktlimit ~6 mm) — S0 trägt den Teller also nur ohne nennenswerten Drift; bei 15° Gier 0/16.
- **S1 Nahekorrektur (D405):** **Glas bis 2 cm geheilt** (Restfehler ≤ 3,8 mm, Grenze 9 mm; leicht
  wachsend mit dem Drift, 1,2 → 1,6 mm). **Teller nur bis ~5 mm** (3,0–3,3 mm); bei 2 cm 6,9 mm und
  nur 5–6 von 16 im Limit; die Drehlage (Gier) bleibt der Stationsfehler, ab 15° verwirft die D405.
- **S2 Fusion (Ensenso ⊕ D405, invers-varianz-gewichtet 0,30 / 0,70):** schlechter als S1 bei Drift
  (Glas 6,5 statt 1,6 mm, Teller 13,9 statt 6,9 mm bei 20 mm), weil der Stationsfehler ein *Bias* ist
  und die naive Gewichtung ihn nicht kennt (bias-blind): sie zieht die gute D405-Pose zur falschen
  Station zurück. Mit S3-Gating (Ensenso aus der Fusion nehmen, wenn die Kreuzprobe anschlägt) oder einem
  größeren σ für die Ensenso wäre S2 nicht schlechter als S1 — nicht gerechnet. Gegen *Rauschen* senkt
  die Fusion σ (2,0 ⊕ 1,3 → 1,09 mm).
- **S3 Kreuzprobe/Misstrauensregel:** erkennt **große** Fehler (Glas ≥ 2 cm 16/16, Teller 20 mm 16/16),
  hat aber (a) **Fehlalarme**: Glas 5 mm 7/16 (S0 greift 16/16, die Kette fällt auf 9/16), und
  (b) **Lücken**: Teller 5 mm nur 1 von 10 S0-Fehlgriffen. Kein Fehlalarm nur bei 0 mm. Mit
  „Abbruch" wirft S3 den geheilten Griff weg; „neu hinsehen" ist ein Vorschlag, nicht gerechnet.
- **S4 Greifer als Toleranz:** mechanisch geschluckt werden Glas **≤ 9 mm** (halbe Fingerbreite
  18 mm, V-Kontur) und Teller **≤ 7,66° Gier** (Kerbengrenze `asin(8 mm/2 / 60 mm/2)`, hergeleitet aus
  der Fingergeometrie) bei ≤ ~6 mm Greifpunktversatz (Annahme). Weder der Glas-Fangbereich 9 mm noch die
  Kerbe sind physikalisch belegt.
- **S5 Nachfassen (Schätzung, nicht gerechnet):** der Zweitversuch setzt S1 voraus; er kostet einen
  zusätzlichen Anlauf (lösen, neu ansehen, erneut anfahren). Es gibt keine Rohdaten dazu.
- **S6 Prüfen statt vertrauen (nur Entwurf, nicht bewertet):** Annahme: die Greifweite beim Schließen
  löst bei jedem Griff außerhalb von S4 aus. Das ist eine Setzung, kein Ergebnis — das Modell ist
  tautologisch (erkennt per Definition jeden S0-Fehlgriff), eine Trefferquote wird deshalb nicht
  angegeben. Ob die Greifweite am Kraftsensor-losen Greifer Fehlgriffe zuverlässig trennt, ist offen.
  Die Ablageprüfung am Ständer hat keinen Sensor.

## Taktzeit

Die D405-Aufnahme sitzt in der Vorposition, die die Bahn ohnehin anfährt — S1 kostet keine
zusätzliche Bewegung (nur eine Punktwolke, ~3–10/s). S3 „neu hinsehen" kostet eine zweite
Stationsaufnahme plus kleines Umpositionieren. S5 kostet einen vollen zweiten Anlauf
(lösen + anfahren + greifen); die Zeiten (Glas ~10 s, Teller ~15 s) sind Schätzungen. Der
Newton-Kurzlauf braucht auf der CPU (8 Kerne) ~5,5 min (Glas) / ~9,5 min (Teller) Wandzeit
— das ist Rechen-, nicht Taktzeit.

## Empfehlung (vorläufig)

- **Glas:** S1 (D405 in der Vorposition) ist stark: Restfehler ≤ 3,8 mm bis 2 cm Versatz und
  beliebiger Drehung, im Fangbereich, solange die D405 die Schätzung annimmt (σ frei: 2 von 16
  verworfen). Die heutige Prüfung (Abbruch bei Widerspruch) wirft diesen
  Griff weg (0/16 bei 20 mm) und löst bei 5 mm sogar Fehlalarme aus (7/16). Sinnvoll ist, bei
  Widerspruch die D405-Pose zu nehmen, solange sie den Fangbereich und den Plan trägt, statt
  abzubrechen; „neu hinsehen" statt Abbruch ist eine Option, nicht gerechnet.
- **Teller:** bleibt **offen**. S1 hält nur bis ~5 mm; bei 2 cm liegt der Restfehler im Mittel über dem
  Greifpunktlimit, die Gier kommt von der Station, ab 10° (Newton) bzw. 15° (Wahrnehmung) verwirft die
  D405. Nötig wäre eine bessere Kalibrierung oder eine Gier aus der D405 (nicht nur dünner Randbogen).
- **S3** taugt als Alarm bei großem Fehler, nicht als Entscheidung bei kleinem (Fehlalarme beim Glas,
  Lücken beim Teller).
- **S6** (Greifweite/Ablageprüfung) ist ein Entwurf unter der Annahme, die Greifweite löse jeden Griff
  außerhalb von S4 aus; ohne Messung am Greifer keine Aussage. S5 ist eine Schätzung.

**σ 15°/2 cm sind nicht blind zu heilen.** Beim Glas trägt S1 auch das Gauss-σ (frei: 14/16 im
Fangbereich, 2/16 verwirft die D405), beim Teller nur 3 (frei) bzw. 5 (hart) von 16.

## Grenzen / offen

- Der mechanische Erfolg ist ein **geometrisches Modell** (Fangbereich = halbe Fingerbreite,
  Kerbengrenze je Objekt), keine Physik; Glas-Fangbereich 9 mm und Kerbe sind nicht physikalisch
  belegt. Verankert nur an den bekannten Newton-Fällen mit kleinem Fehler (10/10 bzw. 12/12);
  die Läufe mit Drift sind Einzelfälle (je ein Seed).
- **Wahre Maske für beide Kameras:** die Segmentmaske der D405 (und der Ensenso) kommt aus der
  wahren Szene (`griffpose.py`), der ROI der D405 startet um das *gedriftete* Ensenso-`c` (Radius
  0,15 m). Eine reale Segmentierung kann zusätzlich fehlerhaft sein.
- **Drift ist nur Versatz + Drehung um die Objektmitte** (`wende_an`). Eine Kalibrierdrehung der
  Station wirkt über den Hebelarm (15° bei ~1 m ≈ 25 cm) auch als großer Versatz. „Heilt" ist deshalb eine
  **Obergrenze**.
- **S2 mit naiver Gewichtung** (0,70 D405 / 0,30 Ensenso): bias-blind, siehe oben; ein gegatetes oder
  anders gewichtetes S2 ist ungerechnet.
- **S6 ist im Modell tautologisch**, S5 ohne Beleg in den Rohdaten; beide nicht bewertet.
- Der **Teller-Newton-Lauf bei 20 mm** ist nicht planbar (IK-Weg); das ist als „Griff nicht planbar"
  berichtet, nicht als Griff-Fehlschlag.
- σ je Kamera ist der Mittelwert der eigenen Wahrnehmungsreihe (kein Datenblatt); die Fusion
  nimmt eine Achse als so unsicher wie die andere an.
- Der Stations-**Raycast läuft noch mit dem alten B57-Sichtfeld** (`wahrnehmung/strahlen.py`), nicht mit
  dem C57-6-S. Die Umstellung kommt später; **alle Zahlen sind danach neu zu rechnen**.
- Die Kerben-/Gierzahlen beim Teller zählen S1-Gier aus der Station (`gier_grad` der Ensenso); die D405
  liefert dort keine eigene Gier.
