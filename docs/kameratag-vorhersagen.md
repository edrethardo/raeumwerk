# Vorhersagekatalog für den ersten Kameratag (eingefroren)

> **Stand-Hinweis: eingefroren.** Die Vorhersagen stehen maschinenlesbar in `config/kameratag_vorhersagen.yaml` und
> wurden vor dem Kameratag in einem eigenen Commit festgeschrieben.
>
> * Einfrier-Commit: `34050e6b0c4cac37484e9073ff069cf0b84fabb3`
> * SHA-256 der Katalogdatei: `4b64f373bd7a84a82e03519786f09af1930cc99e6e1b34f63bc04f8bc1f408ba`
> * Stand der Zahlen: 2026-11-05 (Paket P0 bis P4 auf `main`)
>
> **Nach dem Kameratag wird die Katalogdatei nicht mehr geändert.** Messergebnisse stehen in einer eigenen Datei
> (`kameratag_ergebnis.md` und `.json`, Ausgabe von `scripts/kameratag_auswerten.py`), nie hier. Der Test
> `test_doku_traegt_pruefsumme_des_eingefrorenen_katalogs` schlägt an, wenn die Datei sich von der Prüfsumme oben entfernt.
> Dieses Dokument bleibt ebenfalls unverändert; Korrekturen an den Vorhersagen wären ein neuer Katalog mit neuer Version.

Kamera: Ensenso C57-6-S (Artikel 1009348) als Stationskamera, Intel RealSense D405 am Handgelenk. Alles Folgende ist
**Modell, Datenblatt oder Annahme, keine Messung an der Anlage**; die Herkunft steht in jeder Zeile (D / M / A).

| Kürzel | Bedeutung |
|---|---|
| **D** | Datenblatt (`config/kameras.yaml`) |
| **M** | Modell: gerechnet in `docs/stationssichtbarkeit.md`, `docs/kameratag-p3.md`, `docs/griff-prior.md`, `docs/sensitivitaet.md`; hier nicht neu gerechnet (einzige Ausnahme: Zeile 8b) |
| **A** | Annahme ohne Messbeleg (Prior, Randdicke, Fenstergrößen, Aufwand) |

**Urteilslogik** (gilt für jede Zeile): *stimmt* = Messwert im Fenster der Spalte „Schwelle“; *zu optimistisch* = die
Wirklichkeit ist **schlechter** als das Modell sagt; *zu pessimistisch* = **besser**. Bei Zeile 13 und den
Unbekannt-Zeilen gibt es kein Urteil, nur eine Einordnung. Das Skript fasst Teilgrößen vorsichtig zusammen:
ein „zu optimistisch“ gewinnt vor „zu pessimistisch“.

## Die 13 Zeilen (Kurzform)

Aufwand: P4 = aus `docs/sensitivitaet.md` übernommen (dort selbst Annahme), A = Annahme dieses Katalogs. Rang = Messreihenfolge P4 (1 bis 5).

