# Start: Greifdemo vom frischen Klon

Ziel: Der simulierte ReBeL greift ein Glas vom Tisch, hebt es 10 cm an, fährt
es über die 7. Achse 30 cm weiter, setzt es ab und zieht sich zurück. Ein
automatischer Bericht sagt, ob das geklappt hat und warum nicht.
Was dabei gerechnet und bewertet wird, steht in `docs/greifdemo.md`.

## 1. Voraussetzungen

- Linux (x86_64), `git`, `bash`, `ss` (iproute2)
- [`uv`](https://docs.astral.sh/uv/) mit `uvx` im `PATH` oder unter `~/.local/bin/`
- **Weg A (ohne Isaac-Installation, CPU):** sonst nichts. Beim ersten Lauf lädt
  `uvx` Newton 1.6.1, Warp 1.17.0, MuJoCo 3.12.0 und MuJoCo-Warp 3.12.0 aus PyPI
  (einige hundert MB, landen im uv-Cache).
- **Weg B (GPU):** NVIDIA-GPU und das Isaac-Lab-venv unter
  `$RAEUMWERK_HOME/venvs/isaaclab` (`scripts/install_backends.sh isaaclab`, siehe
  `docs/umgebung.md`; dauert Stunden, nur einmal nötig).

## 2. Klonen und Rechnerwerte

```bash
git clone https://github.com/edrethardo/raeumwerk.git
cd raeumwerk
cp config/local.env.example config/local.env   # optional, Werte anpassen
```

Alles, was nur auf einem Rechner gilt, steht in `config/local.env` (steht in
`.gitignore`). Für die Demo zählt nur:

- `RAEUMWERK_HOME`: Ordner für venvs und Ergebnisse (Standard `$HOME/raeumwerk`)
- `RAEUMWERK_GREIFEN_RUNS`: Ergebnisordner (Standard `$RAEUMWERK_HOME/runs/greifen`)

Ohne `config/local.env` gelten die Standards. Beide Werte lassen sich auch
einmalig als Umgebungsvariable setzen, z. B.
`RAEUMWERK_GREIFEN_RUNS=/tmp/greifen scripts/run_greifen.sh --cpu demo`.

## 3. Demo-Lauf (ein Befehl)

```bash
scripts/run_greifen.sh --cpu demo     # Weg A: CPU, ein paar Minuten
scripts/run_greifen.sh demo           # Weg B: GPU-venv, ca. 35 s auf einer RTX 3090
```

Auf einem **geteilten** GPU-Rechner startet Weg B nur unter dem GPU-Lock bzw.
über die GPU-Warteschlange als eigene `systemd-run --user`-Unit (siehe
`docs/umgebung.md`). Das Skript öffnet keine Netzwerkschnittstelle; es schreibt
währenddessen alle 10 s `ss -ltnp` mit.

Erwartete Ausgabe (Zahlen aus dem Abnahmelauf, siehe `docs/STATUS.md`):

```
VERSUCH {"nr": 0, "erfolg": true, "gruende": [], "fehler_xy_mm": 0.88, "kippung_grad": 0.1, "hub_max_mm": 99.9, ...}
GREIFEN_RESULT {"art": "demo", "ok": true, ...}
Ergebnis: <RAEUMWERK_GREIFEN_RUNS>/<Zeitstempel>
```

Exit-Code 0 heißt: Glas steht innerhalb 1 cm am Ziel, aufrecht (< 10°), ist
nicht gefallen, der Arm hat den Tisch nicht berührt.

## 4. Ergebnis lesen

Unter `<RAEUMWERK_GREIFEN_RUNS>/<Zeitstempel>/demo/`:

| Datei | Inhalt |
|---|---|
| `versuch-00.json` | `erfolg`, `gruende`, `position` (Start, Ende, Ziel, `fehler_xy_m`), `kippung_grad` (`ende`, `max`), `dauer` (Ablauf in Simzeit, Phasen, Wandzeit), `messung` (Hub, Durchdringungen, Glasgeschwindigkeit, Folgefehler der Gelenke, Lage am Ende jeder Phase), `bewertung` (jedes Kriterium mit Wert und Grenze) |
| `zusammenfassung.json` | Erfolgsquote, Fehlergründe mit Anzahl, Versionen, Gerät |
| `lauf.log` | vollständige Ausgabe |
| `../ss-ltnp.txt` | offene Ports während des Laufs |

## 5. Weitere Läufe

```bash
scripts/run_greifen.sh [--cpu] negativ     # falscher Greifpunkt -> Fehlversuch "nicht_gegriffen"
scripts/run_greifen.sh [--cpu] variation   # 20 Versuche, Glas um bis zu ±2 cm verschoben (fester Seed)
scripts/run_greifen.sh [--cpu] alle        # alle drei nacheinander
scripts/job_greifen.sh                     # Abnahme: alle drei + Backend-pytest (GPU-venv)
```

Tests ohne Simulator (Planung, Kinematik, Bewertung):

```bash
uvx -p 3.10 --with numpy --with pyyaml pytest -q tests
```

Die zwei Backend-Tests in `tests/test_greifen.py` starten den Demo- und den
Negativlauf wirklich und prüfen das JSON. Sie laufen nur mit
`RAEUMWERK_RUN_GPU_SMOKE=1` und einem Python mit Newton
(`RAEUMWERK_GREIFEN_PYTHON=…` oder `RAEUMWERK_ROOT=$RAEUMWERK_HOME`), sonst
werden sie übersprungen.

## 6. Bilder und Video

Ein Video der Demo entsteht in zwei Schritten, ganz ohne Display und ohne GPU:

```bash
# 1. Demo laufen lassen und die Posen aller Körper aufzeichnen (30 Bilder je Simsekunde)
scripts/run_greifen.sh --cpu demo --aufzeichnen ergebnis/demo.npz
# 2. Offscreen rendern (matplotlib/Agg) und mit ffmpeg kodieren
uvx -p 3.12 --with numpy --with pyyaml --with matplotlib \
  python scripts/render_video.py ergebnis/demo.npz --out ergebnis/greifdemo.mp4 --standbild ergebnis/mitte.png
```

Schritt 1 dauert auf der CPU etwa 2 min, Schritt 2 etwa 40 s. Ohne
`--aufzeichnen` verhält sich die Demo wie vorher. Das Video zeigt die
Kollisionsquader aus der URDF, das Glas als Zylinder, Tisch, Schiene sowie
Start- und Zielmarke, oben links die Phase und am Ende das Ergebnis der
Bewertung (Zielfehler, Kippung). Kodiert wird mit H.264 (libx264), yuv420p und
`+faststart`, 1280×720 bei 30 Bildern/s. Das spielt auf iPhone und iPad. Ist das
Video kürzer als 24 s, läuft es langsamer als Echtzeit (`--tempo`, die
Einblendung zeigt die Simzeit). `ergebnis/` steht in `.gitignore`; Videos und
Aufzeichnungen kommen nicht ins Repo. Test: `tests/test_video.py` (der
Render-Test braucht matplotlib und ffmpeg, sonst wird er übersprungen).

## 7. Experimente: `raeumwerk run`, `report`, `next`

Parameterstudien (Greifpunkt, Reibung, Greifkraft, Glaslage) mit N Versuchen,
fortsetzbar und in Stücken. Aufbau und Dateiformate: `docs/architektur.md`.

```bash
scripts/raeumwerk --cpu run experimente/beispiel.yaml --run-dir beispiel-1   # Weg A, CPU (~2 min je Versuch)
scripts/raeumwerk run experimente/beispiel.yaml --run-dir beispiel-1         # Weg B, GPU-venv (~30 s je Versuch)
scripts/raeumwerk report beispiel-1      # Erfolge, Kollisionen, Fehlergründe -> bericht.md/.json
scripts/raeumwerk next beispiel-1        # Parametervorschlag -> vorschlag.yaml
scripts/raeumwerk run <run>/vorschlag.yaml --run-dir beispiel-2
```

Ein Name ohne `/` liegt unter `$RAEUMWERK_EXPERIMENT_RUNS` (Standard
`$RAEUMWERK_HOME/runs/experimente`). Bricht ein Lauf ab oder endet ein Stück
(`--max-minuten`, Exit 3), setzt derselbe Befehl bei den fehlenden Versuchen
fort. `report` und `next` brauchen nur `python3`.

**Geteilter GPU-Rechner:** nie direkt starten, sondern vom steuernden Rechner
über `scripts/submit_gpu.sh` (externe GPU-Warteschlange oder GPU-Lock, Werte in
`config/local.env`, siehe `config/local.env.example`):

```bash
scripts/submit_gpu.sh -t 10 --weiter-rc 3 --sync beispiel -- \
    scripts/raeumwerk run experimente/beispiel.yaml --run-dir beispiel-1 --max-minuten 8
```

`--sync` kopiert den Stand (alle Dateien aus `git ls-files` und eine Datei
`REVISION`) nach `REMOTE_REPO`; dort muss einmal eine eigene `config/local.env`
mit `RAEUMWERK_HOME` liegen. Jedes Stück läuft als eigene Unit mit
Laufzeitgrenze; zwischen den Stücken ist die Karte für andere frei.

## 8. Spülmaschine ausräumen (4 Gläser)

Der ReBeL holt vier kopfüber stehende Gläser aus dem Oberkorb, greift sie auf
einer kleinen Zwischenablage seitlich um, dreht sie mit Gelenk 6 um und stellt
sie aufrecht auf die Arbeitsplatte. Erklärung und Messwerte:
`docs/ausraeumen.md`.

```bash
scripts/run_ausraeumen.sh --cpu demo        # 4 Gläser, fester Seed (CPU ~45 min)
scripts/run_ausraeumen.sh --cpu negativ     # Glas 1 klemmt im zu schmalen Halter -> "nicht_aus_dem_korb"
scripts/run_ausraeumen.sh --cpu demo --glaeser 1   # nur das erste Glas (~10 min)
uvx -p 3.12 --with numpy --with pyyaml python scripts/demo_ausraeumen.py --art demo --out ergebnis/plan --nur-plan
                                            # nur planen, ohne Newton (~3 min)
```

Ergebnis unter `$RAEUMWERK_AUSRAEUMEN_RUNS/<Zeitstempel>/<art>/` (Standard
`$RAEUMWERK_HOME/runs/ausraeumen`): `versuch-00.json` mit `bewertung.glaeser[]`
(je Glas Erfolg, Gründe, Zielfehler, Kippung, Kontakte, Nachbarverschiebung),
`zusammenfassung.json`, `lauf.log`, `ss-ltnp.txt`. Exit 0: Demo 4/4, bzw.
Negativtest erkannt.

Variationslauf (je Glas ±5 mm und ±3°, Korbauszug ±1 cm, 10 Versuche) über
`raeumwerk run`; auf der CPU in mehreren Prozessen auf einem Run-Verzeichnis
(`--teil K/N`, je Prozess die Versuche mit `nr % N == K`):

```bash
for k in 0 1 2; do
  scripts/raeumwerk --cpu run experimente/ausraeumen_variation.yaml --run-dir ausraeumen-1 --teil $k/3 --max-minuten 30 &
done; wait                                   # ein Versuch ~45-60 min CPU; Exit 3 = Stueck zu Ende, nochmal starten
scripts/raeumwerk report ausraeumen-1
```

Auf einem geteilten GPU-Rechner wie in §7 über `scripts/submit_gpu.sh`
(`--weiter-rc 3`). Video:

```bash
scripts/run_ausraeumen.sh --cpu demo --aufzeichnen ergebnis/ausraeumen.npz
uvx -p 3.12 --with numpy --with pyyaml --with matplotlib \
  python scripts/render_ausraeumen.py ergebnis/ausraeumen.npz --out ergebnis/ausraeumen.mp4 --standbild ergebnis/bild.png
```

Mit `RAEUMWERK_ASSETS` (ReBeL-Meshes, `scripts/fetch_assets.sh`) zeigt das
Video die igus-Optik, sonst die Kollisionsquader. Newton-Tests:
`RAEUMWERK_RUN_NEWTON=1 RAEUMWERK_NEWTON_PYTHON=<Python mit Newton> pytest -q tests/test_ausraeumen.py -k newton`.
