# Messprotokoll für den ersten Kameratag

Gehört zum eingefrorenen Vorhersagekatalog (`docs/kameratag-vorhersagen.md`, `config/kameratag_vorhersagen.yaml`) und zum
Auswertungsskript `scripts/kameratag_auswerten.py`. Jede Messung prüft eine Zeile des Katalogs; die Reihenfolge folgt
der Messreihenfolge aus `docs/sensitivitaet.md` (Top 5), davor kommt der Aufbau, danach die Zusatzmessungen.

Voraussetzungen, die am Kameratag **nicht** feststehen (Entwurf): Roboter, Kalibrierplatte und Stativ sind nicht gesetzt. Das Protokoll
nimmt daher ein **Stativ** für die Ensenso an und führt an jeder Stelle auf, was ohne Roboter entfällt.

## 1. Reihenfolge und Zeitbedarf

Aufwand: **P4** = Wert aus der Sensitivitätsdokumentation (selbst eine Annahme), **A** = Annahme dieses Protokolls. Keine Zeit ist gemessen.

| Nr | Messung | Zeilen | Aufwand | Quelle |
|---|---|---|---|---|
| 0 | Aufbau, Abstände, Sichtfeld | 2, 3 | 30 + 10 min | A |
| 1 | Randdicke der echten Dessertteller, Aufnahmen der Tellerreihe, Plätze je Mastposition | 11, 4, 5 | 20 min (P4) + je Mastposition 40 min | P4 / A |
| 2 | Kalibrierung Station: Versatz und Drehung | 12 (7) | 45 min | P4 |
| 3 | Erkennungsrate bei Tag / Küche / dunkel (Nachbartreffer mitzählen), Nässe | 6, 5, u1, u3 | 75 min (P4) + 10 min Nässe (A) | P4 / A |
| 4 | Tellerlage und -gier im Ständer, Glaslage, Spiel des Ständers | 9, 10, 13 | 35 min (P4) + 20 min Glas (A) | P4 / A |
| 5 | D405-Rauschen am Teller | 1 | 15 min | P4 |
| 6 | Zusatz, wenn Zeit bleibt: Ensenso-Rauschen, Wiederholgenauigkeit, Lagegenauigkeit, Projektorreflexe | 1, 8, 7, u2 | 10 + 15 + 20 + 10 min | A |

Kern nach P4 (Messung 1 bis 5): 190 min. Mit Aufbau und den Erweiterungen aus P1 etwa 340 min, mit Messung 6 etwa 395 min (alles Annahme).
**Kürzen, wenn die Zeit knapp wird:** zuerst Messung 6, dann den zweiten Mastpositionswechsel in Messung 1, dann die Nässe in Messung 3. Die Messungen 1 bis 5 in dieser Reihenfolge nicht
umstellen: 1 und 2 sind billig und tragen die größten Teller-Indizes, danach bleibt die Erkennung (größter Treiber für Glas), dann die Prior-Annahmen.
Den echten Mast-Umbau (≈ 120 min nach P4) **nicht** am ersten Tag: Mastposition wird mit dem Stativ nachgebildet (Positionswechsel am Stativ: 15 min, **Annahme**).

## 2. Checkliste vor dem Kameratag

* [ ] Ensenso C57-6-S (24 V oder PoE++), GigE-Kabel, Software für Punktwolke und RGB; Version notieren.
* [ ] Belichtung, Projektorhelligkeit, Stereo-Parameter **einmal festlegen und in `kameratag/<datum>/einstellungen.yaml` notieren**; während der Messungen nicht ändern (Voraussetzung für Zeile 8).
* [ ] D405 mit Halterung, SDK-Version notieren.
* [ ] Stativ mit Neigungskopf, Neigungsmesser (Digital), Laser-Entfernungsmesser, Maßband (3 m), Wasserwaage.
* [ ] Messschieber (Nullabgleich geprüft), Winkelmesser (Digital, Nullpunkt gegen eine Referenzfläche geprüft), Lehre bzw. Schablone für Glas- und Tellerplätze.
* [ ] Kalibriertafel 390 × 390 mm, matte weiße Platte (mindestens 0,5 × 0,5 m) für das Rauschen, Klebepunkte für die Referenzpunkte R1 bis R3.
* [ ] 6 Dessertteller (mehr, wenn Sorten unterschiedlich), 16 Gläser, Wasserzerstäuber (Nässe), Handtuch.
* [ ] Lichtmessung: kein Luxmeter nötig; die Lichtklasse wird über den mittleren Grauwert des RGB-Bildes festgelegt (Abschnitt 3).
* [ ] Laptop mit Repo und Python (numpy, pyyaml), Speicher mindestens 20 GB frei, zweiter Datenträger für die Sicherung.
* [ ] Spülmaschine: Auszugsmarkierungen für 0,225 m und 0,45 m an beiden Körben (Klebeband an der Schiene, mit Maßband gesetzt).
* [ ] Kamera für Aufbaufotos (Handy genügt).