| Nr | Größe (Einheit) | Vorhersage | Herkunft | Schwelle „Modell stimmt“ | Konsequenz bei Versagen | Aufwand / Rang |
|---:|---|---|---|---|---|---|
| 1 | Tiefenrauschen (mm) | Ensenso σ = 0,219 mm·z²: 0,147 mm (0,82 m), 0,219 (1,0 m), 0,315 (1,20 m). D405 σ = 20 mm·z²: 0,8 / 1,8 / 3,2 mm bei 0,2 / 0,3 / 0,4 m | Ensenso D (0,123 / 0,219 / 0,46 mm bei 0,75 / 1,0 / 1,45 m, die Form k·z² trifft alle drei); A: Datenblatt-„Genauigkeit“ = Ebenenfit-σ; D405-k = 0,02 1/m ist A | Faktor 0,5 bis 2 (obere Grenze 2× aus dem Entwurf, untere A) | Ensenso zu laut: im Modell bis 3× ohne Wirkung (ST ≤ 0,03), erst Belichtung/Projektor prüfen; D405 ≥ 2×: K bricht, A greift unbemerkt daneben, A für den Teller nicht freigeben | D405 15 min (P4); Ensenso +10 min (A) / Rang 5 |
| 2 | Abstände Mast (m) | Haupt 0,80 / 0,91 / 1,18 m zu R1 (Plattenvorderkante), R2 (Oberkorb-Front, 0,45 m Auszug), R3 (Unterkorb-Front); je Position Tabelle unten | M (Geometrie); Band ±2 cm ist A (Entwurf) | \|gemessen − Modell\| ≤ 20 mm an allen drei Punkten | Geometrie weicht ab: Mastposition mit gemessenen Maßen neu rechnen (`scripts/mast_raster.py`), Betriebsbereich 0,75 bis 1,50 m prüfen | 30 min (A) / nicht in Top 5 |
| 3 | Bildausschnitt (mm) | 954 × 867 mm bei 1 m; Oberkorb-Platzebene bei 0,45 m Auszug rund 830 bis 890 × 750 bis 810 mm; Korbecken im Bild (von 8), 0,225 / 0,45 m: Haupt 8 / 7, höher 8 / 8, Bestand 7 / 6, Ausleger 7 / 7 | D (954 × 867); M (Ecken); A: Punktwolke deckt das volle Arbeitsvolumen ab | Sichtfeld ±5 % (A); Ecken ±1 (A) | Neigung nachstellen (55° / 60° ohne Umbau), Aufnahme wiederholen; fehlende Randplätze gelten als nicht erfasst | 10 min (A) / – |
| 4 | Sichtbarkeit je Platz (Plätze nutzbar, Fläche in %) | Haupt (0,225 / 0,45 m): Gläser 16 / 16, Oberkorb-Teller 8 / 5, Unterkorb-Teller 5 / 0; je Position Tabelle unten; je Platz in der YAML | M (Strahlschnitt mit Verdeckung); A: Nutzbar-Kriterien der Schätzer (Winkel < 60°, Punktzahlen) | je Gruppe und Auszug ±1 Platz; sichtbare Fläche ±15 Prozentpunkte im Mittel (A) | fehlende Plätze namentlich notieren, dort Lage aus dem Slot (Prior B), Kamera nur zur Anwesenheitsprüfung; sonst Mastposition wechseln | 40 min je Position (A) / – |
| 5 | Punktabdeckung (% der Objektpixel mit Tiefe) | Glas Mittel 31 % (P10 bis P90 der Objekte 27 bis 38 %); Teller 29 % trocken / 28 % nass (Bootstrap 25 bis 31 %), Median 18 bis 19 %, P10 bis P90 11 bis 85 % | M mit **angenommenem Fehlermodell** (Glas 50 % Ausfall, 35 % Durchblick, 15 % Reflex; Projektormuster nicht simuliert) – für Glas faktisch A | Mittel über ≥ 8 Objekte in 23 bis 39 % (Glas) bzw. 21 bis 37 % (Teller) (A, ±8 Prozentpunkte) | **Zeile 5 versagt: Glas aus der Slot-Position schätzen, Kamera nur zur Prüfung** (Prior B); Pose aus Kontur plus D405; Teller: Randdicke (Zeile 11) und Winkel (Zeile 4) prüfen | 0 min zusätzlich (Aufnahmen aus Messung 3) / Rang 3 |
| 6 | Erkennung (Trefferquote %, Nachbarverwechslung %) | Baseline-Treffer Glas 55 % (49 bis 61), Tag 86, Küche 66, dunkel 0 (0 bis 5); Teller 45 % (41 bis 50), Tag 52, Küche 54, dunkel 31; Nachbar Glas 9 %, Teller 16 %. Mask R-CNN (COCO): Glas 31 %, Teller 0 % klassenrichtig | M (Renderbilder, 727 Objekte, Wilson 95 %); A: Übertragbarkeit auf echte Bilder (Domänenlücke), „dunkel“ nur über den mittleren Grauwert definiert | Modellrate liegt im Wilson-Intervall der Messung (k/n) | Beleuchtung sicherstellen, Suchfenster auf den Nennort, Glas im Dunkeln nicht einplanen; Teller-Rate < 45 %: Teller aus Slot-Position | 75 min (P4) / Rang 3 |
| 7 | Lagegenauigkeit gegen Referenz (mm) | Glas Median 1,4 / P90 2,5 mm (92 % freigegeben); Teller (5 mm Rand) 3,3 / 4,6 mm (96 von 131); mit erkannter Maske nur 14 % bzw. 3 % freigegeben | M (wahre Maske, ohne Station-Kalibrierfehler); A: Referenzlage ±1 mm, Randdicke 5 mm | Median ≤ 5 mm (Entwurf) und ≥ halber Modellwert | > 5 mm: Station-Pose reicht nicht als Griffpose; erst Zeile 12 und Referenz prüfen, sonst Slot (B) plus D405 | 20 min (A) / – |
| 8 | Wiederholgenauigkeit (mm) | (a) je Punkt = Zeile 1, 0,219 mm bei 1 m; (b) Pose-Streuung über 20 Aufnahmen: Glas 1,8 mm (x 1,1 / y 1,4), Teller 1,5 mm (x 1,2 / y 1,0), Teller-Gier 0,26° | (a) A (zeitlich unabhängiges Rauschen); (b) M, **neu gerechnet** (20 Seeds, einfache Testszene), enthält je Aufnahme neu gezogene Kalibrierfehler, daher obere Schranke | Faktor 0,5 bis 2 (A); erwartete Richtung: zu pessimistisch | zu streuend: mitteln (1/√n), Belichtung/Projektor fest, Stativ prüfen; Zeile 7 erst danach auswerten | 15 min (A) / – |
| 9 | Teller-Lage und -Gier im Ständer (Grad, mm) | Gier ±1°, Lage x/y ±5 mm; Schwelle Gier ≤ 2° | A (Prior); M: B trägt 16/16 bei ±1, ±3, ±6°; Newton: 3° Erfolg, 7° Fehlgriff | größte Gier ≤ 2° und größte Lage ≤ 5 mm; pessimistisch ab Gier ≤ 0,5° (Auflösung) und Lage ≤ 2,5 mm | Gier 2 bis 3°: Prior-Band weiten; > 3°: Prior-Kette B für den Teller verwerfen, Gier messen statt vorgeben; Lage > 10 mm: B beim Teller nicht ohne engeren Alarm | 35 min (P4) / Rang 4 |
| 10 | Glaslage im Slot (mm, Grad) | ±5 mm / ±3°; Schwelle ≤ 8 mm | A (Prior, ungetestet); M: Nennlage allein 16/16 bei ±5 mm, 11/16 bei ±10, 5/16 bei ±15; B 0 unbemerkt in 96 Läufen | größte Lage ≤ 8 mm, Neigung ≤ 3°; pessimistisch ab Lage ≤ 2,5 mm und Neigung ≤ 1° (A) | > 8 mm: B-Abbrüche häufen sich, A („neu hinsehen“, 13 bis 16/16) oder S1 statt B; > 15 mm außerhalb der Modellwelt | 20 min (A), Teil von Messung 4 / P4: im Modell wirkungslos |
| 11 | Randwulst-Dicke der echten Teller (mm) | 5 mm; dann Teller-Pose aus der Station in 96 von 131 Fällen (73 %), bei 12 mm in 0 von 131; Sweep: 3 bis 5 mm 83 bis 100 %, 7 mm 33 bis 100 %, ab 8 mm 0 % | A: 5 mm (Finger-Doku, Auftrag 3 bis 6 mm), 12 mm Szenenannahme ohne Quelle; M: Sweep, nur Bestandsposition; „dicker = schlechter“ folgt aus der Modellgeometrie, nicht aus Sensorphysik | größte Dicke ≤ 6 mm; 6 bis 8 mm Grenzbereich; ≥ 8 mm trägt nicht | **> 8 mm: keine Station-Pose für den Teller**, Teller aus Prior B plus D405, Mast auf Gläser auslegen, Haupt behalten (Fläche bei Auszug 0,225 m); 6 bis 8 mm: Station-Pose nur als Prüfung | 20 min (P4) / **Rang 1** |
| 12 | Station-Kalibrierfehler (mm, Grad) | nach der Kalibrierung 5 mm / 5° (Plan); K trägt bis ≈ 2,5 mm / 5°, ab 7,5 mm bzw. 10° nicht; B bis 20° | A: Planwert, σ 20 mm / 15° aus der Robustheitsstudie; M: Tragfähigkeit je Kette (6 Seeds je Punkt) | Versatz 1,25 bis 5 mm und Drehung 1 bis 5° (untere Grenze A: halber Planwert) | > 5: K nicht einsetzen (A fürs Glas, B für den Teller); ≥ 7,5 mm / 10°: Teller nur mit B; ≥ 15 mm: A beim Teller riskant (unbemerkte Fehlgriffe); Drehung > 20° außerhalb der Rechnung | 45 min (P4) / **Rang 2** |
| 13 | Teller-Gier-Grenze physikalisch (Grad) | Grenze zwischen 3° (Erfolg) und 7° (Fehlgriff); **kein Punktwert** | M: Newton, **je 1 Seed**, nur zwei Punkte; A: Zwischenwert 4° der Sensitivitätsrechnung; Gier-Fehler 6° bei 7° folgt aus 7° − 1° Prior | kein Urteil: der Kameratag misst nur das mechanische Spiel s des Ständers | s ≤ 3°: folgenlos; 3 bis 7°: Newton-Reihe 3 bis 7° vor Einsatz von B; > 7°: B für den Teller nicht einsetzen | 10 min (A), Teil von Messung 4 / Rang 4 |

