# Hardware-Auswahl: Ensenso-Kamera und Zubehör für den igus ReBeL 6 DOF

Stand: 29.10.2026. Kaufempfehlung mit Optionen; **nichts ist bestellt**.
Preise sind Listenpreise aus Webshops, **netto zzgl. MwSt. und Versand**,
Ensenso-Preise sind „ab“-Preise des Herstellers (Grundkonfiguration). Jede Zahl
hat eine Quelle `[Qn]` (Liste in §10, alle abgerufen am 29.10.2026). „Annahme“
heißt: kein Datenblattwert gefunden. „offen“ heißt: nicht ermittelt, vor dem
Kauf anfragen.

Hinweis zu den Quellen: Die Produktseiten von IDS (`en.ids-imaging.com`) liegen
hinter einer Bot-Prüfung und waren nicht direkt lesbar. Ensenso-Werte stammen
deshalb aus dem Ensenso-Handbuch (Hersteller Optonic), aus IDS-Datenblättern
bei Distributoren und aus dem Suchmaschinen-Auszug der IDS-Seiten.

## 0. Kurzfassung

| Punkt | Hauptvariante | Sparvariante |
|---|---|---|
| Kamera | **Ensenso B57-4, Farbe** (5 MP RGB-Stereo, 1,10 kg), ab 7.950 € [Q1][Q2] | **Ensenso N46-604-16-BL** (2,3 MP mono, 0,55 kg), N-Serie ab 5.160 € [Q1][Q5] |
| Montage | fest neben dem Roboter, **nicht am Flansch** (Eye-to-Hand, Mast auf dem Schlitten der 7. Achse) | wie Haupt; Flanschmontage nur als Notlösung (Lastkurve, §6) |
| Greifer | igus ReBeL-Greifer 0-LCA-GRI-0100 (Öffnung 105 mm, DIO), 1.954,07 € [Q20] | wie Haupt |
| 7. Achse | Bundle ReBeL 6 DOF + drylin ZLW-20200, Hub 1000 mm, iRC-Version, 10.499,07 € [Q17] | wie Haupt |
| Summe bekannter Posten | **20.403,14 €** | **17.613,14 €** |
| offen (Angebot nötig) | PoE++-Injektor, Kalibrierplatte, Kameramast, Podest 0,65 m, Sicherheitstechnik | dieselben |

Begründung in einem Satz je Thema:
- **Gewicht entscheidet die Montage:** Der ReBeL trägt 2 kg nur bis 400 mm
  Hebelarm, bei 500 mm noch 1 kg, darüber nichts mehr [Q15]. Die Greifposen der
  Simulation liegen bei 350–451 mm waagerecht bzw. 414–502 mm räumlich (§6). Eine B57 am Flansch ließe für Greifer
  und Glas keine Reserve.
- **Glas:** Keine Ensenso liefert auf klarem Glas verlässliche Tiefe; der
  Hersteller sagt das selbst [Q11][Q13]. Gläser werden deshalb aus dem 2D-Bild
  plus Modellwissen (Glasmaße, Korbslots, Korbebene aus 3D) lokalisiert (§3.4).
  Dafür ist die B57 mit Farbbild aus derselben Perspektive wie die Tiefe die
  bessere Wahl als die monochrome N46.
- **Vor dem Kauf** bietet Optonic eine kostenlose Machbarkeitsanalyse mit
  optionaler Leihkamera an [Q14]. Die sollte mit echten Gläsern, Tassen und
  Tellern im Korb gemacht werden, bevor eine Kamera gekauft wird.
- Die bisherige Annahme **RealSense D405 Eye-in-Hand** ist ersetzt: Reichweite
  7–50 cm [Q30], kein Projektor, auf Glas ebenso schwach. Sie bleibt höchstens
  als späterer Zusatz am Handgelenk für die Nahkontrolle denkbar.

## 1. Anforderungen aus der Simulation

| Größe | Wert | Herkunft |
|---|---|---|
| Objekte | Gläser Ø 75 × 110 mm, 250 g, kopfüber im Oberkorb; später Tassen und Teller | `docs/spuelmaschine.md` |
| Korb | Oberkorb 525 × 475 mm, Unterkorb 525 × 515 × 140 mm | `config/spuelmaschine.yaml` |
| Arbeitsabstand Kamera | 0,25–0,8 m | Auftrag |
| Aufbau | Schiene 1,0 m Hub senkrecht zur Front, Podest 0,65 m (mit Seitgriff und Zwischenablage ~0,40 m) | `docs/spuelmaschine.md` §4, Umgreif-Befund im Ausräum-Ablauf |
| Greifer | Hub 5–105 mm, Greifkraft 10 N je Finger gewählt (20 N Greifdemo) | `config/robot.yaml`, Umgreif-Befund |
| Rechner | NVIDIA Jetson AGX Orin, ROS 2 | Auftrag |

## 2. Ensenso-Portfolio

Alle Ensenso außer S10 arbeiten mit Stereo und Musterprojektor („projected
texture stereo“) [Q3][Q4]. Gemeinsam: Ensenso SDK für Linux x64 und als
arm64-Paket für Jetson (4.3.1057), auf Jetson wird CUDA automatisch benutzt;
nicht verfügbar auf Jetson sind Ensenso Engage und die Befehle
`EstimateDisparitySettings`, `FitPrimitive`, `PartFinder` [Q7][Q8]. Offizieller
ROS-Treiber `ensenso_driver` (BSD-3), v2.1.3 vom 17.06.2025 mit B-Serie; die
CI baut ROS 2 Humble und Jazzy (und Foxy, ROS 1 Noetic); die ROS-2-Pakete
werden per Skript aus dem ROS-1-Code erzeugt [Q9][Q10]. Ein Isaac-Sim-Modell
von IDS/Optonic gibt es nicht (nichts gefunden); CAD-Modelle stellt Ensenso
bereit [Q26].

### 2.1 Vergleich