## 3. Ordner, Dateinamen, Formate, Metadaten

```
kameratag/<datum>/
  einstellungen.yaml             Ensenso/D405-Einstellungen, Software-Versionen, Uhrzeiten
  messung.yaml                   Messdatei für das Auswertungsskript (Aufbau: beispiele/kameratag-messung-beispiel.yaml)
  m0_aufbau/        fotos/ 001_uebersicht.jpg, 002_detail_kamera.jpg ...
  m1_randdicke/     meta.yaml, 001_ensenso.npz, 001_ensenso_rgb.png, 001_d405.npz, 001_d405_rgb.png, fotos/
  m2_kalibrierung/  ...
  m3_erkennung/     ...
  m4_lage_gier/     ...
  m5_d405_rauschen/ ...
  m6_zusatz/        ...
```

Aufnahme-Dateien: `<nr>_<kamera>.<ext>` mit dreistelliger Nummer **je Messung**, Kamera `ensenso` oder `d405`, Ergänzung `_rgb` für das Farbbild.

| Datei | Inhalt und Format |
|---|---|
| `<nr>_ensenso.npz` | Punktwolke: Feld `xyz` (H, W, 3), float32, **Millimeter im Kamerarahmen** (z = Abstand entlang der Blickachse), NaN = ungültig; optional `maske` (H, W), bool, Objektmaske für Zeilen 5, u3. Alternativ `.ply` (ASCII oder binary_little_endian, Eigenschaften `x y z` in mm, unorganisiert) |
| `<nr>_ensenso_rgb.png` | RGB-Bild des Ensenso-Farbsensors (Zeilen 3, 6) |
| `<nr>_d405.npz` | Punktwolke wie oben (aus der Tiefe mit den Intrinsics der Kamera umgerechnet, mm im Kamerarahmen), zusätzlich `tiefe_mm` (H, W) float32 |
| `<nr>_d405_rgb.png` | RGB-Bild der D405 |
| `meta.yaml` | Metadaten je Messung (unten) |
| `fotos/*.jpg` | Fotos der Aufbauten, Pflicht: Übersicht plus Detail mit Maßband je Messung und je Positionswechsel |

Wenn die Software nur ein eigenes Format (z. B. Binärdatei des Herstellers) schreibt: Original **zusätzlich** unverändert ablegen und
mit einem Exportschritt nach `.npz` oder `.ply` wandeln. Die Auswertung liest nur `.npz` und `.ply`.

**Metadaten** `meta.yaml` (je Messung; eine Zeile je Aufnahme):

```
messung: m1_randdicke
datum: <JJJJ-MM-TT>
mast: haupt                  # haupt | ausleger | hoeher | bestand | stativ_frei
kamera_pose: {x_m: 0.55, y_m: 0.70, z_m: 1.25, neigung_grad: 55}     # gemessene Ist-Werte, nicht Soll
einstellungen: einstellungen.yaml
aufnahmen:
  - {nr: 1, kamera: ensenso, korb: oberkorb, auszug_m: 0.225, licht: tag, grauwert: 188, nass: false, objekt: oberteller_0_1, bemerkung: ""}
```

Pflichtfelder je Aufnahme: `nr`, `kamera`, `mast`, `auszug_m` (0, 0.225, 0.45; an der Schiene gemessen), `licht` (`tag` | `kueche` | `dunkel`),
`grauwert` (Mittel des RGB-Bildes, 0 bis 255), `nass` (true/false), `objekt` (Platzname wie im Katalog, z. B. `glas_5`, `oberteller_1_2`, `unterteller_0_1`, sonst `tafel`, `platte`).
Lichtklassen nach dem mittleren Grauwert der Renderbilder (Kalibrierung der Erkennung, `docs/kameratag-p3.md`): Tag 182 bis 194, Küche 86 bis 101, dunkel 14 bis 18.
Echte Bilder können davon abweichen; dann den Grauwert notieren und die nächste Klasse wählen. **Das ist eine Annahme**, kein Messbeleg.

