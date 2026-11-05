# Mechanik-Prior-Kette, „neu hinsehen“, Zielverwechslung (Kameratag P2)

Baut auf `docs/griff-robustheit.md` (Posefehler der Station, σ 15° / 2 cm) und `docs/griff-verrauscht.md`
auf. Alles hier ist **Wahrnehmungsmodell** (CPU, Raycast C57-6-S, wahre Segmentmaske) mit dem
**geometrischen** Erfolgsmaß aus `robustheit.erfolg_mechanisch` (Glas Fangbereich 9 mm; Teller Kerbe 7,66° und
Greifpunkt ≤ 6 mm). Physik (Newton) ist **nicht** gerechnet, siehe „Newton“. S6 bleibt unbewertet.

| Teil | Datei |
|---|---|
| A „neu hinsehen“ (`neu_hinsehen=`), B Prior (`prior=`), Prior-Annahmen `PRIOR_STANDARD` | `wahrnehmung/griffpose.py`, `wahrnehmung/robustheit.py` |
| Welt weicht vom Prior ab (`skala_xy`, `skala_dreh`) | `scripts/griff_lauf.py: abweichung` |
| Läufe (672 Zeilen, 16 Seeds) und Auswertung | `scripts/griff_prior.py`, `scripts/griff_prior_auswerten.py` |
| Newton-Schalter `--neu-hinsehen`, `--prior`, `--gier-wahr` | `scripts/griff_lauf.py` |
| Tests | `tests/test_prior.py` |

Standard (kein Schalter) ist bitgleich zu vorher: SHA-256 des gesamten Schätzer-Dicts, 6 Fälle, gleich zu `main`.

## Was gebaut ist

- **Kette (heute):** Abbruch bei jedem Grund (Kreuzprobe Station↔D405 über 6 mm Glas / 8 mm Teller, Nennlage-Check
  `soll_tol_m` 15 mm, Schätzer lehnt ab).
- **A neu hinsehen:** Widerspruch allein bricht nicht ab; die D405-Pose zählt, solange sie im Plan liegt
  (`soll_tol_m`) und der Schätzer sie annimmt. Die Entscheidung nutzt nur beobachtbare Größen; ob die Pose im
  Fangbereich liegt, steht erst in der Auswertung (gegen die Wahrheit). Eine zweite Stationsaufnahme ist nicht gebaut:
  der Fehler ist ein Bias (Kalibrierung), eine zweite Aufnahme wiederholt ihn und mittelt nur das Rauschen.
- **B Mechanik-Prior:** Lage kommt aus der Mechanik: Nennlage ± Toleranz (Glas ±5 mm je Achse; Teller x/y/z ±5 mm,
  Gier ±1°; Annahmen aus `docs/griff-verrauscht.md`, ungetestet; Teller-z ±5 mm ist eine zusätzliche Annahme). Station und
  D405-Pose werden darauf beschnitten; die D405 sieht von der beschnittenen Vorposition (beim Teller mit der
  Prior-Normalen, also ohne die Stations-Gier). Plausibilität: D405 gegen Prior ± 3σ (`prior_widerspruch`,
  Glas 8,9 mm, Teller 14,6 mm je Achse). Die Kreuzprobe Station↔D405 entfällt als Abbruchgrund. Der Gier-Alarm
  (Station > 2° vom Prior) wird nur gezählt, nicht als Abbruch genutzt: bei einer Station mit 15° Fehler schlüge er
  immer an.
- **N0 (Nennlage blind):** nur der Prior, keine Kamera; Maß dafür, was die Kamera überhaupt noch beiträgt.

Zählweise (je Seed): *erfolg* = nicht abgebrochen und mechanisch ok; *Abbruch (Fehlalarm)* = Kette bricht ab, die eigene
Pose wäre ok gewesen; *unbemerkt* = nicht abgebrochen, aber nicht ok. Der Gier-Fehler wird hier gegen die **wahre** Gier
gerechnet (in `docs/griff-robustheit.md` gegen 0°).

## A, B gegen S0/S1/S2/Kette: Raster, Prior stimmt (16 Seeds je Zeile)

Auszug; alle 11 Zeilen je Objekt, Restfehler und Streuung in den Rohdaten.