| Modell | Projektor, Sensor | Farbe | Arbeitsabstand | z-Genauigkeit (Datenblatt) | Sichtfeld | Maße, Gewicht | Schnittstelle, Strom | IP | Preis ab | Quelle |
|---|---|---|---|---|---|---|---|---|---|---|
| **B57-4** (B-Serie) | 200-W-LED, FlexView 3; 2 × 5 MP (2472 × 2064), Basis 75 mm, f = 4 mm, Vergenz 7° | ja (GN-Variante: RGB-Stereo, grüner Projektor) oder mono (BL) | 210–2000 mm; GN laut Handbuch max. 800 mm | 0,138 mm @ 300, 0,383 @ 500, 0,751 @ 700, 0,981 @ 800 mm | 403 × 380 mm @ 300, 621 × 633 @ 500, 949 × 1012 @ 800 mm | 120 × 56 × 104 mm, **1,10 kg** | 1 GigE; 24 V DC oder PoE++ (802.3bt) 40 W | 65/67 | **7.950 €** | [Q1][Q2][Q6] |
| **N46-604-16-BL** (N4x, Kunststoff) | LED blau 465 nm, FlexView; 2 × 2,3 MP (1936 × 1216), Basis 100 mm, f = 6 mm, Vergenz 4° | nein | 370–800 mm (N4x allgemein ab 330 mm) | wie N36-604-16 (gleiche Optik, *Annahme*): 0,117 @ 400, 0,183 @ 500, 0,264 @ 600, 0,359 @ 700 mm | 435 × 285 @ 400, 565 × 356 @ 500, 751 × 499 @ 700 mm | 193 × 52 × 60 mm, **0,55 kg** | 1 GigE; 24 V DC oder PoE Klasse 3 (≤ 12,95 W) | 65/67 | N-Serie **5.160 €** (Einstieg; Preis N46 offen) | [Q1][Q4][Q5][Q16] |
| N36-604-16 (N3x, Alu) | wie N46 | nein | 370–800 mm | 0,183 mm @ 500 mm (s. o.) | wie N46 | 192 × 50 × 52 mm, 0,65 kg | wie N46 | 65/67 | N-Serie 5.160 € | [Q4][Q5] |
| **C57-6-S** (C-Serie) | 200-W-LED, FlexView 3; 2 × 5 MP (2472 × 2064) + RGB 2 MP, Basis 240 mm, f = 6 mm, Fokus 975 mm | ja (eigener RGB-Sensor) | **750–1500 mm** (Datentabelle bis 1450 mm) | 0,123 @ 750, 0,219 @ 1000, 0,460 @ 1450 mm | 954 × 867 mm @ 1000 mm | 290 × 58 × 100 mm, 1,16 kg | 1 GigE; 24 V oder PoE++ 90 W | 65/67 | 8.900 € (C-Serie ab) | [Q44][Q45][Q1][Q6][Q27] |
| C57-8-S / C57-12-S (C-Serie) | wie C57-6-S, f = 8 bzw. 12 mm, Fokus 975 mm | ja | **850–1100 mm** / **900–1100 mm** | 0,123 @ 860 … 0,201 @ 1100 (8 mm); 0,111 @ 1000 (12 mm) | 738 × 657 / 502 × 440 mm @ 1000 mm | 290 × 58 × 100 mm, 1,16 kg | wie C57-6-S | 65/67 | wie C57-6-S | [Q44][Q45] |
| C57-6-M (C-Serie) | wie C57-6-S, Basis 455 mm, Fokus 1850 mm | ja | **1100–5000 mm** | 0,196 @ 1304 … **0,377 @ 1807 mm** (Datentabelle endet bei 1807 mm) | **1321 × 881 mm @ 1304 mm** | 506 × 58 × 100 mm, **1,66 kg** | wie C57-6-S | 65/67 | wie C57-6-S | [Q44][Q45] |
| CR-Serie | wie C, Tiefe auf der Kamera gerechnet, 8 MP RGB | ja | wie C | wie C | wie C | ab 1,16 kg | 1 GigE, PoE++ | 65/67 | 10.250 € | [Q1][Q3][Q6] |
| X30/X36 | 100-W-Projektor, zwei uEye-Kameras modular, 1,6/5 MP | nein | bis > 5 m | modellabhängig | bis 8 m³ | 1,1 kg (1,7 kg mit Basisverlängerung) | 1–2 GigE | optional 65/67 | 9.360 € | [Q1][Q3][Q28] |
| XR30/XR36 | wie X, Rechnung auf der Projektoreinheit | nein | bis > 5 m | modellabhängig | bis 8 m³ | 1,6 kg (2,2 kg) | 1 GigE | 65/67 | 12.000 € | [Q1][Q3][Q28] |
| S10 | IR-Laserpunkte 835 nm, KI-Triangulation, 1,6 MP | nein | 500–3000 mm | 2,4 mm @ 1 m | 60° × 50° | 130 × 45 × 44 mm, 0,565 kg | GigE, PoE Kl. 3 | 65/67 | — **abgekündigt**, letzte Bestellung 30.06.2026 | [Q29][Q12] |
| *zum Vergleich:* IDS Nion (ToF, keine Ensenso) | iToF 1,2 MP | nein | — | — | — | — | GigE | 67 | 1.499 € | [Q1] |

Weitere Preise von einem US-Händler (USD, nur zur Plausibilität): N46 7.898 $,
N36 9.302 $, B57 11.993 $ [Q31].

Die z-Genauigkeit im Datenblatt ist ein Geometriewert (Kamerageometrie), keine
gemessene Genauigkeit auf realen Oberflächen [Q32]. Auf Glas gilt sie nicht (§3).

### 2.2 Bewertung für Räumwerk

- **B57-4 (Farbe):** kürzester Arbeitsabstand der Familie, großes Sichtfeld
  schon bei 0,5 m (ganzer Korb im Bild), Farbbild exakt aus der Tiefenperspektive
  (wichtig für 2D-Glaserkennung und für Tassen/Teller-Klassifikation), PoE++ an
  einem Kabel. Nachteil: 1,1 kg, PoE++ braucht 802.3bt-Injektor oder 24 V.
  Farbvariante laut Handbuch nur bis 800 mm [Q6] — passt zum Bereich, aber
  ohne Reserve.
- **N46-604-16-BL:** leichteste Ensenso (0,55 kg), FlexView, bessere
  z-Werte bei 0,5–0,7 m als B57 (größere Basis 100 mm), aber **kein Farbbild**
  und bei 0,5 m nur 356 mm Sichtfeld in y (Korb 475 mm tief → Abstand ≥ 0,65 m
  oder zwei Aufnahmen).
- **C/CR/X/XR:** als Kamera für den einen (Ober-)Korb ohne Vorteil (schwer, teurer,
  keine Besserung auf Glas) — dafür bleibt die B57-4 die Wahl. Für **beide Körbe**
  ist die C-Serie dagegen nötig, und dort entscheidet der **Betriebsabstand je
  Variante** (§2.3): nur das **C57-6-S** (750–1500 mm) passt; C57-8-S (850–1100 mm),
  C57-12-S (900–1100 mm) und C57-6-M (1100–5000 mm) sind zu kurz oder zu weit.
  C67 ist der Nachfolger der C57.
- **S10:** abgekündigt. Verworfen.

### 2.3 Beide Körbe (Ober- und Unterkorb) mit einer festen Kamera

Soll eine feste Kamera beide Körbe unterstützen (der Mensch zieht je einen Korb heraus,
Oberkorb z 0,42–0,64 m, Unterkorb z 0,13–0,27 m), scheidet die B57-4 Farbe als *einzige*
Kamera aus: ihr Arbeitsbereich endet bei 0,80 m. Am hohen Mast (0,55; 0,40; 1,15 m) sieht
sie den Oberkorb vollständig, den Unterkorb zu 0 % (0,9 m Abstand); tiefer am selben Mast
(z 0,90–0,95 m) nimmt sie dem Arm ein Glas und einen Teller weg (Erreichbarkeit 7/16, 7/8).
Erst ein tiefer, weit auskragender Ausleger (Kamera (0,30; 0,55; 0,90 m), y 0,55 m) bringt
beide Körbe mit der B57-Farbe ins Bild (Gläser 97 % sichtbar / 100 % ≤ 5 mm, Dessertteller
92 % / 100 %, Unterkorb-Teller 100 % / 100 %, erreichbarkeitsneutral), hängt aber tief über
der offenen Maschine und hat am 0,80-m-Ende keine Reserve.