**Platznamen:** `glas_1` bis `glas_16`; `oberteller_<Reihe>_<Tiefe>` (Reihe 0 bis 1, Tiefe 1 bis 4); `unterteller_<Reihe>_<Tiefe>` (Reihe 0 bis 1, Tiefe 1 bis 3).
Glas 1 bis 16 sind Reihen x = 0,48 / 0,36 / 0,24 / 0,12 m (je 4 Plätze, von vorn nach hinten); Reihe 0 der Teller liegt bei x = 0,15 m, Reihe 1 bei x = 0,45 m (nächste am Mast), Tiefe 1 ist der vorderste Teller (`docs/stationssichtbarkeit.md`).

## 4. Die Messungen

Allgemein vor jeder Messung: Einstellungen unverändert, Auszug an der Markierung, Uhrzeit notieren. Nach jeder Messung: `meta.yaml` ausfüllen, 2 Fotos, Dateien zählen.

### Messung 0: Aufbau, Abstände, Sichtfeld (Zeilen 2, 3)

* **Aufbau:** Stativ mit der Ensenso in der **Hauptposition**: optisches Zentrum 0,39 m über der Plattenoberseite, 0,65 m vor der Plattenvorderkante, x = 0,55 m im Modellrahmen
  (Koordinaten, Ursprung und Achsen wie in `config/spuelmaschine.yaml`; die Stativlage wird am Aufbau in diese Maße übersetzt). Blickachse 55° unter der Waagerechten auf den Blickpunkt (0,30; 0,17; 0,41) m.
* **Hilfsmittel:** Laser-Entfernungsmesser, Maßband, Neigungsmesser, Klebepunkte R1 bis R3.
* **Schritte:** (1) Referenzpunkte kleben: R1 Mitte Plattenvorderkante (Oberseite), R2 Mitte Oberkorb-Front am Boden bei 0,45 m Auszug, R3 Mitte Unterkorb-Front am Boden bei 0,45 m Auszug. (2) Ist-Pose der Kamera messen und in `meta.yaml` schreiben. (3) Abstand vom Kameragehäuse-Ursprung zu R1, R2, R3 mit dem Laser, je 3 Ablesungen, Mittel. Die Lage des optischen Zentrums im Gehäuse ist nicht geklärt (±2 cm in der Katalogtoleranz); als Gegenprobe den Abstand in der Ensenso-Punktwolke an den Klebepunkten ablesen. (4) Wandaufnahme: ebene helle Wand senkrecht zur Blickachse bei z = 1,0 m (Laser), eine Aufnahme; Ausdehnung der gültigen Punkte in x und y ablesen. Das ist das Sichtfeld bei 1 m (Katalog: 954 × 867 mm). (5) Aufnahme des Korbs bei 0,225 m und 0,45 m Auszug; Korbecken im Bild zählen (8 Ecken der Korbhülle je Korb).
* **Dateien:** `m0_aufbau/001_ensenso.npz` (Wand), `002_ensenso.npz`/`003_ensenso.npz` (Korb 0,225 / 0,45 m), `fotos/`.
* **Messdatei:** `z02: {haupt: {r1: <m>, r2: <m>, r3: <m>}}`, `z03: {haupt: {fov_1m_mm: [x, y], ecken: {a225: <n>, a450: <n>}}}`.
* **Entscheidungsregel:** Abweichung > 20 mm an einem Referenzpunkt: Mastposition mit den gemessenen Maßen neu rechnen (`scripts/mast_raster.py`), Zeilen 3 und 4 danach nur mit der tatsächlichen Bildlage auswerten. Fehlt eine Ecke des Unterkorbs bei 0,45 m, Neigung auf 60° stellen und wiederholen (Neigung ist ohne Umbau verstellbar).

### Messung 1: Randdicke der echten Dessertteller und Tellerreihe in Mastpose (Zeile 11; mit Zeilen 4, 5)

