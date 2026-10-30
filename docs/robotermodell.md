# Robotermodell: igus ReBeL 6 DOF + 7. Achse + Parallelgreifer

Stand: 2026-10-29. Das Modell ist parametrisiert: alle Zahlen stehen
in `config/robot.yaml`, jede mit Quelle (`src`) oder als `annahme` markiert.
`rebel_model/urdf_gen.py` erzeugt daraus die URDF (die URDF selbst liegt nicht
im Repo, sie ist ein Erzeugnis):

    python -m rebel_model.urdf_gen [--payload KG] [-o rebel.urdf]

## 1. Quellen und Lizenzen

| Quelle | Was daraus stammt | Lizenz | Version / Prüfsumme | Im Repo? |
|---|---|---|---|---|
| igus Datenblatt „ReBeL 6 DOF“ (`technical data sheet ReBeL 6DOF_EN.pdf`, igus.com, Downloads) | Maße 252/237/297/126 mm, Kerzenhöhe 912 mm, Reichweite 664 mm (660 mm Gelenk 2 → Flansch), Gelenkgrenzen, 45 °/s, 8,2 kg, 2 kg Nutzlast, ±1 mm, Fuß Ø180 mm, Flansch Ø43 mm | igus-Nutzungsbedingungen, keine Weitergabe-Freigabe | sha256 `02b8d7af4a3c971ba93d29cb9cb2cd06510e1b87c2b01422bf8c0e218b12ea49` | nein, `scripts/fetch_assets.sh` |
| CommonplaceRobotics/iRC_ROS (Hersteller der ReBeL-Steuerung, von igus verlinkt), `irc_ros_description/urdf/robots/igus_rebel_6dof_00.description.xacro` | Achsrichtungen (J1 um −z), Höhe Fuß → J1 (100 mm), J5 → J6 (120,8 mm), Vergleichsmodell für den FK-Abgleich | Apache-2.0 (`LICENSE`, `package.xml`) | Commit `41701e6df3398087d217f0f478622e60f694de41` (2025-05-21); sha256 xacro `31d92942…1a16f8`, `_01` `76489bd9…b52f`, LICENSE `ffcc552b…5ef9f` | nein (nur Zahlenwerte im Test, mit Quellenangabe); Dateien über `scripts/fetch_assets.sh` |
| CommonplaceRobotics/iRC_ROS, `irc_ros_description/meshes/igus_rebel_6dof_00/Joint0.dae` … `Joint6.dae` | Visual-Meshes des ReBeL (nur Optik in Render und Video, §6) | Apache-2.0 (Repo-`LICENSE`, `package.xml`); Herkunft der Geometrie nicht dokumentiert (COLLADA aus `ctmconv`, 2023-01-02) | Commit wie oben; sha256 Joint0 `146b8890…d92ad9`, Joint1 `d85b816d…526e79`, Joint2 `36e29bd2…ef1f5f`, Joint3 `b8f4d321…41cc35`, Joint4 `e097f7b7…eb0acb`, Joint5 `8ae70e27…dfb1c9`, Joint6 `d68b1b8f…1e4f59` (vollständig in `scripts/fetch_assets.sh`) | nein, `scripts/fetch_assets.sh` (siehe unten) |
| igus CAD-Portal (`igus-cad.com`, CADClick) und TraceParts: STEP/STL von ReBeL 6 DOF (REBEL-6DOF-01) und drylin ZLW-20200 / 7. Achse | nicht genutzt | Download nur über das Portal mit Formular bzw. Anmeldung und Bedingungen; kein Account angelegt, nichts akzeptiert | — | nein |
| igus Produktseite „7th axis for ReBeL“ (ZLW-20200S-7TH-REBEL-01-&lt;Hub&gt;) | Hub 500–3000 mm, 0,3 m/s, Wiederholgenauigkeit 0,3 mm | Webseite, nur Zahlenwerte übernommen | — | nein |
| igus Produktseite „Lightweight Parallel Gripper for ReBeL“ (0-LCA-GRI-0100) | Greifbereich 100 mm, maximale Öffnung 105 mm | Webseite, nur Zahlenwerte übernommen | — | nein |

