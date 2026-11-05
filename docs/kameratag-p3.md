# Kameratag P3: synthetische Isaac-Bilder und echte Erkennung (Glas, Teller)

Frage: Findet eine echte Erkennung Gläser und Teller im Ensenso-RGB-Bild des Spülmaschinenkorbs,
verwechselt sie Nachbarn, verpasst sie transparentes Glas — und wie wirkt eine erkannte statt der wahren Maske auf die
Griffpose? Bis dahin bekamen beide Kameras die wahre Objektmaske (`maske_wahr`) mit verrauschtem Rand.

**Alle Zahlen stammen aus Renderbildern von Isaac Sim, nicht aus Aufnahmen der echten Kamera.** Siehe „Grenzen“.

## Aufbau

* **Szenen** (`wahrnehmung/p3_szenen.py`, `scripts/p3_szenen.py`): Spülmaschine aus `config/spuelmaschine.yaml`
  (Korbgitter als Quader), Belegung zufällig aus dem Seed.
  Oberkorb: Gläser kopfüber auf dem Glashalter (Reihen x = 0,48/0,36, Layout „glas“ zusätzlich 0,24; Belegung 65 %),
  Dessertteller Ø 19 cm hochkant in der Tellerreihe x = 0,15 (Layout „teller“ auch x = 0,40; 75 %), Layouts
  gemischt/glas/teller (50/25/25 %). Unterkorb (Oberkorb eingeschoben): Essteller Ø 26 cm (80 %, bis ±8° angelehnt) und in
  der rechten Hälfte entweder Dessertteller oder kopfüber stehende Gläser. 20 % der Teller sind blaues Steingut, der
  Rest weißes Porzellan. Maße von Glas/Teller und die Lagejitter (±4–6 mm, ±1,5–3°) sind Annahmen.
* **Versuchsplan:** je Korb 36 Szenen = Licht (Tag / Küche / dunkel) × Auszug (halb 0,225 m / voll 0,45 m) × nass/trocken,
  je Zelle dreimal mit anderer Belegung. Dazu 6 Tuning-Szenen (`t_*`, Seeds ab 90000), mit denen die Schwellen der
  Baseline eingestellt wurden; sie stehen **nicht** in den Tabellen. Gesamt 72 Auswertungsszenen mit 770 Objekten
  (Oberkorb 155 Gläser + 155 Dessertteller; Unterkorb 115 Gläser + 92 Dessertteller + 253 Essteller). Davon sind 727 mit
  ≥ 1500 sichtbaren Pixeln (Instanzkarte) auswertbar; 43 sind fast ganz verdeckt.
* **Kamera:** Ensenso C57-6-S wie in (Mast 0,55 / 0,50 / 1,35 m, Blick 60° nach unten, f = 2591 / 2381 px,
  2472 × 2064 px; Isaac-Kamera mit gleichen Brennweiten und Aperturen, Pixelraster identisch zum Strahlschnitt).
* **Render:** Isaac Sim 6.2 RTX, `scripts/isaac_p3_render.py` (Aufruf über `scripts/isaac_p3.sh`), je Szene RGB-PNG,
  Tiefe (`uint16` mm) und Instanzkarte (Replicator `instance_id_segmentation`, ein Objekt = eine ID, Glas inklusive
  Tropfen). Glas: OmniGlass (n = 1,5), geschlossener Rotationskörper mit Wand und Boden. Nässe: Tropfen als Geometrie
  (25–60 je Glas, 20–45 je Teller), glattere Teller- und Korboberfläche. Licht: Tag (Kuppel + Sonne + Füllicht),
  Küche (zwei warme Deckenflächen), dunkel (eine kleine Lampe). Mittlere Bildhelligkeit (0–255): Tag 182–194, Küche 86–101,
  dunkel 14–18.
* **Renderer-Entscheidung:** RTX Real-Time zeigt Glas als schwarzen Spiegel (1,4 s/Bild), **Path Tracing** zeigt Brechung
  und Transparenz. Gerendert wurde mit Path Tracing, 8 Samples × 6 Subframes + Denoiser.

## Erkennung

Beide Verfahren sehen nur das RGB-Bild des Korb-Ausschnitts (Ausschnitt aus der projizierten Korbgeometrie, nicht aus dem
Bild). Code: `wahrnehmung/erkennung.py`, `scripts/p3_erkennen.py`.

1. **Klassische Baseline** (Farbe/Kanten, ohne Download): Canny-Kanten, Abgleich mit dem aus Kamerapose und Nennmaßen
   projizierten Umriss (Glasdeckel, Dessert-/Essteller) bei drei Maßstäben, Maximumsuche. Das ist keine
   blinde Suche: die Vorlagen kennen Größe und Blickwinkel. Ohne Tiefe. Score-Schwellen (Glas 0,75, Teller 0,45) an den
   6 Tuning-Szenen eingestellt (bei 0,45 für Glas 17 Fehldetektionen je Bild, bei 0,75 1,3).