## Zeilen 2 bis 4 je Mastposition

Quelle: `docs/stationssichtbarkeit.md` und die Rohtabellen des Laufs (Strahlschnitt mit Verdeckung, Zählung „Fläche“, Skala 2). Je Platz (30 Plätze
× 3 Auszüge: sichtbarer Anteil, Platz-z, Einfallswinkel, nutzbar) steht alles in `positionen.<name>.plaetze` der YAML.

| | **Haupt** | Alternative **einfacher Ausleger** | Alternative **höher** | Alternative **Bestand** |
|---|---|---|---|---|
| Kamera (x; y; z) m, Neigung | 0,55; 0,70; 1,25, 55° | 0,55; 0,60; 1,30, 60° | 0,55; 0,70; 1,45, 60° | 0,55; 0,50; 1,35, 60° |
| **Zeile 2** Abstand R1 / R2 / R3 (m) | 0,798 / 0,914 / 1,177 | 0,747 / 0,934 / 1,207 | 0,913 / 1,099 / 1,368 | 0,711 / 0,967 / 1,247 |
| Kamerarahmen-z R1 / R2 / R3 (m) | 0,718 / 0,892 / 1,114 | 0,682 / 0,907 / 1,145 | 0,858 / 1,076 / 1,314 | 0,679 / 0,917 / 1,156 |
| Platz-z bei 0,45 m, Oberkorb / Unterkorb (m) | 0,80–1,06 / 1,03–1,16 | 0,80–1,04 / 1,05–1,18 | 0,98–1,21 / 1,23–1,34 | 0,80–1,05 / 1,04–1,19 |
| **Zeile 3** Sichtfeld Platzebene bei 0,45 m, Gläser / Oberkorb-Teller / Unterkorb-Teller (mm) | 892×811 / 828×753 / 1046×950 | 884×804 / 831×756 / 1063×966 | 1050×954 / 995×904 / 1227×1115 | 886×805 / 841×764 / 1065×968 |
| Korbecken im Bild (von 8), 0,225 / 0,45 m | 8 / 7 | 7 / 7 | 8 / 8 | 7 / 6 |
| **Zeile 4** Gläser nutzbar (von 16), 0,225 / 0,45 m | 16 / 16 | 16 / 16 | 16 / 16 | 12 / 16 |
| Oberkorb-Teller (von 8), Fläche, 0,225 / 0,45 m | 8 / 5 | 8 / 1 | 8 / 2 | 5 / 0 |
| Unterkorb-Teller (von 6), Fläche, 0,225 / 0,45 m | 5 / 0 | 1 / 0 | 1 / 0 | 0 / 0 |
| Teller mit Rand-Zählung (obere Schranke), Ober / Unter, 0,45 m | 8 / 6 | 8 / 6 | 8 / 6 | 7 / 6 |
| Sichtbare Fläche Gläser (Mittel), 0,225 / 0,45 m | 74 % / 87 % | 81 % / 93 % | 80 % / 91 % | 82 % / 97 % |
| σ Ensenso (0,219 mm·z²) Oberkorb / Unterkorb (mm) | 0,14–0,25 / 0,23–0,29 | 0,14–0,24 / 0,24–0,30 | 0,21–0,32 / 0,33–0,39 | 0,14–0,24 / 0,24–0,31 |

