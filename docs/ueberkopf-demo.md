# Physik-Demo: über Kopf an der Hubachse, Ober- und Unterkorb nacheinander

Demonstration, keine Festlegung: Der Aufbau „kopfüber an der frontalen Hubachse“ ist weiterhin nur
geprüft, nicht gewählt (Konzept-Spec §15). Die Körbe zieht der Mensch.

## Aufbau und Ablauf

- Aufbau `beispiele/ueberkopf-045-demo.yaml`: Fußmitte (0,30; 0,45; 0,55 m bei Hub 0), Gier 180°,
  kopfüber, 30° zur Maschine geneigt, Hubachse senkrecht (Hub 1,2 m) mit mitfahrendem Profil. Das ist
  die Lage des Abstandsrasters mit dem kleinsten J2. In Newton ist die Achse ein geregeltes
  Schubgelenk (5·10⁴ N/m, 10³ N·s/m), der Arm hängt am Schlitten.
- Läufer `scripts/ueberkopf_demo.py --objekt glas|teller_ot|teller_ut`, Werte `config/ueberkopf_demo.yaml`.
  Je Objekt ein Newton-Lauf von der Parkpose zurück in die Parkpose; die Achse fährt in der Anfahrt
  auf Korbhöhe. Was vorher abgelegt wurde, steht im nächsten Lauf statisch auf dem Wagen.
  1. Oberkorb 0,45 m ausgezogen, 8 Gläser kopfüber und 6 Dessertteller (Szene wie
     `scripts/griff_lauf.py`): Glas auf Platz 5 greifen, über eine Matte auf dem Wagen umgreifen,
     aufrecht auf den Wagen stellen.
  2. Gleicher Korb: Teller 1 (vorn) mit der breiten Backe (`breit_6n`) greifen und in den Ständer stellen.
  3. Korbwechsel durch den Menschen: Oberkorb ein, Unterkorb 0,45 m aus (nur im Video, kinematisch).
  4. Unterkorb: Reihe aus vier Tellern Ø 26 cm (0,50 kg), Teller 1 in den Ständer.
- Ablage (Annahme): Wagen rechts neben der offenen Tür, Platte 0,55 m hoch, kragt bis x 0,575 über die
  Türkante. Die Arbeitsplatte rechts erreicht der Roboter bei 0,45 m nicht. J2 wächst mit dem
  waagerechten Abstand der Ablage von Gelenk 2 (x 0,30; y 0,32); deshalb liegen alle Plätze bei
  x 0,625–0,675. `raeumwerk aufbau` prüft die Plätze als Ablageziele `wagen_*`
  (`tests/test_ueberkopf_demo.py::test_ablage_mit_raeumwerk_aufbau_erreichbar`).
- Tellerständer: Boden 1 cm, je Platz zwei Stabpaare 35 mm, Tellernormale entlang x. Er ist einfacher
  als ein echter Ständer.

## Vereinfachungen

- Griffposen aus der Wahrheit, keine Wahrnehmung.
- Ein Newton-Lauf je Objekt. Bereits Abgeräumtes steht statisch an der Nennlage. Die Gläser im
  Teller-Lauf und der Inhalt des eingeschobenen Oberkorbs sind statisch oder fehlen.
- Korbwechsel nur kinematisch im Video.
- Ideale Schwerkraftkompensation (`mujoco:gravcomp`) für alle Roboterglieder, auch den Schlitten.
- J2 ist das statische Schweremoment entlang der Soll-Gelenkwinkel (`aufbau.schweremomente`, Glieder
  am Schwerpunkt, Gliedermassen geschätzt). Die Last zählt in Greif- und Lösephasen mit.
- Die Planung hält die Achse 5 cm unter dem oberen Anschlag. Am Anschlag ruckte der Schlitten, und der
  Oberkorb-Teller fiel am Ende des Aushubs aus der Hand (2 von 2 Läufen).

## Ergebnisse (Newton 1.6.1, GPU, Seed ohne Lageabweichung, wenn nicht anders genannt)

| Objekt | Ergebnis | Zielfehler | Kippung | J2 max (Phase) |
|---|---|---|---|---|
| Glas (Oberkorb) | Erfolg | 2,1 mm | 0,1° | 11,0 Nm (Umgreifen auf dem Wagen); Korb ≤ 2,7 Nm |
| Teller Ø 19 cm (Oberkorb) | 0/3: Seed 0 im Ständer, aber 12,7 mm neben dem Ziel und 7,9 mm Fingerdurchdringung; Seeds 1/2 beim Transport gefallen | – | – | 10,3 Nm (Ständer) |
| Teller Ø 26 cm (Unterkorb) | Erfolg (auch auf CPU) | 7,3 mm | 2,7° | 7,9 Nm (Ständer) |

J2-Nennmoment 10 Nm, Maximum 12,5 Nm (`config/robot.yaml`). Im Korb bleibt J2 bei höchstens 2,7 Nm.
Über dem Nennmoment liegt J2 nur an der Ablage, weil der Wagen waagerecht weiter von Gelenk 2 entfernt ist.

## Ergebnisse im Detail

Bericht, Laufdaten und Video liegen im Artefaktordner der Demo.