2. **Vortrainiertes Instanzmodell:** torchvision Mask R-CNN ResNet-50-FPN v1, COCO-Gewichte. Download und Prüfsumme
   (`scripts/p3_modell_holen.sh`, SHA-256 fest eingetragen), Gewichte liegen außerhalb des Repos
   (`$RAEUMWERK_MODELLE`, Standard `$RAEUMWERK_HOME/modelle`). COCO kennt „wine glass“, „cup“ und „bowl“, aber **keinen Teller**.
   Zuordnung: Glas = wine glass/cup (46, 47), Teller = bowl (51), alles andere „andere“. Plattenähnliche Objekte
   bekommen in den Daten meist andere Klassen (z. B. „surfboard“ 42); deshalb steht die Spalte „klassenfrei“ daneben.
   Score-Schwelle 0,3 (Glas wird nur mit Scores um 0,2–0,6 erkannt); die Tabelle mit 0,5 liegt unter den Rohdaten.
   Kein Feintuning auf den Renderbildern.

**Definitionen** (je Objekt, Instanzkarte als Wahrheit, IoU ≥ 0,5): *Treffer* = Erkennung der richtigen Klasse, die
nicht mehrere Objekte verschmilzt; *klassenfrei* = Erkennung beliebiger Klasse mit IoU ≥ 0,5; *Klassenfehler* = beste
Erkennung hat die falsche Klasse; *Nachbar* = kein Treffer und die Erkennung verschmilzt ≥ 2 Objekte (je ≥ 30 % deren
Fläche) oder liegt mit größerem IoU auf einem anderen Objekt; *ungenau* = bester IoU 0,3–0,5; *verpasst* = kein IoU ≥ 0,3;
*Fehldetektion* = Erkennung, die kein Objekt mit IoU ≥ 0,1 berührt. Das Intervall ist Wilson 95 %. Die Auswertung läuft
auf jedem 4. Pixel (IoU-Fehler < 1 %).

## Anbindung an die Griffpose

`griffpose.schaetzen(..., maske_ensenso=<bool-Maske>)` ersetzt für den Ensenso-Schritt `maske_wahr` (+ Randrauschen)
durch die Maske der Erkennung (beliebiges Raster, wird auf das Strahlraster abgebildet; leere Maske → Abbruch
`ensenso:keine_erkennung`). Die D405 behält die wahre Maske, es gibt kein D405-Bild. Standard bleibt unverändert
(`maske_quelle: wahr`). Tests: `tests/test_p3.py` (synthetische Maske, leere Maske, Rasterabbildung).
`scripts/p3_lage.py` wählt die Erkennung der passenden Klasse, die den Nennort des Ziels (Belegungsplan, gemessener
Korbauszug) enthält oder am nächsten liegt (≤ 0,6 Objektradius); die Wahrheit geht nicht in die Auswahl ein.
Tiefe, Fehlermodell und Pose-Schätzer sind die des Strahlschnitt-Simulators; das Isaac-Tiefenbild fließt **nicht** ein.

## Grenzen (nicht schönreden)

* **Domänenlücke Render ↔ Realität.** Material, Beleuchtung, Glas, Tropfen und Korbgitter sind gerendert; echte Gläser
  (Kalk, Gravur, Henkel, Stiel), echte Teller (Dekor, Rand), Spiegelungen in der Küche, Bildrauschen und Objektivfehler
  fehlen. Wer hier „gut“ ist, ist es in der Realität nicht automatisch; wer hier scheitert, hat dafür wahrscheinlich
  einen Grund, der real ähnlich oder schlimmer ist (dunkle Küche, verschmolzene Teller). Mask R-CNN ist ohne Feintuning
  auf Render-Bildern angewandt.
* **Kein Projektormuster.** Die Ensenso projiziert ein Muster, dessen Wirkung auf das RGB-Bild und die Tiefe nicht
  vorhersagbar ist; es wird nicht simuliert. Auch kein Stereo-Matching: die Punktabdeckung kommt aus dem angenommenen
  Fehlermodell, nicht aus den Isaac-Tiefen. Die Isaac-Tiefe sieht Glas ideal und ist bewusst nicht verwendet.
* **Nässe und Reflexe nur angenähert:** Tropfen als abgeflachte Halbkugeln aus Glas, glattere Oberfläche; kein Wasserfilm,
  kein Dampf, keine Wasserflecken, keine nassen Mehrfachspiegelungen im Gitter.