**Die C-Serie: entscheidend ist der Betriebsabstand je Variante.** Der frühere Eintrag
„C57-S, 0,50–5,00 m" war eine Händlerbandbreite über *alle* Fokusvarianten, nicht der
Betriebsabstand eines lieferbaren Modells. Laut IDS-Datenblatt (Stand 2024-04-24, [Q44])
gilt je Bestellvariante: **C57-6-S (Art. 1009348) 750–1500 mm**, C57-8-S (1009349)
850–1100 mm, C57-12-S (1009350) 900–1100 mm, C57-6-M (1009366) 1100–5000 mm. Am Mast aus
dem Vorlauf (Kamera (0,55; 0,40; 1,15) m über der Korbfront) liegen die Objekte nur
0,61–1,00 m entfernt: die oberste Glaskante (≈ 0,61 m) **unterschreitet** die
750-mm-Untergrenze, der Oberkorb fällt aus dem Betriebsbereich (Sichtbarkeit 0 %). Der
Mast muss weiter weg. Mit dem C57-6-S an **(0,55; 0,50; 1,35) m** liegen Oberkorb
0,82–0,98 m und Unterkorb 1,02–1,20 m – beide im Bereich 750–1500 mm (≥ 70 mm zur Unter-,
≥ 300 mm zur Obergrenze), und die Optik bleibt erhalten (Zahlen der Tabelle aus dem früheren
Rechenmodell **ohne Verdeckung und ohne Einfallswinkel der Teller**, Teller nach der
Rand-Zählung; als Stand bewahrt, nicht mehr die Entscheidungsgrundlage):

| Kamera / Mast (x; y; z) m | Abstand Oberkorb | Abstand Unterkorb | Oberkorb Gläser sicht / erk | Oberkorb Teller sicht / erk | Unterkorb Teller sicht / erk | Erreichbarkeit |
|---|---|---|---|---|---|---|
| C57-6-S, (0,55; 0,40; 1,15) alt | 0,61–0,77 m | 0,81–1,00 m | **0 %** (unter 750 mm) | 30 % / 0 % | 100 % / 83 % | 8/16, 8/8, 4/4 |
| C57-6-S, (0,55; 0,50; 1,35) *(früheres Modell ohne Verdeckung, Rand-Zählung)* | 0,82–0,98 m | 1,02–1,20 m | 100 % / 100 % (1,6 mm) | 100 % / 100 % (1,3 mm) | 100 % / 67–83 % (0,7 mm) | 8/16, 8/8, 4/4 |

**Neuer Stand (Mastposition mit Verdeckung und Einfallswinkel, `docs/stationssichtbarkeit.md`):**
Hauptposition (0,55; 0,70; 1,25) m, 55°; als Alternative „einfacher Ausleger“ (0,55; 0,60; 1,30) m, 60° (0,10 m weniger Ausleger,
gleiche Gläser und gleiche Rand-Zählung, aber Teller-Fläche schwächer: Punktzahl 0,549 gegen 0,743); welche gilt, entscheidet die Randwulst-Dicke am Kameratag (zwei Messreihen). Erreichbarkeit
unverändert 8/16, 8/8, 4/4. Die frühere Position (0,55; 0,50; 1,35) ist dort die
„Alternative weiter hinten (Bestand)“: Gläser 12/16 bei 0,225 m und 16/16 bei 0,45 m,
Oberkorb-Teller (Fläche) 5/8 und 0/8, Unterkorb-Teller 0/6 und 0/6 – die oben genannten
„100 %“ der Oberkorb-Teller sind **vom schmalen Tellerrand getragen**, nicht von der
Tellerfläche (Rand-Zählung, 0,45 m: 7/8). Ob die Teller aus der Ensenso eine Pose liefern,
hängt an der Randwulst-Dicke der echten Teller (5 mm trägt, 12 mm nicht: `docs/kameratag-p3.md`)
und ist eine Kameratag-Messgröße.

Damit ist das **C57-6-S (Art. 1009348)** die Kamera, die den Betriebsabstand für beide Körbe
einhält (Gläser beider Körbe liegen im Bereich); **für die Teller in beiden Körben gilt das nur
unter der Randwulst-Annahme** (Flächen-Zählung: Unterkorb bei vollem Auszug 0/6 an jeder
gerechneten Position). Die erhöhte Montage
ist erreichbarkeitsneutral (kein Slot, kein Teller verloren, Ablage 4/4) und kostet rund
950 € mehr als die B57-4. Zwei B57-4 (je eine über einem Korb) liefern die besten
Einzelwerte, kosten aber rund 2 × 7.950 €. Die monochrome N46 hat kein Farbbild und findet
klares Glas nicht (0 %); sie bleibt nur für Teller brauchbar. Sind beide Körbe gleichzeitig
ausgezogen, verdeckt der Oberkorb den Unterkorb vollständig – es wird je ein Korb
herausgezogen. Reicht der Bereich einer Standardvariante nicht, baut IDS laut
Kamera-Selector (Optonic/IDS, [Q45]) Arbeitsbereich und Abstand nach Bedarf; die
Standard-Varianten decken unser Volumen aber ab.

**Vorbehalte zu den Zahlen.** Die Glasquote (100 % auf ≤ 5 mm) stammt aus einer ideal
angenommenen Farbsilhouette mit ±1 px Randunsicherheit; an echtem nassem Geschirr ist sie
schlechter, das muss eine Leihkamera klären. Die Tellerquote (67 % über 8 Seeds, 83 % über 2)
hängt vom Blickwinkel ab; einzelne Teller liegen mit rund 10 mm über der 5-mm-Grenze. Der
Abstand wird als Tiefe im Kamerarahmen gemessen (Betriebsabstands-Grenzen 0,75/1,50 m des
Datenblatts). Verdeckung durch den Roboterarm in Greifposen ist nicht gerechnet – geprüft
ist nur, dass die Kamera die Erreichbarkeit nicht verschlechtert. Die Optikzahlen sind mit
dem korrigierten Datenblattmodell (Betriebsabstand, Z-Genauigkeit, Arbeitsvolumen)
gerechnet.