**Glas** (Drehung ändert nichts: 0°/5°/15° sind zeilengleich)

| Fehler | N0 ok | S0 ok | S1 ok | S2 ok | Kette erfolg | Kette Abbruch (Fehlalarm) | A erfolg | A Abbruch | B erfolg |
|---|---|---|---|---|---|---|---|---|---|
| 0 mm | 16 | 16 | 16 | 16 | 16 | 0 | 16 | 0 | 16 |
| 5 mm | 16 | 16 | 16 | 16 | 11 | 5 (5) | 16 | 0 | 16 |
| 20 mm | 16 | 0 | 16 | 16 | 0 | 16 (16) | 16 | 0 | 16 |
| σ frei | 16 | 0 | 15 | 13 | 0 | 16 (15) | 15 | 1 (0) | 16 |
| σ hart | 16 | 0 | 16 | 16 | 0 | 16 (16) | 16 | 0 | 16 |

**Teller**

| Fehler | N0 ok | S0 ok | S1 ok | S2 ok | Kette erfolg | Kette Abbruch (Fehlalarm) | A erfolg | A Abbruch | A unbemerkt | B erfolg |
|---|---|---|---|---|---|---|---|---|---|---|
| 0° / 0 mm | 15 | 15 | 16 | 16 | 16 | 0 | 16 | 0 | 0 | 16 |
| 5° / 5 mm | 15 | 7 | 16 | 13 | 16 | 0 | 16 | 0 | 0 | 16 |
| 15° / 0 mm | 15 | 0 | 0 | 0 | 0 | 16 (0) | 0 | 16 | 0 | 16 |
| 0° / 20 mm | 15 | 0 | 5 | 0 | 0 | 16 (5) | 5 | 1 (0) | **10** | 16 |
| 15° / 20 mm | 15 | 0 | 0 | 0 | 0 | 16 (0) | 0 | 16 | 0 | 16 |
| σ frei | 15 | 0 | 3 | 0 | 0 | 16 (3) | 3 | 10 | **3** | 16 |
| σ hart | 15 | 0 | 6 | 0 | 0 | 16 (6) | 6 | 8 | **2** | 16 |

Was daraus folgt (Modell):

- **Glas:** A holt die 16/16 zurück, die die Kette wegwirft (20 mm: 0 → 16; 5 mm: 11 → 16), ohne dass ein
  Fehlgriff durchrutscht (0 unbemerkt in allen Glas-Zeilen). B schafft dasselbe — aber **N0 sagt, dass bei stimmendem
  Prior schon die Nennlage allein reicht** (16/16, Max 6,0 mm gegen 9 mm Fangbereich): der Gewinn der Kamera liegt
  hier fast nur darin, einen Prior zu erkennen, der nicht stimmt.
- **Teller, A ist riskant:** bei 20 mm Versatz nimmt A in 10/16 (0° und 5°) die D405-Pose, obwohl sie außerhalb des
  Greifpunktlimits liegt (D405-Restfehler im Mittel 7,0 mm, Max 12,5 mm; die Gier bleibt Stationsfehler). Der
  Plan-Check (15 mm) sieht das nicht. A ist für den Teller kein Ersatz für die Kreuzprobe.
- **Teller, B** trägt in allen 11 Zeilen 16/16 (Restfehler Mittel 2,8–3,2 mm, Max ≤ 5,6 mm; Gier-Fehler Max 1,8°). Das gilt
  **nur, wenn der Prior stimmt**; gegenüber S1 (3–6/16 bei σ) ist der Gewinn die Gier und die Lage aus der Mechanik, nicht
  aus den Kameras (N0 trägt 15/16 für sich).

## Fehlalarmrate der Kreuzprobe bei 0 / 5 mm (S0 greift noch; n = 16, Wilson 95 %)

| Objekt | Fehler | S0 greift | Kreuzprobe schlägt an (Fehlalarm) | Kette-Abbruch-Fehlalarm | A | B |
|---|---|---|---|---|---|---|
| Glas | 0 mm | 16 | 0/16 (0–19 %) | 0/16 | 0/16 | 0/16 |
| Glas | 5 mm | 16 | **5/16 (14–56 %)** | 5/16 | 0/16 | 0/16 |
| Teller | 0 mm (0°, 5°) | 15 | 0/15 (0–20 %) | 0/15 | 0/15 | 0/15 |
| Teller | 5 mm (0°, 5°) | 7 | 0/7 (0–35 %) | 0/7 | 0/7 | 0/7 |

