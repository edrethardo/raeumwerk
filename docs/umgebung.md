# Umgebung: Simulationsrechner für Räumwerk

Stand: 2026-10-28. Alle Werte sind mit `scripts/check_env.sh` gemessen
(Ausgabe unten). Rechnernamen, IPs und Benutzerpfade stehen nicht im Repo,
sondern in `config/local.env` (Vorlage: `config/local.env.example`).

## 1. Bestandsaufnahme Hauptrechner (geteilter GPU-Rechner)

Gemessen mit `ssh <gpu-host> 'RAEUMWERK_ROOT=<datenlaufwerk> bash -s' < scripts/check_env.sh`
vor der Installation (ein fremder GPU-Job lief parallel):

```
OS:                    Ubuntu 22.04.5 LTS
Kernel:                6.8.0-138-generic
Architektur:           x86_64
glibc:                 2.35
CPU:                   AMD Ryzen 9 5900X 12-Core Processor
CPU-Threads:           24
RAM gesamt:            15,5 GiB
RAM verfuegbar:        11,8 GiB
Swap gesamt:           16,0 GiB
Swap frei:             13,8 GiB
GPU:                   NVIDIA GeForce RTX 3090
NVIDIA-Treiber:        580.178.04
VRAM gesamt:           24576 MiB
VRAM belegt:           2041 MiB
Compute Capability:    8.6
CUDA (Treiber-API):    13.0
nvcc:                  nicht installiert
Platz /:               Groesse 278G, belegt 219G, frei 45G (84%)
Platz RAEUMWERK_ROOT:  Groesse 916G, belegt 429G, frei 441G (50%)
Docker:                29.6.1
Docker Root Dir:       /var/lib/docker (Dateisystem: /)
NVIDIA Container Toolkit: 1.19.1
python3:               3.10.12
python3.11:            nicht im PATH
python3.12:            nicht im PATH
uv:                    0.12.10
sudo ohne Passwort:    nein
TCP-Listener (nicht lo): *:22 *:8000
```

`*:22` (sshd) und `*:8000` (Socket-Aktivierung eines anderen Dienstes)
gehören nicht zu Räumwerk und waren vor der Installation da. Sie werden nicht
angefasst; der Smoke-Runner zählt nur Listener, die während eines Laufs **neu**
entstehen.

`scripts/check_env.sh` schreibt keine Dateien, maskiert konkrete
Interface-Adressen (`<iface>:port`) und gibt keinen Rechnernamen aus.

## 2. Offizielle Anforderungen und Versionen

| Produkt | Version (offiziell, geprüft 2026-10-28) | Quelle |
|---|---|---|
| Isaac Sim | **6.2.0** GA (22.10.2026, Bugfix-Release für Isaac Lab 3.0 GA; Kit SDK 110.4, Newton 1.6.1, MuJoCo 3.12.0) | https://forums.developer.nvidia.com/t/isaac-sim-6-2-general-availability/386512 |
| Isaac Lab | **3.0.0** (Release 3.0 ist Standard der Doku; Newton ist Standard-Backend, läuft ohne Isaac Sim) | https://docs.nvidia.com/isaaclab/isaac-lab/installation |
| Newton | 1.6.1 (in Isaac Sim 6.2 gepinnt); Isaac Lab 3.0 bringt sein Newton selbst mit, installierte Version siehe §4 | https://newton-physics.github.io/newton/latest/guide/installation.html |

Die geplanten Versionen (Isaac Sim 6.2, Isaac Lab 3.0) existieren so.

**Isaac Sim 6.2 Systemanforderungen** (x86_64, https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html):

| | Minimum | Hauptrechner | Bewertung |
|---|---|---|---|
| OS | Ubuntu 22.04/24.04 (22.04 *deprecated*) | 22.04.5 | ok, aber Auslaufmodell |
| CPU / Kerne | i7 7. Gen / Ryzen 5, 4 Kerne | Ryzen 9 5900X, 12 Kerne | ok |
| **RAM** | **32 GB** | **15,5 GiB + 16 GiB Swap** | **unter Minimum** |
| Speicher | 50 GB SSD | 45 GB frei auf `/`, 441 GB auf Datenlaufwerk | ok, nur auf Datenlaufwerk |
| GPU / VRAM | RTX 4080 / 16 GB, RT-Cores nötig | RTX 3090 / 24 GB (geteilt, ~10 GB durch andere GPU-Jobs möglich) | ok |
| Treiber | getestet 595.58.03; Omniverse validiert auch R580 (580.95.05) | 580.178.04 (R580) | im validierten Zweig |
| glibc (pip) | 2.35+ | 2.35 | ok |
| Python (pip) | 3.12 | 3.10 System, 3.12 per `uv` | ok mit uv |

Treiberzweige: https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html