**Kamera über der Maschine statt am Mast.** Eine feste Kamera auf/über der Arbeitsplatte
über der Maschine wurde gerastert (x 0,05–0,60 m, y −0,15…+0,10 m, z 0,95–1,45 m, Neigung
30–75° gegen die Waagerechte, Blick jeweils zur Korbmitte; C57-6-S, gleiches Werkzeug wie die
Mastzahlen, aber noch mit der früheren Bereichsannahme 0,5–5 m – die Optikzahlen gelten nur,
soweit die wahren Abstände in 750–1500 mm liegen; Ursache: die Vorstudien rechneten mit einer
Brennweite von 1739 px, das echte Arbeitsvolumen der C57-6-S (954 × 867 mm bei 1 m, 3,45 µm
Pitch) entspricht rund 2590 px – das alte Sichtfeld war also ~35 % zu weit, die Rasterung
damit optisch zu optimistisch). Optisch erreicht sie den Mast rechts nur **mittig und auf Arbeitshöhe**:
(x 0,35; y 0,05–0,10; z 1,15 m; 60°) ergibt Gläser 100 %, Dessertteller 83 %,
Unterkorb-Teller 83 % (6 Rauschseeds) – dieselben Zahlen wie der Mast rechts. Diese Lage
liegt aber in der Reichweite des Arms: mit konservativem Kamerakörper nimmt sie dem Arm die
Teller (Erreichbarkeit 0/16 Slots, 0/8 Teller; die Ablage bleibt nur beim konservativen
Körper mit y 0,10 bei 4/4, bei y 0,05 sind es 0/4; ohne Kamera 8/16, 8/8, 4/4).
Am rechten Maschinenende (x 0,60) ist der Armverlust klein (8/16, 8/8, 3/4 bei schlankem
Kamerakörper), dafür fällt die Optik (Dessertteller 50 %, Unterkorb 67 %). Eine hohe, voll
erreichbarkeitsneutrale Montage (z 1,45 m) verliert den Unterkorb (33 %) und die
Dessertteller (17 %); bei x 0,60 ist es umgekehrt (Dessertteller 83 %, Unterkorb 0 %).
Die Desserttellerquote liegt bei flacher Neigung über der Maschine geometrisch bei 83 %
(der hinterste Teller im ausgezogenen Korb liegt außerhalb des Sichtbereichs). Steiler
(70–75°) holt ihn ins Bild, aber **keine** Pose bringt die Dessertteller über mehrere Seeds
hinweg über 83 % – 83 % ist der höchste belastbare Wert der 6-Seed-Läufe; einzelne Posen
mit 66–75° zeigen 100 % und kosten dafür den Unterkorb (dort 50 %). Beide
Körbe zusammen bleiben bei 100/83/83 (wie am Mast rechts). Der ruhige
Mast rechts bleibt damit die bessere Lösung; über der Maschine löst keine Lage Optik und
Erreichbarkeit gleichzeitig.

## 3. Glas und Nässe

### 3.1 Was der Hersteller sagt

- Ensenso-Handbuch: „Reflective and transparent surfaces pose problems for
  optical measurements, thus also for the Ensenso system.“ Empfehlung: Kamera
  nicht senkrecht auf spiegelnde Flächen richten, sondern um die Basislinie
  drehen, damit der Projektorreflex nicht in die Kameras fällt [Q11].
- Flächen, die mehr als ~60° von der Frontalebene abweichen, werden nicht
  rekonstruiert; ein Zylinder (Flasche) ist mit einer Kamera nur auf ~2/3 des
  Durchmessers erfasst [Q11]. Für ein stehendes Glas heißt das: die Wand ist
  von oben fast gar nicht, von schräg teilweise sichtbar — auch bei undurchsichtigem Material.
- Optonic (Hersteller) auf der Seite zur Machbarkeitsanalyse: „Reflections,
  fine edges, holes, transparencies … this is exactly where holes, noise, and
  outliers appear in the point cloud.“ [Q14]
- FlexView (mehrere Aufnahmen mit verschobenem Muster, N36/N46, B57, C) erhöht
  Detailauflösung und Robustheit auf dunklen, glänzenden oder spiegelnden
  Flächen [Q11][Q13]. Eine Aussage zu **transparenten** Objekten macht der
  Hersteller nicht.
- Ensenso-Forum: Suche nach „transparent“ und „glass“ ergab keinen Beitrag zu
  transparenten Objekten (nur Kalibrierplatten aus Glas) [Q33].

### 3.2 Was die Forschung sagt

- Handelsübliche 3D-Sensoren liefern auf transparenten Objekten verrauschte
  oder verzerrte Tiefe, oft die Tiefe des Hintergrunds hinter dem Glas
  (ClearGrasp) [Q34]. Ein Review unterscheidet „Typ I“ (Hintergrundtiefe durch
  das Glas) und „Typ II“ (fehlende Tiefe) [Q35].
- Abhilfen aus der Literatur: Tiefenvervollständigung aus RGB + Rohtiefe
  (ClearGrasp, TransCG) [Q34][Q36], gelernte Stereo-Netze speziell für Glas
  (ClearDepth) [Q37] oder allgemein (FoundationStereo, mit Beispielen auf
  Glas; Anleitung für Jetson über Isaac ROS) [Q38][Q39], Polarisationskameras
  zur Glassegmentierung [Q40]. IDS hat Polarisationskameras (Sony IMX250MZR)
  im Programm [Q41].

### 3.3 Nässe

- Wasser auf Glas und Geschirr gibt zusätzliche Spiegelpunkte; die Kamera
  selbst ist IP65/67 und damit unkritisch [Q2][Q4].
- **Der ReBeL ist nicht wasserfest** (igus: „Wasserfestigkeit: nein“, IP-Klasse
  ohne Angabe) [Q18][Q15]. Tropfwasser vom Geschirr darf nicht auf Gelenke und
  Fuß laufen; Greiferfinger mit gummierten, wasserabweisenden Belägen.
- In der Simulation die Reibung nass niedriger ansetzen (heute Annahme).

### 3.4 Wie Räumwerk ohne gute Glastiefe auskommt

1. **3D für das, was 3D kann:** Korb (Gitter, Boden, Ränder), Tür, Teller und
   Tassen (undurchsichtig) aus der Punktwolke; daraus Korbpose und -ebene.
2. **Gläser aus 2D + Modell:** Glasrand bzw. -silhouette im Bild erkennen
   (B57: RGB aus derselben Perspektive; Aufnahme zusätzlich ohne Projektor),
   Mittelpunkt-Sichtstrahl mit der bekannten Höhe schneiden (Korbboden aus 3D
   + Glashöhe aus der Konfiguration) → Glaslage. Kopfüber stehende Gläser
   haben den Rand unten am Korbboden — die Höhe ist damit bekannt.
3. **Bekannte Slots:** Die Glashalter-Slots sind Teil des Maschinenmodells;
   die Erkennung muss nur „Slot belegt ja/nein + Versatz“ liefern.
4. **Löcher als Hinweis:** Fehlende Tiefe an einer Stelle, an der der
   Korbboden sichtbar sein müsste, ist selbst ein Glas-Indiz (Typ II).
5. **Aufnahmetechnik:** FlexView, Kamera um die Basislinie geneigt [Q11],
   Belichtungsreihen; feste Kamera schräg von oben, nicht senkrecht.
6. **Experiment (offen):** gelerntes Stereo (FoundationStereo) auf den
   Rohbildern der Ensenso-Stereokameras; Laufzeit auf dem Orin vorher messen.
7. **Prüfung vor dem Kauf:** Machbarkeitsanalyse mit Leihkamera [Q14] mit
   eigenen Gläsern (klar, nass, kopfüber im Korb).

## 4. Montage