Was die Tabelle sagt und was nicht: Die Reihenfolge Haupt > höher > einfacher Ausleger > Bestand gilt nur für die **Flächen-Zählung** der Teller; bei der Rand-Zählung sind Haupt,
höher und Ausleger gleich (1,000). Welche Zählung gilt, entscheidet die Randdicke (Zeile 11). Die Bänder der Zeile 2 (±2 cm) und der Zeile 4 (±1 Platz) sind **Annahmen**.
Die Zahlen des Entwurfs für Zeile 2 (Oberkorb 0,82 bis 0,98 m, Unterkorb 1,02 bis 1,20 m) sind für die Hauptposition durch diese Tabelle ersetzt.

## Was Annahme ist (und nicht gemessen)

* **Prior** Teller-Gier ±1°, Teller-Lage x/y ±5 mm, Teller-z ±5 mm, Glaslage ±5 mm / ±3° (`docs/griff-prior.md`): ungetestet; Zeilen 9 und 10 prüfen sie.
* **Randdicke 5 mm** (Finger-Dokumentation, Auftrag 3 bis 6 mm); die 12 mm der Renderszenen sind eine Szenenannahme ohne Quelle. Die Wirkungsrichtung „dicker = schlechter“ ergibt sich aus der Modellgeometrie (Zylinderhöhe, Stababstand).
* **Station-Kalibrierfehler:** Planwert 5 mm / 5° „nach Kalibrierung“; 20 mm / 15° der Robustheitsstudie sind Rechenwerte, kein Messwert; Fehler als fester Betrag mit zufälliger Richtung, nicht Gauß.
* **Newton-Gier-Grenze:** zwischen 3° und 7°, je ein Seed; der Zwischenwert 4° der Sensitivitätsrechnung ist eine Annahme.
* **Nutzbar-Kriterien** der Schätzer (Winkel 60°, 30 Konturpixel, 60 Tiefenpunkte, Konturbogen 40°), das Fehlermodell der Tiefe (Glas 50/35/15 %, Nässe 5 %), die D405-Konstante k = 0,02 1/m.
* **Fenstergrößen** in der Spalte „Schwelle“, soweit sie nicht aus dem Entwurf stammen (z. B. ±5 % Sichtfeld, ±8 Prozentpunkte Abdeckung, ±15 Prozentpunkte sichtbare Fläche, untere Grenzen 0,5×).
* **Aufwände** außer den fünf P4-Werten (20 / 45 / 75 / 35 / 15 min, selbst Annahmen).
* **Domänenlücke:** Erkennungs- und Abdeckungszahlen stammen aus Isaac-Renderbildern; Projektormuster und Stereo-Matching sind nicht simuliert.