Der Glas-Fehlalarm (5/16 mit der C57-6-S, in `griff-robustheit.md` stand 7/16 mit dem alten Sichtfeld) ist die Lücke, die A
schließt. Beim Teller sind bei 5 mm nur 7 Seeds blind greifbar; 0/7 ist wegen der kleinen Zahl schwach (obere Grenze 35 %).

## B, wenn der Prior selbst daneben liegt (σ 15° / 2 cm, 16 Seeds je Zeile)

Die **Welt** wird um das k-Fache aufgeweitet (Versatz ×k, Drehung/Gier ×m), der Prior bleibt bei ±5 mm / ±1° / ±3°.
σ frei und hart; Spalte „B …“ jeweils σ frei / σ hart.

**Glas** (Versatz ±5 mm × k; Drehung irrelevant)

| Welt | N0 ok | S1 ok | A erfolg | B erfolg | B Abbruch (davon Fehlalarm) | B unbemerkt | D405 widerspricht Prior (von 32) |
|---|---|---|---|---|---|---|---|
| ×1 (±5 mm, Prior stimmt) | 16 | 15 / 16 | 15 / 16 | 16 / 16 | 0 | 0 | 0 |
| ×2 (±10 mm) | 11 | 15 / 16 | 15 / 16 | 11 / 11 | 5 (5) / 5 (5) | 0 | 10 |
| ×3 (±15 mm) | 5 | 15 / 16 | 13 / 13 | 6 / 6 | 10 (6) / 10 (6) | 0 | 20 |

**Teller**

| Welt | N0 ok | S1 ok | A erfolg / unbemerkt | B erfolg | B Abbruch | B unbemerkt | Gier-Fehler B Mittel / Max |
|---|---|---|---|---|---|---|---|
| ×1 (xy ±5 mm, Gier ±1°) | 15 | 3 / 6 | 3 / 3 und 6 / 2 | 16 / 16 | 0 / 0 | 0 / 0 | 0,8 / 1,8° |
| ×2 (xy ±10 mm, Gier ±2°) | 8 | 4 / 6 | 4 / 3 und 6 / 1 | 15 / 15 | 0 / 0 | 1 / 1 | 0,8 / 2,1° |
| ×3 (xy ±15 mm, Gier ±3°) | 3 | 3 / 6 | 2 / 4 und 5 / 1 | **8 / 8** | 0 / 1 | **8 / 7** | 1,2 / 2,6° |
| nur Gier ×3 (±3°) | 15 | 3 / 6 | 3 / 4 und 6 / 2 | 16 / 16 | 0 / 0 | 0 / 0 | 1,1 / 2,6° |
| nur Gier ×6 (±6°) | 15 | 3 / 5 | 3 / 5 und 5 / 3 | 16 / 16 | 0 / 0 | 0 / 0 | 2,3 / 4,5° |

Was daraus folgt (Modell):

- **Glas:** Bei ±10 mm Welt bricht B in 5/16 ab (alle fünf Abbrüche wären ok gewesen: Fehlalarme), bei ±15 mm in 10/16; 0 unbemerkte
  Fehlgriffe in 96 Läufen (Wilson-Obergrenze 3,8 %). Der Prior-Alarm (D405 > Prior + 8,9 mm) schlägt also an, wenn der Prior
  verletzt ist, kostet aber Griffe, die A noch halten würde (A 13–16/16 in allen Welten). Der Abbruch setzt zwischen 5 mm und
  10 mm ein; zwischen den Messpunkten (z. B. 8 mm) liegt kein Lauf.
- **Teller, nur Gier daneben:** B hält 16/16 auch bei ±6° wahrer Gier (Gier-Fehler nach dem Beschneiden Max 4,5° gegen die
  Modellgrenze 7,66°). Der Gier-Prior lässt im Modell viel Spielraum; die Grenze von 7,66° ist eine Geometrie-Annahme
  (nicht physikalisch belegt, Newton nicht gelaufen). Rechnerisch bricht B ab einer wahren Gier von etwa 1° + 7,66° ≈ 8,7° —
  das ist **nicht gerechnet** (größte gerechnete Welt: ±6°).