| Option | Oberkorb | Unterkorb | Tür/Verdeckung | Nutzlast | Kalibrierung | Bewertung |
|---|---|---|---|---|---|---|
| **Eye-to-Hand, Mast auf dem Schlitten der 7. Achse** (Empfehlung) | von schräg oben, 0,5–0,8 m | ausgezogen auf der Tür sichtbar, wenn der Oberkorb eingeschoben ist | Arm verdeckt beim Greifen → erst schauen, dann greifen | belastet den Flansch nicht | Kamera fest zum Roboterfuß: Ensenso-Hand-Auge-Kalibrierung „fixed“ [Q24]; Achsfehler der 7. Achse (±1,5 mm) geht nicht ein | gut; Schlittenlast (ReBeL 8,2 kg + Mast + Kamera) bei igus erfragen (offen) |
| Eye-to-Hand fest am Podest-Ende | wie oben | wie oben | wie oben | keine | „fixed“; Weltlage des Roboterfußes hängt an der 7. Achse (±1,5 mm [Q17]) | gut, einfacher Halter; etwas ungenauer |
| Eye-to-Hand an Küche/Arbeitsplatte | von oben/vorn | gut | Tür und Front im Weg je nach Ort | keine | „fixed“ | nur wenn Montage in der Küche erlaubt |
| Eye-in-Hand am Flansch | beliebige Blickrichtung, nah | gut | keine Verdeckung durch den Arm | **kritisch** (§6), Kabel am Handgelenk | „moving“ [Q24] | nur N46, nur mit leichtem Greifer |
| Beides (fest + leichte Handkamera) | | | | | | später, falls Nahkontrolle nötig |

Hand-Auge-Kalibrierung: `CalibrateHandEye` kennt beide Aufbauten (Kamera fest
oder am Roboter) und braucht eine Ensenso-Kalibrierplatte; für B57-4 nennt das
Datenblatt 390 × 390 mm, 48 mm Raster [Q2], für N36-604-16 200 × 200 mm, 24 mm
[Q5]. Ob die Platte im Lieferumfang ist: offen.

## 5. Zubehör für den ReBeL

### 5.1 Schnittstellen des ReBeL 6 DOF

| Merkmal | Wert | Quelle |
|---|---|---|
| Nutzlast | 2 kg bis 400 mm Hebelarm, linear auf 1 kg bei 500 mm, Kurve endet bei 500 mm | [Q15] |
| Gewicht, Reichweite | 8,2 kg; 664 mm max., 400 mm nominal; ±1 mm | [Q15][Q18] |
| Werkzeugflansch | 6 × 60° M3 × 0,5, max. Gewindetiefe 4 mm, Ø 43 mm | [Q15] |
| Werkzeug-I/O | **an Achse 4** (nicht am Flansch): 2 DI, 2 DO, 24 V, max. 0,75 A | [Q15] |
| I/O am Fuß | 7 DI, 7 DO, 24 V, max. 1,5 A | [Q15] |
| Ethernet | 1 Port: Modbus TCP, CRI (TCP, Port 3920, Standard-IP laut Datenblatt) | [Q15][Q21][Q22] |
| Strom | 210–230 V AC Tischnetzteil, 24 V; Ø 40 W, max. 288 W | [Q15] |
| Wasser | nicht wasserfest; IP-Klasse ohne Angabe | [Q15][Q18] |
| Preis ReBeL 6 DOF allein | 4.970,00 € (REBEL-6DOF-03) | [Q18] |

### 5.2 Greifer

| Greifer | Hub | Kraft | Gewicht | Ansteuerung | ReBeL dokumentiert | Preis | Eignung |
|---|---|---|---|---|---|---|---|
| **igus ReBeL-Greifer 0-LCA-GRI-0100** | 100 mm Greifbereich, max. 105 mm offen | **offen** | **offen** | DIO über Tool-I/O Achse 4 | ja, im ReBeL-Design | 1.954,07 € (igus.de), 1.954,07 € (RBTX) | passt zur Simulation (5–105 mm); deckt Gläser, Tassen und Tellerränder ab. Kraft und Gewicht vor Kauf erfragen; nur auf/zu, keine Kraftregelung (DIO) |
| Zimmer GEP2006IO Set (Greifer, Adapter, Kabel) | 6 mm je Backe | einstellbar, bis 145 N | 0,18 kg | DIO | ja | 1.380,65 € | zu wenig Hub für gemischtes Geschirr; nur mit Fingern für genau eine Glasgröße [Q19] |
| Schunk EGP-40 Set | klein (Kleinteilegreifer) | — | — | DIO | ja | 1.134,06 € | Hub zu klein; verworfen [Q23] |
| OnRobot RG2 | 0–110 mm | 3–40 N einstellbar | 0,78 kg | eigene Steuerbox (vom Jetson aus anzusteuern, Protokoll offen), Anbau über ISO-Adapter (*Annahme*) | nein | offen | beste Kraftregelung für Glas; schwer; als Aufrüstung, falls der igus-Greifer Glas bricht oder rutscht [Q25] |

Für Fremdgreifer mit ISO-Flansch gibt es den Adapter ReBeL ISO-50
(DIN ISO 9409-1-50-4-M6), REBEL-TCP-100, 99,00 € [Q20].

### 5.3 Kamerahalter, Kabel

- Kein fertiger Ensenso-Halter für den ReBeL gefunden. Eigenbau: Mast aus
  Aluprofil auf dem Schlitten bzw. am Podest, Kamerawinkel mit 4 Schrauben
  M4 (C/CR-Serie: 2,4 Nm, nur an den Gewindeflächen anliegen, Gehäuse ist Teil
  der Kalibrierung) [Q27]. B57-Befestigung: Maßzeichnung im Handbuch.
- Kabel: Ensenso bietet M12-X-kodiert-auf-RJ45-GigE-Kabel und einen
  PoE++-Injektor 90 W (AC oder DC) [Q6]; Preise offen. Mit Kamera auf dem
  Schlitten läuft das Kabel in der Energiekette der 7. Achse mit (im Bundle:
  igus E-Kette Serie 2400, Mitteneinspeisung [Q17]).

### 5.4 7. Achse

| Variante | Steuerung | Wiederholgenauigkeit | Preis (1000 mm Hub) | Bewertung |
|---|---|---|---|---|
| **Bundle iRC-Version** (REBEL-6DOF-7TH-1000 / RBTX-IGUS-0238): ReBeL + Steuerbox (CAN, 14 DI/14 DO) + Kabel + ZLW-20200 mit Motor + E-Kette | iRC, externe Achse, **synchron** mit dem Arm | ±1,5 mm, 0,3 m/s, Hub 500–3000 mm | 10.499,07 € (RBTX) bzw. 11.214,08 € (igus.de); 500 mm: 10.369,23 € | Empfehlung; die Simulation bewegt die Achse während der Greifwege mit |
| DIO-Version ZLW-20200S-7TH-REBEL-01-1000 | nur digitale I/O, Steuerung DLE-REBEL-0001 (2.948,99 €) separat | ±0,3 mm | 2.557,31 € (ohne Steuerung) | keine gemeinsame Bahn mit dem Arm; zusammen mit Steuerung kaum günstiger; verworfen |

Quellen: [Q17][Q19b]. Ob die iRC-Achse **ohne** Roboter einzeln lieferbar ist
(falls schon ein ReBeL vorhanden ist): offen, bei igus erfragen.

### 5.5 Podest, Stand

- Für eine 1,3 m lange Schiene auf 0,65 m Höhe gibt es kein igus-Fertigteil.
  Eigenbau aus Aluprofilen (Preis offen). Zum Vergleich: igus „Cobot
  Arbeitstisch“ 21460 kostet 5.114,13 € [Q20]; die ReBeL-Tischplatte
  REBEL-BASE-0300 (66,74 €) ist nur für Tischmontage ohne Achse [Q20].