Offizielle URDF von igus selbst wurde nicht gefunden (Suche: igus-Website,
GitHub, ROS-Pakete). igus-CAD-Daten (STEP/STL) gibt es nur über das
igus-CAD-Portal bzw. TraceParts mit Formular/Anmeldung und eigenen
Bedingungen; sie werden nicht genutzt. Das ROS-Paket von CommonplaceRobotics
(iRC_ROS) ist die herstellernahe Beschreibung und bringt Meshes des ReBeL mit.
**Physik und Kollision** bleiben eigene Quader. Die iRC_ROS-Meshes dienen nur
der **Optik** (§6) und kommen **nicht ins Repo**: Apache-2.0 würde die
Weitergabe zwar erlauben, aber woher die Geometrie stammt (vermutlich aus
Hersteller-CAD), ist nirgends dokumentiert. Deshalb werden sie wie die anderen
Assets nur lokal über `scripts/fetch_assets.sh` geholt. Für die 7. Achse
(drylin ZLW-20200) und den Greifer gibt es keine frei ladbaren Meshes; sie
bleiben eigene Quader.

`scripts/fetch_assets.sh` legt die Dateien nach `$RAEUMWERK_ASSETS`
(Standard `$RAEUMWERK_HOME/assets`) und bricht bei falscher Prüfsumme ab
(Exit 5). Mit gesetztem `RAEUMWERK_ASSETS` prüft
`test_cpr_numbers_in_fetched_asset`, dass die im Test benutzten
iRC_ROS-Zahlen wirklich in der geholten Datei stehen, und
`tests/test_visual_mesh.py` prüft die Ausrichtung der Meshes (§6).

## 2. Kinematische Kette

```
world ─ rail ─axis7 (prismatisch, +x, 0…1,0 m)→ carriage ─fest→ base_link
  ─joint1 (−z)→ link_1 ─joint2 (y)→ link_2 ─joint3 (y)→ link_3 ─joint4 (z)→ link_4
  ─joint5 (y)→ link_5 ─joint6 (z)→ link_6 ─fest→ gripper_base (= Flansch)
      ├─finger_left  (prismatisch, +y, 0…50 mm)
      ├─finger_right (prismatisch, −y, mimic finger_left, Faktor 1)
      └─fest→ payload (nur Masse im TCP, nur im Backend-Test)
```

Nullpunkt aller Armgelenke ist die **Kerzenpose** des Datenblatts (Arm
senkrecht). iRC_ROS hat einen anderen Nullpunkt: J2/J3 sind dort um 30° und J5
um −7,5° geneigt eingebaut; Umrechnung `q_cpr = q + (0, −30°, −30°, 0, +7,5°, 0)`.
Damit werden aus den Datenblattgrenzen J2/J3 −80…140° genau die ±110° von
iRC_ROS (`test_cpr_limits_match_datasheet_after_offset`).

## 3. Maße und Grenzen

