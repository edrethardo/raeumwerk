#!/usr/bin/env bash
# Holt die Referenzunterlagen zum ReBeL-Modell nach $RAEUMWERK_ASSETS
# (Standard $RAEUMWERK_HOME/assets) und prueft jede Datei per sha256.
# Nichts davon liegt im Repo (siehe docs/robotermodell.md):
#   * igus-Datenblatt ReBeL 6 DOF (PDF, igus-Nutzungsbedingungen, nicht
#     zur Weitergabe freigegeben)
#   * iRC_ROS (CommonplaceRobotics, Apache-2.0): ReBeL-xacro und LICENSE als
#     Vergleichsmodell fuer tests/test_rebel_kinematics.py
#
#   scripts/fetch_assets.sh            # holen + pruefen
#   RAEUMWERK_ASSETS=... pytest tests  # dann laeuft test_cpr_numbers_in_fetched_asset
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f config/local.env ]; then set -a; . config/local.env; set +a; fi
RAEUMWERK_HOME=${RAEUMWERK_HOME:-$HOME/raeumwerk}
DEST=${RAEUMWERK_ASSETS:-$RAEUMWERK_HOME/assets}

IRC_COMMIT=41701e6df3398087d217f0f478622e60f694de41
IRC=https://raw.githubusercontent.com/CommonplaceRobotics/iRC_ROS/$IRC_COMMIT
DS=https://www.igus.com/ContentData/Products/Downloads/technical%20data%20sheet%20ReBeL%206DOF_EN.pdf

# Zielpfad (relativ zu DEST) | sha256 | URL
FILES=(
  "igus/rebel_6dof_datenblatt_en.pdf|02b8d7af4a3c971ba93d29cb9cb2cd06510e1b87c2b01422bf8c0e218b12ea49|$DS"
  "irc_ros/urdf/igus_rebel_6dof_00.description.xacro|31d92942b252ae9ea8c49f885ac92ebfc452bf50750680794b113a237d1a16f8|$IRC/irc_ros_description/urdf/robots/igus_rebel_6dof_00.description.xacro"
  "irc_ros/urdf/igus_rebel_6dof_01.description.xacro|76489bd907c4d3ea7f3f1a7b50e60e4920607827a2db02e2d5383d49b030b52f|$IRC/irc_ros_description/urdf/robots/igus_rebel_6dof_01.description.xacro"
  "irc_ros/LICENSE|ffcc552b141668739a97d38f11952199a1fc155eaf81880dd5917a81a415ef9f|$IRC/LICENSE"
)

rc=0
for entry in "${FILES[@]}"; do
  IFS='|' read -r rel sha url <<< "$entry"
  f="$DEST/$rel"
  mkdir -p "$(dirname "$f")"
  if [ -f "$f" ] && echo "$sha  $f" | sha256sum -c --status; then
    echo "ok (vorhanden)  $rel"; continue
  fi
  curl -fsSL --retry 3 -m 300 -o "$f.part" "$url"
  if echo "$sha  $f.part" | sha256sum -c --status; then
    mv "$f.part" "$f"; echo "ok (geholt)     $rel"
  else
    echo "sha256 FALSCH   $rel (Quelle geaendert? docs/robotermodell.md pruefen)" >&2
    mv "$f.part" "$f.falsch"; rc=5
  fi
done
echo "Assets: $DEST"
exit $rc