* **Belegung, Lagejitter und Maße sind Annahmen**; Teller stehen an festen Plätzen in der Reihe, keine freie Lage. Kein
  Besteck, keine Schüsseln, kein Roboterarm im Bild. Eine Szene, ein Blickpunkt (die feste Mastpose).
* Die Baseline nutzt Nennmaße und die Kamerapose; sie ist keine „blinde“ Erkennung. Schwellen kommen von sechs Szenen.
* Unterkorb-Szenen haben den Oberkorb eingeschoben; halber Auszug verdeckt dort viele Plätze (daher die Verpasst-Rate).
* Zwei Gütegrenzen des Pose-Schätzers sind Annahmen aus/1427: Flächen, die flacher als 60° zum Sehstrahl liegen,
  liefern keinen Tiefenwert. Hochkant stehende Teller werden in dieser Mastpose unter 70–80° gesehen; nur 19–29 % der
  Tellerpixel haben dann Tiefe (Diagnose in den Rohdaten), die Ebenenanpassung scheitert.

## Reproduktion

```
scripts/p3_szenen.py --out szenen.json                              # 78 Szenen (72 + 6 Tuning)
scripts/isaac_p3.sh szenen.json lauf --modus pt --spp 8 --subframes 6 --fortsetzen --max-minuten 22   # auf der GPU-Box, unter Lock
scripts/p3_modell_holen.sh                                          # Gewichte + Pruefsumme
scripts/p3_erkennen.py szenen.json <render> --out <erk> --modell <pth> [--verfahren baseline,maskrcnn]
scripts/p3_auswertung.py szenen.json <render> <erk> --out <aus> --schwelle 0.3
scripts/p3_lage.py szenen.json <render> <erk> --out <lage> --quellen wahr,maskrcnn,baseline --schwelle 0.3
scripts/p3_abdeckung.py szenen.json --out <abdeckung>
```
Rohdaten (Bilder, Tiefe, Instanzkarten, Erkennungen, CSV) liegen nicht im Repo.

## Ergebnisse

Gerendert: 78 Szenen in 3 Lock-Stücken (28 + 28 + 22 Szenen), 2472 × 2064, Path Tracing. Render-Schritt je Szene
Median 42,6 s (7–55 s; die erste Szene eines Starts ist kürzer, weil das Einschwingen getrennt zählt), je Szene
inklusive Aufbau Median 48 s, Summe 3 450 s für die 72 Auswertungsszenen; Isaac-Start ca. 10 s. Spitzen: RAM 6 387 MiB,
VRAM 8 803 MiB. Mask R-CNN auf der GPU 0,05–0,08 s je Bild, die Baseline 6–30 s je Bild auf CPU (Rechner belastet).

### Erkennung (Vorhersagezeile 6: Trefferquote, Nachbarverwechslung)

Kernaussagen, alle aus den Tabellen darunter (72 Szenen, 727 auswertbare Objekte, IoU ≥ 0,5):

* **Glas:** Baseline 55 % Treffer (95 %: 49–61), bei Tageslicht 86 % (78–91), Küche 66 % (55–75), **dunkel 0 % (0–5)**.
  Mask R-CNN (COCO, ungetunt) 31 % (26–37), Tag 50 %, Küche 31 %, dunkel 5 %; trifft es, dann genau (Median-IoU 0,95
  gegen 0,80 der Baseline). Nachbarverwechslung 9 % (Baseline) bzw. 10 % (Mask R-CNN), Klassenfehler bei Mask R-CNN 7 %.
  **Transparenz allein ist im Pfadverfolgungs-Bild nicht das Problem (Glas hat Kanten und Brechung), Dunkelheit und
  Verdeckung sind es.** Nass ändert die Baseline kaum (trocken 52 %, nass 61 %: Tropfen liefern Kanten), Mask R-CNN
  wird schlechter (trocken 40 %, nass 18 %).
* **Teller:** Baseline 45 % (41–50), aber 7,2 Fehldetektionen je Bild; Nachbar/Verschmelzung 16 %. Mask R-CNN **0 %
  klassenrichtig** (COCO hat keinen Teller; „bowl“ wird nicht vergeben), klassenfrei 18 % (Dessertteller 27 %,
  Essteller 8 %); bei 56 % der Teller verschmilzt die Erkennung benachbarte Teller der Reihe oder legt sie auf ein
  anderes Objekt. Das ist der Befund zur Nachbarverwechslung: **eng stehende Teller werden nicht getrennt.**
* Halber Auszug ist deutlich schlechter als voller (Baseline Glas 37 % gegen 70 %); die Ursache (Verdeckung, Schatten,
  kleinere Abbildung) wurde nicht getrennt untersucht.