| Größe | Wert | Quelle |
|---|---|---|
| Fuß → Achse J2 | 252 mm | Datenblatt |
| Oberarm J2 → J3 | 237 mm | Datenblatt |
| Unterarm J3 → J5 | 297 mm | Datenblatt |
| Hand J5 → Flansch | 126 mm | Datenblatt |
| Kerzenhöhe (Summe) | 912 mm | Datenblatt (Kontrollwert) |
| Reichweite J2 → Flansch | 660 mm | Datenblatt (664 mm „maximum reach“) |
| Fuß → J1 | 100 mm | iRC_ROS (für die FK egal) |
| J3 → J4 | 127 mm | Annahme (297 − 170 aus iRC_ROS, für die FK egal) |
| J5 → J6 | 120,8 mm | iRC_ROS (für die FK egal) |
| J1, J4, J6 | −179…179° | Datenblatt |
| J2, J3 | −80…140° | Datenblatt |
| J5 | −95…95° | Datenblatt |
| Gelenkgeschwindigkeit | 45 °/s | Datenblatt |
| Moment je Gelenk | J1–J3 (Baugröße 105): Nenn 10–15 Nm, Max 12,5–20 Nm; J4–J6 (Baugröße 80): Nenn 2 Nm, Max 2,5–3 Nm. URDF-Antriebsgrenze = oberer Maximalwert (20 bzw. 3 Nm), Rechnungen nehmen den unteren Wert | igus-Getriebebaukasten (`igus_getriebe`); Zuordnung der Baugrößen: **Annahme** |
| Masse Arm | 8,2 kg (Aufteilung auf die Glieder: Annahme) | Datenblatt |
| Nutzlast | 2 kg inkl. Greifer → 1,5 kg im TCP im Backend-Test | Datenblatt |
| 7. Achse Hub | 1000 mm (Variante; 500…3000 lieferbar) | igus 7. Achse |
| 7. Achse Geschwindigkeit | 0,3 m/s | igus 7. Achse |
| 7. Achse Länge, Profil, Massen, Kraft 300 N | 1300 mm, 200 × 60 mm, 6 + 1 kg | **Annahme** |
| Greifer Hub gesamt / max. Öffnung | 100 / 105 mm → 5 mm Restöffnung, 50 mm je Finger | igus Greifer |
| Fingerbreite / -dicke / -länge | 20 / 10 / 60 mm | **Annahme** |
| Greiferkörper, Massen (0,4 + 2 × 0,05 kg), 50 N, 0,05 m/s | — | **Annahme** |
| TCP ab Flansch | 80 mm (Körper 50 + halbe Fingerlänge) | **Annahme** |
| Kollisionsquader Glieder / Hand | 90 / 80 mm Kantenlänge | **Annahme** |

Annahmen sind am echten Gerät nachzumessen (Hardware-Abgleich); geändert wird
nur `config/robot.yaml`, die Tests nennen die Datenblattwerte direkt.

## 4. Validierung

### Ohne GPU (`tests/test_rebel_kinematics.py`, nur numpy)

`uvx -p 3.10 --with numpy --with pyyaml pytest -q tests`:
44 passed, 3 skipped (Asset-Test ohne `RAEUMWERK_ASSETS`, 2 GPU-Smokes).

| Prüfung | Ergebnis |
|---|---|
| FK gegen 6 Datenblattposen (Kerze 912 mm, J2 = 90° → 660/252 mm, J2 = 90°/J3 = −90°, J2 = 90°/J5 = 90°, J1 = 90°, J4/J6) | Abweichung < 1 µm (`test_fk_datasheet_poses`) |
| FK gegen iRC_ROS, 201 Posen | Kerze 13,6 mm (912 gegen 898,4 mm), max. 14,7 mm, Mittel 10,8 mm — Ursache: andere Längen (249/238,4/289/122 mm in iRC_ROS); Datenblatt gilt (`test_fk_deviation_against_cpr_urdf`) |
| Gelenkgrenzen | gleich Datenblatt; 500 Zufallsposen innerhalb, 141° bzw. −1 mm außerhalb erkannt |
| IK-Rundlauf 6 DOF (Lage + Orientierung), 60 kollisionsfreie Zufallsposen | max. 0,0099 mm, 0,001° (`test_ik_roundtrip_6dof_pose`) |
| IK-Rundlauf mit 7. Achse (nur Lage, redundant), 50 Zufallspunkte | < 1 mm (`test_ik_roundtrip_7axis_position`) |
| Reichweitenhülle | 20 000 Stichproben ≤ 660 mm, > 97 % davon erreicht; 700 mm nicht lösbar (Restfehler = 40 mm), 650 mm lösbar; mit 7. Achse am Schienenende dasselbe |
| Selbstkollision (Quader, Trennachsensatz) | 6 freie Posen ohne Treffer; „Greifer trifft link_1“ (J3 = 140°, J5 = 95°) und „Handgelenk im Fuß“ (J2 = 90°, J3 = 140°) erkannt, beide innerhalb der Gelenkgrenzen |