* **Hilfsmittel:** Messschieber, 6 Dessertteller, Ensenso am Stativ (Hauptposition), Klebeband-Markierungen am Auszug.
* **Schritte:**
  1. **Randdicke:** Randwulst an jedem der 6 Teller an 3 Stellen mit dem Messschieber, Größtwert je Teller notieren (Wulstdicke senkrecht zur Tellerebene, an der dicksten Stelle des Randes). Messdatei: `z11: {dicke_mm: [...]}` (6 Werte).
  2. **Tellerreihe aufnehmen:** Teller in die Tellerreihe des Oberkorbs stellen (vorderste Plätze, mindestens 4 Teller), Auszug 0,225 m und 0,45 m, je 3 Aufnahmen; ebenso die Unterkorb-Teller (6). Dateien `m1_randdicke/<nr>_ensenso.npz` und `_rgb.png`, `meta.yaml` mit `objekt`.
  3. **Gläser:** 16 Gläser in den Oberkorb (Glashalter), Auszug 0,225 und 0,45 m, je eine Aufnahme (für Zeile 4).
  4. **Plätze bewerten:** je Platz und Auszug „nutzbar“ ja/nein nach den Kriterien des Katalogs (Teller: ≥ 240 gültige Tiefenpunkte auf der Fläche bei voller Auflösung, entspricht 60 Punkten auf der Schätzerskala 2, **Annahme 4:1**; Glas: Silhouette im Bild nicht zu mehr als der Hälfte von Stäben verdeckt). Messdatei: `z04: {haupt: {a225: {glas_1: true, ...}, a450: {...}}}`; alternativ `{punkte: n}` je Teller.
  5. **Pose-Ausbeute:** Anteil der Teller, bei denen die Ebenenanpassung im Tellerbereich gelingt. **Behelf, Annahme:** gelungen, wenn `ebene_fit` im Tellerbereich ≥ 240 Punkte findet und der Mittelpunkt des Tellerkreises im RGB-Bild erkennbar ist. Der Pose-Schätzer des Repos läuft bisher auf Strahlschnitt-Aufnahmen, nicht auf Ensenso-Wolken; die Anbindung ist nicht Teil dieses Pakets. Messdatei: `z11: {pose: {k: <gelungen>, n: <alle Aufnahmen>}}`.
  6. **Positionswechsel (einfacher Ausleger):** Stativ auf (0,55; 0,60; 1,30), 60° Neigung, Blickpunkt (0,30; 0,17; 0,44) m; Schritte 2 bis 5 wiederholen (40 min, Wechsel 15 min = Annahme). Messdatei `z04.ausleger` und `z02`/`z03` für die zweite Position.
* **Fotos:** Messschieber am Teller (Ablesung lesbar), Tellerreihe in der Maschine, Stativ in beiden Positionen.
* **Entscheidungsregeln (Zeile 11):**
  * Größte Randdicke ≤ 6 mm: Teller-Pose aus der Station ist plausibel. **Mastwahl:** trägt der Rand an der einfachen Position bei beiden Auszügen (Pose-Ausbeute dort ≥ Haupt), dann einfacher Ausleger (gleiche Gläser 16/16, 0,10 m weniger Ausleger); sonst Hauptposition.
  * 6 bis 8 mm: Grenzbereich. Station-Pose für den Teller nur als Prüfung; Teller-Lage aus dem Slot (Prior B) mit D405. Hauptposition bevorzugen (Fläche 0,743 gegen 0,549).
  * **> 8 mm: keine Station-Pose für den Teller** (Modell: alle Ketten 0 %). Teller aus dem Mechanik-Prior (B) plus D405; Mast auf die Gläser auslegen; Hauptposition behalten, Tellerfläche nur bei Auszug 0,225 m nutzen (dort Haupt: 8/8 Oberkorb-, 5/6 Unterkorb-Teller nutzbar; mit dicken Rändern an dieser Position nicht gerechnet).
  * < 3 mm: außerhalb der gerechneten Spanne; Ausbeute der Aufnahmen entscheidet.
* **Zeile 4 / 5:** fehlende Plätze namentlich notieren; Konsequenz siehe Katalog.

### Messung 2: Kalibrierung Station (Zeile 12; liefert Referenz für Zeile 7)