* Vorhersage für den Kameratag, **ausdrücklich nur für diese Render-Domäne**: ein ungetuntes COCO-Modell reicht für
  Gläser und Teller nicht (Glas 31 %, Teller 0 %); ein auf Nennform und Pose zugeschnittener Kantenabgleich erreicht bei
  Licht und vollem Auszug für Glas 70–86 %, nicht im Dunkeln. Plan: Beleuchtung am Kameratag sicherstellen (Tag/Küche
  hell), Erkennung auf Nennort einengen (Suchfenster), Mask R-CNN erst nach Feintuning auf eigenen Bildern.

### Lagefehler mit erkannter statt wahrer Maske

`scripts/p3_lage.py`, bis zu 3 Ziele je Szene (85 Gläser, 131 Teller je Quelle, jeweils dieselben Ziele und Seeds).
„Griff freigegeben“ = alle Plausibilitätsprüfungen von `griffpose.schaetzen` bestanden.

* **Glas, wahre Maske** (bisheriger Stand): 92 % freigegeben, Fehler Median 1,4 mm, P90 2,5 mm.
* **Glas, Baseline-Maske:** 14 % freigegeben (12 von 85), die freigegebenen mit Median 1,5 mm, P90 2,3 mm. Abbrüche:
  keine Erkennung am Nennort 36, Ensenso–D405-Widerspruch 27, Kontur-Inlier gering 10, Modell passt nicht 3.
* **Glas, Mask-R-CNN-Maske:** 6 % freigegeben (5 von 85), Median 1,1 mm; Abbrüche: keine Erkennung 64, Widerspruch 15.
  Dunkel: 0 % bei beiden Erkennungen.
* **Teller: 0 % in allen drei Quellen, auch mit der wahren Maske.** Das liegt am Pose-Schätzer und am Fehlermodell,
  nicht an der Erkennung: hochkant stehende Teller werden in der Mastpose unter 70–80° zur Flächennormale gesehen
  (Grenze 60°); 70–80 % der Tellerpixel haben keinen Tiefenwert (Diagnose: ober_030 teller_3 19 % gültig,
  ober_026 teller_1 29 %), Abbruchgrund meist `ebene_inlier_gering`. Die Tellerzahlen in sind damit mit dieser
  Mastpose in dichter gepackten, verdeckten Szenen nicht haltbar — das ist ein Befund für P4, kein Ergebnis dieses Pakets.
* Wenn die Erkennung ein Glas trifft, ist die Pose so gut wie mit der wahren Maske (1,1–1,5 mm). Die Lücke steckt in
  „gefunden und am richtigen Platz“, nicht in der Genauigkeit.

Die Lagefehler enthalten das angenommene Fehlermodell der Tiefe (Glas 50 % Ausfall, 35 % Durchblick, 15 % Reflex), nicht das
Isaac-Tiefenbild; Nass-Szenen rechnen mit 5 % zusätzlichem Ausfall.

### Tabellen

Tabelle „Baseline“ (Spalten wie oben definiert; „Fehldet./Bild“ = Erkennungen ohne Objekt dahinter je Bild):
### baseline (Score >= 0.0)