- Mit Seitgriff und Zwischenablage reichen ~0,40 m (Umgreif-Befund); die
  Podesthöhe hängt an der Owner-Frage zum Greifkonzept (§9).

### 5.6 Steuerung, Netzteil, Not-Halt, Sicherheit

- Plug-and-Play-ReBeL: Steuerung im Fuß; im Lieferumfang externer
  NOT-HALT-Taster, Tischnetzteil, Kaltgerätekabel [Q21b].
- Handbuch: „In the basic version, the robot control package does not contain
  any safety-related functions.“ Die Anlage muss als Ganzes einer
  Risikobeurteilung unterzogen werden; üblich sind zusätzlich
  Sicherheitsrelais und Türschalter [Q21b].
- igus: Cobot-Prüfung nach ISO/TS 15066 durch das Institut für Arbeitsschutz,
  „kein Schutzzaun nötig“ [Q42]. Das gilt für den Arm, nicht für die Anlage
  mit Greifer, Glas und Kamera.
- Für die Küche: Not-Halt in Griffweite, langsame Geschwindigkeit, die
  Räumwerk-Freigabeprüfung vor jeder Bewegung (`docs/architektur.md` §7),
  Bereichsüberwachung (Laserscanner/Lichtgitter) als offene Option; Preise
  offen.

### 5.7 Anbindung an den Jetson

- Netzwerk: ReBeL (CRI/Modbus TCP) und Ensenso (GigE) im selben Kabelnetz;
  B57 braucht PoE++ (802.3bt, 40 W) oder 24 V [Q2], N46 PoE Klasse 3 oder
  24 V [Q16]. Ein PoE++-Switch oder -Injektor ist einzuplanen (offen).
- ROS 2: `iRC_ROS` (CommonplaceRobotics, Zweig `humble`, CRI oder CAN,
  Schwerpunkt ReBeL 6 DOF, MoveIt-Konfiguration) [Q22]. Ob die 7. Achse als
  externe Achse über `iRC_ROS` fahrbar ist: offen (README nennt sie nicht).
  Ensenso: `ensenso_driver` für Humble/Jazzy [Q10]. Ob beide Treiber auf dem
  Orin (arm64) bauen: offen, die CI läuft auf x86-Containern.

## 6. Gewichtsbilanz am Flansch

Lastkurve [Q15]: 2,0 kg bis 400 mm Hebelarm, linear auf 1,0 kg bei 500 mm,
darüber keine Freigabe. Zulässiger Hebelarm für eine Last m (1–2 kg):
r_max = 400 mm + (2 kg − m) · 100 mm/kg.

Hebelarm an den Greif- und Ablageposen der gewählten Lage (Podest 0,65 m),
gerechnet mit dem Erreichbarkeitsprüfer des Repos (TCP gegen Roboterfuß):

| Ziel | waagerecht | räumlich |
|---|---|---|
| Slot 1/2 | 359 mm | 422 mm |
| Slot 3/4 | **451 mm** | **502 mm** |
| Ablage 1–4 | 350–366 mm | 414–427 mm |

Ob igus den Hebelarm waagerecht oder räumlich misst, steht nicht im
Datenblatt (offen). Massen:

| Posten | Haupt (Kamera fest) | Flansch-Kamera N46 | Flansch-Kamera B57 | RG2 statt igus-Greifer |
|---|---|---|---|---|
| Glas | 0,25 | 0,25 | 0,25 | 0,25 |
| Greifer inkl. Finger | 0,50 (*Annahme* = Simulation) | 0,50 | 0,50 | 0,78 + 0,05 Adapter (*Annahme*) |
| Kamera | — | 0,55 | 1,10 | — |
| Kamerahalter + Kabelanteil | — | 0,15 (*Annahme*) | 0,15 (*Annahme*) | — |
| **Summe [kg]** | **0,75** | **1,45** | **2,00** | **1,08** |
| r_max | 500 mm | 455 mm | 400 mm | 492 mm |
| Slot 3/4 (451/502 mm) | ok waagerecht; räumlich 2 mm hinter dem Kurvenende | knapp ok waagerecht, **nicht ok** räumlich | **nicht ok** | ok waagerecht, nicht ok räumlich |

Folgerung: Kamera nicht an den Flansch. Mit fester Kamera bleibt auch der
schwerere RG2 möglich. Misst igus räumlich, liegen Slot 3/4 für jede Last
knapp außerhalb der Kurve; dann die Schienenlage um wenige Zentimeter
anpassen und die Erreichbarkeit neu prüfen. Die Gewichte von igus-Greifer und
Halter sind Annahmen und am echten Teil zu wiegen.

## 7. Stücklisten

### 7.1 Hauptvariante

| Pos. | Teil | Teilenummer | Preis | Quelle |
|---|---|---|---|---|
| 1 | ReBeL 6 DOF + 7. Achse 1000 mm, iRC-Version (Bundle) | RBTX-IGUS-0238 / REBEL-6DOF-7TH-1000 | 10.499,07 € | [Q17] |
| 2 | Ensenso B57-4, Farbe (GN), FlexView 3 | B57-5C-4/28\|4/28\|350-75/7 | ab 7.950,00 € | [Q1][Q2] |
| 3 | igus ReBeL-Greifer + eigene Finger (V-Nut, gummiert) | 0-LCA-GRI-0100 | 1.954,07 € | [Q20] |
| 4 | Kalibrierplatte 390 × 390 mm | — | offen | [Q2] |
| 5 | PoE++-Injektor oder 24-V-Netzteil, GigE-Kabel M12 | — | offen | [Q6] |
| 6 | Kameramast und -winkel (Eigenbau Aluprofil) | — | offen | — |
| 7 | Podest 0,65 m für Schiene 1,3 m (Eigenbau) | — | offen | — |
| 8 | Sicherheitstechnik nach Risikobeurteilung | — | offen | [Q21b] |
| | **Summe bekannter Posten** | | **20.403,14 €** | |

### 7.2 Sparvariante

| Pos. | Teil | Teilenummer | Preis | Quelle |
|---|---|---|---|---|
| 1 | wie Haupt | RBTX-IGUS-0238 | 10.499,07 € | [Q17] |
| 2 | Ensenso N46-604-16-BL, FlexView | N46-604-16-BL | N-Serie ab 5.160,00 € (N46 offen) | [Q1][Q16] |
| 3 | wie Haupt | 0-LCA-GRI-0100 | 1.954,07 € | [Q20] |
| 4 | Kalibrierplatte 200 × 200 mm | — | offen | [Q5] |
| 5–8 | wie Haupt (PoE-Injektor genügt Klasse 3) | — | offen | |
| | **Summe bekannter Posten** | | **17.613,14 €** | |

Der Jetson AGX Orin ist in beiden Varianten nicht enthalten (schon geplant).

### 7.3 Variante „beide Körbe“ (Ober- und Unterkorb mit einer Kamera)

