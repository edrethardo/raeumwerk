# Bewertung: NVIDIA Isaac Sim Agent Skills und MCP-Werkzeuge

Stand: 2026-10-28, nur gelesen (Doku und README), nichts installiert, gestartet
oder ins Netz gestellt. Bewertet für den Einsatz in der Agentenumgebung (autonome
Agenten, die Tickets abarbeiten).

## Was es gibt

| Werkzeug | Was es ist | Quelle |
|---|---|---|
| **Isaac Sim Agent Skills** | ca. 40 `SKILL.md`-Anleitungen (Frontmatter + Ablauf + Skripte), die mit Isaac Sim 6.x ausgeliefert werden: im pip-Paket unter `<isaacsim-Paket>/skills/`, dazu `AGENTS.md`/`CLAUDE.md`. Zwei Schichten: *repo-native* (Build, Profiling, `isaac-sim-remote`, Web-Viewer) und *robotics-sim* (Physik, URDF/MJCF→USD, PhysX→Newton, Kameras, Sensoren, SDG, Headless-Deployment, Validator). | https://docs.isaacsim.omniverse.nvidia.com/latest/development_tools/agent_skills.html |
| **`isaac-sim-remote`** (Skill) | Steuert eine laufende Isaac-Sim-Instanz über den TCP-Socket der Erweiterung `isaacsim.code_editor.python_server` (Standard `127.0.0.1:8226`): beliebiger Python-Code im Kit-Prozess, Antwort als JSON. | https://docs.isaacsim.omniverse.nvidia.com/6.2.0/development_tools/python_server.html |
| **`isaac-sim-web-viewer`** (Skill) | WebRTC-Stream eines Containers an einen Browser (Docker Compose, NGC-Image). | Agent-Skills-Seite (s. o.) |
| **Isaac Sim MCP Server** (NVIDIA, `kit-usd-agents`) | MCP-Server (Streamable HTTP, Port 9904) mit 34 Werkzeugen für *Wissenssuche*: Erweiterungen, Codebeispiele, Settings. Semantische Suche + Reranking über NVIDIA-Cloud-Endpunkte; braucht `NVIDIA_API_KEY` (build.nvidia.com), läuft als Docker-Container. Steuert keine laufende Simulation. | https://github.com/NVIDIA-Omniverse/kit-usd-agents/blob/main/source/mcp/isaacsim_mcp/README.md |
| Community-MCPs (`omni-mcp/isaac-sim-mcp` u. a.) | Kit-Erweiterung + MCP-Server zur Steuerung der Szene per natürlicher Sprache. Nicht von NVIDIA. | https://github.com/omni-mcp/isaac-sim-mcp |

## Was für die Agentenumgebung taugt

- **Gut geeignet: die robotics-sim-Skills als Lesestoff.** `physics-simulation`,
  `urdf-mjcf-to-usd-conversion`, `physx-to-newton-conversion`,
  `isaac-sim-headless-deployment`, `isaac-sim-validator` und
  `isaac-sim-troubleshooting` passen direkt zu den Folgetickets (Szenen bauen,
  Assets importieren, headless rechnen). Sie liegen nach der pip-Installation
  lokal vor und müssen nicht aus dem Netz geholt werden. Empfehlung: einzelne
  Skills gezielt im Ticket nennen („lies `<isaacsim>/skills/physics-simulation/SKILL.md`“),
  nicht pauschal die mitgelieferte `CLAUDE.md`/`AGENTS.md` als Arbeitsanweisung
  übernehmen, weil sie mit den Agentenumgebungs-Regeln (Worktree, gpu-lock, keine Ports)
  kollidieren kann.
- **Nur mit Auflagen: `isaac-sim-remote`/Python-Server.** Praktisch, um eine
  lange laufende Instanz nicht für jeden Schritt neu zu starten (Start kostet auf
  dem 16-GB-Rechner viel RAM und Zeit). Erst einsetzen, wenn ein Ticket es
  wirklich braucht, und dann nur auf `127.0.0.1`, mit `ss -ltnp`-Beleg.
- **Kaum Nutzen: der NVIDIA-MCP-Server.** Er beantwortet Doku-Fragen, die ein
  Agent auch mit Websuche und den lokalen Skills beantworten kann, kostet einen
  API-Key, einen Container (~1,35 GB laut README) und schickt jede Anfrage an
  NVIDIA-Cloud-Dienste.
- **Nicht einsetzen: Web-Viewer/Livestream** (Ticket-Regel: keine Livestream- oder
  WebRTC-Schnittstelle).

## Sicherheitsrisiken

1. **Beliebige Codeausführung.** Der Python-Server führt jeden empfangenen Code im
   Kit-Prozess aus, ohne Authentifizierung im Standard, mit vollem Datei- und
   Netzzugriff. NVIDIA schreibt selbst: Bindung an `0.0.0.0` heißt, dass jeder
   Rechner im Netz Python ausführen kann; die echte Grenze ist eine
   Betriebssystem-Sandbox, nicht die Tool-Allowlist des Agenten. Auch auf
   `127.0.0.1` kann jeder lokale Prozess/Benutzer des Rechners den Port nutzen;
   auf dem geteilten GPU-Rechner betrifft das andere Jobs.
2. **Ports nach außen.** Die Container-Anleitungen nutzen `--network=host` bzw.
   `-p 9904:9904` (bindet auf allen Interfaces). Wenn überhaupt, dann
   `-p 127.0.0.1:9904:9904` und ohne `--network=host`.
3. **Daten an Dritte.** Der NVIDIA-MCP-Server sendet Suchanfragen an NVIDIA-Endpunkte
   (Embeddings, Reranking, LLM) und braucht einen persönlichen API-Key. Der Key
   dürfte nie ins öffentliche Repo.
4. **Prompt-Injection über Skills/Doku.** Mitgelieferte `CLAUDE.md`/`AGENTS.md`
   sind Anweisungen eines Dritten an den Agenten. Sie sind Lesestoff, keine
   Autorität über Agentenumgebungs-Regeln.
5. **Community-MCPs**: fremder Code im Kit-Prozess, ungeprüfte Wartung. Nicht
   ohne eigenes Review.

## Ergebnis

Lokale robotics-sim-Skills: ja, gezielt als Referenz. Python-Server: nur
localhost und nur, wenn ein Ticket es begründet. NVIDIA-MCP, Web-Viewer und
Community-MCPs: für Räumwerk nicht einsetzen. In diesem Ticket lief keiner
davon; der Smoke-Runner prüft bei jedem Lauf, ob ein neuer Listener außerhalb
von localhost aufgetaucht ist (siehe `docs/STATUS.md`).