## Nicht vorhersagbar: „unbekannt“-Zeilen

Hier steht bewusst **keine Zahl**. Das Skript ordnet den Messwert in einen Ausgang ein und nennt die Konsequenz.

| Nr | Größe | Warum keine Vorhersage | Messgröße | Ausgang A | Ausgang B | Ausgang C |
|---|---|---|---|---|---|---|
| u1 | **Nasse Optik** (Wasserfilm, Tropfen, Dampf) | Modell kennt nur 5 % Zufallsausfall und Tropfen als Geometrie; die Renderdaten widersprechen sich (Baseline nass 61 % > trocken 52 %, Mask R-CNN nass 18 % < trocken 40 %) | Erkennungsrate nass − trocken (Prozentpunkte) | ≥ −10: Nässe wie trocken planen | −10 bis −30: nur mit nassen Raten planen, Prior B bevorzugen | < −30: im Nassen Lage aus dem Slot, Kamera nur zur Prüfung; Abtropfpause prüfen |
| u2 | **Projektorreflexe im Metallkorb** | Projektormuster und Stereo-Matching sind nirgends simuliert; Menge der Fehlpunkte am Draht unbekannt | Anteil Ausreißerpunkte > 10 mm neben der Ebene im Korbbereich (%) | < 2 %: ignorieren | 2 bis 10 %: Korbdraht per Maske ausblenden, Punkte nur aus der Objektmaske | > 10 %: Winkel/Position ändern, Belichtung senken; sonst Ensenso im Korb nur für Anwesenheit |
| u3 | **Ensenso auf transparentem Glas** | Modell nimmt 50 / 35 / 15 % an; das Isaac-Tiefenbild sieht Glas ideal und ist bewusst nicht verwendet; der Modellwert 31 % in Zeile 5 ist Folge dieser Annahmen | Punktabdeckung Glas trocken, Mittel über ≥ 8 Gläser (%) | ≥ 25 %: Tiefe nutzbar wie im Modell | 5 bis 25 %: Pose aus Kontur (RGB) plus D405 | < 5 %: **Glas aus der Slot-Position schätzen, Kamera nur zur Prüfung** |