| Pos. | Teil | Teilenummer | Preis | Quelle |
|---|---|---|---|---|
| 1 | ReBeL 6 DOF + 7. Achse 1000 mm, iRC-Version (Bundle) | RBTX-IGUS-0238 | 10.499,07 € | [Q17] |
| 2 | **Ensenso C57-6-S** (6 mm, Fokus 975 mm, Basis 240 mm; Betriebsabstand 750–1500 mm) | **1009348** | 8.900,00 € (C-Serie ab) | [Q44][Q45][Q1] |
| 3 | igus ReBeL-Greifer + eigene Finger | 0-LCA-GRI-0100 | 1.954,07 € | [Q20] |
| 4 | Kalibrierplatte 390 × 390 × 3 mm, Raster 15 × 15 / 48 mm | — | offen | [Q44] |
| 5 | PoE++-Injektor 90 W (802.3bt) oder 24-V-Netzteil, GigE-Kabel M12 | — | offen | [Q44][Q6] |
| 6 | Kameramast und -ausleger (Eigenbau Aluprofil); Kamera (0,55; 0,50; 1,35) m | — | offen | — |
| 7–8 | Podest und Sicherheitstechnik wie Hauptvariante | — | offen | — |
| | **Summe bekannter Posten** | | **21.353,14 €** | |

Die Kamera sitzt höher als in der B57-Variante (z 1,35 m statt 1,15 m) und bleibt
erreichbarkeitsneutral (§2.3). Summe = Hauptvariante − 7.950 € + 8.900 €.

## 8. Was in die Simulation muss

| Was | Wert | Wohin |
|---|---|---|
| Wiederholgenauigkeit 7. Achse (iRC-Version) | ±1,5 mm statt 0,3 mm (0,3 mm gilt für die DIO-Version) | `config/robot.yaml` `achse7.wiederholgenauigkeit_m`, Quelle [Q17] |
| Lastkurve | 2 kg ≤ 400 mm, 1 kg bei 500 mm | Prüfung je Wegpunkt: Hebelarm ≤ r_max(m) |
| Kamera B57-4 | 2 Kameras 2472 × 2064, f = 4 mm, Pixel aus Sichtfeld (621 mm bei 500 mm), Basis 75 mm, Vergenz 7°, Fokus 350 mm, Bereich 210–800 mm (Farbe), z-Rauschen nach Tabelle §2.1 | neues Sensormodell: zwei gerenderte Kameras + Tiefe mit Rauschen |
| Kamera C57-6-S (beide Körbe) | 2 Kameras 2472 × 2064, Arbeitsvolumen 954 × 867 mm @ 1000 mm, Basis 240 mm, Fokus 975 mm, **Bereich 750–1500 mm**, z-Rauschen σ(z) = 0,219 · z² mm (0,219 mm @ 1 m), 3–10 fps | wie B57 (Sensormodell + Bereichsgrenzen) |
| Glasverhalten | Tiefe auf Glaspixeln entfernen (Typ II) oder durch Hintergrundtiefe ersetzen (Typ I) [Q35] | Maske aus der Semantik der Szene |
| Kameralage | Mast auf dem Schlitten, Blick schräg auf den ausgezogenen Korb | Szene, Hand-Auge-Transformation als Parameter |
| Greifer | igus-Greifer: Maße aus CAD (igus Download), Masse 0,5 kg (*Annahme* bis gewogen), Kraft offen | `config/robot.yaml` `greifer` |
| Kamera am Schlitten | 1,1 kg + Mast als Zusatzlast der 7. Achse | Achsmodell |

Ein projektorbasiertes Stereo-Modell (Muster + Stereo-Matching) in Isaac Sim
ist möglich, aber aufwendig; eine Arbeit zeigt ein virtuelles
Streifenprojektionssystem in Isaac Sim [Q43]. Für Räumwerk reicht zuerst das
einfache Tiefenmodell mit Glasmaske.

## 9. Offene Fragen an den Owner

1. **Wo sitzt die Kamera?** (a) Mast auf dem Schlitten der 7. Achse —
   Empfehlung; (b) fest am Podest-Ende; (c) an Küche/Arbeitsplatte; (d) am
   Flansch (nur N46, knappe Nutzlast).
2. **Welche Kamera?** (a) B57-4 Farbe (Haupt, ab 7.950 €) — Empfehlung,
   nach Machbarkeitsanalyse mit Leihkamera; (b) N46-604-16-BL (Spar); (c) erst
   die Machbarkeitsanalyse mit beiden, dann entscheiden.
3. **Ist schon ein ReBeL vorhanden?** (a) nein → Bundle mit 7. Achse —
   Empfehlung; (b) ja → bei igus die iRC-Achse einzeln anfragen; (c) ja und
   DIO-Achse in Kauf nehmen (Achse steht während jedes Greifwegs still,
   Simulation neu prüfen).

## 10. Quellen (alle abgerufen am 29.10.2026)