- **Teller, Lage (x/y) daneben:** Das ist die Schwachstelle. Bei ±15 mm trägt B nur noch 8/16 und **8/16 bzw. 7/16 Fehlgriffe
  bleiben unbemerkt**: der Plausibilitätsband des Teller-D405 (5 + 3 × 3,2 mm = 14,6 mm) ist zu weit, der Alarm kommt in
  1 von 32 Läufen. Bei ±10 mm ist es 1/16 unbemerkt. Wer den Prior-Alarm beim Teller nutzen will, muss ihn enger legen
  (nicht gerechnet).
- Gier-Alarm (Station weicht > 2° vom Prior ab): 18–26 von 32 Läufen je Welt, weil die gezogene Stationsdrehung ihn
  auslöst, nicht der Prior. Er taugt nicht als Abbruch (s. o.).

## Zielverwechslung (C): Nachbarmaske für beide Kameras

Beide Kameras bekommen dieselbe falsche Maske (`negativ='nachbar'`; `zwei_glaeser` / `teller_doppelt` = Ziel + Nachbar
in einer Maske). Teilung gemessen: Glas 101 mm, Teller 60 mm. 16 Seeds × 2 Drifts (ohne, σ hart) × 2 Masken = 64 Läufe je Objekt.

| Objekt | Schätzer lehnt selbst ab | Nennlage-Check allein | Kreuzprobe | unbemerkt Kette / A / B |
|---|---|---|---|---|
| Glas | 64/64 (alle Läufe) | 0 | 0 | **0 / 0 / 0 von 64** |
| Teller nachbar, ohne Drift | 0/16 | 16/16 | 0/16 | 0 / 0 / 0 |
| Teller nachbar, σ hart | 7/16 | 9/16 | 9/16 | 0 / 0 / 0 |
| Teller doppelt | 32/32 | 0 | 0 | 0 / 0 / 0 |

- **Unbemerkte Verwechslungsrate u (gegeben Nachbarmaske):** 0/64 je Objekt, Wilson-95 %-Obergrenze **5,7 %** (heutige Kette, A
  und B gleich). Bei p = 5 / 10 / 20 % Verwechslungen ist die unbemerkte Fehlgriff-Rate der gesamten Griffe damit höchstens
  p × 5,7 % = 0,3 / 0,6 / 1,1 %. Das ist eine Obergrenze, kein Messwert 0.
- Der Nennlage-Check (`soll_tol_m` 15 mm) liegt weit unter der Teilung (60 mm / 101 mm). Er erkennt die Verwechslung dort,
  wo der Schätzer sie nicht selbst ablehnt (Teller ohne Drift 16/16). Beim Teller mit Drift lehnt zusätzlich die Kreuzprobe
  9/16 ab (die Drift trennt die Kameras); zusammen sind es 16/16.
- **Folge unbemerkter Verwechslungen:** keine beobachtet; das Modell sagt voraus, dass ein Griff auf den Nachbarn den
  Greifpunkt um die Teilung (60 / 101 mm) verfehlt (Fangbereich 9 mm / 6 mm) — also ein Fehlgriff, kein Beinahe-Treffer.
- **Grenze:** beide Kameras sehen *dasselbe* falsche Objekt, das Nachbarobjekt steht an seinem Nennplatz. Ein leerer
  Nachbarplatz, eine Maske auf dem Falschen mit anderer Pose, oder zwei verschiedene Verwechslungen je Kamera sind nicht
  modelliert; die reale Verwechslungsrate p kommt aus P3 (Isaac-Renders), nicht von hier.

## Newton (Teil D): nicht gelaufen