* **Hilfsmittel:** Kalibriertafel 390 × 390 mm, Referenzpunkte (3 bis 5, besser 5), Roboter-TCP **oder** Maßband/Lehre (siehe unten), Ensenso am Stativ (Hauptposition).
* **Schritte:** (1) Kalibrierung Station → Roboter bzw. → Maschinenrahmen durchführen wie vorgesehen (Verfahren liegt außerhalb dieses Protokolls). (2) **Prüfpunkte**, die nicht in die Kalibrierung eingingen: Tafel an 3 Stellen (nahe am Korb, Mitte, weit) aufstellen; je Stelle Ecken oder Marker der Tafel als Punkte aus der Ensenso-Wolke im Zielrahmen ablesen. (3) Dieselben Punkte im Zielrahmen referenzieren: mit dem **Roboter-TCP**, falls er steht; **ohne Roboter** mit Maßband, Lehre und Laser gegen die Maschine (Genauigkeit etwa 1 bis 2 mm, **Annahme**; ein Versatz unter 2 mm ist dann nicht auflösbar, Zeile 12 ist in dem Fall nur eine Obergrenze). (4) Punktlisten (mm) in die Messdatei: `z12: {station: [[x,y,z], ...], referenz: [[x,y,z], ...]}` (mindestens 3, besser 5 Paare, nicht auf einer Geraden). Das Skript rechnet nach Kabsch: **Versatz** = Abstand der Schwerpunkte, **Drehung** = Winkel der Drehmatrix, dazu den Rest-RMS.
* **Dateien:** `m2_kalibrierung/<nr>_ensenso.npz`, Aufnahme je Tafelstelle; `punkte.yaml` mit den abgelesenen Punkten.
* **Entscheidungsregeln (Zeile 12):**
  * Versatz ≤ 2,5 mm und Drehung ≤ 5°: Kette K (heutige Prüfung) trägt. Planwert 5 mm / 5° bestätigt (Versatz 1,25 bis 5 mm, Drehung 1 bis 5° = stimmt).
  * Versatz 2,5 bis 5 mm: Glas-Fehlalarm von K (50 % bei 5 mm): „neu hinsehen“ (A) einplanen.
  * **Versatz > 5 mm oder Drehung > 5°:** K nicht einsetzen; A fürs Glas, B für den Teller.
  * **Versatz ≥ 7,5 mm oder Drehung ≥ 10°:** K und A tragen beim Teller nicht (0 %), Teller nur mit B; Kalibrierung wiederholen.
  * Versatz ≥ 15 mm: A beim Teller riskant (unbemerkte Fehlgriffe); Drehung > 20°: außerhalb der gerechneten Spanne.
* Die Tafel dient auch als Ebenenreferenz für Zeile 7 (Ebene und Normale), wenn kein Lehrenplatz zur Hand ist.

### Messung 3: Erkennungsrate bei Licht (Zeilen 6, 5; unbekannt u1, u3)

