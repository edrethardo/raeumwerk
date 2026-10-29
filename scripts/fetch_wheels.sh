#!/usr/bin/env bash
# Laedt grosse Wheels von pypi.nvidia.com resumierbar (curl -C -) nach
# $RAEUMWERK_HOME/wheels und prueft die sha256 aus dem Paketindex.
# Grund: uv setzt abgebrochene Downloads nicht fort; ein 5-GiB-Wheel kommt auf
# einer langsamen, wackeligen Leitung so nie an. install_backends.sh nutzt den
# Ordner danach per --find-links.
#
#   scripts/fetch_wheels.sh [paket ...]   # Standard: die drei extscache-Pakete
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
VERSION=${ISAACSIM_VERSION:-6.2.0.0}
TAG=${WHEEL_TAG:-cp312-none-manylinux_2_35_x86_64}
INDEX=${NVIDIA_INDEX:-https://pypi.nvidia.com}
DEST="$RAEUMWERK_HOME/wheels"
mkdir -p "$DEST"

[ $# -gt 0 ] || set -- isaacsim-extscache-kit isaacsim-extscache-kit-sdk isaacsim-extscache-physics

for pkg in "$@"; do
  file="${pkg//-/_}-$VERSION-$TAG.whl"
  sha=$(curl -fsS -m 120 "$INDEX/$pkg/" | grep -o "$file#sha256=[0-9a-f]*" | head -1 | cut -d= -f2)
  [ -n "$sha" ] || { echo "kein Eintrag fuer $file im Index" >&2; exit 4; }
  if [ -f "$DEST/$file" ] && echo "$sha  $DEST/$file" | sha256sum -c --status; then
    echo "[$(date -Is)] $file schon da (sha256 ok)"; continue
  fi
  for try in $(seq 1 200); do
    echo "[$(date -Is)] $file Versuch $try ($(du -h "$DEST/$file.part" 2>/dev/null | cut -f1 || echo 0))"
    if curl -fsSL --retry 5 --retry-delay 10 --speed-limit 1024 --speed-time 120 \
         -C - -o "$DEST/$file.part" "$INDEX/$pkg/$file"; then
      break
    fi
    sleep 10
  done
  echo "$sha  $DEST/$file.part" | sha256sum -c --status || { echo "sha256 falsch: $file" >&2; rm -f "$DEST/$file.part"; exit 5; }
  mv "$DEST/$file.part" "$DEST/$file"
  echo "[$(date -Is)] $file fertig ($(du -h "$DEST/$file" | cut -f1))"
done