| Klasse | Bedingung | n sichtbar | Treffer % (95 %-Intervall) | klassenfrei % | IoU Treffer (Median) | IoU alle (Mittel) | Klassenfehler % | Nachbar % | ungenau % | verpasst % | Fehldet./Bild |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glas | alle | 270 | 55 (49-61) | 56 | 0.80 | 0.45 | 0 | 9 | 3 | 32 | 0.1 |
| glas | Korb ober | 155 | 58 (50-66) | 59 | 0.79 | 0.46 | 1 | 3 | 4 | 34 | 0.2 |
| glas | Korb unter | 115 | 51 (42-60) | 51 | 0.88 | 0.43 | 0 | 17 | 3 | 30 | 0.1 |
| glas | trocken | 166 | 52 (44-59) | 52 | 0.80 | 0.42 | 1 | 10 | 4 | 33 | 0.1 |
| glas | nass | 104 | 61 (51-69) | 61 | 0.82 | 0.49 | 0 | 7 | 2 | 31 | 0.1 |
| glas | Licht tag | 107 | 86 (78-91) | 86 | 0.80 | 0.70 | 0 | 6 | 3 | 6 | 0.3 |
| glas | Licht kueche | 87 | 66 (55-75) | 67 | 0.80 | 0.53 | 1 | 18 | 2 | 13 | 0.1 |
| glas | Licht dunkel | 76 | 0 (0-5) | 0 | nan | 0.00 | 0 | 3 | 5 | 92 | 0.0 |
| glas | Auszug halb | 121 | 37 (29-46) | 38 | 0.78 | 0.30 | 1 | 16 | 4 | 42 | 0.2 |
| glas | Auszug voll | 149 | 70 (62-77) | 70 | 0.82 | 0.57 | 0 | 3 | 3 | 24 | 0.1 |
| teller | alle | 457 | 45 (41-50) | 45 | 0.72 | 0.32 | 0 | 16 | 6 | 32 | 7.2 |
| teller | Korb ober | 155 | 48 (41-56) | 48 | 0.75 | 0.36 | 0 | 12 | 1 | 39 | 5.8 |
| teller | Korb unter | 302 | 44 (38-49) | 44 | 0.70 | 0.30 | 0 | 19 | 9 | 29 | 8.6 |
| teller | trocken | 200 | 47 (40-54) | 47 | 0.72 | 0.34 | 0 | 16 | 6 | 32 | 7.2 |
| teller | nass | 257 | 44 (38-50) | 44 | 0.71 | 0.32 | 0 | 17 | 6 | 33 | 7.2 |
| teller | Licht tag | 150 | 52 (44-60) | 52 | 0.72 | 0.37 | 0 | 22 | 11 | 15 | 10.0 |
| teller | Licht kueche | 150 | 54 (46-62) | 54 | 0.73 | 0.39 | 0 | 12 | 3 | 31 | 8.6 |
| teller | Licht dunkel | 157 | 31 (24-38) | 31 | 0.71 | 0.22 | 0 | 15 | 4 | 50 | 3.0 |
| teller | Auszug halb | 213 | 35 (29-41) | 35 | 0.72 | 0.25 | 0 | 28 | 3 | 34 | 6.5 |
| teller | Auszug voll | 244 | 55 (48-61) | 55 | 0.72 | 0.39 | 0 | 6 | 9 | 31 | 7.9 |
| alle | alle | 727 | 49 (45-53) | 49 | 0.77 | 0.37 | 0 | 13 | 5 | 32 | 7.3 |
| alle | Korb ober | 310 | 53 (48-59) | 54 | 0.77 | 0.41 | 0 | 7 | 2 | 37 | 5.9 |
| alle | Korb unter | 417 | 46 (41-51) | 46 | 0.76 | 0.34 | 0 | 18 | 7 | 29 | 8.7 |
| alle | trocken | 366 | 49 (44-54) | 49 | 0.77 | 0.37 | 0 | 13 | 5 | 32 | 7.3 |
| alle | nass | 361 | 49 (44-54) | 49 | 0.77 | 0.37 | 0 | 14 | 5 | 32 | 7.3 |
| alle | Licht tag | 257 | 66 (60-72) | 66 | 0.77 | 0.50 | 0 | 15 | 7 | 11 | 10.3 |
| alle | Licht kueche | 237 | 58 (52-64) | 59 | 0.77 | 0.44 | 0 | 14 | 3 | 24 | 8.7 |
| alle | Licht dunkel | 233 | 21 (16-26) | 21 | 0.71 | 0.15 | 0 | 11 | 5 | 64 | 3.0 |
| alle | Auszug halb | 334 | 36 (31-41) | 36 | 0.76 | 0.27 | 0 | 24 | 3 | 37 | 6.7 |
| alle | Auszug voll | 393 | 60 (55-65) | 60 | 0.77 | 0.46 | 0 | 5 | 7 | 28 | 8.0 |

Tabelle Mask R-CNN (COCO, Score >= 0,3; Teller = COCO „bowl“, daher Treffer 0 %, siehe Spalte klassenfrei):

### maskrcnn (Score >= 0.3)