* **Hilfsmittel:** Ensenso-Farbbild, Handlabel-Werkzeug (Objektmasken oder Polygone), Erkennungslauf nach `docs/kameratag-p3.md`, Wasserzerstäuber.
* **Schritte:** (1) Je Lichtklasse (Tag, Küche, dunkel) mindestens 8 Gläser und 8 Teller bei Auszug 0,225 **und** 0,45 m aufnehmen (insgesamt ≥ 20 Aufnahmen), trocken. Grauwert je Bild eintragen. (2) Handlabel: Maske je sichtbares Objekt (Instanz). (3) Erkennung (klassische Baseline, danach ggf. Mask R-CNN) auf den RGB-Bildern; **Treffer** = richtige Klasse, IoU ≥ 0,5 gegen das Handlabel, nicht mehrere Objekte verschmolzen; **Nachbarverwechslung** mitzählen. Der vorhandene Erkennungsskript-Eingang (`scripts/p3_erkennen.py`) liest Renderordner; ob er Fotos direkt liest, ist ungeprüft - gegebenenfalls Eingabeordner nach dem Muster des Renderordners anlegen (Annahme: ein Umbau der Ordnerstruktur genügt). (4) **Punktabdeckung** (Zeile 5): je Objekt Maske plus `xyz`-Wolke in einer `.npz`; das Skript berechnet den Anteil gültiger Pixel in der Maske (Mittel über ≥ 8 Objekte je Klasse). (5) **Nässe (u1):** dieselben Plätze mit Wasser besprühen, Tag-Licht, Erkennung wiederholen. (6) **Glas (u3):** Punktabdeckung der trockenen Gläser aus (4) bewerten.
* **Messdatei:** `z06: {glas_tag: {k: .., n: ..}, glas_kueche: ..., glas_dunkel: ..., teller_tag: ..., nachbar_glas: ..., nachbar_teller: ...}`; `z05: {glas: {objekte: [{aufnahme: ..}], ...}, teller: {...}}`; `u1: {erkennung_trocken: {k, n}, erkennung_nass: {k, n}}`; `u3: {objekte: [...]}` bzw. `abdeckung_glas_pct: [...]`.
* **Entscheidungsregeln:**
  * Zeile 6 stimmt oder ist pessimistisch: Erkennungsrate des Katalogs als Erwartung nutzen (Glas bei Tag etwa 80 % Griffe möglich).
  * Zeile 6 zu optimistisch: Beleuchtung sicherstellen, Suchfenster auf den Nennort einengen, Glas im Dunkeln nicht einplanen; Teller < 45 %: Teller aus Slot-Position (B). Kette B braucht die Erkennung nur zur Prüfung.
  * **u3 Ausgang C (Glas-Abdeckung < 5 %):** Zeile 5 versagt - Glas aus der Slot-Position schätzen, Kamera nur zur Prüfung.
  * u1 Ausgang C (Nässe kostet > 30 Prozentpunkte): im Nassen Lage aus dem Slot, Kamera nur zur Prüfung.
* Bei n = 20 ist das Wilson-Intervall etwa ±20 Prozentpunkte breit: ein „stimmt“ ist dann schwach. Mehr Objekte aufnehmen, wenn die Zeit reicht.

### Messung 4: Tellerlage, Tellergier, Glaslage, Spiel des Ständers (Zeilen 9, 10, 13)

* **Hilfsmittel:** Digital-Winkelmesser, Messschieber, Lehre/Schablone auf dem Korbraster, Bleistift für die Nennmarken.
* **Schritte:** (1) **Teller-Gier:** an 6 Tellern im Ständer die Drehung um die Hochachse gegen die Nennrichtung der Reihe messen (Winkelmesser an Tellerkante und Korbrahmen), Vorzeichen notieren. (2) **Teller-Lage:** x/y der Tellermitte gegen den Nennort (Lehre auf dem Stabraster); Teller-z nicht gemessen. (3) **Spiel:** jeden Teller von Hand bis zum Anschlag nach beiden Seiten drehen, den größten Winkel gegen die Nennrichtung ablesen (Zeile 13). (4) **Glaslage:** 8 bis 16 Gläser auf dem Glashalter mit der Schablone gegen den Nennort messen (Lage in mm), Neigung des Glases gegen die Senkrechte mit dem Winkelmesser. Alles bei Auszug 0,45 m, Nennort relativ zur **Korbstruktur**, nicht zur Maschine (der Auszug schwankt, `korbauszug_delta`).
* **Messdatei:** `z09: {gier_grad: [...], lage_mm: [...]}`, `z10: {lage_mm: [...], neigung_grad: [...]}`, `z13: {spiel_grad: [...]}`.
* **Entscheidungsregeln:**
  * **Zeile 9:** Gier ≤ 2° und Lage ≤ 5 mm: Prior-Kette B für den Teller einsetzbar. Gier 2 bis 3°: Prior-Band auf die gemessene Streuung weiten (B trägt im Modell noch, in Newton 3° Erfolg, keine Reserve zur Grenze). **Gier > 3°: Prior-Kette B für den Teller verwerfen**, Gier aus Station und D405 messen statt vorgeben. Lage > 10 mm: B beim Teller nicht ohne engeren Prior-Alarm einsetzen.
  * **Zeile 10:** Lage ≤ 8 mm und Neigung ≤ 3°: B für Gläser einsetzbar. Lage > 8 mm: A („neu hinsehen“) oder S1 statt B; > 15 mm: außerhalb der Modellwelt.
  * **Zeile 13:** Spiel s ≤ 3°: folgenlos. 3 bis 7°: Newton-Reihe (Gier 4, 5, 6°, mehrere Seeds) **vor** dem Einsatz von B für den Teller. s > 7°: B für den Teller nicht einsetzen, Ständer mechanisch führen.

