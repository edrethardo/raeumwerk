#!/usr/bin/env bash
# Bestandsaufnahme des Simulationsrechners. Gibt nur Werte auf stdout aus und
# schreibt keine Dateien. Rechnername, IPs und Benutzerpfade werden nicht
# ausgegeben, damit die Ausgabe ins oeffentliche Repo darf.
#
#   scripts/check_env.sh            # lokal
#   ssh <gpu-host> bash -s < scripts/check_env.sh
#
# Optional: RAEUMWERK_ROOT (Datenlaufwerk fuer venvs/Caches/Runs).
set -uo pipefail

line() { printf '%-22s %s\n' "$1:" "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

os=$( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" )
line "OS" "${os:-unbekannt}"
line "Kernel" "$(uname -r)"
line "Architektur" "$(uname -m)"
line "glibc" "$(ldd --version 2>/dev/null | head -1 | awk '{print $NF}')"
line "CPU" "$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
line "CPU-Threads" "$(nproc)"

mem_kib=$(awk '/^MemTotal/{print $2}' /proc/meminfo)
avail_kib=$(awk '/^MemAvailable/{print $2}' /proc/meminfo)
swap_kib=$(awk '/^SwapTotal/{print $2}' /proc/meminfo)
swapfree_kib=$(awk '/^SwapFree/{print $2}' /proc/meminfo)
gib() { awk -v k="$1" 'BEGIN{printf "%.1f GiB", k/1048576}'; }
line "RAM gesamt" "$(gib "$mem_kib")"
line "RAM verfuegbar" "$(gib "$avail_kib")"
line "Swap gesamt" "$(gib "$swap_kib")"
line "Swap frei" "$(gib "$swapfree_kib")"

if have nvidia-smi; then
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,compute_cap \
    --format=csv,noheader 2>/dev/null | while IFS=, read -r name drv tot used cc; do
      line "GPU" "$(echo "$name" | xargs)"
      line "NVIDIA-Treiber" "$(echo "$drv" | xargs)"
      line "VRAM gesamt" "$(echo "$tot" | xargs)"
      line "VRAM belegt" "$(echo "$used" | xargs)"
      line "Compute Capability" "$(echo "$cc" | xargs)"
    done
  line "CUDA (Treiber-API)" "$(nvidia-smi 2>/dev/null | grep -o 'CUDA Version: [0-9.]*' | awk '{print $3}')"
else
  line "GPU" "nvidia-smi fehlt"
fi
line "nvcc" "$(have nvcc && nvcc --version | grep -o 'release [0-9.]*' || echo 'nicht installiert')"

df_line() { df -BG --output=size,used,avail,pcent "$1" 2>/dev/null | tail -1 | awk '{print "Groesse " $1 ", belegt " $2 ", frei " $3 " (" $4 ")"}'; }
line "Platz /" "$(df_line /)"
if [ -n "${RAEUMWERK_ROOT:-}" ] && [ -d "$RAEUMWERK_ROOT" ]; then
  line "Platz RAEUMWERK_ROOT" "$(df_line "$RAEUMWERK_ROOT")"
  line "Belegt RAEUMWERK_ROOT" "$(du -sh "$RAEUMWERK_ROOT" 2>/dev/null | cut -f1)"
fi

if have docker; then
  line "Docker" "$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'Client da, Daemon nicht erreichbar')"
  root_dir=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)
  if [ -n "$root_dir" ]; then
    mnt=$(df --output=target "$root_dir" 2>/dev/null | tail -1)
    line "Docker Root Dir" "$root_dir (Dateisystem: $mnt)"
  fi
else
  line "Docker" "nicht installiert"
fi
line "NVIDIA Container Toolkit" "$(have nvidia-ctk && nvidia-ctk --version 2>/dev/null | head -1 | grep -o '[0-9][0-9.]*' | head -1 || echo 'nicht installiert')"

line "python3" "$(python3 --version 2>&1 | awk '{print $2}')"
for v in 3.11 3.12; do
  line "python$v" "$(have python$v && python$v --version 2>&1 | awk '{print $2}' || echo 'nicht im PATH')"
done
UVBIN=$(command -v uv || { [ -x "$HOME/.local/bin/uv" ] && echo "$HOME/.local/bin/uv"; })
line "uv" "$([ -n "$UVBIN" ] && "$UVBIN" --version | awk '{print $2}' || echo 'nicht installiert')"
line "sudo ohne Passwort" "$(sudo -n true 2>/dev/null && echo ja || echo nein)"

# Lauschende Ports ausserhalb von localhost (nur Anzahl + Adresse:Port, keine Prozessnamen anderer Nutzer)
if have ss; then
  # konkrete Interface-Adressen werden maskiert, damit keine IP in Ausgaben landet
  ext=$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' \
    | sed -E 's/^(0\.0\.0\.0|\[::\]|\*):/*:/; s/^[^*][^ ]*:([0-9]+)$/<iface>:\1/' | sort -u | tr '\n' ' ')
  line "TCP-Listener (nicht lo)" "${ext:-keine}"
fi