| Klasse | Bedingung | n sichtbar | Treffer % (95 %-Intervall) | klassenfrei % | IoU Treffer (Median) | IoU alle (Mittel) | Klassenfehler % | Nachbar % | ungenau % | verpasst % | Fehldet./Bild |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glas | alle | 270 | 31 (26-37) | 38 | 0.95 | 0.35 | 7 | 10 | 0 | 52 | 0.0 |
| glas | Korb ober | 155 | 30 (23-37) | 37 | 0.94 | 0.33 | 8 | 8 | 1 | 54 | 0.0 |
| glas | Korb unter | 115 | 34 (26-43) | 39 | 0.95 | 0.36 | 5 | 12 | 0 | 49 | 0.0 |
| glas | trocken | 166 | 40 (33-47) | 43 | 0.94 | 0.40 | 4 | 6 | 1 | 50 | 0.0 |
| glas | nass | 104 | 18 (12-27) | 30 | 0.96 | 0.26 | 12 | 15 | 0 | 55 | 0.0 |
| glas | Licht tag | 107 | 50 (41-60) | 54 | 0.95 | 0.49 | 4 | 15 | 0 | 31 | 0.0 |
| glas | Licht kueche | 87 | 31 (22-41) | 39 | 0.96 | 0.37 | 8 | 0 | 0 | 61 | 0.0 |
| glas | Licht dunkel | 76 | 5 (2-13) | 14 | 0.86 | 0.11 | 9 | 13 | 1 | 71 | 0.0 |
| glas | Auszug halb | 121 | 26 (19-35) | 30 | 0.94 | 0.27 | 3 | 0 | 1 | 69 | 0.0 |
| glas | Auszug voll | 149 | 36 (28-44) | 45 | 0.95 | 0.40 | 9 | 17 | 0 | 38 | 0.0 |
| teller | alle | 457 | 0 (0-1) | 18 | nan | 0.15 | 18 | 56 | 0 | 26 | 0.0 |
| teller | Korb ober | 155 | 0 (0-2) | 26 | nan | 0.21 | 26 | 43 | 0 | 31 | 0.0 |
| teller | Korb unter | 302 | 0 (0-1) | 14 | nan | 0.11 | 14 | 62 | 0 | 24 | 0.0 |
| teller | trocken | 200 | 0 (0-2) | 20 | nan | 0.16 | 20 | 59 | 0 | 22 | 0.0 |
| teller | nass | 257 | 0 (0-1) | 17 | nan | 0.14 | 17 | 53 | 0 | 30 | 0.0 |
| teller | Licht tag | 150 | 0 (0-2) | 18 | nan | 0.13 | 18 | 69 | 0 | 13 | 0.0 |
| teller | Licht kueche | 150 | 0 (0-2) | 20 | nan | 0.17 | 20 | 57 | 1 | 23 | 0.0 |
| teller | Licht dunkel | 157 | 0 (0-2) | 16 | nan | 0.14 | 16 | 43 | 0 | 41 | 0.0 |
| teller | Auszug halb | 213 | 0 (0-2) | 15 | nan | 0.13 | 15 | 60 | 0 | 25 | 0.0 |
| teller | Auszug voll | 244 | 0 (0-2) | 20 | nan | 0.17 | 20 | 52 | 0 | 27 | 0.0 |
| alle | alle | 727 | 12 (10-14) | 25 | 0.95 | 0.22 | 14 | 39 | 0 | 36 | 0.2 |
| alle | Korb ober | 310 | 15 (11-19) | 32 | 0.94 | 0.27 | 17 | 25 | 0 | 43 | 0.2 |
| alle | Korb unter | 417 | 9 (7-13) | 21 | 0.95 | 0.18 | 12 | 48 | 0 | 30 | 0.1 |
| alle | trocken | 366 | 18 (14-22) | 30 | 0.94 | 0.27 | 12 | 35 | 0 | 34 | 0.1 |
| alle | nass | 361 | 5 (3-8) | 20 | 0.96 | 0.17 | 15 | 42 | 0 | 37 | 0.2 |
| alle | Licht tag | 257 | 21 (16-26) | 33 | 0.95 | 0.28 | 12 | 46 | 0 | 21 | 0.2 |
| alle | Licht kueche | 237 | 11 (8-16) | 27 | 0.96 | 0.24 | 16 | 36 | 0 | 37 | 0.0 |
| alle | Licht dunkel | 233 | 2 (1-4) | 15 | 0.86 | 0.13 | 14 | 33 | 0 | 51 | 0.3 |
| alle | Auszug halb | 334 | 10 (7-13) | 20 | 0.94 | 0.18 | 11 | 38 | 0 | 41 | 0.0 |
| alle | Auszug voll | 393 | 13 (10-17) | 30 | 0.95 | 0.26 | 16 | 39 | 0 | 31 | 0.3 |

Mask R-CNN mit Score >= 0,5 (gleiche Bilder): Glas 22 % (18-28), Teller 0 % (klassenfrei 12 %), alle 8 % (6-10); Fehldetektionen 0,0 je Bild.

### Lagefehler, vollständige Tabelle

