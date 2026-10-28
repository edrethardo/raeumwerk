#!/usr/bin/env bash
# Read-only Rechner-Probe fuer Raeumwerk: schreibt nur nach ergebnis/.
set -u -o pipefail
mkdir -p ergebnis
out=ergebnis/probe.txt
{
  echo "== os";      (lsb_release -ds 2>/dev/null || cat /etc/os-release | head -2); uname -r
  echo "== cpu";     nproc; lscpu 2>/dev/null | grep "Model name"
  echo "== ram";     free -g
  echo "== disk";    df -h . /
  echo "== gpu";     nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv,noheader 2>&1
                     nvidia-smi 2>/dev/null | grep "CUDA Version"
  echo "== python";  python3 --version 2>&1; command -v uv >/dev/null && uv --version
  echo "== docker";  docker info --format '{{.DockerRootDir}} {{.ServerVersion}}' 2>&1 | head -1
  echo "== docker-gpu"
  timeout 300 docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L 2>&1 | tail -3
  echo "rc=$?"
} > "$out" 2>&1
cat "$out"