### Messung 5: D405-Rauschen am Teller (Zeile 1)

* **Hilfsmittel:** ebene matte Platte, D405 in der Handhalterung am Stativ oder in der Hand fixiert, Maßband.
* **Schritte:** Platte senkrecht zur Blickachse, Abstände **0,20 m und 0,35 m** (A: der Teller liegt im Betrieb etwa 0,2 bis 0,4 m vor der D405), je 5 Aufnahmen. Ebenenanpassung im mittleren Bildbereich; σ der Residuen. Ohne Roboter entfällt die Hand-Auge-Kalibrierung, aus P4 „(und Hand-Auge-Kalibrierung)“; das ist im Protokoll zu vermerken.
* **Messdatei:** `z01: {d405: [{z_m: 0.20, sigma_mm: ..}, {aufnahme: m5_d405_rauschen/003_d405.npz, roi_px: [u0, v0, u1, v1]}]}`.
* **Entscheidungsregel:** Faktor gegenüber dem Modell (0,8 mm bei 0,2 m, 1,8 mm bei 0,3 m, 3,2 mm bei 0,4 m) < 2: Modell behalten. **Faktor ≥ 2: K bricht, A greift unbemerkt daneben (Teller 2×: K 33 %, A 50 % mit 50 % unbemerkt), A für den Teller nicht freigeben**, B oder Abbruch. Faktor ≥ 3: auch A beim Teller 0 % mit 100 % unbemerkt.

### Messung 6: Zusatz, wenn Zeit bleibt (Zeilen 1, 8, 7; u2)

* **Ensenso-Rauschen (Zeile 1, 10 min A):** matte Wand, z = 0,82 / 1,0 / 1,20 m, je 3 Aufnahmen. Entscheidung: bis 3× das Modell ohne Folge im Modell (ST ≤ 0,03); über 2× erst Belichtung und Projektor prüfen.
* **Wiederholgenauigkeit (Zeile 8, 15 min A):** 20 Aufnahmen derselben Szene (ein Glas, ein Teller), Kamera, Licht und Einstellungen unverändert; Messdatei `z08: {punkt: {aufnahmen: [...20 Dateien], roi_px: [...]}, pose: {glas: [[x, y], ...]}}`. Erwartete Richtung: zu pessimistisch (siehe Katalog). Zu streuend: mitteln, Einstellungen fest, Stativ auf Vibration prüfen.
* **Lagegenauigkeit (Zeile 7, 20 min A):** Glas und Teller an Plätzen mit Lehre als Referenz (±1 mm, Annahme); Schätzpose gegen Referenz; Messdatei `z07: {glas: {geschaetzt_mm: [...], referenz_mm: [...]}}` oder `fehler_mm: [...]`. Median > 5 mm: Station-Pose nicht als Griffpose; erst Zeile 12 prüfen.
* **Projektorreflexe im Metallkorb (u2, 10 min A):** ebenes Objekt (Platte) im leeren Korb, Aufnahme; Anteil der Punkte > 10 mm neben der Ebene. Messdatei `u2: {ausreisser_pct: ..}` oder `u2: {aufnahme: ..., roi_px: [...]}`. Ausgang C (> 10 %): Winkel/Position ändern, Belichtung senken; sonst Ensenso im Korb nur für die Anwesenheit.

## 5. Checkliste nach dem Kameratag

* [ ] Alle Dateien gezählt (Aufnahmen je Messung gegen `meta.yaml`), keine Datei ohne Metadaten.
* [ ] Zwei Kopien der Daten auf getrennten Datenträgern.
* [ ] Ist-Pose der Kamera je Position in `meta.yaml` (gemessen, nicht Soll).
* [ ] Fotos den Messungen zugeordnet.
* [ ] `messung.yaml` ausgefüllt, nicht gemessene Zeilen **leer lassen** (das Skript weist sie als `nicht_gemessen` aus).
* [ ] Auswertung laufen lassen: `scripts/kameratag_auswerten.py kameratag/<datum>/messung.yaml --out kameratag/<datum>/auswertung`.
* [ ] Ergebnis lesen: jede Zeile mit Urteil und Konsequenz; Zeilen mit „fehler“ (Aufnahme fehlt oder Format falsch) nachholen.
* [ ] Abweichende Plätze (Zeile 4) und Ausnahmen (Maschine, Licht, Teller-Sorten) im Ergebnisordner als Textnotiz festhalten.
* [ ] Der Katalog bleibt unverändert. Ergebnisse stehen nur in `kameratag_ergebnis.md` und `.json`.