| Klasse | Quelle | Bedingung | n | Griff freigegeben % | Fehler Median (mm) | P90 (mm) | Abbruchgruende |
|---|---|---|---:|---:|---:|---:|---|
| glas | baseline | alle | 85 | 14 | 1.5 | 2.3 | keine_erkennung 36, ensenso_d405_widerspruch 27, kontur_inlier_gering 10, modell_passt_nicht 3 |
| glas | baseline | trocken | 56 | 9 | 1.6 | 1.9 | keine_erkennung 26, ensenso_d405_widerspruch 19, kontur_inlier_gering 6, modell_passt_nicht 2 |
| glas | baseline | nass | 29 | 24 | 1.4 | 2.3 | keine_erkennung 10, ensenso_d405_widerspruch 8, kontur_inlier_gering 4, modell_passt_nicht 1 |
| glas | baseline | Licht tag | 29 | 28 | 1.6 | 2.1 | ensenso_d405_widerspruch 14, kontur_inlier_gering 5, keine_erkennung 2 |
| glas | baseline | Licht kueche | 29 | 14 | 1.1 | 2.0 | ensenso_d405_widerspruch 13, keine_erkennung 7, kontur_inlier_gering 5, modell_passt_nicht 3 |
| glas | baseline | Licht dunkel | 27 | 0 | nan | nan | keine_erkennung 27 |
| glas | baseline | Auszug halb | 41 | 10 | 1.8 | 2.2 | keine_erkennung 23, ensenso_d405_widerspruch 10, kontur_inlier_gering 4, modell_passt_nicht 1 |
| glas | baseline | Auszug voll | 44 | 18 | 1.2 | 2.0 | ensenso_d405_widerspruch 17, keine_erkennung 13, kontur_inlier_gering 6, modell_passt_nicht 2 |
| glas | maskrcnn | alle | 85 | 6 | 1.1 | 1.2 | keine_erkennung 64, ensenso_d405_widerspruch 15, kontur_inlier_gering 1 |
| glas | maskrcnn | trocken | 56 | 7 | 1.1 | 1.2 | keine_erkennung 39, ensenso_d405_widerspruch 12, kontur_inlier_gering 1 |
| glas | maskrcnn | nass | 29 | 3 | 1.1 | 1.1 | keine_erkennung 25, ensenso_d405_widerspruch 3 |
| glas | maskrcnn | Licht tag | 29 | 10 | 0.9 | 1.1 | keine_erkennung 21, ensenso_d405_widerspruch 5 |
| glas | maskrcnn | Licht kueche | 29 | 7 | 1.1 | 1.2 | keine_erkennung 17, ensenso_d405_widerspruch 9, kontur_inlier_gering 1 |
| glas | maskrcnn | Licht dunkel | 27 | 0 | nan | nan | keine_erkennung 26, ensenso_d405_widerspruch 1 |
| glas | maskrcnn | Auszug halb | 41 | 7 | 0.9 | 1.1 | keine_erkennung 33, ensenso_d405_widerspruch 4, kontur_inlier_gering 1 |
| glas | maskrcnn | Auszug voll | 44 | 5 | 1.1 | 1.2 | keine_erkennung 31, ensenso_d405_widerspruch 11 |
| glas | wahr | alle | 85 | 92 | 1.4 | 2.5 | kontur_inlier_gering 3, ensenso_d405_widerspruch 3, zu_wenig_kontur 1 |
| glas | wahr | trocken | 56 | 91 | 1.3 | 2.6 | kontur_inlier_gering 3, zu_wenig_kontur 1, ensenso_d405_widerspruch 1 |
| glas | wahr | nass | 29 | 93 | 1.5 | 2.3 | ensenso_d405_widerspruch 2 |
| glas | wahr | Licht tag | 29 | 93 | 1.4 | 2.6 | kontur_inlier_gering 1, zu_wenig_kontur 1 |
| glas | wahr | Licht kueche | 29 | 93 | 1.6 | 2.5 | kontur_inlier_gering 1, ensenso_d405_widerspruch 1 |
| glas | wahr | Licht dunkel | 27 | 89 | 1.2 | 2.1 | ensenso_d405_widerspruch 2, kontur_inlier_gering 1 |
| glas | wahr | Auszug halb | 41 | 88 | 1.3 | 2.5 | kontur_inlier_gering 3, ensenso_d405_widerspruch 1, zu_wenig_kontur 1 |
| glas | wahr | Auszug voll | 44 | 95 | 1.5 | 2.5 | ensenso_d405_widerspruch 2 |
| teller | baseline | alle | 131 | 0 | nan | nan | ebene_inlier_gering 66, normale_weicht_ab 49, kein_kreis 28, keine_erkennung 25 |
| teller | baseline | trocken | 52 | 0 | nan | nan | ebene_inlier_gering 27, normale_weicht_ab 19, kein_kreis 13, keine_erkennung 9 |
| teller | baseline | nass | 79 | 0 | nan | nan | ebene_inlier_gering 39, normale_weicht_ab 30, keine_erkennung 16, kein_kreis 15 |
| teller | baseline | Licht tag | 43 | 0 | nan | nan | ebene_inlier_gering 26, normale_weicht_ab 18, kein_kreis 11, bogen_zu_kurz 4 |
| teller | baseline | Licht kueche | 43 | 0 | nan | nan | ebene_inlier_gering 25, normale_weicht_ab 17, keine_erkennung 9, kein_kreis 7 |
| teller | baseline | Licht dunkel | 45 | 0 | nan | nan | keine_erkennung 15, ebene_inlier_gering 15, normale_weicht_ab 14, kein_kreis 10 |
| teller | baseline | Auszug halb | 67 | 0 | nan | nan | ebene_inlier_gering 34, normale_weicht_ab 20, keine_erkennung 13, kein_kreis 13 |
| teller | baseline | Auszug voll | 64 | 0 | nan | nan | ebene_inlier_gering 32, normale_weicht_ab 29, kein_kreis 15, keine_erkennung 12 |
| teller | maskrcnn | alle | 131 | 0 | nan | nan | keine_erkennung 131 |
| teller | maskrcnn | trocken | 52 | 0 | nan | nan | keine_erkennung 52 |
| teller | maskrcnn | nass | 79 | 0 | nan | nan | keine_erkennung 79 |
| teller | maskrcnn | Licht tag | 43 | 0 | nan | nan | keine_erkennung 43 |
| teller | maskrcnn | Licht kueche | 43 | 0 | nan | nan | keine_erkennung 43 |
| teller | maskrcnn | Licht dunkel | 45 | 0 | nan | nan | keine_erkennung 45 |
| teller | maskrcnn | Auszug halb | 67 | 0 | nan | nan | keine_erkennung 67 |
| teller | maskrcnn | Auszug voll | 64 | 0 | nan | nan | keine_erkennung 64 |
| teller | wahr | alle | 131 | 0 | nan | nan | ebene_inlier_gering 102, normale_weicht_ab 23, zu_wenig_punkte 21, kein_kreis 5 |
| teller | wahr | trocken | 52 | 0 | nan | nan | ebene_inlier_gering 43, normale_weicht_ab 6, zu_wenig_punkte 6, kein_kreis 3 |
| teller | wahr | nass | 79 | 0 | nan | nan | ebene_inlier_gering 59, normale_weicht_ab 17, zu_wenig_punkte 15, kein_kreis 2 |
| teller | wahr | Licht tag | 43 | 0 | nan | nan | ebene_inlier_gering 34, normale_weicht_ab 8, zu_wenig_punkte 5, kein_kreis 1 |
| teller | wahr | Licht kueche | 43 | 0 | nan | nan | ebene_inlier_gering 33, zu_wenig_punkte 9, normale_weicht_ab 7, kein_kreis 1 |
| teller | wahr | Licht dunkel | 45 | 0 | nan | nan | ebene_inlier_gering 35, normale_weicht_ab 8, zu_wenig_punkte 7, kein_kreis 3 |
| teller | wahr | Auszug halb | 67 | 0 | nan | nan | ebene_inlier_gering 41, zu_wenig_punkte 21, normale_weicht_ab 4, kein_kreis 3 |
| teller | wahr | Auszug voll | 64 | 0 | nan | nan | ebene_inlier_gering 61, normale_weicht_ab 19, kein_kreis 2 |