Die Schwellen 10 / 30 Prozentpunkte, 2 / 10 % und 5 / 25 % sind Entscheidungsschwellen dieses Katalogs (A), keine Modellwerte.

## Abweichungen und Vorbehalte

* **Mast-Umbau:** P4 stellt den Mast-Umbau (≈ 120 min) zurück, weil der Mastort im Modell wirkungslos ist; dabei fehlen Verdeckung und Einfallswinkel im Modell. P1 empfiehlt zwei Montagen (Haupt und einfacher Ausleger) wegen der Randdicke. Das Messprotokoll löst das über das Stativ (siehe dort).
* **Zeile 7 und 8** sind in P4 nicht bewertet; Zeile 8b ist die einzige Zahl dieses Katalogs, die nicht aus einem Dokument übernommen, sondern neu gerechnet wurde (20 Seeds auf den Testszenen von `tests/test_robustheit.py`, einfache Szene, 20 von 20 Läufen freigegeben).
* **Zeile 11** gilt für die Bestandsposition und die wahre Maske; die Höhe (96 von 131) überträgt sich nicht, die Richtung ja (`docs/stationssichtbarkeit.md`).
* **Zeile 13** ist am Kameratag nicht prüfbar (kein Greifversuch). Sie steht im Katalog, weil sie die Konsequenz der Zeile 9 begrenzt.
* Stichproben des Modells sind klein (6 bis 16 Seeds je Zeile, Newton je 1 Seed); Differenzen von 1 bis 2 Läufen sind kein Beleg.

## Verwendung

```
scripts/kameratag_auswerten.py <messdatei.yaml> [--basis <aufnahmen>] [--out <ordner>]
```

Messdatei, Einleseformat der Punktwolken und Entscheidungsregeln: `docs/kameratag-messprotokoll.md`; Beispiel mit erfundenen Werten: `beispiele/kameratag-messung-beispiel.yaml`.