- [Q1] IDS, Übersicht 3D-Kameras mit „Starting at“-Preisen (Suchmaschinen-Auszug, Seite hinter Bot-Prüfung): https://en.ids-imaging.com/ensenso-stereo-3d-camera.html , https://ids-imaging.com/ensenso
- [Q2] IDS-Datenblatt Ensenso B57-4 (B57-5C-4/28|4/28|350-75/7), Stand 25.09.2024, bei 1stVision: https://www.tvcnet.1stvision.com/cameras/IDS/Ensenso/dataman/Ensenso-B-series-datasheet.pdf ; Produktseite: https://www.1stvision.com/cameras/IDS-imaging-Ensenso-B-series-3D-cameras
- [Q3] Ensenso-Handbuch, General Series Features: https://ensenso.com/choosing-camera-series ; C-Serie bei 1stVision: https://www.1stvision.com/cameras/IDS-imaging-Ensenso-C-series-3D-cameras
- [Q4] N-Serie, Vergleichstabelle N3x/N4x: https://www.1stvision.com/cameras/IDS-imaging-Ensenso-N-series-3D-cameras ; Adept: https://www.adept.net.au/cameras/ids/ensenso_n.shtml
- [Q5] Datentabelle N36-604-16 (IDS-Daten beim Distributor Hope): https://www.hopetw.com/modules/cart/index.php/product/view/172-N36-604-16
- [Q6] Ensenso-Handbuch Hardware (Maße/Gewichte, Strom, Kabel, Namensschema): https://manual.ensenso.com/latest/hardware/index.html , …/dimensions-and-mounting/b-series.html , …/dimensions-and-mounting/c-series.html , …/power-supply/b-series.html , …/naming-scheme.html
- [Q7] Ensenso-Handbuch, Nvidia Jetson: https://manual.ensenso.com/latest/guides/nvidia-jetson.html
- [Q8] Ensenso SDK Downloads (arm64 für Jetson): https://community.ensenso.com/t/ensenso-sdk-downloads/58
- [Q9] ensenso/ros_driver, Releases und ROS2.md: https://github.com/ensenso/ros_driver/releases , https://github.com/ensenso/ros_driver/blob/master/docs/ROS2.md
- [Q10] ensenso/ros_driver CI-Matrix: https://github.com/ensenso/ros_driver/blob/master/.github/workflows/build-and-test.yml
- [Q11] Ensenso-Handbuch, Camera Setup Considerations: https://manual.ensenso.com/latest/guides/camera-setup-considerations.html
- [Q12] Ensenso-Handbuch, S-Serie Maße/Strom: https://manual.ensenso.com/latest/hardware/dimensions-and-mounting/s-series.html
- [Q13] Optonic, Ensenso-Technik (FlexView): https://www.optonic.com/en/brands/ensenso/ , https://www.optonic.com/en/products/ensenso/tech-highlights-ensenso/
- [Q14] Optonic, kostenlose Machbarkeitsanalyse mit Leihkamera: https://3d-vision.ensenso.com/en/
- [Q15] igus-Datenblatt ReBeL 6 DOF, Issue 06/2024 (Lastkurve, Flansch, I/O): https://docs.rs-online.com/ded5/A700000012224496.pdf
- [Q16] Ensenso-Handbuch, Stromversorgung N-Serie: https://manual.ensenso.com/latest/hardware/power-supply/n-series.html ; N46-604-16-BL 370–800 mm: https://rodavigo.net/en/p/3d-camera-ensenso-n46-604-16-bl-370-800-mm-flexview-ref-ids-1008601/8071008601
- [Q17] 7. Achse, Bundle iRC-Version: https://www.igus.de/product/22528 (REBEL-6DOF-7TH-1000, 11.214,08 €, Lieferumfang); https://rbtx.de/de-DE/components/cobots/rebel-cobot-incl-seventh-axis-1500-mm-stroke-igus-robot-control-version/1000-mm (10.499,07 €), …/500mm (10.369,23 €)
- [Q18] igus ReBeL 6 DOF, REBEL-6DOF-03, 4.970,00 €, technische Daten: https://www.igus.de/product/REBEL-6DOF-03 ; RBTX: https://rbtx.com/de-DE/components/robots/rebel-cobot-6-degrees-of-freedom-reach-664-mm
- [Q19] Zimmer-Greiferset ReBeL: https://www.igus.de/product/zimmer-gripper ; RBTX GEP2006: https://rbtx.com/de-DE/components/electric-gripper/2-jaw-parallel-gripper-for-rebel-cobot-gep2006
- [Q19b] 7. Achse DIO-Version: https://www.igus.de/product/21473 ; Steuerung DLE-REBEL-0001: https://www.igus.de/product/21475
- [Q20] igus-Shop: ReBeL-Greifer https://www.igus.de/product/0-LCA-GRI-0100 ; RBTX https://rbtx.com/de-DE/components/end-effectors/rebel-gripper ; ISO-50-Adapter https://www.igus.de/product/REBEL-TCP-100 ; Tischplatte https://www.igus.de/product/REBEL-BASE-0300 ; Arbeitstisch https://www.igus.de/product/21460
- [Q21] CRI-Schnittstelle: https://wiki.cpr-robots.com/images/2/23/CPR_RobotInterfaceCRI.pdf ; https://github.com/CommonplaceRobotics/CRI-Python-Lib
- [Q21b] ReBeL-Bedienungsanleitung (Lieferumfang, Sicherheit): https://usersmanualguide.com/igus/robotics/rebel/user-manual/13260 , https://manuals.plus/igus/rebel-series-collaborative-robot-manual
- [Q22] CommonplaceRobotics/iRC_ROS (Zweig humble): https://github.com/CommonplaceRobotics/iRC_ROS
- [Q23] igus ReBeL Schunk-EGP-Greiferset: https://www.igus.de/product/21501
- [Q24] Ensenso-Handbuch, Hand-Eye Calibration: https://manual.ensenso.com/latest/guides/multi-camera-setups-and-calibrations/handeyecalibration.html , https://manual.ensenso.com/latest/commands/calibratehandeye.html
- [Q25] OnRobot RG2: https://onrobot.com/en/products/rg2-finger-gripper ; Daten (0,78 kg, IP54): https://www.samsys.eu/en/product/electric-gripper-rg2/
- [Q26] Ensenso CAD-Modelle: https://ensenso.com/cad-models
- [Q27] Ensenso-Handbuch, Maße C-Serie (Befestigung): https://manual.ensenso.com/latest/hardware/dimensions-and-mounting/c-series.html
- [Q28] Ensenso-Handbuch, Maße X-/XR-Serie: https://manual.ensenso.com/latest/hardware/dimensions-and-mounting/x-series.html , …/xr-series.html ; 1stVision X/XR
- [Q29] IDS-Abkündigungen (S10: Abkündigung 01.04.2026, letzte Bestellung 30.06.2026; Suchmaschinen-Auszug): https://fr.ids-imaging.com/discontinuation.html ; S10-Daten: https://www.1stvision.com/cameras/IDS-imaging-Ensenso-S-series-3D-cameras
- [Q30] Intel RealSense D405, Spezifikation: https://www.intel.com/content/www/us/en/products/sku/229218/intel-realsense-depth-camera-d405/specifications.html
- [Q31] VA Imaging (USD): https://va-imaging.com/en-us/products/n46-3d-camera , …/n36-3d-camera , …/b57-3d-camera
- [Q32] Ensenso-Forum, Formeln des Camera Selectors: https://community.ensenso.com/t/equations-used-in-camera-selector/1835
- [Q33] Ensenso-Forum, Suche: https://community.ensenso.com/search?q=transparent , https://community.ensenso.com/search?q=glass
- [Q34] Sajjan et al., ClearGrasp (ICRA 2020): https://arxiv.org/abs/1910.02550
- [Q35] Robotic Perception of Transparent Objects: A Review: https://arxiv.org/abs/2304.00157
- [Q36] Fang et al., TransCG (RA-L 2022): https://arxiv.org/abs/2202.08471
- [Q37] Bai et al., ClearDepth: https://arxiv.org/abs/2409.08926
- [Q38] Wen et al., FoundationStereo (CVPR 2025): https://nvlabs.github.io/FoundationStereo/
- [Q39] FoundationStereo auf Jetson: https://github.com/NVlabs/FoundationStereo/blob/master/readme_jetson.md
- [Q40] Kalra et al., Deep Polarization Cues for Transparent Object Segmentation (CVPR 2020): https://openaccess.thecvf.com/content_CVPR_2020/html/Kalra_Deep_Polarization_Cues_for_Transparent_Object_Segmentation_CVPR_2020_paper.html
- [Q41] IDS, Polarisationskameras: https://www.ids-imaging.us/techtipp-details/items/techtip-on-camera-polarization.html
- [Q42] igus, ReBeL Cobot-Zertifizierung: https://www.igus.com/automation/news/n23-rebel-cobot
- [Q43] VIRTUS-FPP, virtuelle Streifenprojektion in Isaac Sim: https://arxiv.org/abs/2509.22685
- [Q44] IDS, Datenblatt „Ensenso C-Serie – Coloured 3D Vision“ (Deckblatt + Einzeldatenblätter C57-6-S/8-S/12-S und C57-6-M/8-M/12-M), Stand 2024-04-24/22; Exemplar: https://www.imagesspa.it/image/catalog/pdf/landing/Ensenso_C57_datasheet.pdf (Betriebsabstand „Operating Distance“, Z-Genauigkeitstabelle, Arbeitsvolumen „View Field“, Artikelnummern 1009348/49/50/66/67/68)
- [Q45] Optonic/IDS, Ensenso C57 – Produktseite und Kamera-Selector (Arbeitsbereich/Abstand wählbar, Kamera „nach Bedarf gebaut“): https://www.optonic.com/en/products/ensenso/c57