**Isaac Lab 3.0 (Newton, ohne Isaac Sim)** (https://docs.nvidia.com/isaaclab/isaac-lab/installation):
Python 3.12, CUDA-GPU ab Turing, Treiber ≥ 580.65.06 (wegen PyTorch CUDA 13.0).
„Isaac Sim’s workstation memory requirements do not apply to a Newton-only installation.“
Headless-Newton braucht keine RT-Hardware.

### Installationswege (Isaac Sim 6.2) und Platz auf `/`

| Weg | Quelle | Platz auf `/` | Bewertung |
|---|---|---|---|
| **pip/uv** (`isaacsim[all,extscache]==6.2.0.0` von pypi.nvidia.com) | https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_python.html | **≈ 0**: venv, uv-Cache und Python liegen per `RAEUMWERK_HOME`/`UV_CACHE_DIR`/`UV_PYTHON_INSTALL_DIR` auf dem Datenlaufwerk; Kit-Caches per `RAEUMWERK_KIT_HOME` ebenfalls | **gewählt** |
| Workstation-Zip (`isaac-sim-standalone-6.2.0-linux-x86_64.zip`) | https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_workstation.html | ≈ 0 bei Entpacken aufs Datenlaufwerk, aber Kit-Caches unter `~` und Zip + Entpacktes doppelt | möglich, kein Vorteil |
| Container `nvcr.io/nvidia/isaac-sim:6.2.0` | https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_container.html | **voll auf `/`**: Docker Root Dir ist `/var/lib/docker` auf `/`; Doku nutzt `--network=host` | **verworfen** (Ticket-Regel, Daemon wird nicht umkonfiguriert) |

Lizenz: Isaac Sim verlangt die Annahme der NVIDIA Omniverse License Agreement
(https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html).
Für nicht-interaktive Läufe ist laut Doku `OMNI_KIT_ACCEPT_EULA=YES` der
vorgesehene Weg; Smoke-Skripte setzen die Variable. Kein NGC-Login, kein
Account nötig. Isaac-Sim-Pakete und -Assets kommen nicht ins Repo.

## 3. Installation (ausgeführt)

```
# aus dem Repo-Root, ohne GPU, ohne sudo; RAEUMWERK_HOME aus config/local.env
systemd-run --user --unit=raeumwerk-install-<backend> --collect -p Nice=10 -p IOSchedulingClass=idle \
  -p StandardOutput=append:<RAEUMWERK_HOME>/logs/install-<backend>.log ... \
  /bin/bash <repo>/scripts/install_backends.sh isaacsim|isaaclab
```

`scripts/install_backends.sh` ist idempotent (prüft die installierte Version)
und legt an: `venvs/isaacsim` (torch 2.11.0 cu130 + `isaacsim[all,extscache]==6.2.0.0`),
`venvs/isaaclab` (`isaaclab==3.0.0` mit Newton, ohne Isaac Sim), `uvcache/`,
`uv-python/` (CPython 3.12 von uv).

**Gemessen (Hauptrechner, 2026-10-28/29):**

| | Isaac Lab 3.0 (Newton) | Isaac Sim 6.2 (pip) |
|---|---|---|
| installierte Versionen | isaaclab 3.0.0, newton 1.6.1, warp-lang 1.17.0, torch 2.11.0+cu130 | isaacsim 6.2.0.0, torch 2.11.0+cu130, Kit 110.4 (omni.physx 110.4.4) |
| venv-Größe (`du -sh`) | 7,4 GB | 22–23 GB |
| zusätzlich | – | 6,9 GB vorab geladene Wheels (`wheels/`, nach der Installation löschbar) |
| Datenlaufwerk gesamt (`du -sh RAEUMWERK_HOME`) | 37 GB für beide zusammen | |
| Wanduhr Installation | 21:21 → 23:38 (2 h 17 min, zwei Neustarts) | 21:21 → 01:31 (4 h 10 min) |
| Platz auf `/` vorher → nachher | 45 GB → 45 GB (`df -BG`: GiB, binär, auf ganze GiB aufgerundet); Smoke-JSON nach der Installation: 47,3 GB dezimal = 44,1 GiB – gleicher Wert, andere Einheit | gleich |

Unter `~` entstand nichts Nennenswertes: Kit-, Warp- und Shader-Caches liegen per
`RAEUMWERK_KIT_HOME` auf dem Datenlaufwerk (18 MB), `~/.cache/ov` und
`~/.nvidia-omniverse` gibt es nicht.

**Probleme bei der Installation und Lösungen:**

1. **Langsame Leitung.** Der GPU-Rechner hatte nur ~0,4–2,7 MB/s nach außen und
   ins LAN (100 MB in 37 s von einem anderen Rechner im LAN). Torch allein
   (29 Pakete, ~3,5 GB) brauchte 90 min. Vorladen über einen anderen Rechner
   bringt deshalb nichts.
2. **uv setzt abgebrochene Downloads nicht fort.** `isaacsim-extscache-kit`
   (5,1 GiB) wurde nach `connection reset` mehrfach von vorn begonnen. Lösung:
   `scripts/fetch_wheels.sh` lädt die drei extscache-Wheels mit `curl -C -`,
   prüft die sha256 aus dem Index, und `install_backends.sh` nutzt sie per
   `--find-links`. Zusätzlich gelten `UV_HTTP_RETRIES=10` und `UV_HTTP_TIMEOUT=600`.
3. **Zwei parallele uv-Läufe** kollidierten am Cache-Lock für torch
   (`is another uv process running?`). Lösung: `UV_LOCK_TIMEOUT=7200`.
4. Die beiden venvs teilen sich torch nicht: Isaac Lab löst über
   `--torch-backend cu130` andere Index-URLs auf, deshalb wurden die nvidia-*-Wheels
   zweimal geladen.


## 4. Smoke-Test

`scripts/smoke_runner.py` startet `scripts/smoke_isaacsim.py` bzw.
`scripts/smoke_newton.py` mit dem Python des jeweiligen venv. Szenario:
Bodenplatte, Würfel 0,1 m startet mit Mittelpunkt auf 1,0 m, 300 Schritte à
1/60 s; `ok`, wenn die Endhöhe 0,05 m ± 0,02 m ist, der Prozess mit 0 endet,
kein Timeout eintritt und kein neuer TCP-Listener außerhalb localhost entsteht.
Gemessen von außen: Laufzeit (Wanduhr inkl. Start), RAM-Spitze (RSS-Summe des
Prozessbaums), VRAM-Spitze (nur eigene PIDs laut `nvidia-smi`), freier Platz auf
`/`. Ausgabe je Lauf: `<backend>-<UTC>.json` + `.log` in `RAEUMWERK_RUNS`
(Standard `ergebnis/`).

Start auf dem Hauptrechner nur unter einem GPU-Lock, per ssh von einem anderen
Rechner aus. Das verwendete Lock-Skript kennt (Stand 2026-10-28) nur
`acquire|release|status|wait`, kein `run`/`queue`. Die Messläufe unten liefen
über eine externe GPU-Warteschlange (nicht Teil dieses Repos). Der Lock-Weg
`scripts/remote_smoke.sh` macht Folgendes:

```
gpu-lock.sh acquire raeumwerk-smoke-<backend> -m "..." -t <min>   # alle POLL_S s, höchstens WAIT_MAX_S (Standard 4 h, sonst Exit 4)
timeout SSH_TIMEOUT_S ssh <gpu-host> 'cd <repo> && bash scripts/run_smoke_local.sh <b> <runs>'   # Standard 2 h
gpu-lock.sh release raeumwerk-smoke-<backend>     # immer, per trap
```

Ungültiges Backend: Exit 2, bevor irgendetwas gestartet wird.

pytest: `tests/test_smoke.py` prüft die Runner-Logik immer (Fake-Backend) und
ruft die echten Backends nur mit `RAEUMWERK_RUN_GPU_SMOKE=1` auf; ohne Backend
werden sie übersprungen.

**Ergebnis Hauptrechner (2026-10-29, über die GPU-Warteschlange, je 3 Läufe):**

| Lauf (JSON in `RAEUMWERK_RUNS`) | ok | Laufzeit s | RAM-Spitze MiB | VRAM-Spitze MiB (eigene PIDs) | Endhöhe m | frei auf `/` GB |
|---|---|---|---|---|---|---|
| `newton-20261029T015222Z.json` | ja | 5,72 | 491 | 318 | 0,04999 | 47,3 |
| `newton-20261029T015228Z.json` | ja | 5,57 | 491 | 318 | 0,04999 | 47,3 |
| `newton-20261029T015234Z.json` | ja | 5,78 | 491 | 318 | 0,04999 | 47,3 |
| `isaacsim-20261029T015240Z.json` (erster Start) | ja | 107,75 | 11 154 | 1 776 | 0,05000 | 47,3 |
| `isaacsim-20261029T015428Z.json` | ja | 8,98 | 5 836 | 1 592 | 0,05000 | 47,3 |
| `isaacsim-20261029T015437Z.json` | ja | 8,33 | 5 852 | 1 765 | 0,05000 | 47,3 |

- Isaac Sim: Der erste Start dauerte 105,7 s bis „app ready“ (Extensions und
  Caches wurden aufgewärmt), die Folgestarts 6,9–7,4 s. 300 PhysX-Schritte
  brauchten 0,13 s.
- Newton (XPBD, 10 Substeps): Start 1,1–1,3 s, 300 Schritte 3,4–3,6 s. Die
  erste Kernel-Kompilierung (~18 s) lief schon im vorigen Versuch und liegt im
  Warp-Cache.
- Bei keinem Lauf entstand ein Listener außerhalb von localhost
  (`listeners_non_local_new_during_run: []`). `ss -ltnp`-Mitschnitte:
  `ss-newton-20261029T015222Z.txt` (2 Schnappschüsse) und
  `ss-isaacsim-20261029T015240Z.txt` (13 Schnappschüsse). Nicht-lokal lauschten
  nur `*:22` und `*:8000`, beide gab es schon vor der Installation. Isaac Sim
  öffnete keinen Port.
- Der erste Versuch (02:45) lieferte für beide Backends korrekte Physik
  (Endhöhe 0,04999 bzw. 0,05000 m). Der Runner stürzte aber danach ab, weil
  `Sampler._stop` `threading.Thread._stop` überschrieb (`TypeError` in
  `join()` unter Python 3.10). Behoben im Runner, Regressionstest
  `test_sampler_does_not_shadow_thread_internals`. Logs ohne JSON:
  `newton-20261029T014546Z.log`, `isaacsim-20261029T014611Z.log`.
- Gestartet wurde über eine externe GPU-Warteschlange (nicht Teil dieses
  Repos), nicht über das eigene `acquire`-Pollen: Gegen eine lückenlose Kette
  fremder GPU-Jobs kam dieses nie zum Zug. Der eingereihte Befehl je Backend:
  `systemd-run --user --collect --wait --unit=raeumwerk-smoke-<b> -p RuntimeMaxSec=1800|2700 bash <REMOTE_REPO>/scripts/run_smoke_local.sh <b> 3`.


## 5. Zweiter Rechner (Laptop, 12 GB VRAM, 31 GB RAM)

Laptop ohne ssh-Zugang (Werte aus einer lesenden Probe, 2026-10-28):
Ubuntu 22.04, Kernel 6.8, i7-13850HX (28 Threads), **31 GiB RAM +
31 GiB Swap**, RTX 3500 Ada **12 GB VRAM**, Treiber 595.99 (CUDA 13.2), 177 GB
frei auf `/`, Docker 28.1 (Root Dir auf `/`, `--gpus all` geht), uv 0.12,
Python 3.10. Keine anderen GPU-Nutzer.

Was dort anders ist:

- **Kein ssh, kein GPU-Lock.** Der Lauf wird als Job auf dem Laptop gestartet:
  `bash scripts/job_isaacsim_smoke.sh` aus dem Repo-Root.
- **Pfade:** ohne `config/local.env` gelten die Standards
  `RAEUMWERK_HOME=$HOME/raeumwerk` (venvs, uv-Cache, Python) und
  `RAEUMWERK_RUNS=ergebnis/`. `RAEUMWERK_KIT_HOME` bleibt leer (Kit-Caches
  unter `~`, Platz reicht). Das Skript bricht ab, wenn `RAEUMWERK_HOME` im
  Arbeitsverzeichnis läge.
- **RAM:** 31 GiB liegt knapp unter dem offiziellen Minimum von 32 GB, aber
  doppelt so viel wie der Hauptrechner, und niemand teilt ihn. Isaac Sim ist
  dort der realistischere Kandidat.
- **VRAM:** 12 GB liegt unter dem Minimum von 16 GB. Für den Smoke (ein Würfel,
  kein Rendering-Output) unkritisch; für Folgetickets mit Kameras/vielen
  Sensoren oder vielen parallelen Envs ist es die Grenze.
- **Treiber 595.99** entspricht NVIDIAs getestetem Zweig R595 (Hauptrechner:
  R580).
- **Docker:** Root Dir liegt auch dort auf `/`; mit 177 GB frei wäre der
  Container-Weg möglich, bleibt aber wegen `--network=host` in der NVIDIA-Doku
  und für gleiche Wege auf beiden Rechnern beim pip/uv-Weg.
- Der Job installiert idempotent (Frist 2 h), führt 3 Smokes aus (je ≤ 25 min),
  hält eine Gesamtfrist von 4 h ein, schreibt `ss -ltn`-Mitschnitte und
  `zusammenfassung.json` nach `ergebnis/` und endet nur bei 3/3 ok mit 0.

**Stand Laptop-Lauf** (`bash scripts/job_isaacsim_smoke.sh`, EULA vom
Auftraggeber akzeptiert): **blockiert/läuft.** Der erste Lauf endete mit
Exit 10: Die Installation überschritt die Installationsfrist von 2 h
(`INSTALL_TIMEOUT_S=7200`), weil der Download langsam war. Ein zweiter Lauf
mit längerer Installationsfrist läuft; ein Smoke-Ergebnis vom Laptop gibt es
noch nicht.