Die IK ist gedämpfte kleinste Quadrate mit aktiver Menge an den Gelenkgrenzen
und bis zu 50 zufälligen Neustarts (`rebel_model/kinematics.py`).

### Im Backend (Newton 1.6.1, `scripts/rebel_newton.py`)

Gestartet über `scripts/run_rebel_newton.sh` (auf dem geteilten GPU-Rechner
nur über die GPU-Warteschlange), Ergebnis unter
`$RAEUMWERK_HOME/runs/rebel/<Zeitstempel>/` (`rebel.json`, `rebel.log`,
`rebel.urdf`, `ss-ltnp.txt`). Ablauf:

1. URDF mit Nutzlast 1,5 kg im TCP erzeugen, mit `enable_self_collisions=True`
   laden; Massen, Grenzen, Kraft-/Momentgrenzen und die Mimic-Kopplung im
   geladenen Modell prüfen.
2. FK-Abgleich Newton `eval_fk` gegen `rebel_model.kinematics` (5 Datenblatt-
   + 50 Zufallsposen).
3. Selbstkollision mit der Newton-Kollisionspipeline: gezählt wird nur echte
   Durchdringung (Separation < −0,1 mm, wie Newtons
   `contact_surface_separation`), nicht die Vorschau-Kontakte im
   Kontaktabstand.
4. Fahrt mit `SolverMuJoCo`: PD-Positionsantrieb mit Geschwindigkeits-
   vorsteuerung; jede Achse fährt nacheinander zwei Ziele mit
   Datenblattgeschwindigkeit an (Arm ±60 % des Bereichs, Achse 800/200 mm,
   Finger 45/10 mm), 1,5 s Haltezeit, dann zurück in die Kerze. Toleranz:
   Drehgelenk < 1°, Achse/Finger < 1 mm; beim Greifer muss auch der
   gespiegelte Finger (mimic) das Ziel treffen.

Messwerte (Lauf `runs/rebel/20261029T025400Z`, RTX 3090, Newton 1.6.1):
FK-Abweichung Newton gegen numpy max. 0,34 µm (55 Posen); 16 Ziele erreicht,
Drehgelenke max. 0,18°, Achse 7 max. 0,0001 mm, Finger < 0,001 mm,
gespiegelter Finger 0,38 mm; Selbstkollision in beiden Schnittposen erkannt,
in den 4 freien Posen keine Durchdringung. Übersicht: `docs/STATUS.md`.

## 5. Bekannte Grenzen

- Welche Getriebebaugröße an welchem Gelenk sitzt (J1–J3 105, J4–J6 80), die
  Massenverteilung, Greifer- und Schienenmaße sind Annahmen, keine Datenblattwerte.
- Die Mimic-Kopplung ist in Newton/MuJoCo eine weiche Zwangsbedingung: der
  rechte Finger steht unter Schwerkraft rund 0,4 mm hinter dem linken.
- Das Modell kennt keine Getriebeelastizität, kein Spiel und keine Reibung;
  das ReBeL-Datenblatt nennt ±1 mm Wiederholgenauigkeit.

## 6. Optik: ReBeL-Meshes (nur lokal)

`rebel_model/visual_mesh.py` ordnet jedem Armglied sein iRC_ROS-Mesh zu,
`build_urdf(cfg, mesh_dir=…)` (CLI `python -m rebel_model.urdf_gen --meshes
<Ordner>`) schreibt es als `<visual>` in die URDF. Nur die Visuals ändern
sich: Massen, Gelenke und Kollisionsquader bleiben gleich
(`test_urdf_mit_meshes_aendert_nur_visuals`), und die Simulation ruft
`build_urdf` weiter ohne Meshes auf.