Die Newton-Eckfälle (Glas 20 mm/15° mit A; Teller Gier 3° und 7° mit B; Teller 20 mm mit B; Kontrollen) sind **nicht**
gerechnet. Schalter und Auftrag sind vorbereitet (`--neu-hinsehen`, `--prior`, `--gier-wahr`); der Start auf der GPU-Box
wurde von der Umgebung nicht freigegeben. Alle Aussagen oben zur Mechanik (Fangbereich 9 mm, Kerbe 7,66°, Greifpunkt
6 mm) sind **Modell**; die Frage, ob 6° Gierfehler des Prior-Tellers physikalisch hält, ist offen. Wahrnehmung-Vorprüfung der
Eckfälle (ohne Physik): Glas 20 mm/15° mit A ok (0,37 mm), mit B ok (1,1 mm); Teller Gier 7° mit B ok (3,9 mm, Gier 1,0°
geplant gegen 7° wahr = 6° Fehler); Teller 20 mm mit B ok (4,0 mm), ohne Schalter Abbruch (Widerspruch).

## Vorhersagen für den Katalog (P5), mit Unsicherheit

16 Seeds: eine 16/16-Zeile trägt nur eine Wilson-Untergrenze von 81 %. Alle Zahlen sind Modell.

| Zeile | Vorhersage aus diesem Lauf | Band / Grenze | Konsequenz bei Versagen |
|---|---|---|---|
| 9 Teller-Gier im Ständer (Vorhersage ±1°, Schwelle ≤ 2°) | B trägt 16/16 bei wahrer Gier ±1°, ±3° und ±6° (Gier-Fehler Max 1,8° / 2,6° / 4,5°), also mit Spielraum zur Schwelle; Modellgrenze erst bei ≈ 8,7° (1° Prior + 7,66° Kerbe, nicht gerechnet) | Wilson ≥ 81 % je Zeile; 7,66° nicht physikalisch belegt | Gier > 8° messen → Prior-Kette verwerfen. Ohne Prior: S1 hält bei 5° Stationsdrehung (16/16), bei ≥ 15° 0/16 |
| 10 Glaslage (Vorhersage ±5 mm / ±3°, Schwelle ≤ 8 mm) | N0 allein 16/16 (±5 mm), 11/16 (±10 mm), 5/16 (±15 mm). B: 16/16 bei ±5 mm; bei ±10 mm 11 erfolg + 5 Fehlalarm-Abbrüche; bei ±15 mm 6 erfolg + 10 Abbrüche; **0 unbemerkt in 96 Läufen** | Plausibilitätsband 8,9 mm; zwischen 5 und 10 mm nicht gemessen | Lage > 8 mm: B-Abbrüche häufen sich → A (neu hinsehen, trägt 13–16/16 in allen Welten) oder S1 |
| 10 Tellerlage x/y (Annahme ±5 mm) | B: 16/16 bei ±5 mm, 15/16 bei ±10 mm, **8/16 mit 7–8 unbemerkten Fehlgriffen bei ±15 mm** | Teller-Alarmband 14,6 mm zu weit | Lage > 10 mm: Prior-Kette beim Teller nicht ohne engeren Alarm einsetzen |
| 6 Erkennung / Nachbarverwechslung | unbemerkte Verwechslung 0/64 (Glas), 0/64 (Teller): u ≤ 5,7 % (95 %); bei p = 20 % höchstens 1,1 % unbemerkte Fehlgriffe | nur „beide Kameras, dasselbe falsche Nachbarobjekt, wahre Maske sonst“ | Trefferquote und Verwechslungsrate p kommen aus P3 |

## Grenzen

- Mechanisches Maß = Geometrie (Fangbereich 9 mm, Kerbe 7,66°, Greifpunkt 6 mm), keine Physik; Newton nicht gelaufen.
- Prior-Annahmen (Glas ±5 mm/±3°, Teller xy ±5 mm, Gier ±1°, Teller-z ±5 mm) sind ungetestet; Kameratag-Zeilen 9/10 prüfen sie.
- B ist durch die Toleranz nach oben begrenzt: das Beschneiden macht Fehler der Kamera unschädlich, aber auch jede Abweichung
  der Welt außerhalb der Box zum Fehler; der Erfolg bei stimmendem Prior ist deshalb zum Teil Konstruktion, N0 zeigt den
  Anteil des Priors allein.
- Drift bleibt Versatz + Drehung um die Objektmitte (siehe `griff-robustheit.md`, Obergrenze). Die Maske ist wahr, außer in C.
- 16 Seeds je Zeile: Differenzen von 1–2 Läufen sind kein Beleg.
- S5 ist eine Schätzung, S6 nicht bewertet.