### Punktabdeckung (Vorhersagezeile 5)

Anteil der Pixel eines sichtbaren Objekts mit gültigem Tiefenwert (Ensenso C57-6-S, Strahlschnitt mit angenommenem Fehlermodell, 72 Szenen; Median, P10-P90 über Objekte, Bootstrap-95-%-Intervall des Mittels). Keine Messung: Projektormuster und Stereo-Matching sind nicht simuliert.

| Klasse | Fehlermodell | n Objekte | Abdeckung Median | P10 | P90 | Mittel (Bootstrap-95-%) |
|---|---|---:|---:|---:|---:|---|
| glas | trocken | 270 | 31 % | 27 % | 38 % | 31 % (30-32) |
| glas | nass | 270 | 31 % | 27 % | 38 % | 31 % (30-32) |
| teller | trocken | 458 | 19 % | 11 % | 85 % | 29 % (27-31) |
| teller | nass | 458 | 18 % | 11 % | 81 % | 28 % (25-30) |

Glas „nass“ = „trocken“ ist durch das Fehlermodell bedingt (der Nass-Ausfall gilt nur für Flächen ohne Glasregel), kein Messergebnis. Teller: Median 18–19 %, aber P10–P90 11–85 %: breite Streuung, weil hochkant stehende Teller je nach Lage flach (> 60°) oder steiler zum Strahl liegen. Vorhersagezeile 5 (Punktabdeckung) damit: Glas ca. 31 % (Streuung der Objekte 27–38 %), Teller ca. 28–29 % im Mittel (Bootstrap 25–31 %), Verteilung zweigipflig.

## Rohdaten und Bilder

Montagen der schwierigsten Fälle (je Verfahren: Gläser oben, Teller unten) und Gesamtbilder mit allen Erkennungen liegen im Artefaktordner des Tickets (`montage_<verfahren>.jpg`, `montage_<verfahren>_gesamt.jpg`), nicht im Repo.