| Glied | Mesh | Lage im Linkframe |
|---|---|---|
| base_link | Joint0 | unverändert (Fuß 0…100 mm = J1) |
| link_1 | Joint1 | z × 152/149 (J1 → J2: Datenblatt 152 mm, Mesh 149 mm) |
| link_2 | Joint2 | z × 237/238,4 (Oberarm) |
| link_3 | Joint3 | z × 1,054: schließt die Fuge zum J4-Mesh (Unterarm Datenblatt 297 mm, Mesh 289 mm) |
| link_4 | Joint4 | unverändert, J5 des Meshes liegt auf unserem J5 |
| link_5 | Joint5 | unverändert (J5 → J6 120,8 mm in beiden) |
| link_6 | Joint6 | um 4 mm nach oben, Flanschscheibe endet am Flansch |

Die Linkframes von iRC_ROS liegen in den Gelenken und sind bei gleicher Pose
gleich orientiert wie unsere (Umrechnung §2), deshalb gibt es keine Drehung,
nur eine Streckung entlang der Gliedachse. `visual_mesh.ausrichtung()` misst
nach, wie gut jedes Mesh auf unseren Gelenken sitzt: Bei den y-Gelenken
(J2, J3, J5) wird ein Kreis an die Außenkontur des Gehäuses gelegt und sein
Mittelpunkt mit dem Gelenk verglichen. Bei den z-Gelenken wird die
Querschnittsmitte gegen die Achse gemessen. Dazu kommen die Stirnflächen
und die Fuge J3/J4. Gemessen mit den Dateien oben (`test_ausrichtung_mesh_zu_gelenken`,
Grenze 5 mm):

| Glied | größter Fehler |
|---|---|
| base_link | 0,00 mm (J1-Achse, Fuß, Stirn) |
| link_1 | 1,45 mm (J2-Gehäuse) |
| link_2 | 0,57 mm (J3-Gehäuse; J2 0,53 mm) |
| link_3 | 3,79 mm (J3-Gehäuse, Folge der Streckung um 5,4 %) |
| link_4 | 0,36 mm (J5-Gehäuse) |
| link_5 | 0,36 mm (J5-Gehäuse) |
| link_6 | 0,00 mm |

Die Gegenprobe (`test_ausrichtung_erkennt_versatz`) verschiebt das Oberarm-Mesh
um 8 mm, und dann schlägt die Messung an. Ohne Assets werden die drei
Asset-Tests übersprungen.

`scripts/render_video.py` nimmt die Meshes, wenn sie lokal liegen
(`--optik auto`, Standard; `mesh` erzwingt sie, `quader` schaltet sie ab).
Es dezimiert sie per Vertex-Clustering auf höchstens 1100 Dreiecke je Glied und
färbt sie anthrazit mit orangen Ringen an den Gelenkfugen wie beim echten
ReBeL. Dafür werden die Dreiecke an den Ringkanten zweimal geviertelt. Je Bild
sind das 19 043 Dreiecke (bevor die Rückseiten wegfallen). Gerendert wird in
6 Prozessen (`--jobs`), ffmpeg setzt die Abschnitte ohne Neukodierung zusammen.
Gemessen für die Demo (24,0 s, 721 Bilder, 1280×720, 8 Kerne): mit Meshes
38,5 s Wandzeit, mit Quadern 15,2 s (6 Prozesse) bzw. 36,8 s (1 Prozess).
Ohne Meshes zeigt das Video die Quader.
Schiene und Greifer bleiben Quader: Ein CAD der 7. Achse gibt es nur über
das igus-Portal.

Isaac Sim (zweiter Rechner mit RTX-GPU) könnte die Mesh-URDF
(`urdf_gen --meshes`) mit dem URDF-Importer laden und fotorealistisch
rendern. Gebaut ist das nicht, denn es braucht einen Lauf auf dem zweiten
Rechner, die Annahme der NVIDIA-EULA und die Meshes dort. Das ist nicht mit
wenig Aufwand zu machen.