## 6. Auswertung: Messdatei und Aufruf

* Jede Katalogzeile n hat in `messung.yaml` den Schlüssel `z<nn>` (also `z01` bis `z13`) unter `messungen:`, die Unbekannt-Zeilen `u1` bis `u3`. Das Beispiel `beispiele/kameratag-messung-beispiel.yaml` zeigt alle Schlüssel mit **erfundenen** Werten.
* Aufnahmen werden relativ zu `--basis` (Standard: Ordner der Messdatei) gelesen. Punktwolken: `.npz` mit `xyz` (organisiert, H × W × 3, mm) bzw. `.ply`. Berechnet werden aus Wolken: Zeile 1 (σ der Ebene), 5 und u3 (Abdeckung mit Maske), 8 (Streuung je Pixel über 20 Aufnahmen), 12 (Kabsch aus Punktlisten, die vorab aus den Wolken abgelesen wurden), u2 (Ausreißer).
* Ausgabe: `kameratag_ergebnis.md` und `kameratag_ergebnis.json` (je Zeile Messwert, Modellwert, Abweichung, Urteil, Konsequenz).
* Probelauf ohne Kamera: `scripts/kameratag_auswerten.py --demo <ordner>` schreibt synthetische Aufnahmen, danach `scripts/kameratag_auswerten.py beispiele/kameratag-messung-beispiel.yaml --basis <ordner> --out <ergebnis>`.
* Urteile: *stimmt*, *zu_optimistisch* (Wirklichkeit schlechter als das Modell), *zu_pessimistisch* (besser); Zeile 13 und die Unbekannt-Zeilen: *unbekannt* mit Einordnung.

## 7. Entscheidungsregeln auf einen Blick

| Wenn | dann |
|---|---|
| Zeile 11: Randdicke > 8 mm | keine Station-Pose für den Teller; Teller aus Prior B plus D405; Mast auf die Gläser; Hauptposition behalten (Tellerfläche nur bei 0,225 m) |
| Zeile 11: 6 bis 8 mm | Grenzbereich: Station-Pose für Teller nur als Prüfung, Hauptposition bevorzugen |
| Zeile 11: ≤ 6 mm und Rand trägt an der einfachen Position bei beiden Auszügen | einfacher Ausleger (gleiche Gläser, 0,10 m weniger Ausleger), sonst Hauptposition |
| Zeile 12: Versatz > 5 mm oder Drehung > 5° | Kette K nicht einsetzen; A fürs Glas, B für den Teller |
| Zeile 12: Versatz ≥ 7,5 mm oder Drehung ≥ 10° | Teller nur mit B; Kalibrierung wiederholen |
| Zeile 6 zu optimistisch | Beleuchtung sichern, Suchfenster einengen; Teller-Rate < 45 %: Teller aus Slot |
| u3 Ausgang C oder Zeile 5 zu optimistisch (Glas) | Glas aus der Slot-Position schätzen, Kamera nur zur Prüfung |
| Zeile 9: Gier > 3° | Prior-Kette B für den Teller verwerfen, Gier messen |
| Zeile 9: Lage > 10 mm | B beim Teller nicht ohne engeren Prior-Alarm |
| Zeile 10: Lage > 8 mm | A oder S1 statt B beim Glas |
| Zeile 13: Spiel 3 bis 7° | Newton-Reihe 3 bis 7° vor Einsatz von B für den Teller |
| Zeile 13: Spiel > 7° | B für den Teller nicht einsetzen |
| Zeile 1 (D405): Faktor ≥ 2 | A für den Teller nicht freigeben |
| Zeile 2: Abweichung > 20 mm | Mastposition mit gemessenen Maßen neu rechnen |
| Zeile 4: Plätze fehlen | dort Lage aus dem Slot (B), Kamera nur zur Anwesenheit; oder Mastposition wechseln |
| Zeile 7: Median > 5 mm | Station-Pose nicht als Griffpose; Zeile 12 prüfen; Slot plus D405 |
